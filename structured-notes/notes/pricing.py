"""Monte Carlo pricing, fair coupon, redemption probabilities and Greeks.

Every quantity is computed on common random numbers: the same seed means the
same shocks, so a difference between two prices comes from the bump, not from noise.
"""
from dataclasses import dataclass, replace

import numpy as np
from scipy.optimize import brentq

from notes import params as P
from notes.heston import HestonParams, Simulation, simulate
from notes.products import Product, worst_of


@dataclass(frozen=True)
class Market:
    """Everything the simulation needs besides the product."""
    indices: dict
    rates: dict
    spot_corr: float

    @classmethod
    def default(cls) -> "Market":
        return cls(P.INDICES, P.RATES, P.SPOT_CORRELATION)


@dataclass(frozen=True)
class PriceResult:
    price: float
    std_error: float
    n_paths: int

    @property
    def ci95(self) -> tuple[float, float]:
        return self.price - 1.96 * self.std_error, self.price + 1.96 * self.std_error


def shift_vol(p: HestonParams, vol_points: float) -> HestonParams:
    """Move the initial and long-run volatility by the same amount, e.g. +0.01 = +1 vol point."""
    return replace(p, v0=(np.sqrt(p.v0) + vol_points) ** 2, theta=(np.sqrt(p.theta) + vol_points) ** 2)


def run_simulation(product: Product, market: Market, n_paths: int = P.N_PATHS, seed: int = P.SEED,
                   vol_shift: float = 0.0, spot_corr: float | None = None,
                   vol_scale: float = 1.0) -> Simulation:
    """Simulate the product's underlyings, each drifting at its own rate minus its dividend yield."""
    inputs = [market.indices[name] for name in product.underlyings]
    heston = [shift_vol(i.heston, vol_shift) for i in inputs]
    if vol_scale != 1.0:
        heston = [replace(h, v0=h.v0 * vol_scale ** 2, theta=h.theta * vol_scale ** 2) for h in heston]
    drifts = [market.rates[i.currency] - i.dividend_yield for i in inputs]
    corr = market.spot_corr if spot_corr is None else spot_corr
    return simulate(heston, drifts, corr, product.obs_times, n_paths, seed, P.STEPS_PER_YEAR)


def outcome(product: Product, sim: Simulation, spot_move: float = 1.0):
    """Payoff on the simulated paths; spot_move rescales today's spot against fixed barriers.

    In Heston the returns do not depend on the spot level, so moving today's spot by
    a factor is the same as multiplying every path by that factor.
    """
    perf, path_min = worst_of(sim.obs * spot_move, sim.path_min * spot_move)
    return product.evaluate(perf, path_min)


def pair_values(product: Product, market: Market, sim: Simulation, spot_move: float = 1.0) -> np.ndarray:
    """Discounted value of each antithetic pair, averaged: these averages are independent draws."""
    discount = np.exp(-market.rates[product.currency] * np.array(sim.obs_times))
    pv = outcome(product, sim, spot_move).cashflows @ discount
    half = len(pv) // 2
    return 0.5 * (pv[:half] + pv[half:])


def price(product: Product, market: Market, sim: Simulation, spot_move: float = 1.0) -> PriceResult:
    """Monte Carlo price with its standard error (from the antithetic pair averages)."""
    values = pair_values(product, market, sim, spot_move)
    return PriceResult(float(values.mean()), float(values.std(ddof=1) / np.sqrt(len(values))), 2 * len(values))


def fair_coupon(product: Product, market: Market, sim: Simulation, target: float = 100.0) -> float:
    """Coupon per period that makes the note worth `target` on the same paths (root search)."""
    def gap(c: float) -> float:
        return price(replace(product, coupon=c), market, sim).price - target
    return brentq(gap, 0.0, 0.5, xtol=1e-8)


def probabilities(product: Product, sim: Simulation) -> dict:
    """Chance of redemption on each date, of a capital loss, and the expected life in years."""
    out = outcome(product, sim)
    m = len(sim.obs_times)
    by_date = np.bincount(out.end_index, minlength=m) / len(out.end_index)
    return {
        "redemption_by_date": by_date,
        "early_redemption": float(by_date[:-1].sum()),
        "capital_loss": float(out.capital_loss.mean()),
        "expected_life": float(np.array(sim.obs_times)[out.end_index].mean()),
    }


def greeks(product: Product, market: Market, sim: Simulation, n_paths: int = P.N_PATHS,
           seed: int = P.SEED, spot_bump: float = 0.01) -> dict:
    """Bump-and-reprice Greeks on common random numbers, in note points (% of notional).

    delta: price change for +1% of spot (central difference)
    gamma: change of that delta for +1% of spot
    vega:  price change for +1 vol point on initial and long-run volatility (central)
    corr:  price change for +0.10 of spot correlation (central), worst-of only
    """
    up = price(product, market, sim, 1 + spot_bump).price
    mid = price(product, market, sim).price
    down = price(product, market, sim, 1 - spot_bump).price
    result = {"delta": (up - down) / 2, "gamma": up - 2 * mid + down}
    vol_up = price(product, market, run_simulation(product, market, n_paths, seed, vol_shift=0.01)).price
    vol_down = price(product, market, run_simulation(product, market, n_paths, seed, vol_shift=-0.01)).price
    result["vega"] = (vol_up - vol_down) / 2
    if len(product.underlyings) == 2:
        c = market.spot_corr
        corr_up = price(product, market, run_simulation(product, market, n_paths, seed, spot_corr=c + 0.05)).price
        corr_down = price(product, market, run_simulation(product, market, n_paths, seed, spot_corr=c - 0.05)).price
        result["correlation"] = corr_up - corr_down
    return result
