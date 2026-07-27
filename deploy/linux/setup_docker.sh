#!/bin/bash
# Установка рядом с уже работающим Docker-стеком Caddy (/opt/onco) на этом VPS.
# Не трогает существующий проект — добавляет отдельный контейнер в ту же сеть
# deploy_default и дописывает один site-блок в конец их Caddyfile.
set -euo pipefail

APP_DIR="/opt/applicationsys"
REPO_URL="https://github.com/askhatts/applicationsys.git"
CADDYFILE="/opt/onco/deploy/Caddyfile"
DOMAIN="requests.oncomap-abai.kz"

echo "== 1. Код приложения =="
if [ -d "$APP_DIR/.git" ]; then
  echo "$APP_DIR уже существует — обновляю"
  cd "$APP_DIR" && git pull
else
  git clone "$REPO_URL" "$APP_DIR"
  cd "$APP_DIR"
fi
mkdir -p "$APP_DIR/instance"

echo "== 2. Сборка и запуск контейнера requests_app =="
docker compose -f deploy/linux/docker-compose.requests.yml up -d --build

echo "== 3. Проверка контейнера изнутри сети =="
sleep 2
docker exec deploy-caddy-1 wget -qO- http://requests_app:8000/ | head -c 200 || \
  echo "(предупреждение: не удалось достучаться из caddy — проверьте docker logs requests_app)"

echo "== 4. Caddyfile: добавляю site-блок (если ещё не добавлен) =="
if grep -q "^$DOMAIN " "$CADDYFILE" 2>/dev/null; then
  echo "Блок для $DOMAIN уже есть в $CADDYFILE — пропускаю"
else
  cp "$CADDYFILE" "$CADDYFILE.bak.$(date +%s)"
  echo "" >> "$CADDYFILE"
  cat "$APP_DIR/deploy/linux/caddy-site-block.conf" >> "$CADDYFILE"
  echo "Добавлено. Резервная копия предыдущей версии сохранена рядом (.bak.<timestamp>)"
fi

echo "== 5. Проверка синтаксиса и мягкая перезагрузка Caddy (без даунтайма для oncomap-abai.kz) =="
docker exec deploy-caddy-1 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker exec deploy-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile

echo "== 6. Проверка DNS =="
SERVER_IP="$(curl -s https://api.ipify.org || true)"
DNS_IP="$(dig +short "$DOMAIN" | tail -n1 || true)"
echo "IP сервера: $SERVER_IP | DNS для $DOMAIN сейчас резолвится в: ${DNS_IP:-<пусто>}"
if [ "$DNS_IP" = "$SERVER_IP" ]; then
  echo "DNS уже настроен — Caddy сам получит сертификат Let's Encrypt при следующем обращении."
else
  echo "Добавьте A-запись requests -> $SERVER_IP в панели gohost.kz. Caddy автоматически"
  echo "выпустит сертификат, как только DNS обновится — ничего перезапускать не нужно."
fi

echo "== Готово =="
echo "Приложение будет доступно на https://$DOMAIN после обновления DNS."
echo "Логи контейнера: docker logs -f requests_app"
