from __future__ import annotations

import httpx

from src.agent.settlement import KalshiSettlementClient, resolve_paper_picks

RESOLVED_AT = "2026-08-02T21:00:00+00:00"


def _history(picks: list[dict]) -> dict:
    return {"version": 1, "updated_at": "", "scans": [], "paper_picks": picks, "performance": {}}


def _pick(ticker: str, side: str, entry: float, contracts: int, status: str = "awaiting_resolution") -> dict:
    return {
        "id": f"{ticker}:{side}:t0",
        "ticker": ticker,
        "title": "Test pick",
        "side": side,
        "status": status,
        "entry_price": entry,
        "current_price": entry,
        "model_probability": 0.6,
        "entry_edge": 0.1,
        "confidence": 0.7,
        "contracts": contracts,
        "maximum_loss_usd": entry * contracts,
        "marked_pnl_usd": 1.23,
        "realized_pnl_usd": None,
        "outcome": None,
    }


def test_resolves_winning_and_losing_picks() -> None:
    results = {
        "WIN-YES": {"status": "settled", "result": "yes"},
        "LOSE-YES": {"status": "finalized", "result": "no"},
        "WIN-NO": {"status": "settled", "result": "no"},
    }
    history = _history(
        [
            _pick("WIN-YES", "yes", 0.40, 50),
            _pick("LOSE-YES", "yes", 0.40, 50),
            _pick("WIN-NO", "no", 0.55, 20),
        ]
    )

    updated, resolved = resolve_paper_picks(history, results.get, resolved_at=RESOLVED_AT)

    assert resolved == 3
    by_ticker = {pick["ticker"]: pick for pick in updated["paper_picks"]}
    assert by_ticker["WIN-YES"]["status"] == "resolved"
    assert by_ticker["WIN-YES"]["outcome"] == 1
    assert by_ticker["WIN-YES"]["realized_pnl_usd"] == 30.0  # (1 - 0.40) * 50
    assert by_ticker["LOSE-YES"]["realized_pnl_usd"] == -20.0  # (0 - 0.40) * 50
    assert by_ticker["WIN-NO"]["outcome"] == 0
    assert by_ticker["WIN-NO"]["realized_pnl_usd"] == 9.0  # (1 - 0.55) * 20
    assert all(pick["marked_pnl_usd"] == 0.0 for pick in updated["paper_picks"])

    performance = updated["performance"]
    assert performance["resolved_picks"] == 3
    assert performance["wins"] == 2
    assert performance["realized_pnl_usd"] == 19.0
    assert performance["brier_score"] is not None


def test_unsettled_and_failed_lookups_leave_picks_awaiting() -> None:
    results = {
        "STILL-OPEN": {"status": "closed", "result": ""},
        "NETWORK-FAIL": None,
    }
    history = _history([_pick("STILL-OPEN", "yes", 0.4, 10), _pick("NETWORK-FAIL", "yes", 0.4, 10)])

    updated, resolved = resolve_paper_picks(history, results.get, resolved_at=RESOLVED_AT)

    assert resolved == 0
    assert all(pick["status"] == "awaiting_resolution" for pick in updated["paper_picks"])


def test_voided_settlement_closes_flat() -> None:
    history = _history([_pick("VOID", "yes", 0.4, 10)])

    updated, resolved = resolve_paper_picks(
        history, lambda _: {"status": "settled", "result": "void"}, resolved_at=RESOLVED_AT
    )

    assert resolved == 1
    pick = updated["paper_picks"][0]
    assert pick["status"] == "voided"
    assert pick["realized_pnl_usd"] == 0.0
    assert pick["outcome"] is None


def test_lookup_cap_and_non_awaiting_skipped() -> None:
    calls: list[str] = []

    def fetch(ticker: str) -> dict:
        calls.append(ticker)
        return {"status": "settled", "result": "yes"}

    picks = [_pick(f"T{i}", "yes", 0.4, 10) for i in range(4)]
    picks.append(_pick("OPEN", "yes", 0.4, 10, status="open"))
    updated, resolved = resolve_paper_picks(_history(picks), fetch, resolved_at=RESOLVED_AT, max_lookups=2)

    assert resolved == 2
    assert len(calls) == 2
    statuses = [pick["status"] for pick in updated["paper_picks"]]
    assert statuses.count("resolved") == 2
    assert statuses.count("awaiting_resolution") == 2
    assert statuses.count("open") == 1


def test_settlement_client_parses_market_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/markets/KX-TEST")
        return httpx.Response(200, json={"market": {"status": "settled", "result": "yes"}})

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.elections.kalshi.com/trade-api/v2"
    )
    with KalshiSettlementClient(client=client) as settlement:
        assert settlement.fetch_result("KX-TEST") == {"status": "settled", "result": "yes"}

    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(
        transport=httpx.MockTransport(failing), base_url="https://api.elections.kalshi.com/trade-api/v2"
    )
    with KalshiSettlementClient(client=client) as settlement:
        assert settlement.fetch_result("KX-TEST") is None
