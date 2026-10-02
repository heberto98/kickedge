import joblib
import numpy as np
import pandas as pd
import pytest

from kickedge.modeling.count_models import CANDIDATES, CountModel
from kickedge.modeling.dataset import predictor_columns


def frame(n=60):
    rng = np.random.default_rng(19)
    x = pd.DataFrame({c: rng.uniform(0, 2, n) for c in predictor_columns() if c != 'game_type'})
    x['game_type'] = ['REG'] * n
    x['season'] = 2023
    x.loc[::7, 'previous_game_xpm'] = np.nan
    y = rng.poisson(1 + x['offense_points_per_game_before'])
    return x[predictor_columns()], y


@pytest.mark.parametrize('config', CANDIDATES, ids=lambda c: c['name'])
def test_models_distribution_order_reproducibility_and_roundtrip(config, tmp_path):
    x, y = frame()
    model = CountModel(config).fit(x, y)
    means = model.predict(x)
    assert np.isfinite(means).all() and (means > 0).all()
    np.testing.assert_allclose(model.predict(x.iloc[::-1]), means[::-1], atol=1e-12)
    np.testing.assert_allclose(CountModel(config).fit(x, y).predict(x), means, atol=1e-12)
    d = model.predict_distribution(x)
    np.testing.assert_allclose(d['probabilities'].sum(axis=1) + d['tail'], 1)
    path = tmp_path / 'model.joblib'
    joblib.dump(model, path)
    np.testing.assert_array_equal(joblib.load(path).predict(x), means)


def test_baseline_is_train_mean_and_requires_fit():
    x, y = frame()
    model = CountModel(CANDIDATES[0])
    with pytest.raises(ValueError):
        model.predict(x)
    model.fit(x, y)
    np.testing.assert_allclose(model.predict(x), y.mean())


@pytest.mark.parametrize('year', [2015, 2024, 2025])
def test_selection_fit_rejects_nontraining_years(year):
    x, y = frame()
    x.loc[0, 'season'] = year
    with pytest.raises(ValueError, match='season'):
        CountModel(CANDIDATES[1]).fit(x, y)


def test_refit_accepts_2024_but_rejects_2025():
    x, y = frame()
    x['season'] = 2024
    CountModel(CANDIDATES[0]).fit(x, y, refit=True)
    x['season'] = 2025
    with pytest.raises(ValueError, match='season'):
        CountModel(CANDIDATES[0]).fit(x, y, refit=True)


def test_model_validates_predictor_columns_and_target():
    x, y = frame()
    for bad in [x.assign(xpm=y), x.drop(columns='week')]:
        with pytest.raises(ValueError):
            CountModel(CANDIDATES[0]).fit(bad, y)
    for bad in [np.full(len(y), -1), np.full(len(y), 1.1), np.full(len(y), np.nan)]:
        with pytest.raises(ValueError):
            CountModel(CANDIDATES[0]).fit(x, bad)


def test_glm_can_learn_offensive_context_without_forcing_direction():
    x, _ = frame(180)
    # Controlled synthetic relationship verifies expressive capacity, not a real causal claim.
    x['offense_points_per_game_before'] = np.tile([0., 1., 2.], 60)
    y = (x['offense_points_per_game_before'] * 2).to_numpy()
    model = CountModel(CANDIDATES[1]).fit(x, y)
    paired = pd.concat([x.iloc[[0]], x.iloc[[0]]], ignore_index=True)
    paired['offense_points_per_game_before'] = [0., 2.]
    assert model.predict(paired)[1] > model.predict(paired)[0]
