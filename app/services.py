"""Доменная логика: создание заявок и переходы статусов.

Все изменения статусов идут ТОЛЬКО через change_status() — она валидирует
переход, обновляет requests и пишет request_history в одной транзакции.
Здесь же — единственная точка для будущего подключения уведомлений.
"""
import secrets
from datetime import timedelta

from .db import get_db
from .util import DT_FMT, now, now_str, parse_dt

STATUS_LABELS = {
    "new": "Новая",
    "in_progress": "В работе",
    "done": "Выполнена",
    "confirmed": "Подтверждена",
    "rejected": "Отклонена",
}

ACTION_LABELS = {
    "created": "Заявка подана",
    "accepted": "Принята в работу",
    "due_changed": "Срок исполнения изменён",
    "done": "Отмечена выполненной",
    "confirmed": "Исполнение подтверждено заявителем",
    "returned": "Возвращена в работу заявителем",
    "rejected": "Отклонена",
}

# action -> (допустимые статусы "из", статус "в"; None = статус не меняется)
TRANSITIONS = {
    "accepted": ({"new"}, "in_progress"),
    "done": ({"in_progress"}, "done"),
    "confirmed": ({"done"}, "confirmed"),
    "returned": ({"done"}, "in_progress"),
    "rejected": ({"new", "in_progress"}, "rejected"),
    "due_changed": ({"new", "in_progress"}, None),
}


class TransitionError(Exception):
    """Недопустимый переход статуса."""


def create_request(department_id, category_id, priority_id, description,
                   location, applicant_name, applicant_contact, inventory_number=None):
    """Создаёт заявку: служба по категории, срок по SLA приоритета.

    Возвращает (id, track_token).
    """
    db = get_db()
    category = db.execute(
        "SELECT id, service_id FROM categories WHERE id = ? AND is_active = 1",
        (category_id,),
    ).fetchone()
    priority = db.execute(
        "SELECT id, sla_hours FROM priorities WHERE id = ? AND is_active = 1",
        (priority_id,),
    ).fetchone()
    department = db.execute(
        "SELECT id FROM departments WHERE id = ? AND is_active = 1",
        (department_id,),
    ).fetchone()
    if not (category and priority and department):
        raise ValueError("Неверный отдел, категория или приоритет")

    created = now()
    due = created + timedelta(hours=priority["sla_hours"])
    token = secrets.token_urlsafe(8)

    cur = db.execute(
        "INSERT INTO requests (track_token, department_id, category_id, service_id, "
        " priority_id, description, location, inventory_number, applicant_name, "
        " applicant_contact, status, created_at, due_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)",
        (token, department_id, category_id, category["service_id"], priority_id,
         description, location or None, inventory_number or None, applicant_name,
         applicant_contact, created.strftime(DT_FMT), due.strftime(DT_FMT)),
    )
    request_id = cur.lastrowid
    db.execute(
        "INSERT INTO request_history (request_id, actor_type, actor_name, action, "
        " status_from, status_to, created_at) "
        "VALUES (?, 'applicant', ?, 'created', NULL, 'new', ?)",
        (request_id, applicant_name, created.strftime(DT_FMT)),
    )
    db.commit()
    return request_id, token


def change_status(request_id, action, actor_type, actor_name, user_id=None,
                  comment=None, new_due=None):
    """Выполняет переход по заявке и пишет историю. Бросает TransitionError.

    new_due (datetime) — новый срок для действий accepted / due_changed.
    """
    if action not in TRANSITIONS:
        raise TransitionError(f"Неизвестное действие: {action}")

    db = get_db()
    req = db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if req is None:
        raise TransitionError("Заявка не найдена")

    allowed_from, status_to = TRANSITIONS[action]
    if req["status"] not in allowed_from:
        raise TransitionError(
            f"Действие «{ACTION_LABELS[action]}» недоступно для заявки "
            f"в статусе «{STATUS_LABELS[req['status']]}»"
        )

    ts = now_str()
    sets, params = [], []
    if status_to:
        sets.append("status = ?")
        params.append(status_to)

    if action == "accepted":
        sets += ["accepted_at = ?", "accepted_by = ?"]
        params += [ts, user_id]
    elif action == "done":
        sets += ["done_at = ?", "done_comment = ?"]
        params += [ts, comment]
    elif action in ("confirmed", "rejected"):
        sets.append("closed_at = ?")
        params.append(ts)
    elif action == "returned":
        # Сбрасываем отметку выполнения — заявка снова в работе.
        sets += ["done_at = NULL", "done_comment = NULL"]

    due_before = due_after = None
    if new_due is not None:
        due_after = new_due.strftime(DT_FMT)
        if due_after != req["due_at"]:
            due_before = req["due_at"]
            sets.append("due_at = ?")
            params.append(due_after)
        else:
            due_after = None

    if sets:
        params.append(request_id)
        db.execute(f"UPDATE requests SET {', '.join(sets)} WHERE id = ?", params)

    db.execute(
        "INSERT INTO request_history (request_id, actor_type, user_id, actor_name, "
        " action, status_from, status_to, comment, due_before, due_after, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (request_id, actor_type, user_id, actor_name, action,
         req["status"], status_to or req["status"], comment,
         due_before, due_after, ts),
    )
    # Смена срока при принятии — отдельная строка истории, чтобы причина
    # переноса не смешивалась с фактом принятия.
    if action == "accepted" and due_after:
        db.execute(
            "INSERT INTO request_history (request_id, actor_type, user_id, actor_name, "
            " action, status_from, status_to, comment, due_before, due_after, created_at) "
            "VALUES (?, ?, ?, ?, 'due_changed', ?, ?, ?, ?, ?, ?)",
            (request_id, actor_type, user_id, actor_name,
             status_to, status_to, comment, due_before, due_after, ts),
        )
    db.commit()
    # Точка подключения уведомлений (email/telegram) — вызвать здесь.


def get_request(request_id=None, token=None):
    """Заявка со всеми связанными названиями (или None)."""
    db = get_db()
    where, param = ("r.id = ?", request_id) if request_id else ("r.track_token = ?", token)
    return db.execute(
        f"""SELECT r.*, d.name AS department_name, c.name AS category_name,
                   s.name AS service_name, p.name AS priority_name, p.sla_hours,
                   u.full_name AS accepted_by_name
            FROM requests r
            JOIN departments d ON d.id = r.department_id
            JOIN categories c ON c.id = r.category_id
            JOIN services s ON s.id = r.service_id
            JOIN priorities p ON p.id = r.priority_id
            LEFT JOIN users u ON u.id = r.accepted_by
            WHERE {where}""",
        (param,),
    ).fetchone()


def get_history(request_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM request_history WHERE request_id = ? ORDER BY id",
        (request_id,),
    ).fetchall()
