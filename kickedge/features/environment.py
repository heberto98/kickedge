"""Offline Phase 4: safe training columns plus explicitly experimental sidecars."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import duckdb

from kickedge.io import records,sha256_file,sql_literal,write_json,write_parquet
from kickedge.transform import TEAM_MACRO
from . import load_contract
from .market import FEATURE_NAMES as MARKET_NAMES,market_features,schedule_market
from .validation import validate_contract
from kickedge.providers.weather import weather_features

WEATHER_NAMES=('temperature','wind_speed','wind_gust','precipitation_probability',
    'precipitation','weather_code','is_dome','roof_type')
FEATURE_NAMES=MARKET_NAMES+WEATHER_NAMES
IDENTITY=('game_id','season','team','opponent','kicker_id','kickoff','prediction_cutoff')


def historical_enrichment(identity,schedule,source):
    """Only identity and market/venue/weather projections enter feature builders."""
    market=market_features(identity,schedule_market(schedule,source['sha256']) if schedule else None)
    venue={'game_id':identity['game_id'],'roof_type':schedule.get('roof'),
        'source':'nflverse/schedules','source_sha256':source['sha256'],
        'downloaded_at':source.get('downloaded_at'),'stadium_id':schedule.get('stadium_id')}
    temp=schedule.get('temp');wind=schedule.get('wind')
    weather=weather_features(identity,{
        'game_id':identity['game_id'],'kind':'observed','source':'nflverse/schedules',
        'source_sha256':source['sha256'],'downloaded_at':source.get('downloaded_at'),
        'valid_time':identity['kickoff'],'values':{'temperature':(temp-32)*5/9 if temp is not None else None,
            'wind_speed':wind*1.609344 if wind is not None else None}},venue)
    # These retrospective snapshots are never promoted by the calendar exception.
    if market['training_eligible'] or weather['training_eligible']:
        raise ValueError('Retrospective environment was incorrectly approved')
    return {**identity,'training_values':dict.fromkeys(FEATURE_NAMES),
        'experimental_market':market['values'],'experimental_weather':weather['values'],
        'market_reasons':market['reasons'],'weather_reasons':weather['reasons'],
        'market_provenance':market['provenance'],'weather_provenance':weather['provenance'],
        'phase_4_additions_verified':False}


def summary(enrichment,eligibility):
    per_season={}
    for season in sorted({r['season'] for r in enrichment}):
        rows=[r for r in enrichment if r['season']==season]
        per_season[str(season)]={'rows':len(rows),'eligible_baseline':sum(eligibility[(r['game_id'],r['team'],r['kicker_id'])] for r in rows),
            'experimental_non_null':{n:sum(r['experimental_market' if n in MARKET_NAMES else 'experimental_weather'].get(n) is not None for r in rows) for n in FEATURE_NAMES},
            'training_non_null':{n:0 for n in FEATURE_NAMES},
            'roof_types':dict(Counter(str(r['experimental_weather'].get('roof_type')) for r in rows))}
    return {'rows':len(enrichment),'baseline_predictors':82,'new_training_predictors':0,
        'training_eligible':sum(eligibility.values()),'candidate_columns':list(FEATURE_NAMES),
        'historical_forecast_verified_rows':0,'historical_market_verified_rows':0,
        'per_season':per_season,'policy':'phase4-pit-v1',
        'note':'Training selector retains Phase 3. Retrospective market, observed weather and roof live only in experimental sidecar.'}


def build(config,phase3=None):
    if phase3 is None:
        phase3=config.root/json.loads((config.data_dir/'features/context/latest.json').read_text())['path']
    phase3=Path(phase3)
    meta=json.loads((phase3/'build.json').read_text())
    expected={a['filename']:a['sha256'] for a in meta['artifacts']}
    for name in ('kicker_game_features.parquet','kicker_game_features.json','contract.json'):
        if expected.get(name)!=sha256_file(phase3/name):raise ValueError('Phase 3 integrity failure')
    contract=load_contract();validate_contract(contract)
    old_contract=json.loads((phase3/'contract.json').read_text(encoding='utf-8'))
    prior=old_contract['predictor_columns_through_phase_3']
    fields={f['name']:f for f in contract['fields']};old_fields={f['name']:f for f in old_contract['fields']}
    if (len(prior)!=82 or contract['predictor_columns_through_phase_3']!=prior
            or contract['predictor_columns_through_phase_4']!=prior
            or any(fields[n]!=old_fields[n] for n in prior)):
        raise ValueError('Phase 4 changed the prior predictor contract')
    manifest=json.loads((config.data_dir/'manifests/sources.json').read_text())
    source=next(s for s in manifest['sources'] if s['dataset']=='schedules')
    schedule_path=config.root/source['path']
    if sha256_file(schedule_path)!=source['sha256']:raise ValueError('Schedule integrity failure')
    inputs={'phase3_build':phase3.name,'phase3_build_sha256':sha256_file(phase3/'build.json'),
        'phase3_parquet_sha256':expected['kicker_game_features.parquet'],'schedule_sha256':source['sha256'],
        'schedule_downloaded_at':source.get('downloaded_at'),
        'contract_sha256':sha256_file(Path(__file__).with_name('contract.json')),
        'code_sha256':{str(p.relative_to(Path(__file__).parents[1])):sha256_file(p) for p in
            [Path(__file__),Path(__file__).with_name('market.py'),Path(__file__).parents[1]/'providers/weather.py',Path(__file__).parents[1]/'transform.py']},
        'duckdb_version':duckdb.__version__,'policy':'phase4-pit-v1'}
    digest=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:20]
    out=config.data_dir/'features/environment'/digest
    baseline=phase3/'kicker_game_features.parquet'
    with duckdb.connect() as con:
        con.execute(TEAM_MACRO)
        # Read original timestamp strings: Parquet auto-inference dropped UTC offsets.
        # Only these identity fields enter builders; no outcome fields are selected.
        projection=','.join((f"CAST(json_extract_string(json,'$.{n}') AS INTEGER)" if n=='season'
            else f"json_extract_string(json,'$.{n}')")+' AS '+n for n in IDENTITY)
        ids=records(con,'SELECT '+projection+' FROM read_json_objects(?) ORDER BY game_id,team,kicker_id',
            [str(phase3/'kicker_game_features.json')])
        schedules=records(con,'''SELECT game_id,team_code(home_team) home_team,team_code(away_team) away_team,
            CAST(spread_line AS DOUBLE) spread_line,CAST(total_line AS DOUBLE) total_line,
            home_moneyline,away_moneyline,roof,temp,wind,stadium_id
            FROM read_parquet(?)''',[str(schedule_path)])
        schedule_map={s['game_id']:s for s in schedules}
        if len(schedule_map)!=len(schedules):raise ValueError('Duplicate schedule game')
        if len({(r['game_id'],r['team'],r['kicker_id']) for r in ids})!=len(ids):raise ValueError('Duplicate kicker-game')
        missing={r['game_id'] for r in ids}-set(schedule_map)
        if missing:raise ValueError('Missing schedule identity')
        enrichment=[historical_enrichment(r,schedule_map[r['game_id']],source) for r in ids]
        write_json(out/'enrichment.json',enrichment)
        frozen=sha256_file(out/'enrichment.json')
        # Attach the target-bearing baseline only after enrichment is frozen.
        eligibility={(r['game_id'],r['team'],r['kicker_id']):r['eligible_for_phase_3_training'] for r in records(con,
            'SELECT game_id,team,kicker_id,eligible_for_phase_3_training FROM read_parquet(?)',[str(baseline)])}
        if set(eligibility)!={(r['game_id'],r['team'],r['kicker_id']) for r in ids}:
            raise ValueError('Phase 3 JSON/Parquet population mismatch')
        extra=','.join('CAST(NULL AS '+('BOOLEAN' if n=='is_dome' else 'VARCHAR' if n=='roof_type' else 'DOUBLE')+') AS '+n for n in FEATURE_NAMES)
        old_names={r['column_name'] for r in records(con,'DESCRIBE SELECT * FROM read_parquet(?)',[str(baseline)])}
        if old_names & set(FEATURE_NAMES):raise ValueError('Phase 4 column collision')
        write_parquet(con,f'SELECT *,{extra},eligible_for_phase_3_training AS eligible_for_phase_4_training,FALSE AS phase_4_additions_verified FROM read_parquet({sql_literal(str(baseline))})',out/'kicker_game_features.parquet')
    if sha256_file(out/'enrichment.json')!=frozen or sha256_file(baseline)!=expected['kicker_game_features.parquet']:
        raise ValueError('Frozen enrichment or baseline changed')
    stats=summary(enrichment,eligibility)
    write_json(out/'summary.json',stats);write_json(out/'contract.json',contract)
    write_json(out/'build.json',{'build_id':digest,'inputs':inputs,'row_count':len(ids),
        'artifacts':[{'filename':p.name,'sha256':sha256_file(p)} for p in sorted(out.iterdir()) if p.is_file() and p.name!='build.json']})
    write_json(config.data_dir/'features/environment/latest.json',{'build_id':digest,'path':out.relative_to(config.root).as_posix()})
    write_json(config.reports_dir/'market_weather_phase4.json',{'build_id':digest,**stats})
    return out
