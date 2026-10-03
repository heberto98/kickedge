"""Final polish: decimal odds as the primary price format and multiple selections.
The model, the 82 features and every settlement probability stay unchanged."""
from functools import partial
import json
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kickedge.current.engine import analyze_current_prop
from kickedge.current.multi import INDEPENDENCE, PUSH, SAME_GAME, combine
from kickedge.current.snapshot import KickerTeamUnresolved, resolve_kicker_team
from kickedge.inference.engine import analyze
from kickedge.inference.odds import (analyze_prop, american_to_decimal, decimal_implied_probability,
                                     decimal_no_vig, decimal_profit_per_unit, fair_decimal_odds,
                                     validate_decimal_odds)
from kickedge.web import app as web
from kickedge.web.artifact import ensure_model
from polish_data import ELLIOTT, FORMER, MEVIS, NOW, make_bundle, no_context

FIXTURE = json.loads(Path('examples/inference_demo_2024.json').read_text())


# ---------- decimal price arithmetic ----------

@pytest.mark.parametrize('odds,p', [(2.0, .5), (1.5, 2/3), (1.91, 1/1.91), (2.5, .4)])
def test_decimal_implied_probability(odds, p):
    assert decimal_implied_probability(odds) == pytest.approx(p, abs=1e-15)
    assert round(100*decimal_implied_probability(1.91), 4) == 52.356


@pytest.mark.parametrize('odds,profit', [(1.5, .5), (2.25, 1.25), (2, 1.0)])
def test_decimal_profit(odds, profit):
    assert decimal_profit_per_unit(odds) == pytest.approx(profit)


@pytest.mark.parametrize('p,price', [(.5, 2.0), (.4, 2.5), (.8, 1.25), (1, 1.0)])
def test_fair_decimal_odds(p, price):
    assert fair_decimal_odds(p) == {'decimal': pytest.approx(price), 'reason': None}
    assert fair_decimal_odds(0)['decimal'] is None


@pytest.mark.parametrize('bad', [1, 1.0, 0, -2, float('nan'), float('inf'), True, '2.0', None])
def test_invalid_decimal_odds(bad):
    with pytest.raises(ValueError):
        validate_decimal_odds(bad)


@pytest.mark.parametrize('american,decimal', [(100, 2.0), (150, 2.5), (-110, 1 + 100/110), (-200, 1.5), (119, 2.19)])
def test_legacy_american_to_decimal(american, decimal):
    assert american_to_decimal(american) == pytest.approx(decimal)


def test_decimal_no_vig_and_overround():
    pair = decimal_no_vig(1.91, 1.91)
    assert pair['over'] == pytest.approx(.5) and pair['overround'] == pytest.approx(2/1.91 - 1)
    pair = decimal_no_vig(2.5, 1.5)
    q = (1/2.5, 1/1.5)
    assert pair['over'] == pytest.approx(q[0]/sum(q)) and pair['overround'] == pytest.approx(sum(q) - 1)


@pytest.mark.parametrize('line,side', [(1.5, 'over'), (2, 'under'), (2.5, 'under'), (0, 'over')])
def test_decimal_settlement_matches_american_and_prices_correctly(line, side):
    american, decimal = analyze_prop(2.2, line, side, 119), analyze_prop(2.2, line, side, 2.19, odds_format='decimal')
    assert decimal['prop'] == american['prop']  # settlement never depends on the price format
    p = decimal['prop']
    win, loss = p['model_side_probability'], p['p_loss']
    comparable = win/(win+loss) if float(line).is_integer() else win
    assert decimal['market']['odds_format'] == 'decimal' and decimal['market']['decimal_odds'] == 2.19
    assert decimal['market']['implied_probability'] == pytest.approx(1/2.19)
    assert decimal['analysis']['edge_raw_pp'] == pytest.approx(100*(comparable - 1/2.19))
    assert decimal['analysis']['fair_odds']['decimal'] == pytest.approx(1/comparable)
    assert decimal['analysis']['expected_value_per_unit'] == pytest.approx(win*1.19 - loss)
    assert 'american_odds' not in decimal['market'] and 'odds_format' not in american['market']


def test_decimal_pair_must_match_selected_side_and_format():
    with pytest.raises(ValueError, match='selected side'):
        analyze_prop(2.2, 1.5, 'over', 1.8, 1.9, 1.9, odds_format='decimal')
    with pytest.raises(ValueError, match='together'):
        analyze_prop(2.2, 1.5, 'over', 1.8, 1.8, None, odds_format='decimal')
    with pytest.raises(ValueError, match='odds_format'):
        analyze_prop(2.2, 1.5, 'over', 1.8, odds_format='fractional')


def test_frozen_fixture_identical_in_both_formats():
    ensure_model(Path('.'))
    legacy, decimal = analyze(FIXTURE, 2.5, 'over', 119), analyze(FIXTURE, 2.5, 'over', 2.19, odds_format='decimal')
    assert legacy['prediction']['expected_xpm'] == decimal['prediction']['expected_xpm'] == 1.774292350651335
    assert legacy['prop']['p_over'] == decimal['prop']['p_over'] == 0.2625051047104534
    assert decimal['prediction'] == legacy['prediction'] and decimal['prop'] == legacy['prop']
    assert decimal['prediction']['distribution']['tail_probability'] == 5.379582350402028e-08


# ---------- team derived from the kicker ----------

def test_kicker_team_is_derived_never_asked_twice():
    bundle = make_bundle()
    assert resolve_kicker_team(bundle, 'harrison mevis', '2026_05_LA_PHI', now=NOW) == ('LA', 'PHI')
    assert resolve_kicker_team(bundle, ELLIOTT, '2026_05_LA_PHI', now=NOW) == ('PHI', 'LA')
    with pytest.raises(KickerTeamUnresolved) as err:  # no 2026 roster entry and no 2026 games
        resolve_kicker_team(bundle, FORMER, '2026_05_LA_PHI', now=NOW)
    assert err.value.teams == ['LA', 'PHI']


# ---------- combined summary ----------

def leg(game_id, decimal, p_win, line=1.5, p_push=0.0):
    return {'game': {'game_id': game_id}, 'market': {'odds_format': 'decimal', 'decimal_odds': decimal},
            'prop': {'model_side_probability': p_win, 'p_push': p_push, 'line': line}}


def test_combine_two_and_three_legs():
    c = combine([leg('g1', 1.5, .7), leg('g2', 1.4, .8)])
    assert c['combined_decimal_odds'] == pytest.approx(2.1) and c['implied_probability'] == pytest.approx(1/2.1)
    assert round(100*c['implied_probability'], 2) == 47.62
    assert c['model_probability'] == pytest.approx(.56) and c['difference_pp'] == pytest.approx(100*(.56 - 1/2.1))
    assert c['warnings'] == [INDEPENDENCE] and not c['same_game_correlation_warning'] and c['no_loss_probability'] is None
    c = combine([leg('g1', 1.35, .782), leg('g2', 1.4, .75), leg('g3', 1.5, .8)])
    assert c['selection_count'] == 3 and c['combined_decimal_odds'] == pytest.approx(1.35*1.4*1.5)
    assert c['model_probability'] == pytest.approx(.782*.75*.8)


def test_same_game_and_push_warnings():
    c = combine([leg('2026_05_LA_PHI', 1.3, .8), leg('2026_05_LA_PHI', 1.4, .7), leg('g3', 2.0, .5, line=2, p_push=.2)])
    assert c['same_game_correlation_warning'] and c['same_game_ids'] == ['2026_05_LA_PHI']
    assert c['warnings'] == [INDEPENDENCE, SAME_GAME, PUSH] and c['push_possible']
    assert c['model_probability'] == pytest.approx(.8*.7*.5)                 # all legs win outright
    assert c['no_loss_probability'] == pytest.approx(.8*.7*(.5+.2))          # win or push on every leg


def test_combine_limits():
    with pytest.raises(ValueError):
        combine([leg('g1', 1.5, .7)])
    with pytest.raises(ValueError):
        combine([leg('g', 1.5, .7)]*11)


# ---------- web API ----------

@pytest.fixture
def client(monkeypatch, tmp_path):
    calls = {'loads': 0, 'contexts': 0}

    def loader(*args, **kwargs):
        calls['loads'] += 1
        return make_bundle()

    def counted_context(*args, **kwargs):
        calls['contexts'] += 1
        return no_context()
    monkeypatch.setattr(web, 'load_current_sources', loader)
    monkeypatch.setattr(web, 'collect_context', counted_context)
    monkeypatch.setattr(web, '_now', lambda: NOW)
    monkeypatch.setattr(web, 'ANALYSES_DIR', tmp_path)
    monkeypatch.setattr(web, 'analyze_current_prop', partial(analyze_current_prop, clock=lambda: NOW,
                                                             context_collector=no_context, output_dir=tmp_path))
    web._recent.clear()
    c = TestClient(web.app)
    c.calls = calls
    return c


SINGLE = {'kicker': MEVIS, 'game_id': '2026_05_LA_PHI', 'line': 1.5, 'side': 'over', 'decimal_odds': 1.3}


def test_single_decimal_derives_team_and_prices_in_decimal(client):
    r = client.post('/api/analyze', json=SINGLE)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body['game']['team'], body['game']['opponent']) == ('LA', 'PHI')
    m, a, p = body['market'], body['analysis'], body['prop']
    assert m['odds_format'] == 'decimal' and m['decimal_odds'] == 1.3 and m['implied_probability'] == pytest.approx(1/1.3)
    assert a['fair_odds']['decimal'] == pytest.approx(1/p['model_side_probability'])
    assert a['edge_raw_pp'] == pytest.approx(100*(p['model_side_probability'] - 1/1.3))
    legacy = client.post('/api/analyze', json=SINGLE | {'decimal_odds': None, 'odds': -333, 'team': 'LA', 'opponent': 'PHI'}).json()
    assert legacy['prediction'] == body['prediction'] and legacy['prop'] == body['prop']  # format never moves the model


def test_single_typed_kicker_without_resolvable_team_asks_once(client):
    r = client.post('/api/analyze', json=SINGLE | {'kicker': 'Former Kicker'})
    assert r.status_code == 422 and r.json()['error']['code'] == 'KICKER_TEAM_UNRESOLVED'
    assert [t['nickname'] for t in r.json()['error']['teams']] == ['Rams', 'Eagles']
    r = client.post('/api/analyze', json=SINGLE | {'kicker': 'Former Kicker', 'team': 'LA', 'opponent': 'PHI'})
    assert r.status_code == 200 and r.json()['data_quality']['kicker_current_team_verified'] is False


@pytest.mark.parametrize('change', [{'decimal_odds': 1}, {'decimal_odds': 0}, {'decimal_odds': -2},
                                    {'decimal_odds': '1.9'}, {'decimal_odds': None},
                                    {'odds': 119}, {'over_decimal_odds': 1.3},
                                    {'over_decimal_odds': 1.4, 'under_decimal_odds': 3.0}])
def test_invalid_decimal_requests(client, change):
    r = client.post('/api/analyze', json=SINGLE | change)
    assert r.status_code == 422 and r.json()['error']['code'] == 'INVALID_ODDS'


def test_nan_and_infinite_odds_rejected(client):
    for token in (b'NaN', b'Infinity'):
        raw = b'{"kicker":"' + MEVIS.encode() + b'","game_id":"2026_05_LA_PHI","line":1.5,"side":"over","decimal_odds":' + token + b'}'
        r = client.post('/api/analyze', content=raw, headers={'content-type': 'application/json'})
        assert r.status_code == 422 and r.json()['error']['code'] == 'INVALID_ODDS'


def selection(kicker, game_id, odds, line=1.5, side='over'):
    return {'kicker': kicker, 'game_id': game_id, 'line': line, 'side': side, 'decimal_odds': odds}


def test_multi_legs_equal_single_and_combine_once(client):
    single = client.post('/api/analyze', json=SINGLE).json()
    r = client.post('/api/analyze-multi', json={'selections': [
        selection(MEVIS, '2026_05_LA_PHI', 1.3), selection(ELLIOTT, '2026_06_PHI_DET', 1.4),
        selection('Jake Elliott', '2026_05_LA_PHI', 1.5, line=2.5, side='under')]})
    assert r.status_code == 200, r.text
    body = r.json()
    legs = body['selections']
    assert [l['status'] for l in legs] == ['ok']*3 and [l['index'] for l in legs] == [1, 2, 3]
    first = legs[0]['result']
    assert first['prediction'] == single['prediction'] and first['prop'] == single['prop'] and first['features'] == single['features']
    assert first['market'] == single['market'] and first['analysis'] == single['analysis']
    assert legs[1]['result']['game']['team'] == 'PHI'
    c = body['combined']
    assert c['combined_decimal_odds'] == pytest.approx(1.3*1.4*1.5) and c['implied_probability'] == pytest.approx(1/(1.3*1.4*1.5))
    assert c['model_probability'] == pytest.approx(math.prod(l['result']['prop']['model_side_probability'] for l in legs))
    assert c['same_game_correlation_warning'] and c['same_game_ids'] == ['2026_05_LA_PHI']
    assert client.calls['loads'] == 2   # one load for the single request, one for the whole multi request
    assert client.calls['contexts'] == 2  # weather context looked up once per game, not per leg


def test_multi_different_games_label_independence_only(client):
    body = client.post('/api/analyze-multi', json={'selections': [
        selection(MEVIS, '2026_05_LA_PHI', 1.3), selection(ELLIOTT, '2026_06_PHI_DET', 1.4)]}).json()
    assert not body['combined']['same_game_correlation_warning'] and body['combined']['warnings'] == [INDEPENDENCE]


def test_multi_integer_line_push_warning(client):
    body = client.post('/api/analyze-multi', json={'selections': [
        selection(MEVIS, '2026_05_LA_PHI', 2.1, line=2), selection(ELLIOTT, '2026_06_PHI_DET', 1.4)]}).json()
    c = body['combined']
    assert PUSH in c['warnings'] and c['no_loss_probability'] > c['model_probability']


def test_multi_invalid_leg_blocks_combined(client):
    body = client.post('/api/analyze-multi', json={'selections': [
        selection(MEVIS, '2026_05_LA_PHI', 1.3), selection('Nobody Here', '2026_06_PHI_DET', 1.4),
        selection(ELLIOTT, '2026_06_PHI_DET', 1.4)]}).json()
    assert body['combined'] is None and body['combined_available'] is False and 'stored' not in body
    assert [l['status'] for l in body['selections']] == ['ok', 'error', 'ok']
    assert body['selections'][1]['error']['code'] == 'KICKER_NOT_FOUND'


@pytest.mark.parametrize('count,status', [(1, 422), (2, 200), (10, 200), (11, 422)])
def test_multi_selection_count_limits(client, count, status):
    games = ['2026_05_LA_PHI', '2026_07_LA_JAX', '2026_08_PHI_LA']
    legs = [selection(MEVIS, games[i % 3], 1.2 + i/100, line=0.5 + i % 3) for i in range(count)]
    r = client.post('/api/analyze-multi', json={'selections': legs})
    assert r.status_code == status, r.text
    if status == 200:
        assert r.json()['combined']['selection_count'] == count


@pytest.mark.parametrize('change', [{'decimal_odds': 1}, {'decimal_odds': '1.5'}, {'odds': 119}, {'extra': 1}])
def test_multi_rejects_invalid_legs_before_running(client, change):
    legs = [selection(MEVIS, '2026_05_LA_PHI', 1.3), selection(ELLIOTT, '2026_06_PHI_DET', 1.4) | change]
    r = client.post('/api/analyze-multi', json={'selections': legs})
    assert r.status_code == 422 and 'selections.1' in r.json()['error']['message']


def test_multi_is_stored_listed_and_reopened_without_rerun(client, monkeypatch):
    body = client.post('/api/analyze-multi', json={'selections': [
        selection(MEVIS, '2026_05_LA_PHI', 1.3), selection(ELLIOTT, '2026_06_PHI_DET', 1.4)]}).json()
    stored_id = body['stored']['id']
    client.post('/api/analyze', json=SINGLE)
    listing = client.get('/api/analyses').json()['analyses']
    kinds = {a['kind']: a for a in listing}
    assert set(kinds) == {'single', 'multi'}
    assert kinds['multi']['id'] == stored_id and kinds['multi']['selection_count'] == 2
    assert kinds['multi']['combined_decimal_odds'] == pytest.approx(1.3*1.4)
    assert kinds['single']['odds_format'] == 'decimal' and kinds['single']['decimal_odds'] == 1.3

    def forbidden(*a, **k):
        raise AssertionError('stored analyses are never re-run')
    monkeypatch.setattr(web, 'analyze_current_prop', forbidden)
    monkeypatch.setattr(web, 'load_current_sources', forbidden)
    stored = client.get(f'/api/multi/{stored_id}').json()
    assert stored['combined'] == body['combined'] and stored['stored']['id'] == stored_id
    assert client.get('/api/multi/' + 'a'*64).status_code == 404
    assert client.get('/api/multi/..%2F' + 'a'*61).status_code in (404, 422)


def test_legacy_american_analysis_lists_with_decimal_conversion(client):
    client.post('/api/analyze', json={'kicker': MEVIS, 'team': 'LA', 'opponent': 'PHI', 'season': 2026, 'week': 5,
                                      'line': 1.5, 'side': 'over', 'odds': 150})
    item = client.get('/api/analyses').json()['analyses'][0]
    assert item['odds_format'] == 'american' and item['odds'] == 150 and item['decimal_odds'] == pytest.approx(2.5)
