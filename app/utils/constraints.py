"""
Constraint & bounds helpers for scipy.optimize
===============================================
All weight values passed into scipy are in *decimal* form (0-1).
All constraint thresholds from the request are in *percent* form.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import LinearConstraint, NonlinearConstraint

from app.utils.portfolio_math import (
    annualised_return,
    annualised_volatility,
    max_drawdown,
    portfolio_dividend_yield,
    portfolio_returns,
)


def build_bounds(
    n: int,
    min_weight: Optional[float],
    max_weight: Optional[float],
) -> List[Tuple[float, float]]:
    """
    Scipy bounds: list of (lb, ub) tuples in decimal units.
    Falls back to (0, 1) per asset if no constraint specified.
    """
    lb = (min_weight / 100) if min_weight is not None else 0.0
    ub = (max_weight / 100) if max_weight is not None else 1.0
    return [(lb, ub)] * n


def build_constraints(
    constraints,  # WeightConstraints | None
    returns_df: pd.DataFrame,
    dividend_yields: np.ndarray,
    periods_per_year: int,
    risk_free_rate: float,
) -> list:
    """
    Build a list of scipy constraint dicts / objects from the request constraints.
    Weights passed to all functions are in decimal (0-1).
    """
    cons = []

    # --- Weights must sum to 1 (always required) ---
    cons.append(
        {
            "type": "eq",
            "fun": lambda w: np.sum(w) - 1.0,
        }
    )

    if constraints is None:
        return cons

    # --- Minimum CAGR ---
    if constraints.min_cagr is not None:
        min_cagr = constraints.min_cagr  # in %

        def _cagr_con(w):
            ret = portfolio_returns(w, returns_df)
            return annualised_return(ret, periods_per_year) - min_cagr

        cons.append({"type": "ineq", "fun": _cagr_con})

    # --- Volatility range ---
    if constraints.max_volatility is not None:
        max_vol = constraints.max_volatility  # in %

        def _max_vol_con(w):
            ret = portfolio_returns(w, returns_df)
            return max_vol - annualised_volatility(ret, periods_per_year)

        cons.append({"type": "ineq", "fun": _max_vol_con})

    if constraints.min_volatility is not None:
        min_vol = constraints.min_volatility  # in %

        def _min_vol_con(w):
            ret = portfolio_returns(w, returns_df)
            return annualised_volatility(ret, periods_per_year) - min_vol

        cons.append({"type": "ineq", "fun": _min_vol_con})

    # --- Max drawdown ---
    if constraints.max_drawdown is not None:
        max_dd = constraints.max_drawdown  # in %

        def _dd_con(w):
            ret = portfolio_returns(w, returns_df)
            return max_dd - max_drawdown(ret)

        cons.append({"type": "ineq", "fun": _dd_con})

    # --- Minimum dividend yield ---
    if constraints.min_dividend_yield is not None:
        min_dy = constraints.min_dividend_yield / 100  # fraction

        def _dy_con(w):
            return portfolio_dividend_yield(w, dividend_yields / 100) - min_dy

        cons.append({"type": "ineq", "fun": _dy_con})

    return cons
