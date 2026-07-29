"""Generate auditable forecast signals from independent public sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cross_venue import PolymarketConfig, merge_signal_maps, signal_map_to_json
from .match_engine import PolymarketDiscoveryClient, build_recall_signals
from .models import MarketSnapshot, Signal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build independent evidence signals for prediction markets.")
    parser.add_argument("--markets", required=True, help="JSON market scan produced by src.agent.cli")
    parser.add_argument("--manual-signals", default="config/forecast_signals.json")
    parser.add_argument("--output", default="output/live/combined-signals.json")
    parser.add_argument("--metadata-output", default="output/live/evidence-metadata.json")
    parser.add_argument("--polymarket-limit", type=int, default=5_000)
    parser.add_argument("--min-liquidity", type=float, default=2_500.0)
    parser.add_argument("--min-volume", type=float, default=5_000.0)
    parser.add_argument("--min-similarity", type=float, default=0.60)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    markets = _load_markets(Path(args.markets))
    manual = _load_signals(Path(args.manual_signals))
    config = PolymarketConfig(
        max_markets=max(1, args.polymarket_limit),
        min_liquidity_usd=max(0.0, args.min_liquidity),
        min_volume_usd=max(0.0, args.min_volume),
        min_similarity=min(0.99, max(0.50, args.min_similarity)),
        max_expiration_gap_days=31,
    )

    source_status = "healthy"
    source_error = ""
    external_count = 0
    matches = []
    near_matches = []
    automatic: dict[str, list[Signal]] = {}
    try:
        with PolymarketDiscoveryClient(config=config) as client:
            external = client.fetch_active_markets()
        external_count = len(external)
        automatic, matches, near_matches = build_recall_signals(markets, external, config)
        if external_count == 0:
            source_status = "degraded"
            source_error = "Polymarket returned zero usable binary markets"
    except Exception as exc:  # evidence-source boundary; manual signals still publish
        source_status = "degraded"
        source_error = f"{type(exc).__name__}: {exc}"

    combined = merge_signal_maps(manual, automatic)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(signal_map_to_json(combined), indent=2), encoding="utf-8")

    metadata = {
        "source": "Polymarket Gamma API",
        "source_status": source_status,
        "source_error": source_error,
        "discovery_strategy": "volume + liquidity + endDate descending",
        "kalshi_markets_considered": len(markets),
        "external_markets_loaded": external_count,
        "cross_venue_matches": len(matches),
        "near_match_count": len(near_matches),
        "manual_signal_markets": len(manual),
        "combined_signal_markets": len(combined),
        "matches": [
            {
                "ticker": match.kalshi_ticker,
                "external_question": match.external_market.question,
                "external_probability": match.external_market.yes_probability,
                "similarity": match.similarity,
                "confidence": match.confidence,
                "source_url": match.external_market.source_url,
            }
            for match in matches
        ],
        "near_matches": [
            {
                "ticker": match.kalshi_ticker,
                "kalshi_question": match.kalshi_question,
                "external_question": match.external_question,
                "similarity": match.similarity,
                "rejection": match.rejection,
                "source_url": match.source_url,
            }
            for match in near_matches
        ],
    }
    metadata_output = Path(args.metadata_output)
    metadata_output.parent.mkdir(parents=True, exist_ok=True)
    metadata_output.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(
        f"Built {len(combined)} signal-bearing markets; {len(matches)} accepted and "
        f"{len(near_matches)} diagnostic near matches from {external_count} Polymarket markets"
    )
    return 0


def _load_markets(path: Path) -> list[MarketSnapshot]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("market scan must contain a JSON list")
    return [MarketSnapshot(**row) for row in rows]


def _load_signals(path: Path) -> dict[str, list[Signal]]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("manual signal file must contain a JSON object")
    return {
        str(ticker): [Signal(**item) for item in items]
        for ticker, items in raw.items()
        if isinstance(items, list)
    }


if __name__ == "__main__":
    raise SystemExit(main())
