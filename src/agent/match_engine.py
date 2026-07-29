"""High-recall, fail-closed matching between Kalshi and Polymarket.

The first matcher only compared the first unsorted Polymarket pages against the
Kalshi title. That produced a healthy-looking source with zero useful matches.
This module deliberately improves *recall* while preserving strict semantic,
number, date, negation, liquidity, and expiration checks before a signal is
emitted.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping

import httpx

from .cross_venue import CrossVenueMatch, ExternalMarket, PolymarketConfig, parse_polymarket_market
from .models import MarketSnapshot, Signal

_WORD_RE = re.compile(r"[a-z0-9]+")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")
_MONTHS = {
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
}
_NEGATIONS = {"no", "not", "never", "without", "fail", "fails", "below", "under", "less"}
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "by", "does",
    "for", "from", "in", "is", "it", "of", "on", "or", "than", "the",
    "this", "to", "will", "with", "yes", "market", "event", "contract",
}
_ALIASES = (
    (re.compile(r"\bfederal reserve\b"), "fed"),
    (re.compile(r"\bfomc\b"), "fed"),
    (re.compile(r"\binterest rates?\b"), "rates"),
    (re.compile(r"\bunited states\b"), "us"),
    (re.compile(r"\bu\.s\.\b"), "us"),
    (re.compile(r"\bdonald trump\b"), "trump"),
    (re.compile(r"\bpresidential\b"), "president"),
    (re.compile(r"\belection day\b"), "election"),
    (re.compile(r"\bconsumer price index\b"), "cpi"),
    (re.compile(r"\bgross domestic product\b"), "gdp"),
)


@dataclass(frozen=True)
class NearMatch:
    kalshi_ticker: str
    kalshi_question: str
    external_question: str
    similarity: float
    rejection: str
    source_url: str


class PolymarketDiscoveryClient:
    """Load the most useful active Polymarket universe, not arbitrary first pages."""

    def __init__(self, config: PolymarketConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self._client = client or httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            headers={"User-Agent": "prediction-market-agent/0.3"},
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "PolymarketDiscoveryClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_active_markets(self) -> list[ExternalMarket]:
        """Union high-volume, high-liquidity, and recently ending markets."""

        orders = ("volume", "liquidity", "endDate")
        seen: dict[str, ExternalMarket] = {}
        per_order = max(self.config.page_size, math.ceil(self.config.max_markets / len(orders)))
        for order in orders:
            offset = 0
            loaded = 0
            while loaded < per_order:
                limit = min(self.config.page_size, per_order - loaded)
                response = self._client.get(
                    "/markets",
                    params={
                        "active": "true",
                        "closed": "false",
                        "limit": limit,
                        "offset": offset,
                        "order": order,
                        "ascending": "false",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise ValueError("Polymarket markets response must be a list")
                for row in payload:
                    if not isinstance(row, Mapping):
                        continue
                    parsed = parse_polymarket_market(row)
                    if parsed is not None:
                        seen[parsed.market_id] = parsed
                loaded += len(payload)
                if len(payload) < limit:
                    break
                offset += limit
        return sorted(
            seen.values(),
            key=lambda market: (market.volume_usd, market.liquidity_usd),
            reverse=True,
        )[: self.config.max_markets]


def build_recall_signals(
    kalshi_markets: Iterable[MarketSnapshot],
    external_markets: Iterable[ExternalMarket],
    config: PolymarketConfig,
) -> tuple[dict[str, list[Signal]], list[CrossVenueMatch], list[NearMatch]]:
    """Match equivalent contracts with broad retrieval and strict final gates."""

    candidates = [
        market for market in external_markets
        if market.liquidity_usd >= config.min_liquidity_usd
        and market.volume_usd >= config.min_volume_usd
    ]
    token_index: dict[str, set[int]] = defaultdict(set)
    for index, market in enumerate(candidates):
        for token in _meaningful_tokens(market.question):
            token_index[token].add(index)

    signals: dict[str, list[Signal]] = {}
    matches: list[CrossVenueMatch] = []
    near_matches: list[NearMatch] = []

    for kalshi in kalshi_markets:
        variants = _kalshi_variants(kalshi)
        candidate_ids: set[int] = set()
        for variant in variants:
            for token in _meaningful_tokens(variant):
                candidate_ids.update(token_index.get(token, set()))
        if not candidate_ids:
            continue

        best_match: tuple[ExternalMarket, float, str] | None = None
        best_rejected: tuple[ExternalMarket, float, str, str] | None = None
        for index in candidate_ids:
            external = candidates[index]
            best_variant = max(variants, key=lambda value: _similarity(value, external.question))
            similarity = _similarity(best_variant, external.question)
            rejection = _rejection_reason(best_variant, external.question, kalshi.closes_at, external.end_date, config)
            if rejection:
                if best_rejected is None or similarity > best_rejected[1]:
                    best_rejected = (external, similarity, rejection, best_variant)
                continue
            if similarity < config.min_similarity:
                if best_rejected is None or similarity > best_rejected[1]:
                    best_rejected = (external, similarity, "similarity below threshold", best_variant)
                continue
            if best_match is None or similarity > best_match[1]:
                best_match = (external, similarity, best_variant)

        if best_rejected is not None and best_rejected[1] >= 0.34:
            external, similarity, rejection, variant = best_rejected
            near_matches.append(
                NearMatch(
                    kalshi_ticker=kalshi.ticker,
                    kalshi_question=variant,
                    external_question=external.question,
                    similarity=round(similarity, 6),
                    rejection=rejection,
                    source_url=external.source_url,
                )
            )
        if best_match is None:
            continue

        external, similarity, matched_variant = best_match
        confidence = _confidence(similarity, external, config)
        signal = Signal(
            name="Polymarket equivalent-contract price",
            probability=external.yes_probability,
            confidence=confidence,
            rationale=(
                f"Equivalent Polymarket contract prices YES at {external.yes_probability:.1%}; "
                f"semantic match {similarity:.0%}, liquidity ${external.liquidity_usd:,.0f}, "
                f"volume ${external.volume_usd:,.0f}."
            ),
            weight=1.0,
            metadata={
                "source": "Polymarket",
                "source_url": external.source_url,
                "external_market_id": external.market_id,
                "external_question": external.question,
                "kalshi_question_used": matched_variant,
                "match_similarity": f"{similarity:.4f}",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        signals[kalshi.ticker] = [signal]
        matches.append(
            CrossVenueMatch(
                kalshi_ticker=kalshi.ticker,
                external_market=external,
                similarity=round(similarity, 6),
                confidence=confidence,
            )
        )

    near_matches.sort(key=lambda item: item.similarity, reverse=True)
    return signals, matches, near_matches[:50]


def _kalshi_variants(market: MarketSnapshot) -> list[str]:
    title = market.title.strip()
    rules = " ".join(market.rules_text.split())
    variants = [title]
    if rules:
        first_sentence = re.split(r"(?<=[?.!])\s+", rules, maxsplit=1)[0][:500]
        variants.extend([first_sentence, f"{title} {first_sentence}"])
    return [variant for variant in dict.fromkeys(variants) if len(variant) >= 8]


def _canonical(value: str) -> str:
    canonical = value.lower()
    for pattern, replacement in _ALIASES:
        canonical = pattern.sub(replacement, canonical)
    return " ".join(_WORD_RE.findall(canonical))


def _meaningful_tokens(value: str) -> set[str]:
    return {token for token in _canonical(value).split() if token not in _STOPWORDS and len(token) > 2}


def _similarity(left: str, right: str) -> float:
    left_norm, right_norm = _canonical(left), _canonical(right)
    left_tokens, right_tokens = _meaningful_tokens(left), _meaningful_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    precision = intersection / len(left_tokens)
    recall = intersection / len(right_tokens)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    containment = intersection / max(1, min(len(left_tokens), len(right_tokens)))
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    return round(0.50 * f1 + 0.30 * containment + 0.20 * sequence, 6)


def _rejection_reason(
    left: str,
    right: str,
    left_close: datetime | None,
    right_close: datetime | None,
    config: PolymarketConfig,
) -> str:
    left_canonical, right_canonical = _canonical(left), _canonical(right)
    left_numbers, right_numbers = set(_NUMBER_RE.findall(left_canonical)), set(_NUMBER_RE.findall(right_canonical))
    if left_numbers and right_numbers and left_numbers != right_numbers:
        return "different numeric terms"
    left_tokens, right_tokens = set(left_canonical.split()), set(right_canonical.split())
    left_months, right_months = left_tokens & _MONTHS, right_tokens & _MONTHS
    if left_months and right_months and left_months != right_months:
        return "different month"
    if bool(left_tokens & _NEGATIONS) != bool(right_tokens & _NEGATIONS):
        return "opposite or negated wording"
    shared = _meaningful_tokens(left) & _meaningful_tokens(right)
    if len(shared) < 2:
        return "fewer than two meaningful shared terms"
    if left_close is not None and right_close is not None:
        left_aware = left_close if left_close.tzinfo else left_close.replace(tzinfo=timezone.utc)
        right_aware = right_close if right_close.tzinfo else right_close.replace(tzinfo=timezone.utc)
        gap_days = abs((left_aware - right_aware).total_seconds()) / 86_400
        if gap_days > config.max_expiration_gap_days:
            return "expiration dates too far apart"
    return ""


def _confidence(similarity: float, market: ExternalMarket, config: PolymarketConfig) -> float:
    similarity_component = max(0.0, min(1.0, (similarity - config.min_similarity) / (1.0 - config.min_similarity)))
    liquidity_component = max(0.0, min(1.0, math.log10(max(market.liquidity_usd, 1.0)) / 6.0))
    volume_component = max(0.0, min(1.0, math.log10(max(market.volume_usd, 1.0)) / 7.0))
    return round(min(0.92, 0.62 + 0.18 * similarity_component + 0.06 * liquidity_component + 0.06 * volume_component), 4)
