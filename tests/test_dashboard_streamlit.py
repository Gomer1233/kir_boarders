import pandas as pd

from dashboard_streamlit import (
    FACTORY_COL,
    FILTER_COLUMNS,
    GROUP_COLUMNS,
    RELATIONSHIP_COLUMNS,
    build_bin_table,
    calculate_relationship_stats,
    filter_zero_metric_values,
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
    assert summary["zero_count"] == 1
    assert summary["zero_share"] == 1 / 3
    assert summary["missing_share"] == 1 / 4


def test_filter_zero_metric_values_removes_only_numeric_zero_rows():
    df = pd.DataFrame({"metric": [0, "0", 1, None, "bad"], "label": ["a", "b", "c", "d", "e"]})
    numeric_metric = pd.to_numeric(df["metric"], errors="coerce")

    filtered_df, filtered_metric = filter_zero_metric_values(df, numeric_metric)

    assert filtered_df["label"].tolist() == ["c", "d", "e"]
    assert filtered_metric.tolist()[:1] == [1.0]
    assert pd.isna(filtered_metric.iloc[1])
    assert pd.isna(filtered_metric.iloc[2])


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


from dashboard_streamlit import run_file_paths


def test_run_file_paths_returns_final_and_raw_paths(tmp_path):
    paths = run_file_paths(tmp_path / "run_1_route_1")

    assert paths == {
        "final": tmp_path / "run_1_route_1" / "final_clean_data.xlsx",
        "raw": tmp_path / "run_1_route_1" / "merged_raw.xlsx",
    }


from dashboard_streamlit import read_final_data_with_progress


def test_read_final_data_with_progress_shows_loading_steps(tmp_path):
    calls = []

    class FakeProgress:
        def progress(self, value, text=None):
            calls.append((value, text))

        def empty(self):
            calls.append(("empty", None))

    def fake_read(path, mtime_ns):
        calls.append(("read", path, mtime_ns))
        return pd.DataFrame({"value": [1]})

    path = tmp_path / "final_clean_data.xlsx"
    path.write_text("placeholder")

    df = read_final_data_with_progress(path, 123, read_func=fake_read, progress_factory=lambda value, text: FakeProgress())

    assert df["value"].tolist() == [1]
    assert calls == [
        (10, "Preparing final_clean_data.xlsx..."),
        (35, "Reading Excel file. First load can take a while..."),
        ("read", str(path), 123),
        (90, "Preparing dashboard data..."),
        (100, "Dashboard data loaded."),
        ("empty", None),
    ]


from dashboard_streamlit import DASHBOARD_SCREENS, sample_for_plot


def test_dashboard_screens_match_tz_sections():
    assert DASHBOARD_SCREENS == [
        "Overview",
        "Metric analysis",
        "Group comparison",
        "Poteri relationships",
        "Problem rows",
        "Data",
    ]


def test_sample_for_plot_limits_large_dataframes():
    df = pd.DataFrame({"value": range(100)})

    sampled = sample_for_plot(df, max_rows=10)

    assert len(sampled) == 10
    assert sampled["value"].tolist() == [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]


from dashboard_streamlit import (
    adjust_bin_width,
    build_bin_table_by_width,
    default_bin_width,
    filter_visual_outliers,
    first_bins_store_sum,
    relationship_chart_rows,
    percentile_store_counts,
    split_by_network,
)


def test_build_bin_table_by_width_uses_fixed_bin_width():
    table = build_bin_table_by_width(pd.Series([0, 5, 10, 15, 20]), bin_width=10)

    assert table["bin_start"].tolist() == [0, 10, 20]
    assert table["bin_end"].tolist() == [10, 20, 30]
    assert table["count"].tolist() == [2, 2, 1]


def test_default_bin_width_is_small_editable_starting_value():
    assert default_bin_width(pd.Series([0, 300])) == 10
    assert default_bin_width(pd.Series([0, 1])) == 1


def test_adjust_bin_width_uses_explicit_button_steps_and_never_goes_below_minimum():
    assert adjust_bin_width(100, 10) == 110
    assert adjust_bin_width(100, -10) == 90
    assert adjust_bin_width(5, -10) == 1


def test_percentile_store_counts_counts_values_below_thresholds():
    result = percentile_store_counts(pd.Series([0, 10, 20, 30]), custom_percentile=50)

    assert result["p25"]["percentile"] == 25
    assert result["p25"]["count"] == 1
    assert result["p85"]["percentile"] == 85
    assert result["p85"]["count"] == 3
    assert result["custom"]["percentile"] == 50
    assert result["custom"]["count"] == 2


def test_split_by_network_returns_one_frame_per_ts():
    df = pd.DataFrame({TS_COL: ["B", "A", "B"], "value": [1, 2, 3]})

    groups = split_by_network(df)

    assert [name for name, _ in groups] == ["A", "B"]
    assert [len(group) for _, group in groups] == [1, 2]


def test_filter_visual_outliers_trims_extreme_x_and_y_values_without_mutating_source():
    df = pd.DataFrame({"_metric": [1, 2, 3, 1000], WRITEOFFS: [10, 20, 30, 9999]})

    filtered = filter_visual_outliers(df, "_metric", WRITEOFFS, quantile=0.75)

    assert filtered["_metric"].tolist() == [1, 2, 3]
    assert df["_metric"].tolist() == [1, 2, 3, 1000]


def test_relationship_chart_rows_group_networks_side_by_side_per_comparison_metric():
    rows = relationship_chart_rows(["TC Perekrestok", "TC Pyaterochka"], [WRITEOFFS, REVENUE])

    assert rows == [
        {"comparison": WRITEOFFS, "networks": ["TC Perekrestok", "TC Pyaterochka"]},
        {"comparison": REVENUE, "networks": ["TC Perekrestok", "TC Pyaterochka"]},
    ]



def test_build_bin_table_by_width_counts_unique_stores_when_store_series_is_provided():
    table = build_bin_table_by_width(
        pd.Series([0, 5, 5, 15]),
        bin_width=10,
        store_series=pd.Series(["A", "A", "B", "C"]),
    )

    assert table["count"].tolist() == [3, 1]
    assert table["store_count"].tolist() == [2, 1]


def test_first_bins_store_sum_uses_store_count_when_available():
    table = pd.DataFrame({"count": [100, 50, 25], "store_count": [10, 5, 2]})

    result = first_bins_store_sum(table, 2)

    assert result == {"bins_used": 2, "store_sum": 15, "row_sum": 150}


def test_first_bins_store_sum_clamps_requested_bin_count_to_table_size():
    table = pd.DataFrame({"count": [100, 50]})

    result = first_bins_store_sum(table, 10)

    assert result == {"bins_used": 2, "store_sum": 150, "row_sum": 150}


def test_percentile_store_counts_counts_unique_stores_when_store_series_is_provided():
    result = percentile_store_counts(
        pd.Series([0, 10, 20, 30]),
        custom_percentile=50,
        store_series=pd.Series(["A", "A", "B", "C"]),
    )

    assert result["custom"]["count"] == 1
