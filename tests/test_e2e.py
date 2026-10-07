"""Сквозные сценарии: от создания задачи до готового отчёта."""
import unittest
from pathlib import Path

from tests.helpers import ApiTestCase, config


class EndToEndTests(ApiTestCase):
    """Проверяют работу всех трёх модулей вместе."""

    def test_task_appears_in_project_report(self):
        """Созданная задача попадает в отчёт по проекту."""
        manager = self.login("manager@example.com", "manager12345")
        status, users = self.call("GET", "/api/v1/users", token=manager)
        executor_id = [u["id"] for u in users["items"]
                       if u["email"] == "executor@example.com"][0]
        project = self.make_project(manager)
        status, created = self.call("POST", "/api/v1/reports", {
            "report_type": "by_project", "project_id": project["id"],
            "format": "xlsx"}, manager)
        before = created["report"]["rows_count"]

        self.make_task(manager, project["id"], assignee_id=executor_id)

        status, after = self.call("POST", "/api/v1/reports", {
            "report_type": "by_project", "project_id": project["id"],
            "format": "xlsx"}, manager)
        self.assertEqual(after["report"]["rows_count"], before + 1)

    def test_full_lifecycle_from_new_to_done(self):
        """Задача проходит путь от «новая» до «завершена» и попадает в отчёт."""
        manager = self.login("manager@example.com", "manager12345")
        executor = self.login("executor@example.com", "executor12345")
        status, users = self.call("GET", "/api/v1/users", token=manager)
        executor_id = [u["id"] for u in users["items"]
                       if u["email"] == "executor@example.com"][0]
        project = self.make_project(manager)
        task = self.make_task(manager, project["id"], assignee_id=executor_id)

        self.call("PATCH", "/api/v1/tasks/{}/status".format(task["id"]),
                  {"status": "in_progress"}, manager)
        status, _ = self.call("PATCH", "/api/v1/tasks/{}/status".format(task["id"]),
                              {"status": "on_review"}, executor)
        self.assertEqual(status, 200)
        status, done = self.call("PATCH",
                                 "/api/v1/tasks/{}/status".format(task["id"]),
                                 {"status": "done"}, manager)
        self.assertEqual(done["task"]["status"], "done")

        status, history = self.call("GET",
                                    "/api/v1/tasks/{}/history".format(task["id"]),
                                    token=manager)
        self.assertEqual(len(history["items"]), 3)

        status, report = self.call("POST", "/api/v1/reports", {
            "report_type": "by_period", "format": "xlsx"}, manager)
        self.assertEqual(status, 201)

    def test_report_file_is_downloadable_and_valid_xlsx(self):
        """Сформированный файл Excel читается как ZIP-архив."""
        import zipfile
        manager = self.login("manager@example.com", "manager12345")
        project = self.make_project(manager)
        self.make_task(manager, project["id"])
        _, data = self.call("POST", "/api/v1/reports", {
            "report_type": "by_project", "project_id": project["id"],
            "format": "xlsx"}, manager)
        path = Path(config.REPORTS_DIR) / data["report"]["file_name"]
        self.assertTrue(zipfile.is_zipfile(path))
        with zipfile.ZipFile(path) as archive:
            self.assertIn("xl/worksheets/sheet1.xml", archive.namelist())
            sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("Задача", sheet)


if __name__ == "__main__":
    unittest.main()
