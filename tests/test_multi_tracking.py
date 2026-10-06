"""Official multi tracker: frozen manifest before any kickoff, per-leg settlement and
audited corrections, descriptive multi outcomes and separated metrics."""
from datetime import datetime, timedelta, timezone
import json

import pytest
from fastapi.testclient import TestClient

from kickedge.current import multi_tracking as mt, tracking
from kickedge.current.multi import combine
from kickedge.web import app as web

K1 = datetime(2026, 10, 11, 17, tzinfo=timezone.utc)
K2 = K1 + timedelta(hours=3, minutes=25)
BEFORE, BETWEEN, AFTER = K1 - timedelta(hours=3), K1 + timedelta(hours=3), K2 + timedelta(hours=4)
AID = 'a' * 64


def leg(game_id='2026_06_DAL_HOU', kicker='Brandon Aubrey', kicker_id='00-1', side='over', line=1.5, p_side=.8,
        p_push=0., odds=1.3, kickoff=K1):
    p_over = p_side if side == 'over' else 1 - p_side - p_push
    team, opponent = game_id.split('_')[2:]
    return {'game': {'game_id': game_id, 'kicker_id': kicker_id, 'team': team, 'opponent': opponent,
                     'kickoff': kickoff.isoformat(), 'home_team': opponent, 'away_team': team, 'season': 2026, 'week': 6,
                     'cutoff': (kickoff - timedelta(hours=1)).isoformat()},
            'player': {'kicker_name': kicker},
            'prop': {'side': side, 'line': line, 'p_over': p_over, 'p_under': 1 - p_over - p_push, 'p_push': p_push,
                     'model_side_probability': p_side, 'model_probability_conditional': p_side / (1 - p_push)},
            'prediction': {'expected_xpm': 2.4}, 'market': {'odds_format': 'decimal', 'decimal_odds': odds},
            'model': {'version': 'phase5-c2f8f5ff0071', 'artifact_sha256': 'c' * 64},
            'provenance': {'feature_snapshot_sha256': kicker_id[-1] * 64, 'analysis_generated_at': BEFORE.isoformat()},
            'data_quality': {'model_verified': True, 'warnings': [f'note {kicker_id}']}}


def multi(*results):
    results = results or (leg(), leg('2026_06_BUF_NE', 'Tyler Bass', '00-2', line=2.5, p_side=.5, odds=1.9, kickoff=K2))
    return {'kind': 'multi', 'schema_version': 'multi.1', 'combined_available': True, 'combined': combine(list(results)),
            'selections': [{'index': i, 'status': 'ok', 'input': {}, 'result': r} for i, r in enumerate(results, 1)]}


def tracked(tmp_path, record=None, now=BEFORE):
    return mt.track(tmp_path, record or multi(), AID, now)


# ---------- tracking ----------

def test_track_valid_multi_freezes_combined_and_every_leg(tmp_path):
    record = tracked(tmp_path)
    m = record['manifest']
    assert record['already_tracked'] is False and record['status'] == 'OPEN' and record['outcome'] is None
    assert m['selection_count'] == 2 and m['combined_decimal_odds'] == pytest.approx(1.3 * 1.9)
    assert m['market_implied_combined_probability'] == pytest.approx(1 / (1.3 * 1.9))
    assert m['approximate_kickedge_combined_probability'] == pytest.approx(.8 * .5)
    assert m['independence_warning'].startswith('Approximate combined probability assuming independent')
    assert m['same_game_correlation_warning'] is False and m['analysis_id'] == AID
    first, second = m['legs']
    assert (first['leg'], first['kicker'], first['side'], first['line'], first['decimal_odds']) == (1, 'Brandon Aubrey', 'over', 1.5, 1.3)
    assert first['kickedge_probability'] == .8 and first['expected_xpm'] == 2.4 and first['snapshot_sha256'] == '1' * 64
    assert first['feature_cutoff'] and first['model_version'] == 'phase5-c2f8f5ff0071'
    assert second['kickoff'] == K2.isoformat() and second['data_quality']['warnings'] == ['note 00-2']


def test_duplicate_multi_returns_the_original(tmp_path):
    first = tracked(tmp_path)
    a, b = leg(p_side=.9), leg('2026_06_BUF_NE', 'Tyler Bass', '00-2', line=2.5, p_side=.6, odds=1.9, kickoff=K2)
    again = mt.track(tmp_path, multi(b, a), 'b' * 64, BEFORE + timedelta(hours=1))   # re-analysed, legs reordered
    assert again['already_tracked'] is True and again['manifest'] == first['manifest']
    assert len(mt.list_tracked(tmp_path)['multis']) == 1
    other = mt.track(tmp_path, multi(a, leg('2026_06_BUF_NE', 'Tyler Bass', '00-2', line=2.5, odds=2.0, kickoff=K2)), AID, BEFORE)
    assert other['already_tracked'] is False                                          # different price: new multi


def test_cannot_track_once_any_leg_started(tmp_path):
    with pytest.raises(tracking.TrackingError, match='Selection 1 has reached kickoff'):
        tracked(tmp_path, now=K1)
    with pytest.raises(tracking.TrackingError, match='complete multi'):
        tracked(tmp_path, multi() | {'combined_available': False})
    assert not list(tmp_path.iterdir())


def test_manifest_probabilities_are_immutable(tmp_path):
    m = tracked(tmp_path)['manifest']
    path = tmp_path/m['tracking_id']/'manifest.json'
    before = path.read_bytes()
    mt.settle_leg(tmp_path, m['tracking_id'], 1, 0, BETWEEN)
    mt.correct_leg(tmp_path, m['tracking_id'], 1, 3, AFTER)
    assert path.read_bytes() == before
    for change in ({'approximate_kickedge_combined_probability': .99},
                   {'legs': [m['legs'][0] | {'kickedge_probability': .99}, m['legs'][1]]}):
        path.write_text(json.dumps(json.loads(before) | change))
        with pytest.raises(tracking.TrackingError, match='integrity'):
            mt.load(tmp_path, m['tracking_id'])
        assert mt.list_tracked(tmp_path)['summary']['unreadable'] == 1 and mt.list_tracked(tmp_path)['multis'] == []
    path.write_bytes(before)
    assert mt.load(tmp_path, m['tracking_id'])['manifest'] == m


# ---------- settlement ----------

def test_legs_settle_individually_after_their_own_kickoff(tmp_path):
    tid = tracked(tmp_path)['manifest']['tracking_id']
    with pytest.raises(tracking.TrackingError, match='only after kickoff'):
        mt.settle_leg(tmp_path, tid, 1, 2, BEFORE)
    partial = mt.settle_leg(tmp_path, tid, 1, 2, BETWEEN)
    assert partial['status'] == 'PARTIALLY SETTLED' and partial['settled_legs'] == 1 and partial['outcome'] is None
    assert partial['legs'][0]['settlement']['result'] == 'WIN' and partial['legs'][1]['settlement'] is None
    with pytest.raises(tracking.TrackingError, match='only after kickoff'):
        mt.settle_leg(tmp_path, tid, 2, 3, BETWEEN)                                   # leg 2 has not kicked off yet
    with pytest.raises(tracking.TrackingError, match='already settled'):
        mt.settle_leg(tmp_path, tid, 1, 3, AFTER)
    done = mt.settle_leg(tmp_path, tid, 2, 3, AFTER)
    assert done['status'] == 'SETTLED' and done['outcome'] == 'ALL LEGS WON' and done['push_note'] is None


@pytest.mark.parametrize('actuals,outcome,push', [((2, 1), 'HAS LOSS', False), ((1, 1), 'HAS LOSS', False),
                                                   ((2, 2), 'NO-LOSS WITH PUSH', True), ((1, 2), 'HAS LOSS', True)])
def test_multi_outcomes_never_call_a_push_a_win(tmp_path, actuals, outcome, push):
    record = multi(leg(), leg('2026_06_BUF_NE', 'Tyler Bass', '00-2', line=2, p_side=.5, p_push=.2, odds=1.9, kickoff=K2))
    tid = tracked(tmp_path, record)['manifest']['tracking_id']
    mt.settle_leg(tmp_path, tid, 1, actuals[0], AFTER)
    done = mt.settle_leg(tmp_path, tid, 2, actuals[1], AFTER)
    assert done['outcome'] == outcome
    assert done['push_note'] == (mt.PUSH_NOTE if push else None)
    assert mt.PUSH_NOTE == 'One or more legs pushed. Sportsbook settlement rules may vary.'


# ---------- corrections ----------

def test_leg_correction_is_audited_and_latest_is_effective(tmp_path):
    tid = tracked(tmp_path)['manifest']['tracking_id']
    mt.settle_leg(tmp_path, tid, 1, 1, AFTER)                                        # LOSS
    mt.settle_leg(tmp_path, tid, 2, 3, AFTER)
    folder = tmp_path/tid/'legs'/'1'
    settlement = (folder/'settlement.json').read_bytes()
    assert mt.list_tracked(tmp_path)['summary']['multis']['independent_games']['has_loss'] == 1
    mt.correct_leg(tmp_path, tid, 1, 3, AFTER + timedelta(days=1), 'Entered wrong result')
    record = mt.correct_leg(tmp_path, tid, 1, 2, AFTER + timedelta(days=2))
    first = record['legs'][0]
    assert first['original_settlement']['result'] == 'LOSS' and (folder/'settlement.json').read_bytes() == settlement
    assert [(c['previous_actual_xpm'], c['new_actual_xpm']) for c in first['corrections']] == [(1, 3), (3, 2)]
    assert first['settlement']['actual_xpm'] == 2 and record['outcome'] == 'ALL LEGS WON'
    summary = mt.list_tracked(tmp_path)['summary']
    assert summary['multis']['independent_games']['all_legs_won'] == 1 and summary['multis']['independent_games']['has_loss'] == 0
    assert summary['legs']['graded'] == 2 and summary['legs']['observed_frequency'] == 1     # one result per leg
    with pytest.raises(tracking.TrackingError, match='Only a settled selection'):
        mt.correct_leg(tmp_path, tracked(tmp_path, multi(leg(odds=1.4), leg('2026_06_BUF_NE', 'Tyler Bass', '00-2', kickoff=K2)))
                       ['manifest']['tracking_id'], 1, 2, AFTER)


# ---------- metrics ----------

def test_leg_metrics_exclude_pushes_and_are_labelled(tmp_path):
    record = multi(leg(p_side=.8), leg('2026_06_BUF_NE', 'Tyler Bass', '00-2', line=2, p_side=.45, p_push=.25, kickoff=K2),
                   leg('2026_06_KC_LV', 'Harrison Butker', '00-3', side='under', line=2.5, p_side=.6, kickoff=K2))
    tid = tracked(tmp_path, record)['manifest']['tracking_id']
    for number, actual in ((1, 3), (2, 2), (3, 4)):                                  # WIN, PUSH, LOSS
        mt.settle_leg(tmp_path, tid, number, actual, AFTER)
    legs = mt.list_tracked(tmp_path)['summary']['legs']
    assert legs['source'] == 'multi_leg' and 'correlated' in legs['note']
    assert (legs['tracked'], legs['settled'], legs['pushes'], legs['graded']) == (3, 3, 1, 2)
    assert legs['average_probability'] == pytest.approx(.7) and legs['brier_score'] == pytest.approx((.2 ** 2 + .6 ** 2) / 2)


def test_all_win_metrics_are_split_by_same_game_correlation(tmp_path):
    independent = tracked(tmp_path)['manifest']                                      # p = .4
    same = tracked(tmp_path, multi(leg(), leg(kicker='Ka\'imi Fairbairn', kicker_id='00-9', side='under', line=2.5,
                                              p_side=.5, odds=1.8)))['manifest']     # same game, p = .4
    assert same['same_game_correlation_warning'] is True and same['same_game_ids'] == ['2026_06_DAL_HOU']
    assert any(w.startswith('These selections belong to the same game') for w in same['warnings'])
    for number, actual in ((1, 2), (2, 3)):
        mt.settle_leg(tmp_path, independent['tracking_id'], number, actual, AFTER)   # all legs won
    for number, actual in ((1, 2), (2, 3)):
        mt.settle_leg(tmp_path, same['tracking_id'], number, actual, AFTER)          # under 2.5 with 3 -> loss
    s = mt.list_tracked(tmp_path)['summary']
    ind, cor = s['multis']['independent_games'], s['multis']['same_game_correlated']
    assert (ind['tracked'], ind['settled'], ind['all_legs_won'], ind['observed_all_win_frequency']) == (1, 1, 1, 1)
    assert ind['all_win_brier_score'] == pytest.approx((.4 - 1) ** 2)
    assert (cor['tracked'], cor['has_loss'], cor['observed_all_win_frequency']) == (1, 1, 0)
    assert cor['all_win_brier_score'] == pytest.approx(.4 ** 2)
    assert s['combined_note'] == 'Combined probabilities assume independence.'
    assert s['legs']['graded'] == 4                                                  # every leg counted exactly once


def test_multi_legs_never_enter_single_metrics(tmp_path):
    tid = tracked(tmp_path/'multi')['manifest']['tracking_id']
    mt.settle_leg(tmp_path/'multi', tid, 1, 3, AFTER)
    single = tracking.list_tracked(tmp_path/'single')['summary']
    assert single['tracked'] == 0 and single['source'] == 'single'


# ---------- security ----------

@pytest.mark.parametrize('bad', ['../' + 'a' * 61, 'A' * 64, 'a' * 63, '..', '', None])
def test_invalid_multi_ids_are_rejected(tmp_path, bad):
    with pytest.raises(tracking.TrackingError, match='Invalid tracking id'):
        mt.load(tmp_path, bad)
    with pytest.raises(tracking.TrackingError, match='Invalid tracking id'):
        mt.settle_leg(tmp_path, bad, 1, 1, AFTER)


def test_leg_numbers_and_actual_xpm_are_validated(tmp_path):
    tid = tracked(tmp_path)['manifest']['tracking_id']
    for bad in (0, 3, 11, -1, True, '1', None):
        with pytest.raises(tracking.TrackingError, match='Selection not found'):
            mt.settle_leg(tmp_path, tid, bad, 1, AFTER)
        with pytest.raises(tracking.TrackingError, match='Selection not found'):
            mt.correct_leg(tmp_path, tid, bad, 1, AFTER)
    for bad in (-1, 21, 2.5, True, '2'):
        with pytest.raises(tracking.TrackingError, match='whole number'):
            mt.settle_leg(tmp_path, tid, 1, bad, AFTER)
    with pytest.raises(tracking.TrackingError, match='not found'):
        mt.settle_leg(tmp_path, 'c' * 64, 1, 1, AFTER)
    assert not (tmp_path/tid/'legs').exists()


# ---------- HTTP layer ----------

@pytest.fixture
def client(monkeypatch, tmp_path):
    clock = {'now': BEFORE}
    monkeypatch.setattr(web, '_now', lambda: clock['now'])
    monkeypatch.setattr(web, 'ANALYSES_DIR', tmp_path/'analyses')
    monkeypatch.setattr(web, 'TRACKED_MULTI_DIR', tmp_path/'tracked_multi')
    monkeypatch.setattr(web, 'TRACKED_DIR', tmp_path/'tracked')
    stored = tmp_path/'analyses'/('b' * 64)
    stored.mkdir(parents=True)
    (stored/'multi.json').write_text(json.dumps(multi()))
    (stored/'analysis.json').write_text(json.dumps(leg()))
    c = TestClient(web.app)
    c.clock = clock
    return c


def test_api_tracks_from_the_server_copy_and_settles_legs(client):
    assert client.post('/api/tracked-multi', json={'analysis_id': 'b' * 64, 'combined_decimal_odds': 9}).status_code == 422
    assert client.post('/api/tracked-multi', json={'analysis_id': 'c' * 64}).json()['error']['code'] == 'ANALYSIS_NOT_FOUND'
    first = client.post('/api/tracked-multi', json={'analysis_id': 'b' * 64}).json()
    tid = first['manifest']['tracking_id']
    assert first['already_tracked'] is False and first['manifest']['combined_decimal_odds'] == pytest.approx(2.47)
    assert client.post('/api/tracked-multi', json={'analysis_id': 'b' * 64}).json()['already_tracked'] is True
    url = f'/api/tracked-multi/{tid}/legs'
    assert client.post(f'{url}/1/settle', json={'actual_xpm': 2}).json()['error']['code'] == 'NOT_STARTED'
    client.clock['now'] = BETWEEN
    assert client.post(f'{url}/1/settle', json={'actual_xpm': 2}).json()['status'] == 'PARTIALLY SETTLED'
    for path, body in ((f'{url}/0/settle', {'actual_xpm': 1}), (f'{url}/11/settle', {'actual_xpm': 1}),
                       (f'{url}/x/settle', {'actual_xpm': 1}), (f'{url}/2/settle', {'actual_xpm': 2.5}),
                       (f'{url}/2/settle', {'actual_xpm': 2, 'result': 'WIN'}), (f'{url}/1/correct', {'actual_xpm': 3}),
                       (f'/api/tracked-multi/{"A" * 64}/legs/1/settle', {'actual_xpm': 1}),
                       ('/api/tracked-multi/..%2F..%2Fetc/legs/1/settle', {'actual_xpm': 1})):
        assert client.post(path, json=body).status_code in (404, 422), path
    assert client.post(f'{url}/3/settle', json={'actual_xpm': 1}).json()['error']['code'] == 'LEG_NOT_FOUND'
    assert client.post(f'{url}/2/correct', json={'actual_xpm': 1, 'confirm': True}).json()['error']['code'] == 'NOT_SETTLED'
    client.clock['now'] = AFTER
    done = client.post(f'{url}/2/settle', json={'actual_xpm': 3}).json()
    assert done['status'] == 'SETTLED' and done['outcome'] == 'ALL LEGS WON'
    fixed = client.post(f'{url}/2/correct', json={'actual_xpm': 1, 'confirm': True, 'reason': 'Typo'}).json()
    assert fixed['outcome'] == 'HAS LOSS' and fixed['legs'][1]['original_settlement']['actual_xpm'] == 3
    listing = client.get('/api/tracked-multi').json()
    assert listing['summary']['multis']['independent_games']['has_loss'] == 1 and listing['multis'][0]['manifest'] == first['manifest']
    assert client.get(f'/api/tracked-multi/{tid}').json()['legs'][1]['corrections'][0]['reason'] == 'Typo'
    assert client.get('/api/tracked').json()['summary']['tracked'] == 0             # single tracker untouched


def test_api_refuses_multi_after_a_leg_started(client):
    client.clock['now'] = BETWEEN
    assert client.post('/api/tracked-multi', json={'analysis_id': 'b' * 64}).json()['error']['code'] == 'GAME_STARTED'
    assert client.get('/api/tracked-multi').json()['summary']['tracked'] == 0
