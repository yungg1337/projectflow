"""Модуль авторизации (AuthModule).

Регистрация, вход, обновление токена, восстановление пароля,
профиль пользователя и смена роли.
"""
import time
import uuid

from .. import config, db
from ..errors import conflict, forbidden, not_found, unauthorized
from ..security import (TokenError, create_token, decode_token, hash_password,
                        read_bearer_token, verify_password)
from ..validate import check_email, check_password, require
from ..log import LOG

router_routes = []


def register(ctx):
    """Регистрация нового пользователя с ролью «исполнитель»."""
    body = ctx.body
    require(body, "email", "password", "full_name")
    email = check_email(body["email"])
    check_password(body["password"])
    exists = ctx.con.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if exists:
        raise conflict("Пользователь с таким адресом уже зарегистрирован")
    cursor = ctx.con.execute(
        "INSERT INTO users (email, password_hash, full_name, role, created_at)"
        " VALUES (?, ?, ?, 'executor', ?)",
        (email, hash_password(body["password"]), body["full_name"].strip(), db.now()))
    ctx.con.commit()
    user = ctx.con.execute("SELECT * FROM users WHERE id = ?",
                           (cursor.lastrowid,)).fetchone()
    LOG.info("user.registered", extra={"extra_fields": {"user_id": user["id"]}})
    return 201, {"user": public_user(user)}


def login(ctx):
    """Вход в систему: проверка пароля и выдача пары токенов."""
    body = ctx.body
    require(body, "email", "password")
    email = check_email(body["email"])
    user = ctx.con.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user is None or not verify_password(body["password"], user["password_hash"]):
        LOG.info("user.login_failed", extra={"extra_fields": {"email": email}})
        raise unauthorized("Неверный адрес электронной почты или пароль")
    if not user["is_active"]:
        raise forbidden("Учётная запись заблокирована")
    LOG.info("user.login_succeeded", extra={"extra_fields": {"user_id": user["id"]}})
    return 200, {
        "access_token": create_token(user, "access"),
        "refresh_token": create_token(user, "refresh"),
        "token_type": "Bearer",
        "expires_in": config.ACCESS_TTL,
        "user": public_user(user),
    }


def refresh(ctx):
    """Выдаёт новый access-токен по refresh-токену."""
    require(ctx.body, "refresh_token")
    try:
        payload = decode_token(ctx.body["refresh_token"], expected_type="refresh")
    except TokenError as exc:
        raise unauthorized(str(exc))
    user = ctx.con.execute("SELECT * FROM users WHERE id = ?",
                           (int(payload["sub"]),)).fetchone()
    if user is None or not user["is_active"]:
        raise forbidden("Учётная запись недоступна")
    return 200, {"access_token": create_token(user, "access"),
                 "expires_in": config.ACCESS_TTL}


def password_reset(ctx):
    """Принимает запрос на восстановление пароля и «отправляет» письмо."""
    require(ctx.body, "email")
    email = check_email(ctx.body["email"])
    user = ctx.con.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user is not None:
        token = uuid.uuid4().hex
        ctx.con.execute(
            "INSERT INTO password_resets (token, user_id, expires_at, used)"
            " VALUES (?, ?, ?, 0)",
            (token, user["id"], time.time() + config.RESET_TTL))
        ctx.con.commit()
        write_mail(email, token)
    return 202, {"detail": "Если адрес зарегистрирован, письмо со ссылкой отправлено"}


def password_confirm(ctx):
    """Устанавливает новый пароль по одноразовой ссылке из письма."""
    require(ctx.body, "token", "new_password")
    check_password(ctx.body["new_password"])
    row = ctx.con.execute("SELECT * FROM password_resets WHERE token = ?",
                          (ctx.body["token"],)).fetchone()
    if row is None or row["used"] or row["expires_at"] < time.time():
        raise unauthorized("Ссылка недействительна или устарела")
    ctx.con.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                    (hash_password(ctx.body["new_password"]), row["user_id"]))
    ctx.con.execute("UPDATE password_resets SET used = 1 WHERE token = ?",
                    (ctx.body["token"],))
    ctx.con.commit()
    return 200, {"detail": "Пароль изменён, можно входить"}


def me(ctx):
    """Профиль текущего пользователя."""
    return 200, {"user": public_user(ctx.user), "session": {
        "role": ctx.user["role"], "token_type": "Bearer"}}


def change_role(ctx):
    """Администратор меняет роль пользователя."""
    require(ctx.body, "role")
    user_id = int(ctx.params["id"])
    if user_id == ctx.user["id"]:
        raise forbidden("Нельзя менять роль самому себе")
    user = ctx.con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        raise not_found("Пользователь не найден")
    ctx.con.execute("UPDATE users SET role = ? WHERE id = ?",
                    (ctx.body["role"], user_id))
    ctx.con.commit()
    return 200, {"user": public_user(ctx.con.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())}


def list_users(ctx):
    """Список пользователей (для администратора и менеджера)."""
    rows = ctx.con.execute(
        "SELECT * FROM users ORDER BY id").fetchall()
    return 200, {"items": [public_user(r) for r in rows], "total": len(rows)}


def public_user(user):
    """Представление пользователя для передачи клиенту (без хэша пароля)."""
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "is_active": bool(user["is_active"]),
        "created_at": user["created_at"],
    }


def write_mail(email, token):
    """Записывает «отправленное» письмо в файл вместо реальной почты."""
    config.ensure_dirs()
    with open(config.MAIL_LOG, "a", encoding="utf-8") as handle:
        handle.write("Кому: {}\nТема: Восстановление пароля ProjectFlow\n"
                     "Ссылка: /reset?token={}\n\n".format(email, token))
