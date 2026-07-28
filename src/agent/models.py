from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass(frozen=True)
class MarketSnapshot:
    ticker: str
    title: str
    yes_price: float
    no_price: float
    volume: float
    open_interest: float = 0.0
    spread: float = 0.0
    closes_at: Optional[datetime] = None
    category: str = "unknown"
    rules_text: str = ""
    source: str = "kalshi"

    def __post_init__(self) -> None:
        for name, value in (("yes_price", self.yes_price), ("no_price", self.no_price)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.volume < 0 or self.open_interest < 0 or self.spread < 0:
            raise ValueError("volume, open_interest, and spread cannot be negative")


@dataclass(frozen=True)
class Signal:
    name: str
    probability: float
    confidence: float
    rationale: str
    weight: float = 1.0
    metadata: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be between 0 and 1")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.weight < 0:
            raise ValueError("weight cannot be negative")


@dataclass(frozen=True)
class TradeDecision:
    ticker: str
    side: str
    market_probability: float
    estimated_probability: float
    edge: float
    confidence: float
    recommended_fraction: float
    maximum_loss_usd: float
    action: str
    reasons: List[str]
    warnings: List[str]
