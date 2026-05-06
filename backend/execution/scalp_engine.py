"""
Scalp Mode Activation Engine.
Activates aggressive short-term trading when market conditions are optimal.
Automatically deactivates when conditions degrade or after time limits.

ZERO MODIFICATIONS to existing files.
Attaches via feature flag ENABLE_SCALP_MODE in config.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone, timedelta
from core.logger import get_logger

logger = get_logger("execution.scalp")


@dataclass
class ScalpConditions:
    """Current scalp mode evaluation conditions."""
    session: str
    spread_pips: float
    tick_velocity: float
    atr_ratio: float
    news_imminent: bool
    drawdown: float
    positions_count: int
    recent_losses: int


@dataclass
class ScalpState:
    """Full scalp mode state."""
    active: bool
    conditions: ScalpConditions
    activated_at: Optional[str] = None
    minutes_remaining: float = 0.0
    scalp_trades_taken: int = 0
    scalp_wins: int = 0
    scalp_losses: int = 0
    reason: str = ""


class ScalpEngine:
    """
    Manages scalp mode activation and deactivation.
    
    Activation requires ALL conditions:
    1. Session: LONDON, NEW_YORK, or OVERLAP
    2. Spread < 1.5 pips on EURUSD
    3. Tick velocity > 5 ticks/second
    4. ATR ratio > 1.2
    5. No high-impact news in next 5 minutes
    6. Current drawdown < 3%
    
    Deactivation:
    - Any condition fails
    - 3 consecutive scalp losses
    - 20-minute max window expired
    """

    # Activation thresholds
    MIN_SPREAD_PIPS: float = 1.5
    MIN_TICK_VELOCITY: float = 5.0
    MIN_ATR_RATIO: float = 1.2
    MAX_DRAWDOWN: float = 0.03  # 3%
    MAX_POSITIONS_FOR_SCALP: int = 3

    # Deactivation thresholds
    DEACTIVATE_SPREAD: float = 2.0
    DEACTIVATE_TICK_VEL: float = 3.0
    DEACTIVATE_DRAWDOWN: float = 0.05  # 5%

    # Session list
    SCALP_SESSIONS: tuple = ("LONDON", "NEW_YORK", "OVERLAP")

    # Window limits
    MAX_SCALP_WINDOW_MINUTES: int = 20
    COOLDOWN_MINUTES: int = 10
    MAX_CONSECUTIVE_LOSSES: int = 3

    # Adjusted parameters during scalp mode
    SCALP_CONFIDENCE_FLOOR: float = 0.55  # Lowered from 0.65
    SCALP_MAX_HOLDING_MINUTES: int = 60  # Prioritize short holds
    SCALP_MIN_AGGRESSION: float = 0.6  # Prioritize aggressive strategies

    def __init__(self):
        self.active: bool = False
        self.activated_at: Optional[datetime] = None
        self.scalp_losses: int = 0
        self.scalp_wins: int = 0
        self.total_scalp_trades: int = 0
        self.last_deactivation: Optional[datetime] = None
        self.session_stats: dict = {}
        self.current_conditions: Optional[ScalpConditions] = None

        logger.info("Scalp Engine initialized")

    async def evaluate(
        self,
        session: str,
        spread_pips: float,
        tick_velocity: float,
        atr_ratio: float,
        news_imminent: bool,
        drawdown: float,
        positions_count: int = 0,
    ) -> ScalpState:
        """
        Evaluate scalp mode activation/deactivation.
        
        Returns ScalpState with current status and reasoning.
        """
        conditions = ScalpConditions(
            session=session,
            spread_pips=round(spread_pips, 1),
            tick_velocity=round(tick_velocity, 1),
            atr_ratio=round(atr_ratio, 2),
            news_imminent=news_imminent,
            drawdown=round(drawdown, 4),
            positions_count=positions_count,
            recent_losses=self.scalp_losses,
        )
        self.current_conditions = conditions

        # Check cooldown
        if self.last_deactivation:
            cooldown_elapsed = (
                datetime.now(timezone.utc) - self.last_deactivation
            ).total_seconds() / 60
            if cooldown_elapsed < self.COOLDOWN_MINUTES:
                return ScalpState(
                    active=False,
                    conditions=conditions,
                    reason=f"Cooldown active: {cooldown_elapsed:.0f}/{self.COOLDOWN_MINUTES}min",
                )

        if self.active:
            return self._evaluate_deactivation(conditions)
        else:
            return self._evaluate_activation(conditions)

    def _evaluate_activation(self, conditions: ScalpConditions) -> ScalpState:
        """Check if scalp mode should activate."""
        checks = {
            "session_valid": conditions.session in self.SCALP_SESSIONS,
            "spread_tight": conditions.spread_pips < self.MIN_SPREAD_PIPS,
            "tick_velocity_high": conditions.tick_velocity > self.MIN_TICK_VELOCITY,
            "volatility_elevated": conditions.atr_ratio > self.MIN_ATR_RATIO,
            "no_news": not conditions.news_imminent,
            "drawdown_low": conditions.drawdown < self.MAX_DRAWDOWN,
            "positions_available": conditions.positions_count < self.MAX_POSITIONS_FOR_SCALP,
        }

        all_passed = all(checks.values())

        if all_passed:
            self.active = True
            self.activated_at = datetime.now(timezone.utc)
            self.scalp_losses = 0
            self.scalp_wins = 0

            logger.info(
                f"SCAL