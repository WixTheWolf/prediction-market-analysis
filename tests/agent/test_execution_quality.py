from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from src.agent.execution_quality import (
    KalshiMarketDataClient,
    annotate_opportunities,
    assess_momentum,
    fillable_depth,
)

NOW = datetime(2026, 8, 2, 21, 0, tzinfo=timezone.utc)


def _orderbook(yes_bids: list, no_bids: list) -> dict:
    return {"yes": yes_bids, "no": no_bids}


def test_fillable_depth_walks_opposing_bids() -> None:
    # Buying YES crosses NO bids: NO bid 0.58 -> YES ask 0.42, NO bid 0.55 -> YES ask 0.45.
    book = _orderbook(yes_bids=[(0.40, 100)], no_bids=[(0.58, 30), (0.55, 50), (0.40, 500)])

    contracts, average = fillable_depth(book, "yes", 0.42, slippage_tolerance=0.03)

    assert contracts == 80  # 0.42 and 0.45 both within 0.45 ceiling; 0.60 is not
    assert average is not None and 0.42 < average < 0.45


def test_fillable_depth_returns_zero_without_depth() -> None:
    book = _orderbook(yes_bids=[(0.40, 100)], no_bids=[(0.30, 500)])  # implied YES ask 0.70

    contracts, average = fillable_depth(book, "yes", 0.42)

    assert contracts == 0
    assert average is None


def test_assess_momentum_reports_moves_and_recency() -> None:
    trades = [
        {"yes_price": 0.40, "created_time": NOW - timedelta(hours=30)},
        {"yes_price": 0.42, "created_time": NOW - timedelta(hours=2)},
        {"yes_price": 0.52, "created_time": NOW - timedelta(minutes=10)},
    ]

    momentum = assess_momentum(trades, now=NOW)

    assert momentum["trades_seen"] == 3
    assert momentum["move_1h"] == 0.10  # vs the 2h-old trade (last before the 1h cutoff)
    assert momentum["move_24h"] == 0.12
    assert momentum["minutes_since_last_trade"] == 10.0


def test_annotate_downgrades_unfillable_and_caps_thin_depth() -> None:
    opportunities = [
        {
            "ticker": "KX-EMPTY",
            "side": "yes",
            "action": "PAPER_BUY",
            "market_probability": 0.42,
            "contracts": 40,
            "maximum_loss_usd": 16.8,
            "expected_value_usd": 4.0,
            "reasons": [],
        },
        {
            "ticker": "KX-THIN",
            "side": "yes",
            "action": "PAPER_BUY",
            "market_probability": 0.42,
            "contracts": 40,
            "maximum_loss_usd": 16.8,
            "expected_value_usd": 4.0,
            "reasons": [],
        },
        {"ticker": "KX-PASS", "side": "", "action": "PASS", "reasons": []},
    ]
    books = {
        "KX-EMPTY": _orderbook([], []),
        "KX-THIN": _orderbook([], [(0.57, 10)]),
    }

    annotated, downgrades = annotate_opportunities(
        opportunities,
        lambda ticker: books.get(ticker),
        lambda ticker: [],
        now=NOW,
    )

    assert downgrades == 1
    empty = annotated[0]
    assert empty["action"] == "PASS"
    assert empty["contracts"] == 0
    assert empty["maximum_loss_usd"] == 0.0
    assert any("No resting depth" in reason for reason in empty["reasons"])

    thin = annotated[1]
    assert thin["action"] == "PAPER_BUY"
    assert thin["contracts"] == 10
    assert thin["maximum_loss_usd"] == 4.2  # 16.8 * 10/40
    assert any("Depth-capped" in reason for reason in thin["reasons"])

    assert "execution" not in annotated[2]  # PASS rows are never checked


def test_annotate_warns_on_momentum_and_missing_book() -> None:
    opportunities = [
        {
            "ticker": "KX-MOVED",
            "side": "yes",
            "action": "PAPER_BUY",
            "market_probability": 0.50,
            "contracts": 10,
            "maximum_loss_usd": 5.0,
            "expected_value_usd": 1.0,
            "reasons": [],
        }
    ]
    trades = [
        {"yes_price": 0.40, "created_time": NOW - timedelta(hours=3)},
        {"yes_price": 0.50, "created_time": NOW - timedelta(minutes=5)},
    ]

    annotated, downgrades = annotate_opportunities(
        opportunities,
        lambda ticker: None,
        lambda ticker: trades,
        now=NOW,
    )

    assert downgrades == 0
    row = annotated[0]
    assert row["action"] == "PAPER_BUY"  # missing book warns, never downgrades
    assert row["execution"] == {"status": "unavailable"}
    assert any("Order book unavailable" in reason for reason in row["reasons"])
    assert any("moved" in reason for reason in row["reasons"])
    assert row["momentum"]["move_1h"] == 0.10


def test_client_parses_cent_and_dollar_payloads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/orderbook"):
            return httpx.Response(200, json={"orderbook": {"yes": [[40, 100]], "no": [[55, 25]]}})
        return httpx.Response(
            200,
            json={"trades": [{"yes_price": 45, "created_time": "2026-08-02T20:00:00Z"}]},
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.elections.kalshi.com/trade-api/v2"
    )
    with KalshiMarketDataClient(client=client) as data:
        book = data.fetch_orderbook("KX-T")
        trades = data.fetch_recent_trades("KX-T")

    assert book == {"yes": [(0.40, 100.0)], "no": [(0.55, 25.0)]}
    assert trades is not None and trades[0]["yes_price"] == 0.45
    assert trades[0]["created_time"].tzinfo is not None
