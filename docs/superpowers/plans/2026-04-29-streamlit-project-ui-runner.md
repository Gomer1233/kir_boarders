# Streamlit Project UI Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a simple Streamlit UI layer for managing KIR projects, uploading arbitrary-named KIR/Poteri files, running route pipelines, and reopening historical project dashboards.

**Architecture:** Keep the existing loss-safe pipeline and dashboard analytics intact. Add a thin project/session layer that stores uploaded files under `data/projects/<project>/...`, renames them to internal standard names, runs the existing merge/quality/output functions against project-specific paths, and lets the dashboard select either legacy `data/run_*` runs or project runs.

**Tech Stack:** Python, Streamlit, pandas, existing `main_final_v3.py`, `scripts.excel_reader`, `scripts.merge_data_v3`, `scripts.pipeline`, `scripts.quality_flags`, pytest.

---

## Current Code Context

- `main.py` delegates to `main_final_v3.main()`.
- `main_final_v3.py` currently owns config loading, route config, run numbering, route execution, and CLI mode selection.
- `dashboard_streamlit.py` currently reads legacy run directories directly from `data/run_*`.
- `project_config.yaml` points route inputs to `data/route_1` and `data/route_2`.
- Existing pipeline outputs per route:
  - `merged_raw.xlsx`
  - `final_clean_data.xlsx`
  - `excluded_rows.xlsx`
  - `merge_diagnostics.md`
- Existing tests are in `tests/`, with dashboard coverage in `tests/test_dashboard_streamlit.py`.

## Target User Flow

1. User opens `streamlit run dashboard_streamlit.py`.
2. Sidebar has a mode/section for project management.
3. User chooses existing KIR project, for example `003`, or creates a new one.
4. User uploads arbitrary-named KIR and Poteri files for `route_1`, `route_2`, or both.
5. App stores files under project folders using stable internal names.
6. User clicks `Run route_1`, `Run route_2`, or `Run both`.
7. App runs the same data pipeline and writes project-specific run outputs.
8. User chooses any existing project run and views the normal dashboard analytics.

## Data Layout

Create a project data root under existing `data/`:

```text
data/
  projects/
    registry.json
    003/
      project.json
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
          merged_raw.xlsx
          final_clean_data.xlsx
          excluded_rows.xlsx
          merge_diagnostics.md
        run_002_route_2/
          ...
```

Rules:
- User-facing file names can be anything.
- Internal saved names must be stable:
  - `kir_source.xlsx`
  - `poteri_source.xlsx`
- Preserve original filenames in `upload_manifest.json`.
- Project run folders must not collide with legacy `data/run_*`.
- Legacy `data/run_*` dashboard support must remain.

## File Structure

### Create `scripts/project_registry.py`

Responsibility:
- project name validation;
- project folder creation;
- registry read/write;
- project metadata read/write;
- list existing projects and project runs.

Main functions:
- `sanitize_project_name(name: str) -> str`
- `project_dir(project_name: str, base_dir=Path("data/projects")) -> Path`
- `load_registry(base_dir=Path("data/projects")) -> dict`
- `save_registry(registry: dict, base_dir=Path("data/projects")) -> None`
- `list_projects(base_dir=Path("data/projects")) -> list[str]`
- `create_project(project_name: str, base_dir=Path("data/projects")) -> Path`
- `list_project_runs(project_name: str, base_dir=Path("data/projects")) -> list[Path]`
- `next_project_run_dir(project_name: str, route_name: str, base_dir=Path("data/projects")) -> Path`

### Create `scripts/upload_runner.py`

Responsibility:
- save Streamlit-uploaded files to project upload folders;
- write upload manifest with original names;
- run existing pipeline for project-specific input paths;
- return output paths and status.

Main functions:
- `save_uploaded_route_files(project_name, route_name, kir_file, poteri_file, base_dir=Path("data/projects")) -> dict`
- `build_project_route_config(project_name, route_name, config, base_dir=Path("data/projects")) -> dict`
- `run_project_route(project_name, route_name, config, base_dir=Path("data/projects")) -> dict`
- `run_project_routes(project_name, routes, config, base_dir=Path("data/projects")) -> list[dict]`

Implementation note:
- Do not shell out to `python main.py`.
- Reuse existing internals:
  - `read_excel_loss_safe`
  - `merge_route_data`
  - `add_quality_flags`
  - `assert_audit_invariants`
  - `write_route_outputs`
- Project route configs should use the same merge keys as `main_final_v3.get_route_config()`.
- Avoid duplicating route constants when practical; extract shared helpers from `main_final_v3.py` only if needed.

### Modify `dashboard_streamlit.py`

Responsibility:
- add a project/run selector without breaking legacy run selector;
- add upload/run UI;
- make dashboard analytics work for project run directories.

Target additions:
- `DATA_PROJECTS_DIR = Path("data/projects")`
- run source selector:
  - `Legacy runs`
  - `Project runs`
- project selector:
  - existing project dropdown;
  - new project name input;
  - create project button.
- upload form:
  - route selector: `route_1`, `route_2`, `both`;
  - KIR file upload;
  - Poteri file upload;
  - save/upload button.
- run buttons:
  - `Run route_1`
  - `Run route_2`
  - `Run both`
- status display:
  - success output paths;
  - exception traceback or friendly error;
  - latest run shortcut.

Keep existing analytical screens unchanged as much as possible.

### Modify `tests/test_dashboard_streamlit.py`

Responsibility:
- cover new selector/list helper behavior if helper functions are added to dashboard.

### Create `tests/test_project_registry.py`

Responsibility:
- test project creation, listing, run numbering, metadata paths.

### Create `tests/test_upload_runner.py`

Responsibility:
- test upload saving and stable internal names;
- test route config generation;
- test run orchestration with injected pipeline dependencies if needed.

## Implementation Tasks

### Task 0: Create Implementation Branch Without Losing This Plan

**Files:**
- No file changes.

Context:
- This plan lives on branch `codex/project-ui-runner-plan`.
- If you switch directly to `main`, this plan file may disappear from the working tree because it is not part of `main`.
- Keep this plan open in the agent context, or restore it into the implementation branch with the checkout command below.

- [ ] **Step 1: Fetch latest remote state**

```powershell
git fetch origin
```

- [ ] **Step 2: Create implementation branch from `origin/main`**

```powershell
git switch -c codex/project-ui-runner origin/main
```

- [ ] **Step 3: Restore this plan file into the implementation branch**

```powershell
git checkout codex/project-ui-runner-plan -- docs/superpowers/plans/2026-04-29-streamlit-project-ui-runner.md
```

This does not bring code changes from the planning branch. It restores only this plan file so the implementation worker can keep following it.

- [ ] **Step 4: Commit the plan file on the implementation branch**

```powershell
git add docs/superpowers/plans/2026-04-29-streamlit-project-ui-runner.md
git commit -m "Add project UI runner implementation plan"
```

- [ ] **Step 5: Confirm clean branch**

```powershell
git status --short --branch
```

Expected:

```text
## codex/project-ui-runner
```

### Task 1: Project Registry

**Files:**
- Create: `scripts/project_registry.py`
- Create: `tests/test_project_registry.py`

- [ ] **Step 1: Write failing test for project name sanitization**

```python
from scripts.project_registry import sanitize_project_name


def test_sanitize_project_name_allows_simple_kir_codes():
    assert sanitize_project_name("003") == "003"
    assert sanitize_project_name("KIR 950") == "KIR_950"
```

- [ ] **Step 2: Run focused test and confirm RED**

```powershell
python -m pytest tests\test_project_registry.py -q
```

- [ ] **Step 3: Implement `sanitize_project_name()`**

Rules:
- strip whitespace;
- replace spaces with `_`;
- allow letters, numbers, `_`, `-`;
- reject empty names;
- reject path traversal characters `/`, `\`, `..`, `:`.

Expected implementation shape:

```python
def sanitize_project_name(name: str) -> str:
    raw = str(name).strip()
    if not raw:
        raise ValueError("Project name is required.")
    if any(token in raw for token in ("/", "\\", ":", "..")):
        raise ValueError(f"Unsafe project name: {name!r}")
    cleaned = re.sub(r"\s+", "_", raw)
    if not re.fullmatch(r"[\w-]+", cleaned, flags=re.UNICODE):
        raise ValueError(f"Unsupported project name: {name!r}")
    return cleaned
```

- [ ] **Step 4: Run focused test and confirm GREEN**

```powershell
python -m pytest tests\test_project_registry.py -q
```

- [ ] **Step 5: Write failing tests for create/list project**

```python
from scripts.project_registry import create_project, list_projects


def test_create_project_writes_registry_and_project_metadata(tmp_path):
    create_project("003", base_dir=tmp_path)

    assert list_projects(base_dir=tmp_path) == ["003"]
    assert (tmp_path / "003" / "project.json").exists()
    assert (tmp_path / "003" / "uploads").exists()
    assert (tmp_path / "003" / "runs").exists()
```

- [ ] **Step 6: Implement registry read/write and project creation**

Use JSON with UTF-8.

Registry shape:

```json
{
  "projects": [
    {
      "name": "003",
      "created_at": "2026-04-29T00:00:00Z",
      "last_opened_at": null,
      "last_run": null
    }
  ]
}
```

- [ ] **Step 7: Run focused test**

```powershell
python -m pytest tests\test_project_registry.py -q
```

- [ ] **Step 8: Write failing tests for project run numbering**

```python
from scripts.project_registry import next_project_run_dir


def test_next_project_run_dir_uses_project_runs_folder(tmp_path):
    create_project("003", base_dir=tmp_path)
    first = next_project_run_dir("003", "route_1", base_dir=tmp_path)
    first.mkdir(parents=True)

    second = next_project_run_dir("003", "route_2", base_dir=tmp_path)

    assert first.name == "run_001_route_1"
    assert second.name == "run_002_route_2"
```

- [ ] **Step 9: Implement run numbering**

Numbering must be per project across both routes.

- [ ] **Step 10: Run focused tests**

```powershell
python -m pytest tests\test_project_registry.py -q
```

- [ ] **Step 11: Commit**

```powershell
git add scripts/project_registry.py tests/test_project_registry.py
git commit -m "Add KIR project registry"
```

### Task 2: Upload Saving

**Files:**
- Create: `scripts/upload_runner.py`
- Create/modify: `tests/test_upload_runner.py`

- [ ] **Step 1: Write failing test for saving arbitrary-named files**

Use `io.BytesIO` or a small fake object with `.name` and `.getbuffer()`.

```python
import json
from io import BytesIO

import pytest

from scripts.project_registry import create_project
from scripts.upload_runner import save_uploaded_route_files


class FakeUpload(BytesIO):
    def __init__(self, name, data):
        super().__init__(data)
        self.name = name

    def getbuffer(self):
        return super().getbuffer()


def test_save_uploaded_route_files_uses_stable_internal_names(tmp_path):
    create_project("003", base_dir=tmp_path)

    result = save_uploaded_route_files(
        "003",
        "route_1",
        FakeUpload("my kir file.xlsx", b"kir"),
        FakeUpload("losses april.xlsx", b"poteri"),
        base_dir=tmp_path,
    )

    upload_dir = tmp_path / "003" / "uploads" / "route_1"
    assert (upload_dir / "kir_source.xlsx").read_bytes() == b"kir"
    assert (upload_dir / "poteri_source.xlsx").read_bytes() == b"poteri"
    manifest = json.loads((upload_dir / "upload_manifest.json").read_text(encoding="utf-8"))
    assert manifest["route"] == "route_1"
    assert manifest["kir_original_name"] == "my kir file.xlsx"
    assert manifest["poteri_original_name"] == "losses april.xlsx"
    assert result["kir_path"] == upload_dir / "kir_source.xlsx"
    assert result["poteri_path"] == upload_dir / "poteri_source.xlsx"
```

- [ ] **Step 2: Run focused test and confirm RED**

```powershell
python -m pytest tests\test_upload_runner.py -q
```

- [ ] **Step 3: Implement `save_uploaded_route_files()`**

Rules:
- validate project name and route name;
- require an existing project;
- if the project does not exist, raise `FileNotFoundError("Project does not exist: <name>")`;
- project creation remains a separate UI action via `create_project()`;
- write manifest:

```json
{
  "route": "route_1",
  "kir_original_name": "my kir file.xlsx",
  "poteri_original_name": "losses april.xlsx",
  "saved_at": "..."
}
```

- [ ] **Step 4: Run focused tests**

```powershell
python -m pytest tests\test_upload_runner.py -q
```

- [ ] **Step 5: Add tests for route validation**

Invalid route must raise `ValueError`.

Add a missing-project test:

```python
def test_save_uploaded_route_files_requires_existing_project(tmp_path):
    with pytest.raises(FileNotFoundError, match="Project does not exist"):
        save_uploaded_route_files(
            "missing",
            "route_1",
            FakeUpload("kir.xlsx", b"kir"),
            FakeUpload("poteri.xlsx", b"poteri"),
            base_dir=tmp_path,
        )
```

- [ ] **Step 6: Implement route validation**

Allowed routes:
- `route_1`
- `route_2`

- [ ] **Step 7: Run focused tests**

```powershell
python -m pytest tests\test_upload_runner.py -q
```

- [ ] **Step 8: Commit**

```powershell
git add scripts/upload_runner.py tests/test_upload_runner.py
git commit -m "Add project upload file handling"
```

### Task 3: Project Pipeline Runner

**Files:**
- Modify: `scripts/upload_runner.py`
- Modify: `tests/test_upload_runner.py`
- Optionally modify: `main_final_v3.py` only if extracting shared route constants is cleaner.

- [ ] **Step 1: Write failing test for project route config**

```python
from scripts.upload_runner import build_project_route_config
from main_final_v3 import get_route_config


def test_build_project_route_config_points_to_project_uploads(tmp_path):
    config = {
        "inputs": {"route_1": "data/route_1", "route_2": "data/route_2"},
        "columns": {"poteri": {"rename_map": {}}},
    }
    route = build_project_route_config("003", "route_1", config, base_dir=tmp_path)
    expected = get_route_config(config, "route_1")

    assert route["name"] == "route_1"
    assert route["svod"] == tmp_path / "003" / "uploads" / "route_1" / "kir_source.xlsx"
    assert route["poteri"] == tmp_path / "003" / "uploads" / "route_1" / "poteri_source.xlsx"
    assert route["merge_key"] == expected["merge_key"]
```

- [ ] **Step 2: Run test and confirm RED**

```powershell
python -m pytest tests\test_upload_runner.py -q
```

- [ ] **Step 3: Implement `build_project_route_config()`**

Route merge keys must match the current pipeline exactly, including the current encoded column names in `project_config.yaml`.

Implementation requirement:
- call or mirror `main_final_v3.get_route_config(config, route_name)`;
- override only `svod` and `poteri` to point at project upload files;
- preserve `merge_key` from the existing route config;
- convert `svod` and `poteri` to `Path` objects consistently if tests expect `Path`.

Expected implementation shape:

```python
def build_project_route_config(project_name, route_name, config, base_dir=PROJECTS_DIR):
    route = dict(get_route_config(config, route_name))
    upload_dir = project_upload_route_dir(project_name, route_name, base_dir=base_dir)
    route["svod"] = upload_dir / "kir_source.xlsx"
    route["poteri"] = upload_dir / "poteri_source.xlsx"
    return route
```

- [ ] **Step 4: Run focused tests**

```powershell
python -m pytest tests\test_upload_runner.py -q
```

- [ ] **Step 5: Write failing orchestration test with injected functions**

Avoid reading real Excel here. Make `run_project_route()` accept optional dependencies:
- `read_excel`
- `merge_data`
- `add_flags`
- `write_outputs`
- `assert_invariants`

Expected behavior:
- reads project upload files;
- writes to project run directory;
- returns output paths.

- [ ] **Step 6: Implement `run_project_route()`**

Use existing functions by default:
- `read_excel_loss_safe`
- `merge_route_data`
- `add_quality_flags`
- `assert_audit_invariants`
- `write_route_outputs`

Diagnostics must include:
- `route`
- `final_row_count`
- `excluded_row_count`
- `audit_invariant_ok`
- `project_name`

- [ ] **Step 7: Add test for missing upload files**

Missing `kir_source.xlsx` or `poteri_source.xlsx` should return/raise a clear error before pipeline work.

- [ ] **Step 8: Implement missing file validation**

Raise `FileNotFoundError` with route and expected path.

- [ ] **Step 9: Run focused tests**

```powershell
python -m pytest tests\test_upload_runner.py -q
```

- [ ] **Step 10: Commit**

```powershell
git add scripts/upload_runner.py tests/test_upload_runner.py
git commit -m "Add project pipeline runner"
```

### Task 4: Dashboard Run Sources

**Files:**
- Modify: `dashboard_streamlit.py`
- Modify: `tests/test_dashboard_streamlit.py`

- [ ] **Step 1: Write failing tests for legacy and project run discovery**

Add helper functions before touching UI:
- `list_legacy_run_dirs(data_dir=DATA_DIR)`
- `list_project_run_dirs(project_name, projects_dir=Path("data/projects"))`

Test:
- legacy `data/run_*` still works;
- project `data/projects/003/runs/run_*` works.

- [ ] **Step 2: Run tests and confirm RED**

```powershell
python -m pytest tests\test_dashboard_streamlit.py -q
```

- [ ] **Step 3: Implement run discovery helpers**

Keep existing `list_run_dirs()` as compatibility wrapper if useful.

- [ ] **Step 4: Run focused tests**

```powershell
python -m pytest tests\test_dashboard_streamlit.py -q
```

- [ ] **Step 5: Modify sidebar run selection**

UI behavior:
- `Run source` radio:
  - `Legacy runs`
  - `Project runs`
- If legacy:
  - show current `Run` selectbox from `data/run_*`.
- If project:
  - show project selectbox;
  - show project run selectbox from `data/projects/<project>/runs`.

No analytics screen should need to know whether the run is legacy or project; both pass a `run_dir` to existing `_load_run_dataframe()`.

- [ ] **Step 6: Manual smoke test**

Run:

```powershell
streamlit run dashboard_streamlit.py
```

Check:
- old runs still load;
- project runs selector handles no projects gracefully.

- [ ] **Step 7: Run tests**

```powershell
python -m pytest tests\test_dashboard_streamlit.py -q
```

- [ ] **Step 8: Commit**

```powershell
git add dashboard_streamlit.py tests/test_dashboard_streamlit.py
git commit -m "Add dashboard project run selection"
```

### Task 5: Project Creation UI

**Files:**
- Modify: `dashboard_streamlit.py`
- Modify: `tests/test_dashboard_streamlit.py`

- [ ] **Step 1: Add small pure helper tests**

Helpers:
- `project_select_options(projects: list[str]) -> list[str]`
- `normalize_new_project_input(value: str) -> str`

Tests should cover empty project list and whitespace.

- [ ] **Step 2: Implement helper functions**

Avoid putting logic directly inside Streamlit callbacks where it cannot be tested.

- [ ] **Step 3: Add project creation controls**

Sidebar or top section:
- `New project name` text input;
- `Create project` button;
- success/error messages.

When created:
- call `create_project()`;
- clear relevant input if practical;
- `st.rerun()`.

- [ ] **Step 4: Manual smoke test**

Create project `003`.

Expected folders:

```text
data/projects/003/uploads
data/projects/003/runs
data/projects/003/project.json
```

- [ ] **Step 5: Run tests**

```powershell
python -m pytest tests\test_dashboard_streamlit.py tests\test_project_registry.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add dashboard_streamlit.py tests/test_dashboard_streamlit.py
git commit -m "Add project creation UI"
```

### Task 6: Upload UI

**Files:**
- Modify: `dashboard_streamlit.py`
- Modify: `tests/test_dashboard_streamlit.py`

- [ ] **Step 1: Add route mode helper tests**

Helper:
- `routes_for_ui_mode(mode: str) -> list[str]`

Expected:
- `route_1` -> `["route_1"]`
- `route_2` -> `["route_2"]`
- `both` -> `["route_1", "route_2"]`

- [ ] **Step 2: Implement helper**

- [ ] **Step 3: Add upload controls**

For MVP, keep it explicit and simple:
- select project;
- select upload route mode;
- for each selected route show:
  - KIR uploader;
  - Poteri uploader;
  - save button.

If route mode is `both`, show separate upload sections for `route_1` and `route_2`; do not guess which file belongs to which route.

- [ ] **Step 4: Wire save buttons**

Use `save_uploaded_route_files()`.

Show:
- original filename;
- internal saved path;
- timestamp;
- manifest path.

- [ ] **Step 5: Manual smoke test**

Upload two tiny `.xlsx` files or sample files if available.

Expected:
- arbitrary original names are accepted;
- stable internal names are written.

- [ ] **Step 6: Run tests**

```powershell
python -m pytest tests\test_dashboard_streamlit.py tests\test_upload_runner.py -q
```

- [ ] **Step 7: Commit**

```powershell
git add dashboard_streamlit.py tests/test_dashboard_streamlit.py
git commit -m "Add project upload UI"
```

### Task 7: Run Pipeline UI

**Files:**
- Modify: `dashboard_streamlit.py`
- Modify: `tests/test_dashboard_streamlit.py`

- [ ] **Step 1: Add run status formatting helper tests**

Helper:
- `format_run_result(result: dict) -> str`

Should show:
- route;
- run directory;
- final path;
- raw path.

- [ ] **Step 2: Implement helper**

- [ ] **Step 3: Add run buttons**

Controls:
- `Run route_1`
- `Run route_2`
- `Run both`

Behavior:
- validate project selected;
- validate required upload files exist for selected route(s);
- wrap execution in `st.status()` or spinner;
- show success per route;
- show traceback/error if failed.

- [ ] **Step 4: Refresh project runs after success**

After successful run:
- display latest run path;
- rerun or update selector so user can open it.

- [ ] **Step 5: Manual smoke test**

Use real files if available:

```powershell
streamlit run dashboard_streamlit.py
```

Check:
- route_1 run writes project run folder;
- route_2 run writes project run folder;
- both writes two run folders;
- old CLI still works:

```powershell
python main.py route_1
python main.py route_2
```

- [ ] **Step 6: Run tests**

```powershell
python -m pytest -q
python -m py_compile dashboard_streamlit.py scripts/project_registry.py scripts/upload_runner.py
```

- [ ] **Step 7: Commit**

```powershell
git add dashboard_streamlit.py tests/test_dashboard_streamlit.py
git commit -m "Add project pipeline run UI"
```

### Task 8: Dashboard Polish and Guardrails

**Files:**
- Modify: `dashboard_streamlit.py`
- Modify: `tests/test_dashboard_streamlit.py`
- Modify: docs if needed

- [ ] **Step 1: Add empty-state checks**

Cases:
- no projects;
- project has uploads but no runs;
- project has route_1 run only;
- uploaded files missing for a selected route;
- run failed.

- [ ] **Step 2: Add UI copy**

Use clear Russian/English-neutral operational copy if existing dashboard is English:
- `Create project`
- `Upload source files`
- `Run pipeline`
- `Open dashboard`

Avoid long explanations in the main UI.

- [ ] **Step 3: Add metadata visibility**

Show in expander:
- original uploaded filenames;
- saved internal filenames;
- upload timestamp;
- latest run.

- [ ] **Step 4: Add opened-file actions**

Enhance the existing `Opened files` expander in `_render_audit_tab()`.

Add helper functions before touching UI:
- `read_file_for_download(path: Path) -> bytes`
- `download_file_name(path: Path, run_dir: Path) -> str`

Tests:
- missing file returns disabled state or raises a clear `FileNotFoundError` in helper;
- download file names include route/run context, for example `run_015_route_1_final_clean_data.xlsx`;
- helper reads exact bytes from disk.

UI behavior:
- Keep visible paths for `final_clean_data.xlsx` and `merged_raw.xlsx`.
- Add `Download final_clean_data.xlsx` button.
- Add `Download merged_raw.xlsx` button.
- Optionally add `Open folder` or `Open file` only if implemented safely for local desktop execution. Do not rely on browser opening `file://` links because most browsers block local file access from Streamlit pages.

Implementation notes:
- Use `st.download_button()` as the reliable MVP action.
- MIME type for Excel: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- Do not load these files repeatedly on every rerun without caching if file size is large. Use `st.cache_data` with path and `mtime_ns`, similar to existing `_read_excel_cached()`.

- [ ] **Step 5: Manual browser smoke test**

Check:
- layout fits desktop;
- no huge factory multiselect returns;
- analytics screens still work.
- download buttons produce the expected Excel files.

- [ ] **Step 6: Run full verification**

```powershell
python -m pytest -q
python -m py_compile dashboard_streamlit.py main.py main_final_v3.py scripts/project_registry.py scripts/upload_runner.py
```

- [ ] **Step 7: Commit**

```powershell
git add dashboard_streamlit.py tests/test_dashboard_streamlit.py
git commit -m "Polish project runner UI states"
```

### Task 9: Final Review and PR

**Files:**
- No required code changes unless verification finds issues.

- [ ] **Step 1: Inspect git history**

```powershell
git log --oneline --decorate -10
git status --short --branch
```

- [ ] **Step 2: Run final verification**

```powershell
python -m pytest -q
python -m py_compile dashboard_streamlit.py main.py main_final_v3.py scripts/project_registry.py scripts/upload_runner.py
```

- [ ] **Step 3: Push branch**

```powershell
git push -u origin codex/project-ui-runner
```

- [ ] **Step 4: Open PR**

Title:

```text
Add Streamlit project upload runner
```

Description:

```markdown
## Summary
- Add project/session registry for KIR analyses.
- Add upload handling that accepts arbitrary filenames and saves stable internal source files.
- Add Streamlit UI for creating projects, uploading route files, running pipeline routes, and reopening project runs.
- Preserve existing legacy run dashboard behavior.

## Tests
- `python -m pytest -q`
- `python -m py_compile dashboard_streamlit.py main.py main_final_v3.py scripts/project_registry.py scripts/upload_runner.py`
```

## Acceptance Criteria

- User can create project `003`.
- User can upload files named arbitrarily, and they are stored as stable internal filenames.
- User can run `route_1`, `route_2`, or both from Streamlit.
- Project run outputs are written under `data/projects/<project>/runs`.
- User can reopen old project runs from the UI.
- Existing `python main.py route_1` and `python main.py route_2` still work.
- Existing legacy `data/run_*` dashboard selection still works.
- `Opened files` provides download buttons for `final_clean_data.xlsx` and `merged_raw.xlsx`.
- No data-cleaning rules change.
- No rows are removed by this UI layer.
- Full test suite passes.

## Risks and Mitigations

- **Large Excel files can still be slow.**
  - Mitigation: UI should show status/spinner; existing loss-safe reader remains responsible for loading.

- **Running pipeline inside Streamlit can block the UI.**
  - Mitigation: MVP accepts blocking run with visible status. Background jobs are out of scope.

- **Project naming can create unsafe paths.**
  - Mitigation: strict `sanitize_project_name()`.

- **Route file confusion when running both.**
  - Mitigation: route_1 and route_2 upload sections remain explicit; no auto-detection in MVP.

- **Planning docs should not pollute product docs unintentionally.**
  - Mitigation: this plan is on a dedicated planning branch. If implementation PR should not include it, remove or keep it only in a docs/plans PR by explicit decision.
