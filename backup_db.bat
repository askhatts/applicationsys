@echo off
rem Резервная копия базы данных (можно добавить в Планировщик заданий, раз в сутки).
rem Копии складываются в папку backups\ с датой в имени файла.
cd /d "%~dp0"
if not exist backups mkdir backups
set D=%date:~-4%-%date:~3,2%-%date:~0,2%
.venv\Scripts\python -c "import sqlite3; src = sqlite3.connect('instance/app.db'); dst = sqlite3.connect(r'backups/app-%D%.db'); src.backup(dst); dst.close(); src.close(); print('Backup OK: backups/app-%D%.db')"
