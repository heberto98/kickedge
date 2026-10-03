"""Build current pregame features and analyze a user-specified XPM prop."""
import json
import sys
from pathlib import Path

from kickedge.inference.cli import SafeParser, american, human
from .engine import analyze_current_prop


def main(argv=None):
    parser=SafeParser(description=__doc__)
    for field in ('kicker','team','opponent','side'):
        parser.add_argument('--'+field,required=True)
    for field in ('line','odds','over-odds','under-odds','game-id','bookmaker'):
        parser.add_argument('--'+field)
    parser.add_argument('--season',type=int)
    parser.add_argument('--week',type=int)
    parser.add_argument('--root',type=Path,default=Path('.'))
    for field in ('json','refresh-data','no-weather','no-market'):
        parser.add_argument('--'+field,action='store_true')
    try:
        args=parser.parse_args(argv)
        try:
            line=float(args.line) if args.line is not None else None
        except ValueError:
            raise ValueError('Line must be a nonnegative integer or half-integer') from None
        prices={name:american(getattr(args,name)) if getattr(args,name) is not None else None
                for name in ('odds','over_odds','under_odds')}
        result=analyze_current_prop(args.kicker,args.team,args.opponent,line,args.side,prices.pop('odds'),
            **prices,season=args.season,week=args.week,game_id=args.game_id,bookmaker=args.bookmaker,
            root=args.root,refresh_data=args.refresh_data,no_weather=args.no_weather,no_market=args.no_market)
        if args.json:
            print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
        else:
            print(human(result))
            print('Game: '+result['game']['game_id']+'; kickoff '+result['game']['kickoff'])
            print('Current context: market='+str(result['data_quality']['market_availability'])+
                  '; weather='+str(result['data_quality']['weather_availability']))
            print('Feature cutoff: '+result['provenance']['features']['cutoff'])
            print('Latest prior game: '+str(result['data_quality']['latest_game_used']))
    except (ValueError,OSError) as exc:
        message=str(exc) if isinstance(exc,ValueError) else 'Required local input could not be accessed'
        print('Current analysis error: '+message,file=sys.stderr)
        raise SystemExit(2) from None


if __name__=='__main__':
    main()
