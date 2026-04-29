import pytest
import pandas as pd

from scripts.merge_data_v3 import merge_route_data, normalize_week


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (202603, "202603"),
        (202603.0, "202603"),
        ("202603", "202603"),
        ("202603.0", "202603"),
        ("2026/03", "202603"),
        ("2026/3", "202603"),
        ("2026 03", "202603"),
    ],
)
def test_normalize_week_supported_formats(value, expected):
    assert normalize_week(value) == expected


@pytest.mark.parametrize("value", [None, "", "abc", "202", "2026/abc"])
def test_normalize_week_invalid_values(value):
    assert normalize_week(value) is None


def test_merge_preserves_all_kir_rows_and_marks_poteri_match(tmp_path):
    kir = pd.DataFrame(
        {
            "НеделяГод": [202603, 202603],
            "ТС": ["A", "A"],
            "Категория": ["C", "C"],
            "Завод": ["S1", "S2"],
            "КИР-950": [0, 10],
        }
    )
    poteri = pd.DataFrame(
        {
            "Неделя": ["2026/03"],
            "Торговая сеть": ["A"],
            "Категория": ["C"],
            "Завод": ["S1"],
            "Списание без НДС (Итог) по B06, руб": [100],
            "Выручка, руб": [1000],
            "Свободно используемый товарный запас без НДС, руб": [50],
        }
    )

    result, diagnostics = merge_route_data(
        kir,
        poteri,
        merge_key=["НеделяГод", "ТС", "Категория", "Завод"],
        poteri_rename_map={
            "Неделя": "НеделяГод",
            "Торговая сеть": "ТС",
            "Списание без НДС (Итог) по B06, руб": "Списания",
            "Выручка, руб": "Выручка",
            "Свободно используемый товарный запас без НДС, руб": "Свободный ТЗ",
        },
    )

    assert len(result) == 2
    assert result["source_row_id"].tolist() == [1, 2]
    assert result["has_poteri_match"].tolist() == [True, False]
    assert result["КИР-950"].tolist() == [0, 10]
    assert diagnostics["kir_input_rows"] == 2
    assert diagnostics["raw_row_count"] == 2
    assert diagnostics["rows_without_poteri_match"] == 1


def test_missing_key_rows_do_not_match_each_other():
    kir = pd.DataFrame(
        {
            "НеделяГод": [None],
            "ТС": ["A"],
            "Категория": ["C"],
            "Завод": ["S1"],
            "КИР-950": [10],
        }
    )
    poteri = pd.DataFrame(
        {
            "Неделя": [None],
            "Торговая сеть": ["A"],
            "Категория": ["C"],
            "Завод": ["S1"],
            "Списание без НДС (Итог) по B06, руб": [100],
        }
    )

    result, diagnostics = merge_route_data(
        kir,
        poteri,
        merge_key=["НеделяГод", "ТС", "Категория", "Завод"],
        poteri_rename_map={
            "Неделя": "НеделяГод",
            "Торговая сеть": "ТС",
            "Списание без НДС (Итог) по B06, руб": "Списания",
        },
    )

    assert len(result) == 1
    assert result.loc[0, "has_missing_key"]
    assert not result.loc[0, "has_poteri_match"]
    assert diagnostics["rows_without_poteri_match"] == 1


def test_duplicate_poteri_keys_can_multiply_rows_and_duplicate_flags_still_work():
    kir = pd.DataFrame(
        {
            "НеделяГод": [202603],
            "ТС": ["A"],
            "Категория": ["C"],
            "Завод": ["S1"],
            "КИР-950": [10],
        }
    )
    poteri = pd.DataFrame(
        {
            "Неделя": ["2026/03", "2026/03"],
            "Торговая сеть": ["A", "A"],
            "Категория": ["C", "C"],
            "Завод": ["S1", "S1"],
            "Списание без НДС (Итог) по B06, руб": [100, 200],
        }
    )

    result, diagnostics = merge_route_data(
        kir,
        poteri,
        merge_key=["НеделяГод", "ТС", "Категория", "Завод"],
        poteri_rename_map={
            "Неделя": "НеделяГод",
            "Торговая сеть": "ТС",
            "Списание без НДС (Итог) по B06, руб": "Списания",
        },
    )

    assert len(result) == 2
    assert result["source_row_id"].tolist() == [1, 1]
    assert result["has_duplicate_poteri_key"].tolist() == [True, True]
    assert diagnostics["raw_row_count"] == 2
    assert diagnostics["duplicate_poteri_keys"]
