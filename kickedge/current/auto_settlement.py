"""Automatic settlement of tracked picks and multi legs from the approved nflverse source.

A selection settles automatically only when its game is in the verified current-season
bundle as a completed event (non-deleted END GAME play) and the tracked kicker has
exactly one reconciled label there: same stable player id, same team, the two-source
agreement the training labels use (``statistical_label_usable``) and, for a zero, the
explicit stats zero with complete play-by-play and observed participation. Anything
else stays open: KickEdge never guesses, never substitutes another kicker and never
reads a missing row as zero. Existing settlements are never replaced; a manual result
that disagrees with the source only raises a warning.
"""
from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path

from kickedge.current import multi_tracking, tracking
from kickedge.current.tracking import AUTO_SOURCE, MAX_ACTUAL_XPM, record_auto_settlement, started, tracked_directory

LOG = 'settlement_log.jsonl'
# A game normally ends about 3.5 h after kickoff; after this a missing completed event is notable.
EXPECTED_END = timedelta(hours=4)
VERIFIED_ZERO = 'explicit_stats_zero_and_complete_pbp_with_participation'


def completed_events(bundle):
    """game_id -> completed event of a verified current-season bundle."""
    return {g['game_id']: g for g in bundle.get('games', []) if (g.get('source') or {}).get('event_completed') is True}


def event_fetched_at(bundle):
    """Capture time of the event sources (play-by-play and player stats) behind the bundle."""
    times = [s.get('fetched_at') for s in bundle.get('sources', []) if s.get('dataset') in ('pbp', 'player_stats')]
    times = [t for t in times if t] or [s.get('fetched_at') for s in bundle.get('sources', []) if s.get('fetched_at')]
    return min(times) if times else None


def resolve(events, selection, bundle):
    """Actual XPM of a tracked selection: resolved, pending (game not completed) or unresolved with a reason."""
    game = events.get(selection['game_id'])
    if game is None:
        return {'status': 'pending'}
    rows = [k for k in game.get('kickers', []) if k.get('kicker_id') == selection['kicker_id']]
    if not rows:
        return {'status': 'unresolved', 'reason': 'kicker_not_in_completed_game'}
    if len(rows) > 1:
        return {'status': 'unresolved', 'reason': 'kicker_ambiguous'}
    row = rows[0]
    if row.get('team') != selection['team']:
        return {'status': 'unresolved', 'reason': 'kicker_team_mismatch'}
    if row.get('statistical_label_usable') is not True or row.get('id_in_players') is False or row.get('schedule_identity_ok') is False:
        return {'status': 'unresolved', 'reason': f"label_not_usable:{row.get('label_status') or 'unknown'}"}
    xpm = row.get('xpm')
    if isinstance(xpm, bool) or not isinstance(xpm, int) or not 0 <= xpm <= MAX_ACTUAL_XPM:
        return {'status': 'unresolved', 'reason': 'xpm_missing_or_invalid'}
    if xpm == 0 and row.get('label_evidence') != VERIFIED_ZERO:
        return {'status': 'unresolved', 'reason': 'zero_not_verified'}
    return {'status': 'resolved', 'actual_xpm': xpm,
            'source': {'game_id': game['game_id'], 'sha256': game['source']['sha256'],
                       'fetched_at': event_fetched_at(bundle), 'bundle_id': bundle.get('bundle_id')}}


def _selections(single_base, multi_base):
    """Every tracked selection with its folder: single picks and multi legs (damaged records skipped)."""
    out = []
    singles = tracking.list_tracked(single_base)
    for record in singles['open'] + singles['settled']:
        pick = record['pick']
        out.append({'type': 'single', 'tracking_id': pick['tracking_id'], 'leg': None, 'selection': pick, 'state': record,
                    'folder': tracked_directory(single_base, pick['tracking_id'])})
    for record in multi_tracking.list_tracked(multi_base)['multis']:
        tid = record['manifest']['tracking_id']
        for leg in record['legs']:
            out.append({'type': 'multi', 'tracking_id': tid, 'leg': leg['leg']['leg'], 'selection': leg['leg'], 'state': leg,
                        'folder': tracked_directory(multi_base, tid)/multi_tracking.LEGS/str(leg['leg']['leg'])})
    return out


def seasons_needed(single_base, multi_base, now):
    """Seasons with unsettled selections that have kicked off. Settled selections are cross-checked
    only against seasons loaded anyway (the current one), never loaded for that alone."""
    return {item['selection'].get('season') for item in _selections(single_base, multi_base)
            if not item['state']['original_settlement'] and started(item['selection']['kickoff'], now)
            and item['selection'].get('season')}


def _identity(item):
    s = item['selection']
    return {'type': item['type'], 'tracking_id': item['tracking_id'], 'leg': item['leg'], 'game_id': s['game_id'],
            'kicker': s['kicker'], 'kicker_id': s['kicker_id']}


def append_log(path, entry):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(entry, sort_keys=True, allow_nan=False) + '\n')


def settle_open(single_base, multi_base, bundles, failures, now, log_path):
    """Auto-settle every open selection the source resolves; report pending, unresolved and disagreements.

    ``bundles`` maps season -> verified bundle; ``failures`` maps season -> message for
    seasons that could not be loaded (their selections simply stay open).
    """
    report = {'checked': 0, 'settled': [], 'pending': [], 'unresolved': [], 'warnings': []}
    events = {season: completed_events(bundle) for season, bundle in bundles.items()}
    for item in _selections(single_base, multi_base):
        selection, state = item['selection'], item['state']
        if not started(selection['kickoff'], now):
            continue
        season = selection.get('season')
        if season not in bundles:
            if not state['original_settlement']:
                report['warnings'].append(_identity(item) | {'code': 'SOURCE_UNAVAILABLE',
                                                             'detail': failures.get(season, 'NFL data not loaded')})
            continue
        report['checked'] += 1
        found = resolve(events[season], selection, bundles[season])
        if state['original_settlement']:
            effective = state['settlement']
            if (found['status'] == 'resolved' and state['result_source'] != AUTO_SOURCE
                    and found['actual_xpm'] != effective['actual_xpm']):
                report['warnings'].append(_identity(item) | {
                    'code': 'MANUAL_RESULT_DIFFERS_FROM_SOURCE', 'recorded_xpm': effective['actual_xpm'],
                    'source_xpm': found['actual_xpm'], 'result_source': state['result_source']})
            continue
        if found['status'] == 'pending':
            report['pending'].append(_identity(item))
            if started(selection['kickoff'], now - EXPECTED_END):
                report['warnings'].append(_identity(item) | {'code': 'TRACKED_GAME_PENDING_IN_SOURCE',
                                                             'detail': 'Game should have ended; nflverse does not show it as completed yet.'})
            continue
        if found['status'] == 'unresolved':
            report['unresolved'].append(_identity(item) | {'reason': found['reason']})
            report['warnings'].append(_identity(item) | {'code': 'AUTO_SETTLEMENT_UNRESOLVED', 'detail': found['reason']})
            continue
        settlement = record_auto_settlement(item['folder'], selection, found['actual_xpm'], found['source'], now)
        if settlement is None:
            continue                                                   # settled concurrently; nothing replaced
        entry = {'timestamp': now.isoformat(), 'type': item['type'], 'tracking_id': item['tracking_id'], 'leg': item['leg'],
                 'game_id': selection['game_id'], 'kicker': selection['kicker'], 'kicker_id': selection['kicker_id'],
                 'actual_xpm': settlement['actual_xpm'], 'result': settlement['result'],
                 'source_hash': settlement['source_hash'], 'source_fetched_at': settlement['source_fetched_at']}
        append_log(log_path, entry)
        report['settled'].append(_identity(item) | {'actual_xpm': settlement['actual_xpm'], 'result': settlement['result']})
    return report
