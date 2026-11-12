"""Quote filters. Each rule is a named function that returns True for quotes to DROP.

Keeping the rules separate makes it possible to report how many quotes each one
removed, and to defend each threshold on its own.
"""

import numpy as np
import pandas as pd

MAX_REL_SPREAD = 0.5   # drop if (ask - bid) / mid > 50%: the mid is then a poor price
WING_STDEVS = 4.0      # drop if |ln(K/F)| > 4 standard deviations of a 25% vol move
WING_REF_VOL = 0.25


def zero_bid(q: pd.DataFrame, F: float, T: float) -> pd.Series:
    """No bid means nobody is willing to buy: the option's value is not observed."""
    return q["bid"] <= 0


def wide_spread(q: pd.DataFrame, F: float, T: float) -> pd.Series:
    """A crossed quote, or a spread above MAX_REL_SPREAD of the mid."""
    mid = (q["bid"] + q["ask"]) / 2
    return (q["ask"] <= q["bid"]) | ((q["ask"] - q["bid"]) / mid > MAX_REL_SPREAD)


def no_open_interest(q: pd.DataFrame, F: float, T: float) -> pd.Series:
    """No open contracts: the quote is a market maker's screen price nobody traded."""
    return q["openInterest"] <= 0


def far_wing(q: pd.DataFrame, F: float, T: float) -> pd.Series:
    """Strikes so far from the forward that the quote is mostly tick size and spread.

    The limit scales with sqrt(T): a strike 20% away is far for a two-week option
    and ordinary for an eighteen-month one.
    """
    k = np.log(q["strike"] / F)
    return k.abs() > WING_STDEVS * WING_REF_VOL * np.sqrt(T)


def not_otm(q: pd.DataFrame, F: float, T: float) -> pd.Series:
    """Keep only out-of-the-money options: puts below F, calls at or above F.

    They are the liquid side, and an American OTM option has almost no
    early-exercise premium, so Black-76 fits it well.
    """
    is_call = q["type"] == "call"
    return (is_call & (q["strike"] < F)) | (~is_call & (q["strike"] >= F))


RULES = [zero_bid, wide_spread, no_open_interest, far_wing, not_otm]


def apply_filters(q: pd.DataFrame, F: float, T: float) -> tuple[pd.DataFrame, dict[str, int]]:
    """Apply RULES in order. Returns the kept quotes and how many each rule removed."""
    removed = {}
    for rule in RULES:
        drop = rule(q, F, T)
        removed[rule.__name__] = int(drop.sum())
        q = q[~drop]
    return q, removed
