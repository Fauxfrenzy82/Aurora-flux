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
                f"SCALP MODE ACTIVATED | "
                f"Session: {conditions.session} | "
                f"Spread: {conditions.spread_pips}pips | "
                f"ATR: {conditions.atr_ratio:.1f}x | "
                f"Window: {self.MAX_SCALP_WINDOW_MINUTES}min"
            )

            return ScalpState(
                active=True,
                conditions=conditions,
                activated_at=self.activated_at.isoformat(),
                minutes_remaining=self.MAX_SCALP_WINDOW_MINUTES,
                reason="All activation conditions met",
            )
        else:
            failed = [k for k, v in checks.items() if not v]
            return ScalpState(
                active=False,
                conditions=conditions,
                reason=f"Conditions not met: {', '.join(failed)}",
            )

    def _evaluate_deactivation(self, conditions: ScalpConditions) -> ScalpState:
        """Check if scalp mode should deactivate."""
        deactivation_reasons = []

        # Check time limit
        if self.activated_at:
            elapsed_minutes = (
                datetime.now(timezone.utc) - self.activated_at
            ).total_seconds() / 60
            if elapsed_minutes >= self.MAX_SCALP_WINDOW_MINUTES:
                deactivation_reasons.append(
                    f"Time limit: {elapsed_minutes:.0f}min >= {self.MAX_SCALP_WINDOW_MINUTES}min"
                )
            minutes_remaining = max(0, self.MAX_SCALP_WINDOW_MINUTES - elapsed_minutes)
        else:
            minutes_remaining = 0

        # Check conditions
        if conditions.session not in self.SCALP_SESSIONS:
            deactivation_reasons.append(f"Session ended: {conditions.session}")
        if conditions.spread_pips > self.DEACTIVATE_SPREAD:
            deactivation_reasons.append(f"Spread widened: {conditions.spread_pips}pips")
        if conditions.tick_velocity < self.DEACTIVATE_TICK_VEL:
            deactivation_reasons.append(f"Tick velocity dropped: {conditions.tick_velocity}/s")
        if conditions.drawdown > self.DEACTIVATE_DRAWDOWN:
            deactivation_reasons.append(f"Drawdown elevated: {conditions.drawdown:.1%}")
        if self.scalp_losses >= self.MAX_CONSECUTIVE_LOSSES:
            deactivation_reasons.append(
                f"Consecutive losses: {self.scalp_losses}/{self.MAX_CONSECUTIVE_LOSSES}"
            )

        if deactivation_reasons:
            return self._deactivate(deactivation_reasons, conditions)

        return ScalpState(
            active=True,
            conditions=conditions,
            activated_at=self.activated_at.isoformat() if self.activated_at else None,
            minutes_remaining=round(minutes_remaining, 1),
            scalp_trades_taken=self.total_scalp_trades,
            scalp_wins=self.scalp_wins,
            scalp_losses=self.scalp_losses,
            reason="Scalp mode active",
        )

    def _deactivate(
        self,
        reasons: list,
        conditions: ScalpConditions,
    ) -> ScalpState:
        """Deactivate scalp mode."""
        self.active = False
        self.last_deactivation = datetime.now(timezone.utc)

        # Record session stats
        session_key = datetime.now(timezone.utc).strftime("%Y%m%d_%H")
        self.session_stats[session_key] = {
            "trades": self.total_scalp_trades,
            "wins": self.scalp_wins,
            "losses": self.scalp_losses,
            "reasons": reasons,
        }

        # Keep only last 50 sessions
        if len(self.session_stats) > 50:
            oldest_keys = sorted(self.session_stats.keys())[:len(self.session_stats) - 50]
            for key in oldest_keys:
                del self.session_stats[key]

        reason_str = "; ".join(reasons)
        logger.info(
            f"SCALP MODE DEACTIVATED | "
            f"Trades: {self.total_scalp_trades} | "
            f"W/L: {self.scalp_wins}/{self.scalp_losses} | "
            f"Reason: {reason_str}"
        )

        return ScalpState(
            active=False,
            conditions=conditions,
            reason=reason_str,
            scalp_trades_taken=self.total_scalp_trades,
            scalp_wins=self.scalp_wins,
            scalp_losses=self.scalp_losses,
        )

    def record_scalp_result(self, is_win: bool):
        """Record result of a scalp trade."""
        self.total_scalp_trades += 1
        if is_win:
            self.scalp_wins += 1
            self.scalp_losses = 0  # Reset loss streak on win
        else:
            self.scalp_losses += 1

        if self.scalp_losses >= self.MAX_CONSECUTIVE_LOSSES and self.active:
            logger.warning(
                f"Scalp loss streak: {self.scalp_losses} — deactivating"
            )
            # Force deactivation
            if self.current_conditions:
                self._deactivate(
                    [f"Loss streak: {self.scalp_losses}"],
                    self.current_conditions,
                )

    def is_scalp_mode(self) -> bool:
        """Check if scalp mode is currently active."""
        return self.active

    def get_scalp_params(self) -> dict:
        """
        Get adjusted parameters for scalp mode.
        Returns dict with modified thresholds.
        """
        if not self.active:
            return {}

        return {
            "confidence_floor": self.SCALP_CONFIDENCE_FLOOR,
            "max_holding_minutes": self.SCALP_MAX_HOLDING_MINUTES,
            "min_aggression": self.SCALP_MIN_AGGRESSION,
            "scalp_mode": True,
        }

    def get_stats(self) -> dict:
        """Get scalp engine statistics."""
        return {
            "active": self.active,
            "total_scalp_trades": self.total_scalp_trades,
            "scalp_wins": self.scalp_wins,
            "scalp_losses": self.scalp_losses,
            "win_rate": (
                self.scalp_wins / self.total_scalp_trades
                if self.total_scalp_trades > 0
                else 0
            ),
            "current_conditions": (
                {
                    "session": self.current_conditions.session,
                    "spread": self.current_conditions.spread_pips,
                    "tick_vel": self.current_conditions.tick_velocity,
                    "atr_ratio": self.current_conditions.atr_ratio,
                }
                if self.current_conditions
                else None
            ),
            "recent_sessions": dict(list(self.session_stats.items())[-5:]),
        }