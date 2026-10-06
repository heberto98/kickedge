"""Tracking & monitoring interface in headless Edge/Chrome: Refresh results, auto-settled
picks with their result source, data freshness, the Performance tab with calibration,
prediction movement, line comparison, and a 390 px mobile layout without page overflow."""
from datetime import timedelta
from html import unescape
import json
from pathlib import Path
import re
import shutil

import pytest

from kickedge.current import movement
from kickedge.web import app as web
from test_monitoring_api import client as api_client  # noqa: F401  (fixture reuse)
from test_multi_frontend import FAKE_FETCH
from test_performance_monitoring import stored
from test_tracking import KICKOFF, analysis
from test_web_frontend import dump_dom
from test_web_polish import client, needs_model  # noqa: F401  (fixture reuse)

STATIC = Path(web.__file__).with_name('static')
CLOCK = """
const RealDate = Date, pinned = new RealDate('%s').getTime();
window.Date = class extends RealDate { constructor(...a) { super(...(a.length ? a : [pinned])); } static now() { return pinned; } };
window.addEventListener('error', (e) => { window.parent.postMessage({ error: String(e.message) }, '*'); });
"""


# The app runs in an iframe of the exact viewport size (headless windows have a minimum
# width); its driver posts the collected values to this outer page, which is dumped.
OUTER = """<!doctype html><html><body><iframe src="index.html" width="%d" height="%d" style="border:0"></iframe><script>
addEventListener('message', (e) => { for (const [k, v] of Object.entries(e.data)) document.body.dataset[k] = JSON.stringify(v);
  document.body.dataset.done = '1'; });
</script></body></html>"""
REPORT = """
const report = (out) => { window.parent.postMessage(JSON.parse(JSON.stringify(out)), '*'); };
"""


def page(tmp_path, routes, driver, window_size):
    for name in ('app.js', 'style.css'):
        shutil.copy(STATIC/name, tmp_path/name)
    html = (STATIC/'index.html').read_text(encoding='utf-8')
    html = html.replace('<script src="/static/app.js" defer></script>', '').replace('/static/style.css', 'style.css')
    html = html.replace('</body>', f'<script>window.__routes = {json.dumps(routes)};{FAKE_FETCH}{REPORT}</script>'
                                   f'<script src="app.js"></script><script>{driver}</script></body>')
    (tmp_path/'index.html').write_text(html, encoding='utf-8')
    (tmp_path/'outer.html').write_text(OUTER % window_size, encoding='utf-8')
    dom = dump_dom(tmp_path, tmp_path/'outer.html', budget_ms=15000, window_size=(window_size[0] + 100, window_size[1] + 100))
    assert 'data-done="1"' in dom, 'driver did not finish'
    return dom


def data(dom, name):
    match = re.search(f'data-{name}="([^"]*)"', dom)
    return json.loads(unescape(match.group(1))) if match else None


TRACKING_FLOW = """
const text = (id) => document.getElementById(id).innerText;
window.addEventListener('load', async () => {
  await sleep(300);
  const out = { freshness: text('freshness-body'), status: text('refresh-status'), warnings: text('refresh-warnings'),
                tracked: text('tracked-body') };
  const settled = [...document.querySelectorAll('#tracked-body .tracked-item')].find((li) => li.textContent.includes('SETTLED'));
  const details = [...settled.querySelectorAll('details')].find((d) => d.querySelector('summary').textContent === 'Prediction movement');
  details.open = true;
  details.dispatchEvent(new Event('toggle'));
  await sleep(150);
  out.movement = details.innerText;
  document.getElementById('refresh-results').click();
  await sleep(200);
  out.refreshCalls = window.__refreshCalls;
  document.getElementById('tab-performance').click();
  await sleep(300);
  out.performance = document.getElementById('perf-body').textContent;   // includes collapsed sections
  out.openSections = [...document.querySelectorAll('#perf-body details.perf-section')].map((d) => d.open);
  out.calibrationDots = document.querySelectorAll('#perf-body svg.chart circle').length;
  out.overflow = document.documentElement.scrollWidth - window.innerWidth;
  out.width = window.innerWidth;
  report(out);
});
"""


def tracking_routes(c):
    c.post('/api/tracked', json={'analysis_id': 'b' * 64})
    c.post('/api/tracked-multi', json={'analysis_id': 'c' * 64})
    other = c.root/'analyses'/('e' * 64)
    other.mkdir()
    other.joinpath('analysis.json').write_text(json.dumps(analysis(kicker_id='00-7', odds=1.8)))
    unresolved = c.post('/api/tracked', json={'analysis_id': 'e' * 64}).json()['pick']['tracking_id']
    stored(c.root/'analyses', 'd' * 64, '2026-10-09T09:00:00+00:00', .66, snapshot='2', features={'kicker_xpm_last_3': 2.7})
    c.state['now'] = KICKOFF + timedelta(hours=5)
    refresh = c.post('/api/tracking/refresh-results').json()
    assert len(refresh['report']['settled']) == 2 and refresh['report']['unresolved'][0]['tracking_id'] == unresolved
    single = c.get('/api/tracked').json()
    routes = {'POST /api/tracking/refresh-results': {'status': 200, 'body': refresh},
              '/api/tracked': {'status': 200, 'body': single},
              '/api/tracked-multi': {'status': 200, 'body': c.get('/api/tracked-multi').json()},
              '/api/performance': {'status': 200, 'body': c.get('/api/performance').json()},
              '/api/monitoring': {'status': 200, 'body': c.get('/api/monitoring').json()},
              '/api/analyses': {'status': 200, 'body': {'analyses': []}},
              '/api/games': {'status': 503, 'body': {'error': {'code': 'NFL_SOURCE_UNAVAILABLE', 'message': 'x'}}}}
    for record in single['open'] + single['settled']:
        tid = record['pick']['tracking_id']
        routes[f'/api/prediction-movement/{tid}'] = {'status': 200, 'body': c.get(f'/api/prediction-movement/{tid}').json()}
    return routes, c.state['now']


COUNT_REFRESH = """
window.__refreshCalls = 0;
const baseFetch = window.fetch;
window.fetch = (url, opts) => { if (url.startsWith('/api/tracking/refresh-results')) window.__refreshCalls += 1; return baseFetch(url, opts); };
"""


@pytest.mark.parametrize('window_size', [(1280, 900), (390, 844)])
def test_refresh_results_tracker_freshness_and_performance(api_client, tmp_path, window_size):  # noqa: F811
    routes, now = tracking_routes(api_client)
    dom = page(tmp_path, routes, CLOCK % now.isoformat() + COUNT_REFRESH + TRACKING_FLOW, window_size)
    assert data(dom, 'error') is None
    fresh = data(dom, 'freshness')
    assert 'null' not in fresh
    for text in ('NFL data fetched', '2 h ago', 'Latest completed game', '2026_06_DAL_HOU', 'Feature cutoff policy',
                 '24 h release gate', 'KickEdge V1 · phase5-c2f8f5ff0071'):
        assert text in fresh, text
    assert data(dom, 'status') == '2 results settled automatically from nflverse.'
    assert 'AUTO_SETTLEMENT_UNRESOLVED' in data(dom, 'warnings') and 'kicker_not_in_completed_game' in data(dom, 'warnings')
    tracked = data(dom, 'tracked')
    assert 'SETTLED — WIN' in tracked and 'Result source: Auto — nflverse' in tracked and 'OPEN — enter the result' in tracked
    assert 'MODEL MOVEMENT' in data(dom, 'movement') and 'Change from first: +4.0 pp' in data(dom, 'movement')
    assert data(dom, 'refresh-calls') == 2                                  # on open and on the button
    perf = data(dom, 'performance')
    for text in ('Singles tracked', 'Singles settled', 'Multi legs settled', 'Single tracked picks — 1 graded',
                 'Calibration', 'Small sample', 'By line', 'Over 1.5 XPM', 'By week', '2026 · Week 6',
                 'Multi legs may be correlated.', 'Combined probability assumes independence.',
                 'Forward validation reference: 84 / 150 observations at last V2 audit.', 'Monitoring status'):
        assert text.lower() in perf.lower(), text                          # h3 headings render uppercase
    assert data(dom, 'calibration-dots') >= 1
    assert data(dom, 'open-sections') == [True, False, False, False]          # compact: only Singles open
    assert data(dom, 'width') == window_size[0] and data(dom, 'overflow') <= 0     # no horizontal page scroll


SINGLE_FLOW = """
window.addEventListener('load', async () => {
  await sleep(150);
  render(window.__routes['POST /api/analyze'].body);
  await sleep(150);
  const result = document.getElementById('result');
  const order = [...result.children].slice(0, 5).map((el) => el.className);
  const lines = result.querySelector('details.lines');
  lines.open = true;
  lines.dispatchEvent(new Event('toggle'));
  await sleep(150);
  report({ order, movement: result.querySelector('section.movement').innerText,
         movementHidden: result.querySelector('section.movement').hidden, lines: lines.innerText,
         analysedRow: lines.querySelector('tr.sel').innerText, overflow: document.documentElement.scrollWidth - window.innerWidth });
});
"""


@needs_model
@pytest.mark.parametrize('window_size', [(1280, 900), (390, 844)])
def test_single_result_shows_movement_and_line_comparison(client, tmp_path, window_size):  # noqa: F811
    body = {'kicker': 'Harrison Mevis', 'game_id': '2026_05_LA_PHI', 'line': 1.5, 'side': 'over', 'decimal_odds': 1.3}
    result = client.post('/api/analyze', json=body).json()
    aid = result['stored']['id']
    history = tmp_path/'history'
    stored(history, 'a' * 64, '2026-10-03T10:00:00+00:00', .642, snapshot='1')
    stored(history, 'b' * 64, '2026-10-04T14:00:00+00:00', .668, snapshot='2', features={'kicker_xpm_last_3': 2.7,
                                                                                       'offense_touchdowns_per_game_before': 2.1})
    moves = movement.movement(history, ('2026_06_DAL_HOU', '00-1', 'over', 1.5))
    routes = {'POST /api/analyze': {'status': 200, 'body': result},
              f'/api/prediction-movement/{aid}': {'status': 200, 'body': moves},
              f'/api/line-comparison/{aid}': {'status': 200, 'body': client.get(f'/api/line-comparison/{aid}').json()},
              '/api/analyses': {'status': 200, 'body': {'analyses': []}}}
    out_dir = tmp_path/'page'
    out_dir.mkdir()
    dom = page(out_dir, routes, CLOCK % '2026-10-08T12:00:00+00:00' + SINGLE_FLOW, window_size)
    assert data(dom, 'error') is None
    order = data(dom, 'order')
    assert order[0].startswith('card hero') and order[1] == 'card track-bar' and order[2] == 'card movement' and order[3] == 'card lines'
    assert data(dom, 'movement-hidden') is False
    move = data(dom, 'movement')
    assert 'Prediction movement' in move and '64.2%' in move and '66.8%' in move and 'Inputs that changed (1)' in move
    assert 'not an explanation' in move and 'caused' not in move.lower()
    lines = data(dom, 'lines')
    assert 'Fair odds Over' in lines and '0.5' in lines and '4.5' in lines
    probability = f"{100 * result['prop']['p_over']:.1f}%"
    assert data(dom, 'analysed-row').startswith('1.5 (analysed)') and probability in data(dom, 'analysed-row')
    assert data(dom, 'overflow') <= 0
