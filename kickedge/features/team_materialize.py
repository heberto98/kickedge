"""Freeze Phase 2 predictors, then join the unchanged Phase 1 dataset."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import platform

import duckdb

from kickedge.io import write_json, write_parquet, sql_literal, sha256_file
from . import load_contract
from .kicker import LabelOracle, instant, key
from .team import FEATURE_NAMES, simulate
from .temporal import HISTORICAL_EVENT, POLICY_VERSION, temporal_evidence_valid
from .validation import validate_contract


def validate(rows, contract):
    fields=validate_contract(contract)
    if contract.get('predictor_columns_phase_2')!=list(FEATURE_NAMES):
        raise ValueError('Invalid Phase 2 predictor contract')
    for name in FEATURE_NAMES:
        f=fields[name]
        if (not f['implemented'] or not f['historical_training_approved'] or not f['predictive_input_allowed']
                or f['role']!='feature' or f['temporal_class']!=HISTORICAL_EVENT or f['publication_timestamp_required']):
            raise ValueError('Invalid Phase 2 temporal contract: '+name)
    for r in rows:
        cutoff=instant(r['prediction_cutoff'])
        if cutoff>=instant(r['kickoff']):
            raise ValueError('Invalid Phase 2 cutoff')
        for name in FEATURE_NAMES:
            value=r[name]
            if value is None:
                if not fields[name]['nullable']:
                    raise ValueError('Unexpected NULL feature value: '+name)
                continue
            if (type(value) not in (int,float) or not math.isfinite(value)
                    or ('epa' not in name and value<0)
                    or (any(s in name for s in ('success_rate','red_zone_td_rate','td_per_drive','td_allowed_per_drive')) and value>1)
                    or (name.endswith('games_before') and type(value) is not int)):
                raise ValueError('Invalid Phase 2 feature value: '+name)
        for side in ('offense','defense'):
            expected_team=r['team'] if side=='offense' else r['opponent']
            provenance=r['team_feature_provenance'][side]
            if provenance['team']!=expected_team:
                raise ValueError('Incorrect offense/opponent defense')
            for h in provenance['history']:
                if (h['game_id']==r['game_id'] or h['season']!=r['season']
                        or h['team' if side=='offense' else 'opponent']!=expected_team
                        or not temporal_evidence_valid(h,cutoff)):
                    raise ValueError('Phase 2 history leakage')


def summary(rows):
    coverage={name:{'non_null':sum(r[name] is not None for r in rows),
                    'null':sum(r[name] is None for r in rows)} for name in FEATURE_NAMES}
    cols=('game_id','team','opponent','kicker_name','season','week','offense_games_before',
          'offense_points_per_game_before','defense_games_before','defense_points_allowed_per_game_before',
          'offense_epa_per_play_before','defense_epa_allowed_per_play_before')
    samples={}
    for name,metric,count in [('strong_offense','offense_points_per_game_before','offense_games_before'),
                              ('permissive_defense','defense_points_allowed_per_game_before','defense_games_before')]:
        choices=[r for r in rows if r[count]>=5 and r[metric] is not None]
        if choices:
            samples[name]={k:max(choices,key=lambda r:r[metric]).get(k) for k in cols}
    first=next((r for r in rows if r['offense_games_before']==0),None)
    if first:
        samples['early_season']={k:first.get(k) for k in cols}
    return {'rows':len(rows),'new_features':len(FEATURE_NAMES),'coverage':coverage,
        'coverage_pct':100*sum(c['non_null'] for c in coverage.values())/(len(rows)*len(FEATURE_NAMES)) if rows else None,
        'training_eligible':sum(r['eligible_for_phase_2_training'] for r in rows),
        'training_exclusions':dict(Counter(s for r in rows for s in r['phase_2_training_exclusion_reasons'])),
        'null_reasons':dict(Counter(reason for r in rows for reason in r['team_feature_provenance']['null_reasons'].values())),
        'examples':samples}


def build(config, prepared=None):
    if prepared is None:
        prepared=config.root/json.loads((config.data_dir/'features/team_inputs/latest.json').read_text())['path']
    prepared=Path(prepared)
    source=json.loads((prepared/'source.json').read_text())
    if source['inputs']['temporal_policy']!=POLICY_VERSION:
        raise ValueError('Unapproved team temporal policy')
    for name in ('identities','manifest'):
        if sha256_file(prepared/(name+'.json'))!=source[name+'_sha256']:
            raise ValueError('Prepared team input integrity failure')
    contract=load_contract()
    validate([],contract)
    inputs={'prepared_build':prepared.name,'prepared_source_sha256':sha256_file(prepared/'source.json'),
        'phase1_build':source['inputs']['phase1_build'],'phase1_build_sha256':source['inputs']['phase1_build_sha256'],
        'contract_sha256':sha256_file(Path(__file__).parent/'contract.json'),
        'code_sha256':{p.name:sha256_file(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
        'python':platform.python_version(),'duckdb':duckdb.__version__,'temporal_policy':POLICY_VERSION}
    digest=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:20]
    directory=config.data_dir/'features/teams'/digest
    directory.mkdir(parents=True,exist_ok=True)
    identities=json.loads((prepared/'identities.json').read_text())
    manifest=json.loads((prepared/'manifest.json').read_text())
    chain='0'*64
    with (directory/'events.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        def sink(event):
            nonlocal chain
            payload={'previous_sha256':chain,**event}
            chain=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
            stream.write(json.dumps({**payload,'event_sha256':chain},sort_keys=True)+'\n')
            stream.flush()
        rows=simulate(identities,LabelOracle(prepared/'outcomes',manifest),sink)
    validate(rows,contract)
    feature_path=directory/'features_frozen.json'
    write_json(feature_path,rows)
    frozen_hash=sha256_file(feature_path)
    write_json(directory/'freeze.json',{'inputs':inputs,'features_sha256':frozen_hash,
        'event_chain_final_sha256':chain,'events_sha256':sha256_file(directory/'events.jsonl')})
    # Phase 1 contains G's target: do not read it until all Phase 2 features freeze.
    phase1=config.data_dir/'features/kicker'/inputs['phase1_build']
    if sha256_file(phase1/'build.json')!=inputs['phase1_build_sha256']:
        raise ValueError('Phase 1 build integrity failure')
    meta=json.loads((phase1/'build.json').read_text())
    expected=next(a['sha256'] for a in meta['artifacts'] if a['filename']=='kicker_game_features.json')
    if sha256_file(phase1/'kicker_game_features.json')!=expected:
        raise ValueError('Phase 1 dataset integrity failure')
    baseline={key(r):r for r in json.loads((phase1/'kicker_game_features.json').read_text())}
    if set(baseline)!={key(r) for r in rows}:
        raise ValueError('Phase 1/2 populations differ')
    dataset=[]
    for r in rows:
        old=baseline[key(r)]
        if any(old.get(k)!=r[k] for k in ('season','team','opponent','kickoff','prediction_cutoff')):
            raise ValueError('Phase 1/2 identity clocks differ')
        reasons=[]
        if not old['eligible_for_final_training']:
            reasons.append('phase_1_ineligible')
        if r['team_history_unavailable_before_cutoff']:
            reasons.append('team_history_unavailable')
        if 'missing_source_metric' in r['team_feature_provenance']['null_reasons'].values():
            reasons.append('missing_team_source_metric')
        dataset.append({**old,**{k:v for k,v in r.items() if k not in old},
            'team_features_temporally_verified':True,'eligible_for_phase_2_training':not reasons,
            'phase_2_training_exclusion_reasons':reasons})
    if sha256_file(feature_path)!=frozen_hash:
        raise ValueError('Frozen Phase 2 features changed')
    write_json(directory/'kicker_game_features.json',dataset)
    write_json(directory/'contract.json',contract)
    with duckdb.connect() as con:
        write_parquet(con,f"SELECT * FROM read_json_auto({sql_literal(str(directory/'kicker_game_features.json'))},sample_size=-1,maximum_object_size=8000000)",directory/'kicker_game_features.parquet')
    stats=summary(dataset)
    write_json(directory/'summary.json',stats)
    write_json(directory/'build.json',{'build_id':digest,'inputs':inputs,'row_count':len(dataset),
        'artifacts':[{'filename':p.name,'sha256':sha256_file(p)} for p in sorted(directory.iterdir()) if p.is_file() and p.name!='build.json']})
    write_json(config.data_dir/'features/teams/latest.json',{'build_id':digest,'path':directory.relative_to(config.root).as_posix()})
    write_json(config.reports_dir/'team_features_phase2.json',{'build_id':digest,**stats})
    return directory
