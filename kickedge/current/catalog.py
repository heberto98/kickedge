"""Read-only views over a current bundle: upcoming games, kicker candidates and
roster affiliation. Nothing here enters the 82-feature snapshot."""
from datetime import datetime, timezone

from kickedge.features.kicker import instant
from kickedge.teams import search_terms, team_display
from kickedge.venues import venue_context

GAME_TYPES = ('REG', 'WC', 'DIV', 'CON', 'SB')
ROSTER_LABELS = {'ACT': 'Active roster', 'DEV': 'Practice squad', 'RES': 'Reserve/injured list',
                 'CUT': 'Released', 'PUP': 'PUP list', 'SUS': 'Suspended', 'RSN': 'Reserve/non-football injury',
                 'EXE': 'Exempt list'}


def _utc(value):
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError('Timezone-aware timestamp required')
        return value.astimezone(timezone.utc)
    return instant(value)


def game_summary(row):
    home, away = team_display(row['home_team']), team_display(row['away_team'])
    venue = venue_context(row)
    return {'game_id': row['game_id'], 'season': row['season'], 'week': row['week'],
            'game_type': row['game_type'], 'kickoff': row['scheduled_kickoff'],
            'home_team': home['code'], 'away_team': away['code'], 'home': home, 'away': away,
            'display_name': f"{away['nickname']} @ {home['nickname']}",
            'full_name': f"{away['name']} @ {home['name']}",
            'venue': venue.get('venue') or row.get('venue'), 'venue_city': venue.get('venue_city'),
            'roof': venue.get('roof') or row.get('roof'),
            'search': ' '.join([*search_terms(home['code']), *search_terms(away['code']), f"week {row['week']}",
                                row['game_id'], venue.get('venue') or row.get('venue') or '']).lower()}


def upcoming_games(bundle, now):
    """Analyzable games: target season, known kickoff strictly after ``now``.

    Mirrors resolve_target's own future-game rule, in kickoff order.
    """
    now = _utc(now)
    games = [game_summary(row) for row in bundle['schedules']
             if row['season'] == bundle['season'] and row['game_type'] in GAME_TYPES
             and row.get('scheduled_kickoff') and _utc(row['scheduled_kickoff']) > now]
    return sorted(games, key=lambda g: (_utc(g['kickoff']), g['game_id']))


def _players(bundle):
    return {row.get('kicker_id') or row.get('player_id'): row for row in bundle['players']}


def roster_label(status):
    return ROSTER_LABELS.get(status, f'Roster status {status}' if status else 'Roster status unknown')


def kicker_affiliation(bundle, kicker_id, target):
    """Current-team evidence from nflverse player data (latest_team/status).

    verified is True (target team, active roster, this season), False (evidence
    against), or None (no roster data). conflict marks an active-roster listing
    on the opponent: the requested pairing contradicts the source.
    """
    season, team, opponent = target['season'], target['team'], target['opponent']
    row = _players(bundle).get(kicker_id) or {}
    latest, status, last = row.get('latest_team'), row.get('roster_status'), row.get('last_season')
    name = row.get('display_name') or kicker_id
    result = {'verified': None, 'conflict': False, 'latest_team': latest, 'roster_status': status,
              'last_season': last, 'source': 'nflverse players (latest_team, status)'}
    if not latest or last is None:
        return result | {'message': 'Kicker identity is verified from NFL history, but current team '
                                    'affiliation could not be independently confirmed.'}
    if last != season:
        return result | {'verified': False, 'message': f'nflverse player data has no {season} roster entry for '
                         f'{name} (last: {latest}, {last}); current team affiliation not confirmed.'}
    if latest == team and status == 'ACT':
        return result | {'verified': True, 'message': 'Current team affiliation verified.'}
    if latest == team:
        return result | {'verified': False, 'message': f'{name} is listed on {team} but not on the active roster '
                         f'({roster_label(status)}).'}
    if latest == opponent and status == 'ACT':
        return result | {'verified': False, 'conflict': True, 'message':
                         f'Kicker roster conflict: nflverse lists {name} on the {opponent} active roster, '
                         f'the opponent in this game. Select the kicker for {team}.'}
    return result | {'verified': False, 'message': f'nflverse lists {name} on {latest} ({roster_label(status)}), '
                     f'not {team}; check the kicker for this game.'}


def kicker_candidates(bundle, game, now):
    """Kickers for both teams of a game: active/practice-squad roster entries
    plus anyone who kicked for the team this season. Never substitutes."""
    now = _utc(now)
    season, players = bundle['season'], _players(bundle)
    teams = {game['home_team']: {}, game['away_team']: {}}
    for pid, row in players.items():
        if (row.get('position') in ('K', 'PK') and row.get('latest_team') in teams
                and row.get('last_season') == season and row.get('roster_status') in ('ACT', 'DEV')):
            teams[row['latest_team']][pid] = {'kicker_id': pid, 'kicker_name': row.get('display_name') or pid,
                                              'season_games': 0, 'season_xpm': 0, 'season_xpa': 0, 'last_week': None}
    for event in bundle['games']:
        if event['season'] != season or _utc(event['source']['actual_kickoff']) >= now:
            continue
        for row in event['kickers']:
            if row['team'] not in teams:
                continue
            entry = teams[row['team']].setdefault(row['kicker_id'], {
                'kicker_id': row['kicker_id'], 'kicker_name': row['kicker_name'],
                'season_games': 0, 'season_xpm': 0, 'season_xpa': 0, 'last_week': None})
            entry['season_games'] += 1
            entry['season_xpm'] += row.get('xpm') or 0
            entry['season_xpa'] += row.get('xpa') or 0
            entry['last_week'] = max(entry['last_week'] or 0, row.get('week') or 0) or None
    result = []
    for code, entries in teams.items():
        kickers = []
        for entry in entries.values():
            target = {'season': season, 'team': code, 'opponent': next(t for t in teams if t != code)}
            affiliation = kicker_affiliation(bundle, entry['kicker_id'], target)
            kickers.append(entry | {'team': code, 'roster_verified': affiliation['verified'],
                                    'roster_status': affiliation['roster_status'],
                                    'roster_label': roster_label(affiliation['roster_status'])
                                    if affiliation['latest_team'] == code else
                                    (f"Listed on {affiliation['latest_team']}" if affiliation['latest_team'] else
                                     'Roster status unknown')})
        rank = {True: 0, None: 1, False: 2}
        kickers.sort(key=lambda k: (rank[k['roster_verified']], -k['season_games'], k['kicker_name']))
        result.append(team_display(code) | {'kickers': kickers})
    return result
