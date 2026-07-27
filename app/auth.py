import functools
import secrets

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)


# --- CSRF: простой session-токен для всех POST-форм -------------------------

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(16)
    return session["_csrf"]


def check_csrf():
    token = session.get("_csrf")
    if not token or request.form.get("_csrf") != token:
        abort(400, "Неверный CSRF-токен. Обновите страницу и повторите.")


def init_app(app):
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def _csrf_protect():
        if request.method == "POST":
            check_csrf()


# --- Пользователь в g и декораторы ролей ------------------------------------

@bp.before_app_request
def load_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id:
        g.user = get_db().execute(
            "SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)
        ).fetchone()
        if g.user is None:
            session.pop("user_id", None)


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


# --- Вход / выход -----------------------------------------------------------

@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        login_ = request.form.get("login", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE login = ? AND is_active = 1", (login_,)
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Неверный логин или пароль", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            target = request.args.get("next")
            if target and target.startswith("/") and not target.startswith("//"):
                return redirect(target)
            return redirect(url_for("work.index"))
    return render_template("auth/login.html")


@bp.route("/logout", methods=("POST",))
def logout():
    session.clear()
    return redirect(url_for("public.index"))
