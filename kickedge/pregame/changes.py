"""Pure pre-freeze change rules. Receives identities/evidence, never outcomes."""
from .select import admissibility, instant, select
from .sequential import clear_identity


VERSION = 'change-v1'


def detect(game, historical_id, evidence, previous_game, previous_evidence, policy):
    """Return an override on positive change evidence; None preserves continuity.

    A new backup is uncertainty, not an automatic starter. Depth replacement
    requires a visible transition from the historical player's rank 1 to a
    unique new rank 1. Neither rule establishes health or active-game status.
    """
    if game['week'] == 1:
        return clear_identity(game, 'UNKNOWN', 'week_one_out_of_scope')
    current = [e for e in evidence if e['game_id'] == game['game_id'] and e['team'] == game['team']
               and admissibility(e, instant(game['prediction_cutoff']), policy) is None]
    prior = []
    if (previous_game and previous_game['game_id'] != game['game_id']
            and previous_game['team'] == game['team'] and previous_game['season'] == game['season']
            and instant(previous_game['kickoff_utc']) < instant(game['prediction_cutoff'])):
        prior = [e for e in previous_evidence if e['kind'] == 'depth_snapshot'
                 and e['game_id'] == previous_game['game_id'] and e['team'] == game['team']
                 and admissibility(e, instant(previous_game['prediction_cutoff']), policy) is None]
    selected, _ = select(game, current, policy)
    candidates = selected['expected_kicker_candidates']
    blocked = {e.get('player_id') for e in current if e['kind'] == 'official_unavailable'}
    blocked.update(c['player_id'] for c in candidates if c['blocked'])
    for e in current:
        if e['kind'] == 'official_inactives' and e.get('complete_list'):
            blocked.update(e.get('inactive_ids', []))
    assignments = [c for c in candidates if c['explicit_assignment']]
    roster = [c for c in candidates if c['active_roster'] and not c['blocked']]
    depth = [e for e in current if e['kind'] == 'depth_snapshot']
    top = [e for e in depth if e.get('rank') == 1 and e.get('player_id') not in blocked]
    old_top = any(e.get('player_id') == historical_id and e.get('rank') == 1 for e in prior)
    prior_ids = {e.get('player_id') for e in prior}
    added = [e for e in depth if e.get('player_id') not in prior_ids and e.get('player_id') != historical_id]
    removed_or_demoted = not any(e.get('player_id') == historical_id and e.get('rank') == 1 for e in depth)

    def result(reason, chosen=None, category='AMBIGUOUS', use_prior=False):
        support = current + (prior if use_prior else [])
        r = clear_identity(game, category, reason, candidates)
        r.update(change_detector_version=VERSION, change_signal=reason,
                 change_historical_id=historical_id, change_evidence=support,
                 expected_kicker_source=sorted({e['source_url'] for e in support}),
                 expected_kicker_evidence_ids=sorted({e['evidence_id'] for e in support}),
                 expected_kicker_evidence_type=sorted({e['kind'] for e in support}),
                 expected_kicker_evidence_timestamp=max((e['available_at'] for e in support), key=instant, default=None))
        if chosen:
            r.update(expected_kicker_id=chosen['player_id'], expected_kicker_name=chosen.get('name'),
                     expected_kicker_confidence=category, expected_kicker_ambiguous=False,
                     inference_subtype='change_detector:' + reason,
                     pregame_exclusion_reason='policy_selection_pending_review')
        return r

    # Explicit contradictory statements cannot be resolved with game outcomes.
    if assignments and (len(assignments) > 1 or any(c['blocked'] for c in assignments)):
        return result('contradictory_official_assignments')
    if assignments and assignments[0]['player_id'] != historical_id:
        c = assignments[0]
        return result('official_replacement', c if c['player_id'] else None,
                      'VERIFIED' if c['player_id'] else 'UNKNOWN')
    if assignments:
        return None  # Existing explicit confirmation outranks depth uncertainty.
    if historical_id and historical_id in blocked:
        if len(roster) == 1 and roster[0]['player_id']:
            c = roster[0]
            return result('unavailable_with_active_replacement', c, 'STRONG' if c['not_inactive'] else 'INFERRED')
        return result('historical_kicker_unavailable', category='AMBIGUOUS' if len(roster) > 1 else 'UNKNOWN')
    if historical_id and any(c['player_id'] != historical_id for c in roster):
        return result('new_active_roster_candidate_without_clear_assignment')
    if old_top and depth and removed_or_demoted:
        if len(top) == 1 and top[0].get('player_id'):
            return result('depth_starter_transition', top[0], 'INFERRED', use_prior=True)
        return result('depth_starter_removed_or_unresolved', use_prior=True)
    if old_top and added:
        return result('new_depth_candidate', use_prior=True)
    return None
