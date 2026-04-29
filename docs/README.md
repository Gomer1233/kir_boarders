# KIR Data Pipeline

## Purpose

This project joins KIR source data with poteri data and produces auditable analytical outputs.
The main rule is simple: rows must not disappear silently during merge, transformation, or quality checks.

## Inputs

Route input folders are configured in `project_config.yaml`:

- `data/route_1/` uses merge key: week + TS + category + factory.
- `data/route_2/` uses merge key: week + TS + factory.

Each route expects one KIR file and one poteri file in its folder.

## Install

```powershell
pip install -r requirements.txt
```

## Run Pipeline

```powershell
python main.py route_1
python main.py route_2
python main.py both
```

`main_final_v3.py` is kept as a compatibility entrypoint, but `main.py` is the primary command.

## Outputs

Each route creates a new `data/run_N_route_X/` folder with these files:

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
- Zero KIR values are valid and must not be removed.
- Empty KIR metric values are not removed by the pipeline; analysts choose metrics in the dashboard.
- Outliers are not deleted automatically. They should be reviewed in the dashboard or handled by an explicit manual mode.

## Dashboard

Run:

```powershell
streamlit run dashboard_streamlit.py
```

The dashboard reads `final_clean_data.xlsx`, lets the analyst select the metric column, and shows:

- run selector;
- metric selector;
- filters by route dimensions and quality flags;
- row counts and data-quality cards;
- distribution charts;
- grouped statistics;
- problem rows with missing matches, missing keys, or duplicate keys.

## Configuration Notes

`target_col` is intentionally not part of the pipeline configuration. The dashboard chooses the analytical metric dynamically from numeric columns in `final_clean_data.xlsx`.

Legacy entrypoints were moved to `archive/legacy_entrypoints/` to reduce the risk of running stale scripts.
