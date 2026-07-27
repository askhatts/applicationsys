"""Сквозной смоук-тест против запущенного dev-сервера (stdlib, без pytest).

Запуск:  python tools/smoke.py [http://127.0.0.1:5000]
Требует: init-db выполнен, пользователи admin/it1/energy1 существуют
(пароли берутся из переменных ниже).
"""
import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"
ADMIN = ("admin", "Admin2026!")
IT_USER = ("it1", "It2026!")
ENERGY_USER = ("energy1", "En2026!")

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, ok, detail))
    mark = "OK " if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))


class Session:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def get(self, path, expect_error=None):
        try:
            resp = self.opener.open(BASE + path)
            return resp.status, resp.geturl(), resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if expect_error:
                return e.code, e.geturl(), e.read().decode("utf-8", "replace")
            raise

    def get_bytes(self, path):
        resp = self.opener.open(BASE + path)
        return resp.status, resp.headers, resp.read()

    def post(self, path, data, expect_error=None):
        body = urllib.parse.urlencode(data).encode()
        try:
            resp = self.opener.open(BASE + path, data=body)
            return resp.status, resp.geturl(), resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if expect_error:
                return e.code, e.geturl(), e.read().decode("utf-8", "replace")
            raise

    def csrf(self, path):
        _, _, html = self.get(path)
        m = re.search(r'name="_csrf" value="([^"]+)"', html)
        assert m, f"CSRF-токен не найден на {path}"
        return m.group(1)

    def login(self, login, password):
        token = self.csrf("/login")
        status, url, html = self.post(
            "/login", {"_csrf": token, "login": login, "password": password})
        assert "Неверный логин" not in html, f"логин {login} не прошёл"
        return html


def main():
    print(f"Смоук-тест против {BASE}\n")

    # --- 1. Подача заявки анонимом ------------------------------------------
    applicant = Session()
    token = applicant.csrf("/")
    status, url, html = applicant.post("/submit", {
        "_csrf": token,
        "department_id": "16",   # Поликлиника
        "category_id": "2",      # Компьютеры и оргтехника -> IT
        "priority_id": "2",      # Срочная (24 ч)
        "description": "Не включается рабочий компьютер в регистратуре",
        "location": "1 этаж, регистратура",
        "applicant_name": "Смоук Тестовна",
        "applicant_contact": "внутр. 123",
    })
    m = re.search(r"/track/([^?\"]+)", url)
    check("Заявка подана, редирект на /track/<token>", bool(m), url)
    track_token = m.group(1) if m else ""
    req_id = re.search(r"Заявка №(\d+)", html)
    req_id = req_id.group(1) if req_id else "?"
    check("Показан номер заявки и код отслеживания",
          "track_token" not in html and track_token in html and "Новая" in html)
    check("Служба-исполнитель = IT (по категории)",
          "Служба цифровизации и IT" in html)

    # Пустая форма отклоняется
    status, _, html2 = applicant.post(
        "/submit", {"_csrf": applicant.csrf("/")}, expect_error=True)
    check("Пустая форма подачи отклонена (400)", status == 400)

    # --- 2. Изоляция служб ---------------------------------------------------
    energy = Session()
    energy.login(*ENERGY_USER)
    _, _, html = energy.get("/work/")
    check("Исполнитель другой службы НЕ видит заявку",
          f"№{req_id}" not in html)
    status, _, _ = energy.get(f"/work/{req_id}", expect_error=True)
    check("Прямой доступ к чужой заявке -> 403", status == 403)

    # --- 3. Исполнитель IT: принять/выполнить --------------------------------
    it = Session()
    it.login(*IT_USER)
    _, _, html = it.get("/work/")
    check("Исполнитель IT видит заявку", f"№{req_id}" in html)

    csrf = it.csrf(f"/work/{req_id}")
    _, _, html = it.post(f"/work/{req_id}/accept", {
        "_csrf": csrf, "new_due": "2026-07-29T15:00",
        "comment": "Ожидание блока питания"})
    check("Принята в работу со сменой срока",
          "В работе" in html and "29.07.2026 15:00" in html)
    check("История: принятие + смена срока с причиной",
          "Принята в работу" in html and "Срок исполнения изменён" in html
          and "Ожидание блока питания" in html)

    _, _, html = it.post(f"/work/{req_id}/done", {
        "_csrf": it.csrf(f"/work/{req_id}"),
        "comment": "Заменён блок питания, компьютер работает"})
    check("Отмечена выполненной", "Выполнена" in html)

    # --- 4. Заявитель: возврат и подтверждение -------------------------------
    _, _, html = applicant.get(f"/track/{track_token}")
    check("Заявителю доступны кнопки подтверждения", "Подтверждаю исполнение" in html)
    _, _, html = applicant.post(f"/track/{track_token}/return", {
        "_csrf": applicant.csrf(f"/track/{track_token}"),
        "comment": "Компьютер снова выключился через час"})
    check("Возврат в работу", "В работе" in html and "Возвращена в работу" in html)

    _, _, html = it.post(f"/work/{req_id}/done", {
        "_csrf": it.csrf(f"/work/{req_id}"),
        "comment": "Дополнительно заменена розетка, протестировано 2 часа"})
    check("Выполнена повторно", "Выполнена" in html)

    _, _, html = applicant.post(f"/track/{track_token}/confirm", {
        "_csrf": applicant.csrf(f"/track/{track_token}")})
    check("Заявитель подтвердил исполнение", "Подтверждена" in html)

    # Повторное подтверждение -> корректная ошибка
    # (на странице подтверждённой заявки форм нет — CSRF берём с главной)
    _, _, html = applicant.post(f"/track/{track_token}/confirm", {
        "_csrf": applicant.csrf("/")})
    check("Повторное подтверждение отклонено", "недоступно" in html)

    # --- 5. Негативные проверки доступа --------------------------------------
    status, _, _ = applicant.get("/track/nonexistent-token", expect_error=True)
    check("Битый токен -> 404", status == 404)

    fresh = Session()
    _, url, _ = fresh.get("/work/")
    check("/work без логина -> redirect на /login", "/login" in url)

    status, _, _ = it.get("/admin/", expect_error=True)
    check("/admin под исполнителем -> 403", status == 403)

    status, _, _ = fresh.get("/dashboard", expect_error=True)
    check("/dashboard без ключа и логина -> 403", status == 403)

    # --- 6. Дэшборд и экспорт (админ) ---------------------------------------
    admin = Session()
    admin.login(*ADMIN)
    _, _, html = admin.get("/dashboard")
    check("Дэшборд открывается под админом", "Мониторинг заявок" in html)
    m = re.search(r'key=([A-Za-z0-9_\-]+)', html)

    _, _, data_json = admin.get("/dashboard/data")
    check("JSON для графиков отдаётся",
          "by_department" in data_json and "Поликлиника" in data_json)

    status, headers, body = admin.get_bytes("/export.csv")
    text = body.decode("utf-8-sig")
    check("CSV: заголовки и заявка на месте",
          text.startswith("№;") and "Смоук Тестовна" in text)
    status, headers, body = admin.get_bytes("/export.xlsx")
    check("XLSX отдаётся (zip-магия PK)", body[:2] == b"PK")

    # Ключ просмотра
    _, _, settings_html = admin.get("/admin/settings")
    m = re.search(r"\?key=([A-Za-z0-9_\-]+)", settings_html)
    check("Ключ дэшборда виден в настройках", bool(m))
    if m:
        viewer = Session()
        status, _, html = viewer.get(f"/dashboard?key={m.group(1)}")
        check("Дэшборд по ключу без входа (read-only)",
              status == 200 and "режим просмотра" in html)
        status, _, _ = viewer.get("/dashboard?key=wrong", expect_error=True)
        check("Неверный ключ -> 403", status == 403)

    # --- Итог ----------------------------------------------------------------
    failed = [c for c in CHECKS if not c[1]]
    print(f"\nПройдено {len(CHECKS) - len(failed)} из {len(CHECKS)} проверок")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
