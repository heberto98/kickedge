"""Phase 3: explicitly authorized calendar approximation plus prior event data."""
from collections import defaultdict
import heapq

from .context_history import ContextHistory, FEATURE_NAMES as HISTORY_NAMES
from .kicker import instant, key


CALENDAR_CLASS='historical_schedule_context'
CALENDAR_POLICY='phase3-calendar-v1'
CALENDAR_NAMES=('is_home','is_away','season','week','game_type','team_days_rest','opponent_days_rest',
    'team_short_week_flag','opponent_short_week_flag','team_long_rest_flag','opponent_long_rest_flag')
FEATURE_NAMES=CALENDAR_NAMES+HISTORY_NAMES


def calendar_field_approved(field, contract):
    """A closed whitelist: calendar authorization cannot waive PIT elsewhere."""
    return (field['name'] in CALENDAR_NAMES and field.get('temporal_class')==CALENDAR_CLASS
        and field.get('calendar_policy')==CALENDAR_POLICY
        and contract.get('calendar_context_policy',{}).get('policy_id')==CALENDAR_POLICY
        and field.get('group') in ('game_context','identity')
        and field.get('historical_training_approved') is True
        and field.get('publication_timestamp_required') is False)


class GameContextBuilder:
    def __init__(self):
        self.history=ContextHistory()

    def build(self, identity, calendar):
        if (calendar.get('temporal_class')!=CALENDAR_CLASS or calendar.get('calendar_policy')!=CALENDAR_POLICY
                or not calendar.get('source_sha256')):
            raise ValueError('Unapproved calendar temporal approximation')
        if (calendar['game_id']!=identity['game_id'] or calendar['season']!=identity['season']
                or {identity['team'],identity['opponent']}!={calendar['home_team'],calendar['away_team']}
                or identity['team']==identity['opponent']):
            raise ValueError('Invalid calendar matchup')
        for name in ('week','game_type'):
            if name in identity and identity[name]!=calendar[name]:
                raise ValueError('Calendar identity mismatch: '+name)
        cutoff=instant(identity['prediction_cutoff'])
        if cutoff>=instant(identity['kickoff']):
            raise ValueError('Invalid context cutoff')
        reference=calendar.get('scheduled_kickoff') or identity['kickoff']
        if instant(reference)<=cutoff:
            raise ValueError('Calendar kickoff must follow cutoff')
        result=self.history.build(identity)
        result.update({n:calendar[n] for n in ('season','week','game_type')})
        result.update(is_home=identity['team']==calendar['home_team'],is_away=identity['team']==calendar['away_team'])
        rest_sources={}
        for side in ('team','opponent'):
            h=result['context_history_provenance'][side]['history']
            previous=h[-1] if h else None
            days=(instant(reference)-instant(previous['kickoff'])).total_seconds()/86400 if previous else None
            result[f'{side}_days_rest']=days
            result[f'{side}_short_week_flag']=days<6 if days is not None else None
            result[f'{side}_long_rest_flag']=days>8 if days is not None else None
            rest_sources[side]={'previous_game_id':previous['game_id'] if previous else None,
                'previous_actual_kickoff':previous['kickoff'] if previous else None}
        result['calendar_provenance']={**calendar,
            'rest_reference':'scheduled_kickoff' if calendar.get('scheduled_kickoff') else 'historical_kickoff_fallback',
            'rest_reference_kickoff':reference,'rest_sources':rest_sources,
            'historical_approximation':True,'point_in_time_verified':False}
        return result


def simulate(identities, oracle, calendar, sink, stop_at=None):
    groups=defaultdict(list)
    if len({key(r) for r in identities})!=len(identities):
        raise ValueError('Duplicate context identity')
    for r in identities:
        groups[r['game_id']].append(r)
    if set(groups)!=set(oracle.manifest) or set(groups)!=set(calendar):
        raise ValueError('Context game populations differ')
    builder=GameContextBuilder()
    pending=[];frozen=set();seen=[];result=[]
    for game in sorted(groups,key=lambda g:(instant(groups[g][0]['prediction_cutoff']),g)):
        current=sorted(groups[game],key=key)
        cutoff=current[0]['prediction_cutoff']
        if len({(r['kickoff'],r['prediction_cutoff'],r['season']) for r in current})!=1:
            raise ValueError('Inconsistent context timing')
        while pending and pending[0][0]<=instant(cutoff):
            _,prior=heapq.heappop(pending)
            rows=oracle.reveal(prior,cutoff,frozen)
            exemplar=groups[prior][0]
            if any(r['game_id']!=prior or r['season']!=exemplar['season'] for r in rows):
                raise ValueError('Context outcome/identity mismatch')
            if {r['team'] for r in rows}!={exemplar['team'],exemplar['opponent']}:
                raise ValueError('Context outcome opponents mismatch')
            builder.history.observe(rows,oracle.manifest[prior])
            sink({'kind':'reveal','game_id':prior,'decision_time':cutoff,
                'available_at':oracle.manifest[prior]['available_at'],'source_sha256':oracle.manifest[prior]['sha256']})
        fixed=[]
        for r in current:
            values=builder.build(r,calendar[game])
            unavailable=[h['game_id'] for h in seen if h['season']==r['season']
                and {h['team'],h['opponent']} & {r['team'],r['opponent']}
                and instant(h['kickoff'])<instant(cutoff)
                and instant(oracle.manifest[h['game_id']]['available_at'])>instant(cutoff)]
            values['context_history_provenance']['unavailable_prior_game_ids']=unavailable
            fixed.append({**r,**values,'context_history_unavailable_before_cutoff':bool(unavailable)})
        sink({'kind':'freeze','game_id':game,'prediction_cutoff':cutoff,'rows':fixed})
        result.extend(fixed);frozen.add(game);seen.append(current[0])
        heapq.heappush(pending,(instant(oracle.manifest[game]['available_at']),game))
        if game==stop_at:
            break
    return result
