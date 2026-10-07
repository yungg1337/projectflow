"""Тесты модуля авторизации через HTTP-интерфейс."""
import unittest

from tests.helpers import ApiTestCase, unique


class AuthApiTests(ApiTestCase):
    """Регистрация, вход, токены и роли."""

    def test_register_new_user(self):
        """Регистрация возвращает 201 и роль исполнителя."""
        email = unique("user") + "@example.com"
        status, data = self.call("POST", "/api/v1/auth/register", {
            "email": email, "password": "password1", "full_name": "Новый Сотрудник"})
        self.assertEqual(status, 201)
        self.assertEqual(data["user"]["role"], "executor")
        self.assertNotIn("password_hash", data["user"])

    def test_register_duplicate_email(self):
        """Повторная регистрация того же адреса даёт 409."""
        email = unique("dup") + "@example.com"
        body = {"email": email, "password": "password1", "full_name": "Первый"}
        self.assertEqual(self.call("POST", "/api/v1/auth/register", body)[0], 201)
        status, data = self.call("POST", "/api/v1/auth/register",
                                 dict(body, full_name="Второй"))
        self.assertEqual(status, 409)
        self.assertIn("уже зарегистрирован", data["detail"])

    def test_register_weak_password(self):
        """Слабый пароль не принимается."""
        status, data = self.call("POST", "/api/v1/auth/register", {
            "email": unique("weak") + "@example.com", "password": "123",
            "full_name": "Слабый Пароль"})
        self.assertEqual(status, 422)
        self.assertIn("Пароль", data["detail"])

    def test_register_bad_email(self):
        """Некорректный адрес электронной почты отклоняется."""
        status, _ = self.call("POST", "/api/v1/auth/register", {
            "email": "не-адрес", "password": "password1", "full_name": "Тест"})
        self.assertEqual(status, 422)

    def test_register_without_fields(self):
        """Пустое тело запроса отклоняется."""
        status, _ = self.call("POST", "/api/v1/auth/register", {})
        self.assertEqual(status, 422)

    def test_login_success(self):
        """Вход возвращает пару токенов."""
        status, data = self.call("POST", "/api/v1/auth/login", {
            "email": "manager@example.com", "password": "manager12345"})
        self.assertEqual(status, 200)
        self.assertIn("access_token", data)
        self.assertIn("refresh_token", data)
        self.assertEqual(data["expires_in"], 1800)

    def test_login_wrong_password(self):
        """Неверный пароль даёт 401."""
        status, _ = self.call("POST", "/api/v1/auth/login", {
            "email": "manager@example.com", "password": "неверный123"})
        self.assertEqual(status, 401)

    def test_refresh_returns_new_access_token(self):
        """По refresh-токену выдаётся новый access-токен."""
        _, login = self.call("POST", "/api/v1/auth/login", {
            "email": "manager@example.com", "password": "manager12345"})
        status, data = self.call("POST", "/api/v1/auth/refresh",
                                 {"refresh_token": login["refresh_token"]})
        self.assertEqual(status, 200)
        self.assertIn("access_token", data)

    def test_refresh_with_access_token_is_rejected(self):
        """Access-токен не годится для обновления."""
        token = self.login("manager@example.com", "manager12345")
        status, _ = self.call("POST", "/api/v1/auth/refresh",
                              {"refresh_token": token})
        self.assertEqual(status, 401)

    def test_me_returns_profile(self):
        """Профиль доступен по токену."""
        token = self.login("executor@example.com", "executor12345")
        status, data = self.call("GET", "/api/v1/users/me", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(data["user"]["role"], "executor")

    def test_request_without_token(self):
        """Без токена защищённый адрес недоступен."""
        status, _ = self.call("GET", "/api/v1/tasks")
        self.assertEqual(status, 401)

    def test_request_with_broken_token(self):
        """Испорченный токен не принимается."""
        status, _ = self.call("GET", "/api/v1/tasks", token="abc.def.ghi")
        self.assertEqual(status, 401)

    def test_password_reset_and_confirm(self):
        """Пароль меняется по одноразовой ссылке из письма."""
        email = unique("reset") + "@example.com"
        self.register(email)
        status, _ = self.call("POST", "/api/v1/auth/password/reset", {"email": email})
        self.assertEqual(status, 202)
        from app import config
        text = config.MAIL_LOG.read_text(encoding="utf-8")
        token = text.split("token=")[-1].split("\n")[0]
        status, _ = self.call("POST", "/api/v1/auth/password/confirm",
                              {"token": token, "new_password": "новыйПароль1"})
        self.assertEqual(status, 200)
        self.assertEqual(self.call("POST", "/api/v1/auth/login",
                                   {"email": email, "password": "новыйПароль1"})[0], 200)

    def test_password_reset_unknown_email(self):
        """Незнакомый адрес не раскрывает сведений о пользователях."""
        status, _ = self.call("POST", "/api/v1/auth/password/reset",
                              {"email": unique("nobody") + "@example.com"})
        self.assertEqual(status, 202)

    def test_confirm_with_bad_token(self):
        """Неверный токен восстановления отклоняется."""
        status, _ = self.call("POST", "/api/v1/auth/password/confirm",
                              {"token": "нет", "new_password": "пароль123"})
        self.assertEqual(status, 401)

    def test_change_role_by_admin(self):
        """Администратор меняет роль пользователя."""
        user = self.register(unique("promote") + "@example.com")
        token = self.login("admin@example.com", "admin12345")
        status, data = self.call("PATCH",
                                 "/api/v1/users/{}/role".format(user["id"]),
                                 {"role": "manager"}, token)
        self.assertEqual(status, 200)
        self.assertEqual(data["user"]["role"], "manager")

    def test_change_role_forbidden_for_manager(self):
        """Менеджер не может менять роли."""
        user = self.register(unique("norole") + "@example.com")
        token = self.login("manager@example.com", "manager12345")
        status, _ = self.call("PATCH", "/api/v1/users/{}/role".format(user["id"]),
                              {"role": "admin"}, token)
        self.assertEqual(status, 403)

    def test_users_list_forbidden_for_executor(self):
        """Исполнитель не видит список пользователей."""
        token = self.login("executor@example.com", "executor12345")
        status, _ = self.call("GET", "/api/v1/users", token=token)
        self.assertEqual(status, 403)

    def test_statuses_endpoint_is_public(self):
        """Описание модели статусов доступно без токена."""
        status, data = self.call("GET", "/api/v1/meta/statuses")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["transitions"]), 8)


if __name__ == "__main__":
    unittest.main()
