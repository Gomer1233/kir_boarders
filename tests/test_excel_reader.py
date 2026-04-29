from openpyxl import Workbook

from scripts.excel_reader import read_xlsx_stream


def test_read_xlsx_stream_preserves_headers_missing_cells_and_numbers(tmp_path):
    path = tmp_path / "sample.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["week", "ts", "value"])
    sheet.append(["2026/03", "A", 10])
    sheet.append(["2026/04", None, 0])
    workbook.save(path)

    df = read_xlsx_stream(path)

    assert df.columns.tolist() == ["week", "ts", "value"]
    assert df.to_dict("records") == [
        {"week": "2026/03", "ts": "A", "value": 10},
        {"week": "2026/04", "ts": None, "value": 0},
    ]
