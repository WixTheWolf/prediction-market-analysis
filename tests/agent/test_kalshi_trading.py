import base64

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.agent.execution import OrderPlan
from src.agent.kalshi_auth import KalshiCredentials, sign_request
from src.agent.kalshi_trading import KalshiTradingClient, TradingConfig


def credentials() -> KalshiCredentials:
    return KalshiCredentials(key_id="test-key", private_key=rsa.generate_private_key(public_exponent=65537, key_size=2048))


def approved_plan() -> OrderPlan:
    return OrderPlan(
        client_order_id="pma-test",
        ticker="TEST-YES",
        side="yes",
        limit_price=0.42,
        contracts=10,
        maximum_loss_usd=4.2,
        created_at="2026-01-01T00:00:00+00:00",
        mode="live",
        approved=True,
        blockers=(),
    )


def test_sign_request_builds_required_headers() -> None:
    headers = sign_request(credentials(), "GET", "/trade-api/v2/portfolio/balance?x=1", "1700000000000")
    assert headers["KALSHI-ACCESS-KEY"] == "test-key"
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1700000000000"
    assert base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])


def test_submit_order_fails_closed_when_writes_disabled() -> None:
    client = KalshiTradingClient(credentials(), TradingConfig(live_write_enabled=False))
    with pytest.raises(PermissionError):
        client.submit_order(approved_plan(), runtime_confirmation="anything")
    client.close()


def test_submit_order_requires_matching_confirmation_and_uses_v2_payload() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        return httpx.Response(201, json={"order": {"order_id": "123"}})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(base_url="https://example.test/trade-api/v2", transport=transport)
    config = TradingConfig(base_url="https://example.test/trade-api/v2", live_write_enabled=True, confirmation_token="confirm")
    client = KalshiTradingClient(credentials(), config, http_client)

    with pytest.raises(PermissionError):
        client.submit_order(approved_plan(), runtime_confirmation="wrong")

    result = client.submit_order(approved_plan(), runtime_confirmation="confirm")
    assert result["order"]["order_id"] == "123"
    assert seen["path"] == "/trade-api/v2/portfolio/events/orders"
    assert '"outcome_side":"yes"' in str(seen["body"])
    assert '"cancel_order_on_pause":true' in str(seen["body"])
    http_client.close()


def test_unapproved_plan_cannot_be_submitted() -> None:
    plan = OrderPlan(**{**approved_plan().__dict__, "approved": False, "blockers": ("blocked",)})
    config = TradingConfig(live_write_enabled=True, confirmation_token="confirm")
    client = KalshiTradingClient(credentials(), config)
    with pytest.raises(PermissionError):
        client.submit_order(plan, runtime_confirmation="confirm")
    client.close()
