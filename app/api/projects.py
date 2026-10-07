"""Модуль работы с проектами (часть TaskModule)."""
from .. import db
from ..errors import ApiError, conflict, not_found
from ..validate import check_choice, check_date, require

STATUSES = ("active", "paused", "done")


def list_projects(ctx):
    """Постраничный список проектов с фильтром по статусу."""
    page = max(1, int(ctx.query.get("page", 1)))
    size = min(100, max(1, int(ctx.query.get("size", 20))))
    status = ctx.query.get("status")
    sql = "SELECT * FROM projects"
    args = []
    if status:
        check_choice(status, STATUSES, "status")
        sql += " WHERE status = ?"
        args.append(status)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    args.extend([size, (page - 1) * size])
    rows = ctx.con.execute(sql, args).fetchall()
    total = ctx.con.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]
    return 200, {"items": [project_view(r) for r in rows], "total": total,
                 "page": page, "size": size}


def get_project(ctx):
    """Карточка проекта с числом задач по статусам."""
    project = load_project(ctx, int(ctx.params["id"]))
    stats = ctx.con.execute(
        "SELECT status, COUNT(*) AS n FROM tasks WHERE project_id = ?"
        " GROUP BY status", (project["id"],)).fetchall()
    data = project_view(project)
    data["tasks_by_status"] = {row["status"]: row["n"] for row in stats}
    return 200, {"project": data}


def create_project(ctx):
    """Создание проекта (менеджер или администратор)."""
    body = ctx.body
    require(body, "code", "name")
    if ctx.con.execute("SELECT id FROM projects WHERE code = ?",
                       (body["code"].strip(),)).fetchone():
        raise conflict("Проект с таким кодом уже существует")
    status = check_choice(body.get("status", "active"), STATUSES, "status")
    cursor = ctx.con.execute(
        "INSERT INTO projects (code, name, description, owner_id, status,"
        " start_date, end_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (body["code"].strip(), body["name"].strip(), body.get("description", ""),
         ctx.user["id"], status, check_date(body.get("start_date"), "start_date"),
         check_date(body.get("end_date"), "end_date"), db.now()))
    ctx.con.commit()
    row = ctx.con.execute("SELECT * FROM projects WHERE id = ?",
                          (cursor.lastrowid,)).fetchone()
    return 201, {"project": project_view(row)}


def update_project(ctx):
    """Изменение проекта."""
    project = load_project(ctx, int(ctx.params["id"]))
    body = ctx.body
    fields = {
        "name": body.get("name", project["name"]),
        "description": body.get("description", project["description"]),
        "status": check_choice(body.get("status", project["status"]),
                               STATUSES, "status"),
        "start_date": check_date(body.get("start_date", project["start_date"]),
                                 "start_date"),
        "end_date": check_date(body.get("end_date", project["end_date"]),
                               "end_date"),
    }
    ctx.con.execute(
        "UPDATE projects SET name = ?, description = ?, status = ?,"
        " start_date = ?, end_date = ? WHERE id = ?",
        (fields["name"], fields["description"], fields["status"],
         fields["start_date"], fields["end_date"], project["id"]))
    ctx.con.commit()
    row = ctx.con.execute("SELECT * FROM projects WHERE id = ?",
                          (project["id"],)).fetchone()
    return 200, {"project": project_view(row)}


def delete_project(ctx):
    """Удаление проекта; запрещено, если в нём есть задачи."""
    project = load_project(ctx, int(ctx.params["id"]))
    count = ctx.con.execute("SELECT COUNT(*) AS n FROM tasks WHERE project_id = ?",
                            (project["id"],)).fetchone()["n"]
    if count:
        raise conflict("Нельзя удалить проект: в нём {} задач".format(count))
    ctx.con.execute("DELETE FROM projects WHERE id = ?", (project["id"],))
    ctx.con.commit()
    return 204, {}


def load_project(ctx, project_id):
    """Находит проект или возбуждает ошибку 404."""
    row = ctx.con.execute("SELECT * FROM projects WHERE id = ?",
                          (project_id,)).fetchone()
    if row is None:
        raise not_found("Проект не найден")
    return row


def project_view(row):
    """Представление проекта для клиента."""
    return {
        "id": row["id"], "code": row["code"], "name": row["name"],
        "description": row["description"], "owner_id": row["owner_id"],
        "status": row["status"], "start_date": row["start_date"],
        "end_date": row["end_date"], "created_at": row["created_at"],
    }
