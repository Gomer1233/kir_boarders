import yaml

from main_final_v3 import get_route_config


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
