"""Local official-pick tracker (default directory data/current/tracked): freeze a pregame analysis, settle it by hand later.

A tracked pick is a copy of what KickEdge said before kickoff. ``pick.json`` is
created once and never rewritten; ``settlement.json`` is created once after kickoff
and only adds settled_at, actual_xpm and result. A wrong manual result is fixed by
appending ``corrections/NNNN.json`` (one new file per correction); the original
settlement and earlier corrections stay untouched, and the latest correction is the
effective result. Every file is written with exclusive creation, so a second writer
fails instead of overwriting.
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
PICK, SETTLEMENT, CORRECTIONS = 'pick.json', 'settlement.json', 'corrections'
CORRECTION_FILE = r'^\d{4}\.json$'
MAX_ACTUAL_XPM = 20
MAX_REASON = 200
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


def _corrections(directory, pick, original):
    """Correction history in order; each entry must continue from the previous effective result."""
    folder = directory/CORRECTIONS
    names = sorted(p.name for p in folder.iterdir() if re.fullmatch(CORRECTION_FILE, p.name)) if folder.is_dir() else []
    history, current = [], original
    for number, name in enumerate(names, start=1):
        entry = json.loads((folder/name).read_text(encoding='utf-8'))
        if (name != f'{number:04d}.json' or entry.get('sequence') != number
                or (entry.get('previous_actual_xpm'), entry.get('previous_result')) != (current['actual_xpm'], current['result'])
                or entry.get('new_result') != outcome(pick['side'], pick['line'], entry.get('new_actual_xpm'))):
            raise TrackingError('PICK_TAMPERED', 'Correction history failed its consistency check')
        history.append(entry)
        current = {'actual_xpm': entry['new_actual_xpm'], 'result': entry['new_result']}
    return history


def load(base, tracking_id):
    """Frozen pick, original settlement, correction history and the effective settlement."""
    directory = _directory(base, tracking_id)
    if not (directory/PICK).is_file():
        raise TrackingError('PICK_NOT_FOUND', 'Tracked pick not found')
    pick = _read_pick(directory)
    original, history, effective = None, [], None
    if (directory/SETTLEMENT).is_file():
        original = json.loads((directory/SETTLEMENT).read_text(encoding='utf-8'))
        history = _corrections(directory, pick, original)
        effective = dict(original)
        if history:
            latest = history[-1]
            effective |= {'actual_xpm': latest['new_actual_xpm'], 'result': latest['new_result'],
                          'corrected_at': latest['corrected_at']}
    return {'pick': pick, 'settlement': effective, 'original_settlement': original, 'corrections': history,
            'corrected': bool(history), 'status': 'SETTLED' if original else 'OPEN'}


def _actual(actual_xpm):
    if isinstance(actual_xpm, bool) or not isinstance(actual_xpm, int) or not 0 <= actual_xpm <= MAX_ACTUAL_XPM:
        raise TrackingError('INVALID_ACTUAL_XPM', f'Actual XPM must be a whole number from 0 to {MAX_ACTUAL_XPM}')
    return actual_xpm


def settle(base, tracking_id, actual_xpm, now):
    """Record the actual XPM once, after kickoff; the pick itself is never touched."""
    _actual(actual_xpm)
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


def correct(base, tracking_id, actual_xpm, now, reason=None):
    """Append a correction of a settled result; nothing already written is changed."""
    _actual(actual_xpm)
    if reason is not None:
        if not isinstance(reason, str) or len(reason.strip()) > MAX_REASON:
            raise TrackingError('INVALID_REASON', f'Reason must be text of at most {MAX_REASON} characters')
        reason = ' '.join(reason.split()) or None
    record = load(base, tracking_id)
    if not record['original_settlement']:
        raise TrackingError('NOT_SETTLED', 'Only a settled pick can be corrected')
    current, pick = record['settlement'], record['pick']
    if actual_xpm == current['actual_xpm']:
        raise TrackingError('NO_CHANGE', 'The actual XPM already has this value')
    sequence = len(record['corrections']) + 1
    entry = {'sequence': sequence, 'corrected_at': now.isoformat(),
             'previous_actual_xpm': current['actual_xpm'], 'previous_result': current['result'],
             'new_actual_xpm': actual_xpm, 'new_result': outcome(pick['side'], pick['line'], actual_xpm), 'reason': reason}
    try:
        _create(_directory(base, tracking_id)/CORRECTIONS/f'{sequence:04d}.json', entry)
    except FileExistsError:
        raise TrackingError('CORRECTION_CONFLICT', 'Another correction was saved first; reload and retry') from None
    return load(base, tracking_id)


def performance(records):
    """Probability-quality summary of settled picks (effective result); pushes are excluded from Brier."""
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
