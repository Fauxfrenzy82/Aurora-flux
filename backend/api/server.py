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

app = FastAPI(
    title="Aurora Flux API",
    description="Autonomous Forex Trading System",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.on_event("startup")
async def startup():
    logger.info("Starting Aurora Flux API server...")
    try:
        config.validate()
    except ValueError as e:
        logger.critical(f"Configuration error: {e}")
        raise

    connected = await deriv.connect()
    current_state["connected"] = connected

    if connected:
        acc_info = await deriv.get_account_info()
        current_state["equity"] = acc_info.get("equity", config.INITIAL_CAPITAL)
        current_state["balance"] = acc_info.get("balance", config.INITIAL_CAPITAL)
        current_state["mode"] = config.MODE
        logger.info(f"API ready | Equity: ${current_state['equity']:.2f} | Mode: {current_state['mode']}")
        await db.save_event("API_STARTUP", "FastAPI server started", {"equity": current_state["equity"]})
    else:
        logger.warning("API started but broker not connected")

    asyncio.create_task(_state_updater())


@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down API server...")
    await db.save_event("API_SHUTDOWN", "FastAPI server stopping", {})
    await deriv.disconnect()


async def _state_updater():
    while True:
        try:
            current_state["uptime_seconds"] = (datetime.now(timezone.utc) - _start_time).total_seconds()
            if current_state.get("connected"):
                acc_info = await deriv.get_account_info()
                if acc_info:
                    current_state["equity"] = acc_info.get("equity", current_state["equity"])
                    current_state["balance"] = acc_info.get("balance", current_state["balance"])
                current_state["positions"] = await get_open_positions()
                current_state["session"] = deriv.detect_session()
                current_state["halted"] = governance.halted
                balance = current_state.get("balance", 1)
                equity = current_state.get("equity", 1)
                if balance > 0:
                    current_state["drawdown"] = max(0, (balance - equity) / balance)
                current_state["last_update"] = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            logger.error(f"State updater error: {e}")
        await asyncio.sleep(5)


@app.get("/")
async def root():
    return {
        "name": "Aurora Flux API",
        "version": "1.0.0",
        "status": "running",
        "uptime_seconds": (datetime.now(timezone.utc) - _start_time).total_seconds(),
    }


@app.get("/api/status")
async def get_status():
    return JSONResponse({**current_state, "governance": governance.get_stats()})


@app.get("/api/health")
async def health_check():
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
    return await get_open_positions()


@app.get("/api/positions/count")
async def get_position_count():
    from execution.orders import get_position_count as gpc
    return {"count": await gpc()}


@app.get("/api/trades")
async def get_trades(
    limit: int = Query(50, ge=1, le=500),
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    result: Optional[str] = None,
):
    return await db.get_trades(limit=limit, symbol=symbol, strategy=strategy, result=result)


@app.get("/api/trades/stats")
async def get_trade_stats(days: int = Query(30, ge=1, le=365)):
    trades = await db.get_trades(limit=10000)
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    filtered = [t for t in trades if t.get("created_at", "") and t.get("created_at", "") > cutoff.isoformat()]
    wins = [t for t in filtered if t.get("result") == "WIN"]
    losses = [t for t in filtered if t.get("result") == "LOSS"]
    total = len(filtered)
    gross_profit = sum(t.get("profit_currency", 0) or 0 for t in wins)
    gross_loss = abs(sum(t.get("profit_currency", 0) or 0 for t in losses))
    return {
        "period_days": days, "total_trades": total, "wins": len(wins), "losses": len(losses),
        "win_rate": len(wins) / total if total > 0 else 0,
        "gross_profit": round(gross_profit, 2), "gross_loss": round(gross_loss, 2),
        "net_pnl": round(gross_profit - gross_loss, 2),
        "profit_factor": round(gross_profit / gross_loss if gross_loss > 0 else (999 if gross_profit > 0 else 0), 2),
    }


@app.get("/api/strategies")
async def get_strategies(status: Optional[str] = None, min_trades: Optional[int] = None):
    return await db.get_strategies(status=status, min_trades=min_trades)


@app.get("/api/signals")
async def get_signals(limit: int = Query(50, ge=1, le=200), symbol: Optional[str] = None):
    return await db.get_signals(limit=limit, symbol=symbol)


@app.get("/api/audit")
async def get_audit(limit: int = Query(50, ge=1, le=200), event_type: Optional[str] = None):
    return await db.get_audit(limit=limit, event_type=event_type)


@app.get("/api/audit/verify")
async def verify_audit():
    return await db.verify_audit_chain()


@app.get("/api/regime")
async def get_regime(pair: str = Query("EURUSD")):
    return await db.get_latest_regime(pair)


@app.get("/api/snapshots")
async def get_snapshots(limit: int = Query(30, ge=1, le=100)):
    return await db.get_snapshots(limit=limit)


@app.get("/api/performance")
async def get_performance():
    from main import get_system
    system = await get_system()
    return system.manager.get_performance_summary()


@app.get("/api/evolution")
async def get_evolution(limit: int = Query(20, ge=1, le=100)):
    return await db.get_evolution_history(limit=limit)


@app.get("/api/events")
async def get_events(limit: int = Query(50, ge=1, le=200), event_type: Optional[str] = None):
    return await db.get_events(limit=limit, event_type=event_type)


# ── NEW: Detailed Pairs Endpoint ──────────────────────

@app.get("/api/pairs/detailed")
async def get_detailed_pairs():
    """Get detailed status for all trading pairs with regime history, signals, and trades."""
    pairs_data = []
    for symbol in config.TRADING_PAIRS:
        regime_data = await db.get_latest_regime(symbol)
        regime_history = await db.get_regime_history(symbol, limit=5)
        signals = await db.get_signals(limit=5, symbol=symbol)
        trades = await db.get_trades(limit=3, symbol=symbol)

        pairs_data.append({
            "symbol": symbol,
            "latest_regime": {
                "regime": regime_data.get("regime", "UNKNOWN") if regime_data else "UNKNOWN",
                "confidence": regime_data.get("confidence", 0) if regime_data else 0,
                "timestamp": regime_data.get("created_at") if regime_data else None,
                "metrics": regime_data.get("metrics", {}) if regime_data else {},
            },
            "regime_history": [
                {"regime": r.get("regime"), "confidence": r.get("confidence"), "timestamp": r.get("created_at")}
                for r in (regime_history or [])
            ],
            "recent_signals": [
                {"direction": s.get("direction"), "confidence": s.get("confidence"),
                 "governance": s.get("governance_result"), "timestamp": s.get("created_at")}
                for s in (signals or [])
            ],
            "recent_trades": [
                {"direction": t.get("direction"), "result": t.get("result"),
                 "profit_pips": t.get("profit_pips"), "timestamp": t.get("created_at")}
                for t in (trades or [])
            ],
        })

    return JSONResponse({"pairs": pairs_data, "count": len(pairs_data)})


# ── NEW: Activity Logs Endpoint ────────────────────────

@app.get("/api/activity/logs")
async def get_activity_logs(limit: int = Query(50, ge=1, le=200)):
    """Get combined activity logs from regime history, signals, trades, and events."""
    regime_logs = await db.get_regime_history(limit=limit)
    signal_logs = await db.get_signals(limit=limit)
    trade_logs = await db.get_trades(limit=limit)
    event_logs = await db.get_events(limit=limit)

    combined = []

    for r in (regime_logs or []):
        combined.append({
            "type": "regime",
            "timestamp": r.get("created_at"),
            "symbol": r.get("pair"),
            "data": f"{r.get('regime')} ({round((r.get('confidence') or 0) * 100)}% conf)",
        })

    for s in (signal_logs or []):
        combined.append({
            "type": "signal",
            "timestamp": s.get("created_at"),
            "symbol": s.get("symbol"),
            "data": f"{s.get('direction')} {round((s.get('confidence') or 0) * 100)}% → {s.get('governance_result')}",
        })

    for t in (trade_logs or []):
        combined.append({
            "type": "trade",
            "timestamp": t.get("created_at"),
            "symbol": t.get("symbol"),
            "data": f"{t.get('direction')} {t.get('result') or 'OPEN'} ({t.get('profit_pips')} pips)",
        })

    for e in (event_logs or []):
        combined.append({
            "type": "event",
            "timestamp": e.get("created_at"),
            "symbol": "",
            "data": e.get("message", ""),
        })

    combined.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return JSONResponse({"logs": combined[:limit], "total": len(combined)})


# ── Control Endpoints ───────────────────────────────────

@app.post("/api/control")
async def control(action: str = Query(...), **kwargs):
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
    await websocket.accept()
    async with websocket_lock:
        active_websockets.append(websocket)
    logger.info(f"WebSocket connected | Total: {len(active_websockets)}")

    try:
        await websocket.send_json({
            "type": "state_update",
            "data": current_state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
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
    if not active_websockets:
        return
    message = json.dumps({"type": event_type, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()}, default=str)
    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    if disconnected:
        async with websocket_lock:
            for ws in disconnected:
                if ws in active_websockets:
                    active_websockets.remove(ws)


async def get_system_status() -> dict:
    return {**current_state, "governance": governance.get_stats(), "websocket_connections": len(active_websockets)}