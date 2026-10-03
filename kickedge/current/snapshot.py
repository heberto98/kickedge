"""Resolve explicit identities and reuse all three frozen historical builders."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re

from kickedge.features import FeatureContext, load_contract
from kickedge.features.context import GameContextBuilder, CALENDAR_CLASS, CALENDAR_POLICY
from kickedge.features.kicker import KickerFeatureBuilder, instant
from kickedge.features.team import TeamFeatureBuilder
from kickedge.features.temporal import temporal_evidence_valid
from kickedge.inference.contracts import FeatureSnapshot
from kickedge.modeling.dataset import predictor_columns
from kickedge.teams import normalize_team
from kickedge.venues import venue_context
from .catalog import upcoming_games


def timestamp(value):
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError('Timezone-aware timestamp required')
        return value.astimezone(timezone.utc)
    return instant(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def normal_name(value):
    return re.sub(r'[^a-z0-9]', '', str(value).casefold())


def _schedule_source(bundle):
    rows = [r for r in bundle['sources'] if r['dataset'] == 'schedules']
    if len(rows) != 1:
        raise ValueError('Exactly one schedule source required')
    return rows[0]


class GameNotFound(ValueError):
    """No analyzable game; carries upcoming games involving either team."""

    def __init__(self, message, suggestions=()):
        super().__init__(message)
        self.suggestions = list(suggestions)


def resolve_target(bundle, team, opponent, *, season, now, week=None, game_id=None, replay=False):
    """Match only explicit schedule identities; multiple upcoming meetings fail.

    Team input is normalized to canonical nflverse codes (LAR -> LA, JAC -> JAX).
    """
    now = timestamp(now)
    team, opponent = normalize_team(team), normalize_team(opponent)
    if team == opponent or season != bundle['season']:
        raise ValueError('Invalid target season or matchup')
    candidates = []
    for row in bundle['schedules']:
        if (row['season'] != season or {team, opponent} != {row['home_team'], row['away_team']}
                or row['game_type'] not in {'REG', 'WC', 'DIV', 'CON', 'SB'}
                or (week is not None and row['week'] != week)
                or (game_id is not None and row['game_id'] != game_id)):
            continue
        if not row.get('scheduled_kickoff'):
            raise ValueError('Target kickoff unresolved in schedule')
        if not replay and timestamp(row['scheduled_kickoff']) <= now:
            continue
        candidates.append(row)
    if not candidates:
        suggestions = [] if replay else [g for g in upcoming_games(bundle, now)
                                         if {team, opponent} & {g['home_team'], g['away_team']}][:8]
        raise GameNotFound('No matching future game; matchup invalid or game already started', suggestions)
    if len(candidates) != 1:
        raise ValueError('Target game ambiguous; provide week or game-id')
    row = candidates[0]
    source = _schedule_source(bundle)
    venue = venue_context(row)
    if venue:
        # Venue evidence = schedule assignment + static metadata: the later capture counts.
        venue['venue_observed_at'] = max(venue['venue_observed_at'], source['fetched_at'], key=timestamp)
    return {k: row.get(k) for k in ('game_id', 'season', 'week', 'game_type', 'home_team',
            'away_team', 'venue', 'roof', 'latitude', 'longitude', 'stadium_id')} | venue | {
        'kickoff': row['scheduled_kickoff'], 'scheduled_kickoff': row['scheduled_kickoff'],
        'team': team, 'opponent': opponent, 'is_home': team == row['home_team'],
        'schedule_sha256': source['sha256'], 'schedule_fetched_at': source['fetched_at']}


def resolve_kicker(bundle, kicker, target, *, cutoff):
    """Resolve the user-specified player. Prior team is never a current roster claim."""
    candidates = {}
    for row in bundle['players']:
        pid = row.get('kicker_id') or row.get('player_id') or row.get('gsis_id')
        name = row.get('kicker_name') or row.get('display_name') or row.get('name')
        if not pid or not name:
            continue
        if kicker == pid or normal_name(kicker) == normal_name(name):
            if row.get('position') not in (None, 'K', 'PK'):
                continue
            candidates[pid] = {'kicker_id': pid, 'kicker_name': name}
    # Only completed prior observations may supplement the identity directory.
    for game in bundle['games']:
        if game['game_id'] == target['game_id'] or game['season'] != target['season']:
            continue
        if not temporal_evidence_valid(game['source'], timestamp(cutoff)):
            continue
        for row in game['kickers']:
            pid, name = row['kicker_id'], row['kicker_name']
            if kicker == pid or normal_name(kicker) == normal_name(name):
                candidates.setdefault(pid, {'kicker_id': pid, 'kicker_name': name})
    if not candidates:
        raise ValueError('Kicker identity unresolved; provide an exact known name or stable ID')
    if len(candidates) != 1:
        raise ValueError('Kicker identity ambiguous; provide stable ID')
    return next(iter(candidates.values())) | {'team': target['team'],
        'current_team_verified': False, 'warnings': [
            'Kicker identity resolved; current team affiliation and participation are not verified']}


def build_snapshot(bundle, target, player, *, now, cutoff=None, replay=False):
    now = timestamp(now)
    scheduled = timestamp(target.get('scheduled_kickoff') or target['kickoff'])
    kickoff = timestamp(target['kickoff'])
    horizon = min(kickoff, scheduled) - timedelta(minutes=60)
    cutoff = timestamp(cutoff) if cutoff is not None else min(now, horizon)
    if cutoff > horizon or (not replay and (now >= kickoff or cutoff > now)):
        raise ValueError('Target started or cutoff violates the frozen pregame horizon')
    if target['season'] != bundle['season']:
        raise ValueError('Source season differs from target season')
    identity = {k: target[k] for k in ('game_id', 'season', 'week', 'game_type', 'team', 'opponent')}
    identity.update(kicker_id=player['kicker_id'], kicker_name=player['kicker_name'],
                    kickoff=kickoff.isoformat(), prediction_cutoff=cutoff.isoformat())
    warnings = list(player.get('warnings', []))
    source_quality = []
    for source in bundle['sources']:
        fetched = timestamp(source['fetched_at'])
        if not replay and fetched > now:
            raise ValueError('Source capture is after snapshot generation')
        age = (now-fetched).total_seconds()
        source_quality.append({'dataset': source['dataset'], 'fetched_at': fetched.isoformat(),
                               'age_seconds': age, 'stale': age > 6*3600})
        if age > 6*3600:
            warnings.append('Source cache older than six hours: '+source['dataset'])
    if not replay and timestamp(target['schedule_fetched_at']) > cutoff:
        raise ValueError('Schedule capture after feature cutoff; use an earlier verified capture')
    kicker_builder, team_builder, context_builder = KickerFeatureBuilder(), TeamFeatureBuilder(), GameContextBuilder()
    used, seen = [], set()
    for game in bundle['games']:
        # Check identity/clocks before accessing any outcomes, even their hashes.
        if game['season'] != target['season'] or game['game_id'] == target['game_id']:
            continue
        source = game['source']
        start = timestamp(source['actual_kickoff'])
        end = timestamp(source['last_event'])
        if start >= cutoff or end >= cutoff:
            continue
        if not source['event_completed']:
            raise ValueError('Historical event is not completed')
        if timestamp(source['available_at']) > cutoff:
            warnings.append('Prior event pending conservative release gate: '+game['game_id'])
            continue
        if not temporal_evidence_valid(source, cutoff):
            raise ValueError('Invalid historical temporal evidence')
        if game['game_id'] in seen:
            raise ValueError('Duplicate historical game')
        seen.add(game['game_id'])
        relevant = False
        for row in game['kickers']:
            if row['kicker_id'] != player['kicker_id']:
                continue
            if row['season'] != target['season'] or row['game_id'] != game['game_id']:
                raise ValueError('Kicker history identity mismatch')
            kicker_builder.observe(row | {'kickoff': source['actual_kickoff']}, row, source)
            relevant = True
        if {r['team'] for r in game['teams']} & {target['team'], target['opponent']}:
            for rows in (game['teams'], game['conversions']):
                if any(r['season'] != target['season'] or r['game_id'] != game['game_id'] for r in rows):
                    raise ValueError('Team history identity mismatch')
            team_builder.observe(game['teams'], source)
            context_builder.history.observe(game['conversions'], source)
            relevant = True
        if relevant:
            used.append({'game_id': game['game_id'], 'actual_kickoff': source['actual_kickoff'],
                         'last_event': source['last_event'], 'available_at': source['available_at'],
                         'source_sha256': source['sha256']})
    calendar = {k: target[k] for k in ('game_id', 'season', 'week', 'game_type', 'home_team', 'away_team')}
    calendar.update(scheduled_kickoff=scheduled.isoformat(), source_sha256=target['schedule_sha256'],
                    temporal_class=CALENDAR_CLASS, calendar_policy=CALENDAR_POLICY)
    kicker_values = kicker_builder.build(FeatureContext(identity['game_id'], identity['team'], identity['opponent'],
                                          identity['kicker_id'], kickoff, cutoff, identity['season']))
    team_values = team_builder.build(identity)
    context_values = context_builder.build(identity, calendar)
    values = kicker_values | team_values | context_values
    columns = predictor_columns()
    features = {name: values[name] for name in columns}
    if len(features) != 82 or list(features) != columns:
        raise ValueError('Current feature schema/order mismatch')
    provenance = {'generated_at': now.isoformat(), 'target_kickoff': kickoff.isoformat(),
                  'cutoff': cutoff.isoformat(), 'season': target['season'], 'mode': 'historical_replay' if replay else 'current',
                  'sources': bundle['sources'], 'feature_schema_version': load_contract()['schema_version'],
                  'history_games': sorted(used, key=lambda r: (r['actual_kickoff'], r['game_id'])),
                  'latest_game_used': max(used, key=lambda r: (r['actual_kickoff'], r['game_id']), default=None),
                  'kicker_history': kicker_values['feature_provenance'],
                  'team_history': team_values['team_feature_provenance'],
                  'context_history': context_values['context_history_provenance'],
                  'calendar': context_values['calendar_provenance']}
    # Rich provenance stays outside the strict 7A envelope; the digest binds it.
    payload = {'features': features, 'metadata': {'kicker': player['kicker_name'], 'kicker_id': player['kicker_id'],
               'team': target['team'], 'opponent': target['opponent'], 'game_id': target['game_id'],
               'kickoff': kickoff.isoformat(), 'cutoff': cutoff.isoformat()},
               'provenance': {'source': 'nflverse current event pipeline', 'source_sha256': digest(provenance),
                              'kind': 'HISTORICAL REPLAY / TEST FIXTURE' if replay else 'current'}}
    validated = FeatureSnapshot.from_mapping(payload)
    payload['features'] = validated.features
    if features['kicker_low_sample_flag']:
        warnings.append('Short kicker history; original counts, NULLs and rolling requirements preserved')
    if features['offense_games_before'] < 5 or features['defense_games_before'] < 5:
        warnings.append('Short team/opponent history; incomplete rolling windows remain NULL')
    quality = {'target_game_verified': True, 'kicker_identity_verified': True,
               'kicker_current_team_verified': player.get('current_team_verified', False),
               'feature_schema_verified': True, 'feature_count': 82, 'missing_feature_count': 0,
               'null_feature_count': len(validated.nullable_features), 'source_data_freshness': source_quality,
               'latest_game_used': provenance['latest_game_used'], 'warnings': warnings}
    return {'snapshot': payload, 'provenance': provenance, 'data_quality': quality}
