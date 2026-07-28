import pytest

from src.agent.models import MarketSnapshot, Signal
from src.agent.scoring import score_market


def test_scores_positive_yes_edge_with_capped_risk() -> None:
    market = MarketSnapshot(
        ticker="TEST-YES",
        title="Will the test resolve yes?",
        yes_price=0.55,
        no_price=0.47,
        volume=100_000,
        spread=0.02,
        rules_text="Resolves yes when the published value exceeds the threshold.",
    )
    signals = [
        Signal("base-rate", 0.68, 0.8, "Comparable events resolved yes 68% of the time."),
        Signal("forecast", 0.64, 0.7, "Current forecast remains above the threshold."),
    ]

    decision = score_market(market, signals, bankroll_usd=1_000)

    assert decision.side == "yes"
    assert decision.action == "PAPER_BUY"
    assert decision.edge > 0.04
    assert decision.maximum_loss_usd <= 20.0


def test_passes_when_edge_is_too_small() -> None:
    market = MarketSnapshot(
        ticker="TEST-PASS",
        title="Efficient market",
        yes_price=0.60,
        no_price=0.41,
        volume=100_000,
        rules_text="Clear rules.",
    )
    signals = [Signal("forecast", 0.61, 0.9, "Estimate is close to the market price.")]

    decision = score_market(market, signals, bankroll_usd=1_000)

    assert decision.action == "PASS"


def test_rejects_invalid_market_price() -> None:
    with pytest.raises(ValueError):
        MarketSnapshot(ticker="BAD", title="Bad", yes_price=1.2, no_price=0.1, volume=0)
