from pathlib import Path

import pandas as pd

try:
    import streamlit as st
except ModuleNotFoundError:
    st = None


DATA_DIR = Path("data")


def _require_streamlit():
    if st is None:
        raise RuntimeError("Streamlit is not installed. Install dependencies from requirements.txt.")


def get_numeric_metric_columns(df):
    return df.select_dtypes(include="number").columns.tolist()


def sort_metric_columns(columns):
    kir = sorted([column for column in columns if str(column).startswith("КИР-")])
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
    for column in ["НеделяГод", "ТС", "Категория", "Завод", "has_poteri_match", "quality_status"]:
        if column not in filtered.columns:
            continue
        options = sorted(filtered[column].dropna().unique().tolist())
        selected = st.sidebar.multiselect(column, options)
        if selected:
            filtered = filtered[filtered[column].isin(selected)]
    return filtered


def _problem_rows(df):
    problem_mask = pd.Series(False, index=df.index)
    for column in ["has_poteri_match", "has_missing_key", "has_duplicate_kir_key", "has_duplicate_poteri_key"]:
        if column == "has_poteri_match" and column in df.columns:
            problem_mask |= ~df[column].fillna(False)
        elif column in df.columns:
            problem_mask |= df[column].fillna(False)
    return df[problem_mask]


def main():
    _require_streamlit()
    st.set_page_config(page_title="KIR Dashboard", layout="wide")
    st.title("KIR Dashboard")

    run_dirs = list_run_dirs()
    if not run_dirs:
        st.warning("No run directories found in data/.")
        return

    run_dir = st.sidebar.selectbox("Run", run_dirs, format_func=lambda path: path.name)
    final_path = run_dir / "final_clean_data.xlsx"
    raw_path = run_dir / "merged_raw.xlsx"

    st.sidebar.write(f"Final: `{final_path}`")
    st.sidebar.write(f"Raw: `{raw_path}`")

    if not final_path.exists():
        st.error(f"Missing final file: {final_path}")
        return

    df = pd.read_excel(final_path)
    metrics = sort_metric_columns(get_numeric_metric_columns(df))
    if not metrics:
        st.error("No numeric metric columns found.")
        return

    metric = st.sidebar.selectbox("Metric", metrics)
    filtered = _apply_sidebar_filters(df)
    numeric_metric = pd.to_numeric(filtered[metric], errors="coerce")

    st.subheader("Data quality")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rows", len(filtered))
    if "has_poteri_match" in filtered.columns:
        no_poteri = int((~filtered["has_poteri_match"].fillna(False)).sum())
    else:
        no_poteri = 0
    col2.metric("No poteri", no_poteri)
    col3.metric("Metric nulls", int(numeric_metric.isna().sum()))
    col4.metric("Metric zeros", int(numeric_metric.eq(0).sum()))

    st.subheader("Metric distribution")
    chart_data = filtered.assign(_metric=numeric_metric)
    try:
        import plotly.express as px

        st.plotly_chart(px.histogram(chart_data, x="_metric"), use_container_width=True)
        st.plotly_chart(px.box(chart_data, y="_metric"), use_container_width=True)
    except ModuleNotFoundError:
        st.warning("Plotly is not installed; showing a basic Streamlit chart.")
        st.bar_chart(numeric_metric.dropna().value_counts().sort_index())

    st.subheader("Group comparison")
    group_options = [column for column in ["ТС", "Категория", "Завод"] if column in filtered.columns]
    if group_options:
        group_col = st.selectbox("Group by", group_options)
        grouped = (
            chart_data.groupby(group_col, dropna=False)["_metric"]
            .agg(count="count", mean="mean", median="median", min="min", max="max")
            .reset_index()
        )
        st.dataframe(grouped, use_container_width=True)

    st.subheader("Problem rows")
    st.dataframe(_problem_rows(filtered).head(1000), use_container_width=True)


if __name__ == "__main__":
    main()
