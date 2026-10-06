"""Official pick tracker: frozen pregame picks, manual settlement, probability metrics."""
from datetime import datetime, timedelta, timezone
from functools import partial
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kickedge.current import tracking
from kickedge.current.engine import analyze_current_prop
from kickedge.web import app as web
from polish_data import NOW, make_bundle, no_context

KICKOFF = datetime(2026, 10, 11, 17, tzinfo=timezone.utc)
BEFORE, AFTER = KICKOFF - timedelta(hours=3), KICKOFF + timedelta(hours=4)
AID = 'a' * 64
needs_model = pytest.mark.skipif(not Path('data/models/phase5/model.joblib').exists(), reason='Local model unavailable')


def analysis(side='over', line=1.5, p_side=.7, p_push=0., odds=1.5, kicker_id='00-1'):
    p_over = p_side if side == 'over' else 1 - p_side - p_push
    p_under = 1 - p_over - p_push
    return {'game': {'game_id': '2026_06_DAL_HOU', 'kicker_id': kicker_id, 'team': 'DAL', 'opponent': 'HOU',
                     'kickoff': KICKOFF.isoformat(), 'home_team': 'HOU', 'away_team': 'DAL', 'season': 2026, 'week': 6,
                     'cutoff': (KICKOFF - timedelta(hours=4)).isoformat()},
            'player': {'kicker_name': 'Brandon Aubrey'},
            'prop': {'side': side, 'line': line, 'p_over': p_over, 'p_under': p_under, 'p_push': p_push,
                     'model_side_probability': p_side, 'model_probability_conditional': p_side / (1 - p_push)},
            'prediction': {'expected_xpm': 2.3},
            'market': {'odds_format': 'decimal', 'decimal_odds': odds},
            'model': {'version': 'phase5-c2f8f5ff0071', 'artifact_sha256': 'c' * 64},
            'provenance': {'feature_snapshot_sha256': 'd' * 64, 'analysis_generated_at': BEFORE.isoformat()},
            'data_quality': {'model_verified': True, 'warnings': ['Weather unavailable']}}


def tracked(tmp_path, **kwargs):
    return tracking.track(tmp_path, analysis(**kwargs), AID, BEFORE)


def test_track_valid_pick_freezes_the_pregame_prediction(tmp_path):
    record = tracked(tmp_path)
    pick = record['pick']
    assert record['status'] == 'OPEN' and record['already_tracked'] is False and record['settlement'] is None
    assert (pick['kicker'], pick['side'], pick['line'], pick['decimal_odds']) == ('Brandon Aubrey', 'over', 1.5, 1.5)
    assert pick['kickedge_probability'] == .7 and pick['expected_xpm'] == 2.3 and pick['p_push'] == 0
    assert pick['model_version'] == 'phase5-c2f8f5ff0071' and pick['snapshot_sha256'] == 'd' * 64
    assert pick['data_quality']['warnings'] == ['Weather unavailable'] and pick['created_at'] == BEFORE.isoformat()


def test_only_pregame_picks_can_be_tracked(tmp_path):
    with pytest.raises(tracking.TrackingError, match='Kickoff has passed'):
        tracking.track(tmp_path, analysis(), AID, KICKOFF)
    assert not list(tmp_path.iterdir())


def test_duplicate_tracking_returns_the_original_unchanged(tmp_path):
    first = tracked(tmp_path)
    again = tracking.track(tmp_path, analysis(p_side=.9), 'b' * 64, BEFORE + timedelta(hours=1))   # re-analysed later
    assert again['already_tracked'] is True and again['pick'] == first['pick'] and again['pick']['kickedge_probability'] == .7
    assert len(tracking.list_tracked(tmp_path)['open']) == 1
    other = tracked(tmp_path, odds=1.6)                                                          # different price: new pick
    assert other['already_tracked'] is False and other['pick']['tracking_id'] != first['pick']['tracking_id']


def test_original_probability_cannot_be_mutated(tmp_path):
    pick = tracked(tmp_path)['pick']
    path = tmp_path/pick['tracking_id']/'pick.json'
    before = path.read_bytes()
    tracking.settle(tmp_path, pick['tracking_id'], 3, AFTER)
    assert path.read_bytes() == before                                     # settling never rewrites the pick
    edited = json.loads(before) | {'kickedge_probability': .99}
    path.write_text(json.dumps(edited))
    with pytest.raises(tracking.TrackingError, match='integrity'):
        tracking.load(tmp_path, pick['tracking_id'])
    assert tracking.list_tracked(tmp_path)['summary']['unreadable'] == 1   # a tampered pick is never counted


@pytest.mark.parametrize('side,line,actual,result', [
    ('over', 1.5, 2, 'WIN'), ('over', 1.5, 1, 'LOSS'), ('under', 2.5, 2, 'WIN'), ('under', 2.5, 3, 'LOSS'),
    ('over', 2, 2, 'PUSH'), ('under', 2, 2, 'PUSH'), ('over', 2, 3, 'WIN'), ('under', 2, 1, 'WIN')])
def test_outcome_rules(side, line, actual, result):
    assert tracking.outcome(side, line, actual) == result


def test_settle_adds_only_the_result_once_after_kickoff(tmp_path):
    tid = tracked(tmp_path)['pick']['tracking_id']
    with pytest.raises(tracking.TrackingError, match='after kickoff'):
        tracking.settle(tmp_path, tid, 2, BEFORE)
    settled = tracking.settle(tmp_path, tid, 2, AFTER)
    assert settled['status'] == 'SETTLED' and settled['settlement'] == {'settled_at': AFTER.isoformat(), 'actual_xpm': 2, 'result': 'WIN'}
    with pytest.raises(tracking.TrackingError, match='already settled'):
        tracking.settle(tmp_path, tid, 0, AFTER)
    for bad in (-1, 21, 2.0, True, '2'):
        with pytest.raises(tracking.TrackingError, match='whole number'):
            tracking.settle(tmp_path, tid, bad, AFTER)


def test_brier_and_observed_frequency_exclude_pushes(tmp_path):
    win = tracked(tmp_path, p_side=.8)['pick']['tracking_id']                                # over 1.5, actual 3 -> WIN
    loss = tracked(tmp_path, side='under', line=2.5, p_side=.6)['pick']['tracking_id']      # under 2.5, actual 4 -> LOSS
    push = tracked(tmp_path, line=2, p_side=.5, p_push=.25)['pick']['tracking_id']          # over 2, actual 2 -> PUSH
    tracked(tmp_path, line=3.5, p_side=.2)                                                  # stays open
    for tid, actual in ((win, 3), (loss, 4), (push, 2)):
        tracking.settle(tmp_path, tid, actual, AFTER)
    data = tracking.list_tracked(tmp_path)
    s = data['summary']
    assert (s['tracked'], s['settled'], s['open'], s['pushes'], s['graded']) == (4, 3, 1, 1, 2)
    assert s['average_probability'] == pytest.approx(.7) and s['observed_frequency'] == .5
    assert s['brier_score'] == pytest.approx(((.8 - 1) ** 2 + (.6 - 0) ** 2) / 2)
    assert [r['settlement']['result'] for r in data['settled']].count('PUSH') == 1


def test_push_probability_uses_the_no_push_conditional(tmp_path):
    tid = tracked(tmp_path, line=2, p_side=.45, p_push=.25)['pick']['tracking_id']
    tracking.settle(tmp_path, tid, 3, AFTER)
    s = tracking.list_tracked(tmp_path)['summary']
    assert s['average_probability'] == pytest.approx(.6) and s['brier_score'] == pytest.approx(.16)


def test_empty_summary_has_no_metrics(tmp_path):
    s = tracking.list_tracked(tmp_path)['summary']
    assert s['tracked'] == 0 and s['brier_score'] is None and s['average_probability'] is None


@pytest.mark.parametrize('bad', ['../' + 'a' * 61, 'A' * 64, 'a' * 63, '..', '', None, 'a' * 64 + '/..'])
def test_invalid_or_traversal_tracking_ids_are_rejected(tmp_path, bad):
    with pytest.raises(tracking.TrackingError, match='Invalid tracking id'):
        tracking.load(tmp_path, bad)
    with pytest.raises(tracking.TrackingError):
        tracking.settle(tmp_path, bad, 1, AFTER)


# ---------- HTTP layer ----------

@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(web, 'load_current_sources', lambda *a, **k: make_bundle())
    clock = {'now': NOW}
    monkeypatch.setattr(web, '_now', lambda: clock['now'])
    monkeypatch.setattr(web, 'TRACKED_DIR', tmp_path/'tracked')
    monkeypatch.setattr(web, 'ANALYSES_DIR', tmp_path/'analyses')
    monkeypatch.setattr(web, 'analyze_current_prop', partial(analyze_current_prop, clock=lambda: NOW,
                                                             context_collector=no_context, output_dir=tmp_path/'analyses'))
    web._recent.clear()
    c = TestClient(web.app)
    c.clock, c.root = clock, tmp_path
    return c


@needs_model
def test_api_track_and_settle_a_real_analysis(client):
    result = client.post('/api/analyze', json={'kicker': 'Harrison Mevis', 'game_id': '2026_05_LA_PHI',
                                              'line': 1.5, 'side': 'over', 'decimal_odds': 1.3}).json()
    analysis_id = result['stored']['id']
    assert result['stored']['fresh'] is True and client.get(f'/api/analyses/{analysis_id}').status_code == 200
    first = client.post('/api/tracked', json={'analysis_id': analysis_id}).json()
    pick = first['pick']
    assert first['already_tracked'] is False and pick['kickedge_probability'] == result['prop']['model_side_probability']
    assert pick['decimal_odds'] == 1.3 and pick['expected_xpm'] == result['prediction']['expected_xpm']
    assert client.post('/api/tracked', json={'analysis_id': analysis_id}).json()['already_tracked'] is True
    tid = pick['tracking_id']
    assert client.post(f'/api/tracked/{tid}/settle', json={'actual_xpm': 3}).json()['error']['code'] == 'NOT_STARTED'
    client.clock['now'] = datetime.fromisoformat(pick['kickoff']) + timedelta(hours=4)
    assert client.post('/api/tracked', json={'analysis_id': analysis_id}).json()['error']['code'] == 'GAME_STARTED'
    settled = client.post(f'/api/tracked/{tid}/settle', json={'actual_xpm': 3}).json()
    assert settled['settlement']['result'] == 'WIN' and settled['pick'] == pick
    assert client.post(f'/api/tracked/{tid}/settle', json={'actual_xpm': 1}).status_code == 409
    listing = client.get('/api/tracked').json()
    assert listing['summary']['settled'] == 1 and listing['settled'][0]['pick'] == pick


def test_api_rejects_bad_ids_payloads_and_late_tracking(client, tmp_path):
    assert client.post('/api/tracked', json={'analysis_id': '../' + 'a' * 61}).status_code == 422
    assert client.post('/api/tracked', json={'analysis_id': 'a' * 64}).json()['error']['code'] == 'ANALYSIS_NOT_FOUND'
    assert client.post('/api/tracked', json={'analysis_id': 'a' * 64, 'kickedge_probability': .9}).status_code == 422
    stored = tmp_path/'analyses'/('b' * 64)
    stored.mkdir(parents=True)
    (stored/'analysis.json').write_text(json.dumps(analysis()))
    client.clock['now'] = AFTER
    assert client.post('/api/tracked', json={'analysis_id': 'b' * 64}).json()['error']['code'] == 'GAME_STARTED'
    for bad in ('..%2F..%2Fetc', 'A' * 64, 'a' * 63):
        assert client.get(f'/api/tracked/{bad}').status_code in (404, 422)
        assert client.post(f'/api/tracked/{bad}/settle', json={'actual_xpm': 1}).status_code in (404, 422)
    assert client.get(f"/api/tracked/{'c' * 64}").json()['error']['code'] == 'PICK_NOT_FOUND'
    client.clock['now'] = BEFORE
    tid = client.post('/api/tracked', json={'analysis_id': 'b' * 64}).json()['pick']['tracking_id']
    client.clock['now'] = AFTER
    for body in ({'actual_xpm': 2.5}, {'actual_xpm': -1}, {'actual_xpm': '2'}, {'actual_xpm': 2, 'result': 'WIN'}):
        assert client.post(f'/api/tracked/{tid}/settle', json=body).status_code == 422
