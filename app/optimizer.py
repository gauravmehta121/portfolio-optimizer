"""
Optimization Orchestrator
=========================
Translates an OptimizationRequest into an OptimizationResponse by:
  1. Preparing data (return matrix, bounds, constraints)
  2. Dispatching to the correct strategy
  3. Computing portfolio statistics
  4. (Bonus) Computing factor betas
  5. Assembling the response
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.models.schemas import (
    AllocationChange,
    FactorBetaResult,
    FactorBetas,
    OptimizationRequest,
    OptimizationResponse,
    PortfolioStats,
    Strategy,
)
from app.strategies.strategies import (
    equal_weights,
    maximize_sharpe_strategy,
    minimize_drawdown_strategy,
    minimize_volatility_strategy,
    optimize_factor_exposure,
    risk_parity,
)
from app.utils.constraints import build_bounds, build_constraints
from app.utils.factor_betas import compute_factor_betas
from app.utils.portfolio_math import (
    build_factor_matrix,
    build_return_matrix,
    compute_portfolio_stats,
    portfolio_returns,
)


def run_optimization(request: OptimizationRequest) -> OptimizationResponse:
    """
    Main entry point called by the FastAPI route handler.
    """
    # ------------------------------------------------------------------
    # 1. Build return matrix and metadata arrays
    # ------------------------------------------------------------------
    returns_df, tickers = build_return_matrix(request.securities)

    # Map ticker → security metadata for easy lookup
    sec_map = {s.ticker: s for s in request.securities}

    # Current weights in decimal (0-1), ordered by tickers
    current_weights = np.array(
        [sec_map[t].current_weight / 100.0 for t in tickers]
    )

    # Dividend yields in percent, ordered by tickers
    dividend_yields = np.array(
        [sec_map[t].dividend_yield for t in tickers]
    )

    n = len(tickers)
    periods_per_year = request.periods_per_year
    risk_free_rate = request.risk_free_rate

    # ------------------------------------------------------------------
    # 2. Build scipy bounds and constraints
    # ------------------------------------------------------------------
    constraints_input = request.constraints

    bounds = build_bounds(
        n,
        min_weight=constraints_input.min_weight if constraints_input else None,
        max_weight=constraints_input.max_weight if constraints_input else None,
    )

    scipy_constraints = build_constraints(
        constraints=constraints_input,
        returns_df=returns_df,
        dividend_yields=dividend_yields,
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
    )

    # ------------------------------------------------------------------
    # 3. Factor data (if provided)
    # ------------------------------------------------------------------
    factor_df: pd.DataFrame | None = None
    if request.factor_returns:
        factor_df = build_factor_matrix(request.factor_returns)

    # ------------------------------------------------------------------
    # 4. Dispatch to strategy
    # ------------------------------------------------------------------
    strategy = request.strategy
    kwargs = dict(
        returns_df=returns_df,
        bounds=bounds,
        constraints=scipy_constraints,
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
        n=n,
    )

    if strategy == Strategy.equal_weights:
        opt_weights = equal_weights(n)

    elif strategy == Strategy.risk_parity:
        opt_weights = risk_parity(**kwargs)

    elif strategy == Strategy.minimize_drawdown:
        opt_weights = minimize_drawdown_strategy(**kwargs)

    elif strategy == Strategy.minimize_volatility:
        opt_weights = minimize_volatility_strategy(**kwargs)

    elif strategy == Strategy.maximize_sharpe:
        opt_weights = maximize_sharpe_strategy(**kwargs)

    elif strategy == Strategy.optimize_factor_exposure:
        if factor_df is None:
            raise ValueError("factor_returns must be provided for this strategy.")
        opt_weights = optimize_factor_exposure(
            factor_df=factor_df,
            factor_objectives=request.factor_objectives,
            **kwargs,
        )
    else:
        raise ValueError(f"Unsupported strategy: {strategy}")

    # Final safety normalisation
    opt_weights = np.clip(opt_weights, 0, 1)
    opt_weights = opt_weights / opt_weights.sum()

    # ------------------------------------------------------------------
    # 5. Validate post-optimisation constraints
    #    (return a useful error if a hard constraint is violated)
    # ------------------------------------------------------------------
    _validate_constraints_post(
        opt_weights, constraints_input, returns_df,
        dividend_yields, periods_per_year, risk_free_rate, tickers
    )

    # ------------------------------------------------------------------
    # 6. Compute portfolio statistics for both current and optimised
    # ------------------------------------------------------------------
    current_stats = compute_portfolio_stats(
        current_weights, returns_df, dividend_yields, periods_per_year, risk_free_rate
    )
    opt_stats = compute_portfolio_stats(
        opt_weights, returns_df, dividend_yields, periods_per_year, risk_free_rate
    )

    # ------------------------------------------------------------------
    # 7. Factor betas (Bonus)
    # ------------------------------------------------------------------
    factor_beta_result: FactorBetaResult | None = None

    if factor_df is not None:
        # Current portfolio return series
        curr_port_ret = pd.Series(
            portfolio_returns(current_weights, returns_df),
            index=returns_df.index,
        )
        opt_port_ret = pd.Series(
            portfolio_returns(opt_weights, returns_df),
            index=returns_df.index,
        )

        curr_betas = compute_factor_betas(curr_port_ret, factor_df)
        opt_betas = compute_factor_betas(opt_port_ret, factor_df)

        factor_beta_result = FactorBetaResult(
            current_portfolio=FactorBetas(
                value=curr_betas.get("value"),
                momentum=curr_betas.get("momentum"),
                size=curr_betas.get("size"),
            ),
            optimized_portfolio=FactorBetas(
                value=opt_betas.get("value"),
                momentum=opt_betas.get("momentum"),
                size=opt_betas.get("size"),
            ),
        )

    # ------------------------------------------------------------------
    # 8. Assemble allocation_changes list
    # ------------------------------------------------------------------
    allocation_changes = []
    for i, ticker in enumerate(tickers):
        sec = sec_map[ticker]
        curr_w_pct = round(current_weights[i] * 100, 4)
        opt_w_pct = round(opt_weights[i] * 100, 4)
        allocation_changes.append(
            AllocationChange(
                ticker=ticker,
                security_name=sec.security_name,
                current_weight=curr_w_pct,
                optimized_weight=opt_w_pct,
                change=round(opt_w_pct - curr_w_pct, 4),
            )
        )

    return OptimizationResponse(
        optimization_strategy=strategy.value,
        allocation_changes=allocation_changes,
        current_portfolio_stats=PortfolioStats(**current_stats),
        optimized_portfolio_stats=PortfolioStats(**opt_stats),
        factor_betas=factor_beta_result,
    )


# ---------------------------------------------------------------------------
# Post-optimisation constraint validation
# ---------------------------------------------------------------------------

def _validate_constraints_post(
    opt_weights, constraints_input, returns_df,
    dividend_yields, periods_per_year, risk_free_rate, tickers
):
    """
    Check that the returned weights satisfy all requested constraints.
    Raises ValueError with a descriptive message if any constraint is violated.
    Tolerances are generous (1%) to avoid false positives from floating point.
    """
    if constraints_input is None:
        return

    from app.utils.portfolio_math import (
        annualised_return,
        annualised_volatility,
        max_drawdown,
        portfolio_dividend_yield,
        portfolio_returns,
    )

    TOLERANCE = 1.0  # percent

    ret_series = portfolio_returns(opt_weights, returns_df)

    if constraints_input.min_dividend_yield is not None:
        blended_dy = portfolio_dividend_yield(opt_weights, dividend_yields)
        if blended_dy < constraints_input.min_dividend_yield - TOLERANCE:
            raise ValueError(
                f"Infeasible: Cannot achieve min_dividend_yield of "
                f"{constraints_input.min_dividend_yield}% with the given securities. "
                f"Best achievable: {blended_dy:.2f}%"
            )

    if constraints_input.max_drawdown is not None:
        dd = max_drawdown(ret_series)
        if dd > constraints_input.max_drawdown + TOLERANCE:
            raise ValueError(
                f"Infeasible: Cannot achieve max_drawdown of "
                f"{constraints_input.max_drawdown}%. Best achievable: {dd:.2f}%"
            )

    if constraints_input.max_volatility is not None:
        vol = annualised_volatility(ret_series, periods_per_year)
        if vol > constraints_input.max_volatility + TOLERANCE:
            raise ValueError(
                f"Infeasible: Cannot achieve max_volatility of "
                f"{constraints_input.max_volatility}%. Best achievable: {vol:.2f}%"
            )

    if constraints_input.min_cagr is not None:
        cagr = annualised_return(ret_series, periods_per_year)
        if cagr < constraints_input.min_cagr - TOLERANCE:
            raise ValueError(
                f"Infeasible: Cannot achieve min_cagr of "
                f"{constraints_input.min_cagr}%. Best achievable: {cagr:.2f}%"
            )
