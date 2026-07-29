"""Persistent paper-trading history for the static command center.

GitHub-hosted runners are ephemeral, so the workflow downloads the previously
published history file, updates it with the current scan, and republishes the
result. This module never submits orders and never treats indicative marks as
realized profit.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Mapping

_MAX_SCANS = 672  # Seven days at a 15-minute cadence.
_MAX_PICKS = 500
_ACTIVE_STATUSES = {"open", "awaiting_resolution"}
_RISK_EXIT_MARKERS = (
    "Correlated market group already represented",
    "Portfolio risk cap reached",
    "minimum required for a paper trade",
    "hard limit",
    "Settlement rules are missing",
)


def update_paper_history(
    previous: Mapping[str, Any] | None,
    markets: list[Mapping[str, Any]],
    opportunities: list[Mapping[str, Any]],
    *,
    generated_at: str,
    build_run: str = "",
) -> dict[str, Any]:
    """Append one scan, open new paper picks, and update indicative marks.

    An existing paper pick is closed at the current displayed price when a new
    hard market-quality, correlation, or portfolio guard explicitly blocks it,
    or when the current actionable model reverses sides. This keeps legacy paper
    exposure aligned with current risk policy while preserving realized paper
    P/L instead of deleting history.
    """

    history = _normalize_history(previous)
    market_by_ticker = {str(row.get("ticker") or ""): row for row in markets if row.get("ticker")}
    actionable = [row for row in opportunities if str(row.get("action") or "PASS") != "PASS"]
    evidence_bearing = [row for row in opportunities if row.get("model_probability") is not None]
    opportunity_by_key = {
        (str(row.get("ticker") or ""), str(row.get("side") or "").lower()): row
        for row in opportunities
        if row.get("ticker")
    }
    opportunity_by_ticker = {
        str(row.get("ticker") or ""): row
        for row in opportunities
        if row.get("ticker")
    }

    scan_record = {
        "generated_at": generated_at,
        "build_run": str(build_run),
        "market_count": len(markets),
        "evidence_count": len(evidence_bearing),
        "actionable_count": len(actionable),
        "best_edge": round(max((float(row.get("edge") or 0.0) for row in actionable), default=0.0), 6),
    }
    scans = list(history["scans"])
    if not scans or scans[-1].get("generated_at") != generated_at:
        scans.append(scan_record)
    history["scans"] = scans[-_MAX_SCANS:]

    picks = [deepcopy(row) for row in history["paper_picks"] if isinstance(row, Mapping)]
    active_keys = {
        (str(row.get("ticker") or ""), str(row.get("side") or "").lower())
        for row in picks
        if str(row.get("status") or "open") in _ACTIVE_STATUSES
    }

    for opportunity in actionable:
        ticker = str(opportunity.get("ticker") or "")
        side = str(opportunity.get("side") or "").lower()
        contracts = int(opportunity.get("contracts") or 0)
        if not ticker or side not in {"yes", "no"} or contracts <= 0 or (ticker, side) in active_keys:
            continue
        market = market_by_ticker.get(ticker, {})
        entry_price = float(opportunity.get("market_probability") or 0.0)
        pick = {
            "id": f"{ticker}:{side}:{generated_at}",
            "ticker": ticker,
            "title": str(opportunity.get("title") or market.get("title") or ticker),
            "side": side,
            "status": "open",
            "opened_at": generated_at,
            "last_seen_at": generated_at,
            "closes_at": market.get("closes_at"),
            "entry_price": entry_price,
            "current_price": entry_price,
            "model_probability": opportunity.get("model_probability"),
            "entry_edge": float(opportunity.get("edge") or 0.0),
            "confidence": float(opportunity.get("confidence") or 0.0),
            "contracts": contracts,
            "maximum_loss_usd": float(opportunity.get("maximum_loss_usd") or 0.0),
            "expected_value_usd": float(opportunity.get("expected_value_usd") or 0.0),
            "marked_pnl_usd": 0.0,
            "realized_pnl_usd": None,
            "outcome": None,
            "evidence": deepcopy(opportunity.get("evidence") or []),
        }
        picks.append(pick)
        active_keys.add((ticker, side))

    now = _parse_datetime(generated_at) or datetime.now(timezone.utc)
    for pick in picks:
        status = str(pick.get("status") or "open")
        if status not in _ACTIVE_STATUSES:
            continue
        ticker = str(pick.get("ticker") or "")
        side = str(pick.get("side") or "yes").lower()
        market = market_by_ticker.get(ticker)
        opportunity = opportunity_by_key.get((ticker, side)) or opportunity_by_ticker.get(ticker)
        exit_reason = _risk_exit_reason(opportunity, current_side=side)

        if market is not None:
            current_price = float(market.get("yes_price") if side == "yes" else market.get("no_price") or 0.0)
            entry_price = float(pick.get("entry_price") or 0.0)
            contracts = int(pick.get("contracts") or 0)
            pnl = round((current_price - entry_price) * contracts, 2)
            pick["current_price"] = current_price
            pick["last_seen_at"] = generated_at

            if exit_reason:
                pick["status"] = "closed_by_risk_guard"
                pick["closed_at"] = generated_at
                pick["close_reason"] = exit_reason
                pick["realized_pnl_usd"] = pnl
                pick["marked_pnl_usd"] = 0.0
                continue

            pick["marked_pnl_usd"] = pnl
            if status == "awaiting_resolution":
                pick["status"] = "open"
            continue

        closes_at = _parse_datetime(pick.get("closes_at"))
        if closes_at is not None and closes_at <= now:
            pick["status"] = "awaiting_resolution"

    history["paper_picks"] = picks[-_MAX_PICKS:]
    history["updated_at"] = generated_at
    history["performance"] = calculate_performance(history["paper_picks"])
    return history


def calculate_performance(picks: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Calculate honest performance metrics from recorded paper picks."""
    active = [row for row in picks if str(row.get("status") or "open") in _ACTIVE_STATUSES]
    resolved = [row for row in picks if row.get("outcome") in {0, 1}]
    wins = [row for row in resolved if _pick_won(row)]
    probabilities = [float(row.get("model_probability")) for row in resolved if row.get("model_probability") is not None]
    outcomes = [_side_outcome(row) for row in resolved if row.get("model_probability") is not None]
    brier = mean((probability - outcome) ** 2 for probability, outcome in zip(probabilities, outcomes)) if probabilities else None
    return {
        "total_picks": len(picks),
        "open_picks": len(active),
        "resolved_picks": len(resolved),
        "wins": len(wins),
        "win_rate": round(len(wins) / len(resolved), 6) if resolved else None,
        "brier_score": round(brier, 6) if brier is not None else None,
        "realized_pnl_usd": round(sum(float(row.get("realized_pnl_usd") or 0.0) for row in picks), 2),
        "marked_pnl_usd": round(sum(float(row.get("marked_pnl_usd") or 0.0) for row in active), 2),
        "open_risk_usd": round(sum(float(row.get("maximum_loss_usd") or 0.0) for row in active), 2),
        "average_entry_edge": round(mean(float(row.get("entry_edge") or 0.0) for row in picks), 6) if picks else None,
        "sample_ready": len(resolved) >= 30,
    }


def _risk_exit_reason(opportunity: Mapping[str, Any] | None, *, current_side: str) -> str:
    if not isinstance(opportunity, Mapping):
        return ""
    action = str(opportunity.get("action") or "PASS")
    proposed_side = str(opportunity.get("side") or "").lower()
    if action != "PASS":
        if proposed_side in {"yes", "no"} and proposed_side != current_side:
            return f"Model side reversed from {current_side.upper()} to {proposed_side.upper()}."
        return ""
    reasons = opportunity.get("reasons")
    if not isinstance(reasons, (list, tuple)):
        return ""
    for reason in reasons:
        text = str(reason)
        if any(marker in text for marker in _RISK_EXIT_MARKERS):
            return text
    return ""


def _normalize_history(previous: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = previous if isinstance(previous, Mapping) else {}
    scans = raw.get("scans") if isinstance(raw.get("scans"), list) else []
    picks = raw.get("paper_picks") if isinstance(raw.get("paper_picks"), list) else []
    return {
        "version": 1,
        "updated_at": str(raw.get("updated_at") or ""),
        "scans": deepcopy(scans),
        "paper_picks": deepcopy(picks),
        "performance": deepcopy(raw.get("performance") if isinstance(raw.get("performance"), Mapping) else {}),
    }


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _side_outcome(pick: Mapping[str, Any]) -> float:
    outcome = 1.0 if bool(pick.get("outcome")) else 0.0
    return outcome if str(pick.get("side") or "yes").lower() == "yes" else 1.0 - outcome


def _pick_won(pick: Mapping[str, Any]) -> bool:
    return _side_outcome(pick) == 1.0
