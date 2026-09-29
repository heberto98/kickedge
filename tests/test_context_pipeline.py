import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kickedge.io import write_json,sha256_file
from test_game_context import fixture


def module(name):
    assert importlib.util.find_spec('kickedge.features.'+name), 'Phase 3 pipeline missing'
    return importlib.import_module('kickedge.features.'+name)


def prepared_fixture(tmp_path):
    ids,manifest,calendar=fixture(tmp_path/'outcomes')
    for name,rows in [('identities',ids),('manifest',manifest),('calendar',calendar)]:
        write_json(tmp_path/(name+'.json'),rows)
    from kickedge.features import load_contract
    predictors=load_contract()['predictor_columns_through_phase_2']
    baseline=[r|{n:0 for n in predictors}|dict(xpm=2,source_label={'retained':True},
        eligible_for_phase_2_training=True,phase_2_training_exclusion_reasons=[]) for r in ids]
    phase2=tmp_path/'data/features/teams/phase2'
    write_json(phase2/'kicker_game_features.json',baseline)
    write_json(phase2/'build.json',{'artifacts':[{'filename':'kicker_game_features.json',
        'sha256':sha256_file(phase2/'kicker_game_features.json')}]})
    write_json(tmp_path/'source.json',{'inputs':{'phase2_build':'phase2','phase2_build_sha256':sha256_file(phase2/'build.json'),
        'temporal_policy':'event-context-v1','calendar_policy':'phase3-calendar-v1'},
        **{n+'_sha256':sha256_file(tmp_path/(n+'.json')) for n in ('identities','manifest','calendar')}})
    return SimpleNamespace(root=tmp_path,data_dir=tmp_path/'data',reports_dir=tmp_path/'reports'),baseline


def test_combined_dataset_keeps_previous_fields_and_reproduces_bytes(tmp_path):
    config,old=prepared_fixture(tmp_path)
    build=module('context_materialize').build
    out=build(config,tmp_path)
    hashes={p.name:sha256_file(p) for p in out.iterdir()}
    assert build(config,tmp_path)==out
    assert hashes=={p.name:sha256_file(p) for p in out.iterdir()}
    rows=json.loads((out/'kicker_game_features.json').read_text())
    for a,b in zip(old,rows):
        assert all(b[k]==v for k,v in a.items())
        assert b['eligible_for_phase_3_training']
        assert b['calendar_historical_approximation'] and not b['calendar_point_in_time_verified']
    assert rows[3]['team_days_rest']==7
    assert rows[3]['team_two_point_attempts_before']==6


def test_bad_phase_two_eligibility_is_preserved(tmp_path):
    config,old=prepared_fixture(tmp_path)
    old[-1]['eligible_for_phase_2_training']=False
    p=tmp_path/'data/features/teams/phase2'
    write_json(p/'kicker_game_features.json',old)
    write_json(p/'build.json',{'artifacts':[{'filename':'kicker_game_features.json','sha256':sha256_file(p/'kicker_game_features.json')}]})
    s=json.loads((tmp_path/'source.json').read_text())
    s['inputs']['phase2_build_sha256']=sha256_file(p/'build.json');write_json(tmp_path/'source.json',s)
    out=module('context_materialize').build(config,tmp_path)
    row=json.loads((out/'kicker_game_features.json').read_text())[-1]
    assert not row['eligible_for_phase_3_training']
    assert row['phase_3_training_exclusion_reasons']==['phase_2_ineligible']


def test_context_input_tampering_fails_closed(tmp_path):
    config,_=prepared_fixture(tmp_path)
    with (tmp_path/'calendar.json').open('a') as f:f.write(' ')
    with pytest.raises(ValueError,match='integrity'):
        module('context_materialize').build(config,tmp_path)
