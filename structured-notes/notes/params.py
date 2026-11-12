"""Model inputs. Every number here is an illustrative assumption, not a calibration.

None of these values is fitted to option quotes. The long-run variances and the
spot correlation are round values meant to sit close to the realised history of
the indices; run.py measures that history from data/ and prints it next to these
inputs in output/results.md, so the choice can be checked. The other Heston
values are typical of equity indices in published calibrations. Calibrating them to a
real implied volatility surface is the natural next step.
"""
from dataclasses import dataclass

from notes.heston import HestonParams


@dataclass(frozen=True)
class IndexInputs:
    heston: HestonParams
    currency: str
    dividend_yield: float   # continuous, flat


INDICES = {
    "SX5E": IndexInputs(
        heston=HestonParams(
            v0=0.045,     # assumption: start at the long-run level
            kappa=2.0,    # assumption: typical index mean reversion (half-life about 4 months)
            theta=0.045,  # assumption: 21.2% vol, near the long-run realised vol of the index (checked in results.md)
            xi=0.60,      # assumption: typical index vol of vol
            rho=-0.70,    # assumption: typical index spot-vol correlation (skew)
        ),
        currency="EUR",
        dividend_yield=0.030,  # assumption: round Euro Stoxx 50 dividend yield
    ),
    "SPX": IndexInputs(
        heston=HestonParams(
            v0=0.037,     # assumption: start at the long-run level
            kappa=2.0,    # assumption: typical index mean reversion
            theta=0.037,  # assumption: 19.2% vol, near the long-run realised vol of the index (checked in results.md)
            xi=0.60,      # assumption: typical index vol of vol
            rho=-0.75,    # assumption: typical S&P 500 spot-vol correlation
        ),
        currency="USD",
        dividend_yield=0.013,  # assumption: round S&P 500 dividend yield
    ),
}

RATES = {
    "EUR": 0.020,  # assumption: flat EUR rate, round number near short-term euro rates
    "USD": 0.040,  # assumption: flat USD rate, round number near short-term dollar rates
}

# Assumption: near the correlation of weekly log returns of the two indices
# (measured in results.md). Weekly, because the two markets close at different hours and daily returns
# would understate the correlation.
SPOT_CORRELATION = 0.75

N_PATHS = 100_000      # Monte Carlo paths for the reference prices
STEPS_PER_YEAR = 52    # weekly grid; every observation date sits on it
SEED = 2026
