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
        self.market_count = 0

    def snapshot(self) -> dict[str, object]:
        return {
            "started_at": self.started_at.isoformat(),
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "last_error": self.last_error,
            "cycles": self.cycles,
            "market_count": self.market_count,
            "healthy": self.last_error is None,
            "mode": "read-only",
        }


class MarketAgentService:
    def __init__(self) -> None:
        self.interval_seconds = max(30, int(os.getenv("SCAN_INTERVAL_SECONDS", "300")))
        self.limit = max(1, min(1_000, int(os.getenv("SCAN_LIMIT", "250"))))
        self.top = max(1, int(os.getenv("SCAN_TOP", "25")))
        self.output_path = Path(os.getenv("SNAPSHOT_PATH", "output/live/market_snapshots.jsonl"))
        self.config = ScannerConfig(
            min_volume=float(os.getenv("MIN_VOLUME", "10000")),
            max_spread=float(os.getenv("MAX_SPREAD", "0.08")),
        )
        self.state = RuntimeState()
        self.stop_event = threading.Event()

    def run(self) -> None:
        LOGGER.info("starting prediction-market service in read-only mode")
        while not self.stop_event.is_set():
            self.run_cycle()
            self.stop_event.wait(self.interval_seconds)

    def run_cycle(self) -> None:
        self.state.cycles += 1
        try:
            with KalshiScanner(config=self.config) as scanner:
                markets = rank_markets(scanner.scan(limit=self.limit))[: self.top]
            self._append_snapshot(markets)
            self.state.market_count = len(markets)
            self.state.last_success_at = datetime.now(timezone.utc)
            self.state.last_error = None
            LOGGER.info("scan completed with %s markets", len(markets))
        except Exception as exc:
            self.state.last_error = str(exc)
            LOGGER.exception("scan failed")

    def stop(self, *_: object) -> None:
        LOGGER.info("shutdown requested")
        self.stop_event.set()

    def _append_snapshot(self, markets: list[object]) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "mode": "read-only",
            "markets": [asdict(market) for market in markets],
        }
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=_json_default, separators=(",", ":")) + "\n")


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def build_handler(state: RuntimeState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in {"/", "/health", "/status"}:
                self.send_error(404)
                return
            payload = json.dumps(state.snapshot()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format_string: str, *args: object) -> None:
            LOGGER.debug(format_string, *args)

    return Handler


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    service = MarketAgentService()
    signal.signal(signal.SIGTERM, service.stop)
    signal.signal(signal.SIGINT, service.stop)

    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), build_handler(service.state))
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    LOGGER.info("health server listening on port %s", port)

    try:
        service.run()
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
