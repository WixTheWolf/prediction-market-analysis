"""Decision-support agent for prediction markets.

The package is intentionally paper-trading first. Live execution should only be
added behind explicit configuration, position limits, and audit logging.
"""

from .evaluation import EvaluationReport, ForecastObservation, evaluate_forecasts
from .journal import DecisionJournal
from .kalshi_scanner import KalshiScanner, ScannerConfig, normalize_market, rank_markets
from .models import MarketSnapshot, Signal, TradeDecision
from .scoring import score_market

__all__ = [
    "DecisionJournal",
    "EvaluationReport",
    "ForecastObservation",
    "KalshiScanner",
    "MarketSnapshot",
    "ScannerConfig",
    "Signal",
    "TradeDecision",
    "evaluate_forecasts",
    "normalize_market",
    "rank_markets",
    "score_market",
]
