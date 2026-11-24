"""Busca, download, corte por cena, curadoria local e envio ao Drive."""
import hashlib, json, os, re, subprocess, tempfile, threading, time, urllib.parse
from pathlib import Path

import numpy as np
import pytesseract
from PIL import Image
import yt_dlp

from . import vision

DATA = Path(os.getenv("DATA_DIR", "/data"))
LIB = DATA / "library"
THUMBS = DATA / "thumbs"
CATALOG = LIB / "catalog.json"
EMB = DATA / "embeddings.json"
COOKIES = DATA / "cookies.txt"
RCONF = DATA / "rclone.conf"
RCLONE_REMOTE = os.getenv("RCLONE_REMOTE", "")
CLIP_MIN, CLIP_MAX = float(os.getenv("CLIP_MIN", 3)), float(os.getenv("CLIP_MAX", 8))
MAX_SOURCE_MIN = float(os.getenv("MAX_SOURCE_MINUTES", 15))
MAX_HEIGHT = int(os.getenv("MAX_HEIGHT", 2160))
MIN_HEIGHT = int(os.getenv("MIN_HEIGHT", 720))
MAX_CLIPS_PER_SOURCE = int(os.getenv("MAX_CLIPS_PER_SOURCE", 6))
VERTICAL_COPY = os.getenv("VERTICAL_COPY", "1") == "1"
KEEP_LOCAL = os.getenv("KEEP_LOCAL", "1") == "1"
SEARCH_SUFFIXES = [s for s in os.getenv("SEARCH_SUFFIXES", " stock footage| b roll 4k").split("|")]
_lock = threading.RLock()

YT_CC = "EgIwAQ%3D%3D"  # filtro Creative Commons do YouTube


# ---------------- catálogo ----------------
def _read(p, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def _write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False))
    tmp.replace(p)


def load_catalog():
    return _read(CATALOG, {"clips": [], "seen_sources": [], "rejected": 0})


def save_catalog(cat):
    _write(CATALOG, cat)


def load_emb():
    return _read(EMB, {})


def add_clip(clip, embedding):
    with _lock:
        c = load_catalog()
        c["clips"].append(clip)
        save_catalog(c)
        if embedding:
            e = load_emb()
            e[clip["id"]] = embedding
            _write(EMB, e)


def delete_clip(cid):
    with _lock:
        c = load_catalog()
        clip = next((x for x in c["clips"] if x["id"] == cid), None)
        if not clip:
            return False
        c["clips"] = [x for x in c["clips"] if x["id"] != cid]
        c.setdefault("blocked", []).append(clip["hash"])  # nunca baixar de novo
        save_catalog(c)
        e = load_emb()
        e.pop(cid, None)
        _write(EMB, e)
    for f in [clip["file"], clip.get("file_vertical")]:
        if f:
            (LIB / f).unlink(missing_ok=True)
            if RCLONE_REMOTE:
                subprocess.run(["rclone", "deletefile", f"{RCLONE_REMOTE}/{f}", "--config", str(RCONF)],
                               capture_output=True)
    (THUMBS / f"{cid}.jpg").unlink(missing_ok=True)
    return True


def mark_seen(url, rejected=0):
    with _lock:
        c = load_catalog()
        c["seen_sources"].append(url)
        c["rejected"] = c.get("rejected", 0) + rejected
        save_catalog(c)


# ---------------- busca/download ----------------
def _ydl_opts(**extra):
    o = {"quiet": True, "no_warnings": True, "noplaylist": True, "socket_timeout": 30, "retries": 3}
    if COOKIES.exists():
        o["cookiefile"] = str(COOKIES)
    o.update(extra)
    return o


def search(query, n, cc_only=False):
    """Busca no YouTube com variações da palavra-chave (stock footage, b roll 4k)."""
    out, seen = [], set()
    per = max(2, n // len(SEARCH_SUFFIXES))
    for suf in SEARCH_SUFFIXES:
        q = query + suf
        if cc_only:
            target = f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}&sp={YT_CC}"
            opts = _ydl_opts(extract_flat=True, playlistend=per)
        else:
            target, opts = f"ytsearch{per}:{q}", _ydl_opts(extract_flat=True)
        try:
            with yt_dlp.YoutubeDL(opts) as y:
                info = y.extract_info(target, download=False)
        except Exception:
            continue
        for e in info.get("entries") or []:
            d, vid = e.get("duration") or 0, e.get("id")
            if not vid or vid in seen or (d and (d < CLIP_MIN or d > MAX_SOURCE_MIN * 60)):
                continue
            if "/shorts/" in (e.get("url") or ""):
                pass  # shorts são aceitos (verticais)
            seen.add(vid)
            out.append({"url": e.get("url") or f"https://www.youtube.com/watch?v={vid}",
                        "id": vid, "title": e.get("title", "")})
    return out


def expand_url(url, limit=15):
    """Link único ou perfil/canal/hashtag (TikTok, Instagram, YouTube) -> lista de vídeos."""
    try:
        with yt_dlp.YoutubeDL(_ydl_opts(extract_flat=True, noplaylist=False, playlistend=limit)) as y:
            info = y.extract_info(url, download=False)
    except Exception:
        return [{"url": url, "title": url}]
    if info.get("entries"):
        return [{"url": e.get("url") or e.get("webpage_url"), "title": e.get("title") or ""}
                for e in info["entries"] if e and (e.get("url") or e.get("webpage_url"))][:limit]
    return [{"url": url, "title": info.get("title") or url}]


def download(url, workdir):
    opts = _ydl_opts(
        outtmpl=str(workdir / "src.%(ext)s"),
        format=f"bv*[height<={MAX_HEIGHT}][ext=mp4]/bv*[height<={MAX_HEIGHT}]/b[height<={MAX_HEIGHT}]/b",
        merge_output_format="mp4",
    )
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)
    files = [f for f in workdir.glob("src.*") if f.suffix not in (".part", ".ytdl")]
    if not files:
        raise RuntimeError("download falhou")
    return files[0], info


# ---------------- análise local ----------------
def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True)
    j = json.loads(r.stdout)
    s = j["streams"][0]
    num, den = (s.get("r_frame_rate") or "30/1").split("/")
    return s["width"], s["height"], float(j["format"]["duration"]), round(float(num) / float(den or 1), 2)


def scene_cuts(path, threshold=0.3):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf",
                        f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def segments(duration, cuts):
    bounds = [0.0] + [c for c in cuts if 0 < c < duration] + [duration]
    segs = []
    for a, b in zip(bounds, bounds[1:]):
        a, b = a + 0.25, b - 0.25  # margem para evitar transições
        while b - a >= CLIP_MIN:
            end = min(a + CLIP_MAX, b)
            if b - end < CLIP_MIN:
                end = b if b - a <= CLIP_MAX * 1.4 else end
            segs.append((a, end))
            a = end
    # pula intro/outro (logos, "inscreva-se")
    if duration > 40:
        segs = [s for s in segs if s[0] > 4 and s[1] < duration - 6]
    return segs


def frame(path, t, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                    "-vf", "scale=640:-2", "-q:v", "3", str(out)], check=True)
    return Image.open(out).convert("RGB")


def has_text(img):
    """OCR local (Tesseract): rejeita frames com palavras legíveis."""
    d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config="--psm 11")
    words = [w for w, c in zip(d["text"], d["conf"])
             if len(w.strip()) >= 3 and float(c) > 65 and sum(ch.isalpha() for ch in w) >= 3]
    return len(words) >= 2


def corner_logo(img):
    """Detecta marca d'água fixa: canto com bordas fortes que não mudam entre frames (checado fora)."""
    a = np.asarray(img.convert("L"), dtype=np.float32)
    h, w = a.shape
    ch, cw = h // 6, w // 5
    return [a[:ch, :cw], a[:ch, -cw:], a[-ch:, :cw], a[-ch:, -cw:]]


def static_watermark(frames):
    c1, c2 = corner_logo(frames[0]), corner_logo(frames[-1])
    full = np.abs(np.asarray(frames[0].convert("L"), np.float32) - np.asarray(frames[-1].convert("L"), np.float32)).mean()
    if full < 8:
        return False  # cena parada: não dá pra distinguir
    for x, y in zip(c1, c2):
        gy, gx = np.gradient(x)
        edges = (np.abs(gx) + np.abs(gy)).mean()
        if np.abs(x - y).mean() < 2.5 and edges > 12:
            return True
    return False


def quality(img):
    a = np.asarray(img.convert("L"), dtype=np.float32)
    gy, gx = np.gradient(a)
    sharp = float((gx ** 2 + gy ** 2).var())
    return {"brightness": float(a.mean()), "sharpness": sharp,
            "ok": 25 < a.mean() < 235 and sharp > 40}


def motion(frames):
    a = [np.asarray(f.convert("L").resize((160, 90)), np.float32) for f in frames]
    return round(float(np.mean([np.abs(x - y).mean() for x, y in zip(a, a[1:])])), 2)


def palette(img, k=4):
    p = img.resize((64, 36)).quantize(colors=k).convert("RGB")
    cols = sorted(p.getcolors(64 * 36), reverse=True)[:k]
    return ["#%02x%02x%02x" % c for _, c in cols]


def ahash(img):
    a = np.asarray(img.convert("L").resize((16, 16)), dtype=np.float32)
    return "".join("1" if v else "0" for v in (a > a.mean()).flatten())


def hamming(a, b):
    return sum(x != y for x, y in zip(a, b))


def encode(src, a, b, out, vf=None):
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.2f}", "-i", str(src), "-t", f"{b - a:.2f}", "-an"]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)


# ---------------- pipeline de um vídeo ----------------
def process_source(src, theme, sub, keyword, job, prompts):
    cat = load_catalog()
    if src["url"] in cat["seen_sources"]:
        return 0
    known = [c["hash"] for c in cat["clips"]] + cat.get("blocked", [])
    saved, rejected = 0, 0
    with tempfile.TemporaryDirectory(dir=DATA) as td:
        td = Path(td)
        try:
            path, info = download(src["url"], td)
        except Exception as e:
            job.log(f"  ✗ download: {str(e)[:120]}")
            mark_seen(src["url"])
            return 0
        w, h, dur, fps = probe(path)
        if min(w, h) < MIN_HEIGHT * 0.99 and max(w, h) < 1280:
            job.log(f"  ✗ resolução baixa ({w}x{h}) — '{src['title'][:50]}'")
            mark_seen(src["url"])
            return 0
        segs = segments(dur, scene_cuts(path))
        job.log(f"  {len(segs)} trechos em '{(info.get('title') or src['title'])[:60]}' ({w}x{h})")
        for i, (a, b) in enumerate(segs):
            if job.done() or saved >= MAX_CLIPS_PER_SOURCE:
                break
            frames = [frame(path, t, td / f"f{i}_{k}.jpg") for k, t in enumerate((a + 0.15, (a + b) / 2, b - 0.15))]
            q = [quality(f) for f in frames]
            if not all(x["ok"] for x in q) or any(has_text(f) for f in frames) or static_watermark(frames):
                rejected += 1
                continue
            hsh = ahash(frames[1])
            with _lock:
                if any(hamming(hsh, k) < 22 for k in known):
                    rejected += 1
                    continue
                known.append(hsh)
            v = vision.analyze(frames, prompts)
            if not v["ok"]:
                rejected += 1
                continue
            cid = hashlib.sha1(f"{src['url']}{a:.2f}".encode()).hexdigest()[:10]
            rel = f"{theme}/{sub}/{theme}_{sub}_{cid}.mp4"
            (LIB / rel).parent.mkdir(parents=True, exist_ok=True)
            encode(path, a, b, LIB / rel)
            clip = {
                "id": cid, "file": rel, "theme": theme, "subcategory": sub, "keyword": keyword,
                "duration": round(b - a, 2), "width": w, "height": h, "fps": fps,
                "orientation": "vertical" if h > w else ("square" if h == w else "horizontal"),
                "relevance": v["relevance"], "tags": v["tags"], "motion": motion(frames),
                "sharpness": round(q[1]["sharpness"]), "brightness": round(q[1]["brightness"]),
                "colors": palette(frames[1]),
                "source_url": info.get("webpage_url") or src["url"], "source_title": info.get("title") or src["title"],
                "source_start": round(a, 2), "uploader": info.get("uploader"), "license": info.get("license"),
                "hash": hsh, "created_at": int(time.time()), "rating": 0,
            }
            if VERTICAL_COPY and w > h:
                vrel = rel.replace(".mp4", "_9x16.mp4")
                encode(path, a, b, LIB / vrel, "crop=ih*9/16:ih,scale=1080:1920:flags=lanczos")
                clip["file_vertical"] = vrel
            THUMBS.mkdir(parents=True, exist_ok=True)
            frames[1].save(THUMBS / f"{cid}.jpg", quality=80)
            add_clip(clip, v["embedding"])
            saved += 1
            job.add(1)
    mark_seen(src["url"], rejected)
    if rejected:
        job.rejected += rejected
    return saved


def sync_drive(log):
    if not RCLONE_REMOTE:
        log("Google Drive não configurado (RCLONE_REMOTE vazio) — clipes ficam só na VPS.")
        return
    log(f"Enviando para {RCLONE_REMOTE} ...")
    args = ["rclone", "copy" if KEEP_LOCAL else "move", str(LIB), RCLONE_REMOTE, "--config", str(RCONF),
            "--exclude", "*.tmp", "--exclude", "catalog.json", "--transfers", "4"]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        log("✗ rclone: " + r.stderr[-300:])
        return
    subprocess.run(["rclone", "copy", str(CATALOG), RCLONE_REMOTE, "--config", str(RCONF)])
    log("✓ Drive atualizado (pastas por tema/subcategoria + catalog.json)")
