"""Versioned NFL venue metadata: schedule venue name -> coordinates and roof.

Matching is by normalized venue name and aliases only. nflverse stadium ids are
kept as cross-checks: they are not reliable for neutral-site games (a London
game can carry the home team's stadium id). Unknown names resolve to None;
coordinates are never guessed.
"""
from functools import lru_cache
import hashlib
from importlib.resources import files
import json
import re
import unicodedata

SOURCE = 'kickedge/venues.json'


def _key(value):
    text = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode()
    text = text.casefold().replace('&', ' and ')
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


@lru_cache(maxsize=1)
def _catalog():
    raw = files('kickedge').joinpath('venues.json').read_bytes()
    doc = json.loads(raw)
    names = {}
    for venue in doc['venues']:
        for name in [venue['name'], *venue['aliases']]:
            key = _key(name)
            if names.get(key, venue['slug']) != venue['slug']:
                raise ValueError('Venue alias maps to two venues: ' + name)
            names[key] = venue['slug']
    venues = {v['slug']: v for v in doc['venues']}
    return doc, venues, names, hashlib.sha256(raw).hexdigest()


def resolve_venue(name, stadium_id=None):
    """Metadata for a schedule venue name, or None when it is not known."""
    if not isinstance(name, str) or not name.strip():
        return None
    doc, venues, names, digest = _catalog()
    slug = names.get(_key(name))
    if slug is None:
        return None
    venue = dict(venues[slug])
    venue['stadium_id_consistent'] = stadium_id is None or stadium_id in venue['stadium_ids']
    venue['source'] = SOURCE
    venue['source_sha256'] = digest
    venue['verified_at'] = doc['verified_at']
    return venue


def game_roof(venue, schedule_roof):
    """Game-day roof: physical type wins; retractables use the schedule's state.

    Returns 'outdoors', 'dome', 'open', 'closed' or 'retractable' (state unknown).
    """
    physical = venue['roof']
    if physical in ('outdoors', 'dome'):
        return physical
    state = schedule_roof.strip().lower() if isinstance(schedule_roof, str) else ''
    if state in ('open', 'outdoors'):
        return 'open'
    if state in ('closed', 'dome'):
        return 'closed'
    return 'retractable'


def venue_context(row):
    """Target fields for a schedule row: canonical venue, coordinates and roof.

    Returns {} when the venue name is unknown or the schedule already supplies
    coordinates, leaving the target exactly as the schedule gave it.
    """
    if row.get('latitude') is not None and row.get('longitude') is not None:
        return {}
    venue = resolve_venue(row.get('venue') or row.get('stadium'), row.get('stadium_id'))
    if venue is None:
        return {}
    return {'schedule_venue': row.get('venue') or row.get('stadium'), 'schedule_roof': row.get('roof'),
            'venue': venue['name'], 'venue_city': venue['city'],
            'latitude': venue['latitude'], 'longitude': venue['longitude'],
            'roof': game_roof(venue, row.get('roof')), 'venue_roof_type': venue['roof'],
            'venue_source': venue['source'], 'venue_source_sha256': venue['source_sha256'],
            'venue_observed_at': venue['verified_at'],
            'venue_stadium_id_consistent': venue['stadium_id_consistent']}
