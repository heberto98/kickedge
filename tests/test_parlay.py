"""Offline contract tests for bounded current ParlayAPI captures."""

from datetime import datetime, timezone
import hashlib
import json
import os

import pytest
import requests


NOW = datetime(2026, 9, 30, 20, 0, tzinfo=timezone.utc)
KEY = "fake-private-key-never-output"


def adapter():
    from kickedge.providers.parlay import ParlayClient, ParlayError, normalize_xpm, american_probability
    return ParlayClient, ParlayError, normalize_xpm, american_probability


def quote(**changes):
    return dict(market_key="player_extra_point_made", bookmaker="fliff", player="Kicker",
                game_id="g", event_id="e", canonical_event_id="c", player_id="p",
                game_date="2026-10-01", home_team="BUF", away_team="NE", line=2.5,
                over_price=105, under_price=-120, last_update="2025-01-01T00:00:00Z", **changes)


class Response:
    def __init__(self, data, status=200, headers=None, content=None, error=None):
        self.data, self.status_code = data, status
        self.headers = headers or {}
        self.content = json.dumps(data).encode() if content is None else content
        self.error = error

    def json(self):
        if self.error:
            raise self.error
        return self.data


class Session:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


def client(response=None, error=None, **kwargs):
    cls, _, _, _ = adapter()
    session = Session(response, error)
    return cls(api_key=KEY, session=session, clock=lambda: NOW, **kwargs), session


def test_adapter_is_available():
    import importlib.util
    assert importlib.util.find_spec("kickedge.providers") is not None


def test_sportsbook_quotes_keep_identity_and_calculate_own_probabilities():
    _, _, normalize, _ = adapter()
    row = quote(implied_probability=99, over_implied_probability=.99)
    result = normalize([row])[0]
    assert result["event_id"] == "e" and result["canonical_event_id"] == "c"
    assert result["player_id"] == "p" and result["game_id"] == "g"
    assert result["over_implied_probability"] == pytest.approx(100 / 205)
    assert result["under_implied_probability"] == pytest.approx(120 / 220)
    assert result["source_implied_probability"] == 99
    assert result["source_over_implied_probability"] == .99
    assert result["source_probabilities_trusted"] is False
    assert result["bookmaker_type"] == "sportsbook"


@pytest.mark.parametrize("book,flag,kind", [("sleeper", False, "dfs"), ("fliff", True, "dfs"), ("unknown", False, "unknown")])
def test_non_sportsbook_quotes_never_gain_arithmetic_approval(book, flag, kind):
    row = quote()
    row.update(bookmaker=book, is_dfs_flat_payout=flag)
    result = adapter()[2]([row])[0]
    assert result["bookmaker_type"] == kind
    assert result["over_price"] == 105
    assert result["over_implied_probability"] is None
    assert result["under_implied_probability"] is None


def test_historical_aliases_and_missing_side_are_explicit_null():
    row = quote()
    del row["over_price"], row["under_price"]
    row["over_odds"] = "-110"
    row["over_implied_prob"] = .52
    row["under_implied_prob"] = .48
    result = adapter()[2]([row])[0]
    assert result["over_price"] == -110
    assert result["over_implied_probability"] == pytest.approx(110 / 210)
    assert result["under_price"] is None and result["under_implied_probability"] is None
    assert result["source_over_implied_probability"] == .52
    assert result["source_under_implied_probability"] == .48


@pytest.mark.parametrize("value", [None, 0, 99, -99, True, "bad", float("inf"), float("nan")])
def test_invalid_american_prices_have_no_probability(value):
    assert adapter()[3](value) is None


def test_normalization_drops_other_markets_and_nulls_nonfinite_data():
    row = quote()
    row.update(line=float("nan"), over_price=float("inf"))
    other = {**row, "market_key": "player_field_goals"}
    result = adapter()[2]([None, "bad", other, row])
    assert len(result) == 1
    assert result[0]["line"] is None and result[0]["over_price"] is None


def test_current_xpm_captures_now_hash_and_bounded_header_only_request():
    response = Response([quote()], headers={"X-Result-Has-More": "false"})
    instance, session = client(response)
    output = instance.current_xpm()
    assert output["observed_at"] == "2026-09-30T20:00:00Z"
    assert output["rows"][0]["last_update"] == "2025-01-01T00:00:00Z"
    assert output["source_sha256"] == hashlib.sha256(response.content).hexdigest()
    url, args = session.calls[0]
    assert url == "https://parlay-api.com/v1/sports/americanfootball_nfl/props"
    assert args["params"] == {"markets": "player_extra_point_made", "limit": 5000}
    assert args["headers"]["X-API-Key"] == KEY
    assert args["allow_redirects"] is False and args["timeout"] == 20
    assert output["metadata"]["has_more"] is False
    assert output["metadata"]["coverage_complete"] is False
    assert KEY not in repr(output) and KEY not in repr(instance)


def test_current_market_capture_keeps_listed_games_and_safe_metadata():
    games = [{"id": "g", "bookmakers": [{"key": "fliff", "markets": [{"key": "h2h"}]}]}]
    instance, session = client(Response(games, headers={"x-result-has-more": "true", "x-archive-truncated": "true", "x-provider-degraded": "true", "account-email": "private@example.com"}))
    result = instance.current_markets()
    assert result["rows"] == games
    assert session.calls[0][0].endswith("/odds")
    assert session.calls[0][1]["params"] == {"markets": "h2h,spreads,totals", "regions": "us", "oddsFormat": "american"}
    assert result["metadata"]["has_more"] is True
    assert result["metadata"]["truncated"] is True
    assert result["metadata"]["degraded"] is True
    assert "private@example.com" not in repr(result)


def test_empty_list_is_valid_but_does_not_claim_complete_coverage():
    instance, _ = client(Response([]))
    result = instance.current_xpm()
    assert result["rows"] == []
    assert result["metadata"]["has_more"] is None
    assert result["metadata"]["coverage_complete"] is False


def test_provider_degraded_books_mark_the_capture_incomplete():
    instance, _ = client(Response([], headers={"x-result-degraded": "fliff,sleeper", "x-result-truncated": "true", "x-result-has-more": "false"}))
    metadata = instance.current_xpm()["metadata"]
    assert metadata["degraded"] is True and metadata["truncated"] is True
    assert metadata["coverage_complete"] is False


@pytest.mark.parametrize("response", [Response(None, content=b""), Response({"error": KEY}), Response([], error=ValueError(KEY)), Response([], status=503, content=KEY.encode()), Response([], status=302)])
def test_bad_responses_raise_sanitized_errors_without_retry(response):
    instance, session = client(response)
    with pytest.raises(adapter()[1]) as caught:
        instance.current_xpm()
    assert KEY not in str(caught.value) and KEY not in repr(caught.value)
    assert caught.value.__suppress_context__
    assert len(session.calls) == 1


@pytest.mark.parametrize("error", [requests.Timeout(KEY), requests.ConnectionError(KEY), RuntimeError(KEY)])
def test_transport_exceptions_are_sanitized_without_retry(error):
    instance, session = client(error=error)
    with pytest.raises(adapter()[1]) as caught:
        instance.current_markets()
    assert KEY not in str(caught.value)
    assert len(session.calls) == 1


def test_env_file_is_read_without_modification_or_environment_mutation(tmp_path, monkeypatch):
    monkeypatch.delenv("PARLAY_API_KEY", raising=False)
    path = tmp_path / ".env"
    content = 'PARLAY_API_KEY="file-secret"\n'
    path.write_text(content)
    session = Session(Response([]))
    instance = adapter()[0](env_path=path, session=session, clock=lambda: NOW)
    instance.current_xpm()
    assert session.calls[0][1]["headers"]["X-API-Key"] == "file-secret"
    assert path.read_text() == content and "PARLAY_API_KEY" not in os.environ


def test_missing_key_fails_before_network(tmp_path, monkeypatch):
    monkeypatch.delenv("PARLAY_API_KEY", raising=False)
    cls, error, _, _ = adapter()
    session = Session(Response([]))
    with pytest.raises(error):
        cls(env_path=tmp_path / "absent", session=session)
    assert session.calls == []


def test_echoed_credential_in_success_response_is_rejected():
    instance, _ = client(Response([{"id": KEY}]))
    with pytest.raises(adapter()[1]) as caught:
        instance.current_markets()
    assert KEY not in str(caught.value)


def test_local_row_bound_is_visible_as_truncation():
    instance, _ = client(Response([quote()] * 5001, headers={"x-result-truncated": "false"}))
    result = instance.current_xpm()
    assert len(result["rows"]) == 5000
    assert result["metadata"]["received_row_count"] == 5001
    assert result["metadata"]["truncated"] is True


def test_env_var_takes_precedence_over_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PARLAY_API_KEY", "env-secret")
    path = tmp_path / ".env"
    path.write_text("PARLAY_API_KEY=file-secret\n")
    session = Session(Response([]))
    instance = adapter()[0](env_path=path, session=session)
    instance.current_xpm()
    assert session.calls[0][1]["headers"]["X-API-Key"] == "env-secret"
