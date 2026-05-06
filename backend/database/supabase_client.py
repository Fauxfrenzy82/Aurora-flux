"""
Supabase database client — production-grade persistent storage.
Uses service role key for all operations.
Audit chain is fully persistent, surviving reboots.
All methods include proper error handling and logging.
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
from core.config import config
from core.logger import get_logger

logger = get_logger("database")


class Database:
    """Persistent storage layer using Supabase."""

    def __init__(self):
        self.client: Client = create_client(
            config.SUPABASE_URL,
            config.SUPABASE_SERVICE_ROLE_KEY
        )

    @staticmethod
    def _now() -> str:
        """Current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    # ── AUDIT CHAIN HELPERS ──────────────────────────────

    async def _latest_hash(self) -> str:
        """Fetch the latest hash from the audit chain."""
        try:
            result = (
                self.client.table("audit_ledger")
                .select("hash")
                .order("id", desc=True)
                .limit(1)
                .execute()
            )
            if result.data and len(result.data) > 0:
                return result.data[0].get("hash", "")
            return ""
        except Exception as e:
            logger.error(f"Failed to fetch latest audit hash: {e}")
            return ""

    @staticmethod
    def _compute_hash(prev_hash: str, payload: str) -> str:
        """Compute SHA-256 hash for audit chain."""
        return hashlib.sha256(
            (prev_hash + payload).encode()
        ).hexdigest()

    # ── TRADES ───────────────────────────────────────────

    async def save_trade(self, data: dict) -> bool:
        """
        Record a completed trade.
        Required fields: trade_id, symbol, strategy_name, direction.
        """
        try:
            data["created_at"] = self._now()
            self.client.table("trades").insert(data).execute()
            logger.debug(f"Trade saved: {data.get('trade_id', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"Failed to save trade: {e}")
            return False

    async def update_trade(self, trade_id: str, data: dict) -> bool:
        """Update an existing trade record."""
        try:
            data["updated_at"] = self._now()
            result = (
                self.client.table("trades")
                .update(data)
                .eq("trade_id", trade_id)
                .execute()
            )
            if result.data:
                logger.debug(f"Trade updated: {trade_id}")
                return True
            logger.warning(f"Trade not found for update: {trade_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to update trade {trade_id}: {e}")
            return False

    async def get_open_trades(self) -> list:
        """Get all trades without a result (still open)."""
        try:
            result = (
                self.client.table("trades")
                .select("*")
                .is_("result", "null")
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to fetch open trades: {e}")
            return []

    async def get_trades(
        self,
        limit: int = 100,
        symbol: str = None,
        strategy: str = None,
        result: str = None,
        regime: str = None,
        session: str = None,
    ) -> list:
        """
        Fetch historical trades with optional filters.
        Results are ordered by most recent first.
        """
        try:
            query = (
                self.client.table("trades")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
            )
            if symbol:
                query = query.eq("symbol", symbol)
            if strategy:
                query = query.eq("strategy_name", strategy)
            if result:
                query = query.eq("result", result)
            if regime:
                query = query.eq("regime", regime)
            if session:
                query = query.eq("session", session)

            result_data = query.execute()
            return result_data.data or []
        except Exception as e:
            logger.error(f"Failed to fetch trades: {e}")
            return []

    async def get_trade_count(
        self,
        symbol: str = None,
        strategy: str = None,
        result: str = None,
        since: str = None,
    ) -> int:
        """Get count of trades matching filters."""
        try:
            query = (
                self.client.table("trades")
                .select("id", count="exact")
            )
            if symbol:
                query = query.eq("symbol", symbol)
            if strategy:
                query = query.eq("strategy_name", strategy)
            if result:
                query = query.eq("result", result)
            if since:
                query = query.gte("created_at", since)

            result_data = query.execute()
            return result_data.count if hasattr(result_data, "count") else 0
        except Exception as e:
            logger.error(f"Failed to count trades: {e}")
            return 0

    async def query_context(
        self,
        strategy: str,
        symbol: str,
        regime: str,
        session: str,
        limit: int = 50
    ) -> dict:
        """
        Pre-trade context query.
        Returns win rate and profit factor for exact strategy/symbol/regime/session.
        """
        try:
            trades = (
                self.client.table("trades")
                .select("result,profit_pips")
                .eq("strategy_name", strategy)
                .eq("symbol", symbol)
                .eq("regime", regime)
                .eq("session", session)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
                .data or []
            )

            if not trades:
                return {
                    "trades": 0,
                    "win_rate": 0.0,
                    "profit_factor": 0.0,
                    "expectancy": 0.0,
                }

            total = len(trades)
            wins = [t for t in trades if t.get("result") == "WIN"]
            losses = [t for t in trades if t.get("result") == "LOSS"]
            win_rate = len(wins) / total if total > 0 else 0.0

            gross_profit = sum(t.get("profit_pips", 0) or 0 for t in wins)
            gross_loss = abs(sum(t.get("profit_pips", 0) or 0 for t in losses))

            profit_factor = (
                gross_profit / gross_loss if gross_loss > 0
                else (999.0 if gross_profit > 0 else 0.0)
            )

            avg_win = gross_profit / len(wins) if wins else 0.0
            avg_loss = gross_loss / len(losses) if losses else 0.0
            expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

            return {
                "trades": total,
                "win_rate": round(win_rate, 4),
                "profit_factor": round(profit_factor, 2),
                "expectancy": round(expectancy, 4),
            }
        except Exception as e:
            logger.error(f"Failed to query context: {e}")
            return {
                "trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "expectancy": 0.0,
            }

    # ── SIGNALS ──────────────────────────────────────────

    async def save_signal(self, data: dict) -> bool:
        """
        Record a trading signal with governance result.
        Required: signal_id, symbol, strategy_name, direction.
        """
        try:
            data["created_at"] = self._now()
            self.client.table("signals").insert(data).execute()
            logger.debug(f"Signal saved: {data.get('signal_id', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"Failed to save signal: {e}")
            return False

    async def get_signals(
        self,
        limit: int = 100,
        symbol: str = None,
        governance_result: str = None,
    ) -> list:
        """Fetch recent signals with optional filters."""
        try:
            query = (
                self.client.table("signals")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
            )
            if symbol:
                query = query.eq("symbol", symbol)
            if governance_result:
                query = query.eq("governance_result", governance_result)

            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to fetch signals: {e}")
            return []

    # ── STRATEGIES ───────────────────────────────────────

    async def save_strategy(self, data: dict) -> bool:
        """
        Create or update a strategy.
        Uses upsert on strategy_id.
        """
        try:
            data["updated_at"] = self._now()
            if "created_at" not in data:
                data["created_at"] = self._now()

            self.client.table("strategies").upsert(
                data,
                on_conflict="strategy_id"
            ).execute()
            logger.debug(f"Strategy saved: {data.get('strategy_id', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"Failed to save strategy: {e}")
            return False

    async def get_strategies(
        self,
        status: str = None,
        min_trades: int = None,
        min_win_rate: float = None,
    ) -> list:
        """Fetch strategies with optional filters."""
        try:
            query = self.client.table("strategies").select("*")

            if status:
                query = query.eq("status", status)
            if min_trades is not None:
                query = query.gte("total_trades", min_trades)
            if min_win_rate is not None:
                query = query.gte("win_rate", min_win_rate)

            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to fetch strategies: {e}")
            return []

    async def get_strategy(self, strategy_id: str) -> Optional[dict]:
        """Get a single strategy by ID."""
        try:
            result = (
                self.client.table("strategies")
                .select("*")
                .eq("strategy_id", strategy_id)
                .limit(1)
                .execute()
            )
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Failed to fetch strategy {strategy_id}: {e}")
            return None

    async def save_weight_change(
        self,
        strategy_id: str,
        old_weight: float,
        new_weight: float,
        reason: str
    ) -> bool:
        """Log a strategy weight adjustment."""
        try:
            self.client.table("strategy_weights").insert({
                "strategy_id": strategy_id,
                "old_weight": old_weight,
                "new_weight": new_weight,
                "reason": reason,
                "created_at": self._now()
            }).execute()
            logger.debug(
                f"Weight change: {strategy_id} "
                f"{old_weight:.4f} -> {new_weight:.4f} ({reason})"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save weight change: {e}")
            return False

    # ── ACCOUNT SNAPSHOTS ────────────────────────────────

    async def save_snapshot(self, data: dict) -> bool:
        """Record periodic account state."""
        try:
            data["created_at"] = self._now()
            self.client.table("account_snapshots").insert(data).execute()
            logger.debug("Account snapshot saved")
            return True
        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")
            return False

    async def latest_snapshot(self) -> Optional[dict]:
        """Get most recent account snapshot."""
        try:
            result = (
                self.client.table("account_snapshots")
                .select("*")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Failed to fetch latest snapshot: {e}")
            return None

    async def get_snapshots(self, limit: int = 30) -> list:
        """Fetch recent account snapshots."""
        try:
            result = (
                self.client.table("account_snapshots")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to fetch snapshots: {e}")
            return []

    # ── AUDIT LEDGER ─────────────────────────────────────

    async def append_audit(self, event_type: str, data: dict) -> Optional[str]:
        """
        Append event to audit chain.
        Returns the new hash, or None on failure.
        """
        try:
            payload = json.dumps(data, sort_keys=True, default=str)
            prev_hash = await self._latest_hash()
            new_hash = self._compute_hash(prev_hash, payload)

            self.client.table("audit_ledger").insert({
                "event_type": event_type,
                "data": data,
                "hash": new_hash,
                "prev_hash": prev_hash,
                "created_at": self._now()
            }).execute()

            logger.debug(f"Audit appended: {event_type} | hash={new_hash[:16]}...")
            return new_hash
        except Exception as e:
            logger.error(f"Failed to append audit: {e}")
            return None

    async def get_audit(
        self,
        limit: int = 100,
        event_type: str = None,
    ) -> list:
        """Fetch audit trail entries with optional event type filter."""
        try:
            query = (
                self.client.table("audit_ledger")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
            )
            if event_type:
                query = query.eq("event_type", event_type)

            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to fetch audit trail: {e}")
            return []

    async def verify_audit_chain(self) -> dict:
        """
        Verify integrity of the entire audit chain.
        Returns validation results with any errors found.
        """
        try:
            result = (
                self.client.table("audit_ledger")
                .select("*")
                .order("id", desc=False)
                .execute()
            )
            entries = result.data or []

            if not entries:
                return {"valid": True, "entries": 0, "errors": []}

            errors = []
            for i in range(1, len(entries)):
                prev_entry = entries[i - 1]
                curr_entry = entries[i]

                # Verify prev_hash chain
                expected_prev = prev_entry.get("hash", "")
                actual_prev = curr_entry.get("prev_hash", "")
                if expected_prev != actual_prev:
                    errors.append({
                        "type": "chain_break",
                        "entry_id": curr_entry.get("id"),
                        "expected_prev": expected_prev,
                        "actual_prev": actual_prev,
                    })

                # Verify hash integrity
                payload = json.dumps(
                    curr_entry.get("data", {}),
                    sort_keys=True,
                    default=str
                )
                expected_hash = self._compute_hash(actual_prev, payload)
                actual_hash = curr_entry.get("hash", "")
                if expected_hash != actual_hash:
                    errors.append({
                        "type": "hash_mismatch",
                        "entry_id": curr_entry.get("id"),
                        "expected_hash": expected_hash,
                        "actual_hash": actual_hash,
                    })

            return {
                "valid": len(errors) == 0,
                "entries": len(entries),
                "errors": errors,
            }
        except Exception as e:
            logger.error(f"Failed to verify audit chain: {e}")
            return {
                "valid": False,
                "entries": 0,
                "errors": [{"type": "exception", "message": str(e)}],
            }

    # ── PATTERNS ─────────────────────────────────────────

    async def save_pattern(self, data: dict) -> bool:
        """Store or update a market pattern."""
        try:
            data["updated_at"] = self._now()
            self.client.table("pattern_library").upsert(
                data,
                on_conflict="signature"
            ).execute()
            logger.debug(f"Pattern saved: {data.get('signature', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"Failed to save pattern: {e}")
            return False

    async def find_patterns(
        self,
        signature: str = None,
        status: str = None,
        min_win_rate: float = None,
    ) -> list:
        """Search pattern library with optional filters."""
        try:
            query = self.client.table("pattern_library").select("*")
            if signature:
                query = query.eq("signature", signature)
            if status:
                query = query.eq("status", status)
            if min_win_rate is not None:
                query = query.gte("win_rate", min_win_rate)

            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to find patterns: {e}")
            return []

    # ── EVOLUTION LOG ────────────────────────────────────

    async def log_evolution(self, data: dict) -> bool:
        """Record an evolution cycle result."""
        try:
            data["created_at"] = self._now()
            self.client.table("evolution_log").insert(data).execute()
            logger.debug(f"Evolution logged: {data.get('event_type', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"Failed to log evolution: {e}")
            return False

    async def get_evolution_history(self, limit: int = 20) -> list:
        """Fetch recent evolution cycles."""
        try:
            result = (
                self.client.table("evolution_log")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to fetch evolution history: {e}")
            return []

    # ── SYSTEM EVENTS ────────────────────────────────────

    async def save_event(
        self,
        event_type: str,
        message: str,
        data: dict = None
    ) -> bool:
        """Record a system event."""
        try:
            self.client.table("system_events").insert({
                "event_type": event_type,
                "message": message,
                "data": data or {},
                "created_at": self._now()
            }).execute()
            logger.debug(f"Event saved: {event_type}")
            return True
        except Exception as e:
            logger.error(f"Failed to save event: {e}")
            return False

    async def get_events(
        self,
        limit: int = 50,
        event_type: str = None,
    ) -> list:
        """Fetch recent system events."""
        try:
            query = (
                self.client.table("system_events")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
            )
            if event_type:
                query = query.eq("event_type", event_type)

            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to fetch events: {e}")
            return []

    # ── REGIME HISTORY ───────────────────────────────────

    async def save_regime(
        self,
        pair: str,
        regime: str,
        confidence: float,
        metrics: dict
    ) -> bool:
        """Record a detected market regime."""
        try:
            self.client.table("regime_history").insert({
                "pair": pair,
                "regime": regime,
                "confidence": confidence,
                "metrics": metrics,
                "created_at": self._now()
            }).execute()
            logger.debug(f"Regime saved: {pair} = {regime} ({confidence:.2%})")
            return True
        except Exception as e:
            logger.error(f"Failed to save regime: {e}")
            return False

    async def get_latest_regime(self, pair: str) -> Optional[dict]:
        """Get most recent regime classification for a pair."""
        try:
            result = (
                self.client.table("regime_history")
                .select("*")
                .eq("pair", pair)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Failed to fetch latest regime for {pair}: {e}")
            return None

    async def get_regime_history(
        self,
        pair: str = None,
        limit: int = 50,
    ) -> list:
        """Fetch regime classification history."""
        try:
            query = (
                self.client.table("regime_history")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
            )
            if pair:
                query = query.eq("pair", pair)

            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to fetch regime history: {e}")
            return []

    # ── PRINCIPLES ───────────────────────────────────────

    async def save_principle(self, data: dict) -> bool:
        """Store an extracted trading principle."""
        try:
            data["created_at"] = self._now()
            self.client.table("principles").insert(data).execute()
            logger.debug(f"Principle saved: {data.get('principle_text', '')[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to save principle: {e}")
            return False

    async def get_principles(
        self,
        status: str = "ACTIVE",
        pair: str = None,
    ) -> list:
        """Fetch trading principles."""
        try:
            query = self.client.table("principles").select("*")
            if status:
                query = query.eq("status", status)
            # Filter by pair in JSONB is complex; do post-filter if needed
            result = query.execute()
            data = result.data or []

            if pair:
                data = [
                    p for p in data
                    if pair in (p.get("applicable_pairs") or [])
                    or not p.get("applicable_pairs")
                ]

            return data
        except Exception as e:
            logger.error(f"Failed to fetch principles: {e}")
            return []

    # ── COGNITIVE LOG ────────────────────────────────────

    async def log_cognitive(
        self,
        event_type: str,
        description: str,
        data: dict
    ) -> bool:
        """Log a cognitive processing event."""
        try:
            self.client.table("cognitive_log").insert({
                "event_type": event_type,
                "description": description,
                "data": data,
                "created_at": self._now()
            }).execute()
            logger.debug(f"Cognitive event logged: {event_type}")
            return True
        except Exception as e:
            logger.error(f"Failed to log cognitive event: {e}")
            return False

    # ── HEALTH CHECK ─────────────────────────────────────

    async def health_check(self) -> dict:
        """Check database connectivity."""
        try:
            start = __import__("time").time()
            result = self.client.table("system_events").select("id").limit(1).execute()
            latency_ms = (__import__("time").time() - start) * 1000

            return {
                "status": "connected",
                "latency_ms": round(latency_ms, 2),
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }


# Singleton instance
db = Database()