import pytest

from kickedge.features.market import market_features, schedule_market


def identity(team='A'):
    return dict(game_id='g',team=team,opponent='B' if team=='A' else 'A',
        kickoff='2025-09-07T17:00:00Z',prediction_cutoff='2025-09-07T16:00:00Z')


def quote(**updates):
    return dict(game_id='g',home_team='A',away_team='B',home_spread=-6,game_total=46,
        home_moneyline=-200,away_moneyline=180,source='book',source_sha256='a'*64,
        bookmaker_type='sportsbook',kind='quote',observed_at='2025-09-07T15:00:00Z',
        last_update='2025-09-07T14:59:00Z',**updates)


def test_team_perspective_and_implied_points():
    a=market_features(identity(),quote());b=market_features(identity('B'),quote())
    assert a['values']['game_spread']==-6 and b['values']['game_spread']==6
    assert a['values']['implied_team_total']==26 and b['values']['implied_team_total']==20
    assert a['values']['implied_opponent_total']==20
    assert a['values']['implied_team_strength']==pytest.approx((2/3)/((2/3)+(100/280)))
    assert a['training_eligible'] and b['training_eligible']


def test_schedule_sign_and_experimental_only():
    s=dict(game_id='g',home_team='A',away_team='B',spread_line=6,total_line=46,
        home_moneyline=-200,away_moneyline=180)
    e=schedule_market(s,'a'*64)
    r=market_features(identity(),e)
    assert r['values']['game_spread']==-6
    assert r['values']['implied_team_total']==26
    assert not r['training_eligible'] and not r['current_usable']
    assert r['classification']=='experimental'


@pytest.mark.parametrize('updates',[
    {'observed_at':'2025-09-07T16:01:00Z'},
    {'last_update':'2025-09-07T16:01:00Z'},
    {'game_id':'wrong'}, {'home_team':'C'},
])
def test_late_or_wrong_game_rejected(updates):
    q=quote();q.update(updates)
    r=market_features(identity(),q)
    assert not r['training_eligible']
    assert all(v is None for v in r['values'].values())


def test_missing_and_partial_market():
    assert all(v is None for v in market_features(identity(),None)['values'].values())
    q=quote();q.update(home_spread=None,away_moneyline=None)
    v=market_features(identity(),q)['values']
    assert v['game_spread'] is None and v['implied_team_total'] is None
    assert v['implied_team_strength'] is None and v['moneyline_team']==-200


def test_invalid_numbers_and_dfs_do_not_invent_strength():
    q=quote();q.update(home_spread=float('nan'),game_total=-1,home_moneyline=0)
    v=market_features(identity(),q)['values']
    assert all(v[k] is None for k in ('game_spread','game_total','moneyline_team','implied_team_total'))
    q=quote();q['bookmaker_type']='dfs'
    r=market_features(identity(),q)
    assert not r['training_eligible'] and r['values']['implied_team_strength'] is None


def test_pickem_and_impossible_implied_score():
    q=quote();q['home_spread']=0
    assert market_features(identity(),q)['values']['implied_team_total']==23
    q['home_spread']=50
    assert market_features(identity(),q)['values']['implied_team_total'] is None


@pytest.mark.parametrize('change',[{'source':' '},{'source_sha256':'not-a-hash'},{'source_sha256':'z'*64}])
def test_malformed_source_never_approves_training(change):
    q=quote();q.update(change)
    result=market_features(identity(),q)
    assert not result['training_eligible'] and not result['current_usable']


def test_current_general_capture_binds_one_book_event_and_team_mapping():
    from kickedge.features.market import parlay_market_features
    capture={'source':'ParlayAPI','source_sha256':'a'*64,'observed_at':'2025-09-07T15:00:00Z',
        'rows':[{'id':'external','home_team':'Alpha','away_team':'Beta','commence_time':'2025-09-07T17:00:00Z',
            'bookmakers':[{'key':'fliff','last_update':'2025-09-07T14:00:00Z','markets':[
                {'key':'spreads','outcomes':[{'name':'Alpha','point':-6},{'name':'Beta','point':6}]},
                {'key':'totals','outcomes':[{'name':'Over','point':46},{'name':'Under','point':46}]},
                {'key':'h2h','outcomes':[{'name':'Alpha','price':-200},{'name':'Beta','price':180}]}]}]}]}
    mapping={'Alpha':'A','Beta':'B'}
    r=parlay_market_features(identity('B'),capture,'external','fliff',mapping)
    assert r['training_eligible'] and r['values']['implied_team_total']==20
    assert not parlay_market_features(identity(),capture,'missing','fliff',mapping)['training_eligible']
    assert not parlay_market_features(identity(),capture,'external','fliff',{'Alpha':'C','Beta':'B'})['training_eligible']
    capture['rows'][0]['bookmakers'][0]['markets'][1]['outcomes'][1]['point']=45
    assert parlay_market_features(identity(),capture,'external','fliff',mapping)['values']['game_total'] is None
