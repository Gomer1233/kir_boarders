# Streamlit Upload Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a simple Streamlit UI layer that lets a user upload arbitrary-named KIR and poteri files, run `route_1`, `route_2`, or both, and then inspect generated outputs in the existing dashboard.

**Architecture:** Keep the current pipeline intact. Add a thin upload/session layer that copies uploaded files into `data/input_uploads/upload_N/...` using canonical file names, writes `upload_manifest.json`, and calls the existing route runner with explicit file paths. Extend `dashboard_streamlit.py` with a runner tab while preserving the current analysis view.

**Tech Stack:** Python, Streamlit, pandas/openpyxl for output reads, existing `main_final_v3.py` pipeline modules, pytest.

---

## File Structure

- Create `scripts/upload_sessions.py`: owns upload session numbering, canonical filenames, manifest writing, and safe file persistence.
- Modify `main_final_v3.py`: allow `run_route()` to receive explicit KIR/poteri file paths from UI while keeping CLI/config behavior unchanged.
- Modify `dashboard_streamlit.py`: add two tabs, `Run pipeline` and `Analyze runs`; upload files, choose route, run pipeline, show result paths.
- Add `tests/test_upload_sessions.py`: tests canonical renaming and manifest content.
- Extend `tests/test_main_cli.py`: tests route config override without changing CLI behavior.
- Extend `tests/test_dashboard_streamlit.py`: tests helper selection logic without requiring Streamlit runtime interaction.
- Modify `.gitignore`: ignore `.superpowers/` local brainstorming artifacts.
- Modify `docs/README.md`: document UI workflow.

---

### Task 1: Upload Session Storage

**Files:**
- Create: `scripts/upload_sessions.py`
- Test: `tests/test_upload_sessions.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_upload_sessions.py`:

```python
from io import BytesIO
import json

from scripts.upload_sessions import CANONICAL_FILES, create_upload_session, save_upload_file


class UploadedFileStub:
    def __init__(self, name, content):
        self.name = name
        self._content = content

    def getbuffer(self):
        return memoryview(self._content)


def test_create_upload_session_uses_next_number(tmp_path):
    root = tmp_path / "input_uploads"
    (root / "upload_1").mkdir(parents=True)
    (root / "upload_3").mkdir(parents=True)

    session = create_upload_session(root)

    assert session.name == "upload_4"
    assert session.exists()


def test_save_upload_file_uses_canonical_name_and_manifest(tmp_path):
    session = create_upload_session(tmp_path / "input_uploads")
    uploaded = UploadedFileStub("random user name.xlsx", b"excel-bytes")

    saved = save_upload_file(session, "route_1", "kir", uploaded)

    expected = session / "route_1" / CANONICAL_FILES[("route_1", "kir")]
    assert saved == expected
    assert saved.read_bytes() == b"excel-bytes"

    manifest = json.loads((session / "upload_manifest.json").read_text(encoding="utf-8"))
    assert manifest["session"] == session.name
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


def create_upload_session(root="data/input_uploads"):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    numbers = []
    for path in root.iterdir():
        if not path.is_dir() or not path.name.startswith("upload_"):
            continue
        suffix = path.name.removeprefix("upload_")
        if suffix.isdigit():
            numbers.append(int(suffix))
    next_number = max(numbers, default=0) + 1
    session = root / f"upload_{next_number}"
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


def _read_manifest(session):
    manifest_path = Path(session) / "upload_manifest.json"
    if not manifest_path.exists():
        return {"session": Path(session).name, "files": []}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _write_manifest(session, files):
    session = Path(session)
    manifest = {"session": session.name, "files": files}
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
git commit -m "Add upload session storage"
```

---

### Task 2: Route Runner File Overrides

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
                "kir": "data/input_uploads/upload_1/route_1/kir_with_cats.xlsx",
                "poteri": "data/input_uploads/upload_1/route_1/poteri_with_cats.xlsx",
            }
        },
    )

    assert route["svod"] == "data/input_uploads/upload_1/route_1/kir_with_cats.xlsx"
    assert route["poteri"] == "data/input_uploads/upload_1/route_1/poteri_with_cats.xlsx"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests\test_main_cli.py::test_route_config_accepts_explicit_input_paths -q
```

Expected: FAIL with `TypeError: get_route_config() got an unexpected keyword argument 'input_paths'`.

- [ ] **Step 3: Update route config and runner signatures**

In `main_final_v3.py`, change signatures and path selection:

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

Change `run_route` signature:

```python
def run_route(config, route_name, input_paths=None):
    route_conf = get_route_config(config, route_name, input_paths=input_paths)
```

Leave CLI `main()` unchanged except internal call may continue as:

```python
run_route(config, route_name)
```

- [ ] **Step 4: Run targeted tests**

Run:

```powershell
python -m pytest tests\test_main_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit task**

```powershell
git add main_final_v3.py tests/test_main_cli.py
git commit -m "Allow route input path overrides"
```

---

### Task 3: Dashboard Runner Helpers

**Files:**
- Modify: `dashboard_streamlit.py`
- Test: `tests/test_dashboard_streamlit.py`

- [ ] **Step 1: Write helper tests**

Append to `tests/test_dashboard_streamlit.py`:

```python
from dashboard_streamlit import required_upload_roles, route_input_paths_from_session


def test_required_upload_roles_for_both_routes():
    assert required_upload_roles("both") == [
        ("route_1", "kir"),
        ("route_1", "poteri"),
        ("route_2", "kir"),
        ("route_2", "poteri"),
    ]


def test_route_input_paths_from_session(tmp_path):
    session = tmp_path / "upload_1"
    assert route_input_paths_from_session(session, "route_1") == {
        "route_1": {
            "kir": str(session / "route_1" / "kir_with_cats.xlsx"),
            "poteri": str(session / "route_1" / "poteri_with_cats.xlsx"),
        }
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests\test_dashboard_streamlit.py -q
```

Expected: FAIL because helpers are missing.

- [ ] **Step 3: Add dashboard helper functions**

In `dashboard_streamlit.py`, import canonical map:

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
git commit -m "Add dashboard runner helpers"
```

---

### Task 4: Streamlit Upload and Run Tab

**Files:**
- Modify: `dashboard_streamlit.py`
- Test: `tests/test_dashboard_streamlit.py`

- [ ] **Step 1: Add a test for upload label text**

Append to `tests/test_dashboard_streamlit.py`:

```python
from dashboard_streamlit import upload_label


def test_upload_label_is_human_readable():
    assert upload_label("route_1", "kir") == "route_1: KIR with categories"
    assert upload_label("route_2", "poteri") == "route_2: poteri without categories"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests\test_dashboard_streamlit.py::test_upload_label_is_human_readable -q
```

Expected: FAIL because `upload_label` is missing.

- [ ] **Step 3: Add upload labels and imports**

In `dashboard_streamlit.py`, add imports:

```python
from main_final_v3 import load_config, run_route
from scripts.upload_sessions import create_upload_session, save_upload_file
```

Add helper:

```python
def upload_label(route, role):
    labels = {
        ("route_1", "kir"): "route_1: KIR with categories",
        ("route_1", "poteri"): "route_1: poteri with categories",
        ("route_2", "kir"): "route_2: KIR without categories",
        ("route_2", "poteri"): "route_2: poteri without categories",
    }
    return labels[(route, role)]
```

- [ ] **Step 4: Split UI into tabs**

In `main()` replace the current straight-line UI with tabs:

```python
st.set_page_config(page_title="KIR Dashboard", layout="wide")
st.title("KIR Pipeline Studio")
runner_tab, analysis_tab = st.tabs(["Run pipeline", "Analyze runs"])
with runner_tab:
    render_runner_tab()
with analysis_tab:
    render_analysis_tab()
```

Move the existing analysis body from `main()` into:

```python
def render_analysis_tab():
    run_dirs = list_run_dirs()
    if not run_dirs:
        st.warning("No run directories found in data/.")
        return
    # existing analysis code continues here
```

Add runner tab:

```python
def render_runner_tab():
    config = load_config()
    mode = st.radio("Route", ["route_1", "route_2", "both"], horizontal=True)
    uploads = {}
    for route, role in required_upload_roles(mode):
        uploads[(route, role)] = st.file_uploader(
            upload_label(route, role),
            type=["xlsx", "xlsm", "xls"],
            key=f"upload-{route}-{role}-{mode}",
        )

    ready = all(file is not None for file in uploads.values())
    if not ready:
        st.info("Upload all required files for the selected route mode.")
        return

    if st.button("Run selected pipeline", type="primary"):
        session = create_upload_session()
        for (route, role), uploaded_file in uploads.items():
            save_upload_file(session, route, role, uploaded_file)

        input_paths = route_input_paths_from_session(session, mode)
        routes = ["route_1", "route_2"] if mode == "both" else [mode]
        with st.status("Running pipeline...", expanded=True) as status:
            for route in routes:
                st.write(f"Running {route}...")
                run_route(config, route, input_paths=input_paths)
            status.update(label="Pipeline completed", state="complete")

        st.success(f"Upload session saved: {session}")
        st.info("Open the Analyze runs tab and select the newest run folder.")
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest tests\test_dashboard_streamlit.py -q
```

Expected: all dashboard helper tests pass.

- [ ] **Step 6: Commit task**

```powershell
git add dashboard_streamlit.py tests/test_dashboard_streamlit.py
git commit -m "Add Streamlit upload runner tab"
```

---

### Task 5: Gitignore and Documentation

**Files:**
- Modify: `.gitignore`
- Modify: `docs/README.md`

- [ ] **Step 1: Ignore local brainstorming artifacts**

Add to `.gitignore`:

```text
# Local planning/mockup artifacts
.superpowers/
```

- [ ] **Step 2: Document UI workflow**

In `docs/README.md`, update `Dashboard` section to:

```markdown
## Dashboard / UI Runner

Run:

```powershell
streamlit run dashboard_streamlit.py
```

The Streamlit app has two tabs:

- `Run pipeline`: upload arbitrary-named KIR and poteri files, choose `route_1`, `route_2`, or `both`, and run the existing pipeline.
- `Analyze runs`: inspect generated `final_clean_data.xlsx` outputs.

Uploaded files are copied into a dedicated session folder under:

```text
data/input_uploads/upload_N/
```

The app stores files under canonical names regardless of original uploaded filename:

```text
route_1/kir_with_cats.xlsx
route_1/poteri_with_cats.xlsx
route_2/kir_without_cats.xlsx
route_2/poteri_without_cats.xlsx
```

Each upload session includes `upload_manifest.json` with original filenames, canonical filenames, size, route, and role.
```

- [ ] **Step 3: Commit docs**

```powershell
git add .gitignore docs/README.md
git commit -m "Document Streamlit upload runner workflow"
```

---

### Task 6: Final Verification

**Files:**
- Verify only

- [ ] **Step 1: Run full tests**

```powershell
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Compile changed modules**

```powershell
python -m py_compile dashboard_streamlit.py main_final_v3.py scripts\upload_sessions.py
```

Expected: exit code 0.

- [ ] **Step 3: Manual UI smoke test**

Run:

```powershell
streamlit run dashboard_streamlit.py
```

Manual expected result:

- `Run pipeline` tab appears.
- Selecting `route_1` asks for exactly two files.
- Selecting `route_2` asks for exactly two files.
- Selecting `both` asks for exactly four files.
- Uploaded files can have arbitrary names.
- After run, `data/input_uploads/upload_N/upload_manifest.json` exists.
- New `data/run_N_route_1` or `data/run_N_route_2` output folders are created.
- `Analyze runs` tab can open the new output.

- [ ] **Step 4: Final commit if smoke test required small fixes**

If any small smoke-test fix was needed:

```powershell
git add dashboard_streamlit.py main_final_v3.py scripts/upload_sessions.py tests docs/README.md .gitignore
git commit -m "Stabilize Streamlit upload runner"
```

- [ ] **Step 5: Push branch**

```powershell
git push -u origin codex/streamlit-upload-runner
```

---

## Self-Review

- Spec coverage: covers arbitrary uploaded filenames, canonical internal names, upload sessions, manifest, route selection, run selected route or both, and reuse of existing pipeline/dashboard.
- Placeholder scan: no TBD/TODO placeholders remain.
- Scope check: focused on Streamlit wrapper only; no pipeline rewrite, no desktop packaging, no FastAPI server.
- Type consistency: route names are `route_1`, `route_2`, `both`; roles are `kir`, `poteri`; helper signatures are repeated consistently.
