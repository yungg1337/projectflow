"""Общая основа тестов: запуск сервера и простой HTTP-клиент."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

TEMP_DIR = Path(tempfile.mkdtemp(prefix="projectflow-tests-"))
os.environ["PROJECTFLOW_VAR"] = str(TEMP_DIR)
os.environ["PROJECTFLOW_DB"] = str(TEMP_DIR / "test.db")
os.environ["PROJECTFLOW_REPORTS"] = str(TEMP_DIR / "reports")
os.environ["PROJECTFLOW_SECRET"] = "test-secret"

from app import config, db, server  # noqa: E402


def unique(prefix):
    """Уникальный суффикс, чтобы тесты не мешали друг другу."""
    return "{}-{}".format(prefix, uuid.uuid4().hex[:8])


class ApiTestCase(unittest.TestCase):
    """Базовый класс: поднимает сервер и даёт методы для запросов."""

    httpd = None
    thread = None
    port = None

    @classmethod
    def setUpClass(cls):
        config.ensure_dirs()
        db.init_db()
        cls.httpd = server.run("127.0.0.1", 0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, method, path, body=None, token=None):
        """Выполняет запрос к API и возвращает код ответа и данные."""
        url = "http://127.0.0.1:{}{}".format(self.port, path)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read()
                kind = response.headers.get("Content-Type", "")
                if not raw:
                    return response.status, None
                if "json" in kind:
                    return response.status, json.loads(raw.decode("utf-8"))
                return response.status, raw
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                return error.code, json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return error.code, raw

    def login(self, email, password):
        """Возвращает access-токен пользователя."""
        status, data = self.call("POST", "/api/v1/auth/login",
                                 {"email": email, "password": password})
        self.assertEqual(status, 200, data)
        return data["access_token"]

    def register(self, role_email, password="password1"):
        """Создаёт пользователя через API и возвращает его данные."""
        email = role_email
        status, data = self.call("POST", "/api/v1/auth/register", {
            "email": email, "password": password,
            "full_name": "Тестовый Пользователь"})
        self.assertEqual(status, 201, data)
        return data["user"]

    def make_project(self, token, code=None):
        """Создаёт проект и возвращает его."""
        status, data = self.call("POST", "/api/v1/projects", {
            "code": code or unique("PRJ"), "name": "Тестовый проект"}, token)
        self.assertEqual(status, 201, data)
        return data["project"]

    def make_task(self, token, project_id, **extra):
        """Создаёт задачу и возвращает её."""
        body = {"project_id": project_id, "title": "Тестовая задача"}
        body.update(extra)
        status, data = self.call("POST", "/api/v1/tasks", body, token)
        self.assertEqual(status, 201, data)
        return data["task"]
