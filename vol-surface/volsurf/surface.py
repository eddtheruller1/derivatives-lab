"""The volatility surface built from fitted SVI slices, and the numbers a desk quotes.

Between two expiries, total variance is interpolated linearly in maturity at a
fixed log-moneyness k = ln(K / F(T)). If the slices are free of calendar
arbitrage (w non-decreasing in T at every k), the interpolated surface is too.
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

from volsurf import black
from volsurf.svi import svi_w

DELTA_25 = 0.25


@dataclass
class Slice:
    """One fitted expiry: maturity, implied forward, rate and SVI parameters."""
    T: float
    F: float
    r: float
    params: np.ndarray

    def w(self, k):
        return svi_w(np.asarray(k, float), *self.params)

    def vol(self, k):
        return np.sqrt(self.w(k) / self.T)


@dataclass
class Surface:
    """A list of slices sorted by maturity. Gives implied vol at any (K, T)."""
    slices: list[Slice]

    def __post_init__(self):
        self.slices = sorted(self.slices, key=lambda s: s.T)
        self._T = np.array([s.T for s in self.slices])

    def forward(self, T: float) -> float:
        """Forward at any T: ln F interpolated linearly in T (flat carry between expiries)."""
        return float(np.exp(np.interp(T, self._T, [np.log(s.F) for s in self.slices])))

    def total_variance(self, k, T: float):
        """w(k, T), linear in T between slices; before the first and after the last
        slice the implied vol of the nearest slice is held flat (w scales with T)."""
        s = self.slices
        if T <= s[0].T:
            return s[0].w(k) * T / s[0].T
        if T >= s[-1].T:
            return s[-1].w(k) * T / s[-1].T
        i = int(np.searchsorted(self._T, T))
        lo, hi = s[i - 1], s[i]
        x = (T - lo.T) / (hi.T - lo.T)
        return (1 - x) * lo.w(k) + x * hi.w(k)

    def implied_vol(self, K, T: float):
        """Implied vol at strike K and maturity T."""
        k = np.log(np.asarray(K, float) / self.forward(T))
        return np.sqrt(self.total_variance(k, T) / T)


def risk_neutral_density(sl: Slice, strikes: np.ndarray) -> np.ndarray:
    """Breeden-Litzenberger: q(K) = exp(rT) d2C/dK2, by central differences on SVI call prices.

    The strike grid must be evenly spaced. The two end points are returned as nan.
    """
    vols = sl.vol(np.log(strikes / sl.F))
    calls = black.price(sl.F, strikes, sl.T, sl.r, vols, True)
    h = strikes[1] - strikes[0]
    q = np.full_like(strikes, np.nan, dtype=float)
    q[1:-1] = np.exp(sl.r * sl.T) * (calls[2:] - 2 * calls[1:-1] + calls[:-2]) / h**2
    return q


def lognormal_density(F: float, T: float, sigma: float, strikes: np.ndarray) -> np.ndarray:
    """Density of S_T under Black-76 with one flat vol: lognormal with mean F."""
    s = sigma * np.sqrt(T)
    mu = np.log(F) - 0.5 * s**2
    return np.exp(-((np.log(strikes) - mu) ** 2) / (2 * s**2)) / (strikes * s * np.sqrt(2 * np.pi))


def delta_strike_k(sl: Slice, target_delta: float, is_call: bool) -> float:
    """Log-moneyness whose forward delta (undiscounted N(d1), at its own smile vol) equals target.

    Call delta N(d1) = 0.25  ->  d1 = N^-1(0.25).  Put delta -N(-d1) = -0.25  ->  d1 = N^-1(0.75).
    d1(k) = -k / sqrt(w(k)) + sqrt(w(k)) / 2.
    """
    d1_target = norm.ppf(target_delta) if is_call else norm.ppf(1 - target_delta)

    def gap(k: float) -> float:
        w = float(sl.w(k))
        return -k / np.sqrt(w) + np.sqrt(w) / 2 - d1_target

    lo, hi = (0.0, 3.0) if is_call else (-3.0, 0.0)
    try:
        return brentq(gap, lo, hi)
    except ValueError:
        return float("nan")


def desk_quotes(sl: Slice) -> dict:
    """ATM vol (at k = 0, the forward), 25-delta risk reversal and 25-delta butterfly, in vol units.

    RR = vol(25d call) - vol(25d put): negative = puts richer = downside skew.
    BF = (vol(25d call) + vol(25d put)) / 2 - ATM vol: how convex the smile is.
    """
    atm = float(sl.vol(0.0))
    k_call = delta_strike_k(sl, DELTA_25, True)
    k_put = delta_strike_k(sl, DELTA_25, False)
    v_call, v_put = float(sl.vol(k_call)), float(sl.vol(k_put))
    return {"atm": atm, "rr25": v_call - v_put, "bf25": (v_call + v_put) / 2 - atm,
            "k_25c": k_call, "k_25p": k_put}
