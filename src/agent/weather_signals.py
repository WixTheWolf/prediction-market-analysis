"""Independent weather probabilities for Kalshi hourly temperature markets.

Kalshi settles these contracts against The Weather Company. Open-Meteo is used
as an independent public forecast, with explicit uncertainty for model and
station-source differences. The client is read-only and requires no API key.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

import httpx

from .models import MarketSnapshot, Signal

_STATION_RE = re.compile(r"coordinates\s+([A-Z0-9]{4})", re.IGNORECASE)
_THRESHOLD_RE = re.compile(r"above\s+(-?\d+(?:\.\d+)?)\s*°", re.IGNORECASE)


@dataclass(frozen=True)
class WeatherStation:
    code: str
    name: str
    latitude: float
    longitude: float


_STATIONS = {
    "KNYC": WeatherStation("KNYC", "Central Park, New York City", 40.7829, -73.9654),
    "KORD": WeatherStation("KORD", "Chicago O'Hare", 41.9742, -87.9073),
    "KAUS": WeatherStation("KAUS", "Austin-Bergstrom", 30.1945, -97.6699),
    "KDCA": WeatherStation("KDCA", "Reagan National, Washington", 38.8512, -77.0402),
    "KLAX": WeatherStation("KLAX", "Los Angeles International", 33.9416, -118.4085),
}


@dataclass(frozen=True)
class WeatherConfig:
    base_url: str = "https://api.open-meteo.com"
    timeout_seconds: float = 20.0
    forecast_days: int = 5
    past_days: int = 1
    base_sigma_f: float = 2.25
    minimum_confidence: float = 0.66
    maximum_confidence: float = 0.80
    source_weight: float = 0.90


@dataclass(frozen=True)
class StationForecast:
    station: WeatherStation
    temperatures_f: dict[datetime, float]
    source_url: str


class OpenMeteoClient:
    """Small cached client for hourly 2-meter temperature forecasts."""

    def __init__(self, config: WeatherConfig | None = None, client: httpx.Client | None = None) -> None:
        self.config = config or WeatherConfig()
        self._client = client or httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
            headers={"User-Agent": "prediction-market-agent/0.5"},
        )
        self._owns_client = client is None
        self._cache: dict[str, StationForecast] = {}
        self.request_count = 0
        self.error_count = 0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "OpenMeteoClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_station(self, station: WeatherStation) -> StationForecast | None:
        cached = self._cache.get(station.code)
        if cached is not None:
            return cached

        self.request_count += 1
        try:
            response = self._client.get(
                "/v1/forecast",
                params={
                    "latitude": station.latitude,
                    "longitude": station.longitude,
                    "hourly": "temperature_2m",
                    "temperature_unit": "fahrenheit",
                    "timezone": "UTC",
                    "past_days": max(0, min(92, self.config.past_days)),
                    "forecast_days": max(1, min(16, self.config.forecast_days)),
                },
            )
            response.raise_for_status()
            payload = response.json()
            forecast = _parse_forecast(payload, station, str(response.request.url))
            self._cache[station.code] = forecast
            return forecast
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            self.error_count += 1
            return None


def build_weather_signals(
    markets: Iterable[MarketSnapshot],
    *,
    config: WeatherConfig | None = None,
    client: OpenMeteoClient | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, list[Signal]], dict[str, Any]]:
    """Build probabilities for supported hourly temperature threshold markets."""

    cfg = config or WeatherConfig()
    owns_client = client is None
    weather_client = client or OpenMeteoClient(cfg)
    now_utc = _as_utc(now or datetime.now(timezone.utc))
    signals: dict[str, list[Signal]] = {}
    supported = 0
    station_codes: set[str] = set()

    try:
        for market in markets:
            parsed = _parse_temperature_market(market)
            if parsed is None:
                continue
            station, threshold_f, target = parsed
            supported += 1
            station_codes.add(station.code)
            forecast = weather_client.fetch_station(station)
            if forecast is None:
                continue
            nearest = _nearest_temperature(forecast.temperatures_f, target)
            if nearest is None:
                continue
            forecast_time, mean_f, gap_minutes = nearest
            if gap_minutes > 75:
                continue

            horizon_hours = max(0.0, (target - now_utc).total_seconds() / 3_600.0)
            sigma_f = _temperature_sigma(cfg.base_sigma_f, horizon_hours, gap_minutes)
            probability = _normal_probability_above(threshold_f, mean_f, sigma_f)
            confidence = _weather_confidence(cfg, horizon_hours, gap_minutes)
            signal = Signal(
                name="Open-Meteo hourly temperature model",
                probability=probability,
                confidence=confidence,
                rationale=(
                    f"Open-Meteo forecasts {mean_f:.1f}°F at {station.code} for "
                    f"{forecast_time:%Y-%m-%d %H:%M UTC}. Using {sigma_f:.1f}°F uncertainty "
                    f"gives {probability:.1%} probability above {threshold_f:.2f}°F."
                ),
                weight=cfg.source_weight,
                metadata={
                    "source": "Open-Meteo",
                    "source_url": forecast.source_url,
                    "station": station.code,
                    "station_name": station.name,
                    "forecast_time": forecast_time.isoformat(),
                    "forecast_temperature_f": f"{mean_f:.3f}",
                    "threshold_f": f"{threshold_f:.3f}",
                    "uncertainty_f": f"{sigma_f:.3f}",
                    "retrieved_at": now_utc.isoformat(),
                },
            )
            signals[market.ticker] = [signal]
    finally:
        if owns_client:
            weather_client.close()

    status = "healthy" if signals else "degraded" if supported else "not_applicable"
    metadata = {
        "name": "Open-Meteo",
        "api": "Forecast API",
        "status": status,
        "error": "" if signals or not supported else "No supported station forecast could be matched",
        "markets_loaded": len(station_codes),
        "markets_considered": supported,
        "signals": len(signals),
        "matches": len(signals),
        "near_matches": 0,
        "request_count": weather_client.request_count,
        "request_errors": weather_client.error_count,
        "weighting": "independent weather model with station/source uncertainty",
    }
    return signals, metadata


def _parse_temperature_market(
    market: MarketSnapshot,
) -> tuple[WeatherStation, float, datetime] | None:
    text = f"{market.title} {market.rules_text}"
    station_match = _STATION_RE.search(text)
    threshold_match = _THRESHOLD_RE.search(text)
    target = _parse_datetime(market.closes_at)
    if station_match is None or threshold_match is None or target is None:
        return None
    station = _STATIONS.get(station_match.group(1).upper())
    if station is None:
        return None
    return station, float(threshold_match.group(1)), _as_utc(target)


def _parse_forecast(payload: Mapping[str, Any], station: WeatherStation, source_url: str) -> StationForecast:
    hourly = payload.get("hourly")
    if not isinstance(hourly, Mapping):
        raise ValueError("Open-Meteo response is missing hourly data")
    times = hourly.get("time")
    temperatures = hourly.get("temperature_2m")
    if not isinstance(times, list) or not isinstance(temperatures, list):
        raise ValueError("Open-Meteo hourly arrays are missing")

    values: dict[datetime, float] = {}
    for time_value, temperature in zip(times, temperatures):
        parsed_time = _parse_datetime(time_value)
        if parsed_time is None or temperature is None:
            continue
        values[_as_utc(parsed_time)] = float(temperature)
    if not values:
        raise ValueError("Open-Meteo returned no usable temperatures")
    return StationForecast(station=station, temperatures_f=values, source_url=source_url)


def _nearest_temperature(
    values: Mapping[datetime, float], target: datetime
) -> tuple[datetime, float, float] | None:
    if not values:
        return None
    target_utc = _as_utc(target)
    forecast_time = min(values, key=lambda candidate: abs((candidate - target_utc).total_seconds()))
    gap_minutes = abs((forecast_time - target_utc).total_seconds()) / 60.0
    return forecast_time, float(values[forecast_time]), gap_minutes


def _temperature_sigma(base_sigma_f: float, horizon_hours: float, gap_minutes: float) -> float:
    horizon_penalty = min(2.5, 0.18 * math.sqrt(max(0.0, horizon_hours)))
    time_alignment_penalty = min(0.75, gap_minutes / 120.0)
    return max(1.5, base_sigma_f + horizon_penalty + time_alignment_penalty)


def _weather_confidence(config: WeatherConfig, horizon_hours: float, gap_minutes: float) -> float:
    confidence = config.maximum_confidence - min(0.12, horizon_hours * 0.003) - min(0.06, gap_minutes / 1_000.0)
    return round(max(config.minimum_confidence, min(config.maximum_confidence, confidence)), 4)


def _normal_probability_above(threshold: float, mean: float, sigma: float) -> float:
    z = (threshold - mean) / max(0.1, sigma)
    probability = 0.5 * math.erfc(z / math.sqrt(2.0))
    return round(max(0.001, min(0.999, probability)), 6)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
