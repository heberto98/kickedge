"""Materialize Phase 3, then attach the unchanged Phase 2 dataset after freeze."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics

import duckdb

from kickedge.io import sha256_file,write_json,write_parquet,sql_literal
from . import load_contract
from .context import CALENDAR_NAMES,CALENDAR_POLICY,FEATURE_NAMES,calendar_field_approved,simulate
from .context_history import FEATURE_NAMES as HISTORY_NAMES
from .kicker import LabelOracle,instant,key
from .temporal import HISTORICAL_EVENT,POLICY_VERSION,temporal_evidence_valid
from .validation import validate_contract


def validate(rows,contract):
    fields=validate_contract(contract)
    if (contract.get('predictor_columns_phase_3')!=list(FEATURE_NAMES)
            or contract.get('predictor_columns_through_phase_3')!=contract['predictor_columns_through_phase_2']+list(FEATURE_NAMES)):
        raise ValueError('Invalid Phase 3 predictor contract')
    for name in FEATURE_NAMES:
        f=fields[name]
        if not f['implemented'] or not f['predictive_input_allowed'] or not f['historical_training_approved']:
            raise ValueError('Unapproved Phase 3 feature: '+name)
        if name in CALENDAR_NAMES and not calendar_field_approved(f,contract):
            raise ValueError('Invalid calendar feature policy')
        if name in HISTORY_NAMES and (f['temporal_class']!=HISTORICAL_EVENT or f['publication_timestamp_required']):
            raise ValueError('Invalid Phase 3 event policy')
    for r in rows:
        cutoff=instant(r['prediction_cutoff'])
        if cutoff>=instant(r['kickoff']):
            raise ValueError('Invalid context cutoff')
        for name in FEATURE_NAMES:
            v=r[name];f=fields[name]
            if v is None:
                if not f['nullable']:raise ValueError('Unexpected context NULL: '+name)
                continue
            valid=(type(v) is bool if f['dtype']=='boolean' else type(v) is int and v>=0 if f['dtype']=='integer'
                else isinstance(v,str) and v in ('REG','WC','DIV','CON','SB') if name=='game_type'
                else type(v) in (int,float) and math.isfinite(v) and v>=0)
            if not valid or ('attempt_rate' in name and v>1):
                raise ValueError('Invalid context feature value: '+name)
        cal=r['calendar_provenance']
        if (cal['calendar_policy']!=CALENDAR_POLICY or not cal['source_sha256']
                or not cal['historical_approximation'] or cal['point_in_time_verified']
                or r['is_home']!=(r['team']==cal['home_team']) or r['is_away']!=(r['team']==cal['away_team'])
                or r['is_home']==r['is_away']):
            raise ValueError('Invalid calendar provenance')
        for side in ('team','opponent'):
            history=r['context_history_provenance'][side]['history']
            if len({h['game_id'] for h in history})!=len(history):
                raise ValueError('Duplicate context prior game')
            for h in history:
                if (h['game_id']==r['game_id'] or h['season']!=r['season'] or h['team']!=r[side]
                        or h['temporal_class']!=HISTORICAL_EVENT or not temporal_evidence_valid(h,cutoff)):
                    raise ValueError('Context event leakage')
            last=max(history,key=lambda h:(instant(h['kickoff']),h['game_id'])) if history else None
            expected=(instant(cal['rest_reference_kickoff'])-instant(last['kickoff'])).total_seconds()/86400 if last else None
            if r[side+'_days_rest']!=expected:
                raise ValueError('Incorrect prior game rest')
            for label,threshold in [('short_week',6),('long_rest',8)]:
                flag=(expected<threshold if label=='short_week' else expected>threshold) if expected is not None else None
                if r[f'{side}_{label}_flag'] is not flag:
                    raise ValueError('Incorrect rest flag')
            for n in (3,5):
                if r[f'{side}_has_{n}_prior_games']!=(len(history)>=n):
                    raise ValueError('Incorrect context sample flag')


def summarize(rows):
    coverage={n:{'non_null':sum(r[n] is not None for r in rows),'null':sum(r[n] is None for r in rows)} for n in FEATURE_NAMES}
    rest={};flags={}
    for side in ('team','opponent'):
        v=sorted(r[side+'_days_rest'] for r in rows if r[side+'_days_rest'] is not None)
        rest[side]={'non_null':len(v),'null':len(rows)-len(v),'min':min(v,default=None),'median':statistics.median(v) if v else None,
            'mean':statistics.mean(v) if v else None,'max':max(v,default=None),
            'under_6_days':sum(x<6 for x in v),'6_to_8_days':sum(6<=x<=8 for x in v),'over_8_days':sum(x>8 for x in v)}
        for kind in ('short_week','long_rest'):
            name=f'{side}_{kind}_flag'
            flags[name]={'true':sum(r[name] is True for r in rows),'false':sum(r[name] is False for r in rows),'null':sum(r[name] is None for r in rows)}
    candidates={
        'week_1':next((r for r in rows if r['week']==1 and r['team_days_rest'] is None),None),
        'after_bye':next((r for r in rows if r['team_days_rest'] is not None and r['team_days_rest']>=13),None),
        'recent_two_point_tendency':max((r for r in rows if r['team_two_point_attempt_rate_last_3'] is not None),
            key=lambda r:(r['team_two_point_attempt_rate_last_3'],r['team_two_point_attempts_last_3']),default=None)}
    columns=('game_id','team','opponent','kicker_name','season','week','game_type','is_home','team_days_rest','opponent_days_rest',
        'team_long_rest_flag','team_two_point_attempts_last_3','team_two_point_attempt_rate_last_3')
    return {'rows':len(rows),'phase_3_predictors':len(FEATURE_NAMES),'new_columns':len(FEATURE_NAMES)-3,'existing_columns_promoted':['season','week','game_type'],
        'coverage':coverage,'coverage_pct':100*sum(v['non_null'] for v in coverage.values())/(len(rows)*len(FEATURE_NAMES)) if rows else None,
        'days_rest_distribution':rest,'flags':flags,'training_eligible':sum(r['eligible_for_phase_3_training'] for r in rows),
        'training_exclusions':dict(Counter(s for r in rows for s in r['phase_3_training_exclusion_reasons'])),
        'calendar_policy':CALENDAR_POLICY,'calendar_point_in_time_verified':False,
        'rest_historical_kickoff_fallback_rows':sum(r['calendar_provenance']['rest_reference']=='historical_kickoff_fallback' for r in rows),
        'examples':{name:{k:r.get(k) for k in columns} for name,r in candidates.items() if r is not None}}


def build(config,prepared=None):
    if prepared is None:
        prepared=config.root/json.loads((config.data_dir/'features/context_inputs/latest.json').read_text())['path']
    prepared=Path(prepared)
    source=json.loads((prepared/'source.json').read_text())
    if source['inputs']['temporal_policy']!=POLICY_VERSION or source['inputs']['calendar_policy']!=CALENDAR_POLICY:
        raise ValueError('Unapproved context policy')
    for name in ('identities','manifest','calendar'):
        if sha256_file(prepared/(name+'.json'))!=source[name+'_sha256']:
            raise ValueError('Context input integrity failure')
    contract=load_contract();validate([],contract)
    inputs={'prepared_build':prepared.name,'prepared_source_sha256':sha256_file(prepared/'source.json'),
        'phase2_build':source['inputs']['phase2_build'],'phase2_build_sha256':source['inputs']['phase2_build_sha256'],
        'contract_sha256':sha256_file(Path(__file__).parent/'contract.json'),
        'code_sha256':{p.name:sha256_file(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
        'python':platform.python_version(),'duckdb':duckdb.__version__,'temporal_policy':POLICY_VERSION,'calendar_policy':CALENDAR_POLICY}
    digest=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:20]
    directory=config.data_dir/'features/context'/digest;directory.mkdir(parents=True,exist_ok=True)
    ids=json.loads((prepared/'identities.json').read_text())
    manifest=json.loads((prepared/'manifest.json').read_text())
    calendar=json.loads((prepared/'calendar.json').read_text())
    chain='0'*64
    with (directory/'events.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        def sink(event):
            nonlocal chain
            payload={'previous_sha256':chain,**event};chain=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
            stream.write(json.dumps({**payload,'event_sha256':chain},sort_keys=True)+'\n');stream.flush()
        rows=simulate(ids,LabelOracle(prepared/'outcomes',manifest),calendar,sink)
    validate(rows,contract)
    path=directory/'features_frozen.json';write_json(path,rows);frozen_hash=sha256_file(path)
    write_json(directory/'freeze.json',{'inputs':inputs,'features_sha256':frozen_hash,
        'event_chain_final_sha256':chain,'events_sha256':sha256_file(directory/'events.jsonl')})
    # Read the target-bearing prior dataset only after every Phase 3 row freezes.
    phase2=config.data_dir/'features/teams'/inputs['phase2_build']
    if sha256_file(phase2/'build.json')!=inputs['phase2_build_sha256']:
        raise ValueError('Phase 2 build integrity failure')
    meta=json.loads((phase2/'build.json').read_text())
    expected=next(a['sha256'] for a in meta['artifacts'] if a['filename']=='kicker_game_features.json')
    if sha256_file(phase2/'kicker_game_features.json')!=expected:
        raise ValueError('Phase 2 dataset integrity failure')
    baseline={key(r):r for r in json.loads((phase2/'kicker_game_features.json').read_text())}
    if set(baseline)!={key(r) for r in rows}:
        raise ValueError('Phase 2/3 populations differ')
    dataset=[]
    for r in rows:
        old=baseline[key(r)]
        if any(old[n]!=r[n] for n in old.keys() & r.keys()):
            raise ValueError('Phase 3 attempted to overwrite a previous field')
        reasons=[]
        if not old['eligible_for_phase_2_training']:reasons.append('phase_2_ineligible')
        if r['context_history_unavailable_before_cutoff']:reasons.append('context_history_unavailable')
        dataset.append({**old,**r,'calendar_historical_approximation':True,'calendar_point_in_time_verified':False,
            'context_features_temporally_compliant':True,'eligible_for_phase_3_training':not reasons,
            'phase_3_training_exclusion_reasons':reasons})
    if sha256_file(path)!=frozen_hash:raise ValueError('Frozen context changed during target join')
    write_json(directory/'kicker_game_features.json',dataset);write_json(directory/'contract.json',contract)
    with duckdb.connect() as con:
        write_parquet(con,f"SELECT * FROM read_json_auto({sql_literal(str(directory/'kicker_game_features.json'))},sample_size=-1,maximum_object_size=12000000)",directory/'kicker_game_features.parquet')
    stats=summarize(dataset);write_json(directory/'summary.json',stats)
    write_json(directory/'build.json',{'build_id':digest,'inputs':inputs,'row_count':len(dataset),
        'artifacts':[{'filename':p.name,'sha256':sha256_file(p)} for p in sorted(directory.iterdir()) if p.is_file() and p.name!='build.json']})
    write_json(config.data_dir/'features/context/latest.json',{'build_id':digest,'path':directory.relative_to(config.root).as_posix()})
    write_json(config.reports_dir/'game_context_phase3.json',{'build_id':digest,**stats})
    return directory
