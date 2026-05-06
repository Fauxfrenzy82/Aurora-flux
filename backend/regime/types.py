"""
Market regime type definitions.
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


class MarketRegime(str, Enum):
    """Market regime classifications."""
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    STRONG_TREND_UP = "STRONG_TREND_UP"
    STRONG_TREND_DOWN = "STRONG_TREND_DOWN"
    RANGE_BOUND = "RANGE_BOUND"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    VOLATILITY_CONTRACTION = "VOLATILITY_CONTRACTION"
    TRANSITION = "TRANSITION"
    RISK_OFF = "RISK_OFF"
    UNCERTAIN = "UNCERTAIN"

    @property
    def is_trending(self) -> bool:
        """Check if regime is trending."""
        return self in (
            MarketRegime.TRENDING_UP,
            MarketRegime.TRENDING_DOWN,
            MarketRegime.STRONG_TREND_UP,
            MarketRegime.STRONG_TREND_DOWN,
        )

    @property
    def is_ranging(self) -> bool:
        """Check if regime is range-bound."""
        return self == MarketRegime.RANGE_BOUND

    @property
    def direction(self) -> int:
        """Return 1 for bullish, -1 for bearish, 0 for neutral."""
        if self in (MarketRegime.TRENDING_UP, MarketRegime.STRONG_TREND_UP):
            return 1
        elif self in (MarketRegime.TRENDING_DOWN, MarketRegime.STRONG_TREND_DOWN):
            return -1
        return 0


@dataclass(frozen=True)
class RegimeVote:
    """A single classifier's regime vote."""
    regime: MarketRegime
    confidence: float
    reason: str = ""


@dataclass
class RegimeClassification:
    """Complete market regime classification result."""
    regime: MarketRegime
    confidence: float
    timestamp: datetime
    technical_vote: RegimeVote
    pattern_vote: Optional[RegimeVote] = None
    ml_vote: Optional[RegimeVote] = None
    adx: float = 0.0
    ema_alignment: float = 0.0
    volatility_ratio: float = 1.0
    volume_ratio: float = 1.0
    hurst_exponent: float = 0.5
    entropy: float = 0.5
    is_transitioning: bool = False
    previous_regime: Optional[MarketRegime] = None
    regime_duration_bars: int = 0
    pair: str = ""
    timeframe: str = "H1"

    def tradeable(self, min_confidence: float = 0.65) -> bool:
        """Determine if this regime is tradeable."""
        if self.regime in (
            MarketRegime.UNCERTAIN,
            MarketRegime.RISK_OFF,
        ):
            return False
        if self.confidence < min_confidence:
            return False
        if self.is_transitioning:
            return False
        return True

    def is_bullish(self) -> bool:
        """Check if regime is bullish."""
        return self.regime.direction > 0

    def is_bearish(self) -> bool:
        """Check if regime is bearish."""
        return self.regime.direction < 0

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "regime": self.regime.value,
            "confidence": round(self.confidence, 4),
            "timestamp": self.timestamp.isoformat(),
            "adx": round(self.adx, 2),
            "ema_alignment": round(self.ema_alignment, 4),
            "volatility_ratio": round(self.volatility_ratio, 2),
            "volume_ratio": round(self.volume_ratio, 2),
            "hurst_exponent": round(self.hurst_exponent, 3),
            "entropy": round(self.entropy, 3),
            "is_transitioning": self.is_transitioning,
            "regime_duration_bars": self.regime_duration_bars,
            "tradeable": self.tradeable(),
        }


def create_default_classification() -> RegimeClassification:
    """Create a default/neutral classification."""
    return RegimeClassification(
        regime=MarketRegime.UNCERTAIN,
        confidence=0.5,
        timestamp=datetime.now(timezone.utc),
        technical_vote=RegimeVote(
            regime=MarketRegime.UNCERTAIN,
            confidence=0.5,
            reason="Default classification"
        ),
    )