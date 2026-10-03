"""Several user selections: each leg is one single analysis; the combination is
plain price arithmetic plus an explicitly labelled independence approximation.

KickEdge has no model of correlation between selections. The combined model
probability is the product of per-leg win probabilities (all legs win outright);
it is never presented as exact, and same-game legs are flagged.
"""
from collections import Counter
import math

MIN_SELECTIONS, MAX_SELECTIONS = 2, 10

INDEPENDENCE = ('Approximate combined probability assuming independent selections. KickEdge does not '
                'model correlation between legs.')
SAME_GAME = ('These selections belong to the same game. KickEdge does not currently model correlation '
             'between legs. The combined probability shown is an independence approximation and may be '
             'materially inaccurate.')
PUSH = ('Integer lines can push. Combined settlement varies by sportsbook. KickEdge reports all-win '
        'probability and does not simulate sportsbook-specific parlay settlement.')


def combine(results):
    """Combined price and model summary for successful decimal-priced leg results."""
    if not MIN_SELECTIONS <= len(results) <= MAX_SELECTIONS:
        raise ValueError('Combined analysis needs 2 to 10 selections')
    legs = []
    for r in results:
        if r['market'].get('odds_format') != 'decimal':
            raise ValueError('Combined analysis requires decimal odds for every selection')
        prop = r['prop']
        legs.append({'game_id': r['game']['game_id'], 'decimal_odds': r['market']['decimal_odds'],
                     'p_win': prop['model_side_probability'], 'p_push': prop['p_push'],
                     'push_possible': float(prop['line']).is_integer()})
    decimal = math.prod(leg['decimal_odds'] for leg in legs)
    implied = 1 / decimal
    all_win = math.prod(leg['p_win'] for leg in legs)
    games = Counter(leg['game_id'] for leg in legs)
    same_game = sorted(game for game, count in games.items() if count > 1)
    push = any(leg['push_possible'] for leg in legs)
    warnings = [INDEPENDENCE] + ([SAME_GAME] if same_game else []) + ([PUSH] if push else [])
    return {'selection_count': len(legs), 'combined_decimal_odds': decimal, 'implied_probability': implied,
            'model_probability': all_win,
            'model_probability_basis': 'independence approximation: product of per-selection win probabilities (all legs win)',
            'no_loss_probability': math.prod(leg['p_win'] + leg['p_push'] for leg in legs) if push else None,
            'difference_pp': 100 * (all_win - implied),
            'same_game_correlation_warning': bool(same_game), 'same_game_ids': same_game,
            'push_possible': push, 'warnings': warnings}


def analyze_selections(selections, analyze_one, describe_error):
    """Run every leg through ``analyze_one`` (the single-analysis pipeline).

    A failed leg is reported with its error and blocks the combination: the
    combined result is never computed over a subset of the requested legs.
    """
    legs = []
    for index, selection in enumerate(selections, 1):
        try:
            legs.append({'index': index, 'status': 'ok', 'input': selection, 'result': analyze_one(selection)})
        except (ValueError, OSError) as exc:
            legs.append({'index': index, 'status': 'error', 'input': selection, 'error': describe_error(exc)})
    ok = all(leg['status'] == 'ok' for leg in legs)
    return {'kind': 'multi', 'schema_version': 'multi.1', 'selections': legs,
            'combined_available': ok,
            'combined': combine([leg['result'] for leg in legs]) if ok else None}
