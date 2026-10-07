"""Тесты модуля отчётов: формирование, экспорт и права доступа."""
import unittest
from pathlib import Path

from tests.helpers import ApiTestCase, config, unique


class ReportApiTests(ApiTestCase):
    """Отчёты по проекту, по исполнителю и за период."""

    def setUp(self):
        """Готовит пользователей, проект и пару задач."""
        self.manager = self.login("manager@example.com", "manager12345")
        self.executor = self.login("executor@example.com", "executor12345")
        self.project = self.make_project(self.manager)
        status, data = self.call("GET", "/api/v1/users", token=self.manager)
        self.executor_id = [u["id"] for u in data["items"]
                            if u["email"] == "executor@example.com"][0]
        self.task = self.make_task(self.manager, self.project["id"],
                                   assignee_id=self.executor_id)

    def make_report(self, **extra):
        """Формирует отчёт с указанными параметрами."""
        body = {"report_type": "by_project", "project_id": self.project["id"],
                "format": "xlsx"}
        body.update(extra)
        return self.call("POST", "/api/v1/reports", body, self.manager)

    def test_project_report_xlsx(self):
        """Отчёт по проекту в Excel формируется."""
        status, data = self.make_report()
        self.assertEqual(status, 201, data)
        self.assertEqual(data["report"]["rows_count"], 1)
        self.assertTrue(data["report"]["file_name"].endswith(".xlsx"))

    def test_project_report_pdf(self):
        """Отчёт по проекту в PDF формируется."""
        status, data = self.make_report(format="pdf")
        if status == 503:
            self.skipTest("нет библиотеки fpdf2 или системного шрифта")
        self.assertEqual(status, 201, data)
        path = Path(config.REPORTS_DIR) / data["report"]["file_name"]
        self.assertTrue(path.exists())
        self.assertEqual(path.read_bytes()[:4], b"%PDF")

    def test_download_report_by_header(self):
        """Файл отчёта скачивается по токену в заголовке."""
        _, data = self.make_report()
        status, raw = self.call("GET", data["download_url"], token=self.manager)
        self.assertEqual(status, 200)
        self.assertGreater(len(raw), 500)

    def test_download_report_by_query_token(self):
        """Файл скачивается по токену в адресе (ссылка из браузера)."""
        _, data = self.make_report()
        status, raw = self.call(
            "GET", data["download_url"] + "?token=" + self.manager)
        self.assertEqual(status, 200)
        self.assertGreater(len(raw), 500)

    def test_report_by_assignee(self):
        """Отчёт по исполнителю содержит его задачи."""
        status, data = self.call("POST", "/api/v1/reports", {
            "report_type": "by_assignee", "assignee_id": self.executor_id,
            "format": "xlsx"}, self.manager)
        self.assertEqual(status, 201, data)
        self.assertGreaterEqual(data["report"]["rows_count"], 1)

    def test_report_by_period_without_data(self):
        """За период без задач отчёт формируется пустым."""
        status, data = self.call("POST", "/api/v1/reports", {
            "report_type": "by_period", "period_from": "2000-01-01",
            "period_to": "2000-12-31", "format": "xlsx"}, self.manager)
        self.assertEqual(status, 201, data)
        self.assertEqual(data["report"]["rows_count"], 0)

    def test_report_by_period_with_data(self):
        """За текущий период задачи попадают в отчёт."""
        status, data = self.call("POST", "/api/v1/reports", {
            "report_type": "by_period", "period_from": "2020-01-01",
            "period_to": "2100-01-01", "format": "xlsx"}, self.manager)
        self.assertEqual(status, 201, data)
        self.assertGreaterEqual(data["report"]["rows_count"], 1)

    def test_report_unknown_type(self):
        """Неизвестный вид отчёта отклоняется."""
        status, _ = self.call("POST", "/api/v1/reports", {
            "report_type": "какой-то", "format": "xlsx"}, self.manager)
        self.assertEqual(status, 422)

    def test_report_unknown_format(self):
        """Неизвестный формат выгрузки отклоняется."""
        status, _ = self.call("POST", "/api/v1/reports", {
            "report_type": "by_project", "project_id": self.project["id"],
            "format": "docx"}, self.manager)
        self.assertEqual(status, 422)

    def test_project_report_without_project(self):
        """Для отчёта по проекту нужно указать проект."""
        status, _ = self.call("POST", "/api/v1/reports",
                              {"report_type": "by_project", "format": "xlsx"},
                              self.manager)
        self.assertEqual(status, 422)

    def test_executor_cannot_build_foreign_report(self):
        """Исполнитель не получает отчёт по чужим задачам."""
        self.make_task(self.manager, self.project["id"])  # задача без исполнителя
        other = self.register(unique("other") + "@example.com")
        other_token = self.login(other["email"], "password1")
        status, data = self.call("POST", "/api/v1/reports", {
            "report_type": "by_project", "project_id": self.project["id"],
            "format": "xlsx"}, other_token)
        self.assertEqual(status, 403, data)

    def test_executor_sees_only_own_reports(self):
        """В списке отчётов исполнитель видит только свои."""
        self.make_report()
        status, me = self.call("GET", "/api/v1/users/me", token=self.executor)
        status, data = self.call("GET", "/api/v1/reports", token=self.executor)
        self.assertEqual(status, 200)
        for item in data["items"]:
            self.assertEqual(item["author_id"], me["user"]["id"])

    def test_download_unknown_report(self):
        """Несуществующий отчёт не скачивается."""
        status, _ = self.call("GET", "/api/v1/reports/999999/download",
                              token=self.manager)
        self.assertEqual(status, 404)

    def test_summary_is_reported(self):
        """В ответе есть данные о числе строк отчёта."""
        _, data = self.make_report(format="xlsx")
        self.assertIn("rows_count", data["report"])


if __name__ == "__main__":
    unittest.main()
