# KIR Loss-Safe Pipeline and Streamlit Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the KIR processing flow so data is never silently lost: every run produces an immutable raw merge, a flagged analytical final file, diagnostics, and a Streamlit dashboard that lets the user choose the metric interactively.

**Architecture:** The pipeline becomes a data-preparation layer: normalize keys, merge KIR with poteri, add audit/quality flags, and write route-scoped run artifacts. The dashboard becomes the analytical layer: open `final_clean_data.xlsx`, choose numeric metrics dynamically, filter, plot, compare, and export views. `target_col` is removed from required pipeline logic.

**Tech Stack:** Python 3.11, pandas, numpy, openpyxl, PyYAML, pytest, Streamlit, Plotly.

---

## Current Approved Spec

Use this spec as the source of truth:

- `docs/superpowers/specs/2026-04-29-kir-data-pipeline-dashboard-design.md`

Key implementation constraints:

- `final_clean_data.xlsx` is the main working output.
- `merged_raw.xlsx` is required audit output and must not be overwritten by cleaning/transformation.
- Pipeline must not require or filter by `target_col`.
- Zero values are valid.
- Rows without poteri match remain in final data with `has_poteri_match=false`.
- Rows with missing merge keys remain in final data with `has_missing_key=true` when representable.
- Outliers are not removed by default and are normally calculated in dashboard based on the selected metric.
- Streamlit replaces Tkinter for the analytical dashboard.

---

## File Structure

- Modify: `main_final_v3.py`
  - Keep working during migration, but refactor around loss-safe route execution.
- Modify: `main.py`
  - Supported CLI wrapper around the final pipeline entrypoint.
- Create: `scripts/pipeline.py`
  - Route config, run directory creation, orchestration, artifact paths, diagnostics.
- Create: `scripts/merge_data_v3.py`
  - Loss-safe merge, source row IDs, key normalization, merge indicators, duplicate diagnostics.
- Create: `scripts/quality_flags.py`
  - Adds quality flags without deleting rows.
- Create: `dashboard_streamlit.py`
  - Streamlit dashboard over `final_clean_data.xlsx` and `merged_raw.xlsx`.
- Modify: `project_config.yaml`
  - Remove required `target_col`; add dashboard and optional outlier config.
- Modify: `scripts/merge_data.py`
  - Compatibility wrapper to expose the new merge function or archive if unused.
- Archive: `main_automated.py`, `main_final.py`, `main_final_v2.py`, `main_new.py`
  - Move to `archive/legacy_entrypoints/` or replace with explicit deprecation shims.
- Create: `.gitignore`
  - Ignore generated runs, caches, logs, temporary Excel files.
- Create: `requirements.txt`
  - Declare runtime/test/dashboard dependencies.
- Add tests: `tests/`
  - Unit tests for normalization, merge invariants, quality flags, CLI behavior, dashboard helpers.

---

### Task 1: Repository Hygiene and Entrypoint Migration

**Files:**
- Create: `.gitignore`
- Create: `requirements.txt`
- Modify: `main.py`
- Modify: `scripts/merge_data.py`
- Move: `main_automated.py`, `main_final.py`, `main_final_v2.py`, `main_new.py` to `archive/legacy_entrypoints/`
- Test: `tests/test_entrypoints.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_entrypoints.py`:

```python
import importlib
import py_compile
from pathlib import Path


def test_main_wrapper_imports():
    importlib.import_module("main")


def test_supported_pipeline_entrypoint_imports():
    importlib.import_module("main_final_v3")


def test_supported_python_files_compile():
    for path in [Path("main.py"), Path("main_final_v3.py"), Path("scripts/merge_data.py")]:
        py_compile.compile(str(path), doraise=True)
```

- [ ] **Step 2: Run tests and observe current failure**

Run:

```powershell
python -m pytest tests\test_entrypoints.py -q
```

Expected before fix: import/compile failures may appear because `main.py` is empty, legacy imports are inconsistent, and dashboard dependency may be missing.

- [ ] **Step 3: Add `.gitignore`**

Create `.gitignore`:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/

# Generated run artifacts
data/run_*/
logs/processing_log_*.md
logs/*.log

# Temporary Excel files
~$*.xlsx
*.tmp.xlsx

# Local Streamlit state
.streamlit/secrets.toml
```

- [ ] **Step 4: Add dependencies**

Create `requirements.txt`:

```text
numpy
openpyxl
pandas
plotly
PyYAML
pytest
streamlit
```

- [ ] **Step 5: Make `main.py` the supported wrapper**

Replace `main.py`:

```python
from main_final_v3 import main


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Archive broken legacy entrypoints**

Run:

```powershell
New-Item -ItemType Directory -Force archive\legacy_entrypoints
Move-Item main_automated.py,main_final.py,main_final_v2.py,main_new.py archive\legacy_entrypoints\
```

If moving files breaks current tests, update tests to compile only supported entrypoints.

- [ ] **Step 7: Replace old `scripts/merge_data.py` wrapper**

Replace `scripts/merge_data.py`:

```python
from scripts.merge_data_v3 import merge_route_data


__all__ = ["merge_route_data"]
```

- [ ] **Step 8: Verify**

Run:

```powershell
python -m pytest tests\test_entrypoints.py -q
python -m py_compile main.py main_final_v3.py scripts\merge_data.py
```

Expected: tests pass and only supported files compile.

---

### Task 2: Robust Week Normalization

**Files:**
- Create: `scripts/merge_data_v3.py`
- Test: `tests/test_merge_data_v3.py`

- [ ] **Step 1: Write failing tests for week normalization**

Create `tests/test_merge_data_v3.py`:

```python
import pytest

from scripts.merge_data_v3 import normalize_week


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (202603, "202603"),
        (202603.0, "202603"),
        ("202603", "202603"),
        ("202603.0", "202603"),
        ("2026/03", "202603"),
        ("2026/3", "202603"),
        ("2026 03", "202603"),
    ],
)
def test_normalize_week_supported_formats(value, expected):
    assert normalize_week(value) == expected


@pytest.mark.parametrize("value", [None, "", "abc", "202", "2026/abc"])
def test_normalize_week_invalid_values(value):
    assert normalize_week(value) is None
```

- [ ] **Step 2: Run test and confirm missing implementation**

Run:

```powershell
python -m pytest tests\test_merge_data_v3.py -q
```

Expected: import fails until `scripts/merge_data_v3.py` exists.

- [ ] **Step 3: Implement normalization**

Create `scripts/merge_data_v3.py` with this initial content:

```python
import re

import pandas as pd


def normalize_week(value):
    if pd.isna(value):
        return None

    if isinstance(value, float) and value.is_integer():
        value = int(value)

    text = str(value).strip()
    if not text:
        return None

    full_match = re.fullmatch(r"(\d{6})(?:\.0+)?", text)
    if full_match:
        return full_match.group(1)

    split_match = re.fullmatch(r"(\d{4})\D+(\d{1,2})", text)
    if split_match:
        return f"{split_match.group(1)}{int(split_match.group(2)):02d}"

    digits = re.sub(r"\D", "", text)
    if len(digits) == 6:
        return digits
    return None
```

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest tests\test_merge_data_v3.py -q
```

Expected: all normalization tests pass.

---

### Task 3: Loss-Safe Raw Merge With Audit IDs

**Files:**
- Modify: `scripts/merge_data_v3.py`
- Test: `tests/test_merge_data_v3.py`

- [ ] **Step 1: Add failing synthetic merge tests**

Append to `tests/test_merge_data_v3.py`:

```python
import pandas as pd

from scripts.merge_data_v3 import merge_route_data


def test_merge_preserves_all_kir_rows_and_marks_poteri_match(tmp_path):
    kir = pd.DataFrame(
        {
            "НеделяГод": [202603, 202603],
            "ТС": ["A", "A"],
            "Категория": ["C", "C"],
            "Завод": ["S1", "S2"],
            "КИР-950": [0, 10],
        }
    )
    poteri = pd.DataFrame(
        {
            "Неделя": ["2026/03"],
            "Торговая сеть": ["A"],
            "Категория": ["C"],
            "Завод": ["S1"],
            "Списание без НДС (Итог) по B06, руб": [100],
            "Выручка, руб": [1000],
            "Свободно используемый товарный запас без НДС, руб": [50],
        }
    )

    result, diagnostics = merge_route_data(
        kir,
        poteri,
        merge_key=["НеделяГод", "ТС", "Категория", "Завод"],
        poteri_rename_map={
            "Неделя": "НеделяГод",
            "Торговая сеть": "ТС",
            "Списание без НДС (Итог) по B06, руб": "Списания",
            "Выручка, руб": "Выручка",
            "Свободно используемый товарный запас без НДС, руб": "Свободный ТЗ",
        },
    )

    assert len(result) == 2
    assert result["source_row_id"].tolist() == [1, 2]
    assert result["has_poteri_match"].tolist() == [True, False]
    assert result["КИР-950"].tolist() == [0, 10]
    assert diagnostics["kir_input_rows"] == 2
    assert diagnostics["raw_row_count"] == 2
    assert diagnostics["rows_without_poteri_match"] == 1
```

```python
def test_missing_key_rows_do_not_match_each_other():
    kir = pd.DataFrame(
        {
            "НеделяГод": [None],
            "ТС": ["A"],
            "Категория": ["C"],
            "Завод": ["S1"],
            "КИР-950": [10],
        }
    )
    poteri = pd.DataFrame(
        {
            "Неделя": [None],
            "Торговая сеть": ["A"],
            "Категория": ["C"],
            "Завод": ["S1"],
            "Списание без НДС (Итог) по B06, руб": [100],
        }
    )

    result, diagnostics = merge_route_data(
        kir,
        poteri,
        merge_key=["НеделяГод", "ТС", "Категория", "Завод"],
        poteri_rename_map={
            "Неделя": "НеделяГод",
            "Торговая сеть": "ТС",
            "Списание без НДС (Итог) по B06, руб": "Списания",
        },
    )

    assert len(result) == 1
    assert result.loc[0, "has_missing_key"]
    assert not result.loc[0, "has_poteri_match"]
    assert diagnostics["rows_without_poteri_match"] == 1
```

```python
def test_duplicate_poteri_keys_can_multiply_rows_and_duplicate_flags_still_work():
    kir = pd.DataFrame(
        {
            "НеделяГод": [202603],
            "ТС": ["A"],
            "Категория": ["C"],
            "Завод": ["S1"],
            "КИР-950": [10],
        }
    )
    poteri = pd.DataFrame(
        {
            "Неделя": ["2026/03", "2026/03"],
            "Торговая сеть": ["A", "A"],
            "Категория": ["C", "C"],
            "Завод": ["S1", "S1"],
            "Списание без НДС (Итог) по B06, руб": [100, 200],
        }
    )

    result, diagnostics = merge_route_data(
        kir,
        poteri,
        merge_key=["НеделяГод", "ТС", "Категория", "Завод"],
        poteri_rename_map={
            "Неделя": "НеделяГод",
            "Торговая сеть": "ТС",
            "Списание без НДС (Итог) по B06, руб": "Списания",
        },
    )

    assert len(result) == 2
    assert result["source_row_id"].tolist() == [1, 1]
    assert result["has_duplicate_poteri_key"].tolist() == [True, True]
    assert diagnostics["raw_row_count"] == 2
    assert diagnostics["duplicate_poteri_keys"]
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests\test_merge_data_v3.py -q
```

Expected: `merge_route_data` is not implemented.

- [ ] **Step 3: Implement `merge_route_data()`**

Add to `scripts/merge_data_v3.py`:

```python
def _normalize_key_columns(df, key_columns):
    result = df.copy()
    for column in key_columns:
        if column not in result.columns:
            result[column] = pd.NA
        if column == "НеделяГод":
            result[column] = result[column].apply(normalize_week)
        else:
            result[column] = result[column].astype("string").str.strip()
            result.loc[result[column].isin(["", "<NA>", "nan", "None"]), column] = pd.NA
    return result


def _duplicate_summary(df, key_columns):
    duplicated = df[df.duplicated(key_columns, keep=False)]
    if duplicated.empty:
        return []
    grouped = duplicated.groupby(key_columns, dropna=False).size().reset_index(name="count")
    return grouped.to_dict("records")


def merge_route_data(kir_df, poteri_df, merge_key, poteri_rename_map):
    kir = kir_df.copy()
    kir.insert(0, "source_row_id", range(1, len(kir) + 1))

    poteri = poteri_df.rename(columns=poteri_rename_map).copy()

    kir = _normalize_key_columns(kir, merge_key)
    poteri = _normalize_key_columns(poteri, merge_key)
    kir["has_missing_key"] = kir[merge_key].isna().any(axis=1)
    poteri["has_missing_key"] = poteri[merge_key].isna().any(axis=1)

    poteri_value_columns = [
        column for column in ["Списания", "Выручка", "Свободный ТЗ"] if column in poteri.columns
    ]
    poteri_merge_columns = merge_key + poteri_value_columns

    # pandas can match NA keys with each other. Split missing-key rows out so they never receive a false poteri match.
    kir_matchable = kir[~kir["has_missing_key"]].copy()
    kir_missing_key = kir[kir["has_missing_key"]].copy()
    poteri_matchable = poteri[~poteri["has_missing_key"]].copy()

    matched = kir_matchable.merge(
        poteri_matchable[poteri_merge_columns],
        on=merge_key,
        how="left",
        indicator=True,
    )
    matched["has_poteri_match"] = matched["_merge"].eq("both")
    matched = matched.drop(columns=["_merge"])

    for column in poteri_value_columns:
        kir_missing_key[column] = pd.NA
    kir_missing_key["has_poteri_match"] = False

    merged = pd.concat([matched, kir_missing_key], ignore_index=True, sort=False)
    merged = merged.sort_values("source_row_id", kind="stable").reset_index(drop=True)

    merged["missing_key_columns"] = merged[merge_key].isna().apply(
        lambda row: ",".join(row.index[row].tolist()), axis=1
    )

    duplicate_kir_keys = _duplicate_summary(kir, merge_key)
    duplicate_poteri_keys = _duplicate_summary(poteri, merge_key)
    duplicate_kir_key_set = {
        tuple(row[column] for column in merge_key) for row in duplicate_kir_keys
    }
    duplicate_poteri_key_set = {
        tuple(row[column] for column in merge_key) for row in duplicate_poteri_keys
    }
    merged_key_tuples = merged[merge_key].apply(tuple, axis=1)
    merged["has_duplicate_kir_key"] = merged_key_tuples.isin(duplicate_kir_key_set)
    merged["has_duplicate_poteri_key"] = merged_key_tuples.isin(duplicate_poteri_key_set)

    diagnostics = {
        "kir_input_rows": int(len(kir_df)),
        "poteri_input_rows": int(len(poteri_df)),
        "raw_row_count": int(len(merged)),
        "rows_with_poteri_match": int(merged["has_poteri_match"].sum()),
        "rows_without_poteri_match": int((~merged["has_poteri_match"]).sum()),
        "missing_key_rows": int(merged["has_missing_key"].sum()),
        "duplicate_kir_keys": duplicate_kir_keys,
        "duplicate_poteri_keys": duplicate_poteri_keys,
        "merge_key": merge_key,
    }
    return merged, diagnostics
```

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest tests\test_merge_data_v3.py -q
```

Expected: raw merge preserves all KIR rows and marks missing poteri matches.

---

### Task 4: Quality Flags Without Row Deletion

**Files:**
- Create: `scripts/quality_flags.py`
- Test: `tests/test_quality_flags.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_quality_flags.py`:

```python
import pandas as pd

from scripts.quality_flags import add_quality_flags


def test_quality_flags_do_not_drop_rows():
    df = pd.DataFrame(
        {
            "source_row_id": [1, 2, 3],
            "has_poteri_match": [True, False, True],
            "has_missing_key": [False, False, True],
            "КИР-950, шт": [0, 5, None],
            "Списания": [0, 10, None],
            "Выручка": [100, 0, None],
            "Свободный ТЗ": [5, 0, None],
        }
    )

    result = add_quality_flags(df)

    assert len(result) == 3
    assert bool(result.loc[0, "has_zero_kir_units"])
    assert bool(result.loc[0, "has_zero_writeoffs"])
    assert bool(result.loc[1, "has_zero_revenue"])
    assert bool(result.loc[1, "has_zero_stock"])
    assert result.loc[1, "quality_status"] == "warning"
    assert result.loc[2, "quality_status"] == "warning"
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests\test_quality_flags.py -q
```

Expected: module is missing.

- [ ] **Step 3: Implement `add_quality_flags()`**

Create `scripts/quality_flags.py`:

```python
import pandas as pd


def _has_zero(df, candidates):
    existing = [column for column in candidates if column in df.columns]
    if not existing:
        return pd.Series(False, index=df.index)
    numeric = df[existing].apply(pd.to_numeric, errors="coerce")
    return numeric.eq(0).any(axis=1)


def add_quality_flags(df):
    result = df.copy()

    result["has_zero_writeoffs"] = _has_zero(result, ["Списания"])
    result["has_zero_revenue"] = _has_zero(result, ["Выручка"])
    result["has_zero_stock"] = _has_zero(result, ["Свободный ТЗ"])
    result["has_zero_kir_units"] = _has_zero(
        result,
        [column for column in result.columns if column.startswith("КИР-") and "шт" in column],
    )

    warning_reasons = []
    for _, row in result.iterrows():
        reasons = []
        if not bool(row.get("has_poteri_match")):
            reasons.append("no_poteri_match")
        if bool(row.get("has_missing_key")):
            reasons.append("missing_merge_key")
        if bool(row.get("has_duplicate_kir_key")):
            reasons.append("duplicate_kir_key")
        if bool(row.get("has_duplicate_poteri_key")):
            reasons.append("duplicate_poteri_key")
        warning_reasons.append(",".join(reasons))

    result["quality_reason"] = warning_reasons
    result["quality_status"] = result["quality_reason"].apply(lambda value: "ok" if not value else "warning")
    return result
```

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest tests\test_quality_flags.py -q
```

Expected: no rows are dropped; flags are set.

---

### Task 5: Route Pipeline Artifacts and Diagnostics

**Files:**
- Create: `scripts/pipeline.py`
- Modify: `main_final_v3.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing artifact test**

Create `tests/test_pipeline.py`:

```python
import pandas as pd

from scripts.pipeline import write_route_outputs


def test_write_route_outputs_preserves_raw_and_final_counts(tmp_path):
    raw = pd.DataFrame(
        {
            "source_row_id": [1, 2],
            "has_poteri_match": [True, False],
            "has_missing_key": [False, False],
        }
    )
    final = raw.copy()
    excluded = pd.DataFrame(columns=list(raw.columns) + ["exclude_reason"])
    diagnostics = {"raw_row_count": 2, "final_row_count": 2, "excluded_row_count": 0}

    paths = write_route_outputs(tmp_path, raw, final, excluded, diagnostics)

    assert paths["merged_raw"].exists()
    assert paths["final_clean"].exists()
    assert paths["excluded_rows"].exists()
    assert paths["merge_diagnostics"].exists()
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests\test_pipeline.py -q
```

Expected: `scripts.pipeline` is missing.

- [ ] **Step 3: Implement output writer**

Create `scripts/pipeline.py`:

```python
import json
from pathlib import Path


def write_route_outputs(run_dir, raw_df, final_df, excluded_df, diagnostics):
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)

    paths = {
        "merged_raw": run_path / "merged_raw.xlsx",
        "final_clean": run_path / "final_clean_data.xlsx",
        "excluded_rows": run_path / "excluded_rows.xlsx",
        "merge_diagnostics": run_path / "merge_diagnostics.md",
    }

    raw_df.to_excel(paths["merged_raw"], index=False)
    final_df.to_excel(paths["final_clean"], index=False)
    excluded_df.to_excel(paths["excluded_rows"], index=False)

    lines = ["# Merge Diagnostics", ""]
    for key, value in diagnostics.items():
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        lines.append(f"- **{key}**: {value}")
    paths["merge_diagnostics"].write_text("\n".join(lines), encoding="utf-8")
    return paths
```

- [ ] **Step 4: Add audit invariant helper**

Add to `scripts/pipeline.py`:

```python
def assert_audit_invariants(raw_df, final_df, excluded_df):
    raw_count = len(raw_df)
    accounted_count = len(final_df) + len(excluded_df)
    if accounted_count != raw_count:
        raise ValueError(
            f"Audit invariant failed: final({len(final_df)}) + excluded({len(excluded_df)}) != raw({raw_count})"
        )
```

- [ ] **Step 5: Verify**

Run:

```powershell
python -m pytest tests\test_pipeline.py -q
```

Expected: artifact writer produces all required files.

---

### Task 6: Refactor CLI Pipeline To Use Loss-Safe Flow

**Files:**
- Modify: `main_final_v3.py`
- Modify: `main.py`
- Modify: `project_config.yaml`
- Test: `tests/test_main_cli.py`

- [ ] **Step 1: Write tests for route config and no target requirement**

Create `tests/test_main_cli.py`:

```python
import yaml

from main_final_v3 import get_route_config


def test_route_1_merge_key_has_category():
    config = yaml.safe_load(open("project_config.yaml", encoding="utf-8"))
    route = get_route_config(config, "route_1")
    assert route["merge_key"] == ["НеделяГод", "ТС", "Категория", "Завод"]


def test_route_2_merge_key_has_no_category():
    config = yaml.safe_load(open("project_config.yaml", encoding="utf-8"))
    route = get_route_config(config, "route_2")
    assert route["merge_key"] == ["НеделяГод", "ТС", "Завод"]


def test_pipeline_config_does_not_require_target_col():
    config = yaml.safe_load(open("project_config.yaml", encoding="utf-8"))
    assert "target_col" not in config.get("columns", {})
```

- [ ] **Step 2: Run test and verify current failure**

Run:

```powershell
python -m pytest tests\test_main_cli.py -q
```

Expected: current config/code still uses old target settings.

- [ ] **Step 3: Update config**

Modify `project_config.yaml`:

```yaml
columns:
  svod:
    week: "НеделяГод"
    ts: "ТС"
    factory: "Завод"
    category: "Категория"
  poteri:
    week: "Неделя"
    ts: "Торговая сеть"
    factory: "Завод"
    category: "Категория"
    rename_map:
      "Неделя": "НеделяГод"
      "Торговая сеть": "ТС"
      "Списание без НДС (Итог) по B06, руб": "Списания"
      "Выручка, руб": "Выручка"
      "Свободно используемый товарный запас без НДС, руб": "Свободный ТЗ"

cleaning:
  outlier_columns: []
  drop_outliers: false

dashboard:
  default_metric: null
```

Remove required `target_col`, `default_kir`, `clean_target_col`, `remove_zeros`, and physical-clean settings from pipeline use. Keep deprecated keys only if necessary for backwards compatibility, but do not use them.

- [ ] **Step 4: Refactor `get_route_config()`**

In `main_final_v3.py`, return `merge_key`:

```python
def get_route_config(config, route_name):
    if route_name == "route_1":
        return {
            "name": "route_1",
            "svod": os.path.join(config["inputs"]["route_1"], "kir_with_cats.xlsx"),
            "poteri": os.path.join(config["inputs"]["route_1"], "poteri_with_cats.xlsx"),
            "merge_key": ["НеделяГод", "ТС", "Категория", "Завод"],
            "desc": "Маршрут 1 (с категориями)",
        }
    if route_name == "route_2":
        return {
            "name": "route_2",
            "svod": os.path.join(config["inputs"]["route_2"], "kir_without_cats.xlsx"),
            "poteri": os.path.join(config["inputs"]["route_2"], "poteri_without_cats.xlsx"),
            "merge_key": ["НеделяГод", "ТС", "Завод"],
            "desc": "Маршрут 2 (без категорий)",
        }
    raise ValueError(f"Unknown route: {route_name}")
```

- [ ] **Step 5: Refactor route execution**

In `main_final_v3.py`, use:

```python
from scripts.merge_data_v3 import merge_route_data
from scripts.quality_flags import add_quality_flags
from scripts.pipeline import assert_audit_invariants, write_route_outputs
```

For each route:

```python
kir_df = pd.read_excel(route_conf["svod"])
poteri_df = pd.read_excel(route_conf["poteri"])
raw_df, diagnostics = merge_route_data(
    kir_df,
    poteri_df,
    route_conf["merge_key"],
    config["columns"]["poteri"]["rename_map"],
)
final_df = add_quality_flags(raw_df)
excluded_df = raw_df.iloc[0:0].copy()
excluded_df["exclude_reason"] = []
diagnostics["final_row_count"] = len(final_df)
diagnostics["excluded_row_count"] = len(excluded_df)
assert_audit_invariants(raw_df, final_df, excluded_df)
write_route_outputs(run_dir, raw_df, final_df, excluded_df, diagnostics)
```

- [ ] **Step 6: Make CLI return non-zero on errors**

Ensure:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

And `main()` returns `0` on success, `1` on any route failure.

- [ ] **Step 7: Verify**

Run:

```powershell
python -m pytest tests\test_main_cli.py -q
python main.py route_1
python main.py route_2
```

Expected: each route writes a new `data/run_N_route_X/` with `merged_raw.xlsx`, `final_clean_data.xlsx`, `excluded_rows.xlsx`, and `merge_diagnostics.md`.

---

### Task 7: Streamlit Dashboard MVP

**Files:**
- Create: `dashboard_streamlit.py`
- Test: `tests/test_dashboard_streamlit.py`

- [ ] **Step 1: Write tests for dashboard helper functions**

Create `tests/test_dashboard_streamlit.py`:

```python
import pandas as pd

from dashboard_streamlit import get_numeric_metric_columns, sort_metric_columns


def test_metric_columns_prioritize_kir_columns():
    df = pd.DataFrame(
        {
            "ТС": ["A"],
            "КИР-950": [1.0],
            "Выручка": [100.0],
            "КИР-066": [2.0],
        }
    )

    metrics = sort_metric_columns(get_numeric_metric_columns(df))

    assert metrics[:2] == ["КИР-066", "КИР-950"]
    assert "Выручка" in metrics
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests\test_dashboard_streamlit.py -q
```

Expected: `dashboard_streamlit.py` is missing.

- [ ] **Step 3: Implement dashboard helpers and MVP UI**

Create `dashboard_streamlit.py`:

```python
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


DATA_DIR = Path("data")


def get_numeric_metric_columns(df):
    return df.select_dtypes(include="number").columns.tolist()


def sort_metric_columns(columns):
    kir = sorted([column for column in columns if str(column).startswith("КИР-")])
    other = sorted([column for column in columns if column not in kir])
    return kir + other


def list_run_dirs():
    if not DATA_DIR.exists():
        return []
    return sorted([path for path in DATA_DIR.iterdir() if path.is_dir() and path.name.startswith("run_")], reverse=True)


def main():
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

    filtered = df.copy()
    for column in ["НеделяГод", "ТС", "Категория", "Завод", "has_poteri_match", "quality_status"]:
        if column in filtered.columns:
            options = sorted(filtered[column].dropna().unique().tolist())
            selected = st.sidebar.multiselect(column, options)
            if selected:
                filtered = filtered[filtered[column].isin(selected)]

    st.subheader("Data quality")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", len(filtered))
    c2.metric("No poteri", int((~filtered.get("has_poteri_match", pd.Series(False, index=filtered.index))).sum()))
    c3.metric("Metric nulls", int(filtered[metric].isna().sum()))
    c4.metric("Metric zeros", int((pd.to_numeric(filtered[metric], errors="coerce") == 0).sum()))

    st.subheader("Metric distribution")
    numeric_metric = pd.to_numeric(filtered[metric], errors="coerce")
    st.plotly_chart(px.histogram(filtered.assign(_metric=numeric_metric), x="_metric"), use_container_width=True)
    st.plotly_chart(px.box(filtered.assign(_metric=numeric_metric), y="_metric"), use_container_width=True)

    st.subheader("Group comparison")
    group_options = [column for column in ["ТС", "Категория", "Завод"] if column in filtered.columns]
    if group_options:
        group_col = st.selectbox("Group by", group_options)
        grouped = filtered.assign(_metric=numeric_metric).groupby(group_col, dropna=False)["_metric"].agg(
            count="count", mean="mean", median="median", min="min", max="max"
        ).reset_index()
        st.dataframe(grouped, use_container_width=True)

    st.subheader("Problem rows")
    problem_mask = pd.Series(False, index=filtered.index)
    for column in ["has_poteri_match", "has_missing_key", "has_duplicate_kir_key", "has_duplicate_poteri_key"]:
        if column == "has_poteri_match" and column in filtered.columns:
            problem_mask |= ~filtered[column]
        elif column in filtered.columns:
            problem_mask |= filtered[column]
    st.dataframe(filtered[problem_mask].head(1000), use_container_width=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify helper tests**

Run:

```powershell
python -m pytest tests\test_dashboard_streamlit.py -q
```

Expected: helper tests pass.

- [ ] **Step 5: Manual dashboard run**

Run:

```powershell
streamlit run dashboard_streamlit.py
```

Expected: dashboard opens at `http://localhost:8501/` and shows run selection, metric selection, filters, quality cards, histogram, boxplot, group table, and problem rows.

---

### Task 8: Documentation and Final Verification

**Files:**
- Modify: `docs/README.md`
- Modify: `docs/PLAN.md`
- Test: all tests and real route smoke runs

- [ ] **Step 1: Update README**

Document commands:

```powershell
pip install -r requirements.txt
python main.py route_1
python main.py route_2
python main.py both
streamlit run dashboard_streamlit.py
```

Document output files:

```text
merged_raw.xlsx         raw audit merge
final_clean_data.xlsx   main analytical file with flags
excluded_rows.xlsx      structurally unrepresentable rows only
merge_diagnostics.md    merge/audit diagnostics
```

- [ ] **Step 2: Remove stale dashboard references**

Replace references to `scripts/db.py` and Tkinter dashboard with `dashboard_streamlit.py`.

- [ ] **Step 3: Run full verification**

Run:

```powershell
python -m pytest -q
python main.py route_1
python main.py route_2
python -m py_compile main.py main_final_v3.py dashboard_streamlit.py scripts\merge_data_v3.py scripts\quality_flags.py scripts\pipeline.py
```

Expected:

```text
all tests pass
route_1 and route_2 create run folders
both routes write merged_raw.xlsx
both routes write final_clean_data.xlsx
both routes write excluded_rows.xlsx
both routes write merge_diagnostics.md
no generated __pycache__ or .pytest_cache files are staged
```

- [ ] **Step 4: Check audit invariants manually on latest runs**

Run a short verification script:

```powershell
python -c "import pandas as pd, pathlib; [print(p, len(pd.read_excel(p/'merged_raw.xlsx')), len(pd.read_excel(p/'final_clean_data.xlsx')), len(pd.read_excel(p/'excluded_rows.xlsx'))) for p in pathlib.Path('data').glob('run_*_route_*') if (p/'merged_raw.xlsx').exists()]"
```

Expected: for every new run, `raw == final + excluded`.

---

## Execution Order

1. Task 1: repo hygiene and entrypoint migration.
2. Task 2: robust week normalization.
3. Task 3: loss-safe raw merge.
4. Task 4: quality flags without row deletion.
5. Task 5: route artifacts and diagnostics.
6. Task 6: CLI refactor and real route outputs.
7. Task 7: Streamlit dashboard MVP.
8. Task 8: docs and final verification.

## Checkpoints

- After Task 3, verify synthetic merge preserves all KIR rows and flags unmatched poteri.
- After Task 5, verify raw/final/excluded audit invariant on synthetic data.
- After Task 6, verify real route outputs before starting dashboard.
- After Task 7, verify dashboard in browser on `localhost:8501`.
