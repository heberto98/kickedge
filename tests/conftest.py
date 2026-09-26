from pathlib import Path

import duckdb
import pytest

from kickedge.config import Config
from kickedge.transform import PBP_COLUMNS, transform
from kickedge.build import create_labels


@pytest.fixture
def synthetic(tmp_path):
    """Deliberately tiny game feed exercising real transformation code."""
    con=duckdb.connect()
    con.execute("""CREATE TABLE schedules_raw AS SELECT '2024_01_NYJ_BUF' game_id,
       2024 season,1 AS week,'REG' game_type,DATE '2024-09-01' gameday,'13:00' gametime,
       'BUF' home_team,'NYJ' away_team,14 home_score,6 away_score,0 overtime,
       'Home' AS location,'schedule-hash' source_sha256""")
    con.execute("CREATE TABLE players_raw(gsis_id VARCHAR,display_name VARCHAR,source_sha256 VARCHAR)")
    con.execute("""INSERT INTO players_raw VALUES
       ('00-0000001','Kicker A','players-hash'),('00-0000002','Punter B','players-hash'),
       ('00-0000003','Kicker C','players-hash')""")
    con.execute("""CREATE TABLE player_stats_raw(game_id VARCHAR,team VARCHAR,opponent_team VARCHAR,
      season INTEGER,week INTEGER,season_type VARCHAR,player_id VARCHAR,player_name VARCHAR,
      player_display_name VARCHAR,position VARCHAR,pat_att INTEGER,pat_made INTEGER,
      pat_missed INTEGER,pat_blocked INTEGER,fg_att INTEGER,fg_made INTEGER,source_sha256 VARCHAR)""")
    text_fields={'game_id','season_type','home_team','away_team','posteam','defteam','play_type',
                 'desc','extra_point_result','field_goal_result','kicker_player_id','kicker_player_name',
                 'td_team','two_point_conv_result','time','source_sha256'}
    columns=[c.strip().strip('"') for c in PBP_COLUMNS.replace('\n','').split(',')]
    con.execute('CREATE TABLE pbp_raw('+','.join('"'+c+'" '+('VARCHAR' if c in text_fields else 'DOUBLE') for c in columns)+')')
    cfg=Config(tmp_path,2024,2024,2024,('REG',),'test_postgame',tmp_path/'data',tmp_path/'reports')

    def play(play_id,**overrides):
        row=dict(game_id='2024_01_NYJ_BUF',play_id=play_id,order_sequence=play_id,
                 season=2024,week=1,season_type='REG',home_team='BUF',away_team='NYJ',
                 posteam='BUF',defteam='NYJ',play_deleted=0,home_score=14,away_score=6,
                 total_home_score=14,total_away_score=6,source_sha256='pbp-hash',qtr=1,
                 extra_point_attempt=0,field_goal_attempt=0,kickoff_attempt=0,two_point_attempt=0,
                 touchdown=0,kicker_player_id='00-0000001',kicker_player_name='K.A',**{})
        row.update(overrides)
        con.execute('INSERT INTO pbp_raw VALUES ('+','.join('?' for _ in columns)+')',[row.get(c) for c in columns])

    def stats(player='00-0000001',position='K',xpa=0,xpm=0,fga=0):
        con.execute("INSERT INTO player_stats_raw VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           ['2024_01_NYJ_BUF','BUF','NYJ',2024,1,'REG',player,'Name','Name',position,xpa,xpm,xpa-xpm,0,fga,0,'stats-hash'])

    def finish():
        play(999,desc='END GAME',play_type=None,kicker_player_id=None)
        transform(con,cfg)
        create_labels(con,cfg)
        return con

    yield play,stats,finish,con
    con.close()
