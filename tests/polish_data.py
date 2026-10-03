"""Shared current-season fixture for the polish-pass tests (no network, no files)."""
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
MEVIS, ELLIOTT, PRACTICE, FORMER = '00-0039498', '00-0033787', '00-0040000', '00-0030000'
LINC = (39.90083333, -75.1675)


def _event(gid, week, kickoff, away, home, kickers):
    source = dict(actual_kickoff=kickoff.isoformat(), scheduled_kickoff=kickoff.isoformat(),
                  last_event=(kickoff+timedelta(hours=3)).isoformat(),
                  available_at=(kickoff+timedelta(hours=24)).isoformat(), event_completed=True,
                  temporal_class='historical_event_data', availability_verified=False, sha256='a'*64)
    teams, conversions = [], []
    for team, opp, points in ((home, away, 24), (away, home, 17)):
        common = dict(game_id=gid, season=2026, team=team, opponent=opp)
        teams.append(dict(common, points=points, touchdowns=3, drives=11, red_zone_drives=4,
                          red_zone_touchdowns=2, epa_sum=1.5, epa_plays=60, successes=27))
        conversions.append(dict(common, two_pt_attempts=0, team_xpa=3, coverage_ok=True))
    rows = [dict(game_id=gid, season=2026, week=week, game_type='REG', team=t, opponent=o, kicker_id=k,
                 kicker_name=n, xpa=3, xpm=3, statistical_label_usable=True) for t, o, k, n in kickers]
    return dict(game_id=gid, season=2026, source=source, kickers=rows, teams=teams, conversions=conversions)


def make_bundle():
    schedules, games = [], []

    def game(gid, week, kickoff, away, home, venue, roof, stadium_id):
        schedules.append(dict(game_id=gid, season=2026, week=week, game_type='REG', home_team=home,
                              away_team=away, scheduled_kickoff=kickoff.isoformat() if kickoff else None,
                              venue=venue, roof=roof, stadium_id=stadium_id))

    first = datetime(2026, 9, 20, 17, tzinfo=timezone.utc)
    for i in range(3):
        kick = first+timedelta(days=7*i)
        game(f'2026_{i+1:02}_SF_LA', i+1, kick, 'SF', 'LA', 'SoFi Stadium', 'dome', 'LAX01')
        game(f'2026_{i+1:02}_DAL_PHI', i+1, kick, 'DAL', 'PHI', 'Lincoln Financial Field', 'outdoors', 'PHI00')
        games.append(_event(f'2026_{i+1:02}_SF_LA', i+1, kick, 'SF', 'LA', [('LA', 'SF', MEVIS, 'Harrison Mevis')]))
        games.append(_event(f'2026_{i+1:02}_DAL_PHI', i+1, kick, 'DAL', 'PHI', [('PHI', 'DAL', ELLIOTT, 'Jake Elliott')]))
    game('2026_05_LA_PHI', 5, datetime(2026, 10, 11, 17, tzinfo=timezone.utc), 'LA', 'PHI',
         'Lincoln Financial Field', 'outdoors', 'PHI00')
    game('2026_05_DAL_HOU', 5, datetime(2026, 10, 11, 17, tzinfo=timezone.utc), 'DAL', 'HOU', 'Reliant Stadium', '', 'HOU00')
    game('2026_06_PHI_DET', 6, datetime(2026, 10, 18, 17, tzinfo=timezone.utc), 'PHI', 'DET', 'Ford Field', 'dome', 'DET00')
    # nflverse quirk: a London game carrying the home team's stadium id.
    game('2026_07_LA_JAX', 7, datetime(2026, 10, 25, 13, 30, tzinfo=timezone.utc), 'LA', 'JAX',
         'Tottenham Hotspur Stadium', 'outdoors', 'JAX00')
    game('2026_08_PHI_LA', 8, datetime(2026, 11, 1, 20, tzinfo=timezone.utc), 'PHI', 'LA', 'SoFi Stadium', 'dome', 'LAX01')
    game('2026_09_SF_PHI', 9, None, 'SF', 'PHI', 'Lincoln Financial Field', 'outdoors', 'PHI00')
    players = [
        dict(kicker_id=MEVIS, display_name='Harrison Mevis', position='K', latest_team='LA', roster_status='ACT', last_season=2026),
        dict(kicker_id=ELLIOTT, display_name='Jake Elliott', position='K', latest_team='PHI', roster_status='ACT', last_season=2026),
        dict(kicker_id=PRACTICE, display_name='Practice Kicker', position='K', latest_team='PHI', roster_status='DEV', last_season=2026),
        dict(kicker_id=FORMER, display_name='Former Kicker', position='K', latest_team='LA', roster_status='ACT', last_season=2025),
        dict(kicker_id='00-0050000', display_name='Some Receiver', position='WR', latest_team='LA', roster_status='ACT', last_season=2026),
    ]
    fetched = (NOW-timedelta(hours=1)).isoformat()
    sources = [dict(dataset='schedules', sha256='b'*64, fetched_at=fetched, path='data/example/games.parquet'),
               dict(dataset='players', sha256='c'*64, fetched_at=fetched, path='data/example/players.parquet')]
    return dict(season=2026, generated_at=NOW.isoformat(), schedules=schedules, games=games,
                players=players, sources=sources)


def no_context(*args, **kwargs):
    return {'context': {'market': {'available': False, 'quotes': []}, 'weather': {'available': False, 'values': {}}},
            'prop_quotes': [], 'provider_timestamps': {}, 'warnings': [], 'source_failures': []}
