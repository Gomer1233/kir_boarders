import pandas as pd


def _has_zero(df, candidates):
    existing = [column for column in candidates if column in df.columns]
    if not existing:
        return pd.Series(False, index=df.index)
    numeric = df[existing].apply(pd.to_numeric, errors="coerce")
    return numeric.eq(0).any(axis=1)


def add_quality_flags(df):
    result = df.copy()

    result["has_zero_writeoffs"] = _has_zero(result, ["Списания"])
    result["has_zero_revenue"] = _has_zero(result, ["Выручка"])
    result["has_zero_stock"] = _has_zero(result, ["Свободный ТЗ"])
    result["has_zero_kir_units"] = _has_zero(
        result,
        [column for column in result.columns if column.startswith("КИР-") and "шт" in column],
    )

    warning_reasons = []
    for _, row in result.iterrows():
        reasons = []
        if not bool(row.get("has_poteri_match")):
            reasons.append("no_poteri_match")
        if bool(row.get("has_missing_key")):
            reasons.append("missing_merge_key")
        if bool(row.get("has_duplicate_kir_key")):
            reasons.append("duplicate_kir_key")
        if bool(row.get("has_duplicate_poteri_key")):
            reasons.append("duplicate_poteri_key")
        warning_reasons.append(",".join(reasons))

    result["quality_reason"] = warning_reasons
    result["quality_status"] = result["quality_reason"].apply(lambda value: "ok" if not value else "warning")
    return result
