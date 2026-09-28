import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from kickedge.io import write_json, write_parquet, sql_literal, sha256_file


def module(name):
    assert importlib.util.find_spec('kickedge.features.'+name) is not None, 'Phase 2 pipeline missing'
    return importlib.import_module('kickedge.features.'+name)


def test_source_aggregation_excludes_returns_tries_deleted_plays_and_pools_red_zone(tmp_path):
    base=dict(game_id='g1',posteam='OAK',defteam='SD',td_team=None,touchdown=0,return_touchdown=0,
        play_deleted=0,play_type='run',extra_point_attempt=0,two_point_attempt=0,special_teams_play=0,
        fixed_drive=1,down=1,yardline_100=15,epa=1.,qb_kneel=0,qb_spike=0)
    rows=[base,
          base|dict(play_type='pass',td_team='OAK',touchdown=1,epa=2.),
          base|dict(fixed_drive=2,play_type='pass',td_team='SD',touchdown=1,return_touchdown=1,yardline_100=70,epa=-4.),
          base|dict(fixed_drive=3,play_type='punt',special_teams_play=1,td_team='OAK',touchdown=1,return_touchdown=1,epa=100.,yardline_100=70),
          base|dict(play_type='extra_point',extra_point_attempt=1,epa=100.),
          base|dict(play_type='run',two_point_attempt=1,td_team='OAK',touchdown=1,epa=100.),
          base|dict(play_deleted=1,td_team='OAK',touchdown=1,epa=100.),
          base|dict(fixed_drive=4,play_type='qb_kneel',qb_kneel=1,epa=100.,yardline_100=50),
          base|dict(fixed_drive=5,play_type='no_play',epa=100.),
          base|dict(fixed_drive=6,play_type='pass',epa=None,yardline_100=50)]
    path=tmp_path/'pbp.json';write_json(path,rows)
    with duckdb.connect() as con:
        write_parquet(con,f'SELECT * FROM read_json_auto({sql_literal(str(path))})',tmp_path/'pbp.parquet')
        result=module('team_prepare').aggregate(con,tmp_path/'pbp.parquet')
    assert len(result)==1
    r=result[0]
    assert r['team']=='LV' and r['opponent']=='LAC'
    assert r['touchdowns']==1
    assert r['drives']==5  # observed source drives, including kneel-only possession
    assert (r['red_zone_drives'],r['red_zone_touchdowns'])==(1,1)
    assert (r['epa_sum'],r['epa_plays'],r['successes'])==(-1.,3,2)


def test_phase_two_materialization_preserves_phase_one_and_is_deterministic(tmp_path):
    from test_team_features import fixture
    from kickedge.features.kicker import FEATURE_NAMES as KICKER_NAMES
    ids,manifest=fixture(tmp_path/'outcomes')
    write_json(tmp_path/'identities.json',ids)
    write_json(tmp_path/'manifest.json',manifest)
    phase1=tmp_path/'data/features/kicker/phase1'
    baseline=[r|{n:0 for n in KICKER_NAMES}|dict(xpm=2,eligible_for_final_training=True,
        features_temporally_verified=True,features_technically_reconstructible=True,
        training_exclusion_reasons=[],source_label={'original_flag':True}) for r in ids]
    write_json(phase1/'kicker_game_features.json',baseline)
    write_json(phase1/'build.json',{'artifacts':[dict(filename='kicker_game_features.json',sha256=sha256_file(phase1/'kicker_game_features.json'))]})
    write_json(tmp_path/'source.json',dict(inputs={'phase1_build':'phase1',
        'phase1_build_sha256':sha256_file(phase1/'build.json'),'temporal_policy':'event-context-v1'},
        identities_sha256=sha256_file(tmp_path/'identities.json'),manifest_sha256=sha256_file(tmp_path/'manifest.json')))
    config=SimpleNamespace(root=tmp_path,data_dir=tmp_path/'data',reports_dir=tmp_path/'reports')
    build=module('team_materialize').build
    out=build(config,tmp_path)
    hashes={p.name:sha256_file(p) for p in out.iterdir()}
    assert build(config,tmp_path)==out
    assert hashes=={p.name:sha256_file(p) for p in out.iterdir()}
    rows=json.loads((out/'kicker_game_features.json').read_text())
    from kickedge.features.team import FEATURE_NAMES
    assert len(FEATURE_NAMES)==40
    for old,new in zip(baseline,rows):
        assert all(new[k]==v for k,v in old.items())
        assert set(FEATURE_NAMES)<=new.keys()
    assert rows[3]['eligible_for_phase_2_training'] is True
    assert rows[3]['offense_points_per_game_before']==2


def test_phase_two_contract_has_exact_predictors_and_allows_negative_epa():
    from kickedge.features import load_contract
    c=load_contract()
    assert len(c.get('predictor_columns_phase_2',[]))==40, 'Phase 2 contract missing'
    from kickedge.features.team import FEATURE_NAMES
    assert tuple(c['predictor_columns_phase_2'])==FEATURE_NAMES
    assert len(c['predictor_columns_phase_1'])==21
    fields={f['name']:f for f in c['fields']}
    for n in FEATURE_NAMES:
        assert fields[n]['implemented'] and fields[n]['historical_training_approved']
        assert fields[n]['temporal_class']=='historical_event_data'
        assert fields[n]['publication_timestamp_required'] is False
    validator=module('team_materialize').validate
    from kickedge.features.team import TeamFeatureBuilder
    r=dict(game_id='x',team='A',opponent='B',season=2025,kicker_id='k',kickoff='2025-09-02T17:00:00+00:00',prediction_cutoff='2025-09-02T16:00:00+00:00')
    row={**r,**TeamFeatureBuilder().build(r)}
    row['offense_epa_per_play_before']=-.7
    validator([row],c)
    row['offense_success_rate_before']=1.1
    with pytest.raises(ValueError,match='value'):
        validator([row],c)


def test_real_phase_two_matches_sql_history_and_preserves_all_phase_one_fields():
    root=Path(__file__).resolve().parents[1]
    pointer=root/'data/features/teams/latest.json'
    if not pointer.exists():
        pytest.skip('Materialize Phase 2 locally')
    directory=root/json.loads(pointer.read_text())['path']
    meta=json.loads((directory/'build.json').read_text())
    prep=root/'data/features/team_inputs'/meta['inputs']['prepared_build']
    phase1=root/'data/features/kicker'/meta['inputs']['phase1_build']
    rows=json.loads((directory/'kicker_game_features.json').read_text())
    old=json.loads((phase1/'kicker_game_features.json').read_text())
    from kickedge.features.kicker import key
    bykey={key(r):r for r in rows}
    assert len(rows)==len(old)==6083
    for r in old:
        assert all(bykey[key(r)][n]==v for n,v in r.items())
    for a in meta['artifacts']:
        assert sha256_file(directory/a['filename'])==a['sha256']
    # Independent SQL history selection and weighted window formulas; does not use
    # the builder's histories, metric map or calculated sums as expected values.
    with duckdb.connect() as con:
        con.execute('CREATE TABLE ids AS SELECT * FROM read_json_auto(?)',[str(prep/'identities.json')])
        con.execute('CREATE TABLE stats AS SELECT * FROM read_json_auto(?)',[str(prep/'outcomes/*.json')])
        clocks=json.loads((prep/'manifest.json').read_text())
        con.execute('CREATE TABLE clocks(game_id VARCHAR,start TIMESTAMPTZ,finish TIMESTAMPTZ,release TIMESTAMPTZ)')
        con.executemany('INSERT INTO clocks VALUES (?,?,?,?)',[(g,s['actual_kickoff'],s['last_event'],s['available_at']) for g,s in clocks.items()])
        for side,condition in [('offense','s.team=i.team'),('defense','s.opponent=i.opponent')]:
            con.execute(f'''CREATE OR REPLACE TABLE history AS SELECT i.game_id target_id,i.team target_team,i.kicker_id,
                s.*,row_number() OVER(PARTITION BY i.game_id,i.team,i.kicker_id ORDER BY c.start DESC,s.game_id DESC) rn
                FROM ids i JOIN stats s ON s.season=i.season AND {condition}
                JOIN clocks c ON c.game_id=s.game_id
                WHERE s.game_id!=i.game_id AND c.start<i.prediction_cutoff::TIMESTAMPTZ
                  AND c.finish<i.prediction_cutoff::TIMESTAMPTZ AND c.release<=i.prediction_cutoff::TIMESTAMPTZ''')
            for size in (None,3,5):
                q='WHERE rn<='+str(size) if size else ''
                expected=con.execute(f'''SELECT target_id,target_team,kicker_id,count(*),avg(points),avg(touchdowns),avg(drives),
                    sum(touchdowns)::DOUBLE/nullif(sum(drives),0),
                    sum(red_zone_touchdowns)::DOUBLE/nullif(sum(red_zone_drives),0),
                    sum(epa_sum)/nullif(sum(epa_plays),0),sum(successes)::DOUBLE/nullif(sum(epa_plays),0)
                    FROM history {q} GROUP BY target_id,target_team,kicker_id''').fetchall()
                suffix='before' if size is None else f'last_{size}'
                names=(['points_per_game','touchdowns_per_game','drives_per_game','td_per_drive','red_zone_td_rate','epa_per_play','success_rate']
                    if side=='offense' else ['points_allowed_per_game','touchdowns_allowed_per_game','drives_faced_per_game','td_allowed_per_drive','red_zone_td_rate_allowed','epa_allowed_per_play','success_rate_allowed'])
                for g,t,k,n,*values in expected:
                    row=bykey[g,t,k]
                    if size is None:
                        assert row[side+'_games_before']==n
                    for metric,value in zip(names,values):
                        if size and metric in ('drives_per_game','drives_faced_per_game'):
                            continue
                        actual=row[f'{side}_{metric}_{suffix}']
                        if (size and n<size) or value is None:
                            assert actual is None
                        else:
                            assert actual==pytest.approx(value), (g,t,k,side,metric,suffix)
