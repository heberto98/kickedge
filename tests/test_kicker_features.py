from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import importlib.util
import json
import random

import pytest

from kickedge.io import sha256_file, write_json


def implementation():
    assert importlib.util.find_spec('kickedge.features.kicker') is not None, 'Kicker feature builder is not implemented'
    return importlib.import_module('kickedge.features.kicker')


def fixture(tmp_path, n=7):
    identities, manifest = [], {}
    for i in range(1, n + 1):
        kickoff = datetime(2025, 9, 7, 17, tzinfo=timezone.utc) + timedelta(days=7 * (i - 1))
        identity = dict(game_id=f'g{i}', team='A', opponent='B', kicker_id='K', kicker_name='Kicker',
                        season=2025, week=i, game_type='REG', kickoff=kickoff.isoformat(),
                        prediction_cutoff=(kickoff-timedelta(hours=1)).isoformat())
        identities.append(identity)
        path = tmp_path / f'g{i}.json'
        write_json(path, [dict(game_id=f'g{i}', team='A', kicker_id='K', xpa=i+1, xpm=i,
                              statistical_label_usable=True, multiple_placekickers=False)])
        manifest[f'g{i}'] = dict(filename=path.name, sha256=sha256_file(path),
            available_at=(kickoff+timedelta(hours=24)).isoformat(), availability_verified=True)
    return identities, manifest


def run(tmp_path, identities, manifest, stop_at=None):
    m = implementation()
    events = []
    rows = m.simulate(identities, m.LabelOracle(tmp_path, manifest), events.append, stop_at=stop_at)
    return rows, events


def mutate(tmp_path, manifest, game, **changes):
    path = tmp_path / manifest[game]['filename']
    rows = json.loads(path.read_text())
    rows[0].update(changes)
    write_json(path, rows)
    manifest[game]['sha256'] = sha256_file(path)


@pytest.mark.parametrize('changes', [{'xpm': 0}, {'xpa': 50}, {'xpm': 0, 'xpa': 50}])
def test_target_counts_cannot_change_same_game_features(tmp_path, changes):
    ids, manifest = fixture(tmp_path)
    before, _ = run(tmp_path, ids, manifest)
    mutate(tmp_path, manifest, 'g4', **changes)
    after, _ = run(tmp_path, ids, manifest)
    assert before[3] == after[3]
    assert before[4]['previous_game_xpm'] == 4
    assert after[4]['previous_game_xpm'] == changes.get('xpm', 4)
    assert after[4]['previous_game_xpa'] == changes.get('xpa', 5)


def test_physical_target_deletion_preserves_features_and_freeze(tmp_path):
    ids, manifest = fixture(tmp_path)
    before, events = run(tmp_path, ids, manifest, stop_at='g4')
    (tmp_path / 'g4.json').unlink()
    after, events_after = run(tmp_path, ids, manifest, stop_at='g4')
    assert before == after and events == events_after
    assert not any(e['kind'] == 'reveal' and e['game_id'] == 'g4' for e in events)


def test_exact_rolling_windows_and_season_to_date_exclude_current(tmp_path):
    ids, manifest = fixture(tmp_path)
    rows, _ = run(tmp_path, ids, manifest)
    r = rows[6]
    assert (r['kicker_games_before'], r['kicker_xpa_before'], r['kicker_xpm_before']) == (6, 27, 21)
    assert r['kicker_xp_conversion_rate_before'] == pytest.approx(21/27)
    assert r['kicker_xpm_per_game_before'] == 3.5 and r['kicker_xpa_per_game_before'] == 4.5
    assert (r['kicker_xpa_last_3'], r['kicker_xpm_last_3']) == (18, 15)
    assert r['kicker_xp_conversion_last_3'] == pytest.approx(15/18)
    assert r['kicker_xpm_per_game_last_3'] == 5
    assert (r['kicker_xpa_last_5'], r['kicker_xpm_last_5']) == (25, 20)
    assert r['kicker_xp_conversion_last_5'] == .8 and r['kicker_xpm_per_game_last_5'] == 4
    # Recency is measured when predicting, not using the target game's later start.
    assert r['days_since_last_game'] == pytest.approx(7-1/24)
    assert r['feature_provenance']['last_3_game_ids'] == ['g4', 'g5', 'g6']
    assert r['feature_provenance']['last_5_game_ids'] == ['g2', 'g3', 'g4', 'g5', 'g6']


def test_first_game_has_zero_counts_null_rates_no_future_fill(tmp_path):
    ids, manifest = fixture(tmp_path)
    rows, _ = run(tmp_path, ids, manifest)
    r = rows[0]
    assert r['kicker_games_before'] == r['kicker_xpa_before'] == r['kicker_xpm_before'] == 0
    for name in ['kicker_xp_conversion_rate_before', 'kicker_xpm_per_game_before',
                 'previous_game_xpa', 'previous_game_xpm', 'days_since_last_game', 'kicker_xpa_last_3', 'kicker_xpa_last_5']:
        assert r[name] is None
    assert not r['kicker_has_prior_game'] and not r['kicker_has_3_prior_games'] and not r['kicker_has_5_prior_games']
    assert r['kicker_low_sample_flag']
    assert rows[1]['kicker_xpm_last_3'] is None
    assert rows[4]['kicker_xpm_last_5'] is None


def test_future_mutation_does_not_change_any_past_row(tmp_path):
    ids, manifest = fixture(tmp_path)
    before, _ = run(tmp_path, ids, manifest)
    mutate(tmp_path, manifest, 'g7', xpa=99, xpm=99)
    after, _ = run(tmp_path, ids, manifest)
    assert before == after


def test_deterministic_chronology_not_input_order_or_week(tmp_path):
    ids, manifest = fixture(tmp_path)
    ids[3]['week'] = 1  # metadata week must not override actual kickoff ordering
    before, events = run(tmp_path, ids, manifest)
    random.Random(17).shuffle(ids)
    after, events_after = run(tmp_path, ids, manifest)
    assert before == after and events == events_after


def test_global_kicker_history_survives_team_change_resets_season(tmp_path):
    ids, manifest = fixture(tmp_path)
    ids[3]['team'] = 'C'
    mutate(tmp_path, manifest, 'g4', team='C')
    ids[6]['season'] = 2026
    rows, _ = run(tmp_path, ids, manifest)
    assert rows[3]['kicker_games_before'] == 3 and rows[3]['previous_game_xpm'] == 3
    assert rows[4]['kicker_games_before'] == 4
    assert rows[6]['kicker_games_before'] == 0


def test_zero_attempts_is_not_missing_and_invalid_label_not_backfilled(tmp_path):
    ids, manifest = fixture(tmp_path)
    for i in (1, 2, 3):
        mutate(tmp_path, manifest, f'g{i}', xpa=0, xpm=0)
    rows, _ = run(tmp_path, ids, manifest)
    assert rows[3]['kicker_xpm_last_3'] == 0 and rows[3]['kicker_xp_conversion_last_3'] is None
    mutate(tmp_path, manifest, 'g3', xpa=None, xpm=None, statistical_label_usable=False)
    rows, _ = run(tmp_path, ids, manifest)
    assert rows[3]['kicker_games_before'] == 3
    assert rows[3]['kicker_xpa_before'] is None and rows[3]['kicker_xpm_last_3'] is None
    assert rows[3]['previous_game_xpm'] is None
    assert rows[3]['feature_provenance']['unusable_prior_game_ids'] == ['g3']


def test_unavailable_prior_results_are_not_read_or_treated_as_known_zero(tmp_path):
    ids, manifest = fixture(tmp_path)
    manifest['g1']['available_at'] = '2026-09-26T00:00:00+00:00'
    (tmp_path / 'g1.json').unlink()
    rows, _ = run(tmp_path, ids[:2], manifest, stop_at='g2')
    assert rows[1]['kicker_games_before'] == 0
    assert rows[1]['history_unavailable_before_cutoff']
    assert rows[1]['kicker_xpm_per_game_before'] is None


def test_same_kickoff_rows_never_reveal_each_others_results(tmp_path):
    ids, manifest = fixture(tmp_path, n=2)
    ids[1]['kickoff'], ids[1]['prediction_cutoff'] = ids[0]['kickoff'], ids[0]['prediction_cutoff']
    rows, events = run(tmp_path, ids, manifest)
    assert all(r['kicker_games_before'] == 0 for r in rows)
    assert all(e['kind'] == 'freeze' for e in events)


def test_duplicate_identity_fails_instead_of_double_counting(tmp_path):
    ids, manifest = fixture(tmp_path)
    with pytest.raises(ValueError, match='Duplicate'):
        run(tmp_path, ids+[deepcopy(ids[0])], manifest)


def test_oracle_requires_frozen_game_and_elapsed_availability(tmp_path):
    _, manifest = fixture(tmp_path)
    oracle = implementation().LabelOracle(tmp_path, manifest)
    with pytest.raises(ValueError):
        oracle.reveal('g1', '2025-09-09T00:00:00+00:00', set())
    with pytest.raises(ValueError):
        oracle.reveal('g1', '2025-09-07T00:00:00+00:00', {'g1'})


def test_observed_target_flags_do_not_enter_predictors(tmp_path):
    ids, manifest = fixture(tmp_path)
    before, _ = run(tmp_path, ids, manifest)
    mutate(tmp_path, manifest, 'g4', multiple_placekickers=True, role_evidence='unusual')
    after, _ = run(tmp_path, ids, manifest)
    assert before[3] == after[3]
    assert 'multiple_placekickers' not in before[3]


def test_null_reasons_use_each_actual_window_not_whole_season(tmp_path):
    ids, manifest = fixture(tmp_path)
    mutate(tmp_path, manifest, 'g1', xpa=None, xpm=None, statistical_label_usable=False)
    for i in (2, 3, 4):
        mutate(tmp_path, manifest, f'g{i}', xpa=0, xpm=0)
    rows, _ = run(tmp_path, ids, manifest)
    r = rows[4]
    assert r['kicker_xpm_last_3'] == 0
    assert r['feature_provenance']['null_reasons']['kicker_xp_conversion_last_3'] == 'zero_attempt_denominator'
    assert r['feature_provenance']['null_reasons']['kicker_xpa_last_5'] == 'insufficient_window'
    assert r['feature_provenance']['null_reasons']['kicker_xpa_before'] == 'unusable_prior_label'
