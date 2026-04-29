import re
import warnings

import pandas as pd


def normalize_week(value):
    if pd.isna(value):
        return None

    if isinstance(value, float) and value.is_integer():
        value = int(value)

    text = str(value).strip()
    if not text:
        return None

    full_match = re.fullmatch(r"(\d{6})(?:\.0+)?", text)
    if full_match:
        return full_match.group(1)

    split_match = re.fullmatch(r"(\d{4})\D+(\d{1,2})", text)
    if split_match:
        return f"{split_match.group(1)}{int(split_match.group(2)):02d}"

    digits = re.sub(r"\D", "", text)
    if len(digits) == 6:
        return digits
    return None


def _normalize_key_columns(df, key_columns):
    result = df.copy()
    for column in key_columns:
        if column not in result.columns:
            result[column] = pd.NA
        if column == "НеделяГод":
            result[column] = result[column].apply(normalize_week)
        else:
            result[column] = result[column].astype("string").str.strip()
            result.loc[result[column].isin(["", "<NA>", "nan", "None"]), column] = pd.NA
    return result


def _duplicate_summary(df, key_columns):
    duplicated = df[df.duplicated(key_columns, keep=False)]
    if duplicated.empty:
        return []
    grouped = duplicated.groupby(key_columns, dropna=False).size().reset_index(name="count")
    return grouped.to_dict("records")


def merge_route_data(kir_df, poteri_df, merge_key, poteri_rename_map):
    kir = kir_df.copy()
    kir.insert(0, "source_row_id", range(1, len(kir) + 1))

    poteri = poteri_df.rename(columns=poteri_rename_map).copy()

    kir = _normalize_key_columns(kir, merge_key)
    poteri = _normalize_key_columns(poteri, merge_key)
    kir["has_missing_key"] = kir[merge_key].isna().any(axis=1)
    poteri["has_missing_key"] = poteri[merge_key].isna().any(axis=1)

    poteri_value_columns = [
        column for column in ["Списания", "Выручка", "Свободный ТЗ"] if column in poteri.columns
    ]
    poteri_merge_columns = merge_key + poteri_value_columns

    # pandas matches NA keys with each other, so missing-key rows must not enter matching.
    kir_matchable = kir[~kir["has_missing_key"]].copy()
    kir_missing_key = kir[kir["has_missing_key"]].copy()
    poteri_matchable = poteri[~poteri["has_missing_key"]].copy()

    matched = kir_matchable.merge(
        poteri_matchable[poteri_merge_columns],
        on=merge_key,
        how="left",
        indicator=True,
    )
    matched["has_poteri_match"] = matched["_merge"].eq("both")
    matched = matched.drop(columns=["_merge"])

    for column in poteri_value_columns:
        kir_missing_key[column] = pd.NA
    kir_missing_key["has_poteri_match"] = False

    merge_parts = [part for part in [matched, kir_missing_key] if not part.empty]
    if not merge_parts:
        merged = kir.iloc[0:0].copy()
    elif len(merge_parts) == 1:
        merged = merge_parts[0].copy()
    else:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="The behavior of DataFrame concatenation with empty or all-NA entries is deprecated.*",
                category=FutureWarning,
            )
            merged = pd.concat(merge_parts, ignore_index=True, sort=False)
    merged = merged.sort_values("source_row_id", kind="stable").reset_index(drop=True)

    merged["missing_key_columns"] = merged[merge_key].isna().apply(
        lambda row: ",".join(row.index[row].tolist()), axis=1
    )

    duplicate_kir_keys = _duplicate_summary(kir, merge_key)
    duplicate_poteri_keys = _duplicate_summary(poteri, merge_key)
    duplicate_kir_key_set = {tuple(row[column] for column in merge_key) for row in duplicate_kir_keys}
    duplicate_poteri_key_set = {
        tuple(row[column] for column in merge_key) for row in duplicate_poteri_keys
    }
    merged_key_tuples = merged[merge_key].apply(tuple, axis=1)
    merged["has_duplicate_kir_key"] = merged_key_tuples.isin(duplicate_kir_key_set)
    merged["has_duplicate_poteri_key"] = merged_key_tuples.isin(duplicate_poteri_key_set)

    diagnostics = {
        "kir_input_rows": int(len(kir_df)),
        "poteri_input_rows": int(len(poteri_df)),
        "raw_row_count": int(len(merged)),
        "rows_with_poteri_match": int(merged["has_poteri_match"].sum()),
        "rows_without_poteri_match": int((~merged["has_poteri_match"]).sum()),
        "missing_key_rows": int(merged["has_missing_key"].sum()),
        "duplicate_kir_keys": duplicate_kir_keys,
        "duplicate_poteri_keys": duplicate_poteri_keys,
        "merge_key": merge_key,
    }
    return merged, diagnostics
