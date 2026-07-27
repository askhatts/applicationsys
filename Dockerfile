# Образ для развёртывания рядом с существующим Caddy-стеком на VPS.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY manage.py run_prod.py ./

# instance/ — том с БД, монтируется снаружи (см. docker-compose.requests.yml)
RUN mkdir -p /app/instance

EXPOSE 8000

CMD ["sh", "-c", "test -f /app/instance/app.db || python manage.py init-db; waitress-serve --listen=0.0.0.0:8000 run_prod:app"]
