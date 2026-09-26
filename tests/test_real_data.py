import json
from pathlib import Path

import duckdb
import pytest

from kickedge.io import sha256_file

ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'audits/cases.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def built():
    pointer=ROOT/'data/processed/latest.json'
    if not pointer.exists():
        pytest.skip('Run python -m kickedge build for real-data integration tests')
    return ROOT/json.loads(pointer.read_text())['path']


@pytest.mark.parametrize('case',CASES,ids=lambda r:r['game_id'])
def test_manually_reviewed_real_labels(built,case):
    with duckdb.connect() as con:
        for row in case['labels']:
            actual=con.execute('SELECT xpa,xpm,stats_xpa,stats_xpm,pbp_xpa,pbp_xpm FROM read_parquet(?) WHERE game_id=? AND team=? AND player_id=?',
                [str(built/'labels.parquet'),case['game_id'],row['team'],row['player_id']]).fetchone()
            assert actual==(row['xpa'],row['xpm'])*3


def test_saved_artifact_integrity(built):
    metadata=json.loads((built/'build.json').read_text())
    for artifact in metadata['artifacts']:
        assert sha256_file(ROOT/artifact['path'])==artifact['sha256']


def test_unidentified_team_games_keep_null_stats(built):
    with duckdb.connect() as con:
        rows=con.execute("SELECT team_xpa,stats_team_xpa,team_reconciliation_status FROM read_parquet(?) WHERE kicker_identity_status='no_observed_candidate'",[str(built/'team_games.parquet')]).fetchall()
        assert rows
        assert all(r==(0,None,'missing_player_stats') for r in rows)


def test_real_nullification_overtime_and_td_classification(built):
    with duckdb.connect() as con:
        con.read_parquet(str(built/'pbp_events.parquet')).create_view('e')
        con.read_parquet(str(built/'team_games.parquet')).create_view('t')
        assert con.execute("SELECT counted_pat FROM e WHERE game_id='2020_06_DET_JAX' AND play_id=2519").fetchone()==(False,)
        assert con.execute("SELECT counted_two_pt FROM e WHERE game_id='2016_21_NE_ATL' AND play_id=4041").fetchone()==(True,)
        assert con.execute("SELECT count(*) FROM e WHERE game_id='2016_21_NE_ATL' AND qtr=5 AND counted_pat").fetchone()==(0,)
        assert con.execute("SELECT touchdowns,defensive_tds FROM t WHERE game_id='2015_03_SF_ARI' AND team='ARI'").fetchone()==(6,2)
        assert con.execute("SELECT counted_td FROM e WHERE game_id='2024_02_NYG_WAS' AND play_id=41").fetchone()==(False,)
