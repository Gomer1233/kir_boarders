import importlib


def test_main_final_v3_is_importable():
    importlib.import_module("main_final_v3")


def test_next_run_number_counts_route_suffixed_runs(tmp_path):
    module = importlib.import_module("main_final_v3")

    (tmp_path / "run_1").mkdir()
    (tmp_path / "run_4_route_1").mkdir()

    assert module.get_next_run_number(tmp_path) == 5
