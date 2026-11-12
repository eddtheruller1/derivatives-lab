"""Download one snapshot of listed option chains and save it as small CSV files.

Run once with network access; everything else in the project then works offline
from the CSVs under data/. Only real quotes are saved. Sources, in order:

1. Yahoo Finance through yfinance.
2. Cboe's public delayed-quotes file (cdn.cboe.com), the same listed contracts
   with bid, ask, volume and open interest. Used when Yahoo refuses or
   rate-limits the request, which happens often with automated clients.

If both fail for the main pair (SPY, FEZ) the script tries a fallback pair
(QQQ, EWG); if everything fails it stops with an error. It never makes quotes up.
"""

import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

DATA_DIR = Path(__file__).parent / "data"

# (US underlying, European underlying). The first pair is the one we want.
PAIRS = [("SPY", "FEZ"), ("QQQ", "EWG")]

MIN_DAYS = 10
MAX_DAYS = 560
N_EXPIRIES = 8
CBOE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{}.json"
OUT_COLUMNS = ["underlying", "snapshot_date", "spot", "expiry", "type", "strike",
               "bid", "ask", "volume", "openInterest", "source"]
# OCC option symbol: root, expiry yymmdd, C or P, strike times 1000 on 8 digits.
OCC = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def pick_expiries(expiries: list[str], today: date) -> list[str]:
    """Pick up to N_EXPIRIES expiries between MIN_DAYS and MAX_DAYS, spread evenly in log-time."""
    days = sorted((d, e) for e in set(expiries)
                  if MIN_DAYS <= (d := (date.fromisoformat(e) - today).days) <= MAX_DAYS)
    if len(days) <= N_EXPIRIES:
        return [e for _, e in days]
    lo, hi = days[0][0], days[-1][0]
    targets = [lo * (hi / lo) ** (i / (N_EXPIRIES - 1)) for i in range(N_EXPIRIES)]
    chosen: list[str] = []
    for t in targets:
        best = min((x for x in days if x[1] not in chosen), key=lambda x: abs(x[0] - t))
        chosen.append(best[1])
    return sorted(chosen)


def fetch_yahoo(symbol: str) -> pd.DataFrame:
    """One underlying from Yahoo Finance via yfinance."""
    today = date.today()
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="5d")
    if hist.empty:
        raise RuntimeError("no price history")
    spot = float(hist["Close"].iloc[-1])
    snap = hist.index[-1].date()
    frames = []
    for expiry in pick_expiries(list(ticker.options), today):
        chain = ticker.option_chain(expiry)
        for kind, table in (("call", chain.calls), ("put", chain.puts)):
            part = table[["strike", "bid", "ask", "volume", "openInterest"]].copy()
            part["type"], part["expiry"] = kind, expiry
            frames.append(part)
        time.sleep(0.5)
    out = pd.concat(frames, ignore_index=True)
    out["underlying"], out["spot"], out["snapshot_date"] = symbol, spot, snap.isoformat()
    out["source"] = "yahoo"
    return out


def fetch_cboe(symbol: str) -> pd.DataFrame:
    """One underlying from Cboe's public delayed quotes.

    The snapshot date is the day of the underlying's last trade, so quotes taken
    before the US open are labelled with the previous session, which is what they are.
    """
    resp = requests.get(CBOE_URL.format(symbol), timeout=30)
    resp.raise_for_status()
    data = resp.json()["data"]
    snap = date.fromisoformat(data["last_trade_time"][:10])
    rows = []
    for opt in data["options"]:
        match = OCC.match(opt["option"])
        if not match or match.group(1) != symbol:  # skip adjusted or non-standard roots
            continue
        _, ymd, cp, strike = match.groups()
        rows.append({
            "expiry": f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:]}",
            "type": "call" if cp == "C" else "put",
            "strike": int(strike) / 1000,
            "bid": opt["bid"], "ask": opt["ask"],
            "volume": opt["volume"], "openInterest": opt["open_interest"],
        })
    out = pd.DataFrame(rows)
    out = out[out["expiry"].isin(pick_expiries(out["expiry"].tolist(), snap))]
    out["underlying"], out["spot"], out["snapshot_date"] = symbol, float(data["current_price"]), snap.isoformat()
    out["source"] = "cboe-delayed"
    return out


def fetch_symbol(symbol: str, tries: int = 2) -> pd.DataFrame:
    """Try Yahoo a few times, then Cboe. Raise if neither gives a usable chain."""
    for source, fetch in (("yahoo", fetch_yahoo), ("cboe", fetch_cboe)):
        for attempt in range(1, tries + 1):
            try:
                df = fetch(symbol)
                if df["expiry"].nunique() < 4:
                    raise RuntimeError(f"only {df['expiry'].nunique()} usable expiries")
                return df
            except Exception as exc:  # network, rate-limit and parsing errors look alike here
                print(f"  {symbol} via {source}, attempt {attempt}: {exc}")
                time.sleep(2 * attempt)
    raise RuntimeError(f"could not fetch {symbol}")


def main() -> int:
    DATA_DIR.mkdir(exist_ok=True)
    for us, eu in PAIRS:
        print(f"Trying {us} and {eu}")
        try:
            frames = {sym: fetch_symbol(sym) for sym in (us, eu)}
        except RuntimeError as exc:
            print(f"  pair failed: {exc}")
            continue
        for old in DATA_DIR.glob("*.csv"):
            old.unlink()
        for sym, df in frames.items():
            df = df[OUT_COLUMNS].sort_values(["expiry", "type", "strike"])
            df["volume"] = df["volume"].fillna(0).astype(int)
            df["openInterest"] = df["openInterest"].fillna(0).astype(int)
            path = DATA_DIR / f"{sym}_{df['snapshot_date'].iloc[0]}.csv"
            df.to_csv(path, index=False)
            print(f"  saved {len(df)} quotes, {df['expiry'].nunique()} expiries, "
                  f"spot {df['spot'].iloc[0]:.2f}, source {df['source'].iloc[0]} -> {path.name}")
        return 0
    print("No real market data could be fetched. Nothing saved.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
