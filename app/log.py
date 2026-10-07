"""Журнал работы приложения в формате JSON."""
import json
import logging
import sys
import time
import uuid


class JsonFormatter(logging.Formatter):
    """Форматирует записи журнала как одну строку JSON."""

    def format(self, record):
        """Собирает запись журнала в строку JSON."""
        data = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            data.update(extra)
        return json.dumps(data, ensure_ascii=False)


def get_logger():
    """Возвращает настроенный журнал приложения."""
    logger = logging.getLogger("projectflow")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def new_request_id():
    """Короткий идентификатор запроса для журнала."""
    return uuid.uuid4().hex[:12]


LOG = get_logger()
