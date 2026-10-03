"""Versioned estimators cannot fit the forward holdout or accept target inputs."""
import importlib

import numpy as np
import pandas as pd
import pytest

from kickedge.modeling.dataset import predictor_columns


def api():
    return importlib.import_module('kickedge.v2.models')


def frame(config, years=(2019, 2020, 2025), size=24):
    names = api().feature_columns(config)
    rng = np.random.default_rng(8)
    result = pd.DataFrame({n: rng.uniform(.1, 3, len(years)*size) for n in names})
    result['season'] = np.repeat(years, size)
    result['week'] = np.tile(np.arange(size)+1, len(years))
    result['game_type'] = 'REG'
    result.loc[result.index % 7 == 0, 'previous_game_xpm'] = np.nan
    y = rng.poisson(2.2, len(result))
    targets = pd.DataFrame({'offensive_td': y+1, 'pat_attempts': y+1,
                           'two_pt_attempts': (result.index % 4 == 0).astype(int),
                           'xpa': y+1, 'xpm': y})
    return result, y, targets


def test_baseline_v2_permits_2025_but_v1_guard_is_unchanged():
    from kickedge.modeling.count_models import CountModel, CANDIDATES
    config = api().CANDIDATES[0]
    x, y, _ = frame(config)
    model = api().V2Model(config).fit(x, y)
    assert model.fit_seasons_ == [2019, 2020, 2025]
    assert model.features_ == predictor_columns()
    with pytest.raises(ValueError, match='2025'):
        CountModel(CANDIDATES[1]).fit(x, y, refit=True)


@pytest.mark.parametrize('candidate', range(5))
def test_candidates_finite_coherent_and_reproducible(candidate):
    config = api().CANDIDATES[candidate]
    x, y, targets = frame(config)
    a = api().V2Model(config).fit(x, y, structural_targets=targets)
    b = api().V2Model(config).fit(x, y, structural_targets=targets)
    np.testing.assert_array_equal(a.predict(x), b.predict(x))
    d = a.predict_distribution(x)
    assert (d['probabilities'] >= 0).all() and (d['tail'] >= 0).all()
    np.testing.assert_allclose(d['probabilities'].sum(axis=1)+d['tail'], 1, atol=1e-12)
    if config['family'] == 'structural':
        parts = a.predict_components(x)
        np.testing.assert_allclose(a.predict(x), parts['expected_td']*parts['pat_probability']*parts['conversion_probability'])
        assert ((parts['pat_probability'] > 0) & (parts['pat_probability'] < 1)).all()


@pytest.mark.parametrize('candidate', range(5))
def test_all_candidates_reject_2026_before_fit(candidate):
    config = api().CANDIDATES[candidate]
    x, y, labels = frame(config, (2026,))
    with pytest.raises(ValueError, match='season'):
        api().V2Model(config).fit(x, y, structural_targets=labels)


def test_predictor_boundary_rejects_target_and_future_identifiers():
    config = api().CANDIDATES[1]
    x, y, _ = frame(config)
    model = api().V2Model(config).fit(x, y)
    for name in ('xpm', 'offensive_td', 'game_id'):
        with pytest.raises(ValueError, match='predictor'):
            model.predict(x.assign(**{name: 4}))
    with pytest.raises(ValueError, match='predictor'):
        model.predict(x.loc[:, list(reversed(x.columns))])


def test_structural_targets_never_enter_predict_transform():
    config = api().CANDIDATES[-1]
    x, y, labels = frame(config)
    model = api().V2Model(config).fit(x, y, structural_targets=labels)
    frozen = model.predict(x)
    labels.loc[:, :] = 999  # original caller can mutate outcomes after fitting
    np.testing.assert_array_equal(frozen, model.predict(x))
    with pytest.raises(ValueError, match='structural'):
        api().V2Model(config).fit(x, y)


def test_oof_calibration_rejects_same_year_future_and_in_sample_rows():
    module = importlib.import_module('kickedge.v2.training')
    oof = pd.DataFrame({'season': [2020, 2021], 'fold_train_max': [2019, 2020],
                        'xpm': [2, 3], 'lambda': [2., 2.]})
    result = module.fit_lambda_calibration(oof, before_season=2022)
    assert result['factor'] == 1.25 and result['fit_max_season'] == 2021
    for mutated in (oof.assign(season=2026), oof.assign(fold_train_max=2021)):
        with pytest.raises(ValueError):
            module.fit_lambda_calibration(mutated, before_season=2022)
    with pytest.raises(ValueError):
        module.fit_lambda_calibration(oof, before_season=2021)


def test_oof_candidate_cannot_see_its_own_outcomes():
    module = importlib.import_module('kickedge.v2.training')
    config = api().CANDIDATES[0]
    x, y, labels = frame(config, (2019, 2020, 2021))
    x['xpm'] = y
    for name in ('game_id', 'team', 'kicker_id'):
        x[name] = [f'{name}_{i}' for i in range(len(x))]
    first = module.candidate_oof(x, labels, config, years=(2020, 2021))
    x.loc[x.season == 2021, 'xpm'] += 100
    labels.loc[x.season == 2021, 'xpm'] += 100
    second = module.candidate_oof(x, labels, config, years=(2020, 2021))
    np.testing.assert_array_equal(first['lambda'], second['lambda'])
    assert (first.fold_train_max < first.season).all()
