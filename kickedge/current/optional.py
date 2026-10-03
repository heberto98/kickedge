"""Bounded optional context, kept outside the frozen predictor frame.

Provider capture clocks describe receipt, independently of feature generation.
Only evidence captured before the prediction horizon and collection completion
is usable. Provider error bodies and credentials never enter returned reports.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import re

from kickedge.teams import team_code


_SPORTSBOOKS = {'fliff', 'draftkings', 'fanduel', 'caesars', 'bovada', 'pinnacle'}


def _instant(value):
    value = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.utcoffset() is None:
        raise ValueError('Timezone-aware timestamp required')
    return value.astimezone(timezone.utc)


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _text(value):
    return ' '.join(value.split()).casefold() if isinstance(value, str) else ''


def _team(value):
    return team_code(value)


def _event_matches(row, target):
    try:
        if (_team(row.get('home_team')) != _team(target['home_team'])
                or _team(row.get('away_team')) != _team(target['away_team'])
                or _team(target['home_team']) is None or _team(target['away_team']) is None
                or _instant(row.get('commence_time')) != _instant(target['kickoff'])):
            return False
        if row.get('game_date') and row['game_date'][:10] != _instant(target['kickoff']).date().isoformat():
            return False
        # Compare shared canonical IDs only when explicitly in nflverse format.
        for field in ('canonical_event_id', 'game_id'):
            value = row.get(field)
            if isinstance(value, str) and re.fullmatch(r'\d{4}_\d{2}_[A-Z]+_[A-Z]+', value):
                if value != target['game_id']:
                    return False
        return True
    except (ValueError, TypeError, AttributeError, KeyError):
        return False


def _player_matches(row, player):
    identifiers = [row.get('player_id'), row.get('player_reference')]
    stable = [value for value in identifiers if isinstance(value, str) and value.startswith('00-')]
    if stable and any(value != player['kicker_id'] for value in stable):
        return False
    return (player['kicker_id'] in identifiers
            or bool(_text(player['kicker_name']) and _text(row.get('player')) == _text(player['kicker_name'])))


def _capture_valid(capture, cutoff):
    try:
        return (isinstance(capture['rows'], list)
                and isinstance(capture.get('source'), str) and bool(capture['source'].strip())
                and isinstance(capture.get('source_sha256'), str)
                and bool(re.fullmatch('[0-9a-fA-F]{64}', capture['source_sha256']))
                and _instant(capture['observed_at']) <= cutoff)
    except (KeyError, TypeError, AttributeError, ValueError):
        return False


def _updates_valid(row, capture):
    try:
        return all(_instant(row[field]) <= _instant(capture['observed_at'])
                   for field in ('last_update', 'last_observed', 'published_at') if row.get(field))
    except (ValueError, TypeError, AttributeError):
        return False


def _props(capture, target, player, line, warnings):
    from kickedge.providers.parlay import normalize_xpm, american_probability

    quotes = []
    for row in normalize_xpm(capture['rows']):
        if not (_event_matches(row, target) and _player_matches(row, player)):
            continue
        if row.get('period') is not None and _text(row['period']) not in {'full', 'full_game', 'full game', 'game'}:
            continue
        if row.get('line') is None or row['line'] < 0 or (line is not None and row['line'] != line):
            continue
        if row['bookmaker_type'] != 'sportsbook':
            warnings.append('DFS or unknown prop pricing is informational; no sportsbook comparison is available.')
            continue
        if not _updates_valid(row, capture):
            warnings.append('Prop timestamps are inconsistent with capture; quote excluded.')
            continue
        prices = {f'{side}_price': row[f'{side}_price'] if american_probability(row[f'{side}_price']) is not None else None
                  for side in ('over', 'under')}
        if all(value is None for value in prices.values()):
            continue
        quotes.append(row | prices | {key: capture[key] for key in ('observed_at', 'source', 'source_sha256')}
                      | {'target_game_id': target['game_id'], 'kicker_id': player['kicker_id']})
    if not quotes:
        warnings.append('No verified sportsbook XPM quote matches the requested event, kicker and line; manual prices remain usable.')
    return quotes


def _markets(capture, target, cutoff, warnings):
    from kickedge.features.market import parlay_market_features

    matches = [row for row in capture['rows'] if isinstance(row, dict) and _event_matches(row, target)]
    if len(matches) != 1:
        warnings.append('General market event is missing or ambiguous; context unavailable.')
        return []
    event = matches[0]
    if not _updates_valid(event, capture):
        warnings.append('General market timestamps are inconsistent with capture; context excluded.')
        return []
    event_id = event.get('id') or event.get('canonical_event_id')
    if not event_id:
        return []
    identity = target | {'prediction_cutoff': cutoff.isoformat()}
    mapping = {event['home_team']: target['home_team'], event['away_team']: target['away_team']}
    results = []
    for book in event.get('bookmakers', []):
        if not isinstance(book, dict) or book.get('key') not in _SPORTSBOOKS:
            continue
        if not _updates_valid(book, capture) or any(
                not _updates_valid(market, capture) for market in book.get('markets', [])):
            continue
        result = parlay_market_features(identity, capture, event_id, book['key'], mapping)
        if result['current_usable']:
            result['training_eligible'] = False
            result['classification'] = 'current_context_only'
            results.append(result)
    return results


def collect_context(target: dict, player: dict, *, line: float | None, now: datetime,
                    no_market=False, no_weather=False, parlay_factory=None,
                    weather_factory=None, env_path='.env', clock=None) -> dict:
    """Collect optional evidence once per endpoint; failures never block inference.

    Factories receive timeout=10 (Parlay also env_path). ``now`` is request start;
    ``clock`` measures completion and defaults to the actual UTC clock. Tests may
    inject it, but live provider receipt timestamps are never overwritten.
    """
    clock = clock or (lambda: datetime.now(timezone.utc))
    start, kickoff = _instant(now), _instant(target['kickoff'])
    horizon = kickoff - timedelta(minutes=60)
    result = {'context': {'market': {'available': False, 'quotes': []},
                          'weather': {'available': False, 'values': {}, 'provenance': {}, 'reasons': []}},
              'prop_quotes': [], 'warnings': [], 'source_failures': [], 'provider_timestamps': {}}
    warnings = result['warnings']

    def cutoff():
        completed = _instant(clock())
        if completed < start:
            raise ValueError('Clock precedes collection start')
        return min(completed, horizon)

    def failure(provider):
        reason = 'Optional provider request or evidence validation failed; continuing without this context.'
        result['source_failures'].append({'provider': provider, 'critical': False, 'reason': reason})
        warnings.append(f'{provider}: {reason}')

    if start > horizon:
        warnings.append('Optional current context skipped: collection starts after the pregame prediction horizon.')
        return result
    if not no_market:
        try:
            if parlay_factory is None:
                from kickedge.providers.parlay import ParlayClient
                parlay_factory = ParlayClient
            client = parlay_factory(env_path=env_path, timeout=10)
        except Exception:
            failure('parlay')
        else:
            for endpoint, method in (('parlay_xpm', 'current_xpm'), ('parlay_markets', 'current_markets')):
                try:
                    capture = getattr(client, method)()
                    boundary = cutoff()
                    if not _capture_valid(capture, boundary):
                        raise ValueError('Unverified capture')
                    result['provider_timestamps'][endpoint] = capture['observed_at']
                    if method == 'current_xpm':
                        result['prop_quotes'] = _props(capture, target, player, line, warnings)
                    else:
                        quotes = _markets(capture, target, boundary, warnings)
                        result['context']['market'] = {'available': bool(quotes), 'quotes': quotes}
                    if any(capture.get('metadata', {}).get(key) for key in ('has_more', 'truncated', 'degraded')):
                        warnings.append('ParlayAPI capture is incomplete or degraded; board coverage is not guaranteed.')
                except Exception:
                    failure(endpoint)
    if not no_weather:
        try:
            from kickedge.providers.weather import OpenMeteoClient, weather_features

            roof = _text(target.get('roof'))
            roof = 'outdoors' if roof == 'outdoor' else roof
            latitude, longitude = _number(target.get('latitude')), _number(target.get('longitude'))
            # Venue metadata (kickedge/venues.json) when resolve_target supplied it.
            venue = dict(game_id=target['game_id'], roof_type=roof, latitude=latitude, longitude=longitude,
                         source=target.get('venue_source', 'nflverse/schedules'),
                         source_sha256=target.get('venue_source_sha256', target.get('schedule_sha256')),
                         observed_at=target.get('venue_observed_at', target.get('schedule_fetched_at')))
            evidence = None
            if roof in {'dome', 'closed'}:
                warnings.append('Indoor venue: outdoor weather is not a game condition.')
            elif roof not in {'open', 'outdoors'}:
                warnings.append('Venue roof exposure is unresolved; weather skipped.')
            elif not target.get('venue') or latitude is None or longitude is None or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                warnings.append('Venue coordinates are unresolved; weather skipped.')
            elif (kickoff.date() - start.date()).days >= 16:
                warnings.append('Weather forecast not yet available: Open-Meteo covers the next 16 days.')
            else:
                factory = weather_factory or OpenMeteoClient
                evidence = factory(timeout=10).forecast(latitude, longitude, target['kickoff'])
                evidence = dict(evidence, game_id=target['game_id'])
            weather = weather_features(target | {'prediction_cutoff': cutoff().isoformat()}, evidence, venue)
            weather['available'] = weather['current_usable']
            weather['training_eligible'] = False
            weather['venue_training_eligible'] = False
            weather['weather_training_eligible'] = False
            if evidence and weather['available']:
                result['provider_timestamps']['open_meteo'] = evidence['observed_at']
            result['context']['weather'] = weather
            if evidence and not weather['available']:
                warnings.append('Weather evidence could not be verified before the prediction horizon.')
        except Exception:
            failure('open_meteo')
    result['warnings'] = list(dict.fromkeys(warnings))
    return result
