"""Админка: справочники, пользователи, настройки."""
import secrets

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, url_for)

from .auth import admin_required
from .db import get_db
from .seed import GROUP_LABELS
from .util import get_setting, now_str, set_setting

bp = Blueprint("admin", __name__, url_prefix="/admin")

# Конфигурация обобщённого CRUD справочников.
DICTS = {
    "departments": {
        "title": "Отделы-заявители",
        "fields": [("name", "Название"), ("grp", "Группа"), ("sort_order", "Порядок")],
    },
    "services": {
        "title": "Службы-исполнители",
        "fields": [("name", "Название")],
    },
    "categories": {
        "title": "Категории заявок",
        "fields": [("name", "Название"), ("service_id", "Служба-исполнитель"),
                   ("sort_order", "Порядок")],
    },
    "priorities": {
        "title": "Приоритеты и сроки (SLA)",
        "fields": [("name", "Название"), ("sla_hours", "Срок, часов"),
                   ("sort_order", "Порядок")],
    },
}


@bp.route("/")
@admin_required
def index():
    return render_template("admin/index.html", dicts=DICTS)


@bp.route("/<dict_name>")
@admin_required
def dict_list(dict_name):
    cfg = DICTS.get(dict_name)
    if cfg is None:
        abort(404)
    db = get_db()
    if dict_name == "categories":
        rows = db.execute(
            "SELECT c.*, s.name AS service_name FROM categories c "
            "JOIN services s ON s.id = c.service_id ORDER BY c.sort_order, c.id"
        ).fetchall()
    elif dict_name == "departments":
        rows = db.execute(
            "SELECT * FROM departments ORDER BY grp, sort_order, id").fetchall()
    elif dict_name == "priorities":
        rows = db.execute("SELECT * FROM priorities ORDER BY sort_order, id").fetchall()
    else:
        rows = db.execute("SELECT * FROM services ORDER BY id").fetchall()
    services = db.execute("SELECT * FROM services WHERE is_active = 1 ORDER BY name").fetchall()
    return render_template("admin/dict_list.html", dict_name=dict_name, cfg=cfg,
                           rows=rows, services=services,
                           group_labels=GROUP_LABELS)


def _dict_form_values(dict_name):
    name = request.form.get("name", "").strip()
    if not name:
        flash("Название обязательно", "error")
        return None
    values = {"name": name}
    if dict_name == "departments":
        grp = request.form.get("grp", "aux")
        values["grp"] = grp if grp in GROUP_LABELS else "aux"
    if dict_name == "categories":
        values["service_id"] = request.form.get("service_id", type=int)
        if not values["service_id"]:
            flash("Выберите службу-исполнителя", "error")
            return None
    if dict_name == "priorities":
        values["sla_hours"] = request.form.get("sla_hours", type=int)
        if not values["sla_hours"] or values["sla_hours"] < 1:
            flash("Срок в часах должен быть положительным числом", "error")
            return None
    if dict_name in ("departments", "categories", "priorities"):
        values["sort_order"] = request.form.get("sort_order", type=int, default=0)
    return values


@bp.route("/<dict_name>/add", methods=("POST",))
@admin_required
def dict_add(dict_name):
    if dict_name not in DICTS:
        abort(404)
    values = _dict_form_values(dict_name)
    if values:
        db = get_db()
        cols = ", ".join(values)
        marks = ", ".join("?" * len(values))
        try:
            db.execute(f"INSERT INTO {dict_name} ({cols}) VALUES ({marks})",
                       list(values.values()))
            db.commit()
            flash("Запись добавлена", "success")
        except db.IntegrityError:
            flash("Запись с таким названием уже существует", "error")
    return redirect(url_for("admin.dict_list", dict_name=dict_name))


@bp.route("/<dict_name>/<int:row_id>/edit", methods=("POST",))
@admin_required
def dict_edit(dict_name, row_id):
    if dict_name not in DICTS:
        abort(404)
    values = _dict_form_values(dict_name)
    if values:
        db = get_db()
        sets = ", ".join(f"{k} = ?" for k in values)
        try:
            db.execute(f"UPDATE {dict_name} SET {sets} WHERE id = ?",
                       list(values.values()) + [row_id])
            db.commit()
            flash("Запись обновлена", "success")
        except db.IntegrityError:
            flash("Запись с таким названием уже существует", "error")
    return redirect(url_for("admin.dict_list", dict_name=dict_name))


@bp.route("/<dict_name>/<int:row_id>/toggle", methods=("POST",))
@admin_required
def dict_toggle(dict_name, row_id):
    if dict_name not in DICTS:
        abort(404)
    db = get_db()
    db.execute(f"UPDATE {dict_name} SET is_active = 1 - is_active WHERE id = ?",
               (row_id,))
    db.commit()
    return redirect(url_for("admin.dict_list", dict_name=dict_name))


# --- Пользователи -----------------------------------------------------------

@bp.route("/users")
@admin_required
def users():
    db = get_db()
    rows = db.execute(
        "SELECT u.*, s.name AS service_name FROM users u "
        "LEFT JOIN services s ON s.id = u.service_id ORDER BY u.id").fetchall()
    services = db.execute(
        "SELECT * FROM services WHERE is_active = 1 ORDER BY name").fetchall()
    return render_template("admin/users.html", rows=rows, services=services)


@bp.route("/users/add", methods=("POST",))
@admin_required
def user_add():
    from werkzeug.security import generate_password_hash
    login = request.form.get("login", "").strip()
    full_name = request.form.get("full_name", "").strip()
    role = request.form.get("role", "executor")
    service_id = request.form.get("service_id", type=int)
    password = request.form.get("password", "").strip() or secrets.token_urlsafe(9)
    if not login or not full_name:
        flash("Логин и ФИО обязательны", "error")
    elif role not in ("admin", "executor"):
        flash("Неверная роль", "error")
    elif role == "executor" and not service_id:
        flash("Для исполнителя выберите службу", "error")
    else:
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (login, password_hash, full_name, role, "
                " service_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (login, generate_password_hash(password), full_name, role,
                 service_id if role == "executor" else None, now_str()))
            db.commit()
            flash(f"Пользователь {login} создан. Пароль: {password}", "success")
        except db.IntegrityError:
            flash("Такой логин уже занят", "error")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/reset-password", methods=("POST",))
@admin_required
def user_reset_password(user_id):
    from werkzeug.security import generate_password_hash
    password = secrets.token_urlsafe(9)
    db = get_db()
    row = db.execute("SELECT login FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        abort(404)
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (generate_password_hash(password), user_id))
    db.commit()
    flash(f"Новый пароль для {row['login']}: {password}", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/toggle", methods=("POST",))
@admin_required
def user_toggle(user_id):
    db = get_db()
    db.execute("UPDATE users SET is_active = 1 - is_active WHERE id = ?", (user_id,))
    db.commit()
    return redirect(url_for("admin.users"))


# --- Настройки --------------------------------------------------------------

@bp.route("/settings", methods=("GET", "POST"))
@admin_required
def settings():
    db = get_db()
    if request.method == "POST":
        if request.form.get("action") == "regen_token":
            set_setting(db, "dashboard_view_token", secrets.token_urlsafe(16))
            db.commit()
            flash("Ключ просмотра дэшборда перегенерирован", "success")
        else:
            frac = request.form.get("near_due_fraction", "").replace(",", ".")
            try:
                value = float(frac)
                if not 0 < value < 1:
                    raise ValueError
                set_setting(db, "near_due_fraction", value)
            except ValueError:
                flash("Доля должна быть числом от 0 до 1, например 0.25", "error")
                return redirect(url_for("admin.settings"))
            org = request.form.get("org_name", "").strip()
            if org:
                set_setting(db, "org_name", org)
            db.commit()
            flash("Настройки сохранены", "success")
        return redirect(url_for("admin.settings"))
    return render_template(
        "admin/settings.html",
        near_due_fraction=get_setting(db, "near_due_fraction", "0.25"),
        org_name_value=get_setting(db, "org_name", ""),
        view_token=get_setting(db, "dashboard_view_token", ""))
