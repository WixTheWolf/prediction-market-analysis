"""Append-only decision journal for paper forecasts."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import MarketSnapshot, Signal, TradeDecision


class DecisionJournal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        market: MarketSnapshot,
        signals: Iterable[Signal],
        decision: TradeDecision,
        notes: str = "",
    ) -> dict[str, Any]:
        record = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "market": _jsonable(asdict(market)),
            "signals": [_jsonable(asdict(signal)) for signal in signals],
            "decision": _jsonable(asdict(decision)),
            "notes": notes,
            "status": "open",
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid journal JSON on line {line_number}") from exc
        return records


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
