"""
Portfolio math utilities
========================
All functions operate on plain numpy arrays / pandas DataFrames.
Returns are assumed to be in *percent* (e.g. 1.5 means +1.5%).
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd




def build_return_matrix(
    securities: list,  # List[SecurityInput]
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Align all securities to their common date range and return:
    - returns_df : DataFrame with dates as index, tickers as columns (values in %)
    - tickers    : ordered list of ticker symbols
    """
    series_map: Dict[str, pd.Series] = {}
    for sec in securities:
        s = pd.Series(sec.returns, dtype=float)
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
        series_map[sec.ticker] = s

    returns_df = pd.DataFrame(series_map).dropna()
    if returns_df.empty:
        raise ValueError("No overlapping dates found across the provided return series.")

    tickers = list(returns_df.columns)
    return returns_df, tickers


def build_factor_matrix(
    factor_returns: Dict[str, Dict[str, float]],
) -> pd.DataFrame:
    """
    Build a DataFrame of factor returns aligned on dates.
    factor_returns: { factor_name: { date_str: return_pct } }
    """
    series_map: Dict[str, pd.Series] = {}
    for factor_name, date_map in factor_returns.items():
        s = pd.Series(date_map, dtype=float)
        s=s/100
        s.index = pd.to_datetime(s.index)
        series_map[factor_name] = s.sort_index()

    factor_df = pd.DataFrame(series_map).dropna()
    return factor_df


# ---------------------------------------------------------------------------
# Core portfolio statistics
# ---------------------------------------------------------------------------

def portfolio_returns(weights: np.ndarray, returns_df: pd.DataFrame) -> pd.Series:
    """Compute the weighted portfolio return series (in %)."""
    return returns_df.values @ weights  # shape: (T,)


def annualised_return(ret_series: np.ndarray, periods_per_year: int) -> float:
    """
    CAGR from a period return series (values in *fractional* form, e.g., 0.0008).
    """
    if len(ret_series) == 0:
        return 0.0
    growth = np.prod(1 + ret_series)          # no division by 100
    cagr = growth ** (periods_per_year / len(ret_series)) - 1
    return float(cagr)                        # decimal, e.g., 0.0936


def annualised_volatility(ret_series: np.ndarray, periods_per_year: int) -> float:
    """Annualised standard deviation of returns (fractional input)."""
    return float(np.std(ret_series, ddof=1) * np.sqrt(periods_per_year))


def max_drawdown(ret_series: np.ndarray) -> float:
    """
    Maximum peak-to-trough drawdown (returns as a positive decimal, e.g., 0.2549).
    """
    cum = np.cumprod(1 + ret_series)          # fractional wealth index
    running_max = np.maximum.accumulate(cum)
    drawdowns = (cum - running_max) / running_max
    return float(-np.min(drawdowns))          # no *100


def sharpe_ratio(
    ret_series: np.ndarray,
    periods_per_year: int,
    risk_free_rate: float = 0.0,
) -> float:
    """
    Sharpe = (CAGR - Rf) / annualised_vol
    risk_free_rate is in decimal (e.g., 0.02 for 2%).
    """
    cagr = annualised_return(ret_series, periods_per_year)
    vol = annualised_volatility(ret_series, periods_per_year)
    if vol == 0:
        return 0.0
    return float((cagr - risk_free_rate) / vol)

def portfolio_dividend_yield(
    weights: np.ndarray,
    dividend_yields: np.ndarray,
) -> float:
    """Blended dividend yield = weighted average of individual yields (%)."""
    return float(np.dot(weights, dividend_yields))


def compute_portfolio_stats(
    weights: np.ndarray,
    returns_df: pd.DataFrame,
    dividend_yields: np.ndarray,
    periods_per_year: int,
    risk_free_rate: float = 0.0,
) -> dict:
    """Return a dict of key portfolio statistics."""
    ret_series = portfolio_returns(weights, returns_df)
    return {
        "cagr": round(annualised_return(ret_series, periods_per_year), 4),
        "volatility": round(annualised_volatility(ret_series, periods_per_year), 4),
        "sharpe_ratio": round(sharpe_ratio(ret_series, periods_per_year, risk_free_rate), 4),
        "max_drawdown": round(max_drawdown(ret_series), 4),
        "dividend_yield": round(portfolio_dividend_yield(weights, dividend_yields), 4),
    }


# ---------------------------------------------------------------------------
# Covariance helper
# ---------------------------------------------------------------------------

def cov_matrix(returns_df: pd.DataFrame, periods_per_year: int) -> np.ndarray:
    """Annualised covariance matrix from a returns DataFrame (values in %)."""
    return returns_df.cov().values * periods_per_year


def individual_volatilities(returns_df: pd.DataFrame, periods_per_year: int) -> np.ndarray:
    """Annualised per-asset volatility array."""
    return returns_df.std(ddof=1).values * np.sqrt(periods_per_year)
