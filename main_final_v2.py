import yaml
import os
import sys
import subprocess
from scripts.merge_data import process as run_merge
from scripts.cleaner import split_outliers_multi

def load_config():
    try:
        # Мы ищем конфиг в корне проекта
        config_path = os.path.join(os.getcwd(), 'project_config.yaml')
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print('ОШИБКА: Файл project_config.yaml не найден!')
        sys.exit(1)

def get_next_run_number(base_dir):
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
        return 1
    runs = [d for d in os.listdir(base_dir) if d.startswith('run_') and d[4:].isdigit()]
    if not runs:
        return 1
    numbers = [int(d[4:]) for d in runs]
    return max(numbers) + 1

def main():
    config = load_config()
    run_num = get_next_run_number('data')
    run_dir = f'data/run_{run_num}'
    os.makedirs(run_dir, exist_ok=True)
    
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Формируем пути
    paths = {
        'merged': os.path.abspath(os.path.join(run_dir, 'merged_step1.xlsx')),
        'final': os.path.abspath(os.path.join(run_dir, 'final_clean_data.xlsx')),
        'outliers': os.path.abspath(os.path.join(run_dir, 'outliers_report.xlsx')),
        'log': os.path.abspath(f'logs/processing_log_{run_num}.md')
    }

    print('\n' + '='*60)
    print(f'ЗАПУСК СЕССИИ №{run_num}')
    print(f'Рабочая директория: {run_dir}')
    print('='*60)

    try:
        # ШАГ 1
        print('\n[ШАГ 1/3] Объединение данных...')
        run_merge(
            os.path.abspath(config['inputs']['svod_file']), 
            os.path.abspath(config['inputs']['poteri_file']), 
            paths['merged'], 
            config['columns']['target_filter_col']
        )

        # ШАГ 2: ОЧИСТКА ВЫБРОСОВ (БЕРЕМ ВСЕ НАСТРОЙКИ ИЗ КОНФИГА)
        print('\n[ШАГ 2/3] Очистка выбросов...')
        cl_conf = config['cleaning']
        
        split_outliers_multi(
            input_file=paths['merged'], 
            columns=cl_conf['columns_to_clean'],
            group_cols=['НеделяГод', 'ТС', 'Категория'], 
            output_clean=paths['final'], 
            output_outliers=paths['outliers'], 
            method=cl_conf['method'], 
            factor=cl_conf['factor'], 
            log_file=paths['log'], 
            min_group_size=cl_conf.get('min_group_size', 3),
            outlier_mode=cl_conf.get('outlier_mode', 'any')
        )

        # ШАГ 3: ЗАПУСК ДАШБОРДА
        print(f'\n[ШАГ 3/3] Запуск дашборда...')
        db_script = os.path.abspath("scripts/db.py")
        
        # Запускаем дашборд и НЕ ждем его закрытия
        subprocess.Popen([sys.executable, db_script, paths['final']], 
                         shell=False)
        print(f"Дашборд запущен для файла: {os.path.basename(paths['final'])}")

    except Exception as e:
        print(f'ОШИБКА ПРОЦЕССА: {e}')
        import traceback
        traceback.print_exc() # Выведет подробности, если что-то упало

    print('\n' + '='*60)
    print(f'СЕССИЯ №{run_num} ЗАВЕРШЕНА')
    print('='*60 + '\n')

if __name__ == "__main__":
    main()