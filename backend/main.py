"""
Aurora Flux — Main Entry Point.
Orchestrates trading, monitoring, evolution, and API.
"""

import asyncio
import signal
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
        config.validate()
        logger.info("Initializing Aurora Flux...")

        # Connect to broker
        ok = await deriv.connect()
        if not ok:
            logger.error("Failed to connect to Deriv")
            return False

        # Load strategies
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

        # Get account state
        acc_info = await deriv.get_account_info()
        current_state["equity"] = acc_info.get("equity", config.INITIAL_CAPITAL)
        current_state["balance"] = acc_info.get("balance", config.INITIAL_CAPITAL)
        current_state["connected"] = True
        current_state["mode"] = config.MODE

        # Register signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                asyncio.get_event_loop().add_signal_handler(
                    sig,
                    lambda: asyncio.create_task(self.shutdown())
                )
            except NotImplementedError:
                pass

        logger.info(
            f"Initialized | {len(strategies)} strategies | "
            f"Mode: {config.MODE} | Equity: ${current_state['equity']:.2f}"
        )

        # Record startup event
        await db.save_event(
            "STARTUP",
            f"Aurora Flux started | Mode: {config.MODE} | "
            f"Capital: ${current_state['equity']:.2f}",
            {"strategies_loaded": len(strategies)}
        )

        return True

    async def trading_loop(self):
        """Main trading loop — scans pairs, generates signals, executes trades."""
        self.running = True
        logger.info("Trading loop started")

        while self.running:
            try:
                # Update session
                self.current_session = deriv.detect_session()
                now = datetime.now(timezone.utc)

                # Check for day reset
                current_day = now.date()
                if self.last_day and self.last_day != current_day:
                    await self._daily_reset()
                self.last_day = current_day

                # Weekend evolution
                if self.current_session == "WEEKEND":
                    await self._handle_weekend()
                    await asyncio.sleep(3600)
                    continue

                # Check if halted
                if self.governance.halted:
                    await asyncio.sleep(10)
                    continue

                # Check max positions
                positions = await get_open_positions()
                current_state["positions"] = positions
                if len(positions) >= config.MAX_POSITIONS:
                    await self._monitor_positions(positions)
                    await asyncio.sleep(30)
                    continue

                # Scan all trading pairs
                for symbol in config.TRADING_PAIRS:
                    if not self.running:
                        break

                    # Skip if max positions reached
                    if len(await get_open_positions()) >= config.MAX_POSITIONS:
                        break

                    await self._process_symbol(symbol)

                # Monitor existing positions
                await self._monitor_positions(await get_open_positions())

                # Periodic snapshot
                await self._save_snapshot()

                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Trading loop error: {e}")
                await db.save_event("ERROR", f"Trading loop: {e}", {})
                await asyncio.sleep(30)

    async def _process_symbol(self, symbol: str):
        """Process a single trading symbol."""
        try:
            session = self.current_session

            # Fetch candle data
            candles = await deriv.get_candles(symbol, "H1", 200)
            if not candles or len(candles) < 50:
                logger.debug(f"Insufficient candle data for {symbol}")
                return

            # Calculate indicators
            df = pd.DataFrame(candles)
            df = Indicators.calculate_all(df)

            # Classify regime
            regime = self.classifier.classify(df)
            current_state["regime"] = regime.regime.value

            # Save regime to database
            await db.save_regime(
                symbol,
                regime.regime.value,
                regime.confidence,
                {
                    "adx": regime.adx,
                    "ema_alignment": regime.ema_alignment,
                    "volatility_ratio": regime.volatility_ratio,
                    "volume_ratio": regime.volume_ratio,
                }
            )

            if not regime.tradeable():
                logger.debug(f"{symbol} not tradeable: {regime.regime.value}")
                return

            # Generate signals
            signals = self.manager.generate_signals(
                df,
                symbol,
                regime.regime.value,
                regime.confidence,
                session
            )

            if not signals:
                return

            # Filter conflicts
            signals = self.manager.filter_conflicts(signals)

            # Process each signal through governance
            for sig in signals:
                await self._process_signal(sig, symbol, regime.confidence)

        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")

    async def _process_signal(
        self,
        signal: dict,
        symbol: str,
        regime_confidence: float
    ):
        """Process a single trading signal through governance and execution."""
        try:
            # Get current account state
            acc_info = await deriv.get_account_info()
            equity = acc_info.get("equity", current_state["equity"])
            balance = acc_info.get("balance", current_state["balance"])

            # Calculate total exposure
            positions = await get_open_positions()
            total_exposure = sum(
                abs(p.get("volume", 0)) * p.get("current_price", 0)
                for p in positions
            )

            # Calculate position size
            pos_size = calculate_position(
                entry=signal["entry_price"],
                stop=signal["stop_loss"],
                direction=signal["direction"],
                equity=equity,
                balance=balance,
                exposure=total_exposure,
                vol_ratio=1.0,
                daily_cap_remaining=max(
                    0,
                    equity * config.DAILY_CAP_PCT / 100 - abs(self.daily_pnl)
                ),
                drawdown_budget=max(
                    0,
                    equity * config.MAX_DRAWDOWN_PCT / 100 - abs(
                        current_state.get("drawdown", 0) * equity
                    )
                ),
                mode=config.MODE,
            )

            # Governance check
            ctx = {
                "strategy_status": "ACTIVE",
                "daily_used": abs(self.daily_risk_used),
                "daily_cap": equity * config.DAILY_CAP_PCT / 100,
                "drawdown_pct": current_state.get("drawdown", 0),
                "max_drawdown": config.MAX_DRAWDOWN_PCT / 100,
                "regime_confidence": regime_confidence,
                "position_size_result": pos_size,
            }

            decision = self.governance.evaluate(signal, ctx)

            # Save signal
            signal_data = {
                **signal,
                "governance_result": (
                    "APPROVED" if decision["approved"] else "REJECTED"
                ),
                "rejection_reason": (
                    None if decision["approved"]
                    else decision.get("reason", "Unknown")
                ),
            }
            await db.save_signal(signal_data)

            # Audit the decision
            await db.append_audit("governance", {
                "signal": {
                    "symbol": signal["symbol"],
                    "direction": signal["direction"],
                    "strategy": signal["strategy_name"],
                },
                "decision": {
                    "approved": decision["approved"],
                    "reason": decision.get("reason", ""),
                    "checkpoints": decision.get("checkpoints", []),
                },
            })

            if decision["approved"] and not pos_size.get("rejected"):
                # Execute trade
                if pos_size["size"] > 0:
                    result = await execute_market(
                        symbol,
                        signal["direction"],
                        pos_size["size"],
                        signal["stop_loss"],
                        signal["take_profit"],
                        signal.get("strategy_name", "AF")
                    )

                    if result.get("success"):
                        self.daily_trades += 1
                        self.daily_risk_used += pos_size.get("risk_amount", 0)

                        # Track for monitoring
                        trade_id = result.get("order_id")
                        if trade_id:
                            self._monitored_trades[trade_id] = {
                                "symbol": symbol,
                                "direction": signal["direction"],
                                "entry": signal["entry_price"],
                                "sl": signal["stop_loss"],
                                "tp": signal["take_profit"],
                                "strategy": signal["strategy_name"],
                                "strategy_id": signal.get("strategy_id"),
                                "regime": signal.get("regime"),
                                "session": signal.get("session"),
                                "confidence": signal.get("confidence"),
                                "risk_amount": pos_size.get("risk_amount", 0),
                                "risk_pct": pos_size.get("risk_pct", 0),
                                "opened_at": datetime.now(timezone.utc).isoformat(),
                            }

                        await broadcast("trade_executed", {
                            "symbol": symbol,
                            "direction": signal["direction"],
                            "size": pos_size["size"],
                            "strategy": signal["strategy_name"],
                        })

                        logger.trade(
                            "EXECUTED",
                            symbol,
                            {
                                "direction": signal["direction"],
                                "size": pos_size["size"],
                                "confidence": signal["confidence"],
                                "strategy": signal["strategy_name"],
                            }
                        )

        except Exception as e:
            logger.error(f"Signal processing error: {e}")

    async def _monitor_positions(self, positions: list):
        """Monitor open positions for TP/SL hits and record results."""
        if not positions:
            return

        account_info = await deriv.get_account_info()
        current_state["equity"] = account_info.get("equity", current_state["equity"])
        current_state["balance"] = account_info.get("balance", current_state["balance"])

        # Update drawdown
        if current_state["balance"] > 0:
            current_state["drawdown"] = max(
                0,
                (current_state["balance"] - current_state["equity"])
                / current_state["balance"]
            )

        # Check for closed trades (positions that disappeared from monitored)
        open_ids = {p.get("position_id") for p in positions}
        closed_ids = set(self._monitored_trades.keys()) - open_ids

        for trade_id in closed_ids:
            trade_info = self._monitored_trades.pop(trade_id, None)
            if trade_info:
                await self._record_closed_trade(trade_id, trade_info)

    async def _record_closed_trade(self, trade_id: str, trade_info: dict):
        """Record a closed trade to the database."""
        try:
            entry = trade_info.get("entry", 0)
            direction = trade_info.get("direction", "LONG")

            # Get current price as approximate exit
            symbol = trade_info.get("symbol", "")
            bid, ask = await deriv.get_price(symbol)
            exit_price = bid if direction == "LONG" else ask
            if not exit_price:
                exit_price = entry

            # Calculate P&L
            pip_size = config.pip_size(symbol)
            if direction == "LONG":
                profit_pips = (exit_price - entry) / pip_size
            else:
                profit_pips = (entry - exit_price) / pip_size

            profit_currency = profit_pips * pip_size * 100000  # Standard lot approx

            # Determine result
            if profit_pips > 0.5:
                result = "WIN"
            elif profit_pips < -0.5:
                result = "LOSS"
            else:
                result = "BREAKEVEN"

            # Save trade to database
            trade_data = {
                "trade_id": trade_id,
                "symbol": symbol,
                "strategy_name": trade_info.get("strategy", "Unknown"),
                "direction": direction,
                "regime": trade_info.get("regime"),
                "session": trade_info.get("session"),
                "entry_price": entry,
                "exit_price": exit_price,
                "stop_loss": trade_info.get("sl"),
                "take_profit": trade_info.get("tp"),
                "profit_pips": round(profit_pips, 2),
                "profit_currency": round(profit_currency, 2),
                "result": result,
                "confidence": trade_info.get("confidence", 0),
                "risk_amount": trade_info.get("risk_amount", 0),
                "risk_pct": trade_info.get("risk_pct", 0),
            }
            await db.save_trade(trade_data)

            # Update strategy performance
            strategy_id = trade_info.get("strategy_id")
            if strategy_id:
                self.manager.update_performance(
                    strategy_id,
                    profit_pips,
                    result == "WIN"
                )

            # Update daily P&L
            self.daily_pnl += profit_currency

            logger.trade(
                "CLOSED",
                symbol,
                {
                    "result": result,
                    "profit_pips": round(profit_pips, 2),
                    "profit_currency": round(profit_currency, 2),
                    "strategy": trade_info.get("strategy"),
                }
            )

            await broadcast("trade_closed", {
                "symbol": symbol,
                "result": result,
                "profit_pips": round(profit_pips, 2),
                "strategy": trade_info.get("strategy"),
            })

        except Exception as e:
            logger.error(f"Error recording closed trade: {e}")

    async def _daily_reset(self):
        """Reset daily counters."""
        logger.info(
            f"Daily reset | Yesterday: {self.daily_trades} trades, "
            f"PnL: ${self.daily_pnl:.2f}"
        )
        await db.save_event(
            "DAILY_RESET",
            f"Daily reset | Trades: {self.daily_trades} | PnL: ${self.daily_pnl:.2f}",
            {
                "trades": self.daily_trades,
                "daily_pnl": self.daily_pnl,
                "daily_risk_used": self.daily_risk_used,
            }
        )

        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.daily_risk_used = 0.0

    async def _handle_weekend(self):
        """Run evolution cycle once per weekend."""
        today = datetime.now(timezone.utc).date()
        if self.last_evolution_day == today:
            return  # Already ran today

        self.last_evolution_day = today
        logger.info("Starting weekend evolution cycle...")

        try:
            strategies = await db.get_strategies()
            result = self.evolution.evolve(strategies)

            # Save updated strategies
            for s in result.get("strategies", []):
                await db.save_strategy(s)

            # Reload strategy manager
            self.manager.load(result.get("strategies", strategies))

            # Log evolution
            await db.log_evolution({
                "event_type": "WEEKEND_CYCLE",
                "description": (
                    f"Gen {result['generation']}: "
                    f"{result['killed']} killed, "
                    f"{result['bred']} bred, "
                    f"{len(result.get('strategies', []))} total"
                ),
                "parent_ids": [],
                "reason": "Scheduled weekend evolution",
            })

            logger.evolution(
                "CYCLE_COMPLETE",
                f"Gen {result['generation']}: "
                f"{result['killed']} killed, {result['bred']} bred"
            )

        except Exception as e:
            logger.error(f"Weekend evolution error: {e}")

    async def _save_snapshot(self):
        """Save periodic account snapshot."""
        try:
            acc_info = await deriv.get_account_info()
            positions = await get_open_positions()

            total_exposure = sum(
                abs(p.get("volume", 0)) * p.get("current_price", 0)
                for p in positions
            )

            snapshot = {
                "balance": acc_info.get("balance", 0),
                "equity": acc_info.get("equity", 0),
                "margin": acc_info.get("margin", 0),
                "free_margin": acc_info.get("free_margin", 0),
                "open_positions": len(positions),
                "exposure_pct": (
                    total_exposure / acc_info.get("balance", 1) * 100
                    if acc_info.get("balance", 0) > 0
                    else 0
                ),
                "daily_pnl": self.daily_pnl,
                "mode": config.MODE,
                "phase_day": getattr(self, "phase_day", 1),
            }

            await db.save_snapshot(snapshot)

        except Exception as e:
            logger.error(f"Snapshot error: {e}")

    async def get_status(self) -> dict:
        """Get comprehensive system status."""
        perf_summary = self.manager.get_performance_summary()
        acc_info = await deriv.get_account_info()

        return {
            "running": self.running,
            "connected": deriv.connected,
            "session": self.current_session,
            "mode": config.MODE,
            "halted": self.governance.halted,
            "account": acc_info,
            "daily_trades": self.daily_trades,
            "daily_pnl": self.daily_pnl,
            "open_positions": len(await get_open_positions()),
            "performance": perf_summary,
            "active_strategies": perf_summary.get("active_strategies", 0),
        }

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down Aurora Flux...")
        self.running = False

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        # Close all positions if configured
        await db.save_event("SHUTDOWN", "Aurora Flux shutting down", {})
        await deriv.disconnect()
        logger.info("Shutdown complete")


# ── Global System Instance ────────────────────────────────────
_system: AuroraFlux = None


async def get_system() -> AuroraFlux:
    global _system
    if _system is None:
        _system = AuroraFlux()
    return _system


async def main():
    """Main entry point."""
    system = await get_system()

    if not await system.initialize():
        logger.critical("Failed to initialize. Exiting.")
        return

    # Start API server
    import uvicorn
    config_dict = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=config.API_PORT,
        log_level=config.LOG_LEVEL.lower(),
    )
    server = uvicorn.Server(config_dict)

    # Run trading loop and API server concurrently
    await asyncio.gather(
        system.trading_loop(),
        server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())