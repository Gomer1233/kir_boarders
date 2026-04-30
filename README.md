# KIR Boarders

Pipeline and Streamlit dashboard for joining KIR source files with Poteri data, checking merge quality, and analyzing KIR metrics by route.

## Setup

```powershell
cd D:\projects\kir_boarders_project_ui_runner
pip install -r requirements.txt
```

## Run With UI

Use the Streamlit app for the normal workflow: create/select a project, upload files, run one or both routes, then open the dashboard.

```powershell
python -m streamlit run dashboard_streamlit.py
```

In the sidebar:

1. Create or select a project.
2. Upload source files.
3. Run pipeline for one route or both routes.
4. Open the generated dashboard run.

The UI also has `Open CLI run (data/run_*)` for older runs created from the command line.

## Run Pipeline From Console

```powershell
python main.py route_1
python main.py route_2
```

Routes:

- `route_1`: Магазины и Категории, merge key is week + TS + category + plant.
- `route_2`: Магазины, merge key is week + TS + plant.

Run both routes by executing both commands one after another.

## Output Files

Project UI runs are saved under:

```text
data/projects/<project>/runs/<run_name>/
```

CLI runs are saved under:

```text
data/run_*/
```

Main files:

- `merged_raw.xlsx`: raw merge result for audit/comparison.
- `final_clean_data.xlsx`: main dashboard input; rows are kept with quality flags instead of being silently deleted.
- `merge_diagnostics.md`: merge and row-count diagnostics.

## Dashboard Notes

- Metric selection is done in the dashboard, not in the pipeline.
- Week filter is shown as `Y2026 W08`.
- Plant is not exposed as a dashboard filter because it can contain too many values.
- Correlation tables include Pearson, Spearman, business-readable strength, and interpretation text.

