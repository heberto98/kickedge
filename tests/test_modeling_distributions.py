import math

import numpy as np
import pytest

from kickedge.modeling.distributions import line_probabilities, poisson_distribution


def test_distribution_preserves_expected_mean_and_residual_mass():
    means = np.array([0.001, 2.0, 1000.0])
    result = poisson_distribution(means, 3)
    np.testing.assert_allclose(result['expected'], means)
    np.testing.assert_allclose(result['probabilities'].sum(axis=1) + result['tail'], 1)
    assert result['probabilities'][1, 2] == pytest.approx(2 * math.exp(-2))
    assert result['tail'][2] == 1


@pytest.mark.parametrize('line,over,under,push', [
    (1.5, 1 - 3 * math.exp(-2), 3 * math.exp(-2), 0),
    (2.5, 1 - 5 * math.exp(-2), 5 * math.exp(-2), 0),
    (2, 1 - 5 * math.exp(-2), 3 * math.exp(-2), 2 * math.exp(-2)),
])
def test_exact_line_settlement(line, over, under, push):
    result = line_probabilities([2.0], line)
    for key, expected in [('over', over), ('under', under), ('push', push)]:
        assert result[key][0] == pytest.approx(expected)


@pytest.mark.parametrize('means', [[], [0], [-1], [float('nan')], [float('inf')], [[2]]])
def test_invalid_means_rejected(means):
    with pytest.raises(ValueError):
        poisson_distribution(means)


@pytest.mark.parametrize('maximum', [-1, 2.5, True])
def test_invalid_display_limit_rejected(maximum):
    with pytest.raises(ValueError):
        poisson_distribution([2], maximum)


@pytest.mark.parametrize('line', [-1, float('nan'), float('inf')])
def test_invalid_line_rejected(line):
    with pytest.raises(ValueError):
        line_probabilities([2], line)
