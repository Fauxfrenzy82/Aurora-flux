"""
Order execution — wraps Deriv client for trade operations.
Provides clean interface with proper error handling and logging.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional, List
from brokers.deriv_client import deriv
from core.logger import get_logger
from core.config import config

logger = get_logger("execution")


@dataclass
class ExecutionResult:
    """Result of a trade execution attempt."""
    success: bool
    order_id: Optional[str] = None
    error: Optional[str] = None
    symbol: str = ""
    direction: str = ""
    volume: float = 0.0
    latency_ms: Optional[float] = None


async def execute_market(
    symbol: str,
    direction: str,
    volume: float,
    stop_loss: float = None,
    take_profit: float = None,
    comment: str = ""
) -> ExecutionResult:
    """
    Execute a market order with safety checks.
    
    Args:
        symbol: Trading pair (e.g., "EURUSD")
        direction: "BUY" or "SELL" (or "LONG"/"SHORT")
        volume: Position size in lots
        stop_loss: Stop loss price
        take_profit: Take profit price
        comment: Order comment
        
    Returns:
        ExecutionResult with success status and order details
    """
    import time

    # Normalize direction
    direction = direction.upper()
    if direction == "LONG":
        direction = "BUY"
    elif direction == "SHORT":
        direction = "SELL"

    if direction not in ("BUY", "SELL"):
        return ExecutionResult(
            success=False,
            error=f"Invalid direction: {direction}",
            symbol=symbol,
        )

    # Validate volume
    if volume <= 0:
        return ExecutionResult(
            success=False,
            error=f"Invalid volume: {volume}",
            symbol=symbol,
        )

    # Execute order
    start_time = time.monotonic()

    try:
        result = await deriv.market_order(
            symbol=symbol,
            direction=direction,
            volume=volume,
            sl=stop_loss,
            tp=take_profit,
            comment=comment
        )

        latency_ms = (time.monotonic() - start_time) * 1000

        if result and result.get("orderId"):
            logger.trade(
                "EXECUTED",
                symbol,
                {
                    "direction": direction,
                    "volume": volume,
                    "sl": stop_loss,
                    "tp": take_profit,
                    "order_id": result.get("orderId"),
                    "latency_ms": round(latency_ms, 1),
                }
            )
            return ExecutionResult(
                success=True,
                order_id=result.get("orderId"),
                symbol=symbol,
                direction=direction,
                volume=volume,
                latency_ms=round(latency_ms, 1),
            )
        else:
            logger.error(f"Order returned no orderId: {result}")
            return ExecutionResult(
                success=False,
                error=f"Order failed: {result}",
                symbol=symbol,
                direction=direction,
                volume=volume,
            )

    except Exception as e:
        latency_ms = (time.monotonic() - start_time) * 1000
        logger.error(f"Order execution error for {symbol} {direction}: {e}")
        return ExecutionResult(
            success=False,
            error=str(e),
            symbol=symbol,
            direction=direction,
            volume=volume,
            latency_ms=round(latency_ms, 1),
        )


async def close_position(position_id: str) -> bool:
    """Close a specific position by ID."""
    try:
        result = await deriv.close_position(position_id)
        if result:
            logger.trade("CLOSED", position_id, {"position_id": position_id})
        return result
    except Exception as e:
        logger.error(f"Failed to close position {position_id}: {e}")
        return False


async def close_all() -> int:
    """Close all open positions. Returns count of closed positions."""
    try:
        count = await deriv.close_all()
        logger.info(f"Closed all positions: {count}")
        return count
    except Exception as e:
        logger.error(f"Failed to close all positions: {e}")
        return 0


async def get_open_positions() -> list:
    """Get all currently open positions."""
    try:
        return await deriv.get_positions()
    except Exception as e:
        logger.error(f"Failed to get open positions: {e}")
        return []


async def get_position_count() -> int:
    """Get count of open positions."""
    try:
        return await deriv.get_position_count()
    except Exception as e:
        logger.error(f"Failed to count positions: {e}")
        return 0


async def emergency_close() -> dict:
    """
    Emergency procedure: close all positions and halt.
    Returns summary of actions taken.
    """
    logger.critical("EMERGENCY CLOSE INITIATED")

    positions_before = await get_position_count()
    closed = await close_all()
    positions_after = await get_position_count()

    result = {
        "positions_before": positions_before,
        "closed": closed,
        "positions_after": positions_after,
        "success": positions_after == 0,
    }

    logger.critical(f"EMERGENCY CLOSE COMPLETE: {result}")
    return result


async def get_execution_stats() -> dict:
    """Get execution statistics."""
    positions = await get_open_positions()
    total_exposure = 0.0
    total_unrealized_pnl = 0.0

    for p in positions:
        total_exposure += abs(p.get("volume", 0)) * p.get("current_price", 0)
        total_unrealized_pnl += p.get("profit", 0)

    return {
        "open_positions": len(positions),
        "total_exposure": round(total_exposure, 2),
        "unrealized_pnl": round(total_unrealized_pnl, 2),
        "symbols": list(set(p.get("symbol") for p in positions)),
    }