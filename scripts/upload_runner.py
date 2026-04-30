import json
from datetime import datetime, timezone
from pathlib import Path

from main_final_v3 import get_route_config
from scripts.excel_reader import read_excel_loss_safe
from scripts.merge_data_v3 import merge_route_data
from scripts.pipeline import assert_audit_invariants, write_route_outputs
from scripts.kir_percentages import add_kir_percentage_columns
from scripts.project_registry import PROJECTS_DIR, VALID_ROUTES, project_dir, sanitize_project_name
from scripts.quality_flags import add_quality_flags


KIR_SOURCE_NAME = "kir_source.xlsx"
POTERI_SOURCE_NAME = "poteri_source.xlsx"
UPLOAD_MANIFEST_NAME = "upload_manifest.json"
SUPPORTED_UPLOAD_SUFFIXES = {".xlsx"}


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _upload_bytes(uploaded_file):
    if hasattr(uploaded_file, "getbuffer"):
        return bytes(uploaded_file.getbuffer())
    if hasattr(uploaded_file, "read"):
        return uploaded_file.read()
    raise TypeError("Uploaded file must provide getbuffer() or read().")


def _require_supported_upload(uploaded_file, label):
    name = getattr(uploaded_file, "name", "")
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
        raise ValueError(f"Only .xlsx uploads are supported for {label}: {name}")


def _validate_route(route_name):
    if route_name not in VALID_ROUTES:
        raise ValueError(f"Unknown route: {route_name}")


def _project_upload_route_dir(project_name, route_name, base_dir=PROJECTS_DIR):
    _validate_route(route_name)
    return project_dir(project_name, base_dir=base_dir) / "uploads" / route_name


def build_project_route_config(project_name, route_name, config, base_dir=PROJECTS_DIR) -> dict:
    route = dict(get_route_config(config, route_name))
    upload_dir = _project_upload_route_dir(project_name, route_name, base_dir=base_dir)
    route["svod"] = upload_dir / KIR_SOURCE_NAME
    route["poteri"] = upload_dir / POTERI_SOURCE_NAME
    return route


def _require_upload_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing upload file: {path}")


def save_uploaded_route_files(project_name, route_name, kir_file, poteri_file, base_dir=PROJECTS_DIR) -> dict:
    name = sanitize_project_name(project_name)
    project_path = project_dir(name, base_dir=base_dir)
    if not project_path.exists():
        raise FileNotFoundError(f"Project does not exist: {name}")
    _require_supported_upload(kir_file, "KIR")
    _require_supported_upload(poteri_file, "Poteri")

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


def run_project_route(
    project_name,
    route_name,
    config,
    base_dir=PROJECTS_DIR,
    read_excel=read_excel_loss_safe,
    merge_data=merge_route_data,
    add_flags=add_quality_flags,
    assert_invariants=assert_audit_invariants,
    write_outputs=write_route_outputs,
    progress_callback=None,
) -> dict:
    def report(stage, message):
        if progress_callback is not None:
            progress_callback(stage, message)

    name = sanitize_project_name(project_name)
    route_conf = build_project_route_config(name, route_name, config, base_dir=base_dir)
    report("validate_uploads", f"Validating uploaded files for {route_name}.")
    _require_upload_file(route_conf["svod"])
    _require_upload_file(route_conf["poteri"])

    from scripts.project_registry import next_project_run_dir

    report("create_run_dir", f"Creating run directory for {route_name}.")
    run_dir = next_project_run_dir(name, route_name, base_dir=base_dir)
    report("read_kir", f"Reading KIR source file for {route_name}.")
    kir_df = read_excel(route_conf["svod"])
    report("read_poteri", f"Reading Poteri source file for {route_name}.")
    poteri_df = read_excel(route_conf["poteri"])
    report("merge", f"Creating raw merge file for {route_name}.")
    raw_df, diagnostics = merge_data(
        kir_df,
        poteri_df,
        route_conf["merge_key"],
        config["columns"]["poteri"]["rename_map"],
    )
    report("quality_flags", f"Adding quality flags for {route_name}.")
    final_df = add_kir_percentage_columns(add_flags(raw_df))
    excluded_df = raw_df.iloc[0:0].copy()
    excluded_df["exclude_reason"] = []

    diagnostics.update(
        {
            "project_name": name,
            "route": route_name,
            "final_row_count": len(final_df),
            "excluded_row_count": len(excluded_df),
            "audit_invariant_ok": len(final_df) + len(excluded_df) == len(raw_df),
        }
    )

    report("audit", f"Checking audit invariants for {route_name}.")
    assert_invariants(raw_df, final_df, excluded_df)
    report("write_outputs", f"Writing final_clean_data.xlsx and merged_raw.xlsx for {route_name}.")
    paths = write_outputs(run_dir, raw_df, final_df, excluded_df, diagnostics)
    report("done", f"Finished {route_name}.")
    return {"project": name, "route": route_name, "run_dir": run_dir, "paths": paths, "diagnostics": diagnostics}


def run_project_routes(project_name, routes, config, base_dir=PROJECTS_DIR, progress_callback=None) -> list[dict]:
    return [
        run_project_route(project_name, route, config, base_dir=base_dir, progress_callback=progress_callback)
        for route in routes
    ]
