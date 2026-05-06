"""
Centralized configuration management.
Reads from environment variables with sensible defaults.
"""

import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration loaded from environment."""

    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")

    # Deriv Broker (FREE — direct WebSocket, no cloud bridge)
    DERIV_APP_ID: str = os.getenv("DERIV_APP_ID", "")
    DERIV_API_TOKEN: str = os.getenv("DERIV_API_TOKEN", "")
    DERIV_SERVER: str = os.getenv("DERIV_SERVER", "Deriv-Demo")
    DERIV_LOGIN: str = os.getenv("DERIV_LOGIN", "")

    # Account
    BROKER: str = os.getenv("BROKER", "DERIV")
    ACCOUNT_TYPE: str = os.getenv("ACCOUNT_TYPE", "DEMO")
    INITIAL_CAPITAL: float = float(os.getenv("INITIAL_CAPITAL", "10.0"))

    # Trading Mode
    MODE: str = os.getenv("MODE", "PHASE")  # PHASE or FREEDOM

    # Risk Management
    BASE_RISK_PCT: float = float(os.getenv("BASE_RISK_PCT", "2.0"))
    MAX_DRAWDOWN_PCT: float = float(os.getenv("MAX_DRAWDOWN_PCT", "6.0"))
    DAILY_CAP_PCT: float = float(os.getenv("DAILY_CAP_PCT", "20.0"))
    CONFIDENCE_FLOOR: float = float(os.getenv("CONFIDENCE_FLOOR", "0.65"))
    MAX_POSITIONS: int = int(os.getenv("MAX_POSITIONS", "5"))
    MAX_EXPOSURE_PCT: float = float(os.getenv("MAX_EXPOSURE_PCT", "50.0"))

    # System
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    BACKTEST_MODE: bool = os.getenv("BACKTEST_MODE", "false").lower() == "true"

    # Phase Configuration
    PHASE_DURATION_DAYS: int = 5
    KELLY_FRACTION_PHASE: float = 0.25
    KELLY_FRACTION_FREEDOM: float = 1.0

    # Trading Universe
    TRADING_PAIRS: List[str] = [
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
        "AUDUSD", "USDCAD", "NZDUSD",
        "EURGBP", "EURJPY", "GBPJPY",
        "EURCHF", "GBPCHF", "AUDJPY"
    ]

    JPY_PAIRS: List[str] = [
        "USDJPY", "EURJPY", "GBPJPY", "AUDJPY"
    ]

    # Trading Sessions (UTC hours)
    SESSIONS: dict = {
        "ASIAN": (0, 7),
        "LONDON": (7, 16),
        "NEW_YORK": (13, 22),
        "OVERLAP": (13, 16),
    }

    @classmethod
    def validate(cls) -> bool:
        """Validate that all required configuration is present."""
        required = [
            "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "DERIV_APP_ID",
            "DERIV_API_TOKEN",
        ]
        missing = [key for key in required if not getattr(cls, key)]
        if missing:
            raise ValueError(
                f"Missing required configuration: {', '.join(missing)}"
            )
        return True

    @classmethod
    def pip_size(cls, symbol: str) -> float:
        """Return pip size for a given symbol."""
        if any(jpy in symbol.upper() for jpy in cls.JPY_PAIRS):
            return 0.01
        return 0.0001

    @classmethod
    def is_jpy_pair(cls, symbol: str) -> bool:
        """Check if symbol is a JPY pair."""
        return any(jpy in symbol.upper() for jpy in cls.JPY_PAIRS)

    @classmethod
    def get_session(cls, hour: int) -> str:
        """Get trading session name for a given UTC hour."""
        for session_name, (start, end) in cls.SESSIONS.items():
            if start <= hour < end:
                return session_name
        return "ASIAN"

    @classmethod
    def to_dict(cls) -> dict:
        """Export configuration as dictionary (secrets masked)."""
        return {
            "broker": cls.BROKER,
            "account_type": cls.ACCOUNT_TYPE,
            "initial_capital": cls.INITIAL_CAPITAL,
            "mode": cls.MODE,
            "base_risk_pct": cls.BASE_RISK_PCT,
            "max_drawdown_pct": cls.MAX_DRAWDOWN_PCT,
            "daily_cap_pct": cls.DAILY_CAP_PCT,
            "confidence_floor": cls.CONFIDENCE_FLOOR,
            "max_positions": cls.MAX_POSITIONS,
            "max_exposure_pct": cls.MAX_EXPOSURE_PCT,
            "phase_duration_days": cls.PHASE_DURATION_DAYS,
            "kelly_fraction": (
                cls.KELLY_FRACTION_PHASE
                if cls.MODE == "PHASE"
                else cls.KELLY_FRACTION_FREEDOM
            ),
            "trading_pairs": cls.TRADING_PAIRS,
            "jpy_pairs": cls.JPY_PAIRS,
            "backtest_mode": cls.BACKTEST_MODE,
        }


# Singleton instance
config = Config()