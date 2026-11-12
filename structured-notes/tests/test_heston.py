"""Closed form and Monte Carlo engine checks."""
import numpy as np
import pytest

from notes.heston import HestonParams, black_scholes, heston_price, simulate

PARAMS = HestonParams(v0=0.04, kappa=2.0, theta=0.04, xi=0.6, rho=-0.7)
S, T, R, Q = 100.0, 1.0, 0.02, 0.03


@pytest.mark.parametrize("strike", [80.0, 100.0, 120.0])
def test_collapses_to_black_scholes_without_vol_of_vol(strike):
    flat = HestonParams(v0=0.04, kappa=2.0, theta=0.04, xi=1e-5, rho=-0.7)  # the gap to BS shrinks linearly with xi * rho
    assert heston_price(S, strike, T, R, Q, flat) == pytest.approx(black_scholes(S, strike, T, R, Q, 0.2), abs=1e-4)


@pytest.mark.parametrize("strike", [70.0, 100.0, 130.0])
def test_put_call_parity(strike):
    for t in (0.25, 5.0):
        call = heston_price(S, strike, t, R, Q, PARAMS, "call")
        put = heston_price(S, strike, t, R, Q, PARAMS, "put")
        assert call - put == pytest.approx(S * np.exp(-Q * t) - strike * np.exp(-R * t), abs=1e-6)


def test_negative_spot_vol_correlation_gives_a_skew():
    """With rho < 0 a low-strike put is dearer than Black-Scholes at the at-the-money Heston vol."""
    from scipy.optimize import brentq
    atm = heston_price(S, 100.0, T, R, Q, PARAMS)
    atm_vol = brentq(lambda s: black_scholes(S, 100.0, T, R, Q, s) - atm, 0.01, 1.0)
    assert heston_price(S, 80.0, T, R, Q, PARAMS, "put") > black_scholes(S, 80.0, T, R, Q, atm_vol, "put")


def test_monte_carlo_european_inside_its_confidence_interval():
    sim = simulate([PARAMS], [R - Q], 0.0, (1.0,), n_paths=40_000, seed=7, steps_per_year=104)
    final = sim.obs[:, -1, 0] * S
    payoff = np.exp(-R * T) * np.maximum(final - 100.0, 0.0)
    pairs = 0.5 * (payoff[:20_000] + payoff[20_000:])
    se = pairs.std(ddof=1) / np.sqrt(len(pairs))
    # Euler bias is small next to 3 standard errors at this step size
    assert abs(pairs.mean() - heston_price(S, 100.0, T, R, Q, PARAMS)) < 3 * se


def test_two_assets_have_the_requested_spot_correlation():
    sim = simulate([PARAMS, PARAMS], [0.0, 0.0], 0.6, (1 / 52,), n_paths=40_000, seed=1)
    returns = np.log(sim.obs[:, 0, :])
    assert np.corrcoef(returns.T)[0, 1] == pytest.approx(0.6, abs=0.02)


def test_same_seed_gives_same_paths():
    a = simulate([PARAMS], [0.0], 0.0, (0.5, 1.0), n_paths=1000, seed=3)
    b = simulate([PARAMS], [0.0], 0.0, (0.5, 1.0), n_paths=1000, seed=3)
    assert np.array_equal(a.obs, b.obs)


def test_observation_dates_must_sit_on_the_grid():
    with pytest.raises(ValueError):
        simulate([PARAMS], [0.0], 0.0, (0.3,), n_paths=10, steps_per_year=52)
