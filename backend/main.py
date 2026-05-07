"""
Aurora Flux — Main Entry Point.
Orchestrates trading, monitoring, evolution, and API.
"""

import asyncio
import signal
import sys
import traceback
from datetime import datetime, timezone
from typing import Dict, List
import pandas as pd

from brokers.deriv_client import deriv
from data.indicators import Indicators
from regime.ensemble import EnsembleClassifier
from strategies.manager import StrategyManager
from strategies.evolution import EvolutionEngine
from strategies.dna import generate_seeds
from governance.checkpoints import Governance
from risk.sizing import calculate_position
from execution.orders import execute_market, get_open_positions
from database.supabase_client import db
from api.server import app, current_state, broadcast
from core.config import config
from core.logger import get_logger

logger = get_logger("main")


class AuroraFlux:
    """Main trading system orchestrator."""

    def __init__(self):
        self.manager = StrategyManager()
        self.evolution = EvolutionEngine()
        self.classifier = EnsembleClassifier()
        self.governance = Governance()
        self.running = False
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.daily_risk_used = 0.0
        self.last_day = None
        self.current_session = "UNKNOWN"
        self.last_evolution_day = None
        self._monitored_trades: Dict[str, dict] = {}
        self._tasks: List[asyncio.Task] = []

    async def initialize(self) -> bool:
        """Initialize all subsystems."""
        print("DEBUG: initialize() called", flush=True)
        try:
            config.validate()
            print("DEBUG: config validated", flush=True)
            logger.info("Initializing Aurora Flux...")

            # Connect to broker
            print("DEBUG: connecting to Deriv...", flush=True)
            ok = await deriv.connect()
            print(f"DEBUG: deriv.connect() returned {ok}", flush=True)
            if not ok:
                logger.error("Failed to connect to Deriv")
                return False

            print("DEBUG: loading strategies...", flush=True)
            strategies = await db.get_strategies()
            if not strategies or len(strategies) < 10:
                logger.info("Generating seed strategies...")
                seeds = generate_seeds(250)
                strategies = [s.to_dict() for s in seeds]
                for s in strategies:
                    s["status"] = "TESTING"
                    s["generation"] = 0
                    s["birth_type"] = "SEED"
                    s["profit_factor"] = 0.0
                    s["win_rate"] = 0.0
                    s["total_trades"] = 0
                    await db.save_strategy(s)
                logger.info(f"Generated {len(strategies)} seed strategies")

            self.manager.load(strategies)
            print(f"DEBUG: {len(strategies)} strategies loaded", flush=True)

            # Get account state
            acc_info = await deriv.get_account_info()
            current_state["equity"] = acc_info.get("equity", config.INITIAL_CAPITAL)
            current_state["balance"] = acc_info.get("balance", config.INITIAL_CAPITAL)
            current_state["connected"] = True
            current_state["mode"] = config.MODE

            logger.info(
                f"Initialized | {len(strategies)} strategies | "
                f"Mode: {config.MODE} | Equity: ${current_state['equity']:.2f}"
            )

            await db.save_event(
                "STARTUP",
                f"Aurora Flux started | Mode: {config.MODE} | "
                f"Capital: ${current_state['equity']:.2f}",
                {"strategies_loaded": len(strategies)}
            )

            print("DEBUG: initialize() successful", flush=True)
            return True
        except Exception as e:
            print(f"DEBUG: initialize() CRASHED: {e}", flush=True)
            traceback.print_exc()
            return False

    async def trading_loop(self):
        """Main trading loop."""
        self.running = True
        logger.info("Trading loop started")

        while self.running:
            try:
                self.current_session = deriv.detect_session()
                now = datetime.now(timezone.utc)

                current_day = now.date()
                if self.last_day and self.last_day != current_day:
                    await self._daily_reset()
                self.last_day = current_day

                if self.current_session == "WEEKEND":
                    await self._handle_weekend()
                    await asyncio.sleep(3600)
                    continue

                if self.governance.halted:
                    await asyncio.sleep(10)
                    continue

                positions = await get_open_positions()
                current_state["positions"] = positions
                if len(positions) >= config.MAX_POSITIONS:
                    await self._monitor_positions(positions)
                    await asyncio.sleep(30)
                    continue

                for symbol in config.TRADING_PAIRS:
                    if not self.running:
                        break
                    if len(await get_open_positions()) >= config.MAX_POSITIONS:
                        break
                    await self._process_symbol(symbol)

                await self._monitor_positions(await get_open_positions())
                await self._save_snapshot()
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Trading loop error: {e}")
                await db.save_event("ERROR", f"Trading loop: {e}", {})
                await asyncio.sleep(30)

    async def _process_symbol(self, symbol: str):
        try:
            session = self.current_session
            candles = await deriv.get_candles(symbol, "H1", 200)
            if not candles or len(candles) < 50:
                logger.debug(f"Insufficient candle data for {symbol}")
                return

            df = pd.DataFrame(candles)
            df = Indicators.calculate_all(df)
            regime = self.classifier.classify(df)
            current_state["regime"] = regime.regime.value

            await db.save_regime(symbol, regime.regime.value, regime.confidence, {
                "adx": regime.adx, "ema_alignment": regime.ema_alignment,
                "volatility_ratio": regime.volatility_ratio, "volume_ratio": regime.volume_ratio,
            })

            if not regime.tradeable():
                return

            signals = self.manager.generate_signals(df, symbol, regime.regime.value, regime.confidence, session)
            if not signals:
                return

            signals = self.manager.filter_conflicts(signals)
            for sig in signals:
                await self._process_signal(sig, symbol, regime.confidence)

        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")

    async def _process_signal(self, signal: dict, symbol: str, regime_confidence: float):
        try:
            acc_info = await deriv.get_account_info()
            equity = acc_info.get("equity", current_state["equity"])
            balance = acc_info.get("balance", current_state["balance"])

            positions = await get_open_positions()
            total_exposure = sum(abs(p.get("volume", 0)) * p.get("current_price", 0) for p in positions)

            pos_size = calculate_position(
                entry=signal["entry_price"], stop=signal["stop_loss"],
                direction=signal["direction"], equity=equity, balance=balance,
                exposure=total_exposure, vol_ratio=1.0,
                daily_cap_remaining=max(0, equity * config.DAILY_CAP_PCT / 100 - abs(self.daily_pnl)),
                drawdown_budget=max(0, equity * config.MAX_DRAWDOWN_PCT / 100 - abs(current_state.get("drawdown", 0) * equity)),
                mode=config.MODE,
            )

            ctx = {
                "strategy_status": "ACTIVE", "daily_used": abs(self.daily_risk_used),
                "daily_cap": equity * config.DAILY_CAP_PCT / 100,
                "drawdown_pct": current_state.get("drawdown", 0),
                "max_drawdown": config.MAX_DRAWDOWN_PCT / 100,
                "regime_confidence": regime_confidence, "position_size_result": pos_size,
            }

            decision = self.governance.evaluate(signal, ctx)

            signal_data = {
                **signal, "governance_result": "APPROVED" if decision["approved"] else "REJECTED",
                "rejection_reason": None if decision["approved"] else decision.get("reason", "Unknown"),
            }
            await db.save_signal(signal_data)
            await db.append_audit("governance", {"signal": {"symbol": signal["symbol"], "direction": signal["direction"], "strategy": signal["strategy_name"]}, "decision": {"approved": decision["approved"], "reason": decision.get("reason", ""), "checkpoints": decision.get("checkpoints", [])}})

            if decision["approved"] and not pos_size.get("rejected") and pos_size["size"] > 0:
                result = await execute_market(symbol, signal["direction"], pos_size["size"], signal["stop_loss"], signal["take_profit"], signal.get("strategy_name", "AF"))
                if result.get("success"):
                    self.daily_trades += 1
                    self.daily_risk_used += pos_size.get("risk_amount", 0)
                    trade_id = result.get("order_id")
                    if trade_id:
                        self._monitored_trades[trade_id] = {
                            "symbol": symbol, "direction": signal["direction"],
                            "entry": signal["entry_price"], "sl": signal["stop_loss"],
                            "tp": signal["take_profit"], "strategy": signal["strategy_name"],
                            "strategy_id": signal.get("strategy_id"), "regime": signal.get("regime"),
                            "session": signal.get("session"), "confidence": signal.get("confidence"),
                            "risk_amount": pos_size.get("risk_amount", 0),
                            "risk_pct": pos_size.get("risk_pct", 0),
                            "opened_at": datetime.now(timezone.utc).isoformat(),
                        }
                    await broadcast("trade_executed", {"symbol": symbol, "direction": signal["direction"], "size": pos_size["size"], "strategy": signal["strategy_name"]})
                    logger.trade("EXECUTED", symbol, {"direction": signal["direction"], "size": pos_size["size"], "confidence": signal["confidence"], "strategy": signal["strategy_name"]})

        except Exception as e:
            logger.error(f"Signal processing error: {e}")

    async def _monitor_positions(self, positions: list):
        if not positions:
            return
        account_info = await deriv.get_account_info()
        current_state["equity"] = account_info.get("equity", current_state["equity"])
        current_state["balance"] = account_info.get("balance", current_state["balance"])
        if current_state["balance"] > 0:
            current_state["drawdown"] = max(0, (current_state["balance"] - current_state["equity"]) / current_state["balance"])
        open_ids = {p.get("position_id") for p in positions}
        closed_ids = set(self._monitored_trades.keys()) - open_ids
        for trade_id in closed_ids:
            trade_info = self._monitored_trades.pop(trade_id, None)
            if trade_info:
                await self._record_closed_trade(trade_id, trade_info)

    async def _record_closed_trade(self, trade_id: str, trade_info: dict):
        try:
            entry = trade_info.get("entry", 0)
            direction = trade_info.get("direction", "LONG")
            symbol = trade_info.get("symbol", "")
            bid, ask = await deriv.get_price(symbol)
            exit_price = bid if direction == "LONG" else ask
            if not exit_price:
                exit_price = entry
            pip_size = config.pip_size(symbol)
            profit_pips = (exit_price - entry) / pip_size if direction == "LONG" else (entry - exit_price) / pip_size
            profit_currency = profit_pips * pip_size * 100000
            result = "WIN" if profit_pips > 0.5 else ("LOSS" if profit_pips < -0.5 else "BREAKEVEN")
            await db.save_trade({
                "trade_id": trade_id, "symbol": symbol, "strategy_name": trade_info.get("strategy", "Unknown"),
                "direction": direction, "regime": trade_info.get("regime"), "session": trade_info.get("session"),
                "entry_price": entry, "exit_price": exit_price, "stop_loss": trade_info.get("sl"),
                "take_profit": trade_info.get("tp"), "profit_pips": round(profit_pips, 2),
                "profit_currency": round(profit_currency, 2), "result": result,
                "confidence": trade_info.get("confidence", 0), "risk_amount": trade_info.get("risk_amount", 0),
                "risk_pct": trade_info.get("risk_pct", 0),
            })
            strategy_id = trade_info.get("strategy_id")
            if strategy_id:
                self.manager.update_performance(strategy_id, profit_pips, result == "WIN")
            self.daily_pnl += profit_currency
            logger.trade("CLOSED", symbol, {"result": result, "profit_pips": round(profit_pips, 2), "profit_currency": round(profit_currency, 2), "strategy": trade_info.get("strategy")})
            await broadcast("trade_closed", {"symbol": symbol, "result": result, "profit_pips": round(profit_pips, 2), "strategy": trade_info.get("strategy")})
        except Exception as e:
            logger.error(f"Error recording closed trade: {e}")

    async def _daily_reset(self):
        logger.info(f"Daily reset | Yesterday: {self.daily_trades} trades, PnL: ${self.daily_pnl:.2f}")
        await db.save_event("DAILY_RESET", f"Daily reset | Trades: {self.daily_trades} | PnL: ${self.daily_pnl:.2f}", {"trades": self.daily_trades, "daily_pnl": self.daily_pnl, "daily_risk_used": self.daily_risk_used})
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.daily_risk_used = 0.0

    async def _handle_weekend(self):
        today = datetime.now(timezone.utc).date()
        if self.last_evolution_day == today:
            return
        self.last_evolution_day = today
        logger.info("Starting weekend evolution cycle...")
        try:
            strategies = await db.get_strategies()
            result = self.evolution.evolve(strategies)
            for s in result.get("strategies", []):
                await db.save_strategy(s)
            self.manager.load(result.get("strategies", strategies))
            await db.log_evolution({"event_type": "WEEKEND_CYCLE", "description": f"Gen {result['generation']}: {result['killed']} killed, {result['bred']} bred, {len(result.get('strategies', []))} total", "parent_ids": [], "reason": "Scheduled weekend evolution"})
            logger.evolution("CYCLE_COMPLETE", f"Gen {result['generation']}: {result['killed']} killed, {result['bred']} bred")
        except Exception as e:
            logger.error(f"Weekend evolution error: {e}")

    async def _save_snapshot(self):
        try:
            acc_info = await deriv.get_account_info()
            positions = await get_open_positions()
            total_exposure = sum(abs(p.get("volume", 0)) * p.get("current_price", 0) for p in positions)
            await db.save_snapshot({
                "balance": acc_info.get("balance", 0), "equity": acc_info.get("equity", 0),
                "margin": acc_info.get("margin", 0), "free_margin": acc_info.get("free_margin", 0),
                "open_positions": len(positions),
                "exposure_pct": total_exposure / acc_info.get("balance", 1) * 100 if acc_info.get("balance", 0) > 0 else 0,
                "daily_pnl": self.daily_pnl, "mode": config.MODE, "phase_day": getattr(self, "phase_day", 1),
            })
        except Exception as e:
            logger.error(f"Snapshot error: {e}")

    async def get_status(self) -> dict:
        perf_summary = self.manager.get_performance_summary()
        acc_info = await deriv.get_account_info()
        return {"running": self.running, "connected": deriv.connected, "session": self.current_session, "mode": config.MODE, "halted": self.governance.halted, "account": acc_info, "daily_trades": self.daily_trades, "daily_pnl": self.daily_pnl, "open_positions": len(await get_open_positions()), "performance": perf_summary, "active_strategies": perf_summary.get("active_strategies", 0)}

    async def shutdown(self):
        logger.info("Shutting down Aurora Flux...")
        self.running = False
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        await db.save_event("SHUTDOWN", "Aurora Flux shutting down", {})
        await deriv.disconnect()
        logger.info("Shutdown complete")


_system: AuroraFlux = None


async def get_system() -> AuroraFlux:
    global _system
    if _system is None:
        _system = AuroraFlux()
    return _system


async def main():
    """Main entry point."""
    try:
        print("DEBUG: main() started", flush=True)
        system = await get_system()
        print("DEBUG: get_system() done", flush=True)

        if not await system.initialize():
            print("DEBUG: initialize() returned False", flush=True)
            logger.critical("Failed to initialize. Exiting.")
            return

        print("DEBUG: initialize() successful, starting server", flush=True)

        import uvicorn
        config_dict = uvicorn.Config(app, host="0.0.0.0", port=config.API_PORT, log_level=config.LOG_LEVEL.lower())
        server = uvicorn.Server(config_dict)
        print("DEBUG: starting trading loop + server", flush=True)
        await asyncio.gather(system.trading_loop(), server.serve())
    except Exception as e:
        print(f"FATAL CRASH in main(): {e}", flush=True)
        traceback.print_exc()
        raise


if __name__ == "__main__":
    try:
        print("DEBUG: Starting asyncio.run(main())", flush=True)
        asyncio.run(main())
    except Exception as e:
        print(f"STARTUP CRASH: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)