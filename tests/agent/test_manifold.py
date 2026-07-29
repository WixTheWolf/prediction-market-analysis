from datetime import datetime, timezone

import httpx

from src.agent.manifold import ManifoldConfig, ManifoldDiscoveryClient, parse_manifold_market
from src.agent.match_engine import build_recall_signals
from src.agent.models import MarketSnapshot


def test_parse_open_binary_manifold_market() -> None:
    market = parse_manifold_market(
        {
            "id": "fed-cut",
            "question": "Will the Fed cut rates in September 2026?",
            "outcomeType": "BINARY",
            "probability": 0.61,
            "totalLiquidity": 2_500,
            "volume": 18_000,
            "closeTime": 1_790_640_000_000,
            "isResolved": False,
            "token": "MANA",
            "url": "https://manifold.markets/example/fed-cut",
        }
    )
    assert market is not None
    assert market.yes_probability == 0.61
    assert market.source_name == "Manifold"
    assert market.source_weight < 1.0


def test_manifold_client_loads_ranked_slices() -> None:
    seen_sorts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_sorts.append(str(request.url.params.get("sort")))
        return httpx.Response(
            200,
            json=[
                {
                    "id": f"market-{len(seen_sorts)}",
                    "question": "Will the Fed cut rates in September 2026?",
                    "outcomeType": "BINARY",
                    "probability": 0.61,
                    "totalLiquidity": 2_500,
                    "volume": 18_000,
                    "closeTime": 1_790_640_000_000,
                    "isResolved": False,
                    "token": "MANA",
                    "url": "https://manifold.markets/example/fed-cut",
                }
            ],
        )

    client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler))
    discovery = ManifoldDiscoveryClient(ManifoldConfig(max_markets=4, page_size=1), client=client)
    markets = discovery.fetch_active_markets()
    assert set(seen_sorts) == {"most-popular", "liquidity", "24-hour-vol", "close-date"}
    assert len(markets) == 4


def test_manifold_match_emits_lower_weight_signal() -> None:
    market = MarketSnapshot(
        ticker="KXFED-SEP26-CUT",
        title="Will the Fed cut rates in September 2026?",
        yes_price=0.42,
        no_price=0.59,
        volume=100_000,
        open_interest=25_000,
        spread=0.02,
        closes_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        category="FED",
        rules_text="Federal Reserve target rate after the September 2026 meeting.",
    )
    external = parse_manifold_market(
        {
            "id": "fed-cut",
            "question": "Will the Fed cut rates in September 2026?",
            "outcomeType": "BINARY",
            "probability": 0.61,
            "totalLiquidity": 2_500,
            "volume": 18_000,
            "closeTime": 1_790_640_000_000,
            "isResolved": False,
            "token": "MANA",
            "url": "https://manifold.markets/example/fed-cut",
        }
    )
    assert external is not None
    signals, matches, _ = build_recall_signals(
        [market],
        [external],
        ManifoldConfig(min_similarity=0.50),  # type: ignore[arg-type]
    )
    signal = signals[market.ticker][0]
    assert matches
    assert signal.metadata["source"] == "Manifold"
    assert signal.weight == 0.55
    assert signal.confidence < 0.75
