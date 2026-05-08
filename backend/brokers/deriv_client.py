"""
Deriv WebSocket client — free broker bridge for Aurora Flux.
Connects directly to Deriv API using OTP authentication.
Features keep-alive pings and exponential backoff retry.
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
    """Direct WebSocket client for Deriv API with keep-alive and retry."""

    REST_API_BASE = "https://api.derivws.com"
    PING_INTERVAL = 20
    MAX_RETRIES = 3
    RETRY_DELAY = 5

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
        self._last_ping = 0
        self._keepalive_task = None

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
                    data = list_resp.json()
                    accounts = data.get("data", [])
                    if accounts:
                        account_id = accounts[0].get("account_id")
                        logger.info(f"Found existing Options demo account: {account_id}")
                        self.deriv_login = account_id
                        return True
                logger.info("No Options demo account found. Creating one automatically...")
                create_data = {"currency": "USD", "group": "row", "account_type": "demo"}
                create_resp = await client.post(list_url, headers=headers, json=create_data)
                if create_resp.status_code in (200, 201):
                    new_data = create_resp.json()
                    new_account = new_data.get("data", {})
                    account_id = new_account.get("account_id")
                    if account_id:
                        logger.info(f"New Options demo account created: {account_id}")
                        self.deriv_login = account_id
                        return True
                    else:
                        logger.error(f"Account created but no ID returned: {new_data}")
                        return False
                else:
                    logger.error(f"Failed to create Options account: {create_resp.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Error during account setup: {type(e).__name__}: {e}")
            return False

    async def _get_otp_websocket_url(self) -> Optional[str]:
        if not await self._ensure_options_account():
            logger.error("Could not obtain or create an Options account. Aborting.")
            return None
        otp_path = f"/trading/v1/options/accounts/{self.deriv_login}/otp"
        url = self.REST_API_BASE + otp_path
        headers = {
            "Deriv-App-ID": self.app_id,
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        logger.info(f"Requesting OTP for account {self.deriv_login}...")
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.post(url, headers=headers)
            logger.info(f"OTP response status: {response.status_code}")
            if response.status_code == 200:
                resp_json = response.json()
                inner_data = resp_json.get("data", {})
                ws_url = inner_data.get("url") or inner_data.get("websocket_url")
                if ws_url:
                    logger.info("Successfully obtained OTP WebSocket URL")
                    return ws_url
                else:
                    logger.error(f"OTP response missing URL. Response: {json.dumps(resp_json)[:500]}")
                    return None
            elif response.status_code == 404:
                logger.error(f"OTP endpoint not found (404). Account ID '{self.deriv_login}' may be invalid.")
                return None
            elif response.status_code == 401:
                logger.error("OTP request failed with 401. Token may lack 'trade' scope.")
                return None
            else:
                logger.error(f"OTP request failed with status {response.status_code}")
                return None
        except httpx.TimeoutException:
            logger.error("OTP request timed out.")
            return None
        except Exception as e:
            logger.error(f"Failed to get OTP URL: {type(e).__name__}: {e}")
            return None

    async def connect(self) -> bool:
        async with self._lock:
            if self.connected and self.ws:
                return True
            try:
                ws_url = await self._get_otp_websocket_url()
                if not ws_url:
                    logger.error("Could not obtain OTP URL. Aborting connection.")
                    return False
                logger.info("Connecting to Deriv with OTP WebSocket URL...")
                self.ws = await websockets.connect(ws_url, ping_interval=self.PING_INTERVAL)
                self.connected = True
                self.authorized = True
                self._last_ping = time.monotonic()
                self._keepalive_task = asyncio.create_task(self._keepalive())
                self._listen_task = asyncio.create_task(self._listen_loop())
                logger.info("Deriv WebSocket connected and authenticated via OTP")
                await asyncio.sleep(0.5)
                try:
                    balance_resp = await self._send({"balance": 1})
                    if balance_resp.get("balance"):
                        b = balance_resp["balance"]
                        if isinstance(b, dict):
                            self._balance = float(b.get("balance", 10000.0))
                            self._currency = b.get("currency", "USD")
                        else:
                            self._balance = float(b)
                        logger.info(f"Deriv balance: {self._balance} {self._currency}")
                    elif balance_resp.get("error"):
                        logger.warning(f"Balance check warning: {balance_resp['error']}")
                        self._balance = 10000.0
                except Exception as e:
                    logger.warning(f"Balance check failed (non-critical): {e}")
                    self._balance = 10000.0
                return True
            except Exception as e:
                logger.error(f"Deriv connection failed: {type(e).__name__}: {e}")
                self.connected = False
                return False

    async def _keepalive(self):
        """Send periodic pings to keep the WebSocket alive."""
        while self.connected and self.ws:
            try:
                await asyncio.sleep(self.PING_INTERVAL)
                if self.ws:
                    pong = await self.ws.ping()
                    self._last_ping = time.monotonic()
            except Exception:
                break

    async def _listen_loop(self):
        """Listen for incoming messages. Triggers reconnect on failure."""
        while True:
            try:
                if not self.ws:
                    await asyncio.sleep(2)
                    continue
                async for msg in self.ws:
                    try:
                        data = json.loads(msg)
                        req_id = data.get("req_id")
                        if req_id and req_id in self._pending:
                            self._pending.pop(req_id).set_result(data)
                    except json.JSONDecodeError:
                        continue
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Deriv WebSocket closed by server. Reconnecting...")
            except Exception as e:
                logger.warning(f"Deriv listen error: {type(e).__name__}: {e}. Reconnecting...")
            
            self.connected = False
            self.ws = None
            
            for attempt in range(1, 11):
                logger.info(f"Reconnect attempt {attempt}/10...")
                try:
                    if await self.connect():
                        logger.info("Reconnected successfully")
                        break
                except Exception as e:
                    logger.warning(f"Attempt {attempt} failed: {e}")
                await asyncio.sleep(min(5 * attempt, 30))
            else:
                logger.error("All reconnect attempts failed. Waiting 60s...")
                await asyncio.sleep(60)

    async def _send(self, msg: dict, timeout: float = 15) -> dict:
        """Send a message with retry logic."""
        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            if not self.connected or not self.ws:
                if attempt < self.MAX_RETRIES:
                    logger.debug(f"Not connected, waiting for reconnect (attempt {attempt})...")
                    await asyncio.sleep(self.RETRY_DELAY)
                    continue
                raise Exception("Not connected after retries")
            try:
                self._req_id += 1
                msg["req_id"] = self._req_id
                future = asyncio.get_event_loop().create_future()
                self._pending[self._req_id] = future
                await self.ws.send(json.dumps(msg))
                return await asyncio.wait_for(future, timeout=timeout)
            except Exception as e:
                last_error = e
                self.connected = False
                self.ws = None
                if attempt < self.MAX_RETRIES:
                    logger.debug(f"Send failed (attempt {attempt}): {e}. Retrying...")
                    await asyncio.sleep(self.RETRY_DELAY)
        raise Exception(f"Send failed after {self.MAX_RETRIES} attempts: {last_error}")

    async def get_price(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        try:
            if not self.authorized:
                return None, None
            resp = await self._send({"ticks": symbol})
            tick = resp.get("tick", {})
            bid = float(tick.get("bid", 0))
            ask = float(tick.get("ask", 0))
            return bid, ask
        except:
            return None, None

    async def get_candles(self, symbol: str, timeframe: str = "1h", count: int = 200) -> list:
        try:
            resp = await self._send({
                "ticks_history": symbol,
                "granularity": self._tf_to_seconds(timeframe),
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
            logger.debug(f"Candles unavailable for {symbol}: {e}")
            return []

    @staticmethod
    def _tf_to_seconds(tf: str) -> int:
        m = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
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
            contract = {"buy": 1, "contract_type": side.upper(), "symbol": symbol,
                        "duration": "day", "basis": "stake", "currency": self._currency,
                        "amount": str(volume)}
            resp = await self._send(contract)
            if resp.get("error"):
                logger.error(f"Order failed: {resp['error']}")
                return None
            buy_info = resp.get("buy") or resp.get("sell") or {}
            return {"orderId": str(buy_info.get("contract_id", int(time.time())))}
        except Exception as e:
            logger.error(f"Order error: {e}")
            return None

    async def close_position(self, position_id: str) -> bool:
        try:
            resp = await self._send({"sell": position_id, "price": 0})
            return "error" not in resp
        except:
            return False

    async def get_positions(self) -> list:
        try:
            resp = await self._send({"portfolio": 1})
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
        if self._keepalive_task:
            self._keepalive_task.cancel()
        if self._listen_task:
            self._listen_task.cancel()
        if self.ws:
            await self.ws.close()
        self.connected = False

    async def health_check(self) -> dict:
        return {"status": "connected" if self.connected else "disconnected",
                "authorized": self.authorized, "balance": self._balance}


deriv = DerivClient()