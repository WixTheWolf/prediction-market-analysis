from datetime import datetime, timezone

import httpx

from src.agent.models import MarketSnapshot
from src.agent.weather_signals import OpenMeteoClient, WeatherConfig, build_weather_signals


def _market(ticker: str, threshold: float) -> MarketSnapshot:
    return MarketSnapshot(
        ticker=ticker,
        title=f"Will the temp in New York City be above {threshold:.2f}° on Jul 29, 2026 at 3am UTC?",
        yes_price=0.45,
        no_price=0.56,
        volume=20_000,
        open_interest=10_000,
        spread=0.01,
        closes_at=datetime(2026, 7, 29, 3, 0, tzinfo=timezone.utc),
        category="KXTEMPNYCH",
        rules_text=(
            f"If the temperature recorded at Central Park, New York City for Jul 29, 2026 "
            f"as reported by The Weather Company (for coordinates KNYC), is above {threshold:.2f}°, "
            "then the market resolves to Yes."
        ),
    )


def test_weather_signal_builds_probability_and_reuses_station_request() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        assert request.url.params.get("temperature_unit") == "fahrenheit"
        assert request.url.params.get("timezone") == "UTC"
        return httpx.Response(
            200,
            json={
                "hourly": {
                    "time": ["2026-07-29T02:00", "2026-07-29T03:00", "2026-07-29T04:00"],
                    "temperature_2m": [72.0, 74.0, 73.5],
                }
            },
        )

    http_client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler))
    client = OpenMeteoClient(WeatherConfig(), client=http_client)
    signals, metadata = build_weather_signals(
        [_market("TEMP-72", 72.0), _market("TEMP-75", 75.0)],
        client=client,
        now=datetime(2026, 7, 29, 2, 0, tzinfo=timezone.utc),
    )

    assert requests == 1
    assert metadata["status"] == "healthy"
    assert metadata["signals"] == 2
    assert signals["TEMP-72"][0].probability > 0.70
    assert signals["TEMP-75"][0].probability < 0.50
    assert signals["TEMP-72"][0].confidence >= 0.66
    assert signals["TEMP-72"][0].metadata["source"] == "Open-Meteo"


def test_unsupported_station_is_not_applicable() -> None:
    market = MarketSnapshot(
        ticker="TEMP-UNKNOWN",
        title="Will the temp be above 70°?",
        yes_price=0.5,
        no_price=0.51,
        volume=1_000,
        open_interest=500,
        spread=0.01,
        closes_at=datetime(2026, 7, 29, 3, 0, tzinfo=timezone.utc),
        category="TEMP",
        rules_text="Uses coordinates KZZZ and resolves above 70°.",
    )
    signals, metadata = build_weather_signals([market], now=datetime(2026, 7, 29, tzinfo=timezone.utc))
    assert signals == {}
    assert metadata["status"] == "not_applicable"
