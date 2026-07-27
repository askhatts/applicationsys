"""Проверка просрочки: подать заявку, сдвинуть due_at в прошлое, проверить
красную подсветку и счётчик «Просрочено» на дэшборде."""
import re
import sqlite3
import sys

sys.path.insert(0, "tools")
from smoke import ADMIN, BASE, Session  # noqa: E402

applicant = Session()
token = applicant.csrf("/")
status, url, html = applicant.post("/submit", {
    "_csrf": token,
    "department_id": "10",   # Отделение хирургии
    "category_id": "4",      # Кондиционеры и вентиляция
    "priority_id": "1",      # Аварийная (4 ч)
    "description": "Не работает вентиляция в операционной — проверка просрочки",
    "applicant_name": "Тест Просрочки",
    "applicant_contact": "внутр. 999",
})
req_id = re.search(r"Заявка №(\d+)", html).group(1)
print(f"Создана заявка №{req_id} (Аварийная, 4 ч)")

db = sqlite3.connect("instance/app.db")
db.execute("UPDATE requests SET created_at = datetime('now','localtime','-6 hours'), "
           "due_at = datetime('now','localtime','-2 hours') WHERE id = ?", (req_id,))
db.commit()
db.close()
print("due_at сдвинут на 2 часа в прошлое")

admin = Session()
admin.login(*ADMIN)
_, _, html = admin.get("/dashboard")
overdue_counter = re.search(
    r'<div class="num">(\d+)</div><div class="lbl">Просрочено</div>', html)
row_red = f'row-overdue' in html and f"№{req_id}" in html
print("Счётчик «Просрочено»:", overdue_counter.group(1) if overdue_counter else "не найден")
print("Красная строка в таблице:", "да" if row_red else "НЕТ")

_, _, work_html = admin.get("/work/")
first_row = work_html.split('<tr class="')[1][:200] if '<tr class="' in work_html else ""
print("Просроченная — первой в /work:",
      "да" if first_row.startswith("row-overdue") and f"№{req_id}" in first_row else "НЕТ")

assert overdue_counter and int(overdue_counter.group(1)) >= 1
assert row_red
print("\nПроверка просрочки пройдена")
