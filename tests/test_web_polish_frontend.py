"""Polish pass, interface: the real index.html + app.js driven in headless Edge/Chrome
with a fake fetch that serves real API responses (no server, no network)."""
from html import unescape
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from kickedge.web import app as web
from polish_data import MEVIS
from test_web_frontend import _browser
from test_web_polish import client, needs_model  # noqa: F401  (fixture reuse)

STATIC = Path(web.__file__).with_name('static')
BODY = {'kicker': MEVIS, 'team': 'LA', 'opponent': 'PHI', 'game_id': '2026_05_LA_PHI', 'season': 2026, 'week': 5,
        'line': 1.5, 'side': 'over', 'decimal_odds': 1.3, 'include_weather': True, 'include_market': False,
        'refresh_data': False}

FAKE_FETCH = """
window.__posted = null;
window.fetch = async (url, opts) => {
  const path = url.split('?')[0];
  const key = (opts && opts.method === 'POST' ? 'POST ' : '') + path;
  if (opts && opts.body) window.__posted = JSON.parse(opts.body);
  const r = window.__routes[key] || { status: 404, body: { error: { code: 'NOT_FOUND', message: 'missing ' + key } } };
  return { ok: r.status === 200, status: r.status, json: async () => r.body };
};
"""

PICK_FLOW = """
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const key = (el, k) => el.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true }));
const type = (el, text) => { el.focus(); el.value = text; el.dispatchEvent(new Event('input', { bubbles: true })); };
const opts = (id) => [...document.querySelectorAll('#' + id + ' [role=option] .opt-main')].map((e) => e.textContent).join('|');
window.addEventListener('load', async () => {
  await sleep(100);
  const game = document.getElementById('game');
  type(game, 'ram');
  document.body.dataset.gameOptions = opts('game-list');
  document.body.dataset.activeGame = game.getAttribute('aria-activedescendant') || '';
  key(game, 'Escape');
  document.body.dataset.afterEscape = document.getElementById('game-list').hidden ? 'closed' : 'open';
  type(game, 'ram');
  key(game, 'Enter');
  await sleep(100);
  const kicker = document.getElementById('kicker');
  type(kicker, 'harri');
  document.body.dataset.kickerOptions = opts('kicker-list');
  key(kicker, 'ArrowDown');
  key(kicker, 'Enter');
  await sleep(20);
  document.body.dataset.teamSelectors = String(document.querySelectorAll('input[name=kteam], #kteam-field').length);
  document.getElementById('line').value = '1.5';
  document.getElementById('odds').value = '1.30';
  document.getElementById('submit').click();
  await sleep(200);
  document.body.dataset.posted = JSON.stringify(window.__posted);
  document.body.dataset.done = '1';
});
"""


def _page(tmp_path, routes, driver):
    for name in ('app.js', 'style.css'):
        shutil.copy(STATIC/name, tmp_path/name)
    html = (STATIC/'index.html').read_text(encoding='utf-8')
    html = html.replace('<script src="/static/app.js" defer></script>', '').replace('/static/style.css', 'style.css')
    scripts = (f'<script>window.__routes = {json.dumps(routes)};{FAKE_FETCH}</script>'
               f'<script src="app.js"></script><script>{driver}</script>')
    html = html.replace('</body>', scripts + '</body>')
    page = tmp_path/'index.html'
    page.write_text(html, encoding='utf-8')
    out = subprocess.run([_browser(), '--headless=new', '--disable-gpu', '--no-first-run',
                          f'--user-data-dir={tmp_path/"profile"}', '--virtual-time-budget=15000',
                          '--dump-dom', page.as_uri()],
                         capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    assert '<body' in out.stdout, out.stderr[-500:]
    return out.stdout


def _data(dom, name):
    match = re.search(f'data-{name}="([^"]*)"', dom)
    return unescape(match.group(1)) if match else None


def _routes(client):  # noqa: F811
    analysis = client.post('/api/analyze', json=BODY).json()
    return {'/api/games': {'status': 200, 'body': client.get('/api/games').json()},
            '/api/games/2026_05_LA_PHI/kickers': {'status': 200, 'body': client.get('/api/games/2026_05_LA_PHI/kickers').json()},
            '/api/analyses': {'status': 200, 'body': client.get('/api/analyses').json()},
            'POST /api/analyze': {'status': 200, 'body': analysis}}, analysis


@needs_model
def test_game_and_kicker_pickers_drive_a_full_analysis(client, tmp_path):  # noqa: F811
    routes, analysis = _routes(client)
    dom = _page(tmp_path, routes, PICK_FLOW)
    assert _data(dom, 'done') == '1'
    assert _data(dom, 'game-options') == 'Rams @ Eagles|Rams @ Jaguars|Eagles @ Rams'
    assert _data(dom, 'active-game') == 'game-list-0' and _data(dom, 'after-escape') == 'closed'
    assert _data(dom, 'kicker-options') == 'Harrison Mevis' and _data(dom, 'team-selectors') == '0'
    assert json.loads(_data(dom, 'posted'))['team'] == 'LA'  # derived from the kicker, never asked
    assert json.loads(_data(dom, 'posted')) == BODY
    probability = f"{100*analysis['prop']['model_side_probability']:.1f}%"
    assert f'id="pick-probability">{probability}<' in dom
    assert 'Harrison Mevis' in dom and 'Rams @ Eagles' in dom and 'Over 1.5 XPM' in dom
    assert 'Line 1.5' in dom and 'dist-row win' in dom and 'dist-row loss' in dom and 'dist-row push' not in dom
    assert '<span class="qk">Kicker team</span><span class="qv">Verified</span>' in dom
    assert 'Current team affiliation verified.' in dom
    assert 'XPM per game, last 3' in dom and 'vs season' in dom
    assert 'View all 82 model inputs' in dom and '[object' not in dom
    assert 'Harrison Mevis — Over 1.5 · 1.30' in dom  # recent analyses list
    assert '<section class="card guide" id="guide" aria-labelledby="guide-h" hidden=""' in dom


MANUAL_FLOW = """
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
window.addEventListener('load', async () => {
  await sleep(100);
  document.getElementById('kicker').value = '  Harrison   Mevis ';
  document.getElementById('line').value = '2';
  document.getElementById('odds').value = '2.15';
  document.getElementById('submit').click();
  await sleep(50);
  document.body.dataset.firstError = (document.querySelector('.field-error') || {}).textContent || '';
  document.getElementById('team').value = 'LAR';
  document.getElementById('opponent').value = 'phi';
  document.getElementById('week').value = '5';
  document.getElementById('submit').click();
  await sleep(200);
  document.body.dataset.posted = JSON.stringify(window.__posted);
});
"""


@needs_model
def test_manual_fallback_keeps_typed_teams_and_kicker(client, tmp_path):  # noqa: F811
    routes, _ = _routes(client)
    routes['/api/games'] = {'status': 503, 'body': {'error': {'code': 'NFL_SOURCE_UNAVAILABLE', 'message': 'x'}}}
    dom = _page(tmp_path, routes, MANUAL_FLOW)
    assert _data(dom, 'first-error') == 'Choose an upcoming game, or enter the teams under Advanced.'
    posted = json.loads(_data(dom, 'posted'))
    assert posted['team'] == 'LAR' and posted['opponent'] == 'phi' and posted['week'] == 5
    assert posted['kicker'] == 'Harrison Mevis' and posted['line'] == 2 and posted['decimal_odds'] == 2.15
    assert 'game_id' not in posted
    assert 'Upcoming games unavailable' in dom


@needs_model
def test_stored_analysis_banner_and_error_suggestions(client, tmp_path):  # noqa: F811
    routes, analysis = _routes(client)
    stored = analysis | {'stored': {'id': 'a'*64, 'saved_at': '2026-10-08T12:00:00+00:00'}}
    suggestions = client.post('/api/analyze', json=BODY | {'game_id': None, 'week': None, 'opponent': 'DAL'}).json()['error']['suggestions']
    driver = f"""window.addEventListener('load', () => {{
      render({json.dumps(stored)});
      showError('GAME_NOT_FOUND', 'No matching future game', {json.dumps(suggestions)});
    }});"""
    dom = _page(tmp_path, routes, driver)
    assert 'Saved analysis from' in dom and 'nothing was re-run' in dom
    assert 'No upcoming game found for that matchup' in dom
    assert 'Upcoming games involving these teams:' in dom and 'Cowboys @ Texans — Week 5' in dom
