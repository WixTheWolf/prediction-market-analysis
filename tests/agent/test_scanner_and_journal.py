from pathlib import Path

from src.agent.journal import DecisionJournal
from src.agent.kalshi_scanner import normalize_market, rank_markets
from src.agent.models import Signal
from src.agent.scoring import score_market


def test_normalizes_cent_prices_and_spread() -> None:
    market = normalize_market(
        {
            "ticker": "TEST-26",
            "title": "Will the test happen?",
            "yes_bid": 42,
            "yes_ask": 45,
            "no_bid": 55,
            "no_ask": 58,
            "volume": 25_000,
            "open_interest": 3_000,
            "close_time": "2026-09-01T00:00:00Z",
            "rules_primary": "Resolves yes if the official source confirms the event.",
        }
    )

    assert market.yes_price == 0.45
    assert market.no_price == 0.58
    assert market.spread == 0.03
    assert market.closes_at is not None


def test_normalizes_current_dollar_and_fixed_point_fields() -> None:
    market = normalize_market(
        {
            "ticker": "CURRENT-26",
            "title": "Current schema market",
            "yes_bid_dollars": "0.4200",
            "yes_ask_dollars": "0.4500",
            "no_bid_dollars": "0.5500",
            "no_ask_dollars": "0.5800",
            "last_price_dollars": "0.4400",
            "volume_fp": "25123.50",
            "open_interest_fp": "3010.25",
            "latest_expiration_time": "2026-09-01T00:00:00Z",
        }
    )

    assert market.yes_price == 0.45
    assert market.no_price == 0.58
    assert market.spread == 0.03
    assert market.volume == 25_123.5
    assert market.open_interest == 3_010.25
    assert market.closes_at is not None


def test_ranking_prefers_tighter_spread_then_volume() -> None:
    first = normalize_market({"ticker": "A", "yes_ask": 50, "no_ask": 51, "yes_bid": 49, "volume": 10_000})
    second = normalize_market({"ticker": "B", "yes_ask": 50, "no_ask": 54, "yes_bid": 46, "volume": 100_000})

    ranked = rank_markets([second, first])

    assert ranked[0].ticker == "A"


def test_journal_round_trip(tmp_path: Path) -> None:
    market = normalize_market(
        {
            "ticker": "JOURNAL",
            "title": "Journal test",
            "yes_ask": 40,
            "no_ask": 61,
            "volume": 50_000,
            "rules_primary": "Clear official resolution rules.",
        }
    )
    signals = [Signal("research", 0.55, 0.8, "Primary sources support yes.")]
    decision = score_market(market, signals, bankroll_usd=1_000)
    journal = DecisionJournal(tmp_path / "decisions.jsonl")

    journal.append(market, signals, decision, notes="paper only")
    records = journal.read_all()

    assert len(records) == 1
    assert records[0]["market"]["ticker"] == "JOURNAL"
    assert records[0]["notes"] == "paper only"
