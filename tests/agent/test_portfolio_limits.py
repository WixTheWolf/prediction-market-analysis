from src.agent.models import MarketSnapshot, Signal
from src.agent.opportunities import rank_opportunities


def _market(index: int, category: str) -> MarketSnapshot:
    return MarketSnapshot(
        ticker=f"TEST-{index}",
        title=f"Will test event {index} resolve Yes?",
        yes_price=0.30 + index * 0.005,
        no_price=0.71 - index * 0.005,
        volume=100_000 - index * 1_000,
        open_interest=10_000,
        spread=0.01,
        category=category,
        rules_text="Resolves Yes if the stated event occurs.",
    )


def _signals(markets: list[MarketSnapshot]) -> dict[str, list[Signal]]:
    return {
        market.ticker: [
            Signal(
                name="independent model",
                probability=0.80,
                confidence=0.90,
                rationale="Documented independent forecast.",
            )
        ]
        for market in markets
    }


def test_only_highest_ranked_candidate_survives_per_category() -> None:
    markets = [_market(0, "SAME-EVENT"), _market(1, "SAME-EVENT"), _market(2, "OTHER-EVENT")]
    ranked = rank_opportunities(markets, _signals(markets), bankroll_usd=1_000)
    actionable = [item for item in ranked if item.action != "PASS"]
    assert len(actionable) == 2
    same_event = [item for item in ranked if item.ticker in {"TEST-0", "TEST-1"}]
    assert sum(item.action != "PASS" for item in same_event) == 1
    blocked = next(item for item in same_event if item.action == "PASS")
    assert blocked.contracts == 0
    assert blocked.maximum_loss_usd == 0.0
    assert any("Correlated market group" in reason for reason in blocked.reasons)


def test_portfolio_limits_actionable_count_and_total_risk() -> None:
    markets = [_market(index, f"EVENT-{index}") for index in range(8)]
    ranked = rank_opportunities(markets, _signals(markets), bankroll_usd=1_000)
    actionable = [item for item in ranked if item.action != "PASS"]
    assert len(actionable) <= 5
    assert sum(item.maximum_loss_usd for item in actionable) <= 100.0
    capped = [item for item in ranked if any("Portfolio risk cap reached" in reason for reason in item.reasons)]
    assert capped
    assert all(item.contracts == 0 and item.maximum_loss_usd == 0.0 for item in capped)
