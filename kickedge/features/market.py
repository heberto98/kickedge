"""Market expectations with explicit team perspective and snapshot eligibility."""
import math
from .kicker import instant

FEATURE_NAMES=('game_spread','game_total','moneyline_team','moneyline_opponent',
    'implied_team_strength','implied_game_environment','implied_team_total','implied_opponent_total')


def number(value):
    return float(value) if type(value) in (int,float) and math.isfinite(value) else None


def probability(value):
    v=number(value)
    if v is None or abs(v)<100:return None
    return 100/(100+v) if v>0 else -v/(100-v)


def schedule_market(row,source_sha256):
    """Project only market fields; nflverse positive spread means home favored."""
    spread=number(row.get('spread_line'))
    return {k:row.get(k) for k in ('game_id','home_team','away_team','home_moneyline','away_moneyline')} | {
        'home_spread':-spread if spread is not None else None,'game_total':row.get('total_line'),
        'source':'nflverse/schedules','source_sha256':source_sha256,'kind':'retrospective_closing',
        'bookmaker_type':'sportsbook','observed_at':None,'last_update':None}


def parlay_market_features(identity,capture,event_id,bookmaker,team_mapping):
    """Bind one captured event/book with caller-verified provider-name/team mapping.

    No fuzzy identity matching or consensus across books. Require matching kickoff;
    the caller must reconcile the provider event to the target before using this.
    """
    missing=lambda:market_features(identity,None)
    try:
        events=[r for r in capture['rows'] if event_id in (r.get('id'),r.get('canonical_event_id'))]
        if not event_id or len(events)!=1:return missing()
        event=events[0];home=event['home_team'];away=event['away_team']
        if instant(event['commence_time'])!=instant(identity['kickoff']):return missing()
        books=[b for b in event['bookmakers'] if b['key']==bookmaker]
        if len(books)!=1:return missing()
        book=books[0]
        q={'game_id':identity['game_id'],'home_team':team_mapping[home],'away_team':team_mapping[away],
            'source':capture['source'],'source_sha256':capture['source_sha256'],'kind':'quote',
            'observed_at':capture['observed_at'],'bookmaker':bookmaker,
            'bookmaker_type':'sportsbook' if bookmaker in ('fliff','draftkings','fanduel','caesars','bovada','pinnacle') else 'unknown'}
        updates=[book['last_update']] if book.get('last_update') else []
        for name in ('h2h','spreads','totals'):
            markets=[m for m in book['markets'] if m.get('key')==name]
            if len(markets)!=1:continue
            m=markets[0];outcomes=m['outcomes']
            if m.get('last_update'):updates.append(m['last_update'])
            if len(outcomes)!=2:continue
            by_name={o['name']:o for o in outcomes}
            if name=='h2h' and set(by_name)=={home,away}:
                q.update(home_moneyline=by_name[home].get('price'),away_moneyline=by_name[away].get('price'))
            elif name=='spreads' and set(by_name)=={home,away}:
                a=number(by_name[home].get('point'));b=number(by_name[away].get('point'))
                if a is not None and b is not None and abs(a+b)<1e-9:q['home_spread']=a
            elif name=='totals' and set(by_name)=={'Over','Under'}:
                a=number(by_name['Over'].get('point'));b=number(by_name['Under'].get('point'))
                if a is not None and a==b:q['game_total']=a
        if updates:q['last_update']=max(updates,key=instant)
        result=market_features(identity,q)
        result['provenance']['provider_event_id']=event_id
        result['provenance']['provider_home_team']=home
        result['provenance']['provider_away_team']=away
        return result
    except (KeyError,ValueError,TypeError,AttributeError):
        return missing()


def market_features(identity,evidence):
    values=dict.fromkeys(FEATURE_NAMES)
    result={'values':values,'training_eligible':False,'current_usable':False,
        'classification':'unavailable','reasons':[],'provenance':{}}
    cutoff=instant(identity['prediction_cutoff'])
    if cutoff>=instant(identity['kickoff']):raise ValueError('Invalid market cutoff')
    if not evidence:
        result['reasons']=['missing_market'];return result
    e=evidence
    result['provenance']={k:e.get(k) for k in ('source','source_sha256','kind','bookmaker','bookmaker_type','observed_at','last_update')}
    if (e.get('game_id')!=identity['game_id'] or
            {identity['team'],identity['opponent']}!={e.get('home_team'),e.get('away_team')} or
            identity['team']==identity['opponent']):
        result['reasons']=['market_identity_mismatch'];return result
    clocks={}
    try:
        for n in ('observed_at','last_update','published_at'):
            if e.get(n):
                clocks[n]=instant(e[n])
                if clocks[n]>cutoff:
                    result['reasons']=['market_after_cutoff'];return result
        if clocks.get('observed_at') and any(t>clocks['observed_at'] for n,t in clocks.items() if n!='observed_at'):
            result['reasons']=['inconsistent_market_timestamps'];return result
    except (ValueError,TypeError):
        result['reasons']=['invalid_market_timestamps'];return result
    home=identity['team']==e['home_team']
    spread=number(e.get('home_spread'));total=number(e.get('game_total'))
    if total is not None and total<0:total=None
    values['game_spread']=spread if home or spread is None else -spread
    values['game_total']=values['implied_game_environment']=total
    for target,source in [('moneyline_team','home_moneyline' if home else 'away_moneyline'),
            ('moneyline_opponent','away_moneyline' if home else 'home_moneyline')]:
        v=number(e.get(source));values[target]=v if probability(v) is not None else None
    p=probability(values['moneyline_team']);q=probability(values['moneyline_opponent'])
    if p is not None and q is not None and e.get('bookmaker_type')=='sportsbook':
        values['implied_team_strength']=p/(p+q)
    if spread is not None and total is not None and total>=abs(spread):
        values['implied_team_total']=(total-values['game_spread'])/2
        values['implied_opponent_total']=(total+values['game_spread'])/2
    source=e.get('source');digest=e.get('source_sha256')
    source_valid=(isinstance(source,str) and bool(source.strip()) and isinstance(digest,str)
        and len(digest)==64 and all(c in '0123456789abcdefABCDEF' for c in digest))
    verified=bool(e.get('kind')=='quote' and source_valid
        and clocks.get('observed_at') and e.get('bookmaker_type')=='sportsbook')
    present=any(v is not None for v in values.values())
    result.update(training_eligible=verified and present,current_usable=verified and present,
        classification='training-historical' if verified else 'experimental',
        reasons=[] if verified else ['unverified_market_availability_or_price_type'])
    return result
