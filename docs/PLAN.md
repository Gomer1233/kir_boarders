# Current Implementation Plan

## Goal

Implement a loss-safe KIR data pipeline where raw merge output is always available for audit and the main analytical output keeps rows with explicit flags instead of silently deleting data.

## Implemented Architecture

- Primary CLI: `python main.py route_1|route_2|both`.
- Compatibility CLI: `python main_final_v3.py route_1|route_2|both`.
- Dashboard CLI: `streamlit run dashboard_streamlit.py`.
- Legacy broken entrypoints are archived under `archive/legacy_entrypoints/`.

## Route Rules

| Route | KIR input | Poteri input | Merge key |
| --- | --- | --- | --- |
| `route_1` | `data/route_1/kir_with_cats.xlsx` | `data/route_1/poteri_with_cats.xlsx` | week + TS + category + factory |
| `route_2` | `data/route_2/kir_without_cats.xlsx` | `data/route_2/poteri_without_cats.xlsx` | week + TS + factory |

## Output Contract

Every run folder must contain:

- `merged_raw.xlsx`: raw audit merge.
- `final_clean_data.xlsx`: main analytical file with quality flags.
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
- Keep outlier handling out of automatic pipeline deletion.
- Keep `target_col` out of the pipeline; metric selection belongs to the dashboard.

## Verification Checklist

Run before considering the implementation complete:

```powershell
python -m pytest -q
python -m py_compile main.py main_final_v3.py dashboard_streamlit.py scripts\merge_data_v3.py scripts\quality_flags.py scripts\pipeline.py
python main.py route_1
python main.py route_2
```

Then verify latest route runs satisfy:

```text
raw_row_count == final_row_count + excluded_row_count
```

## Remaining Product Decisions

- Whether to add an explicit manual outlier review/export workflow.
- Whether to persist dashboard UI settings between sessions.
- Whether to add a richer dashboard tab for correlations after the base audit workflow is stable.
