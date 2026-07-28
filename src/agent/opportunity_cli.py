"""Build an auditable opportunity report from a market scan and forecast signals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import MarketSnapshot, Signal
from .opportunities import rank_opportunities


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank prediction-market opportunities from independent evidence.")
    parser.add_argument("--markets", required=True, help="JSON market scan produced by src.agent.cli")
    parser.add_argument("--signals", required=True, help="JSON mapping of ticker to independent forecast signals")
    parser.add_argument("--output", default="output/live/opportunities.json")
    parser.add_argument("--bankroll", type=float, default=1_000.0)
    parser.add_argument("--top", type=int, default=25)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    markets = _load_markets(Path(args.markets))
    signals = _load_signals(Path(args.signals))
    opportunities = rank_opportunities(markets, signals, bankroll_usd=args.bankroll)[: max(0, args.top)]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps([item.to_dict() for item in opportunities], indent=2), encoding="utf-8")
    print(f"Wrote {len(opportunities)} opportunities to {output}")
    return 0


def _load_markets(path: Path) -> list[MarketSnapshot]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [MarketSnapshot(**row) for row in rows]


def _load_signals(path: Path) -> dict[str, list[Signal]]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {ticker: [Signal(**item) for item in items] for ticker, items in raw.items()}


if __name__ == "__main__":
    raise SystemExit(main())
