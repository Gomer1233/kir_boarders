import yaml
import os
import sys
import shutil
from scripts.merge_data import process as run_merge
from scripts.cleaner import split_outliers_by_groups

def load_config():
    try:
        with open('project_config.yaml', 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(\"ОШИБКА: Файл project_config.yaml не найден!\")
        sys.exit(1)

def get_next_run_number(base_dir):
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
        return 1
    
    # Ищем папки вида run_N
    runs = [d for d in os.listdir(base_dir) if d.startswith('run_') and d[4:].isdigit()]
    if not runs:
        return 1
    
    numbers = [int(d[4:]) for d in runs]
    return max(numbers) + 1

def main():
    config = load_config()
    
    # 1. Определяем номер запуска
    run_num = get_next_run_number('data')
    run_dir = f\"data/run_{run_num}\"
    os.makedirs(run_dir, exist_ok=True)
    
    # Создаем папку для логов если нет
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # 2. Формируем пути для этого конкретного запуска
    # Мы переопределяем пути из конфига, чтобы они вели в новую подпапку
    paths = {
        'merged': os.path.join(run_dir, \"merged_step1.xlsx\"),
        'final': os.path.join(run_dir, \"final_clean_data.xlsx\"),
        'outliers': os.path.join(run_dir, \"outliers_report.xlsx\"),
        'log': f\"logs/processing_log_{run_num}.txt\"
    }

    print(\"\\n\" + \"=\"*60)
    print(f\"ЗАПУСК СЕССИИ №{run_num}\")
    print(f\"Рабочая директория: {run_dir}\")
    print(\"=\"*60)

    # ШАГ 1: МЕРДЖ
    print(f\"\\n[ШАГ 1/3] Объединение: {config['inputs']['svod_file']} + {config['inputs']['poteri_file']}\")
    try:
        merged_file = run_merge(
            svod_path=config['inputs']['svod_file'],
            poteri_path=config['inputs']['poteri_file'],
            output_path=paths['merged'],
            target_col=config['columns']['target_filter_col']
        )
    except Exception as e:
        print(f\"Ошибка на шаге 1: {e}\")
        return

    # ШАГ 2: ОЧИСТКА
    print(f\"\\n[ШАГ 2/3] Очистка выбросов (результат в {paths['final']})...\")
    try:
        split_outliers_by_groups(
            input_file=merged_file,
            column=config['columns']['clean_target_col'],
            group_cols=['НеделяГод', 'ТС', 'Категория'],
            output_clean=paths['final'],
            output_outliers=paths['outliers'],
            method=config['cleaning']['method'],
            factor=config['cleaning']['factor'],
            log_file=paths['log'],
            min_group_size=3
        )
    except Exception as e:
        print(f\"Ошибка на шаге 2: {e}\")
        return

    # Временно обновляем конфиг для дашборда, чтобы он открыл последний файл
    # (Дашборд читает project_config.yaml, поэтому нам нужно на секунду подменить там путь)
    # Но лучше передать путь через окружение или аргумент
    os.environ['LAST_FINAL_DATA'] = paths['final']

    # ШАГ 3: ВИЗУАЛИЗАЦИЯ
    print(f\"\\n[ШАГ 3/3] Запуск дашборда для файла: {paths['final']}\")
    try:
        import subprocess
        # Передаем путь к файлу прямо в скрипт db.py (нужно будет там подправить прием аргумента)
        subprocess.Popen([sys.executable, \"scripts/db.py\", paths['final']])
        print(\"Дашборд запущен.\")
    except Exception as e:
        print(f\"Не удалось запустить дашборд: {e}\")

    print(\"\\n\" + \"=\"*60)
    print(f\"СЕССИЯ №{run_num} ЗАВЕРШЕНА\")
    print(f\"Данные: {run_dir}\")
    print(f\"Лог:   {paths['log']}\")
    print(\"=\"*60 + \"\\n\")

if __name__ == \"__main__\":
    main()\"