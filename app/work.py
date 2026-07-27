"""Кабинет исполнителя: заявки своей службы, действия по заявкам."""
from datetime import datetime

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, url_for)

from .auth import login_required
from .db import get_db
from .deadlines import deadline_state
from .services import (TransitionError, change_status, get_history,
                       get_request)
from .util import get_setting

bp = Blueprint("work", __name__, url_prefix="/work")

BASE_QUERY = """
    SELECT r.*, d.name AS department_name, c.name AS category_name,
           s.name AS service_name, p.name AS priority_name, p.sla_hours
    FROM requests r
    JOIN departments d ON d.id = r.department_id
    JOIN categories c ON c.id = r.category_id
    JOIN services s ON s.id = r.service_id
    JOIN priorities p ON p.id = r.priority_id
"""


def _visible_service_id():
    """Исполнитель видит только свою службу; админ — всех (None)."""
    if g.user["role"] == "admin":
        return None
    return g.user["service_id"]


@bp.route("/")
@login_required
def index():
    db = get_db()
    where, params = [], []

    service_id = _visible_service_id()
    if service_id is not None:
        where.append("r.service_id = ?")
        params.append(service_id)
    elif request.args.get("service"):
        where.append("r.service_id = ?")
        params.append(request.args["service"])

    status = request.args.get("status", "open")
    if status == "open":
        where.append("r.status IN ('new', 'in_progress', 'done')")
    elif status in ("new", "in_progress", "done", "confirmed", "rejected"):
        where.append("r.status = ?")
        params.append(status)

    if request.args.get("priority"):
        where.append("r.priority_id = ?")
        params.append(request.args["priority"])
    if request.args.get("q"):
        where.append("(r.description LIKE ? OR r.applicant_name LIKE ? "
                     "OR CAST(r.id AS TEXT) = ?)")
        q = request.args["q"].strip()
        params += [f"%{q}%", f"%{q}%", q]

    sql = BASE_QUERY
    if where:
        sql += " WHERE " + " AND ".join(where)
    # Просроченные открытые — первыми, затем открытые по близости срока,
    # затем ожидающие подтверждения, закрытые — в конце (свежие выше).
    sql += """ ORDER BY
        CASE
            WHEN r.status IN ('new','in_progress')
                 AND r.due_at < datetime('now','localtime') THEN 0
            WHEN r.status IN ('new','in_progress') THEN 1
            WHEN r.status = 'done' THEN 2
            ELSE 3
        END,
        CASE WHEN r.status IN ('new','in_progress','done') THEN r.due_at END,
        r.created_at DESC"""
    rows = db.execute(sql, params).fetchall()

    near_fraction = float(get_setting(db, "near_due_fraction", "0.25"))
    states = {r["id"]: deadline_state(r, near_fraction) for r in rows}

    priorities = db.execute(
        "SELECT * FROM priorities WHERE is_active = 1 ORDER BY sort_order").fetchall()
    services = db.execute("SELECT * FROM services ORDER BY name").fetchall() \
        if g.user["role"] == "admin" else []
    return render_template("work/list.html", rows=rows, states=states,
                           priorities=priorities, services=services,
                           cur_status=status)


def _load_visible_request(request_id):
    req = get_request(request_id=request_id)
    if req is None:
        abort(404)
    service_id = _visible_service_id()
    if service_id is not None and req["service_id"] != service_id:
        abort(403)
    return req


@bp.route("/<int:request_id>")
@login_required
def detail(request_id):
    req = _load_visible_request(request_id)
    db = get_db()
    near_fraction = float(get_setting(db, "near_due_fraction", "0.25"))
    return render_template("work/detail.html", req=req,
                           history=get_history(request_id),
                           dl_state=deadline_state(req, near_fraction))


def _parse_due(raw):
    """'2026-07-29T14:00' (datetime-local) -> datetime | None."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M")
    except ValueError:
        abort(400, "Неверный формат срока")


def _do_action(request_id, action, *, comment=None, new_due=None):
    try:
        change_status(request_id, action, "user", g.user["full_name"],
                      user_id=g.user["id"], comment=comment, new_due=new_due)
    except TransitionError as e:
        flash(str(e), "error")
        return False
    return True


@bp.route("/<int:request_id>/accept", methods=("POST",))
@login_required
def accept(request_id):
    _load_visible_request(request_id)
    new_due = _parse_due(request.form.get("new_due"))
    comment = request.form.get("comment", "").strip() or None
    if new_due and not comment:
        flash("При изменении срока укажите причину", "error")
    elif _do_action(request_id, "accepted", comment=comment, new_due=new_due):
        flash("Заявка принята в работу", "success")
    return redirect(url_for("work.detail", request_id=request_id))


@bp.route("/<int:request_id>/done", methods=("POST",))
@login_required
def done(request_id):
    _load_visible_request(request_id)
    comment = request.form.get("comment", "").strip()
    if not comment:
        flash("Опишите, что было сделано — поле обязательно", "error")
    elif _do_action(request_id, "done", comment=comment):
        flash("Заявка отмечена выполненной. Ожидает подтверждения заявителя.",
              "success")
    return redirect(url_for("work.detail", request_id=request_id))


@bp.route("/<int:request_id>/reject", methods=("POST",))
@login_required
def reject(request_id):
    _load_visible_request(request_id)
    comment = request.form.get("comment", "").strip()
    if not comment:
        flash("Укажите причину отклонения — поле обязательно", "error")
    elif _do_action(request_id, "rejected", comment=comment):
        flash("Заявка отклонена", "success")
    return redirect(url_for("work.detail", request_id=request_id))


@bp.route("/<int:request_id>/due", methods=("POST",))
@login_required
def due(request_id):
    _load_visible_request(request_id)
    new_due = _parse_due(request.form.get("new_due"))
    comment = request.form.get("comment", "").strip()
    if not new_due:
        flash("Укажите новый срок", "error")
    elif not comment:
        flash("Укажите причину переноса срока — поле обязательно", "error")
    elif _do_action(request_id, "due_changed", comment=comment, new_due=new_due):
        flash("Срок исполнения изменён", "success")
    return redirect(url_for("work.detail", request_id=request_id))
