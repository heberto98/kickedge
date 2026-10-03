"""Phase 7C API: thin HTTP layer over the 7B pipeline and the frozen 7A engine."""
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import shutil

import pytest
from fastapi.testclient import TestClient

from kickedge.current.engine import analyze_current_prop
from kickedge.current.sources import CurrentSourceError
from kickedge.web import app as web
from test_current_snapshot import START, bundle

NOW = START+timedelta(days=42, hours=-2)
PICK = {'kicker': 'Test Kicker', 'team': 'AAA', 'opponent': 'BBB', 'season': 2027, 'week': 7,
        'line': 2.5, 'side': 'over', 'odds': 119}
MODEL_SHA = 'c2f8f5ff00712546023b769a7c8374478399b7d00e343dc4e5e928c10977f0d0'


@pytest.fixture
def client(monkeypatch, tmp_path):
    calls = {}

    def fake(*args, **kwargs):
        calls.update(kwargs)
        kwargs.pop('source_loader')
        context = kwargs.pop('context_collector', None) or (lambda *a, **k: {
            'context': {'market': {'available': False, 'quotes': []}, 'weather': {'available': False, 'values': {}}},
            'prop_quotes': [], 'provider_timestamps': {}, 'warnings': [], 'source_failures': []})
        return analyze_current_prop(*args, **kwargs, clock=lambda: NOW, source_loader=lambda *a, **k: bundle(),
                                    context_collector=context, output_dir=tmp_path)

    monkeypatch.setattr(web, 'analyze_current_prop', fake)
    web._recent.clear()
    web._last_market[0] = 0.
    c = TestClient(web.app)
    c.calls = calls
    return c


def test_health_ready_and_model_info(client):
    assert client.get('/healthz').json() == {'status': 'ok'}
    ready = client.get('/readyz')
    assert ready.status_code == 200 and ready.json()['model_verified'] and ready.json()['feature_count'] == 82
    info = client.get('/api/model').json()
    assert info['artifact_sha256'] == MODEL_SHA and info['alpha'] == .1 and info['training_period'] == '2016-2024'
    assert len(info['feature_order']) == 82 and info['blind_validation_verdict'] == 'PASS'
    assert not any(isinstance(v, str) and (':\\' in v or v.startswith('/')) for v in info.values())


def test_manual_prop_analysis_reuses_engine(client, tmp_path):
    r = client.post('/api/analyze', json=PICK)
    assert r.status_code == 200, r.text
    body = r.json()
    assert list(body['features']) == web.ensure_model(web.ROOT).info['feature_order']
    assert body['data_quality']['feature_count'] == 82 and body['data_quality']['prop_availability'] == 'manual'
    p = body['prop']
    assert p['p_over']+p['p_under']+p['p_push'] == pytest.approx(1)
    assert body['market']['implied_probability'] == pytest.approx(100/219)
    # Default: no market provider call when the user supplies the prop.
    assert client.calls['no_market'] is True and client.calls['no_weather'] is False
    # Identical to calling the 7B/7A engine directly with the same snapshot.
    direct = analyze_current_prop('Test Kicker', 'AAA', 'BBB', 2.5, 'over', 119, season=2027, week=7,
                                  clock=lambda: NOW, source_loader=lambda *a, **k: bundle(), no_market=True,
                                  no_weather=True, output_dir=tmp_path/'direct')
    assert direct['prediction'] == body['prediction']


@pytest.mark.parametrize('change,code', [
    ({'line': 2.25}, 'INVALID_LINE'), ({'line': -1}, 'INVALID_LINE'),
    ({'odds': 50}, 'INVALID_ODDS'), ({'odds': '+119'}, 'INVALID_ODDS'),
    ({'over_odds': 119}, 'INVALID_ODDS'), ({'over_odds': 110, 'under_odds': -130}, 'INVALID_ODDS'),
    ({'side': 'both'}, 'INVALID_REQUEST'), ({'kicker': ''}, 'INVALID_REQUEST'),
    ({'team': '../etc'}, 'INVALID_REQUEST'), ({'extra': 1}, 'INVALID_REQUEST')])
def test_invalid_inputs_are_4xx_without_echo(client, change, code):
    r = client.post('/api/analyze', json=PICK | change)
    assert r.status_code == 422 and r.json()['error']['code'] == code
    assert '../etc' not in r.text and 'Traceback' not in r.text


def test_missing_kicker_and_game_errors(client):
    r = client.post('/api/analyze', json=PICK | {'kicker': 'Nobody Here'})
    assert r.status_code == 404 and r.json()['error']['code'] == 'KICKER_NOT_FOUND'
    r = client.post('/api/analyze', json=PICK | {'opponent': 'CCC'})
    assert r.status_code == 404 and r.json()['error']['code'] == 'GAME_NOT_FOUND'


def test_ambiguous_game_requires_week(client, monkeypatch, tmp_path):
    # Two upcoming AAA-BBB meetings: week 7 and week 8.
    monkeypatch.setattr(web, 'analyze_current_prop', lambda *a, **k: analyze_current_prop(
        *a, **(k | {'source_loader': lambda *x, **y: bundle(8)}), clock=lambda: NOW, output_dir=tmp_path))
    body = {k: v for k, v in PICK.items() if k != 'week'} | {'include_weather': False}
    r = client.post('/api/analyze', json=body)
    assert r.status_code == 409 and r.json()['error']['code'] == 'GAME_AMBIGUOUS'


def test_source_failure_is_503(client, monkeypatch):
    def broken(*a, **k):
        raise CurrentSourceError('Required current source unavailable: pbp')
    monkeypatch.setattr(web, 'analyze_current_prop', broken)
    r = client.post('/api/analyze', json=PICK)
    assert r.status_code == 503 and r.json()['error']['code'] == 'NFL_SOURCE_UNAVAILABLE'


def test_optional_provider_failure_keeps_manual_result(client, monkeypatch):
    def failing_context(*a, **k):
        return {'context': {'market': {'available': False, 'quotes': []}, 'weather': {'available': False, 'values': {}}},
                'prop_quotes': [], 'provider_timestamps': {},
                'warnings': ['parlay_xpm: Optional provider request or evidence validation failed; continuing without this context.'],
                'source_failures': [{'provider': 'parlay_xpm', 'critical': False, 'reason': 'x'}]}
    inner = web.analyze_current_prop
    monkeypatch.setattr(web, 'analyze_current_prop', lambda *a, **k: inner(*a, **k, context_collector=failing_context))
    r = client.post('/api/analyze', json=PICK | {'include_market': True})
    assert r.status_code == 200
    q = r.json()['data_quality']
    assert q['market_availability'] is False and q['prop_availability'] == 'manual'
    assert any('parlay_xpm' in w for w in q['warnings'])
    # A second market request within the window is not sent to the provider.
    r = client.post('/api/analyze', json=PICK | {'include_market': True})
    assert client.calls['no_market'] is True
    assert any('limited to one per minute' in w for w in r.json()['data_quality']['warnings'])


def test_rate_limit_and_body_limit(client):
    web._recent['testclient'].extend([web.time.monotonic()]*web.ANALYSES_PER_MINUTE)
    assert client.post('/api/analyze', json=PICK).json()['error']['code'] == 'RATE_LIMITED'
    r = client.post('/api/analyze', content=b'{"kicker":"' + b'a'*5000 + b'"}', headers={'content-type': 'application/json'})
    assert r.status_code == 413


def test_no_secrets_or_internal_routes_exposed(client, monkeypatch):
    monkeypatch.setenv('PARLAY_API_KEY', 'SECRET_SHOULD_NOT_LEAK')
    for path in ('/', '/about', '/api/model', '/readyz', '/static/app.js'):
        r = client.get(path)
        assert r.status_code == 200 and 'SECRET_SHOULD_NOT_LEAK' not in r.text
        assert "default-src 'self'" in r.headers['content-security-policy']
    assert 'SECRET_SHOULD_NOT_LEAK' not in client.post('/api/analyze', json=PICK).text
    for path in ('/docs', '/openapi.json', '/.env', '/static/../../.env', '/data/models/phase5/model.joblib'):
        assert client.get(path).status_code == 404


def test_bootstrap_installs_pinned_artifact_and_fails_closed(tmp_path):
    from kickedge.web.artifact import ensure_model
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root/'models/phase5', tmp_path/'models/phase5')
    model = ensure_model(tmp_path)
    blob = (tmp_path/'data/models/phase5/model.joblib').read_bytes()
    assert hashlib.sha256(blob).hexdigest() == MODEL_SHA == model.info['artifact_sha256']
    # A tampered existing runtime artifact is never replaced or loaded.
    (tmp_path/'data/models/phase5/model.joblib').write_bytes(blob[:-1]+b'x')
    with pytest.raises(ValueError):
        ensure_model(tmp_path)
    # A tampered pinned release is never installed.
    other = tmp_path/'other'
    shutil.copytree(root/'models/phase5', other/'models/phase5')
    (other/'models/phase5/model.joblib').write_bytes(b'not the model')
    with pytest.raises(ValueError, match='Pinned model release'):
        ensure_model(other)
    assert not (other/'data/models/phase5/model.joblib').exists()


def test_pinned_release_matches_runtime_model():
    root = Path(__file__).resolve().parents[1]
    release = json.loads((root/'kickedge/inference/release.json').read_text())
    assert hashlib.sha256((root/'models/phase5/model.joblib').read_bytes()).hexdigest() == release['artifact_sha256']
