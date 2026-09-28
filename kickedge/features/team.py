"""Pregame team offense and opponent defense; only revealed completed games."""
from collections import defaultdict
import heapq
import math

from .kicker import instant, key
from .temporal import temporal_evidence_valid


# Numerator / denominator. None denotes the number of prior games.
METRICS = {
    'points_per_game': ('points', None),
    'touchdowns_per_game': ('touchdowns', None),
    'drives_per_game': ('drives', None),
    'td_per_drive': ('touchdowns', 'drives'),
    'red_zone_td_rate': ('red_zone_touchdowns', 'red_zone_drives'),
    'epa_per_play': ('epa_sum', 'epa_plays'),
    'success_rate': ('successes', 'epa_plays'),
}
DEFENSE_NAMES = dict(zip(METRICS, (
    'points_allowed_per_game', 'touchdowns_allowed_per_game', 'drives_faced_per_game',
    'td_allowed_per_drive', 'red_zone_td_rate_allowed', 'epa_allowed_per_play', 'success_rate_allowed')))


def specifications():
    for side in ('offense', 'defense'):
        yield f'{side}_games_before', side, 'games', None
        for size in (None, 3, 5):
            suffix = 'before' if size is None else f'last_{size}'
            for metric in METRICS:
                if size and metric == 'drives_per_game':
                    continue
                name = metric if side == 'offense' else DEFENSE_NAMES[metric]
                yield f'{side}_{name}_{suffix}', side, metric, size


FEATURE_NAMES = tuple(s[0] for s in specifications())
STAT_NAMES = ('points', 'touchdowns', 'drives', 'red_zone_drives', 'red_zone_touchdowns',
              'epa_sum', 'epa_plays', 'successes')


class TeamFeatureBuilder:
    def __init__(self):
        self.offense = defaultdict(list)
        self.defense = defaultdict(list)
        self.observed = set()

    def observe(self, rows, source):
        if len(rows) != 2 or len({r['team'] for r in rows}) != 2:
            raise ValueError('Expected two distinct team-games')
        a, b = rows
        if (a['opponent'], b['opponent']) != (b['team'], a['team']) or a['season'] != b['season'] or a['game_id'] != b['game_id']:
            raise ValueError('Invalid team-game opponents')
        for r in rows:
            k = (r['game_id'], r['team'])
            if k in self.observed:
                raise ValueError('Duplicate team-game')
            for name in STAT_NAMES:
                v = r[name]
                if v is not None and (type(v) not in (int, float) or not math.isfinite(v) or (name != 'epa_sum' and v < 0)):
                    raise ValueError('Invalid team statistic: '+name)
            self.observed.add(k)
            entry = {**r, 'kickoff': source['actual_kickoff'], 'last_event': source['last_event'],
                'available_at': source['available_at'], 'event_completed': source['event_completed'],
                'temporal_class': source['temporal_class'], 'source_sha256': source['sha256']}
            self.offense[r['season'], r['team']].append(entry)
            self.defense[r['season'], r['opponent']].append(entry)

    def build(self, identity):
        cutoff = instant(identity['prediction_cutoff'])
        histories = {}
        for side, store, team in [('offense', self.offense, identity['team']), ('defense', self.defense, identity['opponent'])]:
            histories[side] = sorted((h for h in store[identity['season'], team]
                if h['game_id'] != identity['game_id'] and instant(h['kickoff']) < cutoff
                and instant(h['available_at']) <= cutoff), key=lambda h:(instant(h['kickoff']), h['game_id']))
            if not all(temporal_evidence_valid(h, cutoff) for h in histories[side]):
                raise ValueError('Invalid team history temporal evidence')
        result, reasons = {}, {}
        for name, side, metric, size in specifications():
            history = histories[side]
            window = history[-size:] if size else history
            if metric == 'games':
                result[name] = len(history)
                continue
            num, den = METRICS[metric]
            reason = ('no_prior_game' if not history else 'insufficient_window' if size and len(window) < size else None)
            if not reason and any(h[num] is None or (den and h[den] is None) for h in window):
                reason = 'missing_source_metric'
            denominator = sum(h[den] for h in window) if den and not reason else len(window)
            if not reason and not denominator:
                reason = 'zero_denominator'
            result[name] = None if reason else sum(h[num] for h in window)/denominator
            if reason:
                reasons[name] = reason
        result['team_feature_provenance'] = {side: {
            'team': identity['team'] if side == 'offense' else identity['opponent'],
            'history': h, 'last_3_game_ids': [r['game_id'] for r in h[-3:]],
            'last_5_game_ids': [r['game_id'] for r in h[-5:]]} for side,h in histories.items()}
        result['team_feature_provenance']['null_reasons'] = reasons
        return result


def simulate(identities, oracle, sink, stop_at=None):
    """Freeze all observations of G before releasing its per-game file later."""
    groups = defaultdict(list)
    if len({key(r) for r in identities}) != len(identities):
        raise ValueError('Duplicate kicker-game identity')
    for r in identities:
        groups[r['game_id']].append(r)
    if set(groups) != set(oracle.manifest):
        raise ValueError('Team history population differs from identity games')
    builder, pending, frozen, result, seen = TeamFeatureBuilder(), [], set(), [], []
    for game in sorted(groups, key=lambda g:(instant(groups[g][0]['kickoff']),g)):
        current = sorted(groups[game], key=key)
        cutoff = current[0]['prediction_cutoff']
        if len({(r['kickoff'],r['prediction_cutoff'],r['season']) for r in current}) != 1:
            raise ValueError('Inconsistent game timing')
        while pending and pending[0][0] <= instant(cutoff):
            _, prior = heapq.heappop(pending)
            outcomes = oracle.reveal(prior, cutoff, frozen)
            exemplar = groups[prior][0]
            if any(r['game_id'] != prior or r['season'] != exemplar['season'] for r in outcomes):
                raise ValueError('Team outcome/identity mismatch')
            if {r['team'] for r in outcomes} != {exemplar['team'],exemplar['opponent']}:
                raise ValueError('Team outcome/identity opponent mismatch')
            builder.observe(outcomes, oracle.manifest[prior])
            sink({'kind':'reveal','game_id':prior,'decision_time':cutoff,
                  'available_at':oracle.manifest[prior]['available_at'],'source_sha256':oracle.manifest[prior]['sha256']})
        fixed=[]
        for r in current:
            features=builder.build(r)
            unavailable=[h['game_id'] for h in seen if h['season']==r['season']
                and {h['team'],h['opponent']} & {r['team'],r['opponent']}
                and instant(h['kickoff']) < instant(cutoff)
                and instant(oracle.manifest[h['game_id']]['available_at']) > instant(cutoff)]
            features['team_feature_provenance']['unavailable_prior_game_ids']=unavailable
            fixed.append({**r,**features,'team_history_unavailable_before_cutoff':bool(unavailable)})
        sink({'kind':'freeze','game_id':game,'prediction_cutoff':cutoff,'rows':fixed})
        result.extend(fixed)
        frozen.add(game)
        seen.append(current[0])
        heapq.heappush(pending,(instant(oracle.manifest[game]['available_at']),game))
        if game == stop_at:
            break
    return result
