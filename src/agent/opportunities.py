"""Evidence-first opportunity ranking for prediction markets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import log
from typing import Iterable

from .models import MarketSnapshot, Signal
from .scoring import score_market


@dataclass(frozen=True)
class Opportunity:
    ticker: str
    title: str
    market_probability: float
    model_probability: float | None
    edge: float
    confidence: float
    action: str
    maximum_loss_usd: float
    score: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def rank_opportunities(
    markets: Iterable[MarketSnapshot],
    signals_by_ticker: dict[str, list[Signal]],
    *,
    bankroll_usd: float = 1_000.0,
) -> list[Opportunity]:
    """Rank markets using real forecast signals; missing evidence always passes."""
    ranked: list[Opportunity] = []
    for market in markets:
        signals = signals_by_ticker.get(market.ticker, [])
        if not signals:
            ranked.append(
                Opportunity(
                    ticker=market.ticker,
                    title=market.title,
                    market_probability=market.yes_price,
                    model_probability=None,
                    edge=0.0,
                    confidence=0.0,
                    action="PASS",
                    maximum_loss_usd=0.0,
                    score=0.0,
                    reasons=("no independent forecast evidence",),
                )
            )
            continue

        decision = score_market(market, signals, bankroll_usd=bankroll_usd)
        model_probability = _weighted_probability(signals)
        evidence_quality = _evidence_quality(signals)
        liquidity_factor = min(1.0, log(max(market.volume, 1.0), 10) / 6.0)
        spread_factor = max(0.0, 1.0 - market.spread / 0.10)
        score = max(0.0, decision.edge) * decision.confidence * evidence_quality * liquidity_factor * spread_factor
        reasons = list(decision.reasons)
        reasons.extend(decision.warnings)
        reasons.append(f"{len(signals)} independent signal(s)")
        reasons.append(f"evidence quality {evidence_quality:.0%}")

        ranked.append(
            Opportunity(
                ticker=market.ticker,
                title=market.title,
                market_probability=decision.market_probability,
                model_probability=model_probability,
                edge=decision.edge,
                confidence=decision.confidence,
                action=decision.action,
                maximum_loss_usd=decision.maximum_loss_usd,
                score=score,
                reasons=tuple(reasons),
            )
        )

    return sorted(ranked, key=lambda item: (item.action != "PASS", item.score), reverse=True)


def _weighted_probability(signals: list[Signal]) -> float:
    weights = [signal.weight * signal.confidence for signal in signals]
    total_weight = sum(weights)
    if total_weight <= 0:
        return sum(signal.probability for signal in signals) / len(signals)
    return sum(signal.probability * weight for signal, weight in zip(signals, weights)) / total_weight


def _evidence_quality(signals: list[Signal]) -> float:
    confidence = sum(signal.confidence for signal in signals) / len(signals)
    diversity = min(1.0, len({signal.name for signal in signals}) / 3.0)
    return min(1.0, 0.75 * confidence + 0.25 * diversity)
