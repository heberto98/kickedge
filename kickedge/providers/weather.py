"""Current Open-Meteo snapshots and a pure, conservative weather evidence gate.

All weather units are C, km/h, %, mm and WMO code. A forecast's valid time
describes the predicted hour, not when it was published. Captured forecasts
can prove availability; model initialization alone and retrospective observed
weather cannot. This module never requests a historical forecast archive.
"""
from datetime import datetime, timezone
import hashlib
import math
from collections.abc import Mapping


URL = 'https://api.open-meteo.com/v1/forecast'
HOURLY_FIELDS = {
    'temperature': 'temperature_2m',
    'wind_speed': 'wind_speed_10m',
    'wind_gust': 'wind_gusts_10m',
    'precipitation_probability': 'precipitation_probability',
    'precipitation': 'precipitation',
    'weather_code': 'weather_code',
}
FEATURE_NAMES = tuple(HOURLY_FIELDS) + ('is_dome', 'roof_type')
UNITS = {'temperature_2m': '°C', 'wind_speed_10m': 'km/h',
         'wind_gusts_10m': 'km/h', 'precipitation_probability': '%',
         'precipitation': 'mm', 'weather_code': 'wmo code'}
WMO_CODES = {0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65,
             66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99}


class WeatherProviderError(RuntimeError):
    """Sanitized provider failure, without remote bodies or underlying URLs."""


def _instant(value):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ValueError('An explicit timezone-aware timestamp is required') from None


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _coordinates(record):
    latitude, longitude = _number(record.get('latitude')), _number(record.get('longitude'))
    if latitude is None or longitude is None or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude


def _values(raw):
    raw = raw if isinstance(raw, Mapping) else {}
    result = {}
    for field in HOURLY_FIELDS:
        value = _number(raw.get(field))
        if value is not None:
            if field in {'wind_speed', 'wind_gust', 'precipitation'} and value < 0:
                value = None
            elif field == 'precipitation_probability' and not 0 <= value <= 100:
                value = None
            elif field == 'weather_code':
                value = int(value) if value in WMO_CODES else None
        result[field] = value
    return result


def _source_valid(record):
    digest = record.get('source_sha256')
    return (isinstance(record.get('source'), str) and bool(record['source'].strip())
            and isinstance(digest, str) and len(digest) == 64
            and all(char in '0123456789abcdefABCDEF' for char in digest))


def _capture_valid(record, cutoff):
    try:
        captured = _instant(record.get('observed_at'))
        if captured > cutoff:
            return False
        return record.get('published_at') is None or _instant(record['published_at']) <= captured
    except ValueError:
        return False


def _provenance(record):
    return {key: record.get(key) for key in (
        'source', 'source_sha256', 'observed_at', 'published_at',
        'valid_time', 'kind', 'latitude', 'longitude')}


def weather_features(identity, evidence=None, venue=None):
    """Return eight values with separate venue/weather eligibility and reasons.

    Identity requires game_id, kickoff and prediction_cutoff. Both evidence and
    venue must bind game_id and exact requested latitude/longitude, carry source
    and source_sha256, and include observed_at for approval. Evidence also needs
    kind ('forecast' or experimental 'observed'), kickoff-hour valid_time, and a
    values mapping. Optional published_at must precede capture. Venue roof_type
    is dome/closed/outdoors/open; retractable or unknown never implies exposure.

    Late observed weather and retrospective venue can retain experimental values,
    including source/game-bound schedule observations lacking venue coordinates.
    Late forecasts are discarded. Consumers must honor the granular flags:
    venue_training_eligible covers roof_type/is_dome; weather_training_eligible
    covers the six non-null outdoor fields. Indoor fields remain null. Aggregate
    training_eligible/current_usable require verified venue plus a usable forecast
    or verified indoor conditions. This function has no clock/network side effects.
    """
    kickoff = _instant(identity.get('kickoff'))
    cutoff = _instant(identity.get('prediction_cutoff'))
    if not identity.get('game_id') or cutoff >= kickoff:
        raise ValueError('A game and prediction cutoff strictly before kickoff are required')
    evidence = evidence if isinstance(evidence, Mapping) else {}
    venue = venue if isinstance(venue, Mapping) else {}
    values = {field: None for field in HOURLY_FIELDS} | {'is_dome': None, 'roof_type': None}
    reasons = []
    venue_bound = venue.get('game_id') == identity['game_id'] and _source_valid(venue)
    venue_eligible = False
    weather_eligible = False
    if not venue_bound:
        reasons.append('venue_identity_coordinates_or_source_unverified')
    else:
        raw_roof = venue.get('roof_type')
        roof = raw_roof.strip().lower() if isinstance(raw_roof, str) else None
        roof = 'outdoors' if roof == 'outdoor' else roof
        known_roof = roof in {'dome', 'closed', 'outdoors', 'open'}
        values['roof_type'] = roof if roof in {'dome', 'closed', 'outdoors', 'open', 'retractable', 'unknown'} else None
        if known_roof:
            values['is_dome'] = roof in {'dome', 'closed'}
            venue_eligible = _capture_valid(venue, cutoff) and _coordinates(venue) is not None
            if not venue_eligible:
                reasons.append('venue_not_verified_before_cutoff')
        else:
            reasons.append('roof_exposure_unknown')

    if values['is_dome'] is True:
        reasons.append('indoor_outdoor_weather_not_applicable')
    elif values['is_dome'] is False:
        kind = evidence.get('kind')
        coordinates_match = (_coordinates(venue) is not None
                             and _coordinates(evidence) == _coordinates(venue))
        # Missing coordinates never grant approval; schedule observations can
        # still be useful as explicitly experimental values for their game.
        observed_unlocated = (kind == 'observed' and
                              all(record.get(key) is None for record in (evidence, venue)
                                  for key in ('latitude', 'longitude')))
        weather_bound = (evidence.get('game_id') == identity['game_id']
                         and _source_valid(evidence)
                         and (coordinates_match or observed_unlocated))
        try:
            valid_hour = _instant(evidence.get('valid_time'))
            valid_time = (valid_hour == kickoff.replace(minute=0, second=0, microsecond=0)
                          or (kind == 'observed' and valid_hour == kickoff))
        except ValueError:
            valid_time = False
        if not weather_bound:
            reasons.append('weather_identity_coordinates_or_source_unverified')
        elif not valid_time:
            reasons.append('weather_valid_time_does_not_match_kickoff_hour')
        elif kind not in {'forecast', 'observed'}:
            reasons.append('weather_kind_unverified')
        elif kind == 'forecast' and not _capture_valid(evidence, cutoff):
            reasons.append('forecast_not_captured_before_cutoff')
        else:
            values.update(_values(evidence.get('values')))
            populated = any(values[field] is not None for field in HOURLY_FIELDS)
            weather_eligible = populated and kind == 'forecast' and venue_eligible
            if not populated:
                reasons.append('weather_values_missing_or_invalid')
            if kind == 'observed':
                reasons.append('observed_weather_is_experimental')
    aggregate = bool(venue_eligible and (values['is_dome'] or weather_eligible))
    return {'values': values, 'training_eligible': aggregate, 'current_usable': aggregate,
            'venue_training_eligible': bool(venue_eligible),
            'weather_training_eligible': bool(weather_eligible),
            'reasons': reasons,
            'provenance': {'venue': _provenance(venue), 'weather': _provenance(evidence)}}


class OpenMeteoClient:
    """One unauthenticated, bounded current-forecast request; no retry/archive.

    Returned evidence is not game-bound: the caller must explicitly attach the
    intended game_id and provide separate venue evidence to weather_features.
    Requested coordinates remain the binding, since provider grid coordinates
    can differ. Captured time is recorded after receipt, never model init time.
    """

    def __init__(self, session=None, clock=None, timeout=20):
        timeout_value = _number(timeout)
        if timeout_value is None or not 0 < timeout_value <= 60:
            raise ValueError('Timeout must be positive and at most 60 seconds')
        self.session = session
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.timeout = timeout_value

    def forecast(self, latitude, longitude, kickoff):
        coords = _coordinates({'latitude': latitude, 'longitude': longitude})
        if coords is None:
            raise ValueError('Valid latitude and longitude are required')
        kickoff = _instant(kickoff)
        now = _instant(self.clock())
        if not now < kickoff or not 0 <= (kickoff.date() - now.date()).days < 16:
            raise ValueError('Kickoff must be future and within the current 16-day forecast window')
        day = kickoff.date().isoformat()
        params = {'latitude': coords[0], 'longitude': coords[1],
                  'hourly': ','.join(HOURLY_FIELDS.values()), 'timezone': 'UTC',
                  'temperature_unit': 'celsius', 'wind_speed_unit': 'kmh',
                  'precipitation_unit': 'mm', 'start_date': day, 'end_date': day}
        try:
            if self.session is None:
                import requests
                self.session = requests.Session()
                # Do not inherit a local .netrc credential for a public service.
                self.session.trust_env = False
            response = self.session.get(URL, params=params, timeout=self.timeout, allow_redirects=False)
            captured = _instant(self.clock())
            if response.status_code != 200:
                raise WeatherProviderError('Open-Meteo forecast request failed')
            content = response.content
            if len(content) > 1_000_000:
                raise WeatherProviderError('Open-Meteo response exceeded the permitted size')
            payload = response.json()
            if not isinstance(payload, Mapping) or payload.get('utc_offset_seconds') != 0:
                raise ValueError
            hourly, units = payload.get('hourly'), payload.get('hourly_units')
            if not isinstance(hourly, Mapping) or not isinstance(units, Mapping):
                raise ValueError
            times = hourly.get('time')
            if not isinstance(times, list) or not 1 <= len(times) <= 24 or units.get('time') != 'iso8601':
                raise ValueError
            for source_field, unit in UNITS.items():
                if units.get(source_field) != unit:
                    raise ValueError
                series = hourly.get(source_field)
                if not isinstance(series, list) or len(series) != len(times):
                    raise ValueError
            hour = kickoff.replace(minute=0, second=0, microsecond=0)
            target = hour.strftime('%Y-%m-%dT%H:%M')
            if times.count(target) != 1:
                raise ValueError
            index = times.index(target)
            values = _values({field: hourly[source_field][index] for field, source_field in HOURLY_FIELDS.items()})
            return {'latitude': coords[0], 'longitude': coords[1],
                    'valid_time': hour.isoformat(), 'observed_at': captured.isoformat(),
                    'source': URL, 'source_sha256': hashlib.sha256(content).hexdigest(),
                    'kind': 'forecast', 'values': values}
        except WeatherProviderError:
            raise
        except Exception:
            raise WeatherProviderError('Open-Meteo forecast could not be retrieved or validated') from None
