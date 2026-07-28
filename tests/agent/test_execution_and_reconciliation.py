from src.agent.execution import ExecutionLimits, PortfolioState, assert_unique_plans, build_order_plan
from src.agent.models import TradeDecision
from src.agent.reconciliation import LocalOrder, RemoteOrder, reconcile_orders


def _decision() -> TradeDecision:
    return TradeDecision(
        ticker="TEST-LIVE",
        side="yes",
        market_probability=0.50,
        estimated_probability=0.65,
        edge=0.15,
        confidence=0.80,
        recommended_fraction=0.02,
        maximum_loss_usd=20.0,
        action="PAPER_BUY",
        reasons=["test"],
        warnings=[],
    )


def test_live_plan_requires_explicit_enable_and_confirmation() -> None:
    plan = build_order_plan(
        _decision(),
        limit_price=0.50,
        category="economics",
        portfolio=PortfolioState(),
    )
    assert not plan.approved
    assert "live execution is disabled" in plan.blockers
    assert "operator confirmation is required" in plan.blockers


def test_live_plan_is_capped_and_idempotent() -> None:
    kwargs = dict(
        decision=_decision(),
        limit_price=0.50,
        category="economics",
        portfolio=PortfolioState(),
        limits=ExecutionLimits(max_order_loss_usd=10.0),
        live_enabled=True,
        operator_confirmation=True,
    )
    first = build_order_plan(**kwargs)
    second = build_order_plan(**kwargs)
    assert first.approved
    assert first.maximum_loss_usd <= 10.0
    assert first.client_order_id == second.client_order_id


def test_duplicate_open_order_is_blocked() -> None:
    initial = build_order_plan(
        _decision(),
        limit_price=0.50,
        category="economics",
        portfolio=PortfolioState(),
        live_enabled=True,
        operator_confirmation=True,
    )
    duplicate = build_order_plan(
        _decision(),
        limit_price=0.50,
        category="economics",
        portfolio=PortfolioState(open_client_order_ids=(initial.client_order_id,)),
        live_enabled=True,
        operator_confirmation=True,
    )
    assert not duplicate.approved
    assert "duplicate client order ID already open" in duplicate.blockers


def test_assert_unique_plans_rejects_duplicates() -> None:
    plan = build_order_plan(
        _decision(),
        limit_price=0.50,
        category="economics",
        portfolio=PortfolioState(),
    )
    try:
        assert_unique_plans([plan, plan])
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("expected duplicate plan validation to fail")


def test_reconciliation_flags_missing_unknown_and_mismatched_orders() -> None:
    report = reconcile_orders(
        [
            LocalOrder("one", "A", "yes", 2, "open"),
            LocalOrder("two", "B", "no", 1, "open"),
        ],
        [
            RemoteOrder("one", "A", "no", 2, "open"),
            RemoteOrder("three", "C", "yes", 1, "open"),
        ],
    )
    assert not report.healthy
    assert report.missing_remote == ("two",)
    assert report.unknown_remote == ("three",)
    assert report.mismatched == ("one",)
