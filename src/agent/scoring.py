from math import isfinite
from typing import Iterable

from .models import MarketSnapshot, Signal, TradeDecision


def _weighted_probability(signals: Iterable[Signal]) -> tuple[float, float, list[str]]:
    items = list(signals)
    if not items:
        raise ValueError("at least one signal is required")

    effective_weights = [signal.weight * signal.confidence for signal in items]
    total_weight = sum(effective_weights)
    if total_weight <= 0:
        raise ValueError("signals must have positive effective weight")

    probability = sum(signal.probability * weight for signal, weight in zip(items, effective_weights)) / total_weight
    confidence = min(1.0, total_weight / max(1.0, sum(signal.weight for signal in items)))
    reasons = [f"{signal.name}: {signal.rationale}" for signal in items]
    return probability, confidence, reasons


def _fractional_kelly(probability: float, price: float, fraction: float = 0.25) -> float:
    if price <= 0 or price >= 1:
        return 0.0
    payout_multiple = (1.0 - price) / price
    full_kelly = (payout_multiple * probability - (1.0 - probability)) / payout_multiple
    return max(0.0, min(1.0, full_kelly * fraction))


def score_market(
    market: MarketSnapshot,
    signals: Iterable[Signal],
    bankroll_usd: float,
    min_edge: float = 0.04,
    max_bankroll_fraction: float = 0.02,
    kelly_fraction: float = 0.25,
) -> TradeDecision:
    """Turn independent forecasts into a conservative paper-trade decision.

    Prices and probabilities are expressed from 0 to 1. The method selects the
    side with the larger positive edge, applies fractional Kelly sizing, and
    caps risk at ``max_bankroll_fraction``. It does not place an order.
    """
    if bankroll_usd <= 0 or not isfinite(bankroll_usd):
        raise ValueError("bankroll_usd must be a positive finite number")

    estimated_yes, confidence, reasons = _weighted_probability(signals)
    yes_edge = estimated_yes - market.yes_price
    estimated_no = 1.0 - estimated_yes
    no_edge = estimated_no - market.no_price

    if yes_edge >= no_edge:
        side = "yes"
        price = market.yes_price
        probability = estimated_yes
        edge = yes_edge
    else:
        side = "no"
        price = market.no_price
        probability = estimated_no
        edge = no_edge

    warnings: list[str] = []
    if market.spread >= 0.05:
        warnings.append("Wide spread may erase the apparent edge.")
    if market.volume < 10_000:
        warnings.append("Low volume increases slippage and exit risk.")
    if not market.rules_text.strip():
        warnings.append("Resolution rules have not been reviewed.")

    raw_fraction = _fractional_kelly(probability, price, kelly_fraction)
    recommended_fraction = min(raw_fraction, max_bankroll_fraction)
    maximum_loss = round(bankroll_usd * recommended_fraction, 2)

    action = "PASS"
    if edge >= min_edge and confidence >= 0.55 and maximum_loss > 0:
        action = "PAPER_BUY"
    if warnings and edge < min_edge + 0.02:
        action = "PASS"

    return TradeDecision(
        ticker=market.ticker,
        side=side,
        market_probability=price,
        estimated_probability=probability,
        edge=edge,
        confidence=confidence,
        recommended_fraction=recommended_fraction,
        maximum_loss_usd=maximum_loss,
        action=action,
        reasons=reasons,
        warnings=warnings,
    )
