"""Outcome access exists only in phase 2, after the identity artifact is frozen."""
from collections import Counter
import json

import duckdb

from kickedge.io import records, sha256_file
from .select import CATEGORIES


def attach(identity, label, actual, names=None):
    result = dict(identity)
    expected = identity['expected_kicker_id']
    placekickers = sorted({r['player_id'] for r in actual if r['pbp_xpa'] + r['pbp_fga'] > 0})
    kicking = {r['player_id'] for r in actual}
    observed_expected = next((r for r in actual if r['player_id'] == expected), None)
    if not expected:
        comparison = 'expected_unknown'
    elif not placekickers:
        comparison = 'no_actual_placekick'
    elif expected not in placekickers:
        comparison = 'mismatch'
    elif len(placekickers) > 1:
        comparison = 'expected_among_multiple'
    else:
        comparison = 'exclusive_match'
    usable = bool(label and label['statistical_label_usable'])
    result.update(actual_placekicker_ids=placekickers,
        actual_placekicker_names=[(names or {}).get(p, p) for p in placekickers],
        actual_multiple_placekickers=len(placekickers) > 1,
        expected_observed_fga=observed_expected['pbp_fga'] if observed_expected else None,
        expected_observed_kickoffs=observed_expected['pbp_kickoffs'] if observed_expected else None,
        comparison=comparison,
        expected_kicking_participation=('unknown_identity' if not expected else 'observed_kicking' if expected in kicking else 'no_kicking_evidence'),
        xpa=label['xpa'] if usable else None, xpm=label['xpm'] if usable else None,
        outcome_source='existing_reconciled_label' if usable else 'missing_validated_player_label',
        outcome_pbp_sha256=label['pbp_source_sha256'] if label else None,
        outcome_stats_sha256=label['stats_source_sha256'] if label else None,
        eligible_for_pregame_training=bool(identity['pregame_identity_eligible'] and usable and identity['target_season_eligible']))
    if identity['pregame_identity_eligible']:
        result['pregame_exclusion_reason'] = (None if result['eligible_for_pregame_training'] else
            'context_season_only' if not identity['target_season_eligible'] else 'missing_validated_player_label')
    return result


def evaluate(identity_path, identity_sha, base):
    if sha256_file(identity_path) != identity_sha:
        raise ValueError('Frozen identities changed before outcome evaluation')
    identities = json.loads(identity_path.read_text(encoding='utf-8'))
    with duckdb.connect() as con:
        labels = records(con, """SELECT game_id,team,player_id,xpa,xpm,statistical_label_usable,
            pbp_source_sha256,stats_source_sha256 FROM read_parquet(?)""", [str(base / 'labels.parquet')])
        actual = records(con, 'SELECT game_id,team,player_id,pbp_xpa,pbp_fga,pbp_kickoffs FROM read_parquet(?)', [str(base / 'pbp_kicker_totals.parquet')])
        names = dict(con.execute('SELECT player_id,display_name FROM read_parquet(?)', [str(base / 'players.parquet')]).fetchall())
    label_map = {(r['game_id'], r['team'], r['player_id']): r for r in labels}
    actual_map = {}
    for r in actual:
        actual_map.setdefault((r['game_id'], r['team']), []).append(r)
    result = [attach(r, label_map.get((r['game_id'], r['team'], r['expected_kicker_id'])),
                     actual_map.get((r['game_id'], r['team']), []), names) for r in identities]
    if sha256_file(identity_path) != identity_sha:
        raise ValueError('Evaluation mutated frozen identities')
    return result


def summarize(rows):
    def stats(group):
        n = len(group)
        counts = Counter(r['expected_kicker_confidence'] for r in group)
        comparisons = Counter(r['comparison'] for r in group)
        known = sum(bool(r['expected_kicker_id']) for r in group)
        comparable = sum(r['expected_kicker_id'] is not None and bool(r['actual_placekicker_ids']) for r in group)
        matched = comparisons['exclusive_match'] + comparisons['expected_among_multiple']
        return {'team_games': n, 'identified': known, 'coverage_pct': 100 * known / n,
            'categories': {c: counts[c] for c in CATEGORIES},
            'category_pct': {c: 100 * counts[c] / n for c in CATEGORIES},
            'sufficient_identity': counts['VERIFIED'] + counts['STRONG'],
            'comparisons': dict(comparisons), 'comparable': comparable, 'membership_matches': matched,
            'membership_accuracy_pct': 100 * matched / comparable if comparable else None,
            'exact_set_accuracy_pct': 100 * comparisons['exclusive_match'] / comparable if comparable else None,
            'multiple_actual': sum(r['actual_multiple_placekickers'] for r in group),
            'known_without_kicking_evidence': sum(r['expected_kicking_participation'] == 'no_kicking_evidence' for r in group),
            'expected_xpm_zero': sum(r['xpm'] == 0 for r in group),
            'expected_missing_label': sum(r['expected_kicker_id'] is not None and r['xpm'] is None for r in group),
            'training_eligible': sum(r['eligible_for_pregame_training'] for r in group)}
    return {'total': stats(rows), 'seasons': {str(s): stats([r for r in rows if r['season'] == s]) for s in sorted({r['season'] for r in rows})}}
