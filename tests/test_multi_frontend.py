"""Final polish, interface: tabs, multiple selections and statistical feedback, driven
in headless Edge/Chrome with the real index.html + app.js and real API responses."""
from html import unescape
import json
from pathlib import Path
import re
import shutil
import subprocess

from kickedge.web import app as web
from polish_data import ELLIOTT, MEVIS
from test_decimal_multi import client  # noqa: F401  (fixture reuse)
from test_web_frontend import _browser

STATIC = Path(web.__file__).with_name('static')

# Fake fetch: a route may hold a list of responses served in order (last one repeats).
FAKE_FETCH = """
window.__posted = [];
window.fetch = async (url, opts) => {
  const key = (opts && opts.method === 'POST' ? 'POST ' : '') + url.split('?')[0];
  if (opts && opts.body) window.__posted.push(JSON.parse(opts.body));
  let r = window.__routes[key];
  if (Array.isArray(r)) r = r.length > 1 ? r.shift() : r[0];
  r = r || { status: 404, body: { error: { code: 'NOT_FOUND', message: 'missing ' + key } } };
  return { ok: r.status === 200, status: r.status, json: async () => r.body };
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const key = (el, k) => el.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true }));
const type = (el, text) => { el.focus(); el.value = text; el.dispatchEvent(new Event('input', { bubbles: true })); };
const done = (data) => { for (const [k, v] of Object.entries(data)) document.body.dataset[k] = JSON.stringify(v); document.body.dataset.done = '1'; };
"""


def page(tmp_path, routes, driver):
    for name in ('app.js', 'style.css'):
        shutil.copy(STATIC/name, tmp_path/name)
    html = (STATIC/'index.html').read_text(encoding='utf-8')
    html = html.replace('<script src="/static/app.js" defer></script>', '').replace('/static/style.css', 'style.css')
    html = html.replace('</body>', f'<script>window.__routes = {json.dumps(routes)};{FAKE_FETCH}</script>'
                                   f'<script src="app.js"></script><script>{driver}</script></body>')
    (tmp_path/'index.html').write_text(html, encoding='utf-8')
    out = subprocess.run([_browser(), '--headless=new', '--disable-gpu', '--no-first-run',
                          f'--user-data-dir={tmp_path/"profile"}', '--virtual-time-budget=20000',
                          '--dump-dom', (tmp_path/'index.html').as_uri()],
                         capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    assert '<body' in out.stdout, out.stderr[-500:]
    assert 'data-done="1"' in out.stdout, 'driver did not finish'
    return out.stdout


def data(dom, name):
    match = re.search(f'data-{name}="([^"]*)"', dom)
    return json.loads(unescape(match.group(1))) if match else None


def leg(kicker, game_id, odds, line=1.5, side='over'):
    return {'kicker': kicker, 'game_id': game_id, 'line': line, 'side': side, 'decimal_odds': odds}


def routes(client, multi_body=None):  # noqa: F811
    r = {'/api/games': {'status': 200, 'body': client.get('/api/games').json()},
         '/api/analyses': {'status': 200, 'body': client.get('/api/analyses').json()}}
    for game in ('2026_05_LA_PHI', '2026_06_PHI_DET'):
        r[f'/api/games/{game}/kickers'] = {'status': 200, 'body': client.get(f'/api/games/{game}/kickers').json()}
    if multi_body:
        r['POST /api/analyze-multi'] = {'status': 200, 'body': client.post('/api/analyze-multi', json=multi_body).json()}
    return r


def test_tabs_and_add_remove_selections(client, tmp_path):  # noqa: F811
    driver = """window.addEventListener('load', async () => {
      await sleep(50);
      const single = document.getElementById('tab-single');
      single.focus(); key(single, 'ArrowRight');
      const afterArrow = [document.getElementById('tab-multi').getAttribute('aria-selected'), document.getElementById('panel-multi').hidden, document.getElementById('panel-single').hidden, document.activeElement.id];
      const legends = () => [...document.querySelectorAll('#legs > fieldset > legend')].map((l) => l.textContent);
      const removeVisible = () => [...document.querySelectorAll('.leg-remove')].filter((b) => !b.hidden).length;
      const start = [legends(), removeVisible()];
      document.getElementById('add-leg').click();
      const third = document.querySelectorAll('#legs > fieldset')[2];
      third.querySelector('input[id$="-line"]').value = '2.5';
      third.querySelector('input[id$="-odds"]').value = '1.75';
      document.querySelectorAll('.leg-remove')[1].click();
      const afterRemove = [legends(), document.querySelectorAll('#legs > fieldset')[1].querySelector('input[id$="-line"]').value,
                           document.querySelectorAll('#legs > fieldset')[1].querySelector('input[id$="-odds"]').value, removeVisible()];
      for (let i = 0; i < 12; i++) document.getElementById('add-leg').click();
      const full = [legends().length, document.getElementById('add-leg').disabled, document.getElementById('leg-count').textContent];
      key(document.getElementById('tab-multi'), 'Home');
      done({ afterArrow, start, afterRemove, full, backHome: document.getElementById('tab-single').getAttribute('aria-selected') });
    });"""
    dom = page(tmp_path, routes(client), driver)
    assert data(dom, 'after-arrow') == ['true', False, True, 'tab-multi']
    assert data(dom, 'start') == [['Selection 1', 'Selection 2'], 0]  # minimum 2: no remove buttons
    assert data(dom, 'after-remove') == [['Selection 1', 'Selection 2'], '2.5', '1.75', 0]  # renumbered, data kept
    assert data(dom, 'full') == [10, True, '10 of 10 selections (maximum reached)']
    assert data(dom, 'back-home') == 'true'


MULTI_FLOW = """window.addEventListener('load', async () => {
  await sleep(100);
  document.getElementById('tab-multi').click();
  const legsEl = () => document.querySelectorAll('#legs > fieldset');
  async function fill(i, gameQuery, kickerQuery, line, odds) {
    const card = legsEl()[i];
    const game = card.querySelector('input[id$="-game"]');
    type(game, gameQuery); key(game, 'Enter');
    await sleep(100);
    const kicker = card.querySelector('input[id$="-kicker"]');
    type(kicker, kickerQuery); key(kicker, 'Enter');
    await sleep(20);
    card.querySelector('input[id$="-line"]').value = line;
    card.querySelector('input[id$="-odds"]').value = odds;
  }
  await fill(0, 'rams eagles', 'harri', '1.5', '1.30');
  await fill(1, 'lions', 'jake', '1.5', '1.40');
  const teamSelectors = document.querySelectorAll('input[name=kteam], #kteam-field').length;
  document.getElementById('multi-submit').click();
  await sleep(300);
  done({ posted: window.__posted[0], teamSelectors: String(teamSelectors) });
});"""


def test_multi_flow_posts_derived_teams_and_renders_combined(client, tmp_path):  # noqa: F811
    body = {'selections': [leg(MEVIS, '2026_05_LA_PHI', 1.3), leg(ELLIOTT, '2026_06_PHI_DET', 1.4)]}
    rec = client.post('/api/analyze-multi', json=body).json()
    r = routes(client) | {'POST /api/analyze-multi': {'status': 200, 'body': rec}}
    dom = page(tmp_path, r, MULTI_FLOW)
    posted = data(dom, 'posted')
    assert data(dom, 'team-selectors') == '0'
    assert [s['kicker'] for s in posted['selections']] == [MEVIS, ELLIOTT]
    assert [(s['team'], s['opponent'], s['game_id']) for s in posted['selections']] == [('LA', 'PHI', '2026_05_LA_PHI'), ('PHI', 'DET', '2026_06_PHI_DET')]
    assert [s['decimal_odds'] for s in posted['selections']] == [1.3, 1.4] and posted['include_weather'] is True
    c = rec['combined']
    assert 'Multi-selection summary' in dom and f'<span class="stat-value">{c["combined_decimal_odds"]:.2f}</span>' in dom
    assert f'{100*c["implied_probability"]:.1f}%' in dom and f'{100*c["model_probability"]:.1f}%' in dom
    assert 'Independence approximation' in dom and 'Approximate combined probability assuming independent selections' in dom
    assert 'Same-game selections' not in dom
    first = rec['selections'][0]['result']
    assert 'Harrison Mevis · Over 1.5 XPM' in dom and 'Jake Elliott · Over 1.5 XPM' in dom
    assert f'{100*first["prop"]["model_side_probability"]:.1f}%' in dom and f'{100/1.3:.1f}%' in dom
    assert 'Statistical feedback' in dom and 'Assuming independent selections' in dom


def test_same_game_failed_leg_and_push_rendering(client, tmp_path):  # noqa: F811
    same = client.post('/api/analyze-multi', json={'selections': [
        leg(MEVIS, '2026_05_LA_PHI', 1.3), leg(ELLIOTT, '2026_05_LA_PHI', 2.1, line=2)]}).json()
    failed = client.post('/api/analyze-multi', json={'selections': [
        leg(MEVIS, '2026_05_LA_PHI', 1.3), leg('Nobody Here', '2026_06_PHI_DET', 1.4)]}).json()
    driver = f"""window.addEventListener('load', async () => {{
      await sleep(50);
      renderMulti({json.dumps(same)});
      const sameDom = document.getElementById('multi-result').innerHTML;
      renderMulti({json.dumps(failed)});
      done({{ sameDom, failedDom: document.getElementById('multi-result').innerHTML }});
    }});"""
    dom = page(tmp_path, routes(client), driver)
    same_dom, failed_dom = data(dom, 'same-dom'), data(dom, 'failed-dom')
    assert 'Same-game selections' in same_dom and 'These selections belong to the same game' in same_dom
    assert 'may be' in same_dom and 'materially inaccurate' in same_dom
    assert 'Same game as selection 2' in same_dom and 'Same game as selection 1' in same_dom
    assert 'Integer lines can push' in same_dom and 'No-loss probability' in same_dom
    assert 'Selection 2 failed: KICKER_NOT_FOUND' in failed_dom and 'Combined analysis unavailable' in failed_dom
    assert 'Combined decimal odds' not in failed_dom


def test_single_feedback_values_and_direction(client, tmp_path):  # noqa: F811
    base = client.post('/api/analyze', json={'kicker': MEVIS, 'game_id': '2026_05_LA_PHI', 'line': 1.5,
                                              'side': 'over', 'decimal_odds': 1.3}).json()

    def variant(implied, model):
        r = json.loads(json.dumps(base))
        r['market']['implied_probability'], r['prop']['model_side_probability'] = implied, model
        r['market']['decimal_odds'] = 1 / implied
        r['analysis']['edge_raw_pp'] = 100 * (model - implied)
        return r
    driver = f"""window.addEventListener('load', async () => {{
      await sleep(50);
      const out = [];
      for (const r of [{json.dumps(variant(.60, .65))}, {json.dumps(variant(.70, .64))}, {json.dumps(variant(.60, .605))}]) {{
        render(r);
        out.push([document.querySelector('.hero .feedback p').textContent, document.querySelector('.stat.diff .stat-value').textContent,
                  document.querySelector('.stat.diff').className]);
      }}
      done({{ out }});
    }});"""
    (up, up_pp, up_cls), (down, down_pp, down_cls), (close, close_pp, close_cls) = data(page(tmp_path, routes(client), driver), 'out')
    assert up_pp == '+5.0 pp' and 'implies 60.0%' in up and 'estimates 65.0%' in up and '5.0 percentage points higher' in up and 'higher' in up_cls
    assert down_pp == '-6.0 pp' and 'implies 70.0%' in down and 'estimates 64.0%' in down and '6.0 percentage points lower' in down and 'lower' in down_cls
    assert close_pp == '+0.5 pp' and 'very close' in close and 'close' in close_cls
    assert 'decimal odds 1.67' in up  # decimal display with two decimals


def test_team_is_asked_only_when_it_cannot_be_derived(client, tmp_path):  # noqa: F811
    unresolved = client.post('/api/analyze', json={'kicker': 'Former Kicker', 'game_id': '2026_05_LA_PHI', 'line': 1.5,
                                                    'side': 'over', 'decimal_odds': 1.3})
    assert unresolved.status_code == 422
    ok = client.post('/api/analyze', json={'kicker': 'Former Kicker', 'game_id': '2026_05_LA_PHI', 'team': 'LA',
                                            'opponent': 'PHI', 'line': 1.5, 'side': 'over', 'decimal_odds': 1.3}).json()
    r = routes(client) | {'POST /api/analyze': [{'status': 422, 'body': unresolved.json()}, {'status': 200, 'body': ok}]}
    driver = """window.addEventListener('load', async () => {
      await sleep(100);
      const game = document.getElementById('game');
      type(game, 'rams eagles'); key(game, 'Enter');
      await sleep(100);
      document.getElementById('kicker').value = 'Former Kicker';
      document.getElementById('kicker').dispatchEvent(new Event('input', { bubbles: true }));
      document.getElementById('line').value = '1.5';
      document.getElementById('odds').value = '1.30';
      document.getElementById('submit').click();
      await sleep(150);
      const choice = [...document.querySelectorAll('#error .team-choice button')].map((b) => b.textContent);
      document.querySelectorAll('#error .team-choice button')[0].click();
      await sleep(200);
      done({ choice, posted: window.__posted, hero: (document.querySelector('#hero-h') || {}).textContent || '' });
    });"""
    dom = page(tmp_path, r, driver)
    assert data(dom, 'choice') == ['Kicks for Rams', 'Kicks for Eagles']
    first, second = data(dom, 'posted')
    assert 'team' not in first and first['kicker'] == 'Former Kicker' and first['game_id'] == '2026_05_LA_PHI'
    assert (second['team'], second['opponent']) == ('LA', 'PHI')
    assert data(dom, 'hero') == 'Former Kicker'
