"""Order-planning and execution guardrails.

This module does not submit orders. It converts approved paper decisions into
idempotent execution plans that a separately reviewed exchange adapter may use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Iterable

from .models import TradeDecision


@dataclass(frozen=True)
class ExecutionLimits:
    max_order_loss_usd: float = 20.0
    max_daily_loss_usd: float = 50.0
    max_market_exposure_usd: float = 40.0
    max_category_exposure_usd: float = 100.0
    min_edge: float = 0.05
    min_confidence: float = 0.60


@dataclass(frozen=True)
class PortfolioState:
    daily_realized_loss_usd: float = 0.0
    market_exposure_usd: float = 0.0
    category_exposure_usd: float = 0.0
    open_client_order_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrderPlan:
    client_order_id: str
    ticker: str
    side: str
    limit_price: float
    contracts: int
    maximum_loss_usd: float
    created_at: str
    mode: str
    approved: bool
    blockers: tuple[str, ...]


def build_order_plan(
    decision: TradeDecision,
    *,
    limit_price: float,
    category: str,
    portfolio: PortfolioState,
    limits: ExecutionLimits = ExecutionLimits(),
    live_enabled: bool = False,
    operator_confirmation: bool = False,
    kill_switch_active: bool = False,
) -> OrderPlan:
    """Create a deterministic, risk-checked order plan.

    Approval requires both an explicit live flag and operator confirmation.
    Re-running the same decision and price yields the same client order ID,
    preventing accidental duplicate submission.
    """
    if not 0.01 <= limit_price <= 0.99:
        raise ValueError("limit_price must be between 0.01 and 0.99")

    blockers: list[str] = []
    if decision.action not in {"PAPER_BUY", "BUY"}:
        blockers.append("decision is not approved for purchase")
    if decision.edge < limits.min_edge:
        blockers.append("edge is below the live-execution minimum")
    if decision.confidence < limits.min_confidence:
        blockers.append("confidence is below the live-execution minimum")
    if kill_switch_active:
        blockers.append("kill switch is active")
    if portfolio.daily_realized_loss_usd >= limits.max_daily_loss_usd:
        blockers.append("daily loss limit reached")

    requested_loss = min(decision.maximum_loss_usd, limits.max_order_loss_usd)
    remaining_market = limits.max_market_exposure_usd - portfolio.market_exposure_usd
    remaining_category = limits.max_category_exposure_usd - portfolio.category_exposure_usd
    allowed_loss = min(requested_loss, remaining_market, remaining_category)
    contracts = max(0, int(allowed_loss // limit_price))
    actual_loss = round(contracts * limit_price, 2)

    if contracts < 1:
        blockers.append("risk limits permit fewer than one contract")
    if not live_enabled:
        blockers.append("live execution is disabled")
    if not operator_confirmation:
        blockers.append("operator confirmation is required")

    client_order_id = _client_order_id(
        decision.ticker,
        decision.side,
        limit_price,
        category,
    )
    if client_order_id in portfolio.open_client_order_ids:
        blockers.append("duplicate client order ID already open")

    return OrderPlan(
        client_order_id=client_order_id,
        ticker=decision.ticker,
        side=decision.side,
        limit_price=limit_price,
        contracts=contracts,
        maximum_loss_usd=actual_loss,
        created_at=datetime.now(timezone.utc).isoformat(),
        mode="live" if live_enabled else "dry-run",
        approved=not blockers,
        blockers=tuple(blockers),
    )


def assert_unique_plans(plans: Iterable[OrderPlan]) -> None:
    ids = [plan.client_order_id for plan in plans]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate client order IDs detected")


def _client_order_id(ticker: str, side: str, price: float, category: str) -> str:
    raw = f"{ticker}|{side.lower()}|{price:.4f}|{category.lower()}"
    return "pma-" + sha256(raw.encode("utf-8")).hexdigest()[:24]
