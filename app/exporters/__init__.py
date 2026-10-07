"""Экспорт отчётов в файлы PDF и Excel."""
from . import pdf, xlsx

EXPORTERS = {"xlsx": xlsx.write_report, "pdf": pdf.write_report}


def export(fmt, path, title, columns, rows, summary):
    """Сохраняет отчёт в файл нужного формата."""
    return EXPORTERS[fmt](path, title, columns, rows, summary)
