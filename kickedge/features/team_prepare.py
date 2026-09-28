"""Offline per-game team results from the existing frozen PBP and schedules."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import duckdb

from kickedge.io import records, sha256_file, write_json
from kickedge.transform import TEAM_MACRO
from .temporal import POLICY_VERSION


def aggregate(con, path):
    """Sufficient statistics; no averages across games and no final season totals."""
    con.execute(TEAM_MACRO.replace('CREATE MACRO','CREATE OR REPLACE MACRO'))
    return records(con, """WITH p AS (
        SELECT game_id, team_code(posteam) team, team_code(defteam) opponent, fixed_drive,
          down, yardline_100, play_type, epa,
          (play_type IN ('run','pass','field_goal','punt','qb_kneel','qb_spike')) real_drive_play,
          coalesce(touchdown=1 AND team_code(td_team)=team_code(posteam)
            AND coalesce(return_touchdown,0)=0 AND coalesce(special_teams_play,0)=0
            AND play_type NOT IN ('kickoff','punt','field_goal','extra_point'),false) offensive_td,
          (play_type IN ('run','pass') AND coalesce(qb_kneel,0)=0 AND coalesce(qb_spike,0)=0
            AND isfinite(epa)) epa_play
        FROM read_parquet(?) WHERE play_deleted=0 AND posteam IS NOT NULL AND defteam IS NOT NULL
          AND coalesce(two_point_attempt,0)=0 AND coalesce(extra_point_attempt,0)=0
      ), d AS (
        SELECT game_id,team,opponent,fixed_drive,
          bool_or(real_drive_play) real_drive,
          bool_or(real_drive_play AND down BETWEEN 1 AND 4 AND yardline_100 BETWEEN 0 AND 20) red_zone,
          bool_or(offensive_td) td
        FROM p WHERE fixed_drive IS NOT NULL GROUP BY game_id,team,opponent,fixed_drive
      ), drive_totals AS (
        SELECT game_id,team,opponent,count(*) FILTER(WHERE real_drive)::INTEGER drives,
          count(*) FILTER(WHERE real_drive AND red_zone)::INTEGER red_zone_drives,
          count(*) FILTER(WHERE real_drive AND red_zone AND td)::INTEGER red_zone_touchdowns
        FROM d GROUP BY game_id,team,opponent
      ), plays AS (
        SELECT game_id,team,opponent,count(*) FILTER(WHERE offensive_td)::INTEGER touchdowns,
          fsum(epa ORDER BY fixed_drive,epa) FILTER(WHERE epa_play) epa_sum,
          count(*) FILTER(WHERE epa_play)::INTEGER epa_plays,
          count(*) FILTER(WHERE epa_play AND epa>0)::INTEGER successes,
          count(*) FILTER(WHERE real_drive_play AND fixed_drive IS NULL) missing_drive_ids
        FROM p GROUP BY game_id,team,opponent
      ) SELECT p.game_id,p.team,p.opponent,p.touchdowns,
          CASE WHEN missing_drive_ids=0 THEN d.drives END drives,
          CASE WHEN missing_drive_ids=0 THEN d.red_zone_drives END red_zone_drives,
          CASE WHEN missing_drive_ids=0 THEN d.red_zone_touchdowns END red_zone_touchdowns,
          p.epa_sum,p.epa_plays,p.successes
        FROM plays p LEFT JOIN drive_totals d USING(game_id,team,opponent)
        ORDER BY p.game_id,p.team""", [str(path)])


def prepare(config, phase1=None):
    if phase1 is None:
        phase1=config.root/json.loads((config.data_dir/'features/kicker/latest.json').read_text())['path']
    phase1=Path(phase1)
    meta=json.loads((phase1/'build.json').read_text())
    for a in meta['artifacts']:
        if sha256_file(phase1/a['filename']) != a['sha256']:
            raise ValueError('Phase 1 artifact integrity failure')
    prep=config.data_dir/'features/kicker_inputs'/meta['inputs']['prepared_build']
    if sha256_file(prep/'source.json') != meta['inputs']['prepared_source_sha256']:
        raise ValueError('Phase 1 source integrity failure')
    source=json.loads((prep/'source.json').read_text())
    for name in ('identities','manifest'):
        if sha256_file(prep/(name+'.json')) != source[name+'_sha256']:
            raise ValueError('Phase 1 identity/clock integrity failure')
    identities=json.loads((prep/'identities.json').read_text())
    clocks=json.loads((prep/'manifest.json').read_text())
    base=config.data_dir/'processed'/meta['inputs']['historical_build']
    if sha256_file(base/'games.parquet') != source['inputs']['source_hashes']['games.parquet']:
        raise ValueError('Historical schedule integrity failure')
    lock=json.loads((base/'source_lock.json').read_text())
    sources={}
    all_stats=[]
    seasons={r['season'] for r in identities}
    with duckdb.connect() as con:
        for s in lock['sources']:
            if s['dataset']!='pbp' or s['season'] not in seasons:
                continue
            path=config.root/s['path']
            if sha256_file(path)!=s['sha256'] or s['sha256']!=source['inputs']['pbp_clock_hashes'][str(s['season'])]:
                raise ValueError('PBP source integrity failure')
            sources[str(s['season'])]=s['sha256']
            all_stats.extend(aggregate(con,path))
        games=records(con,'SELECT game_id,season,home_team,away_team,home_score,away_score FROM read_parquet(?)', [str(base/'games.parquet')])
    stats={(r['game_id'],r['team']):r for r in all_stats}
    if len(stats)!=len(all_stats):
        raise ValueError('Duplicate team-game source statistics')
    outcomes=defaultdict(list)
    for game in games:
        g=game['game_id']
        if g not in clocks:
            raise ValueError('Game missing from completed Phase 1 population: '+g)
        for side,other in [('home','away'),('away','home')]:
            team,opponent=game[side+'_team'],game[other+'_team']
            r=stats[g,team]
            if r['opponent']!=opponent or game[side+'_score'] is None:
                raise ValueError('Invalid team-game opponent/score: '+g)
            outcomes[g].append({**r,'season':game['season'],'points':game[side+'_score'],
                'pbp_source_sha256':sources[str(game['season'])],
                'games_source_sha256':source['inputs']['source_hashes']['games.parquet']})
    if set(outcomes)!=set(clocks):
        raise ValueError('Missing team-game outcomes')
    inputs={'phase1_build':phase1.name,'phase1_build_sha256':sha256_file(phase1/'build.json'),
        'historical_build':base.name,'pbp_source_hashes':sources,'temporal_policy':POLICY_VERSION,
        'preparation_code_sha256':sha256_file(Path(__file__)),
        'team_normalization_sha256':hashlib.sha256(TEAM_MACRO.encode()).hexdigest()}
    digest=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:20]
    directory=config.data_dir/'features/team_inputs'/digest
    manifest={}
    for game,rows in sorted(outcomes.items()):
        path=directory/'outcomes'/(game+'.json')
        write_json(path,sorted(rows,key=lambda r:r['team']))
        manifest[game]={**clocks[game],'filename':path.name,'sha256':sha256_file(path)}
    write_json(directory/'identities.json',identities)
    write_json(directory/'manifest.json',manifest)
    write_json(directory/'source.json',{'inputs':inputs,'identities_sha256':sha256_file(directory/'identities.json'),
        'manifest_sha256':sha256_file(directory/'manifest.json'),'row_count':len(identities)})
    write_json(config.data_dir/'features/team_inputs/latest.json',{'build_id':digest,'path':directory.relative_to(config.root).as_posix()})
    return directory
