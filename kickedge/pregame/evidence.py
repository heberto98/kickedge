"""Project permitted inputs before selection; untimed tables never supply candidates."""
from bisect import bisect_right
from collections import defaultdict
from datetime import timedelta
import json

import duckdb

from kickedge.ingest import verify_source
from kickedge.io import records, sha256_file
from .official import evidence as official_evidence
from .select import instant, iso


def team_id(value):
    return {'STL': 'LA', 'LAR': 'LA', 'OAK': 'LV', 'SD': 'LAC', 'SDG': 'LAC',
            'JAC': 'JAX', 'WSH': 'WAS'}.get(value, value)


def latest_snapshot(series, pk, team, cutoff):
    i = bisect_right(series, cutoff) - 1
    dt = series[i] if i >= 0 else None
    return dt, pk.get((team, dt), []) if dt else [], len(series) - i - 1


def schedule_rows(con, path, cutoff_minutes):
    con.execute("SET TimeZone='UTC'")
    # Scores, participants and game statistics are intentionally not projected.
    games = records(con, """SELECT game_id,season,week,game_type,home_team,away_team,
        timezone('America/New_York', (gameday || ' ' || gametime)::TIMESTAMP)::VARCHAR kickoff
        FROM read_parquet(?) ORDER BY game_id""", [str(path)])
    result = []
    for g in games:
        kickoff = instant(g['kickoff'])
        for side, other in [('home_team', 'away_team'), ('away_team', 'home_team')]:
            result.append({k: g[k] for k in ('game_id', 'season', 'week', 'game_type')} | {
                'team': g[side], 'opponent': g[other], 'kickoff_utc': iso(kickoff),
                'prediction_cutoff': iso(kickoff - timedelta(minutes=cutoff_minutes)),
                'cutoff_basis': 'historical_nflverse_scheduled_start_Eastern'})
    return sorted(result, key=lambda r: (r['game_id'], r['team']))


def collect(config, base, policy, nfl_manifest, official_manifest, registry):
    sources = {(s['dataset'], s['season']): s for s in nfl_manifest['sources']}
    original = json.loads((base / 'build.json').read_text(encoding='utf-8'))
    player_sha = next(sha for dataset, season, sha in original['identity']['inputs'] if dataset == 'players')
    player_source = json.loads((config.data_dir / 'raw/players/all' / player_sha / 'source.json').read_text(encoding='utf-8'))
    player_path = verify_source(config, player_source)
    inventory = []
    with duckdb.connect() as con:
        games = schedule_rows(con, base / 'games.parquet', policy['cutoff_minutes'])
        crosswalk = records(con, 'SELECT gsis_id,espn_id,display_name FROM read_parquet(?)', [str(player_path)])
        known_ids = {p['gsis_id'] for p in crosswalk if p['gsis_id']}
        espn = defaultdict(set)
        for p in crosswalk:
            if p['espn_id'] and p['gsis_id']:
                espn[str(p['espn_id'])].add(p['gsis_id'])
        for s in sources.values():
            path = verify_source(config, s)
            columns = {c['name'] for c in s['schema']}
            time_col = 'dt' if 'dt' in columns else 'date_modified' if 'date_modified' in columns else None
            time_info = {}
            if time_col:
                time_info = records(con, f"""SELECT min({time_col})::VARCHAR min_timestamp,
                    max({time_col})::VARCHAR max_timestamp, count(DISTINCT {time_col}) timestamps,
                    count(*) FILTER(WHERE {time_col} IS NULL) missing_timestamps FROM read_parquet(?)""", [str(path)])[0]
            inventory.append({k: s[k] for k in ('dataset', 'season', 'url', 'sha256', 'row_count', 'downloaded_at')} | {
                'timestamp_column': time_col, **time_info,
                'selection_use': 'role_snapshot_only' if s['dataset'] == 'depth_charts' and time_col == 'dt'
                  else 'excluded_public_availability_not_demonstrated'})
        by_game = defaultdict(list)
        official = official_evidence(config, registry, official_manifest)
        for e in official:
            if e.get('player_id') and e['player_id'] not in known_ids:
                raise ValueError('Unknown manually mapped GSIS identity')
            e['identity_crosswalk_sha256'] = player_source['sha256']
            by_game[e['game_id'], e['team']].append(e)
        # A snapshot is chosen over ALL positions. If PK disappears in the new
        # snapshot, do not resurrect a PK from the preceding snapshot.
        snapshot_cache = {}
        for season in sorted({g['season'] for g in games}):
            s = sources['depth_charts', season]
            if 'dt' not in {c['name'] for c in s['schema']}:
                continue
            p = str(config.root / s['path'])
            times = defaultdict(set)
            for dt, team in con.execute('SELECT DISTINCT dt,team FROM read_parquet(?)', [p]).fetchall():
                times[team_id(team)].add(instant(dt))
            pk = defaultdict(list)
            for r in records(con, "SELECT dt,team,player_name,espn_id,gsis_id,pos_rank FROM read_parquet(?) WHERE pos_abb='PK'", [p]):
                pk[team_id(r['team']), instant(r['dt'])].append(r)
            snapshot_cache[season] = ({t: sorted(v) for t, v in times.items()}, pk)
        diagnostics = []
        for g in games:
            key = g['game_id'], g['team']
            for dataset in ('depth_charts', 'weekly_rosters', 'injuries'):
                s = sources[dataset, g['season']]
                if dataset == 'depth_charts' and g['season'] in snapshot_cache:
                    continue
                by_game[key].append({'game_id': g['game_id'], 'team': g['team'],
                    'kind': 'untimed_' + dataset, 'evidence_id': f'untimed:{g["game_id"]}:{g["team"]}:{dataset}',
                    'source_url': s['url'], 'source_sha256': s['sha256'], 'source_path': s['path'],
                    'available_at': None, 'temporal_basis': 'public_availability_not_demonstrated',
                    'downloaded_at': s['downloaded_at'], 'player_id': None,
                    'locator': 'season inventory; no player candidate extracted'})
            if g['season'] not in snapshot_cache:
                continue
            times, pk = snapshot_cache[g['season']]
            series = times.get(g['team'], [])
            dt, pk_rows, future_count = latest_snapshot(series, pk, g['team'], instant(g['prediction_cutoff']))
            diagnostics.append({'game_id': g['game_id'], 'team': g['team'],
                'selected_snapshot': iso(dt) if dt else None,
                'future_snapshots_excluded': future_count,
                'pk_rows_in_snapshot': len(pk_rows)})
            if dt is None:
                continue
            s = sources['depth_charts', g['season']]
            for r in pk_rows:
                pid = r['gsis_id'] if r['gsis_id'] in known_ids else None
                mapped = espn.get(str(r['espn_id']), set())
                identity_method = 'provider_gsis_id'
                if not pid and len(mapped) == 1:
                    pid = next(iter(mapped))
                    identity_method = 'unique_static_espn_gsis_crosswalk'
                if pid and mapped and mapped != {pid}:
                    pid = None
                    identity_method = 'conflicting_identity_crosswalk'
                e = {'game_id': g['game_id'], 'team': g['team'], 'kind': 'depth_snapshot',
                    'evidence_id': f'depth:{g["game_id"]}:{g["team"]}:{r["espn_id"]}:{r["pos_rank"]}',
                    'player_id': pid, 'external_id': r['espn_id'], 'name': r['player_name'], 'rank': r['pos_rank'],
                    'available_at': iso(dt), 'modified_at': None, 'temporal_basis': 'provider_snapshot_dt',
                    'source_url': s['url'], 'source_sha256': s['sha256'], 'source_path': s['path'],
                    'downloaded_at': s['downloaded_at'], 'identity_method': identity_method,
                    'identity_crosswalk_sha256': player_source['sha256'],
                    'locator': f'dt={r["dt"]};team={r["team"]};pos_abb=PK;espn_id={r["espn_id"]};pos_rank={r["pos_rank"]}'}
                if e not in by_game[key]:
                    by_game[key].append(e)
    return games, by_game, inventory, diagnostics
