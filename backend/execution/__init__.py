"""
Execution module — order management and trade execution.
"""

from .orders import (
    execute_market,
    close_position,
    close_all,
    get_open_positions,
    ExecutionResult,
)

__all__ = [
    "execute_market",
    "close_position",
    "close_all",
    "get_open_positions",
    "ExecutionResult",
]