"""Implied forward and discount factor from put-call parity.

For European options, C(K) - P(K) = DF (F - K) = DF F - DF K.
So across strikes, call mid minus put mid is a straight line in K with
slope -DF and intercept DF F. A least-squares fit over near-the-money strikes
(where both quotes are liquid) gives DF = -slope and F = intercept / DF.
The forward then carries the market's view of dividends and financing, which
is why we never need to input a dividend yield.

SPY and FEZ options are American. Parity holds only approximately for them
(early exercise is worth a little, mostly for in-the-money puts), which is one
more reason to stay near the money here.
"""

import numpy as np
import pandas as pd

NEAR_MONEY = 0.05   # use strikes within +-5% of spot ...
MIN_PAIRS = 6       # ... or the closest MIN_PAIRS strikes if that gives too few


def regress_forward(strikes: np.ndarray, call_minus_put: np.ndarray) -> tuple[float, float]:
    """OLS of (C - P) on K. Returns (forward, discount factor)."""
    slope, intercept = np.polyfit(strikes, call_minus_put, 1)
    df = -slope
    return intercept / df, df


def parity_pairs(slice_df: pd.DataFrame) -> pd.DataFrame:
    """Strikes where both the call and the put have a two-sided quote, with mids."""
    q = slice_df[(slice_df["bid"] > 0) & (slice_df["ask"] > slice_df["bid"])].copy()
    q["mid"] = (q["bid"] + q["ask"]) / 2
    wide = q.pivot_table(index="strike", columns="type", values="mid")
    if not {"call", "put"} <= set(wide.columns):
        return pd.DataFrame(columns=["strike", "call", "put"])
    return wide.dropna(subset=["call", "put"]).reset_index()


def near_money_pairs(slice_df: pd.DataFrame, spot: float) -> pd.DataFrame:
    """Parity pairs within NEAR_MONEY of spot, or the MIN_PAIRS closest ones."""
    pairs = parity_pairs(slice_df)
    if len(pairs) < 3:
        raise ValueError("fewer than 3 strikes with both a call and a put quote")
    dist = (pairs["strike"] / spot - 1).abs()
    near = pairs[dist <= NEAR_MONEY]
    if len(near) < MIN_PAIRS:
        near = pairs.loc[dist.nsmallest(MIN_PAIRS).index]
    return near


def implied_forward(slice_df: pd.DataFrame, spot: float) -> tuple[float, float, int]:
    """Forward and discount factor for one expiry by regression. Returns (F, DF, strikes used)."""
    near = near_money_pairs(slice_df, spot)
    F, df = regress_forward(near["strike"].to_numpy(), (near["call"] - near["put"]).to_numpy())
    return F, df, len(near)


def forward_given_df(slice_df: pd.DataFrame, spot: float, df: float) -> tuple[float, int]:
    """Forward when the discount factor is already known: F = mean of K + (C - P) / DF.

    Used when a chain is too thin to pin down the slope (DF) of the regression,
    but the rate is known from a more liquid chain in the same currency.
    """
    near = near_money_pairs(slice_df, spot)
    F = float(np.mean(near["strike"] + (near["call"] - near["put"]) / df))
    return F, len(near)
