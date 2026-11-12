"""Historical backtest: launch the same note on every past month start and follow its term sheet.

This is what a structuring desk shows a client: on real closes, how often the note
redeemed early, how often capital was lost, and what the investor earned.
No model is involved; only the realised index levels.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from notes.products import Product, worst_of

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FILES = {"SX5E": "stoxx50e.csv", "SPX": "spx.csv"}


def load_closes(names, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Daily closes of the named indices, on the dates where all of them traded."""
    series = [pd.read_csv(data_dir / FILES[n], index_col="date", parse_dates=True)["close"].rename(n)
              for n in names]
    return pd.concat(series, axis=1, join="inner").dropna()


def on_or_after(index: pd.DatetimeIndex, day: pd.Timestamp) -> pd.Timestamp | None:
    """First trading day on or after `day`, or None past the end of the history."""
    pos = index.searchsorted(day)
    return index[pos] if pos < len(index) else None


def month_starts(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """First trading day of each calendar month in the history."""
    first = pd.Series(index, index=index).groupby(index.to_period("M")).first()
    return list(first)


def observation_dates(index: pd.DatetimeIndex, launch: pd.Timestamp, obs_times) -> list | None:
    """Trading day on or after launch + k months for each observation; None if the history ends first."""
    dates = [on_or_after(index, launch + pd.DateOffset(months=int(round(t * 12)))) for t in obs_times]
    return None if any(d is None for d in dates) else dates


def run_backtest(product: Product, closes: pd.DataFrame) -> pd.DataFrame:
    """One row per launch date with a full life of history: when it ended, what it paid, the return.

    Annualised return = (total paid / 100) ^ (1 / life) - 1, coupons not reinvested.
    """
    prices = closes[list(product.underlyings)]
    rows = []
    for launch in month_starts(prices.index):
        dates = observation_dates(prices.index, launch, product.obs_times)
        if dates is None:
            break
        fixing = prices.loc[launch].to_numpy()
        perf = (prices.loc[dates].to_numpy() / fixing)[None, :, :]
        path_min = (prices.loc[launch:dates[-1]].to_numpy() / fixing).min(axis=0)[None, :]
        out = product.evaluate(*worst_of(perf, path_min))
        end = int(out.end_index[0])
        life = product.obs_times[end]
        paid = float(out.cashflows[0].sum())
        rows.append({"launch": launch, "end_index": end, "end_date": dates[end], "life_years": life,
                     "total_paid": paid, "annual_return": (paid / 100.0) ** (1.0 / life) - 1.0,
                     "capital_loss": bool(out.capital_loss[0])})
    return pd.DataFrame(rows)


def summarise(results: pd.DataFrame, product: Product, worst: int = 5) -> dict:
    """Share redeemed on each date, share that lost capital, average and worst return, worst launches."""
    m = len(product.obs_times)
    by_date = np.bincount(results["end_index"], minlength=m) / len(results)
    worst_rows = results.nsmallest(worst, "annual_return")
    return {
        "launches": len(results),
        "first_launch": results["launch"].iloc[0],
        "last_launch": results["launch"].iloc[-1],
        "redemption_by_date": by_date,
        "early_redemption": float(by_date[:-1].sum()),
        "capital_loss": float(results["capital_loss"].mean()),
        "mean_annual_return": float(results["annual_return"].mean()),
        "worst_annual_return": float(results["annual_return"].min()),
        "worst_launches": [(d.date(), r) for d, r in zip(worst_rows["launch"], worst_rows["annual_return"])],
    }


def historical_estimates(data_dir: Path = DATA_DIR) -> dict:
    """The history-based inputs of params.py: annualised variance of daily returns, weekly correlation."""
    variance = {}
    for name in FILES:
        daily = np.log(load_closes([name], data_dir)[name]).diff().dropna()
        variance[name] = float(daily.var() * 252)
    closes = load_closes(["SX5E", "SPX"], data_dir)
    weekly = np.log(closes.resample("W-FRI").last()).diff().dropna()
    return {
        "variance": variance,
        "weekly_correlation": float(weekly.corr().iloc[0, 1]),
        "start": closes.index[0].date(),
        "end": closes.index[-1].date(),
    }
