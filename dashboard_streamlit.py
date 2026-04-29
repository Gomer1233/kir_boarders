from pathlib import Path

import pandas as pd

try:
    import streamlit as st
except ModuleNotFoundError:
    st = None


DATA_DIR = Path("data")
FILTER_COLUMNS = ["?????????", "??", "?????????", "has_poteri_match", "quality_status"]
GROUP_COLUMNS = ["??", "?????????", "?????"]
PROBLEM_FLAG_COLUMNS = ["has_poteri_match", "has_missing_key", "has_duplicate_kir_key", "has_duplicate_poteri_key"]


def _require_streamlit():
    if st is None:
        raise RuntimeError("Streamlit is not installed. Install dependencies from requirements.txt.")


def get_numeric_metric_columns(df):
    return df.select_dtypes(include="number").columns.tolist()


def sort_metric_columns(columns):
    kir = sorted([column for column in columns if str(column).startswith("???-")])
    other = sorted([column for column in columns if column not in kir])
    return kir + other


def list_run_dirs():
    if not DATA_DIR.exists():
        return []
    return sorted(
        [path for path in DATA_DIR.iterdir() if path.is_dir() and path.name.startswith("run_")],
        reverse=True,
    )


def _apply_sidebar_filters(df):
    _require_streamlit()
    filtered = df.copy()
    for column in FILTER_COLUMNS:
        if column not in filtered.columns:
            continue
        options = sorted(filtered[column].dropna().unique().tolist())
        selected = st.sidebar.multiselect(column, options)
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
    final_path = run_dir / "final_clean_data.xlsx"
    raw_path = run_dir / "merged_raw.xlsx"
    st.sidebar.write(f"Final: `{final_path}`")
    st.sidebar.write(f"Raw: `{raw_path}`")

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


def _render_distribution_tab(filtered, metric, numeric_metric):
    st.subheader("Metric distribution")
    chart_data = filtered.assign(_metric=numeric_metric)
    try:
        import plotly.express as px

        st.plotly_chart(px.histogram(chart_data, x="_metric", nbins=80, title=f"Distribution: {metric}"), use_container_width=True)
        st.plotly_chart(px.box(chart_data, y="_metric", points=False, title=f"Boxplot: {metric}"), use_container_width=True)
    except ModuleNotFoundError:
        st.warning("Plotly is not installed; showing a basic Streamlit chart.")
        st.bar_chart(numeric_metric.dropna().value_counts().sort_index())


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
        .agg(count="count", mean="mean", median="median", min="min", max="max")
        .reset_index()
        .sort_values("count", ascending=False)
    )
    st.dataframe(grouped.head(1000), use_container_width=True)


def _render_audit_tab(run_dir, filtered, numeric_metric):
    _render_quality_cards(filtered, numeric_metric)
    diagnostics_path = run_dir / "merge_diagnostics.md"
    if diagnostics_path.exists():
        st.subheader("Merge diagnostics")
        st.markdown(diagnostics_path.read_text(encoding="utf-8"))
    else:
        st.warning("merge_diagnostics.md not found for this run.")


def _render_problem_rows_tab(filtered):
    st.subheader("Problem rows")
    problems = _problem_rows(filtered)
    st.caption("Rows without poteri match, rows with missing keys, and duplicate-key flags.")
    st.dataframe(problems.head(1000), use_container_width=True)


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

    audit_tab, distribution_tab, group_tab, problems_tab, data_tab = st.tabs(
        ["Audit", "Distribution", "Group comparison", "Problem rows", "Data"]
    )
    with audit_tab:
        _render_audit_tab(run_dir, filtered, numeric_metric)
    with distribution_tab:
        _render_distribution_tab(filtered, metric, numeric_metric)
    with group_tab:
        _render_group_comparison_tab(filtered, numeric_metric)
    with problems_tab:
        _render_problem_rows_tab(filtered)
    with data_tab:
        st.subheader("Filtered data sample")
        st.dataframe(filtered.head(1000), use_container_width=True)


if __name__ == "__main__":
    main()
