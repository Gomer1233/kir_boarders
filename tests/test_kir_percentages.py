import math

import pandas as pd

from scripts.kir_percentages import (
    PERCENT_BASE_COLUMNS,
    add_kir_percentage_columns,
    kir_metric_columns,
    kir_percentage_summary,
    percentage_column_name,
)


def test_kir_metric_columns_selects_numeric_kir_metrics_without_percent_columns():
    df = pd.DataFrame(
        {
            "КИР-950 промо ниже 60%, руб": [10, 20],
            "КИР-950 шт": [1, 2],
            "КИР-950 текстовые числа, руб": ["10", "20.5"],
            "КИР-950 промо ниже 60%, руб / Выручка, %": [10.0, 20.0],
            "Выручка": [100, 200],
            "КИР-текст": ["x", "y"],
        }
    )

    assert kir_metric_columns(df) == ["КИР-950 промо ниже 60%, руб", "КИР-950 шт", "КИР-950 текстовые числа, руб"]


def test_add_kir_percentage_columns_uses_business_percent_and_empty_for_bad_denominator():
    df = pd.DataFrame(
        {
            "КИР-950 руб": [25.0, 30.0, 10.0],
            "КИР-950 шт": [5.0, 2.0, 0.0],
            "Списания": [200.0, 0.0, None],
            "Выручка": [100.0, 200.0, "bad"],
            "Свободный ТЗ": [50.0, None, 0.0],
        }
    )

    result = add_kir_percentage_columns(df)

    assert result.loc[0, percentage_column_name("КИР-950 руб", "Списания")] == 12.5
    assert math.isnan(result.loc[1, percentage_column_name("КИР-950 руб", "Списания")])
    assert result[percentage_column_name("КИР-950 руб", "Выручка")].tolist()[:2] == [25.0, 15.0]
    assert math.isnan(result.loc[2, percentage_column_name("КИР-950 руб", "Выручка")])
    assert result.loc[0, percentage_column_name("КИР-950 шт", "Свободный ТЗ")] == 10.0
    assert math.isnan(result.loc[1, percentage_column_name("КИР-950 шт", "Свободный ТЗ")])
    assert list(df.columns) == ["КИР-950 руб", "КИР-950 шт", "Списания", "Выручка", "Свободный ТЗ"]


def test_add_kir_percentage_columns_handles_kir_numbers_stored_as_text():
    df = pd.DataFrame(
        {
            "КИР-950 руб": ["25", "30.5", "bad"],
            "Выручка": [100, "200", 300],
        }
    )

    result = add_kir_percentage_columns(df, base_columns=("Выручка",))

    column = percentage_column_name("КИР-950 руб", "Выручка")
    assert column in result.columns
    assert result[column].tolist()[:2] == [25.0, 15.25]
    assert math.isnan(result.loc[2, column])


def test_kir_percentage_summary_groups_by_category_and_uses_ratio_of_sums():
    df = pd.DataFrame(
        {
            "Категория": ["A", "A", "B"],
            "КИР-950 руб": [10.0, 30.0, 5.0],
            "Списания": [20.0, 0.0, 5.0],
            "Выручка": [100.0, 100.0, 0.0],
            "Свободный ТЗ": [50.0, 50.0, 10.0],
        }
    )

    result = kir_percentage_summary(df, "КИР-950 руб")

    row_a = result[result["Категория"] == "A"].iloc[0]
    row_b = result[result["Категория"] == "B"].iloc[0]
    assert row_a["Сумма КИР"] == 40.0
    assert row_a["КИР / Списания, %"] == 200.0
    assert row_a["КИР / Выручка, %"] == 20.0
    assert row_a["КИР / Свободный ТЗ, %"] == 40.0
    assert math.isnan(row_b["КИР / Выручка, %"])


def test_kir_percentage_summary_returns_total_row_without_category():
    df = pd.DataFrame(
        {
            "КИР-950 руб": [10.0, 30.0],
            "Списания": [20.0, 30.0],
            "Выручка": [100.0, 200.0],
            "Свободный ТЗ": [50.0, 50.0],
        }
    )

    result = kir_percentage_summary(df, "КИР-950 руб")

    assert result["Итого"].tolist() == ["Итого"]
    assert result.loc[0, "КИР / Выручка, %"] == 40.0 / 300.0 * 100
    assert list(PERCENT_BASE_COLUMNS) == ["Списания", "Выручка", "Свободный ТЗ"]
