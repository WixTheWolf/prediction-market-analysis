from datetime import datetime, timezone

from src.agent.models import MarketSnapshot, Signal
from src.agent.scoring import score_market


def _market() -> MarketSnapshot:
    return MarketSnapshot(
        ticker="TEST",
        title="Test market",
        yes_price=0.50,
        no_price=0.51,
        volume=100_000,
        open_interest=10_000,
        spread=0.01,
        closes_at=datetime(2026, 12, 31, tzinfo=timezone.utc),
        category="TEST",
        rules_text="Resolves Yes when the stated event occurs.",
    )


def test_agreeing_sources_keep_more_confidence_than_conflicting_sources() -> None:
    agreeing = [
        Signal(name="A", probability=0.70, confidence=0.80, rationale="A", metadata={"source": "A"}),
        Signal(name="B", probability=0.68, confidence=0.80, rationale="B", metadata={"source": "B"}),
    ]
    conflicting = [
        Signal(name="A", probability=0.80, confidence=0.80, rationale="A", metadata={"source": "A"}),
        Signal(name="B", probability=0.20, confidence=0.80, rationale="B", metadata={"source": "B"}),
    ]
    agreeing_decision = score_market(_market(), agreeing, bankroll_usd=1_000)
    conflicting_decision = score_market(_market(), conflicting, bankroll_usd=1_000)
    assert agreeing_decision.confidence > conflicting_decision.confidence
    assert any("dispersion" in reason.lower() for reason in conflicting_decision.reasons)
