import pandas as pd


KEY_COLUMNS = ["НеделяГод", "ТС", "Категория", "Завод"]


def _has_zero(df, candidates):
    existing = [column for column in candidates if column in df.columns]
    if not existing:
        return pd.Series(False, index=df.index)
    numeric = df[existing].apply(pd.to_numeric, errors="coerce")
    return numeric.eq(0).any(axis=1)


def _blank_or_missing(frame):
    if frame.empty:
        return pd.DataFrame(index=frame.index)
    return frame.isna() | frame.astype("string").apply(lambda column: column.str.strip().eq(""))


def _has_source_total_marker(df):
    existing = [column for column in KEY_COLUMNS if column in df.columns]
    if not existing:
        return pd.Series(False, index=df.index)
    text = df[existing].astype("string")
    return text.apply(lambda column: column.str.contains("итого|total", case=False, na=False, regex=True)).any(axis=1)


def _has_business_numeric_value(df):
    numeric_columns = [
        column
        for column in df.select_dtypes(include=["number"]).columns
        if column != "source_row_id" and not str(column).startswith("has_")
    ]
    if not numeric_columns:
        return pd.Series(False, index=df.index)
    return df[numeric_columns].notna().any(axis=1)


def _is_total_row(df):
    existing = [column for column in KEY_COLUMNS if column in df.columns]
    if not existing:
        return pd.Series(False, index=df.index)
    key_blank = _blank_or_missing(df[existing]).all(axis=1)
    return _has_source_total_marker(df) | (key_blank & _has_business_numeric_value(df))


def add_quality_flags(df):
    result = df.copy()

    result["is_total_row"] = _is_total_row(result)
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
        if bool(row.get("is_total_row")):
            reasons.append("source_total_row")
        warning_reasons.append(",".join(reasons))

    result["quality_reason"] = warning_reasons
    result["quality_status"] = result["quality_reason"].apply(lambda value: "ok" if not value else "warning")
    return result
