"""Automatic settlement from the verified nflverse bundle: only completed games and
reconciled labels of the same kicker settle; everything else stays open."""
from datetime import timedelta
import json

import pytest

from kickedge.current import auto_settlement as auto, multi_tracking as mt, tracking
from test_multi_tracking import K1, K2, leg, multi
from test_tracking import AFTER, AID, BEFORE, KICKOFF, analysis

FETCHED = (AFTER - timedelta(hours=1)).isoformat()


def label(kicker_id='00-1', team='DAL', xpm=3, **changes):
    return {'kicker_id': kicker_id, 'team': team, 'xpa': xpm, 'xpm': xpm, 'statistical_label_usable': True,
            'label_status': 'agreed', 'id_in_players': True, 'schedule_identity_ok': True, 'target_season_eligible': True,
            'label_evidence': 'two_source_agreement' if xpm else auto.VERIFIED_ZERO} | changes


def event(game_id='2026_06_DAL_HOU', rows=None, kickoff=KICKOFF, sha='e'):
    return {'game_id': game_id, 'season': 2026, 'kickers': [label()] if rows is None else rows,
            'source': {'event_completed': True, 'actual_kickoff': kickoff.isoformat(), 'sha256': sha * 64}}


def bundle(*events):
    return {'season': 2026, 'games': list(events), 'schedules': [], 'bundle_id': 'f' * 64,
            'sources': [{'dataset': 'pbp', 'fetched_at': FETCHED}, {'dataset': 'player_stats', 'fetched_at': FETCHED}]}


@pytest.fixture
def dirs(tmp_path):
    return {'single': tmp_path/'tracked', 'multi': tmp_path/'tracked_multi', 'log': tmp_path/'monitoring'/auto.LOG}


def track_single(dirs, **kwargs):
    return tracking.track(dirs['single'], analysis(**kwargs), AID, BEFORE)['pick']['tracking_id']


def run(dirs, source, now=AFTER, failures=None):
    bundles = {} if source is None else {2026: source}
    return auto.settle_open(dirs['single'], dirs['multi'], bundles, failures or {}, now, dirs['log'])


def log_lines(dirs):
    return [json.loads(line) for line in dirs['log'].read_text().splitlines()] if dirs['log'].exists() else []


def test_completed_game_auto_settles_single_with_source_metadata(dirs):
    tid = track_single(dirs)                                         # Over 1.5
    pick_bytes = (dirs['single']/tid/'pick.json').read_bytes()
    report = run(dirs, bundle(event(rows=[label(xpm=3)])))
    assert [(s['tracking_id'], s['actual_xpm'], s['result']) for s in report['settled']] == [(tid, 3, 'WIN')]
    record = tracking.load(dirs['single'], tid)
    original = record['original_settlement']
    assert original['settlement_source'] == 'auto_nflverse' and original['source_game_id'] == '2026_06_DAL_HOU'
    assert original['source_hash'] == 'e' * 64 and original['source_fetched_at'] == FETCHED
    assert original['auto_settled_at'] == AFTER.isoformat() and record['result_source'] == 'auto_nflverse'
    assert (dirs['single']/tid/'pick.json').read_bytes() == pick_bytes
    with pytest.raises(tracking.TrackingError, match='already settled'):    # manual Settle is blocked afterwards
        tracking.settle(dirs['single'], tid, 1, AFTER)
    again = run(dirs, bundle(event(rows=[label(xpm=3)])))
    assert again['settled'] == [] and len(log_lines(dirs)) == 1           # idempotent: one settlement, one log line


def test_settlement_log_records_each_auto_settlement(dirs):
    tid = track_single(dirs)
    run(dirs, bundle(event(rows=[label(xpm=1)])))
    (entry,) = log_lines(dirs)
    assert entry == {'timestamp': AFTER.isoformat(), 'type': 'single', 'tracking_id': tid, 'leg': None,
                     'game_id': '2026_06_DAL_HOU', 'kicker': 'Brandon Aubrey', 'kicker_id': '00-1', 'actual_xpm': 1,
                     'result': 'LOSS', 'source_hash': 'e' * 64, 'source_fetched_at': FETCHED}
    assert 'PARLAY' not in dirs['log'].read_text() and 'api' not in dirs['log'].read_text().lower()


def test_incomplete_game_stays_open_and_warns_only_when_overdue(dirs):
    tid = track_single(dirs)
    soon = run(dirs, bundle(), now=KICKOFF + timedelta(hours=2))
    assert [p['tracking_id'] for p in soon['pending']] == [tid] and soon['warnings'] == []
    late = run(dirs, bundle(event('2026_06_NYG_WAS')), now=KICKOFF + timedelta(hours=5))
    assert [w['code'] for w in late['warnings']] == ['TRACKED_GAME_PENDING_IN_SOURCE']
    assert tracking.load(dirs['single'], tid)['status'] == 'OPEN' and log_lines(dirs) == []
    assert run(dirs, bundle(event()), now=BEFORE)['checked'] == 0               # before kickoff nothing is checked


def test_source_failure_changes_nothing(dirs):
    tid = track_single(dirs)
    report = run(dirs, None, failures={2026: 'NFL data could not be loaded'})
    assert report['settled'] == [] and report['warnings'][0]['code'] == 'SOURCE_UNAVAILABLE'
    assert tracking.load(dirs['single'], tid)['status'] == 'OPEN' and not (dirs['single']/tid/'settlement.json').exists()


@pytest.mark.parametrize('rows,reason', [
    ([label(), label()], 'kicker_ambiguous'),
    ([label(kicker_id='00-7')], 'kicker_not_in_completed_game'),
    ([], 'kicker_not_in_completed_game'),
    ([label(team='HOU')], 'kicker_team_mismatch'),
    ([label(statistical_label_usable=False, label_status='source_discrepancy', xpm=None)], 'label_not_usable:source_discrepancy'),
    ([label(id_in_players=False)], 'label_not_usable:agreed'),
    ([label(xpm=0, label_evidence='quarantined')], 'zero_not_verified')])
def test_unresolved_kicker_stays_open(dirs, rows, reason):
    tid = track_single(dirs)
    report = run(dirs, bundle(event(rows=rows)))
    assert report['settled'] == [] and report['unresolved'][0]['reason'] == reason
    assert report['warnings'] == [{'code': 'AUTO_SETTLEMENT_UNRESOLVED', 'detail': reason, 'type': 'single',
                                   'tracking_id': tid, 'leg': None, 'game_id': '2026_06_DAL_HOU',
                                   'kicker': 'Brandon Aubrey', 'kicker_id': '00-1'}]
    assert tracking.load(dirs['single'], tid)['status'] == 'OPEN'


def test_verified_zero_settles(dirs):
    tid = track_single(dirs, side='under', line=0.5)
    report = run(dirs, bundle(event(rows=[label(xpm=0)])))
    assert report['settled'][0]['result'] == 'WIN' and tracking.load(dirs['single'], tid)['settlement']['actual_xpm'] == 0


def test_manual_settlement_is_never_overwritten(dirs):
    tid = track_single(dirs)
    tracking.settle(dirs['single'], tid, 1, AFTER)
    before = (dirs['single']/tid/'settlement.json').read_bytes()
    report = run(dirs, bundle(event(rows=[label(xpm=3)])))
    assert report['settled'] == [] and (dirs['single']/tid/'settlement.json').read_bytes() == before
    (warning,) = report['warnings']
    assert warning['code'] == 'MANUAL_RESULT_DIFFERS_FROM_SOURCE' and (warning['recorded_xpm'], warning['source_xpm']) == (1, 3)
    assert run(dirs, bundle(event(rows=[label(xpm=1)])))['warnings'] == []         # agreement: no warning
    assert tracking.load(dirs['single'], tid)['result_source'] == 'manual'


def test_correction_overrides_an_auto_settlement(dirs):
    tid = track_single(dirs)
    run(dirs, bundle(event(rows=[label(xpm=3)])))
    record = tracking.correct(dirs['single'], tid, 1, AFTER + timedelta(days=1), 'nflverse stat correction')
    assert record['original_settlement']['settlement_source'] == 'auto_nflverse'
    assert record['settlement']['result'] == 'LOSS' and record['result_source'] == 'corrected'
    assert tracking.list_tracked(dirs['single'])['summary']['observed_frequency'] == 0
    warning = run(dirs, bundle(event(rows=[label(xpm=3)])))['warnings'][0]   # the user's value is kept, flagged
    assert warning['code'] == 'MANUAL_RESULT_DIFFERS_FROM_SOURCE' and warning['result_source'] == 'corrected'


def test_multi_legs_auto_settle_and_status_follows(dirs):
    record = mt.track(dirs['multi'], multi(), AID, BEFORE)                    # legs: DAL_HOU (K1) and BUF_NE (K2)
    tid = record['manifest']['tracking_id']
    first = run(dirs, bundle(event(rows=[label(xpm=2)], kickoff=K1)), now=K1 + timedelta(hours=4))
    assert [(s['type'], s['leg'], s['result']) for s in first['settled']] == [('multi', 1, 'WIN')]
    assert mt.load(dirs['multi'], tid)['status'] == 'PARTIALLY SETTLED'
    source = bundle(event(rows=[label(xpm=2)], kickoff=K1),
                    event('2026_06_BUF_NE', [label('00-2', 'BUF', 2)], kickoff=K2, sha='d'))
    second = run(dirs, source, now=K2 + timedelta(hours=4))
    assert [(s['leg'], s['actual_xpm'], s['result']) for s in second['settled']] == [(2, 2, 'LOSS')]   # Over 2.5
    done = mt.load(dirs['multi'], tid)
    assert done['status'] == 'SETTLED' and done['outcome'] == 'HAS LOSS'
    assert done['legs'][1]['original_settlement']['source_hash'] == 'd' * 64 and done['legs'][1]['result_source'] == 'auto_nflverse'
    assert [e['leg'] for e in log_lines(dirs)] == [1, 2]
    with pytest.raises(tracking.TrackingError, match='already settled'):
        mt.settle_leg(dirs['multi'], tid, 2, 3, AFTER)
    fixed = mt.correct_leg(dirs['multi'], tid, 2, 3, K2 + timedelta(days=1))
    assert fixed['outcome'] == 'ALL LEGS WON' and fixed['legs'][1]['original_settlement']['actual_xpm'] == 2


def test_legacy_records_without_source_fields_still_auto_settle(dirs):
    tid = track_single(dirs)
    pick_path = dirs['single']/tid/'pick.json'
    assert 'settlement_source' not in pick_path.read_text()                  # nothing to migrate in the pick
    assert run(dirs, bundle(event(rows=[label(xpm=2)])))['settled'][0]['tracking_id'] == tid


def test_seasons_needed_only_for_open_started_selections(dirs):
    track_single(dirs)
    assert auto.seasons_needed(dirs['single'], dirs['multi'], BEFORE) == set()
    assert auto.seasons_needed(dirs['single'], dirs['multi'], AFTER) == {2026}
    run(dirs, bundle(event(rows=[label(xpm=2)])))
    assert auto.seasons_needed(dirs['single'], dirs['multi'], AFTER) == set()
    assert leg()['game']['kickoff'] == K1.isoformat()
