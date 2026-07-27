"""Публичная часть: подача заявки и отслеживание/подтверждение по токену."""
from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)

from .db import get_db
from .deadlines import deadline_state
from .seed import GROUP_LABELS
from .services import (TransitionError, change_status, create_request,
                       get_history, get_request)
from .util import get_setting

bp = Blueprint("public", __name__)


def _form_dicts():
    db = get_db()
    departments = db.execute(
        "SELECT * FROM departments WHERE is_active = 1 ORDER BY grp, sort_order"
    ).fetchall()
    groups = []
    for grp in ("adm", "clin", "diag", "aux"):
        items = [d for d in departments if d["grp"] == grp]
        if items:
            groups.append((GROUP_LABELS[grp], items))
    categories = db.execute(
        "SELECT c.*, s.name AS service_name FROM categories c "
        "JOIN services s ON s.id = c.service_id "
        "WHERE c.is_active = 1 ORDER BY c.sort_order"
    ).fetchall()
    priorities = db.execute(
        "SELECT * FROM priorities WHERE is_active = 1 ORDER BY sort_order"
    ).fetchall()
    return groups, categories, priorities


@bp.route("/")
def index():
    groups, categories, priorities = _form_dicts()
    return render_template("public/index.html", dept_groups=groups,
                           categories=categories, priorities=priorities,
                           form={})


@bp.route("/submit", methods=("POST",))
def submit():
    form = request.form
    errors = []
    description = form.get("description", "").strip()
    applicant_name = form.get("applicant_name", "").strip()
    applicant_contact = form.get("applicant_contact", "").strip()
    if not form.get("department_id"):
        errors.append("Выберите отдел")
    if not form.get("category_id"):
        errors.append("Выберите категорию")
    if not form.get("priority_id"):
        errors.append("Выберите приоритет")
    if len(description) < 10:
        errors.append("Опишите проблему подробнее (не менее 10 символов)")
    if not applicant_name:
        errors.append("Укажите ФИО заявителя")
    if not applicant_contact:
        errors.append("Укажите контакт (телефон или кабинет)")

    if errors:
        for e in errors:
            flash(e, "error")
        groups, categories, priorities = _form_dicts()
        return render_template("public/index.html", dept_groups=groups,
                               categories=categories, priorities=priorities,
                               form=form), 400

    try:
        request_id, token = create_request(
            int(form["department_id"]), int(form["category_id"]),
            int(form["priority_id"]), description,
            form.get("location", "").strip(), applicant_name, applicant_contact,
        )
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("public.index"))

    return redirect(url_for("public.track", token=token, new=1))


@bp.route("/find", methods=("POST",))
def find():
    """Проверка статуса по коду заявки с главной страницы."""
    token = request.form.get("token", "").strip()
    if token:
        return redirect(url_for("public.track", token=token))
    return redirect(url_for("public.index"))


@bp.route("/track/<token>")
def track(token):
    req = get_request(token=token)
    if req is None:
        abort(404)
    db = get_db()
    near_fraction = float(get_setting(db, "near_due_fraction", "0.25"))
    return render_template(
        "public/track.html", req=req, history=get_history(req["id"]),
        dl_state=deadline_state(req, near_fraction),
        just_created=request.args.get("new"),
    )


def _applicant_action(token, action):
    req = get_request(token=token)
    if req is None:
        abort(404)
    comment = request.form.get("comment", "").strip()
    if action == "returned" and not comment:
        flash("Укажите, что именно не выполнено — причина обязательна", "error")
        return redirect(url_for("public.track", token=token))
    try:
        change_status(req["id"], action, "applicant", req["applicant_name"],
                      comment=comment or None)
    except TransitionError as e:
        flash(str(e), "error")
        return redirect(url_for("public.track", token=token))
    flash("Спасибо, исполнение подтверждено" if action == "confirmed"
          else "Заявка возвращена в работу", "success")
    return redirect(url_for("public.track", token=token))


@bp.route("/track/<token>/confirm", methods=("POST",))
def confirm(token):
    return _applicant_action(token, "confirmed")


@bp.route("/track/<token>/return", methods=("POST",))
def return_(token):
    return _applicant_action(token, "returned")
