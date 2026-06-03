"""
Portfolio Optimizer API
=======================
Two endpoint families:

  POST /optimize              — internal format (full return data in request body)
  POST /optimize/finominal    — Finominal frontend format (fetches its own return data)
"""

from fastapi import FastAPI, HTTPException
from app.utils.data_loader import load_factor_returns

from fastapi.middleware.cors import CORSMiddleware

from app.models.schemas import OptimizationRequest, OptimizationResponse
from app.models.finominal_schema import (
    FinominalRequest,
    FinominalResponse,
    translate_finominal_request,
    translate_to_finominal_response,
)
from app.optimizer import run_optimization



app = FastAPI(
    title="Portfolio Optimizer API",
    description=(
        "REST API for portfolio weight optimization.\n\n"
        "- `/optimize` — internal format, return data provided in the request.\n"
        "- `/optimize/finominal` — Finominal frontend format, return data fetched automatically."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Primary endpoint — internal format
# ---------------------------------------------------------------------------

@app.post("/optimize", response_model=OptimizationResponse)
def optimize(request: OptimizationRequest):
    """
    Optimize portfolio weights.  Return data must be included in the request body.
    """
    try:
        return run_optimization(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(exc)}")


# ---------------------------------------------------------------------------
# Finominal-compatible endpoint
# ---------------------------------------------------------------------------

@app.post("/optimize/finominal", response_model=FinominalResponse)
def optimize_finominal(request: FinominalRequest):
    """
    Accepts the exact payload sent by the Finominal portfolio optimizer frontend.

    - Tickers and weights come from `holdings[]`
    - Historical returns are fetched automatically via yfinance
    - Dividend yields are fetched automatically via yfinance
    - Response mirrors the Finominal API output format exactly

    Example payload (copy-paste from the tool's Network tab):
    {
      "holdings": [
        {"ticker": "SPY", "companyName": "SPDR S&P 500", "percentage": 0.6,
         "minWeight": 0, "maxWeight": 1},
        {"ticker": "AGG", "companyName": "iShares AGG", "percentage": 0.4,
         "minWeight": 0, "maxWeight": 1}
      ],
      "countryCode": "US",
      "optimization_objective": "minimize_volatility",
      "rebalance_frequency": "Y",
      "start_date": "2012-10-23",
      "end_date": "2026-05-29"
    }
    """
    try:
        tickers = [h.ticker for h in request.holdings]

        # --- 1. Fetch historical returns ---
        from app.utils.data_loader import load_returns, load_dividend_yields
        returns_map, lookback_years = load_returns(
            tickers=tickers,
            start_date=request.start_date,
            end_date=request.end_date,
            frequency="M",
        )

        # --- 2. Fetch dividend yields ---
        div_yields = load_dividend_yields(tickers)
        security_meta = {
            ticker: {
                "security_name": next(
                    (h.companyName for h in request.holdings if h.ticker == ticker), ticker
                ),
                "dividend_yield": div_yields.get(ticker, 0.0),
            }
            for ticker in tickers
        }
        if request.optimization_objective == "optimize_factor_exposure":
            from app.utils.data_loader import load_factor_returns
            factor_df = load_factor_returns()
            factor_returns_dict = {col: factor_df[col].to_dict() for col in factor_df.columns}

        # --- 3. Translate to internal request format ---
        internal_request = translate_finominal_request(
            req=request,
            returns_map=returns_map,
            security_meta=security_meta,
        )

        # --- 4. Run optimization ---
        internal_response = run_optimization(internal_request)

        # --- 5. Translate back to Finominal response format ---
        return translate_to_finominal_response(internal_response, lookback_years)

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(exc)}")
    




#     text
# Client Request → /optimize/finominal
#        ↓
# Data Loader (Excel → fractional returns, dividends, factors)
#        ↓
# Translate to Internal Request (OptimizationRequest)
#        ↓
# run_optimization()
#   ├─ Build return matrix & bounds/constraints
#   ├─ Dispatch to strategy (scipy.optimize)
#   └─ Compute stats & factor betas
#        ↓
# Translate to Finominal Response
#        ↓
# JSON Response (allocation changes + metrics + factorBetas)