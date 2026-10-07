"""Модуль управления задачами (TaskModule).

Помимо обычных операций создания и изменения здесь работает конечный
автомат статусов из модуля app.states.
"""
from .. import db, states
from ..errors import bad_request, conflict, forbidden, not_found
from ..validate import as_int, check_choice, check_date, require
from ..log import LOG

PRIORITIES = ("low", "normal", "high")


def list_tasks(ctx):
    """Список задач с фильтрами по проекту, исполнителю, статусу и сроку."""
    page = max(1, int(ctx.query.get("page", 1)))
    size = min(100, max(1, int(ctx.query.get("size", 20))))
    conditions, args = [], []
    if ctx.query.get("project_id"):
        conditions.append("project_id = ?")
        args.append(as_int(ctx.query["project_id"], "project_id"))
    if ctx.query.get("assignee_id"):
        conditions.append("assignee_id = ?")
        args.append(as_int(ctx.query["assignee_id"], "assignee_id"))
    if ctx.query.get("status"):
        conditions.append("status = ?")
        args.append(check_choice(ctx.query["status"], states.STATUSES, "status"))
    if ctx.query.get("overdue") == "1":
        conditions.append("due_date IS NOT NULL AND due_date < date('now')"
                          " AND status NOT IN ('done', 'rejected')")
    if ctx.user["role"] == "executor":
        conditions.append("(assignee_id = ? OR author_id = ?)")
        args.extend([ctx.user["id"], ctx.user["id"]])
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    total = ctx.con.execute("SELECT COUNT(*) AS n FROM tasks" + where,
                            args).fetchone()["n"]
    rows = ctx.con.execute(
        "SELECT * FROM tasks" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
        args + [size, (page - 1) * size]).fetchall()
    return 200, {"items": [task_view(ctx, r) for r in rows], "total": total,
                 "page": page, "size": size}


def get_task(ctx):
    """Карточка задачи с историей переходов."""
    task = load_task(ctx, int(ctx.params["id"]))
    history = ctx.con.execute(
        "SELECT * FROM task_status_history WHERE task_id = ? ORDER BY id",
        (task["id"],)).fetchall()
    data = task_view(ctx, task)
    data["history"] = [history_view(ctx, row) for row in history]
    return 200, {"task": data}


def create_task(ctx):
    """Создание задачи (менеджер или администратор)."""
    body = ctx.body
    require(body, "project_id", "title")
    project_id = as_int(body["project_id"], "project_id")
    if ctx.con.execute("SELECT id FROM projects WHERE id = ?",
                       (project_id,)).fetchone() is None:
        raise not_found("Проект не найден")
    assignee_id = body.get("assignee_id")
    if assignee_id:
        assignee_id = as_int(assignee_id, "assignee_id")
        check_user(ctx, assignee_id)
    due_date = check_date(body.get("due_date"), "due_date")
    if due_date and due_date < db.now()[:10]:
        raise bad_request("Срок не может быть раньше текущей даты")
    cursor = ctx.con.execute(
        "INSERT INTO tasks (project_id, title, description, status, priority,"
        " assignee_id, author_id, due_date, created_at, updated_at)"
        " VALUES (?, ?, ?, 'new', ?, ?, ?, ?, ?, ?)",
        (project_id, body["title"].strip(), body.get("description", ""),
         check_choice(body.get("priority", "normal"), PRIORITIES, "priority"),
         assignee_id, ctx.user["id"], due_date, db.now(), db.now()))
    ctx.con.commit()
    task = ctx.con.execute("SELECT * FROM tasks WHERE id = ?",
                           (cursor.lastrowid,)).fetchone()
    LOG.info("task.created", extra={"extra_fields": {"task_id": task["id"]}})
    return 201, {"task": task_view(ctx, task)}


def update_task(ctx):
    """Изменение задачи (менеджер или администратор)."""
    task = load_task(ctx, int(ctx.params["id"]))
    body = ctx.body
    assignee_id = body.get("assignee_id", task["assignee_id"])
    if assignee_id:
        assignee_id = as_int(assignee_id, "assignee_id")
        check_user(ctx, assignee_id)
    due_date = check_date(body.get("due_date", task["due_date"]), "due_date")
    ctx.con.execute(
        "UPDATE tasks SET title = ?, description = ?, priority = ?,"
        " assignee_id = ?, due_date = ?, updated_at = ? WHERE id = ?",
        (body.get("title", task["title"]).strip(),
         body.get("description", task["description"]),
         check_choice(body.get("priority", task["priority"]), PRIORITIES, "priority"),
         assignee_id, due_date, db.now(), task["id"]))
    ctx.con.commit()
    row = ctx.con.execute("SELECT * FROM tasks WHERE id = ?", (task["id"],)).fetchone()
    LOG.info("task.assignee_changed",
             extra={"extra_fields": {"task_id": task["id"]}})
    return 200, {"task": task_view(ctx, row)}


def delete_task(ctx):
    """Удаление задачи; завершённую задачу удалить нельзя."""
    task = load_task(ctx, int(ctx.params["id"]))
    if task["status"] == states.DONE:
        raise conflict("Завершённую задачу удалять нельзя")
    ctx.con.execute("DELETE FROM tasks WHERE id = ?", (task["id"],))
    ctx.con.commit()
    return 204, {}


def change_status(ctx):
    """Перевод задачи в новый статус по правилам конечного автомата."""
    task = load_task(ctx, int(ctx.params["id"]))
    require(ctx.body, "status")
    new_status = ctx.body["status"]
    if new_status == task["status"]:
        raise bad_request("Задача уже находится в этом статусе")
    is_assignee = task["assignee_id"] == ctx.user["id"]
    caption = states.check_transition(task["status"], new_status,
                                      ctx.user["role"], is_assignee)
    if new_status == states.IN_PROGRESS and task["assignee_id"] is None:
        raise bad_request("Нельзя начать работу без исполнителя")
    comment = (ctx.body.get("comment") or "").strip()
    if new_status == states.REJECTED and not comment:
        raise bad_request("При отклонении задачи нужен комментарий")
    ctx.con.execute(
        "INSERT INTO task_status_history (task_id, status_from, status_to,"
        " changed_by, comment, changed_at) VALUES (?, ?, ?, ?, ?, ?)",
        (task["id"], task["status"], new_status, ctx.user["id"], comment, db.now()))
    ctx.con.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                    (new_status, db.now(), task["id"]))
    ctx.con.commit()
    LOG.info("task.status_changed", extra={"extra_fields": {
        "task_id": task["id"], "from": task["status"], "to": new_status,
        "action": caption}})
    row = ctx.con.execute("SELECT * FROM tasks WHERE id = ?", (task["id"],)).fetchone()
    return 200, {"task": task_view(ctx, row)}


def task_history(ctx):
    """История переходов статусов задачи."""
    task = load_task(ctx, int(ctx.params["id"]))
    rows = ctx.con.execute(
        "SELECT * FROM task_status_history WHERE task_id = ? ORDER BY id",
        (task["id"],)).fetchall()
    return 200, {"items": [history_view(ctx, r) for r in rows]}


def load_task(ctx, task_id):
    """Находит задачу или возбуждает ошибку 404."""
    row = ctx.con.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise not_found("Задача не найдена")
    return row


def check_user(ctx, user_id):
    """Проверяет, что пользователь существует и активен."""
    row = ctx.con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise not_found("Исполнитель не найден")
    if not row["is_active"]:
        raise forbidden("Учётная запись исполнителя заблокирована")
    return row


def task_view(ctx, row):
    """Представление задачи для клиента."""
    assignee = None
    if row["assignee_id"]:
        user = ctx.con.execute("SELECT id, full_name FROM users WHERE id = ?",
                               (row["assignee_id"],)).fetchone()
        assignee = dict(user) if user else None
    overdue = bool(row["due_date"] and row["due_date"] < db.now()[:10]
                   and row["status"] not in (states.DONE, states.REJECTED))
    return {
        "id": row["id"], "project_id": row["project_id"], "title": row["title"],
        "description": row["description"], "status": row["status"],
        "status_title": states.STATUS_TITLES[row["status"]],
        "priority": row["priority"], "assignee": assignee,
        "author_id": row["author_id"], "due_date": row["due_date"],
        "overdue": overdue, "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "actions": states.available_transitions(
            row["status"], ctx.user["role"],
            row["assignee_id"] == ctx.user["id"]),
    }


def history_view(ctx, row):
    """Представление записи истории переходов."""
    user = ctx.con.execute("SELECT full_name FROM users WHERE id = ?",
                           (row["changed_by"],)).fetchone()
    return {
        "status_from": row["status_from"],
        "status_from_title": states.STATUS_TITLES[row["status_from"]],
        "status_to": row["status_to"],
        "status_to_title": states.STATUS_TITLES[row["status_to"]],
        "changed_by": user["full_name"] if user else "—",
        "comment": row["comment"], "changed_at": row["changed_at"],
    }
