"""Fail-closed authenticated Kalshi trading adapter.

The adapter supports account reads, order submission, cancellation, and
reconciliation. Production order writes require an approved OrderPlan plus a
second runtime confirmation token.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from .execution import OrderPlan
from .kalshi_auth import KalshiCredentials, sign_request


PRODUCTION_URL = "https://external-api.kalshi.com/trade-api/v2"
DEMO_URL = "https://external-api.demo.kalshi.co/trade-api/v2"


@dataclass(frozen=True)
class TradingConfig:
    base_url: str = DEMO_URL
    timeout_seconds: float = 15.0
    live_write_enabled: bool = False
    confirmation_token: str = ""

    @classmethod
    def from_environment(cls) -> "TradingConfig":
        environment = os.getenv("KALSHI_ENVIRONMENT", "demo").lower()
        base_url = PRODUCTION_URL if environment == "production" else DEMO_URL
        return cls(
            base_url=base_url,
            timeout_seconds=float(os.getenv("KALSHI_TIMEOUT_SECONDS", "15")),
            live_write_enabled=os.getenv("KALSHI_LIVE_WRITE_ENABLED", "false").lower() == "true",
            confirmation_token=os.getenv("KALSHI_LIVE_CONFIRMATION_TOKEN", ""),
        )


class KalshiTradingClient:
    def __init__(
        self,
        credentials: KalshiCredentials,
        config: TradingConfig | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.credentials = credentials
        self.config = config or TradingConfig.from_environment()
        self._client = client or httpx.Client(base_url=self.config.base_url, timeout=self.config.timeout_seconds)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "KalshiTradingClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_balance(self) -> dict[str, Any]:
        return self._request("GET", "/portfolio/balance")

    def get_positions(self) -> dict[str, Any]:
        return self._request("GET", "/portfolio/positions")

    def get_orders(self, status: str | None = None) -> dict[str, Any]:
        params = {"status": status} if status else None
        return self._request("GET", "/portfolio/orders", params=params)

    def submit_order(self, plan: OrderPlan, *, runtime_confirmation: str) -> dict[str, Any]:
        self._assert_write_allowed(plan, runtime_confirmation)
        payload = {
            "ticker": plan.ticker,
            "client_order_id": plan.client_order_id,
            "side": "bid",
            "outcome_side": plan.side.lower(),
            "count": f"{plan.contracts:.2f}",
            "price": f"{plan.limit_price:.4f}",
            "time_in_force": "fill_or_kill",
            "self_trade_prevention_type": "taker_at_cross",
            "cancel_order_on_pause": True,
        }
        return self._request("POST", "/portfolio/events/orders", json=payload)

    def cancel_order(self, order_id: str, *, runtime_confirmation: str) -> dict[str, Any]:
        self._assert_confirmation(runtime_confirmation)
        return self._request("DELETE", f"/portfolio/events/orders/{order_id}")

    def cancel_orders(self, orders: list[dict[str, Any]], *, runtime_confirmation: str) -> dict[str, Any]:
        self._assert_confirmation(runtime_confirmation)
        if not orders:
            return {"orders": []}
        return self._request("DELETE", "/portfolio/events/orders/batched", json={"orders": orders})

    def _assert_write_allowed(self, plan: OrderPlan, runtime_confirmation: str) -> None:
        if not plan.approved or plan.mode != "live":
            raise PermissionError("order plan is not approved for live submission")
        if plan.contracts < 1:
            raise ValueError("order plan has no contracts")
        self._assert_confirmation(runtime_confirmation)

    def _assert_confirmation(self, runtime_confirmation: str) -> None:
        if not self.config.live_write_enabled:
            raise PermissionError("authenticated writes are disabled")
        expected = self.config.confirmation_token
        if not expected or runtime_confirmation != expected:
            raise PermissionError("runtime confirmation token is invalid")

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = sign_request(self.credentials, method, f"/trade-api/v2{path}")
        response = self._client.request(method, path, headers=headers, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Kalshi response must be a JSON object")
        return payload
