from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path

import pytest

from kickedge.io import sha256_file, write_json
from kickedge.pregame.history import OutcomeOracle
from kickedge.pregame.select import instant, iso, select
from kickedge.pregame.sequential import predict, simulate


RULE = {'cutoff_minutes': 60, 'depth_max_age_hours': 48, 'official_max_age_hours': 168, 'eligible_categories': ['VERIFIED']}


def game(n, team='A', season=2025):
    kickoff = instant('2025-09-07T17:00:00Z') + timedelta(days=7 * (n - 1))
    r = {'game_id': f'g{n}', 'team': team, 'opponent': 'B' if team == 'A' else 'A',
         'season': season, 'week': n, 'game_type': 'REG', 'target_season_eligible': True,
         'kickoff_utc': iso(kickoff), 'prediction_cutoff': iso(kickoff - timedelta(hours=1))}
    return select(r, [], RULE)[0]


def history(n, ids=None, season=2025):
    g = game(n, season=season)
    return {'game_id': g['game_id'], 'team': 'A', 'season': season, 'kickoff_utc': g['kickoff_utc'],
            'reveal_at': iso(instant(g['kickoff_utc']) + timedelta(hours=24)), 'placekicker_ids': ['X'] if ids is None else ids,
            'source_sha256': ['source'], 'source_url': 'https://source.example'}


def test_continuity_is_inferred_and_distinct_from_current_roster_verification():
    p = predict(game(3), [history(1), history(2)], {'X': 'Kicker X'})
    assert p['A']['expected_kicker_id'] is None and p['B']['expected_kicker_id'] is None
    assert p['C']['expected_kicker_id'] == 'X' and p['C']['expected_kicker_confidence'] == 'INFERRED'
    assert not p['C']['current_roster_verified'] and not p['C']['pregame_identity_eligible']


def test_only_one_prior_game_is_not_sufficient():
    assert predict(game(2), [history(1)], {})['C']['expected_kicker_id'] is None


def test_same_season_week_one_never_uses_previous_year_continuity():
    p = predict(game(3, season=2026), [history(1), history(2)], {})
    assert all(r['expected_kicker_id'] is None for r in p.values())


def test_bye_and_playoffs_keep_within_season_chronology():
    g = game(4) | {'week': 20, 'game_type': 'WC'}
    p = predict(g, [history(1), history(2)], {})['C']
    assert p['expected_kicker_id'] == 'X'  # two-week gap across bye is valid
    assert predict(game(7), [history(1), history(2)], {})['C']['expected_kicker_id'] is None


@pytest.mark.parametrize('ids,category', [([], 'UNKNOWN'), (['X', 'Y'], 'AMBIGUOUS'), (['Y'], 'UNKNOWN')])
def test_last_game_no_attempt_multiple_or_new_kicker_interrupts_streak(ids, category):
    p = predict(game(3), [history(1), history(2, ids)], {})['C']
    assert p['expected_kicker_confidence'] == category


def test_future_history_and_target_history_cannot_determine_prediction():
    early = predict(game(3), [history(1), history(2)], {})
    assert predict(game(3), [history(1), history(2), history(4, ['Y'])], {}) == early
    forged = history(3) | {'reveal_at': history(2)['reveal_at']}
    with pytest.raises(ValueError, match='Target-game'):
        predict(game(3), [history(1), history(2), forged], {})


def test_pregame_conflict_is_ambiguous_not_corrected_by_actual():
    b = game(3) | {'expected_kicker_id': 'Y', 'expected_kicker_name': 'Y', 'expected_kicker_confidence': 'INFERRED'}
    assert predict(b, [history(1), history(2)], {})['C']['expected_kicker_confidence'] == 'AMBIGUOUS'


def test_corroborated_continuity_enters_b_but_remains_inferred():
    b = game(3) | {'expected_kicker_id': 'X', 'expected_kicker_name': 'X', 'expected_kicker_confidence': 'INFERRED',
                   'expected_kicker_evidence_timestamp': game(3)['prediction_cutoff']}
    r = predict(b, [history(1), history(2)], {})['B']
    assert r['expected_kicker_id'] == 'X' and r['inference_subtype'] == 'continuity_with_current_role'
    assert not r['current_availability_verified']


def test_known_unavailable_player_vetoes_continuity():
    b = game(3) | {'expected_kicker_candidates': [{'player_id': 'X', 'blocked': True}]}
    assert predict(b, [history(1), history(2)], {})['C']['expected_kicker_id'] is None


def oracle_fixture(tmp_path, count=3):
    manifest = {}
    for n in range(1, count + 1):
        p = tmp_path / f'g{n}.json'
        write_json(p, [{'game_id': f'g{n}', 'team': t, 'player_id': 'X' if n < 3 else 'Y',
                       'pbp_xpa': 1, 'pbp_fga': 0, 'pbp_source_sha256': 'source'} for t in ('A', 'B')])
        manifest[f'g{n}'] = {'filename': p.name, 'sha256': sha256_file(p)}
    return manifest


def test_critical_remove_all_target_data_prediction_is_identical(tmp_path):
    manifest = oracle_fixture(tmp_path)
    baselines = [game(n, t) for n in (1, 2, 3) for t in ('A', 'B')]
    first = OutcomeOracle(tmp_path, manifest)
    events = []
    before, _ = simulate(baselines, first, {}, events.append, stop_at='g3')
    (tmp_path / 'g3.json').unlink()  # physically absent target outcome, not merely masked
    second = OutcomeOracle(tmp_path, manifest)
    after, _ = simulate(baselines, second, {}, lambda e: None, stop_at='g3')
    assert before == after
    assert first.reads == second.reads == ['g1', 'g2']
    assert before['C'][-1]['expected_kicker_id'] == 'X'


def test_freeze_reveal_order_and_state_uses_actual_not_prior_prediction(tmp_path):
    manifest = oracle_fixture(tmp_path, 5)
    baselines = [game(n, t) for n in range(1, 6) for t in ('A', 'B')]
    events = []
    result, last_hash = simulate(baselines, OutcomeOracle(tmp_path, manifest), {}, events.append)
    # g3 was predicted X but revealed Y. After g4 also reveals Y, g5 predicts Y.
    assert next(r for r in result['C'] if r['game_id'] == 'g3')['expected_kicker_id'] == 'X'
    assert next(r for r in result['C'] if r['game_id'] == 'g5')['expected_kicker_id'] == 'Y'
    frozen = set()
    chain = '0' * 64
    for e in events:
        assert e['previous_sha256'] == chain
        content = {k: v for k, v in e.items() if k != 'event_sha256'}
        chain = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
        assert chain == e['event_sha256']
        if e['kind'] == 'freeze':
            frozen.add(e['game_id'])
        else:
            assert e['game_id'] in frozen
            assert instant(e['decision_time']) >= instant(e['reveal_at'])
    assert chain == last_hash


def test_oracle_rejects_unfrozen_and_early_access(tmp_path):
    manifest = oracle_fixture(tmp_path)
    oracle = OutcomeOracle(tmp_path, manifest)
    with pytest.raises(ValueError):
        oracle.reveal('g1', '2025-09-09T00:00:00Z', '2025-09-08T17:00:00Z', set())
    with pytest.raises(ValueError):
        oracle.reveal('g1', '2025-09-08T16:59:59Z', '2025-09-08T17:00:00Z', {'g1'})


def test_real_sequential_chain_temporality_and_no_training_admission():
    root = Path(__file__).resolve().parents[1]
    pointer = root / 'data/pregame/sequential/latest.json'
    if not pointer.exists():
        pytest.skip('Run python -m kickedge.pregame compare')
    directory = root / json.loads(pointer.read_text())['path']
    chain, frozen = '0' * 64, set()
    with (directory / 'events.jsonl').open(encoding='utf-8') as f:
        for line in f:
            event = json.loads(line)
            assert event['previous_sha256'] == chain
            content = {k: v for k, v in event.items() if k != 'event_sha256'}
            chain = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
            assert chain == event['event_sha256']
            if event['kind'] == 'freeze':
                frozen.add(event['game_id'])
                for policy, rows in event['decisions'].items():
                    for r in rows:
                        for h in r['history_evidence']:
                            assert h['game_id'] != r['game_id']
                            assert instant(h['reveal_at']) <= instant(r['prediction_cutoff'])
                            assert h['season'] == r['season']
            else:
                assert event['game_id'] in frozen
    assert len(frozen) == 3028
    freeze = json.loads((directory / 'freeze.json').read_text())
    assert chain == freeze['event_chain_final_sha256']
    for policy in ('A', 'B', 'C'):
        p = directory / f'identities_{policy}.json'
        assert sha256_file(p) == freeze['identity_sha256'][policy]
        rows = json.loads((directory / f'labels_{policy}.json').read_text(encoding='utf-8'))
        assert len(rows) == 6056
        assert not any(r['eligible_for_pregame_training'] for r in rows)


def test_identity_only_builder_never_opens_missing_target_outcomes(tmp_path, monkeypatch):
    from kickedge.config import Config
    from kickedge.pregame import build as builder
    config = Config(tmp_path, 2015, 2025, 2016, ('REG',), 'observed', tmp_path / 'data', tmp_path / 'reports')
    write_json(tmp_path / 'data/processed/latest.json', {'build_id': 'historical', 'path': 'data/processed/historical'})
    write_json(tmp_path / 'data/processed/historical/build.json', {
        'artifacts': [{'path': 'data/processed/historical/labels.parquet', 'sha256': 'never-open-this-missing-file'}]})
    for path, value in [('data/pregame/manifests/sources.json', {'sources': []}),
                        ('data/pregame/manifests/official.json', {'sources': []}),
                        ('audits/pregame_claims.json', {'sources': [], 'claims': []})]:
        write_json(tmp_path / path, value)
    policy = tmp_path / 'pregame.toml'
    policy.write_bytes((Path(__file__).resolve().parents[1] / 'pregame.toml').read_bytes())
    baselines = [game(1, t) for t in ('A', 'B')]
    monkeypatch.setattr(builder, 'collect', lambda *args: (baselines, {('g1', 'A'): [], ('g1', 'B'): []}, [], []))
    def forbidden(*args):
        raise AssertionError('Outcome evaluator invoked during identity construction')
    monkeypatch.setattr(builder, 'evaluate', forbidden)
    directory = builder.build(config, policy, identities_only=True)
    assert len(json.loads((directory / 'identities.json').read_text())) == 2
    assert not (directory / 'expected_kicker_labels.json').exists()
