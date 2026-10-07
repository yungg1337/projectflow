"""Проверка входных данных, приходящих от клиента."""
import re

from .errors import invalid_data

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Zа-яА-Я]{2,}$")


def require(body, *fields):
    """Проверяет, что в теле запроса есть обязательные поля."""
    missing = [f for f in fields if not str(body.get(f, "")).strip()]
    if missing:
        raise invalid_data("Не заполнены поля: " + ", ".join(missing))


def check_email(value):
    """Проверяет формат адреса электронной почты."""
    if not EMAIL_RE.match(value or ""):
        raise invalid_data("Некорректный адрес электронной почты")
    return value.strip().lower()


def check_password(value):
    """Проверяет сложность пароля: не менее 8 символов, буквы и цифры."""
    problems = []
    if len(value or "") < 8:
        problems.append("не менее 8 символов")
    if not re.search(r"[A-Za-zА-Яа-я]", value or ""):
        problems.append("хотя бы одна буква")
    if not re.search(r"\d", value or ""):
        problems.append("хотя бы одна цифра")
    if problems:
        raise invalid_data("Пароль слишком простой: нужно " + ", ".join(problems))
    return value


def check_choice(value, allowed, field):
    """Проверяет, что значение входит в список допустимых."""
    if value not in allowed:
        raise invalid_data("Поле {}: допустимые значения {}".format(
            field, ", ".join(sorted(allowed))))
    return value


def check_date(value, field):
    """Проверяет формат даты ГГГГ-ММ-ДД."""
    if value in (None, ""):
        return None
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(value)):
        raise invalid_data("Поле {}: ожидается дата в формате ГГГГ-ММ-ДД".format(field))
    return str(value)


def as_int(value, field):
    """Преобразует значение к целому числу."""
    try:
        return int(value)
    except (TypeError, ValueError):
        raise invalid_data("Поле {}: ожидается целое число".format(field))
