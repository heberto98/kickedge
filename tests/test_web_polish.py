"""Polish pass, web layer: pickers, aliases, suggestions, roster errors, stored
analyses, local launcher, and the exact 7A fixture regression."""
from functools import partial
import json
from pathlib import Path


import pytest
from fastapi.testclient import TestClient

from kickedge.current.engine import analyze_current_prop
from kickedge.web import app as web
from polish_data import ELLIOTT, MEVIS, NOW, make_bundle, no_context

needs_model = pytest.mark.skipif(not Path('data/models/phase5/model.joblib').exists(), reason='Local model unavailable')
PICK = {'kicker': 'Harrison Mevis', 'team': 'LAR', 'opponent': 'PHI', 'week': 5, 'season': 2026,
        'line': 1.5, 'side': 'over', 'odds': -333}


@pytest.fixture
def client(monkeypatch, tmp_path):
    loads = []

    def loader(*args, **kwargs):
        loads.append(kwargs)
        return make_bundle()
    monkeypatch.setattr(web, 'load_current_sources', loader)
    monkeypatch.setattr(web, '_now', lambda: NOW)
    monkeypatch.setattr(web, 'ANALYSES_DIR', tmp_path)
    monkeypatch.setattr(web, 'analyze_current_prop', partial(analyze_current_prop, clock=lambda: NOW,
                                                             context_collector=no_context, output_dir=tmp_path))
    web._recent.clear()
    c = TestClient(web.app)
    c.loads = loads
    return c


def test_games_endpoint_lists_future_games_from_cached_sources(client):
    body = client.get('/api/games').json()
    assert body['season'] == 2026 and body['schedule_fetched_at']
    games = body['games']
    assert [g['game_id'] for g in games] == ['2026_05_DAL_HOU', '2026_05_LA_PHI', '2026_06_PHI_DET',
                                              '2026_07_LA_JAX', '2026_08_PHI_LA']
    kickoffs = [g['kickoff'] for g in games]
    assert kickoffs == sorted(kickoffs) and all(k > NOW.isoformat() for k in kickoffs)
    assert games[1]['display_name'] == 'Rams @ Eagles' and (games[1]['away_team'], games[1]['home_team']) == ('LA', 'PHI')
    assert client.loads[-1]['refresh'] is False  # cache reuse by default
    client.get('/api/games?refresh=true')
    assert client.loads[-1]['refresh'] is True


def test_kickers_endpoint_candidates_and_validation(client):
    body = client.get('/api/games/2026_05_LA_PHI/kickers').json()
    teams = {t['code']: t for t in body['teams']}
    assert [k['kicker_name'] for k in teams['LA']['kickers']] == ['Harrison Mevis']
    assert [k['roster_label'] for k in teams['PHI']['kickers']] == ['Active roster', 'Practice squad']
    assert body['roster_source']['dataset'] == 'nflverse players'
    assert client.get('/api/games/2026_01_SF_LA/kickers').json()['error']['code'] == 'GAME_NOT_FOUND'  # already played
    for bad in ('../etc', '2026_05_la_phi', 'x'*30):
        assert client.get(f'/api/games/{bad}/kickers').status_code in (404, 422)


@needs_model
@pytest.mark.parametrize('team,opponent', [('LAR', 'PHI'), ('lar', 'phi'), ('Los Angeles Rams', 'Eagles')])
def test_analyze_accepts_aliases_and_reports_normalization(client, team, opponent):
    r = client.post('/api/analyze', json=PICK | {'team': team, 'opponent': opponent})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['game']['game_id'] == '2026_05_LA_PHI' and body['game']['team'] == 'LA'
    if team.upper() != 'LA':
        assert any(note.startswith(f'Normalized {team} ') and note.endswith('LA') for note in body['input_notes'])
    assert body['data_quality']['kicker_current_team_verified'] is True
    assert len(body['features']) == 82


def test_ambiguous_or_unknown_team_names_are_422(client):
    for team, text in (('Los Angeles', 'Ambiguous'), ('Springfield Isotopes', 'Unknown')):
        r = client.post('/api/analyze', json=PICK | {'team': team})
        assert r.status_code == 422 and r.json()['error']['code'] == 'INVALID_TEAM'
        assert text in r.json()['error']['message']


def test_missing_matchup_returns_upcoming_suggestions(client):
    r = client.post('/api/analyze', json=PICK | {'opponent': 'DAL', 'week': None})
    assert r.status_code == 404 and r.json()['error']['code'] == 'GAME_NOT_FOUND'
    assert [g['display_name'] for g in r.json()['error']['suggestions']][:2] == ['Cowboys @ Texans', 'Rams @ Eagles']
    r = client.post('/api/analyze', json=PICK | {'week': None})
    assert r.status_code == 409 and r.json()['error']['code'] == 'GAME_AMBIGUOUS'


def test_opponent_roster_listing_is_a_clear_conflict(client):
    r = client.post('/api/analyze', json=PICK | {'kicker': ELLIOTT})
    assert r.status_code == 409 and r.json()['error']['code'] == 'KICKER_TEAM_MISMATCH'
    assert 'PHI' in r.json()['error']['message']


@needs_model
def test_recent_analyses_list_open_and_never_rerun(client, monkeypatch):
    first = client.post('/api/analyze', json=PICK).json()
    client.post('/api/analyze', json=PICK | {'line': 2.5, 'side': 'under', 'odds': 150})
    listing = client.get('/api/analyses').json()['analyses']
    assert len(listing) == 2 and {a['kicker'] for a in listing} == {'Harrison Mevis'}
    item = next(a for a in listing if a['line'] == 1.5)
    assert item['matchup'] == 'Rams @ Eagles' and item['probability'] == first['prop']['model_side_probability']

    def forbidden(*a, **k):
        raise AssertionError('providers or engine must not run when opening a stored analysis')
    monkeypatch.setattr(web, 'analyze_current_prop', forbidden)
    monkeypatch.setattr(web, 'load_current_sources', forbidden)
    stored = client.get(f"/api/analyses/{item['id']}").json()
    assert stored['stored']['id'] == item['id']
    assert stored['prediction'] == first['prediction'] and stored['features'] == first['features']


def test_stored_analysis_ids_are_confined(client, tmp_path):
    (tmp_path.parent/'secret.json').write_text('{"x": 1}')
    for bad in ('abc', '..%2F..%2Fsecret', '%2e%2e', 'G'*64, '../' + 'a'*61):
        r = client.get(f'/api/analyses/{bad}')
        assert r.status_code in (404, 422) and 'secret' not in r.text
    assert client.get('/api/analyses/' + 'a'*64).json()['error']['code'] == 'ANALYSIS_NOT_FOUND'
    # A non-directory entry with a valid-looking name is ignored by the listing.
    (tmp_path/('b'*64)).write_text('not a directory')
    assert client.get('/api/analyses').json() == {'analyses': []}


def test_frozen_7a_fixture_prediction_is_bit_identical():
    from kickedge.inference.engine import analyze
    from kickedge.web.artifact import ensure_model
    ensure_model(Path('.'))
    snapshot = json.loads(Path('examples/inference_demo_2024.json').read_text())
    r = analyze(snapshot, 2.5, 'over', 119)
    assert r['prediction']['expected_xpm'] == 1.774292350651335
    assert r['prop']['p_over'] == 0.2625051047104534
    assert r['prediction']['distribution']['tail_probability'] == 5.379582350402028e-08
    assert r['model']['artifact_sha256'] == 'c2f8f5ff00712546023b769a7c8374478399b7d00e343dc4e5e928c10977f0d0'


def test_launcher_is_local_simple_and_safe():
    raw = Path('start-kickedge.bat').read_bytes()
    assert b'\r\n' in raw and b'\n' not in raw.replace(b'\r\n', b'')  # CRLF for cmd.exe
    lines = raw.decode('ascii').lower().splitlines()
    text = '\n'.join(line for line in lines if not line.lstrip().startswith('rem '))  # commands only
    assert 'cd /d "%~dp0"' in text and '.venv\\scripts\\python.exe" -m kickedge.web --open' in text
    assert 'press ctrl+c to stop kickedge' in text
    for banned in ('taskkill', 'reg ', 'sc ', 'runas', 'schtasks', 'netsh', 'del ', 'rmdir', 'shutdown',
                   'executionpolicy', 'setx', 'startup', 'curl', 'http://0.0.0.0'):
        assert banned not in text, banned
    readme = Path('README.md').read_text(encoding='utf-8')
    assert 'start-kickedge.bat' in readme and '127.0.0.1:8000' in readme


def test_entrypoint_handles_an_occupied_port(monkeypatch, capsys):
    from kickedge.web import __main__ as launcher
    opened, served = [], []
    monkeypatch.setattr(launcher.webbrowser, 'open', opened.append)
    monkeypatch.setattr(launcher.uvicorn, 'run', lambda *a, **k: served.append(k))
    monkeypatch.setattr(launcher, 'port_free', lambda host, port: False)
    monkeypatch.setattr(launcher, 'kickedge_running', lambda url: True)
    assert launcher.main(['--open']) == 0 and opened == ['http://127.0.0.1:8000'] and served == []
    assert 'may already be running' in capsys.readouterr().out
    monkeypatch.setattr(launcher, 'kickedge_running', lambda url: False)
    assert launcher.main([]) == 1 and served == []
    assert 'already used by another program' in capsys.readouterr().err
    monkeypatch.setattr(launcher, 'port_free', lambda host, port: True)
    assert launcher.main([]) == 0 and served[0]['host'] == '127.0.0.1' and served[0]['port'] == 8000
    assert 'Ctrl+C to stop KickEdge' in capsys.readouterr().out
