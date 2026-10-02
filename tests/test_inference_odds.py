import json
import math

import pytest

from kickedge.inference.odds import (
    analyze_prop, fair_odds, implied_probability, no_vig, profit_per_unit, validate_odds,
)


@pytest.mark.parametrize('value', [True, False, '110', 0, 99, -99, math.inf, math.nan, None])
def test_invalid_prices(value):
    with pytest.raises(ValueError):
        validate_odds(value)


def test_american_arithmetic_and_normalization():
    assert implied_probability(150) == pytest.approx(.4)
    assert implied_probability(-150) == pytest.approx(.6)
    assert profit_per_unit(150) == 1.5
    assert profit_per_unit(-200) == .5
    assert fair_odds(.4)['american'] == pytest.approx(150)
    assert fair_odds(.6)['american'] == pytest.approx(-150)
    assert fair_odds(.5)['american'] == -100
    pair = no_vig(-110, -110)
    assert pair['over'] == pair['under'] == .5
    assert pair['overround'] == pytest.approx(1 / 21)
    assert no_vig(150, 150)['overround'] == pytest.approx(-.2)


@pytest.mark.parametrize('p', [0, 1, 5e-324])
def test_fair_price_endpoints_and_overflow_are_json_safe(p):
    result = fair_odds(p)
    assert result['american'] is None
    assert result['reason']
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('p', [True, '0.5', -0.1, 1.1, math.inf, math.nan])
def test_invalid_fair_probability(p):
    with pytest.raises(ValueError):
        fair_odds(p)


@pytest.mark.parametrize('line', [-1, .25, True, math.inf, math.nan, '1.5'])
def test_invalid_lines(line):
    with pytest.raises(ValueError):
        analyze_prop(2, line, 'over', -110)


@pytest.mark.parametrize('side', ['Over', 'UNDER', '', None])
def test_invalid_side(side):
    with pytest.raises(ValueError):
        analyze_prop(2, 1.5, side, -110)


@pytest.mark.parametrize('line', [1, 1.5])
@pytest.mark.parametrize('side', ['over', 'under'])
@pytest.mark.parametrize('price', [-150, 150])
def test_settlement_and_ev(line, side, price):
    result = analyze_prop(2, line, side, price)
    a = result['prop']
    p0, p1 = math.exp(-2), 2 * math.exp(-2)
    under = p0 if line == 1 else p0 + p1
    push = p1 if line == 1 else 0
    over = 1 - under - push
    win, loss = (over, under) if side == 'over' else (under, over)
    assert a['p_over'] == pytest.approx(over)
    assert a['p_under'] == pytest.approx(under)
    assert a['p_push'] == pytest.approx(push)
    assert over + under + push == pytest.approx(1)
    assert a['model_side_probability'] == pytest.approx(win)
    assert a['p_loss'] == pytest.approx(loss)
    assert a['model_probability_conditional'] == pytest.approx(win / (win + loss))
    assert a['model_probability_conditional'] == pytest.approx(win / (win + loss))
    assert a['price_probability_basis'] == ('conditional on no push' if line == 1 else 'direct')
    assert result['analysis']['expected_value_per_unit'] == pytest.approx(win * profit_per_unit(price) - loss)
    json.dumps(result, allow_nan=False)


def test_pair_prices_must_be_complete_and_consistent():
    for kwargs in ({'over_odds': -110}, {'under_odds': -110}, {'over_odds': 120, 'under_odds': -110}):
        with pytest.raises(ValueError):
            analyze_prop(2, 1, 'over', -110, **kwargs)
    result = analyze_prop(2, 1, 'under', 120, over_odds=-130, under_odds=120)
    a, m = result['prop'], result['market']
    assert sum(m['no_vig_probabilities'].values()) == pytest.approx(1)
    assert result['analysis']['edge_novig_pp'] == pytest.approx(100 * (a['model_probability_conditional'] - m['no_vig_probabilities']['under']))


@pytest.mark.parametrize('mean', [True, '2', 0, -1, math.inf, math.nan])
def test_invalid_mean(mean):
    with pytest.raises(ValueError):
        analyze_prop(mean, 1, 'over', -110)


def test_underflowed_no_push_mass_fails_with_readable_error():
    with pytest.raises(ValueError, match='no-push'):
        analyze_prop(1e-320, 0, 'over', 100)
