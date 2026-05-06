"""
Evolution engine — weekend genetic algorithm cycle.
Ranks strategies, breeds elites, mutates, and culls underperformers.
Maintains population diversity and prevents stagnation.
"""

import random
import copy
from typing import List, Dict, Tuple
from datetime import datetime, timezone

from .dna import StrategyDNA, generate_seeds
from core.logger import get_logger

logger = get_logger("evolution")


class EvolutionEngine:
    """
    Genetic algorithm for strategy population management.
    Runs weekly during market close to optimize the strategy pool.
    """

    # Population management
    MIN_POPULATION: int = 50
    MAX_POPULATION: int = 500
    ELITE_RATE: float = 0.20   # Top 20% survive
    CULL_RATE: float = 0.20     # Bottom 20% removed
    BREED_RATE: float = 0.30    # 30% new from breeding
    MUTATION_RATE: float = 0.05 # 5% mutation probability per gene
    SEED_RATE: float = 0.10     # 10% fresh seeds for diversity

    # Performance thresholds
    MIN_TRADES_FOR_EVALUATION: int = 5
    SUSPEND_AFTER_LOSSES: int = 5
    PROMOTE_MIN_TRADES: int = 20
    PROMOTE_MIN_WIN_RATE: float = 0.55
    PROMOTE_MIN_PROFIT_FACTOR: float = 1.5

    def __init__(self):
        self.generation: int = 0
        self.evolution_history: List[dict] = []

    def rank(
        self,
        strategies: List[dict]
    ) -> List[dict]:
        """
        Rank strategies by composite fitness score.
        
        Fitness = (profit_factor × 0.4) + (win_rate × 0.3) + 
                 (sharpe × 0.2) + (trades_penalty × 0.1)
        """
        for s in strategies:
            pf = float(s.get("profit_factor", 0) or 0)
            wr = float(s.get("win_rate", 0) or 0)
            sharpe = float(s.get("sharpe_ratio", 0) or 0)
            trades = int(s.get("total_trades", 0) or 0)

            # Trading activity bonus (more trades = more confidence)
            trades_score = min(1.0, trades / self.PROMOTE_MIN_TRADES)

            # Composite fitness
            fitness = (
                pf * 0.4 +
                wr * 0.3 +
                sharpe * 0.2 +
                trades_score * 0.1
            )

            # Penalize losing streaks
            if float(s.get("win_rate", 0.5)) < 0.4:
                fitness *= 0.7

            s["_fitness"] = round(fitness, 4)

        return sorted(strategies, key=lambda s: s.get("_fitness", 0), reverse=True)

    def evolve(self, strategies: List[dict]) -> dict:
        """
        Run one evolution cycle.
        
        Returns dict with:
        - generation: int
        - killed: int
        - bred: int
        - mutated: int
        - seeded: int
        - promoted: int
        - strategies: list (updated population)
        """
        self.generation += 1
        now = datetime.now(timezone.utc).isoformat()

        logger.evolution(
            "CYCLE_START",
            f"Generation {self.generation} | Population: {len(strategies)}"
        )

        # Handle empty or very small populations
        if not strategies or len(strategies) < 10:
            logger.warning("Population too small — generating fresh seeds")
            new_seeds = [s.to_dict() for s in generate_seeds(self.MIN_POPULATION)]
            for s in new_seeds:
                s["status"] = "TESTING"
                s["generation"] = self.generation
                s["birth_type"] = "SEED"
                s["profit_factor"] = 0.0
                s["win_rate"] = 0.0
                s["total_trades"] = 0
                s["_fitness"] = 0.0
            return {
                "generation": self.generation,
                "killed": 0,
                "bred": len(new_seeds),
                "mutated": 0,
                "seeded": len(new_seeds),
                "promoted": 0,
                "strategies": new_seeds,
            }

        # Rank by fitness
        ranked = self.rank(strategies)
        n = len(ranked)

        # Calculate populations
        elite_count = max(2, int(n * self.ELITE_RATE))
        cull_count = max(1, int(n * self.CULL_RATE))
        breed_count = max(1, int(n * self.BREED_RATE))
        seed_count = max(1, int(n * self.SEED_RATE))

        # Split populations
        elite = ranked[:elite_count]
        middle = ranked[elite_count:n - cull_count]
        dead = ranked[n - cull_count:]

        # Promote strategies meeting criteria
        promoted = 0
        for s in elite + middle:
            trades = int(s.get("total_trades", 0) or 0)
            wr = float(s.get("win_rate", 0) or 0)
            pf = float(s.get("profit_factor", 0) or 0)
            status = s.get("status", "TESTING")

            if (
                status == "TESTING" and
                trades >= self.PROMOTE_MIN_TRADES and
                wr >= self.PROMOTE_MIN_WIN_RATE and
                pf >= self.PROMOTE_MIN_PROFIT_FACTOR
            ):
                s["status"] = "ACTIVE"
                promoted += 1

        # Suspend strategies on losing streaks
        for s in elite + middle:
            wr = float(s.get("win_rate", 1.0) or 1.0)
            trades = int(s.get("total_trades", 0) or 0)
            if trades >= 10 and wr < 0.30:
                s["status"] = "SUSPENDED"
                logger.warning(
                    f"Strategy {s.get('strategy_id')} suspended: "
                    f"WR={wr:.2%} after {trades} trades"
                )

        # Breed elite pairs
        children = []
        for i in range(0, len(elite) - 1, 2):
            parent_a_dna = StrategyDNA.from_dict(elite[i].get("dna", {}))
            parent_b_dna = StrategyDNA.from_dict(elite[i + 1].get("dna", {}))

            child_dna = StrategyDNA.breed(parent_a_dna, parent_b_dna)

            # Chance of mutation
            if random.random() < self.MUTATION_RATE:
                child_dna = StrategyDNA.mutate(child_dna, self.MUTATION_RATE)

            child_dict = child_dna.to_dict()
            child_dict["status"] = "TESTING"
            child_dict["generation"] = self.generation
            child_dict["birth_type"] = "BRED"
            child_dict["profit_factor"] = 0.0
            child_dict["win_rate"] = 0.0
            child_dict["total_trades"] = 0
            child_dict["_fitness"] = 0.0

            children.append(child_dict)

            if len(children) >= breed_count:
                break

        # Generate fresh seeds for diversity
        seeds = []
        for _ in range(seed_count):
            seed = generate_seed()
            seed_dict = seed.to_dict()
            seed_dict["status"] = "TESTING"
            seed_dict["generation"] = self.generation
            seed_dict["birth_type"] = "SEED"
            seed_dict["profit_factor"] = 0.0
            seed_dict["win_rate"] = 0.0
            seed_dict["total_trades"] = 0
            seed_dict["_fitness"] = 0.0
            seeds.append(seed_dict)

        # Kill bottom performers
        killed = 0
        for s in dead:
            trades = int(s.get("total_trades", 0) or 0)
            if trades >= self.MIN_TRADES_FOR_EVALUATION:
                s["status"] = "RETIRED"
                killed += 1

        # Assemble new population
        new_population = middle + children + seeds

        # Enforce population limits
        if len(new_population) > self.MAX_POPULATION:
            new_population = sorted(
                new_population,
                key=lambda s: s.get("_fitness", 0),
                reverse=True
            )[:self.MAX_POPULATION]
        elif len(new_population) < self.MIN_POPULATION:
            extra_seeds = generate_seeds(self.MIN_POPULATION - len(new_population))
            for seed in extra_seeds:
                sd = seed.to_dict()
                sd.update({
                    "status": "TESTING",
                    "generation": self.generation,
                    "birth_type": "SEED",
                    "profit_factor": 0.0,
                    "win_rate": 0.0,
                    "total_trades": 0,
                    "_fitness": 0.0,
                })
                new_population.append(sd)

        # Clean up internal fields
        for s in new_population:
            s.pop("_fitness", None)

        # Record evolution history
        summary = {
            "generation": self.generation,
            "killed": killed,
            "bred": len(children),
            "mutated": len([c for c in children if "Mutant" in c.get("strategy_name", "")]),
            "seeded": len(seeds),
            "promoted": promoted,
            "population_before": n,
            "population_after": len(new_population),
            "strategies": new_population,
        }
        self.evolution_history.append({
            "timestamp": now,
            **{k: v for k, v in summary.items() if k != "strategies"},
        })

        logger.evolution(
            "CYCLE_COMPLETE",
            f"Gen {self.generation}: "
            f"{killed} killed, {len(children)} bred, "
            f"{len(seeds)} seeded, {promoted} promoted, "
            f"Population: {len(new_population)}"
        )

        return summary

    def get_diversity_score(self, strategies: List[dict]) -> float:
        """
        Calculate population diversity.
        Higher score = more diverse strategy pool.
        """
        if len(strategies) < 2:
            return 0.0

        # Count unique combinations of timeframe + regime + session
        combinations = set()
        for s in strategies:
            dna = s.get("dna", {})
            combo = (
                dna.get("tf", ""),
                dna.get("regime", ""),
                dna.get("session", ""),
            )
            combinations.add(combo)

        return len(combinations) / len(strategies)

    def get_generation_summary(self) -> dict:
        """Get summary of all evolution cycles."""
        return {
            "total_generations": self.generation,
            "history": self.evolution_history[-10:],  # Last 10 cycles
        }