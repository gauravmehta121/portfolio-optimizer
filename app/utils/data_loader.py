# """
# Returns Data Loader
# ===================
# Fetches historical monthly returns for tickers using yfinance.
# This is needed because the Finominal frontend payload does NOT include
# return data — it only sends tickers + weights. The API must fetch
# price history itself.

# Usage:
#     from app.utils.data_loader import load_returns, load_dividend_yields
# """

# from __future__ import annotations

# from typing import Dict, List, Optional, Tuple
# from datetime import datetime, date
# import logging

# logger = logging.getLogger(__name__)


# def load_returns(
#     tickers: List[str],
#     start_date: Optional[str] = None,
#     end_date: Optional[str] = None,
#     frequency: str = "M",       # "M" = monthly, "W" = weekly, "D" = daily
# ) -> Tuple[Dict[str, Dict[str, float]], float]:
#     """
#     Fetch adjusted close prices and compute period returns.

#     Parameters
#     ----------
#     tickers    : list of ticker symbols
#     start_date : ISO date string, e.g. "2012-10-23" (default: 10 years ago)
#     end_date   : ISO date string (default: today)
#     frequency  : "M" monthly, "W" weekly, "D" daily

#     Returns
#     -------
#     (returns_map, lookback_years)
#     returns_map : { ticker: { "YYYY-MM-DD": return_pct } }
#     lookback_years: approximate years of data available
#     """
#     try:
#         import yfinance as yf
#     except ImportError:
#         raise ImportError(
#             "yfinance is required to fetch live data. "
#             "Install it with: pip install yfinance"
#         )

#     import pandas as pd

#     if end_date is None:
#         end_date = date.today().isoformat()
#     if start_date is None:
#         # Default: 10 years back
#         start_dt = datetime.fromisoformat(end_date).replace(
#             year=datetime.fromisoformat(end_date).year - 10
#         )
#         start_date = start_dt.date().isoformat()

#     logger.info(f"Fetching {frequency} returns for {tickers} from {start_date} to {end_date}")

#     # Download adjusted close prices for all tickers at once
#     raw = yf.download(
#         tickers,
#         start=start_date,
#         end=end_date,
#         auto_adjust=True,
#         progress=False,
#         group_by="ticker",
#     )

#     if raw.empty:
#         raise ValueError(f"No price data returned for tickers: {tickers}")

#     # Extract Close prices — handle single vs multiple tickers
#     if len(tickers) == 1:
#         close = raw[["Close"]].rename(columns={"Close": tickers[0]})
#     else:
#         if "Close" in raw.columns.get_level_values(0):
#             close = raw["Close"]
#         else:
#             # Some yfinance versions return (ticker, field) ordering
#             close = raw.xs("Close", axis=1, level=1)

#     # Resample to desired frequency and forward-fill gaps
#     freq_map = {"M": "ME", "W": "W-FRI", "D": "D"}
#     resample_rule = freq_map.get(frequency, "ME")
#     close_resampled = close.resample(resample_rule).last().ffill()

#     # Compute period returns in percent
#     returns_pct = close_resampled.pct_change().dropna() * 100

#     # Build output dict
#     returns_map: Dict[str, Dict[str, float]] = {}
#     missing = []
#     for ticker in tickers:
#         if ticker not in returns_pct.columns:
#             missing.append(ticker)
#             logger.warning(f"Ticker '{ticker}' not found in downloaded data")
#             continue
#         series = returns_pct[ticker].dropna()
#         returns_map[ticker] = {
#             idx.strftime("%Y-%m-%d"): round(float(val), 6)
#             for idx, val in series.items()
#         }

#     if missing:
#         raise ValueError(
#             f"Could not fetch price data for: {missing}. "
#             "Check that these tickers are valid and have data in the requested date range."
#         )

#     # Compute lookback years from actual data range
#     all_dates = [
#         list(v.keys()) for v in returns_map.values() if v
#     ]
#     if all_dates:
#         flat = [d for dates in all_dates for d in dates]
#         earliest = min(flat)
#         latest = max(flat)
#         delta_days = (
#             datetime.fromisoformat(latest) - datetime.fromisoformat(earliest)
#         ).days
#         lookback_years = round(delta_days / 365.25, 1)
#     else:
#         lookback_years = 0.0

#     return returns_map, lookback_years


# def load_dividend_yields(tickers: List[str]) -> Dict[str, float]:
#     """
#     Fetch trailing 12-month dividend yield for each ticker (in percent).
#     Returns 0.0 for any ticker where yield data is unavailable.
#     """
#     try:
#         import yfinance as yf
#     except ImportError:
#         return {t: 0.0 for t in tickers}

#     yields = {}
#     for ticker in tickers:
#         try:
#             info = yf.Ticker(ticker).info
#             # yfinance returns dividendYield as a decimal (e.g. 0.013 = 1.3%)
#             dy = info.get("dividendYield") or info.get("trailingAnnualDividendYield") or 0.0
#             yields[ticker] = round(float(dy) * 100, 4)  # convert to percent
#         except Exception:
#             yields[ticker] = 0.0
#             logger.warning(f"Could not fetch dividend yield for {ticker}")

#     return yields

"""
Data Loader – Reads the provided Excel file
Expects three sheets:
- "FundReturns": index = Date (datetime), columns = tickers, values = monthly returns (in percent)
- "FactorReturns": index = Date, columns = ["Momentum", "Value", "Size"], values = factor returns (in percent)
- "FundInfo": columns = ticker, fund_name, dividend_yield (e.g., "3.28%")
"""


from __future__ import annotations

from typing import Dict, List, Tuple, Optional
from pathlib import Path
import pandas as pd
import logging

logger = logging.getLogger(__name__)

EXCEL_PATH = Path("/Users/gaurav/Desktop/protfoliooptimizer/app/data/fund_data.xlsx")

def load_returns(
    tickers: List[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    frequency: str = "M",
) -> Tuple[Dict[str, Dict[str, float]], float]:
    """
    Read long‑format fund returns (date, total_return, ticker) and pivot.
    """
    df = pd.read_excel(EXCEL_PATH, sheet_name="Fund Returns")
    df['date'] = pd.to_datetime(df['date'])
    # Remove '%' and convert to float
    df['total_return'] = df['total_return'].apply(_convert_percent)

    if start_date:
        df = df[df['date'] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df['date'] <= pd.to_datetime(end_date)]

    present = df['ticker'].unique()
    missing = [t for t in tickers if t not in present]
    if missing:
        raise ValueError(f"Missing return data for tickers: {missing}")

    # Pivot to wide format (dates as rows, tickers as columns)
    pivot = df.pivot(index='date', columns='ticker', values='total_return')
    pivot = pivot[tickers]  # keep only requested tickers, in order

    returns_map = {}
    for t in tickers:
        series = pivot[t].dropna()
        returns_map[t] = {
            idx.strftime("%Y-%m-%d"): round(float(val) / 100.0, 8)
            for idx, val in series.items()
        }

    if not pivot.empty:
        days = (pivot.index[-1] - pivot.index[0]).days
        lookback_years = round(days / 365.25, 1)
    else:
        lookback_years = 0.0

    return returns_map, lookback_years


def load_dividend_yields(tickers: List[str]) -> Dict[str, float]:
    """
    Read dividend yields from "Fund Info" sheet.
    Expects columns: ticker, dividend_yield (string like "3.28%").
    """
    df = pd.read_excel(EXCEL_PATH, sheet_name="Fund Info")
    
    def parse_yield(val):
        if pd.isna(val):
            return 0.0
        if isinstance(val, str):
            val = val.replace('%', '').strip()
        try:
            return float(val)
        except:
            return 0.0

    df['dividend_yield'] = df['dividend_yield'].apply(parse_yield)
    div_dict = dict(zip(df['ticker'], df['dividend_yield']))
    return {t: div_dict.get(t, 0.0) for t in tickers}

def _convert_percent(val):
    """Convert a percentage string like '3.28%' or a float to a float."""
    if pd.isna(val):
        return 0.0
    if isinstance(val, str):
        val = val.replace('%', '').strip()
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def load_factor_returns() -> pd.DataFrame:
    """
    Read long‑format factor returns (date, total_return, index_ticker) and
    pivot to wide format with columns: momentum, value, size.
    """
    df = pd.read_excel(EXCEL_PATH, sheet_name="Factor Returns")
    df['date'] = pd.to_datetime(df['date'])
    df['total_return'] = df['total_return'].apply(_convert_percent)
    
    # Map factor names to lower‑case standard names
    factor_map = {
        "Momentum Factor": "momentum",
        "Value Factor": "value",
        "Size Factor": "size",
    }
    df['factor'] = df['index_ticker'].map(factor_map)
    # Drop any rows with unknown factor names
    df = df.dropna(subset=['factor'])
    
    # Pivot
    pivot = df.pivot(index='date', columns='factor', values='total_return')
    # Ensure all three exist; fill missing with 0.0 if needed
    for f in ['momentum', 'value', 'size']:
        if f not in pivot.columns:
            pivot[f] = 0.0
    return pivot[['momentum', 'value', 'size']]