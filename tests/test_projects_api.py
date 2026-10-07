"""Тесты работы с проектами."""
import unittest

from tests.helpers import ApiTestCase, unique


class ProjectApiTests(ApiTestCase):
    """Создание, чтение и изменение проектов."""

    def setUp(self):
        """Токены пользователей для тестов."""
        self.manager = self.login("manager@example.com", "manager12345")
        self.executor = self.login("executor@example.com", "executor12345")

    def test_create_project(self):
        """Менеджер создаёт проект."""
        project = self.make_project(self.manager)
        self.assertEqual(project["status"], "active")

    def test_create_project_by_executor_forbidden(self):
        """Исполнитель не создаёт проекты."""
        status, _ = self.call("POST", "/api/v1/projects",
                              {"code": unique("NO"), "name": "Нельзя"},
                              self.executor)
        self.assertEqual(status, 403)

    def test_duplicate_project_code(self):
        """Код проекта уникален."""
        code = unique("DUP")
        self.make_project(self.manager, code)
        status, data = self.call("POST", "/api/v1/projects",
                                 {"code": code, "name": "Повтор"}, self.manager)
        self.assertEqual(status, 409)
        self.assertIn("код", data["detail"])

    def test_list_projects(self):
        """Список проектов возвращается с общим количеством."""
        self.make_project(self.manager)
        status, data = self.call("GET", "/api/v1/projects", token=self.manager)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["total"], 1)

    def test_project_card_has_statistics(self):
        """В карточке проекта есть сводка по статусам задач."""
        project = self.make_project(self.manager)
        self.make_task(self.manager, project["id"])
        status, data = self.call("GET",
                                 "/api/v1/projects/{}".format(project["id"]),
                                 token=self.manager)
        self.assertEqual(status, 200)
        self.assertEqual(data["project"]["tasks_by_status"].get("new"), 1)

    def test_update_project_status(self):
        """Статус проекта меняется."""
        project = self.make_project(self.manager)
        status, data = self.call("PATCH",
                                 "/api/v1/projects/{}".format(project["id"]),
                                 {"status": "done"}, self.manager)
        self.assertEqual(status, 200)
        self.assertEqual(data["project"]["status"], "done")

    def test_delete_empty_project(self):
        """Пустой проект удаляется."""
        project = self.make_project(self.manager)
        status, _ = self.call("DELETE", "/api/v1/projects/{}".format(project["id"]),
                              token=self.manager)
        self.assertEqual(status, 204)

    def test_unknown_project(self):
        """Несуществующий проект не найден."""
        self.assertEqual(self.call("GET", "/api/v1/projects/999999",
                                   token=self.manager)[0], 404)


if __name__ == "__main__":
    unittest.main()
