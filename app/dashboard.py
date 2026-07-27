"""Дэшборд-мониторинг и экспорт заявок.

Доступ: администратор ИЛИ read-only по ключу ?key=<dashboard_view_token>
(ключ выдаётся руководству, действий по заявкам не даёт).
"""
import csv
import functools
import io
from datetime import date

from flask import (Blueprint, abort, g, jsonify, render_template, request,
                   send_file)

from .db import get_db
from .deadlines import deadline_state, done_late
from .util import get_setting

bp = Blueprint("dashboard", __name__)


def dashboard_access(view):
    """Админ по сессии или просмотр по ключу."""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        g.view_only = False
        if g.user is not None and g.user["role"] == "admin":
            return view(*args, **kwargs)
        key = request.args.get("key", "")
        token = get_setting(get_db(), "dashboard_view_token")
        if key and token and key == token:
            g.view_only = True
            return view(*args, **kwargs)
        abort(403)
    return wrapped


def _period_filter():
    """(where_sql, params, date_from, date_to) по ?from=YYYY-MM-DD&to=YYYY-MM-DD."""
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    where, params = [], []
    if date_from:
        where.append("r.created_at >= ?")
        params.append(date_from + " 00:00:00")
    if date_to:
        where.append("r.created_at <= ?")
        params.append(date_to + " 23:59:59")
    return where, params, date_from, date_to


FILTER_COLUMNS = {"service": "r.service_id", "department": "r.department_id",
                  "category": "r.category_id", "status": "r.status"}


def _list_filters():
    where, params = [], []
    for arg, col in FILTER_COLUMNS.items():
        if request.args.get(arg):
            where.append(f"{col} = ?")
            params.append(request.args[arg])
    return where, params


def _fetch_requests():
    where, params, *_ = _period_filter()
    w2, p2 = _list_filters()
    where += w2
    params += p2
    sql = """
        SELECT r.*, d.name AS department_name, c.name AS category_name,
               s.name AS service_name, p.name AS priority_name, p.sla_hours
        FROM requests r
        JOIN departments d ON d.id = r.department_id
        JOIN categories c ON c.id = r.category_id
        JOIN services s ON s.id = r.service_id
        JOIN priorities p ON p.id = r.priority_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.id DESC"
    return get_db().execute(sql, params).fetchall()


@bp.route("/dashboard")
@dashboard_access
def index():
    db = get_db()
    where, params, date_from, date_to = _period_filter()
    base = "FROM requests r"
    wsql = (" WHERE " + " AND ".join(where)) if where else ""

    def count(extra="", extra_params=()):
        return db.execute(
            f"SELECT COUNT(*) c {base}{wsql}"
            + (f" {'AND' if wsql else 'WHERE'} {extra}" if extra else ""),
            params + list(extra_params),
        ).fetchone()["c"]

    counters = {
        "total": count(),
        "new": count("r.status = 'new'"),
        "in_progress": count("r.status = 'in_progress'"),
        "done": count("r.status = 'done'"),
        "confirmed": count("r.status = 'confirmed'"),
        "rejected": count("r.status = 'rejected'"),
        "overdue": count("r.status IN ('new','in_progress') "
                         "AND r.due_at < datetime('now','localtime')"),
        "done_late": count("r.status IN ('done','confirmed') "
                           "AND r.done_at > r.due_at"),
    }
    returned_sql = ("SELECT COUNT(*) c FROM request_history h "
                    "JOIN requests r ON r.id = h.request_id "
                    "WHERE h.action = 'returned'")
    if where:
        returned_sql += " AND " + " AND ".join(where)
    counters["returned"] = db.execute(returned_sql, params).fetchone()["c"]

    rows = _fetch_requests()
    near_fraction = float(get_setting(db, "near_due_fraction", "0.25"))
    states = {r["id"]: deadline_state(r, near_fraction) for r in rows}
    late = {r["id"]: done_late(r) for r in rows}

    departments = db.execute(
        "SELECT * FROM departments WHERE is_active = 1 ORDER BY grp, sort_order").fetchall()
    services = db.execute("SELECT * FROM services ORDER BY name").fetchall()
    categories = db.execute(
        "SELECT * FROM categories WHERE is_active = 1 ORDER BY sort_order").fetchall()

    return render_template(
        "dashboard/dashboard.html", counters=counters, rows=rows,
        states=states, late=late, date_from=date_from, date_to=date_to,
        departments=departments, services=services, categories=categories,
        view_key=request.args.get("key", ""),
    )


@bp.route("/dashboard/data")
@dashboard_access
def data():
    """JSON-агрегации для Chart.js."""
    db = get_db()
    where, params, *_ = _period_filter()
    wsql = (" WHERE " + " AND ".join(where)) if where else ""
    and_open = (" AND " if wsql else " WHERE ")

    def rows_to_series(rows):
        return {"labels": [r["name"] for r in rows],
                "counts": [r["c"] for r in rows],
                "overdue": [r["o"] for r in rows]}

    by_department = db.execute(f"""
        SELECT d.name AS name, COUNT(*) c,
               SUM(CASE WHEN r.status IN ('new','in_progress')
                        AND r.due_at < datetime('now','localtime')
                   THEN 1 ELSE 0 END) o
        FROM requests r JOIN departments d ON d.id = r.department_id
        {wsql} GROUP BY d.id ORDER BY c DESC LIMIT 15""", params).fetchall()

    by_service = db.execute(f"""
        SELECT s.name AS name, COUNT(*) c,
               SUM(CASE WHEN r.status IN ('new','in_progress')
                        AND r.due_at < datetime('now','localtime')
                   THEN 1 ELSE 0 END) o
        FROM requests r JOIN services s ON s.id = r.service_id
        {wsql} GROUP BY s.id ORDER BY c DESC""", params).fetchall()

    by_category = db.execute(f"""
        SELECT c.name AS name, COUNT(*) c
        FROM requests r JOIN categories c ON c.id = r.category_id
        {wsql} GROUP BY c.id ORDER BY c DESC""", params).fetchall()

    by_day = db.execute(f"""
        SELECT substr(r.created_at, 1, 10) AS day, COUNT(*) c
        FROM requests r
        {wsql}{and_open}r.created_at >= datetime('now','localtime','-30 days')
        GROUP BY day ORDER BY day""", params).fetchall()

    return jsonify({
        "by_department": rows_to_series(by_department),
        "by_service": rows_to_series(by_service),
        "by_category": {"labels": [r["name"] for r in by_category],
                        "counts": [r["c"] for r in by_category]},
        "by_day": {"labels": [r["day"] for r in by_day],
                   "counts": [r["c"] for r in by_day]},
    })


EXPORT_HEADERS = ["№", "Дата подачи", "Отдел", "Категория", "Служба-исполнитель",
                  "Приоритет", "Описание", "Место", "Заявитель", "Контакт",
                  "Статус", "Срок исполнения", "Принята", "Выполнена",
                  "Что сделано", "Закрыта"]


def _export_rows():
    from .services import STATUS_LABELS
    for r in _fetch_requests():
        yield [r["id"], r["created_at"], r["department_name"], r["category_name"],
               r["service_name"], r["priority_name"], r["description"],
               r["location"] or "", r["applicant_name"], r["applicant_contact"],
               STATUS_LABELS.get(r["status"], r["status"]), r["due_at"],
               r["accepted_at"] or "", r["done_at"] or "",
               r["done_comment"] or "", r["closed_at"] or ""]


@bp.route("/export.csv")
@dashboard_access
def export_csv():
    # utf-8-sig + ';' — чтобы русский Excel открывал файл двойным кликом.
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(EXPORT_HEADERS)
    writer.writerows(_export_rows())
    data = buf.getvalue().encode("utf-8-sig")
    return send_file(io.BytesIO(data), mimetype="text/csv",
                     as_attachment=True,
                     download_name=f"заявки_{date.today().isoformat()}.csv")


@bp.route("/export.xlsx")
@dashboard_access
def export_xlsx():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Заявки"
    ws.append(EXPORT_HEADERS)
    for row in _export_rows():
        ws.append(row)
    for col, width in zip(ws.columns,
                          (6, 17, 30, 22, 28, 11, 50, 18, 22, 15, 14, 17, 17, 17, 40, 17)):
        ws.column_dimensions[col[0].column_letter].width = width
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"заявки_{date.today().isoformat()}.xlsx")
