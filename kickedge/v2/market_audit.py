"""Post-freeze market audit: raw implied vs no-vig vs KickEdge on paired XPM quotes.

Descriptive only. It explains why KickEdge looked "always below" the market during
manual use and never feeds model selection: the V2 decision was frozen and the
2026 forward evaluation scored before this audit ran.

The ParlayAPI closing archive carries no quote timestamp or kickoff time and
contains in-game prices, so it is not pregame evidence: no outcome scoring is done
on it, and a ladder screen (no-vig P(over) must fall as the line rises within one
book and kicker-game) flags snapshots that cannot all be pregame.
"""
from __future__ import annotations

from datetime import datetime, timezone
import glob
import json
from pathlib import Path
import unicodedata
from zoneinfo import ZoneInfo

import numpy as np

from kickedge.current.sources import load_current_sources
from kickedge.inference.odds import implied_probability, no_vig
from kickedge.modeling.distributions import line_probabilities

CLOSING = Path('data/v2/market/closing_odds_2026.json')
FORWARD = Path('data/v2/forward/result.json')
OUTPUT = Path('data/v2/market/audit.json')
DFS_BOOKS = {'sleeper', 'prizepicks', 'underdog', 'betr', 'pick6'}   # flat-payout prices, not sportsbook odds
MAX_DATE_GAP_DAYS = 3


def quote_probabilities(over_odds, under_odds, line, mean):
    """Raw implied, no-vig and Poisson KickEdge probabilities for one paired quote."""
    pair = no_vig(over_odds, under_odds)
    model = line_probabilities([mean], line)
    return {'raw': {'over': implied_probability(over_odds), 'under': implied_probability(under_odds)},
            'no_vig': {'over': pair['over'], 'under': pair['under']}, 'overround': pair['overround'],
            'kickedge': {'over': float(model['over'][0]), 'under': float(model['under'][0])}}


def distribution(values):
    values = np.asarray(values, dtype=float)
    if not values.size:
        return {'count': 0}
    q = np.quantile(values, [.1, .25, .5, .75, .9])
    return {'count': int(values.size), 'mean_pp': 100 * float(values.mean()), 'median_pp': 100 * float(q[2]),
            'p10_pp': 100 * float(q[0]), 'p25_pp': 100 * float(q[1]), 'p75_pp': 100 * float(q[3]),
            'p90_pp': 100 * float(q[4]), 'share_kickedge_below': float((values < 0).mean())}


def compare(records):
    """KickEdge minus raw implied and minus no-vig, by side, plus overround."""
    out = {'quotes': len(records), 'overround': distribution([r['overround'] for r in records])}
    for side in ('over', 'under'):
        out[side] = {basis: distribution([r['kickedge'][side] - r[basis][side] for r in records])
                     for basis in ('raw', 'no_vig')}
        out[side]['mean_probability'] = {basis: float(np.mean([r[basis][side] for r in records])) if records else None
                                         for basis in ('raw', 'no_vig', 'kickedge')}
    return out


def _name(value):
    text = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()
    return ''.join(ch for ch in text if ch.isalnum())


def ladder_consistent(records):
    """Mark quotes whose book ladder for the kicker-game is monotone in no-vig P(over)."""
    ladders = {}
    for r in records:
        ladders.setdefault((r['game_id'], r['kicker_id'], r['bookmaker']), []).append(r)
    for ladder in ladders.values():
        ladder.sort(key=lambda r: r['line'])
        ok = all(a['no_vig']['over'] > b['no_vig']['over'] for a, b in zip(ladder, ladder[1:]))
        for r in ladder:
            r['ladder_consistent'] = ok
    return records


def match_closing(quotes, forward_rows, games):
    """Attach each forward kicker-game to its closing quotes by player name and nearest game date.

    One quote per (kicker-game, book, line): the nearest listed date wins and the
    remaining duplicates are counted, never averaged.
    """
    eastern = ZoneInfo('America/New_York')
    index, records, dropped = {}, [], 0
    for row in forward_rows:
        game = games[row['game_id']]
        day = datetime.fromisoformat(game['scheduled_kickoff']).astimezone(eastern).date()
        index.setdefault(_name(game['names'][row['kicker_id']]), []).append((day, row))
    best = {}
    for q in quotes:
        if q.get('over_odds') is None or q.get('under_odds') is None:
            continue
        candidates = [(abs((datetime.fromisoformat(q['game_date']).date() - day).days), row)
                      for day, row in index.get(_name(q['player']), [])]
        candidates = [c for c in candidates if c[0] <= MAX_DATE_GAP_DAYS]
        if not candidates:
            continue
        gap, row = min(candidates, key=lambda c: c[0])
        key = (row['game_id'], row['kicker_id'], q['bookmaker'], float(q['line']))
        if key in best:
            dropped += 1
            if best[key][0] <= gap:
                continue
        best[key] = (gap, q, row)
    for (game_id, kicker_id, book, line), (gap, q, row) in sorted(best.items()):
        record = quote_probabilities(float(q['over_odds']), float(q['under_odds']), line, row['V1'])
        records.append(record | {'game_id': game_id, 'kicker_id': kicker_id, 'bookmaker': book, 'line': line,
                                 'date_gap_days': gap, 'over_odds': q['over_odds'], 'under_odds': q['under_odds']})
    return ladder_consistent(records), dropped


def stored_analyses(root):
    """Saved single analyses: distinct quotes with raw implied, no-vig (if paired) and model side probability."""
    seen = {}
    for path in glob.glob(str(Path(root)/'data/current/analyses/*/analysis.json')):
        r = json.loads(Path(path).read_text(encoding='utf-8'))
        m, p = r['market'], r['prop']
        key = (r['player']['kicker_id'], r['game']['game_id'], p['line'], p['side'],
               m.get('american_odds', m.get('decimal_odds')), m.get('over_odds'), m.get('under_odds'))
        seen.setdefault(key, {'kicker': r['player']['kicker_name'], 'game_id': r['game']['game_id'], 'line': p['line'],
                              'side': p['side'], 'raw': m['implied_probability'], 'no_vig': m.get('no_vig_probability'),
                              'kickedge': p['model_side_probability'], 'repeats': 0})['repeats'] += 1
    rows = list(seen.values())
    return {'distinct_quotes': len(rows), 'saved_analyses': sum(r['repeats'] for r in rows),
            'paired_distinct_quotes': sum(r['no_vig'] is not None for r in rows),
            'kickedge_minus_raw': distribution([r['kickedge'] - r['raw'] for r in rows]),
            'kickedge_minus_no_vig': distribution([r['kickedge'] - r['no_vig'] for r in rows if r['no_vig'] is not None]),
            'quotes': rows}


def run_audit(root=Path('.'), *, now=None):
    root = Path(root)
    forward = json.loads((root/FORWARD).read_text(encoding='utf-8'))      # the stored single reveal; never re-scored
    closing = json.loads((root/CLOSING).read_text(encoding='utf-8'))
    bundle = load_current_sources(root, 2026, refresh=False, now=now or datetime.now(timezone.utc))
    games = {s['game_id']: {'scheduled_kickoff': s['scheduled_kickoff'], 'names': {}} for s in bundle['schedules']}
    for game in bundle['games']:
        for k in game['kickers']:
            games[game['game_id']]['names'][k['kicker_id']] = k['kicker_name']
    records, dropped = match_closing(closing['rows'], forward['row_predictions'], games)
    by_book = {}
    for r in records:
        by_book.setdefault(r['bookmaker'], []).append(r)
    sportsbook = [r for r in records if r['bookmaker'] not in DFS_BOOKS]
    screened = [r for r in sportsbook if r['ladder_consistent']]
    result = {'generated_at': (now or datetime.now(timezone.utc)).isoformat(),
              'closing_capture': {k: closing[k] for k in ('observed_at', 'source', 'params', 'source_sha256')} | {
                  'rows': len(closing['rows']), 'rows_without_commence_time': sum(not q.get('commence_time') for q in closing['rows']),
                  'quote_timestamp_field': any('last_update' in q for q in closing['rows'])},
              'forward_rows': len(forward['row_predictions']), 'kickedge_model': 'V1 (champion), frozen artifact lambdas from the forward reveal',
              'matched_quotes': len(records), 'duplicate_quotes_dropped': dropped,
              'matched_kicker_games': len({(r['game_id'], r['kicker_id']) for r in records}),
              'sportsbook': compare(sportsbook), 'sportsbook_ladder_consistent': compare(screened),
              'by_book': {b: compare(v) for b, v in sorted(by_book.items())},
              'by_line_sportsbook_ladder_consistent': {str(l): compare([r for r in screened if r['line'] == l])
                                                       for l in sorted({r['line'] for r in screened})},
              'stored_analyses': stored_analyses(root), 'records': records}
    (root/OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    (root/OUTPUT).write_text(json.dumps(result, indent=1, allow_nan=False) + '\n', encoding='utf-8')
    return result
