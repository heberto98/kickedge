"""Current cache and event extraction against real tiny Parquet sources."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from kickedge.current import sources as current
from kickedge.io import sha256_file, sql_literal


NOW = datetime(2024, 9, 10, 12, tzinfo=timezone.utc)


@pytest.fixture
def source_records(synthetic, tmp_path):
    play, stats, _, con = synthetic
    play(1, play_type='extra_point', extra_point_attempt=1, extra_point_result='good')
    play(2, play_type='run', touchdown=1, td_team='BUF')
    play(3, play_type='run', posteam='NYJ', defteam='BUF')
    play(999, desc='END GAME', play_type=None, kicker_player_id=None)
    stats(xpa=1, xpm=1)
    con.execute("ALTER TABLE players_raw ADD COLUMN position VARCHAR DEFAULT 'K'")
    for name, kind, value in [
        ('start_time','VARCHAR',"'09/01/24, 13:00:00'"),
        ('time_of_day','VARCHAR',"'2024-09-01T20:00:00Z'"),
        ('fixed_drive','INTEGER','1'),('down','INTEGER','1'),
        ('yardline_100','INTEGER','10'),('epa','DOUBLE','0.5'),
        ('special_teams_play','INTEGER','0'),('qb_kneel','INTEGER','0'),('qb_spike','INTEGER','0'),
    ]:
        con.execute(f'ALTER TABLE pbp_raw ADD COLUMN {name} {kind} DEFAULT {value}')
    # Partial target game has absurd statistics, and must never reach transformation.
    con.execute("INSERT INTO schedules_raw SELECT * REPLACE('2024_02_NYJ_BUF' AS game_id,2 AS week, DATE '2024-09-15' AS gameday,NULL AS home_score,NULL AS away_score) FROM schedules_raw")
    con.execute("INSERT INTO pbp_raw SELECT * REPLACE('2024_02_NYJ_BUF' AS game_id,2 AS week,99 AS total_home_score) FROM pbp_raw WHERE play_id=1")
    result=[]
    for dataset in ('schedules','players','pbp','player_stats'):
        path=tmp_path/'data'/f'{dataset}.parquet'
        path.parent.mkdir(exist_ok=True)
        con.execute(f'COPY (SELECT * EXCLUDE(source_sha256) FROM {dataset}_raw) TO {sql_literal(path)} (FORMAT PARQUET)')
        result.append(dict(dataset=dataset,season=2024 if dataset in ('pbp','player_stats') else None,
            path=path.relative_to(tmp_path).as_posix(),sha256=sha256_file(path),
            downloaded_at='2024-09-09T00:00:00+00:00',fetched_at='2024-09-09T00:00:00+00:00'))
    return result


def test_completed_only_reuses_metrics_and_original_clocks(source_records,tmp_path):
    bundle=current.prepare_bundle(tmp_path,2024,source_records,now=NOW)
    assert len(bundle['schedules']) == 2
    assert [g['game_id'] for g in bundle['games']] == ['2024_01_NYJ_BUF']
    game=bundle['games'][0]
    assert game['source']['actual_kickoff']=='2024-09-01T17:00:00+00:00'
    assert game['source']['available_at']=='2024-09-02T17:00:00+00:00'
    assert game['source']['availability_verified'] is False
    assert game['kickers'][0]['xpm']==1
    assert game['kickers'][0]['statistical_label_usable'] is True
    home=next(r for r in game['teams'] if r['team']=='BUF')
    assert (home['points'],home['touchdowns'],home['drives'],home['epa_sum'])==(14,1,1,0.5)
    assert all(r['coverage_ok'] for r in game['conversions'])
    assert 'team' not in bundle['players'][0]


def test_missing_completed_pbp_fails_instead_of_false_first_game(source_records,tmp_path,synthetic):
    con=synthetic[3]
    con.execute("DELETE FROM pbp_raw WHERE game_id='2024_01_NYJ_BUF'")
    source=next(r for r in source_records if r['dataset']=='pbp')
    path=tmp_path/source['path'];path.unlink()
    con.execute(f'COPY (SELECT * EXCLUDE(source_sha256) FROM pbp_raw) TO {sql_literal(path)} (FORMAT PARQUET)')
    source['sha256']=sha256_file(path)
    with pytest.raises(current.CurrentSourceError,match='coverage'):
        current.prepare_bundle(tmp_path,2024,source_records,now=NOW)


def test_cache_refresh_equal_content_records_real_capture_time(source_records,tmp_path,monkeypatch):
    calls=[]
    def download(config, source):
        calls.append(source['dataset'])
        assert config.timeout_seconds <= 60 and config.retries <= 2
        return dict(next(r for r in source_records if r['dataset']==source['dataset']))
    monkeypatch.setattr(current,'download',download)
    first=current.load_current_sources(tmp_path,2024,now=NOW,clock=lambda:NOW)
    fresh=current.load_current_sources(tmp_path,2024,now=NOW+timedelta(hours=1),clock=lambda:NOW+timedelta(hours=1))
    assert len(calls)==4
    assert fresh['sources'][0]['fetched_at']==NOW.isoformat()
    refreshed=current.load_current_sources(tmp_path,2024,refresh=True,now=NOW+timedelta(hours=2),clock=lambda:NOW+timedelta(hours=2))
    assert len(calls)==8
    assert refreshed['sources'][0]['fetched_at']==(NOW+timedelta(hours=2)).isoformat()
    assert refreshed['sources'][0]['downloaded_at']=='2024-09-09T00:00:00+00:00'
    assert first['games']==refreshed['games']
    current.load_current_sources(tmp_path,2024,now=NOW+timedelta(hours=9),clock=lambda:NOW+timedelta(hours=9))
    assert len(calls)==12


def test_source_corruption_rejected_before_using_derived_cache(source_records,tmp_path):
    current.prepare_bundle(tmp_path,2024,source_records,now=NOW)
    (tmp_path/source_records[0]['path']).write_bytes(b'corrupt')
    with pytest.raises(current.CurrentSourceError,match='integrity'):
        current.prepare_bundle(tmp_path,2024,source_records,now=NOW)


def test_required_download_failure_is_sanitized(tmp_path,monkeypatch):
    def fail(*args):
        raise OSError('secret-query-token=hidden')
    monkeypatch.setattr(current,'download',fail)
    with pytest.raises(current.CurrentSourceError) as error:
        current.load_current_sources(tmp_path,2024,now=NOW)
    assert 'hidden' not in str(error.value)
    assert 'schedules' in str(error.value)


def test_derived_corruption_is_rejected(source_records,tmp_path):
    bundle=current.prepare_bundle(tmp_path,2024,source_records,now=NOW)
    path=tmp_path/'data/cache/current/2024/derived'/bundle['bundle_id']/'bundle.json'
    path.write_text('{}',encoding='utf-8')
    with pytest.raises(current.CurrentSourceError,match='integrity'):
        current.prepare_bundle(tmp_path,2024,source_records,now=NOW)


def test_empty_season_allowed_only_until_scheduled_prior_games_exist(source_records,tmp_path,synthetic):
    con=synthetic[3]
    con.execute('UPDATE schedules_raw SET home_score=NULL,away_score=NULL')
    source=next(r for r in source_records if r['dataset']=='schedules')
    path=tmp_path/source['path'];path.unlink()
    con.execute(f'COPY (SELECT * EXCLUDE(source_sha256) FROM schedules_raw) TO {sql_literal(path)} (FORMAT PARQUET)')
    source['sha256']=sha256_file(path)
    selected=[r for r in source_records if r['dataset'] in ('schedules','players')]
    early=datetime(2024,8,30,tzinfo=timezone.utc)
    assert current.prepare_bundle(tmp_path,2024,selected,now=early)['games']==[]
    with pytest.raises(current.CurrentSourceError,match='coverage'):
        current.prepare_bundle(tmp_path,2024,selected,now=NOW)


def test_final_score_disagreement_fails(source_records,tmp_path,synthetic):
    con=synthetic[3]
    con.execute("UPDATE schedules_raw SET home_score=99 WHERE week=1")
    source=next(r for r in source_records if r['dataset']=='schedules')
    path=tmp_path/source['path'];path.unlink()
    con.execute(f'COPY (SELECT * EXCLUDE(source_sha256) FROM schedules_raw) TO {sql_literal(path)} (FORMAT PARQUET)')
    source['sha256']=sha256_file(path)
    with pytest.raises(current.CurrentSourceError,match='coverage'):
        current.prepare_bundle(tmp_path,2024,source_records,now=NOW)


def test_unrequested_season_is_never_read(source_records,tmp_path):
    source_records.append(dict(dataset='pbp',season=2025,path='data/DO_NOT_READ',sha256='bad'))
    bundle=current.prepare_bundle(tmp_path,2024,source_records,now=NOW)
    assert len(bundle['games'])==1
    assert {r['season'] for r in bundle['sources']}=={None,2024}


def test_capture_clock_records_after_each_fetch_not_request_start(source_records,tmp_path,monkeypatch):
    elapsed=[0]
    def download(config,source):
        elapsed[0]+=10
        return dict(next(r for r in source_records if r['dataset']==source['dataset']))
    monkeypatch.setattr(current,'download',download)
    bundle=current.load_current_sources(tmp_path,2024,now=NOW,
        clock=lambda:NOW+timedelta(seconds=elapsed[0]))
    assert [r['fetched_at'] for r in bundle['sources']]==[
        '2024-09-10T12:00:10+00:00','2024-09-10T12:00:20+00:00',
        '2024-09-10T12:00:30+00:00','2024-09-10T12:00:40+00:00']
    assert bundle['generated_at']=='2024-09-10T12:00:40+00:00'


def test_future_tbd_schedule_does_not_block_completed_history(source_records,tmp_path,synthetic):
    con=synthetic[3]
    con.execute("UPDATE schedules_raw SET gametime=NULL WHERE week=2")
    source=next(r for r in source_records if r['dataset']=='schedules')
    path=tmp_path/source['path'];path.unlink()
    con.execute(f'COPY (SELECT * EXCLUDE(source_sha256) FROM schedules_raw) TO {sql_literal(path)} (FORMAT PARQUET)')
    source['sha256']=sha256_file(path)
    bundle=current.prepare_bundle(tmp_path,2024,source_records,now=NOW)
    assert len(bundle['games'])==1
    assert bundle['schedules'][1]['scheduled_kickoff'] is None
