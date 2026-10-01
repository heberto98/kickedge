"""Weather exposure requires a verified venue and a captured pre-cutoff forecast."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib
import importlib.util
import json

import pytest


def module():
    assert importlib.util.find_spec('kickedge.providers'), 'Weather provider package missing'
    assert importlib.util.find_spec('kickedge.providers.weather'), 'Weather adapter missing'
    return importlib.import_module('kickedge.providers.weather')


IDENTITY = {'game_id': 'g1', 'kickoff': '2026-10-04T20:25:00Z',
            'prediction_cutoff': '2026-10-04T19:25:00Z'}
VENUE = {'game_id': 'g1', 'latitude': 40.8, 'longitude': -74.1,
         'roof_type': 'outdoors', 'observed_at': '2026-10-03T12:00:00Z',
         'source': 'venue-confirmation', 'source_sha256': 'a' * 64}
EVIDENCE = {'game_id': 'g1', 'latitude': 40.8, 'longitude': -74.1,
            'valid_time': '2026-10-04T20:00:00Z',
            'observed_at': '2026-10-04T18:00:00Z', 'kind': 'forecast',
            'source': 'open-meteo', 'source_sha256': 'b' * 64,
            'values': {'temperature': 17.5, 'wind_speed': 12.5, 'wind_gust': 24,
                       'precipitation_probability': 15, 'precipitation': 0.2,
                       'weather_code': 3}}


def build(evidence=None, venue=None, identity=None):
    return module().weather_features(identity or IDENTITY,
        EVIDENCE if evidence is None else evidence, VENUE if venue is None else venue)


def test_precutoff_forecast_and_venue_are_approved_without_mutation():
    e, v = deepcopy(EVIDENCE), deepcopy(VENUE)
    r = build(e, v)
    assert r['training_eligible'] and r['current_usable']
    assert r['venue_training_eligible'] and r['weather_training_eligible']
    assert r['values'] == EVIDENCE['values'] | {'roof_type': 'outdoors', 'is_dome': False}
    assert r == build(e, v)
    assert e == EVIDENCE and v == VENUE


@pytest.mark.parametrize('roof', ['dome', 'closed'])
def test_indoor_weather_is_null_even_when_available(roof):
    r = build(venue=VENUE | {'roof_type': roof})
    assert r['values']['is_dome'] is True
    assert all(r['values'][key] is None for key in EVIDENCE['values'])
    assert r['venue_training_eligible'] and not r['weather_training_eligible']


@pytest.mark.parametrize('roof', [None, 'unknown', 'retractable'])
def test_unknown_roof_does_not_assume_outdoor_exposure(roof):
    r = build(venue=VENUE | {'roof_type': roof})
    assert not r['training_eligible']
    assert r['values']['is_dome'] is None
    assert r['values']['temperature'] is None


@pytest.mark.parametrize('change', [
    {'observed_at': '2026-10-04T19:26:00Z'},
    {'observed_at': '2026-10-04T18:00:00'},
    {'published_at': '2026-10-04T18:01:00Z'},
    {'published_at': '2026-10-04T21:00:00Z'},
    {'observed_at': None, 'initialized_at': '2026-10-04T12:00:00Z'},
    {'valid_time': '2026-10-04T19:00:00Z'},
    {'valid_time': '2026-10-04T21:00:00Z'},
    {'valid_time': '2026-10-04T20:15:00Z'},
    {'game_id': 'other'}, {'latitude': 39.0}, {'longitude': None},
    {'source_sha256': None}, {'source': None},
])
def test_invalid_forecast_is_not_backdated_or_used(change):
    r = build(EVIDENCE | change)
    assert not r['weather_training_eligible']
    assert r['values']['temperature'] is None
    assert r['reasons']


def test_observed_weather_and_retrospective_roof_remain_experimental():
    r = build(EVIDENCE | {'kind': 'observed', 'observed_at': '2026-10-05T12:00:00Z'},
              VENUE | {'observed_at': '2026-10-05T12:00:00Z'})
    assert r['values']['temperature'] == 17.5
    assert r['values']['is_dome'] is False
    assert not r['training_eligible'] and not r['current_usable']
    assert not r['venue_training_eligible'] and not r['weather_training_eligible']


@pytest.mark.parametrize('change', [{'game_id': 'other'}, {'latitude': None},
                                  {'source_sha256': None}])
def test_unbound_venue_cannot_approve_weather(change):
    r = build(venue=VENUE | change)
    assert not r['venue_training_eligible'] and not r['weather_training_eligible']
    assert r['values']['temperature'] is None


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1, True, 'bad'])
def test_invalid_wind_is_missing_not_zero(value):
    r = build(EVIDENCE | {'values': EVIDENCE['values'] | {'wind_speed': value}})
    assert r['values']['wind_speed'] is None
    assert r['values']['temperature'] == 17.5


def test_missing_forecast_preserves_known_roof_and_missing_fields():
    r = build({})
    assert r['values']['roof_type'] == 'outdoors'
    assert r['venue_training_eligible']
    assert not r['weather_training_eligible']
    assert all(r['values'][key] is None for key in EVIDENCE['values'])


def test_historical_schedule_without_venue_coordinates_retains_only_experimental_values():
    venue = {k: v for k, v in VENUE.items() if k not in {'latitude', 'longitude', 'observed_at'}}
    observed = {k: v for k, v in EVIDENCE.items() if k not in {'latitude', 'longitude', 'observed_at'}}
    observed.update(kind='observed', valid_time=IDENTITY['kickoff'])
    r = build(observed, venue)
    assert r['values']['temperature'] == 17.5
    assert r['values']['roof_type'] == 'outdoors'
    assert not r['weather_training_eligible'] and not r['venue_training_eligible']
    assert not r['training_eligible'] and not r['current_usable']
    indoor = build(observed, venue | {'roof_type': 'dome'})
    assert indoor['values']['temperature'] is None and indoor['values']['is_dome'] is True
    assert not indoor['training_eligible']


def test_missing_weather_fields_are_null_but_real_zero_is_preserved():
    r = build(EVIDENCE | {'values': {'precipitation': 0}})
    assert r['values']['temperature'] is None and r['values']['precipitation'] == 0
    assert len(module().FEATURE_NAMES) == 8


def test_http_failure_does_not_expose_response_body():
    class FailedSession(Session):
        def get(self, *args, **kwargs):
            response = super().get(*args, **kwargs)
            response.status_code = 500
            return response

    with pytest.raises(module().WeatherProviderError) as error:
        module().OpenMeteoClient(session=FailedSession({'error': 'private-message'}), clock=now).forecast(40, -74, IDENTITY['kickoff'])
    assert 'private-message' not in str(error.value)


def test_invalid_identity_rejected_without_target_information():
    with pytest.raises(ValueError):
        build(identity=IDENTITY | {'prediction_cutoff': IDENTITY['kickoff']})


class Response:
    status_code = 200

    def __init__(self, payload):
        self.content = json.dumps(payload).encode()

    def json(self):
        return json.loads(self.content)


class Session:
    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.calls = payload, error, []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return Response(self.payload)


def payload():
    return {'latitude': 40.81, 'longitude': -74.09, 'utc_offset_seconds': 0,
            'hourly_units': {'time': 'iso8601', 'temperature_2m': '°C',
                             'wind_speed_10m': 'km/h', 'wind_gusts_10m': 'km/h',
                             'precipitation_probability': '%', 'precipitation': 'mm',
                             'weather_code': 'wmo code'},
            'hourly': {'time': ['2026-10-04T19:00', '2026-10-04T20:00'],
                       'temperature_2m': [18, 17.5], 'wind_speed_10m': [10, 12.5],
                       'wind_gusts_10m': [20, 24], 'precipitation_probability': [10, 15],
                       'precipitation': [0, 0.2], 'weather_code': [2, 3]}}


def now():
    return datetime(2026, 10, 4, 18, tzinfo=timezone.utc)


def test_client_captures_requested_hour_units_and_single_day_without_auth():
    session = Session(payload())
    result = module().OpenMeteoClient(session=session, clock=now).forecast(40.8, -74.1, IDENTITY['kickoff'])
    assert result['values'] == EVIDENCE['values']
    assert result['latitude'] == 40.8 and result['longitude'] == -74.1
    assert result['valid_time'] == '2026-10-04T20:00:00+00:00'
    assert result['kind'] == 'forecast' and len(result['source_sha256']) == 64
    assert 'published_at' not in result and 'game_id' not in result
    assert result['observed_at'] == '2026-10-04T18:00:00+00:00'
    url, kwargs = session.calls[0]
    assert url == 'https://api.open-meteo.com/v1/forecast'
    assert kwargs['timeout'] == 20 and kwargs['allow_redirects'] is False
    assert kwargs['params']['start_date'] == kwargs['params']['end_date'] == '2026-10-04'
    assert kwargs['params']['timezone'] == 'UTC'
    assert kwargs['params']['temperature_unit'] == 'celsius'
    assert kwargs['params']['wind_speed_unit'] == 'kmh'
    assert 'headers' not in kwargs and 'auth' not in kwargs
    assert len(session.calls) == 1


@pytest.mark.parametrize('lat,lon,kickoff', [
    (None, -74, IDENTITY['kickoff']), (91, -74, IDENTITY['kickoff']),
    (40, float('nan'), IDENTITY['kickoff']), (40, 181, IDENTITY['kickoff']),
    (40, -74, '2026-10-04T20:00:00'), (40, -74, '2025-10-04T20:00:00Z'),
    (40, -74, '2026-11-04T20:00:00Z')])
def test_invalid_or_historical_request_makes_no_call(lat, lon, kickoff):
    session = Session(payload())
    with pytest.raises(ValueError):
        module().OpenMeteoClient(session=session, clock=now).forecast(lat, lon, kickoff)
    assert not session.calls


def test_network_exception_is_sanitized_and_not_retried():
    session = Session(error=RuntimeError('secret-token-123'))
    with pytest.raises(module().WeatherProviderError) as error:
        module().OpenMeteoClient(session=session, clock=now).forecast(40, -74, IDENTITY['kickoff'])
    assert 'secret-token-123' not in str(error.value)
    assert error.value.__suppress_context__
    assert len(session.calls) == 1


@pytest.mark.parametrize('bad', [{}, {'hourly': []}, {'utc_offset_seconds': 3600},
                               {'hourly_units': {'temperature_2m': '°F'}}])
def test_malformed_provider_response_fails_closed(bad):
    session = Session(bad)
    with pytest.raises(module().WeatherProviderError):
        module().OpenMeteoClient(session=session, clock=now).forecast(40, -74, IDENTITY['kickoff'])
