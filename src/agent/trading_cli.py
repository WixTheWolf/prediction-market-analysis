"""Operator CLI for authenticated Kalshi account checks.

Read commands are safe for demo or production. This CLI intentionally does not
accept arbitrary order parameters; orders must originate from a risk-approved
OrderPlan produced by the agent.
"""

from __future__ import annotations

import argparse
import json

from .kalshi_auth import KalshiCredentials
from .kalshi_trading import KalshiTradingClient, TradingConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Authenticated Kalshi account diagnostics")
    parser.add_argument("command", choices=("balance", "positions", "orders"))
    parser.add_argument("--status", choices=("resting", "canceled", "executed"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    credentials = KalshiCredentials.from_environment()
    config = TradingConfig.from_environment()
    with KalshiTradingClient(credentials, config) as client:
        if args.command == "balance":
            payload = client.get_balance()
        elif args.command == "positions":
            payload = client.get_positions()
        else:
            payload = client.get_orders(status=args.status)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
