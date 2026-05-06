"""
FastAPI server — REST API + WebSocket for real-time frontend.
Provides endpoints for monitoring, control, and data access.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database.supabase_client import db
from brokers.deriv_client import deriv
from execution.orders import (
    execute_market,
    close_position,
    close_all,
    get_open_positions,
    emergency_close,
)
from governance.checkpoints import Governance
from risk.sizing import calculate_position
from core.config import config
from core.logger import get_logger

logger = get_logger("api")

# ── FastAPI App ─────────────────────────────────────────

app = FastAPI(
    title="Aurora Flux API",
    description="Autonomous Forex Trading System",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global State ────────────────────────────────────────

governance = Governance()
active_websockets: List[WebSocket] = []
websocket_lock = asyncio.Lock()

current_state: dict = {
    "equity": config.INITIAL_CAPITAL,
    "balance": config.INITIAL_CAPITAL,
    "mode": config.MODE,
    "phase_day": 1,
    "regime": "UNKNOWN",
    "drawdown": 0.0,
    "positions": [],
    "daily_pnl": 0.0,
    "daily_trades": 0,
    "connected": False,
    "session": "UNKNOWN",
    "halted": False,
    "last_update": None,
    "uptime_seconds": 0,
}

_start_time = datetime.now(timezone.utc)


# ── Startup / Shutdown ──────────────────────────────────

@app.on_event("startup")
async def startup():
    """Initialize API server."""
    logger.info("Starting Aurora Flux API server...")

    # Validate configuration
    try:
        config.validate()
    except ValueError as e:
        logger.critical(f"Configuration error: {e}")
        raise

    # Connect to broker
    connected = await deriv.connect()
    current_state["connected"] = connected

    if connected:
        acc_info = await deriv.get_account_info()
        current_state["equity"] = acc_info.get("equity", config.INITIAL_CAPITAL)
        current_state["balance"] = acc_info.get("balance", config.INITIAL_CAPITAL)
        current_state["mode"] = config.MODE

        logger.info(
            f"API ready | Equity: ${current_state['equity']:.2f} | "
            f"Mode: {current_state['mode']}"
        )

        # Record startup
        await db.save_event(
            "API_STARTUP",
            "FastAPI server started",
            {"equity": current_state["equity"]}
        )
    else:
        logger.warning("API started but broker not connected")

    # Start background state updater
    asyncio.create_task(_state_updater())


@app.on_event("shutdown")
async def shutdown():
    """Graceful shutdown."""
    logger.info("Shutting down API server...")
    await db.save_event("API_SHUTDOWN", "FastAPI server stopping", {})
    await deriv.disconnect()


# ── Background State Updater ────────────────────────────

async def _state_updater():
    """Update current state every 5 seconds."""
    while True:
        try:
            current_state["uptime_seconds"] = (
                datetime.now(timezone.utc) - _start_time
            ).total_seconds()

            if current_state.get("connected"):
                acc_info = await deriv.get_account_info()
                if acc_info:
                    current_state["equity"] = acc_info.get("equity", current_state["equity"])
                    current_state["balance"] = acc_info.get("balance", current_state["balance"])

                current_state["positions"] = await get_open_positions()
                current_state["session"] = deriv.detect_session()
                current_state["halted"] = governance.halted

                # Calculate drawdown
                balance = current_state.get("balance", 1)
                equity = current_state.get("equity", 1)
                if balance > 0:
                    current_state["drawdown"] = max(0, (balance - equity) / balance)

                current_state["last_update"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            logger.error(f"State updater error: {e}")

        await asyncio.sleep(5)


# ── REST Endpoints ──────────────────────────────────────

@app.get("/")
async def root():
    """API root — health check."""
    return {
        "name": "Aurora Flux API",
        "version": "1.0.0",
        "status": "running",
        "uptime_seconds": (datetime.now(timezone.utc) - _start_time).total_seconds(),
    }


@app.get("/api/status")
async def get_status():
    """Get comprehensive system status."""
    return JSONResponse({
        **current_state,
        "governance": governance.get_stats(),
    })


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    broker_health = await deriv.health_check()
    db_health = await db.health_check()

    return {
        "status": "healthy" if (broker_health.get("status") == "connected") else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "broker": broker_health,
        "database": db_health,
    }


@app.get("/api/positions")
async def get_positions():
    """Get all open positions."""
    return await get_open_positions()


@app.get("/api/positions/count")
async def get_position_count():
    """Get count of open positions."""
    from execution.orders import get_position_count as gpc
    return {"count": await gpc()}


@app.get("/api/trades")
async def get_trades(
    limit: int = Query(50, ge=1, le=500),
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    result: Optional[str] = None,
):
    """Get recent trades with optional filters."""
    return await db.get_trades(
        limit=limit,
        symbol=symbol,
        strategy=strategy,
        result=result,
    )


@app.get("/api/trades/stats")
async def get_trade_stats(days: int = Query(30, ge=1, le=365)):
    """Get trade statistics for a period."""
    trades = await db.get_trades(limit=10000)
    # Filter by days
    cutoff = datetime.now(timezone.utc)
    from datetime import timedelta
    cutoff = cutoff - timedelta(days=days)

    filtered = []
    for t in trades:
        created = t.get("created_at", "")
        if created and created > cutoff.isoformat():
            filtered.append(t)

    wins = [t for t in filtered if t.get("result") == "WIN"]
    losses = [t for t in filtered if t.get("result") == "LOSS"]
    total = len(filtered)
    gross_profit = sum(t.get("profit_currency", 0) or 0 for t in wins)
    gross_loss = abs(sum(t.get("profit_currency", 0) or 0 for t in losses))

    return {
        "period_days": days,
        "total_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / total if total > 0 else 0,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "net_pnl": round(gross_profit - gross_loss, 2),
        "profit_factor": round(
            gross_profit / gross_loss if gross_loss > 0 else (999 if gross_profit > 0 else 0),
            2
        ),
    }


@app.get("/api/strategies")
async def get_strategies(
    status: Optional[str] = None,
    min_trades: Optional[int] = None,
):
    """Get strategies with optional filters."""
    return await db.get_strategies(status=status, min_trades=min_trades)


@app.get("/api/signals")
async def get_signals(
    limit: int = Query(50, ge=1, le=200),
    symbol: Optional[str] = None,
):
    """Get recent signals."""
    return await db.get_signals(limit=limit, symbol=symbol)


@app.get("/api/audit")
async def get_audit(
    limit: int = Query(50, ge=1, le=200),
    event_type: Optional[str] = None,
):
    """Get audit trail entries."""
    return await db.get_audit(limit=limit, event_type=event_type)


@app.get("/api/audit/verify")
async def verify_audit():
    """Verify audit chain integrity."""
    return await db.verify_audit_chain()


@app.get("/api/regime")
async def get_regime(pair: str = Query("EURUSD")):
    """Get latest regime for a pair."""
    return await db.get_latest_regime(pair)


@app.get("/api/snapshots")
async def get_snapshots(limit: int = Query(30, ge=1, le=100)):
    """Get account snapshots."""
    return await db.get_snapshots(limit=limit)


@app.get("/api/performance")
async def get_performance():
    """Get performance summary from strategy manager."""
    from main import get_system
    system = await get_system()
    return system.manager.get_performance_summary()


@app.get("/api/evolution")
async def get_evolution(limit: int = Query(20, ge=1, le=100)):
    """Get evolution history."""
    return await db.get_evolution_history(limit=limit)


@app.get("/api/events")
async def get_events(
    limit: int = Query(50, ge=1, le=200),
    event_type: Optional[str] = None,
):
    """Get system events."""
    return await db.get_events(limit=limit, event_type=event_type)


# ── Control Endpoints ───────────────────────────────────

@app.post("/api/control")
async def control(action: str = Query(...), **kwargs):
    """System control endpoint."""
    action = action.lower().strip()

    if action == "halt":
        governance.halt(kwargs.get("reason", "Manual halt via API"))
        current_state["halted"] = True
        await db.save_event("CONTROL", "System halted via API", {"action": action})
        return {"status": "halted", "reason": governance.halt_reason}

    elif action == "resume":
        governance.resume()
        current_state["halted"] = False
        await db.save_event("CONTROL", "System resumed via API", {"action": action})
        return {"status": "resumed"}

    elif action == "close_all":
        count = await close_all()
        await db.save_event("CONTROL", f"Closed all positions ({count})", {"action": action})
        return {"status": "closed", "count": count}

    elif action == "emergency":
        result = await emergency_close()
        governance.halt("Emergency close via API")
        current_state["halted"] = True
        await db.save_event("EMERGENCY", "Emergency close executed", result)
        return result

    elif action == "switch_mode":
        new_mode = kwargs.get("mode", "").upper()
        if new_mode in ("PHASE", "FREEDOM"):
            config.MODE = new_mode
            current_state["mode"] = new_mode
            await db.save_event("CONTROL", f"Mode switched to {new_mode}", {"action": action})
            return {"status": "switched", "mode": new_mode}
        return {"status": "error", "message": f"Invalid mode: {new_mode}"}

    else:
        return {"status": "error", "message": f"Unknown action: {action}"}


# ── WebSocket ───────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates."""
    await websocket.accept()

    async with websocket_lock:
        active_websockets.append(websocket)

    logger.info(f"WebSocket connected | Total: {len(active_websockets)}")

    try:
        # Send current state immediately
        await websocket.send_json({
            "type": "state_update",
            "data": current_state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Keep connection alive
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30
                )
                # Echo back for ping/pong
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await websocket.send_json({
                        "type": "heartbeat",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        async with websocket_lock:
            if websocket in active_websockets:
                active_websockets.remove(websocket)
        logger.info(f"WebSocket removed | Total: {len(active_websockets)}")


async def broadcast(event_type: str, data: dict):
    """Broadcast event to all connected WebSocket clients."""
    if not active_websockets:
        return

    message = json.dumps({
        "type": event_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, default=str)

    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)

    # Clean up disconnected clients
    if disconnected:
        async with websocket_lock:
            for ws in disconnected:
                if ws in active_websockets:
                    active_websockets.remove(ws)


async def get_system_status() -> dict:
    """Get full system status for API consumers."""
    return {
        **current_state,
        "governance": governance.get_stats(),
        "websocket_connections": len(active_websockets),
    }