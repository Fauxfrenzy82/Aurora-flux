"""
Deriv WebSocket client — free broker bridge for Aurora Flux.
Connects directly to Deriv API using OTP authentication.
Auto-reconnects with fresh OTP on connection drops.
"""

import asyncio
import json
import time
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timezone
import websockets
import httpx
from core.config import config
from core.logger import get_logger

logger = get_logger("deriv")


class DerivClient:
    """Direct WebSocket client for Deriv API with auto-reconnection."""

    REST_API_BASE = "https://api.derivws.com"

    def __init__(self):
        self.app_id = getattr(config, 'DERIV_APP_ID', '')
        self.api_token = getattr(config, 'DERIV_API_TOKEN', '')
        self.deriv_login = getattr(config, 'DERIV_LOGIN', '')
        self.ws = None
        self.connected = False
        self._pending: Dict[str, asyncio.Future] = {}
        self._req_id = 0
        self.authorized = False
        self._balance = 0.0
        self._currency = "USD"
        self._lock = asyncio.Lock()
        self._listen_task = None

    async def _ensure_options_account(self) -> bool:
        headers = {
            "Deriv-App-ID": self.app_id,
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        logger.info("Checking for existing Deriv Options demo accounts...")
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                list_url = f"{self.REST_API_BASE}/trading/v1/options/accounts"
                list_resp = await client.get(list_url, headers=headers)
                if list_resp.status_code == 200:
                    accounts = list_resp.json().get("data", [])
                    if accounts:
                        account_id = accounts[0].get("account_id")
                        logger.info(f"Found Options demo account: {account_id}")
                        self.deriv_login = account_id
                        return True
                create_resp = await client.post(list_url, headers=headers, json={"currency": "USD", "group": "row", "account_type": "demo"})
                if create_resp.status_code in (200, 201):
                    account_id = create_resp.json().get("data", {}).get("account_id")
                    if account_id:
                        logger.info(f"Created Options demo account: {account_id}")
                        self.deriv_login = account_id
                        return True
                return False
        except Exception as e:
            logger.error(f"Account setup error: {e}")
            return False

    async def _get_otp_websocket_url(self) -> Optional[str]:
        if not await self._ensure_options_account():
            return None
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                url = f"{self.REST_API_BASE}/trading/v1/options/accounts/{self.deriv_login}/otp"
                headers = {"Deriv-App-ID": self.app_id, "Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
                resp = await client.post(url, headers=headers)
                if resp.status_code == 200:
                    inner = resp.json().get("data", {})
                    ws_url = inner.get("url") or inner.get("websocket_url")
                    if ws_url:
                        return ws_url
        except Exception as e:
            logger.error(f"OTP error: {e}")
        return None

    async def connect(self) -> bool:
        async with self._lock:
            if self.connected and self.ws:
                return True
            try:
                ws_url = await self._get_otp_websocket_url()
                if not ws_url:
                    return False
                self.ws = await websockets.connect(ws_url, ping_interval=30)
                self.connected = True
                self.authorized = True
                if self._listen_task:
                    self._listen_task.cancel()
                self._listen_task = asyncio.create_task(self._listen_loop())
                logger.info("Deriv connected")
                await asyncio.sleep(0.5)
                try:
                    resp = await self._send_raw({"balance": 1})
                    b = resp.get("balance", {})
                    if isinstance(b, dict):
                        self._balance = float(b.get("balance", 10000.0))
                        self._currency = b.get("currency", "USD")
                    else:
                        self._balance = float(b) if b else 10000.0
                    logger.info(f"Balance: {self._balance} {self._currency}")
                except:
                    self._balance = 10000.0
                return True
            except Exception as e:
                logger.error(f"Connection failed: {e}")
                self.connected = False
                return False

    async def _listen_loop(self):
        """Listen and auto-reconnect with fresh OTP."""
        while True:
            try:
                async for msg in self.ws:
                    try:
                        data = json.loads(msg)
                        req_id = data.get("req_id")
                        if req_id and req_id in self._pending:
                            self._pending.pop(req_id).set_result(data)
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass

            self.connected = False
            self.ws = None
            logger.info("WebSocket disconnected — reconnecting...")
            await asyncio.sleep(5)

            for attempt in range(10):
                try:
                    if await self.connect():
                        logger.info("Reconnected")
                        break
                except:
                    pass
                await asyncio.sleep(min(5 * attempt, 30))

    async def _send_raw(self, msg: dict) -> dict:
        """Send without retry — used internally."""
        self._req_id += 1
        msg["req_id"] = self._req_id
        future = asyncio.get_event_loop().create_future()
        self._pending[self._req_id] = future
        await self.ws.send(json.dumps(msg))
        return await asyncio.wait_for(future, timeout=15)

    async def _send(self, msg: dict) -> dict:
        """Send with retry on connection failure."""
        for attempt in range(3):
            if self.connected and self.ws:
                try:
                    return await self._send_raw(msg)
                except:
                    self.connected = False
                    self.ws = None
            if attempt < 2:
                await asyncio.sleep(5)
        raise Exception("Send failed after retries")

    async def get_price(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        try:
            if not self.authorized: return None, None
            resp = await self._send({"ticks": symbol})
            tick = resp.get("tick", {})
            return float(tick.get("bid", 0)), float(tick.get("ask", 0))
        except:
            return None, None

    async def get_candles(self, symbol: str, timeframe: str = "1h", count: int = 200) -> list:
        try:
            resp = await self._send({"ticks_history": symbol, "granularity": self._tf_to_seconds(timeframe), "count": min(count, 500), "style": "candles", "end": "latest"})
            candles = resp.get("candles", [])
            return [{"open": float(c.get("open", 0)), "high": float(c.get("high", 0)), "low": float(c.get("low", 0)), "close": float(c.get("close", 0)), "volume": int(c.get("epoch", 0)), "time": datetime.fromtimestamp(int(c.get("epoch", 0)), tz=timezone.utc).isoformat()} for c in candles]
        except:
            return []

    @staticmethod
    def _tf_to_seconds(tf: str) -> int:
        return {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}.get(tf.upper(), 3600)

    async def get_symbol_info(self, symbol: str) -> dict:
        pip = 0.01 if "JPY" in symbol.upper() else 0.0001
        return {"symbol": symbol, "point": pip, "digits": 5 if pip == 0.0001 else 3, "min_lot": 0.01, "max_lot": 100, "lot_step": 0.01, "contract_size": 100000, "spread": 0, "stops_level": 0}

    def get_spread(self, symbol: str = "EURUSD") -> float:
        return 1.2

    async def market_order(self, symbol: str, direction: str, volume: float, sl: float = None, tp: float = None, comment: str = "") -> Optional[dict]:
        try:
            side = "buy" if direction.upper() in ("BUY", "LONG") else "sell"
            resp = await self._send({"buy": 1, "contract_type": side.upper(), "symbol": symbol, "duration": "day", "basis": "stake", "currency": self._currency, "amount": str(volume)})
            if resp.get("error"): return None
            info = resp.get("buy") or resp.get("sell") or {}
            return {"orderId": str(info.get("contract_id", int(time.time())))}
        except:
            return None

    async def close_position(self, position_id: str) -> bool:
        try:
            return "error" not in await self._send({"sell": position_id, "price": 0})
        except:
            return False

    async def get_positions(self) -> list:
        try:
            resp = await self._send({"portfolio": 1})
            contracts = resp.get("portfolio", {}).get("contracts", [])
            return [{"position_id": str(c.get("contract_id", "")), "symbol": c.get("display_name", ""), "direction": "LONG" if c.get("contract_type", "").startswith("CALL") else "SHORT", "volume": float(c.get("buy_price", 0)), "entry_price": float(c.get("buy_price", 0)), "current_price": float(c.get("bid_price", 0)), "profit": float(c.get("profit", 0)), "comment": "AF_AuroraFlux"} for c in contracts]
        except:
            return []

    async def close_all(self) -> int:
        return sum(1 for p in await self.get_positions() if await self.close_position(p["position_id"]))

    async def close_positions_by_symbol(self, symbol: str) -> int:
        return sum(1 for p in await self.get_positions() if p.get("symbol") == symbol and await self.close_position(p["position_id"]))

    async def get_account_info(self) -> dict:
        return {"balance": self._balance, "equity": self._balance, "margin": 0, "free_margin": self._balance, "currency": self._currency, "leverage": 100}

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
        if self._listen_task:
            self._listen_task.cancel()
        if self.ws:
            await self.ws.close()
        self.connected = False

    async def health_check(self) -> dict:
        return {"status": "connected" if self.connected else "disconnected", "authorized": self.authorized, "balance": self._balance}


deriv = DerivClient()