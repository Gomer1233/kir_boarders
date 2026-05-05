import json
from io import BytesIO

import pytest
import pandas as pd

from main_final_v3 import get_route_config
from scripts.project_registry import create_project
from scripts.upload_runner import build_project_route_config, run_project_route, save_uploaded_route_files


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


def test_save_uploaded_route_files_requires_existing_project(tmp_path):
    with pytest.raises(FileNotFoundError, match="Project does not exist"):
        save_uploaded_route_files(
            "missing",
            "route_1",
            FakeUpload("kir.xlsx", b"kir"),
            FakeUpload("poteri.xlsx", b"poteri"),
            base_dir=tmp_path,
        )


def test_save_uploaded_route_files_rejects_unknown_route(tmp_path):
    create_project("003", base_dir=tmp_path)

    with pytest.raises(ValueError, match="Unknown route"):
        save_uploaded_route_files(
            "003",
            "route_3",
            FakeUpload("kir.xlsx", b"kir"),
            FakeUpload("poteri.xlsx", b"poteri"),
            base_dir=tmp_path,
        )


def test_save_uploaded_route_files_rejects_xls_uploads(tmp_path):
    create_project("003", base_dir=tmp_path)

    with pytest.raises(ValueError, match="Only .xlsx uploads are supported"):
        save_uploaded_route_files(
            "003",
            "route_1",
            FakeUpload("kir.xls", b"kir"),
            FakeUpload("poteri.xlsx", b"poteri"),
            base_dir=tmp_path,
        )


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


def test_run_project_route_uses_project_uploads_and_run_directory(tmp_path):
    create_project("003", base_dir=tmp_path)
    upload_dir = tmp_path / "003" / "uploads" / "route_1"
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "kir_source.xlsx").write_bytes(b"kir")
    (upload_dir / "poteri_source.xlsx").write_bytes(b"poteri")
    calls = {}
    config = {
        "inputs": {"route_1": "data/route_1", "route_2": "data/route_2"},
        "columns": {"poteri": {"rename_map": {"old": "new"}}},
    }

    def fake_read(path):
        calls.setdefault("read_paths", []).append(path)
        return pd.DataFrame({"source": [str(path)]})

    def fake_merge(kir_df, poteri_df, merge_key, rename_map):
        calls["merge_key"] = merge_key
        calls["rename_map"] = rename_map
        return pd.DataFrame({"КИР-950 руб": [25.0], "Списания": [200.0], "Выручка": [100.0], "Свободный ТЗ": [50.0]}), {"raw_row_count": 1}

    def fake_add_flags(raw_df):
        result = raw_df.copy()
        result["quality_status"] = "ok"
        return result

    def fake_assert_invariants(raw_df, final_df, excluded_df):
        calls["asserted"] = (len(raw_df), len(final_df), len(excluded_df))

    def fake_write_outputs(run_dir, raw_df, final_df, excluded_df, diagnostics):
        calls["run_dir"] = run_dir
        calls["diagnostics"] = diagnostics
        calls["final_columns"] = list(final_df.columns)
        calls["final_df"] = final_df.copy()
        return {"final_clean": run_dir / "final_clean_data.xlsx", "merged_raw": run_dir / "merged_raw.xlsx"}

    result = run_project_route(
        "003",
        "route_1",
        config,
        base_dir=tmp_path,
        read_excel=fake_read,
        merge_data=fake_merge,
        add_flags=fake_add_flags,
        assert_invariants=fake_assert_invariants,
        write_outputs=fake_write_outputs,
    )

    assert calls["read_paths"] == [upload_dir / "kir_source.xlsx", upload_dir / "poteri_source.xlsx"]
    assert calls["merge_key"] == get_route_config(config, "route_1")["merge_key"]
    assert calls["rename_map"] == {"old": "new"}
    assert calls["asserted"] == (1, 1, 0)
    assert calls["run_dir"] == tmp_path / "003" / "runs" / "run_001_route_1"
    assert calls["diagnostics"]["project_name"] == "003"
    assert calls["diagnostics"]["route"] == "route_1"
    assert "КИР-950 руб / Выручка, %" in calls["final_columns"]
    assert calls["final_df"].loc[0, "КИР-950 руб / Выручка, %"] == 25.0
    assert result["route"] == "route_1"
    assert result["run_dir"] == tmp_path / "003" / "runs" / "run_001_route_1"


def test_run_project_route_reports_progress_stages(tmp_path):
    create_project("003", base_dir=tmp_path)
    upload_dir = tmp_path / "003" / "uploads" / "route_1"
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "kir_source.xlsx").write_bytes(b"kir")
    (upload_dir / "poteri_source.xlsx").write_bytes(b"poteri")
    stages = []
    config = {
        "inputs": {"route_1": "data/route_1", "route_2": "data/route_2"},
        "columns": {"poteri": {"rename_map": {}}},
    }

    run_project_route(
        "003",
        "route_1",
        config,
        base_dir=tmp_path,
        read_excel=lambda path: pd.DataFrame({"value": [1]}),
        merge_data=lambda kir_df, poteri_df, merge_key, rename_map: (pd.DataFrame({"value": [1]}), {"raw_row_count": 1}),
        add_flags=lambda raw_df: raw_df.copy(),
        assert_invariants=lambda raw_df, final_df, excluded_df: None,
        write_outputs=lambda run_dir, raw_df, final_df, excluded_df, diagnostics: {},
        progress_callback=lambda stage, message: stages.append((stage, message)),
    )

    assert [stage for stage, _ in stages] == [
        "validate_uploads",
        "create_run_dir",
        "read_kir",
        "read_poteri",
        "merge",
        "quality_flags",
        "audit",
        "write_outputs",
        "done",
    ]
    assert any("merge" in message.lower() for _, message in stages)


def test_run_project_route_requires_uploaded_files(tmp_path):
    create_project("003", base_dir=tmp_path)
    config = {
        "inputs": {"route_1": "data/route_1", "route_2": "data/route_2"},
        "columns": {"poteri": {"rename_map": {}}},
    }

    with pytest.raises(FileNotFoundError, match="Missing upload file"):
        run_project_route("003", "route_1", config, base_dir=tmp_path)
