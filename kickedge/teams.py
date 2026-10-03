"""Central NFL team metadata and input aliases.

Canonical codes are the nflverse codes produced by ``transform.TEAM_MACRO``
(LA, LAC, LV, JAX, WAS, ...). Every user-facing entry point normalizes through
``normalize_team``; providers use ``team_code`` for tolerant lookups.
"""
import re
import unicodedata

# Canonical nflverse code -> (city, nickname).
TEAMS = {
    'ARI': ('Arizona', 'Cardinals'), 'ATL': ('Atlanta', 'Falcons'),
    'BAL': ('Baltimore', 'Ravens'), 'BUF': ('Buffalo', 'Bills'),
    'CAR': ('Carolina', 'Panthers'), 'CHI': ('Chicago', 'Bears'),
    'CIN': ('Cincinnati', 'Bengals'), 'CLE': ('Cleveland', 'Browns'),
    'DAL': ('Dallas', 'Cowboys'), 'DEN': ('Denver', 'Broncos'),
    'DET': ('Detroit', 'Lions'), 'GB': ('Green Bay', 'Packers'),
    'HOU': ('Houston', 'Texans'), 'IND': ('Indianapolis', 'Colts'),
    'JAX': ('Jacksonville', 'Jaguars'), 'KC': ('Kansas City', 'Chiefs'),
    'LA': ('Los Angeles', 'Rams'), 'LAC': ('Los Angeles', 'Chargers'),
    'LV': ('Las Vegas', 'Raiders'), 'MIA': ('Miami', 'Dolphins'),
    'MIN': ('Minnesota', 'Vikings'), 'NE': ('New England', 'Patriots'),
    'NO': ('New Orleans', 'Saints'), 'NYG': ('New York', 'Giants'),
    'NYJ': ('New York', 'Jets'), 'PHI': ('Philadelphia', 'Eagles'),
    'PIT': ('Pittsburgh', 'Steelers'), 'SEA': ('Seattle', 'Seahawks'),
    'SF': ('San Francisco', '49ers'), 'TB': ('Tampa Bay', 'Buccaneers'),
    'TEN': ('Tennessee', 'Titans'), 'WAS': ('Washington', 'Commanders'),
}

# Other abbreviations in common use (PFR, ESPN, older nflverse, relocations).
_CODE_ALIASES = {
    'LAR': 'LA', 'STL': 'LA', 'JAC': 'JAX', 'WSH': 'WAS', 'OAK': 'LV', 'LVR': 'LV',
    'SD': 'LAC', 'SDG': 'LAC', 'ARZ': 'ARI', 'BLT': 'BAL', 'CLV': 'CLE', 'HST': 'HOU',
    'GNB': 'GB', 'KAN': 'KC', 'NWE': 'NE', 'NOR': 'NO', 'SFO': 'SF', 'TAM': 'TB',
}
_NAME_ALIASES = {
    'LA Rams': 'LA', 'St. Louis Rams': 'LA', 'LA Chargers': 'LAC', 'San Diego Chargers': 'LAC',
    'Oakland Raiders': 'LV', 'NY Giants': 'NYG', 'NY Jets': 'NYJ', 'Niners': 'SF',
    'Washington Football Team': 'WAS', 'Washington Redskins': 'WAS', 'Football Team': 'WAS',
    'Tampa': 'TB', 'Bucs': 'TB', 'Jags': 'JAX', 'Pats': 'NE',
}
# Shared city names: never guessed.
_AMBIGUOUS = {'los angeles': ('LA', 'LAC'), 'new york': ('NYG', 'NYJ'), 'ny': ('NYG', 'NYJ')}


def _key(value):
    text = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', ' ', text.casefold()).strip()


def _build():
    aliases = {}
    for code, (city, nickname) in TEAMS.items():
        for name in (code, nickname, f'{city} {nickname}'):
            aliases[_key(name)] = code
        if _key(city) not in _AMBIGUOUS:
            aliases[_key(city)] = code
    for name, code in (_CODE_ALIASES | _NAME_ALIASES).items():
        aliases[_key(name)] = code
    return aliases


_ALIASES = _build()


def team_code(value):
    """Canonical code for a known code/name/alias; None if unknown or ambiguous."""
    if not isinstance(value, str):
        return None
    return _ALIASES.get(_key(value))


def normalize_team(value):
    """Canonical nflverse code for user input.

    Unknown 2-4 letter codes pass through upper-cased (they simply match no
    game); ambiguous or unknown names raise ValueError instead of guessing.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Unknown team: a team name or abbreviation is required')
    key = _key(value)
    if key in _AMBIGUOUS:
        options = ' or '.join(f'{TEAMS[c][1]} ({c})' for c in _AMBIGUOUS[key])
        raise ValueError(f'Ambiguous team name; use {options}')
    code = _ALIASES.get(key)
    if code:
        return code
    raw = value.strip().upper()
    if re.fullmatch(r'[A-Z]{2,4}', raw):
        return raw
    raise ValueError('Unknown team name or abbreviation')


def search_terms(code):
    """Words a user may type for a team: code, names and alias abbreviations."""
    city, nickname = TEAMS.get(code, (None, code))
    names = [code, nickname] + ([city, f'{city} {nickname}'] if city else [])
    return names + [alias for alias, target in (_CODE_ALIASES | _NAME_ALIASES).items() if target == code]


def team_display(code):
    """Display names for a canonical code; unknown codes display as themselves."""
    if code in TEAMS:
        city, nickname = TEAMS[code]
        return {'code': code, 'name': f'{city} {nickname}', 'nickname': nickname, 'city': city}
    return {'code': code, 'name': code, 'nickname': code, 'city': None}
