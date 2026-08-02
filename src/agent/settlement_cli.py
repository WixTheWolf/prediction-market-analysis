"""Grade awaiting paper picks against official Kalshi settlements."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .settlement import KalshiSettlementClient, resolve_paper_picks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve awaiting paper picks with official Kalshi results.")
    parser.add_argument("--history", required=True, help="Paper history JSON produced by src.agent.paper_history_cli")
    parser.add_argument("--output", default=None, help="Output path (defaults to updating --history in place)")
    parser.add_argument("--max-lookups", type=int, default=25)
    parser.add_argument("--resolved-at", default=None, help="ISO timestamp recorded on graded picks")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    history_path = Path(args.history)
    history = json.loads(history_path.read_text(encoding="utf-8"))
    resolved_at = args.resolved_at or datetime.now(timezone.utc).isoformat()

    with KalshiSettlementClient() as client:
        updated, resolved_count = resolve_paper_picks(
            history,
            client.fetch_result,
            resolved_at=resolved_at,
            max_lookups=max(0, args.max_lookups),
        )

    output = Path(args.output) if args.output else history_path
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    performance = updated.get("performance", {})
    print(
        f"Graded {resolved_count} pick(s); resolved={performance.get('resolved_picks', 0)} "
        f"win_rate={performance.get('win_rate')} realized=${performance.get('realized_pnl_usd', 0.0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
