import pandas as pd


KIR_PREFIX = "КИР-"
PERCENT_BASE_COLUMNS = ("Списания", "Выручка", "Свободный ТЗ")
SUMMARY_BASE_LABELS = {
    "Списания": "Сумма списаний",
    "Выручка": "Сумма выручки",
    "Свободный ТЗ": "Сумма свободного ТЗ",
}


def percentage_column_name(kir_column, base_column):
    return f"{kir_column} / {base_column}, %"


def kir_metric_columns(df):
    columns = []
    calculated_percent_columns = set(kir_percentage_columns(df))
    for column in df.columns:
        name = str(column)
        if not name.startswith(KIR_PREFIX) or column in calculated_percent_columns:
            continue
        if pd.to_numeric(df[column], errors="coerce").notna().any():
            columns.append(column)
    return columns


def kir_percentage_columns(df):
    return [column for column in df.columns if str(column).startswith(KIR_PREFIX) and str(column).endswith(", %")]


def _safe_business_percent(numerator, denominator):
    numerator = pd.to_numeric(numerator, errors="coerce")
    denominator = pd.to_numeric(denominator, errors="coerce")
    valid_denominator = denominator.notna() & denominator.ne(0)
    return (numerator / denominator * 100).where(valid_denominator)


def add_kir_percentage_columns(df, base_columns=PERCENT_BASE_COLUMNS):
    result = df.copy()
    for kir_column in kir_metric_columns(result):
        for base_column in base_columns:
            if base_column not in result.columns:
                continue
            result[percentage_column_name(kir_column, base_column)] = _safe_business_percent(
                result[kir_column],
                result[base_column],
            )
    return result


def _sum_numeric(series):
    return pd.to_numeric(series, errors="coerce").sum(min_count=1)


def _summary_row(source, kir_column, base_columns=PERCENT_BASE_COLUMNS):
    kir_sum = _sum_numeric(source[kir_column])
    row = {"Сумма КИР": kir_sum}
    for base_column in base_columns:
        if base_column not in source.columns:
            continue
        base_sum = _sum_numeric(source[base_column])
        row[SUMMARY_BASE_LABELS.get(base_column, f"Сумма {base_column}")] = base_sum
        row[f"КИР / {base_column}, %"] = (
            float(kir_sum / base_sum * 100) if pd.notna(kir_sum) and pd.notna(base_sum) and base_sum != 0 else float("nan")
        )
    return row


def kir_percentage_summary(df, kir_column, category_col="Категория", base_columns=PERCENT_BASE_COLUMNS):
    if kir_column not in df.columns:
        raise KeyError(f"KIR metric column not found: {kir_column}")

    if category_col in df.columns:
        rows = []
        for category, group in df.groupby(category_col, dropna=False):
            row = {category_col: category}
            row.update(_summary_row(group, kir_column, base_columns=base_columns))
            rows.append(row)
        result = pd.DataFrame(rows)
        if "Сумма КИР" in result.columns:
            result = result.sort_values("Сумма КИР", ascending=False, na_position="last").reset_index(drop=True)
        return result

    row = {"Итого": "Итого"}
    row.update(_summary_row(df, kir_column, base_columns=base_columns))
    return pd.DataFrame([row])
