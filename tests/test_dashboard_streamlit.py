import pandas as pd

from dashboard_streamlit import FILTER_COLUMNS, GROUP_COLUMNS, get_numeric_metric_columns, sort_metric_columns


def test_metric_columns_prioritize_kir_columns():
    df = pd.DataFrame(
        {
            "??": ["A"],
            "???-950": [1.0],
            "???????": [100.0],
            "???-066": [2.0],
        }
    )

    metrics = sort_metric_columns(get_numeric_metric_columns(df))

    assert metrics[:2] == ["???-066", "???-950"]
    assert "???????" in metrics


def test_factory_is_not_a_sidebar_filter():
    assert "?????" not in FILTER_COLUMNS


def test_factory_can_still_be_used_for_grouping():
    assert "?????" in GROUP_COLUMNS
