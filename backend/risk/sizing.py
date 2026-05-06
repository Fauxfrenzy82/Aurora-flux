"""
Position sizing engine — 8 constraints plus Kelly Criterion and Risk of Ruin.
Calculates the optimal position size given all limits.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from core.config import config
from core.logger import get_logger

logger = get_logger("risk")


@dataclass
class PositionSize:
    """Result of position sizing calculation."""
    size: float = 0.0
    rejected: bool = False
    reason: str = ""
    binding_constraint: str = ""
    risk_amount: float = 0.0
    risk_pct: float = 0.0
    risk_of_ruin: float = 0.0
    kelly_fraction: float = 0.0
    constraints: Dict[str, float] = field(default_factory=dict)
    drawdown_remaining: float = 0.0
    daily_cap_remaining: float = 0.0


@dataclass
class SizingConstraints:
    """All constraints used for position sizing."""
    equity: float
    balance: float
    entry_price: float
    stop_loss: float
    direction: str
    current_exposure: float = 0.0
    volatility_ratio: float = 1.0
    correlation_penalty: float = 1.0
    regime_multiplier: float = 1.0
    strategy_win_rate: float = 0.5
    strategy_profit_factor: float = 1.0
    daily_pnl: float = 0.0
    daily_risk_used: float = 0.0
    total_positions: int = 0


def calculate_kelly(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
) -> float:
    """
    Calculate Kelly Criterion fraction.
    f* = (p * b - (1-p)) / b
    where p = win_rate, b = avg_win/avg_loss
    """
    if avg_loss <= 0:
        return 0.0
    b = avg_win / avg_loss
    if b <= 0:
        return 0.0
    kelly = (win_rate * b - (1 - win_rate)) / b
    return max(0.0, kelly)


def calculate_risk_of_ruin(
    win_rate: float,
    risk_per_trade: float,
    capital: float,
) -> float:
    """
    Calculate Risk of Ruin using the formula:
    ROR = ((1 - edge) / (1 + edge)) ^ (capital / risk_per_trade)
    """
    if risk_per_trade <= 0 or capital <= 0:
        return 1.0

    edge = 2 * win_rate - 1
    if edge <= 0:
        return 1.0

    capital_units = capital / risk_per_trade
    if capital_units <= 0:
        return 1.0

    try:
        ror = ((1 - edge) / (1 + edge)) ** capital_units
        return round(ror, 6)
    except (OverflowError, ValueError):
        return 0.0 if edge > 0 else 1.0


def calculate_position(
    entry: float,
    stop: float,
    direction: str,
    equity: float,
    balance: float,
    exposure: float = 0.0,
    vol_ratio: float = 1.0,
    regime_mult: float = 1.0,
    corr_penalty: float = 1.0,
    daily_cap_remaining: float = None,
    drawdown_budget: float = None,
    mode: str = None,
    strategy_win_rate: float = 0.5,
    strategy_profit_factor: float = 1.0,
    total_positions: int = 0,
) -> PositionSize:
    """
    Calculate optimal position size considering 8 constraints.
    
    Constraints:
    1. Max Risk per Trade (Kelly-based)
    2. Daily Drawdown Limit
    3. Max Drawdown Limit
    4. Total Exposure Limit
    5. Volatility Adjustment
    6. Regime Adjustment
    7. Correlation Penalty
    8. Balance Limit
    
    Returns PositionSize with result or rejection reason.
    """
    if mode is None:
        mode = config.MODE

    # Validate inputs
    risk_per_unit = abs(entry - stop)
    if risk_per_unit <= 0:
        logger.warning("Invalid stop loss: risk per unit is zero")
        return PositionSize(
            rejected=True,
            reason="Invalid stop loss: zero risk per unit"
        )

    if equity <= 0:
        return PositionSize(
            rejected=True,
            reason="No equity available"
        )

    # Default remaining caps
    if daily_cap_remaining is None:
        daily_cap_remaining = equity * config.DAILY_CAP_PCT / 100

    if drawdown_budget is None:
        drawdown_budget = equity * config.MAX_DRAWDOWN_PCT / 100

    # ── Constraint 1: Max Risk Per Trade (Kelly) ───────

    base_risk_pct = config.BASE_RISK_PCT / 100
    kelly_frac = (
        config.KELLY_FRACTION_PHASE
        if mode == "PHASE"
        else config.KELLY_FRACTION_FREEDOM
    )

    # Adjust Kelly based on strategy performance
    if strategy_win_rate > 0.5 and strategy_profit_factor > 1.0:
        full_kelly = calculate_kelly(strategy_win_rate, 1.0, 1.0 / strategy_profit_factor)
        effective_kelly = full_kelly * kelly_frac
    else:
        effective_kelly = kelly_frac * 0.5  # Half Kelly for unproven strategies

    risk_pct = base_risk_pct * effective_kelly
    max_risk_dollars = equity * risk_pct
    c1_size = max_risk_dollars / risk_per_unit

    # ── Constraint 2: Daily Cap ────────────────────────

    c2_size = (
        daily_cap_remaining / (risk_per_unit * 2.5)
        if daily_cap_remaining > 0
        else 0.0
    )

    # ── Constraint 3: Drawdown Budget ──────────────────

    c3_size = (
        drawdown_budget / (risk_per_unit * 2.0)
        if drawdown_budget > 0
        else 0.0
    )

    # ── Constraint 4: Total Exposure ───────────────────

    max_exposure = equity * config.MAX_EXPOSURE_PCT / 100
    available_exposure = max_exposure - exposure
    c4_size = (
        available_exposure / (entry * 100000)
        if entry > 0 and available_exposure > 0
        else 0.0
    )

    # ── Constraint 5: Volatility ───────────────────────

    c5_size = c1_size / max(vol_ratio, 0.5)

    # ── Constraint 6: Regime ───────────────────────────

    c6_size = c1_size * max(regime_mult, 0.3)

    # ── Constraint 7: Correlation ──────────────────────

    c7_size = c1_size * max(corr_penalty, 0.3)

    # ── Constraint 8: Balance ──────────────────────────

    c8_size = balance / (entry * 100000) if entry > 0 else 0.0

    # ── Max Positions Constraint ───────────────────────

    if total_positions >= config.MAX_POSITIONS:
        return PositionSize(
            rejected=True,
            reason=f"Max positions reached: {total_positions}/{config.MAX_POSITIONS}",
            constraints={
                "Max Risk": round(c1_size, 4),
                "Daily Cap": round(c2_size, 4),
                "Drawdown": round(c3_size, 4),
                "Exposure": round(c4_size, 4),
                "Volatility": round(c5_size, 4),
                "Regime": round(c6_size, 4),
                "Correlation": round(c7_size, 4),
                "Balance": round(c8_size, 4),
            }
        )

    # ── Find Binding Constraint ─────────────────────────

    constraints = {
        "Max Risk": c1_size,
        "Daily Cap": c2_size,
        "Drawdown": c3_size,
        "Exposure": c4_size,
        "Volatility": c5_size,
        "Regime": c6_size,
        "Correlation": c7_size,
        "Balance": c8_size,
    }

    # Filter out zero and negative constraints
    valid_constraints = {
        name: size for name, size in constraints.items()
        if size > 0
    }

    if not valid_constraints:
        return PositionSize(
            rejected=True,
            reason="All constraints are zero or negative",
            constraints={k: round(v, 4) for k, v in constraints.items()}
        )

    binding_name = min(valid_constraints, key=valid_constraints.get)
    raw_size = valid_constraints[binding_name]

    # ── Round to Lot Size ──────────────────────────────

    min_lot = 0.01
    final_size = max(min_lot, round(raw_size / min_lot) * min_lot)

    # ── Calculate Risk Metrics ─────────────────────────

    risk_amount = final_size * risk_per_unit
    actual_risk_pct = risk_amount / equity if equity > 0 else 0

    # Risk of Ruin
    ror = calculate_risk_of_ruin(
        strategy_win_rate,
        risk_amount,
        equity
    )

    # ── Safety Checks ──────────────────────────────────

    if ror > 0.02:  # More than 2% risk of ruin
        return PositionSize(
            rejected=True,
            reason=f"Risk of Ruin too high: {ror:.4f} ({ror*100:.2f}%)",
            risk_of_ruin=ror,
            constraints={k: round(v, 4) for k, v in constraints.items()}
        )

    if actual_risk_pct > config.BASE_RISK_PCT / 100 * 2.0:
        return PositionSize(
            rejected=True,
            reason=f"Risk exceeds maximum: {actual_risk_pct:.2%} > {config.BASE_RISK_PCT*2:.1f}%",
            risk_pct=actual_risk_pct,
            constraints={k: round(v, 4) for k, v in constraints.items()}
        )

    # Log the sizing decision
    logger.risk("POSITION_SIZED", {
        "size": final_size,
        "risk_pct": round(actual_risk_pct, 4),
        "binding": binding_name,
        "risk_amount": round(risk_amount, 2),
        "ror": ror,
    })

    return PositionSize(
        size=round(final_size, 4),
        rejected=False,
        binding_constraint=binding_name,
        risk_amount=round(risk_amount, 2),
        risk_pct=round(actual_risk_pct, 4),
        risk_of_ruin=ror,
        kelly_fraction=effective_kelly,
        constraints={k: round(v, 4) for k, v in constraints.items()},
        drawdown_remaining=drawdown_budget,
        daily_cap_remaining=daily_cap_remaining,
    )