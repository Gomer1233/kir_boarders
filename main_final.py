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

    paths = {
        'merged': os.path.join(run_dir, 'merged_step1.xlsx'),
        'final': os.path.join(run_dir, 'final_clean_data.xlsx'),
        'outliers': os.path.join(run_dir, 'outliers_report.xlsx'),
        'log': f'logs/processing_log_{run_num}.txt'
    }

    print('\n' + '='*60)
    print(f'ЗАПУСК СЕССИИ №{run_num}')
    print(f'Рабочая директория: {run_dir}')
    print('='*60)

    try:
        print('\n[ШАГ 1/3] Объединение данных...')
        run_merge(
            config['inputs']['svod_file'], 
            config['inputs']['poteri_file'], 
            paths['merged'], 
            config['columns']['target_filter_col']
        )

        print('\n[ШАГ 2/3] Очистка выбросов...')
        split_outliers_by_groups(
            paths['merged'], 
            config['columns']['clean_target_col'], 
            ['НеделяГод', 'ТС', 'Категория'], 
            paths['final'], 
            paths['outliers'], 
            config['cleaning']['method'], 
            config['cleaning']['factor'], 
            paths['log'], 
            3
        )

        print(f'\n[ШАГ 3/3] Запуск дашборда...')
        import subprocess
        subprocess.Popen([sys.executable, 'scripts/db.py', paths['final']])

    except Exception as e:
        print(f'ОШИБКА ПРОЦЕССА: {e}')

    print('\n' + '='*60)
    print(f'СЕССИЯ №{run_num} ЗАВЕРШЕНА')
    print('='*60 + '\n')

if __name__ == "__main__":
    main()