import pytest

from kickedge.validate import validate


def test_zero_requires_participation_and_preserves_kickoff_specialist(synthetic):
    play,stats,finish,_=synthetic
    # On kickoffs posteam is the receiving team, so the kicker belongs to defteam.
    play(1,play_type='kickoff',kickoff_attempt=1,posteam='NYJ',defteam='BUF')
    stats()
    con=finish()
    assert con.execute('SELECT team,xpa,xpm,role_evidence FROM labels').fetchone()==('BUF',0,0,'kickoff_only_observed')
    assert con.execute('SELECT expected_kicker_id,eligible_for_pregame_training FROM labels').fetchone()==(None,False)
    validate(con)


def test_absent_stats_cannot_become_zero(synthetic):
    play,_,finish,_=synthetic
    play(1,play_type='field_goal',field_goal_attempt=1,field_goal_result='made')
    con=finish()
    assert con.execute('SELECT stats_xpa,pbp_xpa,xpm,label_status FROM labels').fetchone()==(None,0,None,'missing_player_stats')


def test_stats_only_record_cannot_prove_participation(synthetic):
    _,stats,finish,_=synthetic
    stats()
    con=finish()
    assert con.execute('SELECT xpm,label_status FROM labels').fetchone()==(None,'participation_unverified')


def test_official_flags_handle_nullification_block_and_two_point_penalty(synthetic):
    play,stats,finish,_=synthetic
    play(1,play_type='extra_point',extra_point_attempt=0,desc='Kick GOOD, penalty - No Play.')
    play(2,play_type='extra_point',extra_point_attempt=1,extra_point_result='blocked')
    play(3,play_type='extra_point',extra_point_attempt=1,extra_point_result='failed')
    play(4,play_type='extra_point',extra_point_attempt=1,extra_point_result='good')
    play(5,play_type='no_play',two_point_attempt=1,two_point_conv_result='success',
         desc='TWO-POINT CONVERSION ATTEMPT. SUCCEEDS. Penalty enforced between downs.')
    play(6,play_type='extra_point',extra_point_attempt=1,extra_point_result='good',play_deleted=1)
    stats(xpa=3,xpm=1)
    con=finish()
    assert con.execute('SELECT xpa,xpm FROM labels').fetchone()==(3,1)
    assert con.execute("SELECT team_xpa,team_xpm,two_pt_attempts,two_pt_made,blocked_pat,failed_pat FROM team_games WHERE team='BUF'").fetchone()==(3,1,1,1,1,1)


def test_nullified_kickoff_does_not_prove_participation(synthetic):
    play,stats,finish,_=synthetic
    play(1,play_type='no_play',kickoff_attempt=1,desc='Delay of game - No Play.',posteam='NYJ',defteam='BUF')
    stats()
    con=finish()
    assert con.execute('SELECT xpm,label_status FROM labels').fetchone()==(None,'participation_unverified')


def test_touchdowns_once_by_scoring_team_and_no_invented_ot_pat(synthetic):
    play,stats,finish,_=synthetic
    play(1,play_type='pass',touchdown=1,td_team='BUF',pass_touchdown=1)
    play(2,play_type='pass',touchdown=1,td_team='NYJ',return_touchdown=1)
    play(3,play_type='kickoff',touchdown=1,td_team='NYJ',posteam='NYJ',defteam='BUF',return_touchdown=1,kickoff_attempt=1)
    play(4,play_type='run',touchdown=1,td_team='BUF',rush_touchdown=1,qtr=5,
         desc='Original ruling - No Play. Ruling REVERSED. TOUCHDOWN.')
    stats()
    con=finish()
    assert con.execute("SELECT touchdowns,offensive_tds,defensive_tds,special_teams_tds,team_xpa FROM team_games ORDER BY team").fetchall()==[(2,2,0,0,0),(2,0,1,1,0)]
    validate(con)


def test_replacement_non_kicker_included_and_discrepancy_quarantined(synthetic):
    play,stats,finish,_=synthetic
    play(1,play_type='extra_point',extra_point_attempt=1,extra_point_result='good')
    play(2,play_type='extra_point',extra_point_attempt=1,extra_point_result='failed',kicker_player_id='00-0000002')
    stats(xpa=1,xpm=0)  # intentional source discrepancy
    stats(player='00-0000002',position='P',xpa=1,xpm=0)
    con=finish()
    assert con.execute('SELECT xpm,label_status,multiple_placekickers FROM labels ORDER BY player_id').fetchall()==[(None,'source_discrepancy',True),(0,'agreed',True)]


def test_missing_end_or_score_mismatch_blocks_zero(synthetic):
    play,stats,finish,con=synthetic
    play(1,play_type='kickoff',kickoff_attempt=1,posteam='NYJ',defteam='BUF')
    stats()
    con.execute('UPDATE schedules_raw SET home_score=99')
    finish()
    assert con.execute('SELECT xpm,label_status FROM labels').fetchone()==(None,'incomplete_pbp')


def test_duplicate_label_hard_gate(synthetic):
    play,stats,finish,_=synthetic
    play(1,play_type='extra_point',extra_point_attempt=1,extra_point_result='good')
    stats(xpa=1,xpm=1)
    con=finish()
    con.execute('INSERT INTO labels SELECT * FROM labels')
    with pytest.raises(ValueError,match='unique_labels'):
        validate(con)


def test_configured_game_type_scope_keeps_other_sources_out(synthetic):
    play,stats,finish,con=synthetic
    con.execute("INSERT INTO schedules_raw SELECT * REPLACE('2024_19_NYJ_BUF' AS game_id,'WC' AS game_type,19 AS week) FROM schedules_raw")
    play(1,play_type='extra_point',extra_point_attempt=1,extra_point_result='good')
    stats(xpa=1,xpm=1)
    con.execute("INSERT INTO player_stats_raw SELECT * REPLACE('2024_19_NYJ_BUF' AS game_id,'POST' AS season_type,19 AS week) FROM player_stats_raw")
    play(2,game_id='2024_19_NYJ_BUF',season_type='POST',week=19,play_type='extra_point',extra_point_attempt=1,extra_point_result='good')
    finish()
    assert con.execute('SELECT count(*) FROM labels').fetchone()==(1,)
    assert con.execute('SELECT DISTINCT game_id FROM p').fetchall()==[('2024_01_NYJ_BUF',)]
    validate(con)


def test_unknown_game_is_exposed_not_silently_filtered(synthetic):
    play,stats,finish,con=synthetic
    play(1,game_id='2024_99_NYJ_BUF',play_type='extra_point',extra_point_attempt=1,extra_point_result='good')
    stats()
    finish()
    with pytest.raises(ValueError,match='valid_pbp_game'):
        validate(con)
