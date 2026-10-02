"""Validation-only probabilistic metrics; results contain JSON-native values."""

import math

import numpy as np
from scipy.special import ive, xlogy
from scipy.stats import poisson

from .distributions import _validated_means


def _average(values):
    # fsum makes metrics invariant to row ordering as well as reducing roundoff.
    return math.fsum(float(v) for v in values) / len(values)


def _poisson_rps(y, means):
    """Exact infinite-count RPS (no truncation, hence zero truncation error).

    For integer counts, sum_k (F(k)-1[y<=k])^2 equals
    E|X-y| - E|X-X'|/2. Poisson size bias gives
    E|X-y| = lambda-y+2[y F(y-1)-lambda F(y-2)].
    The independent Poisson difference is Skellam, whose mean absolute
    value is 2 lambda exp(-2 lambda)[I0(2 lambda)+I1(2 lambda)].
    ive computes the exponentially scaled Bessel terms without overflow.
    This avoids an arbitrary display cutoff and preserves all tail mass.
    """
    absolute = means - y + 2 * (y * poisson.cdf(y - 1, means) - means * poisson.cdf(y - 2, means))
    return np.maximum(0, absolute - means * (ive(0, 2 * means) + ive(1, 2 * means)))


def evaluate(y, means, seasons):
    """Evaluate only rows explicitly tagged 2024; never accept holdout years."""
    values = _validated_means(means)
    targets = np.asarray(y, dtype=float)
    years = np.asarray(seasons)
    if years.ndim != 1 or len(years) != len(values) or not np.all(years == 2024):
        raise ValueError('evaluation requires exactly one 2024 season per prediction')
    if targets.ndim != 1 or len(targets) != len(values) or not np.all(np.isfinite(targets)) or np.any(targets < 0) or np.any(targets != np.floor(targets)):
        raise ValueError('targets must be a matching vector of finite nonnegative integer counts')
    errors = targets - values
    result = {
        'nll': _average(-poisson.logpmf(targets, values)),
        'rps': _average(_poisson_rps(targets, values)),
        'mae': _average(np.abs(errors)),
        'rmse': math.sqrt(_average(errors ** 2)),
        'poisson_deviance': _average(2 * (xlogy(targets, targets) - xlogy(targets, values) - targets + values)),
        'calibration': {},
    }
    for threshold in (2, 3, 4):
        predicted = poisson.sf(threshold - 1, values)
        observed = (targets >= threshold).astype(float)
        name = f'ge_{threshold}'
        result[f'brier_{name}'] = _average((predicted - observed) ** 2)
        membership = np.minimum((predicted * 10).astype(int), 9)
        bins = []
        for index in range(10):
            mask = membership == index
            count = int(mask.sum())
            bins.append({
                'lower': index / 10, 'upper': (index + 1) / 10,
                'count': count,
                'predicted_mean': _average(predicted[mask]) if count else None,
                'observed_frequency': _average(observed[mask]) if count else None,
            })
        ece = math.fsum(b['count'] * abs(b['predicted_mean'] - b['observed_frequency']) for b in bins if b['count']) / len(values)
        result['calibration'][name] = {'bins': bins, 'ece': ece}
    return result
