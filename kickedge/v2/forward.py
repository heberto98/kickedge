"""Single 2026 forward evaluation of the frozen models (V1 vs V2 final and challenger).

Runs only after the preregistered freeze; the reveal marker is written before any
2026 outcome is read and a second call returns the stored result. Rows are built
exactly like training rows: 82 V1 features by the 7B builders at scheduled kickoff
minus 60 minutes (actual kickoff as the game time) and carryover from 2025.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pandas as pd

from kickedge.current.snapshot import build_snapshot, resolve_kicker, resolve_target, timestamp
from kickedge.current.sources import load_current_sources
from kickedge.inference.loader import load_model
from kickedge.modeling.dataset import predictor_columns
from kickedge.modeling.preprocessing import NormalizePredictors
from .audit import metrics
from .carryover import PriorSeason, season_games
from .freeze import PREREGISTRATION, REVEAL_MARKER, load_frozen
from .models import feature_columns

RESULT = Path('data/v2/forward/result.json')
MIN_ROWS = 150


def label_exclusions(k):
    """Label-level training rules of the V1 materializer (features/materialize.py)."""
    reasons = []
    if not k.get('target_season_eligible', False):
        reasons.append('outside_target_seasons')
    if not k.get('statistical_label_usable'):
        reasons.append('unusable_target_label')
    if not k.get('id_in_players', False) or not k.get('schedule_identity_ok', False):
        reasons.append('identity_problem')
    return reasons


def history_exclusions(built):
    """Feature-level training rules: complete, released, usable history at the cutoff."""
    reasons = []
    provenance, warnings = built['provenance'], built['data_quality']['warnings']
    if any(w.startswith('Prior event pending conservative release gate') for w in warnings):
        reasons.append('history_unavailable_before_cutoff')
    if provenance['kicker_history']['unusable_prior_game_ids']:
        reasons.append('history_incomplete_or_unusable')
    if 'missing_source_metric' in provenance['team_history']['null_reasons'].values():
        reasons.append('missing_team_source_metric')
    return reasons


def forward_rows(root, *, now, loader=load_current_sources):
    """Eligible completed 2026 kicker-games with pregame features and outcomes."""
    bundle = loader(Path(root), 2026, refresh=False, now=now)
    prior = PriorSeason(2025, season_games(root, 2025, now=now))
    scheduled = {s['game_id']: s['scheduled_kickoff'] for s in bundle['schedules']}
    rows, exclusions = [], []
    for game in bundle['games']:
        source = game['source']
        cutoff = timestamp(scheduled[game['game_id']]) - timedelta(minutes=60)
        for k in game['kickers']:
            identity = {'game_id': game['game_id'], 'team': k['team'], 'kicker_id': k['kicker_id']}
            reasons = label_exclusions(k)
            if reasons:
                exclusions.append(identity | {'reason': ', '.join(reasons)})
                continue
            try:
                target = resolve_target(bundle, k['team'], k['opponent'], season=2026, game_id=game['game_id'],
                                        now=now, replay=True)
                target['kickoff'] = source['actual_kickoff']
                player = resolve_kicker(bundle, k['kicker_id'], target, cutoff=cutoff)
                built = build_snapshot(bundle, target, player, now=now, cutoff=cutoff, replay=True)
                features = built['snapshot']['features']
                carry = prior.features(identity | {'season': 2026, 'opponent': k['opponent'],
                                                   'kickoff': source['actual_kickoff'], 'prediction_cutoff': cutoff.isoformat()})
            except ValueError as exc:
                exclusions.append(identity | {'reason': f'features not reconstructible: {exc}'})
                continue
            reasons = history_exclusions(built)
            if reasons:
                exclusions.append(identity | {'reason': ', '.join(reasons)})
                continue
            carry['current_season_games_before'] = features['kicker_games_before']
            rows.append(identity | {'season': 2026, 'week': k['week'], 'xpm': k['xpm']} | features | carry)
    frame = pd.DataFrame(rows)
    return frame, exclusions


def _numeric(frame, columns):
    out = frame[columns].copy()
    for name in columns:
        if name != 'game_type':
            out[name] = pd.to_numeric(out[name]).astype(float)
    return out


def _scores(y, lam):
    m = metrics(y, lam)
    return {key: m[key] for key in ('count', 'nll', 'rps', 'brier_ge_2', 'brier_ge_3', 'brier_ge_4',
                                     'predicted_mean', 'observed_mean')} | {
        'brier_average': (m['brier_ge_2'] + m['brier_ge_3'] + m['brier_ge_4']) / 3,
        'ece': {k: m['calibration'][k]['ece'] for k in ('ge_2', 'ge_3', 'ge_4')},
        'bias_pp': {k: 100 * m['calibration'][k]['bias'] for k in ('ge_2', 'ge_3', 'ge_4')}}


def reveal(root=Path('.'), *, now=None, loader=load_current_sources, amendment=None):
    """Evaluate once; later calls return the stored result unchanged.

    A marker without a result means an attempt stopped before scoring. It is only
    resumed with an explicit written amendment, which is recorded in the result.
    """
    root = Path(root)
    result_path, marker = root/RESULT, root/REVEAL_MARKER
    if result_path.exists():
        return json.loads(result_path.read_text(encoding='utf-8'))
    aborted = []
    if marker.exists():
        if not amendment:
            raise ValueError('A reveal started without a stored result; review manually instead of re-running')
        aborted.append(json.loads(marker.read_text(encoding='utf-8')) | {'amendment': amendment})
    record = json.loads((root/PREREGISTRATION).read_text(encoding='utf-8'))
    frozen = {name: load_frozen(root, name) for name in record['models']}   # hash-verified before reading outcomes
    v1 = load_model(root/'data/models/phase5')
    now = now or datetime.now(timezone.utc)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({'revealed_at': now.isoformat(), 'frozen_at': record['frozen_at'],
                                  'aborted_attempts': aborted}) + '\n', encoding='utf-8')
    rows, exclusions = forward_rows(root, now=now, loader=loader)
    if not len(rows):
        raise ValueError('No eligible forward rows; nothing was scored')
    y = rows.xpm.to_numpy(dtype=float)
    predictions = {'V1': v1.predict(NormalizePredictors().transform(rows[predictor_columns()]))}
    for name, (model, entry) in frozen.items():
        predictions[f"{entry['role']}:{name}"] = model.predict(_numeric(rows, feature_columns(entry['config'])))
    scores = {name: _scores(y, lam) for name, lam in predictions.items()}
    weeks = {str(int(w)): {name: _scores(y[rows.week == w], lam[rows.week.to_numpy() == w]) for name, lam in predictions.items()}
             for w in sorted(rows.week.unique())}
    final = next(n for n in predictions if n.startswith('v2_final:'))
    deltas = {name: {'nll_pct': 100 * (s['nll'] / scores['V1']['nll'] - 1), 'rps_pct': 100 * (s['rps'] / scores['V1']['rps'] - 1),
                     'brier_average': s['brier_average'] - scores['V1']['brier_average']}
              for name, s in scores.items() if name != 'V1'}
    d = deltas[final]
    gate = {'historical_selection_chose_new_candidate': record['historical_selection']['selected'] != 'v1_style_glm_alpha_0.1',
            'rows_at_least_150': len(rows) >= MIN_ROWS,
            'no_material_deterioration': d['nll_pct'] <= 2 and d['rps_pct'] <= 2 and d['brier_average'] <= .005}
    result = {'revealed_at': now.isoformat(), 'frozen_at': record['frozen_at'], 'aborted_attempts': aborted, 'rows': len(rows),
              'weeks': sorted(int(w) for w in rows.week.unique()), 'games': int(rows.game_id.nunique()),
              'exclusions': exclusions, 'scores': scores, 'by_week': weeks, 'deltas_vs_v1': deltas,
              'adoption_gate': gate, 'adopt_v2': all(gate.values()),
              'row_predictions': [{'game_id': r.game_id, 'team': r.team, 'kicker_id': r.kicker_id, 'week': int(r.week),
                                   'xpm': int(r.xpm)} | {n: float(lam[i]) for n, lam in predictions.items()}
                                  for i, r in enumerate(rows.itertuples())]}
    result_path.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return result
