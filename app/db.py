"""Единая база данных приложения (SQLite).

Здесь описана схема из шести таблиц и функции для работы с ней:
создание схемы, наполнение демонстрационными данными и получение соединения.
"""
import sqlite3
import time

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name     TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'executor'
                  CHECK (role IN ('admin', 'manager', 'executor')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    owner_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'paused', 'done')),
    start_date  TEXT,
    end_date    TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'new'
                CHECK (status IN ('new', 'in_progress', 'on_review',
                                  'done', 'rejected')),
    priority    TEXT NOT NULL DEFAULT 'normal'
                CHECK (priority IN ('low', 'normal', 'high')),
    assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    author_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    due_date    TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_status_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    status_from TEXT NOT NULL,
    status_to   TEXT NOT NULL,
    changed_by  INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    comment     TEXT NOT NULL DEFAULT '',
    changed_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT NOT NULL
                CHECK (report_type IN ('by_assignee', 'by_project', 'by_period')),
    project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    author_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    period_from TEXT,
    period_to   TEXT,
    format      TEXT NOT NULL CHECK (format IN ('pdf', 'xlsx')),
    file_name   TEXT NOT NULL,
    rows_count  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS password_resets (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at REAL NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee_id);
CREATE INDEX IF NOT EXISTS idx_history_task ON task_status_history(task_id);
"""


def now():
    """Текущее время в формате ISO без микросекунд."""
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def connect():
    """Открывает новое соединение с базой данных."""
    config.ensure_dirs()
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db(seed=True):
    """Создаёт таблицы и, если база пустая, добавляет демонстрационные данные."""
    con = connect()
    try:
        con.executescript(SCHEMA)
        con.commit()
        empty = con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0
        if seed and empty:
            seed_demo_data(con)
    finally:
        con.close()


def seed_demo_data(con):
    """Наполняет базу тремя пользователями, проектом и задачами."""
    from .security import hash_password

    created = now()
    users = [
        ("admin@example.com", "admin12345", "Администратор Системы", "admin"),
        ("manager@example.com", "manager12345", "Иванов Иван Иванович", "manager"),
        ("executor@example.com", "executor12345", "Петров Пётр Петрович", "executor"),
    ]
    for email, password, full_name, role in users:
        con.execute(
            "INSERT INTO users (email, password_hash, full_name, role, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (email, hash_password(password), full_name, role, created),
        )
    manager_id = con.execute(
        "SELECT id FROM users WHERE email = 'manager@example.com'").fetchone()["id"]
    executor_id = con.execute(
        "SELECT id FROM users WHERE email = 'executor@example.com'").fetchone()["id"]

    con.execute(
        "INSERT INTO projects (code, name, description, owner_id, status,"
        " start_date, end_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("PF-2026", "Внедрение ProjectFlow", "Учебный проект внедрения системы",
         manager_id, "active", "2026-09-01", "2026-12-20", created),
    )
    project_id = con.execute("SELECT id FROM projects WHERE code = 'PF-2026'"
                             ).fetchone()["id"]

    demo_tasks = [
        ("Собрать требования к системе", "new", "high", "2026-09-20"),
        ("Спроектировать схему базы данных", "in_progress", "normal", "2026-09-25"),
        ("Разработать модуль отчётов", "on_review", "normal", "2026-10-05"),
    ]
    for title, status, priority, due in demo_tasks:
        con.execute(
            "INSERT INTO tasks (project_id, title, description, status, priority,"
            " assignee_id, author_id, due_date, created_at, updated_at)"
            " VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?)",
            (project_id, title, status, priority, executor_id, manager_id, due,
             created, created),
        )
    con.commit()
