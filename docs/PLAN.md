# Current Implementation Plan

## Goal

Maintain a loss-safe KIR data pipeline and local Streamlit analytical dashboard.

The pipeline must always keep a raw audit merge and produce an analytical final file with explicit flags instead of silently deleting rows. The dashboard is the primary user workflow for project-based file upload, route execution, and analysis.

## Implemented Architecture

- Primary UI: `streamlit run dashboard_streamlit.py`.
- Primary CLI: `python main.py route_1|route_2|both`.
- Compatibility CLI: `python main_final_v3.py route_1|route_2|both`.
- Legacy broken entrypoints are archived under `archive/legacy_entrypoints/`.

## Storage Model

Project UI data:

```text
data/projects/<project_name>/
  uploads/
    route_1/
      kir_source.xlsx
      poteri_source.xlsx
      upload_manifest.json
    route_2/
      kir_source.xlsx
      poteri_source.xlsx
      upload_manifest.json
  runs/
    run_001_route_1/
    run_002_route_2/
```

CLI data:

```text
data/run_N_route_X/
```

Project uploads replace previous source files for the same project and route. Run folders are append-only: each pipeline execution creates a new run folder.

## Route Rules

| Route | UI label | KIR input for CLI | Poteri input for CLI | Merge key |
| --- | --- | --- | --- | --- |
| `route_1` | `Route 1: Магазины и Категории` | `data/route_1/kir_with_cats.xlsx` | `data/route_1/poteri_with_cats.xlsx` | week + TS + category + factory |
| `route_2` | `Route 2: Магазины` | `data/route_2/kir_without_cats.xlsx` | `data/route_2/poteri_without_cats.xlsx` | week + TS + factory |

Only `.xlsx` uploads are supported in the project UI.

## Output Contract

Every completed run folder must contain:

- `merged_raw.xlsx`: raw audit merge.
- `final_clean_data.xlsx`: main analytical file with quality flags and KIR percentage columns.
- `excluded_rows.xlsx`: structurally unrepresentable rows only.
- `merge_diagnostics.md`: counts and merge diagnostics.

Required invariant:

```text
final_row_count + excluded_row_count == raw_row_count
```

## Data Safety Rules

- Do not drop rows because of zero metric values.
- Do not drop rows because poteri is missing.
- Keep missing-key KIR rows with `has_missing_key=true` when representable.
- Prevent pandas null-key matching by excluding missing-key rows from the matching part of merge.
- Mark duplicate KIR and poteri keys with flags after merge expansion.
- Keep source total rows flagged, not silently hidden from audit outputs.
- Keep outlier handling out of automatic pipeline deletion.
- Keep `target_col` out of the pipeline; metric selection belongs to the dashboard.

## Calculated KIR Percentages

For every numeric KIR metric, `final_clean_data.xlsx` should include:

```text
<KIR metric> / Списания, %
<KIR metric> / Выручка, %
<KIR metric> / Свободный ТЗ, %
```

Calculation rule:

```text
KIR percent = KIR value / base metric value * 100
```

If the base metric is empty or zero, the percentage result is empty.

Dashboard filters on the `КИР vs Метрики` screen may exclude zero or negative KIR/base values for analysis, but these filters must not mutate source files.

## Dashboard Contract

The dashboard should expose these sections:

1. `Корреляции` - relationship analysis between selected KIR metric and poteri metrics. Spearman is the primary business strength indicator; Pearson is shown as an additional linearity check.
2. `КИР vs Метрики` - percentage analysis of KIR relative to writeoffs, revenue, or free stock.
3. `Распределение показателя` - distribution of the selected KIR metric by bins and percentiles.
4. `Сравнение групп` - grouped comparison. Category grouping splits by TS when both networks are selected; factory grouping is not exposed.
5. `Качество данных` - diagnostics and downloadable run files.
6. `Проблемные строки` - quality-warning rows.
7. `Данные` - filtered data preview.

Dashboard controls should avoid rebuilding heavy charts on every minor filter edit; user-facing filters should use explicit apply actions where practical.

## Current UX Decisions

- Header title is project-specific: `Дашборд <project_name>`.
- Header includes a route toggle for the latest ready project runs by route.
- The header is intended to stay visible while scrolling.
- Project UI disables upload/run controls while a pipeline run is active.
- `Run Both routes` lets the user choose which route to open after the run finishes.
- Existing CLI runs can be opened from the advanced `Open CLI run (data/run_*)` section when completed run folders exist.

## Verification Checklist

Run before considering implementation complete:

```powershell
python -m pytest -q
$files = @('main.py','main_final_v3.py','dashboard_streamlit.py') + (Get-ChildItem scripts -Filter *.py | ForEach-Object { $_.FullName })
python -m py_compile @files
```

Optional data smoke, when source files are present:

```powershell
python main.py route_1
python main.py route_2
```

Then verify latest route runs satisfy:

```text
raw_row_count == final_row_count + excluded_row_count
```

## Known Operational Notes

- A single Streamlit process can become slow if one tab is loading a large Excel file while another tab is running the pipeline.
- For parallel dashboard usage, start separate Streamlit processes on different ports, but avoid running the same project concurrently.
- If a pipeline is interrupted and leaves a stale project lock, clear the lock only after confirming no run is still active.

## Remaining Product Decisions

- Whether to add an explicit manual outlier review/export workflow.
- Whether to persist dashboard UI settings between sessions.
- Whether to add an AI-generated analytical summary after the dashboard calculations are stable enough to trust.
