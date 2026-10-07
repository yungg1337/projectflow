"""Безопасность: хэширование паролей и токены JWT.

Пароли хранятся только в виде хэша PBKDF2-HMAC-SHA256 с индивидуальной солью,
а вход в систему подтверждается токеном JWT, подписанным алгоритмом HS256.
"""
import base64
import hashlib
import hmac
import json
import os
import time
import uuid

from . import config
from .errors import unauthorized

ITERATIONS = 120_000


class TokenError(Exception):
    """Токен повреждён, подписан чужим ключом или просрочен."""


def _b64encode(data):
    """Кодирует байты в base64url без выравнивающих символов."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(text):
    """Декодирует строку base64url, добавляя пропущенные символы выравнивания."""
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def hash_password(password):
    """Возвращает строку вида pbkdf2_sha256$итерации$соль$хэш."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        ITERATIONS, _b64encode(salt), _b64encode(digest))


def verify_password(password, stored):
    """Проверяет пароль по сохранённому хэшу."""
    try:
        algorithm, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    check = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), _b64decode(salt), int(iterations))
    return hmac.compare_digest(check, _b64decode(digest))


def create_token(user, token_type="access", ttl=None):
    """Создаёт токен JWT для пользователя."""
    if ttl is None:
        ttl = config.ACCESS_TTL if token_type == "access" else config.REFRESH_TTL
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "role": user["role"],
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }
    return _sign(header, payload)


def _sign(header, payload):
    """Подписывает токен алгоритмом HS256 и возвращает готовую строку."""
    head = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    body = _b64encode(json.dumps(payload, separators=(",", ":"),
                                 ensure_ascii=False).encode("utf-8"))
    signing_input = "{}.{}".format(head, body)
    signature = hmac.new(config.SECRET.encode("utf-8"),
                         signing_input.encode("ascii"), hashlib.sha256).digest()
    return "{}.{}".format(signing_input, _b64encode(signature))


def decode_token(token, expected_type="access"):
    """Проверяет подпись и срок действия токена, возвращает его полезные данные."""
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("Некорректный формат токена")
    signing_input = "{}.{}".format(parts[0], parts[1])
    expected = hmac.new(config.SECRET.encode("utf-8"),
                        signing_input.encode("ascii"), hashlib.sha256).digest()
    try:
        actual = _b64decode(parts[2])
    except Exception as exc:  # noqa: BLE001 - защита от мусора в токене
        raise TokenError("Подпись токена повреждена") from exc
    if not hmac.compare_digest(expected, actual):
        raise TokenError("Подпись токена не совпадает")
    try:
        payload = json.loads(_b64decode(parts[1]).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise TokenError("Полезные данные токена повреждены") from exc
    if payload.get("exp", 0) < time.time():
        raise TokenError("Срок действия токена истёк")
    if expected_type and payload.get("type") != expected_type:
        raise TokenError("Токен другого назначения")
    return payload


def read_bearer_token(header_value):
    """Достаёт токен из заголовка Authorization."""
    if not header_value:
        raise unauthorized()
    parts = header_value.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise unauthorized("Ожидается заголовок 'Authorization: Bearer <токен>'")
    return parts[1]
