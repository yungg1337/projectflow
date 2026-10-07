"""Тесты модуля задач: операции и переходы статусов."""
import unittest

from tests.helpers import ApiTestCase, unique


class TaskApiTests(ApiTestCase):
    """Создание, изменение, удаление задач и работа конечного автомата."""

    def setUp(self):
        """Готовит токены и проект для каждого теста."""
        self.admin = self.login("admin@example.com", "admin12345")
        self.manager = self.login("manager@example.com", "manager12345")
        self.executor = self.login("executor@example.com", "executor12345")
        self.project = self.make_project(self.manager)

    def executor_id(self):
        """Идентификатор демонстрационного исполнителя."""
        status, data = self.call("GET", "/api/v1/users", token=self.manager)
        self.assertEqual(status, 200)
        for user in data["items"]:
            if user["email"] == "executor@example.com":
                return user["id"]
        raise AssertionError("исполнитель не найден")

    def test_create_task(self):
        """Менеджер создаёт задачу со статусом «новая»."""
        task = self.make_task(self.manager, self.project["id"])
        self.assertEqual(task["status"], "new")
        self.assertEqual(task["status_title"], "новая")

    def test_create_task_by_executor_forbidden(self):
        """Исполнитель не может создавать задачи."""
        status, _ = self.call("POST", "/api/v1/tasks", {
            "project_id": self.project["id"], "title": "Нельзя"}, self.executor)
        self.assertEqual(status, 403)

    def test_create_task_in_unknown_project(self):
        """Задача в несуществующем проекте отклоняется."""
        status, _ = self.call("POST", "/api/v1/tasks", {
            "project_id": 999999, "title": "Нет проекта"}, self.manager)
        self.assertEqual(status, 404)

    def test_create_task_with_past_due_date(self):
        """Срок раньше текущей даты не принимается."""
        status, _ = self.call("POST", "/api/v1/tasks", {
            "project_id": self.project["id"], "title": "Просроченная",
            "due_date": "2000-01-01"}, self.manager)
        self.assertEqual(status, 400)

    def test_update_task(self):
        """Задача изменяется, фиксируется время правки."""
        task = self.make_task(self.manager, self.project["id"])
        status, data = self.call("PATCH", "/api/v1/tasks/{}".format(task["id"]),
                                 {"title": "Новое название"}, self.manager)
        self.assertEqual(status, 200)
        self.assertEqual(data["task"]["title"], "Новое название")

    def test_filter_tasks_by_status(self):
        """Фильтр по статусу возвращает только нужные задачи."""
        self.make_task(self.manager, self.project["id"])
        status, data = self.call("GET",
                                 "/api/v1/tasks?status=new&size=50", token=self.manager)
        self.assertEqual(status, 200)
        self.assertTrue(all(t["status"] == "new" for t in data["items"]))

    def test_filter_tasks_by_project(self):
        """Фильтр по проекту работает."""
        self.make_task(self.manager, self.project["id"])
        status, data = self.call(
            "GET", "/api/v1/tasks?project_id={}".format(self.project["id"]),
            token=self.manager)
        self.assertEqual(status, 200)
        self.assertTrue(all(t["project_id"] == self.project["id"]
                            for t in data["items"]))

    def test_allowed_transition_new_to_in_progress(self):
        """Переход «новая → в работе» выполняется и попадает в историю."""
        task = self.make_task(self.manager, self.project["id"],
                              assignee_id=self.executor_id())
        status, data = self.call("PATCH",
                                 "/api/v1/tasks/{}/status".format(task["id"]),
                                 {"status": "in_progress"}, self.manager)
        self.assertEqual(status, 200)
        self.assertEqual(data["task"]["status"], "in_progress")
        status, history = self.call("GET",
                                    "/api/v1/tasks/{}/history".format(task["id"]),
                                    token=self.manager)
        self.assertEqual(history["items"][0]["status_to"], "in_progress")

    def test_all_eight_transitions(self):
        """Все восемь переходов модели выполняются."""
        task = self.make_task(self.manager, self.project["id"],
                              assignee_id=self.executor_id())
        path = [
            ("in_progress", "начать работу"),
            ("on_review", "отправить на проверку"),
            ("in_progress", "вернуть на доработку"),
            ("new", "вернуть в бэклог"),
            ("rejected", "отменить задачу"),
            ("in_progress", "переоткрыть задачу"),
            ("on_review", "отправить на проверку"),
            ("done", "принять работу"),
        ]
        for target, caption in path:
            body = {"status": target}
            if target == "rejected":
                body["comment"] = "работа отклонена"
            status, data = self.call(
                "PATCH", "/api/v1/tasks/{}/status".format(task["id"]), body,
                self.manager)
            self.assertEqual(status, 200, "{}: {}".format(caption, data))
            self.assertEqual(data["task"]["status"], target)

    def test_forbidden_transition_from_done(self):
        """Из статуса «завершена» переходов нет."""
        task = self.make_task(self.manager, self.project["id"],
                              assignee_id=self.executor_id())
        for target in ("in_progress", "on_review", "done"):
            self.call("PATCH", "/api/v1/tasks/{}/status".format(task["id"]),
                      {"status": target}, self.manager)
        for target in ("new", "in_progress", "on_review"):
            status, data = self.call(
                "PATCH", "/api/v1/tasks/{}/status".format(task["id"]),
                {"status": target}, self.manager)
            self.assertEqual(status, 403, data)

    def test_transition_without_assignee(self):
        """Нельзя начать работу по задаче без исполнителя."""
        task = self.make_task(self.manager, self.project["id"])
        status, _ = self.call("PATCH", "/api/v1/tasks/{}/status".format(task["id"]),
                              {"status": "in_progress"}, self.manager)
        self.assertEqual(status, 400)

    def test_reject_requires_comment(self):
        """Отклонение задачи без комментария запрещено."""
        task = self.make_task(self.manager, self.project["id"])
        status, _ = self.call("PATCH", "/api/v1/tasks/{}/status".format(task["id"]),
                              {"status": "rejected"}, self.manager)
        self.assertEqual(status, 400)

    def test_executor_can_send_own_task_to_review(self):
        """Исполнитель отправляет свою задачу на проверку."""
        executor_id = self.executor_id()
        task = self.make_task(self.manager, self.project["id"],
                              assignee_id=executor_id)
        self.call("PATCH", "/api/v1/tasks/{}/status".format(task["id"]),
                  {"status": "in_progress"}, self.manager)
        status, data = self.call("PATCH",
                                 "/api/v1/tasks/{}/status".format(task["id"]),
                                 {"status": "on_review"}, self.executor)
        self.assertEqual(status, 200, data)
        self.assertEqual(data["task"]["status"], "on_review")

    def test_executor_cannot_accept_work(self):
        """Исполнитель не принимает работу."""
        executor_id = self.executor_id()
        task = self.make_task(self.manager, self.project["id"],
                              assignee_id=executor_id)
        self.call("PATCH", "/api/v1/tasks/{}/status".format(task["id"]),
                  {"status": "in_progress"}, self.manager)
        self.call("PATCH", "/api/v1/tasks/{}/status".format(task["id"]),
                  {"status": "on_review"}, self.manager)
        status, _ = self.call("PATCH", "/api/v1/tasks/{}/status".format(task["id"]),
                              {"status": "done"}, self.executor)
        self.assertEqual(status, 403)

    def test_same_status_is_rejected(self):
        """Перевод в текущий статус отклоняется."""
        task = self.make_task(self.manager, self.project["id"])
        status, _ = self.call("PATCH", "/api/v1/tasks/{}/status".format(task["id"]),
                              {"status": "new"}, self.manager)
        self.assertEqual(status, 400)

    def test_delete_task(self):
        """Задачу можно удалить."""
        task = self.make_task(self.manager, self.project["id"])
        status, _ = self.call("DELETE", "/api/v1/tasks/{}".format(task["id"]),
                              token=self.manager)
        self.assertEqual(status, 204)
        self.assertEqual(self.call("GET", "/api/v1/tasks/{}".format(task["id"]),
                                   token=self.manager)[0], 404)

    def test_delete_finished_task_forbidden(self):
        """Завершённую задачу удалять нельзя."""
        executor_id = self.executor_id()
        task = self.make_task(self.manager, self.project["id"],
                              assignee_id=executor_id)
        for target in ("in_progress", "on_review", "done"):
            self.call("PATCH", "/api/v1/tasks/{}/status".format(task["id"]),
                      {"status": target}, self.manager)
        status, _ = self.call("DELETE", "/api/v1/tasks/{}".format(task["id"]),
                              token=self.manager)
        self.assertEqual(status, 409)

    def test_unknown_task_returns_404(self):
        """Несуществующая задача не найдена."""
        self.assertEqual(self.call("GET", "/api/v1/tasks/999999",
                                   token=self.manager)[0], 404)

    def test_delete_project_with_tasks_forbidden(self):
        """Проект с задачами удалить нельзя."""
        self.make_task(self.manager, self.project["id"])
        status, data = self.call("DELETE",
                                 "/api/v1/projects/{}".format(self.project["id"]),
                                 token=self.admin)
        self.assertEqual(status, 409)
        self.assertIn("задач", data["detail"])

    def test_task_view_has_available_actions(self):
        """В карточке задачи перечислены доступные действия."""
        task = self.make_task(self.manager, self.project["id"],
                              assignee_id=self.executor_id())
        status, data = self.call("GET", "/api/v1/tasks/{}".format(task["id"]),
                                 token=self.manager)
        self.assertEqual(status, 200)
        codes = [a["status"] for a in data["task"]["actions"]]
        self.assertIn("in_progress", codes)


if __name__ == "__main__":
    unittest.main()
