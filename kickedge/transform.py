"""Small SQL transformations; event indicators, not prose, determine outcomes."""
from .io import sql_literal

TEAM_MACRO = """
CREATE MACRO team_code(t) AS CASE t
 WHEN 'STL' THEN 'LA' WHEN 'LAR' THEN 'LA' WHEN 'OAK' THEN 'LV'
 WHEN 'SD' THEN 'LAC' WHEN 'SDG' THEN 'LAC' WHEN 'JAC' THEN 'JAX'
 ELSE t END;
"""

PBP_COLUMNS = """game_id, play_id, order_sequence, season, week, season_type,
home_team, away_team, posteam, defteam, play_type, "desc", play_deleted,
extra_point_attempt, extra_point_result, field_goal_attempt, field_goal_result,
kickoff_attempt, kicker_player_id, kicker_player_name, touchdown, td_team,
pass_touchdown, rush_touchdown, return_touchdown, two_point_attempt,
two_point_conv_result, defensive_two_point_attempt, defensive_two_point_conv,
defensive_extra_point_attempt, defensive_extra_point_conv, qtr, time,
total_home_score, total_away_score, home_score, away_score, safety, source_sha256"""


def transform(con, config):
    con.execute(TEAM_MACRO)
    types = ",".join(sql_literal(t) for t in config.game_types)
    con.execute(f"""CREATE TABLE games AS
        SELECT game_id, season::INTEGER season, week::INTEGER AS week, game_type,
          gameday, gametime, home_team original_home_team, away_team original_away_team,
          team_code(home_team) home_team, team_code(away_team) away_team,
          home_score::INTEGER home_score, away_score::INTEGER away_score,
          overtime, location, source_sha256 schedules_source_sha256,
          season >= {config.target_start_season} target_season_eligible
        FROM schedules_raw WHERE season BETWEEN {config.start_season} AND {config.end_season}
          AND game_type IN ({types})""")
    con.execute("""CREATE TABLE players AS SELECT gsis_id player_id, display_name,
        source_sha256 players_source_sha256 FROM players_raw WHERE gsis_id IS NOT NULL""")
    # Scope known games to configured game types. Keep unknown/null game IDs so
    # integrity gates expose them instead of silently discarding bad source rows.
    scope = "(game_id IN (SELECT game_id FROM games) OR game_id IS NULL OR game_id NOT IN (SELECT game_id FROM schedules_raw))"
    con.execute(f"CREATE TEMP TABLE p AS SELECT {PBP_COLUMNS} FROM pbp_raw WHERE {scope}")
    con.execute("""CREATE TABLE game_coverage AS
      WITH agg AS (SELECT game_id, count(*) pbp_rows,
        count(*) FILTER(WHERE "desc" ILIKE '%END GAME%' AND play_deleted=0) end_markers,
        max(total_home_score) FILTER(WHERE "desc" ILIKE '%END GAME%' AND play_deleted=0) end_home_score,
        max(total_away_score) FILTER(WHERE "desc" ILIKE '%END GAME%' AND play_deleted=0) end_away_score,
        min(home_score) reported_home_min, max(home_score) reported_home_max,
        min(away_score) reported_away_min, max(away_score) reported_away_max,
        min(source_sha256) pbp_source_sha256
      FROM p GROUP BY game_id)
      SELECT g.game_id, a.* EXCLUDE(game_id),
        coalesce(a.end_markers>0 AND a.end_home_score=g.home_score AND a.end_away_score=g.away_score
          AND a.reported_home_min=g.home_score AND a.reported_home_max=g.home_score
          AND a.reported_away_min=g.away_score AND a.reported_away_max=g.away_score, false) coverage_ok
      FROM games g LEFT JOIN agg a USING(game_id)""")
    # Every retained row can be located in the immutable original by hash/game/play.
    # no_play can contain a valid 2PT plus a between-downs foul. Descriptions may
    # also contain a superseded "No Play" ruling followed by a replay reversal.
    con.execute("""CREATE TABLE pbp_events AS SELECT
      p.game_id, p.play_id::BIGINT play_id, p.order_sequence, p.season::INTEGER season,
      p.week::INTEGER AS week, team_code(p.posteam) posteam, team_code(p.defteam) defteam,
      team_code(p.td_team) td_team,
      CASE WHEN kickoff_attempt=1 THEN team_code(defteam) ELSE team_code(posteam) END kicking_team,
      kicker_player_id player_id, kicker_player_name player_name, play_type,
      "desc" description, qtr::INTEGER qtr, time, play_deleted,
      coalesce(play_deleted=0,false) not_deleted,
      coalesce(play_deleted=0 AND extra_point_attempt=1,false) counted_pat,
      coalesce(play_deleted=0 AND extra_point_attempt=1 AND extra_point_result='good',false) made_pat,
      coalesce(play_deleted=0 AND field_goal_attempt=1,false) counted_fg,
      coalesce(play_deleted=0 AND kickoff_attempt=1 AND play_type='kickoff',false) counted_kickoff,
      coalesce(play_deleted=0 AND two_point_attempt=1,false) counted_two_pt,
      coalesce(play_deleted=0 AND touchdown=1,false) counted_td,
      extra_point_attempt, extra_point_result, field_goal_attempt, field_goal_result,
      kickoff_attempt, two_point_attempt, two_point_conv_result, touchdown,
      pass_touchdown, rush_touchdown, return_touchdown,
      defensive_two_point_attempt, defensive_two_point_conv,
      defensive_extra_point_attempt, defensive_extra_point_conv, safety,
      source_sha256 pbp_source_sha256
      FROM p WHERE extra_point_attempt=1 OR field_goal_attempt=1 OR kickoff_attempt=1
        OR two_point_attempt=1 OR touchdown=1 OR safety=1
        OR defensive_two_point_attempt=1 OR defensive_extra_point_attempt=1
        OR play_type IN ('extra_point','field_goal','kickoff')
        OR "desc" ILIKE '%extra point%' OR "desc" ILIKE '%TWO-POINT CONVERSION%'""")
    con.execute(f"""CREATE TABLE player_stats_kicking AS SELECT
        game_id, team_code(team) team, team_code(opponent_team) opponent,
        season::INTEGER season, week::INTEGER AS week, season_type,
        player_id, player_name, player_display_name, position,
        pat_att::INTEGER stats_xpa, pat_made::INTEGER stats_xpm,
        pat_missed::INTEGER stats_pat_missed, pat_blocked::INTEGER stats_pat_blocked,
        fg_att::INTEGER stats_fga, fg_made::INTEGER stats_fgm,
        source_sha256 stats_source_sha256
      FROM player_stats_raw WHERE (position='K' OR pat_att>0 OR fg_att>0) AND {scope}""")
    con.execute("""CREATE TABLE pbp_kicker_totals AS SELECT game_id, kicking_team team,
      player_id, min(player_name) pbp_name,
      count(*) FILTER(WHERE counted_pat)::INTEGER pbp_xpa,
      count(*) FILTER(WHERE made_pat)::INTEGER pbp_xpm,
      count(*) FILTER(WHERE counted_fg)::INTEGER pbp_fga,
      count(*) FILTER(WHERE counted_fg AND field_goal_result='made')::INTEGER pbp_fgm,
      count(*) FILTER(WHERE counted_kickoff)::INTEGER pbp_kickoffs,
      count(*) FILTER(WHERE counted_pat AND (extra_point_result IS NULL OR extra_point_result NOT IN ('good','failed','blocked')))::INTEGER unknown_pat_results,
      min(order_sequence) first_kicking_sequence, max(order_sequence) last_kicking_sequence,
      min(pbp_source_sha256) pbp_source_sha256
      FROM pbp_events WHERE counted_pat OR counted_fg OR counted_kickoff
      GROUP BY game_id,kicking_team,player_id""")
    con.execute("""CREATE TABLE team_games AS
      WITH sides AS (
        SELECT game_id,season,week,game_type,home_team team,away_team opponent,true is_home FROM games
        UNION ALL SELECT game_id,season,week,game_type,away_team,home_team,false FROM games
      ) SELECT s.*, c.coverage_ok,
        count(*) FILTER(WHERE e.counted_td AND e.td_team=s.team)::INTEGER touchdowns,
        count(*) FILTER(WHERE e.counted_td AND e.td_team=s.team AND e.play_type IN ('kickoff','punt','field_goal'))::INTEGER special_teams_tds,
        count(*) FILTER(WHERE e.counted_td AND e.td_team=s.team AND e.td_team!=e.posteam AND e.play_type NOT IN ('kickoff','punt','field_goal'))::INTEGER defensive_tds,
        count(*) FILTER(WHERE e.counted_td AND e.td_team=s.team AND e.td_team=e.posteam AND e.play_type NOT IN ('kickoff','punt','field_goal'))::INTEGER offensive_tds,
        count(*) FILTER(WHERE e.counted_pat AND e.kicking_team=s.team)::INTEGER team_xpa,
        count(*) FILTER(WHERE e.made_pat AND e.kicking_team=s.team)::INTEGER team_xpm,
        count(*) FILTER(WHERE e.counted_two_pt AND e.posteam=s.team)::INTEGER two_pt_attempts,
        count(*) FILTER(WHERE e.counted_two_pt AND e.posteam=s.team AND e.two_point_conv_result='success')::INTEGER two_pt_made,
        count(*) FILTER(WHERE e.counted_pat AND e.kicking_team=s.team AND e.extra_point_result='blocked')::INTEGER blocked_pat,
        count(*) FILTER(WHERE e.counted_pat AND e.kicking_team=s.team AND e.extra_point_result='failed')::INTEGER failed_pat,
        c.pbp_source_sha256
      FROM sides s JOIN game_coverage c USING(game_id)
      LEFT JOIN pbp_events e USING(game_id)
      GROUP BY ALL""")
    con.execute("""ALTER TABLE team_games ADD COLUMN recorded_tries INTEGER;
      UPDATE team_games SET recorded_tries=team_xpa+two_pt_attempts;""")
    con.execute("""CREATE TEMP TABLE candidates AS
       SELECT game_id,team,player_id FROM player_stats_kicking
       UNION SELECT game_id,team,player_id FROM pbp_kicker_totals WHERE pbp_xpa>0 OR pbp_fga>0""")
    con.execute("""CREATE TEMP TABLE candidate_details AS
      SELECT c.game_id,c.team,c.player_id,
        coalesce(s.player_display_name,i.display_name,b.pbp_name) kicker_name,
        g.season,g.week,g.game_type,t.opponent,t.is_home,g.target_season_eligible,
        s.position stats_position, s.stats_xpa,s.stats_xpm,s.stats_fga,s.stats_fgm,
        b.pbp_xpa,b.pbp_xpm,b.pbp_fga,b.pbp_fgm,b.pbp_kickoffs,b.unknown_pat_results,
        b.first_kicking_sequence,b.last_kicking_sequence,
        coalesce(b.pbp_xpa+b.pbp_fga+b.pbp_kickoffs>0,false) participation_observed,
        coalesce(t.coverage_ok,false) coverage_ok,
        i.player_id IS NOT NULL id_in_players,
        g.game_id IS NOT NULL AND t.team IS NOT NULL schedule_identity_ok,
        CASE WHEN b.pbp_xpa>0 OR b.pbp_fga>0 THEN 'placekick_observed'
             WHEN b.pbp_kickoffs>0 THEN 'kickoff_only_observed'
             ELSE 'stats_record_only' END role_evidence,
        CASE WHEN s.position='K' THEN 'historical_stats_position_K'
             ELSE 'observed_placekick_other_position' END population_basis,
        s.stats_source_sha256, coalesce(b.pbp_source_sha256,t.pbp_source_sha256) pbp_source_sha256,
        g.schedules_source_sha256,i.players_source_sha256
      FROM candidates c LEFT JOIN player_stats_kicking s USING(game_id,team,player_id)
      LEFT JOIN pbp_kicker_totals b USING(game_id,team,player_id)
      LEFT JOIN games g USING(game_id)
      LEFT JOIN team_games t ON t.game_id=c.game_id AND t.team=c.team
      LEFT JOIN players i ON i.player_id=c.player_id""")
