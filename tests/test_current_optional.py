"""Optional current context: external I/O replaced, real identity/evidence gates."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from kickedge.current.optional import collect_context


NOW = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
TARGET = dict(game_id='2026_05_HOU_DAL', season=2026, week=5, game_type='REG',
              kickoff='2026-10-04T20:25:00Z', home_team='DAL', away_team='HOU',
              team='DAL', opponent='HOU', venue='AT&T Stadium', roof='open',
              latitude=32.7473, longitude=-97.0945, schedule_sha256='a'*64,
              schedule_fetched_at='2026-10-03T10:00:00Z')
PLAYER = dict(kicker_id='00-0037747', kicker_name='Brandon Aubrey')


def capture(rows, **changes):
    return dict(source='ParlayAPI', source_sha256='b'*64,
                observed_at='2026-10-03T11:55:00Z', rows=rows,
                metadata={'coverage_complete': False}) | changes


def prop(**changes):
    return dict(canonical_event_id=TARGET['game_id'], game_id='provider-id',
                home_team='Dallas Cowboys', away_team='Houston Texans',
                commence_time=TARGET['kickoff'], game_date='2026-10-04',
                player='Brandon Aubrey', player_id=PLAYER['kicker_id'],
                market_key='player_extra_point_made', bookmaker='fliff',
                bookmaker_type='sportsbook', line=2.5, over_price=119,
                under_price=-140, last_update='2026-10-03T11:50:00Z') | changes


def event(**changes):
    return dict(id='provider-id', canonical_event_id=TARGET['game_id'],
                home_team='Dallas Cowboys', away_team='Houston Texans',
                commence_time=TARGET['kickoff'], bookmakers=[{
                    'key': 'fliff', 'last_update': '2026-10-03T11:50:00Z',
                    'markets': [
                        {'key': 'spreads', 'outcomes': [
                            {'name': 'Dallas Cowboys', 'point': -6},
                            {'name': 'Houston Texans', 'point': 6}]},
                        {'key': 'totals', 'outcomes': [
                            {'name': 'Over', 'point': 46}, {'name': 'Under', 'point': 46}]},
                        {'key': 'h2h', 'outcomes': [
                            {'name': 'Dallas Cowboys', 'price': -200},
                            {'name': 'Houston Texans', 'price': 180}]}]}]) | changes


class Parlay:
    def __init__(self, props=None, markets=None, failure=None):
        self.props = props if props is not None else capture([prop()])
        self.markets = markets if markets is not None else capture([event()])
        self.failure = failure
        self.calls = []

    def current_xpm(self):
        self.calls.append('props')
        if self.failure:
            raise self.failure
        return deepcopy(self.props)

    def current_markets(self):
        self.calls.append('markets')
        return deepcopy(self.markets)


def collect(client=None, target=None, **kwargs):
    return collect_context(target or TARGET, PLAYER, line=2.5, now=NOW, clock=lambda: NOW,
                           no_weather=True, parlay_factory=lambda **_: client or Parlay(), **kwargs)


@pytest.mark.parametrize('failure', [RuntimeError('HTTP 503 secret-key'), TimeoutError('secret-url')])
def test_failure_is_optional_sanitized_and_other_endpoint_continues(failure):
    client = Parlay(failure=failure)
    result = collect(client)
    assert result['prop_quotes'] == []
    assert result['context']['market']['available']
    assert result['source_failures'][0]['critical'] is False
    assert 'secret' not in str(result)
    assert client.calls == ['props', 'markets']


def test_valid_quote_preserves_all_books_without_auto_selection():
    result = collect(Parlay(props=capture([prop(), prop(bookmaker='fanduel', over_price=110)])))
    assert [q['over_price'] for q in result['prop_quotes']] == [119, 110]
    assert result['prop_quotes'][0]['observed_at'] == '2026-10-03T11:55:00Z'
    assert result['provider_timestamps']['parlay_xpm'] == '2026-10-03T11:55:00Z'


def test_dfs_and_unknown_books_never_become_sportsbook_quotes():
    rows = [prop(bookmaker='sleeper', bookmaker_type='dfs'),
            prop(bookmaker='unverified', bookmaker_type='unknown')]
    result = collect(Parlay(props=capture(rows)))
    assert result['prop_quotes'] == []
    assert any('DFS' in warning for warning in result['warnings'])


@pytest.mark.parametrize('changes', [
    {'canonical_event_id': '2026_06_DAL_HOU'},
    {'home_team': 'Houston Texans', 'away_team': 'Dallas Cowboys'},
    {'commence_time': '2026-10-11T20:25:00Z'},
    {'game_date': '2026-10-05'}, {'player': 'Other Kicker', 'player_id': 'other'},
    {'line': 3.5}, {'commence_time': None},
])
def test_wrong_event_player_or_line_is_filtered_even_with_same_name(changes):
    result = collect(Parlay(props=capture([prop(**changes), prop()])))
    assert len(result['prop_quotes']) == 1


@pytest.mark.parametrize('changes', [
    {'observed_at': '2026-10-03T12:00:01Z'},
    {'observed_at': None}, {'source_sha256': 'invalid'},
])
def test_capture_cannot_be_backdated_from_last_update(changes):
    assert collect(Parlay(props=capture([prop()], **changes)))['prop_quotes'] == []


def test_future_source_update_is_not_accepted():
    result = collect(Parlay(props=capture([prop(last_update='2026-10-03T11:59:00Z')])))
    assert result['prop_quotes'] == []


def test_game_market_team_perspective_and_reversed_event_rejection():
    result = collect(target=TARGET | {'team': 'HOU', 'opponent': 'DAL'})
    values = result['context']['market']['quotes'][0]['values']
    assert values['game_spread'] == 6
    assert values['moneyline_team'] == 180
    assert values['moneyline_opponent'] == -200
    assert values['game_total'] == 46
    result = collect(Parlay(markets=capture([event(home_team='Houston Texans', away_team='Dallas Cowboys')])))
    assert not result['context']['market']['available']


def test_disabled_providers_never_construct_clients():
    def forbidden(**kwargs):
        raise AssertionError('provider constructed')
    result = collect_context(TARGET, PLAYER, line=2.5, now=NOW, clock=lambda: NOW, no_market=True,
                             no_weather=True, parlay_factory=forbidden, weather_factory=forbidden)
    assert result['source_failures'] == []
    assert result['prop_quotes'] == []


class Weather:
    calls = 0

    def forecast(self, latitude, longitude, kickoff):
        self.calls += 1
        assert (latitude, longitude, kickoff) == (32.7473, -97.0945, TARGET['kickoff'])
        return dict(source='Open-Meteo', source_sha256='c'*64,
                    observed_at='2026-10-03T11:55:00Z', kind='forecast',
                    latitude=latitude, longitude=longitude, valid_time='2026-10-04T20:00:00Z',
                    values={'temperature': 20, 'wind_speed': 15, 'wind_gust': 25,
                            'precipitation_probability': 10, 'precipitation': 0, 'weather_code': 0})


@pytest.mark.parametrize('roof', ['dome', 'closed', 'unknown', 'retractable'])
def test_indoor_or_unresolved_roof_never_requests_outdoor_weather(roof):
    weather = Weather()
    result = collect_context(TARGET | {'roof': roof}, PLAYER, line=2.5, now=NOW, clock=lambda: NOW,
                             no_market=True, weather_factory=lambda **_: weather)
    assert weather.calls == 0
    assert result['context']['weather']['values'].get('temperature') is None
    assert bool(result['warnings'])


def test_outdoor_forecast_is_bound_to_schedule_and_is_context_only():
    weather = Weather()
    result = collect_context(TARGET, PLAYER, line=2.5, now=NOW, clock=lambda: NOW, no_market=True,
                             weather_factory=lambda **_: weather)
    assert weather.calls == 1
    assert result['context']['weather']['available']
    assert result['context']['weather']['values']['wind_speed'] == 15
    assert result['provider_timestamps']['open_meteo'] == '2026-10-03T11:55:00Z'


def test_missing_coordinates_or_weather_failure_continue():
    def fail(**kwargs):
        raise TimeoutError('secret-api-key')
    result = collect_context(TARGET | {'latitude': None}, PLAYER, line=2.5, now=NOW, clock=lambda: NOW,
                             no_market=True, weather_factory=fail)
    assert not result['context']['weather']['available']
    assert result['source_failures'] == []
    result = collect_context(TARGET, PLAYER, line=2.5, now=NOW, clock=lambda: NOW,
                             no_market=True, weather_factory=fail)
    assert result['source_failures'][0]['provider'] == 'open_meteo'
    assert 'secret' not in str(result)


def test_response_after_start_but_before_completion_is_not_backdated():
    client = Parlay(props=capture([prop()], observed_at='2026-10-03T12:00:02Z'))
    result = collect_context(TARGET, PLAYER, line=2.5, now=NOW, no_weather=True,
                             clock=lambda: datetime(2026, 10, 3, 12, 0, 3, tzinfo=timezone.utc),
                             parlay_factory=lambda **_: client)
    assert result['prop_quotes'][0]['observed_at'] == '2026-10-03T12:00:02Z'


def test_response_after_prediction_horizon_is_excluded():
    client = Parlay(props=capture([prop()], observed_at='2026-10-04T19:25:01Z'))
    result = collect_context(TARGET, PLAYER, line=2.5, now=NOW, no_weather=True,
                             clock=lambda: datetime(2026, 10, 4, 19, 26, tzinfo=timezone.utc),
                             parlay_factory=lambda **_: client)
    assert result['prop_quotes'] == []
    assert result['source_failures'][0]['critical'] is False


def test_duplicate_general_events_do_not_choose_first_market():
    result = collect(Parlay(markets=capture([event(), event(id='another-id')])))
    assert not result['context']['market']['available']
    assert any('ambiguous' in warning for warning in result['warnings'])


def test_general_event_timestamp_cannot_exceed_capture():
    result = collect(Parlay(markets=capture([event(last_update='2026-10-03T12:00:01Z')])))
    assert not result['context']['market']['available']


def test_partial_game_prop_does_not_match_full_game_line():
    result = collect(Parlay(props=capture([prop(period='1H')])))
    assert result['prop_quotes'] == []


def test_disabled_context_imports_no_provider_or_dotenv(monkeypatch):
    import builtins
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert name not in {'dotenv', 'kickedge.providers.parlay', 'kickedge.providers.weather'}
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded_import)
    result = collect_context(TARGET, PLAYER, line=2.5, now=NOW, clock=lambda: NOW,
                             no_market=True, no_weather=True)
    assert result['source_failures'] == []
