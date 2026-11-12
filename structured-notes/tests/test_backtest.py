"""Backtest on a tiny hand-made series whose outcome is worked out by hand."""
import numpy as np
import pandas as pd
import pytest

from notes.backtest import run_backtest, summarise
from notes.products import Athena

# Business days, one constant level per month: Jan 100, Feb 105, Mar 90, Apr 50, May 80
DAYS = pd.bdate_range("2020-01-01", "2020-05-29")
LEVELS = {1: 100.0, 2: 105.0, 3: 90.0, 4: 50.0, 5: 80.0}
CLOSES = pd.DataFrame({"X": [LEVELS[d.month] for d in DAYS]}, index=DAYS)
NOTE = Athena("a", ("X",), "EUR", (1 / 12, 2 / 12), coupon=0.02, protection_barrier=0.6)


def test_backtest_matches_hand_computation():
    """
    Launch 1 Jan (100): 3 Feb at 105 >= 100, called on date 1, pays 102.
    Launch 3 Feb (105): 3 Mar at 90/105 no call; 3 Apr at 50/105 = 47.6% < 60%, pays 47.62.
    Launch 2 Mar (90):  2 Apr at 50/90 no call;  4 May at 80/90 = 88.9% >= 60%, pays 100.
    Launch 1 Apr: the second date (1 Jun) is past the history, so no launch.
    """
    results = run_backtest(NOTE, CLOSES)
    assert [d.date().isoformat() for d in results["launch"]] == ["2020-01-01", "2020-02-03", "2020-03-02"]
    assert list(results["end_index"]) == [0, 1, 1]
    assert np.allclose(results["total_paid"], [102.0, 100 * 50 / 105, 100.0])
    assert list(results["capital_loss"]) == [False, True, False]
    assert results["annual_return"].iloc[0] == pytest.approx(1.02 ** 12 - 1)

    summary = summarise(results, NOTE)
    assert np.allclose(summary["redemption_by_date"], [1 / 3, 2 / 3])
    assert summary["capital_loss"] == pytest.approx(1 / 3)
    assert summary["worst_launches"][0][0].isoformat() == "2020-02-03"
