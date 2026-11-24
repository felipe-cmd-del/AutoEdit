#!/usr/bin/env bash
# Instalador do B-Roll Hunter para VPS (Ubuntu/Debian). Uso:
#   curl -fsSL https://raw.githubusercontent.com/felipe-cmd-del/AutoEdit/main/install.sh | bash
set -e
DIR=/opt/broll-hunter
BRANCH=${BRANCH:-main}
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
command -v git >/dev/null || (apt-get update && apt-get install -y git)
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull; else git clone -b "$BRANCH" https://github.com/felipe-cmd-del/AutoEdit.git "$DIR"; fi
cd "$DIR"
mkdir -p data
if [ ! -f .env ]; then
  cp .env.example .env
  read -rp "Senha para o app: " PW </dev/tty
  sed -i "s/^APP_PASSWORD=.*/APP_PASSWORD=$PW/" .env
  read -rp "Porta (Enter = 8090): " P </dev/tty
  [ -n "$P" ] && sed -i "s/^PORT=.*/PORT=$P/" .env
fi
docker compose up -d --build
IP=$(curl -fsSL https://api.ipify.org || hostname -I | awk '{print $1}')
echo
echo "✅ Pronto! Abra no celular: http://$IP:$(grep ^PORT= .env | cut -d= -f2)"
echo "Próximo passo (Google Drive): cd $DIR && docker compose exec broll rclone config --config /data/rclone.conf"
