import json
from datetime import datetime, timezone

import httpx

from src.agent.cross_venue import (
    ExternalMarket,
    PolymarketClient,
    PolymarketConfig,
    build_cross_venue_signals,
    parse_polymarket_market,
    question_similarity,
)
from src.agent.models import MarketSnapshot


def _kalshi(title: str = "Will the Federal Reserve cut rates in September 2026?") -> MarketSnapshot:
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
        rules_text="Resolves yes if the Federal Reserve cuts its target range.",
    )


def _external(question: str = "Will the Fed cut interest rates in September 2026?") -> ExternalMarket:
    return ExternalMarket(
        market_id="poly-1",
        question=question,
        yes_probability=0.55,
        liquidity_usd=50_000,
        volume_usd=250_000,
        end_date=datetime(2026, 9, 29, tzinfo=timezone.utc),
        slug="fed-cut-september-2026",
        source_url="https://polymarket.com/event/fed-cut-september-2026",
    )


def test_parse_binary_polymarket_market() -> None:
    market = parse_polymarket_market(
        {
            "id": "123",
            "question": "Will the Fed cut rates?",
            "outcomes": json.dumps(["Yes", "No"]),
            "outcomePrices": json.dumps(["0.57", "0.43"]),
            "liquidity": "12000.5",
            "volume": "80000",
            "endDate": "2026-09-30T00:00:00Z",
            "slug": "fed-cut",
        }
    )
    assert market is not None
    assert market.yes_probability == 0.57
    assert market.liquidity_usd == 12_000.5
    assert market.source_url.endswith("/fed-cut")


def test_question_similarity_recognizes_equivalent_wording() -> None:
    similarity = question_similarity(
        "Will the Federal Reserve cut rates in September 2026?",
        "Will the Fed cut interest rates in September 2026?",
    )
    assert similarity > 0.72


def test_cross_venue_match_emits_auditable_signal() -> None:
    signals, matches = build_cross_venue_signals([_kalshi()], [_external()])
    assert len(matches) == 1
    signal = signals["KXFED-SEP26-CUT"][0]
    assert signal.probability == 0.55
    assert signal.confidence >= 0.55
    assert signal.metadata["source"] == "Polymarket"
    assert signal.metadata["source_url"].startswith("https://polymarket.com")


def test_numeric_mismatch_is_rejected() -> None:
    external = _external("Will the Fed cut interest rates in December 2026?")
    signals, matches = build_cross_venue_signals([_kalshi()], [external])
    assert signals == {}
    assert matches == []


def test_low_liquidity_market_is_rejected() -> None:
    external = ExternalMarket(
        **{**_external().__dict__, "liquidity_usd": 100.0}
    )
    signals, _ = build_cross_venue_signals([_kalshi()], [external])
    assert signals == {}


def test_client_requests_active_open_markets() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update({key: value for key, value in request.url.params.multi_items()})
        return httpx.Response(200, json=[])

    client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler))
    polymarket = PolymarketClient(PolymarketConfig(max_markets=10, page_size=10), client=client)
    assert polymarket.fetch_active_markets() == []
    assert seen["active"] == "true"
    assert seen["closed"] == "false"
    assert seen["limit"] == "10"
