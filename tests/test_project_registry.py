import pytest

from scripts.project_registry import create_project, list_projects, next_project_run_dir, sanitize_project_name


def test_sanitize_project_name_allows_simple_kir_codes():
    assert sanitize_project_name("003") == "003"
    assert sanitize_project_name("KIR 950") == "KIR_950"


@pytest.mark.parametrize("name", ["", "   ", "../003", "bad/name", "bad\\name", "bad:name"])
def test_sanitize_project_name_rejects_unsafe_names(name):
    with pytest.raises(ValueError):
        sanitize_project_name(name)


def test_create_project_writes_registry_and_project_metadata(tmp_path):
    create_project("003", base_dir=tmp_path)

    assert list_projects(base_dir=tmp_path) == ["003"]
    assert (tmp_path / "003" / "project.json").exists()
    assert (tmp_path / "003" / "uploads").exists()
    assert (tmp_path / "003" / "runs").exists()


def test_next_project_run_dir_uses_project_runs_folder(tmp_path):
    create_project("003", base_dir=tmp_path)
    first = next_project_run_dir("003", "route_1", base_dir=tmp_path)
    first.mkdir(parents=True)

    second = next_project_run_dir("003", "route_2", base_dir=tmp_path)

    assert first.name == "run_001_route_1"
    assert second.name == "run_002_route_2"
