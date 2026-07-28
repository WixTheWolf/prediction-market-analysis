"""Long-running live-data service for the prediction-market agent.

This service continuously reads public Kalshi market data, ranks opportunities,
persists snapshots, and exposes a tiny health endpoint. It never places orders.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .kalshi_scanner import KalshiScanner, ScannerConfig, rank_markets

LOGGER = logging.getLogger("prediction_agent")


class RuntimeState:
    def __init__(self) -> None:
        self.started_at = datetime.now(timezone.utc)
        self.last_success_at: datetime | None = None
        self.last_error: str | None = None
        self.cycles = 0
        self.markets_seen = 0
        self.top_markets: list[dict[str, object]] = []
        self.lock = threading.Lock()

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            return {
                "status": "ok" if self.last_error is None else "degraded",
                "started_at": self.started_at.isoformat(),
                "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
                "last_error": self.last_error,
                "cycles": self.cycles,
                "markets_seen": self.markets_seen,
                "top_markets": self.top_markets,
                "mode": "live-data-paper-only",
            }


class HealthHandler(BaseHTTPRequestHandler):
    state: RuntimeState

    def do_GET(self) -> None:  # noqa: N802
        if self.path not in {"/", "/health", "/status"}:
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps(self.state.snapshot()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.debug(format, *args)


def _serialize_market(market: object) -> dict[str, object]:
    raw = asdict(market)  # type: ignore[arg-type]
    for key, value in list(raw.items()):
        if hasattr(value, "isoformat"):
            raw[key] = value.isoformat()
    return raw


def _append_snapshot(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def run() -> int:
    interval = max(30, int(os.getenv("SCAN_INTERVAL_SECONDS", "300")))
    limit = max(1, int(os.getenv("SCAN_LIMIT", "250")))
    top = max(1, int(os.getenv("SCAN_TOP", "25")))
    min_volume = float(os.getenv("MIN_VOLUME", "10000"))
    max_spread = float(os.getenv("MAX_SPREAD", "0.08"))
    health_port = int(os.getenv("PORT", "8080"))
    snapshot_path = Path(os.getenv("SNAPSHOT_PATH", "output/live/market_snapshots.jsonl"))

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    state = RuntimeState()
    HealthHandler.state = state
    server = ThreadingHTTPServer(("0.0.0.0", health_port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    LOGGER.info("health endpoint listening on port %s", health_port)

    stop = threading.Event()

    def request_stop(signum: int, _frame: object) -> None:
        LOGGER.info("received signal %s; stopping", signum)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    config = ScannerConfig(min_volume=min_volume, max_spread=max_spread)
    with KalshiScanner(config=config) as scanner:
        while not stop.is_set():
            cycle_started = datetime.now(timezone.utc)
            try:
                scanned = scanner.scan(limit=limit)
                ranked = rank_markets(scanned)[:top]
                serializable = [_serialize_market(market) for market in ranked]
                payload = {
                    "captured_at": cycle_started.isoformat(),
                    "market_count": len(scanned),
                    "ranked": serializable,
                }
                _append_snapshot(snapshot_path, payload)
                with state.lock:
                    state.last_success_at = datetime.now(timezone.utc)
                    state.last_error = None
                    state.cycles += 1
                    state.markets_seen = len(scanned)
                    state.top_markets = serializable[:10]
                LOGGER.info("scan complete markets=%s ranked=%s", len(scanned), len(ranked))
            except Exception as exc:  # service boundary: log and retry
                LOGGER.exception("scan failed")
                with state.lock:
                    state.last_error = f"{type(exc).__name__}: {exc}"
                    state.cycles += 1
            stop.wait(interval)

    server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
