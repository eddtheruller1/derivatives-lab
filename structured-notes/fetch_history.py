"""Download daily closes of the Euro Stoxx 50 and the S&P 500 with yfinance.

Run once; the CSVs under data/ let every other script run offline.
"""
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

DATA_DIR = Path(__file__).parent / "data"
TICKERS = {"^STOXX50E": "stoxx50e.csv", "^GSPC": "spx.csv"}
START = "2000-01-01"


def fetch_close(ticker: str) -> pd.Series:
    """Daily closes of one ticker from START to today, as a named Series."""
    for attempt in range(6):  # Yahoo rate-limits bursts; wait and retry
        frame = yf.download(ticker, start=START, auto_adjust=False, progress=False)
        if not frame.empty:
            break
        time.sleep(30 * (attempt + 1))
    else:
        raise RuntimeError(f"No data returned for {ticker}")
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):  # yfinance returns one column per ticker
        close = close.iloc[:, 0]
    close = close.dropna().round(2)
    close.index = pd.to_datetime(close.index).date
    close.index.name = "date"
    close.name = "close"
    return close


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    for ticker, filename in TICKERS.items():
        close = fetch_close(ticker)
        close.to_csv(DATA_DIR / filename)
        print(f"{ticker}: {len(close)} closes, {close.index[0]} to {close.index[-1]} -> data/{filename}")


if __name__ == "__main__":
    main()
