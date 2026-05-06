"""
Pre-Trade Memory Consultant.
Queries historical performance before signals proceed to governance.
Adjusts confidence based on real historical edge in identical conditions.

ZERO MODIFICATIONS to existing files.
Attaches via feature flag ENABLE_MEMORY_CONSULT in config.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
from core.logger import get_logger

logger = get_logger("strategies.memory")


@dataclass
class MemoryContext:
    """Historical performance context for a strategy/symbol/regime/session."""
    trades: int
    win_rate: float
    profit_factor: float
    expectancy: float
    avg_win: float
    avg_loss: float
    last_10_results: List[str] = field(default_factory=list)
    confidence_interval: tuple = (0.0, 0.0)


@dataclass
class ConsultationResult:
    """Result of memory consultation for a signal."""
    original_confidence: float
    adjusted_confidence: float
    adjustment: float
    context: MemoryContext
    action: str  # "BOOST", "REDUCE", "REJECT", "PASS"
    reason: str


class MemoryConsultant:
    """
    Queries trade history to validate or adjust signal confidence.
    
    Adjustment Rules:
    - N >= 20, PF >= 2.0:  +0.10 "Strong historical edge"
    - N >= 20, PF >= 1.5:  +0.05 "Moderate edge"
    - N >= 20, PF < 1.0:   -0.15 "Historical underperformance"
    - N >= 10, WR < 0.40:  -0.10 "Consistent losing pattern"
    - N < 10:              No adjustment "Insufficient data"
    - Danger patterns:     -0.20 "Danger pattern match"
    
    Final confidence clamped [0, 0.95].
    If adjusted below confidence floor, signal is rejected.
    """

    # Thresholds
    MIN_TRADES_FOR_ADJUSTMENT: int = 10
    STRONG_EDGE_TRADES: int = 20
    STRONG_EDGE_PF: float = 2.0
    MODERATE_EDGE_PF: float = 1.5
    UNDERPERFORM_PF: float = 1.0
    LOSING_WR_THRESHOLD: float = 0.40

    # Adjustment amounts
    STRONG_BOOST: float = 0.10
    MODERATE_BOOST: float = 0.05
    UNDERPERFORM_REDUCTION: float = -0.15
    LOSING_REDUCTION: float = -0.10
    DANGER_PENALTY: float = -0.20

    # Confidence bounds
    MAX_CONFIDENCE: float = 0.95
    MIN_CONFIDENCE: float = 0.0

    def __init__(self, db_client):
        """
        Initialize memory consultant.
        
        Args:
            db_client: Database client instance
        """
        self.db = db_client
        self.consultations: int = 0
        self.boosts: int = 0
        self.reductions: int = 0
        self.rejections: int = 0
        self.passes: int = 0
        self._danger_patterns_cache: List[dict] = []
        self._cache_updated_at: Optional[str] = None

        logger.info("Memory Consultant initialized")

    async def consult(
        self,
        signal: dict,
        confidence_floor: float = 0.65,
    ) -> ConsultationResult:
        """
        Consult historical memory for a trading signal.
        
        Args:
            signal: Signal dict with strategy_name, symbol, regime, session, confidence
            confidence_floor: Minimum confidence to proceed
            
        Returns:
            ConsultationResult with adjusted confidence and reasoning
        """
        self.consultations += 1

        strategy = signal.get("strategy_name", "Unknown")
        symbol = signal.get("symbol", "Unknown")
        regime = signal.get("regime", "")
        session = signal.get("session", "")
        original_confidence = float(signal.get("confidence", 0.5))

        # Query historical context
        ctx_data = await self.db.query_context(
            strategy=strategy,
            symbol=symbol,
            regime=regime,
            session=session,
            limit=50,
        )

        # Build memory context
        context = MemoryContext(
            trades=ctx_data.get("trades", 0),
            win_rate=ctx_data.get("win_rate", 0),
            profit_factor=ctx_data.get("profit_factor", 0),
            expectancy=ctx_data.get("expectancy", 0),
            avg_win=0.0,
            avg_loss=0.0,
        )

        # Check danger patterns
        danger_patterns = await self._get_danger_patterns()
        danger_match = self._check_danger_patterns(signal, danger_patterns)

        # Calculate adjustment
        adjustment = self._calculate_adjustment(context, danger_match)
        adjusted_confidence = original_confidence + adjustment
        adjusted_confidence = max(
            self.MIN_CONFIDENCE,
            min(self.MAX_CONFIDENCE, adjusted_confidence)
        )

        # Determine action
        if adjusted_confidence < confidence_floor:
            action = "REJECT"
            self.rejections += 1
            reason = f"Adjusted confidence ({adjusted_confidence:.2%}) below floor ({confidence_floor:.2%})"
        elif adjustment > 0:
            action = "BOOST"
            self.boosts += 1
            reason = self._build_reason(context, adjustment, danger_match)
        elif adjustment < 0:
            action = "REDUCE"
            self.reductions += 1
            reason = self._build_reason(context, adjustment, danger_match)
        else:
            action = "PASS"
            self.passes += 1
            reason = "Insufficient data for adjustment — passing through unchanged"

        result = ConsultationResult(
            original_confidence=round(original_confidence, 4),
            adjusted_confidence=round(adjusted_confidence, 4),
            adjustment=round(adjustment, 4),
            context=context,
            action=action,
            reason=reason,
        )

        if action != "PASS":
            logger.info(
                f"Memory Consultation | {action} | {symbol} {signal.get('direction', '')} | "
                f"Conf: {original_confidence:.2%} → {adjusted_confidence:.2%} "
                f"({adjustment:+.3f}) | {reason[:80]}"
            )

        # Update signal in-place
        signal["confidence"] = result.adjusted_confidence
        signal["memory_adjustment"] = result.adjustment
        signal["memory_context"] = {
            "trades": context.trades,
            "win_rate": context.win_rate,
            "profit_factor": context.profit_factor,
        }

        return result

    def _calculate_adjustment(
        self,
        context: MemoryContext,
        danger_match: bool,
    ) -> float:
        """Calculate confidence adjustment from historical context."""
        adjustment = 0.0
        n = context.trades
        pf = context.profit_factor
        wr = context.win_rate

        # Strong edge
        if n >= self.STRONG_EDGE_TRADES and pf >= self.STRONG_EDGE_PF:
            adjustment += self.STRONG_BOOST

        # Moderate edge
        elif n >= self.STRONG_EDGE_TRADES and pf >= self.MODERATE_EDGE_PF:
            adjustment += self.MODERATE_BOOST

        # Underperformance
        elif n >= self.STRONG_EDGE_TRADES and pf < self.UNDERPERFORM_PF:
            adjustment += self.UNDERPERFORM_REDUCTION

        # Consistent losing (overrides or compounds)
        if n >= self.MIN_TRADES_FOR_ADJUSTMENT and wr < self.LOSING_WR_THRESHOLD:
            # Take the more severe penalty
            adjustment = min(adjustment, self.LOSING_REDUCTION)

        # Danger patterns
        if danger_match:
            adjustment += self.DANGER_PENALTY

        return adjustment

    def _check_danger_patterns(
        self,
        signal: dict,
        danger_patterns: List[dict],
    ) -> bool:
        """
        Check if signal matches any danger patterns.
        Danger patterns are stored in pattern_library with status='DANGER'.
        """
        if not danger_patterns:
            return False

        signal_str = str(signal).lower()

        for pattern in danger_patterns:
            signature = pattern.get("signature", "").lower()
            if signature and signature in signal_str:
                logger.warning(
                    f"Danger pattern matched: {pattern.get('description', signature)}"
                )
                return True

        return False

    async def _get_danger_patterns(self) -> List[dict]:
        """Fetch danger patterns from database (cached)."""
        from datetime import datetime, timezone

        # Refresh cache every 30 minutes
        now = datetime.now(timezone.utc).isoformat()
        if (
            self._cache_updated_at
            and self._danger_patterns_cache
        ):
            # Simple time check
            try:
                cache_time = datetime.fromisoformat(self._cache_updated_at)
                elapsed = (datetime.now(timezone.utc) - cache_time).total_seconds()
                if elapsed < 1800:  # 30 minutes
                    return self._danger_patterns_cache
            except (ValueError, TypeError):
                pass

        try:
            patterns = await self.db.find_patterns(status="DANGER")
            if patterns:
                self._danger_patterns_cache = patterns
                self._cache_updated_at = now
            return patterns or []
        except Exception as e:
            logger.error(f"Failed to fetch danger patterns: {e}")
            return self._danger_patterns_cache  # Return stale cache

    def _build_reason(
        self,
        context: MemoryContext,
        adjustment: float,
        danger_match: bool,
    ) -> str:
        """Build human-readable reason for adjustment."""
        parts = []

        if context.trades >= self.STRONG_EDGE_TRADES:
            if context.profit_factor >= self.STRONG_EDGE_PF:
                parts.append(
                    f"Strong edge: {context.trades} trades, "
                    f"PF={context.profit_factor:.2f}, WR={context.win_rate:.1%}"
                )
            elif context.profit_factor >= self.MODERATE_EDGE_PF:
                parts.append(
                    f"Moderate edge: {context.trades} trades, "
                    f"PF={context.profit_factor:.2f}"
                )
            elif context.profit_factor < self.UNDERPERFORM_PF:
                parts.append(
                    f"Underperformance: {context.trades} trades, "
                    f"PF={context.profit_factor:.2f}"
                )

        if (
            context.trades >= self.MIN_TRADES_FOR_ADJUSTMENT
            and context.win_rate < self.LOSING_WR_THRESHOLD
        ):
            parts.append(f"Low win rate: {context.win_rate:.1%}")

        if danger_match:
            parts.append("Danger pattern detected")

        if not parts:
            parts.append(f"Adjustment: {adjustment:+.3f}")

        return " | ".join(parts)

    def get_stats(self) -> dict:
        """Get consultation statistics."""
        total = self.consultations
        return {
            "total_consultations": total,
            "boosts": self.boosts,
            "reductions": self.reductions,
            "rejections": self.rejections,
            "passes": self.passes,
            "boost_rate": self.boosts / total if total > 0 else 0,
            "reduction_rate": self.reductions / total if total > 0 else 0,
            "rejection_rate": self.rejections / total if total > 0 else 0,
            "pass_rate": self.passes / total if total > 0 else 0,
        }