"""Phase 7C interface: static page structure plus real app.js rendering in headless Edge/Chrome."""
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest
from fastapi.testclient import TestClient

from kickedge.web import app as web
from test_web_api import PICK, client  # noqa: F401  (fixture reuse)

STATIC = Path(web.__file__).with_name('static')


class Fields(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.labels, self.scripts = set(), set(), []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.add(a['id'])
        if tag == 'label' and 'for' in a:
            self.labels.add(a['for'])
        if tag == 'script':
            self.scripts.append(a)


def test_page_loads_with_labelled_form():
    r = TestClient(web.app).get('/')
    assert r.status_code == 200 and 'text/html' in r.headers['content-type']
    p = Fields()
    p.feed(r.text)
    required = {'kicker', 'team', 'opponent', 'line', 'odds', 'side-over', 'side-under',
                'season', 'week', 'game_id', 'over_odds', 'under_odds', 'submit', 'result', 'error'}
    assert required <= p.ids
    assert {'kicker', 'team', 'opponent', 'line', 'odds', 'over_odds', 'under_odds'} <= p.labels
    assert all(s.get('src', '').startswith('/static/') for s in p.scripts)  # no inline or third-party script
    for banned in ('Find winning', 'Beat the', 'Guaranteed', 'LOCK', 'BET NOW', 'Kelly', 'bankroll'):
        assert banned not in r.text
    assert 'not betting recommendations' in r.text


def _browser():
    for path in (shutil.which('msedge'), shutil.which('chrome'), shutil.which('chromium'),
                 shutil.which('google-chrome'),
                 r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                 r'C:\Program Files\Microsoft\Edge\Application\msedge.exe'):
        if path and os.path.exists(path):
            return path
    pytest.skip('No headless Chromium-based browser available')


def dump_dom(tmp_path, page, *, budget_ms=None, timeout=120, window_size=None):
    """Run headless Chromium once and return the serialized DOM.

    Each launch gets its own profile directory. Chromium is a per-profile
    singleton: when another process still holds the same --user-data-dir (a stale
    run reusing --basetemp), the new process forwards its command line, exits with
    code 21 and prints nothing. A unique profile makes every run independent.
    """
    profile = tempfile.mkdtemp(prefix='edge-profile-', dir=tmp_path)
    command = [_browser(), '--headless=new', '--disable-gpu', '--no-first-run', f'--user-data-dir={profile}']
    if budget_ms:
        command.append(f'--virtual-time-budget={budget_ms}')
    if window_size:
        command.append(f'--window-size={window_size[0]},{window_size[1]}')
    out = subprocess.run(command + ['--dump-dom', Path(page).as_uri()], capture_output=True, text=True,
                         encoding='utf-8', errors='replace', timeout=timeout)
    assert '<body' in out.stdout, (f'Browser returned no DOM (exit code {out.returncode}; 21 means the profile '
                                   f'was held by another browser process). stderr: {out.stderr[-500:]}')
    return out.stdout


def _render(tmp_path, script):
    """Load the real app.js in a harness page and dump the DOM after it runs."""
    harness = tmp_path/'harness.html'
    shutil.copy(STATIC/'app.js', tmp_path/'app.js')
    harness.write_text('<!doctype html><html><head><meta charset="utf-8"></head><body>'
                       '<form id="pick"><button id="submit"></button><p id="status"></p></form>'
                       '<div id="error" hidden></div><div id="result" hidden></div>'
                       '<script src="app.js"></script><script>' + script + '</script></body></html>', encoding='utf-8')
    return dump_dom(tmp_path, harness, timeout=90)


def test_result_renders_probability_distribution_warnings_and_inputs(client, tmp_path):  # noqa: F811
    r = client.post('/api/analyze', json=PICK).json()
    dom = _render(tmp_path, 'render(' + json.dumps(r) + ');')
    side_probability = f"{100*r['prop']['model_side_probability']:.1f}%"
    assert f'id="pick-probability">{side_probability}<' in dom
    assert 'Over 2.5 XPM' in dom and 'Expected XPM' in dom and 'P(Over)' in dom
    assert 'P(Push)' not in dom  # half-point line has no push
    assert 'XPM distribution' in dom and 'role="img"' in dom
    assert 'View all 82 model inputs' in dom and 'kicker_xpm_last_5' in dom
    assert '<dt>XPM season-to-date</dt>' in dom and '[object' not in dom
    assert 'Data quality' in dom and 'Not verified' in dom
    for warning in r['data_quality']['warnings'][:3]:
        assert warning.replace('&', '&amp;') in dom
    assert 'Market data unavailable.' not in dom and 'Market context not requested.' in dom
    assert 'Context only — not currently used by the probability model' in dom
    assert 'not a betting recommendation' in dom


def test_integer_line_shows_push_and_conditional_basis(client, tmp_path):  # noqa: F811
    r = client.post('/api/analyze', json=PICK | {'line': 2, 'include_market': True}).json()
    dom = _render(tmp_path, 'render(' + json.dumps(r) + ');')
    assert 'P(Push)' in dom and 'conditional on no push' in dom
    assert 'Market data unavailable.' in dom  # optional market failure does not break the result


def test_error_state_renders(tmp_path):
    dom = _render(tmp_path, "showError('KICKER_AMBIGUOUS','Kicker identity ambiguous; provide stable ID');")
    assert 'Ambiguous kicker' in dom and 'stable player ID' in dom and 'KICKER_AMBIGUOUS' in dom


def test_market_context_table_renders(client, tmp_path):  # noqa: F811
    r = client.post('/api/analyze', json=PICK).json()
    r['data_quality']['market_requested'] = True
    r['context']['market'] = {'available': True, 'quotes': [{'provenance': {'bookmaker': 'fanduel'}, 'values': {
        'game_spread': 3.5, 'game_total': 39.5, 'moneyline_team': 150.0, 'moneyline_opponent': -178.0}}]}
    dom = _render(tmp_path, 'render(' + json.dumps(r) + ');')
    assert '<td>fanduel</td><td>3.5</td><td>39.5</td><td>+150</td><td>-178</td>' in dom
