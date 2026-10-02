"""Offline Phase 5 CLI. There is deliberately no holdout-evaluation command."""
import argparse
import json
from pathlib import Path

from .train import run_training


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['train'])
    parser.add_argument('--dataset', type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path('data/models/phase5'))
    parser.add_argument('--report-dir', type=Path, default=Path('reports'))
    args = parser.parse_args()
    dataset = args.dataset
    if dataset is None:
        latest = json.loads(Path('data/features/environment/latest.json').read_text(encoding='utf-8'))
        dataset = Path(latest['path']) / 'kicker_game_features.parquet'
    report = run_training(dataset, args.output_dir, args.report_dir)
    print(json.dumps({'selected': report['selected']['name'], 'refit_rows': report['refit_rows'],
                      'holdout_2025_evaluated': False}, indent=2))


if __name__ == '__main__':
    main()
