"""Read-only PredictIt market discovery for independent forecast evidence.

PredictIt publishes one unauthenticated snapshot of every market with
two-sided contract quotes but no volume or liquidity figures. Its prices are
real-money political forecasts, so they carry meaningful evidence weight, but
its 10% profit fee and 5% withdrawal fee mean its contracts are never treated
as executable arbitrage legs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

import httpx

from .cross_venue import ExternalMarket


@dataclass(frozen=True)
class PredictItConfig:
    base_url: str = "https://www.predictit.org/api"
    timeout_seconds: float = 20.0
    max_markets: int = 2_000
    # PredictIt reports no liquidity or volume; thresholds stay at zero so the
    # shared matcher interface never filters its contracts on activity.
    min_liquidity_usd: float = 0.0
    min_volume_usd: float = 0.0
    min_similarity: float = 0.60
    max_expiration_gap_days: int = 31


@dataclass(frozen=True)
class PredictItMarket(ExternalMarket):
    source_name: str = "PredictIt"
    activity_unit: str = "none"
    source_weight: float = 0.80
    confidence_multiplier: float = 0.85


class PredictItDiscoveryClient:
    """Load every active contract from the public market-data endpoint."""

    def __init__(self, config: PredictItConfig | None = None, client: httpx.Client | None = None) -> None:
        self.config = config or PredictItConfig()
        self._client = client or httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
            headers={"User-Agent": "prediction-market-agent/0.4"},
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "PredictItDiscoveryClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_active_markets(self) -> list[ExternalMarket]:
        response = self._client.get("/marketdata/all/")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("PredictIt response must be an object")
        raw_markets = payload.get("markets", [])
        if not isinstance(raw_markets, list):
            raise ValueError("PredictIt response field 'markets' must be a list")

        markets: list[ExternalMarket] = []
        for raw in raw_markets:
            if isinstance(raw, Mapping):
                markets.extend(parse_predictit_market(raw))
            if len(markets) >= self.config.max_markets:
                break
        return markets[: self.config.max_markets]


def parse_predictit_market(raw: Mapping[str, Any]) -> list[PredictItMarket]:
    """Flatten one PredictIt market (with N contracts) into binary questions."""
    contracts = raw.get("contracts", [])
    if not isinstance(contracts, list):
        return []
    market_name = str(raw.get("name") or raw.get("shortName") or "").strip()
    market_url = str(raw.get("url") or "https://www.predictit.org").strip()
    if len(market_name) < 8:
        return []

    parsed: list[PredictItMarket] = []
    for contract in contracts:
        if not isinstance(contract, Mapping):
            continue
        yes_ask = _price(contract.get("bestBuyYesCost"))
        yes_bid = _price(contract.get("bestSellYesCost"))
        last_trade = _price(contract.get("lastTradePrice"))
        probability = _probability_estimate(yes_ask, yes_bid, last_trade)
        if probability is None:
            continue

        contract_name = str(contract.get("name") or contract.get("shortName") or "").strip()
        question = market_name if _same_question(market_name, contract_name) else f"{market_name} — {contract_name}"
        contract_id = str(contract.get("id") or "").strip()
        if not contract_id:
            continue

        parsed.append(
            PredictItMarket(
                market_id=f"predictit-{contract_id}",
                question=question,
                yes_probability=probability,
                liquidity_usd=0.0,
                volume_usd=0.0,
                end_date=_parse_datetime(contract.get("dateEnd")),
                slug=contract_id,
                source_url=market_url,
                yes_ask=yes_ask,
                no_ask=_price(contract.get("bestBuyNoCost")),
            )
        )
    return parsed


def _probability_estimate(yes_ask: float | None, yes_bid: float | None, last_trade: float | None) -> float | None:
    if yes_ask is not None and yes_bid is not None:
        return round((yes_ask + yes_bid) / 2.0, 4)
    for value in (last_trade, yes_ask, yes_bid):
        if value is not None:
            return value
    return None


def _same_question(market_name: str, contract_name: str) -> bool:
    """Single-contract markets repeat the question or use a 'Yes' placeholder."""
    contract = contract_name.strip().lower()
    return contract in ("", "yes", market_name.strip().lower())


def _price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not 0.0 < price < 1.0:
        return None
    return price


def _parse_datetime(value: Any) -> datetime | None:
    if not value or str(value).strip().upper() in ("N/A", "NA"):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
