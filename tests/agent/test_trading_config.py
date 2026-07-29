import os

from src.agent.kalshi_trading import DEMO_URL, PRODUCTION_URL, TradingConfig


def test_environment_defaults_to_demo_and_writes_disabled(monkeypatch) -> None:
    monkeypatch.delenv("KALSHI_ENVIRONMENT", raising=False)
    monkeypatch.delenv("KALSHI_LIVE_WRITE_ENABLED", raising=False)
    config = TradingConfig.from_environment()
    assert config.base_url == DEMO_URL
    assert config.live_write_enabled is False


def test_production_url_requires_explicit_environment(monkeypatch) -> None:
    monkeypatch.setenv("KALSHI_ENVIRONMENT", "production")
    monkeypatch.setenv("KALSHI_LIVE_WRITE_ENABLED", "false")
    config = TradingConfig.from_environment()
    assert config.base_url == PRODUCTION_URL
    assert config.live_write_enabled is False
