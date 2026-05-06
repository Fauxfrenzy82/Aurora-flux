"""
Thread-safe logging system with file rotation and structured events.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from datetime import datetime
from threading import Lock
from typing import Optional

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


class AuroraLogger:
    """
    Thread-safe logger with console output and rotating file handler.
    Supports structured logging for trades, evolution, and governance.
    """

    _instances: dict = {}
    _lock: Lock = Lock()

    def __new__(cls, name: str):
        with cls._lock:
            if name not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[name] = instance
            return cls._instances[name]

    def __init__(self, name: str):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.name = name
        self.logger = self._setup_logger(name)

    def _setup_logger(self, name: str) -> logging.Logger:
        """Configure logger with handlers."""
        logger = logging.getLogger(f"aurora.{name}")
        logger.setLevel(logging.DEBUG)

        if logger.handlers:
            return logger

        # Console handler (INFO level)
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
            "%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(console)

        # File handler with daily rotation (DEBUG level)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            LOG_DIR / f"aurora_{datetime.now().strftime('%Y%m%d')}.log",
            when="midnight",
            interval=1,
            backupCount=7,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
            "%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(file_handler)

        return logger

    # ── Standard Logging Methods ─────────────────────────

    def info(self, msg: str):
        """Log informational message."""
        self.logger.info(msg)

    def warning(self, msg: str):
        """Log warning message."""
        self.logger.warning(msg)

    def error(self, msg: str):
        """Log error message."""
        self.logger.error(msg)

    def critical(self, msg: str):
        """Log critical message."""
        self.logger.critical(msg)

    def debug(self, msg: str):
        """Log debug message."""
        self.logger.debug(msg)

    def exception(self, msg: str):
        """Log exception with traceback."""
        self.logger.exception(msg)

    # ── Structured Event Methods ─────────────────────────

    def trade(
        self,
        action: str,
        symbol: str,
        details: dict
    ):
        """Log a trade event with structured data."""
        self.logger.info(
            f"TRADE | {action} | {symbol} | "
            f"direction={details.get('direction', 'N/A')} | "
            f"size={details.get('size', details.get('volume', 'N/A'))} | "
            f"sl={details.get('sl', 'N/A')} | "
            f"tp={details.get('tp', 'N/A')} | "
            f"confidence={details.get('confidence', 'N/A')}"
        )

    def signal(
        self,
        symbol: str,
        strategy: str,
        direction: str,
        confidence: float
    ):
        """Log a generated signal."""
        self.logger.info(
            f"SIGNAL | {symbol} | {strategy} | "
            f"{direction} | confidence={confidence:.2%}"
        )

    def evolution(self, event: str, details: str):
        """Log an evolution event."""
        self.logger.info(f"EVOLUTION | {event} | {details}")

    def governance(
        self,
        decision: str,
        symbol: str = "",
        reason: str = ""
    ):
        """Log a governance decision."""
        self.logger.info(
            f"GOVERNANCE | {decision} | {symbol} | {reason}"
        )

    def risk(
        self,
        event: str,
        details: dict
    ):
        """Log a risk management event."""
        self.logger.info(
            f"RISK | {event} | "
            f"size={details.get('size', 'N/A')} | "
            f"risk_pct={details.get('risk_pct', 'N/A')} | "
            f"binding={details.get('binding', 'N/A')}"
        )

    def system(self, event: str, details: str = ""):
        """Log a system event."""
        self.logger.info(f"SYSTEM | {event} | {details}")

    def performance(
        self,
        strategy_id: str,
        win_rate: float,
        profit_factor: float,
        trades: int
    ):
        """Log strategy performance update."""
        self.logger.info(
            f"PERFORMANCE | {strategy_id} | "
            f"WR={win_rate:.2%} | PF={profit_factor:.2f} | "
            f"Trades={trades}"
        )


def get_logger(name: str) -> AuroraLogger:
    """Get or create a named logger instance."""
    return AuroraLogger(name)


# Pre-created system logger
system_log = get_logger("system")