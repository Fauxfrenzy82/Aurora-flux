"""
Aurora Flux — Autonomous Trading Organism
Main entry point. Coordinates the entire system lifecycle.
"""

import asyncio
import signal
import sys
from datetime import datetime, timezone
from typing import Optional

from core.config import config
from core.logger import get_logger, setup_logging
from database.supabase_client import db
from brokers.metaapi_client import metaapi
from regime.ensemble import EnsembleClassifier
from strategies.manager import StrategyManager
from strategies.dna import generate_seeds
from risk.sizing import calculate_position
from governance.checkpoints import Governance
from execution.orders import execute_market, get_open_positions
from api.server import app, broadcast, current_state
import uvicorn

logger = get_logger("main")


class AuroraFlux:
    """Main trading orchestrator."""

    def __init__(self):
        self.running = True
        self.regime_classifier = EnsembleClassifier()
        self.strategy_manager = StrategyManager()
        self.governance = Governance()
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_reset_day = -1
        self.last_regime_check = {}
        self.phase_day = 1
        self.consecutive_profitable_days = 0
        self.consecutive_losing_days = 0

    async def initialize(self) -> bool:
        """Initialize all components."""
        logger.info("=" * 50)
        logger.info("AURORA FLUX INITIALIZING")
        logger.info(f"Mode: {config.MODE}")
        logger.info(f"Initial Capital: ${config.INITIAL_CAPITAL:,.2f}")
        logger.info(f"Trading Pairs: {', '.join(config.TRADING_PAIRS)}")
        logger.info("=" * 50)

        # Connect to broker
        if not await metaapi.connect():
            logger.error("Failed to connect to broker")
            return False

        # Initialize database
        if not await db.initialize():
            logger.error("Failed to initialize database")
            return False

        # Load strategies
        strategies = await db.get_strategies(status="ACTIVE")
        seeds_created = False

        if not strategies:
            logger.info("No active strategies found — generating seeds")
            seeds = generate_seeds(250)
            for seed in seeds:
                await db.save_strategy(seed)
            strategies = await db.get_strategies(status="ACTIVE")
            seeds_created = True

        self.strategy_manager.load(strategies)
        logger.info(f"Loaded {len(strategies)} active strategies")

        # Load today's state
        await self._load_daily_state()

        # Record startup
        await db.save_event(
            "SYSTEM_START",
            f"Aurora Flux started in {config.MODE} mode",
            {"mode": config.MODE, "seeds_created": seeds_created}
        )

        # Update current state for API
        current_state["mode"] = config.MODE
        current_state["phase_day"] = self.phase_day

        return True

    async def _load_daily_state(self):
        """Load today's trading state."""
        today = datetime.now(timezone.utc).date().isoformat()
        daily = await db.get_daily_stats(today)
        if daily:
            self.daily_pnl = daily.get("pnl", 0.0)
            self.daily_trades = daily.get("trades", 0)

        # Load phase progress
        phase_data = await db.get_phase_progress()
        if phase_data:
            self.phase_day = phase_data.get("phase_day", 1)
            self.consecutive_profitable_days = phase_data.get("consecutive_profitable_days", 0)
            self.consecutive_losing_days = phase_data.get("consecutive_losing_days", 0)

            # Check phase completion
            if config.MODE == "PHASE" and self.phase_day > 5:
                if self.consecutive_profitable_days >= 4:
                    logger.info("Phase successful! Unlocking FREEDOM mode...")
                    config.MODE = "FREEDOM"
                    current_state["mode"] = "FREEDOM"
                    await db.save_event(
                        "PHASE_COMPLETE",
                        "Entering FREEDOM mode",
                        {"profitable_days": self.consecutive_profitable_days}
                    )
                else:
                    logger.warning(f"Phase failed: only {self.consecutive_profitable_days}/4 profitable days")

    async def _check_daily_reset(self):
        """Reset daily counters at market close (Friday 21:00 UTC)."""
        now = datetime.now(timezone.utc)
        current_day = now.day

        if current_day != self.daily_reset_day:
            is_reset_time = now.weekday() == 4 and now.hour >= 21

            if is_reset_time or self.daily_reset_day == -1:
                old_pnl = self.daily_pnl
                self.daily_pnl = 0.0
                self.daily_trades = 0
                self.daily_reset_day = current_day

                if config.MODE == "PHASE" and old_pnl != 0:
                    if old_pnl > 0:
                        self.consecutive_profitable_days += 1
                        self.consecutive_losing_days = 0
                        self.phase_day += 1
                    else:
                        self.consecutive_losing_days += 1
                        self.consecutive_profitable_days = 0
                        self.phase_day += 1

                    await db.save_phase_progress(
                        self.phase_day,
                        self.consecutive_profitable_days,
                        self.consecutive_losing_days
                    )

                    current_state["phase_day"] = self.phase_day

                await db.save_daily_snapshot(
                    date=now.date().isoformat(),
                    equity=current_state.get("equity", 0),
                    balance=current_state.get("balance", 0),
                    pnl=old_pnl,
                    trades=self.daily_trades
                )

                logger.info(f"Daily reset | P&L: ${old_pnl:+.2f} | Trades: {self.daily_trades}")

    async def _fetch_market_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch and process market data for a symbol."""
        try:
            from data.indicators import calculate_indicators
            import pandas as pd

            candles = await metaapi.get_candles(symbol, "H1", 200)
            if not candles or len(candles) < 50:
                return None

            df = pd.DataFrame(candles)
            df = calculate_indicators(df)
            return df
        except Exception as e:
            logger.error(f"Market data error for {symbol}: {e}")
            return None

    async def _evaluate_pair(self, symbol: str):
        """Complete evaluation cycle for a single trading pair."""
        df = await self._fetch_market_data(symbol)
        if df is None or df.empty:
            return

        regime_result = self.regime_classifier.classify(df, pair=symbol)
        current_regime = regime_result.regime.value
        regime_confidence = regime_result.confidence

        if not regime_result.tradeable():
            return

        session = metaapi.detect_session()
        signals = self.strategy_manager.generate_signals(
            df=df,
            symbol=symbol,
            regime=current_regime,
            regime_confidence=regime_confidence,
            session=session
        )

        if not signals:
            return

        signals = self.strategy_manager.filter_conflicts(signals)

        for signal in signals:
            await self._process_signal(signal, regime_result)

    async def _process_signal(self, signal: dict, regime_result):
        """Process a single trading signal through governance and execution."""
        symbol = signal["symbol"]
        direction = signal["direction"]
        entry_price = signal["entry_price"]
        stop_loss = signal["stop_loss"]
        take_profit = signal["take_profit"]
        confidence = signal["confidence"]
        strategy_id = signal["strategy_id"]

        open_positions = await get_open_positions()
        acc_info = await metaapi.get_account_info()
        equity = acc_info.get("equity", config.INITIAL_CAPITAL)

        position_size = calculate_position(
            entry=entry_price,
            stop=stop_loss,
            direction=direction,
            equity=equity,
            balance=acc_info.get("balance", equity),
            exposure=0.0,
            total_positions=len(open_positions)
        )

        if position_size.rejected:
            return

        governance_context = {
            "strategy_status": "ACTIVE",
            "daily_used": abs(self.daily_pnl) if self.daily_pnl < 0 else 0,
            "daily_cap": equity * config.DAILY_CAP_PCT / 100 if config.MODE == "PHASE" else 999999,
            "drawdown_pct": current_state.get("drawdown", 0),
            "max_drawdown": config.MAX_DRAWDOWN_PCT / 100,
            "regime_confidence": regime_result.confidence if regime_result else 0,
            "position_size_result": position_size,
        }

        gov_result = self.governance.evaluate(signal, governance_context)

        if not gov_result.approved:
            await db.save_event(
                "SIGNAL_REJECTED",
                f"Governance rejected {symbol} {direction}",
                {"reason": gov_result.reason}
            )
            return

        await execute_market(
            symbol=symbol,
            direction=direction,
            volume=position_size.size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=f"AF_{strategy_id}"
        )

        await db.save_event(
            "TRADE_EXECUTED",
            f"Executed {symbol} {direction}",
            {"size": position_size.size, "confidence": confidence}
        )

    async def _main_loop(self):
        """Primary trading loop."""
        while self.running:
            try:
                await self._check_daily_reset()

                if not metaapi.is_market_open():
                    await asyncio.sleep(300)
                    continue

                for symbol in config.TRADING_PAIRS:
                    try:
                        await self._evaluate_pair(symbol)
                    except Exception as e:
                        logger.error(f"Error processing {symbol}: {e}")
                    await asyncio.sleep(2)

                await asyncio.sleep(300)

            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(60)

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down Aurora Flux...")
        self.running = False
        await metaapi.close_all()
        await metaapi.disconnect()
        logger.info("Aurora Flux shutdown complete")

    async def run(self):
        """Main entry point."""
        if not await self.initialize():
            logger.critical("Initialization failed — exiting")
            return

        await self._main_loop()


# Global instance
_system: Optional[AuroraFlux] = None


async def get_system() -> AuroraFlux:
    global _system
    if _system is None:
        _system = AuroraFlux()
    return _system


async def run_api():
    """Run the FastAPI server."""
    config_uvicorn = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        loop="asyncio"
    )
    server = uvicorn.Server(config_uvicorn)
    await server.serve()


async def main():
    """Main entry point."""
    system = await get_system()
    await asyncio.gather(
        run_api(),
        system.run(),
        return_exceptions=True
    )


if __name__ == "__main__":
    asyncio.run(main())