"""Read-only Metaculus discovery for independent forecast evidence.

Metaculus is a forecasting community, not an exchange: its aggregate is a
well-calibrated crowd forecast with no tradable price. Questions flow through
the shared recall matcher as high-weight evidence, and forecaster counts stand
in for activity since no dollar liquidity exists. The community prediction is
parsed defensively across the API shapes Metaculus has used over time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

import httpx

from .cross_venue import ExternalMarket


@dataclass(frozen=True)
class MetaculusConfig:
    base_url: str = "https://www.metaculus.com"
    timeout_seconds: float = 20.0
    page_size: int = 100
    max_markets: int = 1_000
    # Shared matcher interface: values are forecaster counts, not dollars.
    min_liquidity_usd: float = 0.0
    min_volume_usd: float = 20.0
    min_similarity: float = 0.58
    max_expiration_gap_days: int = 45


@dataclass(frozen=True)
class MetaculusQuestion(ExternalMarket):
    source_name: str = "Metaculus"
    activity_unit: str = "forecasters"
    source_weight: float = 0.90
    confidence_multiplier: float = 0.90


class MetaculusDiscoveryClient:
    """Load open binary questions ordered by recent activity."""

    def __init__(self, config: MetaculusConfig | None = None, client: httpx.Client | None = None) -> None:
        self.config = config or MetaculusConfig()
        self._client = client or httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
            headers={"User-Agent": "prediction-market-agent/0.4"},
            follow_redirects=True,
        )
        self._owns_client = client is None
        self.request_errors = 0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "MetaculusDiscoveryClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_active_markets(self) -> list[ExternalMarket]:
        questions: dict[str, ExternalMarket] = {}
        offset = 0
        while len(questions) < self.config.max_markets:
            limit = min(self.config.page_size, self.config.max_markets - len(questions))
            try:
                response = self._client.get(
                    "/api2/questions/",
                    params={
                        "status": "open",
                        "type": "forecast",
                        "forecast_type": "binary",
                        "limit": limit,
                        "offset": offset,
                        "order_by": "-activity",
                    },
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError):
                self.request_errors += 1
                break
            results = payload.get("results") if isinstance(payload, Mapping) else None
            if not isinstance(results, list) or not results:
                break
            for row in results:
                if isinstance(row, Mapping):
                    parsed = parse_metaculus_question(row)
                    if parsed is not None:
                        questions[parsed.market_id] = parsed
            offset += len(results)
            if len(results) < limit:
                break
        return list(questions.values())


def parse_metaculus_question(raw: Mapping[str, Any]) -> MetaculusQuestion | None:
    title = str(raw.get("title") or raw.get("title_short") or "").strip()
    question_id = raw.get("id")
    if len(title) < 8 or question_id is None:
        return None

    probability = _community_probability(raw)
    if probability is None or not 0.0 < probability < 1.0:
        return None

    forecasters = _first_number(
        raw,
        "number_of_forecasters",
        "forecasters_count",
        "prediction_count",
        "forecasts_count",
    )
    page_url = str(raw.get("page_url") or "").strip()
    if page_url and not page_url.startswith("http"):
        page_url = f"https://www.metaculus.com{page_url}"

    return MetaculusQuestion(
        market_id=f"metaculus-{question_id}",
        question=title,
        yes_probability=round(probability, 4),
        liquidity_usd=forecasters,
        volume_usd=forecasters,
        end_date=_parse_datetime(raw.get("resolve_time") or raw.get("scheduled_resolve_time") or raw.get("close_time")),
        slug=str(question_id),
        source_url=page_url or f"https://www.metaculus.com/questions/{question_id}/",
    )


def _community_probability(raw: Mapping[str, Any]) -> float | None:
    """Probe the community-prediction shapes Metaculus has published."""
    # Classic api2 shape: community_prediction.full.q2 is the median.
    community = raw.get("community_prediction")
    if isinstance(community, Mapping):
        full = community.get("full")
        if isinstance(full, Mapping):
            value = _number(full.get("q2"))
            if value is not None:
                return value
        value = _number(community.get("q2"))
        if value is not None:
            return value
    # Flat variants seen in newer payloads.
    for key in ("latest_community_prediction", "community_prediction"):
        value = _number(raw.get(key))
        if value is not None:
            return value
    # Post-style shape: question.aggregations.recency_weighted.latest.centers[0].
    question = raw.get("question")
    if isinstance(question, Mapping):
        aggregations = question.get("aggregations")
        if isinstance(aggregations, Mapping):
            recency = aggregations.get("recency_weighted")
            if isinstance(recency, Mapping):
                latest = recency.get("latest")
                if isinstance(latest, Mapping):
                    centers = latest.get("centers")
                    if isinstance(centers, list) and centers:
                        return _number(centers[0])
    return None


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_number(raw: Mapping[str, Any], *keys: str) -> float:
    for key in keys:
        value = _number(raw.get(key))
        if value is not None:
            return max(0.0, value)
    return 0.0


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
