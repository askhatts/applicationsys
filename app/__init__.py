import os

from flask import Flask


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.from_mapping(
        SECRET_KEY="dev",  # переопределяется в instance/config.py
        DATABASE=os.path.join(app.instance_path, "app.db"),
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    app.config.from_pyfile("config.py", silent=True)
    app.json.ensure_ascii = False  # кириллица в JSON как есть, не \uXXXX

    from . import db
    db.init_app(app)

    from . import auth
    auth.init_app(app)
    app.register_blueprint(auth.bp)

    from . import public, work, dashboard, admin
    app.register_blueprint(public.bp)
    app.register_blueprint(work.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(admin.bp)

    from .services import ACTION_LABELS, STATUS_LABELS
    from .util import fmt_dt, get_setting

    app.jinja_env.filters["dt"] = fmt_dt
    app.jinja_env.filters["status_label"] = lambda s: STATUS_LABELS.get(s, s)
    app.jinja_env.filters["action_label"] = lambda a: ACTION_LABELS.get(a, a)

    @app.context_processor
    def inject_globals():
        from .db import get_db
        return {"org_name": get_setting(get_db(), "org_name", "Организация")}

    return app
