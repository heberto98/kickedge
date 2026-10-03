"""Reproduce the V2 development outputs: dataset, walk-forward comparison, market audit.

The freeze (kickedge.v2.freeze.freeze) and the 2026 reveal (kickedge.v2.forward.reveal)
are one-shot steps guarded by their own markers and are deliberately not exposed here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from .carryover import build_dataset, load_dataset
from .market_audit import run_audit
from .models import CANDIDATES
from .training import calibration_check, candidate_oof, selection, structural_frame, summarize

COMPARISON_DIRECTORY = Path('data/v2/comparison')


def compare(root=Path('.')):
    """Walk-forward OOF 2020–2025 for every frozen candidate, preregistered selection and calibration check."""
    out = Path(root)/COMPARISON_DIRECTORY
    out.mkdir(parents=True, exist_ok=True)
    frame = load_dataset(Path(root)/'data/v2/dataset')
    targets = structural_frame(frame)
    summaries, oofs = {}, {}
    for config in CANDIDATES:
        oof = candidate_oof(frame, targets if config['family'] == 'structural' else None, config)
        with duckdb.connect() as con:
            con.register('o', oof)
            con.execute('COPY o TO ? (FORMAT PARQUET)', [str(out/f"{config['name']}_oof.parquet")])
        oofs[config['name']], summaries[config['name']] = oof, summarize(oof)
    result = {'summaries': summaries,
              'selection': selection(summaries, families={c['name']: c['family'] for c in CANDIDATES}),
              'calibration_check': {name: calibration_check(oof) for name, oof in oofs.items()}}
    (out/'comparison.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step', choices=['dataset', 'compare', 'market'])
    step = parser.parse_args().step
    if step == 'dataset':
        _, metadata = build_dataset(Path('.'))
        print('rows:', metadata['rows'], '| content sha256:', metadata['content_sha256'])
    elif step == 'compare':
        print('selected:', compare()['selection']['selected'])
    else:
        result = run_audit()
        print('matched quotes:', result['matched_quotes'], '| written to data/v2/market/audit.json')


if __name__ == '__main__':
    main()
