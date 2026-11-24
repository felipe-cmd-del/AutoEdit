# 🎬 B-Roll Hunter

Você digita um tema (ex.: **diabetes**) e ele:

1. Busca vídeos com palavras-chave por subcategoria (`app/taxonomy.py`, focado em nutracêuticos).
2. Baixa com **yt-dlp** (YouTube por busca; TikTok/Instagram/YouTube por link).
3. Corta por mudança de cena em clipes de 3–8s, sem áudio.
4. **Curadoria 100% local, sem API paga:**
   - **OCR (Tesseract):** descarta trechos com texto, legenda ou marca d'água.
   - **Filtro de qualidade:** descarta tela preta/branca e imagem borrada.
   - **Anti-duplicado:** compara a imagem de cada clipe (hash perceptual).
5. Salva em `Tema/Subcategoria/` + `catalog.json` e envia ao **Google Drive** via rclone.

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
`duration`, `width`, `height`, `orientation`, `source_url`.
