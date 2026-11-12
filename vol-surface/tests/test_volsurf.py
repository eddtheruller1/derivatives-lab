"""Tests for the vol-surface engine. No network: synthetic inputs only."""

import math

import numpy as np
import pandas as pd
import pytest

from volsurf import black
from volsurf.clean import apply_filters
from volsurf.forward import forward_given_df, implied_forward, regress_forward
from volsurf.implied import implied_vol, price_bounds
from volsurf.surface import Slice, Surface, desk_quotes, risk_neutral_density
from volsurf.svi import butterfly_check, calendar_check, fit_svi, svi_w


# ---------- Black-76 ----------

def test_black_known_values():
    # Hull, Options Futures and Other Derivatives, Black's model example:
    # F=20, K=20, T=4/12, r=9%, sigma=25% -> put = 1.1166 (Hull quotes 1.12).
    put = black.price(20.0, 20.0, 4 / 12, 0.09, 0.25, is_call=False)
    assert put == pytest.approx(1.1166, abs=1e-4)
    # ATM forward: call = put = DF F (2 N(sigma sqrt(T)/2) - 1)
    F, T, r, s = 100.0, 1.0, 0.05, 0.2
    expected = math.exp(-r * T) * F * (2 * 0.5398278372770290 - 1)  # N(0.1)
    assert black.price(F, F, T, r, s, True) == pytest.approx(expected, rel=1e-12)


def test_put_call_parity():
    F, T, r, s = 105.0, 0.75, 0.03, 0.3
    for K in (50.0, 90.0, 105.0, 140.0, 250.0):
        c = black.price(F, K, T, r, s, True)
        p = black.price(F, K, T, r, s, False)
        assert c - p == pytest.approx(math.exp(-r * T) * (F - K), abs=1e-10)


def test_greeks_match_finite_differences():
    F, K, T, r, s = 100.0, 110.0, 0.5, 0.04, 0.25
    h = 1e-4
    for call in (True, False):
        p = lambda f=F, t=T, v=s: black.price(f, K, t, r, v, call)
        assert black.delta(F, K, T, r, s, call) == pytest.approx((p(F + h) - p(F - h)) / (2 * h), rel=1e-6)
        assert black.theta(F, K, T, r, s, call) == pytest.approx(-(p(t=T + h) - p(t=T - h)) / (2 * h), rel=1e-5)
    assert black.gamma(F, K, T, r, s) == pytest.approx(
        (black.price(F + 1e-2, K, T, r, s) - 2 * black.price(F, K, T, r, s) + black.price(F - 1e-2, K, T, r, s)) / 1e-4,
        rel=1e-4)
    assert black.vega(F, K, T, r, s) == pytest.approx(
        (black.price(F, K, T, r, s + h) - black.price(F, K, T, r, s - h)) / (2 * h), rel=1e-6)


# ---------- implied vol ----------

@pytest.mark.parametrize("T", [0.02, 0.25, 1.0, 3.0])
@pytest.mark.parametrize("moneyness", [0.6, 0.8, 0.95, 1.0, 1.05, 1.25, 1.6])
@pytest.mark.parametrize("sigma", [0.08, 0.2, 0.5, 1.2])
@pytest.mark.parametrize("call", [True, False])
def test_solver_recovers_vol(T, moneyness, sigma, call):
    """From deep in the money to far out of the money, short to long maturity."""
    F, r = 100.0, 0.03
    K = F * moneyness
    px = black.price(F, K, T, r, sigma, call)
    lo, _ = price_bounds(F, K, T, r, call)
    if px - lo < 1e-9 * F:
        # Time value below double precision: no solver can recover sigma; it must say so.
        vol, why = implied_vol(px, F, K, T, r, call)
        assert math.isnan(vol) or vol == pytest.approx(sigma, abs=1e-2)
        return
    vol, why = implied_vol(px, F, K, T, r, call)
    assert why == "ok"
    assert vol == pytest.approx(sigma, abs=1e-6)


def test_solver_rejects_price_bound_violations():
    F, K, T, r = 100.0, 90.0, 0.5, 0.02
    df = math.exp(-r * T)
    vol, why = implied_vol(df * 10 - 0.01, F, K, T, r, True)  # below intrinsic
    assert math.isnan(vol) and "intrinsic" in why
    vol, why = implied_vol(df * F + 0.01, F, K, T, r, True)  # above the call upper bound
    assert math.isnan(vol) and "upper" in why
    vol, why = implied_vol(df * K + 1.0, F, K, T, r, False)  # above the put upper bound
    assert math.isnan(vol) and "upper" in why
    vol, why = implied_vol(float("nan"), F, K, T, r, True)
    assert math.isnan(vol) and why == "bad input"


# ---------- forward ----------

def make_chain(F: float, df: float, T: float, strikes, sigma: float = 0.2) -> pd.DataFrame:
    """A synthetic expiry with exact European prices and a small symmetric spread."""
    rows = []
    r = -math.log(df) / T
    for K in strikes:
        for kind in ("call", "put"):
            mid = black.price(F, K, T, r, sigma, kind == "call")
            rows.append({"strike": K, "type": kind, "bid": mid - 0.01, "ask": mid + 0.01, "openInterest": 100})
    return pd.DataFrame(rows)


def test_regression_recovers_forward_and_df():
    strikes = np.arange(80.0, 121.0, 2.5)
    F_hat, df_hat = regress_forward(strikes, 0.97 * (103.0 - strikes))
    assert F_hat == pytest.approx(103.0, rel=1e-12) and df_hat == pytest.approx(0.97, rel=1e-12)
    chain = make_chain(103.0, 0.97, 1.0, strikes)
    F, df, n = implied_forward(chain, spot=100.0)
    assert F == pytest.approx(103.0, abs=1e-8)
    assert df == pytest.approx(0.97, abs=1e-10)
    F2, _ = forward_given_df(chain, 100.0, 0.97)
    assert F2 == pytest.approx(103.0, abs=1e-8)


# ---------- filters ----------

def test_filters_are_named_and_counted():
    q = pd.DataFrame({
        "strike": [80, 90, 100, 110, 120, 300],
        "type": ["put", "put", "call", "call", "call", "call"],
        "bid": [0.0, 1.0, 2.0, 1.0, 0.5, 0.1],
        "ask": [0.1, 3.0, 2.2, 1.1, 0.55, 0.12],
        "openInterest": [5, 5, 5, 0, 5, 5],
    })
    kept, removed = apply_filters(q, F=100.0, T=0.5)
    assert removed == {"zero_bid": 1, "wide_spread": 1, "no_open_interest": 1, "far_wing": 1, "not_otm": 0}
    assert kept["strike"].tolist() == [100, 120]


# ---------- SVI ----------

def test_svi_recovers_known_parameters():
    true = np.array([0.02, 0.12, -0.6, 0.05, 0.15])
    T = 0.5
    k = np.linspace(-0.6, 0.4, 41)
    vol = np.sqrt(svi_w(k, *true) / T)
    fitted = fit_svi(k, vol, T)
    np.testing.assert_allclose(fitted, true, atol=1e-4)


def test_butterfly_check_flags_arbitrage():
    # Axel Vogt's raw SVI slice, the standard example of butterfly arbitrage (Gatheral & Jacquier 2014).
    vogt = [-0.0410, 0.1331, 0.3060, 0.3586, 0.4153]
    result = butterfly_check(vogt, np.linspace(-1.5, 1.5, 601))
    assert not result["ok"] and result["min_g"] < 0
    clean = butterfly_check([0.02, 0.12, -0.6, 0.05, 0.15], np.linspace(-1.5, 1.5, 601))
    assert clean["ok"]


def test_calendar_check_flags_crossing():
    grid = np.linspace(-0.5, 0.5, 101)
    short = [0.04, 0.1, -0.5, 0.0, 0.1]
    assert calendar_check(short, [0.06, 0.1, -0.5, 0.0, 0.1], grid)["ok"]
    assert not calendar_check(short, [0.03, 0.1, -0.5, 0.0, 0.1], grid)["ok"]


# ---------- surface ----------

def test_surface_interpolates_total_variance_and_density_integrates():
    flat = lambda T, v: Slice(T, 100.0, 0.0, np.array([v**2 * T, 0.0, 0.0, 0.0, 0.1]))
    surf = Surface([flat(1.0, 0.3), flat(0.5, 0.2)])
    # halfway between in T: w = (0.02 + 0.09) / 2 = 0.055 at T=0.75
    assert surf.implied_vol(100.0, 0.75) == pytest.approx(math.sqrt(0.055 / 0.75), rel=1e-12)
    sl = flat(0.5, 0.2)
    strikes = np.linspace(20, 300, 4001)
    q = risk_neutral_density(sl, strikes)
    assert np.nansum(q) * (strikes[1] - strikes[0]) == pytest.approx(1.0, abs=1e-3)
    quotes = desk_quotes(sl)
    assert quotes["atm"] == pytest.approx(0.2) and quotes["rr25"] == pytest.approx(0, abs=1e-12)
    assert quotes["bf25"] == pytest.approx(0, abs=1e-12)
