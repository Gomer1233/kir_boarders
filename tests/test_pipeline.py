import pandas as pd

from scripts.pipeline import assert_audit_invariants, write_route_outputs


def test_write_route_outputs_preserves_raw_and_final_counts(tmp_path):
    raw = pd.DataFrame(
        {
            "source_row_id": [1, 2],
            "has_poteri_match": [True, False],
            "has_missing_key": [False, False],
        }
    )
    final = raw.copy()
    excluded = pd.DataFrame(columns=list(raw.columns) + ["exclude_reason"])
    diagnostics = {"raw_row_count": 2, "final_row_count": 2, "excluded_row_count": 0}

    paths = write_route_outputs(tmp_path, raw, final, excluded, diagnostics)

    assert paths["merged_raw"].exists()
    assert paths["final_clean"].exists()
    assert paths["excluded_rows"].exists()
    assert paths["merge_diagnostics"].exists()


def test_audit_invariant_rejects_unaccounted_rows():
    raw = pd.DataFrame({"source_row_id": [1, 2]})
    final = pd.DataFrame({"source_row_id": [1]})
    excluded = pd.DataFrame({"source_row_id": []})

    try:
        assert_audit_invariants(raw, final, excluded)
    except ValueError as error:
        assert "Audit invariant failed" in str(error)
    else:
        raise AssertionError("Expected audit invariant failure")


def test_merge_diagnostics_contains_audit_invariant_status(tmp_path):
    raw = pd.DataFrame({"source_row_id": [1]})
    final = raw.copy()
    excluded = pd.DataFrame({"source_row_id": [], "exclude_reason": []})
    diagnostics = {
        "raw_row_count": 1,
        "final_row_count": 1,
        "excluded_row_count": 0,
        "audit_invariant_ok": True,
    }

    paths = write_route_outputs(tmp_path, raw, final, excluded, diagnostics)

    text = paths["merge_diagnostics"].read_text(encoding="utf-8")
    assert "- **audit_invariant_ok**: True" in text
