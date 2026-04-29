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
