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
