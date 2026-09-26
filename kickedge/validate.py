"""Hard integrity checks plus explicit, non-fatal quality findings."""
from .io import records


def validate(con):
    checks = {
        "unique_games": "SELECT count(*)-count(DISTINCT game_id) FROM games",
        "unique_players": "SELECT count(*)-count(DISTINCT player_id) FROM players",
        "unique_pbp_plays": "SELECT count(*) FROM (SELECT game_id,play_id FROM p GROUP BY ALL HAVING count(*)>1)",
        "unique_player_stats": "SELECT count(*) FROM (SELECT game_id,team,player_id FROM player_stats_kicking GROUP BY ALL HAVING count(*)>1)",
        "unique_labels": "SELECT count(*) FROM (SELECT game_id,team,player_id FROM labels GROUP BY ALL HAVING count(*)>1)",
        "valid_label_ids": "SELECT count(*) FROM labels WHERE player_id IS NULL OR NOT regexp_full_match(player_id,'[0-9]{2}-[0-9]{7}')",
        "valid_game_team": "SELECT count(*) FROM labels WHERE NOT schedule_identity_ok OR team=opponent OR season IS NULL",
        "stats_team_opponent": "SELECT count(*) FROM player_stats_kicking s LEFT JOIN team_games t USING(game_id,team) WHERE t.team IS NULL OR s.opponent!=t.opponent OR s.season!=t.season OR s.week!=t.week OR s.season_type!=CASE WHEN t.game_type='REG' THEN 'REG' ELSE 'POST' END",
        "valid_pbp_game": "SELECT count(*) FROM (SELECT DISTINCT p.game_id FROM p LEFT JOIN games g USING(game_id) WHERE g.game_id IS NULL)",
        "pbp_game_metadata": "SELECT count(*) FROM p JOIN games g USING(game_id) WHERE p.season!=g.season OR p.week!=g.week OR team_code(p.home_team)!=g.home_team OR team_code(p.away_team)!=g.away_team OR p.season_type!=CASE WHEN g.game_type='REG' THEN 'REG' ELSE 'POST' END",
        "unrounded_stats_counts": "SELECT count(*) FROM player_stats_raw WHERE pat_att<0 OR pat_made<0 OR pat_made>pat_att OR pat_att!=floor(pat_att) OR pat_made!=floor(pat_made)",
        "valid_pbp_kicking_team": "SELECT count(*) FROM pbp_kicker_totals b LEFT JOIN team_games t USING(game_id,team) WHERE t.team IS NULL OR b.player_id IS NULL",
        "valid_touchdown_team": "SELECT count(*) FROM pbp_events e LEFT JOIN team_games t ON e.game_id=t.game_id AND e.td_team=t.team WHERE e.counted_td AND t.team IS NULL",
        "valid_counts": "SELECT count(*) FROM labels WHERE stats_xpa<0 OR stats_xpm<0 OR stats_xpm>stats_xpa OR pbp_xpa<0 OR pbp_xpm<0 OR pbp_xpm>pbp_xpa OR xpa<0 OR xpm<0 OR xpm>xpa",
        "canonical_only_agreement": "SELECT count(*) FROM labels WHERE (label_status='agreed') IS DISTINCT FROM (xpa IS NOT NULL AND xpm IS NOT NULL) OR (label_status='agreed' AND (xpa!=stats_xpa OR xpm!=stats_xpm OR xpa!=pbp_xpa OR xpm!=pbp_xpm OR NOT participation_observed OR NOT coverage_ok OR NOT id_in_players))",
        "pregame_not_inferred": "SELECT count(*) FROM labels WHERE expected_kicker_id IS NOT NULL OR eligible_for_pregame_training OR pregame_identity_status!='not_reconstructed'",
        "td_counted_once": "SELECT abs((SELECT sum(touchdowns) FROM team_games)-(SELECT count(*) FROM pbp_events WHERE counted_td))",
        "team_xpa_matches_events": "SELECT abs((SELECT sum(team_xpa) FROM team_games)-(SELECT count(*) FROM pbp_events WHERE counted_pat))",
        "td_components_complete": "SELECT count(*) FROM team_games WHERE touchdowns!=offensive_tds+defensive_tds+special_teams_tds",
    }
    results = [{"check": name, "violations": con.execute(sql).fetchone()[0]} for name, sql in checks.items()]
    failures = [r for r in results if r["violations"]]
    if failures:
        raise ValueError(f"Integrity gates failed: {failures}")
    return results


def quality_summary(con, checks):
    return {
        "checks": checks,
        "counts": records(con, """SELECT count(*) observations,count(DISTINCT player_id) kickers,
          count(DISTINCT game_id) games_with_labels,
          count(*) FILTER(WHERE label_status='agreed') usable_statistical_labels,
          count(*) FILTER(WHERE xpm=0) zeros,
          count(*) FILTER(WHERE label_status!='agreed') quarantined,
          count(*) FILTER(WHERE role_evidence='kickoff_only_observed') kickoff_only_rows,
          count(*) FILTER(WHERE multiple_kicking_participants) multiple_participant_rows,
          count(*) FILTER(WHERE multiple_placekickers) multiple_placekicker_rows
          FROM labels""")[0],
        "game_count": con.execute("SELECT count(*) FROM games").fetchone()[0],
        "regular_season_games": con.execute("SELECT count(*) FROM games WHERE game_type='REG'").fetchone()[0],
        "postseason_games": con.execute("SELECT count(*) FROM games WHERE game_type!='REG'").fetchone()[0],
        "target_season_rows": con.execute("SELECT count(*) FROM labels WHERE target_season_eligible").fetchone()[0],
        "missing_team_stats": con.execute("SELECT count(*) FROM team_games WHERE team_reconciliation_status='missing_player_stats'").fetchone()[0],
        "team_numeric_discrepancies": con.execute("SELECT count(*) FROM team_games WHERE team_reconciliation_status='source_discrepancy'").fetchone()[0],
        "team_game_count": con.execute("SELECT count(*) FROM team_games").fetchone()[0],
        "season_counts": records(con, "SELECT season,count(*) observations,count(DISTINCT game_id) games,count(DISTINCT player_id) kickers,count(*) FILTER(WHERE xpm=0) zeros,count(*) FILTER(WHERE label_status!='agreed') quarantined FROM labels GROUP BY season ORDER BY season"),
        "xpm_distribution": records(con, "SELECT xpm,count(*) observations FROM labels GROUP BY xpm ORDER BY xpm NULLS LAST"),
        "label_status": records(con, "SELECT label_status,count(*) observations FROM labels GROUP BY label_status ORDER BY label_status"),
        "zero_basis": records(con, "SELECT zero_context,count(*) observations FROM labels WHERE xpm=0 GROUP BY zero_context ORDER BY zero_context"),
        "multiple_participant_teams": records(con, "SELECT game_id,team,count(*) players,count(*) FILTER(WHERE role_evidence='placekick_observed') placekickers,string_agg(kicker_name, ', ' ORDER BY player_id) AS names FROM labels GROUP BY game_id,team HAVING count(*)>1 ORDER BY game_id,team"),
        "team_games_without_candidate": records(con, "SELECT t.game_id,t.team,t.team_xpa,t.touchdowns FROM team_games t ANTI JOIN labels l USING(game_id,team) ORDER BY game_id,team"),
        "coverage_failures": records(con, "SELECT * FROM game_coverage WHERE NOT coverage_ok ORDER BY game_id"),
        "quarantined_labels": records(con, "SELECT game_id,team,player_id,kicker_name,label_status,stats_xpa,stats_xpm,pbp_xpa,pbp_xpm FROM labels WHERE label_status!='agreed' ORDER BY game_id,team,player_id"),
        "team_reconciliation": records(con, """SELECT t.game_id,t.team,t.team_xpa,t.team_xpm,s.stats_xpa,s.stats_xpm
          FROM team_games t LEFT JOIN (SELECT game_id,team,sum(stats_xpa) stats_xpa,sum(stats_xpm) stats_xpm FROM player_stats_kicking GROUP BY ALL) s USING(game_id,team)
          WHERE s.stats_xpa IS NULL OR s.stats_xpm IS NULL OR t.team_xpa!=s.stats_xpa OR t.team_xpm!=s.stats_xpm ORDER BY t.game_id,t.team"""),
        "nullified_pat_rows": con.execute("SELECT count(*) FROM pbp_events WHERE play_type='extra_point' AND NOT counted_pat").fetchone()[0],
        "nullified_kickoff_rows": con.execute("SELECT count(*) FROM pbp_events WHERE kickoff_attempt=1 AND NOT counted_kickoff").fetchone()[0],
        "valid_two_pt_no_play_rows": con.execute("SELECT count(*) FROM pbp_events WHERE play_type='no_play' AND counted_two_pt").fetchone()[0],
        "missingness": [{"column": name, "nulls": con.execute(f'SELECT count(*) FROM labels WHERE "{name}" IS NULL').fetchone()[0],
                        "percent": con.execute(f'SELECT round(100.0*count(*) FILTER(WHERE "{name}" IS NULL)/count(*),4) FROM labels').fetchone()[0]}
                       for name in ["game_id","player_id","kicker_name","opponent","stats_xpa","stats_xpm","pbp_xpa","pbp_xpm","xpa","xpm","expected_kicker_id"]],
    }
