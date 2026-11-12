"""Heston (1993) stochastic volatility model.

dS/S = (r - q) dt + sqrt(v) dW_s
dv   = kappa (theta - v) dt + xi sqrt(v) dW_v,   corr(dW_s, dW_v) = rho

Two tools: a semi-closed-form European price (used to validate) and a Monte
Carlo path generator for one or two indices (used to price the notes).
"""
from dataclasses import dataclass

import numpy as np
from scipy.integrate import quad
from scipy.stats import norm


@dataclass(frozen=True)
class HestonParams:
    v0: float     # initial variance
    kappa: float  # speed of mean reversion of the variance
    theta: float  # long-run variance
    xi: float     # volatility of the variance ("vol of vol")
    rho: float    # correlation between spot and variance shocks


def char_function(u, spot: float, t: float, r: float, q: float, p: HestonParams):
    """Characteristic function E[exp(i u ln S_T)] in the "little trap" form.

    Albrecher et al. (2007): writing g with (b - d) on top keeps the complex
    logarithm on its main branch, so the integrand has no jumps for long maturities.
    """
    iu = 1j * u
    b = p.kappa - p.rho * p.xi * iu
    d = np.sqrt(b * b + p.xi ** 2 * (iu + u * u))
    g = (b - d) / (b + d)
    e = np.exp(-d * t)
    c_term = p.kappa * p.theta / p.xi ** 2 * ((b - d) * t - 2.0 * np.log((1.0 - g * e) / (1.0 - g)))
    d_term = p.v0 / p.xi ** 2 * (b - d) * (1.0 - e) / (1.0 - g * e)
    return np.exp(iu * (np.log(spot) + (r - q) * t) + c_term + d_term)


def exercise_probabilities(spot, strike, t, r, q, p: HestonParams) -> tuple[float, float]:
    """P1 (share measure) and P2 (risk-neutral) probabilities that S_T > K, by Gil-Pelaez inversion."""
    log_k = np.log(strike)
    forward = spot * np.exp((r - q) * t)

    def p1_integrand(u):
        return (np.exp(-1j * u * log_k) * char_function(u - 1j, spot, t, r, q, p) / (1j * u * forward)).real

    def p2_integrand(u):
        return (np.exp(-1j * u * log_k) * char_function(u, spot, t, r, q, p) / (1j * u)).real

    p1 = 0.5 + quad(p1_integrand, 1e-10, 200.0, limit=500)[0] / np.pi
    p2 = 0.5 + quad(p2_integrand, 1e-10, 200.0, limit=500)[0] / np.pi
    return p1, p2


def heston_price(spot, strike, t, r, q, p: HestonParams, kind: str = "call") -> float:
    """European call or put: C = S e^{-qT} P1 - K e^{-rT} P2, P = K e^{-rT} (1 - P2) - S e^{-qT} (1 - P1)."""
    p1, p2 = exercise_probabilities(spot, strike, t, r, q, p)
    if kind == "call":
        return spot * np.exp(-q * t) * p1 - strike * np.exp(-r * t) * p2
    return strike * np.exp(-r * t) * (1.0 - p2) - spot * np.exp(-q * t) * (1.0 - p1)


def heston_digital_put(spot, strike, t, r, q, p: HestonParams) -> float:
    """Pays 1 if S_T < K: e^{-rT} (1 - P2)."""
    return np.exp(-r * t) * (1.0 - exercise_probabilities(spot, strike, t, r, q, p)[1])


def black_scholes(spot, strike, t, r, q, vol, kind: str = "call") -> float:
    """Black-Scholes price with a continuous dividend yield."""
    d1 = (np.log(spot / strike) + (r - q + 0.5 * vol ** 2) * t) / (vol * np.sqrt(t))
    d2 = d1 - vol * np.sqrt(t)
    if kind == "call":
        return spot * np.exp(-q * t) * norm.cdf(d1) - strike * np.exp(-r * t) * norm.cdf(d2)
    return strike * np.exp(-r * t) * norm.cdf(-d2) - spot * np.exp(-q * t) * norm.cdf(-d1)


@dataclass(frozen=True)
class Simulation:
    """Index performances S_t / S_0 at the observation dates, and their minimum over the whole path."""
    obs: np.ndarray        # (n_paths, n_obs, n_assets)
    path_min: np.ndarray   # (n_paths, n_assets), minimum on the time grid up to the last date
    obs_times: tuple[float, ...]


def time_grid(obs_times, steps_per_year: int) -> tuple[int, list[int]]:
    """Number of steps and the step index of each observation date; every date must sit on the grid."""
    obs_idx = [int(round(t * steps_per_year)) for t in obs_times]
    for t, i in zip(obs_times, obs_idx):
        if abs(i / steps_per_year - t) > 1e-9:
            raise ValueError(f"observation time {t} is not on a {steps_per_year}-per-year grid")
    return obs_idx[-1], obs_idx


def simulate(params: list[HestonParams], drifts: list[float], spot_corr: float, obs_times,
             n_paths: int, seed: int = 42, steps_per_year: int = 52) -> Simulation:
    """Monte Carlo paths of one or two Heston indices: full-truncation Euler, antithetic variates.

    Spot shocks of the indices are correlated with the Cholesky factor of [[1, c], [c, 1]];
    each variance shock is then rho_i * own spot shock + sqrt(1 - rho_i^2) * independent noise.
    Full truncation: the variance may go below zero in the scheme, but only v+ = max(v, 0)
    enters the drift and the diffusion, so square roots are always defined.
    The same seed gives the same random numbers, which is what common random numbers need.
    """
    n_assets = len(params)
    v0, kappa, theta, xi, rho = (np.array([getattr(p, f) for p in params])
                                 for f in ("v0", "kappa", "theta", "xi", "rho"))
    drift = np.array(drifts)
    corr = np.array([[1.0, spot_corr], [spot_corr, 1.0]])[:n_assets, :n_assets]
    chol = np.linalg.cholesky(corr)

    n_steps, obs_idx = time_grid(obs_times, steps_per_year)
    dt = 1.0 / steps_per_year
    half = n_paths // 2
    n = 2 * half
    rng = np.random.default_rng(seed)

    # Arrays are (asset, path) so each asset's paths sit in one contiguous row.
    col = lambda x: x[:, None]
    v0, kappa, theta, xi, rho, drift = map(col, (v0, kappa, theta, xi, rho, drift))
    log_s = np.zeros((n_assets, n))
    v = np.repeat(v0, n, axis=1)
    min_log = np.zeros((n_assets, n))
    obs = np.empty((n, len(obs_idx), n_assets))
    next_obs = 0
    for step in range(1, n_steps + 1):
        z = rng.standard_normal((2 * n_assets, half))
        z = np.concatenate([z, -z], axis=1)               # antithetic: path i and i + half are mirrors
        w_spot = chol @ z[:n_assets]                       # correlated spot shocks
        w_vol = rho * w_spot + np.sqrt(1.0 - rho ** 2) * z[n_assets:]
        v_plus = np.maximum(v, 0.0)
        sqrt_vdt = np.sqrt(v_plus * dt)
        log_s += (drift - 0.5 * v_plus) * dt + sqrt_vdt * w_spot
        v += kappa * (theta - v_plus) * dt + xi * sqrt_vdt * w_vol
        np.minimum(min_log, log_s, out=min_log)
        while next_obs < len(obs_idx) and obs_idx[next_obs] == step:
            obs[:, next_obs, :] = np.exp(log_s).T
            next_obs += 1
    return Simulation(obs=obs, path_min=np.exp(min_log).T, obs_times=tuple(obs_times))
