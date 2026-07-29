from src.agent.market_curation import assess_market, curate_markets
from src.agent.models import MarketSnapshot


def _market(
    ticker: str,
    title: str,
    *,
    volume: float = 20_000,
    open_interest: float = 5_000,
    spread: float = 0.03,
    category: str = "economics",
    rules_text: str = "Resolves from an official source.",
) -> MarketSnapshot:
    return MarketSnapshot(
        ticker=ticker,
        title=title,
        yes_price=0.52,
        no_price=0.49,
        volume=volume,
        open_interest=open_interest,
        spread=spread,
        category=category,
        rules_text=rules_text,
    )


def test_bundle_markets_are_hidden_by_default() -> None:
    bundle = _market(
        "KXMVESPORTSMULTIGAMEEXTENDED-TEST",
        "yes Philadelphia, yes Washington, yes Cleveland, yes Kansas City, yes Chicago",
    )
    normal = _market("KXCPI-26AUG-T3.0", "Will CPI be above 3.0% in August?")

    curated = curate_markets([bundle, normal])

    assert [market.ticker for market in curated] == [normal.ticker]
    assert assess_market(bundle).bundle is True


def test_supported_categories_rank_ahead_of_opaque_markets() -> None:
    weather = _market("KXHIGHTEMP-NYC-26AUG01-T90", "Will New York reach 90°F?", category="weather")
    novelty = _market(
        "KXNOVELTY-THING",
        "Will an unspecified entertainment event happen?",
        volume=50_000,
        category="novelty",
    )

    curated = curate_markets([novelty, weather])

    assert curated[0].ticker == weather.ticker
    assert assess_market(weather).researchable is True


def test_unreadable_titles_are_removed() -> None:
    market = _market("KXBAD", "x")

    assert curate_markets([market]) == []
    assert assess_market(market).readable is False
