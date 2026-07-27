"""Общие помощники: время и настройки."""
from datetime import datetime

DT_FMT = "%Y-%m-%d %H:%M:%S"


def now():
    return datetime.now().replace(microsecond=0)


def now_str():
    return now().strftime(DT_FMT)


def parse_dt(s):
    if not s:
        return None
    return datetime.strptime(s, DT_FMT)


def fmt_dt(s):
    """'2026-07-27 09:15:33' -> '27.07.2026 09:15' (для шаблонов)."""
    dt = parse_dt(s) if isinstance(s, str) else s
    if dt is None:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


def get_setting(db, key, default=None):
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(db, key, value):
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
