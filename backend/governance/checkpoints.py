"""
7-checkpoint governance system.
Every trade must pass all checkpoints before execution.
Provides circuit breaker, drawdown protection, and compliance.
"""

from dataclasses import dataclass, field
from typing import List, Tuple
from core.config import config
from core.logger import get_logger

logger = get_logger("governance")


@dataclass
class CheckpointResult:
    """Result of a single governance checkpoint."""
    name: str
    passed: bool
    detail: str = ""


@dataclass
class GovernanceResult:
    """Complete governance evaluation result."""
    approved: bool
    reason: str = ""
    checkpoints: List[CheckpointResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "reason": self.reason,
            "checkpoints": [
                {"name": cp.name, "passed": cp.passed, "detail": cp.detail}
                for cp in self.checkpoints
            ],
        }


class Governance:
    """
    Trade approval system with 7 mandatory checkpoints.
    
    Checkpoints:
    1. System Operational — no emergency halt
    2. Strategy Active — strategy not suspended/retired
    3. Daily Cap — daily profit/loss within limits
    4. Drawdown Protection — max drawdown not exceeded
    5. Regime Compatible — market regime confidence above floor
    6. Risk Limits — position size within all constraints
    7. Signal Valid — signal confidence above threshold
    """

    def __init__(self):
        self.halted: bool = False
        self.halt_reason: str = ""
        self.total_approved: int = 0
        self.total_rejected: int = 0

    def evaluate(
        self,
        signal: dict,
        context: dict
    ) -> GovernanceResult:
        """
        Evaluate a trading signal against all governance checkpoints.
        
        Args:
            signal: Signal dict with direction, confidence, etc.
            context: Context dict with strategy, risk, and account state
            
        Returns:
            GovernanceResult with approval status and checkpoint details
        """
        checkpoints: List[CheckpointResult] = []

        # ── CP1: System Operational ────────────────────

        if self.halted:
            reason = f"System halted: {self.halt_reason}"
            checkpoints.append(CheckpointResult(
                "System Operational", False, reason
            ))
            self.total_rejected += 1
            return GovernanceResult(False, reason, checkpoints)

        checkpoints.append(CheckpointResult(
            "System Operational", True, "System running"
        ))

        # ── CP2: Strategy Active ───────────────────────

        strategy_status = context.get("strategy_status", "UNKNOWN")
        if strategy_status not in ("ACTIVE", "TESTING"):
            reason = f"Strategy not active: {strategy_status}"
            checkpoints.append(CheckpointResult(
                "Strategy Active", False, reason
            ))
            self.total_rejected += 1
            return GovernanceResult(False, reason, checkpoints)

        checkpoints.append(CheckpointResult(
            "Strategy Active", True, f"Status: {strategy_status}"
        ))

        # ── CP3: Daily Cap ─────────────────────────────

        daily_used = abs(context.get("daily_used", 0))
        daily_cap = context.get("daily_cap", 999999)

        if daily_used >= daily_cap:
            reason = (
                f"Daily cap exhausted: {daily_used:.2f}/{daily_cap:.2f}"
            )
            checkpoints.append(CheckpointResult(
                "Daily Cap", False, reason
            ))
            self.total_rejected += 1
            return GovernanceResult(False, reason, checkpoints)

        remaining_pct = (1 - daily_used / daily_cap) * 100 if daily_cap > 0 else 0
        checkpoints.append(CheckpointResult(
            "Daily Cap", True,
            f"Used: {daily_used:.2f}/{daily_cap:.2f} ({remaining_pct:.0f}% remaining)"
        ))

        # ── CP4: Drawdown Protection ───────────────────

        drawdown_pct = context.get("drawdown_pct", 0)
        max_drawdown = context.get("max_drawdown", config.MAX_DRAWDOWN_PCT / 100)

        if drawdown_pct >= max_drawdown:
            self.halted = True
            self.halt_reason = (
                f"Max drawdown exceeded: {drawdown_pct:.2%} >= {max_drawdown:.2%}"
            )
            reason = self.halt_reason
            checkpoints.append(CheckpointResult(
                "Drawdown Protection", False, reason
            ))
            self.total_rejected += 1
            logger.critical(f"HALT: {reason}")
            return GovernanceResult(False, reason, checkpoints)

        checkpoints.append(CheckpointResult(
            "Drawdown Protection", True,
            f"DD: {drawdown_pct:.2%} / Max: {max_drawdown:.2%}"
        ))

        # ── CP5: Regime Compatible ─────────────────────

        regime_confidence = context.get("regime_confidence", 0)
        confidence_floor = config.CONFIDENCE_FLOOR

        if regime_confidence < confidence_floor:
            reason = (
                f"Regime confidence too low: "
                f"{regime_confidence:.2%} < {confidence_floor:.2%}"
            )
            checkpoints.append(CheckpointResult(
                "Regime Compatible", False, reason
            ))
            self.total_rejected += 1
            return GovernanceResult(False, reason, checkpoints)

        checkpoints.append(CheckpointResult(
            "Regime Compatible", True,
            f"Confidence: {regime_confidence:.2%}"
        ))

        # ── CP6: Risk Limits ───────────────────────────

        position_size = context.get("position_size_result", {})
        if hasattr(position_size, "rejected"):
            # It's a PositionSize dataclass
            if position_size.rejected:
                reason = f"Position sizing rejected: {position_size.reason}"
                checkpoints.append(CheckpointResult(
                    "Risk Limits", False, reason
                ))
                self.total_rejected += 1
                return GovernanceResult(False, reason, checkpoints)
            size = position_size.size
            risk_pct = position_size.risk_pct
            binding = position_size.binding_constraint
        elif isinstance(position_size, dict):
            if position_size.get("rejected"):
                reason = f"Position sizing rejected: {position_size.get('reason', 'Unknown')}"
                checkpoints.append(CheckpointResult(
                    "Risk Limits", False, reason
                ))
                self.total_rejected += 1
                return GovernanceResult(False, reason, checkpoints)
            size = position_size.get("size", 0)
            risk_pct = position_size.get("risk_pct", 0)
            binding = position_size.get("binding_constraint", "Unknown")
        else:
            reason = "Position size not calculated"
            checkpoints.append(CheckpointResult(
                "Risk Limits", False, reason
            ))
            self.total_rejected += 1
            return GovernanceResult(False, reason, checkpoints)

        checkpoints.append(CheckpointResult(
            "Risk Limits", True,
            f"Size: {size:.4f}, Risk: {risk_pct:.2%}, Binding: {binding}"
        ))

        # ── CP7: Signal Valid ──────────────────────────

        signal_confidence = signal.get("confidence", 0)
        signal_direction = signal.get("direction", "UNKNOWN")
        signal_symbol = signal.get("symbol", "UNKNOWN")

        if signal_confidence < confidence_floor:
            reason = (
                f"Signal confidence too low: "
                f"{signal_confidence:.2%} < {confidence_floor:.2%}"
            )
            checkpoints.append(CheckpointResult(
                "Signal Valid", False, reason
            ))
            self.total_rejected += 1
            return GovernanceResult(False, reason, checkpoints)

        if signal_direction not in ("LONG", "SHORT"):
            reason = f"Invalid direction: {signal_direction}"
            checkpoints.append(CheckpointResult(
                "Signal Valid", False, reason
            ))
            self.total_rejected += 1
            return GovernanceResult(False, reason, checkpoints)

        checkpoints.append(CheckpointResult(
            "Signal Valid", True,
            f"{signal_symbol} {signal_direction}, Confidence: {signal_confidence:.2%}"
        ))

        # ── ALL CHECKPOINTS PASSED ─────────────────────

        self.total_approved += 1
        logger.governance(
            "APPROVED",
            signal_symbol,
            f"Direction: {signal_direction}, "
            f"Confidence: {signal_confidence:.2%}"
        )

        return GovernanceResult(
            approved=True,
            reason="All checkpoints passed",
            checkpoints=checkpoints
        )

    def halt(self, reason: str = "Manual halt"):
        """Emergency halt of all trading."""
        self.halted = True
        self.halt_reason = reason
        logger.critical(f"EMERGENCY HALT: {reason}")

    def resume(self):
        """Resume trading after halt."""
        self.halted = False
        self.halt_reason = ""
        logger.info("Trading resumed")

    def get_stats(self) -> dict:
        """Get governance statistics."""
        total = self.total_approved + self.total_rejected
        return {
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "total_evaluated": total,
            "approved": self.total_approved,
            "rejected": self.total_rejected,
            "approval_rate": (
                self.total_approved / total if total > 0 else 0
            ),
        }

    def reset_stats(self):
        """Reset approval/rejection counters."""
        self.total_approved = 0
        self.total_rejected = 0