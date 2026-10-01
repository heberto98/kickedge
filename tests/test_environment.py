import json
from types import SimpleNamespace
import duckdb
import pytest
from kickedge.io import write_json,write_parquet,sha256_file
from kickedge.features import load_contract
from kickedge.features.environment import build


def setup(tmp_path):
    c=SimpleNamespace(root=tmp_path,data_dir=tmp_path/'data',reports_dir=tmp_path/'reports')
    p=c.data_dir/'features/context/baseline';p.mkdir(parents=True)
    old={'game_id':'g','season':2025,'team':'A','opponent':'B','kicker_id':'k',
        'kickoff':'2025-09-07T17:00:00Z','prediction_cutoff':'2025-09-07T16:00:00Z',
        'xpm':2,'eligible_for_phase_3_training':True,'old_provenance':{'history':[{'xpm':3}]}}
    for name in load_contract()['predictor_columns_through_phase_3']:
        old.setdefault(name,1)
    old.update(game_type='REG',week=1)
    write_json(p/'kicker_game_features.json',[old])
    with duckdb.connect() as con:write_parquet(con,f"SELECT * REPLACE ('{old['kickoff']}' AS kickoff,'{old['prediction_cutoff']}' AS prediction_cutoff) FROM read_json_auto('{(p/'kicker_game_features.json').as_posix()}')",p/'kicker_game_features.parquet')
    write_json(p/'contract.json',load_contract())
    write_json(p/'build.json',{'artifacts':[{'filename':n,'sha256':sha256_file(p/n)} for n in ('contract.json','kicker_game_features.parquet','kicker_game_features.json')]})
    schedule=tmp_path/'schedule.parquet'
    with duckdb.connect() as con:write_parquet(con,"SELECT 'g' game_id,'A' home_team,'B' away_team,6.0 spread_line,46.0 total_line,-200 home_moneyline,180 away_moneyline,'outdoors' roof,68 AS \"temp\",10 wind,'s' stadium_id,'Test' stadium",schedule)
    write_json(c.data_dir/'manifests/sources.json',{'sources':[{'dataset':'schedules','path':'schedule.parquet','sha256':sha256_file(schedule),'downloaded_at':'2026-09-30T00:00:00Z'}]})
    return c,p,old,schedule


def test_no_experimental_values_in_training_and_prior_fields_preserved(tmp_path):
    c,p,old,_=setup(tmp_path);before=sha256_file(p/'kicker_game_features.parquet')
    out=build(c,p)
    with duckdb.connect() as con:
        result=con.execute('select * from read_parquet(?)',[str(out/'kicker_game_features.parquet')])
        new=dict(zip([d[0] for d in result.description],result.fetchone()))
    assert all(new[k]==v for k,v in old.items())
    assert new['eligible_for_phase_4_training']
    assert new['game_spread'] is None and new['temperature'] is None
    side=json.loads((out/'enrichment.json').read_text())[0]
    assert side['experimental_market']['game_spread']==-6
    assert side['experimental_weather']['temperature']==20
    assert side['experimental_weather']['wind_speed']==pytest.approx(16.09344)
    assert before==sha256_file(p/'kicker_game_features.parquet')
    hashes={f.name:sha256_file(f) for f in out.iterdir()}
    assert out==build(c,p)
    assert hashes=={f.name:sha256_file(f) for f in out.iterdir()}


def test_snapshot_tampering_and_duplicate_schedule_fail_closed(tmp_path):
    c,p,_,s=setup(tmp_path)
    with s.open('ab') as f:f.write(b'changed')
    with pytest.raises(ValueError,match='integrity'):build(c,p)


def test_contract_preserves_selector_and_no_context_waiver():
    c=load_contract()
    assert c['predictor_columns_through_phase_4']==c['predictor_columns_through_phase_3']
    assert len(c['predictor_columns_through_phase_4'])==82
    fields={f['name']:f for f in c['fields']}
    for name in c['phase_4_candidate_columns']:
        f=fields[name]
        assert f['implemented'] and f['current_usable']
        assert not f['historical_training_approved']
        assert f['publication_timestamp_required']
        assert f['temporal_class']=='point_in_time_context_data'
        assert f['null_behavior']
