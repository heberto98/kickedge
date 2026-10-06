"""Performance dashboard, prediction movement, line comparison and monitoring snapshots."""
from datetime import timedelta
import json

import pytest

from kickedge.current import monitoring, movement, multi_tracking as mt, performance, tracking
from kickedge.inference.odds import analyze_prop
from test_auto_settlement import bundle, event, label
from test_multi_tracking import K2, leg, multi
from test_tracking import AFTER, AID, BEFORE, analysis


def single(base, actual, **kwargs):
    tid = tracking.track(base, analysis(**kwargs), AID, BEFORE)['pick']['tracking_id']
    if actual is not None:
        tracking.settle(base, tid, actual, AFTER)
    return tid


def board(tmp_path):
    return performance.dashboard(tracking.list_tracked(tmp_path/'s'), mt.list_tracked(tmp_path/'m'))


# ---------- performance ----------

def test_global_metrics_buckets_lines_and_pushes(tmp_path):
    base = tmp_path/'s'
    single(base, 3, p_side=.75)                                   # Over 1.5 WIN, bucket 70–80%
    single(base, 1, p_side=.72, odds=1.4)                         # Over 1.5 LOSS, bucket 70–80%
    single(base, 1, side='under', line=2.5, p_side=.55)           # Under 2.5 WIN, bucket 50–60%
    single(base, 2, line=2, p_side=.45, p_push=.25)               # Over 2 PUSH: excluded
    single(base, None, line=3.5, p_side=.2)                       # open
    s = board(tmp_path)['single']
    assert (s['tracked'], s['settled'], s['pushes'], s['graded'], s['small_sample']) == (5, 4, 1, 3, True)
    assert s['average_probability'] == pytest.approx((.75 + .72 + .55) / 3)
    assert s['observed_frequency'] == pytest.approx(2 / 3)
    assert s['brier_score'] == pytest.approx(((.75 - 1) ** 2 + .72 ** 2 + (.55 - 1) ** 2) / 3)
    assert [(b['bucket'], b['graded']) for b in s['calibration']] == [('50–60%', 1), ('70–80%', 2)]
    assert all(b['small_sample'] for b in s['calibration'])
    assert [(r['line'], r['graded']) for r in s['by_line']] == [('Over 1.5', 2), ('Under 2.5', 1)]     # no empty rows
    assert [(r['range'], r['graded']) for r in s['by_range']] == [('50–60%', 1), ('70–80%', 2)]
    assert [(w['season'], w['week'], w['graded']) for w in s['by_week']] == [(2026, 6, 3)]


def test_corrected_results_and_single_vs_multi_separation(tmp_path):
    tid = single(tmp_path/'s', 1, p_side=.8)                      # LOSS, then corrected to WIN
    tracking.correct(tmp_path/'s', tid, 3, AFTER)
    record = mt.track(tmp_path/'m', multi(), AID, BEFORE)         # legs .8 (Over 1.5) and .5 (Over 2.5)
    for number, actual in ((1, 2), (2, 1)):
        mt.settle_leg(tmp_path/'m', record['manifest']['tracking_id'], number, actual, K2 + timedelta(hours=4))
    same = mt.track(tmp_path/'m', multi(leg(odds=1.25), leg(kicker='Ka\'imi Fairbairn', kicker_id='00-9', side='under',
                                                             line=2.5, p_side=.5)), AID, BEFORE)
    for number, actual in ((1, 2), (2, 2)):
        mt.settle_leg(tmp_path/'m', same['manifest']['tracking_id'], number, actual, AFTER)
    d = board(tmp_path)
    assert d['single']['graded'] == 1 and d['single']['observed_frequency'] == 1          # corrected result counts once
    assert d['multi_legs']['graded'] == 4 and d['multi_legs']['source'] == 'multi_leg'
    assert d['all_individual']['graded'] == 5 and d['all_individual']['note'] == 'Multi legs may be correlated.'
    assert d['counts'] == {'singles_tracked': 1, 'singles_settled': 1, 'multi_legs_tracked': 4, 'multi_legs_settled': 4,
                           'multis_tracked': 2, 'multis_settled': 2, 'unreadable': 0}
    ind, cor = d['multis']['independent_games'], d['multis']['same_game_correlated']
    assert (ind['settled'], ind['has_loss'], cor['settled'], cor['all_legs_won']) == (1, 1, 1, 1)
    assert d['combined_note'] == 'Combined probability assumes independence.'


# ---------- prediction movement ----------

def stored(directory, analysis_id, generated, p_side=.7, odds=1.5, snapshot='1', features=None, **kwargs):
    a = analysis(p_side=p_side, odds=odds, **kwargs)
    a['provenance'] |= {'analysis_generated_at': generated, 'feature_snapshot_sha256': snapshot * 64}
    a['features'] = features or {'kicker_xpm_last_3': 2.3, 'offense_touchdowns_per_game_before': 2.1}
    (directory/analysis_id).mkdir(parents=True)
    (directory/analysis_id/'analysis.json').write_text(json.dumps(a))
    return a


def test_movement_history_order_deltas_and_input_changes(tmp_path):
    d = tmp_path/'analyses'
    stored(d, 'c' * 64, '2026-10-05T09:00:00+00:00', .659, snapshot='3',
           features={'kicker_xpm_last_3': 2.7, 'offense_touchdowns_per_game_before': 2.4})
    stored(d, 'a' * 64, '2026-10-03T10:00:00+00:00', .642, snapshot='1')
    stored(d, 'b' * 64, '2026-10-04T14:00:00+00:00', .668, snapshot='2',
           features={'kicker_xpm_last_3': 2.7, 'offense_touchdowns_per_game_before': 2.1})
    stored(d, 'd' * 64, '2026-10-04T15:00:00+00:00', .668, snapshot='2', odds=1.6)    # same inputs, new price
    stored(d, 'e' * 64, '2026-10-04T16:00:00+00:00', .5, line=2.5)                     # other line
    stored(d, 'f' * 64, '2026-10-04T16:00:00+00:00', .5, side='under')                 # other side
    files = {p: p.read_bytes() for p in d.rglob('*.json')}
    m = movement.movement(d, ('2026_06_DAL_HOU', '00-1', 'over', 1.5))
    assert m['analyses'] == 4 and [p['analysis_id'][0] for p in m['model_movement']] == ['a', 'b', 'c']
    assert m['change_from_first_pp'] == pytest.approx(1.7) and m['change_from_previous_pp'] == pytest.approx(-.9)
    assert m['model_movement'][1]['input_changes'] == [{'feature': 'kicker_xpm_last_3', 'before': 2.3, 'after': 2.7}]
    assert m['model_movement'][2]['input_changes'] == [
        {'feature': 'offense_touchdowns_per_game_before', 'before': 2.1, 'after': 2.4}]
    assert [p['decimal_odds'] for p in m['price_movement']] == [1.5, 1.6, 1.5]
    text = json.dumps(m).lower()
    assert not any(word in text for word in ('caused', 'because', 'due to', 'driven by', 'led to'))
    assert {p: p.read_bytes() for p in d.rglob('*.json')} == files                     # read only


def test_single_analysis_has_no_movement(tmp_path):
    stored(tmp_path, 'a' * 64, '2026-10-03T10:00:00+00:00')
    m = movement.movement(tmp_path, ('2026_06_DAL_HOU', '00-1', 'over', 1.5))
    assert m['analyses'] == 1 and len(m['model_movement']) == 1 and m['price_movement'] == []
    assert 'change_from_first_pp' not in m


# ---------- line comparison ----------

@pytest.mark.parametrize('mean', [0.8, 1.774292350651335, 2.4, 3.9])
def test_line_comparison_matches_the_single_engine(mean):
    rows = movement.compare_lines(mean)
    assert [r['line'] for r in rows] == [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5]
    for r in rows:
        assert r['p_over'] + r['p_under'] + r['p_push'] == pytest.approx(1, abs=1e-12)
        assert (r['p_push'] > 0) == float(r['line']).is_integer()
        for side in ('over', 'under'):
            direct = analyze_prop(mean, r['line'], side, 2.0, odds_format='decimal')
            assert (r['p_over'], r['p_under'], r['p_push']) == (direct['prop']['p_over'], direct['prop']['p_under'],
                                                                  direct['prop']['p_push'])
            assert r[f'fair_decimal_{side}'] == direct['analysis']['fair_odds']['decimal']
    integer = next(r for r in rows if r['line'] == 2.0)
    assert integer['fair_basis'] == 'conditional on no push'
    assert integer['fair_decimal_over'] == pytest.approx((integer['p_over'] + integer['p_under']) / integer['p_over'])


def test_line_comparison_reproduces_the_analysed_line():
    a = analysis()
    direct = analyze_prop(2.3, 1.5, 'over', 1.5, odds_format='decimal')['prop']
    a['prop'] |= {k: direct[k] for k in ('p_over', 'p_under', 'p_push', 'model_side_probability', 'model_probability_conditional')}
    c = movement.line_comparison(a)
    row = next(r for r in c['lines'] if r['line'] == 1.5)
    assert (row['p_over'], row['p_under'], row['p_push']) == (a['prop']['p_over'], a['prop']['p_under'], a['prop']['p_push'])
    assert c['analysed_line'] == 1.5 and c['expected_xpm'] == 2.3


# ---------- monitoring ----------

def fresh_bundle(rows=1, now=AFTER):
    b = bundle(*[event(f'2026_06_T{i:02}_HOU', [label(kicker_id=f'00-{i}', xpm=2)]) for i in range(rows)])
    b['schedules'] = [{'game_id': g['game_id'], 'week': 6, 'scheduled_kickoff': g['source']['actual_kickoff']} for g in b['games']]
    return b


def test_freshness_reports_source_age_completion_and_warnings():
    b = fresh_bundle(2)
    b['schedules'].append({'game_id': '2026_06_LATE_GAME', 'week': 6, 'scheduled_kickoff': (AFTER - timedelta(hours=5)).isoformat()})
    b['schedules'].append({'game_id': '2026_05_X_Y', 'week': 5, 'scheduled_kickoff': (AFTER - timedelta(days=7)).isoformat()})
    b['games'].append(event('2026_05_X_Y', [label()]))
    f = monitoring.freshness(b, AFTER)
    assert f['age_hours'] == pytest.approx(1) and f['latest_completed_week'] == 5 and f['completed_games'] == 3
    assert f['model']['artifact_sha256'].startswith('c2f8f5ff') and '24 h' in f['feature_cutoff_policy']
    assert [w['code'] for w in f['warnings']] == ['COMPLETED_GAME_NOT_YET_IN_SOURCE']
    assert f['warnings'][0]['game_ids'] == ['2026_06_LATE_GAME']
    stale = monitoring.freshness(None, AFTER, fetched_at=(AFTER - timedelta(hours=30)).isoformat(), failure='offline')
    assert [w['code'] for w in stale['warnings']] == ['SOURCE_UNAVAILABLE', 'DATA_TOO_STALE']
    assert [w['code'] for w in monitoring.freshness(None, AFTER, fetched_at=(AFTER - timedelta(hours=7)).isoformat())['warnings']] == ['SOURCE_OLDER_THAN_6H']


def test_snapshots_are_written_only_when_content_changes(tmp_path):
    d = board(tmp_path)
    forward = monitoring.forward_status(monitoring.label_eligible_count(fresh_bundle(3)))
    content = monitoring.snapshot_content(d, monitoring.freshness(fresh_bundle(3), AFTER), forward)
    first, written = monitoring.record_snapshot(tmp_path/'mon', content, AFTER)
    again, written_again = monitoring.record_snapshot(tmp_path/'mon', content, AFTER + timedelta(minutes=5))
    assert written and not written_again and again == first and monitoring.snapshot_count(tmp_path/'mon') == 1
    assert first['model']['artifact_sha256'] == 'c2f8f5ff00712546023b769a7c8374478399b7d00e343dc4e5e928c10977f0d0'
    assert first['forward_validation']['label_eligible_completed_observations'] == 3
    single(tmp_path/'s', 3)                                                   # a new settlement changes the content
    changed = monitoring.snapshot_content(board(tmp_path), monitoring.freshness(fresh_bundle(3), AFTER), forward)
    latest, written_new = monitoring.record_snapshot(tmp_path/'mon', changed, AFTER + timedelta(hours=1))
    assert written_new and monitoring.snapshot_count(tmp_path/'mon') == 2 and monitoring.latest_snapshot(tmp_path/'mon') == latest


def test_forward_reference_and_threshold_without_evaluating_v2(monkeypatch):
    from kickedge.v2 import forward as v2_forward

    def forbidden(*args, **kwargs):
        raise AssertionError('V2 evaluation must never run from monitoring')
    monkeypatch.setattr(v2_forward, 'reveal', forbidden)
    monkeypatch.setattr(v2_forward, 'forward_rows', forbidden)
    below = monitoring.forward_status(monitoring.label_eligible_count(fresh_bundle(149)))
    assert below['message'] == 'Forward validation reference: 84 / 150 observations at last V2 audit.'
    assert below['label_eligible_completed_observations'] == 149 and not below['threshold_reached'] and 'threshold_message' not in below
    b = fresh_bundle(150)
    b['games'][0]['kickers'].append(label(kicker_id='00-x', statistical_label_usable=False))   # excluded by the label rule
    reached = monitoring.forward_status(monitoring.label_eligible_count(b))
    assert reached['label_eligible_completed_observations'] == 150 and reached['threshold_reached']
    assert reached['threshold_message'].startswith('V2 re-evaluation threshold reached')
    assert monitoring.forward_status(None)['threshold_reached'] is False
