#!/bin/bash
# Первичная установка приложения на Ubuntu/Debian VPS.
# Выполнять от пользователя с sudo (НЕ от root напрямую, если возможно).
# Использование: скопируйте команды блоками и проверяйте вывод каждого шага —
# не запускайте вслепую одним махом на боевом сервере.
set -euo pipefail

DOMAIN="requests.oncomap-abai.kz"
APP_DIR="/opt/applicationsys"
REPO_URL="https://github.com/askhatts/applicationsys.git"

echo "== 1. Системные пакеты =="
sudo apt update
sudo apt install -y python3-venv python3-pip nginx git ufw

echo "== 2. Клонирование репозитория =="
sudo mkdir -p "$APP_DIR"
sudo chown "$USER":"$USER" "$APP_DIR"
git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"

echo "== 3. Виртуальное окружение и зависимости =="
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "== 4. Инициализация базы данных =="
.venv/bin/python manage.py init-db
# ^ Сохраните пароль администратора и ключ дэшборда из вывода команды!

echo "== 5. Права для systemd-службы (работает от www-data) =="
sudo chown -R www-data:www-data "$APP_DIR"
sudo mkdir -p "$APP_DIR/backups"
sudo chown www-data:www-data "$APP_DIR/backups"

echo "== 6. systemd-служба =="
sudo cp deploy/linux/applicationsys.service /etc/systemd/system/applicationsys.service
sudo systemctl daemon-reload
sudo systemctl enable --now applicationsys
sudo systemctl status applicationsys --no-pager

echo "== 7. nginx (пока без SSL, порт 80) =="
sudo cp deploy/linux/nginx-requests.conf "/etc/nginx/sites-available/$DOMAIN"
sudo ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
sudo nginx -t
sudo systemctl reload nginx

echo "== 8. Брандмауэр =="
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable

echo "== 9. SSL (Let's Encrypt) — выполнить ПОСЛЕ того, как DNS-запись"
echo "   $DOMAIN -> IP сервера уже видна снаружи (проверить: dig +short $DOMAIN)"
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d "$DOMAIN"

echo "== Готово =="
echo "Приложение: https://$DOMAIN"
echo "Логи службы: sudo journalctl -u applicationsys -f"
