"""
KIR-Анализатор v3.2 - Universally configurable pipeline
Исправлена ошибка с отступами
"""

import yaml
import os
import sys
import subprocess
from scripts.merge_data_v2 import process as run_merge
from scripts.cleaner_v2 import split_outliers_multi, pre_clean


def load_config():
    """Загружает конфиг из project_config.yaml"""
    try:
        config_path = os.path.join(os.getcwd(), 'project_config.yaml')
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print('ОШИБКА: Файл project_config.yaml не найден!')
        sys.exit(1)


def get_next_run_number(base_dir):
    """Возвращает следующий номер запуска (run_N)"""
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
        return 1
    
    runs = [d for d in os.listdir(base_dir) if d.startswith('run_') and d[4:].isdigit()]
    if not runs:
        return 1
    numbers = [int(d[4:]) for d in runs]
    return max(numbers) + 1


def get_route_config(config, route_name):
    """Возвращает конфигурацию для указанного маршрута"""
    route_dir = config['inputs'][route_name]

    if route_name == 'route_1':
        return {
            'svod': os.path.join(route_dir, 'kir_with_cats.xlsx'),
            'poteri': os.path.join(route_dir, 'poteri_with_cats.xlsx'),
            'group_cols': config['grouping']['with_cats'],
            'svod_cols': config['columns']['svod'],      # ← добавлено
            'poteri_cols': config['columns']['poteri'],  # ← добавлено
            'desc': 'Маршрут 1 (с категориями)'
        }
    else:  # route_2
        return {
            'svod': os.path.join(route_dir, 'kir_without_cats.xlsx'),
            'poteri': os.path.join(route_dir, 'poteri_without_cats.xlsx'),
            'group_cols': config['grouping']['without_cats'],
            'svod_cols': config['columns']['svod'],      # ← добавлено
            'poteri_cols': config['columns']['poteri'],  # ← добавлено
            'desc': 'Маршрут 2 (без категорий)'
        }


def main():
    config = load_config()

    # === ОПРЕДЕЛЕНИЕ РЕЖИМА ИЗ АРГУМЕНТА КОМАНДНОЙ СТРОКИ ===
    if len(sys.argv) > 1 and sys.argv[1].lower() in ['route_1', 'route_2', 'both']:
        mode = sys.argv[1].lower()
        print(f"[INFO] Режим получен из аргумента: {mode}")
    else:
        mode = config.get('mode', 'route_1')
        print(f"[INFO] Режим получен из конфига: {mode}")
    
    target_col = config['columns']['target_col']
    
    # === ЗАПУСК ПО РЕЖИМАМ ===
    if mode == 'route_1':
        routes = [('route_1',)]
    elif mode == 'route_2':
        routes = [('route_2',)]
    else:  # both
        routes = [('route_1',), ('route_2',)]

    # === ОБРАБОТКА КАЖДОГО МАРШРУТА ===
    for route_tuple in routes:
        route_name = route_tuple[0]
        route_conf = get_route_config(config, route_name)

        run_num = get_next_run_number('data')
        run_dir = f'data/run_{run_num}_{route_name}'
        os.makedirs(run_dir, exist_ok=True)
        
        if not os.path.exists('logs'):
            os.makedirs('logs')

        paths = {
            'merged': os.path.abspath(os.path.join(run_dir, 'merged_step1.xlsx')),
            'final': os.path.abspath(os.path.join(run_dir, 'final_clean_data.xlsx')),
            'outliers': os.path.abspath(os.path.join(run_dir, 'outliers_report.xlsx')),
            'log': os.path.abspath(f'logs/processing_log_{run_num}_{route_name}.md')
        }

        print('\n' + '='*60)
        print(f'ЗАПУСК СЕССИИ №{run_num} - {route_conf["desc"]}')
        print(f'Режим: {mode} | Путь: {route_conf["svod"]}')
        print('='*60)

        try:
            clean_conf = config['cleaning']
            clean_columns = config['columns']['clean_columns']  # ← добавлено

            if clean_conf.get('remove_zeros', True) or clean_conf.get('remove_empty_cols'):
                print('\n[ШАГ 0/3] Очистка мусора (нули/пустые)...')
                pre_clean(
                    input_file=route_conf['svod'],
                    output_file=paths['merged'],
                    target_col=target_col,
                    remove_zeros=clean_conf.get('remove_zeros', True),
                    remove_empty_cols=clean_conf.get('remove_empty_cols', [])
                )
            else:
                print('\n[ШАГ 1/3] Объединение данных...')
                run_merge(
                    os.path.abspath(route_conf['svod']),
                    os.path.abspath(route_conf['poteri']),
                    paths['merged'],
                    target_col,
                    svod_cols=route_conf['svod_cols'],
                    poteri_cols=route_conf['poteri_cols']
                )

            print('\n[ШАГ 2/3] Очистка выбросов...')
            cl_conf = config['cleaning']
            
            split_outliers_multi(
                input_file=paths['merged'],
                columns=cl_conf['columns_to_clean'],
                group_cols=route_conf['group_cols'],
                output_clean=paths['final'],
                output_outliers=paths['outliers'],
                method=cl_conf['method'],
                factor=cl_conf['factor'],
                log_file=paths['log'],
                min_group_size=cl_conf.get('min_group_size', 3),
                outlier_mode=cl_conf.get('outlier_mode', 'any')
            )

            print(f'\n[ШАГ 3/3] Запуск дашборда...')
            db_script = os.path.abspath("scripts/db.py")
            subprocess.Popen([sys.executable, db_script, paths['final']], shell=False)
            print(f"Дашборд запущен для файла: {os.path.basename(paths['final'])}")

        except Exception as e:
            print(f'ОШИБКА ПРОЦЕССА: {e}')
            import traceback
            traceback.print_exc()

    print('\n' + '='*60)
    print(f'ВСЕ СЕССИИ ЗАВЕРШЕНЫ (Режим: {mode})')
    print('='*60 + '\n')


if __name__ == "__main__":
    main()

