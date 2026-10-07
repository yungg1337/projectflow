#!/usr/bin/env python3
"""Проверка качества кода проекта (свой «мини-линтер»).

Проверяет то же, что требуют flake8 и pylint, но без установки библиотек:
длину строк, наличие docstring, стиль имён, «голые» except и отладочные print.

Запуск:  python tools/check.py
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_LINE = 100
CURRENT_DIRS = ("app", "tests", "tools")
SKIP_DIRS = {"vendor", "__pycache__", ".git", "var"}
SNAKE = re.compile(r"^[a-z_][a-z0-9_]*$")
CAMEL = re.compile(r"^[A-Z][A-Za-z0-9]*$")
# имена, которые заданы стандартной библиотекой и менять их нельзя
ALLOWED_NAMES = {"do_GET", "do_POST", "do_PATCH", "do_DELETE", "do_HEAD",
                 "log_message", "setUp", "tearDown", "setUpClass",
                 "tearDownClass", "setUpModule", "tearDownModule"}


class Finding:
    """Одно замечание проверки."""

    def __init__(self, path, line, code, text):
        self.path = path
        self.line = line
        self.code = code
        self.text = text

    def __str__(self):
        return "{}:{}: {} {}".format(self.path, self.line, self.code, self.text)


def python_files():
    """Все файлы проекта, которые нужно проверить."""
    for name in CURRENT_DIRS:
        for path in sorted((ROOT / name).rglob("*.py")):
            if not any(part in SKIP_DIRS for part in path.parts):
                yield path


def check_lines(path, lines, findings):
    """Проверяет длину строк и наличие табуляции."""
    for number, text in enumerate(lines, start=1):
        if len(text.rstrip("\n")) > MAX_LINE:
            findings.append(Finding(path, number, "E501",
                                    "строка длиннее {} символов".format(MAX_LINE)))
        if "\t" in text:
            findings.append(Finding(path, number, "W191", "в строке есть табуляция"))


def check_tree(path, tree, findings):
    """Проверяет имена, docstring и обработку исключений."""
    if ast.get_docstring(tree) is None:
        findings.append(Finding(path, 1, "C0111", "у модуля нет docstring"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in ALLOWED_NAMES or node.name.startswith("__"):
                continue
            if not SNAKE.match(node.name):
                findings.append(Finding(path, node.lineno, "C0103",
                                        "имя функции «{}» не в snake_case".format(node.name)))
            if ast.get_docstring(node) is None and not node.name.startswith("__"):
                findings.append(Finding(path, node.lineno, "C0116",
                                        "у функции «{}» нет docstring".format(node.name)))
            if len(node.body) > 40:
                findings.append(Finding(path, node.lineno, "R0915",
                                        "функция «{}» длиннее 40 операторов".format(node.name)))
        elif isinstance(node, ast.ClassDef):
            if not CAMEL.match(node.name):
                findings.append(Finding(path, node.lineno, "C0103",
                                        "имя класса «{}» не в CamelCase".format(node.name)))
            if ast.get_docstring(node) is None:
                findings.append(Finding(path, node.lineno, "C0111",
                                        "у класса «{}» нет docstring".format(node.name)))
        elif isinstance(node, ast.ExceptHandler) and node.type is None:
            findings.append(Finding(path, node.lineno, "W0702",
                                    "исключение перехвачено без указания типа"))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "print" and "tools" not in path.parts \
                and path.name != "run.py":
            findings.append(Finding(path, node.lineno, "T201",
                                    "отладочный print в рабочем коде"))


def main():
    """Запускает все проверки и печатает отчёт."""
    findings = []
    files = list(python_files())
    for path in files:
        text = path.read_text(encoding="utf-8")
        check_lines(path, text.splitlines(), findings)
        try:
            tree = ast.parse(text)
        except SyntaxError as error:
            findings.append(Finding(path, error.lineno or 1, "E999",
                                    "синтаксическая ошибка: {}".format(error.msg)))
            continue
        check_tree(path, tree, findings)

    print("Проверено файлов: {}".format(len(files)))
    print("Строк кода: {}".format(sum(
        len(p.read_text(encoding="utf-8").splitlines()) for p in files)))
    if not findings:
        print("Замечаний нет — код соответствует принятым правилам.")
        return 0

    by_code = {}
    for finding in findings:
        by_code.setdefault(finding.code, []).append(finding)
    print("Замечаний: {} ({} видов)".format(len(findings), len(by_code)))
    for code in sorted(by_code):
        print("\n[{}] {}".format(code, len(by_code[code])))
        for finding in by_code[code][:5]:
            print("   ", finding)
        if len(by_code[code]) > 5:
            print("    ... и ещё {}".format(len(by_code[code]) - 5))
    return 1


if __name__ == "__main__":
    sys.exit(main())
