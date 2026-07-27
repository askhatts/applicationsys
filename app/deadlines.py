"""Просрочено / близко к сроку.

Считаем календарными часами на лету — без фоновых задач и флагов в БД.
due_at = created_at + sla_hours приоритета (см. services.create_request).
«1 рабочий день» намеренно упрощён до 24 календарных часов; SLA-часы
редактируются в админке. Учёт рабочего календаря при необходимости
добавляется только в этом модуле.
"""
from .util import now, parse_dt

OPEN_STATUSES = ("new", "in_progress")


def deadline_state(req, near_fraction=0.25):
    """'overdue' | 'near' | 'ok' | None (для закрытых/выполненных заявок)."""
    if req["status"] not in OPEN_STATUSES:
        return None
    due = parse_dt(req["due_at"])
    current = now()
    if current > due:
        return "overdue"
    sla_hours = req["sla_hours"] if "sla_hours" in req.keys() else None
    if sla_hours:
        margin_h = max(1.0, sla_hours * near_fraction)
        remaining_h = (due - current).total_seconds() / 3600
        if remaining_h < margin_h:
            return "near"
    return "ok"


def done_late(req):
    """Выполнена/подтверждена, но с нарушением срока."""
    if req["status"] not in ("done", "confirmed") or not req["done_at"]:
        return False
    return parse_dt(req["done_at"]) > parse_dt(req["due_at"])
