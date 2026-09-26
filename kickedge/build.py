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
from .transform import transform

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
