import argparse
from pathlib import Path
from .config import DB_PATH, DATA
from .storage import seed

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Substitui o estoque atomicamente; reexecutável sem duplicar linhas.')
    parser.add_argument('--arquivo', type=Path, default=DATA / 'estoque_antecipe.csv')
    parser.add_argument('--banco', type=Path, default=DB_PATH)
    args = parser.parse_args()
    print(f'{seed(args.arquivo, args.banco)} notas carregadas em {args.banco}')
