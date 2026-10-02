"""Offline CLI for an explicitly materialized snapshot. No dotenv or network."""
import argparse
import json
import re
import sys

from .contracts import read_snapshot
from .engine import analyze


class SafeParser(argparse.ArgumentParser):
    def error(self,message):
        raise ValueError('Invalid CLI arguments; use --help for accepted fields')


def american(text):
    if not isinstance(text,str) or re.fullmatch(r'[+-]?\d+',text) is None:
        raise ValueError('American odds must be an unambiguous signed integer')
    return int(text)


def human(result):
    p,m,a=result['prop'],result['market'],result['analysis']
    lines=['DEMO / TEST FIXTURE — not a current prediction' if result['data_quality']['demo'] else 'KickEdge snapshot analysis',
           f"{result['game']['kicker']} | {result['game']['team']} vs {result['game']['opponent']}",
           f"Model: {result['model']['version']}; frozen 2016–2024",
           f"Expected XPM: {result['prediction']['expected_xpm']:.6f}",
           f"{p['side'].upper()} {p['line']:g} at {m['american_odds']:+g}",
           f"P(Over)={p['p_over']:.6f}; P(Under)={p['p_under']:.6f}; P(Push)={p['p_push']:.6f}",
           f"Price basis: {p['price_probability_basis']}; conditional probability={p['model_probability_conditional']:.6f}",
           f"Market implied={m['implied_probability']:.6f}; no-vig={m['no_vig_probability']}",
           f"Raw edge={a['edge_raw_pp']:+.4f} pp; no-vig edge={a['edge_novig_pp']}",
           f"Fair American odds={a['fair_odds']['american']}; EV per unit={a['expected_value_per_unit']:+.6f}",
           'Distribution 0..12: '+', '.join(f'{v:.6f}' for v in result['prediction']['distribution']['probabilities']),
           f"Tail P(XPM>12)={result['prediction']['distribution']['tail_probability']:.8g}",
           *['Warning: '+w for w in result['data_quality']['warnings']]]
    return '\n'.join(lines)


def main(argv=None):
    parser=SafeParser(description=__doc__)
    parser.add_argument('--features',required=True)
    parser.add_argument('--line',required=True)
    parser.add_argument('--side',required=True)
    parser.add_argument('--odds',required=True)
    parser.add_argument('--over-odds')
    parser.add_argument('--under-odds')
    parser.add_argument('--source')
    parser.add_argument('--timestamp')
    parser.add_argument('--model-dir',default='data/models/phase5')
    for field in ['kicker','team','opponent','game-id','event-id','kicker-id']:
        parser.add_argument('--'+field)
    parser.add_argument('--json',action='store_true')
    try:
        args=parser.parse_args(argv)
        try:
            line=float(args.line)
        except ValueError:
            raise ValueError('Prop line must be a nonnegative integer or half-integer') from None
        odds=american(args.odds)
        over=american(args.over_odds) if args.over_odds is not None else None
        under=american(args.under_odds) if args.under_odds is not None else None
        from .odds import analyze_prop
        analyze_prop(1.,line,args.side,odds,over,under)
        snapshot=read_snapshot(args.features)
        overrides={k:getattr(args,k) for k in ['kicker','team','opponent','game_id','event_id','kicker_id'] if getattr(args,k) is not None}
        result=analyze(snapshot,line,args.side,odds,over_odds=over,under_odds=under,
                       source=args.source,timestamp=args.timestamp,model_dir=args.model_dir,metadata_overrides=overrides)
        print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False) if args.json else human(result))
    except (ValueError,OSError) as exc:
        # Known validators only expose safe field names, never raw JSON/credentials.
        message=str(exc) if isinstance(exc,ValueError) else 'Unable to read a required local inference file'
        print('Inference error: '+message,file=sys.stderr)
        raise SystemExit(2) from None


if __name__=='__main__':
    main()
