"""
Factor Beta Regression
======================
Compute OLS factor betas for a portfolio return series against a set of
factor return series using the common date range.

Model:
    portfolio_return = alpha + beta_1 * Momentum + beta_2 * Value + beta_3 * Size + ε
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd


def compute_factor_betas(
    portfolio_returns: pd.Series,
    factor_df: pd.DataFrame,
) -> Dict[str, Optional[float]]:
    """
    Run OLS regression of portfolio_returns on factor_df columns.

    Parameters
    ----------
    portfolio_returns : pd.Series (indexed by date, values in %)
    factor_df         : pd.DataFrame (indexed by date, columns = factor names, values in %)

    Returns
    -------
    dict mapping factor name → beta coefficient (float, 4 d.p.)
    Returns None for any factor that caused a numerical error.
    """
    common_idx = portfolio_returns.index.intersection(factor_df.index)
    if len(common_idx) < 5:
        return {col: None for col in factor_df.columns}

    y = portfolio_returns.loc[common_idx].values.astype(float)
    X_raw = factor_df.loc[common_idx].values.astype(float)
    # Add intercept (alpha)
    X = np.column_stack([np.ones(len(y)), X_raw])

    try:
        coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        betas = coeffs[1:]  # skip alpha
    except np.linalg.LinAlgError:
        return {col: None for col in factor_df.columns}

    return {
        col: round(float(betas[i]), 4)
        for i, col in enumerate(factor_df.columns)
    }
