"""Ошибки приложения и их коды HTTP."""


class ApiError(Exception):
    """Ошибка, которую нужно вернуть клиенту в виде JSON."""

    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def bad_request(detail="Некорректный запрос"):
    """Ошибка 400 — нарушено правило работы с данными."""
    return ApiError(400, detail)


def unauthorized(detail="Требуется авторизация"):
    """Ошибка 401 — нет токена или он просрочен."""
    return ApiError(401, detail)


def forbidden(detail="Недостаточно прав"):
    """Ошибка 403 — роли пользователя не хватает для операции."""
    return ApiError(403, detail)


def not_found(detail="Объект не найден"):
    """Ошибка 404 — запись отсутствует в базе данных."""
    return ApiError(404, detail)


def conflict(detail="Нарушена уникальность данных"):
    """Ошибка 409 — такая запись уже есть."""
    return ApiError(409, detail)


def invalid_data(detail="Ошибка валидации данных"):
    """Ошибка 422 — данные не прошли проверку."""
    return ApiError(422, detail)


def unavailable(detail="Сервис недоступен"):
    """Ошибка 503 — не хватает компонента (например, шрифта для PDF)."""
    return ApiError(503, detail)
