import httpx

from src.agent.predictit import PredictItDiscoveryClient, parse_predictit_market


def test_parse_flattens_contracts_with_market_context() -> None:
    markets = parse_predictit_market(
        {
            "name": "Who wins the nomination?",
            "url": "https://www.predictit.org/markets/detail/1234",
            "contracts": [
                {
                    "id": 111,
                    "name": "Candidate A",
                    "bestBuyYesCost": 0.35,
                    "bestSellYesCost": 0.33,
                    "bestBuyNoCost": 0.68,
                    "dateEnd": "2027-06-30T23:59:59",
                },
                {
                    "id": 112,
                    "name": "Candidate B",
                    "lastTradePrice": 0.19,
                },
            ],
        }
    )

    assert [market.market_id for market in markets] == ["predictit-111", "predictit-112"]
    first = markets[0]
    assert first.question == "Who wins the nomination? — Candidate A"
    assert first.yes_probability == 0.34  # midpoint of best bid/ask
    assert first.yes_ask == 0.35
    assert first.no_ask == 0.68
    assert first.end_date is not None
    assert first.source_name == "PredictIt"
    assert first.source_weight == 0.80
    assert markets[1].yes_probability == 0.19
    assert markets[1].yes_ask is None


def test_parse_single_yes_contract_keeps_market_title() -> None:
    markets = parse_predictit_market(
        {
            "name": "Will the bill pass in 2026?",
            "contracts": [{"id": 9, "name": "Yes", "lastTradePrice": 0.44}],
        }
    )

    assert len(markets) == 1
    assert markets[0].question == "Will the bill pass in 2026?"
    assert markets[0].yes_probability == 0.44


def test_parse_skips_unpriced_and_malformed_contracts() -> None:
    assert parse_predictit_market({"name": "Too short"[:5], "contracts": [{"id": 1}]}) == []
    markets = parse_predictit_market(
        {
            "name": "A market with mixed contract quality",
            "contracts": [
                {"id": 1},  # no prices at all
                {"id": 2, "lastTradePrice": 0.0},  # settled at zero -> not a live quote
                "not-a-mapping",
                {"name": "no id", "lastTradePrice": 0.5},
                {"id": 3, "lastTradePrice": 0.52, "dateEnd": "N/A"},
            ],
        }
    )
    assert [market.market_id for market in markets] == ["predictit-3"]
    assert markets[0].end_date is None


def test_client_fetches_and_caps_markets() -> None:
    payload = {
        "markets": [
            {
                "name": f"Numbered question market {index}?",
                "url": f"https://www.predictit.org/markets/detail/{index}",
                "contracts": [{"id": index * 10, "name": "Yes", "lastTradePrice": 0.5}],
            }
            for index in range(5)
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/marketdata/all/")
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://www.predictit.org/api")
    from src.agent.predictit import PredictItConfig

    with PredictItDiscoveryClient(config=PredictItConfig(max_markets=3), client=client) as discovery:
        markets = discovery.fetch_active_markets()

    assert len(markets) == 3
