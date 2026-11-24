"""Busca, download, corte por cena, curadoria local (sem API) e envio ao Drive."""
import hashlib, json, os, re, shutil, subprocess, tempfile, threading, time
from pathlib import Path

import numpy as np
import pytesseract
from PIL import Image
import yt_dlp

from .taxonomy import GENERIC_SUFFIX

DATA = Path(os.getenv("DATA_DIR", "/data"))
LIB = DATA / "library"
CATALOG = LIB / "catalog.json"
COOKIES = DATA / "cookies.txt"
RCLONE_REMOTE = os.getenv("RCLONE_REMOTE", "")  # ex: gdrive:B-Rolls
CLIP_MIN, CLIP_MAX = float(os.getenv("CLIP_MIN", 3)), float(os.getenv("CLIP_MAX", 8))
MAX_SOURCE_MIN = float(os.getenv("MAX_SOURCE_MINUTES", 15))
KEEP_LOCAL = os.getenv("KEEP_LOCAL", "0") == "1"
_lock = threading.Lock()


# ---------------- catálogo ----------------
def load_catalog():
    if CATALOG.exists():
        return json.loads(CATALOG.read_text())
    return {"clips": [], "seen_sources": []}


def save_catalog(cat):
    LIB.mkdir(parents=True, exist_ok=True)
    tmp = CATALOG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cat, ensure_ascii=False, indent=1))
    tmp.replace(CATALOG)


# ---------------- busca/download ----------------
def _ydl_opts(**extra):
    o = {"quiet": True, "no_warnings": True, "noplaylist": True}
    if COOKIES.exists():
        o["cookiefile"] = str(COOKIES)
    o.update(extra)
    return o


def search(query, n):
    q = f"ytsearch{n}:{query}{GENERIC_SUFFIX}"
    with yt_dlp.YoutubeDL(_ydl_opts(extract_flat=True)) as y:
        info = y.extract_info(q, download=False)
    out = []
    for e in info.get("entries") or []:
        d = e.get("duration") or 0
        if d and (d < CLIP_MIN or d > MAX_SOURCE_MIN * 60):
            continue
        out.append({"url": e.get("url") or f"https://www.youtube.com/watch?v={e['id']}",
                    "id": e.get("id"), "title": e.get("title", "")})
    return out


def download(url, workdir):
    opts = _ydl_opts(
        outtmpl=str(workdir / "src.%(ext)s"),
        format="bv*[height<=1080][ext=mp4]/bv*[height<=1080]/b[height<=1080]/b",
        merge_output_format="mp4",
    )
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)
    files = list(workdir.glob("src.*"))
    if not files:
        raise RuntimeError("download falhou")
    return files[0], info


# ---------------- análise local ----------------
def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True)
    j = json.loads(r.stdout)
    s = j["streams"][0]
    return s["width"], s["height"], float(j["format"]["duration"])


def scene_cuts(path, threshold=0.3):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf",
                        f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def segments(duration, cuts):
    bounds = [0.0] + [c for c in cuts if 0 < c < duration] + [duration]
    segs = []
    for a, b in zip(bounds, bounds[1:]):
        a, b = a + 0.2, b - 0.2  # margem para evitar transições
        while b - a >= CLIP_MIN:
            end = min(a + CLIP_MAX, b)
            segs.append((a, end))
            a = end
    return segs


def frame(path, t, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                    "-vf", "scale=640:-2", str(out)], check=True)
    return Image.open(out).convert("RGB")


def has_text(img):
    """OCR local (Tesseract): rejeita frames com palavras legíveis."""
    d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config="--psm 11")
    words = [w for w, c in zip(d["text"], d["conf"])
             if len(w.strip()) >= 3 and float(c) > 65 and any(ch.isalpha() for ch in w)]
    return len(words) >= 2


def quality_ok(img):
    a = np.asarray(img.convert("L"), dtype=np.float32)
    if a.mean() < 25 or a.mean() > 235:
        return False  # tela preta/branca
    gy, gx = np.gradient(a)
    return (gx ** 2 + gy ** 2).var() > 40  # nitidez mínima


def ahash(img):
    a = np.asarray(img.convert("L").resize((16, 16)), dtype=np.float32)
    return "".join("1" if v else "0" for v in (a > a.mean()).flatten())


def hamming(a, b):
    return sum(x != y for x, y in zip(a, b))


# ---------------- pipeline de um vídeo ----------------
def process_source(src, theme, sub, keyword, job):
    cat = load_catalog()
    if src["url"] in cat["seen_sources"]:
        return 0
    known = [c["hash"] for c in cat["clips"]]
    saved = 0
    with tempfile.TemporaryDirectory(dir=DATA) as td:
        td = Path(td)
        try:
            path, info = download(src["url"], td)
        except Exception as e:
            job.log(f"  ✗ download: {str(e)[:120]}")
            return 0
        w, h, dur = probe(path)
        segs = segments(dur, scene_cuts(path))
        job.log(f"  {len(segs)} trechos candidatos em '{src['title'][:60]}'")
        for i, (a, b) in enumerate(segs):
            if job.clips_saved >= job.target:
                break
            frames = [frame(path, t, td / f"f{i}_{k}.jpg") for k, t in enumerate((a + 0.1, (a + b) / 2, b - 0.1))]
            if not all(quality_ok(f) for f in frames):
                continue
            if any(has_text(f) for f in frames):
                continue
            hsh = ahash(frames[1])
            if any(hamming(hsh, k) < 20 for k in known):
                continue  # duplicado
            out_dir = LIB / theme / sub
            out_dir.mkdir(parents=True, exist_ok=True)
            cid = hashlib.sha1(f"{src['url']}{a}".encode()).hexdigest()[:10]
            name = f"{theme}_{sub}_{cid}.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.2f}", "-i", str(path), "-t", f"{b - a:.2f}",
                            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_dir / name)], check=True)
            clip = {
                "id": cid, "file": f"{theme}/{sub}/{name}", "theme": theme, "subcategory": sub,
                "keyword": keyword, "duration": round(b - a, 2), "width": w, "height": h,
                "orientation": "vertical" if h > w else ("square" if h == w else "horizontal"),
                "source_url": src["url"], "source_title": src["title"],
                "uploader": info.get("uploader"), "hash": hsh, "created_at": int(time.time()),
            }
            with _lock:
                c = load_catalog()
                c["clips"].append(clip)
                save_catalog(c)
            known.append(hsh)
            saved += 1
            job.clips_saved += 1
    with _lock:
        c = load_catalog()
        c["seen_sources"].append(src["url"])
        save_catalog(c)
    return saved


def sync_drive(job):
    if not RCLONE_REMOTE:
        job.log("Google Drive não configurado (RCLONE_REMOTE vazio) — clipes ficam só na VPS.")
        return
    job.log(f"Enviando para {RCLONE_REMOTE} ...")
    args = ["rclone", "copy" if KEEP_LOCAL else "move", str(LIB), RCLONE_REMOTE,
            "--config", str(DATA / "rclone.conf"), "--exclude", "catalog.tmp"]
    if not KEEP_LOCAL:
        args += ["--exclude", "catalog.json"]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        job.log("✗ rclone: " + r.stderr[-300:])
        return
    if not KEEP_LOCAL:
        subprocess.run(["rclone", "copy", str(CATALOG), RCLONE_REMOTE, "--config", str(DATA / "rclone.conf")])
        for d in LIB.iterdir():
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
    job.log("✓ Drive atualizado (pastas por tema/subcategoria + catalog.json)")
