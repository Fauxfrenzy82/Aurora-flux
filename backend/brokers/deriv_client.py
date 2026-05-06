"""
Deriv WebSocket client using the official python-deriv-api library.
This is the most reliable connection method.
"""

import asyncio
import json
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timezone
from deriv_api import DerivAPI
from core.config import config
from core.logger import get_logger

logger = get_logger("deriv")

class DerivClient:
    """WebSocket client for Deriv API using the official library."""

    MAX_RECONNECT_ATTEMPTS = 20
    RECONNECT_BASE_DELAY = 2.0
    RECONNECT_MAX_DELAY = 60.0

    def __init__(self):
        self.app_id = getattr(config, 'DERIV_APP_ID', '')
        self.api_token = getattr(config, 'DERIV_API_TOKEN', '')
        self.api = None
        self.connected = False
        self.authorized = False
        self._balance = 0.0
        self._currency = "USD"

    async def connect(self) -> bool:
        """Connect to Deriv using the official library."""
        if self.connected:
            return True

        try:
            logger.info(f"Connecting to Deriv with official library...")
            self.api = DerivAPI(app_id=self.app_id)
            
            # Authorize with token
            auth_resp = await self.api.authorize(self.api_token)
            if auth_resp.get("error"):
                logger.error(f"Deriv auth failed: {auth_resp['error']}")
                return False
            
            self.authorized = True
            self.connected = True
            logger.info("Deriv connected and authorized")

            # Get balance
            try:
                balance_resp = await self.api.balance()
                if balance_resp.get("balance"):
                    b = balance_resp["balance"]
                    self._balance = float(b.get("balance", 0))
                    self._currency = b.get("currency", "USD")
                    logger.info(f"Deriv balance: {self._balance} {self._currency}")
            except Exception as e:
                logger.warning(f"Balance check failed (non-critical): {e}")
                self._balance = 10000.0

            return True
        except Exception as e:
            logger.error(f"Deriv connection failed: {e}")
            self.connected = False
            return False

    async def get_price(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        """Get current bid/ask for a symbol."""
        try:
            if not self.authorized:
                return None, None
            resp = await self.api.ticks(symbol)
            tick = resp.get("tick", {})
            bid = float(tick.get("bid", 0))
            ask = float(tick.get("ask", 0))
            return bid, ask
        except:
            return None, None

    async def get_candles(self, symbol: str, timeframe: str = "1h", count: int = 200) -> list:
        """Fetch historical candles."""
        try:
            granularity = self._tf_to_seconds(timeframe)
            resp = await self.api.ticks_history({
                "ticks_history": symbol,
                "granularity": granularity,
                "count": min(count, 500),
                "style": "candles",
                "end": "latest"
            })
            candles = resp.get("candles", [])
            result = []
            for c in candles:
                result.append({
                    "open": float(c.get("open", 0)),
                    "high": float(c.get("high", 0)),
                    "low": float(c.get("low", 0)),
                    "close": float(c.get("close", 0)),
                    "volume": int(c.get("epoch", 0)),
                    "time": datetime.fromtimestamp(int(c.get("epoch", 0)), tz=timezone.utc).isoformat()
                })
            return result
        except Exception as e:
            logger.error(f"Candles error: {e}")
            return []

    @staticmethod
    def _tf_to_seconds(tf: str) -> int:
        m = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800,
             "H1": 3600, "H4": 14400, "D1": 86400}
        return m.get(tf.upper(), 3600)

    async def get_symbol_info(self, symbol: str) -> dict:
        pip = 0.01 if "JPY" in symbol.upper() else 0.0001
        return {"symbol": symbol, "point": pip, "digits": 5 if pip == 0.0001 else 3,
                "min_lot": 0.01, "max_lot": 100, "lot_step": 0.01, "contract_size": 100000,
                "spread": 0, "stops_level": 0}

    def get_spread(self, symbol: str = "EURUSD") -> float:
        return 1.2

    async def market_order(self, symbol: str, direction: str, volume: float,
                           sl: float = None, tp: float = None, comment: str = "") -> Optional[dict]:
        try:
            side = "buy" if direction.upper() in ("BUY", "LONG") else "sell"
            contract = {
                "buy": 1,
                "contract_type": side.upper(),
                "symbol": symbol,
                "duration": "day",
                "basis": "stake",
                "currency": self._currency,
                "amount": str(volume)
            }
            resp = await self.api.buy(contract)
            if resp.get("error"):
                logger.error(f"Order failed: {resp['error']}")
                return None
            buy_info = resp.get("buy") or {}
            return {"orderId": str(buy_info.get("contract_id", int(datetime.now().timestamp())))}
        except Exception as e:
            logger.error(f"Order error: {e}")
            return None

    async def close_position(self, position_id: str) -> bool:
        try:
            resp = await self.api.sell({"sell": position_id})
            return "error" not in resp
        except:
            return False

    async def get_positions(self) -> list:
        try:
            resp = await self.api.portfolio()
            contracts = resp.get("portfolio", {}).get("contracts", [])
            result = []
            for c in contracts:
                result.append({
                    "position_id": str(c.get("contract_id", "")),
                    "symbol": c.get("display_name", ""),
                    "direction": "LONG" if c.get("contract_type", "").startswith("CALL") else "SHORT",
                    "volume": float(c.get("buy_price", 0)),
                    "entry_price": float(c.get("buy_price", 0)),
                    "current_price": float(c.get("bid_price", 0)),
                    "profit": float(c.get("profit", 0)),
                    "comment": "AF_AuroraFlux",
                })
            return result
        except:
            return []

    async def close_all(self) -> int:
        positions = await self.get_positions()
        closed = 0
        for p in positions:
            if await self.close_position(p["position_id"]):
                closed += 1
        return closed

    async def close_positions_by_symbol(self, symbol: str) -> int:
        positions = await self.get_positions()
        closed = 0
        for p in positions:
            if p.get("symbol") == symbol:
                if await self.close_position(p["position_id"]):
                    closed += 1
        return closed

    async def get_account_info(self) -> dict:
        return {"balance": self._balance, "equity": self._balance,
                "margin": 0, "free_margin": self._balance,
                "currency": self._currency, "leverage": 100}

    async def get_position_count(self) -> int:
        return len(await self.get_positions())

    @staticmethod
    def detect_session() -> str:
        hour = datetime.now(timezone.utc).hour
        wd = datetime.now(timezone.utc).weekday()
        if wd >= 5: return "WEEKEND"
        if 13 <= hour < 16: return "OVERLAP"
        if 7 <= hour < 16: return "LONDON"
        if 13 <= hour < 22: return "NEW_YORK"
        return "ASIAN"

    async def disconnect(self):
        if self.api:
            await self.api.disconnect()
        self.connected = False

    async def health_check(self) -> dict:
        return {"status": "connected" if self.connected else "disconnected",
                "authorized": self.authorized, "balance": self._balance}


deriv = DerivClient()