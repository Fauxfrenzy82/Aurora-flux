"""
Ensemble regime classifier — combines multiple classification methods.
Weights votes from technical, pattern, and ML classifiers.
"""

from datetime import datetime, timezone
from collections import Counter
from typing import Optional, Dict
import pandas as pd

from .types import (
    MarketRegime,
    RegimeVote,
    RegimeClassification,
    create_default_classification,
)
from .technical import TechnicalClassifier
from database.supabase_client import db
from core.logger import get_logger

logger = get_logger("regime")


class EnsembleClassifier:
    """
    Multi-method regime classifier with voting and persistence.
    Combines technical, pattern-based, and ML classifications.
    Tracks regime transitions with hysteresis to prevent flickering.
    """

    # Minimum bars before declaring a regime change
    TRANSITION_HYSTERESIS: int = 3
    # Weight for historical regime (prevents rapid switching)
    HISTORY_WEIGHT: float = 0.2

    def __init__(self):
        self.technical = TechnicalClassifier()
        # Per-pair regime tracking
        self._pair_states: Dict[str, dict] = {}

    def classify(
        self,
        df: pd.DataFrame,
        pair: str = "",
        indicators: dict = None
    ) -> RegimeClassification:
        """
        Ensemble regime classification with hysteresis.
        
        Args:
            df: OHLCV DataFrame with calculated indicators
            pair: Trading pair symbol
            indicators: Pre-calculated indicator dict (optional)
            
        Returns:
            RegimeClassification with ensemble result
        """
        # Get or initialize pair state
        if pair:
            state = self._pair_states.setdefault(pair, {
                "previous_regime": None,
                "regime_duration": 0,
                "transition_count": 0,
            })
        else:
            state = {
                "previous_regime": None,
                "regime_duration": 0,
                "transition_count": 0,
            }

        # Extract indicators from DataFrame if not provided
        if indicators is None and not df.empty:
            latest = df.iloc[-1]
            indicators = {
                "adx": latest.get("adx", 20),
                "pdi": latest.get("pdi", 20),
                "ndi": latest.get("ndi", 20),
                "ema_alignment": latest.get("ema_alignment", 0),
                "rsi_14": latest.get("rsi_14", 50),
                "volatility_ratio": latest.get("volatility_ratio", 1.0),
                "volume_ratio": latest.get("volume_ratio", 1.0),
                "hurst_exponent": latest.get("hurst_exponent", 0.5),
            }
        elif indicators is None:
            return create_default_classification()

        # Get votes from each classifier
        technical_vote = self.technical.classify(indicators)

        # Pattern and ML votes (extensible)
        # For now, use technical as base with slight variation
        pattern_vote = self._get_pattern_vote(indicators, df)
        ml_vote = self._get_ml_vote(indicators)

        # Combine votes with weighted scoring
        votes = [
            (technical_vote, 0.5),  # Technical: 50% weight
            (pattern_vote, 0.3),     # Pattern: 30% weight
            (ml_vote, 0.2),          # ML: 20% weight
        ]

        # Weighted voting
        regime_scores: Dict[MarketRegime, float] = {}
        for vote, weight in votes:
            regime_scores[vote.regime] = (
                regime_scores.get(vote.regime, 0) + vote.confidence * weight
            )

        # Find winning regime
        best_regime = max(regime_scores, key=regime_scores.get)
        raw_confidence = regime_scores[best_regime] / sum(
            w for _, w in votes
        )

        # Apply historical weighting
        best_regime, raw_confidence = self._apply_hysteresis(
            best_regime,
            raw_confidence,
            state,
            indicators
        )

        # Update state
        if state["previous_regime"] == best_regime:
            state["regime_duration"] += 1
        else:
            state["transition_count"] += 1
            if state["transition_count"] >= self.TRANSITION_HYSTERESIS:
                state["previous_regime"] = best_regime
                state["regime_duration"] = 1
                state["transition_count"] = 0

        # Detect transitions
        is_transitioning = (
            state["transition_count"] > 0 or
            raw_confidence < 0.65
        )

        return RegimeClassification(
            regime=best_regime,
            confidence=round(raw_confidence, 4),
            timestamp=datetime.now(timezone.utc),
            technical_vote=technical_vote,
            pattern_vote=pattern_vote,
            ml_vote=ml_vote,
            adx=indicators.get("adx", 0),
            ema_alignment=indicators.get("ema_alignment", 0),
            volatility_ratio=indicators.get("volatility_ratio", 1.0),
            volume_ratio=indicators.get("volume_ratio", 1.0),
            hurst_exponent=indicators.get("hurst_exponent", 0.5),
            is_transitioning=is_transitioning,
            previous_regime=state["previous_regime"],
            regime_duration_bars=state["regime_duration"],
            pair=pair,
        )

    def _get_pattern_vote(
        self,
        indicators: dict,
        df: pd.DataFrame
    ) -> RegimeVote:
        """
        Pattern-based regime classification.
        Extendable with pattern library matching.
        """
        # Check for known patterns in recent price action
        if df.empty or len(df) < 5:
            return RegimeVote(
                MarketRegime.UNCERTAIN,
                0.3,
                "Insufficient data for pattern analysis"
            )

        # Simplified pattern detection
        latest = df.iloc[-1]
        bullish_engulfing = (
            not latest.get("bullish", 0) and
            df.iloc[-1].get("bullish", 0)
        )

        vol_ratio = indicators.get("volatility_ratio", 1.0)
        ema_align = indicators.get("ema_alignment", 0)

        if bullish_engulfing and ema_align > 