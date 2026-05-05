# KIR Data Pipeline

## Purpose

This project joins KIR source data with poteri data and produces auditable analytical outputs.
The main rule is simple: rows must not disappear silently during merge, transformation, or quality checks.

The current primary workflow is the Streamlit project UI. The CLI is still supported for direct runs and smoke checks.

## Main Workflow: Streamlit Project UI

Start the local app:

```powershell
streamlit run dashboard_streamlit.py
```

In the sidebar:

1. Create or select a project, for example `003`, `020`, `950`.
2. Upload source files in `1. Upload files`.
3. Run one route or both routes in `2. Run pipeline`.
4. Open a completed run in `3. Open dashboard`.

Projects are stored under:

```text
data/projects/<project_name>/
```

Uploaded files are saved per project and route under:

```text
data/projects/<project_name>/uploads/route_1/
data/projects/<project_name>/uploads/route_2/
```

Only `.xlsx` uploads are supported. Uploaded files may have any original name; the app saves them internally as stable source files and records original names in `upload_manifest.json`.

Uploading new files for the same project and route replaces the previous uploaded source files for that route. Old analytical results are not overwritten; every pipeline run creates a new run folder.

## Routes

| Route | UI label | Merge key | Use case |
| --- | --- | --- | --- |
| `route_1` | `Route 1: Магазины и Категории` | week + TS + category + factory | Analysis by stores and categories. |
| `route_2` | `Route 2: Магазины` | week + TS + factory | Analysis by stores without category split. |

For direct CLI runs, fixed input folders are configured in `project_config.yaml`:

| Route | KIR input | Poteri input |
| --- | --- | --- |
| `route_1` | `data/route_1/kir_with_cats.xlsx` | `data/route_1/poteri_with_cats.xlsx` |
| `route_2` | `data/route_2/kir_without_cats.xlsx` | `data/route_2/poteri_without_cats.xlsx` |

## Install

```powershell
pip install -r requirements.txt
```

## Run Pipeline From CLI

```powershell
python main.py route_1
python main.py route_2
python main.py both
```

`main_final_v3.py` is kept as a compatibility entrypoint, but `main.py` is the primary command.

CLI runs write to `data/run_N_route_X/`. The dashboard can still open completed CLI runs from the advanced `Open CLI run (data/run_*)` section when such folders exist.

## Outputs

Project UI runs create folders like:

```text
data/projects/<project_name>/runs/run_001_route_1/
data/projects/<project_name>/runs/run_002_route_2/
```

CLI runs create folders like:

```text
data/run_17_route_2/
```

Each run folder contains:

| File | Purpose |
| --- | --- |
| `merged_raw.xlsx` | Raw audit merge, before quality filtering or optimization. |
| `final_clean_data.xlsx` | Main analytical file. Rows are preserved and quality issues are represented as flags. |
| `excluded_rows.xlsx` | Structurally unrepresentable rows only. Normally empty. |
| `merge_diagnostics.md` | Merge counts, duplicate-key diagnostics, and audit invariant result. |

Required audit invariant:

```text
final_row_count + excluded_row_count == raw_row_count
```

## Data Policy

- Missing poteri matches stay in `final_clean_data.xlsx` with `has_poteri_match=false`.
- Missing merge keys stay in `final_clean_data.xlsx` with `has_missing_key=true` when they can be represented.
- Missing-key KIR rows must not match missing-key poteri rows.
- Zero KIR values are valid and must not be removed by the pipeline.
- Empty KIR metric values are not removed by the pipeline; analysts choose metrics in the dashboard.
- Source total rows are flagged with `is_total_row` / `quality_status`, not silently deleted from raw audit data.
- Outliers are not deleted automatically. Dashboard screens can hide visual outliers for analysis without changing source files.

## KIR Percent Columns

`final_clean_data.xlsx` includes calculated percentage columns for every numeric KIR metric:

```text
<KIR metric> / Списания, %
<KIR metric> / Выручка, %
<KIR metric> / Свободный ТЗ, %
```

Calculation rule:

```text
KIR percent = KIR value / base metric value * 100
```

If the base metric is empty or zero, the percentage value is left empty. This avoids fake infinite or misleading percentages.

## Dashboard Screens

The dashboard opens `final_clean_data.xlsx`, lets the analyst select a KIR metric, and applies filters only after `Apply settings`.

Current analysis flow:

1. `Корреляции` - compare selected KIR metric with writeoffs, revenue, and free stock. Uses Pearson and Spearman, with business interpretation based mainly on Spearman because it is more stable for non-linear ranked relationships.
2. `КИР vs Метрики` - analyze KIR as a percentage of writeoffs, revenue, or free stock. Includes summary by totals and bin distribution for the selected percentage.
3. `Распределение показателя` - analyze the selected KIR metric itself by fixed-width bins and percentiles.
4. `Сравнение групп` - compare grouped statistics. Category grouping is split by TS when both networks are selected; factory grouping is intentionally not exposed because it can overload the dashboard.
5. `Качество данных` - audit counts, route/run info, diagnostics, and output file download buttons.
6. `Проблемные строки` - rows with missing matches, missing keys, duplicate keys, or quality warnings.
7. `Данные` - filtered data preview.

The dashboard header shows the selected project and route. For project runs, the header route toggle can switch between the latest ready `route_1` and `route_2` runs when both exist.

## Bin Width Recommendation

The bin table can choose first bins either by explicit bin count or by target store share.

When using target store share, `Apply bin width` applies a recommended bin width that aligns the bin grid with the requested share as closely as possible. Exact percentages are not always possible because:

- stores are counted as whole rows/stores;
- many stores may have identical metric values;
- fixed-width bins can only approximate a target share.

The recommendation uses the same bin grid logic as the chart, including negative metric values.

## Pipeline Run Locking

Within one Streamlit app process, only one pipeline run should execute at a time. While a run is active, upload/run controls are disabled for the selected project and a lock file prevents a second run for the same project.

If a run is interrupted and the lock remains, use the UI option to clear the stale lock after confirming no pipeline is running.

## Multiple Browser Tabs and Parallel Work

Opening the same Streamlit URL in several browser tabs uses the same Streamlit server process. Heavy Excel loading or a pipeline run in one tab can slow dashboard interactions in another tab.

For real parallel work, start separate Streamlit processes on different ports:

```powershell
streamlit run dashboard_streamlit.py --server.port 8501
streamlit run dashboard_streamlit.py --server.port 8502
```

Each process has its own UI session, but they still share the same project files under `data/projects/`. Avoid running the same project simultaneously in different processes.

## Configuration Notes

`target_col` is intentionally not part of the pipeline configuration. The dashboard chooses the analytical metric dynamically from KIR metric columns in `final_clean_data.xlsx`.

Legacy entrypoints were moved to `archive/legacy_entrypoints/` to reduce the risk of running stale scripts.
