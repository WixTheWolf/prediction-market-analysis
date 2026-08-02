"""Arbitrage detection within Kalshi and across matched venues.

Two families of structural mispricing are detected:

- Intra-market: YES ask + NO ask on the same Kalshi contract sums below $1.
- Cross-venue box: buying YES on one venue and NO on the other for a matched
  pair of equivalent contracts costs less than the guaranteed $1 payout.

Both apply conservative fee buffers, and every cross-venue finding carries a
resolution-risk caveat: an apparent lock is only real when both venues' rules
resolve identically. Only venues with executable two-sided quotes and low fee
friction qualify as arbitrage legs, so probability-only sources (Manifold) and
high-fee venues (PredictIt) never appear here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .cross_venue import CrossVenueMatch
from .models import MarketSnapshot

# Kalshi charges roughly 0.07 * p * (1-p) per contract; Polymarket adds gas
# and settlement friction. The buffers absorb those plus quote staleness.
DEFAULT_INTRA_FEE_BUFFER = 0.02
DEFAULT_CROSS_FEE_BUFFER = 0.03

# A box is only claimed against a high-precision match; ordinary evidence
# matches are allowed to be looser than this.
DEFAULT_MIN_BOX_SIMILARITY = 0.75

_ARB_CAPABLE_SOURCES = frozenset({"Polymarket"})

RESOLUTION_CAVEAT = "Verify both venues' resolution rules describe the identical outcome before acting."


@dataclass(frozen=True)
class ArbitrageOpportunity:
    kind: str  # "intra_market" | "cross_venue"
    description: str
    legs: tuple[dict[str, object], ...]
    total_cost: float
    gross_profit_per_contract: float
    net_profit_after_buffer: float
    similarity: float | None
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "description": self.description,
            "legs": list(self.legs),
            "total_cost": round(self.total_cost, 4),
            "gross_profit_per_contract": round(self.gross_profit_per_contract, 4),
            "net_profit_after_buffer": round(self.net_profit_after_buffer, 4),
            "similarity": self.similarity,
            "caveats": list(self.caveats),
        }


def intra_market_arbitrage(
    markets: Iterable[MarketSnapshot],
    *,
    fee_buffer: float = DEFAULT_INTRA_FEE_BUFFER,
) -> list[ArbitrageOpportunity]:
    """Find contracts whose YES and NO asks sum below $1 after the fee buffer."""
    found: list[ArbitrageOpportunity] = []
    for market in markets:
        if market.yes_price <= 0.0 or market.no_price <= 0.0:
            continue
        cost = market.yes_price + market.no_price
        gross = 1.0 - cost
        net = gross - fee_buffer
        if net <= 0:
            continue
        found.append(
            ArbitrageOpportunity(
                kind="intra_market",
                description=(
                    f"Buy YES @ {market.yes_price:.2f} + NO @ {market.no_price:.2f} on "
                    f"{market.source} ({market.ticker}) for {cost:.2f} against a $1.00 payout"
                ),
                legs=(
                    _leg(market.source, market.ticker, market.title, "yes", market.yes_price, ""),
                    _leg(market.source, market.ticker, market.title, "no", market.no_price, ""),
                ),
                total_cost=cost,
                gross_profit_per_contract=gross,
                net_profit_after_buffer=net,
                similarity=None,
                caveats=("Quotes can be stale; confirm both sides are still fillable.",),
            )
        )
    return sorted(found, key=lambda item: item.net_profit_after_buffer, reverse=True)


def cross_venue_arbitrage(
    matches: Iterable[CrossVenueMatch],
    kalshi_by_ticker: Mapping[str, MarketSnapshot],
    *,
    fee_buffer: float = DEFAULT_CROSS_FEE_BUFFER,
    min_similarity: float = DEFAULT_MIN_BOX_SIMILARITY,
) -> list[ArbitrageOpportunity]:
    """Find matched pairs where opposite sides on two venues cost under $1."""
    found: list[ArbitrageOpportunity] = []
    for match in matches:
        external = match.external_market
        source = str(getattr(external, "source_name", "Polymarket"))
        if source not in _ARB_CAPABLE_SOURCES:
            continue
        if match.similarity < min_similarity:
            continue
        kalshi = kalshi_by_ticker.get(match.kalshi_ticker)
        if kalshi is None:
            continue

        combos = []
        if external.no_ask is not None and kalshi.yes_price > 0.0:
            combos.append(
                (
                    _leg("kalshi", kalshi.ticker, kalshi.title, "yes", kalshi.yes_price, ""),
                    _leg(
                        source.lower(),
                        external.market_id,
                        external.question,
                        "no",
                        external.no_ask,
                        external.source_url,
                    ),
                    kalshi.yes_price + external.no_ask,
                )
            )
        if external.yes_ask is not None and kalshi.no_price > 0.0:
            combos.append(
                (
                    _leg(
                        source.lower(),
                        external.market_id,
                        external.question,
                        "yes",
                        external.yes_ask,
                        external.source_url,
                    ),
                    _leg("kalshi", kalshi.ticker, kalshi.title, "no", kalshi.no_price, ""),
                    external.yes_ask + kalshi.no_price,
                )
            )

        for first_leg, second_leg, cost in combos:
            gross = 1.0 - cost
            net = gross - fee_buffer
            if net <= 0:
                continue
            found.append(
                ArbitrageOpportunity(
                    kind="cross_venue",
                    description=(
                        f"Buy {str(first_leg['side']).upper()} on {first_leg['source']} @ {float(first_leg['price']):.2f} "
                        f"+ {str(second_leg['side']).upper()} on {second_leg['source']} @ {float(second_leg['price']):.2f} "
                        f"= {cost:.2f} per $1.00 payout"
                    ),
                    legs=(first_leg, second_leg),
                    total_cost=cost,
                    gross_profit_per_contract=gross,
                    net_profit_after_buffer=net,
                    similarity=round(match.similarity, 4),
                    caveats=(
                        RESOLUTION_CAVEAT,
                        "Capital is locked on both venues until resolution.",
                    ),
                )
            )
    return sorted(found, key=lambda item: item.net_profit_after_buffer, reverse=True)


def _leg(source: str, ticker: str, title: str, side: str, price: float, url: str) -> dict[str, object]:
    return {
        "source": source,
        "ticker": ticker,
        "title": title,
        "side": side,
        "price": round(price, 4),
        "url": url,
    }
