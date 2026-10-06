"""Tracked multis in headless Edge/Chrome: Track multi, panel, partial and full settlement,
leg correction. Panel states come from the real multi tracker; the page clock is pinned."""
from datetime import datetime, timedelta
import json

from kickedge.current import multi_tracking as mt
from polish_data import ELLIOTT, MEVIS, NOW
from test_decimal_multi import client  # noqa: F401  (fixture reuse)
from test_multi_frontend import FAKE_FETCH, data, leg, routes, page  # noqa: F401

CLOCK = """
const RealDate = Date;
window.__pinned = new RealDate('%s').getTime();
window.Date = class extends RealDate { constructor(...a) { super(...(a.length ? a : [window.__pinned])); } static now() { return window.__pinned; } };
"""

FLOW = """
const panel = () => document.getElementById('tracked-multi-body').innerText;
const visibleForm = (selector) => [...document.querySelectorAll('#tracked-multi-body ' + selector)].find((f) => !f.hidden);
window.addEventListener('error', (e) => { document.body.dataset.error = JSON.stringify(String(e.message)); });
window.addEventListener('load', async () => {
  await sleep(150);
  const out = { empty: panel() };
  renderMulti(window.__routes['POST /api/analyze-multi'].body);
  const bar = document.querySelector('#multi-result .track-bar');
  out.barAfterSummary = bar.previousElementSibling.classList.contains('summary');
  bar.querySelector('button').click();
  await sleep(150);
  out.trackStatus = bar.querySelector('[role=status]').textContent;
  out.multiTab = document.getElementById('tracked-tab-multi').getAttribute('aria-pressed');
  out.open = panel();
  window.__pinned = new RealDate('BETWEEN').getTime();   // after the first kickoff only
  await loadTrackedMulti();
  out.firstStarted = panel();
  let form = visibleForm('form.settle-form');
  form.querySelector('input').value = '2';
  form.requestSubmit();
  await sleep(150);
  out.partial = panel();
  window.__pinned = new RealDate('AFTER').getTime();     // after the second kickoff
  await loadTrackedMulti();
  form = visibleForm('form.settle-form');
  form.querySelector('input').value = '3';
  form.requestSubmit();
  await sleep(150);
  out.settled = panel();
  const second = [...document.querySelectorAll('#tracked-multi-body .multi-legs > li')][1];
  [...second.querySelectorAll('button')].find((b) => b.textContent === 'Correct result').click();
  form = [...second.querySelectorAll('form.settle-form')].find((f) => !f.hidden);
  form.querySelector('input[type=number]').value = '1';
  form.querySelector('input[type=text]').value = 'Typo';
  window.confirm = () => true;
  form.requestSubmit();
  await sleep(150);
  document.querySelectorAll('#tracked-multi-body details.history').forEach((d) => { d.open = true; });
  out.corrected = panel();
  out.posted = window.__posted;
  done(out);
});
"""


def test_track_multi_partial_full_settlement_and_correction(client, tmp_path):  # noqa: F811
    rec = client.post('/api/analyze-multi', json={'selections': [leg(MEVIS, '2026_05_LA_PHI', 1.3),
                                                                 leg(ELLIOTT, '2026_06_PHI_DET', 1.4)]}).json()
    store = tmp_path/'tracked_multi'
    tracked = mt.track(store, rec, rec['stored']['id'], NOW)
    tid, (first, second) = tracked['manifest']['tracking_id'], tracked['manifest']['legs']
    between = datetime.fromisoformat(first['kickoff']) + timedelta(hours=4)
    after = datetime.fromisoformat(second['kickoff']) + timedelta(hours=4)
    states = [mt.list_tracked(tmp_path/'none')] + [mt.list_tracked(store)] * 2
    mt.settle_leg(store, tid, 1, 2, between)
    states += [mt.list_tracked(store)] * 2
    mt.settle_leg(store, tid, 2, 3, after)
    states.append(mt.list_tracked(store))
    mt.correct_leg(store, tid, 2, 1, after, 'Typo')
    states.append(mt.list_tracked(store))
    base = f'POST /api/tracked-multi/{tid}/legs'
    r = routes(client) | {'POST /api/analyze-multi': {'status': 200, 'body': rec},
                          '/api/tracked-multi': [{'status': 200, 'body': s} for s in states],
                          'POST /api/tracked-multi': {'status': 200, 'body': tracked},
                          f'{base}/1/settle': {'status': 200, 'body': {}}, f'{base}/2/settle': {'status': 200, 'body': {}},
                          f'{base}/2/correct': {'status': 200, 'body': {}}}
    driver = CLOCK % NOW.isoformat() + FLOW.replace('BETWEEN', between.isoformat()).replace('AFTER', after.isoformat())
    dom = page(tmp_path, r, driver)
    assert data(dom, 'error') is None                                    # no script error during the flow
    assert data(dom, 'bar-after-summary') is True and data(dom, 'multi-tab') == 'true'
    assert data(dom, 'empty') == 'No tracked multis yet.'
    assert data(dom, 'track-status').startswith('Tracked: 2-leg multi frozen at')
    opened = data(dom, 'open')
    for text in ('2-leg multi', 'Combined odds: 1.82', 'KickEdge approximate probability:', 'Status: OPEN',
                 'Harrison Mevis', 'Over 1.5 XPM', 'OPEN — awaiting kickoff'):
        assert text in opened, text
    assert 'OPEN — enter the result' not in opened                       # nothing can be settled before kickoff
    started = data(dom, 'first-started')
    assert started.count('OPEN — enter the result') == 1 and started.count('OPEN — awaiting kickoff') == 1
    assert 'Status: PARTIALLY SETTLED (1/2 legs)' in data(dom, 'partial') and 'Actual XPM: 2 · WIN' in data(dom, 'partial')
    settled = data(dom, 'settled')
    for text in ('Status: SETTLED — ALL LEGS WON', 'Independent-game multis: 1 tracked · 1 settled', 'All-win Brier',
                 'Combined probabilities assume independence.', 'Individual legs (source: multi legs)', 'Actual XPM: 3 · WIN'):
        assert text in settled, text
    corrected = data(dom, 'corrected')
    for text in ('Status: SETTLED — HAS LOSS', 'Actual XPM: 1 · LOSS', 'Corrected', 'Original: 3 XPM — WIN',
                 'Corrected: 1 XPM — LOSS · Reason: Typo'):
        assert text in corrected, text
    assert data(dom, 'posted') == [{'analysis_id': rec['stored']['id']}, {'actual_xpm': 2}, {'actual_xpm': 3},
                                   {'actual_xpm': 1, 'confirm': True, 'reason': 'Typo'}]
