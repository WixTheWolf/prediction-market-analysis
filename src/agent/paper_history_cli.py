"""Update the persistent paper ledger used by the static dashboard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .paper_history import update_paper_history


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update paper picks, scan history, and performance metrics.")
    parser.add_argument("--previous", required=True, help="Previously published history JSON")
    parser.add_argument("--markets", required=True, help="Current normalized market scan JSON")
    parser.add_argument("--opportunities", required=True, help="Current opportunity report JSON")
    parser.add_argument("--output", required=True, help="Output history JSON")
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--build-run", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    previous = _load_object(Path(args.previous))
    markets = _load_list(Path(args.markets))
    opportunities = _load_list(Path(args.opportunities))
    history = update_paper_history(
        previous,
        markets,
        opportunities,
        generated_at=args.generated_at,
        build_run=args.build_run,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(history, indent=2), encoding="utf-8")
    print(
        f"Recorded {len(history['scans'])} scans and {len(history['paper_picks'])} paper picks; "
        f"{history['performance']['resolved_picks']} resolved"
    )
    return 0


def _load_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _load_list(path: Path) -> list[dict[str, object]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"{path} must contain a JSON list")
    return [row for row in value if isinstance(row, dict)]


if __name__ == "__main__":
    raise SystemExit(main())
