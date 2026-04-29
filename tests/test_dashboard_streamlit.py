import pandas as pd

from dashboard_streamlit import (
    FACTORY_COL,
    FILTER_COLUMNS,
    GROUP_COLUMNS,
    RELATIONSHIP_COLUMNS,
    build_bin_table,
    calculate_relationship_stats,
    get_numeric_metric_columns,
    metric_summary,
    sort_metric_columns,
)

TS_COL = "\u0422\u0421"
FACTORY = "\u0417\u0430\u0432\u043e\u0434"
KIR_950 = "\u041a\u0418\u0420-950"
KIR_066 = "\u041a\u0418\u0420-066"
REVENUE = "\u0412\u044b\u0440\u0443\u0447\u043a\u0430"
WRITEOFFS = "\u0421\u043f\u0438\u0441\u0430\u043d\u0438\u044f"
STOCK = "\u0421\u0432\u043e\u0431\u043e\u0434\u043d\u044b\u0439 \u0422\u0417"


def test_metric_columns_prioritize_kir_columns():
    df = pd.DataFrame(
        {
            TS_COL: ["A"],
            KIR_950: [1.0],
            REVENUE: [100.0],
            KIR_066: [2.0],
        }
    )

    metrics = sort_metric_columns(get_numeric_metric_columns(df))

    assert metrics[:2] == [KIR_066, KIR_950]
    assert REVENUE in metrics


def test_factory_is_not_a_sidebar_filter():
    assert FACTORY_COL not in FILTER_COLUMNS


def test_factory_can_still_be_used_for_grouping():
    assert FACTORY_COL in GROUP_COLUMNS


def test_metric_summary_contains_tz_statistics():
    summary = metric_summary(pd.Series([0, 10, 20, None]))

    assert summary["count"] == 3
    assert summary["min"] == 0
    assert summary["max"] == 20
    assert summary["mean"] == 10
    assert summary["median"] == 10
    assert summary["p25"] == 5
    assert summary["p85"] == 17
    assert summary["zero_share"] == 1 / 3
    assert summary["missing_share"] == 1 / 4


def test_build_bin_table_counts_rows_per_interval():
    table = build_bin_table(pd.Series([0, 5, 10, 15, 20]), bins=2)

    assert table["count"].tolist() == [3, 2]
    assert round(table["share"].sum(), 6) == 1.0
    assert {"bin", "count", "share"}.issubset(table.columns)


def test_relationship_columns_are_detected_from_final_data():
    df = pd.DataFrame({WRITEOFFS: [1], REVENUE: [2], STOCK: [3], "other": [4]})

    found = [column for column in RELATIONSHIP_COLUMNS if column in df.columns]

    assert found == [WRITEOFFS, REVENUE, STOCK]


def test_calculate_relationship_stats_returns_correlations():
    df = pd.DataFrame({KIR_950: [1, 2, 3, 4], WRITEOFFS: [2, 4, 6, 8], REVENUE: [4, 3, 2, 1]})

    stats = calculate_relationship_stats(df, KIR_950, [WRITEOFFS, REVENUE])

    assert stats.loc[stats["comparison"] == WRITEOFFS, "pearson"].iloc[0] == 1.0
    assert stats.loc[stats["comparison"] == REVENUE, "pearson"].iloc[0] == -1.0
    assert stats["rows_used"].tolist() == [4, 4]


from dashboard_streamlit import format_week_label


def test_format_week_label_handles_excel_float_week():
    assert format_week_label(202607.0) == "07.2026"
    assert format_week_label("202608.0") == "08.2026"
    assert format_week_label("2026.09") == "09.2026"
