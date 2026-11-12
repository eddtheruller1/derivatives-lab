"""Black-76 prices and closed-form Greeks for European options on a forward.

Why price on the forward: the forward F already contains the carry (rates and
dividends), so the formula needs only F, the strike, the discount factor and the
volatility. We back F out of the market (see forward.py) instead of guessing a
dividend yield.

Conventions: T in years, r the continuously compounded rate so that the discount
factor is exp(-r T), sigma the annual volatility. Greeks are per unit change:
delta and gamma with respect to the forward F, vega per 1.00 of vol (divide by
100 for one vol point), theta per year of calendar time (divide by 365 for a day).
"""

import numpy as np
from scipy.stats import norm


def d1_d2(F, K, T, sigma):
    """The two standard Black-76 terms."""
    sqrt_t = np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * sigma**2 * T) / (sigma * sqrt_t)
    return d1, d1 - sigma * sqrt_t


def price(F, K, T, r, sigma, is_call=True):
    """Black-76 price: exp(-rT) [F N(d1) - K N(d2)] for a call, put by symmetry."""
    d1, d2 = d1_d2(F, K, T, sigma)
    df = np.exp(-r * T)
    if is_call:
        return df * (F * norm.cdf(d1) - K * norm.cdf(d2))
    return df * (K * norm.cdf(-d2) - F * norm.cdf(-d1))


def delta(F, K, T, r, sigma, is_call=True):
    """dV/dF. Calls: DF N(d1). Puts: -DF N(-d1)."""
    d1, _ = d1_d2(F, K, T, sigma)
    df = np.exp(-r * T)
    return df * norm.cdf(d1) if is_call else -df * norm.cdf(-d1)


def gamma(F, K, T, r, sigma):
    """d2V/dF2, the same for calls and puts: DF n(d1) / (F sigma sqrt(T))."""
    d1, _ = d1_d2(F, K, T, sigma)
    return np.exp(-r * T) * norm.pdf(d1) / (F * sigma * np.sqrt(T))


def vega(F, K, T, r, sigma):
    """dV/dsigma, the same for calls and puts: DF F n(d1) sqrt(T)."""
    d1, _ = d1_d2(F, K, T, sigma)
    return np.exp(-r * T) * F * norm.pdf(d1) * np.sqrt(T)


def theta(F, K, T, r, sigma, is_call=True):
    """dV/dt as time passes (t = -T), holding F and r fixed.

    V = DF * B(F, T) with DF = exp(-rT), so -dV/dT = r V - DF F n(d1) sigma / (2 sqrt(T)).
    """
    d1, _ = d1_d2(F, K, T, sigma)
    decay = np.exp(-r * T) * F * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
    return r * price(F, K, T, r, sigma, is_call) - decay
