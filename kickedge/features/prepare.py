"""Offline preparation of identity-only inputs and physically separate outcomes."""
from collections import defaultdict
from datetime import timedelta
import hashlib
import json
from pathlib import Path

import duckdb

from kickedge.io import records, sha256_file, write_json
from .kicker import instant, key


POLICY = {'version': 'kicker-features-v1', 'availability': 'experimental_result_plus_24h',
          'history_lag_hours': 24, 'cutoff_minutes': 60, 'history_scope': 'same_season_global_kicker',
          'availability_verified': False, 'eligible_for_final_training': False}


def prepare(config, base=None):
    if base is None:
        base = config.root / json.loads((config.data_dir/'processed/latest.json').read_text())['path']
    base = Path(base)
    meta = json.loads((base/'build.json').read_text())
    hashes = {}
    for name in ('games.parquet', 'labels.parquet'):
        expected = next(a['sha256'] for a in meta['artifacts'] if a['path'].endswith('/'+name) or a['path'].endswith('\\'+name))
        if sha256_file(base/name) != expected:
            raise ValueError('Historical input integrity failure: '+name)
        hashes[name] = expected
    lock = json.loads((base/'source_lock.json').read_text())
    clocks, clocks_sources = {}, {}
    with duckdb.connect() as con:
        con.execute("SET TimeZone='UTC'")
        labels = records(con, 'SELECT * FROM read_parquet(?)', [str(base/'labels.parquet')])
        seasons = {r['season'] for r in labels}
        for source in lock['sources']:
            if source['dataset'] != 'pbp' or source['season'] not in seasons:
                continue
            path = config.root/source['path']
            if sha256_file(path) != source['sha256']:
                raise ValueError('PBP clock input integrity failure')
            clocks_sources[str(source['season'])] = source['sha256']
            for r in records(con, """SELECT game_id, count(DISTINCT start_time) clock_versions,
                timezone('America/New_York',try_strptime(min(start_time),'%m/%d/%y, %H:%M:%S'))::VARCHAR kickoff,
                max(try_cast(time_of_day AS TIMESTAMPTZ))::VARCHAR last_event
                FROM read_parquet(?) GROUP BY game_id""", [str(path)]):
                if r['clock_versions'] != 1 or not r['kickoff'] or not r['last_event']:
                    raise ValueError('Unresolved actual kickoff: '+r['game_id'])
                clocks[r['game_id']] = r
        games = {r['game_id']: r for r in records(con, """SELECT game_id,
            timezone('America/New_York',(gameday||' '||gametime)::TIMESTAMP)::VARCHAR scheduled_kickoff
            FROM read_parquet(?)""", [str(base/'games.parquet')])}
    inputs = {'historical_build': base.name, 'source_hashes': hashes, 'pbp_clock_hashes': clocks_sources,
              'policy': POLICY, 'preparation_code_sha256': sha256_file(Path(__file__))}
    digest = hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:20]
    directory = config.data_dir/'features/kicker_inputs'/digest
    outcomes, identities, manifest = defaultdict(list), [], {}
    for r in labels:
        clock = clocks[r['game_id']]
        kickoff, scheduled = instant(clock['kickoff']), instant(games[r['game_id']]['scheduled_kickoff'])
        end = instant(clock['last_event'])
        if not kickoff <= end or abs((kickoff-scheduled).total_seconds()) > 12*3600:
            raise ValueError('Implausible game clocks: '+r['game_id'])
        identities.append({k:r[k] for k in ('game_id','season','week','game_type','team','opponent','kicker_name')} | {
            'kicker_id': r['player_id'], 'kickoff': kickoff.isoformat(),
            'prediction_cutoff': (min(kickoff,scheduled)-timedelta(minutes=60)).isoformat()})
        outcomes[r['game_id']].append({**r,'kicker_id':r['player_id']})
        manifest[r['game_id']] = {'filename':r['game_id']+'.json',
            'available_at':max(kickoff+timedelta(hours=24),end).isoformat(), 'availability_verified':False,
            'availability_basis':'experimental_24h_after_actual_start_and_not_before_last_event',
            'actual_kickoff':kickoff.isoformat(), 'scheduled_kickoff':scheduled.isoformat(),
            'last_event':end.isoformat(), 'clock_source_sha256':clocks_sources[str(r['season'])]}
    if len({key(r) for r in identities}) != len(identities):
        raise ValueError('Duplicate identity in historical population')
    for game, rows in sorted(outcomes.items()):
        path = directory/'outcomes'/manifest[game]['filename']
        write_json(path, sorted(rows,key=key))
        manifest[game]['sha256'] = sha256_file(path)
    write_json(directory/'identities.json',sorted(identities,key=lambda r:(r['kickoff'],key(r))))
    write_json(directory/'manifest.json',manifest)
    write_json(directory/'source.json', {'inputs':inputs, 'identities_sha256':sha256_file(directory/'identities.json'),
        'manifest_sha256':sha256_file(directory/'manifest.json'), 'row_count':len(identities)})
    write_json(config.data_dir/'features/kicker_inputs/latest.json',{'build_id':digest,'path':directory.relative_to(config.root).as_posix()})
    return directory
