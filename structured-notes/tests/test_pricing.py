"""Pricing checks against things that are known exactly."""
from dataclasses import replace

import numpy as np
import pytest

from notes import params as P
from notes.heston import heston_digital_put, heston_price
from notes.pricing import Market, fair_coupon, greeks, price, probabilities, run_simulation
from notes.products import Athena, EuropeanOption, Phoenix, every

MARKET = Market.default()
SX5E = P.INDICES["SX5E"]
R, Q = P.RATES["EUR"], SX5E.dividend_yield


def test_mc_call_matches_closed_form():
    call = EuropeanOption("c", ("SX5E",), "EUR", (1.0,), strike=1.0)
    result = price(call, MARKET, run_simulation(call, MARKET, n_paths=40_000, seed=11))
    exact = heston_price(100.0, 100.0, 1.0, R, Q, SX5E.heston)
    low, high = result.ci95
    assert low - 0.5 * result.std_error < exact < high + 0.5 * result.std_error


def test_athena_with_unreachable_autocall_is_bond_minus_put():
    """Never called, so: 100 at maturity, minus (1 - S_T) * 100 when S_T < 60%.

    That is a zero-coupon bond minus a 60-strike put minus 40 digital puts at 60.
    """
    t = 3.0
    note = Athena("a", ("SX5E",), "EUR", every(1.0, t), coupon=0.08, autocall_barrier=1e9)
    result = price(note, MARKET, run_simulation(note, MARKET, n_paths=40_000, seed=5))
    put = heston_price(100.0, 60.0, t, R, Q, SX5E.heston, "put")
    digital = heston_digital_put(100.0, 60.0, t, R, Q, SX5E.heston)
    exact = 100.0 * np.exp(-R * t) - put - 40.0 * digital
    assert abs(result.price - exact) < 3 * result.std_error + 0.05


def test_fair_coupon_reprices_to_par():
    note = Phoenix("p", ("SX5E", "SPX"), "EUR", every(0.25, 2.0), coupon=0.02)
    sim = run_simulation(note, MARKET, n_paths=10_000, seed=3)
    c = fair_coupon(note, MARKET, sim)
    assert price(replace(note, coupon=c), MARKET, sim).price == pytest.approx(100.0, abs=1e-5)


def test_probabilities_add_up():
    note = Athena("a", ("SX5E",), "EUR", every(1.0, 3.0), coupon=0.06)
    probs = probabilities(note, run_simulation(note, MARKET, n_paths=4_000, seed=2))
    assert probs["redemption_by_date"].sum() == pytest.approx(1.0)
    assert 1.0 <= probs["expected_life"] <= 3.0


def test_worst_of_needs_a_higher_coupon_and_gains_from_correlation():
    single = Phoenix("s", ("SX5E",), "EUR", every(0.25, 2.0), coupon=0.02)
    worst = replace(single, underlyings=("SX5E", "SPX"))
    c_single = fair_coupon(single, MARKET, run_simulation(single, MARKET, n_paths=10_000, seed=4))
    c_worst = fair_coupon(worst, MARKET, run_simulation(worst, MARKET, n_paths=10_000, seed=4))
    assert c_worst > c_single
    g = greeks(worst, MARKET, run_simulation(worst, MARKET, n_paths=10_000, seed=4), n_paths=10_000, seed=4)
    assert g["correlation"] > 0 and g["vega"] < 0 and g["delta"] > 0
