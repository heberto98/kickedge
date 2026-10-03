"""Historical audit guards and true temporal prediction behavior."""
import importlib
import json

import duckdb
import numpy as np
import pandas as pd
import pytest

from kickedge.modeling.dataset import predictor_columns


def audit_module():
    try:
        return importlib.import_module('kickedge.v2.audit')
    except ModuleNotFoundError:
        pytest.fail('The historical V2 audit API has not been implemented')


def historical_frame(years=(2019, 2020, 2021), per_year=12):
    n = len(years) * per_year
    rng = np.random.default_rng(42)
    frame = pd.DataFrame({name: rng.uniform(0, 2, n) for name in predictor_columns()})
    frame['season'] = np.repeat(years, per_year)
    frame['week'] = np.tile(np.arange(1, per_year + 1), len(years))
    frame['game_type'] = 'REG'
    frame['kicker_games_before'] = frame.week - 1
    frame['kicker_has_3_prior_games'] = frame.week > 3
    frame['kicker_has_5_prior_games'] = frame.week > 5
    frame.loc[frame.week == 1, 'previous_game_xpm'] = np.nan
    frame['game_id'] = [f'{year}_{week:02d}_NYJ_BUF' for year, week in zip(frame.season, frame.week)]
    frame['team'] = 'BUF'
    frame['kicker_id'] = 'kicker_a'
    frame['xpm'] = np.tile([0, 2, 3, 4, 1, 2, 0, 3, 2, 1, 4, 2], len(years))[:n]
    frame['eligible_for_phase_4_training'] = True
    return frame


def write_parquet(path, frame):
    with duckdb.connect() as con:
        con.register('fixture', frame)
        con.execute('COPY fixture TO ? (FORMAT PARQUET)', [str(path)])
    return path


def test_load_filters_before_target_validation_and_keeps_82_predictors(tmp_path):
    module = audit_module()
    frame = historical_frame((2019, 2025, 2026))
    frame.loc[frame.season == 2026, 'xpm'] = -999
    frame.loc[frame.season == 2026, 'offense_points_per_game_before'] = np.inf
    frame.loc[0, 'eligible_for_phase_4_training'] = False
    frame.loc[0, 'xpm'] = -999
    frame['unapproved_predictor'] = 999
    result = module.load_development(write_parquet(tmp_path / 'source.parquet', frame))
    assert set(result.season) == {2019, 2025}
    assert len(result) == 23
    assert list(result.columns) == ['game_id', 'team', 'kicker_id', *predictor_columns(), 'xpm']
    assert result.loc[result.week == 1, 'previous_game_xpm'].isna().all()


@pytest.mark.parametrize('year', [2015, 2026, 2025.5, np.nan])
def test_development_rejects_forbidden_partitions(year):
    frame = historical_frame()
    frame['season'] = frame.season.astype(float)
    frame.loc[0, 'season'] = year
    with pytest.raises(ValueError, match='season'):
        audit_module().validate_development(frame)


def test_walk_forward_never_fits_evaluation_outcomes_and_is_reproducible():
    module = audit_module()
    source = historical_frame()
    actual = module.temporal_oof(source, evaluation_years=(2020, 2021))
    altered = source.copy()
    altered.loc[altered.season == 2021, 'xpm'] += 100
    other = module.temporal_oof(altered, evaluation_years=(2020, 2021))
    np.testing.assert_array_equal(actual['lambda'], other['lambda'])
    repeated = module.temporal_oof(source, evaluation_years=(2020, 2021))
    pd.testing.assert_frame_equal(actual, repeated)
    assert len(actual) == 24
    assert (actual.fold_train_max < actual.season).all()
    assert actual.fold_train_max.tolist() == [2019] * 12 + [2020] * 12
    assert actual.null_count.tolist().count(1) == 2


def test_identical_evaluation_inputs_receive_identical_forecasts():
    module = audit_module()
    source = historical_frame((2019, 2020))
    same = source.iloc[[12]].copy()
    same['game_id'] = '2020_01_OTHER'
    same['xpm'] = 50
    predictions = module.temporal_oof(pd.concat([source, same], ignore_index=True), evaluation_years=(2020,))
    assert predictions.loc[predictions.week == 1, 'lambda'].nunique() == 1


@pytest.mark.parametrize('years', [(2026,), (2020, 2020), (2022,)])
def test_temporal_folds_reject_unavailable_or_forbidden_evaluation(years):
    with pytest.raises(ValueError):
        audit_module().temporal_oof(historical_frame(), evaluation_years=years)


def test_temporal_fold_requires_strictly_earlier_training_rows():
    with pytest.raises(ValueError, match='training'):
        audit_module().temporal_oof(historical_frame((2020,)), evaluation_years=(2020,))


def test_metrics_have_proper_scores_and_observable_calibration():
    result = audit_module().metrics([0, 2, 4], [1., 2., 3.])
    assert result['count'] == 3
    assert result['predicted_mean'] == 2
    assert result['observed_mean'] == 2
    assert result['mae'] == pytest.approx(2 / 3)
    assert result['nll'] > 0
    assert result['rps'] > 0
    assert set(result['calibration']) == {'ge_2', 'ge_3', 'ge_4'}
    assert sum(b['count'] for b in result['calibration']['ge_2']['bins']) == 3
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('y,means', [([], []), ([1], [np.inf]), ([1.5], [2.]), ([1], [0])])
def test_metrics_reject_invalid_values(y, means):
    with pytest.raises(ValueError):
        audit_module().metrics(y, means)


def test_summary_strata_partition_the_same_oof_rows():
    module = audit_module()
    predictions = module.temporal_oof(historical_frame(), evaluation_years=(2020, 2021))
    summary = module.summarize_oof(predictions)
    assert summary['pooled']['count'] == 24
    for name in ('by_season', 'by_fold', 'by_week_group', 'by_week', 'by_kicker_games_before',
                 'by_has_3_games', 'by_has_5_games', 'by_null_bin'):
        assert sum(item['count'] for item in summary[name].values()) == 24
    assert summary['by_week_group']['1-4']['count'] == 8
    assert summary['by_week_group']['5-8']['count'] == 8
    assert summary['by_week_group']['9+']['count'] == 8
    assert set(summary['probability_deciles']) == {'all', '1-4', '5-8', '9+'}
    json.dumps(summary, allow_nan=False)


def test_summary_rejects_overlap_in_training_and_evaluation():
    module = audit_module()
    predictions = module.temporal_oof(historical_frame(), evaluation_years=(2020,))
    predictions['fold_train_max'] = 2020
    with pytest.raises(ValueError, match='strictly earlier'):
        module.summarize_oof(predictions)


def test_development_rejects_ineligible_rows_from_direct_callers():
    frame = historical_frame()
    frame.loc[0, 'eligible_for_phase_4_training'] = False
    with pytest.raises(ValueError, match='eligible'):
        audit_module().temporal_oof(frame, evaluation_years=(2020,))


def test_persisted_oof_is_reused_and_restores_missing_summary(tmp_path):
    module = audit_module()
    source = write_parquet(tmp_path / 'source.parquet', historical_frame())
    directory = tmp_path / 'audit'
    first, summary, metadata = module.run_audit(source, directory, evaluation_years=(2020, 2021))
    (directory / 'summary.json').unlink()
    second, repeated, reused = module.run_audit(source, directory, evaluation_years=(2020, 2021))
    pd.testing.assert_frame_equal(first, second)
    assert summary == repeated
    assert metadata == reused
    assert reused['prediction_row_count'] == 24
    assert len(reused['source_sha256']) == len(reused['prediction_sha256']) == 64
    assert json.loads((directory / 'summary.json').read_text()) == summary
