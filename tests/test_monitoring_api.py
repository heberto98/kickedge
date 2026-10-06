"""HTTP layer of refresh results, performance, monitoring, movement and line comparison."""
from datetime import timedelta
import json

import pytest
from fastapi.testclient import TestClient

from kickedge.current import tracking
from kickedge.current.sources import CurrentSourceError
from kickedge.web import app as web
from test_auto_settlement import bundle, event, label
from test_multi_tracking import multi
from test_performance_monitoring import stored
from test_tracking import AFTER, BEFORE, KICKOFF, analysis


@pytest.fixture
def client(monkeypatch, tmp_path):
    state = {'now': BEFORE, 'bundle': bundle(event(rows=[label(xpm=3)])), 'loads': []}

    def loader(root, season, refresh=False, now=None, clock=None):
        state['loads'].append((season, refresh))
        if isinstance(state['bundle'], Exception):
            raise state['bundle']
        return state['bundle']
    monkeypatch.setattr(web, 'load_current_sources', loader)
    monkeypatch.setattr(web, '_now', lambda: state['now'])
    for name, folder in (('ANALYSES_DIR', 'analyses'), ('TRACKED_DIR', 'tracked'), ('TRACKED_MULTI_DIR', 'tracked_multi'),
                         ('MONITORING_DIR', 'monitoring')):
        monkeypatch.setattr(web, name, tmp_path/folder)
    monkeypatch.setattr(web, 'ROOT', tmp_path)
    for analysis_id, record, name in (('b' * 64, analysis(), 'analysis.json'), ('c' * 64, multi(), 'multi.json')):
        (tmp_path/'analyses'/analysis_id).mkdir(parents=True)
        (tmp_path/'analyses'/analysis_id/name).write_text(json.dumps(record))
    c = TestClient(web.app)
    c.state, c.root = state, tmp_path
    return c


def test_refresh_results_auto_settles_and_updates_everything(client):
    tid = client.post('/api/tracked', json={'analysis_id': 'b' * 64}).json()['pick']['tracking_id']
    mid = client.post('/api/tracked-multi', json={'analysis_id': 'c' * 64}).json()['manifest']['tracking_id']
    client.state['now'] = KICKOFF + timedelta(hours=5)
    body = client.post('/api/tracking/refresh-results', json={}).json()
    assert [(s['type'], s['tracking_id'], s['result']) for s in body['report']['settled']] == [
        ('single', tid, 'WIN'), ('multi', mid, 'WIN')]
    assert client.state['loads'] == [(2026, False)]                                  # cache rules respected
    assert body['freshness']['latest_completed_game']['game_id'] == '2026_06_DAL_HOU'
    assert body['performance']['counts']['singles_settled'] == 1 and body['monitoring']['snapshot_written'] is True
    assert body['monitoring']['forward_validation']['label_eligible_completed_observations'] == 1
    single = client.get(f'/api/tracked/{tid}').json()
    assert single['result_source'] == 'auto_nflverse' and single['original_settlement']['source_game_id'] == '2026_06_DAL_HOU'
    multi_record = client.get(f'/api/tracked-multi/{mid}').json()
    assert multi_record['status'] == 'PARTIALLY SETTLED' and multi_record['legs'][0]['result_source'] == 'auto_nflverse'
    again = client.post('/api/tracking/refresh-results', json={}).json()
    assert again['report']['settled'] == [] and again['monitoring']['snapshot_written'] is False
    log = (client.root/'monitoring'/'settlement_log.jsonl').read_text().splitlines()
    assert len(log) == 2 and len(list((client.root/'monitoring'/'snapshots').glob('*.json'))) == 1
    assert client.get('/api/performance').json()['single']['graded'] == 1
    status = client.get('/api/monitoring').json()
    assert status['snapshots'] == 1 and status['forward_validation']['last_audit_rows'] == 84
    assert status['model']['artifact_sha256'].startswith('c2f8f5ff')


def test_refresh_source_failure_keeps_tracker_unchanged(client):
    tid = client.post('/api/tracked', json={'analysis_id': 'b' * 64}).json()['pick']['tracking_id']
    client.state['now'] = AFTER
    client.state['bundle'] = CurrentSourceError('offline')
    body = client.post('/api/tracking/refresh-results', json={}).json()
    assert body['report']['settled'] == [] and body['report']['warnings'][0]['code'] == 'SOURCE_UNAVAILABLE'
    assert body['freshness']['warnings'][0]['code'] == 'SOURCE_UNAVAILABLE'
    assert body['monitoring']['snapshot_written'] is False
    assert client.get(f'/api/tracked/{tid}').json()['status'] == 'OPEN'


def test_refresh_request_validation_and_explicit_download(client):
    assert client.post('/api/tracking/refresh-results').status_code == 200          # empty POST: plain refresh
    assert client.state['loads'][-1] == (2026, False)
    assert client.post('/api/tracking/refresh-results', json={'refresh_data': 'yes'}).status_code == 422
    assert client.post('/api/tracking/refresh-results', json={'settle': True}).status_code == 422
    client.post('/api/tracking/refresh-results', json={'refresh_data': True})
    assert client.state['loads'][-1] == (2026, True)


def test_movement_and_line_comparison_endpoints(client):
    d = client.root/'analyses'
    stored(d, 'd' * 64, '2026-10-05T09:00:00+00:00', .66, snapshot='2', features={'kicker_xpm_last_3': 2.7})
    movement = client.get(f"/api/prediction-movement/{'b' * 64}").json()
    assert movement['item'] == {'kind': 'analysis', 'id': 'b' * 64} and movement['analyses'] == 2
    tid = client.post('/api/tracked', json={'analysis_id': 'b' * 64}).json()['pick']['tracking_id']
    assert client.get(f'/api/prediction-movement/{tid}').json()['item']['kind'] == 'tracked_pick'
    lines = client.get(f"/api/line-comparison/{'b' * 64}").json()
    assert lines['analysed_line'] == 1.5 and [r['line'] for r in lines['lines']][:3] == [0.5, 1.0, 1.5]
    for bad in ('A' * 64, 'a' * 63, '..%2F' + 'a' * 61):
        assert client.get(f'/api/prediction-movement/{bad}').status_code in (404, 422)
        assert client.get(f'/api/line-comparison/{bad}').status_code in (404, 422)
    assert client.get(f"/api/prediction-movement/{'e' * 64}").status_code == 404
    assert client.get(f"/api/line-comparison/{'c' * 64}").status_code == 404           # a multi is not a single analysis
    assert tracking.load(client.root/'tracked', tid)['status'] == 'OPEN'
