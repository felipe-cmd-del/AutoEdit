import os, queue, threading, time, traceback, uuid
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import pipeline
from .taxonomy import TAXONOMY, resolve_theme

APP_PASSWORD = os.getenv("APP_PASSWORD", "")
STATIC = os.path.join(os.path.dirname(__file__), "static")
app = FastAPI(title="B-Roll Hunter")
jobs: dict = {}
q: "queue.Queue[Job]" = queue.Queue()


class Job:
    def __init__(self, theme_text, per_sub, urls):
        self.id = uuid.uuid4().hex[:8]
        self.theme, self.subs = resolve_theme(theme_text)
        self.per_sub, self.urls = per_sub, urls
        self.target = per_sub * len(self.subs) + 50 * len(urls)
        self.status, self.clips_saved, self.logs, self.created = "na fila", 0, [], time.time()

    def log(self, msg):
        self.logs.append(time.strftime("%H:%M:%S ") + msg)
        self.logs = self.logs[-300:]

    def view(self):
        return {"id": self.id, "theme": self.theme, "subs": list(self.subs), "status": self.status,
                "clips_saved": self.clips_saved, "logs": self.logs[-60:], "created": self.created}


def run(job: Job):
    job.status = "rodando"
    job.log(f"Tema: {job.theme} → subcategorias: {', '.join(job.subs)}")
    for sub, keywords in job.subs.items():
        goal = job.clips_saved + job.per_sub
        for kw in keywords:
            if job.clips_saved >= goal:
                break
            job.log(f"[{sub}] buscando: {kw}")
            try:
                results = pipeline.search(kw, 6)
            except Exception as e:
                job.log(f"  ✗ busca: {str(e)[:120]}")
                continue
            for src in results:
                if job.clips_saved >= goal:
                    break
                n = pipeline.process_source(src, job.theme, sub, kw, job)
                if n:
                    job.log(f"  ✓ +{n} clipes ({job.clips_saved} no total)")
    for url in job.urls:  # links manuais (TikTok, Instagram, YouTube...)
        job.log(f"[links] {url}")
        job.target = job.clips_saved + 50
        pipeline.process_source({"url": url, "title": url}, job.theme, "links_manuais", "manual", job)
    pipeline.sync_drive(job)
    job.status = "concluído"


def worker():
    while True:
        job = q.get()
        try:
            run(job)
        except Exception:
            job.log("ERRO: " + traceback.format_exc()[-500:])
            job.status = "erro"


threading.Thread(target=worker, daemon=True).start()


def auth(token):
    if APP_PASSWORD and token != APP_PASSWORD:
        raise HTTPException(401, "senha inválida")


class JobIn(BaseModel):
    theme: str
    per_sub: int = 5
    urls: list[str] = []


@app.get("/api/themes")
def themes(x_token: str = Header("")):
    auth(x_token)
    return {k: {"aliases": v["aliases"], "subs": v["subs"]} for k, v in TAXONOMY.items()}


@app.post("/api/jobs")
def create_job(body: JobIn, x_token: str = Header("")):
    auth(x_token)
    if not body.theme.strip():
        raise HTTPException(400, "informe um tema")
    job = Job(body.theme, max(1, min(body.per_sub, 30)), [u.strip() for u in body.urls if u.strip()])
    jobs[job.id] = job
    q.put(job)
    return job.view()


@app.get("/api/jobs")
def list_jobs(x_token: str = Header("")):
    auth(x_token)
    return sorted((j.view() for j in jobs.values()), key=lambda j: -j["created"])


@app.get("/api/catalog")
def catalog(x_token: str = Header("")):
    auth(x_token)
    return pipeline.load_catalog()


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
