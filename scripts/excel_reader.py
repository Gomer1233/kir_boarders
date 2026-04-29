import re
from posixpath import normpath
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


_CELL_REF_RE = re.compile(r"([A-Z]+)")
_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def read_excel_loss_safe(path):
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        return read_xlsx_stream(path)
    return pd.read_excel(path)


def read_xlsx_stream(path, sheet_name=None):
    path = Path(path)
    with ZipFile(path) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_path = _resolve_sheet_path(archive, sheet_name)
        rows = _read_sheet_rows(archive, sheet_path, shared_strings)

    if not rows:
        return pd.DataFrame()

    headers = ["" if value is None else str(value) for value in rows[0]]
    data = [row + [None] * (len(headers) - len(row)) for row in rows[1:]]
    data = [row[: len(headers)] for row in data]
    return pd.DataFrame(data, columns=headers)


def _read_shared_strings(archive):
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []

    strings = []
    with archive.open("xl/sharedStrings.xml") as file:
        for _, element in ET.iterparse(file, events=("end",)):
            if element.tag.endswith("}si"):
                text_parts = []
                for text_node in element.iter():
                    if text_node.tag.endswith("}t") and text_node.text:
                        text_parts.append(text_node.text)
                strings.append("".join(text_parts))
                element.clear()
    return strings


def _resolve_sheet_path(archive, sheet_name):
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))

    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall("pkgrel:Relationship", _NS)
    }

    sheets = workbook.find("main:sheets", _NS)
    for sheet in sheets.findall("main:sheet", _NS):
        if sheet_name is not None and sheet.attrib.get("name") != sheet_name:
            continue
        rel_id = sheet.attrib[f"{{{_NS['rel']}}}id"]
        target = rel_targets[rel_id].lstrip("/")
        return normpath(target if target.startswith("xl/") else f"xl/{target}")

    raise ValueError(f"Sheet not found: {sheet_name}")


def _read_sheet_rows(archive, sheet_path, shared_strings):
    rows = []
    with archive.open(sheet_path) as file:
        for _, element in ET.iterparse(file, events=("end",)):
            if not element.tag.endswith("}row"):
                continue

            values = []
            for cell in element:
                if not cell.tag.endswith("}c"):
                    continue
                col_index = _column_index(cell.attrib.get("r", ""))
                while len(values) < col_index:
                    values.append(None)
                values.append(_cell_value(cell, shared_strings))

            if values:
                rows.append(values)
            element.clear()
    return rows


def _column_index(cell_ref):
    match = _CELL_REF_RE.match(cell_ref)
    if not match:
        return 0

    index = 0
    for char in match.group(1):
        index = index * 26 + ord(char) - ord("A") + 1
    return index - 1


def _cell_value(cell, shared_strings):
    cell_type = cell.attrib.get("t")
    value_node = None
    inline_text = []

    for child in cell:
        if child.tag.endswith("}v"):
            value_node = child
        elif child.tag.endswith("}is"):
            for text_node in child.iter():
                if text_node.tag.endswith("}t") and text_node.text:
                    inline_text.append(text_node.text)

    if cell_type == "inlineStr":
        return "".join(inline_text) if inline_text else None
    if value_node is None or value_node.text is None:
        return None

    raw_value = value_node.text
    if cell_type == "s":
        return shared_strings[int(raw_value)]
    if cell_type in {"str", "b"}:
        return raw_value
    return _coerce_number(raw_value)


def _coerce_number(value):
    try:
        number = float(value)
    except ValueError:
        return value

    if number.is_integer():
        return int(number)
    return number
