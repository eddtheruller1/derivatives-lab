"""Term sheets and payoffs.

Every payoff works on index performances (level / initial fixing) at the
observation dates, already reduced to one number per date: the index itself,
or the worse of two indices for a worst-of. Amounts are in % of notional.
"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Outcome:
    cashflows: np.ndarray     # (n_paths, n_obs): amount paid on each observation date
    end_index: np.ndarray     # (n_paths,): observation date on which the note ended
    capital_loss: np.ndarray  # (n_paths,): redeemed below 100% of notional


@dataclass(frozen=True)
class Athena:
    """Athena autocall.

    On each observation date before maturity: if the underlying is at or above the
    autocall barrier, the note redeems at 100% plus every coupon accrued so far.
    At maturity: at or above the autocall barrier, 100% plus all coupons; at or above
    the protection barrier, 100%; below it, the investor gets the performance (loses 1:1).
    """
    name: str
    underlyings: tuple[str, ...]
    currency: str
    obs_times: tuple[float, ...]     # years from the strike date
    coupon: float                    # per observation period, as a fraction of notional
    autocall_barrier: float = 1.00
    protection_barrier: float = 0.60

    def evaluate(self, perf: np.ndarray, path_min: np.ndarray) -> Outcome:
        n, m = perf.shape
        cashflows = np.zeros((n, m))
        end_index = np.full(n, m - 1)
        alive = np.ones(n, dtype=bool)
        for k in range(m - 1):
            called = alive & (perf[:, k] >= self.autocall_barrier)
            cashflows[called, k] = 100.0 * (1.0 + (k + 1) * self.coupon)
            end_index[called] = k
            alive &= ~called
        final = perf[:, -1]
        above_call = alive & (final >= self.autocall_barrier)
        protected = alive & ~above_call & (final >= self.protection_barrier)
        loss = alive & (final < self.protection_barrier)
        cashflows[above_call, -1] = 100.0 * (1.0 + m * self.coupon)
        cashflows[protected, -1] = 100.0
        cashflows[loss, -1] = 100.0 * final[loss]
        return Outcome(cashflows, end_index, loss)


@dataclass(frozen=True)
class Phoenix:
    """Phoenix autocall with memory coupon.

    On each observation date: at or above the coupon barrier, the coupon is paid,
    plus every coupon missed before (memory). Before maturity, at or above the
    autocall barrier, the note also redeems at 100%. At maturity: 100% if at or
    above the capital barrier, otherwise the performance.
    """
    name: str
    underlyings: tuple[str, ...]
    currency: str
    obs_times: tuple[float, ...]
    coupon: float                    # per observation period
    autocall_barrier: float = 1.00
    coupon_barrier: float = 0.70
    capital_barrier: float = 0.60
    memory: bool = True

    def evaluate(self, perf: np.ndarray, path_min: np.ndarray) -> Outcome:
        n, m = perf.shape
        cashflows = np.zeros((n, m))
        end_index = np.full(n, m - 1)
        alive = np.ones(n, dtype=bool)
        missed = np.zeros(n)
        for k in range(m):
            pays = alive & (perf[:, k] >= self.coupon_barrier)
            catch_up = missed[pays] if self.memory else 0.0
            cashflows[pays, k] += 100.0 * self.coupon * (1.0 + catch_up)
            missed = np.where(pays, 0.0, missed + 1.0)
            if k < m - 1:
                called = alive & (perf[:, k] >= self.autocall_barrier)
                cashflows[called, k] += 100.0
                end_index[called] = k
                alive &= ~called
        final = perf[:, -1]
        loss = alive & (final < self.capital_barrier)
        cashflows[alive, -1] += np.where(loss[alive], 100.0 * final[alive], 100.0)
        return Outcome(cashflows, end_index, loss)


@dataclass(frozen=True)
class BarrierReverseConvertible:
    """Barrier reverse convertible: a bond paying a fixed coupon, minus a down-and-in put.

    The coupon is paid on every date whatever happens. At maturity the note repays
    100%, unless the underlying touched the barrier at any time during the life
    (monitored on the simulation grid, or daily in the backtest) and ends below its
    strike: then the investor gets the performance.
    """
    name: str
    underlyings: tuple[str, ...]
    currency: str
    obs_times: tuple[float, ...]
    coupon: float
    barrier: float = 0.60
    strike: float = 1.00

    def evaluate(self, perf: np.ndarray, path_min: np.ndarray) -> Outcome:
        n, m = perf.shape
        cashflows = np.full((n, m), 100.0 * self.coupon)
        final = perf[:, -1]
        loss = (path_min < self.barrier) & (final < self.strike)
        cashflows[:, -1] += np.where(loss, 100.0 * final / self.strike, 100.0)
        return Outcome(cashflows, np.full(n, m - 1), loss)


@dataclass(frozen=True)
class EuropeanOption:
    """Plain European call or put on 100 of notional, used only to validate the engine."""
    name: str
    underlyings: tuple[str, ...]
    currency: str
    obs_times: tuple[float, ...]     # one date: the expiry
    strike: float                    # as a fraction of the initial level
    kind: str = "call"
    coupon: float = 0.0

    def evaluate(self, perf: np.ndarray, path_min: np.ndarray) -> Outcome:
        final = perf[:, -1]
        intrinsic = final - self.strike if self.kind == "call" else self.strike - final
        cashflows = 100.0 * np.maximum(intrinsic, 0.0)[:, None]
        n = len(final)
        return Outcome(cashflows, np.zeros(n, dtype=int), np.zeros(n, dtype=bool))


Product = Athena | Phoenix | BarrierReverseConvertible | EuropeanOption


def worst_of(perf: np.ndarray, path_min: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Reduce (n_paths, n_obs, n_assets) to the worse index on each date.

    For the path minimum, the lowest point of the worse index is the lowest
    of each index's own minimum, so the minimum over assets is enough.
    """
    return perf.min(axis=2), path_min.min(axis=1)


def every(period_years: float, maturity_years: float) -> tuple[float, ...]:
    """Observation schedule: one date every period up to maturity, e.g. every(0.25, 5)."""
    count = int(round(maturity_years / period_years))
    return tuple(round(period_years * (k + 1), 10) for k in range(count))
