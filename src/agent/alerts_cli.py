"""Write a markdown alert file when a scan surfaces new plays or arbitrage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .alerts import build_alert_body


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diff scans and emit an alert body for new signals.")
    parser.add_argument("--opportunities", required=True)
    parser.add_argument("--previous-opportunities", default=None)
    parser.add_argument("--arbitrage", default=None)
    parser.add_argument("--previous-arbitrage", default=None)
    parser.add_argument("--output", required=True, help="Alert markdown path; written empty when nothing is new")
    parser.add_argument("--dashboard-url", required=True)
    parser.add_argument("--generated-at", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    body = build_alert_body(
        _load_list(args.opportunities),
        _load_list(args.previous_opportunities),
        _load_list(args.arbitrage),
        _load_list(args.previous_arbitrage),
        dashboard_url=args.dashboard_url,
        generated_at=args.generated_at,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body or "", encoding="utf-8")
    print("Alert written" if body else "No new signals; alert file left empty")
    return 0


def _load_list(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    file = Path(path)
    if not file.exists():
        return []
    try:
        payload = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return payload if isinstance(payload, list) else []


if __name__ == "__main__":
    raise SystemExit(main())
