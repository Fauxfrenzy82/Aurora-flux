"""
Strategy DNA — parameterized strategy definitions.
Every strategy is a DNA string that can breed, mutate, and evolve.
Supports multiple entry/exit conditions across timeframes.
"""

import uuid
import random
import copy
from typing import Dict, List, Optional


class StrategyDNA:
    """
    Genetic representation of a trading strategy.
    Encodes entry/exit logic, risk parameters, and preferences.
    """

    # Available building blocks
    INDICATORS = [
        "RSI", "ADX", "ATR", "EMA", "SMA", "BB",
        "STOCH", "CCI", "VWAP", "ZSCORE",
        "MACD", "ICHIMOKU",
    ]

    OPERATORS = [
        "ABOVE", "BELOW",
        "CROSS_ABOVE", "CROSS_BELOW",
        "EXTREME", "DIVERGENCE",
    ]

    TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
    SESSIONS = ["ASIAN", "LONDON", "NEW_YORK", "OVERLAP", "ALL"]
    REGIMES = [
        "TRENDING_UP", "TRENDING_DOWN",
        "RANGE_BOUND", "VOLATILITY_EXPANSION",
        "ALL",
    ]

    def __init__(self, name: str = None):
        self.strategy_id: str = str(uuid.uuid4())[:8]
        self.name: str = name or f"Strategy_{self.strategy_id}"

        # Entry conditions — all must be met (AND logic)
        self.entry_conditions: List[dict] = []

        # Exit conditions — any can trigger (OR logic)
        self.exit_conditions: List[dict] = []

        # Risk management
        self.stop_loss: dict = {"method": "ATR_MULTIPLE", "value": 1.5}
        self.take_profit: dict = {"method": "RISK_REWARD", "value": 2.5}
        self.trailing_stop: Optional[dict] = None

        # Execution
        self.timeframe: str = "M15"
        self.confirmation_tf: str = "H1"
        self.max_holding_minutes: int = 240
        self.min_holding_minutes: int = 5

        # Preferences
        self.session_preference: str = "ALL"
        self.regime_preference: str = "ALL"
        self.pair_preference: List[str] = []

        # Behavior
        self.aggression: float = 0.5  # 0=conservative, 1=aggressive
        self.pyramiding: bool = False
        self.max_layers: int = 1
        self.hedging: bool = False
        self.reverse_signals: bool = False

    def to_dict(self) -> dict:
        """Serialize DNA to dictionary for storage."""
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.name,
            "entry": self.entry_conditions,
            "exit": self.exit_conditions,
            "stop": self.stop_loss,
            "profit": self.take_profit,
            "trailing": self.trailing_stop,
            "tf": self.timeframe,
            "confirm_tf": self.confirmation_tf,
            "session": self.session_preference,
            "regime": self.regime_preference,
            "pairs": self.pair_preference,
            "holding_min": self.max_holding_minutes,
            "holding_min_min": self.min_holding_minutes,
            "aggression": self.aggression,
            "pyramiding": self.pyramiding,
            "max_layers": self.max_layers,
            "hedging": self.hedging,
            "reverse_signals": self.reverse_signals,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyDNA":
        """Deserialize DNA from dictionary."""
        dna = cls(data.get("strategy_name", ""))
        dna.strategy_id = data.get("strategy_id", dna.strategy_id)
        dna.entry_conditions = data.get("entry", [])
        dna.exit_conditions = data.get("exit", [])
        dna.stop_loss = data.get("stop", {"method": "ATR_MULTIPLE", "value": 1.5})
        dna.take_profit = data.get("profit", {"method": "RISK_REWARD", "value": 2.5})
        dna.trailing_stop = data.get("trailing", None)
        dna.timeframe = data.get("tf", "M15")
        dna.confirmation_tf = data.get("confirm_tf", "H1")
        dna.session_preference = data.get("session", "ALL")
        dna.regime_preference = data.get("regime", "ALL")
        dna.pair_preference = data.get("pairs", [])
        dna.max_holding_minutes = data.get("holding_min", 240)
        dna.min_holding_minutes = data.get("holding_min_min", 5)
        dna.aggression = data.get("aggression", 0.5)
        dna.pyramiding = data.get("pyramiding", False)
        dna.max_layers = data.get("max_layers", 1)
        dna.hedging = data.get("hedging", False)
        dna.reverse_signals = data.get("reverse_signals", False)
        return dna

    @classmethod
    def breed(cls, parent_a: "StrategyDNA", parent_b: "StrategyDNA") -> "StrategyDNA":
        """
        Create child by combining two parent strategies.
        Uses uniform crossover with random selection per gene.
        """
        child = cls(f"Child_{parent_a.name[:8]}_{parent_b.name[:8]}")

        # Entry conditions — take from either parent
        child.entry_conditions = copy.deepcopy(
            random.choice([parent_a, parent_b]).entry_conditions
        )

        # Exit conditions — take from either parent
        child.exit_conditions = copy.deepcopy(
            random.choice([parent_a, parent_b]).exit_conditions
        )

        # Risk parameters — take from either or blend
        child.stop_loss = copy.deepcopy(
            random.choice([parent_a, parent_b]).stop_loss
        )
        child.take_profit = copy.deepcopy(
            random.choice([parent_a, parent_b]).take_profit
        )
        child.trailing_stop = copy.deepcopy(
            random.choice([parent_a, parent_b]).trailing_stop
        )

        # Timeframes — crossover
        child.timeframe = random.choice([
            parent_a.timeframe,
            parent_b.timeframe
        ])
        child.confirmation_tf = random.choice([
            parent_a.confirmation_tf,
            parent_b.confirmation_tf
        ])

        # Preferences — crossover
        child.regime_preference = random.choice([
            parent_a.regime_preference,
            parent_b.regime_preference
        ])
        child.session_preference = random.choice([
            parent_a.session_preference,
            parent_b.session_preference
        ])
        child.pair_preference = list(set(
            parent_a.pair_preference + parent_b.pair_preference
        ))

        # Holding times — average with slight variation
        child.max_holding_minutes = int(
            (parent_a.max_holding_minutes + parent_b.max_holding_minutes) / 2
        )
        child.min_holding_minutes = int(
            (parent_a.min_holding_minutes + parent_b.min_holding_minutes) / 2
        )

        # Aggression — blend
        child.aggression = round(
            (parent_a.aggression + parent_b.aggression) / 2, 2
        )

        # Boolean traits — random inheritance
        child.pyramiding = random.choice([
            parent_a.pyramiding,
            parent_b.pyramiding
        ])
        child.max_layers = random.choice([
            parent_a.max_layers,
            parent_b.max_layers
        ])
        child.hedging = random.choice([
            parent_a.hedging,
            parent_b.hedging
        ])
        child.reverse_signals = random.choice([
            parent_a.reverse_signals,
            parent_b.reverse_signals
        ])

        return child

    @classmethod
    def mutate(cls, dna: "StrategyDNA", rate: float = 0.05) -> "StrategyDNA":
        """
        Create mutated copy of a strategy.
        Each gene has `rate` probability of mutation.
        """
        mutant = copy.deepcopy(dna)
        mutant.strategy_id = str(uuid.uuid4())[:8]
        mutant.name = f"Mutant_{dna.name[:12]}"

        # Mutate stop loss
        if random.random() < rate and mutant.stop_loss:
            mutant.stop_loss["value"] *= random.uniform(0.8, 1.25)
            mutant.stop_loss["value"] = round(mutant.stop_loss["value"], 1)
            if random.random() < rate * 0.5:
                mutant.stop_loss["method"] = random.choice([
                    "ATR_MULTIPLE", "FIXED_PIPS", "SWING_LOW",
                    "SWING_HIGH", "PERCENTAGE",
                ])

        # Mutate take profit
        if random.random() < rate and mutant.take_profit:
            mutant.take_profit["value"] *= random.uniform(0.8, 1.25)
            mutant.take_profit["value"] = round(mutant.take_profit["value"], 1)
            if random.random() < rate * 0.5:
                mutant.take_profit["method"] = random.choice([
                    "RISK_REWARD", "ATR_MULTIPLE", "FIXED_PIPS",
                ])

        # Mutate timeframes
        if random.random() < rate:
            mutant.timeframe = random.choice(cls.TIMEFRAMES)
        if random.random() < rate:
            mutant.confirmation_tf = random.choice(cls.TIMEFRAMES)

        # Mutate preferences
        if random.random() < rate:
            mutant.session_preference = random.choice(cls.SESSIONS)
        if random.random() < rate:
            mutant.regime_preference = random.choice(cls.REGIMES)

        # Mutate aggression
        if random.random() < rate:
            mutant.aggression = round(
                max(0.1, min(0.95, mutant.aggression + random.uniform(-0.2, 0.2))),
                2
            )

        # Mutate holding times
        if random.random() < rate:
            mutant.max_holding_minutes = max(
                10,
                mutant.max_holding_minutes + random.choice([-60, -30, 30, 60, 120])
            )
        if random.random() < rate:
            mutant.min_holding_minutes = max(
                1,
                min(
                    mutant.max_holding_minutes - 5,
                    mutant.min_holding_minutes + random.choice([-5, 5, 10])
                )
            )

        # Mutate entry/exit conditions
        if random.random() < rate * 0.3 and mutant.entry_conditions:
            condition = random.choice(mutant.entry_conditions)
            condition["value"] = round(
                condition.get("value", 50) * random.uniform(0.85, 1.15),
                1
            )
            if random.random() < rate:
                condition["operator"] = random.choice(cls.OPERATORS)

        # Toggle booleans
        if random.random() < rate:
            mutant.pyramiding = not mutant.pyramiding
        if random.random() < rate:
            mutant.hedging = not mutant.hedging

        return mutant

    def complexity_score(self) -> int:
        """Calculate strategy complexity (more conditions = higher score)."""
        return len(self.entry_conditions) + len(self.exit_conditions)

    def is_trend_following(self) -> bool:
        """Check if strategy is trend-following."""
        return self.regime_preference in (
            "TRENDING_UP", "TRENDING_DOWN", "ALL"
        )

    def is_mean_reverting(self) -> bool:
        """Check if strategy is mean-reverting."""
        return self.regime_preference in ("RANGE_BOUND",)

    def __repr__(self) -> str:
        return (
            f"StrategyDNA(id={self.strategy_id}, "
            f"name={self.name}, "
            f"tf={self.timeframe}, "
            f"regime={self.regime_preference}, "
            f"aggression={self.aggression})"
        )


# ── SEED FACTORY ─────────────────────────────────────────

def generate_seed() -> StrategyDNA:
    """Generate a single random seed strategy."""
    dna = StrategyDNA()

    # Random entry condition
    indicator = random.choice(StrategyDNA.INDICATORS)
    operator = random.choice(StrategyDNA.OPERATORS)
    threshold = round(random.uniform(10, 90), 1)
    dna.entry_conditions = [{
        "indicator": indicator,
        "operator": operator,
        "value": threshold,
        "timeframe": random.choice(StrategyDNA.TIMEFRAMES),
    }]

    # Random exit condition
    if random.random() > 0.3:
        exit_indicator = random.choice(StrategyDNA.INDICATORS)
        exit_operator = random.choice([
            "ABOVE", "BELOW", "CROSS_ABOVE", "CROSS_BELOW"
        ])
        exit_threshold = round(random.uniform(20, 80), 1)
        dna.exit_conditions = [{
            "indicator": exit_indicator,
            "operator": exit_operator,
            "value": exit_threshold,
            "timeframe": random.choice(StrategyDNA.TIMEFRAMES),
        }]

    # Risk parameters
    dna.stop_loss = {
        "method": random.choice([
            "ATR_MULTIPLE", "FIXED_PIPS", "SWING_LOW", "SWING_HIGH"
        ]),
        "value": round(random.uniform(0.8, 3.0), 1),
    }
    dna.take_profit = {
        "method": random.choice(["RISK_REWARD", "ATR_MULTIPLE", "FIXED_PIPS"]),
        "value": round(random.uniform(1.5, 4.0), 1),
    }

    # Random trailing stop
    if random.random() > 0.7:
        dna.trailing_stop = {
            "method": "ATR_MULTIPLE",
            "value": round(random.uniform(0.5, 2.0), 1),
            "activation_pct": round(random.uniform(0.3, 0.7), 2),
        }

    # Timeframe
    dna.timeframe = random.choice(StrategyDNA.TIMEFRAMES[2:])  # Skip M1, M5
    dna.confirmation_tf = random.choice(
        [tf for tf in StrategyDNA.TIMEFRAMES if tf != dna.timeframe]
    )

    # Preferences
    dna.session_preference = random.choice(StrategyDNA.SESSIONS)
    dna.regime_preference = random.choice(StrategyDNA.REGIMES)
    dna.pair_preference = random.sample(
        ["EURUSD", "GBPUSD", "USDJPY", "EURGBP"],
        k=random.randint(0, 4)
    )

    # Holding times
    dna.max_holding_minutes = random.choice([5, 15, 30, 60, 120, 240, 480, 1440])
    dna.min_holding_minutes = random.choice([1, 2, 5, 10, 15])

    # Behavior
    dna.aggression = round(random.uniform(0.2, 0.9), 2)
    dna.pyramiding = random.random() > 0.8
    dna.max_layers = random.choice([1, 1, 2, 2, 3])
    dna.hedging = random.random() > 0.9
    dna.reverse_signals = random.random() > 0.95

    return dna


def generate_seeds(count: int = 250) -> List[StrategyDNA]:
    """Generate a population of random seed strategies."""
    seeds = []
    for i in range(count):
        seed = generate_seed()
        seed.name = f"Seed_{i+1:04d}"
        seeds.append(seed)
    return seeds