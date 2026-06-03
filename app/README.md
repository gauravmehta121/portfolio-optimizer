# Portfolio Optimizer API

A clean, well-structured REST API that replicates the core optimization engine of a portfolio optimizer tool.  
Built with **FastAPI** and **scipy** – runs locally in seconds.

---

## Features

| Strategy | Description |
|---|---|
| `equal_weights` | 1/N allocation across all securities |
| `risk_parity` | Equal risk contribution per asset |
| `minimize_drawdown` | Minimises maximum historical drawdown |
| `minimize_volatility` | Global minimum variance portfolio |
| `maximize_sharpe` | Maximum risk-adjusted return |
| `optimize_factor_exposure` | *(Bonus)* Maximise/minimise Value, Momentum, or Size exposure |

**Bonus:** Factor beta regression (OLS) for both current and optimised portfolios.

---

## Quick Start

### 1. Clone & Install

```bash
git clone <your-repo-url>
cd portfolio-optimizer
pip install -r requirements.txt
```

### 2. Run the API

```bash
uvicorn app.main:app --reload
```

The API is now live at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

### 3. Run Tests

```bash
pytest tests/ -v
```

---

## Project Structure

```
portfolio-optimizer/
├── app/
│   ├── main.py               # FastAPI app, routes
│   ├── optimizer.py          # Orchestrator: request → strategy → response
│   ├── models/
│   │   └── schemas.py        # Pydantic request/response models
│   ├── strategies/
│   │   └── strategies.py     # All 6 optimization algorithms
│   └── utils/
│       ├── portfolio_math.py # Returns, volatility, drawdown, CAGR, Sharpe
│       ├── constraints.py    # scipy bounds/constraint builders
│       └── factor_betas.py   # OLS factor beta regression (Bonus)
├── tests/
│   └── test_optimizer.py     # 16 unit tests
├── examples/
│   └── curl_examples.sh      # Ready-to-run curl commands for all 6 test cases
├── requirements.txt
└── README.md
```

---

## API Reference

### `POST /optimize`

**Request body:**

```json
{
  "securities": [
    {
      "ticker": "SPY",
      "security_name": "SPDR S&P 500 ETF Trust",
      "current_weight": 60.0,
      "dividend_yield": 1.30,
      "returns": {
        "2020-01-01": -0.20,
        "2020-02-01": -8.41,
        "2020-03-01": -12.35
      }
    }
  ],
  "strategy": "minimize_volatility",
  "periods_per_year": 12,
  "risk_free_rate": 0.0,
  "constraints": {
    "min_weight": 5.0,
    "max_weight": 40.0,
    "min_dividend_yield": 2.50
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `securities` | array | ✅ | List of securities with return data |
| `strategy` | string | ✅ | One of the 6 strategies above |
| `periods_per_year` | int | ❌ | Default `12` (monthly). Use `252` for daily returns |
| `risk_free_rate` | float | ❌ | Default `0.0` (percent) |
| `constraints` | object | ❌ | Weight and portfolio-level constraints |
| `factor_returns` | object | ⚠️ | Required for `optimize_factor_exposure` |
| `factor_objectives` | array | ⚠️ | Required for `optimize_factor_exposure` |

**Response:**

```json
{
  "optimization_strategy": "minimize_volatility",
  "allocation_changes": [
    {
      "ticker": "SPY",
      "security_name": "SPDR S&P 500 ETF Trust",
      "current_weight": 60.0,
      "optimized_weight": 22.14,
      "change": -37.86
    }
  ],
  "current_portfolio_stats": {
    "cagr": 7.21,
    "volatility": 11.43,
    "sharpe_ratio": 0.63,
    "max_drawdown": 14.22,
    "dividend_yield": 1.30
  },
  "optimized_portfolio_stats": {
    "cagr": 5.88,
    "volatility": 6.71,
    "sharpe_ratio": 0.88,
    "max_drawdown": 8.14,
    "dividend_yield": 2.11
  },
  "factor_betas": null
}
```

### `GET /health`

Returns `{"status": "ok"}`.

---

## Constraints Reference

| Constraint | Type | Description |
|---|---|---|
| `min_weight` | float (%) | Minimum allocation per security |
| `max_weight` | float (%) | Maximum allocation per security |
| `min_cagr` | float (%) | Minimum required CAGR |
| `min_volatility` | float (%) | Minimum allowed annualised volatility |
| `max_volatility` | float (%) | Maximum allowed annualised volatility |
| `max_drawdown` | float (%) | Maximum allowed historical drawdown |
| `min_dividend_yield` | float (%) | Minimum blended portfolio dividend yield |

If a constraint is infeasible (e.g. you demand 5% dividend yield from zero-yield funds), the API returns a `422` with a descriptive error message.

---

## Test Cases

The required 6 test scenarios from the assignment are in `examples/curl_examples.sh`.  
Run them after starting the API:

```bash
bash examples/curl_examples.sh
```

---

## Design Decisions & Trade-offs

### Why scipy SLSQP?
SLSQP (Sequential Least Squares Programming) handles both equality and inequality constraints natively and is battle-tested for convex portfolio problems. It's fast enough for 5–20 assets with 60+ months of data.

### Sharpe: Analytical vs Numerical
For unconstrained Maximize Sharpe, the code uses the closed-form tangency portfolio (inverse covariance times excess returns), clipped to remove short positions. When constraints are present, it falls back to SLSQP.

### Risk Parity
Implemented via the risk contribution formulation: minimise sum of squared deviations from the equal-risk-contribution target. More numerically stable than iterative approaches.

### Factor Exposure (Bonus)
Rather than re-running a portfolio-level OLS regression inside the optimiser (which would be slow and non-differentiable), we pre-compute per-asset factor betas and use the linearity of the OLS estimator: `portfolio_beta = w' × asset_betas`. This makes the objective differentiable and SLSQP converges reliably.

Factor betas for the response are computed via a separate full OLS regression of the portfolio return series on factors, using the common date range.

### Periods Per Year
Defaults to 12 (monthly). Set `periods_per_year: 252` for daily return data. This affects all annualised statistics: CAGR, volatility, and Sharpe.

---

## Validation

The API validates:
- `current_weight` values sum to 100% (±0.1% tolerance)
- `min_weight ≤ max_weight` and `min_volatility ≤ max_volatility`
- Factor strategy requires `factor_returns` and `factor_objectives`
- Post-optimisation: if constraints cannot be satisfied, returns `422` with clear message
- Optimised weights always sum to 100% and are non-negative
