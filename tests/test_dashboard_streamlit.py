import pandas as pd

from dashboard_streamlit import get_numeric_metric_columns, sort_metric_columns


def test_metric_columns_prioritize_kir_columns():
    df = pd.DataFrame(
        {
            "ТС": ["A"],
            "КИР-950": [1.0],
            "Выручка": [100.0],
            "КИР-066": [2.0],
        }
    )

    metrics = sort_metric_columns(get_numeric_metric_columns(df))

    assert metrics[:2] == ["КИР-066", "КИР-950"]
    assert "Выручка" in metrics
