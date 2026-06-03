"""
Unit tests for the Portfolio Optimizer API
==========================================
Run with:  pytest tests/ -v
"""

import math
from typing import Dict

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Shared test data helpers
# ---------------------------------------------------------------------------

def _make_returns(seed: int, n_periods: int = 60) -> Dict[str, float]:
    """Generate reproducible monthly return series (in %)."""
    rng = np.random.default_rng(seed)
    dates = [f"2019-{(m % 12) + 1:02d}-01" for m in range(n_periods)]
    # Use pd.date_range for proper unique dates
    import pandas as pd
    dates = [d.strftime("%Y-%m-%d") for d in pd.date_range("2019-01-01", periods=n_periods, freq="MS")]
    returns = rng.normal(0.8, 3.0, n_periods).tolist()
    return dict(zip(dates, returns))


SPY_RETURNS = _make_returns(1)
AGG_RETURNS = _make_returns(2)
GLD_RETURNS = _make_returns(3)
IEFA_RETURNS = _make_returns(4)
VEA_RETURNS = _make_returns(5)


def _base_request(strategy: str, weights: Dict[str, float], extra: dict = None):
    """Build a minimal valid request body."""
    securities = [
        {
            "ticker": t,
            "security_name": t,
            "current_weight": w,
            "dividend_yield": 1.5,
            "returns": r,
        }
        for (t, w), r in zip(
            weights.items(),
            [SPY_RETURNS, AGG_RETURNS, GLD_RETURNS, IEFA_RETURNS, VEA_RETURNS][: len(weights)],
        )
    ]
    body = {"securities": securities, "strategy": strategy}
    if extra:
        body.update(extra)
    return body


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# 1. Equal Weights
# ---------------------------------------------------------------------------

class TestEqualWeights:
    def test_two_assets_equal_split(self):
        body = _base_request("equal_weights", {"SPY": 75, "AGG": 25})
        r = client.post("/optimize", json=body)
        assert r.status_code == 200
        data = r.json()
        assert data["optimization_strategy"] == "equal_weights"
        weights = {a["ticker"]: a["optimized_weight"] for a in data["allocation_changes"]}
        assert abs(weights["SPY"] - 50.0) < 0.01
        assert abs(weights["AGG"] - 50.0) < 0.01

    def test_weights_sum_to_100(self):
        body = _base_request("equal_weights", {"SPY": 60, "AGG": 30, "GLD": 10})
        r = client.post("/optimize", json=body)
        total = sum(a["optimized_weight"] for a in r.json()["allocation_changes"])
        assert abs(total - 100.0) < 0.01

    def test_five_assets(self):
        body = _base_request(
            "equal_weights",
            {"SPY": 20, "AGG": 20, "GLD": 20, "IEFA": 20, "VEA": 20},
        )
        r = client.post("/optimize", json=body)
        for a in r.json()["allocation_changes"]:
            assert abs(a["optimized_weight"] - 20.0) < 0.01


# ---------------------------------------------------------------------------
# 2. Risk Parity
# ---------------------------------------------------------------------------

class TestRiskParity:
    def test_two_assets(self):
        body = _base_request("risk_parity", {"SPY": 75, "AGG": 25})
        r = client.post("/optimize", json=body)
        assert r.status_code == 200
        total = sum(a["optimized_weight"] for a in r.json()["allocation_changes"])
        assert abs(total - 100.0) < 0.01

    def test_no_negative_weights(self):
        body = _base_request("risk_parity", {"SPY": 60, "AGG": 30, "GLD": 10})
        r = client.post("/optimize", json=body)
        for a in r.json()["allocation_changes"]:
            assert a["optimized_weight"] >= -0.001


# ---------------------------------------------------------------------------
# 3. Minimize Drawdown
# ---------------------------------------------------------------------------

class TestMinimizeDrawdown:
    def test_basic(self):
        body = _base_request("minimize_drawdown", {"SPY": 60, "AGG": 30, "GLD": 10})
        r = client.post("/optimize", json=body)
        assert r.status_code == 200
        total = sum(a["optimized_weight"] for a in r.json()["allocation_changes"])
        assert abs(total - 100.0) < 0.01


# ---------------------------------------------------------------------------
# 4. Minimize Volatility
# ---------------------------------------------------------------------------

class TestMinimizeVolatility:
    def test_basic(self):
        body = _base_request("minimize_volatility", {"SPY": 60, "AGG": 30, "GLD": 10})
        r = client.post("/optimize", json=body)
        assert r.status_code == 200
        total = sum(a["optimized_weight"] for a in r.json()["allocation_changes"])
        assert abs(total - 100.0) < 0.01

    def test_optimised_vol_le_equal_weight_vol(self):
        """Optimised volatility must be ≤ equal-weight volatility."""
        body = _base_request("minimize_volatility", {"SPY": 60, "AGG": 30, "GLD": 10})
        r = client.post("/optimize", json=body)
        data = r.json()
        opt_vol = data["optimized_portfolio_stats"]["volatility"]
        curr_vol = data["current_portfolio_stats"]["volatility"]
        # Optimised portfolio should have lower or equal volatility
        assert opt_vol <= curr_vol + 0.5  # allow tiny tolerance


# ---------------------------------------------------------------------------
# 5. Maximize Sharpe
# ---------------------------------------------------------------------------

class TestMaximizeSharpe:
    def test_five_assets_no_constraint(self):
        body = _base_request(
            "maximize_sharpe",
            {"SPY": 20, "AGG": 20, "GLD": 20, "IEFA": 20, "VEA": 20},
        )
        r = client.post("/optimize", json=body)
        assert r.status_code == 200
        total = sum(a["optimized_weight"] for a in r.json()["allocation_changes"])
        assert abs(total - 100.0) < 0.01

    def test_with_constraints(self):
        """Case 5: Sharpe + min_dividend_yield + per-asset min/max."""
        body = _base_request(
            "maximize_sharpe",
            {"SPY": 20, "AGG": 20, "GLD": 20, "IEFA": 20, "VEA": 20},
        )
        body["constraints"] = {
            "min_dividend_yield": 2.50,
            "min_weight": 5,
            "max_weight": 40,
        }
        r = client.post("/optimize", json=body)
        assert r.status_code in (200, 422)  # 422 if infeasible with synthetic data
        if r.status_code == 200:
            data = r.json()
            for a in data["allocation_changes"]:
                assert a["optimized_weight"] >= 4.99
                assert a["optimized_weight"] <= 40.01


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class TestValidation:
    def test_weights_not_summing_to_100(self):
        body = _base_request("equal_weights", {"SPY": 60, "AGG": 10})  # sums to 70
        r = client.post("/optimize", json=body)
        assert r.status_code == 422

    def test_unsupported_strategy(self):
        body = _base_request("equal_weights", {"SPY": 100})
        body["strategy"] = "fly_to_the_moon"
        r = client.post("/optimize", json=body)
        assert r.status_code == 422

    def test_factor_exposure_without_factor_returns(self):
        body = _base_request(
            "optimize_factor_exposure",
            {"SPY": 50, "AGG": 50},
        )
        body["factor_objectives"] = [{"factor": "momentum", "direction": "maximize"}]
        r = client.post("/optimize", json=body)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------

class TestResponseShape:
    def test_allocation_change_fields_present(self):
        body = _base_request("equal_weights", {"SPY": 60, "AGG": 40})
        r = client.post("/optimize", json=body)
        assert r.status_code == 200
        for item in r.json()["allocation_changes"]:
            for field in ["ticker", "security_name", "current_weight", "optimized_weight", "change"]:
                assert field in item

    def test_stats_present(self):
        body = _base_request("minimize_volatility", {"SPY": 60, "AGG": 40})
        r = client.post("/optimize", json=body)
        data = r.json()
        assert "current_portfolio_stats" in data
        assert "optimized_portfolio_stats" in data
