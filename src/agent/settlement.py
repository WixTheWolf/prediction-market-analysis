"""Resolve awaiting paper picks against official Kalshi settlement results.

The paper scorecard only earns trust once picks are graded against real
outcomes. This module looks up each awaiting pick's market on the public
Kalshi API and, when the exchange reports a final YES/NO result, records the
outcome and the realized paper P/L. Marks are never treated as settlements,
and a network failure leaves a pick untouched for the next run.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

import httpx

_SETTLED_STATUSES = {"settled", "finalized"}
_AWAITING_STATUS = "awaiting_resolution"


class KalshiSettlementClient:
    """Read-only lookups of market results on the public Kalshi API."""

    def __init__(
        self,
        base_url: str = "https://api.elections.kalshi.com/trade-api/v2",
        timeout_seconds: float = 15.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"User-Agent": "prediction-market-agent/0.4"},
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "KalshiSettlementClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_result(self, ticker: str) -> Optional[dict[str, str]]:
        """Return {"status": ..., "result": ...} or None when unavailable."""
        try:
            response = self._client.get(f"/markets/{ticker}")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        market = payload.get("market") if isinstance(payload, Mapping) else None
        if not isinstance(market, Mapping):
            return None
        return {
            "status": str(market.get("status") or "").lower(),
            "result": str(market.get("result") or "").lower(),
        }


def resolve_paper_picks(
    history: Mapping[str, Any],
    fetch_result: Callable[[str], Optional[dict[str, str]]],
    *,
    resolved_at: str,
    max_lookups: int = 25,
) -> tuple[dict[str, Any], int]:
    """Grade awaiting picks with official results; returns (history, resolved).

    ``calculate_performance`` is re-run afterwards so win rate, Brier score,
    and realized P/L reflect the newly graded picks.
    """
    from .paper_history import calculate_performance

    updated = dict(history)
    picks = [dict(pick) for pick in history.get("paper_picks", []) if isinstance(pick, Mapping)]
    lookups = 0
    resolved_count = 0

    for pick in picks:
        if str(pick.get("status") or "") != _AWAITING_STATUS:
            continue
        if lookups >= max_lookups:
            break
        ticker = str(pick.get("ticker") or "")
        if not ticker:
            continue
        lookups += 1
        settlement = fetch_result(ticker)
        if settlement is None or settlement.get("status") not in _SETTLED_STATUSES:
            continue

        result = settlement.get("result") or ""
        if result not in ("yes", "no"):
            # Voided or non-binary settlement: close flat rather than guess.
            pick["status"] = "voided"
            pick["resolved_at"] = resolved_at
            pick["close_reason"] = f"Market settled without a binary result ({result or 'unknown'})."
            pick["realized_pnl_usd"] = 0.0
            pick["marked_pnl_usd"] = 0.0
            resolved_count += 1
            continue

        side = str(pick.get("side") or "yes").lower()
        entry_price = float(pick.get("entry_price") or 0.0)
        contracts = int(pick.get("contracts") or 0)
        won = side == result
        payout = 1.0 if won else 0.0

        pick["status"] = "resolved"
        pick["resolved_at"] = resolved_at
        pick["outcome"] = 1 if result == "yes" else 0
        pick["realized_pnl_usd"] = round((payout - entry_price) * contracts, 2)
        pick["marked_pnl_usd"] = 0.0
        pick["current_price"] = payout
        resolved_count += 1

    updated["paper_picks"] = picks
    updated["performance"] = calculate_performance(picks)
    return updated, resolved_count
