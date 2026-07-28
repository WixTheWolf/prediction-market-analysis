from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Iterable, Sequence


_EPSILON = 1e-12


@dataclass(frozen=True)
class ForecastObservation:
    probability: float
    outcome: int
    market_close_probability: float | None = None
    pnl_usd: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be between 0 and 1")
        if self.outcome not in (0, 1):
            raise ValueError("outcome must be 0 or 1")
        if self.market_close_probability is not None and not 0.0 <= self.market_close_probability <= 1.0:
            raise ValueError("market_close_probability must be between 0 and 1")


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_forecast: float
    observed_rate: float


@dataclass(frozen=True)
class EvaluationReport:
    count: int
    brier_score: float
    log_loss: float
    accuracy: float
    mean_probability: float
    observed_rate: float
    calibration_error: float
    closing_line_value: float | None
    total_pnl_usd: float
    calibration_bins: tuple[CalibrationBin, ...]


def brier_score(observations: Iterable[ForecastObservation]) -> float:
    items = list(observations)
    _require_observations(items)
    return sum((item.probability - item.outcome) ** 2 for item in items) / len(items)


def binary_log_loss(observations: Iterable[ForecastObservation]) -> float:
    items = list(observations)
    _require_observations(items)
    losses = []
    for item in items:
        p = min(1.0 - _EPSILON, max(_EPSILON, item.probability))
        losses.append(-(item.outcome * log(p) + (1 - item.outcome) * log(1 - p)))
    return sum(losses) / len(losses)


def calibration_table(
    observations: Iterable[ForecastObservation],
    bins: int = 10,
) -> tuple[CalibrationBin, ...]:
    items = list(observations)
    _require_observations(items)
    if bins <= 0:
        raise ValueError("bins must be positive")

    groups: list[list[ForecastObservation]] = [[] for _ in range(bins)]
    for item in items:
        index = min(bins - 1, int(item.probability * bins))
        groups[index].append(item)

    result: list[CalibrationBin] = []
    for index, group in enumerate(groups):
        if not group:
            continue
        lower = index / bins
        upper = (index + 1) / bins
        result.append(
            CalibrationBin(
                lower=lower,
                upper=upper,
                count=len(group),
                mean_forecast=sum(item.probability for item in group) / len(group),
                observed_rate=sum(item.outcome for item in group) / len(group),
            )
        )
    return tuple(result)


def expected_calibration_error(calibration_bins: Sequence[CalibrationBin]) -> float:
    total = sum(item.count for item in calibration_bins)
    if total <= 0:
        raise ValueError("calibration_bins cannot be empty")
    return sum(
        item.count / total * abs(item.mean_forecast - item.observed_rate)
        for item in calibration_bins
    )


def closing_line_value(observations: Iterable[ForecastObservation]) -> float | None:
    comparable = [item for item in observations if item.market_close_probability is not None]
    if not comparable:
        return None
    return sum(item.probability - float(item.market_close_probability) for item in comparable) / len(comparable)


def evaluate_forecasts(
    observations: Iterable[ForecastObservation],
    bins: int = 10,
) -> EvaluationReport:
    items = list(observations)
    _require_observations(items)
    table = calibration_table(items, bins=bins)
    predicted = [1 if item.probability >= 0.5 else 0 for item in items]

    return EvaluationReport(
        count=len(items),
        brier_score=brier_score(items),
        log_loss=binary_log_loss(items),
        accuracy=sum(prediction == item.outcome for prediction, item in zip(predicted, items)) / len(items),
        mean_probability=sum(item.probability for item in items) / len(items),
        observed_rate=sum(item.outcome for item in items) / len(items),
        calibration_error=expected_calibration_error(table),
        closing_line_value=closing_line_value(items),
        total_pnl_usd=sum(item.pnl_usd for item in items),
        calibration_bins=table,
    )


def _require_observations(items: Sequence[ForecastObservation]) -> None:
    if not items:
        raise ValueError("at least one forecast observation is required")
