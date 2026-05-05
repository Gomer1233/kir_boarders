from pathlib import Path

import pandas as pd

from dashboard_streamlit import (
    DATA_PROJECTS_DIR,
    acquire_project_run_lock,
    allowed_upload_extensions,
    apply_filter_values,
    dataframe_cache_key,
    download_file_name,
    FACTORY_COL,
    FILTER_COLUMNS,
    format_run_result,
    format_running_message,
    metric_analysis_context,
    _problem_rows,
    render_metric_analysis_context_html,
    render_correlation_interpretation_html,
    pipeline_progress_value,
    pipeline_status_text,
    dashboard_run_label,
    dashboard_title,
    dashboard_css,
    GROUP_COLUMNS,
    RELATIONSHIP_COLUMNS,
    build_bin_table,
    bin_width_settings,
    calculate_relationship_stats,
    chart_settings_summary,
    collapse_tail_bins,
    compare_network_correlations,
    correlation_business_insights,
    correlation_strength_label,
    filter_zero_metric_values,
    filter_label,
    format_percentile_card,
    render_percentile_card_html,
    get_numeric_metric_columns,
    filter_options_for_column,
    group_comparison_tables,
    route_label,
    route_short_label,
    list_legacy_run_dirs,
    list_project_run_dirs,
    latest_project_run_name,
    latest_project_run_by_route,
    route_from_run_dir,
    load_upload_manifest,
    make_pipeline_run_request,
    metric_unit_for_metric,
    prepare_bin_table_display,
    prepare_bin_chart_table,
    metric_summary,
    metric_bar_value_column,
    network_brand_html,
    network_chart_color,
    normalize_new_project_input,
    project_route_uploads_exist,
    project_run_lock_status,
    routes_for_ui_mode,
    select_run_result_to_open,
    should_render_upload_widgets,
    sort_metric_columns,
    project_select_options,
    read_file_for_download,
    release_project_run_lock,
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


def test_factory_is_not_available_for_grouping():
    assert GROUP_COLUMNS == [TS_COL, "\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f"]
    assert FACTORY_COL not in GROUP_COLUMNS


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


def test_metric_analysis_context_describes_store_and_category_route_with_selected_categories():
    df = pd.DataFrame(
        {
            TS_COL: ["ТС Пятерочка", "ТС Перекресток"],
            "\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f": ["Молоко", "Хлеб"],
        }
    )

    context = metric_analysis_context(
        df,
        {"\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f": ["Молоко", "Хлеб"], TS_COL: ["ТС Пятерочка"]},
        metric="КИР-950",
    )

    assert context == {
        "metric": "КИР-950",
        "scope": "Магазины и Категории",
        "categories": "Молоко, Хлеб",
        "networks": "ТС Пятерочка",
    }


def test_metric_analysis_context_summarizes_all_categories_without_overloading_ui():
    df = pd.DataFrame(
        {
            TS_COL: ["A", "B", "B"],
            "\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f": ["Cat 1", "Cat 2", "Cat 3"],
        }
    )

    context = metric_analysis_context(df, {})

    assert context["metric"] is None
    assert context["scope"] == "Магазины и Категории"
    assert context["categories"] == "Все категории (3)"
    assert context["networks"] == "A, B"


def test_metric_analysis_context_describes_store_only_route():
    df = pd.DataFrame({TS_COL: ["A", "B"]})

    context = metric_analysis_context(df, {})

    assert context == {"metric": None, "scope": "Магазины", "categories": None, "networks": "A, B"}


def test_render_metric_analysis_context_html_is_compact_and_escapes_values():
    html = render_metric_analysis_context_html(
        {"metric": "КИР <950>", "scope": "Магазины и Категории", "categories": "A <B>", "networks": "ТС Пятерочка"}
    )

    assert "Что анализируем" in html
    assert "Метрика" in html
    assert "КИР &lt;950&gt;" in html
    assert "Магазины и Категории" in html
    assert "A &lt;B&gt;" in html
    assert "A <B>" not in html
    assert "Сеть" in html
    assert "ТС ТС Пятерочка" not in html
    assert "analysis-context" in html


def test_render_metric_analysis_context_html_wraps_long_metric_names():
    html = render_metric_analysis_context_html(
        {
            "metric": "КИР-950. ТЗ после рег./сезон. Промо с реализацией ниже 60% от прогноза",
            "scope": "Магазины и Категории",
            "categories": None,
            "networks": "ТС Пятерочка",
        }
    )

    assert "white-space:normal" in html
    assert "overflow-wrap:break-word" in html
    assert "word-break:normal" in html
    assert "text-overflow:ellipsis" not in html
    assert "white-space:nowrap" not in html


def test_dashboard_css_wraps_long_selectbox_values():
    css = dashboard_css()

    assert ".stSelectbox" in css
    assert "radial-gradient" in css
    assert "linear-gradient" in css
    assert 'data-testid="stAppViewContainer"' in css
    assert 'data-testid="stSidebar"' in css
    assert "border-radius: 18px" in css
    assert "rgba(15, 23, 42" in css
    assert "[data-testid=\"stRadio\"] div[role=\"radiogroup\"] label" in css
    assert "[data-testid=\"stRadio\"] div[role=\"radiogroup\"] label:has(input:checked)" in css
    assert "[data-testid=\"stRadio\"] div[role=\"radiogroup\"] label > div:first-child" in css
    assert "[data-testid=\"stRadio\"] label {" not in css
    assert "display: none" in css
    assert "justify-content: center" in css
    assert "[data-testid=\"stRadio\"] div[role=\"radiogroup\"] label p" in css
    assert "line-height: 1" in css
    assert "white-space: normal" in css
    assert "overflow-wrap: anywhere" in css
    assert "text-overflow: clip" in css
    assert "height: auto" in css
    assert "text-overflow: ellipsis" not in css


def test_filter_zero_metric_values_removes_only_numeric_zero_rows():
    df = pd.DataFrame({"metric": [0, "0", 1, None, "bad"], "label": ["a", "b", "c", "d", "e"]})
    numeric_metric = pd.to_numeric(df["metric"], errors="coerce")

    filtered_df, filtered_metric = filter_zero_metric_values(df, numeric_metric)

    assert filtered_df["label"].tolist() == ["c", "d", "e"]
    assert filtered_metric.tolist()[:1] == [1.0]
    assert pd.isna(filtered_metric.iloc[1])
    assert pd.isna(filtered_metric.iloc[2])


def test_filter_options_for_column_formats_weeks_and_omits_nulls():
    df = pd.DataFrame({"week": [202607.0, None, "202608.0"]})

    options = filter_options_for_column(df, "week")

    assert options == [202607.0, "202608.0"]


def test_apply_filter_values_filters_only_selected_columns():
    df = pd.DataFrame({"week": [1, 1, 2], "ts": ["A", "B", "A"], "value": [10, 20, 30]})

    filtered = apply_filter_values(df, {"week": [1], "ts": []})

    assert filtered["value"].tolist() == [10, 20]


def test_apply_filter_values_excludes_total_rows_by_default_for_analytics():
    df = pd.DataFrame({"value": [10, 20, 30], "is_total_row": [False, True, False]})

    filtered = apply_filter_values(df, {})

    assert filtered["value"].tolist() == [10, 30]


def test_apply_filter_values_can_keep_total_rows_for_problem_rows():
    df = pd.DataFrame({"value": [10, 20, 30], "is_total_row": [False, True, False]})

    filtered = apply_filter_values(df, {}, exclude_total_rows=False)

    assert filtered["value"].tolist() == [10, 20, 30]


def test_problem_rows_include_source_total_rows():
    df = pd.DataFrame(
        {
            "value": [10, 20],
            "has_poteri_match": [True, True],
            "has_missing_key": [False, False],
            "has_duplicate_kir_key": [False, False],
            "has_duplicate_poteri_key": [False, False],
            "is_total_row": [False, True],
        }
    )

    problems = _problem_rows(df)

    assert problems["value"].tolist() == [20]


def test_format_percentile_card_separates_count_from_threshold():
    card = format_percentile_card("Stores >= P85", {"count": 21140, "total_count": 26213, "threshold": 4197.33}, metric_unit="руб")

    assert card["primary_value"] == "21 140"
    assert card["count_share"] == "80.6%"
    assert card["count_details"] == "магазинов выше или равно порогу"
    assert card["threshold_label"] == "Порог метрики"
    assert card["threshold_value"] == "4,197.33"
    assert card["threshold_unit"] == "руб"
    assert card["threshold_help"] == "Порог: 4,197.33 руб. Ниже порога: 5 073 магазинов. Всего в выборке: 26 213."


def test_format_percentile_card_explains_lower_threshold_direction():
    card = format_percentile_card("Stores <= P25", {"count": 6498, "total_count": 26213, "threshold": 0}, metric_unit="шт")

    assert card["threshold_unit"] == "шт"
    assert card["count_share"] == "24.8%"
    assert card["primary_value"] == "6 498"
    assert card["count_details"] == "магазинов ниже или равно порогу"
    assert card["threshold_help"] == "Порог: 0.00 шт. Выше порога: 19 715 магазинов. Всего в выборке: 26 213."


def test_format_percentile_card_for_percent_metric_uses_business_percent_format():
    card = format_percentile_card(
        "Stores >= P85",
        {"count": 3724, "total_count": 24825, "threshold": 1.389432},
        metric_unit="%",
        metric_label="процента КИР",
    )

    assert card["primary_value"] == "3 724"
    assert card["count_share"] == "15.0%"
    assert card["count_details"] == "магазинов выше или равно порогу"
    assert card["threshold_value"] == "1,3894"
    assert card["threshold_unit"] == "%"
    assert card["threshold_help"] == "\u041f\u043e\u0440\u043e\u0433: 1,3894 %. \u041d\u0438\u0436\u0435 \u043f\u043e\u0440\u043e\u0433\u0430: 21 101 \u043c\u0430\u0433\u0430\u0437\u0438\u043d\u043e\u0432. \u0412\u0441\u0435\u0433\u043e \u0432 \u0432\u044b\u0431\u043e\u0440\u043a\u0435: 24 825."


def test_metric_unit_for_metric_detects_rubles_and_units():
    assert metric_unit_for_metric("КИР-950, руб. без НДС") == "руб"
    assert metric_unit_for_metric("КИР-950, шт") == "шт"
    assert metric_unit_for_metric("КИР-950. Промо ниже 60% от прогноза, руб. без НДС") == "руб"
    assert metric_unit_for_metric("КИР-950. Промо ниже 60% от прогноза, шт") == "шт"
    assert metric_unit_for_metric("КИР-950. Промо ниже 60% от прогноза, руб. без НДС / Выручка, %") == "%"
    assert metric_unit_for_metric("КИР-950") == ""


def test_render_percentile_card_html_includes_soft_percentile_color():
    card = format_percentile_card(
        "Stores >= P85",
        {"count": 21140, "total_count": 26213, "threshold": 4197.33},
        metric_unit="руб",
    )

    html = render_percentile_card_html(card, "#ff4d4d")

    assert "Stores &gt;= P85" in html
    assert "21 140" in html
    assert "(80.6%)" in html
    assert "магазинов выше или равно порогу" in html
    assert "Порог метрики" in html
    assert "Threshold" not in html
    assert "info-icon" not in html
    assert 'title="' not in html
    assert '<span style="color:#ff4d4d;font-weight:850;">4,197.33 руб</span>' in html
    assert "#ff4d4d" in html


def test_render_percentile_card_html_has_no_indented_html_code_blocks():
    card = format_percentile_card(
        "Stores <= P25",
        {"count": 6207, "total_count": 24825, "threshold": 0.6843},
        metric_unit="%",
        metric_label="процента КИР",
    )

    html = render_percentile_card_html(card, "#2fbf71")

    assert "\n    <div" not in html
    assert "\n        <div" not in html


def test_metric_bar_value_column_prefers_unique_store_counts():
    assert metric_bar_value_column(pd.DataFrame({"count": [1], "store_count": [1]})) == "store_count"
    assert metric_bar_value_column(pd.DataFrame({"count": [1]})) == "count"


def test_network_chart_color_uses_soft_brand_colors():
    assert network_chart_color("ТС Пятерочка") == "#f06a6a"
    assert network_chart_color("ТС Перекресток") == "#64b878"
    assert network_chart_color("Unknown") == "#79bff2"


def test_network_brand_html_renders_pyaterochka_brand_label():
    html = network_brand_html("ТС Пятерочка")

    assert "brand-pyaterochka" in html
    assert "Пятёрочка" in html
    assert "#e52320" in html
    assert ">5<" not in html
    assert "border-radius:50%" not in html


def test_network_brand_html_renders_perekrestok_brand_label():
    html = network_brand_html("ТС Перекресток")

    assert "brand-perekrestok" in html
    assert "Перекрёсток" in html
    assert "#00843d" in html
    assert "∞" not in html
    assert "text-shadow" not in html


def test_network_brand_html_escapes_unknown_network_name():
    html = network_brand_html("Unknown <network>")

    assert "Unknown &lt;network&gt;" in html
    assert "Unknown <network>" not in html


def test_collapse_tail_bins_keeps_head_and_sums_remaining_bins():
    table = pd.DataFrame(
        {
            "bin_start": [0, 10, 20, 30],
            "bin_end": [10, 20, 30, 40],
            "bin": ["0 - 10", "10 - 20", "20 - 30", "30 - 40"],
            "count": [100, 50, 25, 10],
            "store_count": [80, 40, 20, 8],
            "share": [0.54, 0.27, 0.14, 0.05],
        }
    )

    collapsed = collapse_tail_bins(table, head_bins=2)

    assert collapsed["bin"].tolist() == ["0 - 10", "10 - 20", "Tail: >= 20"]
    assert collapsed["count"].tolist() == [100, 50, 35]
    assert collapsed["store_count"].tolist() == [80, 40, 28]
    assert collapsed["share"].round(2).tolist() == [0.54, 0.27, 0.19]


def test_collapse_tail_bins_returns_copy_when_head_covers_all_bins():
    table = pd.DataFrame({"bin_start": [0, 10], "bin_end": [10, 20], "bin": ["0 - 10", "10 - 20"], "count": [1, 2]})

    collapsed = collapse_tail_bins(table, head_bins=5)

    assert collapsed.equals(table)
    assert collapsed is not table


def test_prepare_bin_chart_table_uses_bin_midpoints_and_widths_for_geometry():
    table = pd.DataFrame(
        {
            "bin_start": [0, 3469.068],
            "bin_end": [3469.068, 5203.602],
            "bin": ["0 - 3469.068", "3469.068 - 5203.602"],
            "count": [100, 10],
        }
    )

    chart_table = prepare_bin_chart_table(table)

    assert chart_table["bin_mid"].round(3).tolist() == [1734.534, 4336.335]
    assert chart_table["bar_width"].round(3).tolist() == [3469.068, 1734.534]


def test_prepare_bin_chart_table_preserves_chart_columns_for_empty_input():
    table = pd.DataFrame(columns=["bin_start", "bin_end", "bin", "count", "store_count", "share"])

    chart_table = prepare_bin_chart_table(table)

    assert chart_table.empty
    assert {"bin_mid", "bar_width"}.issubset(chart_table.columns)


def test_prepare_bin_table_display_hides_duplicate_bin_label_and_starts_rows_at_one():
    table = pd.DataFrame(
        {
            "bin_start": [0, 10],
            "bin_end": [10, 20],
            "bin": ["0 - 10", "10 - 20"],
            "count": [3, 2],
            "store_count": [3, 2],
            "share": [0.6, 0.4],
        }
    )

    display = prepare_bin_table_display(table)

    assert "bin" not in display.columns
    assert display.index.tolist() == [1, 2]
    assert display.index.name == "№"
    assert display["bin_start"].tolist() == [0, 10]


def test_build_bin_table_counts_rows_per_interval():
    table = build_bin_table(pd.Series([0, 5, 10, 15, 20]), bins=2)

    assert table["count"].tolist() == [3, 2]
    assert round(table["share"].sum(), 6) == 1.0
    assert {"bin", "count", "share"}.issubset(table.columns)


def test_group_comparison_tables_split_categories_by_ts_when_multiple_networks_selected():
    df = pd.DataFrame(
        {
            TS_COL: ["Perek", "Perek", "Pyater", "Pyater"],
            "\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f": ["A", "A", "A", "B"],
        }
    )
    metric = pd.Series([10, 30, 100, 200])

    tables = group_comparison_tables(df, metric, "\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f")

    assert [name for name, _ in tables] == ["Perek", "Pyater"]
    perek = tables[0][1]
    pyater = tables[1][1]
    assert perek["\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f"].tolist() == ["A"]
    assert perek["count"].tolist() == [2]
    assert perek["mean"].tolist() == [20.0]
    assert pyater["\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f"].tolist() == ["A", "B"]


def test_group_comparison_tables_keep_single_table_for_ts_grouping():
    df = pd.DataFrame({TS_COL: ["Perek", "Pyater"], "\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f": ["A", "A"]})
    metric = pd.Series([10, 20])

    tables = group_comparison_tables(df, metric, TS_COL)

    assert len(tables) == 1
    assert tables[0][0] is None
    assert tables[0][1][TS_COL].tolist() == ["Perek", "Pyater"]


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


def test_calculate_relationship_stats_can_use_same_cleaned_slice_as_relationship_charts():
    df = pd.DataFrame(
        {
            KIR_950: [1, 2, 3, 4, 1000, 0, -1],
            WRITEOFFS: [1, 2, 3, 4, 1000, 5, 6],
        }
    )

    stats = calculate_relationship_stats(
        df,
        KIR_950,
        [WRITEOFFS],
        clean_visual=True,
        outlier_quantile=0.80,
    )

    assert stats.loc[0, "rows_used"] == 4
    assert stats.loc[0, "spearman"] == 1.0


def test_correlation_strength_label_uses_spearman_business_ranges():
    assert correlation_strength_label(None) == "нет данных"
    assert correlation_strength_label(0.10) == "связи почти нет"
    assert correlation_strength_label(0.40) == "умеренная положительная связь"
    assert correlation_strength_label(-0.73) == "сильная отрицательная связь"
    assert correlation_strength_label(0.86) == "очень сильная положительная связь"


def test_prepare_correlation_display_stats_adds_business_strength_column():
    stats = pd.DataFrame(
        [
            {"comparison": WRITEOFFS, "pearson": 0.11, "spearman": 0.40, "rows_used": 1029},
            {"comparison": REVENUE, "pearson": 0.39, "spearman": 0.60, "rows_used": 1029},
        ]
    )

    display = prepare_correlation_display_stats(stats)

    assert display["Сила связи"].tolist() == ["умеренная положительная связь", "сильная положительная связь"]
    assert display.columns.tolist() == ["Показатель", "Pearson", "Spearman", "Сила связи", "Строк в расчете"]


def test_prepare_correlation_display_stats_uses_spearman_not_pearson_for_strength():
    stats = pd.DataFrame([{"comparison": WRITEOFFS, "pearson": 0.95, "spearman": 0.10, "rows_used": 100}])

    display = prepare_correlation_display_stats(stats)

    assert display.loc[0, "Сила связи"] == "связи почти нет"


def test_correlation_business_insights_explain_best_signal_and_nonlinear_gap():
    stats = pd.DataFrame(
        [
            {"comparison": WRITEOFFS, "pearson": 0.11, "spearman": 0.40, "rows_used": 1029},
            {"comparison": REVENUE, "pearson": 0.39, "spearman": 0.60, "rows_used": 1029},
        ]
    )

    insights = correlation_business_insights(stats, "ТС Перекресток")

    assert any("Самая заметная связь: Выручка" in line for line in insights)
    assert any("Spearman 0.60" in line for line in insights)
    assert any("Списания" in line and "ранговая связь заметнее линейной" in line for line in insights)


def test_compare_network_correlations_highlights_stronger_network_and_small_differences():
    perek = pd.DataFrame(
        [
            {"comparison": REVENUE, "pearson": 0.39, "spearman": 0.60, "rows_used": 1029},
            {"comparison": WRITEOFFS, "pearson": 0.11, "spearman": 0.40, "rows_used": 1029},
        ]
    )
    pyater = pd.DataFrame(
        [
            {"comparison": REVENUE, "pearson": 0.41, "spearman": 0.52, "rows_used": 24813},
            {"comparison": WRITEOFFS, "pearson": 0.04, "spearman": 0.39, "rows_used": 24813},
        ]
    )

    comparison = compare_network_correlations({"ТС Перекресток": perek, "ТС Пятерочка": pyater})

    assert any("Выручка" in line and "сильнее у ТС Перекресток" in line and "Δ 0.08" in line for line in comparison)
    assert any("Списания" in line and "различие небольшое" in line for line in comparison)
    assert any("rows_used" in line and "сильно отличаются" in line for line in comparison)


def test_render_correlation_interpretation_html_escapes_values_and_explains_methods():
    stats = pd.DataFrame([{"comparison": "A <B>", "pearson": 0.11, "spearman": 0.40, "rows_used": 10}])

    html = render_correlation_interpretation_html("ТС <Перекресток>", stats)

    assert "Pearson" in html
    assert "Spearman" in html
    assert "Оценка силы связи строится по Spearman" in html
    assert "Положительная связь" in html
    assert "Отрицательная связь" in html
    assert "не доказывает причинно-следственную связь" in html
    assert "ТС &lt;Перекресток&gt;" in html
    assert "A &lt;B&gt;" in html
    assert "A <B>" not in html


from dashboard_streamlit import format_week_label


def test_format_week_label_handles_excel_float_week():
    assert format_week_label(202607.0) == "Y2026 W07"
    assert format_week_label("202608.0") == "Y2026 W08"
    assert format_week_label("2026.09") == "Y2026 W09"
    assert format_week_label("2026/3") == "Y2026 W03"


def test_filter_label_renames_week_year_for_business_users():
    assert filter_label("\u041d\u0435\u0434\u0435\u043b\u044f\u0413\u043e\u0434") == "Год и Неделя"
    assert filter_label(TS_COL) == TS_COL


from dashboard_streamlit import run_file_paths


def test_run_file_paths_returns_final_and_raw_paths(tmp_path):
    paths = run_file_paths(tmp_path / "run_1_route_1")

    assert paths == {
        "final": tmp_path / "run_1_route_1" / "final_clean_data.xlsx",
        "raw": tmp_path / "run_1_route_1" / "merged_raw.xlsx",
    }


def test_allowed_upload_extensions_only_accepts_xlsx():
    assert allowed_upload_extensions() == ["xlsx"]


def test_dataframe_cache_key_uses_path_and_mtime(tmp_path):
    path = tmp_path / "final_clean_data.xlsx"

    assert dataframe_cache_key(path, 123).endswith("final_clean_data.xlsx:123")


def test_list_project_run_dirs_returns_project_runs(tmp_path):
    runs_dir = tmp_path / "003" / "runs"
    (runs_dir / "run_001_route_1").mkdir(parents=True)
    (runs_dir / "run_002_route_2").mkdir()

    runs = list_project_run_dirs("003", projects_dir=tmp_path)

    assert [run.name for run in runs] == ["run_002_route_2", "run_001_route_1"]


def test_list_legacy_run_dirs_returns_ready_data_runs(tmp_path):
    (tmp_path / "run_001_route_1").mkdir()
    (tmp_path / "run_001_route_1" / "final_clean_data.xlsx").write_text("x")
    (tmp_path / "run_002_route_2").mkdir()
    (tmp_path / "run_002_route_2" / "final_clean_data.xlsx").write_text("x")
    (tmp_path / "run_003_route_1").mkdir()
    (tmp_path / "projects" / "003" / "runs" / "run_004_route_1").mkdir(parents=True)

    runs = list_legacy_run_dirs(data_dir=tmp_path)

    assert [run.name for run in runs] == ["run_002_route_2", "run_001_route_1"]


def test_data_projects_dir_points_under_data():
    assert DATA_PROJECTS_DIR.name == "projects"
    assert DATA_PROJECTS_DIR.parent.name == "data"


def test_project_select_options_keeps_empty_project_list_empty():
    assert project_select_options([]) == []


def test_project_select_options_sorts_existing_projects():
    assert project_select_options(["020", "003", "950"]) == ["003", "020", "950"]


def test_normalize_new_project_input_strips_whitespace():
    assert normalize_new_project_input("  003  ") == "003"


def test_normalize_new_project_input_collapses_inner_spaces():
    assert normalize_new_project_input(" KIR 003 ") == "KIR_003"


def test_routes_for_ui_mode_maps_single_and_both_modes():
    assert routes_for_ui_mode("route_1") == ["route_1"]
    assert routes_for_ui_mode("route_2") == ["route_2"]
    assert routes_for_ui_mode("both") == ["route_1", "route_2"]


def test_route_label_uses_business_names_for_ui():
    assert route_label("route_1") == "Route 1: Магазины и Категории"
    assert route_label("route_2") == "Route 2: Магазины"
    assert route_label("both") == "Both routes"
    assert route_label("unknown") == "unknown"


def test_route_short_label_uses_compact_business_names_for_header_toggle():
    assert route_short_label("route_1") == "Магазины + категории"
    assert route_short_label("route_2") == "Магазины"
    assert route_short_label("unknown") == "unknown"


def test_route_from_run_dir_detects_route_suffix():
    assert route_from_run_dir(Path("data/projects/950/runs/run_003_route_1")) == "route_1"
    assert route_from_run_dir(Path("data/projects/950/runs/run_004_route_2")) == "route_2"
    assert route_from_run_dir(Path("data/run_005")) is None


def test_dashboard_title_uses_selected_project_name():
    assert dashboard_title("950") == "Дашборд 950"
    assert dashboard_title("KIR_083") == "Дашборд KIR_083"
    assert dashboard_title(None) == "KIR Dashboard"


def test_dashboard_css_makes_header_sticky():
    css = dashboard_css()

    assert ".st-key-dashboard_header" in css
    assert "div[data-testid=\"stVerticalBlock\"] > div:has(.st-key-dashboard_header)" in css
    assert "position: sticky" in css
    assert "top: 0" in css


def test_routes_for_ui_mode_rejects_unknown_mode():
    try:
        routes_for_ui_mode("bad")
    except ValueError as exc:
        assert "Unsupported route mode" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_format_run_result_includes_route_run_and_output_paths(tmp_path):
    result = {
        "route": "route_1",
        "run_dir": tmp_path / "run_001_route_1",
        "paths": {
            "final_clean": tmp_path / "run_001_route_1" / "final_clean_data.xlsx",
            "merged_raw": tmp_path / "run_001_route_1" / "merged_raw.xlsx",
        },
    }

    text = format_run_result(result)

    assert "Route 1: Магазины и Категории" in text
    assert "Файлы успешно созданы" in text
    assert "перехожу к сборке дашборда" in text
    assert "run_001_route_1" in text
    assert "final_clean_data.xlsx" in text
    assert "merged_raw.xlsx" in text
    assert "unknown" not in text


def test_format_running_message_uses_readable_routes_and_project():
    assert format_running_message("950", ["route_1"]) == "Running Route 1: Магазины и Категории for project 950..."
    assert format_running_message("950", ["route_1", "route_2"]) == "Running Both routes for project 950..."


def test_pipeline_status_text_returns_readable_russian_copy():
    assert pipeline_status_text("active").startswith("Прогон выполняется")
    assert "завершения" in pipeline_status_text("already_running")
    assert "другого проекта" in pipeline_status_text("other_project")
    assert "lock-файл" in pipeline_status_text("stale_lock")
    for key in [
        "active",
        "already_running",
        "other_project",
        "stale_lock",
        "open_after_both_label",
        "open_after_both_help",
    ]:
        assert "Ð" not in pipeline_status_text(key)
        assert "???" not in pipeline_status_text(key)


def test_pipeline_progress_value_starts_visible_and_never_reaches_finished_state():
    assert pipeline_progress_value(0, 18) == 10
    assert pipeline_progress_value(1, 18) > 10
    assert pipeline_progress_value(18, 18) == 99


def test_should_render_upload_widgets_only_when_project_is_not_running():
    assert should_render_upload_widgets(False) is True
    assert should_render_upload_widgets(True) is False


def test_download_file_name_includes_run_context():
    run_dir = Path("data") / "run_015_route_1"
    path = run_dir / "final_clean_data.xlsx"

    assert download_file_name(path, run_dir) == "run_015_route_1_final_clean_data.xlsx"


def test_read_file_for_download_reads_exact_bytes(tmp_path):
    path = tmp_path / "merged_raw.xlsx"
    path.write_bytes(b"excel-bytes")

    assert read_file_for_download(path, path.stat().st_mtime_ns) == b"excel-bytes"


def test_read_file_for_download_raises_clear_error_for_missing_file(tmp_path):
    missing = tmp_path / "missing.xlsx"

    try:
        read_file_for_download(missing, 0)
    except FileNotFoundError as exc:
        assert "Download file not found" in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError")


def test_load_upload_manifest_returns_none_when_missing(tmp_path):
    assert load_upload_manifest("003", "route_1", projects_dir=tmp_path) is None


def test_load_upload_manifest_reads_saved_upload_metadata(tmp_path):
    manifest_dir = tmp_path / "003" / "uploads" / "route_1"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "upload_manifest.json").write_text(
        '{"kir_original_name": "kir.xlsx", "poteri_original_name": "poteri.xlsx", "saved_at": "2026-04-29T00:00:00Z"}',
        encoding="utf-8",
    )

    manifest = load_upload_manifest("003", "route_1", projects_dir=tmp_path)

    assert manifest["kir_original_name"] == "kir.xlsx"
    assert manifest["poteri_original_name"] == "poteri.xlsx"


def test_project_route_uploads_exist_requires_both_stable_source_files(tmp_path):
    upload_dir = tmp_path / "950" / "uploads" / "route_1"
    upload_dir.mkdir(parents=True)
    (upload_dir / "kir_source.xlsx").write_bytes(b"kir")

    assert project_route_uploads_exist("950", "route_1", projects_dir=tmp_path) is False

    (upload_dir / "poteri_source.xlsx").write_bytes(b"poteri")

    assert project_route_uploads_exist("950", "route_1", projects_dir=tmp_path) is True


def test_project_run_lock_prevents_second_parallel_run(tmp_path):
    assert acquire_project_run_lock("950", projects_dir=tmp_path) is True
    assert acquire_project_run_lock("950", projects_dir=tmp_path) is False

    release_project_run_lock("950", projects_dir=tmp_path)

    assert acquire_project_run_lock("950", projects_dir=tmp_path) is True
    release_project_run_lock("950", projects_dir=tmp_path)


def test_project_run_lock_status_reports_lock_path(tmp_path):
    unlocked = project_run_lock_status("950", projects_dir=tmp_path)

    assert unlocked["locked"] is False
    assert unlocked["path"] == tmp_path / "950" / ".pipeline.lock"

    acquire_project_run_lock("950", projects_dir=tmp_path)
    locked = project_run_lock_status("950", projects_dir=tmp_path)

    assert locked["locked"] is True
    assert locked["path"] == tmp_path / "950" / ".pipeline.lock"
    release_project_run_lock("950", projects_dir=tmp_path)


def test_make_pipeline_run_request_stores_project_and_routes():
    assert make_pipeline_run_request("950", ("route_1", "route_2")) == {
        "project": "950",
        "routes": ["route_1", "route_2"],
        "open_route": "route_1",
    }


def test_make_pipeline_run_request_accepts_explicit_open_route():
    assert make_pipeline_run_request("950", ("route_1", "route_2"), open_route="route_2") == {
        "project": "950",
        "routes": ["route_1", "route_2"],
        "open_route": "route_2",
    }


def test_select_run_result_to_open_uses_preferred_route():
    results = [
        {"route": "route_1", "run_dir": "run_001_route_1"},
        {"route": "route_2", "run_dir": "run_002_route_2"},
    ]

    assert select_run_result_to_open(results, "route_1") == results[0]
    assert select_run_result_to_open(results, "route_2") == results[1]


def test_select_run_result_to_open_falls_back_to_last_result():
    results = [
        {"route": "route_1", "run_dir": "run_001_route_1"},
        {"route": "route_2", "run_dir": "run_002_route_2"},
    ]

    assert select_run_result_to_open(results, "route_3") == results[-1]


def test_latest_project_run_name_returns_newest_run(tmp_path):
    runs_dir = tmp_path / "003" / "runs"
    (runs_dir / "run_001_route_1").mkdir(parents=True)
    (runs_dir / "run_002_route_2").mkdir()

    assert latest_project_run_name("003", projects_dir=tmp_path) == "run_002_route_2"


def test_latest_project_run_by_route_returns_newest_ready_run_per_route(tmp_path):
    runs_dir = tmp_path / "003" / "runs"
    (runs_dir / "run_001_route_1").mkdir(parents=True)
    (runs_dir / "run_002_route_2").mkdir()
    (runs_dir / "run_003_route_1").mkdir()
    (runs_dir / "run_004_route_3").mkdir()
    (runs_dir / "run_001_route_1" / "final_clean_data.xlsx").write_text("ready")
    (runs_dir / "run_002_route_2" / "final_clean_data.xlsx").write_text("ready")
    (runs_dir / "run_004_route_3" / "final_clean_data.xlsx").write_text("ready")

    runs = latest_project_run_by_route("003", projects_dir=tmp_path)

    assert {route: path.name for route, path in runs.items()} == {
        "route_1": "run_001_route_1",
        "route_2": "run_002_route_2",
    }


def test_dashboard_run_label_uses_run_folder_name():
    assert dashboard_run_label(Path("data/projects/083/runs/run_002_route_1")) == "run_002_route_1"


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


def test_read_final_data_with_progress_reuses_session_cache(tmp_path):
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
    cache = {}

    first = read_final_data_with_progress(
        path,
        123,
        read_func=fake_read,
        progress_factory=lambda value, text: FakeProgress(),
        dataframe_cache=cache,
    )
    second = read_final_data_with_progress(
        path,
        123,
        read_func=fake_read,
        progress_factory=lambda value, text: FakeProgress(),
        dataframe_cache=cache,
    )

    assert first is second
    assert [call for call in calls if call[0] == "read"] == [("read", str(path), 123)]


from dashboard_streamlit import (
    DASHBOARD_SCREENS,
    DATA_STRUCTURE_SECTIONS,
    build_bin_table_by_width,
    default_bin_width,
    adjust_bin_width,
    format_kir_summary_amount,
    format_kir_summary_display,
    prepare_bin_chart_table,
    sample_for_plot,
)


def test_dashboard_screens_match_tz_sections():
    assert DASHBOARD_SCREENS == [
        "1. Корреляции",
        "2. КИР vs Метрики",
        "3. Распределение показателя",
        "Структура данных",
    ]


def test_data_structure_sections_collect_technical_screens():
    assert DATA_STRUCTURE_SECTIONS == [
        "Сравнение групп",
        "Качество данных",
        "Проблемные строки",
        "Таблица данных",
    ]


def test_sample_for_plot_limits_large_dataframes():
    df = pd.DataFrame({"value": range(100)})

    sampled = sample_for_plot(df, max_rows=10)

    assert len(sampled) == 10
    assert sampled["value"].tolist() == [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]


def test_default_bin_width_can_ignore_extreme_percent_tail():
    series = pd.Series([0.0, 0.1, 0.2, 0.5, 1.0, 2.0] * 100 + [30000.0])

    width = default_bin_width(series, minimum=0.01, maximum=5.0, upper_quantile=0.99)

    assert 0.01 <= width <= 1.0


def test_adjust_bin_width_supports_fractional_percent_steps():
    assert adjust_bin_width(0.2, 0.1, minimum=0.01) == 0.3
    assert adjust_bin_width(0.2, -0.1, minimum=0.01) == 0.1
    assert adjust_bin_width(0.01, -0.1, minimum=0.01) == 0.01


def test_build_bin_table_by_width_caps_huge_bin_counts_with_tail():
    series = pd.Series([0.0, 0.1, 0.2, 10000.0])

    table = build_bin_table_by_width(series, bin_width=0.1, max_bins=10)

    assert len(table) == 10
    assert table.iloc[-1]["bin"].startswith("Tail:")
    assert table.iloc[-1]["count"] == 1


def test_prepare_bin_chart_table_draws_tail_as_compact_bar():
    table = pd.DataFrame(
        [
            {"bin_start": 0.0, "bin_end": 1.0, "bin": "0 - 1", "count": 10, "store_count": 10, "share": 0.5},
            {"bin_start": 1.0, "bin_end": 2.0, "bin": "1 - 2", "count": 8, "store_count": 8, "share": 0.4},
            {"bin_start": 2.0, "bin_end": 100000.0, "bin": "Tail: >= 2", "count": 2, "store_count": 2, "share": 0.1},
        ]
    )

    chart = prepare_bin_chart_table(table)

    assert chart.loc[2, "bar_width"] == 1.0
    assert chart.loc[2, "bin_mid"] == 2.5


def test_format_kir_summary_display_formats_amounts_without_decimals():
    summary = pd.DataFrame(
        {
            "Категория": ["Бакалея", None],
            "Сумма КИР": [1936376253.9925, None],
            "Сумма списаний": [295312091.9, None],
            "КИР / Списания, %": [264.8659, None],
            "Сумма выручки": [34933625180.27, None],
        }
    )

    display = format_kir_summary_display(summary)

    assert display.loc[0, "Сумма КИР"] == "1 936 376 254"
    assert display.loc[0, "Сумма списаний"] == "295 312 092"
    assert display.loc[0, "Сумма выручки"] == "34 933 625 180"
    assert display.loc[1, "Сумма КИР"] == ""
    assert display.loc[0, "КИР / Списания, %"] == "264.9%"
    assert display.loc[1, "КИР / Списания, %"] == ""


def test_format_kir_summary_amount_handles_empty_values():
    assert format_kir_summary_amount(None) == ""
    assert format_kir_summary_amount(float("nan")) == ""


def test_relationship_summary_table_reuses_kir_summary_for_current_metric():
    source = pd.DataFrame(
        {
            "Категория": ["A", "A", "B"],
            "КИР-950 руб": [10, 20, 40],
            "Списания": [100, 200, 300],
            "Выручка": [1000, 2000, 3000],
            "Свободный ТЗ": [50, 100, 150],
        }
    )

    display = relationship_summary_table(source, "КИР-950 руб")

    assert display.loc[0, "Категория"] == "B"
    assert display.loc[0, "Сумма КИР"] == "40"
    assert display.loc[0, "КИР / Списания, %"] == "13.3%"
    assert display.loc[0, "КИР / Выручка, %"] == "1.3%"
    assert display.loc[0, "КИР / Свободный ТЗ, %"] == "26.7%"


def test_metric_analysis_does_not_render_boxplot():
    source = Path("dashboard_streamlit.py").read_text(encoding="utf-8")

    assert "px.box" not in source
    assert "Boxplot:" not in source


def test_metric_analysis_hides_detailed_summary_table_and_moves_chart_settings_below_cards():
    source = Path("dashboard_streamlit.py").read_text(encoding="utf-8")
    stats_table_index = source.index("st.dataframe(pd.DataFrame([summary]), use_container_width=True)")

    assert source.rfind("with st.expander(", 0, stats_table_index) > source.index('c5.metric("Zero values"')
    assert source.index("render_percentile_card_html") < source.index('with st.expander("Настройки графика", expanded=False):')
    assert source.index('"Hide zero metric values"') > source.index("render_percentile_card_html")


def test_metric_chart_settings_expander_has_stable_title_and_visible_summary():
    source = Path("dashboard_streamlit.py").read_text(encoding="utf-8")
    expander_index = source.index('with st.expander("Настройки графика", expanded=False):')

    assert "with st.expander(chart_settings_summary(" not in source
    assert source.index("metric-chart-settings-spacer") < expander_index
    assert source.index("st.caption(chart_settings_summary(") > expander_index


def test_bin_table_keeps_only_manual_first_bin_summary():
    source = Path("dashboard_streamlit.py").read_text(encoding="utf-8")

    assert "By store share" not in source
    assert "Target % of stores" not in source
    assert '"Apply bin width"' not in source
    assert "Подогнать bin width под выбранный % магазинов" not in source
    assert 'format=width_settings["format"]' in source
    assert "Для анализа порогов используйте плитки перцентилей выше." in source
    assert "Сумма первых N бинов" in source


def test_percent_bin_width_settings_allow_four_decimal_precision():
    settings = bin_width_settings(is_percent_metric=True)

    assert settings["step"] == 0.0001
    assert settings["format"] == "%.4f"


def test_dashboard_exposes_cli_runs_even_without_project_selection():
    source = Path("dashboard_streamlit.py").read_text(encoding="utf-8")

    assert "list_legacy_run_dirs()" in source
    assert "Open CLI run (data/run_*)" in source
    assert source.index("legacy_run_dirs = list_legacy_run_dirs()") < source.index("opened_run_dir = st.session_state.get")


from dashboard_streamlit import (
    adjust_bin_width,
    build_bin_table_by_width,
    default_bin_width,
    filter_visual_outliers,
    first_bin_count_for_target_share,
    first_bins_store_sum,
    first_bins_summary,
    apply_pending_session_value,
    queue_session_value,
    relationship_summary_table,
    recommended_bin_width_for_target_share,
    set_session_value,
    relationship_chart_rows,
    relationship_heading_html,
    percentile_store_counts,
    prepare_correlation_display_stats,
    split_by_network,
    resolve_kir_percent_settings,
    filter_kir_percentage_source,
)


def test_build_bin_table_by_width_uses_fixed_bin_width():
    table = build_bin_table_by_width(pd.Series([0, 5, 10, 15, 20]), bin_width=10)

    assert table["bin_start"].tolist() == [0, 10, 20]
    assert table["bin_end"].tolist() == [10, 20, 30]
    assert table["count"].tolist() == [2, 2, 1]


def test_default_bin_width_is_small_editable_starting_value():
    assert default_bin_width(pd.Series([0, 300])) == 10
    assert default_bin_width(pd.Series([0, 1])) == 1
    assert default_bin_width(pd.Series([0, 999])) == 100
    assert default_bin_width(pd.Series([0, 100_000_000])) == 1000


def test_adjust_bin_width_uses_explicit_button_steps_and_never_goes_below_minimum():
    assert adjust_bin_width(100, 10) == 110
    assert adjust_bin_width(100, -10) == 90
    assert adjust_bin_width(5, -10) == 1


def test_chart_settings_summary_is_compact_and_business_readable():
    assert chart_settings_summary(1000.0, 40, hide_zero_values=False, collapse_tail=True) == (
        "Настройки графика: bin 1,000, P40, нули показаны, хвост свернут"
    )
    assert chart_settings_summary(250.5, 85, hide_zero_values=True, collapse_tail=False) == (
        "Настройки графика: bin 250.50, P85, нули скрыты, хвост показан"
    )

    assert chart_settings_summary(2.486732, 30, hide_zero_values=True, collapse_tail=False, is_percent_metric=True) == (
        "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0433\u0440\u0430\u0444\u0438\u043a\u0430: bin 2.4867, P30, \u043d\u0443\u043b\u0438 \u0441\u043a\u0440\u044b\u0442\u044b, \u0445\u0432\u043e\u0441\u0442 \u043f\u043e\u043a\u0430\u0437\u0430\u043d"
    )

def test_percentile_store_counts_counts_low_p25_and_high_upper_thresholds():
    result = percentile_store_counts(pd.Series([0, 10, 20, 30]), custom_percentile=50)

    assert result["p25"]["percentile"] == 25
    assert result["p25"]["count"] == 1
    assert result["p25"]["total_count"] == 4
    assert result["p25"]["share"] == 0.25
    assert result["p85"]["percentile"] == 85
    assert result["p85"]["count"] == 1
    assert result["custom"]["percentile"] == 50
    assert result["custom"]["count"] == 2
    assert result["custom"]["total_count"] == 4
    assert result["custom"]["share"] == 0.5


def test_split_by_network_returns_one_frame_per_ts():
    df = pd.DataFrame({TS_COL: ["B", "A", "B"], "value": [1, 2, 3]})

    groups = split_by_network(df)

    assert [name for name, _ in groups] == ["A", "B"]
    assert [len(group) for _, group in groups] == [1, 2]


def test_split_by_network_handles_missing_ts_without_pandas_categorical_error():
    df = pd.DataFrame({TS_COL: ["B", None, "A", float("nan")], "value": [1, 2, 3, 4]})

    groups = split_by_network(df)

    assert [name for name, _ in groups] == ["A", "B", "Без ТС"]
    missing_group = dict(groups)["Без ТС"]
    assert missing_group["value"].tolist() == [2, 4]


def test_filter_visual_outliers_trims_extreme_x_and_y_values_without_mutating_source():
    df = pd.DataFrame({"_metric": [1, 2, 3, 1000], WRITEOFFS: [10, 20, 30, 9999]})

    filtered = filter_visual_outliers(df, "_metric", WRITEOFFS, quantile=0.75)

    assert filtered["_metric"].tolist() == [1, 2, 3]
    assert df["_metric"].tolist() == [1, 2, 3, 1000]


def test_filter_visual_outliers_removes_zero_and_negative_x_or_y_values():
    df = pd.DataFrame({"_metric": [-1, 0, 1, 2], WRITEOFFS: [10, 10, 0, 20]})

    filtered = filter_visual_outliers(df, "_metric", WRITEOFFS, quantile=1.0)

    assert filtered["_metric"].tolist() == [2]
    assert filtered[WRITEOFFS].tolist() == [20]


def test_relationship_chart_rows_group_networks_side_by_side_per_comparison_metric():
    rows = relationship_chart_rows(["TC Perekrestok", "TC Pyaterochka"], [WRITEOFFS, REVENUE])

    assert rows == [
        {"comparison": WRITEOFFS, "networks": ["TC Perekrestok", "TC Pyaterochka"]},
        {"comparison": REVENUE, "networks": ["TC Perekrestok", "TC Pyaterochka"]},
    ]


def test_relationship_heading_html_makes_vs_and_comparison_metric_visually_explicit():
    html = relationship_heading_html("KIR <950>", REVENUE)

    assert "VS" in html
    assert "relationship-heading" in html
    assert "comparison-label" in html
    assert "metric-label" in html
    assert "comparison-badge" not in html
    assert REVENUE in html
    assert "KIR &lt;950&gt;" in html
    assert "KIR <950>" not in html



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


def test_first_bin_count_for_target_share_returns_minimum_bins_covering_share():
    table = pd.DataFrame({"count": [100, 50, 25], "store_count": [10, 5, 2]})

    assert first_bin_count_for_target_share(table, 0.70) == 2
    assert first_bin_count_for_target_share(table, 1.00) == 3
    assert first_bin_count_for_target_share(table, 0) == 1


def test_recommended_bin_width_for_target_share_uses_actual_bin_grid():
    metric = pd.Series(range(101))

    recommendation = recommended_bin_width_for_target_share(metric, target_share=0.40, bins_used=8, current_bin_width=10)

    assert recommendation == 6.6668


def test_recommended_bin_width_for_target_share_is_stable_after_apply():
    metric = pd.Series([0] * 100 + list(range(1, 1000)))

    first_recommendation = recommended_bin_width_for_target_share(
        metric,
        target_share=0.50,
        bins_used=46,
        current_bin_width=10,
    )
    applied_table = build_bin_table_by_width(metric, first_recommendation)
    applied_bins = first_bin_count_for_target_share(applied_table, 0.50)
    second_recommendation = recommended_bin_width_for_target_share(
        metric,
        target_share=0.50,
        bins_used=applied_bins,
        current_bin_width=first_recommendation,
    )

    assert second_recommendation == first_recommendation


def test_recommended_bin_width_for_target_share_uses_actual_negative_bin_start():
    metric = pd.Series([-5, 20, 21, 22, 23])

    recommendation = recommended_bin_width_for_target_share(
        metric,
        target_share=0.40,
        bins_used=2,
        current_bin_width=25,
    )
    applied_table = build_bin_table_by_width(metric, recommendation)
    applied_bins = first_bin_count_for_target_share(applied_table, 0.40)
    applied_summary = first_bins_summary(metric, applied_table, applied_bins)

    assert recommendation != 25.0
    assert applied_bins == 2
    assert applied_summary["store_share"] == 0.40


def test_set_session_value_updates_target_key(monkeypatch):
    import dashboard_streamlit

    fake_state = {}
    monkeypatch.setattr(dashboard_streamlit.st, "session_state", fake_state)

    set_session_value("bin_width", 947.76)

    assert fake_state["bin_width"] == 947.76


def test_queue_session_value_stores_pending_widget_update(monkeypatch):
    import dashboard_streamlit

    fake_state = {}
    monkeypatch.setattr(dashboard_streamlit.st, "session_state", fake_state)

    queue_session_value("bin_width", 947.76)

    assert fake_state["bin_width__pending"] == 947.76
    assert "bin_width" not in fake_state


def test_apply_pending_session_value_updates_widget_key_before_render(monkeypatch):
    import dashboard_streamlit

    fake_state = {"bin_width": 1000.0, "bin_width__pending": 947.76}
    monkeypatch.setattr(dashboard_streamlit.st, "session_state", fake_state)

    apply_pending_session_value("bin_width")

    assert fake_state["bin_width"] == 947.76
    assert "bin_width__pending" not in fake_state


def test_resolve_kir_percent_settings_keeps_valid_applied_values():
    result = resolve_kir_percent_settings(
        {
            "metric": "КИР-2",
            "base": "Выручка",
            "exclude_zero_kir": True,
            "exclude_zero_base": False,
            "exclude_negative_kir": True,
            "exclude_negative_base": False,
        },
        ["КИР-1", "КИР-2"],
        ["Списания", "Выручка"],
        default_metric="КИР-1",
    )

    assert result == {
        "metric": "КИР-2",
        "base": "Выручка",
        "exclude_zero_kir": True,
        "exclude_zero_base": False,
        "exclude_negative_kir": True,
        "exclude_negative_base": False,
    }


def test_resolve_kir_percent_settings_falls_back_when_applied_values_are_missing():
    result = resolve_kir_percent_settings(
        {"metric": "missing", "base": "missing"},
        ["КИР-1", "КИР-2"],
        ["Списания", "Выручка"],
        default_metric="КИР-2",
    )

    assert result == {
        "metric": "КИР-2",
        "base": "Списания",
        "exclude_zero_kir": False,
        "exclude_zero_base": True,
        "exclude_negative_kir": False,
        "exclude_negative_base": True,
    }


def test_filter_kir_percentage_source_excludes_zero_base_by_default():
    source = pd.DataFrame(
        {
            "КИР-950 руб": [0, 10, 20, 30],
            "Выручка": [100, 0, 200, 0],
        }
    )

    result, counters = filter_kir_percentage_source(source, "КИР-950 руб", "Выручка")

    assert result["КИР-950 руб"].tolist() == [0, 20]
    assert counters == {
        "input_rows": 4,
        "excluded_zero_kir_rows": 0,
        "excluded_zero_base_rows": 2,
        "excluded_negative_kir_rows": 0,
        "excluded_negative_base_rows": 0,
        "excluded_rows": 2,
        "remaining_rows": 2,
    }


def test_filter_kir_percentage_source_can_exclude_zero_kir_and_keep_zero_base():
    source = pd.DataFrame(
        {
            "КИР-950 руб": [0, 10, 0, 30],
            "Выручка": [100, 0, 200, 300],
        }
    )

    result, counters = filter_kir_percentage_source(
        source,
        "КИР-950 руб",
        "Выручка",
        exclude_zero_kir=True,
        exclude_zero_base=False,
    )

    assert result["КИР-950 руб"].tolist() == [10, 30]
    assert counters == {
        "input_rows": 4,
        "excluded_zero_kir_rows": 2,
        "excluded_zero_base_rows": 0,
        "excluded_negative_kir_rows": 0,
        "excluded_negative_base_rows": 0,
        "excluded_rows": 2,
        "remaining_rows": 2,
    }


def test_filter_kir_percentage_source_handles_numeric_text_values():
    source = pd.DataFrame(
        {
            "КИР-950 руб": ["0", "10", "20"],
            "Выручка": ["100", "0", "200"],
        }
    )

    result, counters = filter_kir_percentage_source(
        source,
        "КИР-950 руб",
        "Выручка",
        exclude_zero_kir=True,
        exclude_zero_base=True,
    )

    assert result["КИР-950 руб"].tolist() == ["20"]
    assert counters == {
        "input_rows": 3,
        "excluded_zero_kir_rows": 1,
        "excluded_zero_base_rows": 1,
        "excluded_negative_kir_rows": 0,
        "excluded_negative_base_rows": 0,
        "excluded_rows": 2,
        "remaining_rows": 1,
    }


def test_filter_kir_percentage_source_excludes_negative_base_by_default_but_keeps_negative_kir():
    source = pd.DataFrame(
        {
            "КИР-950 руб": [-5, 10, 20, -30],
            "Выручка": [100, -100, 200, 300],
        }
    )

    result, counters = filter_kir_percentage_source(source, "КИР-950 руб", "Выручка")

    assert result["КИР-950 руб"].tolist() == [-5, 20, -30]
    assert counters == {
        "input_rows": 4,
        "excluded_zero_kir_rows": 0,
        "excluded_zero_base_rows": 0,
        "excluded_negative_kir_rows": 0,
        "excluded_negative_base_rows": 1,
        "excluded_rows": 1,
        "remaining_rows": 3,
    }


def test_filter_kir_percentage_source_can_exclude_negative_kir():
    source = pd.DataFrame(
        {
            "КИР-950 руб": [-5, 10, 20, -30],
            "Выручка": [100, -100, 200, 300],
        }
    )

    result, counters = filter_kir_percentage_source(
        source,
        "КИР-950 руб",
        "Выручка",
        exclude_negative_kir=True,
        exclude_negative_base=False,
    )

    assert result["КИР-950 руб"].tolist() == [10, 20]
    assert counters == {
        "input_rows": 4,
        "excluded_zero_kir_rows": 0,
        "excluded_zero_base_rows": 0,
        "excluded_negative_kir_rows": 2,
        "excluded_negative_base_rows": 0,
        "excluded_rows": 2,
        "remaining_rows": 2,
    }


def test_filter_kir_percentage_source_counters_ignore_disabled_rules_for_overlapping_conditions():
    source = pd.DataFrame(
        {
            "КИР-950 руб": [-5, 10],
            "Выручка": [0, 100],
        }
    )

    result, counters = filter_kir_percentage_source(
        source,
        "КИР-950 руб",
        "Выручка",
        exclude_zero_base=False,
        exclude_negative_kir=True,
        exclude_negative_base=False,
    )

    assert result["КИР-950 руб"].tolist() == [10]
    assert counters == {
        "input_rows": 2,
        "excluded_zero_kir_rows": 0,
        "excluded_zero_base_rows": 0,
        "excluded_negative_kir_rows": 1,
        "excluded_negative_base_rows": 0,
        "excluded_rows": 1,
        "remaining_rows": 1,
    }


def test_first_bins_summary_counts_unique_stores_across_combined_first_bins():
    metric = pd.Series([1, 2, 12, 14, 25])
    stores = pd.Series(["A", "A", "B", "C", "D"])
    bin_table = pd.DataFrame({"bin_start": [0, 10, 20], "bin_end": [10, 20, 30]})

    result = first_bins_summary(metric, bin_table, 2, store_series=stores)

    assert result == {"bins_used": 2, "store_sum": 3, "total_stores": 4, "store_share": 0.75}


def test_percentile_store_counts_counts_unique_stores_when_store_series_is_provided():
    result = percentile_store_counts(
        pd.Series([0, 10, 20, 30]),
        custom_percentile=50,
        store_series=pd.Series(["A", "A", "B", "C"]),
    )

    assert result["custom"]["count"] == 2
    assert result["custom"]["total_count"] == 3
    assert result["custom"]["share"] == 2 / 3
