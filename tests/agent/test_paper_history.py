from src.agent.paper_history import calculate_performance, update_paper_history


def _market(yes_price: float = 0.40) -> dict[str, object]:
    return {
        "ticker": "TEST-26",
        "title": "Will the test happen?",
        "yes_price": yes_price,
        "no_price": round(1.0 - yes_price, 2),
        "closes_at": "2026-09-01T00:00:00+00:00",
    }


def _opportunity() -> dict[str, object]:
    return {
        "ticker": "TEST-26",
        "title": "Will the test happen?",
        "side": "yes",
        "market_probability": 0.40,
        "model_probability": 0.58,
        "edge": 0.18,
        "confidence": 0.80,
        "action": "PAPER_BUY",
        "contracts": 25,
        "maximum_loss_usd": 10.0,
        "expected_value_usd": 4.5,
        "evidence": [{"name": "independent market", "source_url": "https://example.test"}],
    }


def test_opportunity_creates_one_paper_pick_and_scan() -> None:
    history = update_paper_history(
        {},
        [_market()],
        [_opportunity()],
        generated_at="2026-07-28T12:00:00+00:00",
        build_run="1",
    )
    assert len(history["scans"]) == 1
    assert len(history["paper_picks"]) == 1
    pick = history["paper_picks"][0]
    assert pick["status"] == "open"
    assert pick["contracts"] == 25
    assert history["performance"]["open_risk_usd"] == 10.0


def test_repeated_action_does_not_duplicate_open_pick_and_updates_mark() -> None:
    first = update_paper_history(
        {},
        [_market()],
        [_opportunity()],
        generated_at="2026-07-28T12:00:00+00:00",
    )
    second = update_paper_history(
        first,
        [_market(0.46)],
        [_opportunity()],
        generated_at="2026-07-28T12:15:00+00:00",
    )
    assert len(second["paper_picks"]) == 1
    assert second["paper_picks"][0]["current_price"] == 0.46
    assert second["paper_picks"][0]["marked_pnl_usd"] == 1.5
    assert len(second["scans"]) == 2


def test_missing_closed_market_moves_to_awaiting_resolution() -> None:
    first = update_paper_history(
        {},
        [_market()],
        [_opportunity()],
        generated_at="2026-07-28T12:00:00+00:00",
    )
    second = update_paper_history(
        first,
        [],
        [],
        generated_at="2026-09-02T12:00:00+00:00",
    )
    assert second["paper_picks"][0]["status"] == "awaiting_resolution"


def test_resolved_performance_calculates_win_rate_and_brier() -> None:
    picks = [
        {"side": "yes", "outcome": 1, "model_probability": 0.75, "realized_pnl_usd": 5.0, "status": "settled"},
        {"side": "no", "outcome": 1, "model_probability": 0.70, "realized_pnl_usd": -2.0, "status": "settled"},
    ]
    performance = calculate_performance(picks)
    assert performance["resolved_picks"] == 2
    assert performance["wins"] == 1
    assert performance["win_rate"] == 0.5
    assert performance["realized_pnl_usd"] == 3.0
    assert performance["brier_score"] is not None
