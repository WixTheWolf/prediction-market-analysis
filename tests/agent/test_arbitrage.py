from __future__ import annotations

from datetime import datetime, timezone

from src.agent.arbitrage import cross_venue_arbitrage, intra_market_arbitrage
from src.agent.cross_venue import CrossVenueMatch, ExternalMarket, parse_polymarket_market
from src.agent.models import MarketSnapshot
from src.agent.predictit import PredictItMarket


def _kalshi(ticker: str, yes: float, no: float) -> MarketSnapshot:
    return MarketSnapshot(
        ticker=ticker,
        title="Will the treaty be signed in 2027?",
        yes_price=yes,
        no_price=no,
        volume=50_000.0,
        spread=0.02,
        closes_at=datetime(2027, 3, 1, tzinfo=timezone.utc),
        rules_text="Clear rules.",
    )


def _external(yes_ask: float | None, no_ask: float | None) -> ExternalMarket:
    return ExternalMarket(
        market_id="pm-1",
        question="Treaty signed in 2027?",
        yes_probability=0.5,
        liquidity_usd=40_000.0,
        volume_usd=90_000.0,
        end_date=datetime(2027, 3, 5, tzinfo=timezone.utc),
        slug="treaty-2027",
        source_url="https://polymarket.com/event/treaty-2027",
        yes_ask=yes_ask,
        no_ask=no_ask,
    )


def test_parse_polymarket_market_captures_two_sided_quotes() -> None:
    market = parse_polymarket_market(
        {
            "id": "123",
            "question": "Will the event happen in 2027?",
            "slug": "event-2027",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.42", "0.58"]',
            "bestBid": 0.41,
            "bestAsk": 0.43,
            "liquidity": "10000",
            "volume": "50000",
        }
    )

    assert market is not None
    assert market.yes_ask == 0.43
    assert market.no_ask == 0.59  # 1 - bestBid


def test_parse_polymarket_market_leaves_quotes_none_without_book() -> None:
    market = parse_polymarket_market(
        {
            "id": "9",
            "question": "Will the event happen in 2027?",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.42", "0.58"]',
        }
    )

    assert market is not None
    assert market.yes_ask is None
    assert market.no_ask is None


def test_intra_market_arbitrage_detects_underpriced_book() -> None:
    cheap = _kalshi("KX-ARB", 0.45, 0.50)
    fair = _kalshi("KX-FAIR", 0.50, 0.52)

    found = intra_market_arbitrage([cheap, fair])

    assert len(found) == 1
    assert found[0].kind == "intra_market"
    assert found[0].legs[0]["ticker"] == "KX-ARB"
    assert round(found[0].gross_profit_per_contract, 4) == 0.05
    assert round(found[0].net_profit_after_buffer, 4) == 0.03


def test_cross_venue_arbitrage_detects_box() -> None:
    kalshi = _kalshi("KX-TREATY", 0.40, 0.62)
    match = CrossVenueMatch(
        kalshi_ticker="KX-TREATY",
        external_market=_external(yes_ask=0.55, no_ask=0.42),
        similarity=0.86,
        confidence=0.8,
    )

    found = cross_venue_arbitrage([match], {"KX-TREATY": kalshi})

    assert found, "expected a cross-venue box"
    best = found[0]
    # Buy YES on kalshi @ 0.40 + NO on polymarket @ 0.42 = 0.82 -> 15% net.
    assert best.kind == "cross_venue"
    assert round(best.total_cost, 4) == 0.82
    assert round(best.net_profit_after_buffer, 4) == 0.15
    assert {leg["source"] for leg in best.legs} == {"kalshi", "polymarket"}
    assert any("resolution" in caveat.lower() for caveat in best.caveats)


def test_cross_venue_arbitrage_requires_high_similarity_and_quotes() -> None:
    kalshi = _kalshi("KX-TREATY", 0.40, 0.62)
    loose_match = CrossVenueMatch(
        kalshi_ticker="KX-TREATY",
        external_market=_external(yes_ask=0.55, no_ask=0.42),
        similarity=0.60,
        confidence=0.8,
    )
    no_book = CrossVenueMatch(
        kalshi_ticker="KX-TREATY",
        external_market=_external(yes_ask=None, no_ask=None),
        similarity=0.90,
        confidence=0.8,
    )

    assert cross_venue_arbitrage([loose_match, no_book], {"KX-TREATY": kalshi}) == []


def test_cross_venue_arbitrage_excludes_high_friction_sources() -> None:
    kalshi = _kalshi("KX-TREATY", 0.40, 0.62)
    predictit = PredictItMarket(
        market_id="predictit-7",
        question="Will the treaty be signed in 2027?",
        yes_probability=0.5,
        liquidity_usd=0.0,
        volume_usd=0.0,
        end_date=datetime(2027, 3, 5, tzinfo=timezone.utc),
        slug="7",
        source_url="https://www.predictit.org/markets/detail/7",
        yes_ask=0.30,
        no_ask=0.30,
    )
    match = CrossVenueMatch(
        kalshi_ticker="KX-TREATY",
        external_market=predictit,
        similarity=0.95,
        confidence=0.8,
    )

    assert cross_venue_arbitrage([match], {"KX-TREATY": kalshi}) == []
