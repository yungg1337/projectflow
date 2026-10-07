"""Конечный автомат статусов задачи.

Модель: M = (S, T, R), где S — статусы, T — допустимые переходы,
R — роли, которым разрешён переход.
"""
from .errors import bad_request, forbidden

NEW = "new"
IN_PROGRESS = "in_progress"
ON_REVIEW = "on_review"
DONE = "done"
REJECTED = "rejected"

STATUSES = (NEW, IN_PROGRESS, ON_REVIEW, DONE, REJECTED)

STATUS_TITLES = {
    NEW: "новая",
    IN_PROGRESS: "в работе",
    ON_REVIEW: "на проверке",
    DONE: "завершена",
    REJECTED: "отклонена",
}

TRANSITIONS = {
    NEW: {IN_PROGRESS, REJECTED},
    IN_PROGRESS: {NEW, ON_REVIEW},
    ON_REVIEW: {IN_PROGRESS, DONE, REJECTED},
    REJECTED: {IN_PROGRESS},
    DONE: set(),
}

TRANSITION_RULES = {
    (NEW, IN_PROGRESS): ("manager", "admin", "executor"),
    (NEW, REJECTED): ("manager", "admin"),
    (IN_PROGRESS, NEW): ("manager", "admin"),
    (IN_PROGRESS, ON_REVIEW): ("manager", "admin", "executor"),
    (ON_REVIEW, IN_PROGRESS): ("manager", "admin"),
    (ON_REVIEW, DONE): ("manager", "admin"),
    (ON_REVIEW, REJECTED): ("manager", "admin"),
    (REJECTED, IN_PROGRESS): ("manager", "admin"),
}

TRANSITION_CAPTIONS = {
    (NEW, IN_PROGRESS): "начать работу",
    (NEW, REJECTED): "отменить задачу",
    (IN_PROGRESS, NEW): "вернуть в бэклог",
    (IN_PROGRESS, ON_REVIEW): "отправить на проверку",
    (ON_REVIEW, IN_PROGRESS): "вернуть на доработку",
    (ON_REVIEW, DONE): "принять работу",
    (ON_REVIEW, REJECTED): "отклонить работу",
    (REJECTED, IN_PROGRESS): "переоткрыть задачу",
}


def check_transition(status_from, status_to, role, is_assignee):
    """Проверяет переход и права пользователя.

    Возвращает текст-обоснование перехода, если он разрешён.
    """
    if status_to not in STATUSES:
        raise bad_request("Неизвестный статус: {}".format(status_to))
    if status_to not in TRANSITIONS.get(status_from, set()):
        raise forbidden("Недопустимый переход: {} -> {}".format(
            STATUS_TITLES[status_from], STATUS_TITLES[status_to]))
    allowed_roles = TRANSITION_RULES[(status_from, status_to)]
    if role not in allowed_roles:
        raise forbidden("Роль «{}» не может выполнить действие «{}»".format(
            role, TRANSITION_CAPTIONS[(status_from, status_to)]))
    if role == "executor" and not is_assignee:
        raise forbidden("Исполнитель может менять только свои задачи")
    return TRANSITION_CAPTIONS[(status_from, status_to)]


def available_transitions(status, role, is_assignee):
    """Список переходов, доступных пользователю из текущего статуса."""
    result = []
    for target in sorted(TRANSITIONS.get(status, set())):
        allowed_roles = TRANSITION_RULES[(status, target)]
        if role in allowed_roles and (role != "executor" or is_assignee):
            result.append({"status": target, "title": STATUS_TITLES[target],
                           "caption": TRANSITION_CAPTIONS[(status, target)]})
    return result


def summary():
    """Описание модели для документации и интерфейса."""
    return {
        "statuses": [{"code": s, "title": STATUS_TITLES[s]} for s in STATUSES],
        "transitions": [
            {"from": a, "to": b, "caption": TRANSITION_CAPTIONS[(a, b)],
             "roles": list(TRANSITION_RULES[(a, b)])}
            for a, b in TRANSITION_CAPTIONS
        ],
    }
