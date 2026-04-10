import pandas as pd
import numpy as np
from datetime import datetime
import os

def save_log(log_list, filename):
    """Сохраняет список строк в файл."""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_list))

def get_bounds(series, method, factor):
    """Вспомогательная функция расчета границ."""
    if method == 'iqr':
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            return series.min() - 1, series.max() + 1
        return q1 - factor * iqr, q3 + factor * iqr
    elif method == 'zscore':
        mean = series.mean()
        std = series.std()
        if std == 0 or pd.isna(std):
            return mean - 1, mean + 1
        return mean - factor * std, mean + factor * std
    elif method == 'percentile':
        return series.quantile(factor/100), series.quantile(1 - factor/100)
    else:
        raise ValueError(f"Неизвестный метод: {method}")

def split_outliers_multi(input_file, columns, group_cols=['НеделяГод', 'ТС', 'Категория'],
                         output_clean='clean.xlsx', output_outliers='outliers.xlsx', 
                         method='iqr', factor=1.5, log_file='processing_log.md',
                         min_group_size=5, outlier_mode='any'):
    """
    Очистка выбросов по нескольким столбцам.
    
    columns: список столбцов для проверки, например ['КИР-066', 'Списания']
    outlier_mode: 'any' (выброс, если хотя бы в одном столбце) 
                  или 'all' (выброс, только если во всех столбцах сразу)
    """
    log_data = []
    start_time = datetime.now()
    
    def log(msg):
        clean_msg = msg.replace('**', '').replace('## ', '').replace('# ', '').replace('- ', '').replace('|', '')
        print(clean_msg)
        log_data.append(msg)
    
    mode_desc = "хотя бы один столбец" if outlier_mode == 'any' else "все столбцы одновременно"
    
    log(f"# Многомерная очистка выбросов\n")
    log(f"## Начало обработки")
    log(f"- **Дата/время**: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"- **Файл**: `{input_file}`")
    log(f"- **Столбцы для очистки**: {columns}")
    log(f"- **Группировка**: {group_cols} (магазины внутри групп)")
    log(f"- **Метод**: `{method.upper()}` (factor={factor})")
    log(f"- **Условие выброса**: `{outlier_mode}` ({mode_desc})")
    log(f"- **Мин. размер группы**: {min_group_size}")
    log("---")
    
    # Загрузка
    log(f"\n## Загрузка данных")
    try:
        df = pd.read_excel(input_file)
        log(f"- ✅ Загружено: **{len(df)}** строк")
    except Exception as e:
        log(f"- ❌ Ошибка: {e}")
        save_log(log_data, log_file)
        raise
    
    # Проверка столбцов
    required = group_cols + columns
    missing = [c for c in required if c not in df.columns]
    if missing:
        err = f"Отсутствуют столбцы: {missing}. В файле: {list(df.columns)}"
        log(f"- ❌ {err}")
        save_log(log_data, log_file)
        raise ValueError(err)
    
    # Конвертация целевых столбцов в числа
    for col in columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    original_rows = len(df)
    log(f"- Проверяемые столбцы конвертированы в числовой формат")
    
    # Обработка по группам
    log(f"\n## Анализ выбросов")
    log(f"Уникальных групп: **{df[group_cols].drop_duplicates().shape[0]}**")
    
    clean_parts = []
    outliers_parts = []
    stats_rows = []  # Для таблицы статистики
    
    grouped = df.groupby(group_cols, sort=False)
    
    for idx, (group_key, group_df) in enumerate(grouped, 1):
        group_name = " | ".join([f"{c}={v}" for c, v in zip(group_cols, group_key)])
        n_total = len(group_df)
        
        masks = []
        per_col_info = {}
        skip_group = True
        
        # Анализируем каждый столбец в группе
        for col in columns:
            col_data = group_df[col].dropna()
            n_valid = len(col_data)
            
            if n_valid < min_group_size:
                per_col_info[col] = {'status': 'skip', 'count': 0, 'n_valid': n_valid}
                masks.append(pd.Series(False, index=group_df.index))
                continue
            
            skip_group = False
            lower, upper = get_bounds(col_data, method, factor)
            
            # Маска выбросов для этого столбца (NaN дают False в сравнениях)
            is_out = (group_df[col] < lower) | (group_df[col] > upper)
            masks.append(is_out)
            
            per_col_info[col] = {
                'status': 'ok',
                'count': int(is_out.sum()),
                'bounds': [round(lower, 4), round(upper, 4)],
                'n_valid': n_valid
            }
        
        # Если ни по одному столбцу нельзя оценить (все NaN или мало данных) - пропускаем группу
        if skip_group:
            clean_parts.append(group_df)
            continue
        
        # Объединение масок
        if outlier_mode == 'any':
            final_mask = np.logical_or.reduce(masks)
        else:  # 'all'
            final_mask = np.logical_and.reduce(masks)
        
        final_count = int(final_mask.sum())
        
        # Логирование, если есть выбросы
        if final_count > 0 and len(stats_rows) < 30:  # Лимит строк в логе
            row_stat = {
                'group': group_name[:40],
                'total': n_total,
                'total_out': final_count
            }
            for col in columns:
                if per_col_info[col]['status'] == 'ok':
                    row_stat[col] = f"{per_col_info[col]['count']} ([{per_col_info[col]['bounds'][0]}..{per_col_info[col]['bounds'][1]}])"
                else:
                    row_stat[col] = "N/A"
            stats_rows.append(row_stat)
        
        # Разделение
        group_outliers = group_df[final_mask]
        group_clean = group_df[~final_mask]
        
        if len(group_outliers) > 0:
            outliers_parts.append(group_outliers)
        clean_parts.append(group_clean)
    
    # Формирование таблицы в логе
    if stats_rows:
        log(f"\n### Группы с выбросами (первые 30)")
        header = "| Группа | Всего | Итого выбросов |"
        subheader = "|---|---|---|"
        for col in columns:
            header += f" {col} |"
            subheader += "---|"
        log(header)
        log(subheader)
        
        for row in stats_rows:
            line = f"| {row['group']} | {row['total']} | **{row['total_out']}** |"
            for col in columns:
                line += f" {row.get(col, '-')} |"
            log(line)
    
    # Сборка итогов
    log(f"\n## Итоговое разделение")
    df_clean = pd.concat(clean_parts, ignore_index=True) if clean_parts else pd.DataFrame(columns=df.columns)
    df_outliers = pd.concat(outliers_parts, ignore_index=True) if outliers_parts else pd.DataFrame(columns=df.columns)
    
    n_clean = len(df_clean)
    n_out = len(df_outliers)
    
    log(f"- Исходно строк: **{original_rows}**")
    log(f"- Чистые данные: **{n_clean}** ({n_clean/original_rows*100:.1f}%)")
    log(f"- Выбросы: **{n_out}** ({n_out/original_rows*100:.1f}%)")
    
    # Сохранение
    try:
        df_clean.to_excel(output_clean, index=False)
        log(f"- ✅ Сохранено: `{output_clean}`")
    except Exception as e:
        log(f"- ❌ Ошибка сохранения: {e}")
    
    if n_out > 0:
        df_outliers.to_excel(output_outliers, index=False)
        log(f"- ✅ Сохранено: `{output_outliers}`")
    
    end_time = datetime.now()
    log(f"\n## Завершение")
    log(f"- Длительность: {end_time - start_time}")
    log(f"- Лог: `{log_file}`")
    
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_data))

if __name__ == "__main__":
    # === НАСТРОЙКИ ===
    INPUT_FILE = 'kir_66_poteri.xlsx'
    
    # Укажите здесь один или несколько столбцов через запятую
    COLUMNS_TO_CLEAN = ['Выручка', 'Списания', 'Свободный ТЗ']  # Примеры: ['Выручка'], ['Списания', 'Выручка', 'ТЗ']
    
    # Группировка: внутри каждой такой комбинации ищем выбросы среди магазинов
    GROUP_COLS = ['НеделяГод', 'ТС', 'Категория']
    
    # Параметры метода
    METHOD = 'iqr'           # 'iqr', 'zscore', 'percentile'
    FACTOR = 1.5             # 1.5 стандарт, 3 строгий
    
    # Логика выброса:
    # 'any' = выброс, если аномалия хотя бы в одном столбце (рекомендуется)
    # 'all' = выброс, только если аномалия во ВСЕХ указанных столбцах одновременно
    OUTLIER_MODE = 'any'
    
    MIN_GROUP_SIZE = 3       # Минимум магазинов в группе для анализа
    
    OUTPUT_CLEAN = 'data_clean.xlsx'
    OUTPUT_OUTLIERS = 'data_outliers.xlsx'
    LOG_FILE = 'processing_log.md'
    
    split_outliers_multi(
        INPUT_FILE, 
        COLUMNS_TO_CLEAN, 
        GROUP_COLS,
        OUTPUT_CLEAN, 
        OUTPUT_OUTLIERS, 
        METHOD, 
        FACTOR, 
        LOG_FILE, 
        MIN_GROUP_SIZE,
        OUTLIER_MODE
    )
