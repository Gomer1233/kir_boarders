import yaml

from main_final_v3 import get_route_config, parse_cli_args


def test_route_1_merge_key_has_category():
    config = yaml.safe_load(open("project_config.yaml", encoding="utf-8"))
    route = get_route_config(config, "route_1")
    assert route["merge_key"] == ["НеделяГод", "ТС", "Категория", "Завод"]


def test_route_2_merge_key_has_no_category():
    config = yaml.safe_load(open("project_config.yaml", encoding="utf-8"))
    route = get_route_config(config, "route_2")
    assert route["merge_key"] == ["НеделяГод", "ТС", "Завод"]


def test_pipeline_config_does_not_require_target_col():
    config = yaml.safe_load(open("project_config.yaml", encoding="utf-8"))
    assert "target_col" not in config.get("columns", {})


def test_route_descriptions_are_console_safe_ascii():
    config = yaml.safe_load(open("project_config.yaml", encoding="utf-8"))

    for route_name in ["route_1", "route_2"]:
        route = get_route_config(config, route_name)
        route["desc"].encode("ascii")


def test_cli_accepts_explicit_source_files_for_single_route():
    args = parse_cli_args(["route_1", "--kir", "data/route_1/кир950.xlsx", "--poteri", "data/route_1/потери.xlsx"])

    assert args.mode == "route_1"
    assert args.kir == "data/route_1/кир950.xlsx"
    assert args.poteri == "data/route_1/потери.xlsx"


def test_cli_rejects_explicit_source_files_for_both_routes():
    try:
        parse_cli_args(["both", "--kir", "kir.xlsx", "--poteri", "poteri.xlsx"])
    except ValueError as error:
        assert "--kir/--poteri can only be used with route_1 or route_2" in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_route_config_uses_explicit_source_file_overrides():
    config = yaml.safe_load(open("project_config.yaml", encoding="utf-8"))

    route = get_route_config(config, "route_1", kir_path="custom_kir.xlsx", poteri_path="custom_poteri.xlsx")

    assert route["svod"] == "custom_kir.xlsx"
    assert route["poteri"] == "custom_poteri.xlsx"
    assert route["merge_key"] == ["НеделяГод", "ТС", "Категория", "Завод"]
