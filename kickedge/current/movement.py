"""Prediction movement and line comparison from stored analyses.

Movement lists, in time order, every saved analysis of the same selection (game,
kicker, side, line): model movement follows the pregame snapshot and price movement
only the decimal odds the user entered. The snapshot diff names model inputs whose
values changed; it describes data and never attributes a probability change to them.

Line comparison reuses the analysis' frozen Poisson mean (its expected XPM) with the
engine's own line probabilities: nothing is re-run and the analysed line reproduces
the stored probabilities exactly.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from kickedge.current.tracking import prediction_fields
from kickedge.inference.odds import fair_decimal_odds
from kickedge.modeling.distributions import line_probabilities

ANALYSIS = 'analysis.json'
LINES = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5)
NOTE = ('Movement shows how saved analyses of this selection changed over time. Input changes are listed as data '
        'only; they are not an explanation of the probability change.')


def selection_key(fields):
    return fields['game_id'], fields['kicker_id'], fields['side'], float(fields['line'])


def _stored(directory):
    """(analysis id, kind, analysis) of every readable single analysis and multi leg."""
    directory = Path(directory)
    for kind, folder in (('single', directory), ('multi_leg', directory/'legs')):
        if not folder.is_dir():
            continue
        for child in folder.iterdir():
            path = child/ANALYSIS
            if len(child.name) == 64 and path.is_file():
                try:
                    yield child.name, kind, json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    continue


def history(directory, key):
    """Every saved analysis of the selection, oldest first."""
    entries = []
    for analysis_id, kind, analysis in _stored(directory):
        try:
            fields = prediction_fields(analysis)
        except (KeyError, TypeError, ValueError):
            continue
        if selection_key(fields) != key:
            continue
        entries.append({'analysis_id': analysis_id, 'kind': kind, 'generated_at': fields['analysis_generated_at'],
                        'probability': fields['kickedge_probability'], 'expected_xpm': fields['expected_xpm'],
                        'decimal_odds': fields['decimal_odds'], 'snapshot_sha256': fields['snapshot_sha256'],
                        'features': analysis.get('features')})
    entries.sort(key=lambda e: (e['generated_at'], e['analysis_id']))
    return entries


def _changes(entries, field):
    """Entries where ``field`` differs from the previous entry (the first entry always counts)."""
    points = []
    for entry in entries:
        if not points or entry[field] != points[-1][field]:
            points.append(entry)
    return points


def feature_diff(before, after):
    """Model inputs whose stored value changed between two snapshots."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None
    diff = []
    for name in after:
        old, new = before.get(name), after.get(name)
        same = old == new or (isinstance(old, float) and isinstance(new, float) and math.isnan(old) and math.isnan(new))
        if not same:
            diff.append({'feature': name, 'before': old, 'after': new})
    return diff


def movement(directory, key):
    entries = history(directory, key)
    model = _changes(entries, 'snapshot_sha256')
    price = _changes(entries, 'decimal_odds')
    model_points = []
    for i, entry in enumerate(model):
        point = {k: entry[k] for k in ('analysis_id', 'generated_at', 'probability', 'expected_xpm', 'snapshot_sha256')}
        if i:
            point['change_from_previous_pp'] = 100 * (entry['probability'] - model[i - 1]['probability'])
            point['input_changes'] = feature_diff(model[i - 1]['features'], entry['features'])
        model_points.append(point)
    game_id, kicker_id, side, line = key
    out = {'selection': {'game_id': game_id, 'kicker_id': kicker_id, 'side': side, 'line': line},
           'analyses': len(entries), 'model_movement': model_points,
           'price_movement': [{k: e[k] for k in ('analysis_id', 'generated_at', 'decimal_odds')} | {
               'implied_probability': 1 / e['decimal_odds']} for e in price] if len(price) > 1 else [],
           'note': NOTE}
    if len(model) > 1:
        out['change_from_first_pp'] = 100 * (model[-1]['probability'] - model[0]['probability'])
        out['change_from_previous_pp'] = model_points[-1]['change_from_previous_pp']
    return out


def compare_lines(expected_xpm, lines=LINES):
    """P(Over), P(Under), P(Push) and fair no-push decimal prices for several lines of one Poisson mean.

    The fair price uses the probability the engine compares with a price: conditional on
    no push for integer lines, direct otherwise (inference.odds.analyze_prop).
    """
    rows = []
    for line in lines:
        probabilities = line_probabilities([expected_xpm], line)
        over, under, push = (float(probabilities[k][0]) for k in ('over', 'under', 'push'))
        integer = float(line).is_integer()
        fair = {}
        for side, win, loss in (('over', over, under), ('under', under, over)):
            comparison = win / (win + loss) if integer else win
            fair[side] = fair_decimal_odds(comparison)['decimal']
        rows.append({'line': line, 'p_over': over, 'p_under': under, 'p_push': push, 'push_possible': integer,
                     'fair_decimal_over': fair['over'], 'fair_decimal_under': fair['under'],
                     'fair_basis': 'conditional on no push' if integer else 'direct'})
    return rows


def line_comparison(analysis):
    fields = prediction_fields(analysis)
    lines = sorted(set(LINES) | {float(fields['line'])})
    return {'expected_xpm': fields['expected_xpm'], 'analysed_line': float(fields['line']), 'side': fields['side'],
            'kicker': fields['kicker'], 'game_id': fields['game_id'], 'model_version': fields['model_version'],
            'lines': compare_lines(fields['expected_xpm'], lines),
            'note': 'Same model distribution as the analysis (one Poisson mean); probabilities only, no price advice.'}
