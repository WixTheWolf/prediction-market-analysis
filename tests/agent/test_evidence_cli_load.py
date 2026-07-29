import json
from datetime import datetime

from src.agent.evidence_cli import _load_markets


def test_load_markets_parses_serialized_close_time(tmp_path) -> None:
    path = tmp_path / "markets.json"
    path.write_text(
        json.dumps(
            [
                {
                    "ticker": "TEST",
                    "title": "Will the test event happen?",
                    "yes_price": 0.42,
                    "no_price": 0.59,
                    "volume": 10_000,
                    "open_interest": 5_000,
                    "spread": 0.02,
                    "closes_at": "2026-09-30T00:00:00+00:00",
                    "category": "TEST",
                    "rules_text": "Resolves Yes if the event occurs.",
                }
            ]
        ),
        encoding="utf-8",
    )
    markets = _load_markets(path)
    assert len(markets) == 1
    assert isinstance(markets[0].closes_at, datetime)
    assert markets[0].closes_at.isoformat() == "2026-09-30T00:00:00+00:00"
