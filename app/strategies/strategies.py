"""
Optimization Strategies
=======================
Each function receives pre-processed numpy / pandas data and returns
an array of optimised weights in *decimal* form (0-1), summing to 1.

Strategies:
  1. equal_weights
  2. risk_parity
  3. minimize_drawdown
  4. minimize_volatility
  5. maximize_sharpe
  6. optimize_factor_exposure  (Bonus)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from app.utils.portfolio_math import (
    annualised_volatility,
    cov_matrix,
    individual_volatilities,
    max_drawdown,
    portfolio_returns,
    sharpe_ratio,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uniform_start(n: int) -> np.ndarray:
    """Equal-weight starting point for optimisers."""
    return np.ones(n) / n


def _clip_and_normalise(w: np.ndarray, bounds) -> np.ndarray:
    """
    Post-process: clip to bounds then renormalise so weights sum to 1.
    This handles tiny floating-point violations returned by the solver.
    """
    lb = np.array([b[0] for b in bounds])
    ub = np.array([b[1] for b in bounds])
    w = np.clip(w, lb, ub)
    total = w.sum()
    if total <= 0:
        w = np.array(lb)
        w = np.clip(w, lb, ub)
        total = w.sum()
    return w / total


def _check_feasibility(result, strategy_name: str) -> np.ndarray:
    """Raise ValueError if scipy could not find a feasible solution."""
    if not result.success:
        # Some solvers set success=False but still return a decent solution;
        # tolerate small constraint violations (|fun| < 1e-6).
        if result.fun is None or abs(result.fun) > 1e-4:
            raise ValueError(
                f"Optimisation failed for strategy '{strategy_name}': {result.message}"
            )
    return result.x


# ---------------------------------------------------------------------------
# 1. Equal Weights
# ---------------------------------------------------------------------------

def equal_weights(n: int, **_) -> np.ndarray:
    """Assign 1/n to each security."""
    return _uniform_start(n)


# ---------------------------------------------------------------------------
# 2. Risk Parity
# ---------------------------------------------------------------------------

def risk_parity(
    returns_df: pd.DataFrame,
    bounds: list,
    periods_per_year: int,
    **_,
) -> np.ndarray:
    """
    Each asset contributes equally to total portfolio risk.
    Minimise sum of squared differences between risk contributions.

    Risk contribution of asset i = w_i * (Σw)_i / (w'Σw)
    where Σ is the covariance matrix.
    """
    n = returns_df.shape[1]
    cov = cov_matrix(returns_df, periods_per_year)

    def _objective(w):
        port_var = w @ cov @ w
        if port_var <= 0:
            return 1e10
        marginal_risk = cov @ w
        risk_contrib = w * marginal_risk / port_var
        target = 1.0 / n
        return float(np.sum((risk_contrib - target) ** 2))

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    x0 = _uniform_start(n)

    result = minimize(
        _objective,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 2000, "ftol": 1e-12},
    )
    w = _check_feasibility(result, "risk_parity")
    return _clip_and_normalise(w, bounds)


# ---------------------------------------------------------------------------
# 3. Minimize Drawdown
# ---------------------------------------------------------------------------

def minimize_drawdown_strategy(
    returns_df: pd.DataFrame,
    bounds: list,
    constraints: list,
    periods_per_year: int,
    **_,
) -> np.ndarray:
    """
    Find weights that minimise the maximum historical peak-to-trough drawdown.
    """
    n = returns_df.shape[1]
    x0 = _uniform_start(n)

    def _objective(w):
        ret = portfolio_returns(w, returns_df)
        return max_drawdown(ret)

    result = minimize(
        _objective,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 3000, "ftol": 1e-10},
    )
    w = _check_feasibility(result, "minimize_drawdown")
    return _clip_and_normalise(w, bounds)


# ---------------------------------------------------------------------------
# 4. Minimize Volatility
# ---------------------------------------------------------------------------

def minimize_volatility_strategy(
    returns_df: pd.DataFrame,
    bounds: list,
    constraints: list,
    periods_per_year: int,
    **_,
) -> np.ndarray:
    """
    Classic mean-variance: find the global minimum variance portfolio.
    Uses the analytical covariance matrix for speed, but respects
    all supplied constraints via SLSQP.
    """
    n = returns_df.shape[1]
    cov = cov_matrix(returns_df, periods_per_year)
    x0 = _uniform_start(n)

    def _objective(w):
        return float(w @ cov @ w)  # portfolio variance (minimise)

    def _grad(w):
        return 2 * cov @ w

    result = minimize(
        _objective,
        x0,
        jac=_grad,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 2000, "ftol": 1e-12},
    )
    w = _check_feasibility(result, "minimize_volatility")
    return _clip_and_normalise(w, bounds)


# ---------------------------------------------------------------------------
# 5. Maximize Sharpe Ratio
# ---------------------------------------------------------------------------

def maximize_sharpe_strategy(
    returns_df: pd.DataFrame,
    bounds: list,
    constraints: list,
    periods_per_year: int,
    risk_free_rate: float = 0.0,
    **_,
) -> np.ndarray:
    """
    Maximise risk-adjusted return (Sharpe ratio).

    When there are no extra portfolio-level constraints we use the
    classic two-fund separation (Tangency portfolio via the analytical
    solution on the covariance matrix).  When extra constraints exist,
    we fall back to SLSQP numerical optimisation so all constraints
    are honoured.
    """
    n = returns_df.shape[1]
    cov = cov_matrix(returns_df, periods_per_year)
    # Annualised mean returns (in %)
    mu = returns_df.mean().values * periods_per_year

    x0 = _uniform_start(n)

    def _neg_sharpe(w):
        return -sharpe_ratio(
            portfolio_returns(w, returns_df),
            periods_per_year,
            risk_free_rate,
        )

    # Check if any constraint beyond the sum-to-1 equality is present
    has_extra_constraints = any(c.get("type") == "ineq" for c in constraints)
    has_custom_bounds = any(b != (0.0, 1.0) for b in bounds)

    if not has_extra_constraints and not has_custom_bounds:
        # Analytical tangency portfolio (no short selling: clip & renormalise)
        try:
            excess_mu = mu - risk_free_rate
            inv_cov = np.linalg.inv(cov + np.eye(n) * 1e-8)  # regularise
            z = inv_cov @ excess_mu
            if z.sum() > 0:
                w = z / z.sum()
                w = np.clip(w, 0, 1)
                if w.sum() > 0:
                    return w / w.sum()
        except np.linalg.LinAlgError:
            pass  # fall through to numerical

    result = minimize(
        _neg_sharpe,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 3000, "ftol": 1e-12},
    )
    w = _check_feasibility(result, "maximize_sharpe")
    return _clip_and_normalise(w, bounds)


# ---------------------------------------------------------------------------
# 6. Optimize Factor Exposure  (Bonus)
# ---------------------------------------------------------------------------

def optimize_factor_exposure(
    returns_df: pd.DataFrame,
    factor_df: pd.DataFrame,
    factor_objectives: list,  # List[FactorObjective]
    bounds: list,
    constraints: list,
    periods_per_year: int,
    **_,
) -> np.ndarray:
    """
    Maximise or minimise exposure (OLS beta) to one or more risk factors.

    Approach:
    1. Compute OLS betas of each individual asset vs each factor.
    2. The portfolio's factor beta = weighted sum of individual betas.
       (This is valid for linear factor models and avoids rerunning a
        regression inside the optimiser, making it fast and differentiable.)
    3. Optimise the objective subject to weight constraints.
    """
    # Align dates between portfolio returns and factor returns
    common_idx = returns_df.index.intersection(factor_df.index)
    if len(common_idx) < 10:
        raise ValueError(
            "Fewer than 10 overlapping dates between portfolio returns and "
            "factor returns. Cannot compute reliable factor betas."
        )

    port_r = returns_df.loc[common_idx]
    fact_r = factor_df.loc[common_idx]

    # --- Step 1: OLS beta of each asset on each factor ---
    # Factor matrix X with constant: shape (T, F+1)
    X = np.column_stack([np.ones(len(fact_r)), fact_r.values])  # (T, F+1)
    n_assets = port_r.shape[1]
    n_factors = fact_r.shape[1]
    factor_names = list(fact_r.columns)

    # asset_betas[i, j] = beta of asset i on factor j
    asset_betas = np.zeros((n_assets, n_factors))
    for i in range(n_assets):
        y = port_r.iloc[:, i].values
        try:
            coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            asset_betas[i, :] = coeffs[1:]  # skip intercept
        except np.linalg.LinAlgError:
            pass  # leave as zeros

    # --- Step 2: Build objective ---
    # Portfolio factor beta j = w' * asset_betas[:, j]
    # Build a combined objective: weighted sum across all requested factors.
    def _objective(w):
        total = 0.0
        for fo in factor_objectives:
            j = factor_names.index(fo.factor.value)
            port_beta = float(w @ asset_betas[:, j])
            if fo.direction.value == "maximize":
                total -= port_beta   # negate to minimise
            else:
                total += port_beta
        return total

    n = returns_df.shape[1]
    x0 = _uniform_start(n)

    result = minimize(
        _objective,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 3000, "ftol": 1e-12},
    )
    w = _check_feasibility(result, "optimize_factor_exposure")
    return _clip_and_normalise(w, bounds)
