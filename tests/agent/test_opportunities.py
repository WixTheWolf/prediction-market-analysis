from src.agent.models import MarketSnapshot, Signal
from src.agent.opportunities import rank_opportunities


def _market() -> MarketSnapshot:
    return MarketSnapshot(
        ticker="TEST",
        title="Test market",
        yes_price=0.50,
        no_price=0.50,
        volume=100_000,
        spread=0.02,
        rules_text="Resolves yes when the stated event occurs.",
    )


def test_missing_evidence_always_passes() -> None:
    result = rank_opportunities([_market()], {})[0]
    assert result.action == "PASS"
    assert result.model_probability is None
    assert result.maximum_loss_usd == 0.0


def test_independent_signal_can_create_paper_opportunity() -> None:
    signals = {
        "TEST": [
            Signal(
                name="official model",
                probability=0.65,
                confidence=0.80,
                rationale="Independent forecast based on official data.",
            )
        ]
    }
    result = rank_opportunities([_market()], signals, bankroll_usd=1_000)[0]
    assert result.action == "PAPER_BUY"
    assert result.edge > 0.10
    assert result.maximum_loss_usd <= 20.0
    assert result.score > 0


def test_ranked_opportunities_put_actionable_items_first() -> None:
    second = MarketSnapshot(
        ticker="NOEVIDENCE",
        title="No evidence",
        yes_price=0.40,
        no_price=0.60,
        volume=200_000,
        spread=0.01,
        rules_text="Clear rules.",
    )
    signals = {
        "TEST": [
            Signal(name="model", probability=0.70, confidence=0.90, rationale="Documented forecast.")
        ]
    }
    ranked = rank_opportunities([second, _market()], signals)
    assert ranked[0].ticker == "TEST"
    assert ranked[-1].ticker == "NOEVIDENCE"
