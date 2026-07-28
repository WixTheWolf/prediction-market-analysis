"""Command-line entry points for read-only market discovery."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .kalshi_scanner import KalshiScanner, ScannerConfig, rank_markets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan and rank Kalshi markets without placing orders.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum markets to request")
    parser.add_argument("--min-volume", type=float, default=10_000.0)
    parser.add_argument("--max-spread", type=float, default=0.08)
    parser.add_argument("--top", type=int, default=20, help="Number of ranked markets to print")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a table")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = ScannerConfig(min_volume=args.min_volume, max_spread=args.max_spread)
    with KalshiScanner(config=config) as scanner:
        markets = rank_markets(scanner.scan(limit=args.limit))[: max(0, args.top)]

    if args.json:
        print(json.dumps([_serializable(asdict(market)) for market in markets], indent=2))
        return 0

    print(f"{'TICKER':<28} {'YES':>6} {'NO':>6} {'SPREAD':>8} {'VOLUME':>12}  TITLE")
    for market in markets:
        title = market.title.replace("\n", " ")[:70]
        print(
            f"{market.ticker:<28} {market.yes_price:>6.1%} {market.no_price:>6.1%} "
            f"{market.spread:>8.1%} {market.volume:>12,.0f}  {title}"
        )
    return 0


def _serializable(value: object) -> object:
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[union-attr]
    if isinstance(value, dict):
        return {key: _serializable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serializable(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
