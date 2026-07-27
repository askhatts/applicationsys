#!/bin/bash
# Первичная установка приложения на Ubuntu/Debian VPS.
# Выполнять от пользователя с sudo (или от root — скрипт это учитывает).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

DOMAIN="requests.oncomap-abai.kz"
APP_DIR="/opt/applicationsys"
REPO_URL="https://github.com/askhatts/applicationsys.git"
ADMIN_EMAIL="thesisdis2022@gmail.com"
RUN_USER="$(id -un)"

sudo_() { if [ "$(id -u)" = "0" ]; then "$@"; else sudo "$@"; fi; }

echo "== 1. Системные пакеты =="
sudo_ apt-get update -qq
sudo_ apt-get install -y -qq python3-venv python3-pip nginx git ufw curl dnsutils

echo "== 2. Клонирование репозитория =="
if [ -d "$APP_DIR/.git" ]; then
  echo "$APP_DIR уже существует — обновляю (git pull)"
  cd "$APP_DIR" && git pull
else
  sudo_ mkdir -p "$APP_DIR"
  sudo_ chown "$RUN_USER":"$RUN_USER" "$APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
  cd "$APP_DIR"
fi

echo "== 3. Виртуальное окружение и зависимости =="
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "== 4. Инициализация базы данных =="
if [ -f "$APP_DIR/instance/app.db" ]; then
  echo "БД уже существует — пропускаю init-db (данные не трогаю)"
else
  .venv/bin/python manage.py init-db
  # ^ Пароль администратора и ключ дэшборда — см. вывод выше, сохраните их.
fi

echo "== 5. Права для systemd-службы (работает от www-data) =="
sudo_ mkdir -p "$APP_DIR/backups"
sudo_ chown -R www-data:www-data "$APP_DIR"

echo "== 6. systemd-служба =="
sudo_ cp "$APP_DIR/deploy/linux/applicationsys.service" /etc/systemd/system/applicationsys.service
sudo_ systemctl daemon-reload
sudo_ systemctl enable --now applicationsys
sleep 1
sudo_ systemctl --no-pager status applicationsys || true

echo "== 7. nginx (порт 80) =="
sudo_ cp "$APP_DIR/deploy/linux/nginx-requests.conf" "/etc/nginx/sites-available/$DOMAIN"
sudo_ ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
sudo_ rm -f /etc/nginx/sites-enabled/default
sudo_ nginx -t
sudo_ systemctl reload nginx

echo "== 8. Брандмауэр =="
sudo_ ufw allow OpenSSH >/dev/null
sudo_ ufw allow 'Nginx Full' >/dev/null
yes | sudo_ ufw enable || true
sudo_ ufw status

echo "== 9. Проверка HTTP =="
curl -sS -o /dev/null -w "HTTP через nginx: %{http_code}\n" "http://127.0.0.1/" || true

echo "== 10. SSL (Let's Encrypt) =="
SERVER_IP="$(curl -s https://api.ipify.org || true)"
DNS_IP="$(dig +short "$DOMAIN" | tail -n1 || true)"
echo "IP сервера: $SERVER_IP | DNS для $DOMAIN резолвится в: ${DNS_IP:-<пусто>}"
if [ -n "$DNS_IP" ] && [ "$DNS_IP" = "$SERVER_IP" ]; then
  sudo_ apt-get install -y -qq certbot python3-certbot-nginx
  sudo_ certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$ADMIN_EMAIL" --redirect
  echo "SSL настроен: https://$DOMAIN"
else
  echo "ПРОПУЩЕНО: DNS-запись $DOMAIN пока не указывает на этот сервер."
  echo "Добавьте A-запись requests -> $SERVER_IP в панели домена, подождите обновления DNS,"
  echo "затем выполните: sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m $ADMIN_EMAIL --redirect"
fi

echo "== Готово =="
echo "Приложение (по IP, без SSL): http://$SERVER_IP"
echo "Логи службы: sudo journalctl -u applicationsys -f"
