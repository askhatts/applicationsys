#!/bin/bash
# Обновление уже развёрнутого приложения новой версией из GitHub.
# Использование: sudo -u www-data /opt/applicationsys/deploy/linux/update.sh
set -euo pipefail
APP_DIR="/opt/applicationsys"
cd "$APP_DIR"
git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart applicationsys
echo "Обновлено и перезапущено. Логи: sudo journalctl -u applicationsys -f"
