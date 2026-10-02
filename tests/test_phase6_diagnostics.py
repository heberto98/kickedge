import json
import numpy as np
import pandas as pd
from kickedge.validation.diagnostics import subgroups, analyze_subgroups, drift, error_cases


def frame(n=12):
    return pd.DataFrame({'is_home': [True, False, None] * (n//3), 'week': np.arange(n),
        'kicker_games_before': np.arange(n), 'team_short_week_flag': False,
        'team_long_rest_flag': False, 'offense_points_per_game_last_5': np.arange(n),
        'defense_points_allowed_per_game_last_5': np.arange(n), 'game_type': 'REG', 'season': 2025})


def test_groups_use_reference_and_keep_unknowns():
    x=frame(); ref=frame(); ref['offense_points_per_game_last_5']=100
    groups=subgroups(x, ref, np.full(12, 2.5))
    assert groups['offense:weak'].all()
    assert groups['home:unknown'].sum()==4
    for family in ('home','week','history','lambda','rest','offense','defense'):
        assert np.stack([v for k,v in groups.items() if k.startswith(family+':')]).sum(axis=0).tolist()==[1]*12
    a=analyze_subgroups(x,ref,np.zeros(12),np.full(12,3.),np.ones(12))
    b=analyze_subgroups(x,ref,np.ones(12),np.full(12,3.),np.ones(12))
    assert {k:v['n'] for k,v in a.items()}=={k:v['n'] for k,v in b.items()}
    assert all(not v['warning'] and v['small_sample'] for v in a.values())
    assert all('calibration' not in v['model'] for v in a.values() if v['n'])
    json.dumps(a, allow_nan=False)


def test_drift_means_missingness_categories_ranges():
    ref=frame(); x=frame(); ref['week']=np.arange(12); x['week']=100.
    x.loc[:3,'offense_points_per_game_last_5']=np.nan; x['game_type']='NOVEL'
    result=drift(ref,x,['numeric__week','numeric__offense_points_per_game_last_5'])
    assert result['top_features']['week']['smd_flag']
    assert result['outside_reference_range']['week']==12
    assert result['missingness']['offense_points_per_game_last_5']['flag']
    assert result['game_type']['new_categories']==['NOVEL']
    assert result['expected_calendar_drift']
    json.dumps(result,allow_nan=False)


def test_all_overpredictions_have_no_underprediction_reason():
    x=frame(); ids=pd.DataFrame({'game_id':range(12),'team':'A','opponent':'B','kicker_id':'K'})
    result=error_cases(ids,x,np.zeros(12),np.full(12,3.))
    assert not any('largest_underprediction' in row['reasons'] for row in result)


def test_error_cases_union_bounded_and_prop_diagnostics():
    x=frame(30); y=np.arange(30)%6; means=np.linspace(.1,5,30)
    ids=pd.DataFrame({'game_id': [str(i) for i in range(30)],'team':'A','opponent':'B',
                      'kicker_id':'K','kicker_name':'Name'})
    result=error_cases(ids,x,y,means)
    assert len(result)==16
    assert len({r['game_id'] for r in result})==16
    assert all(0<=r['probability_ge3']<=1 and r['observed_pmf']>0 and r['reasons'] for r in result)
    assert any('highest_failed_ge3' in r['reasons'] for r in result)
    json.dumps(result,allow_nan=False)


def test_warning_requires_50_and_nulls_are_json_safe():
    x=frame(60); ref=frame(60)
    x['is_home']=pd.Series([pd.NA]*60,dtype='boolean')
    x['team_short_week_flag']=pd.Series([pd.NA]*60,dtype='boolean')
    ref['offense_points_per_game_last_5']=np.nan
    groups=subgroups(x,ref,np.full(60,3.))
    assert groups['home:unknown'].all() and groups['rest:unknown'].all()
    assert groups['offense:unknown'].all()
    result=analyze_subgroups(x,ref,np.zeros(60),np.full(60,3.),np.ones(60))
    assert result['lambda:3plus']['warning']
    assert not result['lambda:3plus']['small_sample']
    assert result['home:home']['model'] is None
    json.dumps(drift(ref,x,['offense_points_per_game_last_5']),allow_nan=False)
    json.dumps(result,allow_nan=False)
