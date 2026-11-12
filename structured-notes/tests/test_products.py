"""Payoff logic on hand-written paths."""
import numpy as np

from notes.products import Athena, BarrierReverseConvertible, EuropeanOption, Phoenix, worst_of

ATHENA = Athena("a", ("X",), "EUR", (1.0, 2.0, 3.0), coupon=0.06)
PHOENIX = Phoenix("p", ("X",), "EUR", (0.25, 0.5, 0.75, 1.0), coupon=0.02)


def paths(*rows):
    return np.array(rows, dtype=float)


def test_athena_redeems_on_first_date_above_barrier():
    out = ATHENA.evaluate(paths([0.9, 1.05, 1.2]), np.zeros(1))
    assert out.end_index[0] == 1
    assert np.allclose(out.cashflows[0], [0.0, 112.0, 0.0])   # 100 + 2 coupons of 6


def test_athena_at_maturity_protected_and_lost():
    out = ATHENA.evaluate(paths([0.9, 0.8, 1.0], [0.9, 0.8, 0.7], [0.9, 0.8, 0.5]), np.zeros(3))
    assert np.allclose(out.cashflows[:, -1], [118.0, 100.0, 50.0])
    assert list(out.capital_loss) == [False, False, True]


def test_phoenix_memory_coupon_catches_up():
    # below the coupon barrier twice, then back above it (but below autocall)
    out = PHOENIX.evaluate(paths([0.65, 0.60, 0.85, 0.9]), np.zeros(1))
    assert np.allclose(out.cashflows[0], [0.0, 0.0, 6.0, 102.0])  # 3 coupons on date 3, then coupon + 100


def test_phoenix_without_memory_loses_missed_coupons():
    no_memory = Phoenix("p", ("X",), "EUR", PHOENIX.obs_times, coupon=0.02, memory=False)
    out = no_memory.evaluate(paths([0.65, 0.60, 0.85, 0.9]), np.zeros(1))
    assert np.allclose(out.cashflows[0], [0.0, 0.0, 2.0, 102.0])


def test_phoenix_autocall_and_capital_loss():
    out = PHOENIX.evaluate(paths([0.8, 1.01, 0.5, 0.5], [0.8, 0.9, 0.9, 0.55]), np.zeros(2))
    assert out.end_index[0] == 1 and np.allclose(out.cashflows[0], [2.0, 102.0, 0.0, 0.0])
    assert out.capital_loss[1] and np.allclose(out.cashflows[1], [2.0, 2.0, 2.0, 55.0])


def test_barrier_reverse_convertible_knock_in():
    brc = BarrierReverseConvertible("b", ("X",), "EUR", (0.5, 1.0), coupon=0.03, barrier=0.6)
    perf = paths([0.9, 0.8], [0.9, 0.8], [0.9, 1.1])
    out = brc.evaluate(perf, np.array([0.7, 0.55, 0.5]))
    # never touched / touched and below strike / touched but back above strike
    assert np.allclose(out.cashflows[:, -1], [103.0, 83.0, 103.0])
    assert list(out.capital_loss) == [False, True, False]


def test_worst_of_picks_the_worse_index():
    perf = np.array([[[1.1, 0.9], [0.7, 1.2]]])          # one path, two dates, two indices
    path_min = np.array([[0.65, 0.85]])
    worst, worst_min = worst_of(perf, path_min)
    assert np.allclose(worst, [[0.9, 0.7]]) and np.allclose(worst_min, [0.65])
    out = Athena("w", ("X", "Y"), "EUR", (1.0, 2.0), coupon=0.05).evaluate(worst, worst_min)
    assert out.end_index[0] == 1 and out.capital_loss[0] == False and out.cashflows[0, -1] == 100.0


def test_european_payoffs():
    call = EuropeanOption("c", ("X",), "EUR", (1.0,), strike=1.0)
    put = EuropeanOption("p", ("X",), "EUR", (1.0,), strike=1.0, kind="put")
    perf = paths([1.2], [0.7])
    assert np.allclose(call.evaluate(perf, np.zeros(2)).cashflows[:, 0], [20.0, 0.0])
    assert np.allclose(put.evaluate(perf, np.zeros(2)).cashflows[:, 0], [0.0, 30.0])
