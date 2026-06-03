#!/usr/bin/env bash
# =============================================================================
# Portfolio Optimizer API – curl examples for all 6 required test cases
# Start the server first: uvicorn app.main:app --reload
# =============================================================================

BASE="http://localhost:8000"

# NOTE: Replace the return data in each request below with the actual historical
# returns from the provided Excel file. The structure shown here is correct;
# the date → return_pct mapping should use real data for accurate results.
#
# To generate real requests, load your Excel data and build the JSON using:
#   python examples/build_request.py  (see below)

echo ""
echo "======================================================================"
echo "Case 1: Equal Weights – IEFA 25%, SPY 75%"
echo "======================================================================"
curl -s -X POST "$BASE/optimize" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "equal_weights",
    "periods_per_year": 12,
    "securities": [
      {
        "ticker": "IEFA",
        "security_name": "iShares Core MSCI EAFE ETF",
        "current_weight": 25.0,
        "dividend_yield": 3.10,
        "returns": {"2020-01-01": -2.1, "2020-02-01": -8.3, "2020-03-01": -14.0,
                    "2020-04-01": 6.4, "2020-05-01": 2.1, "2020-06-01": 2.8}
      },
      {
        "ticker": "SPY",
        "security_name": "SPDR S&P 500 ETF Trust",
        "current_weight": 75.0,
        "dividend_yield": 1.30,
        "returns": {"2020-01-01": -0.2, "2020-02-01": -8.4, "2020-03-01": -12.4,
                    "2020-04-01": 12.7, "2020-05-01": 4.8, "2020-06-01": 1.8}
      }
    ]
  }' | python3 -m json.tool

echo ""
echo "======================================================================"
echo "Case 2: Risk Parity – VEA 25%, AGG 75%"
echo "======================================================================"
curl -s -X POST "$BASE/optimize" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "risk_parity",
    "periods_per_year": 12,
    "securities": [
      {
        "ticker": "VEA",
        "security_name": "Vanguard FTSE Developed Markets ETF",
        "current_weight": 25.0,
        "dividend_yield": 3.40,
        "returns": {"2020-01-01": -2.3, "2020-02-01": -8.8, "2020-03-01": -14.5,
                    "2020-04-01": 6.1, "2020-05-01": 2.0, "2020-06-01": 2.5}
      },
      {
        "ticker": "AGG",
        "security_name": "iShares Core US Aggregate Bond ETF",
        "current_weight": 75.0,
        "dividend_yield": 2.70,
        "returns": {"2020-01-01": 1.8, "2020-02-01": 1.7, "2020-03-01": 0.6,
                    "2020-04-01": 1.8, "2020-05-01": 0.4, "2020-06-01": 0.6}
      }
    ]
  }' | python3 -m json.tool

echo ""
echo "======================================================================"
echo "Case 3: Minimize Volatility – SPY 60%, AGG 30%, GLD 10%"
echo "======================================================================"
curl -s -X POST "$BASE/optimize" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "minimize_volatility",
    "periods_per_year": 12,
    "securities": [
      {
        "ticker": "SPY",
        "security_name": "SPDR S&P 500 ETF Trust",
        "current_weight": 60.0,
        "dividend_yield": 1.30,
        "returns": {"2020-01-01": -0.2, "2020-02-01": -8.4, "2020-03-01": -12.4,
                    "2020-04-01": 12.7, "2020-05-01": 4.8, "2020-06-01": 1.8}
      },
      {
        "ticker": "AGG",
        "security_name": "iShares Core US Aggregate Bond ETF",
        "current_weight": 30.0,
        "dividend_yield": 2.70,
        "returns": {"2020-01-01": 1.8, "2020-02-01": 1.7, "2020-03-01": 0.6,
                    "2020-04-01": 1.8, "2020-05-01": 0.4, "2020-06-01": 0.6}
      },
      {
        "ticker": "GLD",
        "security_name": "SPDR Gold Shares",
        "current_weight": 10.0,
        "dividend_yield": 0.0,
        "returns": {"2020-01-01": 4.7, "2020-02-01": 0.5, "2020-03-01": -1.0,
                    "2020-04-01": 6.9, "2020-05-01": 2.8, "2020-06-01": 2.9}
      }
    ]
  }' | python3 -m json.tool

echo ""
echo "======================================================================"
echo "Case 4: Maximize Sharpe – 5 equal-weight assets, no constraints"
echo "======================================================================"
curl -s -X POST "$BASE/optimize" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "maximize_sharpe",
    "periods_per_year": 12,
    "securities": [
      {"ticker":"IEFA","security_name":"iShares Core MSCI EAFE ETF","current_weight":20.0,"dividend_yield":3.10,
       "returns":{"2020-01-01":-2.1,"2020-02-01":-8.3,"2020-03-01":-14.0,"2020-04-01":6.4,"2020-05-01":2.1,"2020-06-01":2.8}},
      {"ticker":"GLD","security_name":"SPDR Gold Shares","current_weight":20.0,"dividend_yield":0.0,
       "returns":{"2020-01-01":4.7,"2020-02-01":0.5,"2020-03-01":-1.0,"2020-04-01":6.9,"2020-05-01":2.8,"2020-06-01":2.9}},
      {"ticker":"AGG","security_name":"iShares Core US Aggregate Bond ETF","current_weight":20.0,"dividend_yield":2.70,
       "returns":{"2020-01-01":1.8,"2020-02-01":1.7,"2020-03-01":0.6,"2020-04-01":1.8,"2020-05-01":0.4,"2020-06-01":0.6}},
      {"ticker":"VEA","security_name":"Vanguard FTSE Developed Markets ETF","current_weight":20.0,"dividend_yield":3.40,
       "returns":{"2020-01-01":-2.3,"2020-02-01":-8.8,"2020-03-01":-14.5,"2020-04-01":6.1,"2020-05-01":2.0,"2020-06-01":2.5}},
      {"ticker":"SPY","security_name":"SPDR S&P 500 ETF Trust","current_weight":20.0,"dividend_yield":1.30,
       "returns":{"2020-01-01":-0.2,"2020-02-01":-8.4,"2020-03-01":-12.4,"2020-04-01":12.7,"2020-05-01":4.8,"2020-06-01":1.8}}
    ]
  }' | python3 -m json.tool

echo ""
echo "======================================================================"
echo "Case 5: Maximize Sharpe + Constraints (min_dividend_yield 2.5%, min 5%, max 40%)"
echo "======================================================================"
curl -s -X POST "$BASE/optimize" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "maximize_sharpe",
    "periods_per_year": 12,
    "constraints": {
      "min_dividend_yield": 2.50,
      "min_weight": 5.0,
      "max_weight": 40.0
    },
    "securities": [
      {"ticker":"IEFA","security_name":"iShares Core MSCI EAFE ETF","current_weight":20.0,"dividend_yield":3.10,
       "returns":{"2020-01-01":-2.1,"2020-02-01":-8.3,"2020-03-01":-14.0,"2020-04-01":6.4,"2020-05-01":2.1,"2020-06-01":2.8}},
      {"ticker":"GLD","security_name":"SPDR Gold Shares","current_weight":20.0,"dividend_yield":0.0,
       "returns":{"2020-01-01":4.7,"2020-02-01":0.5,"2020-03-01":-1.0,"2020-04-01":6.9,"2020-05-01":2.8,"2020-06-01":2.9}},
      {"ticker":"AGG","security_name":"iShares Core US Aggregate Bond ETF","current_weight":20.0,"dividend_yield":2.70,
       "returns":{"2020-01-01":1.8,"2020-02-01":1.7,"2020-03-01":0.6,"2020-04-01":1.8,"2020-05-01":0.4,"2020-06-01":0.6}},
      {"ticker":"VEA","security_name":"Vanguard FTSE Developed Markets ETF","current_weight":20.0,"dividend_yield":3.40,
       "returns":{"2020-01-01":-2.3,"2020-02-01":-8.8,"2020-03-01":-14.5,"2020-04-01":6.1,"2020-05-01":2.0,"2020-06-01":2.5}},
      {"ticker":"SPY","security_name":"SPDR S&P 500 ETF Trust","current_weight":20.0,"dividend_yield":1.30,
       "returns":{"2020-01-01":-0.2,"2020-02-01":-8.4,"2020-03-01":-12.4,"2020-04-01":12.7,"2020-05-01":4.8,"2020-06-01":1.8}}
    ]
  }' | python3 -m json.tool

echo ""
echo "======================================================================"
echo "Case 6 (Bonus): Optimize Factor Exposure – Maximize Momentum"
echo "======================================================================"
curl -s -X POST "$BASE/optimize" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "optimize_factor_exposure",
    "periods_per_year": 12,
    "factor_objectives": [
      {"factor": "momentum", "direction": "maximize"}
    ],
    "factor_returns": {
      "momentum": {"2020-01-01": 1.2, "2020-02-01": -0.8, "2020-03-01": -3.1,
                   "2020-04-01": 2.1, "2020-05-01": 0.9, "2020-06-01": 1.4},
      "value":    {"2020-01-01": -0.4, "2020-02-01": -1.2, "2020-03-01": -2.0,
                   "2020-04-01": 1.1, "2020-05-01": 0.3, "2020-06-01": 0.7},
      "size":     {"2020-01-01": 0.6, "2020-02-01": -0.5, "2020-03-01": -1.8,
                   "2020-04-01": 1.5, "2020-05-01": 0.4, "2020-06-01": 0.9}
    },
    "securities": [
      {"ticker":"IEFA","security_name":"iShares Core MSCI EAFE ETF","current_weight":20.0,"dividend_yield":3.10,
       "returns":{"2020-01-01":-2.1,"2020-02-01":-8.3,"2020-03-01":-14.0,"2020-04-01":6.4,"2020-05-01":2.1,"2020-06-01":2.8}},
      {"ticker":"GLD","security_name":"SPDR Gold Shares","current_weight":20.0,"dividend_yield":0.0,
       "returns":{"2020-01-01":4.7,"2020-02-01":0.5,"2020-03-01":-1.0,"2020-04-01":6.9,"2020-05-01":2.8,"2020-06-01":2.9}},
      {"ticker":"AGG","security_name":"iShares Core US Aggregate Bond ETF","current_weight":20.0,"dividend_yield":2.70,
       "returns":{"2020-01-01":1.8,"2020-02-01":1.7,"2020-03-01":0.6,"2020-04-01":1.8,"2020-05-01":0.4,"2020-06-01":0.6}},
      {"ticker":"VEA","security_name":"Vanguard FTSE Developed Markets ETF","current_weight":20.0,"dividend_yield":3.40,
       "returns":{"2020-01-01":-2.3,"2020-02-01":-8.8,"2020-03-01":-14.5,"2020-04-01":6.1,"2020-05-01":2.0,"2020-06-01":2.5}},
      {"ticker":"SPY","security_name":"SPDR S&P 500 ETF Trust","current_weight":20.0,"dividend_yield":1.30,
       "returns":{"2020-01-01":-0.2,"2020-02-01":-8.4,"2020-03-01":-12.4,"2020-04-01":12.7,"2020-05-01":4.8,"2020-06-01":1.8}}
    ]
  }' | python3 -m json.tool

echo ""
echo "All test cases complete."
