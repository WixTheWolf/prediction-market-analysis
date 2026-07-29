from src.agent.paper_history import update_paper_history


def test_active_pick_is_closed_when_portfolio_guard_blocks_it() -> None:
    previous = {
        "scans": [],
        "paper_picks": [
            {
                "id": "TEST:yes:old",
                "ticker": "TEST",
                "title": "Test",
                "side": "yes",
                "status": "open",
                "opened_at": "2026-07-28T12:00:00+00:00",
                "closes_at": "2026-09-01T00:00:00+00:00",
                "entry_price": 0.40,
                "current_price": 0.40,
                "model_probability": 0.70,
                "entry_edge": 0.30,
                "confidence": 0.80,
                "contracts": 25,
                "maximum_loss_usd": 10.0,
                "expected_value_usd": 7.5,
                "marked_pnl_usd": 0.0,
                "realized_pnl_usd": None,
                "outcome": None,
                "evidence": [],
            }
        ],
        "performance": {},
    }
    markets = [
        {
            "ticker": "TEST",
            "title": "Test",
            "yes_price": 0.46,
            "no_price": 0.55,
            "closes_at": "2026-09-01T00:00:00+00:00",
        }
    ]
    opportunities = [
        {
            "ticker": "TEST",
            "side": "yes",
            "action": "PASS",
            "model_probability": 0.70,
            "edge": 0.24,
            "reasons": ["Portfolio risk cap reached."],
        }
    ]

    history = update_paper_history(
        previous,
        markets,
        opportunities,
        generated_at="2026-07-28T12:15:00+00:00",
    )
    pick = history["paper_picks"][0]
    assert pick["status"] == "closed_by_risk_guard"
    assert pick["realized_pnl_usd"] == 1.5
    assert pick["marked_pnl_usd"] == 0.0
    assert history["performance"]["open_risk_usd"] == 0.0
    assert history["performance"]["realized_pnl_usd"] == 1.5
