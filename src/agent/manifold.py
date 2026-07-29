"""Read-only Manifold market discovery for independent forecast evidence.

Manifold uses play-money and prize-cash markets rather than regulated dollar
contracts. Its prices are therefore treated as a lower-weight independent crowd
forecast, never as directly comparable liquidity in U.S. dollars.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

import httpx

from .cross_venue import ExternalMarket


@dataclass(frozen=True)
class ManifoldConfig:
    base_url: str = "https://api.manifold.markets"
    timeout_seconds: float = 20.0
    page_size: int = 1_000
    max_markets: int = 4_000
    # These legacy field names match the shared matcher interface. Values are
    # Manifold activity units, not U.S. dollars.
    min_liquidity_usd: float = 500.0
    min_volume_usd: float = 1_000.0
    min_similarity: float = 0.55
    max_expiration_gap_days: int = 45


@dataclass(frozen=True)
class ManifoldMarket(ExternalMarket):
    source_name: str = "Manifold"
    activity_unit: str = "M$"
    source_weight: float = 0.55
    confidence_multiplier: float = 0.78


class ManifoldDiscoveryClient:
    """Load active binary markets from several relevance-ranked slices."""

    def __init__(self, config: ManifoldConfig | None = None, client: httpx.Client | None = None) -> None:
        self.config = config or ManifoldConfig()
        self._client = client or httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
            headers={"User-Agent": "prediction-market-agent/0.4"},
        )
        self._owns_client = client is None
        self.request_errors = 0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "ManifoldDiscoveryClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_active_markets(self) -> list[ExternalMarket]:
        sorts = ("most-popular", "liquidity", "24-hour-vol", "close-date")
        per_sort = min(self.config.page_size, max(1, self.config.max_markets // len(sorts)))
        seen: dict[str, ExternalMarket] = {}

        for sort in sorts:
            try:
                response = self._client.get(
                    "/v0/search-markets",
                    params={
                        "term": "",
                        "sort": sort,
                        "filter": "open",
                        "contractType": "BINARY",
                        "limit": per_sort,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise ValueError("Manifold search response must be a list")
                for row in payload:
                    if isinstance(row, Mapping):
                        parsed = parse_manifold_market(row)
                        if parsed is not None:
                            seen[parsed.market_id] = parsed
            except (httpx.HTTPError, ValueError, TypeError):
                self.request_errors += 1

        return sorted(
            seen.values(),
            key=lambda market: (market.volume_usd, market.liquidity_usd),
            reverse=True,
        )[: self.config.max_markets]


def parse_manifold_market(raw: Mapping[str, Any]) -> ManifoldMarket | None:
    if str(raw.get("outcomeType") or "").upper() != "BINARY":
        return None
    if bool(raw.get("isResolved")):
        return None

    try:
        probability = float(raw.get("probability"))
    except (TypeError, ValueError):
        return None
    if not 0.0 < probability < 1.0:
        return None

    question = str(raw.get("question") or "").strip()
    market_id = str(raw.get("id") or "").strip()
    if len(question) < 8 or not market_id:
        return None

    token = str(raw.get("token") or "MANA").upper()
    activity_unit = "M$" if token == "MANA" else "cash"
    return ManifoldMarket(
        market_id=market_id,
        question=question,
        yes_probability=probability,
        liquidity_usd=_float(raw.get("totalLiquidity")),
        volume_usd=_float(raw.get("volume")),
        end_date=_parse_millis(raw.get("closeTime")),
        slug=market_id,
        source_url=str(raw.get("url") or f"https://manifold.markets/market/{market_id}"),
        activity_unit=activity_unit,
    )


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _parse_millis(value: Any) -> datetime | None:
    try:
        timestamp = float(value) / 1_000.0
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
