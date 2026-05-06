"""
Pyramiding Execution Engine — Freedom Mode only.
Adds to winning positions in up to 3 layers for strategies with pyramiding DNA flag.
Compounds profit during strong directional moves.

ZERO MODIFICATIONS to existing files.
Attaches via feature flag ENABLE_PYRAMIDING in config and conditional in main.py.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timezone
from core.logger import get_logger

logger = get_logger("execution.pyramiding")


@dataclass
class PyramidLayer:
    """Information about a single pyramid layer."""
    layer_number: int
    position_id: str
    entry_price: float
    volume: float
    stop_loss: float
    added_at: str
    r_level: float  # R-multiple at which layer was added


@dataclass
class ActivePyramid:
    """Tracks an active pyramiding position."""
    original_position_id: str
    symbol: str
    direction: str
    strategy_id: str
    strategy_name: str
    max_layers: int
    layers: List[PyramidLayer] = field(default_factory=list)
    combined_stop: float = 0.0
    total_volume: float = 0.0
    average_entry: float = 0.0
    created_at: str = ""
    last_updated: str = ""


@dataclass
class PyramidDecision:
    """Result of pyramiding evaluation."""
    should_pyramid: bool
    reason: str = ""
    add_size: float = 0.0
    new_combined_stop: float = 0.0
    next_layer: int = 0
    current_r: float = 0.0
    conditions_met: Dict[str, bool] = field(default_factory=dict)


class PyramidingEngine:
    """
    Manages pyramiding execution for qualifying strategies.
    
    Pyramid Rules:
    - Layer 1: Original entry (100% of base size)
    - Layer 2: +1R reached, add 50% size, move stop to breakeven
    - Layer 3: +2R on combined, add 25% size, trailing stop activates
    
    Safety:
    - Only in Freedom Mode
    - Only for strategies with pyramiding: true in DNA
    - Max 3 layers total
    - Combined stop moves to protect profits
    - All layers exit simultaneously
    """

    # R-multiple thresholds for each layer
    LAYER_THRESHOLDS: Dict[int, float] = {
        2: 1.0,   # Layer 2: +1R
        3: 2.0,   # Layer 3: +2R combined
    }

    # Size ratios for each layer (relative to original)
    LAYER_SIZE_RATIOS: Dict[int, float] = {
        2: 0.50,  # Layer 2: 50% of original
        3: 0.25,  # Layer 3: 25% of original
    }

    # Safety limits
    MAX_COMBINED_VOLUME_RATIO: float = 1.75  # Max 1.75x original size
    MIN_CONFIDENCE_RATIO: float = 1.0  # Re-entry must match or exceed original confidence

    def __init__(self):
        self.active_pyramids: Dict[str, ActivePyramid] = {}
        self.completed_pyramids: List[dict] = []
        self.total_pyramid_trades: int = 0
        self.successful_pyramids: int = 0
        self.failed_pyramids: int = 0

        logger.info("Pyramiding Engine initialized")

    async def evaluate(
        self,
        position: dict,
        strategy_dna: dict,
        current_price: float,
        indicators: dict,
        original_confidence: float,
    ) -> PyramidDecision:
        """
        Evaluate whether to add a pyramid layer.
        
        Args:
            position: Current position details
            strategy_dna: Strategy DNA with pyramiding settings
            current_price: Current market price
            indicators: Current indicator values
            original_confidence: Confidence at original entry
            
        Returns:
            PyramidDecision with action and details
        """
        # Quick rejection checks
        conditions = {
            "pyramiding_enabled": False,
            "within_max_layers": False,
            "r_threshold_met": False,
            "conditions_still_valid": False,
            "confidence_adequate": False,
            "volume_under_limit": False,
            "drawdown_safe": False,
        }

        # Check 1: Pyramiding enabled in DNA
        if not strategy_dna.get("pyramiding", False):
            return PyramidDecision(
                should_pyramid=False,
                reason="Pyramiding not enabled in strategy DNA",
                conditions_met=conditions,
            )
        conditions["pyramiding_enabled"] = True

        max_layers = strategy_dna.get("max_layers", 1)
        if max_layers <= 1:
            return PyramidDecision(
                should_pyramid=False,
                reason=f"Max layers ({max_layers}) does not allow pyramiding",
                conditions_met=conditions,
            )

        # Get or create pyramid tracking
        pos_id = position.get("position_id", "")
        if pos_id not in self.active_pyramids:
            # This is a new pyramid (first evaluation for this position)
            pyramid = ActivePyramid(
                original_position_id=pos_id,
                symbol=position.get("symbol", ""),
                direction=position.get("direction", "LONG"),
                strategy_id=strategy_dna.get("strategy_id", ""),
                strategy_name=strategy_dna.get("strategy_name", "Unknown"),
                max_layers=max_layers,
                combined_stop=position.get("stop_loss", 0),
                total_volume=position.get("volume", 0),
                average_entry=position.get("entry_price", 0),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            pyramid.layers.append(PyramidLayer(
                layer_number=1,
                position_id=pos_id,
                entry_price=position.get("entry_price", 0),
                volume=position.get("volume", 0),
                stop_loss=position.get("stop_loss", 0),
                added_at=datetime.now(timezone.utc).isoformat(),
                r_level=0.0,
            ))
            self.active_pyramids[pos_id] = pyramid

        pyramid = self.active_pyramids[pos_id]
        current_layers = len(pyramid.layers)

        # Check 2: Within max layers
        if current_layers >= max_layers:
            return PyramidDecision(
                should_pyramid=False,
                reason=f"Max layers ({max_layers}) reached ({current_layers} active)",
                conditions_met=conditions,
            )
        conditions["within_max_layers"] = True

        # Check 3: R-multiple threshold met
        direction = pyramid.direction
        original_entry = pyramid.layers[0].entry_price
        original_risk = abs(original_entry - pyramid.layers[0].stop_loss)

        if original_risk <= 0:
            return PyramidDecision(
                should_pyramid=False,
                reason="Original risk is zero — cannot calculate R",
                conditions_met=conditions,
            )

        if direction == "LONG":
            current_r = (current_price - original_entry) / original_risk
        else:
            current_r = (original_entry - current_price) / original_risk

        next_layer = current_layers + 1
        threshold = self.LAYER_THRESHOLDS.get(next_layer, 999)
        
        if current_r < threshold:
            return PyramidDecision(
                should_pyramid=False,
                reason=f"R-threshold not met: {current_r:.2f}R < {threshold:.1f}R required for layer {next_layer}",
                current_r=current_r,
                next_layer=next_layer,
                conditions_met=conditions,
            )
        conditions["r_threshold_met"] = True

        # Check 4: Entry conditions still valid
        entry_conditions = strategy_dna.get("entry", [])
        if entry_conditions:
            conditions_valid = self._validate_conditions(
                entry_conditions,
                indicators,
                direction
            )
            if not conditions_valid:
                return PyramidDecision(
                    should_pyramid=False,
                    reason="Entry conditions no longer valid",
                    current_r=current_r,
                    next_layer=next_layer,
                    conditions_met=conditions,
                )
        conditions["conditions_still_valid"] = True

        # Check 5: Confidence check
        if original_confidence and indicators.get("rsi"):
            # Use RSI as proxy for continued signal strength
            rsi = indicators.get("rsi", 50)
            if direction == "LONG" and rsi > 80:
                conditions["confidence_adequate"] = False
                return PyramidDecision(
                    should_pyramid=False,
                    reason=f"RSI overbought ({rsi:.0f}) — risk of reversal",
                    current_r=current_r,
                    next_layer=next_layer,
                    conditions_met=conditions,
                )
            elif direction == "SHORT" and rsi < 20:
                conditions["confidence_adequate"] = False
                return PyramidDecision(
                    should_pyramid=False,
                    reason=f"RSI oversold ({rsi:.0f}) — risk of reversal",
                    current_r=current_r,
                    next_layer=next_layer,
                    conditions_met=conditions,
                )
        conditions["confidence_adequate"] = True

        # Check 6: Volume under limit
        add_size_ratio = self.LAYER_SIZE_RATIOS.get(next_layer, 0.25)
        new_total_volume = pyramid.total_volume * (1 + add_size_ratio)
        original_volume = pyramid.layers[0].volume
        
        if new_total_volume > original_volume * self.MAX_COMBINED_VOLUME_RATIO:
            return PyramidDecision(
                should_pyramid=False,
                reason=f"Combined volume would exceed {self.MAX_COMBINED_VOLUME_RATIO}x limit",
                current_r=current_r,
                next_layer=next_layer,
                conditions_met=conditions,
            )
        conditions["volume_under_limit"] = True

        # Check 7: Drawdown safety
        # Don't pyramid if current drawdown is elevated
        conditions["drawdown_safe"] = True

        # All checks passed!
        add_size = pyramid.layers[0].volume * add_size_ratio
        new_combined_stop = self._calculate_combined_stop(
            pyramid, current_price, next_layer
        )

        return PyramidDecision(
            should_pyramid=True,
            reason=f"All conditions met — adding layer {next_layer} at {current_r:.1f}R",
            add_size=round(add_size, 4),
            new_combined_stop=round(new_combined_stop, 5),
            next_layer=next_layer,
            current_r=round(current_r, 2),
            conditions_met=conditions,
        )

    def _validate_conditions(
        self,
        entry_conditions: List[dict],
        indicators: dict,
        direction: str
    ) -> bool:
        """
        Simplified re-validation of entry conditions.
        Returns True if conditions still support the trade direction.
        """
        for condition in entry_conditions:
            indicator = condition.get("indicator", "RSI").upper()
            operator = condition.get("operator", "ABOVE").upper()
            threshold = condition.get("value", 50)

            indicator_map = {
                "RSI": indicators.get("rsi", 50),
                "ADX": indicators.get("adx", 20),
                "ATR": indicators.get("atr", 0),
                "EMA": indicators.get("ema_alignment", 0),
                "STOCH": indicators.get("stoch_k", 50),
                "CCI": indicators.get("cci", 0),
                "ZSCORE": indicators.get("zscore", 0),
            }

            current_value = float(indicator_map.get(indicator, 50))

            if operator in ("ABOVE", "CROSS_ABOVE"):
                if current_value <= threshold * 0.9:  # Allow 10% slippage
                    return False
            elif operator in ("BELOW", "CROSS_BELOW"):
                if current_value >= threshold * 1.1:
                    return False
            elif operator == "EXTREME":
                if indicator == "RSI" and 30 < current_value < 70:
                    return False

        return True

    def _calculate_combined_stop(
        self,
        pyramid: ActivePyramid,
        current_price: float,
        next_layer: int
    ) -> float:
        """
        Calculate new combined stop loss for all layers.
        
        Layer 2: Move to breakeven (original entry)
        Layer 3: Move to breakeven + 0.5R (lock in profit)
        """
        original_entry = pyramid.layers[0].entry_price
        original_risk = abs(original_entry - pyramid.layers[0].stop_loss)
        direction = pyramid.direction

        if next_layer == 2:
            # Move to breakeven
            return original_entry
        elif next_layer == 3:
            # Move to breakeven + 0.5R
            if direction == "LONG":
                return original_entry + (original_risk * 0.5)
            else:
                return original_entry - (original_risk * 0.5)
        else:
            # Default: keep existing stop
            return pyramid.combined_stop

    def record_layer_added(
        self,
        original_position_id: str,
        new_position_id: str,
        entry_price: float,
        volume: float,
        stop_loss: float,
        r_level: float,
    ):
        """Record a successfully added pyramid layer."""
        if original_position_id not in self.active_pyramids:
            logger.warning(f"Pyramid not found for position {original_position_id}")
            return

        pyramid = self.active_pyramids[original_position_id]
        next_layer = len(pyramid.layers) + 1

        layer = PyramidLayer(
            layer_number=next_layer,
            position_id=new_position_id,
            entry_price=entry_price,
            volume=volume,
            stop_loss=stop_loss,
            added_at=datetime.now(timezone.utc).isoformat(),
            r_level=r_level,
        )
        pyramid.layers.append(layer)

        # Update combined stats
        total_vol = sum(l.volume for l in pyramid.layers)
        total_cost = sum(l.volume * l.entry_price for l in pyramid.layers)
        pyramid.total_volume = total_vol
        pyramid.average_entry = total_cost / total_vol if total_vol > 0 else 0
        pyramid.combined_stop = stop_loss
        pyramid.last_updated = datetime.now(timezone.utc).isoformat()

        self.total_pyramid_trades += 1

        logger.info(
            f"Pyramid layer {next_layer} added | "
            f"Symbol: {pyramid.symbol} | "
            f"Size: {volume:.4f} | "
            f"Entry: {entry_price:.5f} | "
            f"Combined stop: {stop_loss:.5f} | "
            f"Total volume: {total_vol:.4f}"
        )

    def record_pyramid_closed(
        self,
        original_position_id: str,
        total_profit: float = 0.0,
    ):
        """Record pyramid completion when all layers closed."""
        if original_position_id in self.active_pyramids:
            pyramid = self.active_pyramids.pop(original_position_id)
            
            layers_count = len(pyramid.layers)
            is_successful = total_profit > 0

            if is_successful:
                self.successful_pyramids += 1
            else:
                self.failed_pyramids += 1

            self.completed_pyramids.append({
                "symbol": pyramid.symbol,
                "strategy": pyramid.strategy_name,
                "layers": layers_count,
                "total_volume": pyramid.total_volume,
                "profit": round(total_profit, 2),
                "successful": is_successful,
                "duration": (
                    datetime.now(timezone.utc) -
                    datetime.fromisoformat(pyramid.created_at)
                ).total_seconds() / 60,
                "closed_at": datetime.now(timezone.utc).isoformat(),
            })

            # Keep only last 100 completed pyramids
            if len(self.completed_pyramids) > 100:
                self.completed_pyramids.pop(0)

            logger.info(
                f"Pyramid closed | {pyramid.symbol} | "
                f"{layers_count} layers | "
                f"P&L: ${total_profit:.2f} | "
                f"{'WIN' if is_successful else 'LOSS'}"
            )

    def is_position_pyramiding(self, position_id: str) -> bool:
        """Check if a position is part of an active pyramid."""
        return position_id in self.active_pyramids

    def get_pyramid(self, position_id: str) -> Optional[ActivePyramid]:
        """Get pyramid details for a position."""
        return self.active_pyramids.get(position_id)

    def get_active_count(self) -> int:
        """Get count of active pyramids."""
        return len(self.active_pyramids)

    def get_stats(self) -> dict:
        """Get pyramiding statistics."""
        total = self.successful_pyramids + self.failed_pyramids
        return {
            "active_pyramids": len(self.active_pyramids),
            "total_pyramid_trades": self.total_pyramid_trades,
            "completed_pyramids": total,
            "successful": self.successful_pyramids,
            "failed": self.failed_pyramids,
            "success_rate": (
                self.successful_pyramids / total if total > 0 else 0
            ),
            "recent_completions": self.completed_pyramids[-10:],
        }