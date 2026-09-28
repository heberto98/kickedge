"""Phase 2: temporal boundaries and independently specified aggregate examples."""
from datetime import datetime, timedelta, timezone
import importlib
import importlib.util
import json

import pytest

from kickedge.io import write_json, sha256_file


def module():
    assert importlib.util.find_spec('kickedge.features.team') is not None, 'Phase 2 builder missing'
    return importlib.import_module('kickedge.features.team')


def fixture(tmp_path):
    identities, manifest = [], {}
    for n in range(1, 9):
        # A bye separates g3 and g4; g8 starts a new season.
        start = datetime(2025,9,1,17,tzinfo=timezone.utc)+timedelta(days=7*(n-1)+(7 if n>=4 else 0))
        season = 2026 if n==8 else 2025
        game = f'g{n}'
        identities.append(dict(game_id=game,season=season,team='A',opponent='B',kicker_id='k',
                               kickoff=start.isoformat(),prediction_cutoff=(start-timedelta(hours=1)).isoformat()))
        rows=[]
        for team,opp,factor in [('A','B',1),('B','A',10)]:
            rows.append(dict(game_id=game,season=season,team=team,opponent=opp,points=factor*n,
                touchdowns=n,drives=10,red_zone_drives=4,red_zone_touchdowns=2,
                epa_sum=-n,epa_plays=10,successes=n))
        path=tmp_path/(game+'.json'); write_json(path,rows)
        manifest[game]=dict(filename=path.name,sha256=sha256_file(path),temporal_class='historical_event_data',
            event_completed=True,actual_kickoff=start.isoformat(),last_event=(start+timedelta(hours=3)).isoformat(),
            available_at=(start+timedelta(hours=24)).isoformat(),availability_verified=False)
    return identities,manifest


def run(tmp_path,identities,manifest,stop_at=None):
    from kickedge.features.kicker import LabelOracle
    return module().simulate(identities,LabelOracle(tmp_path,manifest),lambda e:None,stop_at=stop_at)


def test_shifted_season_rolling_bye_and_opponent_defense(tmp_path):
    ids,m=fixture(tmp_path); rows=run(tmp_path,ids,m)
    first=rows[0]
    assert first['offense_games_before']==first['defense_games_before']==0
    assert all(first[n] is None for n in module().FEATURE_NAMES if not n.endswith('games_before'))
    fourth=rows[3]
    assert fourth['offense_points_per_game_before']==2
    assert fourth['offense_touchdowns_per_game_before']==2
    assert fourth['offense_points_per_game_last_3']==2
    assert fourth['offense_points_per_game_last_5'] is None
    assert fourth['offense_td_per_drive_before']==pytest.approx(.2)
    assert fourth['offense_red_zone_td_rate_before']==.5
    assert fourth['offense_epa_per_play_before']==pytest.approx(-.2)
    # Opponent B conceded A's values, not B's offensive values (20 ppg).
    assert fourth['defense_points_allowed_per_game_before']==2
    seventh=rows[6]
    assert seventh['offense_points_per_game_before']==3.5
    assert seventh['offense_points_per_game_last_3']==5
    assert seventh['offense_points_per_game_last_5']==4
    assert seventh['team_feature_provenance']['offense']['last_3_game_ids']==['g4','g5','g6']
    assert seventh['team_feature_provenance']['offense']['last_5_game_ids']==['g2','g3','g4','g5','g6']
    assert rows[7]['offense_games_before']==rows[7]['defense_games_before']==0


@pytest.mark.parametrize('field', ['points','touchdowns','epa_sum'])
def test_target_mutation_cannot_change_own_features_but_updates_later(tmp_path,field):
    ids,m=fixture(tmp_path); before=run(tmp_path,ids,m)
    path=tmp_path/'g4.json'; values=json.loads(path.read_text()); values[0][field]+=1
    write_json(path,values); m['g4']['sha256']=sha256_file(path)
    after=run(tmp_path,ids,m)
    assert before[:4]==after[:4]
    assert before[4]!=after[4]


def test_future_mutation_and_target_file_deletion_do_not_change_past(tmp_path):
    ids,m=fixture(tmp_path); before=run(tmp_path,ids,m,stop_at='g4')
    path=tmp_path/'g7.json'; write_json(path,[{'invalid':'future'}]);m['g7']['sha256']=sha256_file(path)
    (tmp_path/'g4.json').unlink()
    assert run(tmp_path,ids,m,stop_at='g4')==before


def test_rates_pool_numerators_denominators_not_game_rates(tmp_path):
    ids,m=fixture(tmp_path)
    path=tmp_path/'g1.json';v=json.loads(path.read_text())
    v[0].update(epa_sum=20,epa_plays=100,successes=60,drives=20,touchdowns=2,red_zone_drives=0,red_zone_touchdowns=0)
    write_json(path,v);m['g1']['sha256']=sha256_file(path)
    row=run(tmp_path,ids,m)[2]
    assert row['offense_epa_per_play_before']==pytest.approx(18/110)
    assert row['offense_success_rate_before']==pytest.approx(62/110)
    assert row['offense_td_per_drive_before']==pytest.approx(4/30)
    assert row['offense_red_zone_td_rate_before']==.5


def test_unfinished_source_is_rejected_and_unreleased_history_not_imputed(tmp_path):
    ids,m=fixture(tmp_path)
    m['g1']['event_completed']=False
    with pytest.raises(ValueError,match='temporal'):
        run(tmp_path,ids,m)
    m['g1']['event_completed']=True
    m['g1']['available_at']=ids[2]['kickoff']
    row=run(tmp_path,ids,m,stop_at='g2')[-1]
    assert row['offense_points_per_game_before'] is None
    assert row['team_history_unavailable_before_cutoff']


def test_deterministic_multiple_kickers_do_not_duplicate_team_games(tmp_path):
    ids,m=fixture(tmp_path)
    ids.insert(1,ids[0]|{'kicker_id':'second'})
    a=run(tmp_path,ids,m);b=run(tmp_path,list(reversed(ids)),m)
    assert a==b
    assert a[0]['offense_games_before']==a[1]['offense_games_before']==0
    assert a[2]['offense_games_before']==1


def test_defense_reads_target_opponent_against_other_prior_teams(tmp_path):
    ids,m=fixture(tmp_path)
    builder=module().TeamFeatureBuilder()
    first=json.loads((tmp_path/'g1.json').read_text())
    first[0]['opponent']='C';first[1].update(team='C',opponent='A')
    builder.observe(first,m['g1'])
    second=json.loads((tmp_path/'g2.json').read_text())
    second[0].update(team='B',opponent='D',points=7)
    second[1].update(team='D',opponent='B',points=42)
    builder.observe(second,m['g2'])
    r=builder.build(ids[2])
    assert r['offense_points_per_game_before']==1
    assert r['defense_points_allowed_per_game_before']==42
    assert r['team_feature_provenance']['defense']['history'][0]['team']=='D'


def test_missing_metric_and_zero_denominator_remain_null(tmp_path):
    ids,m=fixture(tmp_path)
    p=tmp_path/'g1.json';v=json.loads(p.read_text())
    v[0].update(epa_sum=None,red_zone_drives=0,red_zone_touchdowns=0)
    write_json(p,v);m['g1']['sha256']=sha256_file(p)
    r=run(tmp_path,ids,m,stop_at='g2')[-1]
    assert r['offense_epa_per_play_before'] is None
    assert r['offense_red_zone_td_rate_before'] is None
    assert r['team_feature_provenance']['null_reasons']['offense_epa_per_play_before']=='missing_source_metric'
    assert r['team_feature_provenance']['null_reasons']['offense_red_zone_td_rate_before']=='zero_denominator'
