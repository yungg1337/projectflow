"""Экспорт отчёта в PDF с помощью библиотеки fpdf2."""
from pathlib import Path

from ..errors import unavailable


def find_font():
    """Ищет системный шрифт с поддержкой кириллицы."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/times.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def write_report(path, title, columns, rows, summary):
    """Записывает отчёт в файл PDF и возвращает число строк данных."""
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise unavailable(
            "Для выгрузки в PDF установите библиотеку: pip install fpdf2") from exc
    font_path = find_font()
    if font_path is None:
        raise unavailable("Не найден системный шрифт с поддержкой кириллицы")

    document = FPDF(orientation="L", unit="mm", format="A4")
    document.set_auto_page_break(auto=True, margin=12)
    document.add_font("main", "", font_path)
    document.set_font("main", size=14)
    document.add_page()
    usable = document.w - 2 * document.l_margin

    document.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT", align="C")
    document.set_font("main", size=9)
    for line in summary[:1]:
        document.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    document.ln(2)

    widths = _column_widths(document, columns, rows, usable)
    document.set_font("main", size=9)
    for index, name in enumerate(columns):
        document.cell(widths[index], 7, name, border=1, align="C")
    document.ln()
    for row in rows:
        for index, name in enumerate(columns):
            text = _shorten(row.get(name, ""), widths[index], document)
            document.cell(widths[index], 6, text, border=1)
        document.ln()
    if not rows:
        document.cell(0, 6, "Данных за указанный период нет",
                      new_x="LMARGIN", new_y="NEXT")

    document.ln(3)
    document.set_font("main", size=10)
    for line in summary[1:]:
        document.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    document.output(path)
    return len(rows)


def _column_widths(document, columns, rows, usable):
    """Подбирает ширину колонок по длине самого длинного значения."""
    widths = []
    for name in columns:
        longest = len(str(name))
        for row in rows:
            longest = max(longest, len(str(row.get(name, ""))))
        widths.append(longest)
    total = sum(widths) or 1
    return [max(18.0, usable * width / total) for width in widths]


def _shorten(text, width, document):
    """Обрезает слишком длинный текст, чтобы он влез в колонку."""
    limit = int(width / 1.6)
    text = str(text)
    return text if len(text) <= limit else text[:limit - 1] + "…"
