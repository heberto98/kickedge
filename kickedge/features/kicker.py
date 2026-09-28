"""Kicker-only history, frozen before any target-game outcome can be read."""
from collections import defaultdict
from datetime import datetime, timezone
import heapq
import json

from kickedge.io import sha256_file
from . import FeatureContext
from .temporal import temporal_evidence_valid


FEATURE_NAMES = (
    'kicker_games_before', 'kicker_xpa_before', 'kicker_xpm_before',
    'kicker_xp_conversion_rate_before', 'kicker_xpm_per_game_before', 'kicker_xpa_per_game_before',
    'kicker_xpa_last_3', 'kicker_xpm_last_3', 'kicker_xp_conversion_last_3', 'kicker_xpm_per_game_last_3',
    'kicker_xpa_last_5', 'kicker_xpm_last_5', 'kicker_xp_conversion_last_5', 'kicker_xpm_per_game_last_5',
    'days_since_last_game', 'previous_game_xpa', 'previous_game_xpm',
    'kicker_has_prior_game', 'kicker_has_3_prior_games', 'kicker_has_5_prior_games', 'kicker_low_sample_flag')
IDENTITY_FIELDS = ('game_id', 'team', 'opponent', 'kicker_id', 'kicker_name', 'season', 'week',
                   'game_type', 'kickoff', 'prediction_cutoff')


def instant(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.utcoffset() is None:
        raise ValueError('Explicit timezone required')
    return dt.astimezone(timezone.utc)


def key(row):
    return row['game_id'], row['team'], row['kicker_id']


class KickerFeatureBuilder:
    """History keys are (season, kicker_id), deliberately not team."""

    def __init__(self):
        self.history = defaultdict(list)
        self.observed = set()

    def observe(self, identity, outcome, source):
        if key(identity) != key(outcome) or key(identity) in self.observed:
            raise ValueError('Mismatched or duplicate historical observation')
        valid = outcome['statistical_label_usable']
        xpa, xpm = outcome['xpa'], outcome['xpm']
        if valid and not (type(xpa) is int and type(xpm) is int and 0 <= xpm <= xpa):
            raise ValueError('Invalid usable XPA/XPM counts')
        self.observed.add(key(identity))
        self.history[identity['season'], identity['kicker_id']].append({
            'game_id': identity['game_id'], 'team': identity['team'], 'kickoff': identity['kickoff'],
            'available_at': source['available_at'], 'availability_verified': source['availability_verified'],
            'source_sha256': source['sha256'], 'xpa': xpa if valid else None,
            'xpm': xpm if valid else None, 'usable': valid,
            'temporal_class': source.get('temporal_class'), 'last_event': source.get('last_event'),
            'event_completed': source.get('event_completed', False)})

    def build(self, context: FeatureContext):
        if context.season is None:
            raise ValueError('Season required for season-to-date features')
        history = sorted([h for h in self.history[context.season, context.kicker_id]
                          if h['game_id'] != context.game_id and instant(h['kickoff']) < context.kickoff
                          and instant(h['available_at']) <= context.cutoff],
                         key=lambda h: (instant(h['kickoff']), h['game_id'], h['team']))
        n = len(history)
        valid = all(h['usable'] for h in history)
        xpa = sum(h['xpa'] for h in history) if valid else None
        xpm = sum(h['xpm'] for h in history) if valid else None
        last = history[-1] if history else None
        row = dict(kicker_games_before=n, kicker_xpa_before=xpa, kicker_xpm_before=xpm,
            kicker_xp_conversion_rate_before=xpm/xpa if xpa else None,
            kicker_xpm_per_game_before=xpm/n if n and valid else None,
            kicker_xpa_per_game_before=xpa/n if n and valid else None,
            previous_game_xpa=last['xpa'] if last else None, previous_game_xpm=last['xpm'] if last else None,
            days_since_last_game=(context.cutoff-instant(last['kickoff'])).total_seconds()/86400 if last else None,
            kicker_has_prior_game=n > 0, kicker_has_3_prior_games=n >= 3,
            kicker_has_5_prior_games=n >= 5, kicker_low_sample_flag=n < 5)
        for size in (3, 5):
            window = history[-size:]
            complete = len(window) == size and all(h['usable'] for h in window)
            a = sum(h['xpa'] for h in window) if complete else None
            m = sum(h['xpm'] for h in window) if complete else None
            row.update({f'kicker_xpa_last_{size}': a, f'kicker_xpm_last_{size}': m,
                        f'kicker_xp_conversion_last_{size}': m/a if a else None,
                        f'kicker_xpm_per_game_last_{size}': m/size if complete else None})
        reasons = {}
        for name in FEATURE_NAMES:
            if row[name] is not None:
                continue
            size = 3 if name.endswith('_last_3') else 5 if name.endswith('_last_5') else None
            contributing = history[-size:] if size else history[-1:] if name.startswith('previous_game_') else history
            reasons[name] = ('no_prior_game' if not n else
                             'insufficient_window' if size and n < size else
                             'unusable_prior_label' if any(not h['usable'] for h in contributing) else
                             'zero_attempt_denominator')
        row['feature_provenance'] = {
            'history_scope': 'same_season_global_kicker', 'history': history,
            'last_3_game_ids': [h['game_id'] for h in history[-3:]],
            'last_5_game_ids': [h['game_id'] for h in history[-5:]],
            'unusable_prior_game_ids': [h['game_id'] for h in history if not h['usable']],
            'max_available_at': max((h['available_at'] for h in history), key=instant, default=None),
            'null_reasons': reasons}
        return row


class LabelOracle:
    def __init__(self, directory, manifest):
        self.directory, self.manifest = directory, manifest

    def reveal(self, game_id, now, frozen):
        source = self.manifest[game_id]
        if game_id not in frozen or instant(now) < instant(source['available_at']):
            raise ValueError('Outcome access before freeze/availability')
        if source.get('temporal_class') and not temporal_evidence_valid(source, instant(now)):
            raise ValueError('Outcome temporal evidence is invalid')
        path = self.directory / source['filename']
        if sha256_file(path) != source['sha256']:
            raise ValueError('Outcome source changed')
        return json.loads(path.read_text(encoding='utf-8'))


def simulate(identities, oracle, sink, stop_at=None):
    """The only outcome access is a guarded reveal of previously frozen games.

    The target-game oracle file is not even hashed until its later reveal.
    sink must persist each freeze before this function advances. Outcomes still
    pending after the final freeze are left unread; target attachment is separate.
    """
    if len({key(r) for r in identities}) != len(identities):
        raise ValueError('Duplicate kicker-game identity')
    groups = defaultdict(list)
    for r in identities:
        groups[r['game_id']].append({k: r[k] for k in IDENTITY_FIELDS})
    ordered = sorted(groups, key=lambda g: (instant(groups[g][0]['kickoff']), g))
    builder, pending, frozen, result, seen = KickerFeatureBuilder(), [], set(), [], []
    for game in ordered:
        current = sorted(groups[game], key=key)
        cutoff = current[0]['prediction_cutoff']
        if len({(r['kickoff'], r['prediction_cutoff']) for r in current}) != 1:
            raise ValueError('Inconsistent game timing')
        while pending and pending[0][0] <= instant(cutoff):
            _, prior = heapq.heappop(pending)
            outcomes = {key(r): r for r in oracle.reveal(prior, cutoff, frozen)}
            if set(outcomes) != {key(r) for r in groups[prior]}:
                raise ValueError('Outcome/identity population mismatch')
            for identity in groups[prior]:
                builder.observe(identity, outcomes[key(identity)], oracle.manifest[prior])
            sink({'kind': 'reveal', 'game_id': prior, 'decision_time': cutoff,
                  'available_at': oracle.manifest[prior]['available_at'],
                  'source_sha256': oracle.manifest[prior]['sha256']})
        fixed = []
        for r in current:
            context = FeatureContext(r['game_id'], r['team'], r['opponent'], r['kicker_id'],
                                     instant(r['kickoff']), instant(cutoff), r['season'])
            features = builder.build(context)
            unavailable = [h['game_id'] for h in seen if h['season'] == r['season']
                           and h['kicker_id'] == r['kicker_id'] and instant(h['kickoff']) < context.kickoff
                           and instant(oracle.manifest[h['game_id']]['available_at']) > context.cutoff]
            row = {**r, **features, 'history_unavailable_before_cutoff': bool(unavailable),
                   'feature_sources_verified': all(h['availability_verified'] for h in features['feature_provenance']['history'])}
            row['feature_provenance']['unavailable_prior_game_ids'] = unavailable
            fixed.append(row)
        sink({'kind': 'freeze', 'game_id': game, 'prediction_cutoff': cutoff, 'rows': fixed})
        result.extend(fixed)
        frozen.add(game)
        seen.extend(current)
        heapq.heappush(pending, (instant(oracle.manifest[game]['available_at']), game))
        if stop_at == game:
            break
    return result
