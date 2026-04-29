"""
merge_data v2.0 - универсальный модуль для KIR-анализатора.
- Поддержка универсальных ключей из конфига
- Нормализация недели (202603, 2026/03, 2026 03 → 202603)
"""

import pandas as pd
import re
import warnings

def normalize_week(week_val):
    """
    Нормализует формат недели к YYYYMM (6 цифр).
    """
    if pd.isna(week_val):
        return None
    return re.sub(r'[^\d]', '', str(week_val))[-6:]


def process(svod_path, poteri_path, output_path, target_col,
            svod_cols, poteri_cols, use_category=True):
    """
    Объединяет данные свода и потерь, нормализует ключи и фильтрует пустые значения.
    
    Args:
        svod_path: путь к файлу свода
        poteri_path: путь к файлу потерь
        output_path: выходной файл
        target_col: целевой столбец (КИР-ХХХ)
        svod_cols: dict с колонками для svod (week, ts, factory, category)
        poteri_cols: dict с колонками для poteri (week, ts, factory, category, rename_map)
        use_category: использовать ли столбец Категория (для route_2 = False)
    """
    warnings.filterwarnings('ignore', category=UserWarning, module='openpy_excel')
    
    print(f"Загрузка данных: {svod_path} и {poteri_path}...")
    df_svod = pd.read_excel(svod_path)
    df_poteri = pd.read_excel(poteri_path)

    # === ИЗВЛЕЧЕНИЕ КОНФИГА ===
    svod_week = svod_cols['week']
    svod_ts = svod_cols['ts']
    svod_factory = svod_cols['factory']
    svod_category = svod_cols['category']

    poteri_week = poteri_cols['week']
    poteri_ts = poteri_cols['ts']
    poteri_factory = poteri_cols['factory']
    poteri_category = poteri_cols['category']
    rename_map = poteri_cols.get('rename_map', {})

    if not rename_map:
        raise ValueError("❌ В конфиге columns.poteri.rename_map не указано!")

    # === НОРМАЛИЗАЦИЯ НЕДЕЛИ ===
    if svod_week in df_svod.columns:
        df_svod[svod_week] = df_svod[svod_week].apply(normalize_week)
    if poteri_week in df_poteri.columns:
        df_poteri[poteri_week] = df_poteri[poteri_week].apply(normalize_week)
    
    # === ОБЩИЕ ИМЕНА КОЛОНОК ===
    COMMON_WEEK = 'НеделяГод'
    COMMON_TS = svod_ts
    COMMON_FACTORY = svod_factory
    COMMON_CATEGORY = svod_category
    # Переименовываем недели к единому названию
    if svod_week != COMMON_WEEK and svod_week in df_svod.columns:
        df_svod[COMMON_WEEK] = df_svod[svod_week]
        df_svod = df_svod.drop(columns=[svod_week])
    if poteri_week != COMMON_WEEK and poteri_week in df_poteri.columns:
        df_poteri[COMMON_WEEK] = df_poteri[poteri_week]
        df_poteri = df_poteri.drop(columns=[poteri_week])
    
    # === ОЧИСТКА ТЕКСТОВЫХ ПОЛЕЙ ===
    text_cols_svod = [svod_ts, svod_factory]
    if use_category and svod_category in df_svod.columns:
        text_cols_svod.append(svod_category)
        df_svod[svod_category] = df_svod[svod_category].astype(str).str.strip()

    text_cols_poteri = [poteri_ts, poteri_factory]
    if use_category and poteri_category in df_poteri.columns:
        text_cols_poteri.append(poteri_category)
        df_poteri[poteri_category] = df_poteri[poteri_category].astype(str).str.strip()
    
    for col in text_cols_svod:
        if col in df_svod.columns:
            df_svod[col] = df_svod[col].astype(str).str.strip()

    for col in text_cols_poteri:
        if col in df_poteri.columns:
            df_poteri[col] = df_poteri[col].astype(str).str.strip()
    
    # === ДИНАМИЧЕСКОЕ ПЕРЕИМЕНОВАНИЕ СТОЛБЦОВ В POTERI ===
    print(f"Применение rename_map из конфига...")
    poteri_to_merge = df_poteri.rename(columns=rename_map)
    
    # Проверяем, что все необходимые столбцы после переименования существуют
    expected_cols = ['Списания', 'Выручка', 'Свободный ТЗ']
    missing = [c for c in expected_cols if c not in poteri_to_merge.columns]
    if missing:
        print(f"⚠️  ВНИМАНИЕ: После переименования не найдены столбцы: {missing}")
    print(f"Объединение данных по ключам: {COMMON_WEEK}, {COMMON_TS}, {COMMON_FACTORY}, {COMMON_CATEGORY if use_category else ''}...")
    
    # Формируем список колонок для merge
    if use_category:
        poteri_merge_cols = [COMMON_WEEK, COMMON_TS, COMMON_FACTORY, COMMON_CATEGORY] + expected_cols
    else:
        poteri_merge_cols = [COMMON_WEEK, COMMON_TS, COMMON_FACTORY] + expected_cols

    poteri_merge_cols = [c for c in poteri_merge_cols if c in poteri_to_merge.columns]

    # Формируем список колонок для merge из svod
    # 1. Сначала добавляем ключевые колонки (по которым мержим)
    if use_category:
        svod_merge_cols = [COMMON_WEEK, COMMON_TS, COMMON_FACTORY, COMMON_CATEGORY]
    else:
        svod_merge_cols = [COMMON_WEEK, COMMON_TS, COMMON_FACTORY]

    # 2. Добавляем все числовые столбцы из svod (кроме ключевых)
    numeric_cols = df_svod.select_dtypes(include=['number']).columns.tolist()
    key_cols = [COMMON_WEEK, COMMON_TS, COMMON_FACTORY]
    if use_category:
        key_cols.append(COMMON_CATEGORY)
    for col in numeric_cols:
        if col not in key_cols and col not in svod_merge_cols:
            svod_merge_cols.append(col)

    # Убираем колонки, которых нет в данных
    svod_merge_cols = [c for c in svod_merge_cols if c in df_svod.columns]

    result = pd.merge(
        df_svod[svod_merge_cols],
        poteri_to_merge[poteri_merge_cols],
        on=[COMMON_WEEK, COMMON_TS, COMMON_FACTORY] + ([COMMON_CATEGORY] if use_category else []),
        how='left'
    )

    print(f"Очистка строк с пустыми значениями в столбце '{target_col}'...")
    if target_col in result.columns:
        before_drop = len(result)
        result = result.dropna(subset=[target_col])
        print(f"- Удалено строк с NaN: {before_drop - len(result)}")
    else:
        print(f"❌ ВНИМАНИЕ: Столбец {target_col} не найден!")
    print(f"Сохранение в {output_path}...")
    result.to_excel(output_path, index=False)
    return output_path


if __name__ == "__main__":
    import yaml
    try:
        with open('project_config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # Получаем настройки из конфига
        route = 'route_1'  # Можно сделать параметром командной строки
        svod_path = config['inputs'][route] + '/kir_with_cats.xlsx'
        poteri_path = config['inputs'][route] + '/poteri_with_cats.xlsx'
        output_path = 'data/merged_temp_v2.xlsx'
        target_col = config['columns']['target_col']
        
        svod_cols = config['columns']['svod']
        poteri_cols = config['columns']['poteri']

        process(
            svod_path=svod_path,
            poteri_path=poteri_path,
            output_path=output_path,
            target_col=target_col,
            svod_cols=svod_cols,
            poteri_cols=poteri_cols
        )
        print(f"Готово: {output_path}")
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()

