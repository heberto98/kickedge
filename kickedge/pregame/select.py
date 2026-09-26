"""Pure point-in-time selection. This module has no I/O or outcome dependencies."""
from datetime import datetime, timedelta, timezone


CATEGORIES = ("VERIFIED", "STRONG", "INFERRED", "AMBIGUOUS", "UNKNOWN")
KINDS = {"depth_snapshot", "official_assignment", "official_roster",
         "official_unavailable", "official_inactives", "official_context"}


def instant(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("A timezone is required; never infer local publication time")
    return dt.astimezone(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def admissibility(evidence, cutoff, policy):
    if evidence["kind"] not in KINDS:
        return "forbidden_or_untimed_source_kind"
    if not evidence.get("available_at"):
        return "availability_not_demonstrated"
    at = instant(evidence["available_at"])
    if evidence.get("published_at") and instant(evidence["published_at"]) > cutoff:
        return "after_cutoff"
    if evidence.get("modified_at") and instant(evidence["modified_at"]) > cutoff:
        return "content_modified_after_cutoff"
    if at > cutoff:
        return "after_cutoff"
    age_limit = (policy["depth_max_age_hours"] if evidence["kind"] == "depth_snapshot"
                 else policy["official_max_age_hours"])
    if cutoff - at > timedelta(hours=age_limit):
        return "stale_evidence"
    return None


def select(game, evidence, policy):
    """Only game identity/timing and pregame evidence may be passed here.

    Alternatives from rejected/future records are never exposed as candidates.
    A missing player ID is an unresolved candidate, not permission to use names
    or actual game participants as a crosswalk.
    """
    cutoff = instant(game["prediction_cutoff"])
    accepted, ledger = [], []
    for e in evidence:
        if e["game_id"] != game["game_id"] or e["team"] != game["team"]:
            continue
        reason = admissibility(e, cutoff, policy)
        ledger.append({**e, "admissible": reason is None, "rejection_reason": reason})
        if reason is None:
            accepted.append(e)
    candidates = {}
    blocked = {e["player_id"] for e in accepted if e["kind"] == "official_unavailable"}
    positive = {"depth_snapshot", "official_assignment", "official_roster", "official_unavailable"}
    for e in accepted:
        if e["kind"] not in positive:
            continue
        key = e.get("player_id") or "unresolved:" + str(e.get("external_id", e["evidence_id"]))
        c = candidates.setdefault(key, {"player_id": e.get("player_id"), "name": e.get("name"),
            "evidence_ids": [], "rank": None, "blocked": key in blocked,
            "explicit_assignment": False, "active_roster": False, "not_inactive": False})
        c["evidence_ids"].append(e["evidence_id"])
        if e["kind"] == "depth_snapshot":
            c["rank"] = e.get("rank")
        if e["kind"] == "official_assignment":
            c["explicit_assignment"] = True
        if e["kind"] == "official_roster":
            c["active_roster"] = True
    # Absence from an inactive list is useful only with separate positive roster
    # evidence. It cannot manufacture roster membership from a depth chart.
    for c in candidates.values():
        if any(e['kind'] == 'official_inactives' and e.get('complete_list') and
               (c['player_id'] in e.get('inactive_ids', []) or c['name'] in e.get('inactive_names', [])) for e in accepted):
            c['blocked'] = True
        c["not_inactive"] = c["active_roster"] and any(
            e["kind"] == "official_inactives" and e.get("complete_list")
            and c["player_id"] not in e.get("inactive_ids", [])
            and c["name"] not in e.get("inactive_names", []) for e in accepted)
    explicit = [c for c in candidates.values() if c["explicit_assignment"] and not c["blocked"]]
    strong = [c for c in candidates.values() if c["active_roster"] and c["not_inactive"] and not c["blocked"]]
    inferred = [c for c in candidates.values() if (c["rank"] == 1 or c["active_roster"]) and not c["blocked"]]
    pool = explicit or strong or inferred
    category = "VERIFIED" if explicit else "STRONG" if strong else "INFERRED" if inferred else "UNKNOWN"
    chosen = None
    if len(pool) > 1:
        category = "AMBIGUOUS"
    elif pool and pool[0]["player_id"]:
        chosen = pool[0]
    elif pool:
        category = "UNKNOWN"
    reason = (None if category in policy["eligible_categories"] else
              "unresolved_player_id" if pool and not pool[0]["player_id"] else
              "conflicting_candidates" if category == "AMBIGUOUS" else
              "insufficient_temporal_evidence" if category == "UNKNOWN" else
              "evidence_below_training_policy")
    support = [e for e in accepted if chosen and (
        e["evidence_id"] in chosen["evidence_ids"] or
        (category == "STRONG" and e["kind"] == "official_inactives"))]
    result = {**game, "expected_kicker_id": chosen["player_id"] if chosen else None,
        "expected_kicker_name": chosen["name"] if chosen else None,
        "expected_kicker_confidence": category,
        "expected_kicker_source": sorted({e["source_url"] for e in support}),
        "expected_kicker_evidence_type": sorted({e["kind"] for e in support}),
        "expected_kicker_evidence_timestamp": max((e["available_at"] for e in support), key=instant, default=None),
        "expected_kicker_evidence_ids": sorted(e["evidence_id"] for e in support),
        "expected_kicker_candidates": sorted(candidates.values(), key=lambda c: (c["player_id"] or "", c["name"] or "")),
        "expected_kicker_ambiguous": category == "AMBIGUOUS",
        "pregame_identity_eligible": bool(chosen and category in policy["eligible_categories"]),
        "pregame_exclusion_reason": reason}
    return result, ledger
