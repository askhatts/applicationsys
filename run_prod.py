"""Продакшен-объект приложения для waitress:
waitress-serve --listen=0.0.0.0:8080 run_prod:app
"""
from app import create_app


class PrefixMiddleware:
    """Позволяет приложению работать за реверс-прокси не из корня сайта
    (например /requests/*). Caddy должен прислать заголовок
    X-Forwarded-Prefix со значением префикса (см. deploy/linux/caddy-site-block.conf)."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        prefix = environ.get("HTTP_X_FORWARDED_PREFIX", "")
        if prefix:
            environ["SCRIPT_NAME"] = prefix
            path_info = environ.get("PATH_INFO", "")
            if path_info.startswith(prefix):
                environ["PATH_INFO"] = path_info[len(prefix):]
        return self.wsgi_app(environ, start_response)


app = create_app()
app.wsgi_app = PrefixMiddleware(app.wsgi_app)
