"""Post-freeze market audit arithmetic and matching on synthetic quotes."""
import pytest
from scipy.stats import poisson

from kickedge.v2 import market_audit as audit

GAME = {'g1': {'scheduled_kickoff': '2026-09-14T00:20:00+00:00', 'names': {'k1': 'José Pérez'}}}   # Sunday night ET
ROW = {'game_id': 'g1', 'kicker_id': 'k1', 'V1': 2.0}


def quote(day, line=1.5, over=-150, under=120, book='fliff', player='Jose Perez'):
    return {'game_date': day, 'player': player, 'line': line, 'over_odds': over, 'under_odds': under, 'bookmaker': book}


def test_quote_probabilities_separate_vig_from_model():
    q = audit.quote_probabilities(-110, -110, 1.5, 2.0)
    assert q['raw']['over'] == q['raw']['under'] == pytest.approx(110 / 210)
    assert q['no_vig']['over'] == pytest.approx(.5) and q['overround'] == pytest.approx(220 / 210 - 1)
    assert q['kickedge']['over'] == pytest.approx(poisson.sf(1, 2.0))


def test_a_model_equal_to_no_vig_looks_below_raw_on_both_sides():
    record = {'raw': {'over': 110 / 210, 'under': 110 / 210}, 'no_vig': {'over': .5, 'under': .5},
              'kickedge': {'over': .5, 'under': .5}, 'overround': 220 / 210 - 1}
    c = audit.compare([record, record])
    for side in ('over', 'under'):
        assert c[side]['raw']['share_kickedge_below'] == 1 and c[side]['raw']['mean_pp'] == pytest.approx(-100 * (110 / 210 - .5))
        assert c[side]['no_vig']['mean_pp'] == pytest.approx(0)


def test_matching_uses_name_and_nearest_date_and_counts_duplicates():
    quotes = [quote('2026-09-10'), quote('2026-09-13', over=-160), quote('2026-09-12', over=-170),
              quote('2026-09-13', line=2.5, over=150, under=-190), quote('2026-09-20'), quote('2026-09-13', player='Someone Else')]
    records, dropped = audit.match_closing(quotes, [ROW], GAME)
    assert [(r['line'], r['over_odds'], r['date_gap_days']) for r in records] == [(1.5, -160, 0), (2.5, 150, 0)]
    assert dropped == 2 and all(r['ladder_consistent'] for r in records)    # 09-10 and 09-12 lose to 09-13; 09-20 too far


def test_ladder_screen_flags_snapshots_that_cannot_be_one_pregame_board():
    records, _ = audit.match_closing([quote('2026-09-13', 1.5, 110, -140), quote('2026-09-13', 2.5, -200, 160)], [ROW], GAME)
    assert not any(r['ladder_consistent'] for r in records)                # P(over 2.5) above P(over 1.5)
