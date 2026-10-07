#!/usr/bin/env python3
"""Демонстрационный проход по всем возможностям приложения.

Скрипт обращается к запущенному серверу как обычный клиент: регистрирует
пользователя, создаёт проект и задачу, проводит её по всем статусам и
формирует отчёты в PDF и Excel.

Запуск:  python tools/demo.py [адрес сервера]
"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
TOKEN = {"value": None}


def call(method, path, body=None, token=None):
    """Выполняет запрос к API и возвращает код и данные."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read()
            if not raw:
                return response.status, None
            if "json" in response.headers.get("Content-Type", ""):
                return response.status, json.loads(raw.decode("utf-8"))
            return response.status, raw
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            return error.code, json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return error.code, raw


def step(text):
    """Печатает заголовок шага демонстрации."""
    print("\n=== {} ===".format(text))


def main():
    """Проходит сценарий целиком."""
    step("Вход менеджера")
    status, data = call("POST", "/api/v1/auth/login", {
        "email": "manager@example.com", "password": "manager12345"})
    print("код:", status, "| пользователь:", data["user"]["full_name"],
          "| роль:", data["user"]["role"])
    token = data["access_token"]

    step("Создание проекта")
    status, project = call("POST", "/api/v1/projects", {
        "code": "DEMO-1", "name": "Демонстрационный проект",
        "description": "Проверка работы приложения"}, token)
    if status == 409:
        _, page = call("GET", "/api/v1/projects?size=100", token=token)
        project = {"project": [p for p in page["items"] if p["code"] == "DEMO-1"][0]}
    print("код:", status, "| проект:", project["project"]["name"],
          "| id:", project["project"]["id"])
    project_id = project["project"]["id"]

    step("Создание задачи")
    _, users = call("GET", "/api/v1/users", token=token)
    executor = [u for u in users["items"] if u["email"] == "executor@example.com"][0]
    status, task = call("POST", "/api/v1/tasks", {
        "project_id": project_id, "title": "Подготовить отчёт для руководителя",
        "priority": "high", "assignee_id": executor["id"],
        "due_date": "2026-12-01"}, token)
    print("код:", status, "| задача:", task["task"]["title"],
          "| статус:", task["task"]["status_title"])
    task_id = task["task"]["id"]

    step("Проведение задачи по статусам")
    for target in ("in_progress", "on_review", "done"):
        body = {"status": target}
        status, data = call("PATCH", "/api/v1/tasks/{}/status".format(task_id),
                            body, token)
        print("переход в «{}»: код {} | {}".format(
            target, status, data["task"]["status_title"]))

    step("Запрещённый переход")
    status, data = call("PATCH", "/api/v1/tasks/{}/status".format(task_id),
                        {"status": "new"}, token)
    print("попытка вернуть завершённую задачу в «новая»: код", status,
          "|", data["detail"])

    step("История переходов")
    _, history = call("GET", "/api/v1/tasks/{}/history".format(task_id), token=token)
    for item in history["items"]:
        print("  {} -> {} ({})".format(item["status_from_title"],
                                       item["status_to_title"], item["changed_by"]))

    step("Отчёты")
    for fmt in ("xlsx", "pdf"):
        status, report = call("POST", "/api/v1/reports", {
            "report_type": "by_project", "project_id": project_id,
            "format": fmt}, token)
        if status == 503:
            print("формат {}: недоступен ({})".format(fmt, report["detail"]))
            continue
        info = report["report"]
        print("формат {}: код {} | файл {} | строк {}".format(
            fmt, status, info["file_name"], info["rows_count"]))
        raw = call("GET", info["download_url"] + "?token=" + token)[1]
        print("   скачано байт:", len(raw))

    step("Отчёты в списке")
    _, reports = call("GET", "/api/v1/reports", token=token)
    for item in reports["items"][:5]:
        print("  №{} {} [{}], строк {}".format(item["id"], item["title"],
                                               item["format"], item["rows_count"]))
    print("\nДемонстрация завершена.")


if __name__ == "__main__":
    main()
