"""Current sources -> original builders -> verified Phase 7A prediction."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

from kickedge.inference.engine import analyze
from kickedge.inference.odds import analyze_prop
from kickedge.io import write_json
from kickedge.teams import team_display
from .catalog import kicker_affiliation
from .snapshot import resolve_target, resolve_kicker, build_snapshot, timestamp, digest
from .sources import load_current_sources
from .optional import collect_context


def current_season(now):
    """NFL season containing ``now``: January/February belong to the prior season."""
    return now.year-(now.month<3)


def select_quote(quotes, line, side, odds, over_odds, under_odds, bookmaker=None):
    """Manual quotes are authoritative; an automatic quote must be unique."""
    if odds is not None:
        if line is None:
            raise ValueError('Manual odds require a line')
        analyze_prop(1., line, side, odds, over_odds, under_odds)
        return {'line':line,'side':side,'odds':odds,'over_odds':over_odds,'under_odds':under_odds,
                'source':'manual user quote','timestamp':None,'availability':'manual'}
    if over_odds is not None or under_odds is not None:
        raise ValueError('Paired manual prices require selected-side odds')
    candidates=[q for q in quotes if (line is None or q['line']==line)
                and (bookmaker is None or q['bookmaker']==bookmaker.casefold())
                and q.get(side+'_price') is not None]
    if not candidates:
        raise ValueError('No usable sportsbook prop; provide manual line, side and odds')
    if len(candidates)!=1:
        raise ValueError('Sportsbook prop ambiguous; select bookmaker/line or provide manual prices')
    q=candidates[0]
    over,under=q.get('over_price'),q.get('under_price')
    if over is None or under is None: over=under=None
    analyze_prop(1.,q['line'],side,q[side+'_price'],over,under)
    return {'line':q['line'],'side':side,'odds':q[side+'_price'],'over_odds':over,'under_odds':under,
            'source':q['bookmaker'],'timestamp':q['observed_at'],'availability':'parlay_current'}


def analyze_current_prop(kicker, team, opponent, line=None, side='over', odds=None, *,
                         season=None, week=None, game_id=None, over_odds=None, under_odds=None,
                         bookmaker=None, root=Path('.'), refresh_data=False,
                         no_market=False, no_weather=False, clock=None,
                         source_loader=None, context_collector=None, output_dir=None):
    """Construct a current pregame snapshot without fitting or downloading models."""
    clock=clock or (lambda:datetime.now(timezone.utc))
    root=Path(root).resolve()
    started=timestamp(clock())
    if side not in ('over','under'):
        raise ValueError('Side must be over or under')
    if odds is not None:
        select_quote([],line,side,odds,over_odds,under_odds)
    elif line is not None:
        analyze_prop(1.,line,side,100)
    if season is None:
        season=current_season(started)
    loader=source_loader or load_current_sources
    bundle=loader(root,season,refresh=refresh_data,now=started,clock=clock)
    now=timestamp(clock())
    target=resolve_target(bundle,team,opponent,season=season,week=week,game_id=game_id,now=now)
    cutoff=min(now,timestamp(target['kickoff'])-timedelta(minutes=60))
    player=resolve_kicker(bundle,kicker,target,cutoff=cutoff)
    # Roster evidence is data quality only; a clear opponent listing stops the analysis.
    affiliation=kicker_affiliation(bundle,player['kicker_id'],target)
    if affiliation['conflict']:
        raise ValueError(affiliation['message'])
    player=player|{'current_team_verified':affiliation['verified'],'roster':affiliation,
                   'warnings':[] if affiliation['verified'] else [affiliation['message']]}
    built=build_snapshot(bundle,target,player,now=now,cutoff=cutoff)
    collector=context_collector or collect_context
    optional=collector(target,player,line=line,now=now,no_market=no_market,no_weather=no_weather,
                       env_path=root/'.env',clock=clock)
    quote=select_quote(optional['prop_quotes'],line,side,odds,over_odds,under_odds,bookmaker)
    result=analyze(built['snapshot'],quote['line'],quote['side'],quote['odds'],
                   over_odds=quote['over_odds'],under_odds=quote['under_odds'],
                   source=quote['source'],timestamp=quote['timestamp'],model_dir=root/'data/models/phase5')
    finished=timestamp(clock())
    if finished>=timestamp(target['kickoff']):
        raise ValueError('Target kickoff passed during collection; pregame analysis unavailable')
    result['schema_version']='7b.1'
    result['game'].update({k:target[k] for k in ('home_team','away_team','venue','roof','season','week','game_type','is_home')})
    result['game'].update(venue_city=target.get('venue_city'),venue_roof_type=target.get('venue_roof_type'))
    result['teams']={code:team_display(code) for code in (target['home_team'],target['away_team'])}
    result['player']=player
    result['features']=built['snapshot']['features']
    result['context']=optional['context']
    result['provenance']={'features':built['provenance'],'provider_timestamps':optional['provider_timestamps'],
                          'model_version':result['model']['version'],'analysis_generated_at':finished.isoformat(),
                          'feature_snapshot_sha256':digest(built['snapshot'])}
    warnings=result['data_quality']['warnings']+built['data_quality']['warnings']+optional['warnings']
    result['data_quality'].update(built['data_quality'])
    result['data_quality'].update(market_availability=optional['context']['market']['available'],
        weather_availability=optional['context']['weather']['available'],prop_availability=quote['availability'],
        source_failures=optional['source_failures'],warnings=list(dict.fromkeys(warnings)),
        historical_event_chronology_verified=True,
        pregame_availability_verified=True,market_requested=not no_market,weather_requested=not no_weather)
    # A deterministic content key retains every distinct snapshot/result without overwrite.
    directory=Path(output_dir) if output_dir is not None else root/'data/current/analyses'
    directory=directory/digest(result)
    write_json(directory/'snapshot.json',built['snapshot'])
    write_json(directory/'provenance.json',result['provenance'])
    write_json(directory/'analysis.json',result)
    json.dumps(result,allow_nan=False)
    return result
