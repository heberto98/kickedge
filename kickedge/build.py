"""Reproducible builds keyed by inputs, code, configuration and runtime."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform

import duckdb

from .config import Config
from .ingest import sources, verify_source
from .io import records, sha256_file, sql_literal, utc_now, write_json, write_parquet, parquet_info
from .labels import reconcile
from .report import render_quality
from .transform import transform
from .validate import validate, quality_summary

TABLES = {
    "games": "game_id", "players": "player_id", "game_coverage": "game_id",
    "pbp_events": "game_id,play_id", "player_stats_kicking": "game_id,team,player_id",
    "pbp_kicker_totals": "game_id,team,player_id", "team_games": "game_id,team",
    "labels": "game_id,team,player_id", "historical_base": "game_id,team,player_id",
}


def build_identity(config, manifest):
    cfg = {k:v for k,v in asdict(config).items() if k not in {"root","data_dir","reports_dir"}}
    code = {p.name:sha256_file(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    return {"inputs": [(r['dataset'],r['season'],r['sha256']) for r in manifest['sources']],
            "config":cfg,"code":code,"python":platform.python_version(),"duckdb":duckdb.__version__}


def load_sources(con, config, manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {(r["dataset"], r["season"]) for r in sources(config)}
    chosen = [r for r in manifest["sources"] if (r["dataset"],r["season"]) in expected]
    if len(chosen) != len(expected) or {(r['dataset'],r['season']) for r in chosen} != expected:
        raise ValueError("Source lock is incomplete or duplicated for configured seasons. Run ingest.")
    for ds in ("schedules", "players", "pbp", "player_stats"):
        branches = []
        for r in chosen:
            if r["dataset"] != ds:
                continue
            path = verify_source(config, r)
            branches.append(f"SELECT *, {sql_literal(r['sha256'])} source_sha256 FROM read_parquet({sql_literal(path.as_posix())})")
        con.execute(f"CREATE VIEW {ds}_raw AS " + " UNION ALL BY NAME ".join(branches))
    return {**manifest, "sources": chosen}


def create_labels(con, config):
    outcomes = []
    for r in records(con, "SELECT * FROM candidate_details ORDER BY game_id,team,player_id"):
        xpa, xpm, status = reconcile(r['stats_xpa'], r['stats_xpm'], r['pbp_xpa'], r['pbp_xpm'],
                                     r['coverage_ok'], r['participation_observed'], r['unknown_pat_results'] or 0)
        if not r['id_in_players']:
            xpa, xpm, status = None, None, "unmapped_player_id"
        if not r['schedule_identity_ok']:
            xpa, xpm, status = None, None, "invalid_schedule_identity"
        outcomes.append((r['game_id'],r['team'],r['player_id'],xpa,xpm,status))
    con.execute("CREATE TEMP TABLE reconciled(game_id VARCHAR,team VARCHAR,player_id VARCHAR,xpa INTEGER,xpm INTEGER,label_status VARCHAR)")
    con.execute("BEGIN TRANSACTION")
    if outcomes:
        con.executemany("INSERT INTO reconciled VALUES (?,?,?,?,?,?)", outcomes)
    con.execute("COMMIT")
    con.execute(f"""CREATE TABLE labels AS WITH counts AS (
      SELECT game_id,team,count(*) FILTER(WHERE participation_observed) participants,
        count(*) FILTER(WHERE role_evidence='placekick_observed') placekickers
      FROM candidate_details GROUP BY ALL
    ) SELECT d.*, r.xpa,r.xpm,r.label_status,r.label_status='agreed' statistical_label_usable,
      {sql_literal(config.population)} population,
      'not_reconstructed' pregame_identity_status, NULL::VARCHAR expected_kicker_id,
      false eligible_for_pregame_training,
      CASE WHEN d.participation_observed THEN 'observed_postgame' ELSE 'unverified' END participation_status,
      c.participants>1 multiple_kicking_participants, c.placekickers>1 multiple_placekickers,
      CASE WHEN r.xpm IS NULL THEN NULL
           WHEN r.xpm>0 THEN 'not_zero'
           WHEN r.xpa>0 THEN 'all_pat_failed_or_blocked'
           WHEN t.recorded_tries=0 THEN 'team_without_recorded_try'
           WHEN t.team_xpa=0 THEN 'team_only_two_point_tries'
           ELSE 'other_player_took_team_pat' END zero_context,
      CASE WHEN r.xpm=0 THEN 'explicit_stats_zero_and_complete_pbp_with_participation'
           WHEN r.xpm>0 THEN 'two_source_agreement' ELSE 'quarantined' END label_evidence,
      'stable_player_id_join_no_name_matching' identity_method
      FROM candidate_details d JOIN reconciled r USING(game_id,team,player_id)
      JOIN counts c USING(game_id,team) LEFT JOIN team_games t USING(game_id,team)""")
    con.execute("""CREATE TABLE historical_base AS SELECT l.*,
      t.touchdowns,t.offensive_tds,t.defensive_tds,t.special_teams_tds,
      t.team_xpa,t.team_xpm,t.two_pt_attempts,t.two_pt_made,t.recorded_tries,
      g.gameday,g.gametime,g.home_score,g.away_score,g.overtime,g.location
      FROM labels l LEFT JOIN team_games t USING(game_id,team) JOIN games g USING(game_id)""")
    con.execute("""CREATE OR REPLACE TABLE team_games AS SELECT t.*,
      coalesce(l.observed_kicker_count,0)::INTEGER observed_kicker_count,
      coalesce(l.placekicker_count,0)::INTEGER placekicker_count,
      CASE WHEN l.observed_kicker_count>0 THEN 'observed_postgame_candidates'
        ELSE 'no_observed_candidate' END kicker_identity_status,
      s.stats_team_xpa,s.stats_team_xpm,
      CASE WHEN s.stats_team_xpa IS NULL OR s.stats_team_xpm IS NULL THEN 'missing_player_stats'
        WHEN s.stats_team_xpa=t.team_xpa AND s.stats_team_xpm=t.team_xpm THEN 'agreed'
        ELSE 'source_discrepancy' END team_reconciliation_status
      FROM team_games t LEFT JOIN (
        SELECT game_id,team,count(*) FILTER(WHERE participation_observed) observed_kicker_count,
          count(*) FILTER(WHERE role_evidence='placekick_observed') placekicker_count
        FROM labels GROUP BY ALL) l USING(game_id,team)
      LEFT JOIN (SELECT game_id,team,sum(stats_xpa) stats_team_xpa,sum(stats_xpm) stats_team_xpm
        FROM player_stats_kicking GROUP BY ALL) s USING(game_id,team)""")


def build(config: Config, manifest_path: Path | None = None):
    manifest_path = (manifest_path or config.data_dir / "manifests/sources.json").resolve()
    with duckdb.connect() as con:
        con.execute("SET threads=1")  # Stable ordering/serialization for these small derived tables.
        manifest = load_sources(con, config, manifest_path)
        identity = build_identity(config, manifest)
        build_id = hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:20]
        directory = config.data_dir / "processed" / build_id
        print(f"Building {build_id}: checking originals, identities and outcomes", flush=True)
        transform(con, config)
        create_labels(con, config)
        checks = validate(con)
        quality = quality_summary(con, checks)
        directory.mkdir(parents=True,exist_ok=True)
        artifacts = []
        for name, order in TABLES.items():
            path = directory / f"{name}.parquet"
            temporary = directory / f"{name}.pending.parquet"
            write_parquet(con, f"SELECT * FROM {name} ORDER BY {order}", temporary)
            digest = sha256_file(temporary)
            if path.exists():
                if sha256_file(path) != digest:
                    temporary.unlink()
                    raise ValueError(f"Reproducibility failure or modified output: {path}")
                temporary.unlink()
            else:
                temporary.replace(path)
            artifacts.append({"table":name,"path":path.relative_to(config.root).as_posix(),
                              "sha256":digest,**parquet_info(path)})
        text = render_quality(quality, build_id)
        # Repeated builds preserve the original build metadata and immutable source lock.
        if not (directory / 'build.json').exists():
            source_copy=directory/'pipeline_source/kickedge'
            source_copy.mkdir(parents=True,exist_ok=True)
            for source in sorted(Path(__file__).parent.glob('*.py')):
                (source_copy/source.name).write_bytes(source.read_bytes())
            write_json(directory / 'source_lock.json',manifest)
            write_json(directory / 'quality.json', quality)
            (directory / 'quality.md').write_text(text, encoding='utf-8')
            write_json(directory / 'build.json', {"build_id":build_id,"created_at":utc_now(),
                "identity":identity,"source_manifest":str(manifest_path),"artifacts":artifacts})
        else:
            old_quality=json.loads((directory/'quality.json').read_text(encoding='utf-8'))
            if old_quality != quality:
                raise ValueError('Quality report changed for identical build identity')
        config.reports_dir.mkdir(parents=True,exist_ok=True)
        (config.reports_dir/'quality.md').write_text(text,encoding='utf-8')
        write_json(config.reports_dir/'quality.json',quality)
        write_json(config.data_dir / 'processed/latest.json', {"build_id":build_id,"path":directory.relative_to(config.root).as_posix()})
        print(json.dumps({"build_id":build_id,"directory":str(directory),**quality['counts']},ensure_ascii=False),flush=True)
        return directory


def latest_build(config):
    latest = json.loads((config.data_dir/'processed/latest.json').read_text(encoding='utf-8'))
    return config.root/latest['path']


def validate_existing(config):
    directory=latest_build(config)
    metadata=json.loads((directory/'build.json').read_text(encoding='utf-8'))
    manifest=json.loads((directory/'source_lock.json').read_text(encoding='utf-8'))
    if json.dumps(build_identity(config,manifest),sort_keys=True)!=json.dumps(metadata['identity'],sort_keys=True):
        raise ValueError('Code, configuration or runtime changed. Run build for a new version before validate.')
    for artifact in metadata['artifacts']:
        if sha256_file(config.root/artifact['path'])!=artifact['sha256']:
            raise ValueError(f"Modified output: {artifact['path']}")
    result=build(config,directory/'source_lock.json')
    if result!=directory:
        raise ValueError('Rebuilt version does not match the selected build')
    print('Reproducibility verified: identical Parquet hashes and quality report.')


def inspect_label(config, game, team, player):
    directory = latest_build(config)
    with duckdb.connect() as con:
        labels = records(con, "SELECT * FROM read_parquet(?) WHERE game_id=? AND team=? AND player_id=?", [str(directory/'historical_base.parquet'),game,team,player])
        events = records(con, "SELECT play_id,order_sequence,description,counted_pat,made_pat,counted_fg,counted_kickoff,pbp_source_sha256 FROM read_parquet(?) WHERE game_id=? AND player_id=? ORDER BY order_sequence,play_id", [str(directory/'pbp_events.parquet'),game,player])
    print(json.dumps({"build_id":directory.name,"labels":labels,"kicking_events":events},ensure_ascii=False,indent=2,default=str))
    if not labels:
        raise ValueError("No label matches that game/team/player ID")
