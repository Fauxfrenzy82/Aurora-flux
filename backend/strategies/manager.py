"""
Strategy manager — coordinates all active strategies.
Handles signal generation, conflict resolution, and performance tracking.
"""

import uuid
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np

from .dna import StrategyDNA
from core.config import config
from core.logger import get_logger

logger = get_logger("strategy_manager")


class StrategyManager:
    """
    Manages the full lifecycle of trading strategies.
    Loads from database, generates signals, filters conflicts,
    and tracks real-time performance.
    """

    def __init__(self):
        self.strategies: Dict[str, dict] = {}
        self.performance: Dict[str, dict] = {}
        self._signal_counter: int = 0
        self._indicator_cache: Dict[str, dict] = {}

    def load(self, strategies: List[dict]):
        """Load strategies from database into memory."""
        self.strategies = {}
        active_count = 0
        for s in strategies:
            sid = s.get("strategy_id")
            if sid:
                self.strategies[sid] = s
                if s.get("status") in ("ACTIVE", "TESTING"):
                    active_count += 1

        logger.info(
            f"Loaded {len(self.strategies)} strategies "
            f"({active_count} active/testing)"
        )

    def get_active(self) -> List[dict]:
        """Get all active or testing strategies."""
        return [
            s for s in self.strategies.values()
            if s.get("status") in ("ACTIVE", "TESTING")
        ]

    def get_strategy(self, strategy_id: str) -> Optional[dict]:
        """Get a specific strategy by ID."""
        return self.strategies.get(strategy_id)

    def get_active_count(self) -> int:
        """Count of active strategies."""
        return len(self.get_active())

    def generate_signal_id(self) -> str:
        """Generate a unique signal identifier."""
        self._signal_counter += 1
        return f"SIG_{uuid.uuid4().hex[:8].upper()}_{self._signal_counter:06d}"

    def extract_indicators(self, df: pd.DataFrame) -> dict:
        """
        Extract indicator values from a DataFrame.
        Includes current and previous bar values for cross detection.
        """
        if df.empty:
            return {}

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        prev2 = df.iloc[-3] if len(df) > 2 else prev

        return {
            # Current values
            "close": float(latest.get("close", 0)),
            "open": float(latest.get("open", 0)),
            "high": float(latest.get("high", 0)),
            "low": float(latest.get("low", 0)),
            "rsi": float(latest.get("rsi_14", 50)),
            "rsi_7": float(latest.get("rsi_7", 50)),
            "adx": float(latest.get("adx", 20)),
            "pdi": float(latest.get("pdi", 20)),
            "ndi": float(latest.get("ndi", 20)),
            "atr": float(latest.get("atr_14", 0)),
            "ema_8": float(latest.get("ema_8", 0)),
            "ema_21": float(latest.get("ema_21", 0)),
            "ema_50": float(latest.get("ema_50", 0)),
            "ema_200": float(latest.get("ema_200", 0)),
            "sma_20": float(latest.get("sma_20", 0)),
            "ema_alignment": float(latest.get("ema_alignment", 0)),
            "bb_upper": float(latest.get("bb_upper", 0)),
            "bb_middle": float(latest.get("bb_middle", 0)),
            "bb_lower": float(latest.get("bb_lower", 0)),
            "bb_width": float(latest.get("bb_width", 0)),
            "bb_pct_b": float(latest.get("bb_pct_b", 0.5)),
            "stoch_k": float(latest.get("stoch_k", 50)),
            "stoch_d": float(latest.get("stoch_d", 50)),
            "cci": float(latest.get("cci_20", 0)),
            "vwap": float(latest.get("vwap", 0)),
            "zscore": float(latest.get("z_score", 0)),
            "volatility_ratio": float(latest.get("volatility_ratio", 1)),
            "volume_ratio": float(latest.get("volume_ratio", 1)),
            "bullish": bool(latest.get("bullish", True)),
            "bearish": bool(latest.get("bearish", False)),
            "doji": bool(latest.get("doji", False)),
            # Previous values for cross detection
            "rsi_prev": float(prev.get("rsi_14", 50)),
            "rsi_prev2": float(prev2.get("rsi_14", 50)),
            "stoch_k_prev": float(prev.get("stoch_k", 50)),
            "stoch_d_prev": float(prev.get("stoch_d", 50)),
            "adx_prev": float(prev.get("adx", 20)),
            "close_prev": float(prev.get("close", 0)),
            "ema_8_prev": float(prev.get("ema_8", 0)),
            "ema_21_prev": float(prev.get("ema_21", 0)),
            "bullish_prev": bool(prev.get("bullish", True)),
        }

    def evaluate_condition(
        self,
        condition: dict,
        indicators: dict
    ) -> Tuple[bool, float]:
        """
        Evaluate a single entry/exit condition.
        
        Returns:
            (triggered: bool, strength: float 0-1)
        """
        if not condition:
            return False, 0.0

        indicator = condition.get("indicator", "RSI").upper()
        operator = condition.get("operator", "ABOVE").upper()
        threshold = float(condition.get("value", 50))

        # Map indicator name to actual value
        indicator_map = {
            "RSI": indicators.get("rsi", 50),
            "RSI_7": indicators.get("rsi_7", 50),
            "ADX": indicators.get("adx", 20),
            "ATR": indicators.get("atr", 0),
            "EMA": indicators.get("ema_alignment", 0),
            "SMA": indicators.get("ema_alignment", 0),
            "BB": indicators.get("bb_pct_b", 0.5),
            "STOCH": indicators.get("stoch_k", 50),
            "CCI": indicators.get("cci", 0),
            "VWAP": indicators.get("vwap", 0),
            "ZSCORE": indicators.get("zscore", 0),
            "VOLATILITY": indicators.get("volatility_ratio", 1),
        }

        current_value = float(indicator_map.get(indicator, 0))
        prev_value = float(indicators.get(
            f"{indicator.lower()}_prev",
            current_value
        ))

        triggered = False
        strength = 0.0

        try:
            if operator == "ABOVE":
                triggered = current_value > threshold
                if triggered and threshold != 0:
                    strength = min(1.0, (current_value - threshold) / abs(threshold))
                else:
                    strength = 0.0

            elif operator == "BELOW":
                triggered = current_value < threshold
                if triggered and threshold != 0:
                    strength = min(1.0, (threshold - current_value) / abs(threshold))
                else:
                    strength = 0.0

            elif operator == "CROSS_ABOVE":
                triggered = (
                    prev_value <= threshold and
                    current_value > threshold
                )
                strength = 0.7 if triggered else 0.0

            elif operator == "CROSS_BELOW":
                triggered = (
                    prev_value >= threshold and
                    current_value < threshold
                )
                strength = 0.7 if triggered else 0.0

            elif operator == "EXTREME":
                if indicator in ("RSI", "STOCH"):
                    triggered = current_value > 80 or current_value < 20
                    strength = 0.8 if triggered else 0.0
                elif indicator == "CCI":
                    triggered = abs(current_value) > 200
                    strength = 0.75 if triggered else 0.0
                elif indicator == "ZSCORE":
                    triggered = abs(current_value) > 2.5
                    strength = 0.7 if triggered else 0.0

            elif operator == "DIVERGENCE":
                # Simple divergence: price making higher high but RSI lower high
                price_rising = indicators.get("close", 0) > indicators.get("close_prev", 0)
                rsi_falling = current_value < prev_value
                triggered = price_rising != rsi_falling  # Divergence
                strength = 0.6 if triggered else 0.0

        except Exception as e:
            logger.error(f"Condition evaluation error: {e}")
            triggered = False
            strength = 0.0

        return triggered, min(1.0, abs(strength))

    def _determine_direction(
        self,
        dna: StrategyDNA,
        indicators: dict
    ) -> str:
        """
        Determine trade direction from strategy DNA and current indicators.
        
        Returns:
            "LONG" or "SHORT"
        """
        entry_conditions = dna.entry_conditions
        if not entry_conditions:
            # Fallback to EMA alignment
            ema_align = indicators.get("ema_alignment", 0)
            return "LONG" if ema_align > 0 else "SHORT"

        first_condition = entry_conditions[0]
        indicator = first_condition.get("indicator", "RSI").upper()
        operator = first_condition.get("operator", "ABOVE").upper()
        threshold = first_condition.get("value", 50)

        # Direction logic based on indicator and operator
        oversold_long_indicators = {"RSI", "RSI_7", "STOCH", "CCI"}
        overbought_short_indicators = {"RSI", "RSI_7", "STOCH"}

        if indicator in oversold_long_indicators:
            if operator in ("BELOW", "CROSS_BELOW") or (
                operator == "EXTREME" and indicators.get(indicator.lower(), 50) < 30
            ):
                return "LONG"

        if indicator in overbought_short_indicators:
            if operator in ("ABOVE", "CROSS_ABOVE") or (
                operator == "EXTREME" and indicators.get(indicator.lower(), 50) > 70
            ):
                return "SHORT"

        # Trend following
        if operator in ("CROSS_ABOVE", "ABOVE") and indicator in ("ADX", "EMA", "SMA", "BB"):
            return "LONG"
        if operator in ("CROSS_BELOW", "BELOW") and indicator in ("ADX", "EMA", "SMA", "BB"):
            return "SHORT"

        # Default: use price action
        return "LONG" if indicators.get("bullish", True) else "SHORT"

    def generate_signals(
        self,
        df: pd.DataFrame,
        symbol: str,
        regime: str,
        regime_confidence: float,
        session: str = "UNKNOWN",
    ) -> List[dict]:
        """
        Generate trading signals from all active strategies.
        
        Each signal is evaluated through the strategy's DNA conditions.
        Returns list of signal dicts with full trade parameters.
        """
        signals = []
        indicators = self.extract_indicators(df)
        current_price = indicators.get("close", 0)
        atr = indicators.get("atr", current_price * 0.002)
        pip = config.pip_size(symbol)

        if current_price <= 0 or atr <= 0:
            return []

        active_strategies = self.get_active()
        logger.debug(
            f"Generating signals for {symbol}: "
            f"{len(active_strategies)} active strategies, "
            f"regime={regime}"
        )

        for s in active_strategies:
            try:
                dna_data = s.get("dna", {})
                if not dna_data:
                    continue

                dna = StrategyDNA.from_dict(dna_data)

                # Check regime compatibility
                if (
                    dna.regime_preference != "ALL" and
                    dna.regime_preference != regime
                ):
                    continue

                # Check session preference
                if (
                    dna.session_preference != "ALL" and
                    dna.session_preference != session
                ):
                    continue

                # Check pair preference
                if (
                    dna.pair_preference and
                    symbol not in dna.pair_preference
                ):
                    continue

                # Evaluate entry conditions (ALL must be met)
                entry_conditions = dna.entry_conditions
                if not entry_conditions:
                    continue

                all_triggered = True
                total_strength = 0.0

                for condition in entry_conditions:
                    triggered, strength = self.evaluate_condition(
                        condition, indicators
                    )
                    if not triggered:
                        all_triggered = False
                        break
                    total_strength += strength

                if not all_triggered:
                    continue

                # Average strength across conditions
                avg_strength = (
                    total_strength / len(entry_conditions)
                    if entry_conditions else 0
                )

                # Determine direction
                direction = self._determine_direction(dna, indicators)

                # Calculate stop loss
                stop_method = dna.stop_loss.get("method", "ATR_MULTIPLE")
                stop_value = dna.stop_loss.get("value", 1.5)

                if stop_method == "ATR_MULTIPLE":
                    stop_distance = atr * stop_value
                elif stop_method == "FIXED_PIPS":
                    stop_distance = stop_value * pip
                elif stop_method == "PERCENTAGE":
                    stop_distance = current_price * stop_value / 100
                elif stop_method == "SWING_LOW":
                    stop_distance = current_price - indicators.get("low", current_price)
                elif stop_method == "SWING_HIGH":
                    stop_distance = indicators.get("high", current_price) - current_price
                else:
                    stop_distance = atr * 1.5

                if direction == "LONG":
                    stop_loss = current_price - stop_distance
                else:
                    stop_loss = current_price + stop_distance

                # Calculate take profit
                tp_method = dna.take_profit.get("method", "RISK_REWARD")
                tp_value = dna.take_profit.get("value", 2.5)

                if tp_method == "RISK_REWARD":
                    tp_distance = stop_distance * tp_value
                elif tp_method == "ATR_MULTIPLE":
                    tp_distance = atr * tp_value
                elif tp_method == "FIXED_PIPS":
                    tp_distance = tp_value * pip
                else:
                    tp_distance = stop_distance * 2.5

                if direction == "LONG":
                    take_profit = current_price + tp_distance
                else:
                    take_profit = current_price - tp_distance

                # Calculate confidence
                strategy_confidence = float(s.get("win_rate", 0.5) or 0.5)
                base_confidence = 0.4 + avg_strength * 0.3
                regime_factor = 0.7 + regime_confidence * 0.3
                strategy_factor = 0.6 + strategy_confidence * 0.4

                final_confidence = min(
                    0.95,
                    base_confidence * regime_factor * strategy_factor
                )

                if final_confidence < config.CONFIDENCE_FLOOR:
                    continue

                # Build signal
                signal = {
                    "signal_id": self.generate_signal_id(),
                    "strategy_id": s.get("strategy_id"),
                    "strategy_name": s.get("strategy_name", "Unknown"),
                    "symbol": symbol,
                    "direction": direction,
                    "entry_price": round(current_price, 5),
                    "stop_loss": round(stop_loss, 5),
                    "take_profit": round(take_profit, 5),
                    "confidence": round(final_confidence, 4),
                    "regime": regime,
                    "session": session,
                    "expected_value": round(
                        (final_confidence * tp_distance) -
                        ((1 - final_confidence) * stop_distance),
                        5
                    ),
                }

                signals.append(signal)

            except Exception as e:
                logger.error(
                    f"Error generating signal for strategy "
                    f"{s.get('strategy_id', 'unknown')}: {e}"
                )
                continue

        logger.debug(f"Generated {len(signals)} signals for {symbol}")
        return signals

    def filter_conflicts(self, signals: List[dict]) -> List[dict]:
        """
        Filter conflicting signals per symbol.
        When multiple strategies conflict on direction:
        - Prefer the majority direction
        - Within that direction, keep top 2 by confidence
        """
        if len(signals) <= 1:
            return signals

        # Group by symbol
        by_symbol: Dict[str, list] = {}
        for s in signals:
            symbol = s.get("symbol", "UNKNOWN")
            by_symbol.setdefault(symbol, []).append(s)

        filtered = []

        for symbol, symbol_signals in by_symbol.items():
            long_signals = [
                s for s in symbol_signals
                if s.get("direction") == "LONG"
            ]
            short_signals = [
                s for s in symbol_signals
                if s.get("direction") == "SHORT"
            ]

            if long_signals and short_signals:
                # Conflict: prefer direction with more signals
                if len(long_signals) >= len(short_signals):
                    best = max(long_signals, key=lambda x: x.get("confidence", 0))
                    filtered.append(best)
                    logger.debug(
                        f"Conflict resolution for {symbol}: "
                        f"LONG ({len(long_signals)} signals) wins over "
                        f"SHORT ({len(short_signals)} signals)"
                    )
                else:
                    best = max(short_signals, key=lambda x: x.get("confidence", 0))
                    filtered.append(best)
                    logger.debug(
                        f"Conflict resolution for {symbol}: "
                        f"SHORT ({len(short_signals)} signals) wins over "
                        f"LONG ({len(long_signals)} signals)"
                    )

            elif long_signals:
                # Keep top 2 non-conflicting signals
                long_signals.sort(
                    key=lambda x: x.get("confidence", 0),
                    reverse=True
                )
                filtered.extend(long_signals[:2])

            elif short_signals:
                short_signals.sort(
                    key=lambda x: x.get("confidence", 0),
                    reverse=True
                )
                filtered.extend(short_signals[:2])

        return filtered

    def update_performance(
        self,
        strategy_id: str,
        profit: float,
        is_win: bool
    ):
        """
        Update strategy performance after trade closes.
        Tracks rolling win rate, profit factor, and streaks.
        """
        if strategy_id not in self.performance:
            self.performance[strategy_id] = {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "total_profit": 0.0,
                "total_loss": 0.0,
                "streak": 0,
                "max_win_streak": 0,
                "max_loss_streak": 0,
                "last_10_results": [],
            }

        perf = self.performance[strategy_id]
        perf["trades"] += 1

        if is_win:
            perf["wins"] += 1
            perf["total_profit"] += abs(profit)
            perf["streak"] = max(1, perf["streak"] + 1)
            perf["max_win_streak"] = max(perf["max_win_streak"], perf["streak"])
        else:
            perf["losses"] += 1
            perf["total_loss"] += abs(profit)
            perf["streak"] = min(-1, perf["streak"] - 1)
            perf["max_loss_streak"] = min(perf["max_loss_streak"], perf["streak"])

        # Track last 10 results
        perf["last_10_results"].append("WIN" if is_win else "LOSS")
        if len(perf["last_10_results"]) > 10:
            perf["last_10_results"].pop(0)

        # Calculate metrics
        total_trades = perf["trades"]
        wins = perf["wins"]
        total_profit = perf["total_profit"]
        total_loss = perf["total_loss"]

        win_rate = wins / total_trades if total_trades > 0 else 0.0
        profit_factor = (
            total_profit / total_loss if total_loss > 0
            else (999.0 if total_profit > 0 else 0.0)
        )

        # Update strategy record in memory
        if strategy_id in self.strategies:
            self.strategies[strategy_id]["win_rate"] = round(win_rate, 4)
            self.strategies[strategy_id]["profit_factor"] = round(profit_factor, 2)
            self.strategies[strategy_id]["total_trades"] = total_trades

            # Auto-suspend on losing streak
            if perf["streak"] <= -5:
                self.strategies[strategy_id]["status"] = "SUSPENDED"
                logger.performance(
                    strategy_id,
                    win_rate,
                    profit_factor,
                    total_trades
                )
                logger.warning(
                    f"Strategy {strategy_id} SUSPENDED: "
                    f"{abs(perf['streak'])} consecutive losses "
                    f"(WR: {win_rate:.2%}, PF: {profit_factor:.2f})"
                )

    def get_performance_summary(self) -> dict:
        """Get aggregate performance across all strategies."""
        total_trades = sum(p["trades"] for p in self.performance.values())
        total_wins = sum(p["wins"] for p in self.performance.values())
        total_profit = sum(p["total_profit"] for p in self.performance.values())
        total_loss = sum(p["total_loss"] for p in self.performance.values())

        net_pnl = total_profit - total_loss
        profit_factor = (
            total_profit / total_loss if total_loss > 0
            else (999.0 if total_profit > 0 else 0.0)
        )
        win_rate = total_wins / total_trades if total_trades > 0 else 0.0

        return {
            "total_trades": total_trades,
            "total_wins": total_wins,
            "total_losses": total_trades - total_wins,
            "win_rate": round(win_rate, 4),
            "total_profit": round(total_profit, 2),
            "total_loss": round(total_loss, 2),
            "net_pnl": round(net_pnl, 2),
            "profit_factor": round(profit_factor, 2),
            "active_strategies": self.get_active_count(),
            "total_strategies": len(self.strategies),
        }

    def get_top_strategies(self, n: int = 5) -> List[dict]:
        """Get top N performing strategies by P&L."""
        perf_list = []
        for sid, perf in self.performance.items():
            if perf["trades"] >= 5:
                net = perf["total_profit"] - perf["total_loss"]
                perf_list.append({
                    "strategy_id": sid,
                    "name": self.strategies.get(sid, {}).get("strategy_name", "Unknown"),
                    "trades": perf["trades"],
                    "win_rate": perf["wins"] / perf["trades"] if perf["trades"] > 0 else 0,
                    "net_pnl": round(net, 2),
                })

        perf_list.sort(key=lambda x: x["net_pnl"], reverse=True)
        return perf_list[:n]