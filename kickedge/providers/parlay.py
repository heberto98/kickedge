"""Bounded current captures from ParlayAPI, never historical availability proof.

No endpoint retries, redirects or pagination are performed. Source probabilities
remain untrusted, and a successful page never proves the whole board is covered.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os

from dotenv import dotenv_values
import requests


_BASE = "https://parlay-api.com/v1/sports/americanfootball_nfl"
_XPM = "player_extra_point_made"
_LIMIT = 5000
_MAX_BYTES = 10 * 1024 * 1024
_SPORTSBOOKS = {"fliff", "draftkings", "fanduel", "caesars", "bovada", "pinnacle"}
_DFS = {"sleeper", "prizepicks", "underdog", "betr", "pick6"}
_IDENTITY = (
    "game_id", "match_id", "event_id", "canonical_event_id", "player_id",
    "player_reference", "player", "game_date", "home_team", "away_team",
    "commence_time", "commence_time_reported", "sport_key", "market_key",
    "period", "last_update", "last_observed", "last_update_type",
)


class ParlayError(RuntimeError):
    """Sanitized adapter failure; never contains raw response or request objects."""

    def __init__(self,message,http_status=None):
        super().__init__(message)
        self.http_status=http_status


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def american_probability(odds):
    """Convert standard American odds; missing/invalid prices yield None.

    This arithmetic function does not classify a provider or approve DFS prices.
    """
    price = _number(odds)
    if price is None or abs(price) < 100:
        return None
    return 100 / (price + 100) if price > 0 else -price / (-price + 100)


def _scalar(value):
    if isinstance(value, str):
        return value if len(value) <= 1024 else None
    if value is None or isinstance(value, bool):
        return value
    return value if isinstance(value, (int, float)) and _number(value) is not None else None


def _boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower().strip() in {"true", "false"}:
        return value.lower().strip() == "true"
    return None


def normalize_xpm(rows):
    """Normalize at most 5,000 input rows without mutation or availability claims.

    Preserve current/closing price aliases and source-reported probabilities in
    their original scales. Only known sportsbook American quotes are converted.
    Missing and nonfinite numbers become None; other markets are excluded.
    """
    if not isinstance(rows, list):
        return []
    normalized = []
    for row in rows[:_LIMIT]:
        if not isinstance(row, dict) or row.get("market_key") != _XPM:
            continue
        item = {key: _scalar(row.get(key)) for key in _IDENTITY}
        book = row.get("bookmaker")
        book = book.strip().lower() if isinstance(book, str) else None
        dfs_flag = _boolean(row.get("is_dfs_flat_payout"))
        kind = "dfs" if book in _DFS or dfs_flag is True else "sportsbook" if book in _SPORTSBOOKS else "unknown"
        item.update(bookmaker=_scalar(book), bookmaker_type=kind,
                    is_dfs_flat_payout=dfs_flag,
                    dfs_normalized=_boolean(row.get("dfs_normalized")),
                    line=_number(row.get("line")),
                    source_implied_probability=_number(row.get("implied_probability")),
                    source_probabilities_trusted=False)
        for side in ("over", "under"):
            current = row.get(f"{side}_price")
            price = _number(current if current is not None else row.get(f"{side}_odds"))
            item[f"{side}_price"] = price
            item[f"{side}_implied_probability"] = american_probability(price) if kind == "sportsbook" else None
            probability = row.get(f"{side}_implied_probability")
            item[f"source_{side}_implied_probability"] = _number(
                probability if probability is not None else row.get(f"{side}_implied_prob")
            )
        normalized.append(item)
    return normalized


def _utc_now():
    return datetime.now(timezone.utc)


class ParlayClient:
    """Read-only current capture client. Secrets are used only in auth headers."""

    def __init__(self, api_key=None, env_path=".env", session=None, clock=_utc_now, timeout=20):
        try:
            key = api_key if api_key is not None else os.environ.get("PARLAY_API_KEY")
            if key is None:
                key = dotenv_values(env_path, interpolate=False).get("PARLAY_API_KEY")
        except Exception:
            raise ParlayError("ParlayAPI credential configuration could not be read") from None
        if not isinstance(key, str) or not key.strip() or "\n" in key or "\r" in key:
            raise ParlayError("PARLAY_API_KEY is missing or invalid") from None
        timeout_number = _number(timeout)
        if timeout_number is None or not 0 < timeout_number <= 120:
            raise ParlayError("ParlayAPI timeout must be between 0 and 120 seconds") from None
        self._api_key = key.strip()
        self._session = session if session is not None else requests.Session()
        self._clock = clock
        self._timeout = timeout_number

    def current_xpm(self):
        """Capture current XPM observations; old last_update cannot backdate capture."""
        result = self._capture("props", {"markets": _XPM, "limit": _LIMIT})
        raw_count = len(result["rows"])
        result["rows"] = normalize_xpm(result["rows"])
        result["metadata"]["normalized_row_count"] = len(result["rows"])
        result["metadata"]["dropped_row_count"] = raw_count - len(result["rows"])
        return result

    def current_markets(self):
        """Capture listed game objects for future identity/cutoff validation."""
        return self._capture("odds", {"markets": "h2h,spreads,totals", "regions": "us", "oddsFormat": "american"})

    def _capture(self, endpoint, params):
        try:
            response = self._session.get(
                f"{_BASE}/{endpoint}", params=params,
                headers={"X-API-Key": self._api_key, "Accept": "application/json"},
                timeout=self._timeout, allow_redirects=False,
            )
        except requests.Timeout:
            raise ParlayError("ParlayAPI request timed out; no retry attempted") from None
        except Exception:
            raise ParlayError("ParlayAPI request failed; no retry attempted") from None
        try:
            if response.status_code != 200:
                status=response.status_code if type(response.status_code) is int else None
                raise ParlayError(f"ParlayAPI HTTP {status}; no retry attempted",status) from None
            content = response.content
            if not isinstance(content, bytes) or not content.strip() or len(content) > _MAX_BYTES:
                raise ValueError()
            rows = response.json()
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError()
            # Validate finite JSON and catch credentials echoed in successful data,
            # including JSON-escaped values. Never persist a raw response body.
            serialized = json.dumps(rows, allow_nan=False, ensure_ascii=False)
            if self._api_key in serialized or self._api_key.encode() in content:
                raise ValueError()
            observed = self._clock()
            if not isinstance(observed, datetime) or observed.tzinfo is None or observed.utcoffset() is None:
                raise ValueError()
            observed_at = observed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            headers = {key.lower(): value for key, value in response.headers.items()}
            has_more = _boolean(headers.get("x-result-has-more"))
            truncated = _boolean(headers.get("x-result-truncated", headers.get("x-archive-truncated")))
            degraded_value = headers.get("x-result-degraded", headers.get("x-provider-degraded"))
            degraded = _boolean(degraded_value)
            if degraded is None and isinstance(degraded_value, str) and degraded_value.strip():
                degraded = True
            if len(rows) > _LIMIT:
                truncated = True
            metadata = {
                "has_more": has_more, "truncated": truncated, "degraded": degraded,
                "coverage_complete": False, "pagination_followed": False,
                "received_row_count": len(rows), "retained_row_count": min(len(rows), _LIMIT),
                "limit": _LIMIT,
            }
            return {"observed_at": observed_at, "source": f"{_BASE}/{endpoint}",
                    "source_sha256": hashlib.sha256(content).hexdigest(),
                    "rows": rows[:_LIMIT], "metadata": metadata}
        except ParlayError:
            raise
        except Exception:
            raise ParlayError("ParlayAPI returned an unsuccessful or invalid response") from None
