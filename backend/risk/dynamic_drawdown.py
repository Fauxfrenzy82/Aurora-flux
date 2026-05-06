
```python
"""
Dynamic Drawdown Engine — Freedom Mode only.
Calculates volatility-adaptive drawdown limits based on market conditions.
Replaces fixed 6% drawdown with a dynamic threshold between 3% and 10%.

ZERO MODIFICATIONS to existing files.
Attaches via feature flag ENABLE_DYNAMIC_DD in config and conditional in main.py.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple
from datetime import datetime, timezone
from core.logger import get_logger

logger = get_logger("risk.dynamic_dd")


@dataclass
class DrawdownComponents:
    """Component factors for dynamic drawdown calculation."""
    volatility_factor: float = 1.0
    regime_factor: float = 1.0
    correlation_factor: float = 1.0
    streak_factor: float = 1.0
    time_factor: float = 1.0


@dataclass
class DrawdownLimit:
    """Complete dynamic drawdown limit calculation."""
    limit_pct: float
    components: DrawdownComponents
    base_dd: float
    calculated_at: str
    reason: str = ""


class DynamicDrawdown:
    """
    Volatility-adaptive drawdown engine.
    
    Calculates drawdown tolerance as a function of:
    - Volatility (ATR ratio)
    - Regime type and confidence
    - Portfolio correlation risk
    - Recent performance streak
    - Session/time-based factors
    
    Clamped between floor (3%) and ceiling (10%).
    Default base is 6% from config.
    """

    # Constants
    FLOOR_PCT: float = 3.0
    CEILING_PCT: float = 10.0
    DEFAULT_BASE: float = 6.0

    # Volatility thresholds
    LOW_VOL_THRESHOLD: float = 0.8
    HIGH_VOL_THRESHOLD: float = 1.5
    EXTREME_VOL_THRESHOLD: float = 2.5

    # Regime multipliers
    TRENDING_BOOST: float = 1.3
    STRONG_TREND_BOOST: float = 1.5
    UNCERTAIN_PENALTY: float = 0.7
    TRANSITION_PENALTY: float = 0.6
    RISK_OFF_PENALTY: float = 0.5

    # Correlation thresholds
    HIGH_CORRELATION: float = 0.7
    EXTREME_CORRELATION: float = 0.85

    # Streak factors
    WINNING_STREAK_BOOST: float = 1.1
    LOSING_STREAK_PENALTY: float = 0.8

    def __init__(self, base_dd_pct: float = None):
        """
        Initialize dynamic drawdown engine.
        
        Args:
            base_dd_pct: Base drawdown percentage (default from config or 6.0)
        """
        self.base_dd = base_dd_pct or self.DEFAULT_BASE
        self.current_limit = self.base_dd
        self.last_calculation: Optional[DrawdownLimit] = None
        self.calculation_count: int = 0
        self.history: list = []  # Last 100 calculations

        logger.info(
            f"Dynamic Drawdown Engine initialized | "
            f"Base: {self.base_dd}% | "
            f"Range: {self.FLOOR_PCT}%-{self.CEILING_PCT}%"
        )

    def calculate(
        self,
        vol_ratio: float,
        regime: str,
        regime_confidence: float,
        correlation_risk: float,
        win_streak: int = 0,
        loss_streak: int = 0,
        session: str = "UNKNOWN",
        positions_count: int = 0,
    ) -> DrawdownLimit:
        """
        Calculate dynamic drawdown limit.
        
        Args:
            vol_ratio: Current ATR ratio (current/past)
            regime: Market regime string (e.g., "TRENDING_UP")
            regime_confidence: Regime classification confidence (0-1)
            correlation_risk: Portfolio correlation score (0-1)
            win_streak: Consecutive winning trades
            loss_streak: Consecutive losing trades
            session: Current trading session
            positions_count: Number of open positions
            
        Returns:
            DrawdownLimit with calculated limit and component breakdown
        """
        # Calculate component factors
        vol_factor = self._calc_volatility_factor(vol_ratio)
        regime_factor = self._calc_regime_factor(regime, regime_confidence)
        corr_factor = self._calc_correlation_factor(correlation_risk, positions_count)
        streak_factor = self._calc_streak_factor(win_streak, loss_streak)
        time_factor = self._calc_time_factor(session)

        # Build components
        components = DrawdownComponents(
            volatility_factor=round(vol_factor, 3),
            regime_factor=round(regime_factor, 3),
            correlation_factor=round(corr_factor, 3),
            streak_factor=round(streak_factor, 3),
            time_factor=round(time_factor, 3),
        )

        # Calculate limit
        raw_limit = (
            self.base_dd *
            vol_factor *
            regime_factor *
            corr_factor *
            streak_factor *
            time_factor
        )

        # Clamp to bounds
        limit = max(self.FLOOR_PCT, min(self.CEILING_PCT, raw_limit))
        limit = round(limit, 2)

        # Determine reason for significant changes
        reason = self._determine_reason(components, limit)

        # Update state
        self.current_limit = limit
        self.calculation_count += 1

        result = DrawdownLimit(
            limit_pct=limit,
            components=components,
            base_dd=self.base_dd,
            calculated_at=datetime.now(timezone.utc).isoformat(),
            reason=reason,
        )

        self.last_calculation = result

        # Track history
        self.history.append(result)
        if len(self.history) > 100:
            self.history.pop(0)

        # Log if limit changed significantly
        if abs(limit - self.base_dd) > 1.0:
            logger.info(
                f"Dynamic DD adjusted: {self.base_dd}% → {limit}% | "
                f"VF={vol_factor:.2f} RF={regime_factor:.2f} "
                f"CF={corr_factor:.2f} SF={streak_factor:.2f}"
            )

        return result

    def _calc_volatility_factor(self, vol_ratio: float) -> float:
        """
        Calculate volatility-based factor.
        
        Low volatility → more drawdown tolerance (mean reversion likely).
        High volatility → less tolerance (risk of large moves).
        """
        if vol_ratio < self.LOW_VOL_THRESHOLD:
            # Very low volatility — markets calm, wider stops acceptable
            factor = 1.5 + (self.LOW_VOL_THRESHOLD - vol_ratio) * 0.5
            return min(2.0, factor)
        elif vol_ratio <= 1.0:
            # Below normal — slightly more tolerance
            return 1.2
        elif vol_ratio <= self.HIGH_VOL_THRESHOLD:
            # Normal to elevated — linear decay
            return max(0.6, 1.2 - (vol_ratio - 1.0) * 0.8)
        elif vol_ratio <= self.EXTREME_VOL_THRESHOLD:
            # High volatility — tight leash
            return max(0.4, 0.6 - (vol_ratio - self.HIGH_VOL_THRESHOLD) * 0.3)
        else:
            # Extreme volatility — minimal tolerance
            return 0.4

    def _calc_regime_factor(self, regime: str, confidence: float) -> float:
        """
        Calculate regime-based factor.
        
        Trending → more tolerance (trends can pull back).
        Uncertain → less tolerance (confusion = danger).
        """
        regime_upper = regime.upper()

        if "STRONG_TREND" in regime_upper and confidence > 0.75:
            # Strong trend with high confidence — wide tolerance
            return self.STRONG_TREND_BOOST
        elif "TRENDING" in regime_upper and confidence > 0.65:
            # Trending — moderate boost
            return self.TRENDING_BOOST
        elif "RANGE" in regime_upper:
            # Range-bound — neutral
            return 1.0
        elif "VOLATILITY_EXPANSION" in regime_upper:
            # Expanding volatility — caution
            return 0.8
        elif "TRANSITION" in regime_upper:
            # Transitioning — tighten
            return self.TRANSITION_PENALTY
        elif "RISK_OFF" in regime_upper:
            # Risk-off — very tight
            return self.RISK_OFF_PENALTY
        elif "UNCERTAIN" in regime_upper:
            # Uncertain — tighten
            return self.UNCERTAIN_PENALTY
        else:
            # Default neutral
            return 1.0

    def _calc_correlation_factor(
        self,
        correlation_risk: float,
        positions_count: int
    ) -> float:
        """
        Calculate correlation-based factor.
        
        High correlation → concentrated risk → reduce drawdown tolerance.
        With many open positions, correlation risk compounds.
        """
        if positions_count <= 1:
            # Single position — no correlation concern
            return 1.0

        if correlation_risk > self.EXTREME_CORRELATION:
            # Extremely concentrated
            return 0.5
        elif correlation_risk > self.HIGH_CORRELATION:
            # Highly correlated
            # More positions amplify the penalty
            position_penalty = 1.0 - (positions_count - 1) * 0.05
            return max(0.5, 0.7 * position_penalty)
        elif correlation_risk > 0.5:
            # Moderately correlated
            return 0.85
        elif correlation_risk > 0.3:
            # Mild correlation — slight adjustment
            return 0.95
        else:
            # Diversified — full tolerance
            return 1.0

    def _calc_streak_factor(
        self,
        win_streak: int,
        loss_streak: int
    ) -> float:
        """
        Calculate performance streak factor.
        
        Winning streak → slightly more tolerance (hot hand).
        Losing streak → less tolerance (protect capital).
        """
        if loss_streak >= 5:
            # Significant losing streak — protect capital aggressively
            return 0.6
        elif loss_streak >= 3:
            # Developing losing streak — tighten
            return self.LOSING_STREAK_PENALTY
        elif win_streak >= 10:
            # Extended winning streak — mild boost with caution
            return self.WINNING_STREAK_BOOST * 0.9
        elif win_streak >= 5:
            # Good winning streak — slight boost
            return self.WINNING_STREAK_BOOST
        else:
            # Neutral
            return 1.0

    def _calc_time_factor(self, session: str) -> float:
        """
        Calculate session/time-based factor.
        
        Overlap sessions → more tolerance (liquidity).
        Asian/Weeks → less tolerance (thin markets).
        """
        session_upper = session.upper()

        if session_upper == "OVERLAP":
            # Maximum liquidity — most tolerant
            return 1.15
        elif session_upper == "LONDON":
            # High liquidity
            return 1.05
        elif session_upper == "NEW_YORK":
            # High liquidity
            return 1.05
        elif session_upper == "ASIAN":
            # Lower liquidity — tighter
            return 0.9
        elif session_upper in ("WEEKEND", "CLOSED"):
            # Market closed — irrelevant but tight
            return 0.8
        else:
            return 1.0

    def _determine_reason(
        self,
        components: DrawdownComponents,
        limit: float
    ) -> str:
        """Generate human-readable reason for drawdown limit."""
        reasons = []

        if components.volatility_factor > 1.2:
            reasons.append("low volatility expanding tolerance")
        elif components.volatility_factor < 0.7:
            reasons.append("high volatility tightening tolerance")

        if components.regime_factor > 1.2:
            reasons.append("favorable regime")
        elif components.regime_factor < 0.8:
            reasons.append("uncertain regime tightening")

        if components.correlation_factor < 0.8:
            reasons.append("concentrated portfolio risk")

        if components.streak_factor < 0.9:
            reasons.append("losing streak protection")
        elif components.streak_factor > 1.05:
            reasons.append("winning streak confidence")

        if components.time_factor < 0.95:
            reasons.append("thin session adjustment")
        elif components.time_factor > 1.05:
            reasons.append("high liquidity session")

        if not reasons:
            return f"Standard conditions — limit at {limit}%"

        return f"{'; '.join(reasons)} — limit set to {limit}%"

    def get_current_limit(self) -> float:
        """Get the currently active drawdown limit."""
        return self.current_limit

    def get_last_calculation(self) -> Optional[DrawdownLimit]:
        """Get the most recent calculation details."""
        return self.last_calculation

    def get_average_limit(self, lookback: int = 20) -> float:
        """Get average drawdown limit over recent calculations."""
        if not self.history:
            return self.current_limit

        recent = self.history[-lookback:]
        if not recent:
            return self.current_limit

        avg = sum(h.limit_pct for h in recent) / len(recent)
        return round(avg, 2)

    def get_stats(self) -> dict:
        """Get engine statistics."""
        return {
            "base_dd": self.base_dd,
            "current_limit": self.current_limit,
            "floor": self.FLOOR_PCT,
            "ceiling": self.CEILING_PCT,
            "calculations": self.calculation_count,
            "average_30": self.get_average_limit(30),
            "last_components": (
                {
                    "volatility": self.last_calculation.components.volatility_factor,
                    "regime": self.last_calculation.components.regime_factor,
                    "correlation": self.last_calculation.components.correlation_factor,
                    "streak": self.last_calculation.components.streak_factor,
                    "time": self.last_calculation.components.time_factor,
                }
                if self.last_calculation
                else None
            ),
        }

    def reset(self):
        """Reset engine to base state."""
        self.current_limit = self.base_dd
        self.last_calculation = None
        self.history.clear()
        self.calculation_count = 0
        logger.info("Dynamic Drawdown Engine reset to defaults")