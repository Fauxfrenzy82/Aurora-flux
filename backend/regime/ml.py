"""
Machine Learning regime classifier — XGBoost and HMM models.
Trained on labeled regime data for higher accuracy classification.
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple
from core.logger import get_logger

logger = get_logger("regime.ml")

# Placeholder for trained models (load from disk or database)
_xgboost_model = None
_hmm_model = None


class MLClassifier:
    """
    Machine learning-based regime classifier.
    Uses XGBoost for point-in-time classification and
    Hidden Markov Models for sequential state detection.
    """

    def __init__(self):
        self.xgb_model = _xgboost_model
        self.hmm_model = _hmm_model
        self.feature_columns = [
            "adx", "pdi", "ndi",
            "rsi_14", "ema_alignment",
            "volatility_ratio", "volume_ratio",
            "bb_width", "z_score",
            "hurst_exponent",
        ]

    def extract_features(self, indicators: dict) -> np.ndarray:
        """Extract feature vector from indicators dict."""
        features = []
        for col in self.feature_columns:
            value = indicators.get(col, 0)
            features.append(float(value) if value is not None else 0.0)
        return np.array(features).reshape(1, -1)

    def predict_xgboost(self, indicators: dict) -> Optional[Tuple[str, float]]:
        """
        Predict regime using XGBoost model.
        Returns (regime_label, confidence) or None if model not loaded.
        """
        if self.xgb_model is None:
            logger.debug("XGBoost model not loaded — using rule-based fallback")
            return None

        try:
            features = self.extract_features(indicators)
            probabilities = self.xgb_model.predict_proba(features)[0]
            predicted_class = self.xgb_model.classes_[
                np.argmax(probabilities)
            ]
            confidence = float(np.max(probabilities))
            return predicted_class, confidence
        except Exception as e:
            logger.error(f"XGBoost prediction error: {e}")
            return None

    def predict_hmm(self, indicator_sequence: pd.DataFrame) -> Optional[list]:
        """
        Predict regime sequence using HMM.
        Returns list of state labels or None if model not loaded.
        """
        if self.hmm_model is None:
            logger.debug("HMM model not loaded")
            return None

        try:
            features = indicator_sequence[self.feature_columns].values
            states = self.hmm_model.predict(features)
            return list(states)
        except Exception as e:
            logger.error(f"HMM prediction error: {e}")
            return None

    def is_available(self) -> bool:
        """Check if ML models are loaded."""
        return self.xgb_model is not None or self.hmm_model is not None


# Singleton
ml_classifier = MLClassifier()