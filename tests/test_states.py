"""Проверка конечного автомата статусов задачи."""
import unittest

from app import states


class TransitionTests(unittest.TestCase):
    """Разрешёнными считаются только переходы из модели."""

    def test_all_model_transitions_are_allowed(self):
        """Каждый переход модели выполняется без ошибок."""
        for (start, target), roles in states.TRANSITION_RULES.items():
            states.check_transition(start, target, roles[0], True)

    def test_forbidden_transitions_are_rejected(self):
        """Запрещённые переходы отклоняются."""
        forbidden = [("done", "new"), ("done", "in_progress"), ("new", "done"),
                     ("new", "on_review"), ("on_review", "new"),
                     ("rejected", "done")]
        for start, target in forbidden:
            with self.assertRaises(Exception):
                states.check_transition(start, target, "admin", True)

    def test_unknown_status_is_rejected(self):
        """Несуществующий статус не принимается."""
        with self.assertRaises(Exception):
            states.check_transition("new", "готово", "admin", True)

    def test_executor_cannot_accept_work(self):
        """Исполнитель не может принять свою работу."""
        with self.assertRaises(Exception):
            states.check_transition("on_review", "done", "executor", True)

    def test_executor_cannot_work_on_foreign_task(self):
        """Исполнитель не может менять чужую задачу."""
        with self.assertRaises(Exception):
            states.check_transition("in_progress", "on_review", "executor", False)

    def test_manager_can_accept_work(self):
        """Менеджер принимает работу."""
        text = states.check_transition("on_review", "done", "manager", False)
        self.assertIn("принять", text)

    def test_done_has_no_transitions(self):
        """Из завершённого состояния переходов нет."""
        self.assertEqual(states.TRANSITIONS[states.DONE], set())

    def test_available_transitions_for_executor(self):
        """Исполнитель видит только доступные ему действия."""
        actions = states.available_transitions("in_progress", "executor", True)
        self.assertEqual([a["status"] for a in actions], ["on_review"])

    def test_available_transitions_for_admin(self):
        """Администратор видит все переходы из состояния."""
        actions = states.available_transitions("on_review", "admin", False)
        self.assertEqual(len(actions), 3)

    def test_summary_describes_model(self):
        """Описание модели содержит пять статусов и восемь переходов."""
        data = states.summary()
        self.assertEqual(len(data["statuses"]), 5)
        self.assertEqual(len(data["transitions"]), 8)


if __name__ == "__main__":
    unittest.main()
