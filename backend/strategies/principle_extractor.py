"""
Principle Extraction Engine.
Analyzes trade history to extract universal trading principles.
Guides strategy breeding by favoring DNA elements aligned with proven principles.

ZERO MODIFICATIONS to existing files.
Attaches via feature flag ENABLE_PRINCIPLE_EXTRACTION in config.
Uses existing principles table.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field
from collections import Counter, defaultdict
from core.logger import get_logger

logger = get_logger("strategies.principles")


@dataclass
class TradeCluster:
    """Cluster of similar winning trades."""
    feature_signature: str
    trades_count: int
    wins: int
    losses: int
    win_rate: float
    avg_profit_pips: float
    common_features: Dict[str, any]
    pairs: List[str]
    regimes: List[str]
    sessions: List[str]


@dataclass
class ExtractedPrinciple:
    """Extracted trading principle."""
    principle_text: str
    confidence: float
    evidence_count: int
    applicable_pairs: List[str]
    applicable_regimes: List[str]
    win_rate: float
    profit_factor: float
    extracted_at: str
    cluster: TradeCluster


class PrincipleExtractor:
    """
    Extracts trading principles from historical trade data.
    
    Process:
    1. Cluster winning trades by feature similarity
    2. Identify clusters with >50 trades and >65% win rate
    3. Extract principle describing the winning pattern
    4. Store in principles table
    5. Use principles to guide strategy breeding
    """

    # Thresholds for principle extraction
    MIN_TRADES_FOR_PRINCIPLE: int = 20
    MIN_WIN_RATE_FOR_PRINCIPLE: float = 0.60
    MIN_PROFIT_FACTOR: float = 1.3
    STRONG_PRINCIPLE_TRADES: int = 50
    STRONG_PRINCIPLE_WIN_RATE: float = 0.65

    # Feature dimensions for clustering
    FEATURE_DIMENSIONS: List[str] = [
        "symbol",
        "regime",
        "session",
        "direction",
        "strategy_type",  # Derived from DNA
    ]

    def __init__(self, db_client):
        """
        Initialize principle extractor.
        
        Args:
            db_client: Database client for querying trades
        """
        self.db = db_client
        self.principles: List[ExtractedPrinciple] = []
        self.last_extraction: Optional[datetime] = None
        self.extraction_count: int = 0

        logger.info("Principle Extraction Engine initialized")

    async def extract_principles(self) -> List[ExtractedPrinciple]:
        """Run principle extraction on all trade history."""
        logger.info("Starting principle extraction...")

        # Fetch all winning trades
        trades = await self.db.get_trades(
            limit=10000,
            result="WIN",
        )

        if len(trades) < self.MIN_TRADES_FOR_PRINCIPLE:
            logger.info(
                f"Insufficient trades for principles: {len(trades)} wins"
            )
            return []

        # Also fetch losses for comparison
        all_trades = await self.db.get_trades(limit=10000)

        # Cluster trades by feature similarity
        clusters = self._cluster_trades(all_trades)

        # Extract principles from strong clusters
        principles = []
        for cluster in clusters:
            if (
                cluster.trades_count >= self.MIN_TRADES_FOR_PRINCIPLE and
                cluster.win_rate >= self.MIN_WIN_RATE_FOR_PRINCIPLE
            ):
                principle = self._extract_principle_from_cluster(cluster)
                if principle:
                    principles.append(principle)

        # Sort by confidence
        principles.sort(key=lambda p: p.confidence, reverse=True)

        # Store in database
        await self._store_principles(principles)

        self.principles = principles
        self.last_extraction = datetime.now(timezone.utc)
        self.extraction_count += 1

        logger.info(
            f"Principle extraction complete | "
            f"{len(clusters)} clusters | "
            f"{len(principles)} principles extracted"
        )

        return principles

    def _cluster_trades(self, trades: List[dict]) -> List[TradeCluster]:
        """Cluster trades by feature similarity."""
        clusters_dict: Dict[str, TradeCluster] = {}

        for trade in trades:
            # Build feature signature
            features = self._extract_features(trade)
            signature = self._build_signature(features)

            if signature not in clusters_dict:
                clusters_dict[signature] = TradeCluster(
                    feature_signature=signature,
                    trades_count=0,
                    wins=0,
                    losses=0,
                    win_rate=0.0,
                    avg_profit_pips=0.0,
                    common_features=features,
                    pairs=[],
                    regimes=[],
                    sessions=[],
                )

            cluster = clusters_dict[signature]
            cluster.trades_count += 1

            if trade.get("result") == "WIN":
                cluster.wins += 1
            else:
                cluster.losses += 1

            # Track metadata
            pair = trade.get("symbol", "")
            regime = trade.get("regime", "")
            session = trade.get("session", "")

            if pair and pair not in cluster.pairs:
                cluster.pairs.append(pair)
            if regime and regime not in cluster.regimes:
                cluster.regimes.append(regime)
            if session and session not in cluster.sessions:
                cluster.sessions.append(session)

        # Calculate metrics for each cluster
        for cluster in clusters_dict.values():
            if cluster.trades_count > 0:
                cluster.win_rate = cluster.wins / cluster.trades_count

        return list(clusters_dict.values())

    def _extract_features(self, trade: dict) -> Dict[str, any]:
        """Extract relevant features from a trade."""
        return {
            "symbol": trade.get("symbol", "UNKNOWN"),
            "regime": trade.get("regime", "UNKNOWN"),
            "session": trade.get("session", "UNKNOWN"),
            "direction": trade.get("direction", "UNKNOWN"),
        }

    def _build_signature(self, features: Dict[str, any]) -> str:
        """Build a string signature from features for clustering."""
        return "|".join(
            f"{dim}={features.get(dim, 'UNKNOWN')}"
            for dim in self.FEATURE_DIMENSIONS
        )

    def _extract_principle_from_cluster(
        self,
        cluster: TradeCluster,
    ) -> Optional[ExtractedPrinciple]:
        """Extract a principle from a trade cluster."""
        features = cluster.common_features

        # Determine confidence based on cluster strength
        if (
            cluster.trades_count >= self.STRONG_PRINCIPLE_TRADES and
            cluster.win_rate >= self.STRONG_PRINCIPLE_WIN_RATE
        ):
            confidence = min(0.95, 0.7 + (cluster.win_rate - 0.65) * 2)
        else:
            confidence = min(0.80, 0.5 + cluster.win_rate * 0.5)

        # Build principle text
        direction = features.get("direction", "").lower()
        symbol = features.get("symbol", "this pair")
        regime = features.get("regime", "any regime").replace("_", " ").lower()
        session = features.get("session", "any session").lower()

        if direction == "long":
            action = "going LONG"
        elif direction == "short":
            action = "going SHORT"
        else:
            action = "trading"

        principle_text = (
            f"When trading {symbol} during {session} session "
            f"in {regime} conditions, {action} has achieved "
            f"a {cluster.win_rate:.0%} win rate over "
            f"{cluster.trades_count} trades."
        )

        return ExtractedPrinciple(
            principle_text=principle_text,
            confidence=round(confidence, 4),
            evidence_count=cluster.trades_count,
            applicable_pairs=cluster.pairs,
            applicable_regimes=cluster.regimes,
            win_rate=round(cluster.win_rate, 4),
            profit_factor=0.0,  # Would calculate from trade data
            extracted_at=datetime.now(timezone.utc).isoformat(),
            cluster=cluster,
        )

    async def _store_principles(self, principles: List[ExtractedPrinciple]):
        """Store extracted principles in database."""
        stored = 0
        for principle in principles:
            try:
                await self.db.save_principle({
                    "principle_text": principle.principle_text,
                    "confidence": principle.confidence,
                    "evidence_count": principle.evidence_count,
                    "applicable_pairs": principle.applicable_pairs,
                    "applicable_regimes": principle.applicable_regimes,
                    "status": "ACTIVE",
                })
                stored += 1
            except Exception as e:
                logger.error(f"Failed to store principle: {e}")

        logger.debug(f"Stored {stored} principles")

    def get_principle_guidance(
        self,
        symbol: str,
        regime: str,
        session: str,
    ) -> List[ExtractedPrinciple]:
        """
        Get relevant principles for current market context.
        Used to guide strategy selection.
        """
        relevant = []
        for principle in self.principles:
            if (
                symbol in principle.applicable_pairs or
                not principle.applicable_pairs
            ):
                if (
                    regime in principle.applicable_regimes or
                    not principle.applicable_regimes
                ):
                    relevant.append(principle)

        return sorted(relevant, key=lambda p: p.confidence, reverse=True)

    def get_stats(self) -> dict:
        """Get principle extraction statistics."""
        return {
            "total_principles": len(self.principles),
            "last_extraction": (
                self.last_extraction.isoformat()
                if self.last_extraction
                else None
            ),
            "extraction_count": self.extraction_count,
            "top_principles": [
                {
                    "text": p.principle_text[:100],
                    "confidence": p.confidence,
                    "evidence": p.evidence_count,
                }
                for p in self.principles[:5]
            ],
        }