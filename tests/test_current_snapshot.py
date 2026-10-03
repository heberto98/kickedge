from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib

import pytest


START = datetime(2027, 9, 5, 17, tzinfo=timezone.utc)


def api():
    assert importlib.util.find_spec('kickedge.current.snapshot'), 'Current snapshot implementation missing'
    return importlib.import_module('kickedge.current.snapshot')


def bundle(n=7):
    schedules, games = [], []
    for i in range(n):
        kick = START + timedelta(days=7*i)
        gid = f'2027_{i+1:02}_AAA_BBB'
        schedules.append(dict(game_id=gid, season=2027, week=i+1, game_type='REG',
                              home_team='AAA', away_team='BBB', scheduled_kickoff=kick.isoformat()))
        source = dict(actual_kickoff=kick.isoformat(), scheduled_kickoff=kick.isoformat(),
                      last_event=(kick+timedelta(hours=3)).isoformat(),
                      available_at=(kick+timedelta(hours=24)).isoformat(), event_completed=True,
                      temporal_class='historical_event_data', availability_verified=False, sha256='a'*64)
        kickers = [dict(game_id=gid,season=2027,week=i+1,game_type='REG',team='AAA',opponent='BBB',
                       kicker_id='K1',kicker_name='Test Kicker',xpa=i+1,xpm=i,statistical_label_usable=True)]
        teams, conversions = [], []
        for team,opp,points in [('AAA','BBB',21),('BBB','AAA',14)]:
            common=dict(game_id=gid,season=2027,team=team,opponent=opp)
            teams.append(dict(common,points=points,touchdowns=3 if team=='AAA' else 2,drives=10,
                              red_zone_drives=4,red_zone_touchdowns=2,epa_sum=2.,epa_plays=50,successes=25))
            conversions.append(dict(common,two_pt_attempts=1,team_xpa=2,coverage_ok=True))
        games.append(dict(game_id=gid,season=2027,source=source,kickers=kickers,teams=teams,conversions=conversions))
    now=START-timedelta(days=1)
    return dict(season=2027,generated_at=now.isoformat(),schedules=schedules,games=games,
                players=[dict(player_id='K1',display_name='Test Kicker',position='K')],
                sources=[dict(dataset='schedules',sha256='b'*64,fetched_at=now.isoformat(),path='data/example.parquet')])


def build(data, week, now=None):
    m=api()
    now=now or START+timedelta(days=7*(week-1),hours=-1)
    target=m.resolve_target(data,'AAA','BBB',season=2027,week=week,now=now)
    player=m.resolve_kicker(data,'Test Kicker',target,cutoff=now)
    return m.build_snapshot(data,target,player,now=now)


def test_exact_order_rolling_defense_perspective_and_rest():
    result=build(bundle(),7)
    from kickedge.modeling.dataset import predictor_columns
    f=result['snapshot']['features']
    assert list(f)==predictor_columns() and len(f)==82
    assert f['kicker_games_before']==6
    assert f['kicker_xpm_last_3']==12 and f['kicker_xpa_last_5']==20
    assert f['offense_points_per_game_before']==21
    assert f['defense_points_allowed_per_game_before']==21
    assert f['team_days_rest']==7
    assert f['team_two_point_attempt_rate_before']==pytest.approx(1/3)
    assert result['provenance']['latest_game_used']['game_id']=='2027_06_AAA_BBB'


def test_first_game_nulls_and_same_season_reset():
    d=bundle()
    d['games'].append(deepcopy(d['games'][0])|{'season':2026,'game_id':'previous'})
    f=build(d,1)['snapshot']['features']
    assert f['kicker_games_before']==0 and f['offense_games_before']==0
    assert f['previous_game_xpm'] is None and f['team_days_rest'] is None
    assert f['team_two_point_attempts_before']==0
    assert f['kicker_low_sample_flag']==1


def test_target_and_future_mutation_or_removal_cannot_change_snapshot():
    d=bundle(); before=build(d,4)
    for game in d['games'][3:]:
        game['kickers']='UNREADABLE TARGET';game['teams']=None;game['conversions']=None
    assert build(d,4)==before
    d['games']=d['games'][:3]
    assert build(d,4)==before


def test_game_ambiguity_mismatch_and_started_game_fail():
    d=bundle();m=api();now=START-timedelta(days=1)
    with pytest.raises(ValueError,match='ambiguous'):
        m.resolve_target(d,'AAA','BBB',season=2027,now=now)
    with pytest.raises(ValueError,match='match'):
        m.resolve_target(d,'AAA','CCC',season=2027,week=1,now=now)
    with pytest.raises(ValueError,match='future|started'):
        m.resolve_target(d,'AAA','BBB',season=2027,week=1,now=START)


def test_player_ambiguity_and_no_silent_substitution():
    d=bundle();m=api();t=m.resolve_target(d,'AAA','BBB',season=2027,week=1,now=START-timedelta(hours=1))
    d['players'].append(dict(player_id='K2',display_name='Test Kicker',position='K'))
    with pytest.raises(ValueError,match='ambiguous'):
        m.resolve_kicker(d,'Test Kicker',t,cutoff=START)
    with pytest.raises(ValueError,match='identity'):
        m.resolve_kicker(d,'Unknown Person',t,cutoff=START)


def test_completed_event_and_conservative_release_gate():
    d=bundle();d['games'][0]['source']['event_completed']=False
    with pytest.raises(ValueError,match='completed|temporal'):
        build(d,2)
    d=bundle();d['games'][0]['source']['available_at']=(START+timedelta(days=8)).isoformat()
    result=build(d,2)
    assert result['snapshot']['features']['kicker_games_before']==0
    assert any('release' in w for w in result['data_quality']['warnings'])


def test_actual_generation_time_prevents_using_not_yet_completed_game():
    now=START+timedelta(hours=1)
    result=build(bundle(),2,now=now)
    assert result['snapshot']['features']['kicker_games_before']==0
    assert result['snapshot']['metadata']['cutoff']==now.isoformat()
