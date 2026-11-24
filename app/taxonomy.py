"""Taxonomia de B-rolls para o mercado de nutracêuticos.

Estrutura: TEMA -> SUBCATEGORIA -> lista de buscas (em inglês, que retorna
muito mais B-roll de qualidade). Para adicionar temas, edite este arquivo.
Cada clipe baixado é categorizado pela subcategoria cuja busca o encontrou.
"""
import json, os, unicodedata
from pathlib import Path

CUSTOM = Path(os.getenv("DATA_DIR", "/data")) / "themes_custom.json"

TAXONOMY = {
    "diabetes": {
        "aliases": ["diabete", "glicose", "acucar no sangue", "insulina", "glicemia"],
        "subs": {
            "medicao_glicose": ["glucometer blood sugar test finger", "glucose meter close up", "continuous glucose monitor arm"],
            "insulina": ["insulin pen injection close up", "insulin syringe vial"],
            "alimentacao": ["sugar cubes close up slow motion", "healthy low carb meal preparation", "sweets desserts sugar close up"],
            "medico_paciente": ["doctor talking with diabetic patient", "doctor checking blood test results"],
            "sintomas": ["tired person fatigue at home", "person thirsty drinking water", "blurry vision person rubbing eyes"],
        },
    },
    "emagrecimento": {
        "aliases": ["obesidade", "perder peso", "peso", "gordura", "dieta", "barriga"],
        "subs": {
            "balanca_medidas": ["person stepping on scale", "measuring waist tape measure", "loose pants weight loss"],
            "alimentacao_saudavel": ["healthy salad preparation close up", "fresh vegetables cutting kitchen", "meal prep healthy food"],
            "exercicio": ["woman jogging park morning", "man workout gym cinematic", "walking outdoors sunset"],
            "metabolismo": ["fat burning concept 3d animation", "fat cells 3d animation"],
        },
    },
    "articulacoes": {
        "aliases": ["articulacao", "joelho", "dor nas juntas", "artrite", "artrose", "colageno", "coluna", "dor"],
        "subs": {
            "dor_articular": ["senior knee pain holding knee", "person back pain stretching", "hand joint pain arthritis"],
            "anatomia": ["knee joint 3d animation", "cartilage anatomy 3d", "spine anatomy 3d animation"],
            "mobilidade": ["senior couple walking happy", "elderly stretching exercise", "person climbing stairs"],
        },
    },
    "sono": {
        "aliases": ["insonia", "dormir", "melatonina", "descanso"],
        "subs": {
            "insonia": ["person awake in bed at night insomnia", "alarm clock night 3am", "tossing turning in bed"],
            "sono_profundo": ["woman sleeping peacefully bed", "man sleeping comfortably morning light"],
            "relaxamento": ["herbal tea chamomile evening", "calm bedroom dim light"],
        },
    },
    "memoria": {
        "aliases": ["cerebro", "foco", "concentracao", "cognicao", "alzheimer", "esquecimento"],
        "subs": {
            "cerebro_3d": ["brain neurons 3d animation", "neural network brain synapses", "brain scan mri"],
            "esquecimento": ["senior confused looking for keys", "person forgetting stressed"],
            "foco_estudo": ["focused person working laptop", "student studying concentration library"],
        },
    },
    "coracao": {
        "aliases": ["cardiaco", "cardiovascular", "pressao", "hipertensao", "colesterol", "circulacao", "omega 3"],
        "subs": {
            "pressao_arterial": ["blood pressure monitor measuring arm", "doctor measuring blood pressure"],
            "anatomia_cardio": ["human heart 3d animation beating", "blood cells flowing artery 3d", "artery plaque cholesterol 3d"],
            "estilo_vida": ["salmon fish oil capsules", "senior man jogging healthy heart", "olive oil nuts healthy fats"],
        },
    },
    "prostata": {
        "aliases": ["saude masculina", "urinar", "bexiga"],
        "subs": {
            "sintomas": ["man waking up at night bathroom", "middle aged man worried bathroom door"],
            "medico": ["urologist doctor consultation man", "senior man doctor appointment"],
            "anatomia": ["prostate anatomy 3d animation", "male urinary system 3d"],
        },
    },
    "menopausa": {
        "aliases": ["saude feminina", "hormonios", "calores", "fogacho"],
        "subs": {
            "sintomas": ["woman hot flash fanning herself", "middle aged woman tired stressed", "woman night sweats bed"],
            "bem_estar": ["mature woman yoga relaxing", "happy middle aged woman smiling outdoors"],
        },
    },
    "imunidade": {
        "aliases": ["imunologico", "gripe", "resfriado", "vitamina c", "vitamina d", "zinco", "defesas"],
        "subs": {
            "celulas": ["immune system cells 3d animation", "virus attacking cells 3d", "white blood cells 3d"],
            "doenca": ["person sick with flu blanket", "woman sneezing tissue"],
            "nutrientes": ["oranges citrus slow motion", "vitamin pills supplements close up", "ginger lemon tea"],
        },
    },
    "digestao": {
        "aliases": ["intestino", "probiotico", "estomago", "gases", "inchaco", "prisao de ventre", "intestinal"],
        "subs": {
            "desconforto": ["woman stomach pain holding belly", "bloated stomach discomfort"],
            "microbiota": ["gut bacteria 3d animation", "intestine anatomy 3d", "probiotics microscope bacteria"],
            "alimentos": ["yogurt kefir close up", "fiber rich foods vegetables", "fermented foods kimchi"],
        },
    },
    "pele_cabelo": {
        "aliases": ["pele", "cabelo", "unhas", "rugas", "queda de cabelo", "beleza", "colageno pele"],
        "subs": {
            "envelhecimento": ["woman looking at wrinkles mirror", "aging skin close up"],
            "queda_cabelo": ["hair loss comb close up", "man checking receding hairline mirror"],
            "beleza": ["glowing skin woman face close up", "healthy shiny hair slow motion"],
        },
    },
    "energia": {
        "aliases": ["cansaco", "fadiga", "disposicao", "vitalidade", "estresse", "ansiedade"],
        "subs": {
            "cansaco": ["tired man office yawning", "exhausted woman couch afternoon"],
            "estresse": ["stressed woman headache work", "anxious person breathing deeply"],
            "disposicao": ["energetic woman morning stretch window", "happy active senior cycling"],
        },
    },
    "visao": {
        "aliases": ["olhos", "vista", "enxergar", "catarata", "luteina"],
        "subs": {
            "problemas": ["senior squinting reading small text", "person rubbing tired eyes screen"],
            "anatomia": ["human eye macro close up", "eye anatomy 3d animation"],
            "exame": ["eye exam optometrist", "eye chart test"],
        },
    },
    "figado": {
        "aliases": ["detox", "esteatose", "gordura no figado"],
        "subs": {
            "anatomia": ["liver anatomy 3d animation", "fatty liver 3d"],
            "habitos": ["fast food greasy close up", "alcohol glass pouring", "detox green juice"],
        },
    },
    "suplementos": {
        "aliases": ["capsulas", "vitaminas", "nutraceuticos", "comprimidos", "natural"],
        "subs": {
            "capsulas": ["supplement capsules falling slow motion", "pills in hand close up", "pill bottle pouring capsules"],
            "natural": ["herbs medicinal plants mortar", "natural ingredients turmeric ginger", "green tea leaves close up"],
            "laboratorio": ["laboratory scientist research", "pharmaceutical production line capsules"],
        },
    },
}



def all_themes():
    """Taxonomia base + temas criados pelo app (data/themes_custom.json)."""
    t = dict(TAXONOMY)
    try:
        t.update(json.loads(CUSTOM.read_text()))
    except Exception:
        pass
    return t


def save_custom(name, aliases, subs):
    try:
        c = json.loads(CUSTOM.read_text())
    except Exception:
        c = {}
    c[normalize(name).replace(" ", "_")] = {"aliases": aliases, "subs": subs}
    CUSTOM.parent.mkdir(parents=True, exist_ok=True)
    CUSTOM.write_text(json.dumps(c, ensure_ascii=False, indent=1))


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace("_", " ").split())


def resolve_theme(user_text: str):
    """Retorna (tema, subs). Se não reconhecer, cria um tema livre."""
    q = normalize(user_text)
    for theme, data in all_themes().items():
        names = [normalize(theme)] + [normalize(a) for a in data["aliases"]]
        if q in names:
            return theme, data["subs"]
    for theme, data in all_themes().items():
        names = [normalize(theme)] + [normalize(a) for a in data["aliases"]]
        if any(n in q or q in n for n in names):
            return theme, data["subs"]
    slug = q.replace(" ", "_") or "outros"
    return slug, {"geral": [q]}
