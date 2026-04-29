import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.project_registry import PROJECTS_DIR, VALID_ROUTES, project_dir, sanitize_project_name


KIR_SOURCE_NAME = "kir_source.xlsx"
POTERI_SOURCE_NAME = "poteri_source.xlsx"
UPLOAD_MANIFEST_NAME = "upload_manifest.json"


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _upload_bytes(uploaded_file):
    if hasattr(uploaded_file, "getbuffer"):
        return bytes(uploaded_file.getbuffer())
    if hasattr(uploaded_file, "read"):
        return uploaded_file.read()
    raise TypeError("Uploaded file must provide getbuffer() or read().")


def _validate_route(route_name):
    if route_name not in VALID_ROUTES:
        raise ValueError(f"Unknown route: {route_name}")


def _project_upload_route_dir(project_name, route_name, base_dir=PROJECTS_DIR):
    _validate_route(route_name)
    return project_dir(project_name, base_dir=base_dir) / "uploads" / route_name


def save_uploaded_route_files(project_name, route_name, kir_file, poteri_file, base_dir=PROJECTS_DIR) -> dict:
    name = sanitize_project_name(project_name)
    project_path = project_dir(name, base_dir=base_dir)
    if not project_path.exists():
        raise FileNotFoundError(f"Project does not exist: {name}")

    upload_dir = _project_upload_route_dir(name, route_name, base_dir=base_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    kir_path = upload_dir / KIR_SOURCE_NAME
    poteri_path = upload_dir / POTERI_SOURCE_NAME
    kir_path.write_bytes(_upload_bytes(kir_file))
    poteri_path.write_bytes(_upload_bytes(poteri_file))

    manifest = {
        "route": route_name,
        "kir_original_name": getattr(kir_file, "name", KIR_SOURCE_NAME),
        "poteri_original_name": getattr(poteri_file, "name", POTERI_SOURCE_NAME),
        "saved_at": _utc_now(),
    }
    manifest_path = upload_dir / UPLOAD_MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "project": name,
        "route": route_name,
        "kir_path": kir_path,
        "poteri_path": poteri_path,
        "manifest_path": manifest_path,
    }
