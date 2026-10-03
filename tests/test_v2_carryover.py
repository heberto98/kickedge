"""V2 carryover: prior season only, released before the cutoff, player/team keyed,
explicit NULLs, V1 columns untouched; freeze guard and calibration/selection rules."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kickedge.modeling.dataset import predictor_columns
from kickedge.v2 import carryover, training
from kickedge.v2.carryover import CARRYOVER_COLUMNS, PriorSeason

START = datetime(2025, 9, 7, 17, tzinfo=timezone.utc)


def event(gid, season, kickoff, home, away, kickers, home_points=24, away_points=17):
    source = dict(actual_kickoff=kickoff.isoformat(), scheduled_kickoff=kickoff.isoformat(),
                  last_event=(kickoff + timedelta(hours=3)).isoformat(),
                  available_at=(kickoff + timedelta(hours=24)).isoformat(), event_completed=True,
                  temporal_class='historical_event_data', availability_verified=False, sha256='a'*64)
    teams, conversions = [], []
    for team, opp, points, tds in ((home, away, home_points, 3), (away, home, away_points, 2)):
        common = dict(game_id=gid, season=season, team=team, opponent=opp)
        teams.append(dict(common, points=points, touchdowns=tds, drives=10, red_zone_drives=4,
                          red_zone_touchdowns=2, epa_sum=1., epa_plays=50, successes=25))
        conversions.append(dict(common, two_pt_attempts=1, team_xpa=tds - 1, coverage_ok=True))
    rows = [dict(game_id=gid, season=season, week=1, game_type='REG', team=t, opponent=o, kicker_id=k,
                 kicker_name=k, xpa=a, xpm=m, statistical_label_usable=True) for t, o, k, a, m in kickers]
    return dict(game_id=gid, season=season, source=source, kickers=rows, teams=teams, conversions=conversions)


def prior_games():
    # 2025 season: kicker K1 kicks for AAA, then (traded) for CCC; AAA scores 24 and 30.
    return [event('2025_01_BBB_AAA', 2025, START, 'AAA', 'BBB', [('AAA', 'BBB', 'K1', 3, 3), ('BBB', 'AAA', 'K2', 2, 1)]),
            event('2025_02_DDD_CCC', 2025, START + timedelta(days=7), 'CCC', 'DDD', [('CCC', 'DDD', 'K1', 4, 4)], 30, 10),
            event('2025_03_BBB_AAA', 2025, START + timedelta(days=14), 'AAA', 'BBB', [('AAA', 'BBB', 'K3', 2, 2)], 30, 20)]


def target(**changes):
    return {'game_id': '2026_01_AAA_BBB', 'season': 2026, 'team': 'BBB', 'opponent': 'AAA', 'kicker_id': 'K1',
            'kickoff': '2026-09-10T00:20:00+00:00', 'prediction_cutoff': '2026-09-09T23:20:00+00:00'} | changes


def test_kicker_follows_player_offense_team_defense_opponent():
    f = PriorSeason(2025, prior_games()).features(target())
    # K1's two 2025 games (AAA and CCC) count although he now kicks for BBB.
    assert (f['kicker_prior_season_games'], f['kicker_prior_season_xpa'], f['kicker_prior_season_xpm']) == (2, 7, 7)
    assert f['kicker_prior_season_xpm_per_game'] == 3.5 and f['kicker_prior_season_conversion_rate'] == 1
    assert f['offense_prior_season_points_per_game'] == (17 + 20) / 2           # BBB offense in 2025
    assert f['defense_prior_season_points_allowed_per_game'] == (17 + 20) / 2   # AAA defense allowed in 2025


def test_no_prior_season_is_explicitly_null():
    f = PriorSeason(2025, prior_games()).features(target(kicker_id='ROOKIE'))
    assert f['kicker_prior_season_games'] == 0
    assert all(f[k] is None for k in ('kicker_prior_season_xpa', 'kicker_prior_season_xpm',
                                      'kicker_prior_season_conversion_rate', 'kicker_prior_season_xpm_per_game'))


def test_only_the_completed_immediately_preceding_season():
    prior = PriorSeason(2025, prior_games())
    with pytest.raises(ValueError, match='immediately preceding'):
        prior.features(target(season=2027))
    with pytest.raises(ValueError, match='completed'):  # a prior game ending after the target cutoff
        prior.features(target(kickoff='2025-09-21T20:00:00+00:00', prediction_cutoff='2025-09-21T19:00:00+00:00'))
    with pytest.raises(ValueError, match='belong to the prior season'):
        PriorSeason(2025, prior_games() + [event('2026_01_X_Y', 2026, START, 'XXX', 'YYY', [])])


def test_dataset_rules_and_2026_exclusion(tmp_path):
    with pytest.raises(ValueError, match='2026'):
        carryover.load_rows(seasons=(2016, 2026))
    frame = pd.DataFrame({'game_id': ['g1', 'g2'], 'team': ['A', 'A'], 'kicker_id': ['k', 'k'], 'season': [2020, 2021],
                          'kicker_prior_season_games': [0, 1], 'kicker_prior_season_xpa': [np.nan, 2.],
                          'kicker_prior_season_xpm': [np.nan, 2.], 'kicker_prior_season_conversion_rate': [np.nan, 1.],
                          'current_season_games_before': [0, 3], 'kicker_games_before': [0, 3]})
    carryover.validate_dataset(frame)
    with pytest.raises(ValueError, match='NULL'):
        carryover.validate_dataset(frame.assign(kicker_prior_season_xpa=[0., 2.]))
    with pytest.raises(ValueError, match='2016'):
        carryover.validate_dataset(frame.assign(season=[2020, 2026]))
    assert len(CARRYOVER_COLUMNS) == 19 and not set(CARRYOVER_COLUMNS) & set(predictor_columns())


@pytest.mark.skipif(not Path('data/v2/dataset/metadata.json').exists(), reason='V2 dataset not built locally')
def test_built_dataset_matches_its_recorded_hash_and_keeps_v1_columns():
    metadata = json.loads(Path('data/v2/dataset/metadata.json').read_text())
    frame = carryover.load_dataset()
    assert carryover.content_hash(frame) == metadata['content_sha256'] and len(frame) == metadata['rows']
    assert metadata['v1_predictors'] == predictor_columns() and frame.season.max() == 2025


def oof_rows(factor):
    rng = np.random.default_rng(3)
    rows = []
    for season in range(2020, 2026):
        lam = rng.uniform(1.5, 3., 200)
        rows.append(pd.DataFrame({'season': season, 'fold_train_max': season - 1, 'lambda': lam,
                                  'xpm': rng.poisson(lam * factor)}))
    return pd.concat(rows, ignore_index=True)


def test_calibration_check_retains_only_a_consistent_rolling_improvement():
    assert training.calibration_check(oof_rows(.7))['retained'] is True      # strong, consistent overprediction
    assert training.calibration_check(oof_rows(1.))['retained'] is False     # calibrated model: no correction
    with pytest.raises(ValueError):
        training.fit_lambda_calibration(oof_rows(1.), before_season=2023)    # rows from 2023+ are not "before"


def summary(nll, rps, seasons, early_nll, early_rps, brier=.2):
    block = lambda n, r: {'nll': n, 'rps': r, 'brier_average': brier}
    return {'pooled': block(nll, rps), 'by_season': {str(y): block(v, rps) for y, v in zip(range(2020, 2026), seasons)},
            'by_week_group': {'1-4': block(early_nll, early_rps)}}


def test_selection_rule_requires_overall_gains_not_just_early_season():
    base = summary(1.70, .77, [1.7] * 6, 1.72, .78)
    early_only = summary(1.695, .766, [1.69] * 6, 1.69, .75)        # better early, <1% overall
    strong = summary(1.68, .76, [1.68] * 6, 1.70, .77)
    result = training.selection({'v1_style_glm_alpha_0.1': base, 'early': early_only, 'strong': strong})
    assert result['candidates']['early']['passes'] is False and result['candidates']['strong']['passes'] is True
    assert result['selected'] == 'strong'
    boost = training.selection({'v1_style_glm_alpha_0.1': base, 'b': strong}, families={'b': 'boost'})
    assert boost['selected'] == 'v1_style_glm_alpha_0.1'             # boosting needs >=2% NLL


def test_freeze_refuses_after_reveal_and_detects_tampering(tmp_path):
    from kickedge.v2 import freeze
    (tmp_path/freeze.REVEAL_MARKER).parent.mkdir(parents=True)
    (tmp_path/freeze.REVEAL_MARKER).write_text('{}')
    with pytest.raises(ValueError, match='revealed'):
        freeze.freeze(tmp_path)
    record = {'models': {'m': {'artifact_path': 'models/v2/m/model.joblib', 'artifact_sha256': '0'*64}}}
    (tmp_path/'reports').mkdir()
    (tmp_path/freeze.PREREGISTRATION).write_text(json.dumps(record))
    (tmp_path/'models/v2/m').mkdir(parents=True)
    (tmp_path/'models/v2/m/model.joblib').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='hash mismatch'):
        freeze.load_frozen(tmp_path, 'm')
