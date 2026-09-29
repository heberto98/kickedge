"""Calendar approximation is explicit, scoped, and does not unlock PIT data."""
from datetime import timedelta
import importlib
import importlib.util
import json

import pytest

from kickedge.features.kicker import instant, LabelOracle
from kickedge.io import write_json, sha256_file
from test_context_history import source, result, identity


def module():
    assert importlib.util.find_spec('kickedge.features.context'), 'Phase 3 context builder missing'
    return importlib.import_module('kickedge.features.context')


def calendar(n,**kwargs):
    return dict(game_id=f'g{n}',season=2025,week=n,game_type='REG',home_team='A',away_team='B',
        scheduled_kickoff=source(n)['actual_kickoff'],source_sha256='schedule-hash',
        temporal_class='historical_schedule_context',calendar_policy='phase3-calendar-v1',**kwargs)


def test_home_away_week_one_and_wrong_matchup():
    b=module().GameContextBuilder()
    r=b.build(identity(1),calendar(1))
    assert r['is_home'] and not r['is_away']
    assert (r['season'],r['week'],r['game_type'])==(2025,1,'REG')
    assert r['team_days_rest'] is r['opponent_days_rest'] is None
    assert r['team_short_week_flag'] is r['team_long_rest_flag'] is None
    away=b.build(identity(1)|{'team':'B','opponent':'A'},calendar(1))
    assert away['is_away'] and not away['is_home']
    with pytest.raises(ValueError,match='matchup'):
        b.build(identity(1)|{'opponent':'C'},calendar(1))


@pytest.mark.parametrize('days,short,long',[(4,True,False),(6,False,False),(8,False,False),(9,False,True),(14,False,True)])
def test_rest_thresholds_and_bye(days,short,long):
    b=module().GameContextBuilder()
    b.history.observe([result(1),result(1,'B','A')],source(1))
    start=instant(source(1)['actual_kickoff'])+timedelta(days=days)
    i=identity(2)|{'kickoff':start.isoformat(),'prediction_cutoff':(start-timedelta(hours=1)).isoformat()}
    r=b.build(i,calendar(2)|{'scheduled_kickoff':start.isoformat()})
    assert r['team_days_rest']==r['opponent_days_rest']==days
    assert r['team_short_week_flag'] is short
    assert r['opponent_short_week_flag'] is short
    assert r['team_long_rest_flag'] is long
    assert r['opponent_long_rest_flag'] is long


def test_rest_uses_correct_each_team_prior_actual_and_target_scheduled():
    b=module().GameContextBuilder()
    b.history.observe([result(1,'A','C'),result(1,'C','A')],source(1))
    b.history.observe([result(2,'B','D'),result(2,'D','B')],source(2))
    i=identity(3)
    r=b.build(i,calendar(3))
    assert r['team_days_rest']==14 and r['opponent_days_rest']==7
    delayed=i|{'kickoff':(instant(i['kickoff'])+timedelta(hours=2)).isoformat()}
    other=b.build(delayed,calendar(3))
    assert other['team_days_rest']==r['team_days_rest']
    fallback=b.build(delayed,calendar(3)|{'scheduled_kickoff':None})
    assert fallback['team_days_rest']==pytest.approx(14+2/24)
    assert fallback['calendar_provenance']['rest_reference']=='historical_kickoff_fallback'


def test_playoff_continues_same_season_and_next_season_resets():
    b=module().GameContextBuilder()
    b.history.observe([result(1),result(1,'B','A')],source(1))
    row=b.build(identity(2),calendar(2)|{'game_type':'WC'})
    assert row['team_days_rest']==7
    assert row['team_two_point_attempts_before']==1
    row=b.build(identity(2,2026),calendar(2)|{'season':2026,'week':1})
    assert row['team_days_rest'] is None
    assert row['team_two_point_attempts_before']==0


def fixture(tmp_path):
    ids=[];m={};s={}
    for n in range(1,8):
        ids.append(identity(n)|{'week':n,'game_type':'REG','kicker_name':'Synthetic Kicker'})
        path=tmp_path/(f'g{n}.json')
        write_json(path,[result(n),result(n,'B','A')])
        m[f'g{n}']={**source(n),'filename':path.name,'sha256':sha256_file(path)}
        s[f'g{n}']=calendar(n)
    return ids,m,s


def test_freeze_before_reveal_target_future_mutation_and_file_removal(tmp_path):
    ids,m,s=fixture(tmp_path)
    simulate=module().simulate
    events=[]
    before=simulate(ids,LabelOracle(tmp_path,m),s,events.append)
    frozen=set()
    for e in events:
        if e['kind']=='freeze':frozen.add(e['game_id'])
        else:assert e['game_id'] in frozen
    p=tmp_path/'g4.json';values=json.loads(p.read_text());values[0]['two_pt_attempts']=100
    write_json(p,values);m['g4']['sha256']=sha256_file(p)
    after=simulate(ids,LabelOracle(tmp_path,m),s,lambda e:None)
    assert before[:4]==after[:4] and before[4]!=after[4]
    (tmp_path/'g4.json').unlink();(tmp_path/'g7.json').unlink()
    assert simulate(ids,LabelOracle(tmp_path,m),s,lambda e:None,stop_at='g4')==before[:4]


def test_calendar_approximation_cannot_authorize_market_or_injuries():
    from kickedge.features import load_contract
    from kickedge.features.validation import validate_contract
    c=load_contract()
    assert c.get('calendar_context_policy',{}).get('policy_id')=='phase3-calendar-v1', 'Calendar policy missing'
    fields=validate_contract(c)
    assert fields['is_home']['temporal_class']=='historical_schedule_context'
    field=next(f for f in c['fields'] if f['group']=='market')
    field.update(temporal_class='historical_schedule_context',calendar_policy='phase3-calendar-v1',publication_timestamp_required=False)
    with pytest.raises(ValueError,match='temporal'):
        validate_contract(c)
