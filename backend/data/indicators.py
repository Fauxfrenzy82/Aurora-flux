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
        """Volume Weighted Average Price."""
        typical_price = (high + low + close) / 3.0
        # Handle zero volume gracefully
        volume_safe = volume.replace(0, 1)
        cumulative_tp_vol = (typical_price * volume_safe).cumsum()
        cumulative_vol = volume_safe.cumsum()
        return (cumulative_tp_vol / cumulative_vol.replace(0, np.nan)).fillna(typical_price)

    # ── ICHIMOKU ────────────────────────────────────────

    @staticmethod
    def ichimoku(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series
    ) -> dict:
        """Ichimoku Cloud — complete components."""
        tenkan_sen = (
            high.rolling(9, min_periods=1).max() +
            low.rolling(9, min_periods=1).min()
        ) / 2.0

        kijun_sen = (
            high.rolling(26, min_periods=1).max() +
            low.rolling(26, min_periods=1).min()
        ) / 2.0

        senkou_span_a = ((tenkan_sen + kijun_sen) / 2.0).shift(26)
        senkou_span_b = (
            (
                high.rolling(52, min_periods=1).max() +
                low.rolling(52, min_periods=1).min()
            ) / 2.0
        ).shift(26)

        chikou_span = close.shift(-26)

        return {
            "tenkan": tenkan_sen,
            "kijun": kijun_sen,
            "senkou_a": senkou_span_a,
            "senkou_b": senkou_span_b,
            "chikou": chikou_span,
        }

    @staticmethod
    def ichimoku_signal(ichimoku_data: dict, close: pd.Series) -> pd.Series:
        """Generate Ichimoku signal: 1=above cloud, -1=below cloud, 0=inside."""
        above_cloud = (
            (close > ichimoku_data["senkou_a"]) &
            (close > ichimoku_data["senkou_b"])
        )
        below_cloud = (
            (close < ichimoku_data["senkou_a"]) &
            (close < ichimoku_data["senkou_b"])
        )
        signal = pd.Series(0, index=close.index)
        signal[above_cloud] = 1
        signal[below_cloud] = -1
        return signal

    # ── ADVANCED METRICS ────────────────────────────────

    @staticmethod
    def hurst_exponent(series: pd.Series, max_lag: int = 20) -> float:
        """
        Hurst Exponent — measures trend persistence.
        H > 0.5: trending, H < 0.5: mean-reverting, H ≈ 0.5: random walk.
        """
        cleaned = series.dropna()
        if len(cleaned) < max_lag:
            return 0.5
        if cleaned.std() == 0:
            return 0.5

        lags = range(2, min(max_lag, len(cleaned) // 2) + 1)
        tau = []
        for lag in lags:
            diff = cleaned.diff(lag).dropna()
            if len(diff) > 0:
                tau.append(float(np.std(diff)))

        if len(tau) < 2:
            return 0.5

        try:
            log_lags = np.log(list(lags))
            log_tau = np.log(tau)
            slope, _ = np.polyfit(log_lags, log_tau, 1)
            return float(np.clip(slope, 0.0, 1.0))
        except (np.linalg.LinAlgError, ValueError, RuntimeWarning):
            return 0.5

    @staticmethod
    def shannon_entropy(series: pd.Series, bins: int = 10) -> float:
        """
        Shannon Entropy of returns distribution.
        Higher values indicate more randomness/disorder.
        """
        returns = series.pct_change().dropna()
        if len(returns) < 20:
            return 1.0

        try:
            counts, _ = np.histogram(returns, bins=bins)
            probabilities = counts / counts.sum()
            probabilities = probabilities[probabilities > 0]
            entropy = -np.sum(probabilities * np.log2(probabilities))
            # Normalize to 0-1 range
            max_entropy = np.log2(bins)
            normalized = entropy / max_entropy if max_entropy > 0 else 0
            return float(normalized)
        except Exception:
            return 1.0

    @staticmethod
    def z_score(series: pd.Series, period: int = 20) -> pd.Series:
        """Rolling Z-Score — distance from mean in standard deviations."""
        mean = series.rolling(period, min_periods=1).mean()
        std = series.rolling(period, min_periods=1).std()
        z = (series - mean) / std.replace(0, np.nan)
        return z.fillna(0.0)

    # ── PRICE ACTION ────────────────────────────────────

    @staticmethod
    def pivot_points(
        high: float,
        low: float,
        close: float
    ) -> dict:
        """Classic pivot points from a single period."""
        pp = (high + low + close) / 3.0
        return {
            "pp": pp,
            "r1": 2.0 * pp - low,
            "r2": pp + (high - low),
            "r3": high + 2.0 * (pp - low),
            "r4": high + 3.0 * (pp - low),
            "s1": 2.0 * pp - high,
            "s2": pp - (high - low),
            "s3": low - 2.0 * (high - pp),
            "s4": low - 3.0 * (high - pp),
        }

    @staticmethod
    def swing_points(
        high: pd.Series,
        low: pd.Series,
        window: int = 5
    ) -> Tuple[List[int], List[int]]:
        """
        Detect swing highs and lows.
        Returns (swing_high_indices, swing_low_indices).
        """
        if len(high) < 2 * window + 1:
            return [], []

        swing_highs = []
        swing_lows = []

        for i in range(window, len(high) - window):
            if high.iloc[i] == high.iloc[i - window:i + window + 1].max():
                swing_highs.append(i)
            if low.iloc[i] == low.iloc[i - window:i + window + 1].min():
                swing_lows.append(i)

        return swing_highs, swing_lows

    @staticmethod
    def support_resistance(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        window: int = 20
    ) -> Tuple[pd.Series, pd.Series]:
        """Dynamic support and resistance levels."""
        resistance = high.rolling(window, min_periods=1).max()
        support = low.rolling(window, min_periods=1).min()
        return support, resistance

    # ── COMPOSITE CALCULATOR ────────────────────────────

    @staticmethod
    def calculate_all(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all technical indicators for a DataFrame.
        Expects columns: open, high, low, close.
        Optional: volume.
        """
        result = df.copy()

        # Validate required columns
        required = ["open", "high", "low", "close"]
        missing = [col for col in required if col not in result.columns]
        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")

        # Extract series
        o = result["open"]
        h = result["high"]
        l = result["low"]
        c = result["close"]
        v = result.get("volume", pd.Series([0] * len(result)))

        # Moving Averages
        for period in [8, 13, 20, 21, 50, 200]:
            result[f"ema_{period}"] = Indicators.ema(c, period)
            result[f"sma_{period}"] = Indicators.sma(c, period)

        # Oscillators
        result["rsi_14"] = Indicators.rsi(c, 14)
        result["rsi_7"] = Indicators.rsi(c, 7)
        result["stoch_k"], result["stoch_d"] = Indicators.stochastic(h, l, c)
        result["cci_20"] = Indicators.cci(h, l, c)

        # Volatility
        result["atr_14"] = Indicators.atr(h, l, c, 14)
        result["atr_50"] = Indicators.atr(h, l, c, 50)
        result["bb_upper"], result["bb_middle"], result["bb_lower"] = (
            Indicators.bollinger(c)
        )
        result["bb_width"] = Indicators.bollinger_width(c)
        result["bb_pct_b"] = Indicators.bollinger_pct_b(c)

        # Trend
        result["adx"], result["pdi"], result["ndi"] = Indicators.adx(h, l, c)

        # VWAP (only if volume data is meaningful)
        if v.sum() > 0 and v.max() > 0:
            result["vwap"] = Indicators.vwap(h, l, c, v)
        else:
            result["vwap"] = c  # Fallback to close price

        # Ichimoku
        ichi = Indicators.ichimoku(h, l, c)
        result["ichimoku_tenkan"] = ichi["tenkan"]
        result["ichimoku_kijun"] = ichi["kijun"]
        result["ichimoku_senkou_a"] = ichi["senkou_a"]
        result["ichimoku_senkou_b"] = ichi["senkou_b"]
        result["ichimoku_signal"] = Indicators.ichimoku_signal(ichi, c)

        # Composite signals
        # EMA alignment — positive when short > medium > long
        ema_8 = result.get("ema_8", c)
        ema_21 = result.get("ema_21", c)
        ema_50 = result.get("ema_50", c)
        result["ema_alignment"] = (
            (ema_8 - ema_21) / ema_21.replace(0, 1.0)
        ) * 0.5 + (
            (ema_21 - ema_50) / ema_50.replace(0, 1.0)
        ) * 0.5

        # Volatility ratio (current vs average)
        result["volatility_ratio"] = (
            result["atr_14"] /
            result["atr_14"].rolling(20, min_periods=1).mean().replace(0, 1.0)
        )

        # Volume ratio (current vs average)
        if v.sum() > 0 and v.max() > 0:
            result["volume_ratio"] = (
                v / v.rolling(20, min_periods=1).mean().replace(0, 1.0)
            )
        else:
            result["volume_ratio"] = 1.0

        # Z-Score of close
        result["z_score"] = Indicators.z_score(c)

        # Candle analysis
        result["body"] = (c - o).abs()
        result["upper_wick"] = h - result[["open", "close"]].max(axis=1)
        result["lower_wick"] = result[["open", "close"]].min(axis=1) - l
        result["total_range"] = h - l
        result["bullish"] = (c > o).astype(int)
        result["bearish"] = (c < o).astype(int)
        result["doji"] = (
            result["body"] < (result["atr_14"] * 0.1)
        ).astype(int)
        result["marubozu"] = (
            (result["upper_wick"] < result["body"] * 0.1) &
            (result["lower_wick"] < result["body"] * 0.1)
        ).astype(int)

        # Support & Resistance
        result["support_20"], result["resistance_20"] = (
            Indicators.support_resistance(h, l, c, 20)
        )

        # Forward fill any remaining NaN values, then fill with 0
        result = result.ffill().bfill().fillna(0)

        return result

    @staticmethod
    def calculate_quick(df: pd.DataFrame) -> pd.DataFrame:
        """
        Lightweight calculation — essential indicators only.
        Faster for high-frequency use.
        """
        result = df.copy()
        c = result["close"]
        h = result["high"]
        l = result["low"]

        result["ema_8"] = Indicators.ema(c, 8)
        result["ema_21"] = Indicators.ema(c, 21)
        result["rsi_14"] = Indicators.rsi(c, 14)
        result["atr_14"] = Indicators.atr(h, l, c, 14)
        result["adx"], result["pdi"], result["ndi"] = Indicators.adx(h, l, c)
        result["volatility_ratio"] = (
            result["atr_14"] /
            result["atr_14"].rolling(20, min_periods=1).mean().replace(0, 1.0)
        )
        result["bullish"] = (c > result["open"]).astype(int)

        return result.ffill().bfill().fillna(0)


# Module-level convenience function
def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all technical indicators for a DataFrame."""
    return Indicators.calculate_all(df)