"""Generate auditable forecast signals from independent public sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .cross_venue import PolymarketConfig, merge_signal_maps, signal_map_to_json
from .manifold import ManifoldConfig, ManifoldDiscoveryClient
from .match_engine import (
    NearMatch,
    PolymarketDiscoveryClient,
    build_recall_signals,
    dedupe_external_markets,
)
from .models import MarketSnapshot, Signal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build independent evidence signals for prediction markets.")
    parser.add_argument("--markets", required=True, help="JSON market scan produced by src.agent.cli")
    parser.add_argument("--manual-signals", default="config/forecast_signals.json")
    parser.add_argument("--output", default="output/live/combined-signals.json")
    parser.add_argument("--metadata-output", default="output/live/evidence-metadata.json")

    parser.add_argument("--polymarket-limit", type=int, default=5_000)
    parser.add_argument("--targeted-polymarket-queries", type=int, default=80)
    parser.add_argument("--min-liquidity", type=float, default=2_500.0)
    parser.add_argument("--min-volume", type=float, default=5_000.0)
    parser.add_argument("--min-similarity", type=float, default=0.58)

    parser.add_argument("--manifold-limit", type=int, default=4_000)
    parser.add_argument("--manifold-min-liquidity", type=float, default=500.0)
    parser.add_argument("--manifold-min-volume", type=float, default=1_000.0)
    parser.add_argument("--manifold-min-similarity", type=float, default=0.55)
    parser.add_argument("--disable-manifold", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    markets = _load_markets(Path(args.markets))
    manual = _load_signals(Path(args.manual_signals))

    signal_maps: list[dict[str, list[Signal]]] = [manual]
    all_matches = []
    all_near_matches: list[NearMatch] = []
    source_records: list[dict[str, Any]] = []

    polymarket_config = PolymarketConfig(
        max_markets=max(1, args.polymarket_limit),
        min_liquidity_usd=max(0.0, args.min_liquidity),
        min_volume_usd=max(0.0, args.min_volume),
        min_similarity=min(0.99, max(0.45, args.min_similarity)),
        max_expiration_gap_days=31,
    )
    try:
        with PolymarketDiscoveryClient(config=polymarket_config) as client:
            bulk = client.fetch_active_markets()
            targeted = client.fetch_targeted_markets(
                markets,
                max_queries=max(0, args.targeted_polymarket_queries),
            )
            targeted_queries = client.targeted_query_count
            targeted_errors = client.targeted_error_count
        external = dedupe_external_markets([*bulk, *targeted])
        signals, matches, near = build_recall_signals(markets, external, polymarket_config)
        signal_maps.append(signals)
        all_matches.extend(matches)
        all_near_matches.extend(near)
        source_records.append(
            {
                "name": "Polymarket",
                "api": "Gamma API",
                "status": "healthy" if external else "degraded",
                "error": "" if external else "Polymarket returned zero usable binary markets",
                "markets_loaded": len(external),
                "bulk_markets_loaded": len(bulk),
                "targeted_markets_loaded": len(targeted),
                "targeted_queries": targeted_queries,
                "targeted_query_errors": targeted_errors,
                "matches": len(matches),
                "near_matches": len(near),
            }
        )
    except Exception as exc:  # source boundary; other evidence still publishes
        source_records.append(_failed_source("Polymarket", "Gamma API", exc))

    if not args.disable_manifold:
        manifold_config = ManifoldConfig(
            max_markets=max(1, args.manifold_limit),
            min_liquidity_usd=max(0.0, args.manifold_min_liquidity),
            min_volume_usd=max(0.0, args.manifold_min_volume),
            min_similarity=min(0.99, max(0.45, args.manifold_min_similarity)),
            max_expiration_gap_days=45,
        )
        try:
            with ManifoldDiscoveryClient(config=manifold_config) as client:
                external = client.fetch_active_markets()
                request_errors = client.request_errors
            signals, matches, near = build_recall_signals(markets, external, manifold_config)  # type: ignore[arg-type]
            signal_maps.append(signals)
            all_matches.extend(matches)
            all_near_matches.extend(near)
            source_records.append(
                {
                    "name": "Manifold",
                    "api": "Public API",
                    "status": "healthy" if external else "degraded",
                    "error": "" if external else "Manifold returned zero usable binary markets",
                    "markets_loaded": len(external),
                    "request_errors": request_errors,
                    "matches": len(matches),
                    "near_matches": len(near),
                    "weighting": "lower-weight play-money crowd forecast",
                }
            )
        except Exception as exc:  # source boundary; Polymarket/manual evidence still publishes
            source_records.append(_failed_source("Manifold", "Public API", exc))

    combined = merge_signal_maps(*signal_maps)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(signal_map_to_json(combined), indent=2), encoding="utf-8")

    healthy_sources = [source for source in source_records if source.get("status") == "healthy"]
    degraded_sources = [source for source in source_records if source.get("status") != "healthy"]
    if healthy_sources and not degraded_sources:
        source_status = "healthy"
    elif healthy_sources:
        source_status = "partial"
    else:
        source_status = "degraded"
    source_error = "; ".join(
        f"{source.get('name')}: {source.get('error')}"
        for source in degraded_sources
        if source.get("error")
    )

    all_near_matches.sort(key=lambda item: item.similarity, reverse=True)
    metadata = {
        "source": "Polymarket Gamma API + Manifold Public API",
        "source_status": source_status,
        "source_error": source_error,
        "sources": source_records,
        "discovery_strategy": "ranked bulk slices + targeted search + independent second venue",
        "kalshi_markets_considered": len(markets),
        "external_markets_loaded": sum(int(source.get("markets_loaded", 0)) for source in source_records),
        "cross_venue_matches": len(all_matches),
        "near_match_count": len(all_near_matches),
        "manual_signal_markets": len(manual),
        "combined_signal_markets": len(combined),
        "matches": [
            {
                "ticker": match.kalshi_ticker,
                "source": str(getattr(match.external_market, "source_name", "Polymarket")),
                "external_question": match.external_market.question,
                "external_probability": match.external_market.yes_probability,
                "similarity": match.similarity,
                "confidence": match.confidence,
                "source_url": match.external_market.source_url,
            }
            for match in all_matches
        ],
        "near_matches": [
            {
                "ticker": match.kalshi_ticker,
                "source": match.source,
                "kalshi_question": match.kalshi_question,
                "external_question": match.external_question,
                "similarity": match.similarity,
                "rejection": match.rejection,
                "source_url": match.source_url,
            }
            for match in all_near_matches[:100]
        ],
    }
    metadata_output = Path(args.metadata_output)
    metadata_output.parent.mkdir(parents=True, exist_ok=True)
    metadata_output.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(
        f"Built {len(combined)} signal-bearing markets; {len(all_matches)} accepted and "
        f"{len(all_near_matches)} diagnostic near matches from "
        f"{metadata['external_markets_loaded']} external markets"
    )
    return 0


def _failed_source(name: str, api: str, exc: Exception) -> dict[str, Any]:
    return {
        "name": name,
        "api": api,
        "status": "degraded",
        "error": f"{type(exc).__name__}: {exc}",
        "markets_loaded": 0,
        "matches": 0,
        "near_matches": 0,
    }


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
