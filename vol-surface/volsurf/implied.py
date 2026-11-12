"""Implied volatility: the sigma that makes the Black-76 price equal the market price.

There is no closed form for the inverse of Black-76, so it is solved numerically.
Newton's method on vega converges in a few steps near the money, but it can fail
when vega is tiny (far wings, very short maturities) because the step
price_error / vega explodes. So every Newton step is checked, and on any trouble
we fall back to Brent's method, which needs only a bracket [lo, hi] where the
price error changes sign and always converges inside it.

Before solving, the price is checked against the no-arbitrage bounds. A price
outside them has no implied vol at all, and we say so instead of returning junk.
"""

import math

import numpy as np
from scipy.optimize import brentq

from volsurf import black

VOL_LO, VOL_HI = 1e-6, 10.0
TOL = 1e-10


def price_bounds(F: float, K: float, T: float, r: float, is_call: bool) -> tuple[float, float]:
    """No-arbitrage bounds of a European option on a forward.

    Call: DF max(F-K, 0) <= C <= DF F.  Put: DF max(K-F, 0) <= P <= DF K.
    The lower bound is the discounted intrinsic value (vol 0), the upper one the
    limit as vol goes to infinity.
    """
    df = math.exp(-r * T)
    if is_call:
        return df * max(F - K, 0.0), df * F
    return df * max(K - F, 0.0), df * K


def implied_vol(px: float, F: float, K: float, T: float, r: float,
                is_call: bool = True, guess: float = 0.2) -> tuple[float, str]:
    """Return (vol, "ok") or (nan, reason). Never raises on bad market data."""
    if not all(math.isfinite(x) for x in (px, F, K, T, r)) or F <= 0 or K <= 0 or T <= 0:
        return math.nan, "bad input"
    lo, hi = price_bounds(F, K, T, r, is_call)
    if px <= lo:
        return math.nan, "price at or below intrinsic"
    if px >= hi:
        return math.nan, "price at or above upper bound"

    def error(sigma: float) -> float:
        return black.price(F, K, T, r, sigma, is_call) - px

    sigma = guess
    for _ in range(50):
        v = black.vega(F, K, T, r, sigma)
        if v < 1e-12 * F:
            break  # flat price curve: a Newton step would shoot off
        step = error(sigma) / v
        new = sigma - step
        if not VOL_LO < new < VOL_HI:
            break
        sigma = new
        if abs(step) < TOL:
            return sigma, "ok"

    try:
        if error(VOL_LO) * error(VOL_HI) > 0:
            return math.nan, "no bracket"
        return brentq(error, VOL_LO, VOL_HI, xtol=TOL), "ok"
    except (ValueError, RuntimeError):
        return math.nan, "brent failed"


def is_otm(K: float, F: float, is_call: bool) -> bool:
    """Out of the money: puts below the forward, calls at or above it."""
    return K >= F if is_call else K < F


def implied_vols(prices, F: float, strikes, T: float, r: float, is_call) -> tuple[np.ndarray, list[str]]:
    """Solve a whole slice. Returns vols (nan where it failed) and one reason per quote."""
    vols, reasons = [], []
    for px, K, c in zip(prices, strikes, is_call):
        vol, why = implied_vol(float(px), F, float(K), T, r, bool(c))
        vols.append(vol)
        reasons.append(why)
    return np.array(vols), reasons
