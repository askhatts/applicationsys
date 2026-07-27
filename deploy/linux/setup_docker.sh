#!/bin/bash
# Установка/обновление приложения рядом с уже работающим Docker-стеком Caddy
# (/opt/onco) на этом VPS. Не трогает существующий проект — поднимает только
# наш контейнер requests_app в сети deploy_default.
#
# Конфигурацию Caddy (site-блок с /requests*) этот скрипт НЕ трогает —
# см. deploy/linux/caddy-site-block.conf и раздел README «Развёртывание на VPS».
# Правка живого Caddyfile — ручной шаг, сделанный один раз при первом
# развёртывании (замена всего блока {$SITE_DOMAIN}, не добавление).
set -euo pipefail

APP_DIR="/opt/applicationsys"
REPO_URL="https://github.com/askhatts/applicationsys.git"

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

echo "== Готово =="
echo "Если это ПЕРВЫЙ запуск — примените вручную конфиг из deploy/linux/caddy-site-block.conf"
echo "в /opt/onco/deploy/Caddyfile (см. README), затем:"
echo "  docker exec deploy-caddy-1 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile"
echo "  docker exec deploy-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile"
echo "Если конфиг уже применён — просто перезапущен свежий код, ничего больше делать не нужно."
echo "Логи контейнера: docker logs -f requests_app"
