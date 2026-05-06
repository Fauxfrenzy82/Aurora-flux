"""
Metacognition Logger.
Periodically evaluates the system's own decision quality.
Detects cognitive biases in strategy selection and confidence calibration.

ZERO MODIFICATIONS to existing files.
Attaches via feature flag ENABLE_METACOGNITION in config.
Uses existing cognitive_log table.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from core.logger import get_logger

logger = get_logger("strategies.metacognition")


@dataclass
class BiasDetection:
    """Detected cognitive bias."""
    bias_type: str
    severity: float  # 0-1
    evidence: str
    recommendation: str
    detected_at: str


@dataclass
class MetacognitionReport:
    """Complete metacognition assessment."""
    timestamp: str
    overconfidence_detected: bool
    concentration_detected: bool
    recency_bias_detected: bool
    regime_decay_detected: bool
    biases: List[BiasDetection]
    confidence_calibration_error: float
    strategy_diversity_score: float
    overall_health: str  # "HEALTHY", "WARNING", "CRITICAL"


class MetacognitionEngine:
    """
    Self-evaluating cognitive monitor.
    
    Hourly checks:
    1. Confidence calibration — predicted vs actual win rate
    2. Strategy diversity — concentration in top strategies
    3. Recency bias — overweighting recent results
    4. Regime persistence decay — declining confidence in stable regime
    """

    CHECK_INTERVAL_MINUTES: int = 60
    CONFIDENCE_BINS: int = 5  # Number of confidence buckets for calibration

    # Thresholds
    OVERCONFIDENCE_THRESHOLD: float = 0.10  # 10% calibration error
    CONCENTRATION_THRESHOLD: float = 0.70  # 70% in top 3 strategies
    RECENCY_BIAS_THRESHOLD: float = 2.0  # 2x weight ratio
    REGIME_DECAY_BARS: int = 100  # Bars before regime decay check
    CONFIDENCE_DECLINE_THRESHOLD: float = 0.05  # 5% confidence decline

    def __init__(self, db_client):
        """
        Initialize metacognition engine.
        
        Args:
            db_client: Database client for querying trade history
        """
        self.db = db_client
        self.reports: List[MetacognitionReport] = []
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self.last_check: Optional[datetime] = None

        logger.info("Metacognition Engine initialized")

    async def start(self):
        """Start periodic metacognition checks."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info(
            f"Metacognition monitoring started — "
            f"every {self.CHECK_INTERVAL_MINUTES} minutes"
        )

    async def stop(self):
        """Stop periodic checks."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Metacognition monitoring stopped")

    async def _check_loop(self):
        """Background check loop."""
        while self._running:
            try:
                await self.run_check()
                await asyncio.sleep(self.CHECK_INTERVAL_MINUTES * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metacognition check error: {e}")
                await asyncio.sleep(300)

    async def run_check(self) -> MetacognitionReport:
        """Run a complete metacognition check."""
        now = datetime.now(timezone.utc)
        biases = []
        report = MetacognitionReport(
            timestamp=now.isoformat(),
            overconfidence_detected=False,
            concentration_detected=False,
            recency_bias_detected=False,
            regime_decay_detected=False,
            biases=[],
            confidence_calibration_error=0.0,
            strategy_diversity_score=0.0,
            overall_health="HEALTHY",
        )

        # Check 1: Confidence calibration
        cal_result = await self._check_confidence_calibration()
        if cal_result:
            report.overconfidence_detected = True
            report.confidence_calibration_error = cal_result.severity
            biases.append(cal_result)

        # Check 2: Strategy diversity
        div_result = await self._check_strategy_diversity()
        if div_result:
            report.concentration_detected = True
            report.strategy_diversity_score = 1.0 - div_result.severity
            biases.append(div_result)

        # Check 3: Recency bias
        rec_result = await self._check_recency_bias()
        if rec_result:
            report.recency_bias_detected = True
            biases.append(rec_result)

        # Check 4: Regime persistence decay
        reg_result = await self._check_regime_decay()
        if reg_result:
            report.regime_decay_detected = True
            biases.append(reg_result)

        report.biases = biases

        # Determine overall health
        severity_scores = [b.severity for b in biases]
        if severity_scores:
            max_severity = max(severity_scores)
            count_severe = sum(1 for s in severity_scores if s > 0.7)

            if max_severity > 0.8 or count_severe >= 3:
                report.overall_health = "CRITICAL"
            elif max_severity > 0.5 or count_severe >= 2:
                report.overall_health = "WARNING"

        # Store report
        self.reports.append(report)
        if len(self.reports) > 50:
            self.reports.pop(0)

        # Log to cognitive_log if findings
        if biases:
            await self.db.log_cognitive(
                event_type="METACOGNITION_CHECK",
                description=f"Health: {report.overall_health} | {len(biases)} biases detected",
                data={
                    "health": report.overall_health,
                    "biases": [
                        {
                            "type": b.bias_type,
                            "severity": b.severity,
                            "recommendation": b.recommendation,
                        }
                        for b in biases
                    ],
                },
            )

        self.last_check = now
        return report

    async def _check_confidence_calibration(self) -> Optional[BiasDetection]:
        """
        Check if predicted confidence matches actual win rate.
        High confidence predictions should win more often.
        """
        try:
            trades = await self.db.get_trades(limit=100)

            if len(trades) < 30:
                return None  # Insufficient data

            # Group trades by confidence level
            high_conf = [
                t for t in trades
                if (t.get("confidence") or 0) > 0.75
            ]
            med_conf = [
                t for t in trades
                if 0.55 < (t.get("confidence") or 0) <= 0.75
            ]
            low_conf = [
                t for t in trades
                if (t.get("confidence") or 0) <= 0.55
            ]

            high_wr = (
                sum(1 for t in high_conf if t.get("result") == "WIN") / len(high_conf)
                if high_conf else 0
            )
            med_wr = (
                sum(1 for t in med_conf if t.get("result") == "WIN") / len(med_conf)
                if med_conf else 0
            )
            low_wr = (
                sum(1 for t in low_conf if t.get("result") == "WIN") / len(low_conf)
                if low_conf else 0
            )

            # Check if high confidence underperforms
            if high_wr < 0.70 and len(high_conf) >= 10:
                severity = min(1.0, (0.70 - high_wr) / 0.20)
                return BiasDetection(
                    bias_type="OVERCONFIDENCE",
                    severity=round(severity, 3),
                    evidence=(
                        f"High-conf WR: {high_wr:.1%} vs expected 70%+ "
                        f"({len(high_conf)} trades). "
                        f"Med-conf: {med_wr:.1%}, Low-conf: {low_wr:.1%}"
                    ),
                    recommendation=(
                        "Reduce confidence floor or apply calibration adjustment "
                        "to confidence scores during signal generation"
                    ),
                    detected_at=datetime.now(timezone.utc).isoformat(),
                )

            # Check if calibration is inverted
            if len(high_conf) >= 10 and len(low_conf) >= 10:
                if high_wr < low_wr:
                    return BiasDetection(
                        bias_type="CONFIDENCE_INVERSION",
                        severity=0.8,
                        evidence=(
                            f"Low-conf WR ({low_wr:.1%}) > "
                            f"High-conf WR ({high_wr:.1%})"
                        ),
                        recommendation=(
                            "Confidence scoring is inverted. Review signal generation."
                        ),
                        detected_at=datetime.now(timezone.utc).isoformat(),
                    )

        except Exception as e:
            logger.error(f"Confidence calibration check error: {e}")

        return None

    async def _check_strategy_diversity(self) -> Optional[BiasDetection]:
        """Check if top strategies dominate allocation."""
        try:
            trades = await self.db.get_trades(limit=200)

            if len(trades) < 20:
                return None

            # Count trades per strategy
            strategy_counts: Dict[str, int] = {}
            for t in trades:
                strategy = t.get("strategy_name", "Unknown")
                strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

            if not strategy_counts:
                return None

            # Calculate concentration
            total = sum(strategy_counts.values())
            sorted_counts = sorted(strategy_counts.values(), reverse=True)
            top_3_share = sum(sorted_counts[:3]) / total if total > 0 else 0

            if top_3_share > self.CONCENTRATION_THRESHOLD:
                severity = min(
                    1.0,
                    (top_3_share - self.CONCENTRATION_THRESHOLD) / 0.30,
                )
                return BiasDetection(
                    bias_type="STRATEGY_CONCENTRATION",
                    severity=round(severity, 3),
                    evidence=(
                        f"Top 3 strategies account for {top_3_share:.1%} "
                        f"of {total} trades"
                    ),
                    recommendation=(
                        "Force diversity in next evolution cycle. "
                        "Consider reducing weights of dominant strategies."
                    ),
                    detected_at=datetime.now(timezone.utc).isoformat(),
                )

        except Exception as e:
            logger.error(f"Strategy diversity check error: {e}")

        return None

    async def _check_recency_bias(self) -> Optional[BiasDetection]:
        """Check if recent trades are overweighted in strategy ranking."""
        try:
            trades = await self.db.get_trades(limit=50)

            if len(trades) < 20:
                return None

            # Split into recent (last 10) and older (11-20)
            recent = trades[:10]
            older = trades[10:20] if len(trades) >= 20 else trades[10:]

            if not recent or not older:
                return None

            recent_wr = sum(1 for t in recent if t.get("result") == "WIN") / len(recent)
            older_wr = sum(1 for t in older if t.get("result") == "WIN") / len(older)

            # If recent performance is dramatically different from older
            if older_wr > 0 and recent_wr / older_wr > self.RECENCY_BIAS_THRESHOLD:
                severity = min(1.0, (recent_wr / older_wr - 1) / 2)
                return BiasDetection(
                    bias_type="RECENCY_BIAS",
                    severity=round(severity, 3),
                    evidence=(
                        f"Recent WR: {recent_wr:.1%}, "
                        f"Older WR: {older_wr:.1%} "
                        f"(ratio: {recent_wr/older_wr:.1f}x)"
                    ),
                    recommendation=(
                        "Apply exponential decay weighting to strategy rankings. "
                        "Recent performance may be anomalous."
                    ),
                    detected_at=datetime.now(timezone.utc).isoformat(),
                )

        except Exception as e:
            logger.error(f"Recency bias check error: {e}")

        return None

    async def _check_regime_decay(self) -> Optional[BiasDetection]:
        """Check if regime confidence is declining while regime persists."""
        try:
            # Get recent regime history
            regime_history = await self.db.get_regime_history(limit=100)

            if len(regime_history) < 20:
                return None

            # Check for prolonged same regime with declining confidence
            recent = regime_history[:20]
            regimes = [r.get("regime") for r in recent]
            confidences = [r.get("confidence", 0) for r in recent]

            unique_regimes = set(regimes)
            if len(unique_regimes) == 1 and len(confidences) >= 10:
                # Same regime throughout — check for decline
                first_half = np.mean(confidences[:10])
                second_half = np.mean(confidences[10:])

                decline = first_half - second_half
                if decline > self.CONFIDENCE_DECLINE_THRESHOLD:
                    severity = min(1.0, decline / 0.15)
                    return BiasDetection(
                        bias_type="REGIME_DECAY",
                        severity=round(severity, 3),
                        evidence=(
                            f"Regime '{regimes[0]}' persistent but confidence "
                            f"declined from {first_half:.2%} to {second_half:.2%}"
                        ),
                        recommendation=(
                            "Increase transition sensitivity in regime classifier. "
                            "Possible regime change approaching."
                        ),
                        detected_at=datetime.now(timezone.utc).isoformat(),
                    )

        except Exception as e:
            logger.error(f"Regime decay check error: {e}")

        return None

    def get_latest_report(self) -> Optional[MetacognitionReport]:
        """Get most recent metacognition report."""
        return self.reports[-1] if self.reports else None

    def get_stats(self) -> dict:
        """Get metacognition statistics."""
        latest = self.get_latest_report()
        return {
            "checks_run": len(self.reports),
            "last_check": (
                self.last_check.isoformat()
                if self.last_check
                else None
            ),
            "latest_health": latest.overall_health if latest else "UNKNOWN",
            "biases_detected": (
                [{"type": b.bias_type, "severity": b.severity} for b in latest.biases]
                if latest else []
            ),
            "health_history": [
                {"timestamp": r.timestamp, "health": r.overall_health}
                for r in self.reports[-10:]
            ],
        }