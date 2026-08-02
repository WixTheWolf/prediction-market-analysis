from __future__ import annotations

import httpx

from src.agent.metaculus import MetaculusConfig, MetaculusDiscoveryClient, parse_metaculus_question


def test_parse_classic_api2_shape() -> None:
    question = parse_metaculus_question(
        {
            "id": 42,
            "title": "Will the treaty be signed before 2028?",
            "page_url": "/questions/42/treaty-signed/",
            "community_prediction": {"full": {"q2": 0.63}},
            "number_of_forecasters": 150,
            "resolve_time": "2027-12-31T23:59:59Z",
        }
    )

    assert question is not None
    assert question.market_id == "metaculus-42"
    assert question.yes_probability == 0.63
    assert question.volume_usd == 150
    assert question.source_name == "Metaculus"
    assert question.source_url == "https://www.metaculus.com/questions/42/treaty-signed/"
    assert question.end_date is not None
    assert question.yes_ask is None  # no tradable book


def test_parse_post_style_aggregation_shape() -> None:
    question = parse_metaculus_question(
        {
            "id": 7,
            "title": "Will inflation exceed 3% in 2027?",
            "question": {"aggregations": {"recency_weighted": {"latest": {"centers": [0.41]}}}},
            "prediction_count": 88,
        }
    )

    assert question is not None
    assert question.yes_probability == 0.41
    assert question.volume_usd == 88


def test_parse_rejects_missing_probability_or_title() -> None:
    assert parse_metaculus_question({"id": 1, "title": "Valid title but no prediction"}) is None
    assert parse_metaculus_question({"id": 2, "title": "short", "community_prediction": {"full": {"q2": 0.5}}}) is None
    assert (
        parse_metaculus_question(
            {"id": 3, "title": "Degenerate certainty question", "community_prediction": {"full": {"q2": 1.0}}}
        )
        is None
    )


def test_client_paginates_and_dedupes() -> None:
    pages = [
        {
            "results": [
                {
                    "id": index,
                    "title": f"Numbered forecasting question {index}?",
                    "community_prediction": {"full": {"q2": 0.5}},
                    "number_of_forecasters": 30,
                }
                for index in range(2)
            ]
        },
        {"results": []},
    ]
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        return httpx.Response(200, json=pages[min(len(calls) - 1, len(pages) - 1)])

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://www.metaculus.com")
    with MetaculusDiscoveryClient(config=MetaculusConfig(page_size=2), client=client) as discovery:
        questions = discovery.fetch_active_markets()

    assert [question.market_id for question in questions] == ["metaculus-0", "metaculus-1"]
    assert calls[0]["forecast_type"] == "binary"


def test_client_records_errors_instead_of_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://www.metaculus.com")
    with MetaculusDiscoveryClient(client=client) as discovery:
        assert discovery.fetch_active_markets() == []
        assert discovery.request_errors == 1
