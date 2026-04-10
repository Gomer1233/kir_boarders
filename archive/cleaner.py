import pandas as pd
import numpy as np
from datetime import datetime
import os

def split_outliers_by_groups(input_file, column, group_cols=['НеделяГод', 'ТС', 'Категория'],
                             output_clean='clean.xlsx', output_outliers='outliers.xlsx', 
                             method='iqr', factor=1.5, log_file='processing_log.md',
                             min_group_size=5):
    """
    Разделяет Excel на два файла с очисткой выбросов.
    Выбросы определяются внутри групп: Неделя + ТС + Категория (магазины внутри этих групп)
    """
    log_data = []
    start_time = datetime.now()
    
    def log(msg):
        clean_msg = msg.replace('**', '').replace('## ', '').replace('# ', '').replace('- ', '').replace('|', '')
        print(clean_msg)
        log_data.append(msg)
    
    log(f"# Отчет об обработке выбросов (по магазинам внутри групп)\n")
    log(f"## Начало обработки")
    log(f"- **Дата/время**: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"- **Входной файл**: `{input_file}`")
    log(f"- **Целевой показатель**: `{column}`")
    log(f"- **Группировка**: {group_cols} (внутри групп чистим магазины/заводы)")
    log(f"- **Метод**: `{method.upper()}`")
    log(f"- **Параметр factor/k**: `{factor}`")
    log(f"- **Мин. размер группы**: `{min_group_size}` (магазинов)")
    log("---")
    
    # Загрузка
    log(f"\n## Загрузка данных")
    try:
        df = pd.read_excel(input_file)
        log(f"- ✅ Загружено: **{len(df)}** строк")
        log(f"- Колонки: {list(df.columns)}")
    except Exception as e:
        log(f"- ❌ **ОШИБКА**: {e}")
        save_log(log_data, log_file)
        raise
    
    # Проверка столбцов
    required = group_cols + [column, 'Завод']  # Завод нужен для информации, но не для группировки
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        err = f"Отсутствуют столбцы: {missing_cols}. В файле: {list(df.columns)}"
        log(f"- ❌ {err}")
        save_log(log_data, log_file)
        raise ValueError(err)
    
    # Преобразование числового столбца
    df[column] = pd.to_numeric(df[column], errors='coerce')
    original_rows = len(df)
    valid_rows = df[column].notna().sum()
    
    log(f"- Всего записей (магазин-категория): **{original_rows}**")
    log(f"- Из них с числовыми значениями `{column}`: **{valid_rows}**")
    log(f"- Уникальных групп {group_cols}: **{df[group_cols].drop_duplicates().shape[0]}**")
    log(f"- Уникальных магазинов (Заводов): **{df['Завод'].nunique()}**")
    
    # Обработка по группам
    log(f"\n## Анализ выбросов по группам")
    log(f"*Для каждой комбинации Неделя+ТС+Категория анализируем распределение показателя `{column}` по магазинам*")
    
    clean_parts = []
    outliers_parts = []
    stats_groups = []
    
    grouped = df.groupby(group_cols, sort=False)
    
    for idx, (group_key, group_df) in enumerate(grouped, 1):
        group_name = " | ".join([f"{col}={val}" for col, val in zip(group_cols, group_key)])
        
        # Работаем только с валидными числовыми данными внутри группы
        group_data = group_df[group_df[column].notna()].copy()
        n = len(group_data)  # количество магазинов в этой группе
        
        if n < min_group_size:
            # Мало магазинов для анализа - сохраняем всю группу как чистую
            clean_parts.append(group_df)
            continue
        
        values = group_data[column]
        
        # Расчет границ
        try:
            if method == 'iqr':
                Q1 = values.quantile(0.25)
                Q3 = values.quantile(0.75)
                IQR = Q3 - Q1
                if IQR == 0:
                    lower, upper = values.min() - 1, values.max() + 1
                else:
                    lower = Q1 - factor * IQR
                    upper = Q3 + factor * IQR
                    
            elif method == 'zscore':
                mean = values.mean()
                std = values.std()
                if std == 0:
                    lower, upper = mean - 1, mean + 1
                else:
                    lower = mean - factor * std
                    upper = mean + factor * std
                    
            elif method == 'percentile':
                lower = values.quantile(factor/100)
                upper = values.quantile(1 - factor/100)
            else:
                lower, upper = -np.inf, np.inf
            
            # Определяем выбросы среди магазинов в группе
            is_outlier = (group_data[column] < lower) | (group_data[column] > upper)
            group_outliers = group_data[is_outlier].copy()
            group_clean_valid = group_data[~is_outlier].copy()
            
            # Добавляем строки с NaN (пропуски) обратно в чистые данные
            group_nan = group_df[group_df[column].isna()]
            group_clean = pd.concat([group_clean_valid, group_nan], ignore_index=True)
            
            # Сохраняем результаты
            if len(group_outliers) > 0:
                outliers_parts.append(group_outliers)
                stats_groups.append({
                    'group': group_name,
                    'total': n,
                    'outliers': len(group_outliers),
                    'pct': len(group_outliers)/n*100,
                    'min': values.min(),
                    'max': values.max(),
                    'lower_bound': lower,
                    'upper_bound': upper
                })
            clean_parts.append(group_clean)
            
        except Exception as e:
            log(f"- ❌ Ошибка в группе {group_name}: {e}")
            clean_parts.append(group_df)  # В случае ошибки - все в чистые
    
    # Сводка по группам с выбросами
    log(f"\n### Группы с выбросами (первые 20 из {len(stats_groups)})")
    log(f"| Группа | Магазинов | Выбросов | % | Границы |")
    log(f"|--------|-----------|----------|---|---------|")
    
    for i, st in enumerate(sorted(stats_groups, key=lambda x: x['outliers'], reverse=True)[:20], 1):
        log(f"| {st['group'][:50]} | {st['total']} | {st['outliers']} | {st['pct']:.1f}% | [{st['lower_bound']:.3f}, {st['upper_bound']:.3f}] |")
    
    # Итоговая статистика
    total_outliers = sum(s['outliers'] for s in stats_groups)
    log(f"\n### Итоги по группам")
    log(f"- Всего групп проанализировано: **{len(grouped)}**")
    log(f"- Групп с выбросами: **{len(stats_groups)}**")
    log(f"- Всего выбросов (магазинов): **{total_outliers}**")
    
    # Сборка итоговых датафреймов
    log(f"\n## Формирование файлов")
    
    df_clean = pd.concat(clean_parts, ignore_index=True) if clean_parts else pd.DataFrame(columns=df.columns)
    df_outliers = pd.concat(outliers_parts, ignore_index=True) if outliers_parts else pd.DataFrame(columns=df.columns)
    
    clean_count = len(df_clean)
    outliers_count = len(df_outliers)
    
    log(f"- Чистые данные (включая NaN): **{clean_count}** строк")
    log(f"- Выбросы: **{outliers_count}** строк")
    log(f"- Доля выбросов: **{outliers_count/original_rows*100:.2f}%**")
    
    # Сохранение
    try:
        df_clean.to_excel(output_clean, index=False)
        log(f"- ✅ Сохранено: `{output_clean}`")
    except Exception as e:
        log(f"- ❌ Ошибка сохранения `{output_clean}`: {e}")
    
    if outliers_count > 0:
        try:
            df_outliers.to_excel(output_outliers, index=False)
            log(f"- ✅ Сохранено: `{output_outliers}`")
        except Exception as e:
            log(f"- ❌ Ошибка сохранения `{output_outliers}`: {e}")
    else:
        log(f"- ℹ️ Выбросов не обнаружено")
    
    end_time = datetime.now()
    duration = end_time - start_time
    log(f"\n## Завершение")
    log(f"- Время: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"- Длительность: {duration}")
    
    save_log(log_data, log_file)
    log(f"- 📄 Лог: `{log_file}`")

def save_log(log_list, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_list))

if __name__ == "__main__":
    # === НАСТРОЙКИ ===
    INPUT_FILE = 'kir_66_poteri.xlsx'                
    COLUMN = 'Списания'                      # Показатель для очистки
    
    # ГРУППЫ для анализа: Неделя + Сеть + Категория
    # Внутри каждой такой группы анализируем магазины (Заводы)
    GROUP_COLS = ['НеделяГод', 'ТС', 'Категория']  
    
    METHOD = 'iqr'                          # iqr, zscore, percentile
    FACTOR = 1.5                            # 1.5 - стандарт, 3 - строгий
    
    MIN_GROUP_SIZE = 3                      # Минимум магазинов в группе для анализа
    
    OUTPUT_CLEAN = 'data_clean.xlsx'        
    OUTPUT_OUTLIERS = 'data_outliers.xlsx'  
    LOG_FILE = 'processing_log.md'
    
    split_outliers_by_groups(INPUT_FILE, COLUMN, GROUP_COLS, 
                            OUTPUT_CLEAN, OUTPUT_OUTLIERS, 
                            METHOD, FACTOR, LOG_FILE, MIN_GROUP_SIZE)
