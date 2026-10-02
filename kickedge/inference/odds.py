"""Strict American-price arithmetic and Poisson prop settlement, without fitting."""

import math

from kickedge.modeling.distributions import line_probabilities


def _number(value, name):
    if type(value) not in (int, float):
        raise ValueError(f'{name} must be a finite numeric int or float')
    try:
        value = float(value)
    except OverflowError as exc:
        raise ValueError(f'{name} must be finite') from exc
    if not math.isfinite(value):
        raise ValueError(f'{name} must be finite')
    return value


def validate_odds(odds):
    """Accept conventional finite American odds with magnitude at least 100."""
    value = _number(odds, 'odds')
    if abs(value) < 100:
        raise ValueError('American odds must have absolute value >= 100')
    return value


def implied_probability(odds):
    value = validate_odds(odds)
    return 100 / (100 + value) if value > 0 else 1 / (1 + 100 / -value)


def profit_per_unit(odds):
    value = validate_odds(odds)
    return value / 100 if value > 0 else 100 / -value


def no_vig(over_odds, under_odds):
    """Normalize a paired quote and preserve negative overrounds."""
    over, under = implied_probability(over_odds), implied_probability(under_odds)
    total = over + under
    return {'over': over / total, 'under': under / total, 'overround': total - 1}


def fair_odds(probability):
    """Price a no-push probability; endpoints and overflow have no finite price."""
    p = _number(probability, 'probability')
    if not 0 <= p <= 1:
        raise ValueError('probability must be between 0 and 1')
    if p in (0, 1):
        return {'american': None, 'reason': f'probability {int(p)} has no finite American price'}
    price = -100 * (p / (1 - p)) if p >= .5 else 100 * ((1 - p) / p)
    if not math.isfinite(price):
        return {'american': None, 'reason': 'American price exceeds finite numeric range'}
    return {'american': price, 'reason': None}


def analyze_prop(mean, line, side, odds, over_odds=None, under_odds=None,
                 source=None, timestamp=None):
    """Compare a quote using no-push probabilities; settle EV unconditionally."""
    mean = _number(mean, 'mean')
    if mean <= 0:
        raise ValueError('mean must be strictly positive')
    line = _number(line, 'line')
    if line < 0 or not (line % 1 in (0, .5)):
        raise ValueError('line must be nonnegative and integer or half-integer')
    if side not in ('over', 'under'):
        raise ValueError('side must be exactly over or under')
    odds = validate_odds(odds)
    if (over_odds is None) != (under_odds is None):
        raise ValueError('over_odds and under_odds must be supplied together')
    pair = None
    if over_odds is not None:
        over_odds, under_odds = validate_odds(over_odds), validate_odds(under_odds)
        if odds != (over_odds if side == 'over' else under_odds):
            raise ValueError('requested odds must match the selected side of the paired quote')
        pair = no_vig(over_odds, under_odds)
    probabilities = line_probabilities([mean], line)
    over, under, push = (float(probabilities[key][0]) for key in ('over', 'under', 'push'))
    if (not all(math.isfinite(p) and 0 <= p <= 1 for p in (over, under, push))
            or not math.isclose(over + under + push, 1., abs_tol=1e-12)):
        raise ValueError('Invalid prop settlement probabilities')
    win, loss = (over, under) if side == 'over' else (under, over)
    if not math.isfinite(win + loss) or win + loss <= 0:
        raise ValueError('Numerically unresolved no-push probability mass')
    conditional = win / (win + loss)
    comparison = conditional if line.is_integer() else win
    implied = implied_probability(odds)
    no_vig_probability = pair[side] if pair else None
    return {
        'prop': {'line': line, 'side': side, 'p_over': over, 'p_under': under,
                 'p_push': push, 'model_side_probability': win, 'p_loss': loss,
                 'model_probability_conditional': conditional,
                 'price_probability_basis': 'conditional on no push' if line.is_integer() else 'direct'},
        'market': {'american_odds': odds, 'implied_probability': implied,
                   'over_odds': over_odds, 'under_odds': under_odds,
                   'no_vig_probability': no_vig_probability,
                   'no_vig_probabilities': {'over': pair['over'], 'under': pair['under']} if pair else None,
                   'overround': pair['overround'] if pair else None,
                   'source': source, 'timestamp': timestamp},
        'analysis': {'edge_raw_pp': 100 * (comparison - implied),
                     'edge_novig_pp': 100 * (comparison - no_vig_probability) if pair else None,
                     'fair_odds': fair_odds(comparison),
                     'expected_value_per_unit': win * profit_per_unit(odds) - loss},
    }
