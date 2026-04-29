# Streamlit KIR Projects Upload Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a simple Streamlit UI layer with persistent KIR project memory: users can create/select a KIR project such as `003`, upload arbitrary-named KIR/poteri files, run `route_1`, `route_2`, or both, and later reopen old project runs without re-uploading files.

**Architecture:** Keep the current pipeline intact. Add a thin project/session layer under `data/kir_projects/<project_slug>/` with `project.json`, `uploads/upload_N/...`, and `runs/run_N_route_X/...`. Uploaded files are stored under canonical names inside the selected project, while the pipeline is called with explicit input and output paths. Extend `dashboard_streamlit.py` with project selection, a runner tab, and an analysis tab scoped to the selected KIR project.

**Tech Stack:** Python, Streamlit, pandas/openpyxl for output reads, existing `main_final_v3.py` pipeline modules, pytest.

---

## Target Directory Layout

For a project entered as `003`:

```text
data/kir_projects/
  kir_003/
    project.json
    uploads/
      upload_1/
        upload_manifest.json
        route_1/
          kir_with_cats.xlsx
          poteri_with_cats.xlsx
        route_2/
          kir_without_cats.xlsx
          poteri_without_cats.xlsx
    runs/
      run_1_route_1/
        merged_raw.xlsx
        final_clean_data.xlsx
        excluded_rows.xlsx
        merge_diagnostics.md
      run_2_route_2/
        merged_raw.xlsx
        final_clean_data.xlsx
        excluded_rows.xlsx
        merge_diagnostics.md
```

`project.json`:

```json
{
  "kir_id": "003",
  "display_name": "KIR 003",
  "slug": "kir_003",
  "created_at": "2026-04-29T19:30:00",
  "updated_at": "2026-04-29T19:45:00",
  "notes": ""
}
```

---

## File Structure

- Create `scripts/kir_projects.py`: owns KIR project slugging, project metadata, project listing, upload/run roots, and project-scoped run numbering.
- Create `scripts/upload_sessions.py`: owns canonical filenames, upload session numbering inside a project, manifest writing, and safe file persistence.
- Modify `main_final_v3.py`: allow `run_route()` to receive explicit input paths and output base directory from UI while keeping CLI/config behavior unchanged.
- Modify `dashboard_streamlit.py`: add project selector, `New KIR` flow, `Run pipeline` tab, and project-scoped `Analyze runs` tab.
- Add `tests/test_kir_projects.py`: tests project creation/listing and project-scoped run directory numbering.
- Add `tests/test_upload_sessions.py`: tests canonical renaming and upload manifest content under a project.
- Extend `tests/test_main_cli.py`: tests route config override and output base directory override without changing CLI behavior.
- Extend `tests/test_dashboard_streamlit.py`: tests helper selection logic without requiring Streamlit runtime interaction.
- Modify `.gitignore`: ignore `.superpowers/` local brainstorming artifacts.
- Modify `docs/README.md`: document project memory and UI workflow.

---

### Task 1: KIR Project Storage

**Files:**
- Create: `scripts/kir_projects.py`
- Test: `tests/test_kir_projects.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_kir_projects.py`:

```python
import json

from scripts.kir_projects import (
    create_kir_project,
    list_kir_projects,
    next_project_run_dir,
    normalize_kir_slug,
)


def test_normalize_kir_slug_keeps_digits_and_prefixes_kir():
    assert normalize_kir_slug("003") == "kir_003"
    assert normalize_kir_slug("KIR 950") == "kir_950"
    assert normalize_kir_slug("kir-020") == "kir_020"


def test_create_kir_project_writes_metadata(tmp_path):
    project = create_kir_project("003", root=tmp_path)

    assert project.name == "kir_003"
    assert (project / "uploads").is_dir()
    assert (project / "runs").is_dir()

    metadata = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert metadata["kir_id"] == "003"
    assert metadata["display_name"] == "KIR 003"
    assert metadata["slug"] == "kir_003"
    assert metadata["notes"] == ""
    assert "created_at" in metadata
    assert "updated_at" in metadata


def test_list_kir_projects_reads_existing_metadata(tmp_path):
    create_kir_project("003", root=tmp_path)
    create_kir_project("950", root=tmp_path)

    projects = list_kir_projects(root=tmp_path)

    assert [project["slug"] for project in projects] == ["kir_003", "kir_950"]
    assert [project["display_name"] for project in projects] == ["KIR 003", "KIR 950"]


def test_next_project_run_dir_is_scoped_to_project(tmp_path):
    project = create_kir_project("003", root=tmp_path)
    (project / "runs" / "run_1_route_1").mkdir(parents=True)
    (project / "runs" / "run_3_route_2").mkdir(parents=True)

    run_dir = next_project_run_dir(project, "route_1")

    assert run_dir == project / "runs" / "run_4_route_1"
    assert run_dir.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests\test_kir_projects.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.kir_projects'`.

- [ ] **Step 3: Implement project helpers**

Create `scripts/kir_projects.py`:

```python
import json
import re
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PROJECT_ROOT = Path("data/kir_projects")


def normalize_kir_slug(value):
    text = str(value).strip().lower()
    text = re.sub(r"^kir", "", text).strip()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if not text:
        raise ValueError("KIR name cannot be empty")
    return f"kir_{text}"


def create_kir_project(kir_id, root=DEFAULT_PROJECT_ROOT, notes=""):
    root = Path(root)
    slug = normalize_kir_slug(kir_id)
    project = root / slug
    project.mkdir(parents=True, exist_ok=True)
    (project / "uploads").mkdir(exist_ok=True)
    (project / "runs").mkdir(exist_ok=True)

    now = _now_iso()
    metadata_path = project / "project.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["updated_at"] = now
        metadata["notes"] = metadata.get("notes", notes)
    else:
        clean_id = str(kir_id).strip()
        metadata = {
            "kir_id": clean_id,
            "display_name": f"KIR {clean_id}",
            "slug": slug,
            "created_at": now,
            "updated_at": now,
            "notes": notes,
        }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return project


def list_kir_projects(root=DEFAULT_PROJECT_ROOT):
    root = Path(root)
    if not root.exists():
        return []
    projects = []
    for metadata_path in sorted(root.glob("*/project.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["path"] = str(metadata_path.parent)
        projects.append(metadata)
    return projects


def next_project_run_dir(project, route_name):
    runs_root = Path(project) / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    numbers = []
    for path in runs_root.iterdir():
        if not path.is_dir() or not path.name.startswith("run_"):
            continue
        number = path.name.removeprefix("run_").split("_", 1)[0]
        if number.isdigit():
            numbers.append(int(number))
    run_dir = runs_root / f"run_{max(numbers, default=0) + 1}_{route_name}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests\test_kir_projects.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit task**

```powershell
git add scripts/kir_projects.py tests/test_kir_projects.py
git commit -m "Add KIR project storage"
```

---

### Task 2: Project-Scoped Upload Sessions

**Files:**
- Create: `scripts/upload_sessions.py`
- Test: `tests/test_upload_sessions.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_upload_sessions.py`:

```python
import json

from scripts.kir_projects import create_kir_project
from scripts.upload_sessions import CANONICAL_FILES, create_upload_session, save_upload_file


class UploadedFileStub:
    def __init__(self, name, content):
        self.name = name
        self._content = content

    def getbuffer(self):
        return memoryview(self._content)


def test_create_upload_session_is_scoped_to_project(tmp_path):
    project = create_kir_project("003", root=tmp_path)
    (project / "uploads" / "upload_1").mkdir(parents=True)
    (project / "uploads" / "upload_3").mkdir(parents=True)

    session = create_upload_session(project)

    assert session == project / "uploads" / "upload_4"
    assert session.exists()


def test_save_upload_file_uses_canonical_name_and_manifest(tmp_path):
    project = create_kir_project("003", root=tmp_path)
    session = create_upload_session(project)
    uploaded = UploadedFileStub("random user name.xlsx", b"excel-bytes")

    saved = save_upload_file(session, "route_1", "kir", uploaded)

    expected = session / "route_1" / CANONICAL_FILES[("route_1", "kir")]
    assert saved == expected
    assert saved.read_bytes() == b"excel-bytes"

    manifest = json.loads((session / "upload_manifest.json").read_text(encoding="utf-8"))
    assert manifest["session"] == session.name
    assert manifest["project_slug"] == "kir_003"
    assert manifest["files"] == [
        {
            "route": "route_1",
            "role": "kir",
            "original_name": "random user name.xlsx",
            "canonical_name": "kir_with_cats.xlsx",
            "relative_path": "route_1/kir_with_cats.xlsx",
            "size_bytes": 11,
        }
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests\test_upload_sessions.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.upload_sessions'`.

- [ ] **Step 3: Implement upload session helpers**

Create `scripts/upload_sessions.py`:

```python
import json
from pathlib import Path


CANONICAL_FILES = {
    ("route_1", "kir"): "kir_with_cats.xlsx",
    ("route_1", "poteri"): "poteri_with_cats.xlsx",
    ("route_2", "kir"): "kir_without_cats.xlsx",
    ("route_2", "poteri"): "poteri_without_cats.xlsx",
}


def create_upload_session(project):
    project = Path(project)
    root = project / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    numbers = []
    for path in root.iterdir():
        if not path.is_dir() or not path.name.startswith("upload_"):
            continue
        suffix = path.name.removeprefix("upload_")
        if suffix.isdigit():
            numbers.append(int(suffix))
    session = root / f"upload_{max(numbers, default=0) + 1}"
    session.mkdir(parents=True, exist_ok=False)
    _write_manifest(session, [])
    return session


def save_upload_file(session, route, role, uploaded_file):
    session = Path(session)
    canonical_name = CANONICAL_FILES[(route, role)]
    route_dir = session / route
    route_dir.mkdir(parents=True, exist_ok=True)
    destination = route_dir / canonical_name
    content = bytes(uploaded_file.getbuffer())
    destination.write_bytes(content)

    manifest = _read_manifest(session)
    manifest["files"].append(
        {
            "route": route,
            "role": role,
            "original_name": uploaded_file.name,
            "canonical_name": canonical_name,
            "relative_path": f"{route}/{canonical_name}",
            "size_bytes": len(content),
        }
    )
    _write_manifest(session, manifest["files"])
    return destination


def _project_slug_from_session(session):
    return Path(session).parents[1].name


def _read_manifest(session):
    manifest_path = Path(session) / "upload_manifest.json"
    if not manifest_path.exists():
        return {"session": Path(session).name, "project_slug": _project_slug_from_session(session), "files": []}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _write_manifest(session, files):
    session = Path(session)
    manifest = {
        "session": session.name,
        "project_slug": _project_slug_from_session(session),
        "files": files,
    }
    (session / "upload_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests\test_upload_sessions.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit task**

```powershell
git add scripts/upload_sessions.py tests/test_upload_sessions.py
git commit -m "Add project-scoped upload sessions"
```

---

### Task 3: Route Runner Input and Output Overrides

**Files:**
- Modify: `main_final_v3.py`
- Test: `tests/test_main_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_main_cli.py`:

```python
from main_final_v3 import get_route_config


def test_route_config_accepts_explicit_input_paths():
    config = {
        "inputs": {"route_1": "data/route_1", "route_2": "data/route_2"},
    }
    route = get_route_config(
        config,
        "route_1",
        input_paths={
            "route_1": {
                "kir": "data/kir_projects/kir_003/uploads/upload_1/route_1/kir_with_cats.xlsx",
                "poteri": "data/kir_projects/kir_003/uploads/upload_1/route_1/poteri_with_cats.xlsx",
            }
        },
    )

    assert route["svod"] == "data/kir_projects/kir_003/uploads/upload_1/route_1/kir_with_cats.xlsx"
    assert route["poteri"] == "data/kir_projects/kir_003/uploads/upload_1/route_1/poteri_with_cats.xlsx"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests\test_main_cli.py::test_route_config_accepts_explicit_input_paths -q
```

Expected: FAIL with `TypeError: get_route_config() got an unexpected keyword argument 'input_paths'`.

- [ ] **Step 3: Update route config path selection**

In `main_final_v3.py`, change signature:

```python
def get_route_config(config, route_name, input_paths=None):
    input_paths = input_paths or {}
    route_override = input_paths.get(route_name, {})
```

For `route_1`, use:

```python
"svod": route_override.get("kir", os.path.join(config["inputs"]["route_1"], "kir_with_cats.xlsx")),
"poteri": route_override.get("poteri", os.path.join(config["inputs"]["route_1"], "poteri_with_cats.xlsx")),
```

For `route_2`, use:

```python
"svod": route_override.get("kir", os.path.join(config["inputs"]["route_2"], "kir_without_cats.xlsx")),
"poteri": route_override.get("poteri", os.path.join(config["inputs"]["route_2"], "poteri_without_cats.xlsx")),
```

- [ ] **Step 4: Add output base directory override**

Change `run_route` signature:

```python
def run_route(config, route_name, input_paths=None, output_base_dir="data"):
    route_conf = get_route_config(config, route_name, input_paths=input_paths)
    run_num = get_next_run_number(output_base_dir)
    run_dir = os.path.join(output_base_dir, f"run_{run_num}_{route_name}")
```

CLI remains unchanged because default `output_base_dir="data"` preserves current behavior.

UI will call:

```python
run_route(config, route, input_paths=input_paths, output_base_dir=str(project / "runs"))
```

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
python -m pytest tests\test_main_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit task**

```powershell
git add main_final_v3.py tests/test_main_cli.py
git commit -m "Allow project-scoped route IO"
```

---

### Task 4: Dashboard Project Helpers

**Files:**
- Modify: `dashboard_streamlit.py`
- Test: `tests/test_dashboard_streamlit.py`

- [ ] **Step 1: Write helper tests**

Append to `tests/test_dashboard_streamlit.py`:

```python
from dashboard_streamlit import required_upload_roles, route_input_paths_from_session, upload_label


def test_required_upload_roles_for_both_routes():
    assert required_upload_roles("both") == [
        ("route_1", "kir"),
        ("route_1", "poteri"),
        ("route_2", "kir"),
        ("route_2", "poteri"),
    ]


def test_route_input_paths_from_session(tmp_path):
    session = tmp_path / "kir_003" / "uploads" / "upload_1"
    assert route_input_paths_from_session(session, "route_1") == {
        "route_1": {
            "kir": str(session / "route_1" / "kir_with_cats.xlsx"),
            "poteri": str(session / "route_1" / "poteri_with_cats.xlsx"),
        }
    }


def test_upload_label_is_human_readable():
    assert upload_label("route_1", "kir") == "route_1: KIR with categories"
    assert upload_label("route_2", "poteri") == "route_2: poteri without categories"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests\test_dashboard_streamlit.py -q
```

Expected: FAIL because helpers are missing.

- [ ] **Step 3: Add dashboard helper imports and functions**

In `dashboard_streamlit.py`, add imports:

```python
from scripts.upload_sessions import CANONICAL_FILES
```

Add helpers near existing pure functions:

```python
def required_upload_roles(mode):
    if mode == "route_1":
        return [("route_1", "kir"), ("route_1", "poteri")]
    if mode == "route_2":
        return [("route_2", "kir"), ("route_2", "poteri")]
    if mode == "both":
        return [
            ("route_1", "kir"),
            ("route_1", "poteri"),
            ("route_2", "kir"),
            ("route_2", "poteri"),
        ]
    raise ValueError(f"Unknown mode: {mode}")


def route_input_paths_from_session(session, mode):
    session = Path(session)
    input_paths = {}
    for route, role in required_upload_roles(mode):
        input_paths.setdefault(route, {})[role] = str(session / route / CANONICAL_FILES[(route, role)])
    return input_paths


def upload_label(route, role):
    labels = {
        ("route_1", "kir"): "route_1: KIR with categories",
        ("route_1", "poteri"): "route_1: poteri with categories",
        ("route_2", "kir"): "route_2: KIR without categories",
        ("route_2", "poteri"): "route_2: poteri without categories",
    }
    return labels[(route, role)]
```

- [ ] **Step 4: Run helper tests**

Run:

```powershell
python -m pytest tests\test_dashboard_streamlit.py -q
```

Expected: pass.

- [ ] **Step 5: Commit task**

```powershell
git add dashboard_streamlit.py tests/test_dashboard_streamlit.py
git commit -m "Add dashboard project helpers"
```

---

### Task 5: Streamlit Project Selector and Runner Tab

**Files:**
- Modify: `dashboard_streamlit.py`
- Test: `tests/test_dashboard_streamlit.py`

- [ ] **Step 1: Add tests for project option labels**

Append to `tests/test_dashboard_streamlit.py`:

```python
from dashboard_streamlit import project_option_label


def test_project_option_label_includes_display_name_and_slug():
    option = {"display_name": "KIR 003", "slug": "kir_003"}
    assert project_option_label(option) == "KIR 003 (kir_003)"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests\test_dashboard_streamlit.py::test_project_option_label_includes_display_name_and_slug -q
```

Expected: FAIL because `project_option_label` is missing.

- [ ] **Step 3: Add project imports and label helper**

In `dashboard_streamlit.py`, add imports:

```python
from main_final_v3 import load_config, run_route
from scripts.kir_projects import DEFAULT_PROJECT_ROOT, create_kir_project, list_kir_projects
from scripts.upload_sessions import create_upload_session, save_upload_file
```

Add helper:

```python
def project_option_label(option):
    return f"{option['display_name']} ({option['slug']})"
```

- [ ] **Step 4: Split UI into project-aware tabs**

In `main()` replace the current straight-line UI with:

```python
st.set_page_config(page_title="KIR Dashboard", layout="wide")
st.title("KIR Pipeline Studio")
project = render_project_selector()
if project is None:
    st.info("Create or select a KIR project to continue.")
    return

runner_tab, analysis_tab = st.tabs(["Run pipeline", "Analyze runs"])
with runner_tab:
    render_runner_tab(project)
with analysis_tab:
    render_analysis_tab(project)
```

- [ ] **Step 5: Implement project selector**

Add:

```python
def render_project_selector():
    projects = list_kir_projects()
    options = [{"display_name": "New KIR", "slug": "__new__", "path": ""}] + projects
    selected = st.sidebar.selectbox("KIR project", options, format_func=project_option_label)

    if selected["slug"] != "__new__":
        st.sidebar.caption(f"Project folder: `{selected['path']}`")
        return Path(selected["path"])

    kir_id = st.sidebar.text_input("New KIR name/code", placeholder="003")
    notes = st.sidebar.text_area("Notes", height=80)
    if st.sidebar.button("Create KIR project", type="primary"):
        if not kir_id.strip():
            st.sidebar.error("Enter KIR name/code first.")
            return None
        project = create_kir_project(kir_id, notes=notes)
        st.sidebar.success(f"Created {project.name}. Select it in the dropdown.")
        return project
    return None
```

- [ ] **Step 6: Implement runner tab**

Add:

```python
def render_runner_tab(project):
    config = load_config()
    mode = st.radio("Route", ["route_1", "route_2", "both"], horizontal=True)
    uploads = {}
    for route, role in required_upload_roles(mode):
        uploads[(route, role)] = st.file_uploader(
            upload_label(route, role),
            type=["xlsx", "xlsm", "xls"],
            key=f"upload-{project.name}-{route}-{role}-{mode}",
        )

    ready = all(file is not None for file in uploads.values())
    if not ready:
        st.info("Upload all required files for the selected route mode.")
        return

    if st.button("Run selected pipeline", type="primary"):
        session = create_upload_session(project)
        for (route, role), uploaded_file in uploads.items():
            save_upload_file(session, route, role, uploaded_file)

        input_paths = route_input_paths_from_session(session, mode)
        routes = ["route_1", "route_2"] if mode == "both" else [mode]
        output_base_dir = project / "runs"
        with st.status("Running pipeline...", expanded=True) as status:
            for route in routes:
                st.write(f"Running {route}...")
                run_route(config, route, input_paths=input_paths, output_base_dir=str(output_base_dir))
            status.update(label="Pipeline completed", state="complete")

        st.success(f"Upload session saved: {session}")
        st.info("Open Analyze runs and select the newest project run.")
```

- [ ] **Step 7: Make analysis tab project-scoped**

Change `list_run_dirs()` to accept a root:

```python
def list_run_dirs(root=DATA_DIR):
    root = Path(root)
    if not root.exists():
        return []
    return sorted(
        [path for path in root.iterdir() if path.is_dir() and path.name.startswith("run_")],
        reverse=True,
    )
```

Change analysis entry:

```python
def render_analysis_tab(project):
    run_dirs = list_run_dirs(project / "runs")
    if not run_dirs:
        st.warning("No run directories found for this KIR project.")
        return
    # existing analysis body continues here
```

- [ ] **Step 8: Run dashboard tests**

Run:

```powershell
python -m pytest tests\test_dashboard_streamlit.py -q
```

Expected: all dashboard helper tests pass.

- [ ] **Step 9: Commit task**

```powershell
git add dashboard_streamlit.py tests/test_dashboard_streamlit.py
git commit -m "Add Streamlit KIR project runner"
```

---

### Task 6: Gitignore and Documentation

**Files:**
- Modify: `.gitignore`
- Modify: `docs/README.md`

- [ ] **Step 1: Ignore local brainstorming artifacts**

Add to `.gitignore` if not already present:

```text
# Local planning/mockup artifacts
.superpowers/
```

- [ ] **Step 2: Document project memory workflow**

In `docs/README.md`, update the dashboard section to:

```markdown
## Dashboard / UI Runner

Run:

```powershell
streamlit run dashboard_streamlit.py
```

The Streamlit app stores analysis by KIR project.

Workflow:

1. Select an existing KIR project, or choose `New KIR` and enter a code such as `003`, `020`, or `950`.
2. Upload arbitrary-named KIR and poteri files.
3. Choose `route_1`, `route_2`, or `both`.
4. Run the existing pipeline from the UI.
5. Open `Analyze runs` to inspect saved project runs.

Project data is stored under:

```text
data/kir_projects/kir_003/
```

Uploaded files are copied into project upload sessions:

```text
data/kir_projects/kir_003/uploads/upload_N/
```

The app stores files under canonical names regardless of original uploaded filename:

```text
route_1/kir_with_cats.xlsx
route_1/poteri_with_cats.xlsx
route_2/kir_without_cats.xlsx
route_2/poteri_without_cats.xlsx
```

Each upload session includes `upload_manifest.json` with original filenames, canonical filenames, size, route, and role.

Pipeline outputs created from the UI are stored inside the selected project:

```text
data/kir_projects/kir_003/runs/run_N_route_1/
data/kir_projects/kir_003/runs/run_N_route_2/
```
```

- [ ] **Step 3: Commit docs**

```powershell
git add .gitignore docs/README.md
git commit -m "Document KIR project UI workflow"
```

---

### Task 7: Final Verification

**Files:**
- Verify only

- [ ] **Step 1: Run full tests**

```powershell
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Compile changed modules**

```powershell
python -m py_compile dashboard_streamlit.py main_final_v3.py scripts\kir_projects.py scripts\upload_sessions.py
```

Expected: exit code 0.

- [ ] **Step 3: Manual UI smoke test**

Run:

```powershell
streamlit run dashboard_streamlit.py
```

Manual expected result:

- Sidebar has `KIR project` selector.
- User can create `KIR 003`.
- Existing `KIR 003` appears in selector after creation.
- `Run pipeline` tab appears after project selection.
- Selecting `route_1` asks for exactly two files.
- Selecting `route_2` asks for exactly two files.
- Selecting `both` asks for exactly four files.
- Uploaded files can have arbitrary names.
- After run, `data/kir_projects/kir_003/uploads/upload_N/upload_manifest.json` exists.
- New `data/kir_projects/kir_003/runs/run_N_route_1` or `run_N_route_2` output folders are created.
- `Analyze runs` tab can open the new project output.
- Returning to the tool later shows `KIR 003` without re-uploading files.

- [ ] **Step 4: Final commit if smoke test required small fixes**

If any small smoke-test fix was needed:

```powershell
git add dashboard_streamlit.py main_final_v3.py scripts/kir_projects.py scripts/upload_sessions.py tests docs/README.md .gitignore
git commit -m "Stabilize Streamlit KIR project runner"
```

- [ ] **Step 5: Push branch**

```powershell
git push -u origin codex/streamlit-upload-runner
```

---

## Self-Review

- Spec coverage: covers named KIR projects, returning to old KIRs, arbitrary uploaded filenames, canonical internal names, project-scoped upload sessions, manifest, project-scoped runs, route selection, run selected route or both, and reuse of existing pipeline/dashboard.
- Placeholder scan: no unresolved placeholders remain.
- Scope check: focused on Streamlit wrapper and project memory only; no full pipeline rewrite, no desktop packaging, no FastAPI server.
- Type consistency: route names are `route_1`, `route_2`, `both`; roles are `kir`, `poteri`; project slug examples use `kir_003`; helper signatures are repeated consistently.
