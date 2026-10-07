"""Простой маршрутизатор запросов.

Маршрут описывается методом, шаблоном пути и ролями, которым он разрешён.
Шаблон может содержать параметры вида {id}.
"""
from .errors import not_found


class Route:
    """Один маршрут API."""

    def __init__(self, method, pattern, handler, roles=None, public=False):
        self.method = method
        self.pattern = pattern
        self.handler = handler
        self.roles = roles or []
        self.public = public
        self.parts = [p for p in pattern.strip("/").split("/") if p]

    def match(self, method, path):
        """Совпадает ли запрос с маршрутом; возвращает параметры пути."""
        if method != self.method:
            return None
        segments = [p for p in path.strip("/").split("/") if p]
        if len(segments) != len(self.parts):
            return None
        params = {}
        for pattern_part, value in zip(self.parts, segments):
            if pattern_part.startswith("{") and pattern_part.endswith("}"):
                params[pattern_part[1:-1]] = value
            elif pattern_part != value:
                return None
        return params


class Router:
    """Список маршрутов приложения."""

    def __init__(self):
        self.routes = []

    def add(self, method, pattern, handler, roles=None, public=False):
        """Добавляет маршрут в таблицу."""
        self.routes.append(Route(method, pattern, handler, roles, public))

    def get(self, pattern, handler, roles=None, public=False):
        """Регистрирует обработчик GET."""
        self.add("GET", pattern, handler, roles, public)

    def post(self, pattern, handler, roles=None, public=False):
        """Регистрирует обработчик POST."""
        self.add("POST", pattern, handler, roles, public)

    def patch(self, pattern, handler, roles=None, public=False):
        """Регистрирует обработчик PATCH."""
        self.add("PATCH", pattern, handler, roles, public)

    def delete(self, pattern, handler, roles=None, public=False):
        """Регистрирует обработчик DELETE."""
        self.add("DELETE", pattern, handler, roles, public)

    def find(self, method, path):
        """Ищет маршрут; если путь есть, а метода нет — возвращает 405."""
        path_matched = False
        for route in self.routes:
            params = route.match(method, path)
            if params is not None:
                return route, params
            if route.match("GET", path) is not None or \
                    route.match("POST", path) is not None:
                path_matched = True
        if path_matched:
            from .errors import ApiError
            raise ApiError(405, "Метод не поддерживается для этого адреса")
        raise not_found("Адрес не найден")
