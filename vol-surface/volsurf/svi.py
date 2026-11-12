"""Raw SVI fit of one expiry slice, and static-arbitrage checks.

Raw SVI (Gatheral, 2004) writes total implied variance w = sigma_imp^2 * T as a
function of log-moneyness k = ln(K / F):

    w(k) = a + b * ( rho * (k - m) + sqrt((k - m)^2 + sigma^2) )

a: overall level of variance.      b: slope of the wings (how fast w grows).
rho: tilt, -1..1 (negative = put skew).    m: horizontal shift of the smile.
sigma: curvature at the bottom (small = sharp V, large = round U).
"""

import itertools

import numpy as np
from scipy.optimize import least_squares

PARAM_NAMES = ("a", "b", "rho", "m", "sigma")


def svi_w(k, a, b, rho, m, sigma):
    """Total variance w(k) of raw SVI."""
    x = k - m
    return a + b * (rho * x + np.sqrt(x**2 + sigma**2))


def svi_derivatives(k, a, b, rho, m, sigma):
    """w, dw/dk and d2w/dk2 in closed form."""
    x = k - m
    root = np.sqrt(x**2 + sigma**2)
    w = a + b * (rho * x + root)
    w1 = b * (rho + x / root)
    w2 = b * sigma**2 / root**3
    return w, w1, w2


def _residuals(p, k, vol, T, weight):
    """Vega-weighted vol errors, plus a penalty if the minimum variance turns negative."""
    w = svi_w(k, *p)
    model_vol = np.sqrt(np.maximum(w, 1e-12) / T)
    a, b, rho, _, sigma = p
    min_w = a + b * sigma * np.sqrt(1 - rho**2)
    penalty = 1e3 * max(0.0, -min_w)
    return np.append(np.sqrt(weight) * (model_vol - vol), penalty)


def fit_svi(k: np.ndarray, vol: np.ndarray, T: float, vega: np.ndarray | None = None) -> np.ndarray:
    """Fit (a, b, rho, m, sigma) to market vols of one slice.

    Minimises sum_i vega_i * (svi_vol_i - market_vol_i)^2, so quotes with more
    vega (near the money, where prices are most informative) count more, and far
    wing quotes, whose vol is very sensitive to a one-tick price change, count less.
    Several starting points are tried because the problem is not convex.
    """
    k, vol = np.asarray(k, float), np.asarray(vol, float)
    weight = np.ones_like(k) if vega is None else np.asarray(vega, float) / np.max(vega)
    w_mkt = vol**2 * T
    w_max = float(w_mkt.max())
    lower = [-w_max, 1e-6, -0.999, 2 * k.min() - 0.1, 1e-4]
    upper = [w_max, 4.0, 0.999, 2 * k.max() + 0.1, 2.0]
    best = None
    for rho0, m0, s0 in itertools.product((-0.7, -0.3, 0.0), (0.0, k.min() / 2, k.max() / 2), (0.05, 0.2)):
        x0 = [0.5 * w_mkt.min(), 0.1 * w_max / max(np.ptp(k), 1e-3) + 1e-3, rho0, m0, s0]
        x0 = np.clip(x0, np.array(lower) + 1e-9, np.array(upper) - 1e-9)
        res = least_squares(_residuals, x0, bounds=(lower, upper), args=(k, vol, T, weight),
                            method="trf", x_scale="jac", max_nfev=2000)
        if best is None or res.cost < best.cost:
            best = res
    return best.x


def g_function(k, a, b, rho, m, sigma):
    """Gatheral's density function g(k). Butterfly-arbitrage free  <=>  g(k) >= 0.

    g(k) = (1 - k w' / (2w))^2 - (w'^2 / 4) (1/w + 1/4) + w'' / 2
    The risk-neutral density equals g(k) / sqrt(2 pi w) * exp(-d2^2 / 2), so a
    negative g means a negative probability density.
    """
    w, w1, w2 = svi_derivatives(k, a, b, rho, m, sigma)
    return (1 - k * w1 / (2 * w)) ** 2 - (w1**2 / 4) * (1 / w + 0.25) + w2 / 2


def butterfly_check(params, k_grid: np.ndarray) -> dict:
    """Evaluate g on a grid. Reports the minimum of g and where it is negative."""
    g = g_function(k_grid, *params)
    bad = k_grid[g < 0]
    return {
        "min_g": float(g.min()),
        "ok": bool(bad.size == 0),
        "bad_from": float(bad.min()) if bad.size else None,
        "bad_to": float(bad.max()) if bad.size else None,
    }


def calendar_check(params_short, params_long, k_grid: np.ndarray) -> dict:
    """Total variance must not fall with maturity at a fixed k: w_long(k) >= w_short(k).

    Reports the largest shortfall in total variance and the k range where it happens.
    """
    diff = svi_w(k_grid, *params_long) - svi_w(k_grid, *params_short)
    bad = k_grid[diff < 0]
    return {
        "min_diff": float(diff.min()),
        "ok": bool(bad.size == 0),
        "bad_from": float(bad.min()) if bad.size else None,
        "bad_to": float(bad.max()) if bad.size else None,
    }
