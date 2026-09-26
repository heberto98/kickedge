"""Chronological identity simulation; outcomes enter only through guarded reveal()."""
from collections import defaultdict
from datetime import timedelta
import hashlib
import heapq
import json

from .select import instant, iso


SEQUENTIAL_POLICY = {
    'version': 'sequential-v1', 'history_lag_hours': 24, 'min_consecutive_games': 2,
    'max_gap_days': 21, 'reset_each_season': True,
    'A': 'VERIFIED or STRONG official evidence',
    'B': 'A or two consecutive unique prior kickers plus fresh agreeing pregame role evidence',
    'C': 'A or two consecutive unique prior kickers; availability unverified unless corroborated',
    'development_period': '2015-2020', 'temporal_evaluation_period': '2021-2024',
    'previously_inspected_period': '2025',
    'validation_note': 'Single preregistered rule after prior snapshot study. Known audit cases overlap evaluation; not untouched validation.'}


def clear_identity(baseline, category, reason, candidates=None):
    r = dict(baseline)
    r.update(expected_kicker_id=None, expected_kicker_name=None, expected_kicker_confidence=category,
        expected_kicker_source=[], expected_kicker_evidence_type=[], expected_kicker_evidence_timestamp=None,
        expected_kicker_evidence_ids=[], expected_kicker_candidates=candidates or [],
        expected_kicker_ambiguous=category == 'AMBIGUOUS', pregame_identity_eligible=False,
        pregame_exclusion_reason=reason, inference_subtype=None)
    return r


def predict(baseline, history, names, rule=SEQUENTIAL_POLICY, change_detector=None):
    """Receives only revealed same-team history, never a target outcome argument."""
    cutoff = instant(baseline['prediction_cutoff'])
    history = [h for h in history if h['season'] == baseline['season'] and instant(h['reveal_at']) <= cutoff]
    if any(h['game_id'] == baseline['game_id'] for h in history):
        raise ValueError('Target-game history is forbidden')
    history.sort(key=lambda h: (h['kickoff_utc'], h['game_id']))
    last = history[-1] if history else None
    recent = bool(last and cutoff - instant(last['kickoff_utc']) <= timedelta(days=rule['max_gap_days']))
    last_ids = last['placekicker_ids'] if recent else []
    candidate = last_ids[0] if len(last_ids) == 1 else None
    streak, used = 0, []
    if candidate:
        previous_time = instant(baseline['kickoff_utc'])
        for h in reversed(history):
            if h['placekicker_ids'] != [candidate] or previous_time - instant(h['kickoff_utc']) > timedelta(days=rule['max_gap_days']):
                break
            streak += 1
            used.append(h)
            previous_time = instant(h['kickoff_utc'])
    historical = [{'player_id': p, 'name': names.get(p, p), 'basis': 'previous_game_placekick',
                   'source_game_id': last['game_id']} for p in last_ids]
    blocked = {c['player_id'] for c in baseline['expected_kicker_candidates'] if c.get('blocked')}
    fresh_id = baseline['expected_kicker_id']
    has_fresh_role = fresh_id is not None and baseline['expected_kicker_confidence'] == 'INFERRED'
    results = {}
    change = change_detector(baseline, candidate, last) if change_detector else None
    for policy in ('A', 'B', 'C'):
        if policy == 'C' and change is not None:
            r = dict(change)
        elif baseline['expected_kicker_confidence'] in ('VERIFIED', 'STRONG'):
            r = dict(baseline)
            r['inference_subtype'] = 'official_confirmation'
        elif baseline['expected_kicker_confidence'] == 'AMBIGUOUS':
            r = clear_identity(baseline, 'AMBIGUOUS', 'conflicting_pregame_candidates', baseline['expected_kicker_candidates'])
        elif policy == 'A':
            r = clear_identity(baseline, 'UNKNOWN', 'no_official_confirmation')
        elif len(last_ids) > 1:
            r = clear_identity(baseline, 'AMBIGUOUS', 'multiple_previous_placekickers', historical)
        elif candidate in blocked:
            r = clear_identity(baseline, 'UNKNOWN', 'known_unavailable_candidate', historical)
        elif candidate and has_fresh_role and fresh_id != candidate:
            r = clear_identity(baseline, 'AMBIGUOUS', 'history_conflicts_with_pregame_role', historical + baseline['expected_kicker_candidates'])
        elif not candidate or streak < rule['min_consecutive_games']:
            r = clear_identity(baseline, 'UNKNOWN', 'insufficient_same_season_continuity', historical)
        elif policy == 'B' and not has_fresh_role:
            r = clear_identity(baseline, 'UNKNOWN', 'no_current_role_corroboration', historical)
        else:
            r = dict(baseline)
            subtype = 'continuity_with_current_role' if has_fresh_role else 'experimental_continuity_only'
            source_urls = sorted({h['source_url'] for h in used})
            source_ids = ['history:' + h['game_id'] + ':' + baseline['team'] for h in used]
            r.update(expected_kicker_id=candidate, expected_kicker_name=names.get(candidate, candidate),
                expected_kicker_confidence='INFERRED', expected_kicker_ambiguous=False,
                expected_kicker_source=sorted(set(source_urls + (baseline['expected_kicker_source'] if has_fresh_role else []))),
                expected_kicker_evidence_type=['previous_game_placekick'] + (baseline['expected_kicker_evidence_type'] if has_fresh_role else []),
                expected_kicker_evidence_timestamp=max([h['reveal_at'] for h in used] + ([baseline['expected_kicker_evidence_timestamp']] if has_fresh_role else []), key=instant),
                expected_kicker_evidence_ids=source_ids + (baseline['expected_kicker_evidence_ids'] if has_fresh_role else []),
                expected_kicker_candidates=historical + [c for c in baseline['expected_kicker_candidates'] if c['player_id'] != candidate],
                pregame_identity_eligible=False, pregame_exclusion_reason='policy_selection_pending_review',
                inference_subtype=subtype)
        r.update(policy=policy, prior_consecutive_games=streak, prior_game_id=last['game_id'] if last else None,
            previous_placekicker_ids=last_ids,
            history_evidence=used, history_availability_basis='game_event_plus_24h_assumption_not_publication_timestamp',
            current_availability_verified=r['expected_kicker_confidence'] in ('VERIFIED', 'STRONG'),
            current_roster_verified=r['expected_kicker_confidence'] in ('VERIFIED', 'STRONG'),
            transaction_feed_complete=False, injury_feed_complete=False,
            historical_evaluation_split='development' if baseline['season'] <= 2020 else 'temporal_evaluation_with_known_audit_overlap' if baseline['season'] <= 2024 else 'previously_inspected_2025')
        # The user asked for a recommendation and comparison, not automatic
        # admission of experimental observations into a training population.
        r['pregame_identity_eligible'] = False
        r['pregame_exclusion_reason'] = 'policy_selection_pending_review' if r['expected_kicker_id'] else r['pregame_exclusion_reason']
        results[policy] = r
    return results


def simulate(baselines, oracle, names, sink, rule=SEQUENTIAL_POLICY, stop_at=None, change_detector=None):
    """Freeze both teams before enqueueing their game's eventual reveal.

    sink(event) persists the chained log. stop_at permits deletion tests: it
    returns immediately after freezing that game, before its oracle file opens.
    """
    groups = defaultdict(list)
    for r in baselines:
        groups[r['game_id']].append(r)
    ordered = sorted(groups, key=lambda k: (instant(groups[k][0]['prediction_cutoff']), k))
    pending, frozen, state = [], set(), defaultdict(list)
    predictions = {p: [] for p in ('A', 'B', 'C')}
    chain, sequence = '0' * 64, 0
    def event(kind, payload):
        nonlocal chain, sequence
        sequence += 1
        value = {'sequence': sequence, 'kind': kind, 'previous_sha256': chain, **payload}
        chain = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        sink({**value, 'event_sha256': chain})
    def reveal(now):
        while pending and pending[0][0] <= instant(now):
            _, game = heapq.heappop(pending)
            g = groups[game][0]
            reveal_at = iso(instant(g['kickoff_utc']) + timedelta(hours=rule['history_lag_hours']))
            actual = oracle.reveal(game, now, reveal_at, frozen)
            for team_game in groups[game]:
                team = team_game['team']
                selected = [a for a in actual if a['team'] == team and a['pbp_xpa'] + a['pbp_fga'] > 0]
                fact = {'game_id': game, 'team': team, 'season': g['season'], 'kickoff_utc': g['kickoff_utc'],
                    'reveal_at': reveal_at, 'placekicker_ids': sorted({a['player_id'] for a in selected}),
                    'source_sha256': sorted({a['pbp_source_sha256'] for a in selected}),
                    'source_url': f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{g["season"]}.parquet',
                    'locator': 'game_id=' + game + ';team=' + team + ';counted PAT or FG',
                    'oracle_sha256': oracle.manifest[game]['sha256']}
                state[g['season'], team].append(fact)
            event('reveal', {'game_id': game, 'reveal_at': reveal_at, 'decision_time': now,
                'oracle_sha256': oracle.manifest[game]['sha256']})
    for game in ordered:
        current = groups[game]
        cutoff = current[0]['prediction_cutoff']
        reveal(cutoff)
        fixed = {p: [] for p in predictions}
        for r in sorted(current, key=lambda r: r['team']):
            decision = predict(r, state[r['season'], r['team']], names, rule, change_detector)
            for p, row in decision.items():
                predictions[p].append(row)
                fixed[p].append(row)
        event('freeze', {'game_id': game, 'prediction_cutoff': cutoff, 'decisions': fixed})
        frozen.add(game)
        heapq.heappush(pending, (instant(current[0]['kickoff_utc']) + timedelta(hours=rule['history_lag_hours']), game))
        if stop_at == game:
            return predictions, chain
    if pending:
        reveal(iso(max(t for t, _ in pending)))
    return predictions, chain
