import json
from datetime import datetime, timezone

import httpx

from src.agent.cross_venue import ExternalMarket, PolymarketConfig
from src.agent.match_engine import PolymarketDiscoveryClient, build_recall_signals
from src.agent.models import MarketSnapshot


def _kalshi(title: str, rules: str = "") -> MarketSnapshot:
    return MarketSnapshot(
        ticker="KXFED-SEP26-CUT",
        title=title,
        yes_price=0.42,
        no_price=0.59,
        volume=100_000,
        open_interest=25_000,
        spread=0.02,
        closes_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        category="FED",
        rules_text=rules,
    )


def _external(question: str, probability: float = 0.55) -> ExternalMarket:
    return ExternalMarket(
        market_id=question,
        question=question,
        yes_probability=probability,
        liquidity_usd=50_000,
        volume_usd=250_000,
        end_date=datetime(2026, 9, 29, tzinfo=timezone.utc),
        slug="fed-cut-september-2026",
        source_url="https://polymarket.com/event/fed-cut-september-2026",
    )


def test_discovery_queries_useful_sorted_slices() -> None:
    seen_orders: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_orders.append(str(request.url.params.get("order")))
        row = {
            "id": f"market-{len(seen_orders)}",
            "question": "Will the Fed cut rates in September 2026?",
            "outcomes": json.dumps(["Yes", "No"]),
            "outcomePrices": json.dumps(["0.55", "0.45"]),
            "liquidity": "50000",
            "volume": "250000",
            "endDate": "2026-09-29T00:00:00Z",
            "slug": "fed-cut-september-2026",
        }
        return httpx.Response(200, json=[row])

    client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler))
    config = PolymarketConfig(max_markets=3, page_size=1)
    discovery = PolymarketDiscoveryClient(config, client=client)
    markets = discovery.fetch_active_markets()
    assert set(seen_orders) == {"volume", "liquidity", "endDate"}
    assert markets


def test_rules_text_can_supply_full_question() -> None:
    kalshi = _kalshi(
        "Rates lower after September meeting?",
        "This market resolves Yes if the Federal Reserve lowers its target interest rate at the September 2026 meeting.",
    )
    signals, matches, _ = build_recall_signals(
        [kalshi],
        [_external("Will the Fed cut interest rates at its September 2026 meeting?")],
        PolymarketConfig(min_similarity=0.55, max_expiration_gap_days=31),
    )
    assert matches
    assert signals[kalshi.ticker][0].probability == 0.55


def test_conflicting_numeric_terms_are_rejected_and_diagnosed() -> None:
    kalshi = _kalshi("Will inflation be above 3% in September 2026?")
    external = _external("Will inflation be above 4% in September 2026?")
    signals, matches, near = build_recall_signals(
        [kalshi],
        [external],
        PolymarketConfig(min_similarity=0.50, max_expiration_gap_days=31),
    )
    assert signals == {}
    assert matches == []
    assert near and near[0].rejection == "different numeric terms"
