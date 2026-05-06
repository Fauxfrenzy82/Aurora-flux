"""
Technical regime classifier — rule-based market state detection.
Uses ADX, EMA alignment, volatility, and volume to classify regimes.
"""

import numpy as np
import pandas as pd
from typing import Optional
from .types import MarketRegime, RegimeVote
from core.config import config


class TechnicalClassifier:
    """
    Rule-based market regime classifier using technical indicators.
    Detects trending, ranging, volatile, and transition states.
    """

    # Thresholds (calibrated for H1 timeframe)
    ADX_STRONG_TREND: float = 30.0
    ADX_TREND: float = 25.0
    ADX_RANGE: float = 20.0
    EMA_ALIGNMENT_THRESHOLD: float = 0.02
    VOLATILITY_EXPANSION_THRESHOLD: float = 1.5
    VOLATILITY_CONTRACTION_THRESHOLD: float = 0.7
    VOLUME_THRESHOLD: float = 1.5

    def __init__(
        self,
        adx_strong_trend: float = 30.0,
        adx_trend: float = 25.0,
        adx_range: float = 20.0,
        vol_expansion: float = 1.5,
        vol_contraction: float = 0.7,
        ema_align_threshold: float = 0.02,
        volume_threshold: float = 1.5,
    ):
        self.adx_strong_trend = adx_strong_trend
        self.adx_trend = adx_trend
        self.adx_range = adx_range
        self.vol_expansion = vol_expansion
        self.vol_contraction = vol_contraction
        self.ema_align_threshold = ema_align_threshold
        self.volume_threshold = volume_threshold

    def classify(self, indicators: dict) -> RegimeVote:
        """
        Classify market regime from technical indicators.
        
        Args:
            indicators: dict with keys: adx, pdi, ndi, ema_alignment, 
                       rsi_14, volatility_ratio, volume_ratio, hurst_exponent
            
        Returns:
            RegimeVote with regime and confidence
        """
        adx = float(indicators.get("adx", 20))
        pdi = float(indicators.get("pdi", 20))
        ndi = float(indicators.get("ndi", 20))
        ema_align = float(indicators.get("ema_alignment", 0))
        rsi = float(indicators.get("rsi_14", 50))
        vol_ratio = float(indicators.get("volatility_ratio", 1.0))
        volume_ratio = float(indicators.get("volume_ratio", 1.0))
        hurst = float(indicators.get("hurst_exponent", 0.5))

        # Check risk-off conditions
        if self._is_risk_off(vol_ratio, volume_ratio, rsi):
            return RegimeVote(
                MarketRegime.RISK_OFF,
                0.85,
                f"Risk-off: Vol={vol_ratio:.1f}x, VolVol={volume_ratio:.1f}x, RSI={rsi:.0f}"
            )

        # Check volatility expansion
        if vol_ratio > self.vol_expansion and volume_ratio > self.volume_threshold:
            confidence = min(0.95, 0.6 + (vol_ratio - self.vol_expansion) * 0.3)
            return RegimeVote(
                MarketRegime.VOLATILITY_EXPANSION,
                confidence,
                f"Volatility expansion: {vol_ratio:.1f}x vol, {volume_ratio:.1f}x volume"
            )

        # Check volatility contraction
        if vol_ratio < self.vol_contraction:
            return RegimeVote(
                MarketRegime.VOLATILITY_CONTRACTION,
                0.75,
                f"Volatility contraction: {vol_ratio:.1f}x"
            )

        # Check strong trends
        if adx > self.adx_strong_trend:
            return self._classify_strong_trend(adx, pdi, ndi, ema_align, hurst)

        # Check moderate trends
        if adx > self.adx_trend:
            return self._classify_trend(adx, pdi, ndi, ema_align)

        # Check range-bound
        if adx < self.adx_range:
            return self._classify_range(adx, ema_align, rsi)

        # Default: transition
        return RegimeVote(
            MarketRegime.TRANSITION,
            0.5 + (adx - self.adx_range) / (self.adx_trend - self.adx_range) * 0.3,
            f"Transition zone: ADX={adx:.0f}"
        )

    def _classify_strong_trend(
        self,
        adx: float,
        pdi: float,
        ndi: float,
        ema_align: float,
        hurst: float
    ) -> RegimeVote:
        """Classify strong trending conditions."""
        if pdi > ndi and ema_align > self.ema_align_threshold:
            confidence = min(
                0.95,
                0.7 + (adx - self.adx_strong_trend) / 50 + abs(ema_align) * 3
            )
            return RegimeVote(
                MarketRegime.STRONG_TREND_UP,
                confidence,
                f"Strong uptrend: ADX={adx:.0f}, +DI={pdi:.0f}, EMA_align={ema_align:.3f}"
            )
        elif ndi > pdi and ema_align < -self.ema_align_threshold:
            confidence = min(
                0.95,
                0.7 + (adx - self.adx_strong_trend) / 50 + abs(ema_align) * 3
            )
            return RegimeVote(
                MarketRegime.STRONG_TREND_DOWN,
                confidence,
                f"Strong downtrend: ADX={adx:.0f}, -DI={ndi:.0f}, EMA_align={ema_align:.3f}"
            )

        # Strong ADX but conflicting signals
        return RegimeVote(
            MarketRegime.TRANSITION,
            0.65,
            f"High ADX but conflicting: ADX={adx:.0f}, +DI={pdi:.0f}, -DI={ndi:.0f}"
        )

    def _classify_trend(
        self,
        adx: float,
        pdi: float,
        ndi: float,
        ema_align: float
    ) -> RegimeVote:
        """Classify moderate trending conditions."""
        if ema_align > self.ema_align_threshold and pdi > ndi:
            confidence = min(
                0.85,
                0.6 + (adx - self.adx_trend) / 30 + abs(ema_align) * 4
            )
            return RegimeVote(
                MarketRegime.TRENDING_UP,
                confidence,
                f"Uptrend: ADX={adx:.0f}, +DI={pdi:.0f}>-DI={ndi:.0f}"
            )
        elif ema_align < -self.ema_align_threshold and ndi > pdi:
            confidence = min(
                0.85,
                0.6 + (adx - self.adx_trend) / 30 + abs(ema_align) * 4
            )
            return RegimeVote(
                MarketRegime.TRENDING_DOWN,
                confidence,
                f"Downtrend: ADX={adx:.0f}, -DI={ndi:.0f}>+DI={pdi:.0f}"
            )

        return RegimeVote(
            MarketRegime.TRANSITION,
            0.6,
            f"Mixed signals: ADX={adx:.0f}, EMA_align={ema_align:.3f}"
        )

    def _classify_range(
        self,
        adx: float,
        ema_align: float,
        rsi: float
    ) -> RegimeVote:
        """Classify range-bound conditions."""
        if abs(ema_align) < self.ema_align_threshold and 30 < rsi < 70:
            confidence = min(0.85, 0.6 + (self.adx_range - adx) / 20)
            return RegimeVote(
                MarketRegime.RANGE_BOUND,
                confidence,
                f"Range-bound: ADX={adx:.0f}, RSI={rsi:.0f}, EMA flat"
            )

        return RegimeVote(
            MarketRegime.TRANSITION,
            0.5,
            f"Low ADX but not clean range: ADX={adx:.0f}, RSI={rsi:.0f}"
        )

    @staticmethod
    def _is_risk_off(
        vol_ratio: float,
        volume_ratio: float,
        rsi: float
    ) -> bool:
        """Detect risk-off conditions."""
        # Extreme volatility with high volume
        if vol_ratio > 2.5 and volume_ratio > 2.0:
            return True
        # Extreme RSI readings with high volatility
        if (rsi < 15 or rsi > 85) and vol_ratio > 2.0:
            return True
        return False

    def classify_from_dataframe(self, df: pd.DataFrame) -> RegimeVote:
        """Classify using the last row of a DataFrame."""
        if df.empty:
            return RegimeVote(MarketRegime.UNCERTAIN, 0.0, "Empty DataFrame")

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
        return self.classify(indicators)