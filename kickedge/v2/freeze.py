"""Freeze the V2 decision before any 2026 outcome is read.

Refits the historically selected candidate ("V2 final") and the best remaining
challenger on 2016–2025 only, writes versioned artifacts with SHA-256 lineage and a
preregistration that fixes rows, metrics and the adoption gate of the single 2026
forward evaluation. Refuses to run once that evaluation has been revealed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path

import joblib
import numpy as np

from .carryover import load_dataset
from .models import CANDIDATES, V2Model, feature_columns
from .training import structural_frame

MODEL_DIRECTORY = Path('models/v2')
PREREGISTRATION = Path('reports/v2_freeze.json')
REVEAL_MARKER = Path('data/v2/forward/reveal_marker.json')
COMPARISON = Path('data/v2/comparison/comparison.json')
FORWARD_PROTOCOL = {
    'rows': 'Every 2026 kicker-game in a completed game present in the current nflverse cache at reveal time, '
            'with a usable label and eligible for pregame training; prediction cutoff = scheduled kickoff - 60 min, '
            'kickoff = actual kickoff, 82 V1 features rebuilt by the 7B builders and carryover from 2025. '
            'All exclusions are reported.',
    'models': 'Frozen V1 artifact, frozen V2 final and frozen challenger, scored on the same rows.',
    'metrics': ['nll', 'rps', 'brier_ge_2', 'brier_ge_3', 'brier_ge_4', 'calibration ECE', 'predicted vs observed mean'],
    'adoption_gate': 'V1 stays champion unless the historical selection chose a new candidate AND the forward rows are '
                     '>= 150 AND V2 final shows no >2% NLL or RPS deterioration and no >0.005 average Brier deterioration '
                     'versus V1. No model change after the reveal.',
    'single_reveal': 'A durable marker blocks a second evaluation; later calls only read the stored result.',
}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _file_sha(path):
    return _sha(Path(path).read_bytes())


def code_hashes():
    package = Path(__file__).resolve().parents[1]
    names = ['v2/carryover.py', 'v2/models.py', 'v2/training.py', 'v2/audit.py', 'v2/freeze.py',
             'modeling/preprocessing.py', 'modeling/distributions.py', 'modeling/dataset.py',
             'features/kicker.py', 'features/team.py', 'features/contract.json']
    return {name: _file_sha(package/name) for name in names}


def freeze(root=Path('.'), *, now=None):
    root = Path(root)
    if (root/REVEAL_MARKER).exists():
        raise ValueError('2026 outcomes were already revealed; the V2 freeze cannot be changed')
    comparison = json.loads((root/COMPARISON).read_text(encoding='utf-8'))
    summaries, selection = comparison['summaries'], comparison['selection']
    final = selection['selected']
    challenger = min((n for n in summaries if n != final), key=lambda n: summaries[n]['pooled']['nll'])
    dataset = load_dataset(root/'data/v2/dataset')
    if dataset.season.max() > 2025:
        raise ValueError('Freeze data must end in 2025')
    dataset_meta = json.loads((root/'data/v2/dataset/metadata.json').read_text(encoding='utf-8'))
    targets = structural_frame(dataset)
    models = {}
    for name, role in ((final, 'v2_final'), (challenger, 'challenger')):
        config = next(c for c in CANDIDATES if c['name'] == name)
        columns = feature_columns(config)
        model = V2Model(config).fit(dataset[columns], dataset.xpm.to_numpy(),
                                    structural_targets=targets if config['family'] == 'structural' else None)
        buffer = io.BytesIO()
        joblib.dump(model, buffer)
        blob = buffer.getvalue()
        directory = root/MODEL_DIRECTORY/name
        directory.mkdir(parents=True, exist_ok=True)
        (directory/'model.joblib').write_bytes(blob)
        in_sample = model.predict(dataset[columns])
        models[name] = {'role': role, 'config': config, 'features': columns, 'feature_count': len(columns),
                        'preprocessing': 'V1 recipe: median imputation + all-column missing indicators, '
                                         + ('StandardScaler, ' if config['family'] != 'boost' else '')
                                         + 'one-hot game_type' + ('' if config['features'] == 'v1' else ' (V2 column list)'),
                        'calibration': None, 'fit_seasons': model.fit_seasons_, 'fit_rows': model.fit_row_count_,
                        'artifact_path': (MODEL_DIRECTORY/name/'model.joblib').as_posix(), 'artifact_sha256': _sha(blob),
                        'in_sample_lambda_sha256': _sha(np.asarray(in_sample, dtype=float).tobytes()),
                        'historical_oof': summaries[name]['pooled']}
    record = {'frozen_at': (now or datetime.now(timezone.utc)).isoformat(), 'base_commit_v1': 'f78c223',
              'v1_artifact_sha256': 'c2f8f5ff00712546023b769a7c8374478399b7d00e343dc4e5e928c10977f0d0',
              'historical_selection': selection, 'calibration': 'Not retained: rolling OOF check failed for every candidate.',
              'calibration_check': {n: c['pooled'] | {'retained': c['retained']} for n, c in comparison['calibration_check'].items()},
              'dataset': {'content_sha256': dataset_meta['content_sha256'], 'rows': dataset_meta['rows'],
                          'seasons': dataset_meta['seasons'], 'source_sha256': dataset_meta['source_sha256']},
              'code_sha256': code_hashes(), 'models': models, 'forward_protocol': FORWARD_PROTOCOL,
              'outcomes_2026_read_before_freeze': False}
    (root/PREREGISTRATION).write_text(json.dumps(record, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return record


def load_frozen(root, name):
    """Load a frozen V2 artifact after verifying it against the preregistration."""
    root = Path(root)
    record = json.loads((root/PREREGISTRATION).read_text(encoding='utf-8'))
    entry = record['models'][name]
    blob = (root/entry['artifact_path']).read_bytes()
    if _sha(blob) != entry['artifact_sha256']:
        raise ValueError('Frozen V2 artifact hash mismatch')
    return joblib.load(io.BytesIO(blob)), entry
