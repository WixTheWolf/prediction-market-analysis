import json
from datetime import datetime, timezone

from src.agent.service import RuntimeState, _append_snapshot


def test_runtime_state_reports_live_paper_mode() -> None:
    state = RuntimeState()
    with state.lock:
        state.last_success_at = datetime.now(timezone.utc)
        state.cycles = 2
        state.markets_seen = 42

    snapshot = state.snapshot()

    assert snapshot["status"] == "ok"
    assert snapshot["mode"] == "live-data-paper-only"
    assert snapshot["cycles"] == 2
    assert snapshot["markets_seen"] == 42


def test_append_snapshot_is_jsonl(tmp_path) -> None:
    path = tmp_path / "live" / "snapshots.jsonl"
    _append_snapshot(path, {"captured_at": "2026-01-01T00:00:00+00:00", "market_count": 3})
    _append_snapshot(path, {"captured_at": "2026-01-01T00:05:00+00:00", "market_count": 4})

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["market_count"] for row in rows] == [3, 4]
