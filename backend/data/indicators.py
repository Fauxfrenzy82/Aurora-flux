"""
Technical indicators — production-grade vectorized calculations.
All methods handle NaN, zero division, and edge cases gracefully.
Supports: EMA, SMA, ADX, RSI, ATR, Bollinger, Stochastic, CCI,
Ichimoku, Hurst Exponent, Shannon Entropy, Z-Score,
VWAP, Pivot Points, Swing Points, Candle Analysis.
"""

import numpy as np
import pandas as pd
from typing import Tuple, List, Optional


class Indicators:
    """Collection of technical indicator calculations."""

    # ── MOVING AVERAGES ─────────────────────────────────

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        """Exponential Moving Average."""
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        """Simple Moving Average with minimum periods."""
        return series.rolling(period, min_periods=1).mean()

    # ── OSCILLATORS ─────────────────────────────────────

    @staticmethod
    def rsi(close: pd.Series, period: int = 14) -> pd.Series:
        """Relative Strength Index — Wilder's smoothing."""
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta.where(delta < 0, 0.0))

        # Use Wilder's smoothing (EMA of gains/losses)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi_values = 100.0 - (100.0 / (1.0 + rs))
        return rsi_values.fillna(50.0).clip(0, 100)

    @staticmethod
    def stochastic(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        k_period: int = 14,
        d_period: int = 3
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Stochastic Oscillator.
        Returns (%K, %D).
        """
        lowest_low = low.rolling(k_period, min_periods=1).min()
        highest_high = high.rolling(k_period, min_periods=1).max()

        denominator = (highest_high - lowest_low).replace(0, np.nan)
        k_values = 100.0 * (close - lowest_low) / denominator
        k_values = k_values.fillna(50.0).clip(0, 100)
        d_values = k_values.rolling(d_period, min_periods=1).mean()

        return k_values, d_values

    @staticmethod
    def cci(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 20
    ) -> pd.Series:
        """Commodity Channel Index."""
        typical_price = (high + low + close) / 3.0
        sma_tp = typical_price.rolling(period, min_periods=1).mean()

        def mean_absolute_deviation(x):
            return np.mean(np.abs(x - np.mean(x)))

        mean_dev = typical_price.rolling(period, min_periods=1).apply(
            mean_absolute_deviation, raw=True
        )
        denominator = 0.015 * mean_dev
        denominator = denominator.replace(0, np.nan)

        cci_values = (typical_price - sma_tp) / denominator
        return cci_values.fillna(0.0)

    # ── VOLATILITY ──────────────────────────────────────

    @staticmethod
    def atr(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14
    ) -> pd.Series:
        """Average True Range."""
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()

        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return true_range.ewm(span=period, adjust=False).mean()

    @staticmethod
    def bollinger(
        close: pd.Series,
        period: int = 20,
        num_std: float = 2.0
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Bollinger Bands.
        Returns (upper_band, middle_band, lower_band).
        """
        middle = close.rolling(period, min_periods=1).mean()
        std = close.rolling(period, min_periods=1).std()
        upper = middle + num_std * std
        lower = middle - num_std * std
        return upper, middle, lower

    @staticmethod
    def bollinger_width(close: pd.Series, period: int = 20) -> pd.Series:
        """Bollinger Band Width — measures volatility."""
        upper, middle, lower = Indicators.bollinger(close, period)
        return ((upper - lower) / middle.replace(0, np.nan)).fillna(0)

    @staticmethod
    def bollinger_pct_b(close: pd.Series, period: int = 20) -> pd.Series:
        """Bollinger %B — position within bands."""
        upper, middle, lower = Indicators.bollinger(close, period)
        denominator = (upper - lower).replace(0, np.nan)
        return ((close - lower) / denominator).fillna(0.5).clip(0, 1)

    # ── TREND ───────────────────────────────────────────

    @staticmethod
    def adx(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Average Directional Index.
        Returns (ADX, +DI, -DI).
        """
        prev_close = close.shift(1)

        # True Range
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Directional Movement
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low

        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

        # Smooth with Wilder's method
        atr_smooth = true_range.ewm(alpha=1 / period, adjust=False).mean()
        plus_di = 100.0 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_smooth.replace(0, np.nan)
        minus_di = 100.0 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_smooth.replace(0, np.nan)

        # DX and ADX
        di_sum = plus_di + minus_di
        di_sum = di_sum.replace(0, np.nan)
        dx = 100.0 * (plus_di - minus_di).abs() / di_sum
        adx_values = dx.ewm(alpha=1 / period, adjust=False).mean()

        return adx_values.fillna(20.0), plus_di.fillna(20.0), minus_di.fillna(20.0)

    # ── VOLUME ──────────────────────────────────────────

    @staticmethod
    def vwap(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series
    ) -> pd.Series:
        """Volume Weighted Average