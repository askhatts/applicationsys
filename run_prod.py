"""Продакшен-объект приложения для waitress:
waitress-serve --listen=0.0.0.0:8080 run_prod:app
"""
from app import create_app

app = create_app()
