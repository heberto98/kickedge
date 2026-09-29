"""Offline Phase 3 inputs from the frozen schedule, clocks and team-game counts."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import duckdb

from kickedge.io import records,sha256_file,write_json
from .context import CALENDAR_CLASS,CALENDAR_POLICY
from .temporal import POLICY_VERSION


def prepare(config, phase2=None):
    if phase2 is None:
        phase2=config.root/json.loads((config.data_dir/'features/teams/latest.json').read_text())['path']
    phase2=Path(phase2)
    meta=json.loads((phase2/'build.json').read_text())
    for a in meta['artifacts']:
        if sha256_file(phase2/a['filename'])!=a['sha256']:
            raise ValueError('Phase 2 artifact integrity failure')
    prior=config.data_dir/'features/team_inputs'/meta['inputs']['prepared_build']
    if sha256_file(prior/'source.json')!=meta['inputs']['prepared_source_sha256']:
        raise ValueError('Phase 2 source integrity failure')
    src=json.loads((prior/'source.json').read_text())
    for name in ('identities','manifest'):
        if sha256_file(prior/(name+'.json'))!=src[name+'_sha256']:
            raise ValueError('Phase 2 clock/identity integrity failure')
    ids=json.loads((prior/'identities.json').read_text())
    clocks=json.loads((prior/'manifest.json').read_text())
    base=config.data_dir/'processed'/src['inputs']['historical_build']
    original=json.loads((base/'build.json').read_text())
    hashes={}
    for name in ('games.parquet','team_games.parquet'):
        expected=next(a['sha256'] for a in original['artifacts'] if a['path'].replace('\\','/').endswith('/'+name))
        if sha256_file(base/name)!=expected:
            raise ValueError('Historical context integrity failure: '+name)
        hashes[name]=expected
    lock=json.loads((base/'source_lock.json').read_text())
    schedule=next(s for s in lock['sources'] if s['dataset']=='schedules')
    if sha256_file(config.root/schedule['path'])!=schedule['sha256']:
        raise ValueError('Historical schedule source integrity failure')
    with duckdb.connect() as con:
        games=records(con,'SELECT game_id,season,week,game_type,home_team,away_team FROM read_parquet(?)',[str(base/'games.parquet')])
        outcomes=records(con,'''SELECT game_id,season,team,opponent,two_pt_attempts,team_xpa,
            coverage_ok,recorded_tries,pbp_source_sha256 FROM read_parquet(?) ORDER BY game_id,team''',[str(base/'team_games.parquet')])
    if any(not r['coverage_ok'] or r['recorded_tries']!=r['two_pt_attempts']+r['team_xpa'] for r in outcomes):
        raise ValueError('Invalid completed conversion counts')
    calendar={g['game_id']:{**g,'scheduled_kickoff':clocks[g['game_id']].get('scheduled_kickoff'),
        'source_sha256':hashes['games.parquet'],'schedule_source_sha256':schedule['sha256'],
        'schedule_downloaded_at':schedule['downloaded_at'],'temporal_class':CALENDAR_CLASS,
        'calendar_policy':CALENDAR_POLICY} for g in games}
    if len(calendar)!=len(games) or set(calendar)!=set(clocks):
        raise ValueError('Calendar population differs from frozen games')
    by_game=defaultdict(list)
    for r in outcomes:
        by_game[r['game_id']].append({**r,'team_games_source_sha256':hashes['team_games.parquet']})
    if set(by_game)!=set(clocks) or any(len(rows)!=2 for rows in by_game.values()):
        raise ValueError('Invalid conversion team-game population')
    inputs={'phase2_build':phase2.name,'phase2_build_sha256':sha256_file(phase2/'build.json'),
        'phase2_prepared_source_sha256':sha256_file(prior/'source.json'),'historical_build':base.name,
        'source_hashes':hashes,'schedule_source_sha256':schedule['sha256'],
        'temporal_policy':POLICY_VERSION,'calendar_policy':CALENDAR_POLICY,
        'preparation_code_sha256':sha256_file(Path(__file__))}
    digest=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:20]
    directory=config.data_dir/'features/context_inputs'/digest
    manifest={}
    for game,rows in sorted(by_game.items()):
        path=directory/'outcomes'/(game+'.json');write_json(path,rows)
        manifest[game]={**clocks[game],'filename':path.name,'sha256':sha256_file(path)}
    for name,value in [('identities',ids),('manifest',manifest),('calendar',calendar)]:
        write_json(directory/(name+'.json'),value)
    write_json(directory/'source.json',{'inputs':inputs,'row_count':len(ids),
        **{n+'_sha256':sha256_file(directory/(n+'.json')) for n in ('identities','manifest','calendar')}})
    write_json(config.data_dir/'features/context_inputs/latest.json',{'build_id':digest,'path':directory.relative_to(config.root).as_posix()})
    return directory
