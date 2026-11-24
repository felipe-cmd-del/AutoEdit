"""IA de visão LOCAL (CLIP, código aberto, roda na CPU da VPS — sem API).

- Relevância: o clipe combina com a subcategoria buscada?
- Rejeição: pessoa falando pra câmera, slide, thumbnail, tela, logo, texto.
- Tags automáticas: tipo de plano, pessoas, clima/cor.
- Embedding salvo por clipe -> busca semântica na biblioteca ("mão segurando cápsulas").
"""
import os, threading
import numpy as np

ENABLED = os.getenv("VISION", "1") == "1"
MODEL, PRETRAINED = os.getenv("CLIP_MODEL", "ViT-B-32"), os.getenv("CLIP_WEIGHTS", "laion2b_s34b_b79k")
MIN_RELEVANCE = float(os.getenv("MIN_RELEVANCE", 0.22))
_lock, _m = threading.Lock(), {}
_cache: dict = {}

NEGATIVES = {
    "talking_head": "a person talking to the camera, vlog, interview, podcast",
    "slide": "a presentation slide, infographic or diagram with words",
    "thumbnail": "a youtube thumbnail with big letters",
    "screen": "a screenshot of a website, app or computer screen",
    "logo": "a logo, brand intro or watermark",
    "text": "an image with subtitles, captions or written text",
    "cartoon": "a low quality cartoon or meme",
    "blank": "a blank black or white screen",
}
NEG_LIMIT = float(os.getenv("NEG_LIMIT", 0.35))
TAGS = {
    "shot": ["close-up shot", "macro shot", "medium shot", "wide shot", "aerial drone shot",
             "3d medical animation", "microscope footage", "product shot on table"],
    "people": ["no people", "one person", "two people", "a group of people", "hands only"],
    "age": ["young adult", "middle aged adult", "senior elderly person", "child", "no person"],
    "mood": ["bright and happy", "dark and moody", "clinical medical environment", "warm natural light", "kitchen or food"],
}


def _load():
    if "model" not in _m:
        with _lock:
            if "model" not in _m:
                import open_clip, torch
                torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))
                model, _, pre = open_clip.create_model_and_transforms(MODEL, pretrained=PRETRAINED)
                _m.update(model=model.eval(), pre=pre, tok=open_clip.get_tokenizer(MODEL), torch=torch)
    return _m


def text_emb(texts):
    key = tuple(texts)
    if key not in _cache:
        m = _load()
        with m["torch"].no_grad():
            e = m["model"].encode_text(m["tok"](list(texts))).float().numpy()
        _cache[key] = e / np.linalg.norm(e, axis=1, keepdims=True)
    return _cache[key]


def image_emb(images):
    m = _load()
    with m["torch"].no_grad():
        x = m["torch"].stack([m["pre"](i) for i in images])
        e = m["model"].encode_image(x).float().numpy()
    return e / np.linalg.norm(e, axis=1, keepdims=True)


def _softmax(s):
    s = np.exp((s - s.max()) * 100)
    return s / s.sum()


def analyze(images, sub_prompts):
    """Retorna dict com ok, relevance, motivo e tags. images = 3 frames do clipe."""
    if not ENABLED:
        return {"ok": True, "relevance": None, "tags": {}, "embedding": None}
    emb = image_emb(images)
    mean = emb.mean(0)
    mean /= np.linalg.norm(mean)
    pos = text_emb(tuple(f"a stock video frame of {p}" for p in sub_prompts))
    neg_keys = list(NEGATIVES)
    neg = text_emb(tuple(NEGATIVES[k] for k in neg_keys))
    relevance = float((pos @ mean).max())
    probs = _softmax(np.concatenate([pos @ mean, neg @ mean]))
    neg_probs = dict(zip(neg_keys, probs[len(pos):]))
    worst = max(neg_probs, key=neg_probs.get)
    tags = {}
    for k, labels in TAGS.items():
        tags[k] = labels[int(np.argmax(text_emb(tuple(labels)) @ mean))]
    reason = None
    if relevance < MIN_RELEVANCE:
        reason = f"pouco relevante ({relevance:.2f})"
    elif neg_probs[worst] > NEG_LIMIT:
        reason = f"rejeitado: {worst} ({neg_probs[worst]:.2f})"
    return {"ok": reason is None, "reason": reason, "relevance": round(relevance, 3),
            "tags": tags, "embedding": mean.round(4).tolist()}


def search(query, embeddings):
    q = text_emb((query,))[0]
    return np.asarray(embeddings) @ q
