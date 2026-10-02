"""Stable Poisson probabilities with an explicit undisplayed residual tail."""

import numbers

import numpy as np
from scipy.stats import poisson


def _validated_means(means):
    values = np.asarray(means, dtype=float)
    if values.ndim != 1 or not values.size or not np.all(np.isfinite(values)) or np.any(values <= 0):
        raise ValueError('means must be a nonempty vector of finite strictly positive values')
    return values


def poisson_distribution(means, max_display=12):
    """Return displayed masses, residual P(X > max_display), and full E[X]."""
    values = _validated_means(means)
    if isinstance(max_display, bool) or not isinstance(max_display, numbers.Integral) or max_display < 0:
        raise ValueError('max_display must be a nonnegative integer')
    return {
        'probabilities': poisson.pmf(np.arange(max_display + 1)[None, :], values[:, None]),
        'tail': poisson.sf(max_display, values),
        'expected': values.copy(),
    }


def line_probabilities(means, line):
    """Exact strict over/under and equality settlement for any nonnegative line."""
    values = _validated_means(means)
    if not isinstance(line, numbers.Real) or not np.isfinite(line) or line < 0:
        raise ValueError('line must be a finite nonnegative number')
    integer = float(line).is_integer()
    cutoff = np.floor(line)
    return {
        'over': poisson.sf(cutoff, values),
        'under': poisson.cdf(cutoff - int(integer), values),
        'push': poisson.pmf(cutoff, values) if integer else np.zeros_like(values),
    }
