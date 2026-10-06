"""Local official-pick tracker (default directory data/current/tracked): freeze a pregame analysis, settle it by hand later.

A tracked pick is a copy of what KickEdge said before kickoff. ``pick.json`` is
created once and never rewritten; ``settlement.json`` is created once after kickoff
and only adds settled_at, actual_xpm and result. Both files are written with
exclusive creation, so a second writer fails instead of overwriting.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re

from kickedge.current.snapshot import digest
from kickedge.inference.odds import american_to_decimal

TRACKING_ID = r'^[0-9a-f]{64}$'
PICK, SETTLEMENT = 'pick.json', 'settlement.json'
MAX_ACTUAL_XPM = 20
# Summary booleans worth keeping with the frozen pick; warnings are copied verbatim.
QUALITY_FLAGS = ('model_verified', 'pregame_availability_verified', 'target_game_verified',
                 'kicker_identity_verified', 'kicker_current_team_verified', 'feature_schema_verified',
                 'missing_feature_count', 'null_feature_count')


class TrackingError(ValueError):
    """Rejected tracking operation; ``code`` maps to the HTTP error."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _instant(value):
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise TrackingError('INVALID_PICK', 'Stored kickoff has no time zone')
    return moment


def _decimal_odds(market):
    if market.get('odds_format') == 'decimal':
        return 'decimal', market['decimal_odds'], market['decimal_odds']
    return 'american', market['american_odds'], american_to_decimal(market['american_odds'])


def freeze_pick(analysis, analysis_id, now):
    """The immutable pick record of a stored single analysis, only before kickoff."""
    game, prop, quality = analysis['game'], analysis['prop'], analysis['data_quality']
    if now >= _instant(game['kickoff']):
        raise TrackingError('GAME_STARTED', 'Kickoff has passed; only pregame analyses can be tracked')
    odds_format, odds, decimal = _decimal_odds(analysis['market'])
    identity = {'game_id': game['game_id'], 'kicker_id': game['kicker_id'], 'side': prop['side'],
                'line': prop['line'], 'decimal_odds': decimal}
    pick = {'tracking_id': digest(identity), 'created_at': now.isoformat(), 'analysis_id': analysis_id,
            'game_id': game['game_id'], 'kickoff': game['kickoff'], 'season': game.get('season'), 'week': game.get('week'),
            'kicker': analysis['player']['kicker_name'], 'kicker_id': game['kicker_id'],
            'team': game['team'], 'opponent': game['opponent'],
            'home_team': game.get('home_team'), 'away_team': game.get('away_team'),
            'side': prop['side'], 'line': prop['line'], 'odds_format': odds_format, 'odds': odds, 'decimal_odds': decimal,
            'kickedge_probability': prop['model_side_probability'],
            'kickedge_probability_no_push': prop['model_probability_conditional'],
            'expected_xpm': analysis['prediction']['expected_xpm'],
            'p_over': prop['p_over'], 'p_under': prop['p_under'], 'p_push': prop['p_push'],
            'model_version': analysis['model']['version'], 'model_artifact_sha256': analysis['model']['artifact_sha256'],
            'snapshot_sha256': analysis['provenance']['feature_snapshot_sha256'],
            'analysis_generated_at': analysis['provenance']['analysis_generated_at'],
            'feature_cutoff': game.get('cutoff'),
            'data_quality': {k: quality.get(k) for k in QUALITY_FLAGS} | {'warnings': list(quality.get('warnings', []))}}
    return pick | {'integrity_sha256': digest(pick)}


def outcome(side, line, actual_xpm):
    """WIN, LOSS or PUSH of an XPM prop from the actual count."""
    if actual_xpm == line:
        return 'PUSH'
    return 'WIN' if (actual_xpm > line) == (side == 'over') else 'LOSS'


def _directory(base, tracking_id):
    if not isinstance(tracking_id, str) or not re.fullmatch(TRACKING_ID, tracking_id):
        raise TrackingError('INVALID_TRACKING_ID', 'Invalid tracking id')
    base = Path(base).resolve()
    path = (base/tracking_id).resolve()
    if not path.is_relative_to(base) or path == base:
        raise TrackingError('INVALID_TRACKING_ID', 'Invalid tracking id')
    return path


def _create(path, record):
    """Write a new JSON file; never replaces an existing one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(record, indent=2, allow_nan=False) + '\n').encode('utf-8')
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o644)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(data)


def _read_pick(directory):
    pick = json.loads((directory/PICK).read_text(encoding='utf-8'))
    frozen = {k: v for k, v in pick.items() if k != 'integrity_sha256'}
    if digest(frozen) != pick.get('integrity_sha256') or pick.get('tracking_id') != directory.name:
        raise TrackingError('PICK_TAMPERED', 'Tracked pick failed its integrity check')
    return pick


def track(base, analysis, analysis_id, now):
    """Freeze a pick; tracking the same pick again returns the original unchanged."""
    pick = freeze_pick(analysis, analysis_id, now)
    directory = _directory(base, pick['tracking_id'])
    try:
        _create(directory/PICK, pick)
    except FileExistsError:
        return load(base, pick['tracking_id']) | {'already_tracked': True}
    return load(base, pick['tracking_id']) | {'already_tracked': False}


def load(base, tracking_id):
    directory = _directory(base, tracking_id)
    if not (directory/PICK).is_file():
        raise TrackingError('PICK_NOT_FOUND', 'Tracked pick not found')
    pick = _read_pick(directory)
    settlement = None
    if (directory/SETTLEMENT).is_file():
        settlement = json.loads((directory/SETTLEMENT).read_text(encoding='utf-8'))
    return {'pick': pick, 'settlement': settlement, 'status': 'SETTLED' if settlement else 'OPEN'}


def settle(base, tracking_id, actual_xpm, now):
    """Record the actual XPM once, after kickoff; the pick itself is never touched."""
    if isinstance(actual_xpm, bool) or not isinstance(actual_xpm, int) or not 0 <= actual_xpm <= MAX_ACTUAL_XPM:
        raise TrackingError('INVALID_ACTUAL_XPM', f'Actual XPM must be a whole number from 0 to {MAX_ACTUAL_XPM}')
    record = load(base, tracking_id)
    pick = record['pick']
    if record['settlement']:
        raise TrackingError('ALREADY_SETTLED', 'This pick is already settled')
    if now < _instant(pick['kickoff']):
        raise TrackingError('NOT_STARTED', 'A pick can be settled only after kickoff')
    settlement = {'settled_at': now.isoformat(), 'actual_xpm': actual_xpm,
                  'result': outcome(pick['side'], pick['line'], actual_xpm)}
    try:
        _create(_directory(base, tracking_id)/SETTLEMENT, settlement)
    except FileExistsError:
        raise TrackingError('ALREADY_SETTLED', 'This pick is already settled') from None
    return load(base, tracking_id)


def performance(records):
    """Probability-quality summary of settled picks; pushes are excluded from Brier."""
    settled = [r for r in records if r['settlement']]
    graded = [r for r in settled if r['settlement']['result'] != 'PUSH']
    # Without a push, the no-push conditional probability is the probability of a win.
    probabilities = [r['pick']['kickedge_probability_no_push'] for r in graded]
    outcomes = [1. if r['settlement']['result'] == 'WIN' else 0. for r in graded]
    n = len(graded)
    return {'tracked': len(records), 'open': len(records) - len(settled), 'settled': len(settled),
            'pushes': len(settled) - n, 'graded': n,
            'average_probability': sum(probabilities) / n if n else None,
            'observed_frequency': sum(outcomes) / n if n else None,
            'brier_score': sum((p - y) ** 2 for p, y in zip(probabilities, outcomes)) / n if n else None}


def list_tracked(base):
    """Every readable tracked pick, newest kickoff first; damaged records are reported, not shown."""
    base = Path(base)
    records, rejected = [], 0
    if base.is_dir():
        for child in base.iterdir():
            if not re.fullmatch(TRACKING_ID, child.name):
                continue
            try:
                records.append(load(base, child.name))
            except (OSError, ValueError, KeyError, TypeError):
                rejected += 1
    records.sort(key=lambda r: (r['pick']['kickoff'], r['pick']['created_at']), reverse=True)
    return {'summary': performance(records) | {'unreadable': rejected},
            'open': [r for r in records if not r['settlement']],
            'settled': [r for r in records if r['settlement']]}
