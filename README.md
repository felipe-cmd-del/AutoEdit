# 🎬 B-Roll Hunter

Você digita um tema (ex.: **diabetes**) e ele caça, corta, faz a curadoria, categoriza e manda pro Drive.

**Busca**
- Palavras-chave por subcategoria (`app/taxonomy.py`), focadas em nutracêuticos, com variações automáticas ("stock footage", "b roll 4k").
- YouTube por busca (opção "só Creative Commons"). TikTok, Instagram e YouTube por link, **perfil, canal ou hashtag**.
- Temas personalizados criados pelo app, sem mexer em código.
- Agendamento: um tema roda sozinho a cada X horas.

**Curadoria 100% local, sem API paga**
- Corte por mudança de cena (3–8s), sem áudio, pulando intro e encerramento.
- OCR (Tesseract): descarta texto, legenda e "inscreva-se".
- Detector de marca d'água fixa nos cantos.
- **IA de visão CLIP (open source, roda na CPU):**
  - mede a relevância ao tema;
  - recusa pessoa falando pra câmera, slide, thumbnail, tela, logo e meme;
  - gera tags (tipo de plano, pessoas, faixa etária, clima).
- Filtro de qualidade (escuro, estourado, borrado, resolução mínima) e anti-duplicado com hash perceptual.
- Clipe apagado no app entra numa lista de bloqueio e nunca volta.

**Entrega**
- Arquivos em `Tema/Subcategoria/`. Reencode H.264 de alta qualidade (CRF 18) e **cópia vertical 9:16** automática.
- `catalog.json` com relevância, tags, cores dominantes, movimento, nitidez, fps, fonte e minuto de origem. Exporta em CSV.
- App: galeria com prévia, **busca inteligente por descrição** ("mão segurando cápsulas"), favoritos e apagar.

Temas: diabetes, emagrecimento, articulacoes, sono, memoria, coracao, prostata, menopausa,
imunidade, digestao, pele_cabelo, energia, visao, figado, suplementos (aceita sinônimos:
"glicose" → diabetes, "pressão" → coração...). Tema desconhecido vira busca livre.

## Instalação na VPS
No terminal da Hostinger (hPanel → VPS → Terminal do navegador):
```bash
curl -fsSL https://raw.githubusercontent.com/felipe-cmd-del/AutoEdit/main/install.sh | bash
```

## Google Drive (uma vez)
1. No celular, instale o **Termux** (F-Droid) e rode: `pkg install rclone && rclone authorize "drive"`.
   Abra o link que aparecer, faça login no Google e copie o token impresso no fim.
2. Na VPS: `cd /opt/broll-hunter && docker compose exec broll rclone config --config /data/rclone.conf`
   → `n` (novo) → nome `gdrive` → tipo `drive` → Enter nos campos → scope `1`
   → "Use web browser?" **n** → cole o token → `n` (shared drive) → `y`.
3. Pronto: os clipes vão para `Meu Drive/B-Rolls/`.

## Cookies (Instagram / YouTube bloqueando)
Exporte `cookies.txt` com a extensão "Get cookies.txt LOCALLY" e salve em
`/opt/broll-hunter/data/cookies.txt`. **Nunca suba esse arquivo no GitHub.**

## Importar no outro app
Leia `B-Rolls/catalog.json` → `clips[]`: `file`, `theme`, `subcategory`, `keyword`,
`duration`, `width`, `height`, `orientation`, `relevance`, `tags`, `colors`,
`file_vertical`, `source_url`, `rating`. Ajustes finos de curadoria: veja `.env.example`.

**Requisitos da VPS:** 2+ vCPU e 4 GB RAM recomendados (a IA de visão usa cerca de 1 GB).
Com pouca RAM, use `VISION=0`.
