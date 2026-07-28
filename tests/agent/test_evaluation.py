import pytest

from src.agent.evaluation import (
    ForecastObservation,
    binary_log_loss,
    brier_score,
    evaluate_forecasts,
)


def test_evaluation_report_tracks_core_metrics() -> None:
    observations = [
        ForecastObservation(0.80, 1, market_close_probability=0.72, pnl_usd=18.0),
        ForecastObservation(0.65, 1, market_close_probability=0.61, pnl_usd=9.0),
        ForecastObservation(0.30, 0, market_close_probability=0.35, pnl_usd=7.0),
        ForecastObservation(0.55, 0, market_close_probability=0.52, pnl_usd=-10.0),
    ]

    report = evaluate_forecasts(observations, bins=5)

    assert report.count == 4
    assert report.brier_score == pytest.approx(brier_score(observations))
    assert report.log_loss == pytest.approx(binary_log_loss(observations))
    assert report.accuracy == pytest.approx(0.75)
    assert report.closing_line_value == pytest.approx(0.025)
    assert report.total_pnl_usd == pytest.approx(24.0)
    assert sum(item.count for item in report.calibration_bins) == 4


def test_perfect_forecasts_have_zero_brier_score() -> None:
    observations = [ForecastObservation(1.0, 1), ForecastObservation(0.0, 0)]

    report = evaluate_forecasts(observations)

    assert report.brier_score == pytest.approx(0.0)
    assert report.accuracy == pytest.approx(1.0)
    assert report.closing_line_value is None


def test_rejects_invalid_observations_and_empty_reports() -> None:
    with pytest.raises(ValueError):
        ForecastObservation(1.2, 1)
    with pytest.raises(ValueError):
        ForecastObservation(0.5, 2)
    with pytest.raises(ValueError):
        evaluate_forecasts([])
