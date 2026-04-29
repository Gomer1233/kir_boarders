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
    return pd.read_excel(final_path)


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

    bins = st.slider("Number of bins", min_value=5, max_value=100, value=30, step=5)
    bin_table = build_bin_table(numeric_metric, bins=bins)
    chart_data = filtered.assign(_metric=numeric_metric)
    try:
        import plotly.express as px

        st.plotly_chart(px.histogram(chart_data, x="_metric", nbins=bins, title=f"Bin distribution: {metric}"), use_container_width=True)
        st.plotly_chart(px.box(chart_data, y="_metric", points=False, title=f"Boxplot: {metric}"), use_container_width=True)
    except ModuleNotFoundError:
        st.warning("Plotly is not installed; showing a basic Streamlit chart.")
        st.bar_chart(bin_table.set_index("bin")["count"])
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

    stats = calculate_relationship_stats(filtered.assign(_metric=numeric_metric), metric, available)
    st.dataframe(stats, use_container_width=True)

    try:
        import plotly.express as px
    except ModuleNotFoundError:
        st.warning("Plotly is not installed; relationship scatter plots are unavailable.")
        return

    chart_df = filtered.assign(_metric=numeric_metric)
    for column in available:
        st.plotly_chart(
            px.scatter(chart_df, x="_metric", y=column, opacity=0.45, title=f"{metric} vs {column}"),
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

    audit_tab, metric_tab, group_tab, relationships_tab, problems_tab, data_tab = st.tabs(
        ["Overview", "Metric analysis", "Group comparison", "Poteri relationships", "Problem rows", "Data"]
    )
    with audit_tab:
        _render_audit_tab(run_dir, filtered, numeric_metric)
    with metric_tab:
        _render_metric_analysis_tab(filtered, metric, numeric_metric)
    with group_tab:
        _render_group_comparison_tab(filtered, numeric_metric)
    with relationships_tab:
        _render_relationships_tab(filtered, metric, numeric_metric)
    with problems_tab:
        _render_problem_rows_tab(filtered)
    with data_tab:
        st.subheader("Filtered data sample")
        st.dataframe(filtered.head(1000), use_container_width=True)


if __name__ == "__main__":
    main()
