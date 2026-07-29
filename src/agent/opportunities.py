"""Evidence-first opportunity ranking for prediction markets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor, log
from typing import Iterable

from .models import MarketSnapshot, Signal
from .scoring import score_market


@dataclass(frozen=True)
class Opportunity:
    ticker: str
    title: str
    side: str
    market_probability: float
    model_probability: float | None
    edge: float
    confidence: float
    action: str
    contracts: int
    maximum_loss_usd: float
    expected_value_usd: float
    score: float
    reasons: tuple[str, ...]
    evidence: tuple[dict[str, str], ...]

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
                    side="",
                    market_probability=market.yes_price,
                    model_probability=None,
                    edge=0.0,
                    confidence=0.0,
                    action="PASS",
                    contracts=0,
                    maximum_loss_usd=0.0,
                    expected_value_usd=0.0,
                    score=0.0,
                    reasons=("no independent forecast evidence",),
                    evidence=(),
                )
            )
            continue

        decision = score_market(market, signals, bankroll_usd=bankroll_usd)
        evidence_quality = _evidence_quality(signals)
        liquidity_factor = min(1.0, log(max(market.volume, 1.0), 10) / 6.0)
        spread_factor = max(0.0, 1.0 - market.spread / 0.10)
        score = max(0.0, decision.edge) * decision.confidence * evidence_quality * liquidity_factor * spread_factor
        reasons = list(decision.reasons)
        reasons.extend(decision.warnings)
        reasons.append(f"{len(signals)} independent signal(s)")
        reasons.append(f"evidence quality {evidence_quality:.0%}")

        contracts = floor(decision.maximum_loss_usd / decision.market_probability) if decision.market_probability > 0 else 0
        expected_value = round(contracts * max(0.0, decision.edge), 2)
        ranked.append(
            Opportunity(
                ticker=market.ticker,
                title=market.title,
                side=decision.side,
                market_probability=decision.market_probability,
                model_probability=decision.estimated_probability,
                edge=decision.edge,
                confidence=decision.confidence,
                action=decision.action,
                contracts=contracts,
                maximum_loss_usd=decision.maximum_loss_usd,
                expected_value_usd=expected_value,
                score=score,
                reasons=tuple(reasons),
                evidence=tuple(_signal_evidence(signal) for signal in signals),
            )
        )

    return sorted(ranked, key=lambda item: (item.action != "PASS", item.score), reverse=True)


def _evidence_quality(signals: list[Signal]) -> float:
    confidence = sum(signal.confidence for signal in signals) / len(signals)
    diversity = min(1.0, len({signal.name for signal in signals}) / 3.0)
    return min(1.0, 0.75 * confidence + 0.25 * diversity)


def _signal_evidence(signal: Signal) -> dict[str, str]:
    evidence = {
        "name": signal.name,
        "rationale": signal.rationale,
        "probability": f"{signal.probability:.6f}",
        "confidence": f"{signal.confidence:.6f}",
    }
    evidence.update({str(key): str(value) for key, value in signal.metadata.items()})
    return evidence
