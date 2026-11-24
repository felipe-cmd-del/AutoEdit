import csv, io, json, os, queue, threading, time, traceback, uuid
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.responses import FileResponse, StreamingResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import pipeline, vision
from .taxonomy import all_themes, resolve_theme, save_custom

APP_PASSWORD = os.getenv("APP_PASSWORD", "")
WORKERS = int(os.getenv("WORKERS", 2))
STATIC = os.path.join(os.path.dirname(__file__), "static")
JOBS_FILE = pipeline.DATA / "jobs.json"
SCHED_FILE = pipeline.DATA / "schedules.json"
app = FastAPI(title="B-Roll Hunter")
jobs: dict = {}
q: "queue.Queue[Job]" = queue.Queue()


class Job:
    def __init__(self, theme_text, per_sub, urls, cc_only=False, subs_filter=None, origin="manual"):
        self.id = uuid.uuid4().hex[:8]
        self.theme, subs = resolve_theme(theme_text)
        self.subs = {k: v for k, v in subs.items() if not subs_filter or k in subs_filter} or subs
        self.per_sub, self.urls, self.cc_only, self.origin = per_sub, urls, cc_only, origin
        self.status, self.clips_saved, self.rejected, self.logs = "na fila", 0, 0, []
        self.created, self.goal, self.cancel = time.time(), 0, False
        self._l = threading.Lock()

    def add(self, n):
        with self._l:
            self.clips_saved += n

    def done(self):
        return self.cancel or self.clips_saved >= self.goal

    def log(self, msg):
        self.logs.append(time.strftime("%H:%M:%S ") + msg)
        self.logs = self.logs[-300:]

    def view(self):
        return {"id": self.id, "theme": self.theme, "subs": list(self.subs), "status": self.status,
                "clips_saved": self.clips_saved, "rejected": self.rejected, "logs": self.logs[-80:],
                "created": self.created, "origin": self.origin}


def persist():
    pipeline._write(JOBS_FILE, [j.view() for j in sorted(jobs.values(), key=lambda j: -j.created)[:50]])


def run(job: Job):
    job.status = "rodando"
    job.log(f"Tema: {job.theme} → {', '.join(job.subs)}")
    pool = ThreadPoolExecutor(WORKERS)
    for sub, keywords in job.subs.items():
        job.goal = job.clips_saved + job.per_sub
        for kw in keywords:
            if job.done():
                break
            job.log(f"[{sub}] buscando: {kw}")
            results = pipeline.search(kw, 10, job.cc_only)
            job.log(f"  {len(results)} vídeos encontrados")
            list(pool.map(lambda s: None if job.done() else
                          pipeline.process_source(s, job.theme, sub, kw, job, keywords), results))
            persist()
        job.log(f"[{sub}] {job.clips_saved} clipes até agora")
    for url in job.urls:
        job.log(f"[links] {url}")
        job.goal = job.clips_saved + 200
        srcs = pipeline.expand_url(url)
        prompts = [p for v in job.subs.values() for p in v]
        list(pool.map(lambda s: pipeline.process_source(s, job.theme, "links_manuais", "manual", job, prompts), srcs))
    pool.shutdown()
    pipeline.sync_drive(job.log)
    job.status = "cancelado" if job.cancel else "concluído"
    job.log(f"Fim: {job.clips_saved} salvos, {job.rejected} trechos rejeitados pela curadoria")
    persist()


def worker():
    while True:
        job = q.get()
        try:
            run(job)
        except Exception:
            job.log("ERRO: " + traceback.format_exc()[-600:])
            job.status = "erro"
            persist()


def scheduler():
    """Agendamentos: roda temas automaticamente a cada N horas."""
    while True:
        scheds = pipeline._read(SCHED_FILE, [])
        now, changed = time.time(), False
        for s in scheds:
            if s.get("enabled", True) and now - s.get("last_run", 0) >= s["every_hours"] * 3600:
                j = Job(s["theme"], s["per_sub"], [], s.get("cc_only", False), origin="agendado")
                jobs[j.id] = j
                q.put(j)
                s["last_run"], changed = now, True
        if changed:
            pipeline._write(SCHED_FILE, scheds)
        time.sleep(60)


threading.Thread(target=worker, daemon=True).start()
threading.Thread(target=scheduler, daemon=True).start()


def auth(token):
    if APP_PASSWORD and token != APP_PASSWORD:
        raise HTTPException(401, "senha inválida")


# ---------------- API ----------------
class JobIn(BaseModel):
    theme: str
    per_sub: int = 5
    urls: list[str] = []
    cc_only: bool = False
    subs: list[str] = []


class ThemeIn(BaseModel):
    name: str
    aliases: list[str] = []
    subs: dict[str, list[str]]


class SchedIn(BaseModel):
    theme: str
    per_sub: int = 3
    every_hours: float = 24
    cc_only: bool = False


@app.get("/api/themes")
def themes(x_token: str = Header("")):
    auth(x_token)
    return all_themes()


@app.post("/api/themes")
def add_theme(body: ThemeIn, x_token: str = Header("")):
    auth(x_token)
    save_custom(body.name, body.aliases, body.subs)
    return {"ok": True}


@app.post("/api/jobs")
def create_job(body: JobIn, x_token: str = Header("")):
    auth(x_token)
    if not body.theme.strip():
        raise HTTPException(400, "informe um tema")
    job = Job(body.theme, max(1, min(body.per_sub, 50)), [u.strip() for u in body.urls if u.strip()],
              body.cc_only, body.subs)
    jobs[job.id] = job
    q.put(job)
    return job.view()


@app.post("/api/jobs/{jid}/cancel")
def cancel_job(jid: str, x_token: str = Header("")):
    auth(x_token)
    if jid in jobs:
        jobs[jid].cancel = True
    return {"ok": True}


@app.get("/api/jobs")
def list_jobs(x_token: str = Header("")):
    auth(x_token)
    live = sorted((j.view() for j in jobs.values()), key=lambda j: -j["created"])
    ids = {j["id"] for j in live}
    old = [j for j in pipeline._read(JOBS_FILE, []) if j["id"] not in ids]
    return live + old[:20]


@app.get("/api/catalog")
def catalog(x_token: str = Header(""), theme: str = "", sub: str = "", orientation: str = "",
            q_: str = Query("", alias="q"), limit: int = 200):
    auth(x_token)
    cat = pipeline.load_catalog()
    clips = [c for c in cat["clips"] if (not theme or c["theme"] == theme) and (not sub or c["subcategory"] == sub)
             and (not orientation or c["orientation"] == orientation)]
    if q_ and vision.ENABLED:  # busca semântica local
        emb = pipeline.load_emb()
        clips = [c for c in clips if c["id"] in emb]
        if clips:
            scores = vision.search(q_, [emb[c["id"]] for c in clips])
            clips = [c for _, c in sorted(zip(scores, clips), key=lambda x: -x[0])]
    else:
        clips = sorted(clips, key=lambda c: -c["created_at"])
    return {"total": len(cat["clips"]), "rejected": cat.get("rejected", 0), "clips": clips[:limit]}


@app.delete("/api/clips/{cid}")
def remove_clip(cid: str, x_token: str = Header("")):
    auth(x_token)
    return {"ok": pipeline.delete_clip(cid)}


@app.post("/api/clips/{cid}/rating/{stars}")
def rate(cid: str, stars: int, x_token: str = Header("")):
    auth(x_token)
    with pipeline._lock:
        c = pipeline.load_catalog()
        for x in c["clips"]:
            if x["id"] == cid:
                x["rating"] = max(0, min(5, stars))
        pipeline.save_catalog(c)
    return {"ok": True}


@app.get("/api/export.csv")
def export_csv(token: str = ""):
    auth(token)
    clips = pipeline.load_catalog()["clips"]
    buf = io.StringIO()
    cols = ["id", "file", "file_vertical", "theme", "subcategory", "keyword", "duration", "width", "height",
            "orientation", "relevance", "rating", "motion", "source_url", "source_start"]
    w = csv.DictWriter(buf, fieldnames=cols + ["tags"], extrasaction="ignore")
    w.writeheader()
    for c in clips:
        w.writerow({**c, "tags": json.dumps(c.get("tags", {}), ensure_ascii=False)})
    return PlainTextResponse(buf.getvalue(), media_type="text/csv")


@app.get("/api/schedules")
def get_sched(x_token: str = Header("")):
    auth(x_token)
    return pipeline._read(SCHED_FILE, [])


@app.post("/api/schedules")
def add_sched(body: SchedIn, x_token: str = Header("")):
    auth(x_token)
    s = pipeline._read(SCHED_FILE, [])
    s.append({**body.model_dump(), "id": uuid.uuid4().hex[:6], "last_run": 0, "enabled": True})
    pipeline._write(SCHED_FILE, s)
    return s


@app.delete("/api/schedules/{sid}")
def del_sched(sid: str, x_token: str = Header("")):
    auth(x_token)
    s = [x for x in pipeline._read(SCHED_FILE, []) if x["id"] != sid]
    pipeline._write(SCHED_FILE, s)
    return s


@app.get("/thumb/{cid}.jpg")
def thumb(cid: str):
    p = pipeline.THUMBS / f"{os.path.basename(cid)}.jpg"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


@app.get("/media/{path:path}")
def media(path: str, token: str = ""):
    auth(token)
    p = (pipeline.LIB / path).resolve()
    if not str(p).startswith(str(pipeline.LIB.resolve())) or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
