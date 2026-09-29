"""Completed-game conversion choices and same-season sample windows."""
from datetime import datetime, timedelta, timezone
import importlib
import importlib.util

import pytest


def builder():
    assert importlib.util.find_spec('kickedge.features.context_history'), 'Phase 3 history builder missing'
    return importlib.import_module('kickedge.features.context_history').ContextHistory()


def source(n):
    start=datetime(2025,9,1,17,tzinfo=timezone.utc)+timedelta(days=7*(n-1))
    return dict(actual_kickoff=start.isoformat(),last_event=(start+timedelta(hours=3)).isoformat(),
        available_at=(start+timedelta(hours=24)).isoformat(),event_completed=True,
        temporal_class='historical_event_data',sha256=f'game-{n}')


def result(n,team='A',opponent='B',season=2025):
    return dict(game_id=f'g{n}',season=season,team=team,opponent=opponent,
                two_pt_attempts=n,team_xpa=10-n,coverage_ok=True)


def identity(n,season=2025):
    start=datetime.fromisoformat(source(n)['actual_kickoff'])
    return dict(game_id=f'g{n}',season=season,team='A',opponent='B',kicker_id='k',
        kickoff=start.isoformat(),prediction_cutoff=(start-timedelta(hours=1)).isoformat())


def test_two_point_windows_are_shifted_exact_and_weighted():
    b=builder()
    for n in range(1,8):
        b.observe([result(n),result(n,'B','A')],source(n))
    r=b.build(identity(7))
    assert r['team_two_point_attempts_before']==21
    assert r['team_two_point_attempt_rate_before']==pytest.approx(21/60)
    assert r['team_two_point_attempts_last_3']==15
    assert r['team_two_point_attempt_rate_last_3']==.5
    assert r['team_two_point_attempts_last_5']==20
    assert r['team_two_point_attempt_rate_last_5']==.4
    assert r['context_history_provenance']['team']['last_3_game_ids']==['g4','g5','g6']
    assert r['context_history_provenance']['team']['last_5_game_ids']==['g2','g3','g4','g5','g6']


def test_zero_history_small_windows_zero_tries_and_season_reset():
    b=builder()
    first=b.build(identity(1))
    assert first['team_two_point_attempts_before']==0
    assert first['team_two_point_attempt_rate_before'] is None
    assert first['team_two_point_attempts_last_3'] is None
    assert not first['team_has_3_prior_games']
    b.observe([result(1)|{'two_pt_attempts':0,'team_xpa':0},result(1,'B','A')],source(1))
    r=b.build(identity(2))
    assert r['team_two_point_attempts_before']==0
    assert r['team_two_point_attempt_rate_before'] is None
    assert b.build(identity(2,2026))['team_two_point_attempts_before']==0


def test_target_and_future_conversion_changes_do_not_affect_own_or_past():
    before,after=builder(),builder()
    for n in range(1,8):
        rows=[result(n),result(n,'B','A')]
        before.observe(rows,source(n))
        if n>=4:
            rows[0]=rows[0]|{'two_pt_attempts':100}
        after.observe(rows,source(n))
    assert before.build(identity(4))==after.build(identity(4))
    assert before.build(identity(5))!=after.build(identity(5))


def test_sample_flags_use_each_teams_own_history():
    b=builder()
    for n in range(1,6):
        b.observe([result(n,'A','C'),result(n,'C','A')],source(n))
    for n in range(6,9):
        b.observe([result(n,'B','D'),result(n,'D','B')],source(n))
    r=b.build(identity(9))
    assert r['team_has_3_prior_games'] and r['team_has_5_prior_games']
    assert r['opponent_has_3_prior_games'] and not r['opponent_has_5_prior_games']


def test_pool_attempts_not_average_game_rates():
    b=builder()
    b.observe([result(1)|{'two_pt_attempts':1,'team_xpa':0},result(1,'B','A')],source(1))
    b.observe([result(2)|{'two_pt_attempts':0,'team_xpa':9},result(2,'B','A')],source(2))
    assert b.build(identity(3))['team_two_point_attempt_rate_before']==.1


def test_invalid_counts_and_incomplete_game_fail_closed():
    b=builder()
    with pytest.raises(ValueError,match='count'):
        b.observe([result(1)|{'two_pt_attempts':-1},result(1,'B','A')],source(1))
    b=builder()
    b.observe([result(1),result(1,'B','A')],source(1)|{'event_completed':False})
    with pytest.raises(ValueError,match='temporal'):
        b.build(identity(2))
