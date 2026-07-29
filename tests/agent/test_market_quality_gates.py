from src.agent.models import MarketSnapshot, Signal
from src.agent.scoring import score_market


STRONG_SIGNAL = [
    Signal(
        name="independent model",
        probability=0.85,
        confidence=0.90,
        rationale="Documented high-confidence independent forecast.",
    )
]


def _market(*, volume: float = 10_000, spread: float = 0.01, rules: str = "Clear settlement rules.") -> MarketSnapshot:
    return MarketSnapshot(
        ticker="QUALITY",
        title="Will the quality test resolve Yes?",
        yes_price=0.30,
        no_price=0.71,
        volume=volume,
        open_interest=5_000,
        spread=spread,
        category="QUALITY",
        rules_text=rules,
    )


def test_very_low_volume_is_hard_pass_even_with_large_edge() -> None:
    decision = score_market(_market(volume=99), STRONG_SIGNAL, bankroll_usd=1_000)
    assert decision.action == "PASS"
    assert decision.maximum_loss_usd == 0.0
    assert any("below the 100 minimum" in warning for warning in decision.warnings)


def test_ten_percent_spread_is_hard_pass() -> None:
    decision = score_market(_market(spread=0.10), STRONG_SIGNAL, bankroll_usd=1_000)
    assert decision.action == "PASS"
    assert decision.maximum_loss_usd == 0.0
    assert any("10% hard limit" in warning for warning in decision.warnings)


def test_missing_rules_are_hard_pass() -> None:
    decision = score_market(_market(rules=""), STRONG_SIGNAL, bankroll_usd=1_000)
    assert decision.action == "PASS"
    assert decision.maximum_loss_usd == 0.0
    assert any("rules are missing" in warning.lower() for warning in decision.warnings)
