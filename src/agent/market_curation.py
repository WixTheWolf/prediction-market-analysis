"""Heuristics for surfacing understandable, researchable prediction markets."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import MarketSnapshot

_BUNDLE_TICKER_HINTS = (
    "MULTIGAME",
    "CROSSCATEGORY",
    "PARLAY",
    "COMBO",
    "SAMEGAME",
)
_RESEARCHABLE_CATEGORY_HINTS = (
    "FED",
    "CPI",
    "JOBS",
    "GDP",
    "WEATHER",
    "TEMP",
    "RAIN",
    "SNOW",
    "ELECTION",
    "PRES",
    "SENATE",
    "HOUSE",
    "NBA",
    "NFL",
    "MLB",
    "NHL",
    "GOLF",
    "EARNINGS",
)


@dataclass(frozen=True)
class MarketQuality:
    score: float
    readable: bool
    researchable: bool
    bundle: bool
    reasons: tuple[str, ...]


def assess_market(market: MarketSnapshot) -> MarketQuality:
    """Score whether a market deserves prominent placement on the dashboard."""
    ticker = market.ticker.upper()
    title = " ".join(market.title.split())
    title_lower = title.lower()
    reasons: list[str] = []

    bundle = any(hint in ticker for hint in _BUNDLE_TICKER_HINTS)
    repeated_yes_no = len(re.findall(r"\b(?:yes|no)\b", title_lower)) >= 4
    comma_heavy = title.count(",") >= 4
    if repeated_yes_no or comma_heavy:
        bundle = True
    if bundle:
        reasons.append("bundle or parlay-style market")

    readable = 8 <= len(title) <= 180 and not bundle
    if len(title) > 180:
        reasons.append("title is too long")
    if len(title) < 8:
        reasons.append("title is too short")

    searchable_text = f"{ticker} {market.category.upper()} {title.upper()}"
    researchable = any(hint in searchable_text for hint in _RESEARCHABLE_CATEGORY_HINTS)
    if researchable:
        reasons.append("supported research category")

    liquidity_score = min(1.0, market.volume / 25_000.0)
    open_interest_score = min(1.0, market.open_interest / 10_000.0)
    spread_score = max(0.0, 1.0 - market.spread / 0.15)
    rules_score = 1.0 if market.rules_text.strip() else 0.0
    category_score = 1.0 if researchable else 0.35

    score = (
        0.28 * liquidity_score
        + 0.18 * open_interest_score
        + 0.22 * spread_score
        + 0.17 * rules_score
        + 0.15 * category_score
    )
    if not readable:
        score *= 0.1
    if bundle:
        score = 0.0

    return MarketQuality(
        score=round(score, 6),
        readable=readable,
        researchable=researchable,
        bundle=bundle,
        reasons=tuple(reasons),
    )


def curate_markets(markets: list[MarketSnapshot], *, include_bundles: bool = False) -> list[MarketSnapshot]:
    """Return dashboard-worthy markets ranked by research tier and execution quality."""
    assessed = [(market, assess_market(market)) for market in markets]
    filtered = [
        (market, quality)
        for market, quality in assessed
        if quality.readable and (include_bundles or not quality.bundle)
    ]
    return [
        market
        for market, _ in sorted(
            filtered,
            key=lambda item: (
                not item[1].researchable,
                item[0].spread,
                -item[1].score,
                -item[0].volume,
                -item[0].open_interest,
            ),
        )
    ]
