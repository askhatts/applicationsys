-- Все даты/время хранятся как TEXT в формате 'YYYY-MM-DD HH:MM:SS' (локальное время).

CREATE TABLE departments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    grp        TEXT    NOT NULL CHECK (grp IN ('adm', 'clin', 'diag', 'aux')),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE services (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    service_id INTEGER NOT NULL REFERENCES services (id),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE priorities (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    sla_hours  INTEGER NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    login         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    full_name     TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('admin', 'executor')),
    service_id    INTEGER REFERENCES services (id),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL
);

CREATE TABLE requests (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    track_token       TEXT    NOT NULL UNIQUE,
    department_id     INTEGER NOT NULL REFERENCES departments (id),
    category_id       INTEGER NOT NULL REFERENCES categories (id),
    -- Служба-исполнитель: снимок маппинга категория->служба на момент подачи.
    service_id        INTEGER NOT NULL REFERENCES services (id),
    priority_id       INTEGER NOT NULL REFERENCES priorities (id),
    description       TEXT    NOT NULL,
    location          TEXT,
    inventory_number  TEXT,
    applicant_name    TEXT    NOT NULL,
    applicant_contact TEXT    NOT NULL,
    status            TEXT    NOT NULL DEFAULT 'new'
                      CHECK (status IN ('new', 'in_progress', 'done', 'confirmed', 'rejected')),
    created_at        TEXT    NOT NULL,
    due_at            TEXT    NOT NULL,
    accepted_at       TEXT,
    accepted_by       INTEGER REFERENCES users (id),
    done_at           TEXT,
    done_comment      TEXT,
    closed_at         TEXT
);

CREATE INDEX idx_requests_status         ON requests (status);
CREATE INDEX idx_requests_service_status ON requests (service_id, status);
CREATE INDEX idx_requests_created        ON requests (created_at);

CREATE TABLE request_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  INTEGER NOT NULL REFERENCES requests (id),
    actor_type  TEXT    NOT NULL CHECK (actor_type IN ('applicant', 'user', 'system')),
    user_id     INTEGER REFERENCES users (id),
    actor_name  TEXT    NOT NULL,
    action      TEXT    NOT NULL CHECK (action IN
                ('created', 'accepted', 'due_changed', 'done', 'confirmed', 'returned', 'rejected')),
    status_from TEXT,
    status_to   TEXT,
    comment     TEXT,
    due_before  TEXT,
    due_after   TEXT,
    created_at  TEXT    NOT NULL
);

CREATE INDEX idx_history_request ON request_history (request_id);

CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
