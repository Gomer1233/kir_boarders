import yaml
import pandas as pd
import warnings
from scripts.merge_data_v2 import process

if __name__ == "__main__":
    with open('project_config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    route = 'route_1'
    svod_path = config['inputs'][route] + '/kir_with_cats.xlsx'
    poteri_path = config['inputs'][route] + '/poteri_with_cats.xlsx'
    output_path = 'data/merged_temp.xlsx'
    target_col = config['columns']['target_col']
    
    process(svod_path, poteri_path, output_path, target_col)
    print(f"Готово: {output_path}")
