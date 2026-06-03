"""
Request / Response schemas
==========================
All inputs and outputs are fully typed so FastAPI auto-generates OpenAPI docs
and performs validation before the optimisation logic ever runs.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Strategy(str, Enum):
    equal_weights = "equal_weights"
    risk_parity = "risk_parity"
    minimize_drawdown = "minimize_drawdown"
    minimize_volatility = "minimize_volatility"
    maximize_sharpe = "maximize_sharpe"
    optimize_factor_exposure = "optimize_factor_exposure"


class FactorDirection(str, Enum):
    maximize = "maximize"
    minimize = "minimize"


class Factor(str, Enum):
    momentum = "momentum"
    value = "value"
    size = "size"


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------

class SecurityInput(BaseModel):
    """One fund's metadata and its dated return series."""

    ticker: str = Field(..., description="Fund ticker symbol, e.g. 'SPY'")
    security_name: str = Field(..., description="Human-readable fund name")
    current_weight: float = Field(
        ..., ge=0, le=100, description="Current allocation in percent (0-100)"
    )
    dividend_yield: float = Field(
        default=0.0, ge=0, description="Trailing dividend yield in percent"
    )
    # date → daily/monthly return in percent
    returns: Dict[str, float] = Field(
        ..., description="Map of ISO date strings to period returns (in percent)"
    )


class WeightConstraints(BaseModel):
    """Per-security and portfolio-level constraints (all values in percent)."""

    min_weight: Optional[float] = Field(
        None, ge=0, le=100, description="Minimum allocation per security (%)"
    )
    max_weight: Optional[float] = Field(
        None, ge=0, le=100, description="Maximum allocation per security (%)"
    )
    min_cagr: Optional[float] = Field(
        None, description="Minimum required CAGR for the optimized portfolio (%)"
    )
    min_volatility: Optional[float] = Field(
        None, ge=0, description="Minimum allowed annualised volatility (%)"
    )
    max_volatility: Optional[float] = Field(
        None, ge=0, description="Maximum allowed annualised volatility (%)"
    )
    max_drawdown: Optional[float] = Field(
        None, ge=0, le=100, description="Maximum allowed historical drawdown (%)"
    )
    min_dividend_yield: Optional[float] = Field(
        None, ge=0, description="Minimum blended dividend yield for the portfolio (%)"
    )

    @model_validator(mode="after")
    def _validate_vol_range(self):
        if (
            self.min_volatility is not None
            and self.max_volatility is not None
            and self.min_volatility > self.max_volatility
        ):
            raise ValueError("min_volatility must be <= max_volatility")
        if (
            self.min_weight is not None
            and self.max_weight is not None
            and self.min_weight > self.max_weight
        ):
            raise ValueError("min_weight must be <= max_weight")
        return self


class FactorObjective(BaseModel):
    """Which factor(s) to optimise and in which direction."""

    factor: Factor
    direction: FactorDirection = FactorDirection.maximize


class OptimizationRequest(BaseModel):
    """Top-level request body."""

    securities: List[SecurityInput] = Field(
        ..., min_length=1, description="At least one security required"
    )
    strategy: Strategy
    constraints: Optional[WeightConstraints] = None
    # Required only when strategy == optimize_factor_exposure
    factor_returns: Optional[Dict[str, Dict[str, float]]] = Field(
        None,
        description=(
            "Factor return series keyed by factor name then date. "
            "Required for optimize_factor_exposure strategy."
        ),
    )
    factor_objectives: Optional[List[FactorObjective]] = Field(
        None,
        description="Which factor(s) to maximise/minimise. Used with optimize_factor_exposure.",
    )
    risk_free_rate: float = Field(
        default=0.0,
        ge=0,
        description="Annual risk-free rate in percent used for Sharpe calculation",
    )
    # How many periods per year (12 for monthly, 252 for daily)
    periods_per_year: int = Field(
        default=12,
        gt=0,
        description="Number of return periods per year for annualisation (12=monthly, 252=daily)",
    )

    @model_validator(mode="after")
    def _validate_weights_sum(self):
        total = sum(s.current_weight for s in self.securities)
        if abs(total - 100.0) > 0.1:
            raise ValueError(
                f"current_weight values must sum to 100 (got {total:.4f})"
            )
        return self

    @model_validator(mode="after")
    def _validate_factor_strategy(self):
        if self.strategy == Strategy.optimize_factor_exposure:
            if not self.factor_returns:
                raise ValueError(
                    "factor_returns is required for the optimize_factor_exposure strategy"
                )
            if not self.factor_objectives:
                raise ValueError(
                    "factor_objectives is required for the optimize_factor_exposure strategy"
                )
        return self


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

class AllocationChange(BaseModel):
    ticker: str
    security_name: str
    current_weight: float
    optimized_weight: float
    change: float


class PortfolioStats(BaseModel):
    cagr: Optional[float] = None
    volatility: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    dividend_yield: Optional[float] = None


class FactorBetas(BaseModel):
    value: Optional[float] = None
    momentum: Optional[float] = None
    size: Optional[float] = None


class FactorBetaResult(BaseModel):
    current_portfolio: FactorBetas
    optimized_portfolio: FactorBetas


class OptimizationResponse(BaseModel):
    optimization_strategy: str
    allocation_changes: List[AllocationChange]
    # Portfolio-level statistics (informational)
    current_portfolio_stats: Optional[PortfolioStats] = None
    optimized_portfolio_stats: Optional[PortfolioStats] = None
    # Bonus: factor betas
    factor_betas: Optional[FactorBetaResult] = None
