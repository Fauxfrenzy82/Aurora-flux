"""
Correlation Risk Calculator.
Maintains rolling correlation matrix for all trading pairs.
Applies penalties when portfolio becomes concentrated in correlated positions.

ZERO MODIFICATIONS to existing files.
Attaches via feature flag ENABLE_CORRELATION_ENGINE in config.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timezone
from collections import deque
from dataclasses import dataclass, field
from core.config import config
from core.logger import get_logger

logger = get_logger("risk.correlation")


@dataclass
class CorrelationPair:
    """Correlation data between two symbols."""
    symbol_a: str
    symbol_b: str
    correlation: float
    direction: str  # "POSITIVE", "NEGATIVE", "NEUTRAL"
    strength: str   # "STRONG", "MODERATE", "WEAK"


@dataclass
class PortfolioCorrelation:
    """Complete portfolio correlation analysis."""
    overall_correlation: float
    concentration_risk: float
    pair_correlations: List[CorrelationPair]
    penalty_factor: float
    warning: str = ""


class CorrelationEngine:
    """
    Calculates real-time correlation between positions and proposed trades.
    
    Maintains:
    - Rolling 50-period correlation matrix for all configured pairs
    - Correlation penalties for position sizing
    - Concentration risk warnings
    
    Penalty rules:
    - Correlation > 0.85: 0.5 penalty (50% size reduction)
    - Correlation > 0.70: 0.7 penalty (30% size reduction)
    - Correlation > 0.50: 0.85 penalty (15% size reduction)
    - Negative correlation with same direction: 0.6 penalty
    """

    # Correlation thresholds
    EXTREME_CORRELATION: float = 0.85
    HIGH_CORRELATION: float = 0.70
    MODERATE_CORRELATION: float = 0.50
    LOW_CORRELATION: float = 0.30

    # Penalty factors
    EXTREME_PENALTY: float = 0.50
    HIGH_PENALTY: float = 0.70
    MODERATE_PENALTY: float = 0.85
    SAME_DIRECTION_EXTRA_PENALTY: float = 0.10

    # Configuration
    CORRELATION_WINDOW: int = 50
    MIN_BARS_FOR_CALCULATION: int = 20

    def __init__(self):
        self.price_history: Dict[str, deque] = {}
        self.correlation_matrix: Optional[pd.DataFrame] = None
        self.last_update: Optional[datetime] = None
        self.pairs: List[str] = config.TRADING_PAIRS
        self._initialize_price_history()

        logger.info(
            f"Correlation Engine initialized | "
            f"Pairs: {len(self.pairs)} | "
            f"Window: {self.CORRELATION_WINDOW} bars"
        )

    def _initialize_price_history(self):
        """Initialize price history deques for all pairs."""
        for pair in self.pairs:
            self.price_history[pair] = deque(maxlen=self.CORRELATION_WINDOW)

    def update_prices(self, pair_prices: Dict[str, float]):
        """
        Update price history with new prices.
        
        Args:
            pair_prices: Dict of symbol -> current price
        """
        updated = 0
        for symbol, price in pair_prices.items():
            if symbol in self.price_history and price and price > 0:
                self.price_history[symbol].append(price)
                updated += 1

        if updated > 0:
            self.last_update = datetime.now(timezone.utc)

    async def update_correlation_matrix(self, broker_client=None):
        """
        Recalculate the full correlation matrix.
        Optionally fetches historical data from broker.
        """
        if broker_client:
            await self._fetch_historical_prices(broker_client)

        # Build returns DataFrames
        returns_data = {}
        for pair in self.pairs:
            prices = list(self.price_history.get(pair, []))
            if len(prices) >= self.MIN_BARS_FOR_CALCULATION:
                price_series = pd.Series(prices)
                returns = price_series.pct_change().dropna()
                if len(returns) >= self.MIN_BARS_FOR_CALCULATION:
                    returns_data[pair] = returns

        if len(returns_data) < 2:
            logger.debug("Insufficient data for correlation matrix")
            return

        # Build correlation matrix
        returns_df = pd.DataFrame(returns_data)
        self.correlation_matrix = returns_df.corr()

        logger.debug(
            f"Correlation matrix updated | "
            f"Pairs: {len(returns_data)} | "
            f"Bars: {len(returns_df)}"
        )

    async def _fetch_historical_prices(self, broker_client):
        """Fetch historical prices from broker to populate price history."""
        for pair in self.pairs:
            if len(self.price_history[pair]) < self.MIN_BARS_FOR_CALCULATION:
                try:
                    candles = await broker_client.get_candles(
                        pair, "H1", self.CORRELATION_WINDOW
                    )
                    if candles:
                        closes = [c.get("close", 0) for c in candles if c.get("close")]
                        self.price_history[pair] = deque(
                            closes[-self.CORRELATION_WINDOW:],
                            maxlen=self.CORRELATION_WINDOW
                        )
                        logger.debug(
                            f"Fetched {len(closes)} prices for {pair}"
                        )
                except Exception as e:
                    logger.error(f"Failed to fetch prices for {pair}: {e}")

    def get_pair_correlation(self, symbol_a: str, symbol_b: str) -> float:
        """
        Get correlation between two specific pairs.
        
        Returns:
            Correlation coefficient (-1 to 1) or 0 if insufficient data
        """
        if self.correlation_matrix is None:
            return 0.0

        if symbol_a == symbol_b:
            return 1.0

        try:
            return float(
                self.correlation_matrix.loc[symbol_a, symbol_b]
            )
        except (KeyError, TypeError):
            return 0.0

    def analyze_portfolio(
        self,
        open_positions: List[dict],
        proposed_symbol: str = None,
        proposed_direction: str = None,
    ) -> PortfolioCorrelation:
        """
        Analyze portfolio correlation risk.
        
        Args:
            open_positions: List of open position dicts
            proposed_symbol: Symbol of proposed new trade
            proposed_direction: Direction of proposed trade
            
        Returns:
            PortfolioCorrelation with risk assessment
        """
        if not open_positions and not proposed_symbol:
            return PortfolioCorrelation(
                overall_correlation=0.0,
                concentration_risk=0.0,
                pair_correlations=[],
                penalty_factor=1.0,
            )

        # Get unique symbols in portfolio
        portfolio_symbols = set()
        for pos in open_positions:
            symbol = pos.get("symbol", "")
            if symbol:
                portfolio_symbols.add(symbol)

        if proposed_symbol:
            portfolio_symbols.add(proposed_symbol)

        if len(portfolio_symbols) <= 1:
            return PortfolioCorrelation(
                overall_correlation=0.0,
                concentration_risk=0.0,
                pair_correlations=[],
                penalty_factor=1.0,
            )

        # Calculate pairwise correlations
        pair_correlations = []
        correlation_values = []

        symbols_list = list(portfolio_symbols)
        for i in range(len(symbols_list)):
            for j in range(i + 1, len(symbols_list)):
                corr = self.get_pair_correlation(symbols_list[i], symbols_list[j])
                abs_corr = abs(corr)

                # Determine correlation characteristics
                if abs_corr > self.EXTREME_CORRELATION:
                    strength = "STRONG"
                elif abs_corr > self.MODERATE_CORRELATION:
                    strength = "MODERATE"
                elif abs_corr > self.LOW_CORRELATION:
                    strength = "WEAK"
                else:
                    strength = "NEGLIGIBLE"

                direction = (
                    "POSITIVE" if corr > 0.2
                    else "NEGATIVE" if corr < -0.2
                    else "NEUTRAL"
                )

                pair_correlations.append(CorrelationPair(
                    symbol_a=symbols_list[i],
                    symbol_b=symbols_list[j],
                    correlation=round(corr, 4),
                    direction=direction,
                    strength=strength,
                ))
                correlation_values.append(abs_corr)

        # Calculate overall metrics
        if correlation_values:
            overall_correlation = np.mean(correlation_values)
            max_correlation = max(correlation_values)

            # Concentration risk (how many pairs are highly correlated)
            highly_correlated = sum(
                1 for c in correlation_values if c > self.HIGH_CORRELATION
            )
            total_pairs = len(correlation_values)
            concentration_risk = (
                highly_correlated / total_pairs if total_pairs > 0 else 0
            )
        else:
            overall_correlation = 0.0
            max_correlation = 0.0
            concentration_risk = 0.0

        # Calculate penalty factor
        penalty_factor = self._calculate_penalty(
            max_correlation,
            proposed_symbol,
            proposed_direction,
            open_positions,
        )

        # Generate warning if needed
        warning = ""
        if concentration_risk > 0.7:
            warning = "HIGH CONCENTRATION: Portfolio heavily correlated"
        elif max_correlation > self.EXTREME_CORRELATION:
            warning = "EXTREME CORRELATION: Consider reducing position sizes"
        elif max_correlation > self.HIGH_CORRELATION:
            warning = "Elevated correlation detected"

        return PortfolioCorrelation(
            overall_correlation=round(overall_correlation, 4),
            concentration_risk=round(concentration_risk, 4),
            pair_correlations=pair_correlations,
            penalty_factor=round(penalty_factor, 4),
            warning=warning,
        )

    def _calculate_penalty(
        self,
        max_correlation: float,
        proposed_symbol: Optional[str],
        proposed_direction: Optional[str],
        open_positions: List[dict],
    ) -> float:
        """
        Calculate correlation penalty factor for position sizing.
        1.0 = no penalty, <1.0 = size reduction.
        """
        penalty = 1.0

        # Base penalty from correlation strength
        if max_correlation > self.EXTREME_CORRELATION:
            penalty = self.EXTREME_PENALTY
        elif max_correlation > self.HIGH_CORRELATION:
            penalty = self.HIGH_PENALTY
        elif max_correlation > self.MODERATE_CORRELATION:
            penalty = self.MODERATE_PENALTY

        # Extra penalty for same-direction trades on correlated pairs
        if proposed_symbol and proposed_direction and open_positions:
            for pos in open_positions:
                pos_symbol = pos.get("symbol", "")
                pos_direction = pos.get("direction", "")

                if pos_symbol and pos_direction:
                    corr = self.get_pair_correlation(
                        proposed_symbol, pos_symbol
                    )

                    # Same direction on positively correlated pairs
                    if corr > self.HIGH_CORRELATION:
                        if proposed_direction == pos_direction:
                            penalty -= self.SAME_DIRECTION_EXTRA_PENALTY
                    # Same direction on negatively correlated pairs (inverse risk)
                    elif corr < -self.HIGH_CORRELATION:
                        if proposed_direction != pos_direction:
                            penalty -= self.SAME_DIRECTION_EXTRA_PENALTY

        return max(0.3, penalty)  # Floor at 30%

    def get_penalty_for_signal(
        self,
        signal: dict,
        open_positions: List[dict],
    ) -> float:
        """
        Get correlation penalty for a specific trading signal.
        Convenience method for use in position sizing.
        
        Args:
            signal: Signal dict with symbol and direction
            open_positions: Current open positions
            
        Returns:
            Penalty factor (0.0-1.0)
        """
        if not open_positions:
            return 1.0

        analysis = self.analyze_portfolio(
            open_positions=open_positions,
            proposed_symbol=signal.get("symbol"),
            proposed_direction=signal.get("direction"),
        )

        if analysis.warning:
            logger.risk("CORRELATION_WARNING", {
                "penalty": analysis.penalty_factor,
                "warning": analysis.warning,
                "overall_corr": analysis.overall_correlation,
            })

        return analysis.penalty_factor

    def get_stats(self) -> dict:
        """Get correlation engine statistics."""
        return {
            "pairs_tracked": len(self.price_history),
            "pairs_with_data": sum(
                1 for prices in self.price_history.values()
                if len(prices) >= self.MIN_BARS_FOR_CALCULATION
            ),
            "last_update": (
                self.last_update.isoformat()
                if self.last_update
                else None
            ),
            "matrix_available": self.correlation_matrix is not None,
        }