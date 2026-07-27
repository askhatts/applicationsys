"""Служебные команды.

  python manage.py init-db [--force]        создать БД, справочники, админа
  python manage.py create-admin ЛОГИН       создать администратора
  python manage.py create-user ЛОГИН "ФИО" "Название службы"
                                            создать исполнителя службы
  python manage.py set-password ЛОГИН       сменить пароль пользователя
  python manage.py regen-dashboard-token    новый ключ просмотра дэшборда

Пароль можно передать флагом --password, иначе будет сгенерирован.
"""
import argparse
import os
import secrets
import sys

from app import create_app
from app.db import get_db


def _gen_password():
    return secrets.token_urlsafe(9)


def cmd_init_db(app, args):
    db_path = app.config["DATABASE"]
    if os.path.exists(db_path):
        if not args.force:
            print(f"БД уже существует: {db_path}\nЗапустите с --force для пересоздания "
                  "(ВСЕ ДАННЫЕ БУДУТ УДАЛЕНЫ).")
            sys.exit(1)
        os.remove(db_path)

    config_path = os.path.join(app.instance_path, "config.py")
    if not os.path.exists(config_path):
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(f"SECRET_KEY = {secrets.token_hex(32)!r}\n")
        print(f"Создан {config_path} со случайным SECRET_KEY")

    from app.seed import create_user, seed_all
    db = get_db()
    with open(os.path.join(os.path.dirname(__file__), "app", "schema.sql"),
              encoding="utf-8") as f:
        db.executescript(f.read())
    db.execute("PRAGMA journal_mode = WAL")
    seed_all(db)

    password = args.password or _gen_password()
    create_user(db, "admin", password, "Администратор", "admin")
    from app.util import get_setting
    print("База данных создана и заполнена справочниками.")
    print(f"  Администратор: логин admin, пароль: {password}")
    print(f"  Ключ просмотра дэшборда: /dashboard?key={get_setting(db, 'dashboard_view_token')}")


def _create_account(app, args, role):
    from app.seed import create_user
    db = get_db()
    service_id = None
    if role == "executor":
        svc = db.execute("SELECT id FROM services WHERE name = ?", (args.service,)).fetchone()
        if not svc:
            names = [r["name"] for r in db.execute("SELECT name FROM services ORDER BY id")]
            print(f"Служба «{args.service}» не найдена. Доступные:\n  " + "\n  ".join(names))
            sys.exit(1)
        service_id = svc["id"]
    password = args.password or _gen_password()
    create_user(db, args.login, password, args.full_name, role, service_id)
    print(f"Пользователь {args.login} ({role}) создан, пароль: {password}")


def cmd_set_password(app, args):
    from werkzeug.security import generate_password_hash
    db = get_db()
    password = args.password or _gen_password()
    cur = db.execute(
        "UPDATE users SET password_hash = ? WHERE login = ?",
        (generate_password_hash(password), args.login),
    )
    db.commit()
    if cur.rowcount == 0:
        print(f"Пользователь {args.login} не найден")
        sys.exit(1)
    print(f"Пароль для {args.login}: {password}")


def cmd_regen_token(app, args):
    from app.util import set_setting
    db = get_db()
    token = secrets.token_urlsafe(16)
    set_setting(db, "dashboard_view_token", token)
    db.commit()
    print(f"Новый ключ просмотра дэшборда: /dashboard?key={token}")


def main():
    parser = argparse.ArgumentParser(description="Служебные команды приложения")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init-db", help="создать БД и справочники")
    p.add_argument("--force", action="store_true")
    p.add_argument("--password", help="пароль администратора")

    p = sub.add_parser("create-admin", help="создать администратора")
    p.add_argument("login")
    p.add_argument("full_name", nargs="?", default="Администратор")
    p.add_argument("--password")

    p = sub.add_parser("create-user", help="создать исполнителя")
    p.add_argument("login")
    p.add_argument("full_name")
    p.add_argument("service", help="точное название службы-исполнителя")
    p.add_argument("--password")

    p = sub.add_parser("set-password", help="сменить пароль")
    p.add_argument("login")
    p.add_argument("--password")

    sub.add_parser("regen-dashboard-token", help="новый ключ дэшборда")

    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        if args.cmd == "init-db":
            cmd_init_db(app, args)
        elif args.cmd == "create-admin":
            _create_account(app, args, "admin")
        elif args.cmd == "create-user":
            _create_account(app, args, "executor")
        elif args.cmd == "set-password":
            cmd_set_password(app, args)
        elif args.cmd == "regen-dashboard-token":
            cmd_regen_token(app, args)


if __name__ == "__main__":
    main()
