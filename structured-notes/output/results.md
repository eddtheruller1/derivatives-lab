# Results

Run of run.py, 100,000 paths, weekly grid, seed 2026, 206 s.
Prices are in % of notional, at the stated coupon; the fair coupon is the one that makes the price 100%.
Model parameters are illustrative assumptions (see notes/params.py), not a calibration.

| note | price (se) | 95% interval | fair coupon a year | P(early) | P(loss) | expected life | backtest early | backtest loss | backtest avg / worst return |
|---|---|---|---|---|---|---|---|---|---|
| Athena on Euro Stoxx 50 | 97.95 (0.07) | [97.80, 98.09] | 10.97% | 71.4% | 12.5% | 2.41y | not run | not run | not run |
| Phoenix memory on S&P 500 | 99.53 (0.04) | [99.45, 99.60] | 7.13% | 91.4% | 3.7% | 0.96y | not run | not run | not run |
| Phoenix memory worst-of Euro Stoxx 50 / S&P 500 | 99.31 (0.06) | [99.19, 99.44] | 8.11% | 79.3% | 11.0% | 1.59y | not run | not run | not run |

## Engine check
1-year at-the-money call on SX5E: closed form 6.6964, Monte Carlo 6.7306 (se 0.0224, 95% [6.6868, 6.7744])

## History behind the assumptions
- Not run: no index history in data/. Run `python fetch_history.py`, then `python run.py` again.

## Athena on Euro Stoxx 50
Stated coupon 9.00% a year. Greeks: delta +0.401, gamma -0.024, vega -0.572.

- Not run: no index history in data/. Run `python fetch_history.py`, then `python run.py` again.

Term sheet: [athena_sx5e.md](athena_sx5e.md)

## Phoenix memory on S&P 500
Stated coupon 6.50% a year. Greeks: delta +0.068, gamma -0.016, vega -0.247.

- Not run: no index history in data/. Run `python fetch_history.py`, then `python run.py` again.

Term sheet: [phoenix_spx.md](phoenix_spx.md)

## Phoenix memory worst-of Euro Stoxx 50 / S&P 500
Stated coupon 7.50% a year. Greeks: delta +0.106, gamma -0.007, vega -0.563, correlation +0.184.

- Not run: no index history in data/. Run `python fetch_history.py`, then `python run.py` again.

Term sheet: [phoenix_worstof.md](phoenix_worstof.md)
