"""Tracked picks interface in headless Edge/Chrome: Track pick, panel, settle form."""
import json

from polish_data import NOW
from test_web_polish import client, needs_model  # noqa: F401  (fixture reuse)
from test_web_polish_frontend import _data, _page, _routes

TID = 'e' * 64


def pick(tracking_id, kickoff, side='over', line=1.5, probability=.784, odds=1.3):
    return {'tracking_id': tracking_id, 'kicker': 'Brandon Aubrey', 'team': 'DAL', 'opponent': 'HOU', 'side': side,
            'line': line, 'decimal_odds': odds, 'kickedge_probability': probability, 'kickoff': kickoff,
            'created_at': '2026-10-04T12:00:00+00:00'}


LISTING = {'summary': {'tracked': 3, 'open': 2, 'settled': 1, 'pushes': 0, 'graded': 1, 'unreadable': 0,
                       'average_probability': .784, 'observed_frequency': 1.0, 'brier_score': .046656},
           'open': [{'pick': pick('f' * 64, '2026-12-01T18:00:00+00:00'), 'settlement': None, 'status': 'OPEN'},
                    {'pick': pick(TID, '2026-09-01T18:00:00+00:00', 'under', 2.5, .55, 1.8), 'settlement': None, 'status': 'OPEN'}],
           'settled': [{'pick': pick('d' * 64, '2026-09-01T17:00:00+00:00'), 'status': 'SETTLED', 'corrected': True,
                        'settlement': {'settled_at': '2026-09-02T00:00:00+00:00', 'actual_xpm': 3, 'result': 'WIN',
                                       'corrected_at': '2026-09-03T00:00:00+00:00'},
                        'original_settlement': {'settled_at': '2026-09-02T00:00:00+00:00', 'actual_xpm': 1, 'result': 'LOSS'},
                        'corrections': [{'sequence': 1, 'corrected_at': '2026-09-03T00:00:00+00:00', 'previous_actual_xpm': 1,
                                         'previous_result': 'LOSS', 'new_actual_xpm': 3, 'new_result': 'WIN',
                                         'reason': 'Entered wrong result'}]}]}

FLOW = """
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
window.addEventListener('load', async () => {
  await sleep(150);
  document.body.dataset.panel = document.getElementById('tracked-body').innerText;
  render(window.__routes['POST /api/analyze'].body);
  const button = [...document.querySelectorAll('.track-bar button')][0];
  document.body.dataset.trackBelowHero = String(button.closest('section').previousElementSibling.classList.contains('hero'));
  button.click();
  await sleep(150);
  document.body.dataset.trackPosted = JSON.stringify(window.__posted);
  document.body.dataset.trackStatus = document.querySelector('.track-bar [role=status]').textContent;
  const form = document.querySelector('.settle-form');
  form.querySelector('input').value = '2.5';
  form.requestSubmit();
  await sleep(50);
  document.body.dataset.badSettle = String(form.querySelector('input').checkValidity()) + '|' + JSON.stringify(window.__posted);
  form.querySelector('input').value = '2';
  form.requestSubmit();
  await sleep(150);
  document.body.dataset.settlePosted = JSON.stringify(window.__posted);
  const settledItem = [...document.querySelectorAll('.tracked-item')].find((li) => li.textContent.includes('SETTLED'));
  const history = settledItem.querySelector('details.history');
  history.open = true;
  document.body.dataset.history = history.innerText;
  const toggle = [...settledItem.querySelectorAll('button')].find((b) => b.textContent === 'Correct result');
  toggle.click();
  const correct = settledItem.querySelector('form.settle-form');
  document.body.dataset.correctVisible = String(!correct.hidden) + '|' + toggle.getAttribute('aria-expanded');
  correct.querySelector('input[type=number]').value = '2';
  correct.querySelector('input[type=text]').value = 'Typo';
  const prompts = [];
  window.confirm = (msg) => { prompts.push(msg); return false; };
  const before = JSON.stringify(window.__posted);
  correct.requestSubmit();
  await sleep(50);
  document.body.dataset.cancelled = correct.querySelector('[role=status]').textContent + '|' + String(JSON.stringify(window.__posted) === before);
  window.confirm = (msg) => { prompts.push(msg); return true; };
  correct.requestSubmit();
  await sleep(150);
  document.body.dataset.prompt = prompts[0];
  document.body.dataset.correctPosted = JSON.stringify(window.__posted);
  document.body.dataset.done = '1';
});
"""

# Pins the page clock (before DOMContentLoaded) so kickoff checks do not depend on the machine date.
CLOCK = """
const RealDate = Date, pinned = new RealDate('%s').getTime();
window.Date = class extends RealDate { constructor(...a) { super(...(a.length ? a : [pinned])); } static now() { return pinned; } };
"""


@needs_model
def test_track_button_panel_and_settle_form(client, tmp_path):  # noqa: F811
    routes, analysis = _routes(client)
    frozen = {'pick': pick(TID, analysis['game']['kickoff']) | {'kickedge_probability': analysis['prop']['model_side_probability']},
              'settlement': None, 'status': 'OPEN', 'already_tracked': False}
    routes |= {'/api/tracked': {'status': 200, 'body': LISTING}, 'POST /api/tracked': {'status': 200, 'body': frozen},
               f'POST /api/tracked/{TID}/settle': {'status': 200, 'body': LISTING['settled'][0]},
               f"POST /api/tracked/{'d' * 64}/correct": {'status': 200, 'body': LISTING['settled'][0]}}
    dom = _page(tmp_path, routes, CLOCK % NOW.isoformat() + FLOW)
    assert _data(dom, 'done') == '1'
    panel = _data(dom, 'panel')
    for text in ('Tracked', 'Settled', 'Open', 'Avg. probability', '78.4%', 'Observed freq.', '100.0%', 'Brier score', '0.047',
                 'Sample: 1 settled pick. Small samples can be noisy', 'DAL vs HOU · Over 1.5 XPM · 1.30', 'KickEdge: 78.4%',
                 'OPEN — awaiting kickoff', 'OPEN — enter the result', 'SETTLED — WIN', 'Corrected',
                 'Actual XPM: 3 · Result: WIN', 'View correction history', 'Correct result'):
        assert text in panel, text
    assert _data(dom, 'track-below-hero') == 'true'
    assert json.loads(_data(dom, 'track-posted')) == {'analysis_id': analysis['stored']['id']}
    assert _data(dom, 'track-status').startswith('Tracked: Over 1.5 XPM frozen at')
    assert _data(dom, 'bad-settle') == 'false|' + _data(dom, 'track-posted')   # 2.5 blocked; nothing new was sent
    assert json.loads(_data(dom, 'settle-posted')) == {'actual_xpm': 2}
    history = _data(dom, 'history')
    assert 'Original: 1 XPM — LOSS' in history and 'Corrected: 3 XPM — WIN · Reason: Entered wrong result' in history
    assert _data(dom, 'correct-visible') == 'true|true'
    assert _data(dom, 'cancelled') == 'Correction cancelled; nothing changed.|true'          # declined: nothing sent
    assert _data(dom, 'prompt') == 'Correct this settled result?\nThe original settlement will remain in the audit history.'
    assert json.loads(_data(dom, 'correct-posted')) == {'actual_xpm': 2, 'confirm': True, 'reason': 'Typo'}
