"""Модуль формирования отчётов (ReportModule).

Отчёты строятся по исполнителю, по проекту и за период,
выгружаются в PDF или Excel и сохраняются в каталоге var/reports.
"""
from pathlib import Path

from .. import config, db, exporters
from ..errors import forbidden, not_found
from ..validate import check_choice, check_date, require
from ..log import LOG
from . import projects as projects_api

REPORT_TYPES = ("by_assignee", "by_project", "by_period")
FORMATS = ("pdf", "xlsx")

TITLES = {
    "by_assignee": "Отчёт по исполнителю",
    "by_project": "Отчёт по проекту",
    "by_period": "Отчёт за период",
}


def create_report(ctx):
    """Формирует отчёт, сохраняет файл и запись о нём в базе данных."""
    body = ctx.body
    require(body, "report_type")
    report_type = check_choice(body["report_type"], REPORT_TYPES, "report_type")
    fmt = check_choice(body.get("format", "pdf"), FORMATS, "format")
    period_from = check_date(body.get("period_from"), "period_from")
    period_to = check_date(body.get("period_to"), "period_to")

    project_id = body.get("project_id")
    assignee_id = body.get("assignee_id")
    if report_type == "by_project" and not project_id:
        require(body, "project_id")
    if report_type == "by_assignee" and not assignee_id:
        require(body, "assignee_id")

    columns, rows, filters = collect(report_type, ctx, project_id, assignee_id,
                                     period_from, period_to)
    if ctx.user["role"] == "executor":
        for row in rows:
            if row.get("_owner") not in (None, ctx.user["id"]):
                raise forbidden("Исполнитель видит отчёты только по своим задачам")
    for row in rows:
        row.pop("_owner", None)

    summary = build_summary(ctx, report_type, rows, period_from, period_to,
                            project_id, assignee_id)
    file_name = "report_{}_{}_{}.{}".format(report_type, ctx.user["id"],
                                            db.now().replace(":", "").replace("-", ""),
                                            fmt)
    config.ensure_dirs()
    exporters.export(fmt, str(config.REPORTS_DIR / file_name), TITLES[report_type],
                     columns, rows, summary)
    cursor = ctx.con.execute(
        "INSERT INTO reports (report_type, project_id, author_id, period_from,"
        " period_to, format, file_name, rows_count, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (report_type, project_id, ctx.user["id"], period_from, period_to, fmt,
         file_name, len(rows), db.now()))
    ctx.con.commit()
    row = ctx.con.execute("SELECT * FROM reports WHERE id = ?",
                          (cursor.lastrowid,)).fetchone()
    LOG.info("report.generated", extra={"extra_fields": {
        "report_id": row["id"], "format": fmt, "rows": len(rows)}})
    return 201, {"report": report_view(row), "filters": filters,
                 "download_url": "/api/v1/reports/{}/download".format(row["id"])}


def list_reports(ctx):
    """Список сформированных отчётов."""
    if ctx.user["role"] == "executor":
        rows = ctx.con.execute("SELECT * FROM reports WHERE author_id = ?"
                               " ORDER BY id DESC", (ctx.user["id"],)).fetchall()
    else:
        rows = ctx.con.execute("SELECT * FROM reports ORDER BY id DESC").fetchall()
    return 200, {"items": [report_view(r) for r in rows], "total": len(rows)}


def download_report(ctx):
    """Отдаёт файл отчёта."""
    row = ctx.con.execute("SELECT * FROM reports WHERE id = ?",
                          (int(ctx.params["id"]),)).fetchone()
    if row is None:
        raise not_found("Отчёт не найден")
    if ctx.user["role"] == "executor" and row["author_id"] != ctx.user["id"]:
        raise forbidden("Нет доступа к этому отчёту")
    path = Path(config.REPORTS_DIR) / row["file_name"]
    if not path.exists():
        raise not_found("Файл отчёта не найден на диске")
    content_type = ("application/pdf" if row["format"] == "pdf"
                    else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return 200, path.read_bytes(), content_type


def collect(report_type, ctx, project_id, assignee_id, period_from, period_to):
    """Собирает строки отчёта в зависимости от его вида."""
    filters = {"period_from": period_from, "period_to": period_to}
    if report_type == "by_assignee":
        user = ctx.con.execute("SELECT * FROM users WHERE id = ?",
                               (int(assignee_id),)).fetchone()
        if user is None:
            raise not_found("Исполнитель не найден")
        filters["assignee"] = user["full_name"]
        rows = ctx.con.execute(
            "SELECT t.*, p.name AS project_name FROM tasks t"
            " JOIN projects p ON p.id = t.project_id"
            " WHERE t.assignee_id = ? ORDER BY t.id", (user["id"],)).fetchall()
        columns = ["№", "Задача", "Проект", "Статус", "Приоритет", "Срок"]
        return columns, [task_row(ctx, index, row, columns) for index, row in
                         enumerate(_filter_period(rows, period_from, period_to), 1)], filters

    if report_type == "by_project":
        project = projects_api.load_project(ctx, int(project_id))
        filters["project"] = "{} ({})".format(project["name"], project["code"])
        rows = ctx.con.execute(
            "SELECT t.*, p.name AS project_name FROM tasks t"
            " JOIN projects p ON p.id = t.project_id"
            " WHERE t.project_id = ? ORDER BY t.id", (project["id"],)).fetchall()
        columns = ["№", "Задача", "Исполнитель", "Статус", "Приоритет", "Срок"]
        return columns, [task_row(ctx, index, row, columns) for index, row in
                         enumerate(_filter_period(rows, period_from, period_to), 1)], filters

    rows = ctx.con.execute(
        "SELECT t.*, p.name AS project_name FROM tasks t"
        " JOIN projects p ON p.id = t.project_id"
        " ORDER BY t.id").fetchall()
    columns = ["№", "Задача", "Проект", "Исполнитель", "Статус", "Создана"]
    return columns, [task_row(ctx, index, row, columns) for index, row in
                     enumerate(_filter_period(rows, period_from, period_to), 1)], filters


def _filter_period(rows, period_from, period_to):
    """Оставляет задачи, созданные внутри указанного периода."""
    result = []
    for row in rows:
        created = row["created_at"][:10]
        if period_from and created < period_from:
            continue
        if period_to and created > period_to:
            continue
        result.append(row)
    return result


def task_row(ctx, index, row, columns):
    """Превращает запись задачи в строку отчёта."""
    from .. import states
    assignee = "—"
    if row["assignee_id"]:
        user = ctx.con.execute("SELECT full_name FROM users WHERE id = ?",
                               (row["assignee_id"],)).fetchone()
        assignee = user["full_name"] if user else "—"
    data = {
        "№": index,
        "Задача": row["title"],
        "Проект": row["project_name"],
        "Исполнитель": assignee,
        "Статус": states.STATUS_TITLES[row["status"]],
        "Приоритет": row["priority"],
        "Срок": row["due_date"] or "—",
        "Создана": row["created_at"][:10],
        "_owner": row["assignee_id"] or row["author_id"],
    }
    result = {name: data.get(name, "") for name in columns}
    result["_owner"] = data["_owner"]
    return result


def build_summary(ctx, report_type, rows, period_from, period_to, project_id,
                  assignee_id):
    """Строит текстовую сводку по отчёту."""
    from .. import states
    counters = {status: 0 for status in states.STATUSES}
    for row in rows:
        for code, title in states.STATUS_TITLES.items():
            if row.get("Статус") == title:
                counters[code] += 1
    total = len(rows)
    done = counters[states.DONE]
    percent = round(done * 100 / total) if total else 0
    period = "период: {} — {}".format(period_from or "начало", period_to or "текущая дата")
    lines = [
        "Сформирован: {} | {}".format(db.now().replace("T", " "), period),
        "Всего задач: {}".format(total),
        "Выполнено: {} ({} %)".format(done, percent),
        "В работе: {} | На проверке: {} | Отклонено: {}".format(
            counters[states.IN_PROGRESS], counters[states.ON_REVIEW],
            counters[states.REJECTED]),
    ]
    if report_type == "by_project":
        project = projects_api.load_project(ctx, int(project_id))
        lines.insert(1, "Проект: {} ({})".format(project["name"], project["code"]))
    if report_type == "by_assignee":
        user = ctx.con.execute("SELECT full_name FROM users WHERE id = ?",
                               (int(assignee_id),)).fetchone()
        lines.insert(1, "Исполнитель: {}".format(user["full_name"]))
    return lines


def report_view(row):
    """Представление отчёта для клиента."""
    return {
        "id": row["id"], "report_type": row["report_type"],
        "title": TITLES[row["report_type"]], "project_id": row["project_id"],
        "author_id": row["author_id"], "period_from": row["period_from"],
        "period_to": row["period_to"], "format": row["format"],
        "file_name": row["file_name"], "rows_count": row["rows_count"],
        "created_at": row["created_at"],
        "download_url": "/api/v1/reports/{}/download".format(row["id"]),
    }
