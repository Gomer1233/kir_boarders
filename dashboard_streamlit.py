from pathlib import Path
from html import escape
import json
import math
import os
import re

import pandas as pd

from main_final_v3 import load_config
from scripts.kir_percentages import (
    PERCENT_BASE_COLUMNS,
    add_kir_percentage_columns,
    kir_metric_columns,
    kir_percentage_summary,
    kir_percentage_columns,
    percentage_column_name,
)
from scripts.project_registry import create_project, list_projects, sanitize_project_name
from scripts.upload_runner import (
    KIR_SOURCE_NAME,
    POTERI_SOURCE_NAME,
    UPLOAD_MANIFEST_NAME,
    run_project_routes,
    save_uploaded_route_files,
)

try:
    import streamlit as st
except ModuleNotFoundError:
    st = None


DATA_DIR = Path("data")
DATA_PROJECTS_DIR = DATA_DIR / "projects"
EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
WEEK_COL = "\u041d\u0435\u0434\u0435\u043b\u044f\u0413\u043e\u0434"
TS_COL = "\u0422\u0421"
CATEGORY_COL = "\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f"
FACTORY_COL = "\u0417\u0430\u0432\u043e\u0434"
WRITEOFFS_COL = "\u0421\u043f\u0438\u0441\u0430\u043d\u0438\u044f"
REVENUE_COL = "\u0412\u044b\u0440\u0443\u0447\u043a\u0430"
FREE_STOCK_COL = "\u0421\u0432\u043e\u0431\u043e\u0434\u043d\u044b\u0439 \u0422\u0417"

FILTER_COLUMNS = [WEEK_COL, TS_COL, CATEGORY_COL, "has_poteri_match", "quality_status"]
GROUP_COLUMNS = [TS_COL, CATEGORY_COL]
RELATIONSHIP_COLUMNS = [WRITEOFFS_COL, REVENUE_COL, FREE_STOCK_COL]
PROBLEM_FLAG_COLUMNS = ["has_poteri_match", "has_missing_key", "has_duplicate_kir_key", "has_duplicate_poteri_key"]
KIR_SUMMARY_AMOUNT_COLUMNS = ["Сумма КИР", "Сумма списаний", "Сумма выручки", "Сумма свободного ТЗ"]
RELATIONSHIP_HEADING_COLORS = {
    WRITEOFFS_COL: {"accent": "#fb923c", "background": "rgba(251, 146, 60, 0.18)"},
    REVENUE_COL: {"accent": "#4ade80", "background": "rgba(74, 222, 128, 0.16)"},
    FREE_STOCK_COL: {"accent": "#60a5fa", "background": "rgba(96, 165, 250, 0.18)"},
}
DASHBOARD_SCREENS = [
    "1. Корреляции",
    "2. Проценты КИР",
    "3. Распределение показателя",
    "Сравнение групп",
    "Качество данных",
    "Проблемные строки",
    "Данные",
]


def _require_streamlit():
    if st is None:
        raise RuntimeError("Streamlit is not installed. Install dependencies from requirements.txt.")


def get_numeric_metric_columns(df):
    percentage_columns = set(kir_percentage_columns(df))
    return [column for column in df.select_dtypes(include="number").columns.tolist() if column not in percentage_columns]


def sort_metric_columns(columns):
    kir = sorted([column for column in columns if str(column).startswith("\u041a\u0418\u0420-")])
    other = sorted([column for column in columns if column not in kir])
    return kir + other


def list_project_run_dirs(project_name, projects_dir=DATA_PROJECTS_DIR):
    runs_dir = Path(projects_dir) / str(project_name) / "runs"
    if not runs_dir.exists():
        return []
    return sorted(
        [path for path in runs_dir.iterdir() if path.is_dir() and path.name.startswith("run_")],
        reverse=True,
    )


def list_legacy_run_dirs(data_dir=DATA_DIR):
    data_path = Path(data_dir)
    if not data_path.exists():
        return []
    return sorted(
        [
            path
            for path in data_path.iterdir()
            if path.is_dir() and path.name.startswith("run_") and (path / "final_clean_data.xlsx").exists()
        ],
        reverse=True,
    )


def latest_project_run_name(project_name, projects_dir=DATA_PROJECTS_DIR):
    runs = list_project_run_dirs(project_name, projects_dir=projects_dir)
    if not runs:
        return None
    return runs[0].name


def load_upload_manifest(project_name, route_name, projects_dir=DATA_PROJECTS_DIR):
    manifest_path = Path(projects_dir) / str(project_name) / "uploads" / route_name / UPLOAD_MANIFEST_NAME
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def project_route_uploads_exist(project_name, route_name, projects_dir=DATA_PROJECTS_DIR):
    upload_dir = Path(projects_dir) / str(project_name) / "uploads" / route_name
    return (upload_dir / KIR_SOURCE_NAME).exists() and (upload_dir / POTERI_SOURCE_NAME).exists()


def project_run_lock_path(project_name, projects_dir=DATA_PROJECTS_DIR):
    return Path(projects_dir) / str(project_name) / ".pipeline.lock"


def project_run_lock_status(project_name, projects_dir=DATA_PROJECTS_DIR):
    lock_path = project_run_lock_path(project_name, projects_dir=projects_dir)
    return {"locked": lock_path.exists(), "path": lock_path}


def acquire_project_run_lock(project_name, projects_dir=DATA_PROJECTS_DIR):
    lock_path = project_run_lock_path(project_name, projects_dir=projects_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write("Pipeline run is active.\n")
    return True


def release_project_run_lock(project_name, projects_dir=DATA_PROJECTS_DIR):
    lock_path = project_run_lock_path(project_name, projects_dir=projects_dir)
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def make_pipeline_run_request(project_name, routes, open_route=None):
    route_list = list(routes)
    if open_route not in route_list:
        open_route = route_list[0] if route_list else None
    return {"project": project_name, "routes": route_list, "open_route": open_route}


def queue_pipeline_run(project_name, routes, open_route=None):
    st.session_state["pending_pipeline_run"] = make_pipeline_run_request(project_name, routes, open_route=open_route)
    st.session_state["pipeline_running"] = True


def select_run_result_to_open(results, preferred_route):
    if not results:
        return None
    for result in results:
        if result.get("route") == preferred_route:
            return result
    return results[-1]


def allowed_upload_extensions():
    return ["xlsx"]


def should_render_upload_widgets(project_is_running):
    return not project_is_running


def project_select_options(projects):
    return sorted(projects)


def normalize_new_project_input(value):
    return sanitize_project_name(value)


def routes_for_ui_mode(mode):
    route_modes = {
        "route_1": ["route_1"],
        "route_2": ["route_2"],
        "both": ["route_1", "route_2"],
    }
    if mode not in route_modes:
        raise ValueError(f"Unsupported route mode: {mode}")
    return route_modes[mode]


def route_label(route_name):
    labels = {
        "route_1": "Route 1: Магазины и Категории",
        "route_2": "Route 2: Магазины",
        "both": "Both routes",
    }
    return labels.get(route_name, route_name)


def format_running_message(project_name, routes):
    route_name = "both" if len(routes) > 1 else routes[0]
    return f"Running {route_label(route_name)} for project {project_name}..."


def pipeline_progress_value(completed_steps, total_steps, start=10):
    if total_steps <= 0:
        return start
    value = start + int(completed_steps / total_steps * (99 - start))
    return min(99, max(start, value))


def pipeline_status_text(status):
    texts = {
        "active": "\u041f\u0440\u043e\u0433\u043e\u043d \u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442\u0441\u044f. \u041d\u0435 \u0437\u0430\u043a\u0440\u044b\u0432\u0430\u0439\u0442\u0435 \u0432\u043a\u043b\u0430\u0434\u043a\u0443 \u0438 \u043d\u0435 \u043c\u0435\u043d\u044f\u0439\u0442\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0434\u043e \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0438\u044f.",
        "already_running": "\u041f\u0440\u043e\u0433\u043e\u043d \u0443\u0436\u0435 \u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442\u0441\u044f \u0434\u043b\u044f \u044d\u0442\u043e\u0433\u043e \u043f\u0440\u043e\u0435\u043a\u0442\u0430. \u0414\u043e\u0436\u0434\u0438\u0442\u0435\u0441\u044c \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0438\u044f \u0442\u0435\u043a\u0443\u0449\u0435\u0433\u043e \u0437\u0430\u043f\u0443\u0441\u043a\u0430.",
        "other_project": "\u041f\u0440\u043e\u0433\u043e\u043d \u0437\u0430\u043f\u0443\u0449\u0435\u043d \u0434\u043b\u044f \u0434\u0440\u0443\u0433\u043e\u0433\u043e \u043f\u0440\u043e\u0435\u043a\u0442\u0430. \u0414\u043e\u0436\u0434\u0438\u0442\u0435\u0441\u044c \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0438\u044f \u0442\u0435\u043a\u0443\u0449\u0435\u0433\u043e \u0437\u0430\u043f\u0443\u0441\u043a\u0430.",
        "stop_help": "\u0412 MVP \u043f\u0440\u043e\u0433\u043e\u043d \u043d\u0435\u043b\u044c\u0437\u044f \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c \u0438\u0437 UI. \u0414\u043e\u0436\u0434\u0438\u0442\u0435\u0441\u044c \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0438\u044f \u0438\u043b\u0438 \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u0435 Streamlit \u0432 \u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b\u0435.",
        "stop_button": "\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c \u043f\u0440\u043e\u0433\u043e\u043d",
        "open_dashboard_caption": "\u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u0434\u0430\u0448\u0431\u043e\u0440\u0434 \u0442\u043e\u043b\u044c\u043a\u043e \u043f\u043e\u0441\u043b\u0435 \u0433\u043e\u0442\u043e\u0432\u043e\u0433\u043e \u043f\u0440\u043e\u0433\u043e\u043d\u0430. \u0412\u044b\u0431\u043e\u0440 run-\u0430 \u0441\u0430\u043c \u043f\u043e \u0441\u0435\u0431\u0435 \u0434\u0430\u043d\u043d\u044b\u0435 \u043d\u0435 \u0437\u0430\u0433\u0440\u0443\u0436\u0430\u0435\u0442.",
        "no_ready_runs": "\u0414\u043b\u044f \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u043e\u0433\u043e \u043f\u0440\u043e\u0435\u043a\u0442\u0430 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442 \u0433\u043e\u0442\u043e\u0432\u044b\u0445 \u043f\u0440\u043e\u0433\u043e\u043d\u043e\u0432.",
        "open_dashboard_first": "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043f\u0440\u043e\u0435\u043a\u0442, \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u0435 \u0444\u0430\u0439\u043b\u044b, \u0432\u044b\u043f\u043e\u043b\u043d\u0438\u0442\u0435 \u043f\u0440\u043e\u0433\u043e\u043d \u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 Open dashboard \u0434\u043b\u044f \u0433\u043e\u0442\u043e\u0432\u043e\u0433\u043e run-\u0430.",
        "open_current_project": "\u0412\u044b\u0431\u0440\u0430\u043d \u0434\u0440\u0443\u0433\u043e\u0439 \u043f\u0440\u043e\u0435\u043a\u0442. \u041d\u0430\u0436\u043c\u0438\u0442\u0435 Open dashboard \u0434\u043b\u044f run-\u0430 \u0442\u0435\u043a\u0443\u0449\u0435\u0433\u043e \u043f\u0440\u043e\u0435\u043a\u0442\u0430.",
        "preparing": "\u0413\u043e\u0442\u043e\u0432\u043b\u044e \u0437\u0430\u043f\u0443\u0441\u043a \u043f\u0430\u0439\u043f\u043b\u0430\u0439\u043d\u0430...",
        "checking_uploads": "\u041f\u0440\u043e\u0432\u0435\u0440\u044f\u044e \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u043d\u044b\u0435 \u0444\u0430\u0439\u043b\u044b...",
        "saving_uploads": "\u0421\u043e\u0445\u0440\u0430\u043d\u044f\u044e \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u044b\u0435 \u0444\u0430\u0439\u043b\u044b...",
        "upload_disabled": "\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0444\u0430\u0439\u043b\u043e\u0432 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430, \u043f\u043e\u043a\u0430 \u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442\u0441\u044f \u043f\u0440\u043e\u0433\u043e\u043d.",
        "stale_lock": "\u041d\u0430\u0439\u0434\u0435\u043d lock-\u0444\u0430\u0439\u043b \u043f\u0440\u0435\u0434\u044b\u0434\u0443\u0449\u0435\u0433\u043e \u043f\u0440\u043e\u0433\u043e\u043d\u0430. \u0415\u0441\u043b\u0438 \u0441\u0435\u0439\u0447\u0430\u0441 \u043f\u0440\u043e\u0433\u043e\u043d \u043d\u0435 \u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442\u0441\u044f, \u0441\u0431\u0440\u043e\u0441\u044c\u0442\u0435 lock, \u0447\u0442\u043e\u0431\u044b \u0441\u043d\u043e\u0432\u0430 \u0432\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0443 \u0444\u0430\u0439\u043b\u043e\u0432.",
        "reset_lock_button": "\u0421\u0431\u0440\u043e\u0441\u0438\u0442\u044c \u0437\u0430\u0432\u0438\u0441\u0448\u0438\u0439 lock",
        "finished": "\u041f\u0440\u043e\u0433\u043e\u043d \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d.",
        "open_after_both_label": "\u0427\u0442\u043e \u043e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u043e\u0441\u043b\u0435 Run Both routes:",
        "open_after_both_help": "\u041d\u0435 \u0444\u0438\u043b\u044c\u0442\u0440: \u0432\u043b\u0438\u044f\u0435\u0442 \u0442\u043e\u043b\u044c\u043a\u043e \u043d\u0430 \u043a\u043d\u043e\u043f\u043a\u0443 Run Both routes.",
    }
    return texts[status]


def format_run_result(result):
    paths = result.get("paths", {})
    final_path = paths.get("final_clean") or paths.get("final") or "unknown"
    raw_path = paths.get("merged_raw") or paths.get("raw") or "unknown"
    lines = [
        "Файлы успешно созданы, перехожу к сборке дашборда.",
        f"Route: {route_label(result.get('route', 'unknown'))}",
        f"Run folder: {result.get('run_dir', 'unknown')}",
        f"Final clean data: {final_path}",
        f"Merged raw: {raw_path}",
    ]
    return "\n".join(lines)


def run_file_paths(run_dir):
    run_dir = Path(run_dir)
    return {
        "final": run_dir / "final_clean_data.xlsx",
        "raw": run_dir / "merged_raw.xlsx",
    }


def download_file_name(path, run_dir):
    return f"{Path(run_dir).name}_{Path(path).name}"


def dashboard_run_label(run_dir):
    return Path(run_dir).name


def read_file_for_download(path, mtime_ns):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Download file not found: {path}")
    return path.read_bytes()


if st is not None:
    read_file_for_download = st.cache_data(show_spinner=False)(read_file_for_download)


def _read_excel_cached(path, mtime_ns):
    return pd.read_excel(path)


if st is not None:
    _read_excel_cached = st.cache_data(show_spinner=False)(_read_excel_cached)


def dataframe_cache_key(path, mtime_ns):
    return f"{Path(path).resolve()}:{mtime_ns}"


def read_final_data_with_progress(path, mtime_ns, read_func=None, progress_factory=None, dataframe_cache=None):
    cache_key = dataframe_cache_key(path, mtime_ns)
    if dataframe_cache is not None and cache_key in dataframe_cache:
        return dataframe_cache[cache_key]

    read_func = read_func or _read_excel_cached
    progress_factory = progress_factory or st.progress
    progress_bar = progress_factory(0, text="Starting dashboard load...")
    progress_bar.progress(10, text="Preparing final_clean_data.xlsx...")
    progress_bar.progress(35, text="Reading Excel file. First load can take a while...")
    df = read_func(str(path), mtime_ns)
    progress_bar.progress(90, text="Preparing dashboard data...")
    progress_bar.progress(100, text="Dashboard data loaded.")
    progress_bar.empty()
    if dataframe_cache is not None:
        dataframe_cache.clear()
        dataframe_cache[cache_key] = df
    return df


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
        return f"Y{compact_match.group(1)} W{int(compact_match.group(2)):02d}"

    dotted_match = re.fullmatch(r"(\d{4})[./-](\d{1,2})", text)
    if dotted_match:
        return f"Y{dotted_match.group(1)} W{int(dotted_match.group(2)):02d}"

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
            "zero_count": 0,
            "zero_share": 0,
            "missing_share": 1 if total_count else 0,
        }
    zero_count = int(valid.eq(0).sum())
    return {
        "count": int(valid_count),
        "min": float(valid.min()),
        "max": float(valid.max()),
        "mean": float(valid.mean()),
        "median": float(valid.median()),
        "p25": float(valid.quantile(0.25)),
        "p85": float(valid.quantile(0.85)),
        "zero_count": zero_count,
        "zero_share": float(zero_count / valid_count),
        "missing_share": float(numeric.isna().sum() / total_count) if total_count else 0,
    }


def filter_zero_metric_values(df, numeric_metric):
    numeric = pd.to_numeric(numeric_metric, errors="coerce")
    mask = ~numeric.eq(0)
    return df.loc[mask].copy(), numeric.loc[mask]


def filter_options_for_column(df, column):
    if column not in df.columns:
        return []
    return df[column].dropna().unique().tolist()


def filter_label(column):
    if column == WEEK_COL:
        return "\u0413\u043e\u0434 \u0438 \u041d\u0435\u0434\u0435\u043b\u044f"
    return str(column)


def apply_filter_values(df, filter_values):
    filtered = df.copy()
    for column, selected in filter_values.items():
        if column in filtered.columns and selected:
            filtered = filtered[filtered[column].isin(selected)]
    return filtered


def _compact_context_values(values, max_items=4):
    clean_values = [str(value) for value in values if pd.notna(value)]
    if not clean_values:
        return "\u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445"
    if len(clean_values) <= max_items:
        return ", ".join(clean_values)
    visible = ", ".join(clean_values[:max_items])
    return f"{visible} +{len(clean_values) - max_items}"


def metric_analysis_context(filtered, filter_values, metric=None):
    filter_values = filter_values or {}
    has_category = CATEGORY_COL in filtered.columns
    context = {
        "metric": metric,
        "scope": "\u041c\u0430\u0433\u0430\u0437\u0438\u043d\u044b \u0438 \u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u0438" if has_category else "\u041c\u0430\u0433\u0430\u0437\u0438\u043d\u044b",
        "categories": None,
        "networks": None,
    }
    if has_category:
        selected_categories = filter_values.get(CATEGORY_COL) or []
        if selected_categories:
            context["categories"] = _compact_context_values(selected_categories)
        else:
            category_count = int(filtered[CATEGORY_COL].dropna().nunique())
            context["categories"] = f"\u0412\u0441\u0435 \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u0438 ({category_count})"
    if TS_COL in filtered.columns:
        selected_networks = filter_values.get(TS_COL) or []
        network_values = selected_networks if selected_networks else filtered[TS_COL].dropna().unique().tolist()
        context["networks"] = _compact_context_values(network_values, max_items=3)
    return context


def render_metric_analysis_context_html(context):
    chips = []
    if context.get("metric"):
        chips.append(("\u041c\u0435\u0442\u0440\u0438\u043a\u0430", context["metric"]))
    chips.append(("\u0420\u0430\u0437\u0440\u0435\u0437", context.get("scope")))
    if context.get("categories"):
        chips.append(("\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u0438", context["categories"]))
    if context.get("networks"):
        chips.append(("\u0421\u0435\u0442\u044c", context["networks"]))
    chip_html_parts = []
    for label, value in chips:
        label_text = escape(str(label))
        value_text = escape(str(value))
        value_style = "color:#f8fafc;font-size:0.88rem;font-weight:760;"
        if label == "\u041c\u0435\u0442\u0440\u0438\u043a\u0430":
            value_style += "display:inline-block;max-width:min(720px,100%);white-space:normal;overflow-wrap:break-word;word-break:normal;line-height:1.35;vertical-align:bottom;"
        chip_html_parts.append(
            '<span style="display:inline-flex;align-items:center;gap:6px;padding:6px 10px;'
            'border:1px solid rgba(148,163,184,0.28);border-radius:999px;background:rgba(15,23,42,0.35);"'
            f' title="{value_text}">'
            f'<span style="color:#94a3b8;font-size:0.76rem;font-weight:760;text-transform:uppercase;letter-spacing:0.06em;">{label_text}</span>'
            f'<span style="{value_style}">{value_text}</span>'
            '</span>'
        )
    chip_html = "".join(chip_html_parts)
    return (
        '<div class="analysis-context" style="margin:18px 0 14px 0;padding:13px 15px;'
        'border:1px solid rgba(148,163,184,0.22);border-left:4px solid #60a5fa;'
        'border-radius:14px;background:linear-gradient(135deg, rgba(96,165,250,0.12), rgba(15,23,42,0.08));">'
        '<div style="color:#cbd5e1;font-size:0.82rem;font-weight:820;margin-bottom:9px;">\u0427\u0442\u043e \u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u0435\u043c</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:8px;">{chip_html}</div>'
        '</div>'
    )


def metric_unit_for_metric(metric):
    metric_text = str(metric).strip()
    metric_lower = metric_text.lower()
    if " / " in metric_lower and metric_lower.endswith("%"):
        return "%"
    if "\u0440\u0443\u0431" in metric_lower or "rub" in metric_lower:
        return "\u0440\u0443\u0431"
    if "\u0448\u0442" in metric_lower or "pcs" in metric_lower:
        return "\u0448\u0442"
    if "%" in metric_lower:
        return "%"
    return ""


def dashboard_css():
    return """
<style>
:root {
    --kir-bg: #070b12;
    --kir-surface: rgba(15, 23, 42, 0.78);
    --kir-surface-strong: rgba(15, 23, 42, 0.92);
    --kir-border: rgba(148, 163, 184, 0.18);
    --kir-border-strong: rgba(96, 165, 250, 0.34);
    --kir-text-muted: #9aa6b2;
}
[data-testid="stAppViewContainer"] {
    background:
        linear-gradient(90deg, rgba(2, 6, 23, 0.98) 0%, rgba(2, 6, 23, 0.94) 46%, rgba(2, 6, 23, 0.62) 78%, rgba(2, 6, 23, 0.36) 100%),
        radial-gradient(820px 620px at 104% 18%, rgba(96, 165, 250, 0.26), transparent 62%),
        radial-gradient(760px 560px at 104% 96%, rgba(47, 191, 113, 0.22), transparent 68%),
        var(--kir-bg);
}
[data-testid="stAppViewContainer"]::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    opacity: 0.12;
    background-image: radial-gradient(rgba(255, 255, 255, 0.42) 1px, transparent 1px);
    background-size: 42px 42px;
    mask-image: linear-gradient(90deg, transparent 0%, black 42%, black 100%);
}
[data-testid="stHeader"] {
    background: transparent;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(15, 23, 42, 0.94), rgba(15, 23, 42, 0.86));
    border-right: 1px solid var(--kir-border);
}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    gap: 0.85rem;
}
.block-container {
    padding-top: 2.1rem;
}
h1 {
    letter-spacing: -0.04em;
}
[data-testid="stExpander"],
[data-testid="stForm"],
[data-testid="stDataFrame"],
[data-testid="stTable"],
[data-testid="stPlotlyChart"],
[data-testid="stAlert"] {
    border: 1px solid var(--kir-border);
    border-radius: 18px;
    background: var(--kir-surface);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04), 0 18px 60px rgba(0, 0, 0, 0.18);
    overflow: hidden;
}
[data-testid="stExpander"] details {
    background: transparent;
}
[data-testid="stExpander"] summary {
    border-radius: 18px;
}
[data-testid="stRadio"] div[role="radiogroup"] {
    gap: 0.6rem;
    flex-wrap: wrap;
}
[data-testid="stRadio"] div[role="radiogroup"] label {
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.28);
    background: rgba(15, 23, 42, 0.58);
    padding: 0.54rem 0.95rem;
    min-height: 38px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0;
    transition: border-color 120ms ease, background 120ms ease, color 120ms ease;
}
[data-testid="stRadio"] div[role="radiogroup"] label > div:first-child {
    display: none;
}
[data-testid="stRadio"] div[role="radiogroup"] label p {
    margin: 0;
    line-height: 1;
}
[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) {
    border-color: #ff4d4d;
    background: #ff4d4d;
    color: #ffffff;
}
[data-testid="stRadio"] div[role="radiogroup"] label:hover {
    border-color: var(--kir-border-strong);
    background: rgba(30, 41, 59, 0.92);
}
.stButton > button,
[data-testid="stDownloadButton"] > button {
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.34);
    background: rgba(15, 23, 42, 0.74);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}
.stButton > button:hover,
[data-testid="stDownloadButton"] > button:hover {
    border-color: var(--kir-border-strong);
    background: rgba(30, 41, 59, 0.92);
}
.stTabs [data-baseweb="tab-list"] {
    gap: 0.55rem;
    flex-wrap: wrap;
}
.stTabs [data-baseweb="tab"] {
    border: 1px solid rgba(148, 163, 184, 0.28);
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.58);
    padding: 0.45rem 0.75rem;
}
.stTabs [aria-selected="true"] {
    border-color: #ff4d4d;
    background: #ff4d4d;
    color: #ffffff;
}
.stMetric {
    border: 1px solid var(--kir-border);
    border-radius: 18px;
    background: var(--kir-surface);
    padding: 1rem;
}
.element-container:has(.relationship-heading),
.element-container:has(.analysis-context) {
    margin-top: 0.2rem;
}
.stSelectbox div[data-baseweb="select"] > div {
    height: auto;
    min-height: 50px;
    align-items: flex-start;
    border-radius: 13px;
    background: rgba(8, 13, 22, 0.86);
    border-color: rgba(148, 163, 184, 0.20);
}
.stSelectbox div[data-baseweb="select"] div[role="combobox"],
.stSelectbox div[data-baseweb="select"] div[role="combobox"] > div,
.stSelectbox div[data-baseweb="select"] span {
    white-space: normal;
    overflow-wrap: anywhere;
    word-break: normal;
    text-overflow: clip;
    line-height: 1.28;
}
.stSelectbox div[data-baseweb="select"] div[role="combobox"] {
    padding-top: 0.45rem;
    padding-bottom: 0.45rem;
}
.stMultiSelect div[data-baseweb="select"] > div,
.stNumberInput input,
.stTextInput input {
    border-radius: 13px;
    background: rgba(8, 13, 22, 0.86);
    border-color: rgba(148, 163, 184, 0.20);
}
</style>
"""


def format_percentile_card(label, item, metric_unit="", metric_label="\u041a\u0418\u0420"):
    count_for_sentence = f"{int(item['count']):,}".replace(",", " ")
    total_count = int(item.get("total_count", 0))
    total_for_sentence = f"{total_count:,}".replace(",", " ")
    share = item.get("share")
    if share is None:
        share = int(item["count"]) / total_count if total_count else 0
    is_percent_metric = metric_unit == "%"
    count_share = f"{float(share):.1%}"
    threshold_value = (
        f"{float(item['threshold']):,.2f}".replace(".", ",") if is_percent_metric and item["threshold"] is not None else _format_number(item["threshold"])
    )
    is_lower = "<=" in label
    count_details = "\u043c\u0430\u0433\u0430\u0437\u0438\u043d\u043e\u0432 \u043d\u0438\u0436\u0435 \u0438\u043b\u0438 \u0440\u0430\u0432\u043d\u043e \u043f\u043e\u0440\u043e\u0433\u0443" if is_lower else "\u043c\u0430\u0433\u0430\u0437\u0438\u043d\u043e\u0432 \u0432\u044b\u0448\u0435 \u0438\u043b\u0438 \u0440\u0430\u0432\u043d\u043e \u043f\u043e\u0440\u043e\u0433\u0443"
    opposite_count = max(total_count - int(item["count"]), 0)
    opposite_for_sentence = f"{opposite_count:,}".replace(",", " ")
    opposite_label = "\u0412\u044b\u0448\u0435 \u043f\u043e\u0440\u043e\u0433\u0430" if is_lower else "\u041d\u0438\u0436\u0435 \u043f\u043e\u0440\u043e\u0433\u0430"
    threshold_display = f"{threshold_value} {metric_unit}".strip()
    return {
        "label": label,
        "count": f"{int(item['count']):,}",
        "count_share": count_share,
        "primary_value": count_for_sentence,
        "count_details": count_details,
        "threshold_label": "\u041f\u043e\u0440\u043e\u0433 \u043c\u0435\u0442\u0440\u0438\u043a\u0438",
        "threshold_value": threshold_value,
        "threshold_unit": metric_unit,
        "threshold_help": f"\u041f\u043e\u0440\u043e\u0433: {threshold_display}. {opposite_label}: {opposite_for_sentence} \u043c\u0430\u0433\u0430\u0437\u0438\u043d\u043e\u0432. \u0412\u0441\u0435\u0433\u043e \u0432 \u0432\u044b\u0431\u043e\u0440\u043a\u0435: {total_for_sentence}.",
    }


def render_percentile_card_html(card, color):
    label = escape(str(card["label"]))
    count = escape(str(card["count"]))
    count_share = escape(str(card.get("count_share", "")))
    primary_value = escape(str(card.get("primary_value", "")))
    count_details = escape(str(card.get("count_details", "")))
    threshold_label = escape(str(card["threshold_label"]))
    threshold_value = escape(str(card["threshold_value"]))
    threshold_unit = escape(str(card.get("threshold_unit", "")))
    threshold_help = escape(str(card.get("threshold_help", "")))
    threshold_display = f"{threshold_value} {threshold_unit}".strip()
    if primary_value:
        share_html = (
            f' <span style="font-size:0.98rem;font-weight:760;color:rgba(255,255,255,0.58);">({count_share})</span>'
            if count_share
            else ""
        )
        primary_html = (
            '<div style="font-size:2.05rem;font-weight:750;color:#ffffff;margin-top:22px;line-height:1;">'
            f"{primary_value}{share_html}</div>"
            '<div style="font-size:0.86rem;font-weight:720;color:rgba(255,255,255,0.60);margin-top:10px;">'
            f"{count_details}</div>"
        )
    else:
        primary_html = (
            '<div style="font-size:2.05rem;font-weight:750;color:#ffffff;margin-top:22px;line-height:1;">'
            f'{count} <span style="font-size:0.98rem;font-weight:760;color:rgba(255,255,255,0.58);">({count_share})</span>'
            "</div>"
        )
    threshold_html = (
        '<div style="font-size:0.84rem;color:rgba(255,255,255,0.68);margin-top:18px;">'
        f'{threshold_label} <span style="color:{color};font-weight:850;">{threshold_display}</span></div>'
    )
    color = escape(str(color))
    return (
        f'<div style="border:1px solid {color};border-left:7px solid {color};border-radius:14px;'
        f'padding:16px 18px;background:linear-gradient(135deg, color-mix(in srgb, {color} 18%, transparent), rgba(255,255,255,0.025));'
        'box-shadow:inset 0 1px 0 rgba(255,255,255,0.06);min-height:132px;">'
        f'<div style="font-size:0.9rem;font-weight:700;color:rgba(255,255,255,0.92);">{label}</div>'
        f"{primary_html}{threshold_html}"
        '<div style="font-size:0.74rem;line-height:1.32;color:rgba(255,255,255,0.48);margin-top:8px;max-width:360px;">'
        f"{threshold_help}</div></div>"
    )


def metric_bar_value_column(bin_table):
    return "store_count" if "store_count" in bin_table.columns else "count"


def network_chart_color(network_name):
    name = str(network_name).lower()
    if "\u043f\u044f\u0442\u0435\u0440" in name or "pyater" in name:
        return "#f06a6a"
    if "\u043f\u0435\u0440\u0435\u043a" in name or "perek" in name:
        return "#64b878"
    return "#79bff2"


def network_brand_html(network_name):
    name = str(network_name).lower()
    if "\u043f\u044f\u0442\u0435\u0440" in name or "pyater" in name:
        brand_class = "brand-pyaterochka"
        label = "\u041f\u044f\u0442\u0451\u0440\u043e\u0447\u043a\u0430"
        color = "#e52320"
    if "\u043f\u0435\u0440\u0435\u043a" in name or "perek" in name:
        brand_class = "brand-perekrestok"
        label = "\u041f\u0435\u0440\u0435\u043a\u0440\u0451\u0441\u0442\u043e\u043a"
        color = "#00843d"
    if "\u043f\u044f\u0442\u0435\u0440" not in name and "pyater" not in name and "\u043f\u0435\u0440\u0435\u043a" not in name and "perek" not in name:
        brand_class = "brand-generic"
        label = str(network_name)
        color = "#cbd5e1"
    return (
        f'<div class="network-brand {brand_class}" style="margin:0 0 8px 0;">'
        '<div style="display:flex;align-items:center;gap:9px;min-height:24px;">'
        f'<span style="display:inline-block;width:18px;height:2px;border-radius:999px;background:{color};opacity:0.95;"></span>'
        f'<span style="color:{color};font-size:1.05rem;font-weight:850;letter-spacing:-0.02em;">{escape(label)}</span>'
        '</div>'
        '</div>'
    )


def group_summary_table(chart_data, group_col):
    return (
        chart_data.groupby(group_col, dropna=False)["_metric"]
        .agg(count="count", mean="mean", median="median", min="min", max="max", p85=lambda value: value.quantile(0.85), total="sum")
        .reset_index()
        .sort_values("count", ascending=False)
    )


def group_comparison_tables(filtered, numeric_metric, group_col):
    chart_data = filtered.assign(_metric=numeric_metric)
    if group_col == CATEGORY_COL and TS_COL in chart_data.columns:
        networks = split_by_network(chart_data)
        if len(networks) > 1:
            return [(network_name, group_summary_table(network_df, group_col)) for network_name, network_df in networks]
    return [(None, group_summary_table(chart_data, group_col))]


def collapse_tail_bins(bin_table, head_bins):
    if bin_table.empty:
        return bin_table.copy()

    head_bins = max(int(head_bins), 1)
    if head_bins >= len(bin_table):
        return bin_table.copy()

    head = bin_table.head(head_bins).copy()
    tail = bin_table.iloc[head_bins:].copy()
    tail_row = tail.iloc[0].copy()
    tail_row["bin_start"] = tail["bin_start"].iloc[0]
    tail_row["bin_end"] = tail["bin_end"].iloc[-1]
    tail_row["bin"] = f"Tail: >= {_clean_number(tail['bin_start'].iloc[0])}"
    for column in ["count", "store_count", "share"]:
        if column in tail.columns:
            tail_row[column] = tail[column].sum()
    return pd.concat([head, pd.DataFrame([tail_row])], ignore_index=True)


def prepare_bin_chart_table(bin_table):
    chart_table = bin_table.copy()
    if chart_table.empty:
        chart_table["bin_mid"] = pd.Series(dtype="float64")
        chart_table["bar_width"] = pd.Series(dtype="float64")
        return chart_table

    chart_table["bin_mid"] = (pd.to_numeric(chart_table["bin_start"]) + pd.to_numeric(chart_table["bin_end"])) / 2
    chart_table["bar_width"] = pd.to_numeric(chart_table["bin_end"]) - pd.to_numeric(chart_table["bin_start"])
    tail_mask = chart_table["bin"].astype(str).str.startswith("Tail:")
    if tail_mask.any():
        regular_widths = chart_table.loc[~tail_mask, "bar_width"]
        visual_width = float(regular_widths[regular_widths.gt(0)].median()) if regular_widths.gt(0).any() else 1.0
        chart_table.loc[tail_mask, "bar_width"] = visual_width
        chart_table.loc[tail_mask, "bin_mid"] = pd.to_numeric(chart_table.loc[tail_mask, "bin_start"]) + visual_width / 2
    return chart_table


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


def build_bin_table_by_width(series, bin_width, store_series=None, max_bins=2000):
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
    bin_count = int(math.ceil((end - start) / bin_width))
    has_tail = bin_count > int(max_bins)
    if has_tail:
        regular_bin_count = max(int(max_bins) - 1, 1)
        tail_start = start + regular_bin_count * bin_width
        edges = [start + index * bin_width for index in range(regular_bin_count + 1)]
    else:
        tail_start = None
        edges = [start + index * bin_width for index in range(bin_count + 1)]
    source = pd.DataFrame({"metric": pd.to_numeric(series, errors="coerce")})
    if store_series is not None:
        source["store"] = store_series
    source = source.dropna(subset=["metric"])
    regular_source = source[source["metric"].lt(tail_start)].copy() if has_tail else source
    source_for_cut = regular_source if has_tail else source
    source_for_cut["bin_interval"] = pd.cut(source_for_cut["metric"], bins=edges, right=False, include_lowest=True)
    counts = source_for_cut["bin_interval"].value_counts(sort=False)

    rows = []
    total = int(len(source))
    for interval, count in counts.items():
        bin_rows = source_for_cut[source_for_cut["bin_interval"] == interval]
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
    if has_tail:
        tail = source[source["metric"].ge(tail_start)]
        tail_count = int(len(tail))
        tail_store_count = int(tail["store"].nunique()) if "store" in tail.columns else tail_count
        rows.append(
            {
                "bin_start": _clean_number(tail_start),
                "bin_end": _clean_number(max_value),
                "bin": f"Tail: >= {_clean_number(tail_start)}",
                "count": tail_count,
                "store_count": tail_store_count,
                "share": float(tail_count / total) if total else 0,
            }
        )
    return pd.DataFrame(rows)


def _nice_width(raw_width):
    if raw_width <= 0:
        return 1.0
    exponent = math.floor(math.log10(raw_width))
    scale = 10**exponent
    normalized = raw_width / scale
    if normalized <= 1:
        multiplier = 1
    elif normalized <= 2:
        multiplier = 2
    elif normalized <= 5:
        multiplier = 5
    else:
        multiplier = 10
    return multiplier * scale


def default_bin_width(series, target_bins=30, minimum=1, maximum=1000, upper_quantile=None):
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return float(minimum)
    upper = numeric.quantile(float(upper_quantile)) if upper_quantile is not None else numeric.max()
    span = float(upper - numeric.min())
    raw_width = span / target_bins
    if raw_width <= minimum:
        return float(minimum)
    nice_width = _nice_width(raw_width) if upper_quantile is not None else 10 ** math.ceil(math.log10(raw_width))
    return float(min(max(nice_width, float(minimum)), float(maximum)))


def adjust_bin_width(current, delta, minimum=1):
    return round(max(float(minimum), float(current) + float(delta)), 10)


def bin_width_settings(is_percent_metric=False):
    if is_percent_metric:
        return {
            "minimum": 0.01,
            "maximum": 5.0,
            "step": 0.01,
            "buttons": [("-0.01", -0.01), ("+0.01", 0.01), ("-0.1", -0.1), ("+0.1", 0.1), ("-1", -1), ("+1", 1)],
            "upper_quantile": 0.99,
        }
    return {
        "minimum": 1.0,
        "maximum": 1000.0,
        "step": 1.0,
        "buttons": [("-10", -10), ("+10", 10), ("-100", -100), ("+100", 100), ("-1000", -1000), ("+1000", 1000)],
        "upper_quantile": None,
    }


def _format_setting_number(value):
    number = float(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def chart_settings_summary(bin_width, custom_percentile, hide_zero_values=False, collapse_tail=False):
    zero_text = "\u043d\u0443\u043b\u0438 \u0441\u043a\u0440\u044b\u0442\u044b" if hide_zero_values else "\u043d\u0443\u043b\u0438 \u043f\u043e\u043a\u0430\u0437\u0430\u043d\u044b"
    tail_text = "\u0445\u0432\u043e\u0441\u0442 \u0441\u0432\u0435\u0440\u043d\u0443\u0442" if collapse_tail else "\u0445\u0432\u043e\u0441\u0442 \u043f\u043e\u043a\u0430\u0437\u0430\u043d"
    return f"\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0433\u0440\u0430\u0444\u0438\u043a\u0430: bin {_format_setting_number(bin_width)}, P{int(custom_percentile)}, {zero_text}, {tail_text}"


def _adjust_session_bin_width(key, delta, minimum=1):
    st.session_state[key] = adjust_bin_width(st.session_state.get(key, minimum), delta, minimum=minimum)


def set_session_value(key, value):
    st.session_state[key] = value


def first_bins_store_sum(bin_table, n_bins):
    if bin_table.empty:
        return {"bins_used": 0, "store_sum": 0, "row_sum": 0}

    bins_used = min(max(int(n_bins), 0), len(bin_table))
    first_bins = bin_table.head(bins_used)
    store_column = "store_count" if "store_count" in first_bins.columns else "count"
    return {
        "bins_used": bins_used,
        "store_sum": int(first_bins[store_column].sum()),
        "row_sum": int(first_bins["count"].sum()) if "count" in first_bins.columns else 0,
    }


def first_bin_count_for_target_share(bin_table, target_share):
    if bin_table.empty:
        return 0
    store_column = "store_count" if "store_count" in bin_table.columns else "count"
    counts = pd.to_numeric(bin_table[store_column], errors="coerce").fillna(0)
    total = float(counts.sum())
    if total <= 0:
        return 0
    target_share = min(max(float(target_share), 0.0), 1.0)
    target_count = total * target_share
    cumulative = counts.cumsum()
    matching = cumulative[cumulative.ge(target_count)]
    if matching.empty:
        return int(len(bin_table))
    return int(matching.index[0]) + 1


def recommended_bin_width_for_target_share(metric_series, target_share, bins_used, current_bin_width, minimum=0.01):
    numeric = pd.to_numeric(metric_series, errors="coerce").dropna()
    if numeric.empty or int(bins_used) <= 0:
        return None
    current_bin_width = float(current_bin_width)
    if current_bin_width <= 0:
        return None
    start = (float(numeric.min()) // current_bin_width) * current_bin_width
    target_value = float(numeric.quantile(min(max(float(target_share), 0.0), 1.0)))
    width = (target_value - start) / int(bins_used)
    if width <= 0:
        return float(minimum)
    return round(max(float(minimum), width), 4)


def first_bins_summary(metric_series, bin_table, n_bins, store_series=None):
    if bin_table.empty:
        return {"bins_used": 0, "store_sum": 0, "total_stores": 0, "store_share": 0}

    bins_used = min(max(int(n_bins), 0), len(bin_table))
    if bins_used == 0:
        return {"bins_used": 0, "store_sum": 0, "total_stores": 0, "store_share": 0}

    first_bins = bin_table.head(bins_used)
    start = float(first_bins["bin_start"].iloc[0])
    end = float(first_bins["bin_end"].iloc[-1])
    numeric = pd.to_numeric(metric_series, errors="coerce")
    mask = numeric.ge(start) & numeric.lt(end)
    if store_series is not None:
        stores = pd.Series(store_series)
        store_sum = int(stores.loc[mask].nunique())
        total_stores = int(stores.loc[numeric.notna()].nunique())
    else:
        store_sum = int(mask.sum())
        total_stores = int(numeric.notna().sum())
    store_share = float(store_sum / total_stores) if total_stores else 0
    return {"bins_used": bins_used, "store_sum": store_sum, "total_stores": total_stores, "store_share": store_share}


def percentile_store_counts(series, custom_percentile, store_series=None):
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return {
            "p25": {"percentile": 25, "threshold": None, "count": 0, "total_count": 0, "share": 0},
            "p85": {"percentile": 85, "threshold": None, "count": 0, "total_count": 0, "share": 0},
            "custom": {"percentile": custom_percentile, "threshold": None, "count": 0, "total_count": 0, "share": 0},
        }

    source = pd.DataFrame({"metric": pd.to_numeric(series, errors="coerce")})
    if store_series is not None:
        source["store"] = store_series
    source = source.dropna(subset=["metric"])
    total_count = int(source["store"].nunique()) if "store" in source.columns else int(len(source))

    def make_item(percentile):
        threshold = float(source["metric"].quantile(percentile / 100))
        if percentile == 25:
            matching = source[source["metric"] <= threshold]
        else:
            matching = source[source["metric"] >= threshold]
        count = int(matching["store"].nunique()) if "store" in matching.columns else int(len(matching))
        return {
            "percentile": percentile,
            "threshold": threshold,
            "count": count,
            "total_count": total_count,
            "share": float(count / total_count) if total_count else 0,
        }

    return {"p25": make_item(25), "p85": make_item(85), "custom": make_item(custom_percentile)}


def split_by_network(df):
    if TS_COL not in df.columns:
        return [("All", df)]
    network_key = df[TS_COL].astype("string").fillna("\u0411\u0435\u0437 \u0422\u0421")
    return [(str(name), group.copy()) for name, group in sorted(df.groupby(network_key), key=lambda item: str(item[0]))]


def filter_visual_outliers(df, x_col, y_col, quantile=0.99):
    source = df.copy()
    x_values = pd.to_numeric(source[x_col], errors="coerce")
    y_values = pd.to_numeric(source[y_col], errors="coerce")
    positive_mask = x_values.gt(0) & y_values.gt(0)
    source = source[positive_mask].copy()
    x_values = x_values[positive_mask]
    y_values = y_values[positive_mask]
    pair = pd.DataFrame({"x": x_values, "y": y_values}).dropna()
    if pair.empty:
        return source.iloc[0:0].copy()

    x_limit = float(pair["x"].quantile(quantile))
    y_limit = float(pair["y"].quantile(quantile))
    return source[(x_values <= x_limit) & (y_values <= y_limit)].copy()


def relationship_chart_rows(network_names, relationship_columns):
    return [{"comparison": column, "networks": list(network_names)} for column in relationship_columns]


def relationship_heading_html(metric, comparison):
    colors = RELATIONSHIP_HEADING_COLORS.get(
        comparison,
        {"accent": "#93c5fd", "background": "rgba(147, 197, 253, 0.16)"},
    )
    return (
        '<div class="relationship-heading" style="margin:22px 0 16px 0;">'
        '<div style="display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;'
        'font-size:1.28rem;font-weight:820;line-height:1.28;">'
        f'<span class="metric-label" style="color:#f8fafc;">{escape(str(metric))}</span>'
        '<span style="font-size:0.78rem;letter-spacing:0.14em;color:#94a3b8;font-weight:760;">VS</span>'
        f'<span class="comparison-label" style="color:{colors["accent"]};'
        f'border-bottom:2px solid {colors["accent"]};padding-bottom:2px;">'
        f'{escape(str(comparison))}</span>'
        '</div>'
        '</div>'
    )


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


def _correlation_value(value):
    if value is None or pd.isna(value):
        return None
    return float(value)


def _format_correlation(value):
    value = _correlation_value(value)
    return "n/a" if value is None else f"{value:.2f}"


def correlation_strength_label(value):
    value = _correlation_value(value)
    if value is None:
        return "\u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445"

    absolute = abs(value)
    if absolute < 0.20:
        return "\u0441\u0432\u044f\u0437\u0438 \u043f\u043e\u0447\u0442\u0438 \u043d\u0435\u0442"
    if absolute < 0.40:
        level = "\u0441\u043b\u0430\u0431\u0430\u044f"
    elif absolute < 0.60:
        level = "\u0443\u043c\u0435\u0440\u0435\u043d\u043d\u0430\u044f"
    elif absolute < 0.80:
        level = "\u0441\u0438\u043b\u044c\u043d\u0430\u044f"
    else:
        level = "\u043e\u0447\u0435\u043d\u044c \u0441\u0438\u043b\u044c\u043d\u0430\u044f"
    direction = "\u043f\u043e\u043b\u043e\u0436\u0438\u0442\u0435\u043b\u044c\u043d\u0430\u044f" if value > 0 else "\u043e\u0442\u0440\u0438\u0446\u0430\u0442\u0435\u043b\u044c\u043d\u0430\u044f"
    return f"{level} {direction} \u0441\u0432\u044f\u0437\u044c"


def prepare_correlation_display_stats(stats):
    display = stats.copy()
    if display.empty:
        display["\u0421\u0438\u043b\u0430 \u0441\u0432\u044f\u0437\u0438"] = []
        return display
    display["\u0421\u0438\u043b\u0430 \u0441\u0432\u044f\u0437\u0438"] = display["spearman"].apply(correlation_strength_label)
    display = display.rename(
        columns={
            "comparison": "\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u044c",
            "pearson": "Pearson",
            "spearman": "Spearman",
            "rows_used": "\u0421\u0442\u0440\u043e\u043a \u0432 \u0440\u0430\u0441\u0447\u0435\u0442\u0435",
        }
    )
    return display[["\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u044c", "Pearson", "Spearman", "\u0421\u0438\u043b\u0430 \u0441\u0432\u044f\u0437\u0438", "\u0421\u0442\u0440\u043e\u043a \u0432 \u0440\u0430\u0441\u0447\u0435\u0442\u0435"]]


def correlation_business_insights(stats, network_name=None):
    if stats.empty:
        return ["\u041d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445 \u0434\u043b\u044f \u0438\u043d\u0442\u0435\u0440\u043f\u0440\u0435\u0442\u0430\u0446\u0438\u0438 \u043a\u043e\u0440\u0440\u0435\u043b\u044f\u0446\u0438\u0438."]

    source = stats.copy()
    source["_abs_spearman"] = pd.to_numeric(source["spearman"], errors="coerce").abs()
    valid = source.dropna(subset=["_abs_spearman"])
    if valid.empty:
        return ["\u041a\u043e\u0440\u0440\u0435\u043b\u044f\u0446\u0438\u044f \u043d\u0435 \u0440\u0430\u0441\u0441\u0447\u0438\u0442\u0430\u043b\u0430\u0441\u044c: \u0441\u043b\u0438\u0448\u043a\u043e\u043c \u043c\u0430\u043b\u043e \u043f\u0430\u0440 \u0447\u0438\u0441\u043b\u043e\u0432\u044b\u0445 \u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0439."]

    best = valid.sort_values("_abs_spearman", ascending=False).iloc[0]
    best_spearman = _format_correlation(best["spearman"])
    insights = [
        f"\u0421\u0430\u043c\u0430\u044f \u0437\u0430\u043c\u0435\u0442\u043d\u0430\u044f \u0441\u0432\u044f\u0437\u044c: {best['comparison']} - Spearman {best_spearman} ({correlation_strength_label(best['spearman'])})."
    ]

    for _, row in valid.iterrows():
        pearson = _correlation_value(row["pearson"])
        spearman = _correlation_value(row["spearman"])
        if pearson is None or spearman is None:
            continue
        if abs(spearman) - abs(pearson) >= 0.20 and abs(spearman) >= 0.30:
            insights.append(
                f"{row['comparison']}: \u0440\u0430\u043d\u0433\u043e\u0432\u0430\u044f \u0441\u0432\u044f\u0437\u044c \u0437\u0430\u043c\u0435\u0442\u043d\u0435\u0435 \u043b\u0438\u043d\u0435\u0439\u043d\u043e\u0439 "
                f"(Spearman {_format_correlation(spearman)}, Pearson {_format_correlation(pearson)}). "
                "\u042d\u0442\u043e \u0447\u0430\u0441\u0442\u043e \u043e\u0437\u043d\u0430\u0447\u0430\u0435\u0442 \u043d\u0435\u043b\u0438\u043d\u0435\u0439\u043d\u043e\u0441\u0442\u044c, \u0445\u0432\u043e\u0441\u0442\u044b \u0438\u043b\u0438 \u0432\u043b\u0438\u044f\u043d\u0438\u0435 \u0432\u044b\u0431\u0440\u043e\u0441\u043e\u0432."
            )

    min_rows = int(valid["rows_used"].min()) if "rows_used" in valid.columns else 0
    scope_name = network_name or "\u0441\u0435\u0442\u0438"
    insights.append(f"\u0412\u044b\u0432\u043e\u0434 \u043f\u043e {scope_name} \u043e\u0441\u043d\u043e\u0432\u0430\u043d \u043c\u0438\u043d\u0438\u043c\u0443\u043c \u043d\u0430 {min_rows:,} \u0441\u0442\u0440\u043e\u043a\u0430\u0445 \u043f\u043e\u0441\u043b\u0435 \u0444\u0438\u043b\u044c\u0442\u0440\u043e\u0432.")
    return insights


def compare_network_correlations(stats_by_network):
    if len(stats_by_network) < 2:
        return []

    names = list(stats_by_network)
    first = stats_by_network[names[0]]
    comparisons = first["comparison"].tolist() if "comparison" in first.columns else []
    lines = []
    for comparison in comparisons:
        values = []
        for network_name, stats in stats_by_network.items():
            match = stats[stats["comparison"] == comparison]
            if match.empty:
                continue
            row = match.iloc[0]
            spearman = _correlation_value(row["spearman"])
            if spearman is None:
                continue
            values.append((network_name, spearman))
        if len(values) < 2:
            continue
        values = sorted(values, key=lambda item: abs(item[1]), reverse=True)
        best_name, best_value = values[0]
        second_name, second_value = values[1]
        delta = abs(best_value) - abs(second_value)
        if delta < 0.05:
            lines.append(
                f"{comparison}: \u0440\u0430\u0437\u043b\u0438\u0447\u0438\u0435 \u043d\u0435\u0431\u043e\u043b\u044c\u0448\u043e\u0435 "
                f"(Spearman {best_name} {_format_correlation(best_value)}, {second_name} {_format_correlation(second_value)}, \u0394 {delta:.2f})."
            )
        else:
            lines.append(
                f"{comparison}: \u0441\u0432\u044f\u0437\u044c \u0441\u0438\u043b\u044c\u043d\u0435\u0435 \u0443 {best_name} "
                f"(Spearman {_format_correlation(best_value)} vs {_format_correlation(second_value)}, \u0394 {delta:.2f})."
            )

    row_counts = []
    for stats in stats_by_network.values():
        if "rows_used" in stats.columns and not stats.empty:
            row_counts.append(int(pd.to_numeric(stats["rows_used"], errors="coerce").min()))
    if row_counts and min(row_counts) > 0 and max(row_counts) / min(row_counts) >= 3:
        lines.append("\u0412\u0430\u0436\u043d\u043e: rows_used \u043c\u0435\u0436\u0434\u0443 \u0422\u0421 \u0441\u0438\u043b\u044c\u043d\u043e \u043e\u0442\u043b\u0438\u0447\u0430\u044e\u0442\u0441\u044f, \u043f\u043e\u044d\u0442\u043e\u043c\u0443 \u0441\u0440\u0430\u0432\u043d\u0435\u043d\u0438\u0435 \u043d\u0443\u0436\u043d\u043e \u0447\u0438\u0442\u0430\u0442\u044c \u043e\u0441\u0442\u043e\u0440\u043e\u0436\u043d\u043e.")
    return lines


def render_correlation_interpretation_html(network_name, stats):
    insights = correlation_business_insights(stats, network_name)
    insight_items = "".join(f"<li>{escape(line)}</li>" for line in insights)
    network = escape(str(network_name))
    return (
        '<div class="correlation-interpretation" style="margin-top:12px;padding:13px 15px;'
        'border:1px solid rgba(148,163,184,0.20);border-radius:14px;'
        'background:linear-gradient(135deg, rgba(15,23,42,0.72), rgba(30,41,59,0.36));">'
        f'<div style="font-weight:820;color:#e2e8f0;margin-bottom:8px;">\u041a\u0430\u043a \u0447\u0438\u0442\u0430\u0442\u044c \u043a\u043e\u0440\u0440\u0435\u043b\u044f\u0446\u0438\u0438: {network}</div>'
        '<div style="color:#94a3b8;font-size:0.86rem;line-height:1.45;margin-bottom:8px;">'
        'Pearson \u043f\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u0435\u0442 \u043b\u0438\u043d\u0435\u0439\u043d\u0443\u044e \u0441\u0432\u044f\u0437\u044c. Spearman \u043f\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u0435\u0442 \u0440\u0430\u043d\u0433\u043e\u0432\u0443\u044e \u0441\u0432\u044f\u0437\u044c \u0438 \u0443\u0441\u0442\u043e\u0439\u0447\u0438\u0432\u0435\u0435 \u043a \u0445\u0432\u043e\u0441\u0442\u0430\u043c. '
        '\u0414\u043b\u044f \u0441\u0438\u043b\u044b \u0441\u0432\u044f\u0437\u0438 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0435\u043c |Spearman|: 0.00-0.19 \u043f\u043e\u0447\u0442\u0438 \u043d\u0435\u0442, 0.20-0.39 \u0441\u043b\u0430\u0431\u0430\u044f, 0.40-0.59 \u0443\u043c\u0435\u0440\u0435\u043d\u043d\u0430\u044f, 0.60-0.79 \u0441\u0438\u043b\u044c\u043d\u0430\u044f, 0.80-1.00 \u043e\u0447\u0435\u043d\u044c \u0441\u0438\u043b\u044c\u043d\u0430\u044f. '
        '\u041a\u043e\u0440\u0440\u0435\u043b\u044f\u0446\u0438\u044f \u043d\u0435 \u0434\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u0435\u0442 \u043f\u0440\u0438\u0447\u0438\u043d\u043d\u043e-\u0441\u043b\u0435\u0434\u0441\u0442\u0432\u0435\u043d\u043d\u0443\u044e \u0441\u0432\u044f\u0437\u044c.'
        '</div>'
        f'<ul style="margin:0;padding-left:18px;color:#cbd5e1;font-size:0.86rem;line-height:1.48;">{insight_items}</ul>'
        '</div>'
    )


def render_network_correlation_comparison_html(stats_by_network):
    lines = compare_network_correlations(stats_by_network)
    if not lines:
        return ""
    items = "".join(f"<li>{escape(line)}</li>" for line in lines)
    return (
        '<div class="network-correlation-comparison" style="margin:12px 0 18px 0;padding:13px 15px;'
        'border:1px solid rgba(96,165,250,0.24);border-left:4px solid #60a5fa;'
        'border-radius:14px;background:rgba(96,165,250,0.09);">'
        '<div style="font-weight:820;color:#e2e8f0;margin-bottom:8px;">\u0421\u0440\u0430\u0432\u043d\u0435\u043d\u0438\u0435 \u0422\u0421 \u043f\u043e Spearman</div>'
        f'<ul style="margin:0;padding-left:18px;color:#cbd5e1;font-size:0.86rem;line-height:1.48;">{items}</ul>'
        '</div>'
    )


def _apply_sidebar_filters(df):
    _require_streamlit()
    filtered = df.copy()
    for column in FILTER_COLUMNS:
        if column not in filtered.columns:
            continue
        options = sorted(filtered[column].dropna().unique().tolist())
        format_func = format_week_label if column == WEEK_COL else str
        selected = st.sidebar.multiselect(filter_label(column), options, format_func=format_func)
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
    dataframe_cache = st.session_state.setdefault("loaded_dataframes", {})
    return read_final_data_with_progress(final_path, final_path.stat().st_mtime_ns, dataframe_cache=dataframe_cache)


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
        for label, path in [("Final", paths["final"]), ("Raw", paths["raw"])]:
            st.write(f"{label}: `{path}`")
            exists = path.exists()
            data = read_file_for_download(path, path.stat().st_mtime_ns) if exists else b""
            st.download_button(
                f"Download {path.name}",
                data=data,
                file_name=download_file_name(path, run_dir),
                mime=EXCEL_MIME,
                disabled=not exists,
                key=f"download_{label}_{Path(run_dir).name}",
            )

    diagnostics_path = run_dir / "merge_diagnostics.md"
    if diagnostics_path.exists():
        st.subheader("Merge diagnostics")
        st.markdown(diagnostics_path.read_text(encoding="utf-8"))
    else:
        st.warning("merge_diagnostics.md not found for this run.")


def _render_metric_analysis_tab(
    filtered,
    metric,
    numeric_metric,
    filter_values=None,
    title="Metric analysis",
    key_prefix="metric",
    metric_label="КИР",
    is_percent_metric=False,
):
    st.subheader(title)
    bin_width_key = f"{key_prefix}_bin_width_v2_{metric}"
    hide_zero_key = f"{key_prefix}_hide_zero_metric_values_{metric}"
    custom_percentile_key = f"{key_prefix}_custom_percentile_{metric}"
    collapse_tail_key = f"{key_prefix}_collapse_tail_bins_{metric}"
    tail_bins_key = f"{key_prefix}_tail_bins_to_keep_{metric}"
    width_settings = bin_width_settings(is_percent_metric=is_percent_metric)

    if bin_width_key not in st.session_state:
        st.session_state[bin_width_key] = default_bin_width(
            numeric_metric,
            minimum=width_settings["minimum"],
            maximum=width_settings["maximum"],
            upper_quantile=width_settings["upper_quantile"],
        )
    if hide_zero_key not in st.session_state:
        st.session_state[hide_zero_key] = False
    if custom_percentile_key not in st.session_state:
        st.session_state[custom_percentile_key] = 50
    if collapse_tail_key not in st.session_state:
        st.session_state[collapse_tail_key] = False

    original_summary = metric_summary(numeric_metric)
    hide_zero_values = bool(st.session_state.get(hide_zero_key, False))
    if hide_zero_values:
        filtered, numeric_metric = filter_zero_metric_values(filtered, numeric_metric)

    summary = metric_summary(numeric_metric)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Count", summary["count"])
    c2.metric("Mean", _format_number(summary["mean"]))
    c3.metric("Median", _format_number(summary["median"]))
    c4.metric("P85", _format_number(summary["p85"]))
    c5.metric("Zero values", original_summary["zero_count"])
    if hide_zero_values:
        st.caption(f"Hidden zero rows on this screen: {original_summary['zero_count']:,}")

    with st.expander("\u041f\u043e\u0434\u0440\u043e\u0431\u043d\u0430\u044f \u0441\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430", expanded=False):
        st.dataframe(pd.DataFrame([summary]), use_container_width=True)

    custom_percentile = int(st.session_state.get(custom_percentile_key, 50))
    store_series = filtered[FACTORY_COL] if FACTORY_COL in filtered.columns else None
    percentile_counts = percentile_store_counts(numeric_metric, custom_percentile=custom_percentile, store_series=store_series)

    st.markdown(render_metric_analysis_context_html(metric_analysis_context(filtered, filter_values or {}, metric=metric)), unsafe_allow_html=True)
    pc1, pc2, pc3 = st.columns(3)
    metric_unit = metric_unit_for_metric(metric)
    for container, card, color in zip(
        [pc1, pc2, pc3],
        [
            format_percentile_card("Stores <= P25", percentile_counts["p25"], metric_unit=metric_unit, metric_label=metric_label),
            format_percentile_card("Stores >= P85", percentile_counts["p85"], metric_unit=metric_unit, metric_label=metric_label),
            format_percentile_card(
                f"Stores >= P{custom_percentile}",
                percentile_counts["custom"],
                metric_unit=metric_unit,
                metric_label=metric_label,
            ),
        ],
        ["#2fbf71", "#ff4d4d", "#f59f00"],
    ):
        container.markdown(render_percentile_card_html(card, color), unsafe_allow_html=True)

    collapse_tail = bool(st.session_state.get(collapse_tail_key, False))
    st.markdown('<div class="metric-chart-settings-spacer" style="height:18px;"></div>', unsafe_allow_html=True)
    with st.expander("Настройки графика", expanded=False):
        st.caption(chart_settings_summary(st.session_state[bin_width_key], custom_percentile, hide_zero_values, collapse_tail))
        st.checkbox(
            "Hide zero metric values",
            key=hide_zero_key,
            help="Only affects this Metric analysis screen. Source rows are not changed.",
        )
        bin_width = st.number_input(
            "Bin width",
            min_value=width_settings["minimum"],
            step=width_settings["step"],
            key=bin_width_key,
        )
        step_columns = st.columns(6)
        for column, (label, delta) in zip(
            step_columns,
            width_settings["buttons"],
        ):
            column.button(
                label,
                key=f"{bin_width_key}_{label}",
                on_click=_adjust_session_bin_width,
                args=(bin_width_key, delta, width_settings["minimum"]),
            )
        custom_percentile = st.slider("Custom percentile", min_value=1, max_value=99, key=custom_percentile_key)

        max_bin_count = 500 if is_percent_metric else 2000
        bin_table = build_bin_table_by_width(numeric_metric, bin_width=bin_width, store_series=store_series, max_bins=max_bin_count)
        chart_bin_table = bin_table
        if len(bin_table) > 3:
            collapse_tail = st.checkbox(
                "Collapse long tail on bin chart",
                key=collapse_tail_key,
                help="Only affects the chart. The full bin table below stays unchanged.",
            )
            if collapse_tail:
                max_tail_bins = len(bin_table) - 1
                if tail_bins_key not in st.session_state or int(st.session_state[tail_bins_key]) > max_tail_bins:
                    st.session_state[tail_bins_key] = min(30, max_tail_bins)
                head_bins = st.number_input(
                    "Bins to keep before tail",
                    min_value=1,
                    max_value=max_tail_bins,
                    step=1,
                    key=tail_bins_key,
                )
                chart_bin_table = collapse_tail_bins(bin_table, head_bins)
                st.caption(f"Chart tail is collapsed into one bar. Full bin table still has {len(bin_table):,} bins.")
        else:
            collapse_tail = False

    try:
        import plotly.express as px

        if bin_table.empty:
            st.info("No valid numeric metric values after filters. Bin chart is unavailable.")
        else:
            bar_value_column = metric_bar_value_column(bin_table)
            chart_bin_table = prepare_bin_chart_table(chart_bin_table)
            fig = px.bar(
                chart_bin_table,
                x="bin_mid",
                y=bar_value_column,
                text=bar_value_column,
                hover_data=["bin", "bin_start", "bin_end", "share"],
                title=f"Fixed-width bin distribution: {metric}",
            )
            fig.update_traces(
                width=chart_bin_table["bar_width"],
                texttemplate="%{text:,}",
                textposition="outside",
                cliponaxis=False,
            )
            fig.update_xaxes(title_text="metric value")
            fig.add_vline(x=percentile_counts["p25"]["threshold"], line_color="green", line_width=3)
            fig.add_vline(x=percentile_counts["p85"]["threshold"], line_color="red", line_width=3)
            fig.add_vline(x=percentile_counts["custom"]["threshold"], line_color="orange", line_width=3, line_dash="dash")
            st.plotly_chart(fig, use_container_width=True)
    except ModuleNotFoundError:
        st.warning("Plotly is not installed; showing a basic Streamlit chart.")
        st.bar_chart(bin_table.set_index("bin")["count"] if not bin_table.empty else bin_table)
    st.subheader("Bin table")
    if not bin_table.empty:
        max_bins = len(bin_table)
        sum_mode = st.radio(
            "How to choose first bins",
            ["By bin count", "By store share"],
            horizontal=True,
            key=f"{key_prefix}_first_bins_mode_{metric}",
        )
        if sum_mode == "By store share":
            target_share_percent = st.number_input(
                "Target % of stores",
                min_value=0.1,
                max_value=100.0,
                value=30.0,
                step=0.1,
                key=f"{key_prefix}_first_bins_target_share_{metric}",
            )
            n_bins = first_bin_count_for_target_share(bin_table, target_share_percent / 100)
            previous_bins = first_bins_summary(numeric_metric, bin_table, n_bins - 1, store_series=store_series) if n_bins > 1 else None
            recommended_width = recommended_bin_width_for_target_share(
                numeric_metric,
                target_share_percent / 100,
                n_bins,
                bin_width,
                minimum=width_settings["minimum"],
            )
            st.caption(
                f"Selected {n_bins} first bins because this mode uses the first bin count that reaches at least "
                f"{target_share_percent:.1f}% of stores."
            )
            if previous_bins:
                st.caption(f"Previous {n_bins - 1} bins cover {previous_bins['store_share']:.1%} of stores.")
            if recommended_width is not None:
                rec_col, apply_col = st.columns([3, 1])
                rec_col.info(f"Recommended bin width for this target: {_format_setting_number(recommended_width)}")
                apply_col.button(
                    "Apply bin width",
                    key=f"{key_prefix}_apply_recommended_bin_width_{metric}",
                    on_click=set_session_value,
                    args=(bin_width_key, recommended_width),
                    help="Applies the recommended value to Bin width in chart settings.",
                )
        else:
            n_bins = st.number_input(
                "Sum first N bins",
                min_value=1,
                max_value=max_bins,
                value=min(3, max_bins),
                step=1,
                key=f"{key_prefix}_first_bins_count_{metric}",
            )
        first_bins = first_bins_summary(numeric_metric, bin_table, n_bins, store_series=store_series)
        sum_col1, sum_col2 = st.columns(2)
        sum_col1.metric("First bins used", first_bins["bins_used"])
        sum_col2.metric(
            "Stores in first bins",
            first_bins["store_sum"],
            f"{first_bins['store_share']:.1%} of stores",
            delta_color="off",
        )
    st.dataframe(bin_table, use_container_width=True)


def _render_kir_percentages_tab(filtered, selected_metric, filter_values=None):
    st.subheader("Проценты КИР")
    source = add_kir_percentage_columns(filtered)
    kir_columns = kir_metric_columns(source)
    base_columns = [column for column in PERCENT_BASE_COLUMNS if column in source.columns]
    if not kir_columns:
        st.info("Нет числовых КИР-показателей для расчета процентов.")
        return
    if not base_columns:
        st.info("Нет колонок Списания, Выручка или Свободный ТЗ для расчета процентов.")
        return

    default_metric = selected_metric if selected_metric in kir_columns else kir_columns[0]
    applied_settings = resolve_kir_percent_settings(
        st.session_state.get("kir_percent_settings"),
        kir_columns,
        base_columns,
        default_metric,
    )
    with st.form("kir_percent_settings_form"):
        draft_kir = st.selectbox(
            "КИР-показатель для анализа процентов",
            kir_columns,
            index=kir_columns.index(applied_settings["metric"]),
        )
        draft_base = st.radio(
            "С чем сравниваем КИР",
            base_columns,
            horizontal=True,
            index=base_columns.index(applied_settings["base"]),
        )
        if st.form_submit_button("Apply percentage settings"):
            applied_settings = {"metric": draft_kir, "base": draft_base}
            st.session_state["kir_percent_settings"] = applied_settings

    selected_kir = applied_settings["metric"]
    selected_base = applied_settings["base"]
    percent_metric = percentage_column_name(selected_kir, selected_base)
    if percent_metric not in source.columns:
        st.info(f"Не удалось рассчитать колонку: {percent_metric}")
        return

    st.caption(f"Формула: {selected_kir} / {selected_base} * 100. Значение 12.5 означает 12.5%.")
    st.subheader("Сводная таблица по суммам")
    summary = kir_percentage_summary(source, selected_kir)
    st.dataframe(format_kir_summary_display(summary), use_container_width=True)

    numeric_percent = pd.to_numeric(source[percent_metric], errors="coerce")
    _render_metric_analysis_tab(
        source,
        percent_metric,
        numeric_percent,
        filter_values=filter_values,
        title="Распределение процента по бинам",
        key_prefix="kir_percent",
        metric_label="процента КИР",
        is_percent_metric=True,
    )


def _render_group_comparison_tab(filtered, numeric_metric):
    st.subheader("Group comparison")
    group_options = [column for column in GROUP_COLUMNS if column in filtered.columns]
    if not group_options:
        st.info("No group columns found.")
        return

    group_col = st.selectbox("Group by", group_options)
    for network_name, grouped in group_comparison_tables(filtered, numeric_metric, group_col):
        if network_name is not None:
            st.markdown(network_brand_html(network_name), unsafe_allow_html=True)
        st.dataframe(grouped.head(1000), use_container_width=True)


def _render_relationships_tab(filtered, metric, numeric_metric):
    st.subheader("Poteri relationship analysis")
    available = [column for column in RELATIONSHIP_COLUMNS if column in filtered.columns]
    if not available:
        st.info("No poteri numeric columns found for relationship analysis.")
        return

    hide_outliers = st.checkbox(
        "Hide visual outliers, zeros and negatives",
        value=False,
        help="Only affects relationship charts. Keeps points where selected KIR metric and comparison metric are > 0, then applies percentile cutoff.",
    )
    outlier_percentile = st.slider(
        "Visible percentile cutoff",
        min_value=90,
        max_value=100,
        value=99,
        disabled=not hide_outliers,
        help="Only affects charts. Source rows and calculations are not deleted.",
    )

    try:
        import plotly.express as px
    except ModuleNotFoundError:
        st.warning("Plotly is not installed; relationship scatter plots are unavailable.")
        return

    networks = split_by_network(filtered.assign(_metric=numeric_metric))
    if not networks:
        st.info("No rows available for relationship analysis after filters.")
        return

    network_names = [name for name, _ in networks]
    stats_by_network = {}
    for network_name, network_df in networks:
        stats = calculate_relationship_stats(network_df, metric, available)
        stats_by_network[network_name] = stats
        with st.expander(f"Correlation stats: {network_name}", expanded=False):
            st.dataframe(prepare_correlation_display_stats(stats), use_container_width=True)
            st.markdown(render_correlation_interpretation_html(network_name, stats), unsafe_allow_html=True)

    comparison_html = render_network_correlation_comparison_html(stats_by_network)
    if comparison_html:
        st.markdown(comparison_html, unsafe_allow_html=True)

    network_by_name = {name: df for name, df in networks}
    for row in relationship_chart_rows(network_names, available):
        column = row["comparison"]
        st.markdown(relationship_heading_html(metric, column), unsafe_allow_html=True)
        chart_columns = st.columns(len(row["networks"]))
        for container, network_name in zip(chart_columns, row["networks"]):
            network_df = network_by_name[network_name]
            if hide_outliers:
                network_df = filter_visual_outliers(network_df, "_metric", column, quantile=outlier_percentile / 100)
            chart_df = sample_for_plot(network_df)
            with container:
                st.markdown(network_brand_html(network_name), unsafe_allow_html=True)
                fig = px.scatter(chart_df, x="_metric", y=column, opacity=0.38)
                fig.update_traces(
                    marker={
                        "color": network_chart_color(network_name),
                        "size": 5,
                        "line": {"width": 0},
                    }
                )
                st.plotly_chart(fig, use_container_width=True)
                if hide_outliers:
                    st.caption(f"Visual filter: x/y > 0 and P{outlier_percentile} cutoff; shown {len(chart_df):,} points.")


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


def format_kir_summary_amount(value):
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):,.0f}".replace(",", " ")


def format_kir_summary_percent(value):
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):,.1f}%".replace(",", " ")


def format_kir_summary_display(summary):
    display = summary.copy()
    for column in KIR_SUMMARY_AMOUNT_COLUMNS:
        if column in display.columns:
            display[column] = display[column].map(format_kir_summary_amount)
    for column in display.columns:
        if str(column).startswith("КИР / ") and str(column).endswith(", %"):
            display[column] = display[column].map(format_kir_summary_percent)
    return display


def resolve_kir_percent_settings(settings, kir_columns, base_columns, default_metric):
    metric = (settings or {}).get("metric")
    base = (settings or {}).get("base")
    if metric not in kir_columns:
        metric = default_metric if default_metric in kir_columns else kir_columns[0]
    if base not in base_columns:
        base = base_columns[0]
    return {"metric": metric, "base": base}


def main():
    _require_streamlit()
    st.set_page_config(page_title="KIR Dashboard", layout="wide")
    st.markdown(dashboard_css(), unsafe_allow_html=True)
    st.title("KIR Dashboard")

    is_running = st.session_state.get("pipeline_running", False)
    current_projects = project_select_options(list_projects(DATA_PROJECTS_DIR))

    st.sidebar.subheader("Project")
    if is_running:
        st.sidebar.warning(pipeline_status_text("active"))
        st.sidebar.button(
            pipeline_status_text("stop_button"),
            disabled=True,
            help=pipeline_status_text("stop_help"),
        )
        top_progress_bar = st.sidebar.progress(1, text=pipeline_status_text("preparing"))
        top_progress_text = st.sidebar.empty()
    else:
        top_progress_bar = None
        top_progress_text = None
        if st.sidebar.button("Create new project"):
            st.session_state["show_create_project"] = True

    if st.session_state.get("show_create_project") and not is_running:
        with st.sidebar.container(border=True):
            new_project_name = st.text_input("Project name", placeholder="003")
            if st.button("Save project"):
                try:
                    project_name = normalize_new_project_input(new_project_name)
                    create_project(project_name, base_dir=DATA_PROJECTS_DIR)
                    st.session_state["show_create_project"] = False
                    st.sidebar.success(f"Project created: {project_name}")
                    st.rerun()
                except Exception as exc:
                    st.sidebar.error(str(exc))

    selected_project = None
    if current_projects:
        selected_project = st.sidebar.selectbox("Selected project", current_projects, disabled=is_running)
        latest_run = latest_project_run_name(selected_project)
        if latest_run:
            st.sidebar.caption(f"Latest run: {latest_run}")
    else:
        st.sidebar.info("Create a project before uploading files or running the pipeline.")

    if selected_project:
        lock_status = project_run_lock_status(selected_project)
        pending_run = st.session_state.get("pending_pipeline_run")
        project_is_running = is_running or lock_status["locked"]

        if pending_run and pending_run["project"] == selected_project:
            routes = pending_run["routes"]
            lock_acquired = False
            progress_bar = top_progress_bar or st.sidebar.progress(1, text=pipeline_status_text("preparing"))
            progress_text = top_progress_text or st.sidebar.empty()
            progress_bar.progress(1, text=pipeline_status_text("preparing"))
            progress_text.caption(format_running_message(selected_project, routes))
            try:
                if not acquire_project_run_lock(selected_project):
                    st.warning(pipeline_status_text("already_running"))
                    st.session_state["pipeline_running"] = False
                    st.session_state.pop("pending_pipeline_run", None)
                    st.stop()
                lock_acquired = True
                project_is_running = True
                progress_bar.progress(2, text=pipeline_status_text("checking_uploads"))

                for route_name in routes:
                    kir_file = st.session_state.get(f"{route_name}_kir_upload")
                    poteri_file = st.session_state.get(f"{route_name}_poteri_upload")
                    if kir_file and poteri_file:
                        progress_bar.progress(
                            5,
                            text=f"{pipeline_status_text('saving_uploads')} {route_label(route_name)}",
                        )
                        save_uploaded_route_files(
                            selected_project,
                            route_name,
                            kir_file,
                            poteri_file,
                            base_dir=DATA_PROJECTS_DIR,
                        )
                    progress_bar.progress(8, text=f"Checking files for {route_label(route_name)}...")
                    if not project_route_uploads_exist(selected_project, route_name):
                        st.error(
                            f"Upload KIR and Poteri files for {route_label(route_name)} first, "
                            "or click Save uploaded files."
                        )
                        st.stop()

                progress_bar.progress(10, text=format_running_message(selected_project, routes))
                progress_text.caption(format_running_message(selected_project, routes))
                completed_steps = {"count": 0}
                total_steps = max(1, len(routes) * 9)

                def progress_callback(stage, message):
                    completed_steps["count"] += 1
                    value = pipeline_progress_value(completed_steps["count"], total_steps)
                    progress_bar.progress(value, text=message)
                    progress_text.caption(message)

                results = run_project_routes(
                    selected_project,
                    routes,
                    load_config(),
                    base_dir=DATA_PROJECTS_DIR,
                    progress_callback=progress_callback,
                )
                progress_bar.progress(100, text=pipeline_status_text("finished"))
                for result in results:
                    st.success(format_run_result(result))
                result_to_open = select_run_result_to_open(results, pending_run.get("open_route"))
                if result_to_open:
                    st.session_state["opened_run_dir"] = str(result_to_open["run_dir"])
            except Exception as exc:
                st.exception(exc)
            finally:
                st.session_state["pipeline_running"] = False
                st.session_state.pop("pending_pipeline_run", None)
                if lock_acquired:
                    release_project_run_lock(selected_project)
        elif pending_run:
            st.warning(pipeline_status_text("other_project"))
            st.stop()

        lock_status = project_run_lock_status(selected_project)
        project_is_running = st.session_state.get("pipeline_running", False) or lock_status["locked"]
        if lock_status["locked"] and not st.session_state.get("pipeline_running", False):
            st.sidebar.warning(pipeline_status_text("stale_lock"))
            if st.sidebar.button(pipeline_status_text("reset_lock_button")):
                release_project_run_lock(selected_project)
                st.rerun()

        with st.sidebar.expander("1. Upload files", expanded=False):
            if not should_render_upload_widgets(project_is_running):
                st.info(pipeline_status_text("upload_disabled"))
            else:
                if latest_run:
                    st.caption(f"Latest run: {latest_run}")
                route_mode = st.selectbox(
                    "Upload route mode",
                    ["route_1", "route_2", "both"],
                    format_func=route_label,
                    key="upload_route_mode",
                )
                for route_name in routes_for_ui_mode(route_mode):
                    route_display = route_label(route_name)
                    st.markdown(f"**{route_display}**")
                    manifest = load_upload_manifest(selected_project, route_name)
                    if manifest:
                        st.caption(
                            "Last upload: "
                            f"KIR `{manifest.get('kir_original_name', 'n/a')}`, "
                            f"Poteri `{manifest.get('poteri_original_name', 'n/a')}`, "
                            f"{manifest.get('saved_at', 'n/a')}"
                        )
                    kir_file = st.file_uploader(
                        f"KIR file for {route_display}",
                        type=allowed_upload_extensions(),
                        key=f"{route_name}_kir_upload",
                    )
                    poteri_file = st.file_uploader(
                        f"Poteri file for {route_display}",
                        type=allowed_upload_extensions(),
                        key=f"{route_name}_poteri_upload",
                    )
                    if st.button(
                        "Save uploaded files",
                        disabled=not (kir_file and poteri_file),
                        key=f"save_{route_name}",
                    ):
                        try:
                            result = save_uploaded_route_files(
                                selected_project,
                                route_name,
                                kir_file,
                                poteri_file,
                                base_dir=DATA_PROJECTS_DIR,
                            )
                            st.success(f"Saved uploads for {route_display}")
                            st.caption(f"KIR: {result['kir_path']}")
                            st.caption(f"Poteri: {result['poteri_path']}")
                            st.caption(f"Manifest: {result['manifest_path']}")
                        except Exception as exc:
                            st.error(str(exc))

        with st.sidebar.expander("2. Run pipeline", expanded=project_is_running):
            if project_is_running:
                st.info(pipeline_status_text("already_running"))
            open_after_both = st.radio(
                pipeline_status_text("open_after_both_label"),
                ["route_1", "route_2"],
                format_func=route_label,
                horizontal=True,
                key="open_route_after_both",
                disabled=project_is_running,
            )
            st.caption(pipeline_status_text("open_after_both_help"))
            st.button(
                f"Run {route_label('route_1')}",
                disabled=project_is_running,
                on_click=queue_pipeline_run,
                args=(selected_project, ["route_1"], "route_1"),
            )
            st.button(
                f"Run {route_label('route_2')}",
                disabled=project_is_running,
                on_click=queue_pipeline_run,
                args=(selected_project, ["route_2"], "route_2"),
            )
            st.button(
                f"Run {route_label('both')}",
                disabled=project_is_running,
                on_click=queue_pipeline_run,
                args=(selected_project, ["route_1", "route_2"], open_after_both),
            )

        with st.sidebar.expander("3. Open dashboard", expanded=True):
            st.caption(pipeline_status_text("open_dashboard_caption"))
            run_dirs = list_project_run_dirs(selected_project)
            if not run_dirs:
                st.info(pipeline_status_text("no_ready_runs"))
            else:
                selected_run = st.selectbox(
                    "Ready run",
                    run_dirs,
                    format_func=dashboard_run_label,
                    disabled=project_is_running,
                )
                if st.button("Open dashboard", disabled=project_is_running):
                    st.session_state["opened_run_dir"] = str(selected_run)

    legacy_run_dirs = list_legacy_run_dirs()
    if legacy_run_dirs:
        with st.sidebar.expander("Open CLI run (data/run_*)", expanded=False):
            st.caption("Use this only for runs created by python main.py outside the project UI.")
            selected_legacy_run = st.selectbox(
                "CLI run",
                legacy_run_dirs,
                format_func=dashboard_run_label,
                disabled=is_running,
            )
            if st.button("Open CLI dashboard", disabled=is_running):
                st.session_state["opened_run_dir"] = str(selected_legacy_run)

    opened_run_dir = st.session_state.get("opened_run_dir")
    if not opened_run_dir:
        st.info(pipeline_status_text("open_dashboard_first"))
        return
    run_dir = Path(opened_run_dir)
    if selected_project and DATA_PROJECTS_DIR in run_dir.parents:
        expected_project_dir = DATA_PROJECTS_DIR / selected_project
        if expected_project_dir not in run_dir.parents:
            st.info(pipeline_status_text("open_current_project"))
            return

    df = _load_run_dataframe(run_dir)
    if df is None:
        return
    df = add_kir_percentage_columns(df)

    metrics = sort_metric_columns(get_numeric_metric_columns(df))
    if not metrics:
        st.error("No numeric metric columns found.")
        return

    settings = st.session_state.get("dashboard_settings")
    if not settings or settings.get("run_dir") != str(run_dir):
        settings = {"run_dir": str(run_dir), "metric": metrics[0], "filters": {}}
        st.session_state["dashboard_settings"] = settings

    with st.sidebar.expander("4. Dashboard settings", expanded=True):
        st.caption("Choose metric and filters, then apply. This avoids rebuilding charts on every click.")
        with st.form("dashboard_settings_form"):
            current_metric = settings.get("metric", metrics[0])
            if current_metric not in metrics:
                current_metric = metrics[0]
            selected_metric = st.selectbox("Metric", metrics, index=metrics.index(current_metric))

            selected_filters = {}
            current_filters = settings.get("filters", {})
            for column in FILTER_COLUMNS:
                if column not in df.columns:
                    continue
                options = filter_options_for_column(df, column)
                current_selection = [value for value in current_filters.get(column, []) if value in options]
                format_func = format_week_label if column == WEEK_COL else str
                selected_filters[column] = st.multiselect(
                    filter_label(column),
                    options,
                    default=current_selection,
                    format_func=format_func,
                )

            if st.form_submit_button("Apply settings"):
                settings = {"run_dir": str(run_dir), "metric": selected_metric, "filters": selected_filters}
                st.session_state["dashboard_settings"] = settings

    metric = settings.get("metric", metrics[0])
    if metric not in metrics:
        metric = metrics[0]
    filtered = apply_filter_values(df, settings.get("filters", {}))
    numeric_metric = pd.to_numeric(filtered[metric], errors="coerce")

    screen = st.radio("Раздел анализа", DASHBOARD_SCREENS, horizontal=True)
    if screen == "1. Корреляции":
        _render_relationships_tab(filtered, metric, numeric_metric)
    elif screen == "2. Проценты КИР":
        _render_kir_percentages_tab(filtered, metric, settings.get("filters", {}))
    elif screen == "3. Распределение показателя":
        _render_metric_analysis_tab(filtered, metric, numeric_metric, settings.get("filters", {}))
    elif screen == "Сравнение групп":
        _render_group_comparison_tab(filtered, numeric_metric)
    elif screen == "Качество данных":
        _render_audit_tab(run_dir, filtered, numeric_metric)
    elif screen == "Проблемные строки":
        _render_problem_rows_tab(filtered)
    elif screen == "Данные":
        st.subheader("Пример отфильтрованных данных")
        st.dataframe(filtered.head(1000), use_container_width=True)


if __name__ == "__main__":
    main()
