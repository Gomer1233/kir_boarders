from pathlib import Path
import re

import pandas as pd

try:
    import streamlit as st
except ModuleNotFoundError:
    st = None


DATA_DIR = Path("data")
WEEK_COL = "\u041d\u0435\u0434\u0435\u043b\u044f\u0413\u043e\u0434"
TS_COL = "\u0422\u0421"
CATEGORY_COL = "\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f"
FACTORY_COL = "\u0417\u0430\u0432\u043e\u0434"
WRITEOFFS_COL = "\u0421\u043f\u0438\u0441\u0430\u043d\u0438\u044f"
REVENUE_COL = "\u0412\u044b\u0440\u0443\u0447\u043a\u0430"
FREE_STOCK_COL = "\u0421\u0432\u043e\u0431\u043e\u0434\u043d\u044b\u0439 \u0422\u0417"

FILTER_COLUMNS = [WEEK_COL, TS_COL, CATEGORY_COL, "has_poteri_match", "quality_status"]
GROUP_COLUMNS = [TS_COL, CATEGORY_COL, FACTORY_COL]
RELATIONSHIP_COLUMNS = [WRITEOFFS_COL, REVENUE_COL, FREE_STOCK_COL]
PROBLEM_FLAG_COLUMNS = ["has_poteri_match", "has_missing_key", "has_duplicate_kir_key", "has_duplicate_poteri_key"]
DASHBOARD_SCREENS = [
    "Overview",
    "Metric analysis",
    "Group comparison",
    "Poteri relationships",
    "Problem rows",
    "Data",
]


def _require_streamlit():
    if st is None:
        raise RuntimeError("Streamlit is not installed. Install dependencies from requirements.txt.")


def get_numeric_metric_columns(df):
    return df.select_dtypes(include="number").columns.tolist()


def sort_metric_columns(columns):
    kir = sorted([column for column in columns if str(column).startswith("\u041a\u0418\u0420-")])
    other = sorted([column for column in columns if column not in kir])
    return kir + other


def list_run_dirs():
    if not DATA_DIR.exists():
        return []
    return sorted(
        [path for path in DATA_DIR.iterdir() if path.is_dir() and path.name.startswith("run_")],
        reverse=True,
    )


def run_file_paths(run_dir):
    run_dir = Path(run_dir)
    return {
        "final": run_dir / "final_clean_data.xlsx",
        "raw": run_dir / "merged_raw.xlsx",
    }


def _read_excel_cached(path, mtime_ns):
    return pd.read_excel(path)


if st is not None:
    _read_excel_cached = st.cache_data(show_spinner="Loading final_clean_data.xlsx...")(_read_excel_cached)


def sample_for_plot(df, max_rows=20000):
    if len(df) <= max_rows:
        return df
    step = max(1, len(df) // max_rows)
    return df.iloc[::step].head(max_rows)


def format_week_label(value):
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]

    compact_match = re.fullmatch(r"(\d{4})(\d{2})", text)
    if compact_match:
        return f"{compact_match.group(2)}.{compact_match.group(1)}"

    dotted_match = re.fullmatch(r"(\d{4})[./-](\d{1,2})", text)
    if dotted_match:
        return f"{int(dotted_match.group(2)):02d}.{dotted_match.group(1)}"

    return str(value)


def metric_summary(series):
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    total_count = len(numeric)
    valid_count = len(valid)
    if valid_count == 0:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "p25": None,
            "p85": None,
            "zero_share": 0,
            "missing_share": 1 if total_count else 0,
        }
    return {
        "count": int(valid_count),
        "min": float(valid.min()),
        "max": float(valid.max()),
        "mean": float(valid.mean()),
        "median": float(valid.median()),
        "p25": float(valid.quantile(0.25)),
        "p85": float(valid.quantile(0.85)),
        "zero_share": float(valid.eq(0).sum() / valid_count),
        "missing_share": float(numeric.isna().sum() / total_count) if total_count else 0,
    }


def build_bin_table(series, bins=20):
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return pd.DataFrame(columns=["bin", "count", "share"])

    bucketed = pd.cut(numeric, bins=bins, include_lowest=True, duplicates="drop")
    counts = bucketed.value_counts(sort=False)
    table = counts.rename_axis("bin").reset_index(name="count")
    table["bin"] = table["bin"].astype(str)
    table["share"] = table["count"] / int(counts.sum())
    return table


def build_bin_table_by_width(series, bin_width, store_series=None):
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return pd.DataFrame(columns=["bin_start", "bin_end", "bin", "count", "store_count", "share"])

    bin_width = float(bin_width)
    if bin_width <= 0:
        raise ValueError("bin_width must be positive")

    min_value = float(numeric.min())
    max_value = float(numeric.max())
    start = (min_value // bin_width) * bin_width
    end = ((max_value // bin_width) + 1) * bin_width
    edges = list(_frange(start, end + bin_width, bin_width))
    source = pd.DataFrame({"metric": pd.to_numeric(series, errors="coerce")})
    if store_series is not None:
        source["store"] = store_series
    source = source.dropna(subset=["metric"])
    source["bin_interval"] = pd.cut(source["metric"], bins=edges, right=False, include_lowest=True)
    counts = source["bin_interval"].value_counts(sort=False)

    rows = []
    total = int(counts.sum())
    for interval, count in counts.items():
        bin_rows = source[source["bin_interval"] == interval]
        store_count = int(bin_rows["store"].nunique()) if "store" in bin_rows.columns else int(count)
        rows.append(
            {
                "bin_start": _clean_number(interval.left),
                "bin_end": _clean_number(interval.right),
                "bin": f"{_clean_number(interval.left)} - {_clean_number(interval.right)}",
                "count": int(count),
                "store_count": store_count,
                "share": float(count / total) if total else 0,
            }
        )
    return pd.DataFrame(rows)


def percentile_store_counts(series, custom_percentile, store_series=None):
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return {
            "p25": {"percentile": 25, "threshold": None, "count": 0},
            "p85": {"percentile": 85, "threshold": None, "count": 0},
            "custom": {"percentile": custom_percentile, "threshold": None, "count": 0},
        }

    source = pd.DataFrame({"metric": pd.to_numeric(series, errors="coerce")})
    if store_series is not None:
        source["store"] = store_series
    source = source.dropna(subset=["metric"])

    def make_item(percentile):
        threshold = float(source["metric"].quantile(percentile / 100))
        below = source[source["metric"] <= threshold]
        count = int(below["store"].nunique()) if "store" in below.columns else int(len(below))
        return {
            "percentile": percentile,
            "threshold": threshold,
            "count": count,
        }

    return {"p25": make_item(25), "p85": make_item(85), "custom": make_item(custom_percentile)}


def split_by_network(df):
    if TS_COL not in df.columns:
        return [("All", df)]
    return [(str(name), group.copy()) for name, group in sorted(df.groupby(TS_COL, dropna=False), key=lambda item: str(item[0]))]


def _frange(start, stop, step):
    values = []
    value = start
    while value < stop:
        values.append(value)
        value += step
    return values


def _clean_number(value):
    value = float(value)
    if value.is_integer():
        return int(value)
    return round(value, 6)


def calculate_relationship_stats(df, metric, relationship_columns):
    rows = []
    metric_values = pd.to_numeric(df[metric], errors="coerce")
    for column in relationship_columns:
        if column not in df.columns:
            continue
        comparison = pd.to_numeric(df[column], errors="coerce")
        pair = pd.DataFrame({"metric": metric_values, "comparison": comparison}).dropna()
        if len(pair) < 2:
            pearson = None
            spearman = None
        else:
            pearson = float(pair["metric"].corr(pair["comparison"], method="pearson"))
            spearman = float(pair["metric"].corr(pair["comparison"], method="spearman"))
        rows.append({"comparison": column, "pearson": pearson, "spearman": spearman, "rows_used": int(len(pair))})
    return pd.DataFrame(rows, columns=["comparison", "pearson", "spearman", "rows_used"])


def _apply_sidebar_filters(df):
    _require_streamlit()
    filtered = df.copy()
    for column in FILTER_COLUMNS:
        if column not in filtered.columns:
            continue
        options = sorted(filtered[column].dropna().unique().tolist())
        format_func = format_week_label if column == WEEK_COL else str
        selected = st.sidebar.multiselect(column, options, format_func=format_func)
        if selected:
            filtered = filtered[filtered[column].isin(selected)]
    return filtered


def _problem_rows(df):
    problem_mask = pd.Series(False, index=df.index)
    for column in PROBLEM_FLAG_COLUMNS:
        if column == "has_poteri_match" and column in df.columns:
            problem_mask |= ~df[column].fillna(False)
        elif column in df.columns:
            problem_mask |= df[column].fillna(False)
    return df[problem_mask]


def _load_run_dataframe(run_dir):
    final_path = run_file_paths(run_dir)["final"]

    if not final_path.exists():
        st.error(f"Missing final file: {final_path}")
        return None
    return _read_excel_cached(str(final_path), final_path.stat().st_mtime_ns)


def _render_quality_cards(filtered, numeric_metric):
    st.subheader("Data quality")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Rows", len(filtered))

    no_poteri = int((~filtered["has_poteri_match"].fillna(False)).sum()) if "has_poteri_match" in filtered.columns else 0
    missing_key = int(filtered["has_missing_key"].fillna(False).sum()) if "has_missing_key" in filtered.columns else 0

    col2.metric("No poteri", no_poteri)
    col3.metric("Missing keys", missing_key)
    col4.metric("Metric nulls", int(numeric_metric.isna().sum()))
    col5.metric("Metric zeros", int(numeric_metric.eq(0).sum()))


def _render_audit_tab(run_dir, filtered, numeric_metric):
    _render_quality_cards(filtered, numeric_metric)
    paths = run_file_paths(run_dir)
    with st.expander("Opened files", expanded=False):
        st.write(f"Final: `{paths['final']}`")
        st.write(f"Raw: `{paths['raw']}`")

    diagnostics_path = run_dir / "merge_diagnostics.md"
    if diagnostics_path.exists():
        st.subheader("Merge diagnostics")
        st.markdown(diagnostics_path.read_text(encoding="utf-8"))
    else:
        st.warning("merge_diagnostics.md not found for this run.")


def _render_metric_analysis_tab(filtered, metric, numeric_metric):
    st.subheader("Metric analysis")
    summary = metric_summary(numeric_metric)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Count", summary["count"])
    c2.metric("Mean", _format_number(summary["mean"]))
    c3.metric("Median", _format_number(summary["median"]))
    c4.metric("P85", _format_number(summary["p85"]))

    stats_df = pd.DataFrame([summary])
    st.dataframe(stats_df, use_container_width=True)

    valid_metric = numeric_metric.dropna()
    default_width = 1.0
    if not valid_metric.empty:
        span = float(valid_metric.max() - valid_metric.min())
        default_width = max(span / 30, 1.0)
    bin_width = st.number_input("Bin width", min_value=0.000001, value=float(default_width), step=float(default_width))
    custom_percentile = st.slider("Custom percentile", min_value=1, max_value=99, value=50)
    store_series = filtered[FACTORY_COL] if FACTORY_COL in filtered.columns else None
    bin_table = build_bin_table_by_width(numeric_metric, bin_width=bin_width, store_series=store_series)
    percentile_counts = percentile_store_counts(numeric_metric, custom_percentile=custom_percentile, store_series=store_series)
    chart_data = sample_for_plot(filtered.assign(_metric=numeric_metric))

    pc1, pc2, pc3 = st.columns(3)
    pc1.metric(
        "Stores <= P25",
        percentile_counts["p25"]["count"],
        _format_number(percentile_counts["p25"]["threshold"]),
    )
    pc2.metric(
        "Stores <= P85",
        percentile_counts["p85"]["count"],
        _format_number(percentile_counts["p85"]["threshold"]),
    )
    pc3.metric(
        f"Stores <= P{custom_percentile}",
        percentile_counts["custom"]["count"],
        _format_number(percentile_counts["custom"]["threshold"]),
    )

    try:
        import plotly.express as px

        fig = px.bar(
            bin_table,
            x="bin_start",
            y="store_count" if "store_count" in bin_table.columns else "count",
            hover_data=["bin", "share"],
            title=f"Fixed-width bin distribution: {metric}",
        )
        fig.add_vline(x=percentile_counts["p25"]["threshold"], line_color="green", line_width=3)
        fig.add_vline(x=percentile_counts["p85"]["threshold"], line_color="red", line_width=3)
        fig.add_vline(x=percentile_counts["custom"]["threshold"], line_color="orange", line_width=3, line_dash="dash")
        st.plotly_chart(fig, use_container_width=True)
        st.plotly_chart(px.box(chart_data, y="_metric", points=False, title=f"Boxplot: {metric}"), use_container_width=True)
    except ModuleNotFoundError:
        st.warning("Plotly is not installed; showing a basic Streamlit chart.")
        st.bar_chart(bin_table.set_index("bin")["count"] if not bin_table.empty else bin_table)
    st.subheader("Bin table")
    st.dataframe(bin_table, use_container_width=True)


def _render_group_comparison_tab(filtered, numeric_metric):
    st.subheader("Group comparison")
    chart_data = filtered.assign(_metric=numeric_metric)
    group_options = [column for column in GROUP_COLUMNS if column in filtered.columns]
    if not group_options:
        st.info("No group columns found.")
        return

    group_col = st.selectbox("Group by", group_options)
    grouped = (
        chart_data.groupby(group_col, dropna=False)["_metric"]
        .agg(count="count", mean="mean", median="median", min="min", max="max", p85=lambda value: value.quantile(0.85), total="sum")
        .reset_index()
        .sort_values("count", ascending=False)
    )
    st.dataframe(grouped.head(1000), use_container_width=True)


def _render_relationships_tab(filtered, metric, numeric_metric):
    st.subheader("Poteri relationship analysis")
    available = [column for column in RELATIONSHIP_COLUMNS if column in filtered.columns]
    if not available:
        st.info("No poteri numeric columns found for relationship analysis.")
        return

    try:
        import plotly.express as px
    except ModuleNotFoundError:
        st.warning("Plotly is not installed; relationship scatter plots are unavailable.")
        return

    for network_name, network_df in split_by_network(filtered.assign(_metric=numeric_metric)):
        st.markdown(f"### {network_name}")
        stats = calculate_relationship_stats(network_df, metric, available)
        st.dataframe(stats, use_container_width=True)

        chart_df = sample_for_plot(network_df)
        for column in available:
            st.plotly_chart(
                px.scatter(chart_df, x="_metric", y=column, opacity=0.45, title=f"{network_name}: {metric} vs {column}"),
                use_container_width=True,
            )


def _render_problem_rows_tab(filtered):
    st.subheader("Problem rows")
    problems = _problem_rows(filtered)
    st.caption("Rows without poteri match, rows with missing keys, duplicate-key flags, and outlier flags when present.")
    st.download_button(
        "Download problem rows CSV",
        data=problems.to_csv(index=False).encode("utf-8-sig"),
        file_name="problem_rows.csv",
        mime="text/csv",
        disabled=problems.empty,
    )
    st.dataframe(problems.head(1000), use_container_width=True)


def _format_number(value):
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:,.2f}"


def main():
    _require_streamlit()
    st.set_page_config(page_title="KIR Dashboard", layout="wide")
    st.title("KIR Dashboard")

    run_dirs = list_run_dirs()
    if not run_dirs:
        st.warning("No run directories found in data/.")
        return

    run_dir = st.sidebar.selectbox("Run", run_dirs, format_func=lambda path: path.name)
    df = _load_run_dataframe(run_dir)
    if df is None:
        return

    metrics = sort_metric_columns(get_numeric_metric_columns(df))
    if not metrics:
        st.error("No numeric metric columns found.")
        return

    metric = st.sidebar.selectbox("Metric", metrics)
    filtered = _apply_sidebar_filters(df)
    numeric_metric = pd.to_numeric(filtered[metric], errors="coerce")

    screen = st.radio("Dashboard screen", DASHBOARD_SCREENS, horizontal=True)
    if screen == "Overview":
        _render_audit_tab(run_dir, filtered, numeric_metric)
    elif screen == "Metric analysis":
        _render_metric_analysis_tab(filtered, metric, numeric_metric)
    elif screen == "Group comparison":
        _render_group_comparison_tab(filtered, numeric_metric)
    elif screen == "Poteri relationships":
        _render_relationships_tab(filtered, metric, numeric_metric)
    elif screen == "Problem rows":
        _render_problem_rows_tab(filtered)
    elif screen == "Data":
        st.subheader("Filtered data sample")
        st.dataframe(filtered.head(1000), use_container_width=True)


if __name__ == "__main__":
    main()
