import json
import re
from datetime import datetime, timezone
from pathlib import Path


PROJECTS_DIR = Path("data/projects")
VALID_ROUTES = {"route_1", "route_2"}


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


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def project_dir(project_name: str, base_dir=PROJECTS_DIR) -> Path:
    return Path(base_dir) / sanitize_project_name(project_name)


def load_registry(base_dir=PROJECTS_DIR) -> dict:
    registry_path = Path(base_dir) / "registry.json"
    if not registry_path.exists():
        return {"projects": []}
    return json.loads(registry_path.read_text(encoding="utf-8"))


def save_registry(registry: dict, base_dir=PROJECTS_DIR) -> None:
    base_path = Path(base_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    (base_path / "registry.json").write_text(
        json.dumps(registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_projects(base_dir=PROJECTS_DIR) -> list[str]:
    registry = load_registry(base_dir=base_dir)
    return sorted(project["name"] for project in registry.get("projects", []))


def create_project(project_name: str, base_dir=PROJECTS_DIR) -> Path:
    name = sanitize_project_name(project_name)
    path = project_dir(name, base_dir=base_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "uploads").mkdir(exist_ok=True)
    (path / "runs").mkdir(exist_ok=True)

    project_meta = {
        "name": name,
        "created_at": _utc_now(),
        "last_opened_at": None,
        "last_run": None,
    }
    project_json = path / "project.json"
    if not project_json.exists():
        project_json.write_text(json.dumps(project_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    registry = load_registry(base_dir=base_dir)
    projects = registry.setdefault("projects", [])
    if name not in {project["name"] for project in projects}:
        projects.append(project_meta)
        projects.sort(key=lambda project: project["name"])
        save_registry(registry, base_dir=base_dir)
    return path


def list_project_runs(project_name: str, base_dir=PROJECTS_DIR) -> list[Path]:
    runs_dir = project_dir(project_name, base_dir=base_dir) / "runs"
    if not runs_dir.exists():
        return []
    return sorted(
        [path for path in runs_dir.iterdir() if path.is_dir() and path.name.startswith("run_")],
        reverse=True,
    )


def next_project_run_dir(project_name: str, route_name: str, base_dir=PROJECTS_DIR) -> Path:
    if route_name not in VALID_ROUTES:
        raise ValueError(f"Unknown route: {route_name}")

    runs_dir = project_dir(project_name, base_dir=base_dir) / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    numbers = []
    for path in runs_dir.iterdir():
        if not path.is_dir() or not path.name.startswith("run_"):
            continue
        run_number = path.name[4:].split("_", 1)[0]
        if run_number.isdigit():
            numbers.append(int(run_number))

    next_number = max(numbers, default=0) + 1
    return runs_dir / f"run_{next_number:03d}_{route_name}"
