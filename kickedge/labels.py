"""Label policy: only two-source agreement publishes a canonical outcome.

Player-stat absence is never a zero. A PBP zero needs a complete game and
observed kicking participation by that player, not just absence of a PAT.
"""


def reconcile(stats_xpa, stats_xpm, pbp_xpa, pbp_xpm, coverage_ok, observed, unknown_results=0):
    values = (stats_xpa, stats_xpm, pbp_xpa, pbp_xpm)
    for value in values:
        if value is not None and (value < 0 or int(value) != value):
            return None, None, "invalid_count"
    if ((stats_xpa is not None and stats_xpm is not None and stats_xpm > stats_xpa)
            or (pbp_xpa is not None and pbp_xpm is not None and pbp_xpm > pbp_xpa)):
        return None, None, "invalid_count"
    if not coverage_ok:
        return None, None, "incomplete_pbp"
    if unknown_results:
        return None, None, "unknown_pat_result"
    if not observed:
        return None, None, "participation_unverified"
    if stats_xpa is None or stats_xpm is None:
        return None, None, "missing_player_stats"
    if pbp_xpa is None or pbp_xpm is None:
        return None, None, "missing_pbp"
    if stats_xpa != pbp_xpa or stats_xpm != pbp_xpm:
        return None, None, "source_discrepancy"
    return int(stats_xpa), int(stats_xpm), "agreed"
