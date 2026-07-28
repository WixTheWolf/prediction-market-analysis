"""Read-only Kalshi market scanning and normalization.

The scanner deliberately stops at market discovery. It does not authenticate,
sign orders, or submit trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional

import httpx

from .models import MarketSnapshot


@dataclass(frozen=True)
class ScannerConfig:
    base_url: str = "https://api.elections.kalshi.com/trade-api/v2"
    timeout_seconds: float = 15.0
    min_volume: float = 100.0
    max_spread: float = 0.15
    page_size: int = 1_000


class KalshiScanner:
    """Small read-only client for public Kalshi market endpoints."""

    def __init__(self, config: Optional[ScannerConfig] = None, client: Optional[httpx.Client] = None) -> None:
        self.config = config or ScannerConfig()
        self._client = client or httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
            headers={"User-Agent": "prediction-market-agent/0.1"},
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "KalshiScanner":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_markets(self, limit: int = 100, status: str = "open", cursor: Optional[str] = None) -> dict[str, Any]:
        if limit <= 0 or limit > 1_000:
            raise ValueError("limit must be between 1 and 1000")
        params: dict[str, Any] = {"limit": limit, "status": status}
        if cursor:
            params["cursor"] = cursor
        response = self._client.get("/markets", params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Kalshi markets response must be an object")
        return payload

    def scan(self, limit: int = 100, status: str = "open") -> list[MarketSnapshot]:
        """Fetch up to ``limit`` markets across cursor-paginated responses."""
        if limit <= 0:
            return []

        raw_markets: list[Mapping[str, Any]] = []
        cursor: Optional[str] = None
        while len(raw_markets) < limit:
            remaining = limit - len(raw_markets)
            page_limit = min(self.config.page_size, remaining)
            payload = self.fetch_markets(limit=page_limit, status=status, cursor=cursor)
            page = payload.get("markets", [])
            if not isinstance(page, list):
                raise ValueError("Kalshi response field 'markets' must be a list")
            raw_markets.extend(item for item in page if isinstance(item, Mapping))
            cursor_value = payload.get("cursor")
            cursor = str(cursor_value) if cursor_value else None
            if not cursor or not page:
                break

        markets = [normalize_market(item) for item in raw_markets[:limit]]
        return [
            market
            for market in markets
            if market.volume >= self.config.min_volume and market.spread <= self.config.max_spread
        ]


def normalize_market(raw: Mapping[str, Any]) -> MarketSnapshot:
    """Normalize current dollar/fixed-point fields with legacy fallbacks."""

    yes_bid = _first_price(raw, "yes_bid_dollars", "yes_bid")
    yes_ask = _first_price(raw, "yes_ask_dollars", "yes_ask")
    no_bid = _first_price(raw, "no_bid_dollars", "no_bid")
    no_ask = _first_price(raw, "no_ask_dollars", "no_ask")

    last_price = _first_price(raw, "last_price_dollars", "last_price", default=0.5)
    yes_price = yes_ask if yes_ask is not None else last_price
    no_price = no_ask if no_ask is not None else round(1.0 - yes_price, 4)
    spread = _spread(yes_bid, yes_ask, no_bid, no_ask)

    return MarketSnapshot(
        ticker=str(raw.get("ticker") or raw.get("market_ticker") or "unknown"),
        title=str(raw.get("title") or raw.get("yes_sub_title") or raw.get("subtitle") or "Untitled market"),
        yes_price=yes_price,
        no_price=no_price,
        volume=_first_number(raw, "volume_fp", "volume", "volume_24h_fp", "volume_24h"),
        open_interest=_first_number(raw, "open_interest_fp", "open_interest"),
        spread=spread,
        closes_at=_parse_datetime(
            raw.get("close_time") or raw.get("latest_expiration_time") or raw.get("expected_expiration_time")
        ),
        category=str(raw.get("category") or raw.get("series_ticker") or raw.get("event_ticker") or "unknown"),
        rules_text=str(raw.get("rules_primary") or raw.get("rules") or ""),
    )


def rank_markets(markets: Iterable[MarketSnapshot]) -> list[MarketSnapshot]:
    """Rank liquid, tight-spread markets first for downstream research."""

    return sorted(markets, key=lambda market: (market.spread, -market.volume, -market.open_interest))


def _first_price(raw: Mapping[str, Any], *keys: str, default: Optional[float] = None) -> Optional[float]:
    for key in keys:
        if raw.get(key) is not None:
            return _price(raw[key], default=default)
    return default


def _first_number(raw: Mapping[str, Any], *keys: str) -> float:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return float(value)
    return 0.0


def _price(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    price = float(value)
    if price > 1.0:
        price /= 100.0
    return min(1.0, max(0.0, price))


def _spread(*prices: Optional[float]) -> float:
    yes_bid, yes_ask, no_bid, no_ask = prices
    spreads = []
    if yes_bid is not None and yes_ask is not None:
        spreads.append(max(0.0, yes_ask - yes_bid))
    if no_bid is not None and no_ask is not None:
        spreads.append(max(0.0, no_ask - no_bid))
    return min(spreads) if spreads else 0.0


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
