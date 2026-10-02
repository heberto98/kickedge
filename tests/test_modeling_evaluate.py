import json
import math

import numpy as np
import pytest
from scipy.stats import poisson

from kickedge.modeling.evaluate import evaluate


def test_metrics_match_analytic_single_zero_target():
    result = evaluate([0], [2], [2024])
    assert result['nll'] == pytest.approx(2)
    assert result['mae'] == 2
    assert result['rmse'] == 2
    assert result['poisson_deviance'] == 4
    assert result['brier_ge_2'] == pytest.approx((1 - 3 * math.exp(-2)) ** 2)
    assert result['brier_ge_3'] == pytest.approx((1 - 5 * math.exp(-2)) ** 2)
    assert result['brier_ge_4'] == pytest.approx((1 - (19 / 3) * math.exp(-2)) ** 2)
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('mean,target', [(1e-12, 0), (0.01, 3), (2, 0), (2, 7), (1000, 1001)])
def test_rps_matches_independent_large_cdf_sum(mean, target):
    counts = np.arange(max(2000, target + 100))
    expected = np.sum((poisson.cdf(counts, mean) - (counts >= target)) ** 2)
    assert evaluate([target], [mean], [2024])['rps'] == pytest.approx(expected, abs=1e-10)


def test_calibration_fixed_bins_and_row_order():
    result = evaluate([0, 2, 4], [0.1, 2, 4], [2024] * 3)
    assert result == evaluate([4, 2, 0], [4, 2, 0.1], [2024] * 3)
    for threshold in ('ge_2', 'ge_3', 'ge_4'):
        calibration = result['calibration'][threshold]
        assert len(calibration['bins']) == 10
        assert sum(b['count'] for b in calibration['bins']) == 3
        expected = sum(b['count'] * abs(b['predicted_mean'] - b['observed_frequency']) for b in calibration['bins'] if b['count']) / 3
        assert calibration['ece'] == pytest.approx(expected)


@pytest.mark.parametrize('seasons', [[2025], [2024, 2025], [], [2023]])
def test_evaluation_rejects_nonvalidation_years_or_lengths(seasons):
    with pytest.raises(ValueError):
        evaluate([0], [2], seasons)


@pytest.mark.parametrize('target', [[-1], [1.5], [float('nan')], [float('inf')], []])
def test_evaluation_rejects_invalid_counts(target):
    with pytest.raises(ValueError):
        evaluate(target, [2], [2024])


def test_extreme_means_remain_finite():
    result = evaluate([0, 1000000], [1e-200, 1000000], [2024, 2024])
    json.dumps(result, allow_nan=False)
