import json
from pathlib import Path


def write_route_outputs(run_dir, raw_df, final_df, excluded_df, diagnostics):
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)

    paths = {
        "merged_raw": run_path / "merged_raw.xlsx",
        "final_clean": run_path / "final_clean_data.xlsx",
        "excluded_rows": run_path / "excluded_rows.xlsx",
        "merge_diagnostics": run_path / "merge_diagnostics.md",
    }

    raw_df.to_excel(paths["merged_raw"], index=False)
    final_df.to_excel(paths["final_clean"], index=False)
    excluded_df.to_excel(paths["excluded_rows"], index=False)

    lines = ["# Merge Diagnostics", ""]
    for key, value in diagnostics.items():
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        lines.append(f"- **{key}**: {value}")
    paths["merge_diagnostics"].write_text("\n".join(lines), encoding="utf-8")
    return paths


def assert_audit_invariants(raw_df, final_df, excluded_df):
    raw_count = len(raw_df)
    accounted_count = len(final_df) + len(excluded_df)
    if accounted_count != raw_count:
        raise ValueError(
            f"Audit invariant failed: final({len(final_df)}) + excluded({len(excluded_df)}) != raw({raw_count})"
        )
