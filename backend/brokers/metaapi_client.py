"""
MetaApi client — production-grade bridge to Exness MT5.
Uses metaapi-sdk v2 with automatic reconnection, tick streaming,
proper symbol handling, and comprehensive error management.
"""

import asyncio
from typing import Optional, Dict, List, Tuple, Callable, Any
from datetime import datetime, timezone
from metaapi_cloud_sdk import MetaApi
from core.config import config
from core.logger import get_logger

logger = get_logger("metaapi")


class MetaApiClient:
    """
    Thread-safe MetaApi broker bridge with automatic reconnection.
    Handles connection lifecycle, order execution, position tracking,
    market data, and WebSocket streaming.
    """

    MAX_RECONNECT_ATTEMPTS: int = 10
    RECONNECT_BASE_DELAY: float = 2.0
    RECONNECT_MAX_DELAY: float = 120.0
    HEALTH_CHECK_INTERVAL: int = 30

    def __init__(self):
        self.api: Optional[MetaApi] = None
        self.account: Any = None
        self.connection: Any = None
        self.terminal_state: Any = None
        self.connected: bool = False
        self._reconnecting: bool = False
        self._reconnect_count: int = 0
        self._callbacks: Dict[str, list] = {
            "tick": [],
            "position_update": [],
            "connection_status": [],
            "order_update": [],
        }
        self._subscriptions: set = set()
        self._connection_lock: asyncio.Lock = asyncio.Lock()
        self._last_health_check: float = 0

    # ── CONNECTION MANAGEMENT ────────────────────────────

    async def connect(self) -> bool:
        """
        Connect to MetaApi with proper initialization sequence.
        Returns True if connection established.
        """
        async with self._connection_lock:
            if self.connected:
                return True

            try:
                logger.info("Connecting to MetaApi...")

                # Initialize API
                self.api = MetaApi(
                    config.METAAPI_TOKEN,
                    {"application": config.METAAPI_APPLICATION}
                )

                # Get account
                self.account = await self.api.metatrader_account_api.get_account(
                    config.METAAPI_ACCOUNT_ID
                )

                # Wait for account to connect and synchronize
                logger.info("Waiting for account synchronization...")
                await self.account.wait_connected({"keepAlive": True})

                # Set up streaming connection
                self.connection = self.account.get_streaming_connection()
                await self.connection.connect()

                # Wait for terminal state synchronization
                await self.connection.wait_sync()
                self.terminal_state = self.connection.terminal_state
                self.connected = True
                self._reconnect_count = 0

                # Register connection status handler
                self.connection.on("status", self._on_connection_status)

                # Get account information
                acc_info = self.terminal_state.account_information
                logger.info(
                    f"Connected successfully | "
                    f"Login: {acc_info.get('login')} | "
                    f"Balance: {acc_info.get('balance', 0):.2f} "
                    f"{acc_info.get('currency', 'USD')} | "
                    f"Equity: {acc_info.get('equity', 0):.2f} | "
                    f"Leverage: 1:{acc_info.get('leverage', 0)}"
                )

                # Subscribe to configured trading pairs
                await self._subscribe_all_pairs()

                # Notify status callbacks
                await self._notify_connection_status(True)

                return True

            except Exception as e:
                logger.error(f"Connection failed: {e}")
                self.connected = False
                await self._notify_connection_status(False)
                return False

    async def _on_connection_status(self, status: dict):
        """Handle MetaApi connection status changes."""
        status_type = status.get("type", "UNKNOWN")
        logger.debug(f"MetaApi connection status: {status_type}")

        if status_type in ("DISCONNECTED", "ERROR", "CLOSED"):
            was_connected = self.connected
            self.connected = False
            if was_connected:
                logger.warning(f"MetaApi disconnected: {status_type}")
                await self._notify_connection_status(False)
                if not self._reconnecting:
                    asyncio.create_task(self._auto_reconnect())

    async def _auto_reconnect(self):
        """
        Attempt automatic reconnection with exponential backoff.
        Runs as a background task.
        """
        if self._reconnecting:
            return

        self._reconnecting = True
        logger.warning("Starting automatic reconnection sequence...")

        while self._reconnect_count < self.MAX_RECONNECT_ATTEMPTS and not self.connected:
            self._reconnect_count += 1
            delay = min(
                self.RECONNECT_BASE_DELAY * (2 ** (self._reconnect_count - 1)),
                self.RECONNECT_MAX_DELAY
            )
            logger.info(
                f"Reconnection attempt {self._reconnect_count}/"
                f"{self.MAX_RECONNECT_ATTEMPTS} in {delay:.0f}s"
            )
            await asyncio.sleep(delay)

            try:
                # Clean up old connection
                try:
                    if self.connection:
                        await self.connection.close()
                except Exception:
                    pass

                if await self.connect():
                    logger.info("Reconnection successful")
                    self._reconnecting = False
                    self._reconnect_count = 0
                    return
            except Exception as e:
                logger.error(f"Reconnection attempt failed: {e}")

        self._reconnecting = False
        if not self.connected:
            logger.critical(
                f"Failed to reconnect after {self.MAX_RECONNECT_ATTEMPTS} attempts"
            )

    async def _subscribe_all_pairs(self):
        """Subscribe to tick data for all configured trading pairs."""
        if not self.connection:
            return

        self._subscriptions = set()
        for symbol in config.TRADING_PAIRS:
            try:
                self.connection.subscribe(symbol)
                self._subscriptions.add(symbol)
                logger.debug(f"Subscribed to {symbol}")
            except Exception as e:
                logger.warning(f"Failed to subscribe to {symbol}: {e}")

        # Set up tick handler if callbacks are registered
        if self._callbacks.get("tick"):
            self.connection.on("price", self._on_tick)

    def _on_tick(self, tick_data: dict):
        """Process incoming tick data and notify callbacks."""
        for callback in self._callbacks.get("tick", []):
            try:
                callback(tick_data)
            except Exception as e:
                logger.error(f"Tick callback error: {e}")

    async def disconnect(self):
        """Graceful disconnection from MetaApi."""
        logger.info("Disconnecting from MetaApi...")
        try:
            if self.connection:
                await self.connection.close()
            if self.account:
                await self.account.disconnect()
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
        finally:
            self.connected = False
            self._subscriptions = set()
            await self._notify_connection_status(False)
            logger.info("Disconnected from MetaApi")

    # ── MARKET DATA ──────────────────────────────────────

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1h",
        count: int = 200
    ) -> list:
        """
        Fetch historical candles with normalized column names.
        Returns list of dicts with keys: open, high, low, close, volume, time.
        """
        if not self.connected:
            logger.warning(f"Cannot fetch candles: not connected")
            return []

        try:
            candles = await self.account.get_historical_candles(
                symbol,
                timeframe,
                count
            )

            if not candles:
                logger.debug(f"No candle data returned for {symbol} {timeframe}")
                return []

            # Normalize keys to lowercase for consistency
            normalized = []
            for candle in candles:
                normalized.append({
                    "open": float(candle.get("open", 0)),
                    "high": float(candle.get("high", 0)),
                    "low": float(candle.get("low", 0)),
                    "close": float(candle.get("close", 0)),
                    "volume": int(candle.get("tickVolume", 0)),
                    "spread": int(candle.get("spread", 0)),
                    "time": candle.get("time", ""),
                })

            logger.debug(f"Fetched {len(normalized)} candles for {symbol} {timeframe}")
            return normalized

        except Exception as e:
            logger.error(f"Failed to fetch candles for {symbol} {timeframe}: {e}")
            return []

    async def get_multi_timeframe_candles(
        self,
        symbol: str,
        timeframes: List[str] = None,
        count: int = 200
    ) -> Dict[str, list]:
        """Fetch candles for multiple timeframes simultaneously."""
        if timeframes is None:
            timeframes = ["M5", "M15", "H1", "H4", "D1"]

        tasks = {
            tf: self.get_candles(symbol, tf, count)
            for tf in timeframes
        }
        results = {}
        for tf, task in tasks.items():
            results[tf] = await task

        return results

    async def get_price(
        self,
        symbol: str
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Get current bid/ask for a symbol.
        Returns (bid, ask) tuple. Either can be None if unavailable.
        """
        try:
            if not self.terminal_state:
                return None, None

            price = self.terminal_state.price(symbol)
            if not price:
                return None, None

            bid = price.get("bid")
            ask = price.get("ask")

            # Estimate ask from spread if not available
            if bid is not None and ask is None:
                pip = config.pip_size(symbol)
                spec = self.terminal_state.specification(symbol)
                spread_points = spec.get("spread", 10) if spec else 10
                ask = bid + (spread_points * pip)

            return (
                float(bid) if bid is not None else None,
                float(ask) if ask is not None else None
            )

        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            return None, None

    async def get_spread(self, symbol: str) -> float:
        """Get current spread in pips."""
        try:
            bid, ask = await self.get_price(symbol)
            if bid is None or ask is None:
                return 999.0

            pip = config.pip_size(symbol)
            if pip == 0:
                return 999.0

            spread_pips = (ask - bid) / pip
            return round(spread_pips, 1)

        except Exception as e:
            logger.error(f"Failed to calculate spread for {symbol}: {e}")
            return 999.0

    async def get_symbol_info(self, symbol: str) -> dict:
        """
        Get complete symbol specification.
        Returns dict with all trading parameters.
        """
        try:
            if not self.terminal_state:
                return self._make_default_symbol_info(symbol)

            spec = self.terminal_state.specification(symbol)
            if not spec:
                logger.warning(f"No specification found for {symbol}, using defaults")
                return self._make_default_symbol_info(symbol)

            pip = config.pip_size(symbol)
            return {
                "symbol": symbol,
                "point": pip,
                "digits": spec.get("digits", 5 if pip < 0.01 else 3),
                "min_lot": float(spec.get("minVolume", 0.01)),
                "max_lot": float(spec.get("maxVolume", 100.0)),
                "lot_step": float(spec.get("volumeStep", 0.01)),
                "contract_size": float(spec.get("contractSize", 100000)),
                "spread_raw": int(spec.get("spread", 0)),
                "spread_pips": round(int(spec.get("spread", 0)) * pip / pip, 1),
                "stops_level": int(spec.get("stopsLevel", 0)),
                "margin_required": float(spec.get("margin", 0)),
                "swap_long": float(spec.get("swapLong", 0)),
                "swap_short": float(spec.get("swapShort", 0)),
                "tick_size": float(spec.get("tickSize", pip)),
                "tick_value": float(spec.get("tickValue", 0)),
            }

        except Exception as e:
            logger.error(f"Failed to get symbol info for {symbol}: {e}")
            return self._make_default_symbol_info(symbol)

    @staticmethod
    def _make_default_symbol_info(symbol: str) -> dict:
        """Create fallback symbol info when API is unavailable."""
        pip = config.pip_size(symbol)
        return {
            "symbol": symbol,
            "point": pip,
            "digits": 5 if pip < 0.01 else 3,
            "min_lot": 0.01,
            "max_lot": 100.0,
            "lot_step": 0.01,
            "contract_size": 100000,
            "spread_raw": 0,
            "spread_pips": 0.0,
            "stops_level": 0,
            "margin_required": 0.0,
            "swap_long": 0.0,
            "swap_short": 0.0,
            "tick_size": pip,
            "tick_value": 0.0,
        }

    # ── ORDER EXECUTION ──────────────────────────────────

    async def market_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        sl: float = None,
        tp: float = None,
        comment: str = ""
    ) -> Optional[dict]:
        """
        Place a market order with optional stop loss and take profit.
        Returns order result dict with orderId on success, None on failure.
        """
        if not self.connected:
            logger.error(f"Cannot place order: not connected")
            return None

        try:
            direction_upper = direction.upper()
            if direction_upper not in ("BUY", "SELL"):
                logger.error(f"Invalid direction: {direction}")
                return None

            order_type = (
                "MARKET_ORDER_TYPE_BUY"
                if direction_upper == "BUY"
                else "MARKET_ORDER_TYPE_SELL"
            )

            order_comment = f"AF_{comment}" if comment else "AF_AuroraFlux"

            # Get symbol info for validation
            symbol_info = await self.get_symbol_info(symbol)

            # Validate volume
            volume = max(
                symbol_info["min_lot"],
                min(symbol_info["max_lot"], volume)
            )
            volume = round(
                volume / symbol_info["lot_step"]
            ) * symbol_info["lot_step"]

            # Ensure stops respect broker minimum distance
            if sl or tp:
                stops_level = symbol_info["stops_level"] * symbol_info["point"]
                current_price = await self.get_price(symbol)
                mid_price = (
                    (current_price[0] + current_price[1]) / 2
                    if current_price[0] and current_price[1]
                    else None
                )

                if mid_price and stops_level > 0:
                    if sl and abs(mid_price - sl) < stops_level:
                        logger.warning(
                            f"Stop loss too close to market: "
                            f"distance={abs(mid_price - sl):.5f}, "
                            f"min={stops_level:.5f}"
                        )
                    if tp and abs(tp - mid_price) < stops_level:
                        logger.warning(
                            f"Take profit too close to market: "
                            f"distance={abs(tp - mid_price):.5f}, "
                            f"min={stops_level:.5f}"
                        )

            result = await self.account.create_market_order(
                symbol,
                order_type,
                volume,
                stop_loss=sl,
                take_profit=tp,
                comment=order_comment
            )

            logger.trade(
                "OPEN",
                symbol,
                {
                    "direction": direction_upper,
                    "volume": volume,
                    "sl": sl,
                    "tp": tp,
                    "order_id": result.get("orderId"),
                    "comment": order_comment,
                }
            )

            return result

        except Exception as e:
            logger.error(f"Market order failed for {symbol} {direction}: {e}")
            return None

    async def close_position(self, position_id: str) -> bool:
        """Close a specific position by ID."""
        if not self.connected:
            logger.error("Cannot close position: not connected")
            return False

        try:
            await self.account.close_position(position_id)
            logger.trade("CLOSE", position_id, {"position_id": position_id})
            return True
        except Exception as e:
            logger.error(f"Failed to close position {position_id}: {e}")
            return False

    async def modify_position(
        self,
        position_id: str,
        sl: float = None,
        tp: float = None
    ) -> bool:
        """Modify stop loss and/or take profit of an open position."""
        if not self.connected:
            return False

        try:
            await self.account.modify_position(
                position_id,
                stop_loss=sl,
                take_profit=tp
            )
            logger.debug(
                f"Position modified: {position_id} | "
                f"SL={sl} | TP={tp}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to modify position {position_id}: {e}")
            return False

    async def close_positions_by_symbol(self, symbol: str) -> int:
        """Close all positions for a specific symbol."""
        positions = await self.get_positions()
        closed = 0
        for p in positions:
            if p.get("symbol") == symbol:
                if await self.close_position(p["position_id"]):
                    closed += 1
        return closed

    async def close_all(self) -> int:
        """Close all open positions. Returns count of closed positions."""
        positions = await self.get_positions()
        closed = 0
        for p in positions:
            if await self.close_position(p["position_id"]):
                closed += 1

        logger.info(
            f"Closed {closed}/{len(positions)} positions"
        )
        return closed

    # ── POSITION TRACKING ────────────────────────────────

    async def get_positions(self) -> list:
        """Get all open positions with normalized data."""
        try:
            if not self.terminal_state:
                return []

            positions = self.terminal_state.positions
            if not positions:
                return []

            result = []
            for p in positions:
                direction = (
                    "LONG"
                    if p.get("type") == "POSITION_TYPE_BUY"
                    else "SHORT"
                )

                entry_price = p.get("openPrice", 0)
                current_price = p.get("currentPrice", 0)

                # Calculate unrealized PnL
                if direction == "LONG":
                    unrealized_pips = (
                        (current_price - entry_price)
                        / config.pip_size(p.get("symbol", ""))
                        if current_price and entry_price
                        else 0
                    )
                else:
                    unrealized_pips = (
                        (entry_price - current_price)
                        / config.pip_size(p.get("symbol", ""))
                        if current_price and entry_price
                        else 0
                    )

                result.append({
                    "position_id": p.get("id"),
                    "symbol": p.get("symbol"),
                    "direction": direction,
                    "volume": float(p.get("volume", 0)),
                    "entry_price": float(entry_price) if entry_price else 0,
                    "current_price": float(current_price) if current_price else 0,
                    "stop_loss": float(p.get("stopLoss", 0)) if p.get("stopLoss") else None,
                    "take_profit": float(p.get("takeProfit", 0)) if p.get("takeProfit") else None,
                    "profit": float(p.get("profit", 0)),
                    "swap": float(p.get("swap", 0)),
                    "commission": float(p.get("commission", 0)),
                    "unrealized_pips": round(unrealized_pips, 2),
                    "comment": p.get("comment", ""),
                    "open_time": p.get("time", ""),
                })

            return result

        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    async def get_position_count(self) -> int:
        """Get count of open positions."""
        positions = await self.get_positions()
        return len(positions)

    async def get_position_by_id(self, position_id: str) -> Optional[dict]:
        """Get a specific position by ID."""
        positions = await self.get_positions()
        for p in positions:
            if p.get("position_id") == position_id:
                return p
        return None

    async def get_positions_by_symbol(self, symbol: str) -> list:
        """Get all positions for a specific symbol."""
        positions = await self.get_positions()
        return [p for p in positions if p.get("symbol") == symbol]

    async def get_total_exposure(self) -> float:
        """Calculate total notional exposure across all positions."""
        positions = await self.get_positions()
        total = 0.0
        for p in positions:
            volume = p.get("volume", 0)
            price = p.get("current_price", 0)
            total += abs(volume) * price
        return total

    # ── ACCOUNT INFORMATION ──────────────────────────────

    async def get_account_info(self) -> dict:
        """Get current account information."""
        try:
            if not self.terminal_state:
                return self._make_default_account_info()

            acc = self.terminal_state.account_information
            if not acc:
                return self._make_default_account_info()

            return {
                "balance": float(acc.get("balance", 0)),
                "equity": float(acc.get("equity", 0)),
                "margin": float(acc.get("margin", 0)),
                "free_margin": float(acc.get("freeMargin", 0)),
                "currency": acc.get("currency", "USD"),
                "leverage": int(acc.get("leverage", 100)),
                "margin_level": (
                    float(acc.get("equity", 0)) / float(acc.get("margin", 1)) * 100
                    if float(acc.get("margin", 0)) > 0
                    else 0
                ),
                "name": acc.get("name", ""),
                "server": acc.get("server", ""),
                "login": acc.get("login", ""),
            }

        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return self._make_default_account_info()

    @staticmethod
    def _make_default_account_info() -> dict:
        """Return default account info when unavailable."""
        return {
            "balance": 0.0,
            "equity": 0.0,
            "margin": 0.0,
            "free_margin": 0.0,
            "currency": "USD",
            "leverage": 100,
            "margin_level": 0.0,
            "name": "",
            "server": "",
            "login": "",
        }

    # ── SESSION DETECTION ────────────────────────────────

    @staticmethod
    def detect_session() -> str:
        """Detect current trading session based on UTC time."""
        now = datetime.now(timezone.utc)
        hour = now.hour
        weekday = now.weekday()

        if weekday >= 5:  # Saturday or Sunday
            return "WEEKEND"

        if 13 <= hour < 16:
            return "OVERLAP"
        elif 7 <= hour < 16:
            return "LONDON"
        elif 13 <= hour < 22:
            return "NEW_YORK"
        else:
            return "ASIAN"

    @staticmethod
    def get_utc_hour() -> int:
        """Get current UTC hour."""
        return datetime.now(timezone.utc).hour

    @staticmethod
    def get_utc_weekday() -> int:
        """Get current UTC weekday (0=Monday, 6=Sunday)."""
        return datetime.now(timezone.utc).weekday()

    @staticmethod
    def is_market_open() -> bool:
        """Check if forex market is currently open."""
        weekday = datetime.now(timezone.utc).weekday()
        if weekday >= 5:  # Weekend
            # Sunday after 21:00 UTC market opens
            if weekday == 6 and datetime.now(timezone.utc).hour >= 21:
                return True
            return False
        return True

    # ── CALLBACK SYSTEM ──────────────────────────────────

    def on_tick(self, callback: Callable):
        """Register a callback for tick data."""
        if "tick" not in self._callbacks:
            self._callbacks["tick"] = []
        self._callbacks["tick"].append(callback)

    def on_position_update(self, callback: Callable):
        """Register a callback for position updates."""
        if "position_update" not in self._callbacks:
            self._callbacks["position_update"] = []
        self._callbacks["position_update"].append(callback)

    def on_connection_status(self, callback: Callable):
        """Register a callback for connection status changes."""
        if "connection_status" not in self._callbacks:
            self._callbacks["connection_status"] = []
        self._callbacks["connection_status"].append(callback)

    def on_order_update(self, callback: Callable):
        """Register a callback for order updates."""
        if "order_update" not in self._callbacks:
            self._callbacks["order_update"] = []
        self._callbacks["order_update"].append(callback)

    def remove_callback(self, callback_type: str, callback: Callable):
        """Remove a registered callback."""
        if callback_type in self._callbacks:
            try:
                self._callbacks[callback_type].remove(callback)
            except ValueError:
                pass

    async def _notify_connection_status(self, connected: bool):
        """Notify all connection status callbacks."""
        for callback in self._callbacks.get("connection_status", []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(connected)
                else:
                    callback(connected)
            except Exception as e:
                logger.error(f"Connection status callback error: {e}")

    # ── HEALTH CHECK ─────────────────────────────────────

    async def health_check(self) -> dict:
        """Check broker connection health and latency."""
        try:
            import time
            start = time.monotonic()

            if not self.connected:
                return {
                    "status": "disconnected",
                    "latency_ms": None,
                    "subscriptions": 0,
                    "mode": config.MODE,
                }

            # Test account access
            await self.get_account_info()
            latency = (time.monotonic() - start) * 1000

            return {
                "status": "connected",
                "latency_ms": round(latency, 2),
                "reconnect_count": self._reconnect_count,
                "subscriptions": len(self._subscriptions),
                "mode": config.MODE,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "latency_ms": None,
                "subscriptions": len(self._subscriptions),
                "mode": config.MODE,
            }


# Singleton instance
metaapi = MetaApiClient()