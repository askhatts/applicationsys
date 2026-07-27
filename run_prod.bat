@echo off
rem Запуск приложения в рабочем режиме (waitress, порт 8080).
rem Для автозапуска добавьте этот файл в Планировщик заданий Windows
rem (триггер «При запуске системы», запускать в папке проекта).
cd /d "%~dp0"
.venv\Scripts\waitress-serve --listen=0.0.0.0:8080 run_prod:app
