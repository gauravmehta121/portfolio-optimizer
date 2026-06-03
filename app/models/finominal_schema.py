"""
Finominal API Schema Adapter
============================
Accepts the exact payload format sent by the Finominal frontend tool and
returns a response that mirrors their API's output structure.

Request:  POST /optimize/finominal  (Finominal format)
Response: matches https://finominal.com/api/tools/portfolio-optimizer/optimize

Strategy name mapping (Finominal → internal):
  equal_weighted          → equal_weights
  risk_parity             → risk_parity
  minimize_volatility     → minimize_volatility
  minimize_drawdown       → minimize_drawdown
  maximize_sharpe_ratio   → maximize_sharpe
  optimize_factor_exposure→ optimize_factor_exposure
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

from app.models.schemas import (
    OptimizationRequest,
    SecurityInput,
    Strategy,
    WeightConstraints,
)


# ---------------------------------------------------------------------------
# Finominal request schema  (mirrors the frontend's exact payload)
# ---------------------------------------------------------------------------

class FinominalHolding(BaseModel):
    ticker: str
    companyName: str
    percentage: float          # decimal 0-1
    minWeight: float = 0.0     # decimal 0-1
    maxWeight: float = 1.0     # decimal 0-1
    dividendYield: float = 0.0 # decimal 0-1 (may not always be present)


class FinominalConstraints(BaseModel):
    min_cagr: Optional[float] = None
    min_volatility: Optional[float] = None
    max_volatility: Optional[float] = None
    max_drawdown: Optional[float] = None
    min_dividend_yield: Optional[float] = None  # decimal 0-1


class FinominalRequest(BaseModel):
    holdings: List[FinominalHolding]
    countryCode: str = "US"
    optimization_objective: str = "equal_weighted"
    rebalance_frequency: str = "Y"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    risk_free_rate: float = 0.0
    # Optional portfolio-level constraints in Finominal's format
    constraints: Optional[FinominalConstraints] = None
    # Factor exposure bonus
    factor_returns: Optional[Dict[str, Dict[str, float]]] = None
    factor_objectives: Optional[List[Dict[str, str]]] = None


# ---------------------------------------------------------------------------
# Strategy name normalisation
# ---------------------------------------------------------------------------

STRATEGY_MAP: Dict[str, Strategy] = {
    "equal_weighted":           Strategy.equal_weights,
    "equal_weights":            Strategy.equal_weights,
    "risk_parity":              Strategy.risk_parity,
    "minimize_volatility":      Strategy.minimize_volatility,
    "min_volatility":           Strategy.minimize_volatility,
    "minimize_drawdown":        Strategy.minimize_drawdown,
    "min_drawdown":             Strategy.minimize_drawdown,
    "maximize_sharpe_ratio":    Strategy.maximize_sharpe,
    "maximize_sharpe":          Strategy.maximize_sharpe,
    "max_sharpe":               Strategy.maximize_sharpe,
    "optimize_factor_exposure": Strategy.optimize_factor_exposure,
    "factor_exposure":          Strategy.optimize_factor_exposure,
}


def _map_strategy(objective: str) -> Strategy:
    key = objective.lower().strip()
    if key not in STRATEGY_MAP:
        valid = list(STRATEGY_MAP.keys())
        raise ValueError(
            f"Unknown optimization_objective '{objective}'. "
            f"Valid values: {valid}"
        )
    return STRATEGY_MAP[key]


# ---------------------------------------------------------------------------
# Translator: FinominalRequest → OptimizationRequest
# ---------------------------------------------------------------------------

def translate_finominal_request(
    req: FinominalRequest,
    returns_map: Dict[str, Dict[str, float]],   # ticker → {date: return%}
    security_meta: Dict[str, Dict[str, Any]],   # ticker → {security_name, dividend_yield%}
) -> OptimizationRequest:
    """
    Convert a Finominal-format request into the internal OptimizationRequest.

    Parameters
    ----------
    req           : parsed FinominalRequest
    returns_map   : historical returns per ticker (must be provided externally,
                    e.g. loaded from the Excel file).
                    Format: { "SPY": {"2020-01-01": -0.2, ...}, ... }
    security_meta : optional extra metadata (security_name, dividend_yield in %)
                    Format: { "SPY": {"security_name": "SPDR S&P 500", "dividend_yield": 1.3} }
    """
    securities = []
    for h in req.holdings:
        meta = security_meta.get(h.ticker, {})
        securities.append(SecurityInput(
            ticker=h.ticker,
            security_name=meta.get("security_name", h.companyName),
            # percentage is 0-1 decimal → convert to 0-100
            current_weight=round(h.percentage * 100, 6),
            # dividend_yield: prefer metadata (in %), fall back to holding field (×100)
            dividend_yield=meta.get("dividend_yield", h.dividendYield * 100),
            returns=returns_map.get(h.ticker, {}),
        ))

    # Build per-security weight bounds from the holdings
    # If all holdings share the same min/max, use global constraints
    min_weights = [h.minWeight * 100 for h in req.holdings]
    max_weights = [h.maxWeight * 100 for h in req.holdings]
    global_min = min(min_weights) if min_weights else None
    global_max = max(max_weights) if max_weights else None

    # Build WeightConstraints
    wc_kwargs: Dict[str, Any] = {}
    if global_min is not None and global_min > 0:
        wc_kwargs["min_weight"] = global_min
    if global_max is not None and global_max < 100:
        wc_kwargs["max_weight"] = global_max

    # Merge in any portfolio-level constraints
    if req.constraints:
        fc = req.constraints
        if fc.min_cagr is not None:
            wc_kwargs["min_cagr"] = fc.min_cagr * 100  # decimal → %
        if fc.min_volatility is not None:
            wc_kwargs["min_volatility"] = fc.min_volatility * 100
        if fc.max_volatility is not None:
            wc_kwargs["max_volatility"] = fc.max_volatility * 100
        if fc.max_drawdown is not None:
            wc_kwargs["max_drawdown"] = abs(fc.max_drawdown) * 100
        if fc.min_dividend_yield is not None:
            wc_kwargs["min_dividend_yield"] = fc.min_dividend_yield * 100

    constraints = WeightConstraints(**wc_kwargs) if wc_kwargs else None

    # Factor objectives
    from app.models.schemas import FactorObjective, Factor, FactorDirection
    factor_objectives = None
    if req.factor_objectives:
        factor_objectives = [
            FactorObjective(
                factor=Factor(fo["factor"].lower()),
                direction=FactorDirection(fo.get("direction", "maximize").lower()),
            )
            for fo in req.factor_objectives
        ]

    return OptimizationRequest(
        securities=securities,
        strategy=_map_strategy(req.optimization_objective),
        constraints=constraints,
        factor_returns=req.factor_returns,
        factor_objectives=factor_objectives,
        risk_free_rate=req.risk_free_rate,
        periods_per_year=12,
    )


# ---------------------------------------------------------------------------
# Finominal response schema  (mirrors their actual API output)
# ---------------------------------------------------------------------------

class FinominalOptimizedHolding(BaseModel):
    ticker: str
    name: str
    optimizedWeight: float    # decimal 0-1
    currentWeight: float      # decimal 0-1
    change: float             # decimal


class FinominalMetricValue(BaseModel):
    initial: Optional[float] = None
    optimized: Optional[float] = None
    change: Optional[float] = None
    benchmark: Optional[float] = None


class FinominalFactorBetas(BaseModel):
    equityQuality: Optional[FinominalMetricValue] = None
    equityMomentum: Optional[FinominalMetricValue] = None
    equitySize: Optional[FinominalMetricValue] = None
    equityValue: Optional[FinominalMetricValue] = None
    equityVolatility: Optional[FinominalMetricValue] = None


class FinominalOptimizationResults(BaseModel):
    cagr: Optional[FinominalMetricValue] = None
    volatility: Optional[FinominalMetricValue] = None
    sharpeRatio: Optional[FinominalMetricValue] = None
    maxDrawdown: Optional[FinominalMetricValue] = None
    dividendYield: Optional[FinominalMetricValue] = None
    totalReturn: Optional[FinominalMetricValue] = None
    expectedReturn: Optional[FinominalMetricValue] = None
    fees: Optional[FinominalMetricValue] = None
    trackingError: Optional[FinominalMetricValue] = None


class FinominalMetrics(BaseModel):
    factorBetas: Optional[FinominalFactorBetas] = None
    optimizationResults: Optional[FinominalOptimizationResults] = None


class FinominalResponseData(BaseModel):
    lookbackYears: Optional[float] = None
    optimizedPortfolio: List[FinominalOptimizedHolding]
    metrics: Optional[FinominalMetrics] = None


class FinominalResponse(BaseModel):
    success: bool = True
    data: FinominalResponseData


# ---------------------------------------------------------------------------
# Translator: OptimizationResponse → FinominalResponse
# ---------------------------------------------------------------------------

def translate_to_finominal_response(
    internal_response,   # OptimizationResponse
    lookback_years: Optional[float] = None,
) -> FinominalResponse:
    """
    Convert the internal OptimizationResponse into the Finominal response format.
    Weights are converted from percent (0-100) back to decimal (0-1).
    """
    portfolio = []
    for ac in internal_response.allocation_changes:
        portfolio.append(FinominalOptimizedHolding(
            ticker=ac.ticker,
            name=ac.security_name,
            optimizedWeight=round(ac.optimized_weight / 100, 6),
            currentWeight=round(ac.current_weight / 100, 6),
            change=round(ac.change / 100, 6),
        ))

    # Build optimizationResults from portfolio stats
    opt_results = None
    curr = internal_response.current_portfolio_stats
    opt  = internal_response.optimized_portfolio_stats
    if curr and opt:
        def _mv(i, o):
            i_val = i if i is not None else None          # <-- remove /100
            o_val = o if o is not None else None          # <-- remove /100
            chg   = round(o_val - i_val, 6) if (i_val is not None and o_val is not None) else None
            return FinominalMetricValue(initial=i_val, optimized=o_val, change=chg)

        opt_results = FinominalOptimizationResults(
            cagr=_mv(curr.cagr, opt.cagr),
            volatility=_mv(curr.volatility, opt.volatility),
            sharpeRatio=FinominalMetricValue(
                initial=curr.sharpe_ratio,
                optimized=opt.sharpe_ratio,
                change=round((opt.sharpe_ratio or 0) - (curr.sharpe_ratio or 0), 6)
            ),
            maxDrawdown=_mv(
                -(curr.max_drawdown or 0),   # store as negative like Finominal
                -(opt.max_drawdown or 0),
            ),
            dividendYield=_mv(curr.dividend_yield, opt.dividend_yield),
        )

    # Factor betas
    factor_betas = None
    if internal_response.factor_betas:
        fb = internal_response.factor_betas

        def _fb(initial, optimized):
            chg = round((optimized or 0) - (initial or 0), 6) if (initial is not None and optimized is not None) else None
            return FinominalMetricValue(initial=initial, optimized=optimized, change=chg)

        factor_betas = FinominalFactorBetas(
            equityMomentum=_fb(
                fb.current_portfolio.momentum,
                fb.optimized_portfolio.momentum,
            ),
            equityValue=_fb(
                fb.current_portfolio.value,
                fb.optimized_portfolio.value,
            ),
            equitySize=_fb(
                fb.current_portfolio.size,
                fb.optimized_portfolio.size,
            ),
        )

    metrics = FinominalMetrics(
        factorBetas=factor_betas,
        optimizationResults=opt_results,
    )

    return FinominalResponse(
        success=True,
        data=FinominalResponseData(
            lookbackYears=lookback_years,
            optimizedPortfolio=portfolio,
            metrics=metrics,
        )
    )