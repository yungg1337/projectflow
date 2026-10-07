"""Информационная система управления проектами «ProjectFlow».

Учебный проект: три модуля (авторизация, задачи, отчёты) в одном приложении
на стандартной библиотеке Python и базе данных SQLite.

Если рядом с проектом есть папка vendor (локально установленные библиотеки),
она добавляется в пути поиска модулей.
"""
import sys
from pathlib import Path

_VENDOR = Path(__file__).resolve().parent.parent / "vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

__version__ = "1.0.0"
