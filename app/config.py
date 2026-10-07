"""Настройки приложения.

Все параметры читаются из переменных окружения, но у каждой есть значение
по умолчанию, поэтому приложение запускается сразу после распаковки.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VAR_DIR = Path(os.environ.get("PROJECTFLOW_VAR", BASE_DIR / "var"))
DB_PATH = Path(os.environ.get("PROJECTFLOW_DB", VAR_DIR / "projectflow.db"))
REPORTS_DIR = Path(os.environ.get("PROJECTFLOW_REPORTS", VAR_DIR / "reports"))
MAIL_LOG = VAR_DIR / "mail.log"
FRONTEND_DIR = BASE_DIR / "frontend"

SECRET = os.environ.get("PROJECTFLOW_SECRET", "projectflow-dev-secret")
ACCESS_TTL = int(os.environ.get("PROJECTFLOW_ACCESS_TTL", 30 * 60))
REFRESH_TTL = int(os.environ.get("PROJECTFLOW_REFRESH_TTL", 14 * 24 * 60 * 60))
RESET_TTL = int(os.environ.get("PROJECTFLOW_RESET_TTL", 60 * 60))

HOST = os.environ.get("PROJECTFLOW_HOST", "127.0.0.1")
PORT = int(os.environ.get("PROJECTFLOW_PORT", 8000))
MAX_BODY = 1_000_000
API_PREFIX = "/api/v1"


def ensure_dirs():
    """Создаёт каталоги для базы данных, отчётов и журналов."""
    VAR_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
