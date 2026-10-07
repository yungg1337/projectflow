"""Веб-сервер приложения: маршрутизация, проверка токена и отдача файлов.

Сервер построен на стандартном модуле http.server, поэтому приложению
не нужны внешние веб-фреймворки.
"""
import json
import sqlite3
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import config, db, states
from .api import auth, projects, reports, tasks
from .errors import ApiError, forbidden, unauthorized
from .log import LOG, new_request_id
from .router import Router
from .security import TokenError, decode_token, read_bearer_token

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".ico": "image/x-icon",
    ".png": "image/png",
}


class Ctx:
    """Всё, что обработчику нужно знать о запросе."""

    def __init__(self, method, path, params, query, body, user, con, request_id):
        self.method = method
        self.path = path
        self.params = params
        self.query = query
        self.body = body
        self.user = user
        self.con = con
        self.request_id = request_id


def build_router():
    """Собирает таблицу маршрутов API."""
    prefix = config.API_PREFIX
    router = Router()

    router.post(prefix + "/auth/register", auth.register, public=True)
    router.post(prefix + "/auth/login", auth.login, public=True)
    router.post(prefix + "/auth/refresh", auth.refresh, public=True)
    router.post(prefix + "/auth/password/reset", auth.password_reset, public=True)
    router.post(prefix + "/auth/password/confirm", auth.password_confirm, public=True)
    router.get(prefix + "/meta/statuses", lambda ctx: (200, states.summary()),
               public=True)

    router.get(prefix + "/users/me", auth.me)
    router.get(prefix + "/users", auth.list_users, roles=("admin", "manager"))
    router.patch(prefix + "/users/{id}/role", auth.change_role, roles=("admin",))

    router.get(prefix + "/projects", projects.list_projects)
    router.post(prefix + "/projects", projects.create_project,
                roles=("manager", "admin"))
    router.get(prefix + "/projects/{id}", projects.get_project)
    router.patch(prefix + "/projects/{id}", projects.update_project,
                 roles=("manager", "admin"))
    router.delete(prefix + "/projects/{id}", projects.delete_project,
                  roles=("manager", "admin"))

    router.get(prefix + "/tasks", tasks.list_tasks)
    router.post(prefix + "/tasks", tasks.create_task, roles=("manager", "admin"))
    router.get(prefix + "/tasks/{id}", tasks.get_task)
    router.patch(prefix + "/tasks/{id}", tasks.update_task,
                 roles=("manager", "admin"))
    router.delete(prefix + "/tasks/{id}", tasks.delete_task,
                  roles=("manager", "admin"))
    router.patch(prefix + "/tasks/{id}/status", tasks.change_status)
    router.get(prefix + "/tasks/{id}/history", tasks.task_history)

    router.post(prefix + "/reports", reports.create_report)
    router.get(prefix + "/reports", reports.list_reports)
    router.get(prefix + "/reports/{id}/download", reports.download_report)
    return router


ROUTER = build_router()


class RequestHandler(BaseHTTPRequestHandler):
    """Обработчик одного HTTP-запроса."""

    server_version = "ProjectFlow/1.0"
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        """Обрабатывает GET."""
        self.handle_request("GET")

    def do_POST(self):
        """Обрабатывает POST."""
        self.handle_request("POST")

    def do_PATCH(self):
        """Обрабатывает PATCH."""
        self.handle_request("PATCH")

    def do_DELETE(self):
        """Обрабатывает DELETE."""
        self.handle_request("DELETE")

    def log_message(self, fmt, *args):
        """Отключает стандартный журнал: пишем свой в формате JSON."""

    def handle_request(self, method):
        """Основной конвейер обработки запроса."""
        started = time.perf_counter()
        request_id = new_request_id()
        status, body, content_type = 500, b"", "application/json"
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        user_id = None
        con = None
        try:
            if not path.startswith(config.API_PREFIX):
                status, body, content_type = self.serve_static(path)
            else:
                con = db.connect()
                query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                payload = self.read_body()
                route, params = ROUTER.find(method, path)
                user = None
                if not route.public:
                    user = self.authenticate(con, query)
                    user_id = user["id"]
                    if route.roles and user["role"] not in route.roles:
                        raise forbidden("Недостаточно прав для этой операции")
                ctx = Ctx(method, path, params, query, payload, user, con, request_id)
                result = route.handler(ctx)
                status, body, content_type = self.pack(result)
        except ApiError as exc:
            status, body = exc.status, self.json_bytes({"detail": exc.detail})
        except sqlite3.IntegrityError as exc:
            status = 409
            body = self.json_bytes({"detail": "Нарушение целостности данных",
                                    "db_error": str(exc)})
        except Exception:  # noqa: BLE001 - последний рубеж защиты
            traceback.print_exc()
            status = 500
            body = self.json_bytes({"detail": "Внутренняя ошибка сервера",
                                    "request_id": request_id})
        finally:
            if con is not None:
                con.close()
            self.send_payload(status, body, content_type)
            LOG.info("request", extra={"extra_fields": {
                "request_id": request_id, "method": method, "path": path,
                "status": status, "user_id": user_id,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1)}})

    def authenticate(self, con, query=None):
        """Проверяет токен JWT и возвращает пользователя.

        Токен берётся из заголовка Authorization, а если его нет — из
        параметра token в адресе (так работает скачивание файлов из браузера).
        """
        header = self.headers.get("Authorization")
        try:
            token = read_bearer_token(header) if header else (query or {}).get("token")
            if not token:
                raise unauthorized()
            payload = decode_token(token)
        except TokenError as exc:
            raise unauthorized(str(exc))
        except ApiError:
            raise
        user = con.execute("SELECT * FROM users WHERE id = ?",
                           (int(payload["sub"]),)).fetchone()
        if user is None:
            raise unauthorized("Пользователь не найден")
        if not user["is_active"]:
            raise forbidden("Учётная запись заблокирована")
        return user

    def read_body(self):
        """Читает и разбирает тело запроса в формате JSON."""
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        if length > config.MAX_BODY:
            raise ApiError(413, "Слишком большой запрос")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(422, "Тело запроса должно быть в формате JSON")
        if not isinstance(data, dict):
            raise ApiError(422, "Ожидается объект JSON")
        return data

    def pack(self, result):
        """Превращает ответ обработчика в байты и тип содержимого."""
        if len(result) == 3:
            status, raw, content_type = result
            return status, raw, content_type
        status, payload = result
        if status == 204:
            return 204, b"", "application/json"
        return status, self.json_bytes(payload), "application/json"

    def json_bytes(self, payload):
        """Кодирует ответ в JSON."""
        return json.dumps(payload, ensure_ascii=False,
                          default=str).encode("utf-8")

    def serve_static(self, path):
        """Отдаёт файлы веб-интерфейса из каталога frontend."""
        root = Path(config.FRONTEND_DIR).resolve()
        relative = path.lstrip("/") or "index.html"
        target = (root / relative).resolve()
        if root not in target.parents and target != root:
            raise forbidden("Недопустимый путь к файлу")
        if not target.exists() or target.is_dir():
            target = root / "index.html"
        if not target.exists():
            raise ApiError(404, "Файл интерфейса не найден")
        content_type = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        return 200, target.read_bytes(), content_type

    def send_payload(self, status, body, content_type):
        """Отправляет ответ клиенту."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)


def run(host=None, port=None):
    """Запускает сервер и ждёт запросы."""
    db.init_db()
    address = (host or config.HOST, port or config.PORT)
    httpd = ThreadingHTTPServer(address, RequestHandler)
    LOG.info("server.started", extra={"extra_fields": {
        "url": "http://{}:{}".format(*address)}})
    return httpd


def serve_forever(host=None, port=None):
    """Запускает сервер до нажатия Ctrl+C."""
    httpd = run(host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        LOG.info("server.stopped")
    finally:
        httpd.server_close()
