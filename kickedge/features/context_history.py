"""Completed-game conversion choices and team sample sizes for Phase 3."""
from collections import defaultdict

from .kicker import instant
from .temporal import temporal_evidence_valid


TWO_POINT_NAMES = tuple(f'team_two_point_{metric}_{window}'
    for window in ('before','last_3','last_5') for metric in ('attempt_rate','attempts'))
SAMPLE_NAMES = tuple(f'{side}_has_{n}_prior_games' for side in ('team','opponent') for n in (3,5))
FEATURE_NAMES = TWO_POINT_NAMES + SAMPLE_NAMES


class ContextHistory:
    def __init__(self):
        self.history=defaultdict(list)
        self.observed=set()

    def observe(self, rows, source):
        if len(rows)!=2 or len({r['team'] for r in rows})!=2:
            raise ValueError('Expected two distinct context team-games')
        a,b=rows
        if (a['opponent'],b['opponent'])!=(b['team'],a['team']) or a['season']!=b['season'] or a['game_id']!=b['game_id']:
            raise ValueError('Invalid context opponents')
        for r in rows:
            if any(type(r[n]) is not int or r[n]<0 for n in ('two_pt_attempts','team_xpa')):
                raise ValueError('Invalid conversion count')
            if not r['coverage_ok']:
                raise ValueError('Incomplete conversion coverage')
            if (r['game_id'],r['team']) in self.observed:
                raise ValueError('Duplicate context team-game')
        for r in rows:
            self.observed.add((r['game_id'],r['team']))
            self.history[r['season'],r['team']].append({**r,
                'kickoff':source['actual_kickoff'],'last_event':source['last_event'],
                'available_at':source['available_at'],'event_completed':source['event_completed'],
                'temporal_class':source['temporal_class'],'source_sha256':source['sha256']})

    def histories(self, identity):
        cutoff=instant(identity['prediction_cutoff'])
        result={}
        for side in ('team','opponent'):
            h=sorted((r for r in self.history[identity['season'],identity[side]]
                if r['game_id']!=identity['game_id'] and instant(r['kickoff'])<cutoff
                and instant(r['available_at'])<=cutoff),key=lambda r:(instant(r['kickoff']),r['game_id']))
            if not all(temporal_evidence_valid(r,cutoff) for r in h):
                raise ValueError('Invalid context history temporal evidence')
            result[side]=h
        return result

    def build(self, identity):
        histories=self.histories(identity)
        result={}; reasons={}
        for size in (None,3,5):
            suffix='before' if size is None else f'last_{size}'
            h=histories['team'][-size:] if size else histories['team']
            complete=size is None or len(h)==size
            attempts=sum(r['two_pt_attempts'] for r in h) if complete else None
            denominator=sum(r['two_pt_attempts']+r['team_xpa'] for r in h) if complete else None
            result[f'team_two_point_attempts_{suffix}']=attempts
            result[f'team_two_point_attempt_rate_{suffix}']=attempts/denominator if denominator else None
            if not complete:
                reasons[f'team_two_point_attempts_{suffix}']='insufficient_window'
            if not denominator:
                reasons[f'team_two_point_attempt_rate_{suffix}']=('insufficient_window' if not complete
                    else 'no_prior_game' if not h else 'zero_conversion_attempts')
        for side,h in histories.items():
            for n in (3,5):
                result[f'{side}_has_{n}_prior_games']=len(h)>=n
        result['context_history_provenance']={side:{'team':identity[side],'history':h,
            'last_3_game_ids':[r['game_id'] for r in h[-3:]],'last_5_game_ids':[r['game_id'] for r in h[-5:]]}
            for side,h in histories.items()}
        result['context_history_provenance']['null_reasons']=reasons
        return result
