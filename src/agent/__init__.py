"""Decision-support agent for prediction markets.

The package is intentionally paper-trading first. Live execution should only be
added behind explicit configuration, position limits, and audit logging.
"""

from .models import MarketSnapshot, Signal, TradeDecision
from .scoring import score_market

__all__ = ["MarketSnapshot", "Signal", "TradeDecision", "score_market"]
