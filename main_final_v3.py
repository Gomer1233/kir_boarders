import os
import sys
import traceback

import pandas as pd
import yaml

from scripts.merge_data_v3 import merge_route_data
from scripts.pipeline import assert_audit_invariants, write_route_outputs
from scripts.quality_flags import add_quality_flags


def load_config():
    config_path = os.path.join(os.getcwd(), "project_config.yaml")
    with open(config_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def get_next_run_number(base_dir):
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
        return 1

    numbers = []
    for name in os.listdir(base_dir):
        if not name.startswith("run_"):
            continue
        run_number = name[4:].split("_", 1)[0]
        if run_number.isdigit():
            numbers.append(int(run_number))

    if not numbers:
        return 1
    return max(numbers) + 1


def get_route_config(config, route_name):
    if route_name == "route_1":
        return {
            "name": "route_1",
            "svod": os.path.join(config["inputs"]["route_1"], "kir_with_cats.xlsx"),
            "poteri": os.path.join(config["inputs"]["route_1"], "poteri_with_cats.xlsx"),
            "merge_key": ["НеделяГод", "ТС", "Категория", "Завод"],
            "desc": "route 1 with categories",
        }
    if route_name == "route_2":
        return {
            "name": "route_2",
            "svod": os.path.join(config["inputs"]["route_2"], "kir_without_cats.xlsx"),
            "poteri": os.path.join(config["inputs"]["route_2"], "poteri_without_cats.xlsx"),
            "merge_key": ["НеделяГод", "ТС", "Завод"],
            "desc": "route 2 without categories",
        }
    raise ValueError(f"Unknown route: {route_name}")


def _routes_for_mode(mode):
    if mode == "route_1":
        return ["route_1"]
    if mode == "route_2":
        return ["route_2"]
    if mode == "both":
        return ["route_1", "route_2"]
    raise ValueError(f"Unknown mode: {mode}")


def run_route(config, route_name):
    route_conf = get_route_config(config, route_name)
    run_num = get_next_run_number("data")
    run_dir = os.path.join("data", f"run_{run_num}_{route_name}")

    print("\n" + "=" * 60)
    print(f"START RUN #{run_num} - {route_conf['desc']}")
    print(f"KIR path: {route_conf['svod']}")
    print(f"poteri path: {route_conf['poteri']}")
    print("=" * 60)

    kir_df = pd.read_excel(route_conf["svod"])
    poteri_df = pd.read_excel(route_conf["poteri"])

    raw_df, diagnostics = merge_route_data(
        kir_df,
        poteri_df,
        route_conf["merge_key"],
        config["columns"]["poteri"]["rename_map"],
    )
    final_df = add_quality_flags(raw_df)
    excluded_df = raw_df.iloc[0:0].copy()
    excluded_df["exclude_reason"] = []

    diagnostics.update(
        {
            "route": route_name,
            "final_row_count": len(final_df),
            "excluded_row_count": len(excluded_df),
            "audit_invariant_ok": len(final_df) + len(excluded_df) == len(raw_df),
        }
    )

    assert_audit_invariants(raw_df, final_df, excluded_df)
    paths = write_route_outputs(run_dir, raw_df, final_df, excluded_df, diagnostics)

    print(f"merged_raw: {paths['merged_raw']}")
    print(f"final_clean_data: {paths['final_clean']}")
    print(f"excluded_rows: {paths['excluded_rows']}")
    print(f"merge_diagnostics: {paths['merge_diagnostics']}")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    config = load_config()

    args = [arg for arg in argv if arg != "--no-dashboard"]
    mode = args[0].lower() if args else config.get("mode", "route_1")

    try:
        routes = _routes_for_mode(mode)
    except ValueError as error:
        print(f"ERROR: {error}")
        return 1

    failed = False
    for route_name in routes:
        try:
            run_route(config, route_name)
        except Exception as error:
            failed = True
            print(f"PROCESS ERROR ({route_name}): {error}")
            traceback.print_exc()

    if failed:
        print("\nFAILED\n")
        return 1

    print("\n" + "=" * 60)
    print(f"ALL RUNS COMPLETED (mode: {mode})")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
