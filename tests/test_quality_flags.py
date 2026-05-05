import pandas as pd

from scripts.quality_flags import add_quality_flags


def test_quality_flags_do_not_drop_rows():
    df = pd.DataFrame(
        {
            "source_row_id": [1, 2, 3],
            "has_poteri_match": [True, False, True],
            "has_missing_key": [False, False, True],
            "КИР-950, шт": [0, 5, None],
            "Списания": [0, 10, None],
            "Выручка": [100, 0, None],
            "Свободный ТЗ": [5, 0, None],
        }
    )

    result = add_quality_flags(df)

    assert len(result) == 3
    assert bool(result.loc[0, "has_zero_kir_units"])
    assert bool(result.loc[0, "has_zero_writeoffs"])
    assert bool(result.loc[1, "has_zero_revenue"])
    assert bool(result.loc[1, "has_zero_stock"])
    assert result.loc[1, "quality_status"] == "warning"
    assert result.loc[2, "quality_status"] == "warning"


def test_quality_flags_marks_source_total_rows_without_dropping_them():
    df = pd.DataFrame(
        {
            "source_row_id": [1, 2],
            "НеделяГод": ["202607", None],
            "ТС": ["ТС Пятерочка", None],
            "Категория": ["Бакалея", None],
            "Завод": ["001-Пятерочка", None],
            "has_poteri_match": [True, False],
            "has_missing_key": [False, True],
            "has_duplicate_kir_key": [False, False],
            "has_duplicate_poteri_key": [False, False],
            "КИР-950, руб. без НДС": [100, "1000"],
        }
    )

    result = add_quality_flags(df)

    assert len(result) == 2
    assert result["is_total_row"].tolist() == [False, True]
    assert "source_total_row" in result.loc[1, "quality_reason"]
    assert result.loc[1, "quality_status"] == "warning"


def test_quality_flags_marks_explicit_itogo_rows_before_key_normalization():
    df = pd.DataFrame(
        {
            "НеделяГод": ["Итого"],
            "ТС": [""],
            "Категория": [""],
            "Завод": [""],
            "has_poteri_match": [False],
            "has_missing_key": [True],
            "КИР-950, руб. без НДС": [1000],
        }
    )

    result = add_quality_flags(df)

    assert bool(result.loc[0, "is_total_row"])
    assert "source_total_row" in result.loc[0, "quality_reason"]
