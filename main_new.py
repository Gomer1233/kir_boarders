import yaml
import os
import sys
from scripts.merge_data import process as run_merge
from scripts.cleaner import split_outliers_by_groups

def load_config():
    try:
        with open('project_config.yaml', 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print("ОШИБКА: Файл project_config.yaml не найден!")
        sys.exit(1)

def main():
    print("\n" + "="*50)
    print("ЗАПУСК АВТОМАТИЗАЦИИ ОБРАБОТКИ ДАННЫХ")
    print("="*50)
    
    config = load_config()

    # Гарантируем наличие папок
    for folder in ['data', 'logs']:
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"Создана папка: {folder}")

    # ШАГ 1: МЕРДЖ И НОРМАЛИЗАЦИЯ
    print("\n[ШАГ 1/2] Объединение исходных файлов...")
    try:
        merged_file = run_merge(
            svod_path=config['inputs']['svod_file'],
            poteri_path=config['inputs']['poteri_file'],
            output_path=config['outputs']['merged_temp'],
            target_col=config['columns']['target_filter_col']
        )
    except Exception as e:
        print(f"Ошибка на шаге 1: {e}")
        return

    # ШАГ 2: ОЧИСТКА ВЫБРОСОВ (ПО ГРУППАМ)
    print("\n[ШАГ 2/3] Очистка данных по группам (Неделя + ТС + Категория)...")
    try:
        split_outliers_by_groups(
            input_file=merged_file,
            column=config['columns']['clean_target_col'],
            group_cols=['НеделяГод', 'ТС', 'Категория'],
            output_clean=config['outputs']['final_clean'],
            output_outliers=config['outputs']['outliers_report'],
            method=config['cleaning']['method'],
            factor=config['cleaning']['factor'],
            log_file=config['outputs']['log_file'],
            min_group_size=3
        )
    except Exception as e:
        print(f"Ошибка на шаге 2: {e}")
        return

    # ШАГ 3: ВИЗУАЛИЗАЦИЯ
    print("\n[ШАГ 3/3] Запуск аналитического дашборда...")
    try:
        import subprocess
        subprocess.Popen([sys.executable, "scripts/db.py"])
        print("Дашборд запущен в отдельном окне.")
    except Exception as e:
        print(f"Не удалось запустить дашборд: {e}")

    print("\n" + "="*50)
    print("ПРОЦЕСС УСПЕШНО ЗАВЕРШЕН")
    print(f"Итоговый файл: {config['outputs']['final_clean']}")
    print(f"Лог очистки:   {config['outputs']['log_file']}")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()