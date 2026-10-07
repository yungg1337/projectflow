"""Минимальный экспорт в Excel (XLSX) без внешних библиотек.

Файл XLSX — это ZIP-архив с несколькими XML-документами, поэтому его можно
собрать средствами стандартной библиотеки.
"""
import zipfile
from xml.sax.saxutils import escape

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    '</Types>')

ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    '</Relationships>')

WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="Отчёт" sheetId="1" r:id="rId1"/></sheets>'
    '</workbook>')

WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '</Relationships>')

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1">
<alignment horizontal="left"/></xf>
</cellXfs>
</styleSheet>"""


def column_name(index):
    """Превращает номер столбца (1, 2, ...) в его буквенное имя (A, B, ...)."""
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def cell(reference, value, style=0):
    """Собирает XML одной ячейки."""
    if isinstance(value, bool):
        value = str(value)
    if isinstance(value, (int, float)):
        return '<c r="{}" s="{}"><v>{}</v></c>'.format(reference, style, value)
    text = escape("" if value is None else str(value))
    return '<c r="{}" s="{}" t="inlineStr"><is><t xml:space="preserve">{}</t></is></c>'.format(
        reference, style, text)


def write_report(path, title, columns, rows, summary):
    """Записывает отчёт в файл XLSX и возвращает число строк данных."""
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    widths = "".join('<column min="{0}" max="{0}" width="26" customWidth="1"/>'.format(i)
                     for i in range(1, len(columns) + 1))
    parts.append("<cols>{}</cols>".format(widths))
    parts.append("<sheetData>")
    parts.append('<row r="1">{}</row>'.format(cell("A1", title, 1)))
    parts.append('<row r="2">{}</row>'.format(cell("A2", summary[0] if summary else "")))
    header = ['<row r="4">']
    for index, name in enumerate(columns, start=1):
        header.append(cell("{}{}".format(column_name(index), 4), name, 1))
    header.append("</row>")
    parts.append("".join(header))
    for offset, row in enumerate(rows):
        line = ['<row r="{}">'.format(5 + offset)]
        for index, name in enumerate(columns, start=1):
            line.append(cell("{}{}".format(column_name(index), 5 + offset),
                             row.get(name, "")))
        line.append("</row>")
        parts.append("".join(line))
    extra = 6 + len(rows)
    for offset, text in enumerate(summary[1:] if summary else []):
        parts.append('<row r="{}">{}</row>'.format(
            extra + offset, cell("A{}".format(extra + offset), text, 1)))
    parts.append("</sheetData></worksheet>")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("xl/workbook.xml", WORKBOOK)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        archive.writestr("xl/styles.xml", STYLES)
        archive.writestr("xl/worksheets/sheet1.xml", "".join(parts))
    return len(rows)
