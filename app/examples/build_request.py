"""
build_request.py
================
Utility to load the provided Excel file and construct API request bodies
for each of the 6 required test cases.

Usage:
    python examples/build_request.py --excel path/to/returns.xlsx --case 3

Outputs a ready-to-paste JSON request body, or optionally runs it against
the local API.

Expected Excel format:
- Sheet "Returns": first column = date, subsequent columns = ticker returns (%)
- Sheet "FactorReturns": first column = date, columns = Momentum, Value, Size (%)
- Sheet "Metadata": columns = Ticker, SecurityName, DividendYield
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import requests


# ---------------------------------------------------------------------------
# Test case definitions (portfolios from the assignment)
# ---------------------------------------------------------------------------

TEST_CASES = {
    1: {
        "name": "Equal Weights – IEFA 25%, SPY 75%",
        "portfolio": {"IEFA": 25.0, "SPY": 75.0},
        "strategy": "equal_weights",
        "constraints": None,
    },
    2: {
        "name": "Risk Parity – VEA 25%, AGG 75%",
        "portfolio": {"VEA": 25.0, "AGG": 75.0},
        "strategy": "risk_parity",
        "constraints": None,
    },
    3: {
        "name": "Minimize Volatility – SPY 60%, AGG 30%, GLD 10%",
        "portfolio": {"SPY": 60.0, "AGG": 30.0, "GLD": 10.0},
        "strategy": "minimize_volatility",
        "constraints": None,
    },
    4: {
        "name": "Maximize Sharpe – 5 equal-weight assets",
        "portfolio": {"IEFA": 20.0, "GLD": 20.0, "AGG": 20.0, "VEA": 20.0, "SPY": 20.0},
        "strategy": "maximize_sharpe",
        "constraints": None,
    },
    5: {
        "name": "Maximize Sharpe + Constraints – 5 equal-weight assets",
        "portfolio": {"IEFA": 20.0, "GLD": 20.0, "AGG": 20.0, "VEA": 20.0, "SPY": 20.0},
        "strategy": "maximize_sharpe",
        "constraints": {
            "min_dividend_yield": 2.50,
            "min_weight": 5.0,
            "max_weight": 40.0,
        },
    },
    6: {
        "name": "Optimize Factor Exposure – Maximize Momentum (Bonus)",
        "portfolio": {"IEFA": 20.0, "GLD": 20.0, "AGG": 20.0, "VEA": 20.0, "SPY": 20.0},
        "strategy": "optimize_factor_exposure",
        "factor_objectives": [{"factor": "momentum", "direction": "maximize"}],
        "constraints": None,
    },
}


# ---------------------------------------------------------------------------
# Excel loading
# ---------------------------------------------------------------------------

def load_excel(path: str):
    """
    Load returns, factor returns, and metadata from the Excel file.
    Returns: (returns_df, factor_df, metadata_df)
    """
    xl = pd.ExcelFile(path)

    # --- Returns sheet ---
    # Try common sheet name patterns
    ret_sheet = next(
        (s for s in xl.sheet_names if "return" in s.lower()), xl.sheet_names[0]
    )
    returns_df = xl.parse(ret_sheet, index_col=0, parse_dates=True)
    returns_df.index = pd.to_datetime(returns_df.index)
    returns_df = returns_df.sort_index()

    # --- Factor returns sheet ---
    factor_df = None
    factor_sheet = next(
        (s for s in xl.sheet_names if "factor" in s.lower()), None
    )
    if factor_sheet:
        factor_df = xl.parse(factor_sheet, index_col=0, parse_dates=True)
        factor_df.index = pd.to_datetime(factor_df.index)
        factor_df = factor_df.sort_index()

    # --- Metadata sheet ---
    meta_df = None
    meta_sheet = next(
        (s for s in xl.sheet_names if "meta" in s.lower() or "info" in s.lower()), None
    )
    if meta_sheet:
        meta_df = xl.parse(meta_sheet)

    print(f"Loaded '{ret_sheet}': {len(returns_df)} rows, columns: {list(returns_df.columns)}")
    if factor_df is not None:
        print(f"Loaded '{factor_sheet}': factors: {list(factor_df.columns)}")
    if meta_df is not None:
        print(f"Loaded metadata: {list(meta_df.columns)}")

    return returns_df, factor_df, meta_df


def build_security(ticker, weight, returns_df, meta_df):
    """Build a SecurityInput dict from Excel data."""
    if ticker not in returns_df.columns:
        raise ValueError(f"Ticker '{ticker}' not found in returns data. Available: {list(returns_df.columns)}")

    ret_series = returns_df[ticker].dropna()
    returns_dict = {d.strftime("%Y-%m-%d"): float(v) for d, v in ret_series.items()}

    security_name = ticker
    dividend_yield = 0.0

    if meta_df is not None:
        # Try to find by ticker (flexible column name matching)
        ticker_col = next((c for c in meta_df.columns if "ticker" in c.lower()), None)
        if ticker_col:
            row = meta_df[meta_df[ticker_col].astype(str).str.upper() == ticker.upper()]
            if not row.empty:
                name_col = next((c for c in meta_df.columns if "name" in c.lower()), None)
                yield_col = next((c for c in meta_df.columns if "yield" in c.lower() or "dividend" in c.lower()), None)
                if name_col:
                    security_name = str(row.iloc[0][name_col])
                if yield_col:
                    dividend_yield = float(row.iloc[0][yield_col])

    return {
        "ticker": ticker,
        "security_name": security_name,
        "current_weight": weight,
        "dividend_yield": dividend_yield,
        "returns": returns_dict,
    }


def build_request(case_num: int, returns_df, factor_df, meta_df):
    """Build the full API request body for a given test case number."""
    case = TEST_CASES[case_num]
    print(f"\nBuilding Case {case_num}: {case['name']}")

    securities = [
        build_security(ticker, weight, returns_df, meta_df)
        for ticker, weight in case["portfolio"].items()
    ]

    body = {
        "strategy": case["strategy"],
        "periods_per_year": 12,
        "securities": securities,
    }

    if case.get("constraints"):
        body["constraints"] = case["constraints"]

    if case.get("factor_objectives"):
        body["factor_objectives"] = case["factor_objectives"]
        if factor_df is not None:
            factor_returns = {}
            for col in factor_df.columns:
                col_lower = col.lower().strip()
                # Normalise factor names
                if "mom" in col_lower:
                    key = "momentum"
                elif "val" in col_lower:
                    key = "value"
                elif "size" in col_lower or "smb" in col_lower:
                    key = "size"
                else:
                    key = col_lower
                factor_returns[key] = {
                    d.strftime("%Y-%m-%d"): float(v)
                    for d, v in factor_df[col].dropna().items()
                }
            body["factor_returns"] = factor_returns
        else:
            print("WARNING: No factor returns sheet found – case 6 will fail without it.")

    return body


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build Portfolio Optimizer API request from Excel data")
    parser.add_argument("--excel", required=True, help="Path to the Excel file with return data")
    parser.add_argument("--case", type=int, choices=range(1, 7), help="Test case number (1-6). Omit for all.")
    parser.add_argument("--run", action="store_true", help="POST the request to http://localhost:8000/optimize")
    parser.add_argument("--output", help="Save request JSON to this file path")
    args = parser.parse_args()

    returns_df, factor_df, meta_df = load_excel(args.excel)

    cases_to_run = [args.case] if args.case else list(TEST_CASES.keys())

    for case_num in cases_to_run:
        try:
            body = build_request(case_num, returns_df, factor_df, meta_df)
            json_str = json.dumps(body, indent=2)

            if args.output:
                out_path = args.output if len(cases_to_run) == 1 else args.output.replace(".json", f"_case{case_num}.json")
                Path(out_path).write_text(json_str)
                print(f"Saved to {out_path}")
            else:
                print(json_str[:500] + "..." if len(json_str) > 500 else json_str)

            if args.run:
                resp = requests.post("http://localhost:8000/optimize", json=body, timeout=30)
                print(f"\nAPI Response (Case {case_num}):")
                try:
                    print(json.dumps(resp.json(), indent=2))
                except Exception:
                    print(resp.text)

        except Exception as exc:
            print(f"ERROR in case {case_num}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
