"""Verify actionable plays against live Kalshi order books."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .execution_quality import (
    DEFAULT_SLIPPAGE_TOLERANCE,
    KalshiMarketDataClient,
    annotate_opportunities,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Annotate opportunities with order-book fillability and momentum.")
    parser.add_argument("--opportunities", required=True, help="Opportunity JSON produced by src.agent.opportunity_cli")
    parser.add_argument("--output", default=None, help="Output path (defaults to updating --opportunities in place)")
    parser.add_argument("--max-checks", type=int, default=10)
    parser.add_argument("--slippage", type=float, default=DEFAULT_SLIPPAGE_TOLERANCE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.opportunities)
    opportunities = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(opportunities, list):
        raise SystemExit("opportunities file must contain a JSON list")

    with KalshiMarketDataClient() as client:
        annotated, downgrades = annotate_opportunities(
            opportunities,
            client.fetch_orderbook,
            client.fetch_recent_trades,
            max_checks=max(0, args.max_checks),
            slippage_tolerance=max(0.0, args.slippage),
        )

    output = Path(args.output) if args.output else path
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(annotated, indent=2), encoding="utf-8")
    checked = sum(1 for item in annotated if isinstance(item.get("execution"), dict))
    print(f"Execution-checked {checked} play(s); downgraded {downgrades} unfillable play(s) to PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
