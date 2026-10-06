"""Model performance on tracked selections only (official pregame predictions).

Every figure uses the effective (latest) result and the probability the Brier score
already uses: the KickEdge probability of the selected side, conditional on no push
for integer lines, with pushes excluded. Single picks and multi legs stay separate;
the combined view is labelled because legs of one multi can be correlated. Nothing
here changes predictions, refits or calibrates the model.
"""
from __future__ import annotations

from kickedge.current.tracking import graded_pair, probability_summary

SMALL_SAMPLE = 20
PROBABILITY_BASIS = ('KickEdge probability of the selected side as tracked; for integer lines it is conditional '
                     'on no push. Pushes are excluded.')
LEGS_NOTE = 'Multi legs may be correlated.'
COMBINED_NOTE = 'Combined probability assumes independence.'
RANGES = (('<50%', 0., .5), ('50–60%', .5, .6), ('60–70%', .6, .7), ('70–80%', .7, .8), ('80–90%', .8, .9),
          ('90%+', .9, float('inf')))


def _row(source, selection, settlement, same_game=None):
    return {'source': source, 'side': selection['side'], 'line': selection['line'], 'season': selection.get('season'),
            'week': selection.get('week'), 'settled': settlement is not None,
            'push': bool(settlement) and settlement['result'] == 'PUSH', 'pair': graded_pair(selection, settlement),
            'same_game': same_game}


def selection_rows(singles, multis):
    """One row per tracked single pick and per multi leg, with its effective result."""
    rows = [_row('single', r['pick'], r['settlement']) for r in singles['open'] + singles['settled']]
    for record in multis['multis']:
        same_game = record['manifest']['same_game_correlation_warning']
        rows += [_row('multi_leg', leg['leg'], leg['settlement'], same_game) for leg in record['legs']]
    return rows


def summarize(rows):
    pairs = [r['pair'] for r in rows if r['pair']]
    return ({'tracked': len(rows), 'settled': sum(r['settled'] for r in rows), 'pushes': sum(r['push'] for r in rows)}
            | probability_summary(pairs) | {'small_sample': len(pairs) < SMALL_SAMPLE})


def _groups(rows, key, order, label):
    """Graded summaries per group, labelled by ``label(group key)``; groups without a graded selection are omitted."""
    groups = {}
    for r in rows:
        if r['pair']:
            groups.setdefault(key(r), []).append(r)
    return [label(name) | summarize(groups[name]) for name in sorted(groups, key=order)]


def calibration(rows):
    """Ten probability buckets [0,10%) … [90%,100%]; only buckets with graded selections."""
    return _groups(rows, lambda r: min(int(r['pair'][0] * 10), 9), lambda b: b,
                   lambda b: {'bucket': f'{10 * b}–{10 * b + 10}%', 'low': b / 10, 'high': (b + 1) / 10})


def by_range(rows):
    index = lambda r: next(i for i, (_, low, high) in enumerate(RANGES) if low <= r['pair'][0] < high)
    return _groups(rows, index, lambda i: i, lambda i: {'range': RANGES[i][0]})


def by_line(rows):
    return _groups(rows, lambda r: (r['side'], float(r['line'])), lambda k: (k[0] != 'over', k[1]),
                   lambda k: {'line': f'{k[0].title()} {k[1]:g}', 'side': k[0], 'line_value': k[1]})


def by_week(rows):
    return _groups(rows, lambda r: (r['season'] or 0, r['week'] or 0), lambda k: k,
                   lambda k: {'season': k[0], 'week': k[1]})


def section(rows):
    return summarize(rows) | {'calibration': calibration(rows), 'by_range': by_range(rows), 'by_line': by_line(rows),
                              'by_week': by_week(rows)}


def dashboard(singles, multis):
    """Performance of tracked selections: singles, multi legs, both (labelled) and whole multis."""
    rows = selection_rows(singles, multis)
    single_rows = [r for r in rows if r['source'] == 'single']
    leg_rows = [r for r in rows if r['source'] == 'multi_leg']
    multi_groups = multis['summary']['multis']
    return {'counts': {'singles_tracked': len(single_rows), 'singles_settled': sum(r['settled'] for r in single_rows),
                       'multi_legs_tracked': len(leg_rows), 'multi_legs_settled': sum(r['settled'] for r in leg_rows),
                       'multis_tracked': multis['summary']['tracked'],
                       'multis_settled': sum(g['settled'] for g in multi_groups.values()),
                       'unreadable': singles['summary']['unreadable'] + multis['summary']['unreadable']},
            'single': section(single_rows) | {'source': 'single'},
            'multi_legs': section(leg_rows) | {'source': 'multi_leg', 'note': LEGS_NOTE},
            'all_individual': section(rows) | {'source': 'single+multi_leg', 'note': LEGS_NOTE},
            'multis': {name: group | {'small_sample': group['settled'] < SMALL_SAMPLE} for name, group in multi_groups.items()},
            'combined_note': COMBINED_NOTE, 'probability_basis': PROBABILITY_BASIS, 'small_sample_threshold': SMALL_SAMPLE}
