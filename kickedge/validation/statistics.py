"""Frozen Phase 6 scores; bootstrap is paired IID rows, not clustered.

Shared games/teams/kickers imply dependence and potentially optimistic CIs.
Intervals omit model estimation uncertainty and bias correction. Calibration
bands are operational descriptions, not significance tests.
"""
import math
import numbers
import numpy as np
from scipy.special import xlogy
from scipy.stats import poisson
from kickedge.modeling.distributions import _validated_means
from kickedge.modeling.evaluate import _average, _poisson_rps


def _vectors(y, means):
    values = _validated_means(means)
    targets = np.asarray(y, dtype=float)
    if (targets.ndim != 1 or len(targets) != len(values) or not np.all(np.isfinite(targets))
            or np.any(targets < 0) or np.any(targets != np.floor(targets))):
        raise ValueError('targets must be a matching vector of finite nonnegative integer counts')
    return targets, values


def score_rows(y, means):
    """Per-row proper scores and errors as NumPy vectors."""
    targets, values = _vectors(y, means)
    errors = targets - values
    result = {'nll': -poisson.logpmf(targets, values), 'rps': _poisson_rps(targets, values),
              'mae': np.abs(errors), 'squared_error': errors ** 2,
              'poisson_deviance': 2 * (xlogy(targets, targets) - xlogy(targets, values) - targets + values)}
    for t in (2, 3, 4):
        result[f'brier_ge_{t}'] = (poisson.sf(t - 1, values) - (targets >= t)) ** 2
    return result


def reliability(prob, observed):
    """Ten fixed bins with Wilson observed-frequency 95% intervals."""
    predicted, actual = np.asarray(prob, dtype=float), np.asarray(observed, dtype=float)
    if (predicted.ndim != 1 or not predicted.size or actual.shape != predicted.shape
            or not np.all(np.isfinite(predicted)) or np.any((predicted < 0) | (predicted > 1))
            or not np.all((actual == 0) | (actual == 1))):
        raise ValueError('probabilities and binary observations must be matching finite nonempty vectors')
    membership = np.minimum((predicted * 10).astype(int), 9)
    bins, z = [], 1.959963984540054
    for i in range(10):
        mask = membership == i
        count = int(mask.sum())
        obs = _average(actual[mask]) if count else None
        interval = None
        if count:
            denominator = 1 + z * z / count
            center = (obs + z * z / (2 * count)) / denominator
            radius = z * math.sqrt(obs * (1 - obs) / count + z * z / (4 * count ** 2)) / denominator
            interval = [max(0.0, center - radius), min(1.0, center + radius)]
        bins.append({'lower': i / 10, 'upper': (i + 1) / 10, 'count': count,
                     'predicted_mean': _average(predicted[mask]) if count else None,
                     'observed_frequency': obs, 'observed_ci95': interval})
    ece = math.fsum(b['count'] * abs(b['predicted_mean'] - b['observed_frequency']) for b in bins if b['count']) / len(predicted)
    pred, obs = _average(predicted), _average(actual)
    return {'bins': bins, 'ece': ece, 'predicted_mean': pred, 'observed_frequency': obs,
            'bias': pred - obs, 'category': 'reasonably_calibrated' if ece <= .05 else 'slight_deviation' if ece <= .10 else 'important_deviation',
            'interpretation': 'Operational descriptive bands, not significance tests.'}


def metrics(y, means, seasons):
    targets, values = _vectors(y, means)
    years = np.asarray(seasons)
    if years.ndim != 1 or len(years) != len(values) or not np.all(years == 2025):
        raise ValueError('evaluation requires exactly one 2025 season per prediction')
    rows = score_rows(targets, values)
    result = {key: _average(row) for key, row in rows.items() if key != 'squared_error'}
    result['rmse'] = math.sqrt(_average(rows['squared_error']))
    result['calibration'] = {f'ge_{t}': reliability(poisson.sf(t - 1, values), targets >= t) for t in (2, 3, 4)}
    return result


def paired_bootstrap(y, means, baseline_means, seed=42, resamples=1000):
    """Same sampled row indices for all metrics; differences are GLM minus baseline."""
    if isinstance(resamples, bool) or not isinstance(resamples, numbers.Integral) or resamples < 1:
        raise ValueError('resamples must be a positive integer')
    if isinstance(seed, bool) or not isinstance(seed, numbers.Integral) or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    rows, baseline = score_rows(y, means), score_rows(y, baseline_means)
    selected = {name: rows[name] for name in ('nll', 'rps', 'brier_ge_2', 'brier_ge_3', 'brier_ge_4')}
    selected.update({f'delta_{name}': rows[name] - baseline[name] for name in ('nll', 'rps')})
    sampled = {name: [] for name in selected}
    rng = np.random.default_rng(seed)
    for _ in range(resamples):
        indices = rng.integers(0, len(rows['nll']), size=len(rows['nll']))
        for name, row in selected.items():
            sampled[name].append(_average(row[indices]))
    estimates = {}
    for name, row in selected.items():
        lower, upper = np.percentile(sampled[name], [2.5, 97.5])
        estimates[name] = {'point': _average(row), 'lower': float(lower), 'upper': float(upper)}
    return {'method': 'paired IID row bootstrap, percentile', 'seed': int(seed), 'resamples': int(resamples),
            'confidence_level': .95, 'estimates': estimates,
            'limitations': 'Shared games, teams and kickers imply dependence; row intervals may be optimistic. No model estimation uncertainty or bias correction.'}


def distribution_summary(y, means):
    targets, values = _vectors(y, means)
    bins = []
    for count in range(6):
        pred = poisson.pmf(count, values) if count < 5 else poisson.sf(4, values)
        obs = targets == count if count < 5 else targets >= 5
        bins.append({'label': str(count) if count < 5 else '5+', 'predicted_probability': _average(pred),
                     'observed_frequency': _average(obs), 'observed_count': int(obs.sum()),
                     'expected_count': math.fsum(float(p) for p in pred)})
    return {'predicted_mean': _average(values), 'observed_mean': _average(targets), 'bins': bins}


def prop_summary(y, means):
    targets, values = _vectors(y, means)
    result = {}
    for line in (1.5, 2.5, 3.5):
        over = poisson.sf(math.floor(line), values)
        for side, pred, obs in (('over', over, targets > line), ('under', 1 - over, targets < line)):
            rel = reliability(pred, obs)
            result[f'{side}_{line}'] = {'predicted_mean': rel['predicted_mean'], 'observed_frequency': rel['observed_frequency'],
                                      'brier': _average((pred - obs) ** 2), 'reliability': rel}
    return result
