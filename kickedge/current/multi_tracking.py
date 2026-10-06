"""Local official multi tracker: freeze a whole multiple-selection analysis before any
leg starts, then settle and correct each leg by hand (default directory
data/current/tracked_multi).

``manifest.json`` is created once with an integrity hash and never rewritten. Each
leg ``legs/<n>/`` holds its own append-only ``settlement.json`` and ``corrections/``,
with exactly the Single tracker rules. Combined figures are the ones frozen from the
analysis (independence approximation); KickEdge never simulates parlay payouts.
"""
from __future__ import annotations

from pathlib import Path
import re

from kickedge.current.multi import MAX_SELECTIONS
from kickedge.current.snapshot import digest
from kickedge.current.tracking import (TRACKING_ID, TrackingError, correct_selection, create_json, performance,
                                       prediction_fields, read_frozen, selection_identity, settle_selection,
                                       settlement_state, started, tracked_directory)

MANIFEST, LEGS = 'manifest.json', 'legs'
OPEN, PARTIAL, SETTLED = 'OPEN', 'PARTIALLY SETTLED', 'SETTLED'
ALL_WON, HAS_LOSS, NO_LOSS_PUSH = 'ALL LEGS WON', 'HAS LOSS', 'NO-LOSS WITH PUSH'
PUSH_NOTE = 'One or more legs pushed. Sportsbook settlement rules may vary.'
INDEPENDENCE_NOTE = 'Combined probabilities assume independence.'
LEG_CORRELATION_NOTE = ('Legs of the same multi can be correlated (same game, same week), so leg-level metrics '
                        'are not independent observations.')


def freeze_multi(record, analysis_id, now):
    """The immutable manifest of a stored multi analysis; refused if any leg has started."""
    if not record.get('combined_available') or record.get('kind') != 'multi':
        raise TrackingError('INVALID_PICK', 'Only a complete multi analysis can be tracked')
    legs = []
    for number, selection in enumerate(record['selections'], start=1):
        if selection.get('status') != 'ok':
            raise TrackingError('INVALID_PICK', 'Only a complete multi analysis can be tracked')
        fields = prediction_fields(selection['result'])
        if started(fields['kickoff'], now):
            raise TrackingError('GAME_STARTED', f'Selection {number} has reached kickoff; the whole multi cannot be tracked')
        legs.append({'leg': number} | fields)
    combined = record['combined']
    identity = sorted(selection_identity(leg) for leg in legs)
    manifest = {'tracking_id': digest({'kind': 'multi', 'selections': identity}), 'analysis_id': analysis_id,
                'created_at': now.isoformat(), 'selection_count': len(legs),
                'combined_decimal_odds': combined['combined_decimal_odds'],
                'market_implied_combined_probability': combined['implied_probability'],
                'approximate_kickedge_combined_probability': combined['model_probability'],
                'combined_probability_basis': combined['model_probability_basis'],
                'no_loss_probability': combined.get('no_loss_probability'),
                'independence_warning': combined['warnings'][0],
                'same_game_correlation_warning': combined['same_game_correlation_warning'],
                'same_game_ids': combined['same_game_ids'], 'push_possible': combined['push_possible'],
                'warnings': combined['warnings'], 'legs': legs}
    return manifest | {'integrity_sha256': digest(manifest)}


def track(base, record, analysis_id, now):
    """Freeze a multi; the same selections tracked again return the original unchanged."""
    manifest = freeze_multi(record, analysis_id, now)
    directory = tracked_directory(base, manifest['tracking_id'])
    try:
        create_json(directory/MANIFEST, manifest)
    except FileExistsError:
        return load(base, manifest['tracking_id']) | {'already_tracked': True}
    return load(base, manifest['tracking_id']) | {'already_tracked': False}


def multi_outcome(results):
    """Descriptive outcome of a fully settled multi; never a payout."""
    if 'LOSS' in results:
        return HAS_LOSS
    return NO_LOSS_PUSH if 'PUSH' in results else ALL_WON


def load(base, tracking_id):
    directory = tracked_directory(base, tracking_id)
    if not (directory/MANIFEST).is_file():
        raise TrackingError('PICK_NOT_FOUND', 'Tracked multi not found')
    manifest = read_frozen(directory/MANIFEST, directory, 'Tracked multi')
    legs = [{'leg': leg} | settlement_state(directory/LEGS/str(leg['leg']), leg) for leg in manifest['legs']]
    results = [leg['settlement']['result'] for leg in legs if leg['settlement']]
    status = SETTLED if len(results) == len(legs) else PARTIAL if results else OPEN
    return {'manifest': manifest, 'legs': legs, 'status': status, 'settled_legs': len(results),
            'outcome': multi_outcome(results) if status == SETTLED else None,
            'push_note': PUSH_NOTE if 'PUSH' in results else None}


def _leg(record, leg):
    if isinstance(leg, bool) or not isinstance(leg, int) or not 1 <= leg <= min(MAX_SELECTIONS, len(record['legs'])):
        raise TrackingError('LEG_NOT_FOUND', 'Selection not found in this tracked multi')
    return record['legs'][leg - 1]


def settle_leg(base, tracking_id, leg, actual_xpm, now):
    """Settle one leg once, after that leg's kickoff."""
    record = load(base, tracking_id)
    state = _leg(record, leg)
    settle_selection(tracked_directory(base, tracking_id)/LEGS/str(leg), state['leg'], state, actual_xpm, now, noun='selection')
    return load(base, tracking_id)


def correct_leg(base, tracking_id, leg, actual_xpm, now, reason=None):
    """Append an audited correction to one settled leg; the manifest is never touched."""
    record = load(base, tracking_id)
    state = _leg(record, leg)
    correct_selection(tracked_directory(base, tracking_id)/LEGS/str(leg), state['leg'], state, actual_xpm, now,
                      reason, noun='selection')
    return load(base, tracking_id)


def multi_performance(records):
    """Descriptive counts and the all-legs-win event; combined probabilities assume independence."""
    settled = [r for r in records if r['status'] == SETTLED]
    won = [1. if r['outcome'] == ALL_WON else 0. for r in settled]
    probabilities = [r['manifest']['approximate_kickedge_combined_probability'] for r in settled]
    n = len(settled)
    return {'tracked': len(records), 'open': sum(r['status'] == OPEN for r in records),
            'partially_settled': sum(r['status'] == PARTIAL for r in records), 'settled': n,
            'all_legs_won': sum(r['outcome'] == ALL_WON for r in settled),
            'has_loss': sum(r['outcome'] == HAS_LOSS for r in settled),
            'no_loss_with_push': sum(r['outcome'] == NO_LOSS_PUSH for r in settled),
            'average_combined_probability': sum(probabilities) / n if n else None,
            'observed_all_win_frequency': sum(won) / n if n else None,
            'all_win_brier_score': sum((p - y) ** 2 for p, y in zip(probabilities, won)) / n if n else None}


def list_tracked(base):
    """Tracked multis (newest first) with leg-level and multi-level metrics; damaged records excluded."""
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
    records.sort(key=lambda r: (min(leg['kickoff'] for leg in r['manifest']['legs']), r['manifest']['created_at']), reverse=True)
    legs = [{'pick': leg['leg'], 'settlement': leg['settlement']} for r in records for leg in r['legs']]
    groups = {'independent_games': [r for r in records if not r['manifest']['same_game_correlation_warning']],
              'same_game_correlated': [r for r in records if r['manifest']['same_game_correlation_warning']]}
    return {'summary': {'tracked': len(records), 'unreadable': rejected,
                        'legs': performance(legs) | {'source': 'multi_leg', 'note': LEG_CORRELATION_NOTE},
                        'multis': {name: multi_performance(group) for name, group in groups.items()},
                        'combined_note': INDEPENDENCE_NOTE},
            'multis': records}
