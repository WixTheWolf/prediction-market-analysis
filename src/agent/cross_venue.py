"""Independent cross-venue evidence for Kalshi markets.

The engine compares standard Kalshi binary markets with active Polymarket
markets. A signal is emitted only when question text, numeric terms, negation,
and expiration timing are sufficiently aligned. It is deliberately
conservative: an unmatched market receives no forecast rather than an invented
probability.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping

import httpx

from .models import MarketSnapshot, Signal

_WORD_RE = re.compile(r"[a-z0-9]+")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")
_NEGATIONS = {"no", "not", "never", "without", "fail", "fails", "failed", "below", "under"}
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "before",
    "by",
    "do",
    "does",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "will",
    "with",
}


@dataclass(frozen=True)
class ExternalMarket:
    market_id: str
    question: str
    yes_probability: float
    liquidity_usd: float
    volume_usd: float
    end_date: datetime | None
    slug: str
    source_url: str


@dataclass(frozen=True)
class CrossVenueMatch:
    kalshi_ticker: str
    external_market: ExternalMarket
    similarity: float
    confidence: float


@dataclass(frozen=True)
class PolymarketConfig:
    base_url: str = "https://gamma-api.polymarket.com"
    timeout_seconds: float = 20.0
    page_size: int = 500
    max_markets: int = 2_000
    min_liquidity_usd: float = 5_000.0
    min_volume_usd: float = 10_000.0
    min_similarity: float = 0.72
    max_expiration_gap_days: int = 21


class PolymarketClient:
    def __init__(self, config: PolymarketConfig | None = None, client: httpx.Client | None = None) -> None:
        self.config = config or PolymarketConfig()
        self._client = client or httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
            headers={"User-Agent": "prediction-market-agent/0.2"},
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "PolymarketClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_active_markets(self) -> list[ExternalMarket]:
        markets: list[ExternalMarket] = []
        offset = 0
        while len(markets) < self.config.max_markets:
            limit = min(self.config.page_size, self.config.max_markets - len(markets))
            response = self._client.get(
                "/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": limit,
                    "offset": offset,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("Polymarket markets response must be a list")
            page = [parsed for row in payload if isinstance(row, Mapping) if (parsed := parse_polymarket_market(row))]
            markets.extend(page)
            if len(payload) < limit:
                break
            offset += limit
        return markets[: self.config.max_markets]


def parse_polymarket_market(raw: Mapping[str, Any]) -> ExternalMarket | None:
    outcomes = _json_list(raw.get("outcomes"))
    prices = _json_list(raw.get("outcomePrices"))
    if len(outcomes) != len(prices) or len(outcomes) != 2:
        return None

    lowered = [str(value).strip().lower() for value in outcomes]
    if "yes" not in lowered or "no" not in lowered:
        return None
    yes_index = lowered.index("yes")
    try:
        probability = float(prices[yes_index])
    except (TypeError, ValueError):
        return None
    if not 0.0 < probability < 1.0:
        return None

    question = str(raw.get("question") or "").strip()
    if len(question) < 8:
        return None
    slug = str(raw.get("slug") or "").strip()
    return ExternalMarket(
        market_id=str(raw.get("id") or raw.get("conditionId") or slug or question),
        question=question,
        yes_probability=probability,
        liquidity_usd=_float(raw.get("liquidity")),
        volume_usd=_float(raw.get("volume")),
        end_date=_parse_datetime(raw.get("endDate") or raw.get("end_date_iso")),
        slug=slug,
        source_url=f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com",
    )


def build_cross_venue_signals(
    kalshi_markets: Iterable[MarketSnapshot],
    external_markets: Iterable[ExternalMarket],
    config: PolymarketConfig | None = None,
) -> tuple[dict[str, list[Signal]], list[CrossVenueMatch]]:
    cfg = config or PolymarketConfig()
    candidates = [
        market
        for market in external_markets
        if market.liquidity_usd >= cfg.min_liquidity_usd and market.volume_usd >= cfg.min_volume_usd
    ]
    signals: dict[str, list[Signal]] = {}
    matches: list[CrossVenueMatch] = []

    for kalshi in kalshi_markets:
        best: tuple[ExternalMarket, float] | None = None
        for external in candidates:
            similarity = question_similarity(kalshi.title, external.question)
            if similarity < cfg.min_similarity:
                continue
            if not _semantics_compatible(kalshi.title, external.question):
                continue
            if not _expiration_compatible(kalshi.closes_at, external.end_date, cfg.max_expiration_gap_days):
                continue
            if best is None or similarity > best[1]:
                best = (external, similarity)
        if best is None:
            continue

        external, similarity = best
        confidence = _match_confidence(similarity, external, cfg)
        rationale = (
            f"Polymarket prices YES at {external.yes_probability:.1%}; "
            f"question match {similarity:.0%}, liquidity ${external.liquidity_usd:,.0f}, "
            f"volume ${external.volume_usd:,.0f}."
        )
        signal = Signal(
            name="Polymarket cross-venue consensus",
            probability=external.yes_probability,
            confidence=confidence,
            rationale=rationale,
            weight=1.0,
            metadata={
                "source": "Polymarket",
                "source_url": external.source_url,
                "external_market_id": external.market_id,
                "match_similarity": f"{similarity:.4f}",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        signals[kalshi.ticker] = [signal]
        matches.append(
            CrossVenueMatch(
                kalshi_ticker=kalshi.ticker,
                external_market=external,
                similarity=similarity,
                confidence=confidence,
            )
        )
    return signals, matches


def question_similarity(left: str, right: str) -> float:
    left_norm = _normalized_question(left)
    right_norm = _normalized_question(right)
    if not left_norm or not right_norm:
        return 0.0
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    containment = min(1.0, len(left_tokens & right_tokens) / max(4, min(len(left_tokens), len(right_tokens))))
    return round(0.50 * jaccard + 0.30 * sequence + 0.20 * containment, 6)


def merge_signal_maps(*maps: Mapping[str, list[Signal]]) -> dict[str, list[Signal]]:
    merged: dict[str, list[Signal]] = {}
    for mapping in maps:
        for ticker, items in mapping.items():
            merged.setdefault(ticker, []).extend(items)
    return merged


def signal_map_to_json(signals: Mapping[str, list[Signal]]) -> dict[str, list[dict[str, object]]]:
    return {
        ticker: [
            {
                "name": signal.name,
                "probability": signal.probability,
                "confidence": signal.confidence,
                "rationale": signal.rationale,
                "weight": signal.weight,
                "metadata": signal.metadata,
            }
            for signal in items
        ]
        for ticker, items in signals.items()
    }


def _normalized_question(value: str) -> str:
    words = [word for word in _WORD_RE.findall(value.lower()) if word not in _STOPWORDS]
    return " ".join(words)


def _semantics_compatible(left: str, right: str) -> bool:
    left_numbers = set(_NUMBER_RE.findall(left.lower()))
    right_numbers = set(_NUMBER_RE.findall(right.lower()))
    if left_numbers and right_numbers and left_numbers != right_numbers:
        return False
    left_tokens = set(_WORD_RE.findall(left.lower()))
    right_tokens = set(_WORD_RE.findall(right.lower()))
    left_negated = bool(left_tokens & _NEGATIONS)
    right_negated = bool(right_tokens & _NEGATIONS)
    return left_negated == right_negated


def _expiration_compatible(left: datetime | None, right: datetime | None, max_gap_days: int) -> bool:
    if left is None or right is None:
        return True
    left_aware = left if left.tzinfo else left.replace(tzinfo=timezone.utc)
    right_aware = right if right.tzinfo else right.replace(tzinfo=timezone.utc)
    return abs((left_aware - right_aware).total_seconds()) <= max_gap_days * 86_400


def _match_confidence(similarity: float, market: ExternalMarket, config: PolymarketConfig) -> float:
    similarity_component = max(0.0, min(1.0, (similarity - config.min_similarity) / (1.0 - config.min_similarity)))
    liquidity_component = max(0.0, min(1.0, math.log10(max(market.liquidity_usd, 1.0)) / 6.0))
    volume_component = max(0.0, min(1.0, math.log10(max(market.volume_usd, 1.0)) / 7.0))
    return round(min(0.90, 0.55 + 0.20 * similarity_component + 0.08 * liquidity_component + 0.07 * volume_component), 4)


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
