#!/bin/bash
# Резервная копия БД. Добавить в cron от www-data, например ежедневно в 02:00:
#   sudo crontab -u www-data -e
#   0 2 * * * /opt/applicationsys/deploy/linux/backup_db.sh
set -euo pipefail
APP_DIR="/opt/applicationsys"
STAMP="$(date +%F)"
mkdir -p "$APP_DIR/backups"
"$APP_DIR/.venv/bin/python" - <<PY
import sqlite3
src = sqlite3.connect("$APP_DIR/instance/app.db")
dst = sqlite3.connect("$APP_DIR/backups/app-$STAMP.db")
src.backup(dst)
dst.close()
src.close()
print("Backup OK: $APP_DIR/backups/app-$STAMP.db")
PY
# Хранить последние 30 копий, старые удалять.
find "$APP_DIR/backups" -name 'app-*.db' -mtime +30 -delete
