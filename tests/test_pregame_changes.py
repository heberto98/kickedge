from copy import deepcopy
from datetime import timedelta

import pytest

from kickedge.pregame.changes import detect
from kickedge.pregame.history import OutcomeOracle
from kickedge.pregame.select import instant, iso
from kickedge.pregame.sequential import predict, simulate
from test_pregame_sequential import RULE, game, history, oracle_fixture


def evidence(kind='official_unavailable', player='X', n=3, **fields):
    return {'game_id': f'g{n}', 'team': 'A', 'kind': kind, 'player_id': player, 'name': player,
            'evidence_id': f'{kind}:{player}:{n}', 'source_url': 'https://official.example/news',
            'available_at': game(n)['prediction_cutoff'], **fields}


def decision(records, previous=()):
    def detector(g, candidate, last):
        return detect(g, candidate, records, game(2), previous, RULE)
    return predict(game(3), [history(1), history(2)], {}, change_detector=detector)['C']


@pytest.mark.parametrize('reason', ['released', 'IR', 'OUT', 'inactive'])
def test_prior_official_transaction_or_unavailable_blocks_continuity(reason):
    r = decision([evidence(status=reason)])
    assert r['expected_kicker_id'] is None
    assert r['change_signal'] == 'historical_kicker_unavailable'


def test_inactive_list_blocks_even_when_historical_candidate_not_in_depth():
    r = decision([evidence('official_inactives', None, complete_list=True, inactive_ids=['X'])])
    assert r['expected_kicker_id'] is None


def test_signed_or_elevated_replacement_requires_old_unavailable():
    roster = evidence('official_roster', 'Y', transaction='practice_squad_elevation')
    assert decision([roster])['expected_kicker_confidence'] == 'AMBIGUOUS'
    r = decision([evidence(), roster])
    assert r['expected_kicker_id'] == 'Y' and r['expected_kicker_confidence'] == 'INFERRED'
    assert not r['current_availability_verified'] and not r['pregame_identity_eligible']


@pytest.mark.parametrize('records', [
    [evidence('official_assignment', 'Y'), evidence('official_unavailable', 'Y')],
    [evidence('official_assignment', 'Y'), evidence('official_assignment', 'Z')],
    [evidence(), evidence('official_roster', 'Y'), evidence('official_roster', 'Z')],
])
def test_contradictory_or_multiple_candidates_abstain(records):
    r = decision(records)
    assert r['expected_kicker_id'] is None and r['expected_kicker_confidence'] == 'AMBIGUOUS'


def test_no_change_evidence_preserves_exact_continuity_result():
    expected = predict(game(3), [history(1), history(2)], {})['C']
    assert decision([]) == expected
    assert decision([evidence('untimed_weekly_rosters', 'Y')]) == expected


def test_new_backup_abstains_but_unique_starter_transition_can_replace():
    old = [evidence('depth_snapshot', 'X', n=2, rank=1)]
    current = [evidence('depth_snapshot', 'X', rank=1), evidence('depth_snapshot', 'Y', rank=2)]
    assert decision(current, old)['expected_kicker_confidence'] == 'AMBIGUOUS'
    current[0]['rank'], current[1]['rank'] = 2, 1
    r = decision(current, old)
    assert r['expected_kicker_id'] == 'Y' and r['expected_kicker_confidence'] == 'INFERRED'
    assert not r['current_availability_verified']
    assert len(r['change_evidence']) == 3
    # An empty PK snapshot is missing evidence, not a confirmed release.
    assert decision([], old)['expected_kicker_id'] == 'X'


@pytest.mark.parametrize('field', ['available_at', 'published_at', 'modified_at'])
def test_after_cutoff_cannot_change_selection(field):
    future = iso(instant(game(3)['prediction_cutoff']) + timedelta(seconds=1))
    assert decision([evidence(**{field: future})]) == decision([])


def test_target_outcome_is_never_an_input_and_physical_removal_keeps_freeze(tmp_path):
    manifest = oracle_fixture(tmp_path)
    baselines = [game(n, t) for n in (1, 2, 3) for t in ('A', 'B')]
    def detector(g, candidate, last):
        return detect(g, candidate, [evidence(), evidence('official_roster', 'Y')], None, [], RULE)
    before, chain = simulate(baselines, OutcomeOracle(tmp_path, manifest), {}, lambda e: None,
                             stop_at='g3', change_detector=detector)
    (tmp_path / 'g3.json').unlink()
    after, chain2 = simulate(baselines, OutcomeOracle(tmp_path, manifest), {}, lambda e: None,
                             stop_at='g3', change_detector=detector)
    assert before == after and chain == chain2
    assert next(r for r in after['C'] if r['game_id'] == 'g3' and r['team'] == 'A')['expected_kicker_id'] == 'Y'
    # Outcome-shaped records cannot masquerade as eligible pregame evidence.
    assert decision([evidence('pbp', 'Y'), evidence('player_stats', 'Y')]) == decision([])


def test_week_one_stays_unknown_even_with_assignment():
    r = detect(game(1), None, [evidence('official_assignment', 'Y', n=1)], None, [], RULE)
    assert r['expected_kicker_confidence'] == 'UNKNOWN'


def test_comparison_keeps_fixed_cohort_and_accounts_for_lost_normal_matches():
    from kickedge.pregame.change_compare import measure
    # Use actual evaluation schema instead of inventing incomplete summary rows.
    from kickedge.pregame.evaluate import attach
    before = []
    for n, actual, changed in [(3, 'Y', True), (4, 'X', False)]:
        row = predict(game(n), [history(1), history(2)], {})['C']
        row = attach(row, None, [{'player_id': actual, 'pbp_xpa': 1, 'pbp_fga': 0, 'pbp_kickoffs': 0}])
        row['actual_kicker_changed_since_prior_game'] = changed
        before.append(row)
    after = deepcopy(before)
    for r in after:
        r.update(expected_kicker_id=None, expected_kicker_confidence='AMBIGUOUS', comparison='expected_unknown')
    metrics, _ = measure(before, after)
    assert metrics['fixed_change_cohort']['total'] == 1
    assert metrics['old_errors_abstained'] == 1 and metrics['normal_correct_to_abstention'] == 1


def test_cached_change_replay_has_valid_freeze_chain_and_dated_evidence():
    import hashlib
    import json
    from pathlib import Path
    from kickedge.io import sha256_file
    root = Path(__file__).resolve().parents[1]
    pointer = root / 'data/pregame/changes/latest.json'
    if not pointer.exists():
        pytest.skip('Run python -m kickedge.pregame compare-changes')
    directory = root / json.loads(pointer.read_text())['path']
    chain, frozen, count = '0' * 64, set(), 0
    with (directory / 'events.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            event = json.loads(line)
            assert event['previous_sha256'] == chain
            content = {k: v for k, v in event.items() if k != 'event_sha256'}
            chain = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
            assert event['event_sha256'] == chain
            if event['kind'] == 'freeze':
                frozen.add(event['game_id'])
                for r in event['decisions']['C']:
                    count += 1
                    if r['week'] == 1:
                        assert r['expected_kicker_id'] is None
                    assert not r['pregame_identity_eligible']
                    for e in r.get('change_evidence', []):
                        assert e['team'] == r['team']
                        assert instant(e['available_at']) <= instant(r['prediction_cutoff'])
                        if e.get('modified_at'):
                            assert instant(e['modified_at']) <= instant(r['prediction_cutoff'])
            else:
                assert event['game_id'] in frozen
                assert instant(event['reveal_at']) <= instant(event['decision_time'])
    freeze = json.loads((directory / 'freeze.json').read_text())
    assert count == 6056 and len(frozen) == 3028
    assert chain == freeze['event_chain_final_sha256']
    assert sha256_file(directory / 'identities_C_change.json') == freeze['identity_sha256']
    assert sha256_file(directory / 'events.jsonl') == freeze['events_sha256']
