"""Order-book fillability and momentum context for actionable plays.

A quoted edge is only real if the recommended contracts can actually be
filled near the displayed price, so each actionable play is checked against
the live Kalshi order book: plays with zero resting depth are downgraded to
PASS, and plays with thin depth have their contracts and risk capped at what
is fillable. Recent trade momentum is attached as context — a price that
moved sharply in the last hour, or a book with no trades for a day, both mean
the displayed edge deserves suspicion.

Everything here is read-only and fail-soft: a failed lookup annotates the
play instead of blocking the pipeline, and no annotation ever upgrades a
play or increases its size.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional

import httpx

DEFAULT_SLIPPAGE_TOLERANCE = 0.02
MOMENTUM_WARNING_MOVE_1H = 0.08
STALE_QUOTE_MINUTES = 24 * 60


class KalshiMarketDataClient:
    """Read-only order-book and trade lookups on the public Kalshi API."""

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

    def __enter__(self) -> "KalshiMarketDataClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_orderbook(self, ticker: str) -> Optional[dict[str, list[tuple[float, float]]]]:
        """Return {"yes": [(price, count), ...], "no": ...} bids, or None."""
        try:
            response = self._client.get(f"/markets/{ticker}/orderbook")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        orderbook = payload.get("orderbook") if isinstance(payload, Mapping) else None
        if not isinstance(orderbook, Mapping):
            return None
        return {
            "yes": _parse_levels(orderbook, "yes"),
            "no": _parse_levels(orderbook, "no"),
        }

    def fetch_recent_trades(self, ticker: str, limit: int = 100) -> Optional[list[dict[str, Any]]]:
        try:
            response = self._client.get("/markets/trades", params={"ticker": ticker, "limit": limit})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        trades = payload.get("trades") if isinstance(payload, Mapping) else None
        if not isinstance(trades, list):
            return None
        parsed = []
        for trade in trades:
            if not isinstance(trade, Mapping):
                continue
            price = _price(trade.get("yes_price_dollars"), trade.get("yes_price"), trade.get("price"))
            created = _parse_datetime(trade.get("created_time") or trade.get("ts"))
            if price is None or created is None:
                continue
            parsed.append({"yes_price": price, "created_time": created})
        return parsed


def fillable_depth(
    orderbook: Mapping[str, list[tuple[float, float]]],
    side: str,
    limit_price: float,
    *,
    slippage_tolerance: float = DEFAULT_SLIPPAGE_TOLERANCE,
) -> tuple[int, Optional[float]]:
    """Contracts available to BUY ``side`` within tolerance of ``limit_price``.

    Kalshi books list resting bids per side; buying YES crosses against NO
    bids (implied YES ask = 1 - NO bid) and vice versa. Returns the fillable
    contract count and the volume-weighted average fill price.
    """
    opposing = orderbook.get("no" if side == "yes" else "yes", [])
    ceiling = round(limit_price + slippage_tolerance, 6)
    fills: list[tuple[float, float]] = []
    for bid_price, count in opposing:
        implied_ask = round(1.0 - bid_price, 4)
        if implied_ask <= ceiling and count > 0:
            fills.append((implied_ask, count))
    if not fills:
        return 0, None
    fills.sort(key=lambda level: level[0])
    total = sum(count for _, count in fills)
    average = sum(price * count for price, count in fills) / total
    return int(total), round(average, 4)


def assess_momentum(trades: list[Mapping[str, Any]], *, now: datetime) -> dict[str, Any]:
    """Summarize recent YES-price movement and trade recency."""
    ordered = sorted(trades, key=lambda trade: trade["created_time"])
    if not ordered:
        return {"trades_seen": 0, "minutes_since_last_trade": None, "move_1h": None, "move_24h": None}

    latest = ordered[-1]
    minutes_since = (now - latest["created_time"]).total_seconds() / 60.0
    return {
        "trades_seen": len(ordered),
        "last_price": latest["yes_price"],
        "minutes_since_last_trade": round(max(0.0, minutes_since), 1),
        "move_1h": _move_since(ordered, now - timedelta(hours=1)),
        "move_24h": _move_since(ordered, now - timedelta(hours=24)),
    }


def annotate_opportunities(
    opportunities: list[dict[str, Any]],
    fetch_orderbook: Callable[[str], Optional[Mapping[str, list[tuple[float, float]]]]],
    fetch_trades: Callable[[str], Optional[list[Mapping[str, Any]]]],
    *,
    now: Optional[datetime] = None,
    max_checks: int = 10,
    slippage_tolerance: float = DEFAULT_SLIPPAGE_TOLERANCE,
) -> tuple[list[dict[str, Any]], int]:
    """Annotate actionable plays in place; returns (opportunities, downgrades)."""
    now = now or datetime.now(timezone.utc)
    checks = 0
    downgrades = 0
    for opportunity in opportunities:
        if str(opportunity.get("action") or "PASS") == "PASS":
            continue
        if checks >= max_checks:
            break
        checks += 1
        ticker = str(opportunity.get("ticker") or "")
        side = str(opportunity.get("side") or "yes").lower()
        quoted_price = float(opportunity.get("market_probability") or 0.0)
        contracts = int(opportunity.get("contracts") or 0)
        reasons = list(opportunity.get("reasons") or [])

        orderbook = fetch_orderbook(ticker)
        if orderbook is None:
            opportunity["execution"] = {"status": "unavailable"}
            reasons.append("Order book unavailable; fill quality not verified.")
        else:
            fillable, average_price = fillable_depth(
                orderbook, side, quoted_price, slippage_tolerance=slippage_tolerance
            )
            opportunity["execution"] = {
                "status": "checked",
                "fillable_contracts": fillable,
                "average_fill_price": average_price,
                "slippage_tolerance": slippage_tolerance,
            }
            if fillable <= 0:
                opportunity["action"] = "PASS"
                opportunity["contracts"] = 0
                opportunity["maximum_loss_usd"] = 0.0
                opportunity["expected_value_usd"] = 0.0
                reasons.append(
                    f"No resting depth to fill {side.upper()} within "
                    f"{slippage_tolerance:.0%} of the quote; downgraded to PASS."
                )
                downgrades += 1
            elif contracts > 0 and fillable < contracts:
                scale = fillable / contracts
                opportunity["contracts"] = fillable
                opportunity["maximum_loss_usd"] = round(float(opportunity.get("maximum_loss_usd") or 0.0) * scale, 2)
                opportunity["expected_value_usd"] = round(
                    float(opportunity.get("expected_value_usd") or 0.0) * scale, 2
                )
                reasons.append(f"Depth-capped from {contracts} to {fillable} fillable contracts.")

        trades = fetch_trades(ticker)
        if trades is not None:
            momentum = assess_momentum(list(trades), now=now)
            opportunity["momentum"] = momentum
            move_1h = momentum.get("move_1h")
            minutes_since = momentum.get("minutes_since_last_trade")
            if move_1h is not None and abs(move_1h) >= MOMENTUM_WARNING_MOVE_1H:
                reasons.append(f"Price moved {move_1h:+.0%} in the last hour; the quoted edge may already be gone.")
            if minutes_since is not None and minutes_since >= STALE_QUOTE_MINUTES:
                reasons.append("No trades in the last 24h; quotes may be stale.")

        opportunity["reasons"] = reasons
    return opportunities, downgrades


def _parse_levels(orderbook: Mapping[str, Any], key: str) -> list[tuple[float, float]]:
    raw = orderbook.get(f"{key}_dollars")
    if not isinstance(raw, list):
        raw = orderbook.get(key)
    levels: list[tuple[float, float]] = []
    if not isinstance(raw, list):
        return levels
    for entry in raw:
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        price = _price(entry[0])
        try:
            count = float(entry[1])
        except (TypeError, ValueError):
            continue
        if price is not None and count > 0:
            levels.append((price, count))
    return levels


def _price(*candidates: Any) -> Optional[float]:
    for value in candidates:
        if value in (None, ""):
            continue
        try:
            price = float(value)
        except (TypeError, ValueError):
            continue
        if price > 1.0:
            price /= 100.0
        if 0.0 < price < 1.0:
            return round(price, 4)
    return None


def _move_since(ordered_trades: list[Mapping[str, Any]], cutoff: datetime) -> Optional[float]:
    baseline = None
    for trade in ordered_trades:
        if trade["created_time"] <= cutoff:
            baseline = trade["yes_price"]
        else:
            break
    if baseline is None:
        return None
    return round(ordered_trades[-1]["yes_price"] - baseline, 4)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
