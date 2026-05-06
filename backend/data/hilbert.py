"""
Hilbert Transform Cycle Detector.
Extracts instantaneous phase, frequency, and amplitude from price cycles.
Identifies cycle turning points before they complete.

ZERO MODIFICATIONS to existing files.
Attaches via feature flag ENABLE_HILBERT_CYCLE in config.
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional, Dict
from dataclasses import dataclass
from scipy.signal import hilbert
from core.logger import get_logger

logger = get_logger("data.hilbert")


@dataclass
class CycleState:
    """Current cycle state from Hilbert Transform."""
    phase_degrees: float  # 0-360, where in the cycle
    dominant_period: int  # Estimated bars per cycle
    amplitude: float      # Cycle strength
    trend: float          # Underlying trend component
    signal: str           # "TURNING_POINT", "MID_CYCLE", "TRENDING", "WEAK"
    confidence: float     # 0-1


@dataclass
class HilbertOutput:
    """Complete Hilbert Transform output."""
    phase: np.ndarray
    dominant_cycle: np.ndarray
    amplitude: np.ndarray
    trend_line: np.ndarray
    cycle_state: CycleState
    reversal_probability: float


class HilbertCycleDetector:
    """
    Uses Hilbert Transform to detect market cycles.
    
    Extracts:
    - Instantaneous phase: Where in the current cycle (0-360°)
    - Dominant cycle period: How many bars per cycle
    - Cycle amplitude: How strong the cycle is
    - Trend component: Underlying trend beneath the cycle
    
    Trading signals:
    - Phase near 0° or 180° → Cycle turning point → Potential reversal
    - Phase near 90° or 270° → Cycle midpoint → Trend continuation
    - Low amplitude → Cycle weakening → Regime change possible
    """

    # Phase regions
    TURNING_REGION_DEGREES: float = 30  # +/- degrees around 0 and 180
    MID_CYCLE_REGION_DEGREES: float = 25  # +/- degrees around 90 and 270

    # Cycle detection parameters
    MIN_CYCLE_BARS: int = 6
    MAX_CYCLE_BARS: int = 50
    SMOOTHING_ORDER: int = 4

    def __init__(self):
        self.current_state: Optional[CycleState] = None
        self.cycle_history: list = []
        self.logger = logger

        logger.info("Hilbert Cycle Detector initialized")

    def analyze(self, price: pd.Series) -> HilbertOutput:
        """
        Apply Hilbert Transform to price series.
        
        Args:
            price: Price series (close prices)
            
        Returns:
            HilbertOutput with complete cycle analysis
        """
        if len(price) < self.MIN_CYCLE_BARS:
            return self._empty_output(len(price))

        # Detrend the price series
        trend = self._smooth(price, self.MAX_CYCLE_BARS)
        detrended = price - trend

        # Apply Hilbert Transform
        try:
            analytic_signal = hilbert(detrended.values)
            amplitude = np.abs(analytic_signal)
            phase = np.angle(analytic_signal)  # Radians (-π to π)

            # Convert to degrees (0 to 360)
            phase_degrees = np.degrees(phase) % 360

            # Estimate dominant cycle period
            dominant_cycle = self._estimate_dominant_cycle(phase)

            # Smooth amplitude
            amplitude_smooth = self._smooth(pd.Series(amplitude), 3)

            # Get current cycle state
            current_phase = float(phase_degrees[-1])
            current_amplitude = float(amplitude_smooth.iloc[-1])
            current_dominant = int(dominant_cycle[-1]) if len(dominant_cycle) > 0 else 20
            current_trend = float(trend.iloc[-1])

            # Classify cycle position
            cycle_state = self._classify_cycle_state(
                current_phase, current_dominant, current_amplitude
            )

            # Calculate reversal probability
            reversal_prob = self._calculate_reversal_probability(
                current_phase, current_amplitude, amplitude_smooth
            )

            self.current_state = cycle_state
            self.cycle_history.append({
                "phase": current_phase,
                "amplitude": current_amplitude,
                "period": current_dominant,
                "state": cycle_state.signal,
            })
            if len(self.cycle_history) > 100:
                self.cycle_history.pop(0)

            return HilbertOutput(
                phase=phase_degrees,
                dominant_cycle=dominant_cycle,
                amplitude=amplitude_smooth.values,
                trend_line=trend.values,
                cycle_state=cycle_state,
                reversal_probability=round(reversal_prob, 4),
            )

        except Exception as e:
            logger.error(f"Hilbert Transform error: {e}")
            return self._empty_output(len(price))

    def _smooth(self, series: pd.Series, period: int) -> pd.Series:
        """Apply smoothing to a series."""
        return series.rolling(
            window=period,
            min_periods=max(1, period // 2),
            center=False,
        ).mean()

    def _estimate_dominant_cycle(self, phase: np.ndarray) -> np.ndarray:
        """
        Estimate dominant cycle period from phase changes.
        The rate of phase change indicates the cycle frequency.
        """
        if len(phase) < 2:
            return np.array([self.MAX_CYCLE_BARS])

        # Calculate instantaneous frequency from phase differences
        phase_diff = np.diff(phase)
        # Convert to positive (unwrap diff)
        phase_diff = np.where(phase_diff < 0, phase_diff + 2 * np.pi, phase_diff)

        # Convert to cycle period (bars per cycle)
        cycle_periods = 2 * np.pi / np.maximum(phase_diff, 0.01)

        # Smooth and clip
        cycle_periods = np.clip(
            cycle_periods,
            self.MIN_CYCLE_BARS,
            self.MAX_CYCLE_BARS,
        )
        cycle_periods = np.insert(cycle_periods, 0, cycle_periods[0])

        # Apply smoothing
        if len(cycle_periods) > self.SMOOTHING_ORDER:
            smoothed = (
                pd.Series(cycle_periods)
                .rolling(self.SMOOTHING_ORDER, min_periods=1)
                .mean()
                .values
            )
            return smoothed

        return cycle_periods

    def _classify_cycle_state(
        self,
        phase_degrees: float,
        dominant_period: int,
        amplitude: float,
    ) -> CycleState:
        """
        Classify the current position in the market cycle.
        
        Phase regions:
        - 0° (±30°): Cycle trough — bullish reversal zone
        - 90° (±25°): Cycle rising midpoint — uptrend continuation
        - 180° (±30°): Cycle peak — bearish reversal zone
        - 270° (±25°): Cycle falling midpoint — downtrend continuation
        """
        # Normalize to 0-360
        phase = phase_degrees % 360

        # Determine signal
        if self._in_phase_region(phase, 0, self.TURNING_REGION_DEGREES):
            signal = "TURNING_POINT"
            confidence = 1.0 - (min(abs(phase - 0), abs(phase - 360)) / self.TURNING_REGION_DEGREES)
        elif self._in_phase_region(phase, 180, self.TURNING_REGION_DEGREES):
            signal = "TURNING_POINT"
            confidence = 1.0 - (abs(phase - 180) / self.TURNING_REGION_DEGREES)
        elif self._in_phase_region(phase, 90, self.MID_CYCLE_REGION_DEGREES):
            signal = "MID_CYCLE"
            confidence = 1.0 - (abs(phase - 90) / self.MID_CYCLE_REGION_DEGREES)
        elif self._in_phase_region(phase, 270, self.MID_CYCLE_REGION_DEGREES):
            signal = "MID_CYCLE"
            confidence = 1.0 - (abs(phase - 270) / self.MID_CYCLE_REGION_DEGREES)
        else:
            signal = "TRENDING"
            confidence = 0.5

        # Adjust confidence by amplitude
        if amplitude < 0.1:
            signal = "WEAK"
            confidence *= 0.5

        return CycleState(
            phase_degrees=round(phase, 1),
            dominant_period=dominant_period,
            amplitude=round(amplitude, 4),
            trend=0.0,
            signal=signal,
            confidence=round(min(0.95, confidence), 4),
        )

    @staticmethod
    def _in_phase_region(phase: float, center: float, tolerance: float) -> bool:
        """Check if phase is within tolerance of center."""
        if center == 0:
            return phase <= tolerance or phase >= (360 - tolerance)
        return abs(phase - center) <= tolerance

    def _calculate_reversal_probability(
        self,
        current_phase: float,
        current_amplitude: float,
        amplitude_history: pd.Series,
    ) -> float:
        """
        Calculate reversal probability based on phase and amplitude.
        
        Factors:
        - Phase proximity to turning points (0° or 180°)
        - Amplitude trend (declining = cycle weakening = possible reversal)
        """
        prob = 0.0

        # Phase factor
        phase_factor = 0.0
        if self._in_phase_region(current_phase, 0, self.TURNING_REGION_DEGREES):
            phase_factor = 1.0 - abs(current_phase - 0) / self.TURNING_REGION_DEGREES
        elif self._in_phase_region(current_phase, 180, self.TURNING_REGION_DEGREES):
            phase_factor = 1.0 - abs(current_phase - 180) / self.TURNING_REGION_DEGREES

        prob += phase_factor * 0.6

        # Amplitude factor (declining amplitude = cycle ending)
        if len(amplitude_history) >= 5:
            recent_trend = (
                amplitude_history.iloc[-1] - amplitude_history.iloc[-5]
            ) / max(amplitude_history.iloc[-5], 0.001)
            if recent_trend < -0.1:
                prob += 0.3

        return max(0.0, min(1.0, prob))

    def get_trading_signal(self) -> Optional[str]:
        """
        Get trading signal based on current cycle state.
        
        Returns:
            "BULLISH_REVERSAL", "BEARISH_REVERSAL", 
            "CONTINUATION_UP", "CONTINUATION_DOWN", or None
        """
        if not self.current_state:
            return None

        state = self.current_state

        if state.signal == "WEAK":
            return None
        if state.confidence < 0.6:
            return None

        phase = state.phase_degrees

        if self._in_phase_region(phase, 0, self.TURNING_REGION_DEGREES):
            return "BULLISH_REVERSAL"
        elif self._in_phase_region(phase, 180, self.TURNING_REGION_DEGREES):
            return "BEARISH_REVERSAL"
        elif self._in_phase_region(phase, 90, self.MID_CYCLE_REGION_DEGREES):
            return "CONTINUATION_UP"
        elif self._in_phase_region(phase, 270, self.MID_CYCLE_REGION_DEGREES):
            return "CONTINUATION_DOWN"

        return None

    def get_cycle_indicators(self, price: pd.Series) -> Dict[str, float]:
        """
        Extract cycle-based indicators for strategy evaluation.
        
        Returns dict with cycle metrics for use in DNA conditions.
        """
        output = self.analyze(price)
        state = output.cycle_state

        return {
            "hilbert_phase": state.phase_degrees,
            "hilbert_period": state.dominant_period,
            "hilbert_amplitude": state.amplitude,
            "hilbert_signal": (
                1.0 if state.signal in ("TURNING_POINT",)
                else 0.5 if state.signal == "MID_CYCLE"
                else 0.0
            ),
            "hilbert_reversal_prob": output.reversal_probability,
        }

    def _empty_output(self, length: int) -> HilbertOutput:
        """Return empty/default output when insufficient data."""
        return HilbertOutput(
            phase=np.zeros(length),
            dominant_cycle=np.full(length, 20),
            amplitude=np.zeros(length),
            trend_line=np.zeros(length),
            cycle_state=CycleState(
                phase_degrees=0,
                dominant_period=20,
                amplitude=0,
                trend=0,
                signal="WEAK",
                confidence=0,
            ),
            reversal_probability=0.0,
        )

    def get_stats(self) -> dict:
        """Get cycle detector statistics."""
        return {
            "current_state": (
                {
                    "phase": self.current_state.phase_degrees,
                    "period": self.current_state.dominant_period,
                    "amplitude": self.current_state.amplitude,
                    "signal": self.current_state.signal,
                    "confidence": self.current_state.confidence,
                }
                if self.current_state
                else None
            ),
            "history_samples": len(self.cycle_history),
        }