"""Verified current-season nflverse cache; historical event definitions are reused."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile

import duckdb

from kickedge.build import create_labels
from kickedge.config import Config
from kickedge.features.kicker import instant
from kickedge.features.team_prepare import aggregate
from kickedge.features.temporal import HISTORICAL_EVENT
from kickedge.ingest import download, sources
from kickedge.io import records, sha256_file, sql_literal, write_json
from kickedge.transform import TEAM_MACRO, transform


class CurrentSourceError(ValueError):
    """Required current input is missing, inconsistent, or unverifiable."""


def _now(now):
    value = now or datetime.now(timezone.utc)
    if value.utcoffset() is None:
        raise CurrentSourceError('Current source time requires an explicit timezone')
    return value.astimezone(timezone.utc)


def _config(root, season):
    if type(season) is not int or season < 2015:
        raise CurrentSourceError('Current season must be an integer in the modern PAT era')
    root = Path(root).resolve()
    return Config(root, season, season, season, ('REG','WC','DIV','CON','SB'),
                  'current_explicit_kicker', root/'data/cache/current'/str(season),
                  root/'reports', timeout_seconds=30, retries=2)


def _verify(root, source):
    try:
        path = (root/source['path']).resolve()
        if not path.is_relative_to((root/'data').resolve()) or sha256_file(path) != source['sha256']:
            raise ValueError('Invalid original')
        return path
    except (OSError, ValueError, KeyError, TypeError):
        raise CurrentSourceError('Current source integrity failure: '+str(source.get('dataset','unknown'))) from None


def load_current_sources(root: Path, season: int, *, refresh=False, now=None, clock=None) -> dict:
    """Load a six-hour verified cache, or fetch approved assets with bounded retries.

    Capture time is updated even when the provider returns an existing content
    version. The historical manifest and immutable source metadata are untouched.
    """
    now = _now(now)
    capture_time = lambda: _now(clock() if clock else None)
    config = _config(root, season)
    manifest_path = config.data_dir/'sources.json'
    cached = []
    if manifest_path.exists() and not refresh:
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            age = now-instant(manifest['fetched_at'])
            if timedelta(0) <= age < timedelta(hours=6):
                cached = manifest['sources']
                # prepare_bundle verifies raw and derived hashes on every read.
                bundle = prepare_bundle(config.root, season, cached, now=now)
                return {**bundle,'generated_at':capture_time().isoformat()}
        except CurrentSourceError:
            raise
        except (KeyError, ValueError, OSError, TypeError):
            raise CurrentSourceError('Current cache manifest integrity failure') from None
    selected = []
    failures = []
    for source in sources(config):
        try:
            record = download(config, source)
        except Exception:
            if source['dataset'] in ('pbp','player_stats'):
                # Only an independently verified empty season may omit events.
                failures.append(source['dataset'])
                continue
            raise CurrentSourceError('Required current source unavailable: '+source['dataset']) from None
        selected.append({**record, 'fetched_at': capture_time().isoformat()})
    bundle = prepare_bundle(config.root, season, selected, now=capture_time())
    finished = capture_time().isoformat()
    bundle['generated_at'] = finished
    bundle['source_failures'] = failures
    write_json(manifest_path, {'season':season,'fetched_at':min(r['fetched_at'] for r in selected),'sources':selected})
    return bundle


def _identity(season, selected):
    package = Path(__file__).resolve().parents[1]
    code = {name:sha256_file(package/name) for name in (
        'current/sources.py','transform.py','build.py','labels.py',
        'features/team_prepare.py','features/temporal.py')}
    value = {'season':season,'sources':sorted((r['dataset'],r['sha256']) for r in selected),
             'code':code,'duckdb':duckdb.__version__}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def prepare_bundle(root: Path, season: int, source_records: list[dict], now=None) -> dict:
    """Prepare one season from frozen originals without touching historical builds.

    Accepts a full historical lock but reads only global identity/calendar sources
    and the requested season. Returns schedules, players, and completed games
    with original clock evidence, reconciled kicker labels, team sufficient
    statistics and Phase 3 conversion rows.
    """
    now = _now(now)
    config = _config(root, season)
    selected = [dict(r) for r in source_records if
                (r.get('dataset') in ('schedules','players') and r.get('season') is None) or
                (r.get('dataset') in ('pbp','player_stats') and r.get('season') == season)]
    datasets = [r['dataset'] for r in selected]
    if len(set(datasets)) != len(datasets) or not {'schedules','players'} <= set(datasets):
        raise CurrentSourceError('Required current source selection is incomplete or duplicated')
    paths = {r['dataset']:_verify(config.root,r) for r in selected}
    for r in selected:
        r.setdefault('fetched_at', r.get('downloaded_at'))
    digest = _identity(season, selected)
    directory = config.data_dir/'derived'/digest
    artifact, metadata = directory/'bundle.json', directory/'integrity.json'
    if artifact.exists() or metadata.exists():
        try:
            expected = json.loads(metadata.read_text(encoding='utf-8'))['sha256']
            if sha256_file(artifact) != expected:
                raise ValueError('Corrupt bundle')
            bundle = json.loads(artifact.read_text(encoding='utf-8'))
        except (OSError, ValueError, KeyError):
            raise CurrentSourceError('Derived current cache integrity failure') from None
    else:
        try:
            bundle = _prepare(config, selected, paths, now)
        except CurrentSourceError:
            raise
        except Exception:
            raise CurrentSourceError('Required current event source schema or data is invalid') from None
        write_json(artifact,bundle)
        write_json(metadata,{'sha256':sha256_file(artifact),'source_code_key':digest})
    _validate_coverage(bundle,now)
    return {**bundle,'sources':selected,'generated_at':now.isoformat(),'bundle_id':digest}


def _validate_coverage(bundle, now):
    required = set(bundle.get('reported_completed_game_ids',[]))
    required.update(g['game_id'] for g in bundle['schedules'] if g.get('scheduled_kickoff') and
                    instant(g['scheduled_kickoff'])+timedelta(hours=24) <= now)
    missing = required-{g['game_id'] for g in bundle['games']}
    if missing:
        raise CurrentSourceError('Critical completed-game coverage missing: '+', '.join(sorted(missing)))


def _prepare(config, selected, paths, now):
    hashes = {r['dataset']:r['sha256'] for r in selected}
    with duckdb.connect() as con:
        con.execute("SET TimeZone='UTC'")
        con.execute('SET threads=1')
        for dataset,path in paths.items():
            con.execute(f'CREATE VIEW {dataset}_all AS SELECT *, {sql_literal(hashes[dataset])} source_sha256 FROM read_parquet({sql_literal(path)})')
        con.execute(TEAM_MACRO)
        season = config.start_season
        calendar = records(con, f"""SELECT *,
            timezone('America/New_York',try_cast(gameday||' '||gametime AS TIMESTAMP))::VARCHAR scheduled_kickoff,
            team_code(home_team) normalized_home,team_code(away_team) normalized_away
            FROM schedules_all WHERE season={season} AND game_type IN ('REG','WC','DIV','CON','SB')
            ORDER BY gameday,gametime,game_id""")
        if not calendar or len({g['game_id'] for g in calendar}) != len(calendar):
            raise CurrentSourceError('Current season schedule is missing or duplicated')
        schedules = []
        for row in calendar:
            g = {k:row[k] for k in ('game_id','season','week','game_type')}
            g.update(home_team=row['normalized_home'],away_team=row['normalized_away'],
                     scheduled_kickoff=instant(row['scheduled_kickoff']).isoformat() if row['scheduled_kickoff'] else None)
            for field in ('stadium','venue','roof','stadium_id','latitude','longitude','stadium_latitude','stadium_longitude'):
                if field in row:
                    g[field] = row[field]
            if 'venue' not in g and g.get('stadium'):
                g['venue'] = g['stadium']
            schedules.append(g)
        player_columns = {r[0] for r in con.execute('DESCRIBE players_all').fetchall()}
        position = 'position' if 'position' in player_columns else 'NULL::VARCHAR AS position'
        players = records(con,f'SELECT gsis_id kicker_id,display_name,{position} FROM players_all WHERE gsis_id IS NOT NULL ORDER BY gsis_id')
        required = {g['game_id'] for g in calendar if
                    g.get('home_score') is not None or g.get('away_score') is not None or
                    (g['scheduled_kickoff'] and instant(g['scheduled_kickoff'])+timedelta(hours=24) <= now)}
        reported = [g['game_id'] for g in calendar if g.get('home_score') is not None or g.get('away_score') is not None]
        bundle = {'season':season,'schedules':schedules,'players':players,'games':[],
                  'reported_completed_game_ids':reported}
        if not {'pbp','player_stats'} <= set(paths):
            if required:
                raise CurrentSourceError('Critical completed-game coverage missing: required event sources unavailable')
            return bundle
        clocks = records(con,"""SELECT p.game_id,count(DISTINCT start_time) clock_versions,
            timezone('America/New_York',try_strptime(min(start_time),'%m/%d/%y, %H:%M:%S'))::VARCHAR kickoff,
            max(try_cast(time_of_day AS TIMESTAMPTZ))::VARCHAR last_event,
            count(*) FILTER(WHERE "desc" ILIKE '%END GAME%' AND play_deleted=0) end_markers
            FROM pbp_all p JOIN schedules_all s USING(game_id)
            WHERE s.season=? AND s.game_type IN ('REG','WC','DIV','CON','SB') GROUP BY p.game_id""",[season])
        complete = {r['game_id']:r for r in clocks if r['end_markers']}
        if required-set(complete):
            raise CurrentSourceError('Critical completed-game coverage missing: '+', '.join(sorted(required-set(complete))))
        if not complete:
            return bundle
        con.execute('CREATE TEMP TABLE completed(game_id VARCHAR)')
        con.executemany('INSERT INTO completed VALUES (?)',[(g,) for g in sorted(complete)])
        for dataset in ('schedules','pbp','player_stats'):
            con.execute(f'CREATE VIEW {dataset}_raw AS SELECT * FROM {dataset}_all WHERE game_id IN (SELECT game_id FROM completed)')
        con.execute('CREATE VIEW players_raw AS SELECT * FROM players_all')
        con.execute('DROP MACRO team_code')
        transform(con,config)
        create_labels(con,config)
        if con.execute('SELECT count(*) FROM game_coverage WHERE NOT coverage_ok').fetchone()[0]:
            raise CurrentSourceError('Critical completed-game coverage inconsistent with final scores')
        # aggregate is deliberately the frozen implementation, on completed PBP only.
        config.data_dir.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='completed-',dir=config.data_dir) as temp:
            filtered = Path(temp)/'pbp.parquet'
            con.execute(f'COPY (SELECT * FROM pbp_raw) TO {sql_literal(filtered)} (FORMAT PARQUET)')
            team_stats = aggregate(con,filtered)
        teams = {(r['game_id'],r['team']):r for r in team_stats}
        if len(teams) != len(team_stats):
            raise CurrentSourceError('Duplicate completed team-game statistics')
        labels, conversions = defaultdict(list),defaultdict(list)
        for r in records(con,'SELECT *,player_id kicker_id FROM labels ORDER BY game_id,team,player_id'):
            labels[r['game_id']].append(r)
        for r in records(con,'SELECT * FROM team_games ORDER BY game_id,team'):
            conversions[r['game_id']].append(r)
        schedules_by_id = {g['game_id']:g for g in schedules}
        for g in records(con,'SELECT * FROM games ORDER BY game_id'):
            gid = g['game_id']; clock = complete[gid]
            if clock['clock_versions'] != 1 or not clock['kickoff'] or not clock['last_event']:
                raise CurrentSourceError('Completed event clock unresolved: '+gid)
            kickoff,end = instant(clock['kickoff']),instant(clock['last_event'])
            scheduled = instant(schedules_by_id[gid]['scheduled_kickoff'])
            if kickoff > end or abs((kickoff-scheduled).total_seconds()) > 12*3600:
                raise CurrentSourceError('Completed event clock inconsistent: '+gid)
            event_teams = []
            for side,other in (('home','away'),('away','home')):
                team,opponent = g[side+'_team'],g[other+'_team']
                r = teams.get((gid,team))
                if not r or r['opponent'] != opponent or g[side+'_score'] is None:
                    raise CurrentSourceError('Completed team-game coverage missing: '+gid)
                event_teams.append({**r,'season':season,'points':g[side+'_score'],
                    'pbp_source_sha256':hashes['pbp'],'games_source_sha256':hashes['schedules']})
            event = {'game_id':gid,'season':season,'kickers':labels[gid],
                     'teams':event_teams,'conversions':conversions[gid]}
            event_digest = hashlib.sha256(json.dumps(event,sort_keys=True).encode()).hexdigest()
            event['source'] = {'actual_kickoff':kickoff.isoformat(),'scheduled_kickoff':scheduled.isoformat(),
                'last_event':end.isoformat(),'event_completed':True,
                'available_at':max(kickoff+timedelta(hours=24),end).isoformat(),
                'temporal_class':HISTORICAL_EVENT,'availability_verified':False,
                'availability_basis':'completed_event_conservative_24h_gate_not_publication',
                'completion_basis':'non_deleted_pbp_END_GAME','clock_source_sha256':hashes['pbp'],
                'sha256':event_digest}
            bundle['games'].append(event)
        return bundle
