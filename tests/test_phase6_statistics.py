import json

import numpy as np
import pytest
from scipy.stats import poisson

from kickedge.modeling.evaluate import evaluate
from kickedge.validation.statistics import (
    distribution_summary, metrics, paired_bootstrap, prop_summary, reliability, score_rows,
)


def test_phase5_equivalence_on_synthetic_vectors():
    y, means = [0, 1, 2, 4, 9], [0.01, 1, 2.4, 3.8, 6]
    old = evaluate(y, means, [2024] * 5)
    new = metrics(y, means, [2025] * 5)
    for key in old:
        if key != 'calibration':
            assert new[key] == old[key]
    for key, calibration in old['calibration'].items():
        assert new['calibration'][key]['ece'] == calibration['ece']
        for old_bin, new_bin in zip(calibration['bins'], new['calibration'][key]['bins']):
            assert all(new_bin[k] == v for k, v in old_bin.items())


def test_bootstrap_reproducible_identity_and_single_row():
    a = paired_bootstrap([0, 2, 6], [1, 2, 4], [1, 2, 4], resamples=100)
    assert a == paired_bootstrap([0, 2, 6], [1, 2, 4], [1, 2, 4], resamples=100)
    assert a['estimates']['delta_nll'] == {'point': 0.0, 'lower': 0.0, 'upper': 0.0}
    assert a['estimates']['delta_rps'] == {'point': 0.0, 'lower': 0.0, 'upper': 0.0}
    one = paired_bootstrap([0], [2], [1], resamples=10)
    assert one['estimates']['nll'] == {'point': 2.0, 'lower': 2.0, 'upper': 2.0}
    assert one['estimates']['delta_nll'] == {'point': 1.0, 'lower': 1.0, 'upper': 1.0}
    json.dumps(a, allow_nan=False)


def test_bootstrap_uses_identical_paired_indices_for_every_metric():
    y, means, base = [0, 3, 7], [1, 2, 4], [2, 2, 2]
    result = paired_bootstrap(y, means, base, seed=7, resamples=20)
    rows, baseline = score_rows(y, means), score_rows(y, base)
    rng = np.random.default_rng(7)
    indices = [rng.integers(0, 3, size=3) for _ in range(20)]
    for name, interval in result['estimates'].items():
        values = rows[name] if not name.startswith('delta_') else rows[name[6:]] - baseline[name[6:]]
        expected = np.percentile([np.mean(values[i]) for i in indices], [2.5, 97.5])
        assert [interval['lower'], interval['upper']] == pytest.approx(expected)


@pytest.mark.parametrize('kwargs', [{'resamples': 0}, {'resamples': True}, {'resamples': 1.5}, {'seed': -1}, {'seed': True}])
def test_invalid_bootstrap_settings(kwargs):
    with pytest.raises(ValueError):
        paired_bootstrap([0], [2], [2], **kwargs)


@pytest.mark.parametrize('y,means', [([], []), ([-1], [2]), ([1.5], [2]), ([np.nan], [2]), ([0], [0]), ([0], [np.inf]), ([0, 1], [2]), ([[0]], [2])])
def test_invalid_vectors(y, means):
    with pytest.raises(ValueError):
        score_rows(y, means)


@pytest.mark.parametrize('years', [[2024], [], [2025, 2025], [[2025]], [np.nan]])
def test_invalid_years(years):
    with pytest.raises(ValueError):
        metrics([0], [2], years)


def test_distribution_mass_tails_and_props():
    result = distribution_summary([0, 5], [2, 3])
    assert sum(b['predicted_probability'] for b in result['bins']) == pytest.approx(1)
    assert sum(b['observed_count'] for b in result['bins']) == 2
    assert result['bins'][-1]['predicted_probability'] == pytest.approx(np.mean(poisson.sf(4, [2, 3])))
    props = prop_summary([0, 5], [2, 3])
    for line in (1.5, 2.5, 3.5):
        over, under = props[f'over_{line}'], props[f'under_{line}']
        assert over['predicted_mean'] + under['predicted_mean'] == pytest.approx(1)
        assert over['observed_frequency'] == 0.5
        assert over['brier'] == pytest.approx(under['brier'])


def test_reliability_fixed_bins_wilson_and_operational_bands():
    result = reliability([0, 1], [0, 1])
    assert len(result['bins']) == 10
    assert result['bins'][0]['count'] == result['bins'][9]['count'] == 1
    assert result['bins'][0]['observed_ci95'][0] == pytest.approx(0)
    assert result['bins'][9]['observed_ci95'][1] == pytest.approx(1)
    assert result['category'] == 'reasonably_calibrated'
    assert reliability([0.1], [0])['category'] == 'slight_deviation'
    assert reliability([0.2], [0])['category'] == 'important_deviation'
    for p, o in [([], []), ([1.1], [0]), ([np.nan], [0]), ([0.1], [0.2])]:
        with pytest.raises(ValueError):
            reliability(p, o)
