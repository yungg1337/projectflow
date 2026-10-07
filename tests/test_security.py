"""Проверка хэширования паролей и токенов JWT."""
import time
import unittest

from app import security


class PasswordTests(unittest.TestCase):
    """Пароли должны храниться только в виде хэша."""

    def test_hash_is_not_plain_text(self):
        """В хэше нет исходного пароля."""
        digest = security.hash_password("secret123")
        self.assertNotIn("secret123", digest)
        self.assertTrue(digest.startswith("pbkdf2_sha256$"))

    def test_correct_password_matches(self):
        """Верный пароль проходит проверку."""
        digest = security.hash_password("secret123")
        self.assertTrue(security.verify_password("secret123", digest))

    def test_wrong_password_rejected(self):
        """Неверный пароль не проходит проверку."""
        digest = security.hash_password("secret123")
        self.assertFalse(security.verify_password("secret124", digest))

    def test_same_password_gives_different_hashes(self):
        """Соль делает хэши одинаковых паролей разными."""
        first = security.hash_password("secret123")
        second = security.hash_password("secret123")
        self.assertNotEqual(first, second)

    def test_broken_hash_is_rejected(self):
        """Испорченная строка хэша не приводит к падению."""
        self.assertFalse(security.verify_password("secret123", "мусор"))


class TokenTests(unittest.TestCase):
    """Токены JWT должны иметь подпись и срок действия."""

    USER = {"id": 1, "email": "user@example.com", "role": "manager"}

    def test_token_contains_claims(self):
        """В токене есть идентификатор, роль и срок действия."""
        payload = security.decode_token(security.create_token(self.USER))
        self.assertEqual(payload["sub"], "1")
        self.assertEqual(payload["role"], "manager")
        self.assertIn("exp", payload)
        self.assertIn("jti", payload)

    def test_token_has_three_parts(self):
        """Токен состоит из заголовка, данных и подписи."""
        self.assertEqual(len(security.create_token(self.USER).split(".")), 3)

    def test_changed_payload_is_rejected(self):
        """Подмена данных ломает подпись."""
        token = security.create_token(self.USER)
        head, _, signature = token.split(".")
        broken = "{}.{}.{}".format(head, "eyJzdWIiOiI5OTkifQ", signature)
        with self.assertRaises(security.TokenError):
            security.decode_token(broken)

    def test_expired_token_is_rejected(self):
        """Просроченный токен не принимается."""
        token = security.create_token(self.USER, "access", ttl=-10)
        with self.assertRaises(security.TokenError):
            security.decode_token(token)

    def test_refresh_token_is_not_access_token(self):
        """Refresh-токен нельзя использовать как access-токен."""
        token = security.create_token(self.USER, "refresh")
        with self.assertRaises(security.TokenError):
            security.decode_token(token, expected_type="access")

    def test_garbage_token_is_rejected(self):
        """Строка без структуры JWT не принимается."""
        with self.assertRaises(security.TokenError):
            security.decode_token("не-токен")

    def test_read_bearer_token(self):
        """Токен читается из заголовка Authorization."""
        self.assertEqual(security.read_bearer_token("Bearer abc"), "abc")


if __name__ == "__main__":
    unittest.main()
