"""
Pattern-based regime classifier.
Identifies market patterns from price action and pattern library.
"""

import pandas as pd
from typing import Optional, List
from .types import MarketRegime, RegimeVote
from data.indicators import Indicators
from core.logger import get_logger

logger = get_logger("regime.pattern")


class PatternClassifier:
    """
    Pattern recognition-based regime classifier.
    Detects common chart patterns and maps them to regimes.
    """

    # Pattern definitions
    PATTERN_CONFIGS = {
        "double_top": {
            "regime_after": MarketRegime.TRENDING_DOWN,
            "confidence_boost": 0.15,
            "description": "Double top — bearish reversal"
        },
        "double_bottom": {
            "regime_after": MarketRegime.TRENDING_UP,
            "confidence_boost": 0.15,
            "description": "Double bottom — bullish reversal"
        },
        "head_and_shoulders": {
            "regime_after": MarketRegime.TRENDING_DOWN,
            "confidence_boost": 0.20,
            "description": "Head and shoulders — bearish reversal"
        },
        "ascending_triangle": {
            "regime_after": MarketRegime.TRENDING_UP,
            "confidence_boost": 0.10,
            "description": "Ascending triangle — bullish continuation"
        },
        "descending_triangle": {
            "regime_after": MarketRegime.TRENDING_DOWN,
            "confidence_boost": 0.10,
            "description": "Descending triangle — bearish continuation"
        },
        "bullish_flag": {
            "regime_after": MarketRegime.TRENDING_UP,
            "confidence_boost": 0.12,
            "description": "Bullish flag — trend continuation"
        },
        "bearish_flag": {
            "regime_after": MarketRegime.TRENDING_DOWN,
            "confidence_boost": 0.12,
            "description": "Bearish flag — trend continuation"
        },
    }

    def __init__(self, min_pattern_bars: int = 10):
        self.min_pattern_bars = min_pattern_bars

    def classify(self, df: pd.DataFrame, indicators: dict) -> RegimeVote:
        """
        Detect patterns in price action and classify regime.
        
        Args:
            df: OHLCV DataFrame
            indicators: Technical indicator values
            
        Returns:
            RegimeVote with pattern-based classification
        """
        if df.empty or len(df) < self.min_pattern_bars:
            return RegimeVote(
                MarketRegime.UNCERTAIN,
                0.3,
                "Insufficient data for pattern detection"
            )

        # Detect patterns
        detected_patterns = self._detect_patterns(df)

        if not detected_patterns:
            return self._default_classification(df, indicators)

        # Use strongest detected pattern
        strongest = max(detected_patterns, key=lambda x: x["confidence"])
        pattern_config = self.PATTERN_CONFIGS.get(
            strongest["pattern"],
            {}
        )

        regime = pattern_config.get(
            "regime_after",
            MarketRegime.UNCERTAIN
        )
        confidence = min(
            0.85,
            0.5 + pattern_config.get("confidence_boost", 0.0)
        )

        return RegimeVote(
            regime,
            confidence,
            f"{pattern_config.get('description', strongest['pattern'])}"
        )

    def _detect_patterns(self, df: pd.DataFrame) -> List[dict]:
        """Detect chart patterns in price data."""
        patterns = []

        # Get swing points
        highs, lows = Indicators.swing_points(
            df["high"],
            df["low"],
            window=5
        )

        if len(highs) < 2 or len(lows) < 2:
            return patterns

        # Check for double top/bottom
        dt_result = self._check_double_top(df, highs)
        if dt_result:
            patterns.append(dt_result)

        db_result = self._check_double_bottom(df, lows)
        if db_result:
            patterns.append(db_result)

        # Check for head and shoulders
        hs_result = self._check_head_shoulders(df, highs, lows)
        if hs_result:
            patterns.append(hs_result)

        return patterns

    def _check_double_top(
        self,
        df: pd.DataFrame,
        swing_highs: List[int]
    ) -> Optional[dict]:
        """Detect double top pattern."""
        if len(swing_highs) < 2:
            return None

        # Last two swing highs
        h1_idx = swing_highs[-2]
        h2_idx = swing_highs[-1]

        if h2_idx - h1_idx < 5:  # Too close
            return None

        h1_price = df["high"].iloc[h1_idx]
        h2_price = df["high"].iloc[h2_idx]

        # Tops should be similar in price
        price_similarity = 1 - abs(h1_price - h2_price) / max(h1_price, 0.001)
        if price_similarity < 0.98:  # Within 2%
            return None

        return {
            "pattern": "double_top",
            "confidence": 0.65 + price_similarity * 0.2,
            "indices": (h1_idx, h2_idx),
        }

    def _check_double_bottom(
        self,
        df: pd.DataFrame,
        swing_lows: List[int]
    ) -> Optional[dict]:
        """Detect double bottom pattern."""
        if len(swing_lows) < 2:
            return None

        l1_idx = swing_lows[-2]
        l2_idx = swing_lows[-1]

        if l2_idx - l1_idx < 5:
            return None

        l1_price = df["low"].iloc[l1_idx]
        l2_price = df["low"].iloc[l2_idx]

        price_similarity = 1 - abs(l1_price - l2_price) / max(l1_price, 0.001)
        if price_similarity < 0.98:
            return None

        return {
            "pattern": "double_bottom",
            "confidence": 0.65 + price_similarity * 0.2,
            "indices": (l1_idx, l2_idx),
        }

    def _check_head_shoulders(
        self,
        df: pd.DataFrame,
        swing_highs: List[int],
        swing_lows: List[int]
    ) -> Optional[dict]:
        """Detect head and shoulders pattern."""
        if len(swing_highs) < 3:
            return None

        # Last three swing highs: left shoulder, head, right shoulder
        ls_idx = swing_highs[-3]
        h_idx = swing_highs[-2]
        rs_idx = swing_highs[-1]

        ls_price = df["high"].iloc[ls_idx]
        h_price = df["high"].iloc[h_idx]
        rs_price = df["high"].iloc[rs_idx]

        # Head should be higher than shoulders
        if not (h_price > ls_price and h_price > rs_price):
            return None

        # Shoulders should be similar
        shoulder_similarity = 1 - abs(ls_price - rs_price) / max(ls_price, 0.001)
        if shoulder_similarity < 0.95:
            return None

        return {
            "pattern": "head_and_shoulders",
            "confidence": 0.7 + shoulder_similarity * 0.15,
            "indices": (ls_idx, h_idx, rs_idx),
        }

    def _default_classification(
        self,
        df: pd.DataFrame,
        indicators: dict
    ) -> RegimeVote:
        """Default classification when no patterns detected."""
        ema_align = indicators.get("ema_alignment", 0)
        if abs(ema_align) > 0.03:
            if ema_align > 0:
                return RegimeVote(
                    MarketRegime.TRENDING_UP,
                    0.55,
                    "Price action suggests uptrend"
                )
            else:
                return RegimeVote(
                    MarketRegime.TRENDING_DOWN,
                    0.55,
                    "Price action suggests downtrend"
                )

        return RegimeVote(
            MarketRegime.UNCERTAIN,
            0.35,
            "No clear pattern or trend detected"
        )