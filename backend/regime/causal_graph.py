"""
Causal Graph Builder.
Builds directed causal relationships between trading pairs using Granger causality.
Distinguishes genuine cause-effect from mere correlation.

ZERO MODIFICATIONS to existing files.
Attaches via feature flag ENABLE_CAUSAL_GRAPH in config.
Uses existing causal_graph table (schema append-only).
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime, timezone
from dataclasses import dataclass, field
from collections import defaultdict
from core.logger import get_logger
from statsmodels.tsa.stattools import grangercausalitytests

logger = get_logger("regime.causal")


@dataclass
class CausalEdge:
    """Directed causal relationship between two pairs."""
    source: str
    target: str
    p_value: float
    correlation: float
    optimal_lag: int
    direction: str  # "source_leads_target", "target_leads_source", "bidirectional"
    confidence: float
    discovered_at: str


@dataclass
class CausalGraph:
    """Complete causal graph of market relationships."""
    edges: List[CausalEdge]
    nodes: Set[str]
    adjacency: Dict[str, List[str]]
    timestamp: str
    total_pairs: int
    significant_edges: int


class CausalGraphBuilder:
    """
    Builds causal relationships using Granger causality tests.
    
    Weekly analysis during weekend evolution:
    1. Runs Granger causality on daily returns for all pair combinations
    2. Records significant relationships (p < 0.05)
    3. Builds directed graph for lead-lag trading
    4. Stores results for strategy enhancement
    """

    # Granger test parameters
    MAX_LAG: int = 5
    SIGNIFICANCE_LEVEL: float = 0.05
    MIN_CORRELATION: float = 0.3  # Minimum correlation to test causality

    # Graph pruning
    MIN_EDGE_CONFIDENCE: float = 0.7

    def __init__(self, db_client):
        """
        Initialize causal graph builder.
        
        Args:
            db_client: Database client for storage
        """
        self.db = db_client
        self.graph: Optional[CausalGraph] = None
        self.last_build: Optional[datetime] = None
        self.build_count: int = 0
        self.pairs: List[str] = [
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
            "AUDUSD", "USDCAD", "NZDUSD",
            "EURGBP", "EURJPY", "GBPJPY",
            "EURCHF", "GBPCHF", "AUDJPY"
        ]

        logger.info(f"Causal Graph Builder initialized for {len(self.pairs)} pairs")

    async def build_graph(
        self,
        price_data: Dict[str, pd.DataFrame],
    ) -> CausalGraph:
        """
        Build complete causal graph from price data.
        
        Args:
            price_data: Dict of symbol -> DataFrame with 'close' column
            
        Returns:
            CausalGraph with all significant edges
        """
        # Extract daily returns
        returns = {}
        for symbol, df in price_data.items():
            if df is not None and not df.empty and "close" in df.columns:
                close_series = df["close"]
                if len(close_series) >= 50:
                    returns[symbol] = close_series.pct_change().dropna()

        if len(returns) < 2:
            logger.warning("Insufficient pairs for causal graph")
            return CausalGraph(
                edges=[], nodes=set(), adjacency={},
                timestamp=datetime.now(timezone.utc).isoformat(),
                total_pairs=len(returns), significant_edges=0,
            )

        nodes = set(returns.keys())
        edges: List[CausalEdge] = []
        adjacency: Dict[str, List[str]] = defaultdict(list)

        # Test each pair combination
        pair_list = list(returns.keys())
        for i in range(len(pair_list)):
            for j in range(len(pair_list)):
                if i == j:
                    continue

                source = pair_list[i]
                target = pair_list[j]

                # Check minimum correlation
                correlation = returns[source].corr(returns[target])
                if abs(correlation) < self.MIN_CORRELATION:
                    continue

                # Run Granger causality test
                edge = await self._test_granger_causality(
                    returns[source],
                    returns[target],
                    source,
                    target,
                    correlation,
                )

                if edge:
                    edges.append(edge)
                    adjacency[source].append(target)

        # Count significant edges
        significant = sum(1 for e in edges if e.p_value < self.SIGNIFICANCE_LEVEL)

        self.graph = CausalGraph(
            edges=edges,
            nodes=nodes,
            adjacency=dict(adjacency),
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_pairs=len(nodes),
            significant_edges=significant,
        )
        self.last_build = datetime.now(timezone.utc)
        self.build_count += 1

        # Store in database
        await self._store_graph(self.graph)

        logger.info(
            f"Causal graph built | {len(nodes)} pairs | "
            f"{len(edges)} edges | {significant} significant"
        )

        return self.graph

    async def _test_granger_causality(
        self,
        source_returns: pd.Series,
        target_returns: pd.Series,
        source_name: str,
        target_name: str,
        correlation: float,
    ) -> Optional[CausalEdge]:
        """
        Test Granger causality between two return series.
        Returns CausalEdge if significant, None otherwise.
        """
        # Align series
        combined = pd.concat([source_returns, target_returns], axis=1).dropna()
        combined.columns = ["source", "target"]

        if len(combined) < 30:
            return None

        try:
            # Run Granger test
            test_data = combined[["target", "source"]]

            # Test if source Granger-causes target
            gc_result_forward = grangercausalitytests(
                test_data,
                maxlag=min(self.MAX_LAG, len(test_data) // 10),
                verbose=False,
            )

            # Test if target Granger-causes source (reverse)
            test_data_reverse = combined[["source", "target"]]
            gc_result_reverse = grangercausalitytests(
                test_data_reverse,
                maxlag=min(self.MAX_LAG, len(test_data) // 10),
                verbose=False,
            )

            # Find best p-value and lag
            best_p_forward = 1.0
            best_lag_forward = 1
            for lag, result in gc_result_forward.items():
                p_val = result[0]["ssr_ftest"][1]  # F-test p-value
                if p_val < best_p_forward:
                    best_p_forward = p_val
                    best_lag_forward = lag

            best_p_reverse = 1.0
            best_lag_reverse = 1
            for lag, result in gc_result_reverse.items():
                p_val = result[0]["ssr_ftest"][1]
                if p_val < best_p_reverse:
                    best_p_reverse = p_val
                    best_lag_reverse = lag

            # Determine direction
            forward_sig = best_p_forward < self.SIGNIFICANCE_LEVEL
            reverse_sig = best_p_reverse < self.SIGNIFICANCE_LEVEL

            if not forward_sig and not reverse_sig:
                return None

            if forward_sig and reverse_sig:
                direction = "bidirectional"
                p_value = min(best_p_forward, best_p_reverse)
                lag = min(best_lag_forward, best_lag_reverse)
            elif forward_sig:
                direction = f"{source_name}_leads_{target_name}"
                p_value = best_p_forward
                lag = best_lag_forward
            else:
                direction = f"{target_name}_leads_{source_name}"
                p_value = best_p_reverse
                lag = best_lag_reverse

            # Calculate confidence
            confidence = 1.0 - p_value
            if confidence < self.MIN_EDGE_CONFIDENCE:
                return None

            return CausalEdge(
                source=source_name,
                target=target_name,
                p_value=round(p_value, 6),
                correlation=round(correlation, 4),
                optimal_lag=lag,
                direction=direction,
                confidence=round(confidence, 4),
                discovered_at=datetime.now(timezone.utc).isoformat(),
            )

        except Exception as e:
            logger.error(
                f"Granger test failed for {source_name}->{target_name}: {e}"
            )
            return None

    async def _store_graph(self, graph: CausalGraph):
        """Store causal graph in database."""
        stored = 0
        for edge in graph.edges:
            try:
                await self.db.client.table("causal_graph").upsert({
                    "source_pair": edge.source,
                    "target_pair": edge.target,
                    "granger_p_value": edge.p_value,
                    "correlation": edge.correlation,
                    "lag_bars": edge.optimal_lag,
                    "direction": edge.direction,
                    "confidence": edge.confidence,
                    "discovered_at": edge.discovered_at,
                    "last_verified": datetime.now(timezone.utc).isoformat(),
                }, on_conflict="source_pair,target_pair,lag_bars").execute()
                stored += 1
            except Exception as e:
                logger.error(f"Failed to store causal edge: {e}")

        logger.debug(f"Stored {stored} causal edges")

    def get_leading_indicators(self, target_pair: str) -> List[CausalEdge]:
        """
        Get pairs that Granger-cause the target pair.
        Useful for lead-lag trading signals.
        """
        if not self.graph:
            return []

        leading = []
        for edge in self.graph.edges:
            if "leads" in edge.direction and target_pair in edge.direction:
                if edge.direction.startswith(edge.source):
                    leading.append(edge)

        return sorted(leading, key=lambda e: e.confidence, reverse=True)

    def get_early_warning_pairs(self) -> Dict[str, List[str]]:
        """
        Get pairs that serve as early warning for others.
        Returns dict of source_pair -> [target_pairs_it_leads].
        """
        if not self.graph:
            return {}

        early_warning = defaultdict(list)
        for edge in self.graph.edges:
            if edge.source in edge.direction and "leads" in edge.direction:
                early_warning[edge.source].append(edge.target)

        return dict(early_warning)

    def is_causally_related(self, pair_a: str, pair_b: str) -> bool:
        """Check if two pairs have a causal relationship."""
        if not self.graph:
            return False

        for edge in self.graph.edges:
            if (
                (edge.source == pair_a and edge.target == pair_b) or
                (edge.source == pair_b and edge.target == pair_a)
            ):
                return edge.confidence > self.MIN_EDGE_CONFIDENCE

        return False

    def get_graph_summary(self) -> dict:
        """Get causal graph summary."""
        if not self.graph:
            return {
                "edges": 0,
                "nodes": 0,
                "significant": 0,
                "last_build": None,
            }

        return {
            "edges": len(self.graph.edges),
            "nodes": len(self.graph.nodes),
            "significant": self.graph.significant_edges,
            "last_build": self.last_build.isoformat() if self.last_build else None,
            "build_count": self.build_count,
        }

    def get_stats(self) -> dict:
        """Get builder statistics."""
        return {
            **self.get_graph_summary(),
            "pairs_configured": len(self.pairs),
            "min_correlation": self.MIN_CORRELATION,
            "significance_level": self.SIGNIFICANCE_LEVEL,
            "max_lag": self.MAX_LAG,
        }