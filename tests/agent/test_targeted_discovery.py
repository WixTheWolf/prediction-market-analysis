import json
from datetime import datetime, timezone

import httpx

from src.agent.cross_venue import PolymarketConfig
from src.agent.match_engine import PolymarketDiscoveryClient
from src.agent.models import MarketSnapshot


def test_targeted_search_extracts_nested_markets() -> None:
    queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        queries.append(str(request.url.params.get("q")))
        market = {
            "id": "fed-cut",
            "question": "Will the Fed cut rates in September 2026?",
            "outcomes": json.dumps(["Yes", "No"]),
            "outcomePrices": json.dumps(["0.58", "0.42"]),
            "liquidity": "50000",
            "volume": "250000",
            "endDate": "2026-09-29T00:00:00Z",
            "slug": "fed-cut-september-2026",
        }
        return httpx.Response(200, json={"events": [{"markets": [market]}], "pagination": {}})

    kalshi = MarketSnapshot(
        ticker="KXFED-SEP26-CUT",
        title="Will the Federal Reserve cut interest rates in September 2026?",
        yes_price=0.42,
        no_price=0.59,
        volume=100_000,
        open_interest=25_000,
        spread=0.02,
        closes_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        category="FED",
        rules_text="",
    )
    client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler))
    discovery = PolymarketDiscoveryClient(PolymarketConfig(), client=client)
    markets = discovery.fetch_targeted_markets([kalshi], max_queries=1)
    assert queries
    assert markets and markets[0].market_id == "fed-cut"
    assert discovery.targeted_query_count == 1
    assert discovery.targeted_error_count == 0
