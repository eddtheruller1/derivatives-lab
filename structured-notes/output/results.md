# Results

Run of run.py, 100,000 paths, weekly grid, seed 2026, 167 s.
Prices are in % of notional, at the stated coupon; the fair coupon is the one that makes the price 100%.
Model parameters are illustrative assumptions (see notes/params.py), not a calibration.

| note | price (se) | 95% interval | fair coupon a year | P(early) | P(loss) | expected life | backtest early | backtest loss | backtest avg / worst return |
|---|---|---|---|---|---|---|---|---|---|
| Athena on Euro Stoxx 50 | 97.95 (0.07) | [97.80, 98.09] | 10.97% | 71.4% | 12.5% | 2.41y | 80.9% | 5.3% | +6.65% / -14.61% |
| Phoenix memory on S&P 500 | 99.53 (0.04) | [99.45, 99.60] | 7.13% | 91.4% | 3.7% | 0.96y | 93.9% | 0.0% | +6.55% / +5.79% |
| Phoenix memory worst-of Euro Stoxx 50 / S&P 500 | 99.31 (0.06) | [99.19, 99.44] | 8.11% | 79.3% | 11.0% | 1.59y | 88.9% | 3.4% | +6.84% / -11.34% |

## Engine check
1-year at-the-money call on SX5E: closed form 6.6964, Monte Carlo 6.7306 (se 0.0224, 95% [6.6868, 6.7744])

## History behind the assumptions
Daily closes 2000-01-03 to 2026-10-06.
- SX5E: realised variance 0.0483 (22.0% vol); model long-run variance 0.0450 (21.2% vol)
- SPX: realised variance 0.0370 (19.2% vol); model long-run variance 0.0370 (19.2% vol)
- Weekly log-return correlation 0.781; model input 0.75

## Athena on Euro Stoxx 50
Stated coupon 9.00% a year. Greeks: delta +0.401, gamma -0.024, vega -0.572.

- 262 monthly launches from 2000-01-03 to 2021-10-01
- Redeemed early: 80.9%; ended with a capital loss: 5.3%
- Where they ended: 1y 56%, 2y 11%, 3y 6%, 4y 8%, 5y 19%
- Annualised return: average +6.65%, worst -14.61%
- Worst launch dates: 2007-06-01 (-14.6%), 2007-07-02 (-12.5%), 2007-05-02 (-12.3%), 2000-05-02 (-11.5%), 2007-08-01 (-11.2%)

Term sheet: [athena_sx5e.md](athena_sx5e.md)

## Phoenix memory on S&P 500
Stated coupon 6.50% a year. Greeks: delta +0.068, gamma -0.016, vega -0.247.

- 262 monthly launches from 2000-01-03 to 2021-10-01
- Redeemed early: 93.9%; ended with a capital loss: 0.0%
- Where they ended: 0.25y 67%, 0.5y 11%, 0.75y 6%, 1y 2%, 1.25y 1%, 1.5y 1%, 1.75y 0%, 2y 1%, 2.25y 0%, 2.5y 1%, 2.75y 0%, 3y 0%, 4y 1%, 4.25y 0%, 4.5y 1%, 4.75y 0%, 5y 6%
- Annualised return: average +6.55%, worst +5.79%
- Worst launch dates: 2000-04-03 (+5.8%), 2000-05-02 (+5.8%), 2000-07-03 (+5.8%), 2000-08-01 (+5.8%), 2000-09-01 (+5.8%)

Term sheet: [phoenix_spx.md](phoenix_spx.md)

## Phoenix memory worst-of Euro Stoxx 50 / S&P 500
Stated coupon 7.50% a year. Greeks: delta +0.106, gamma -0.007, vega -0.563, correlation +0.184.

- 262 monthly launches from 2000-01-03 to 2021-10-01
- Redeemed early: 88.9%; ended with a capital loss: 3.4%
- Where they ended: 0.25y 55%, 0.5y 11%, 0.75y 6%, 1y 3%, 1.25y 2%, 1.5y 2%, 1.75y 0%, 2y 0%, 2.25y 2%, 2.5y 2%, 2.75y 1%, 3y 0%, 3.5y 1%, 3.75y 1%, 4y 2%, 4.25y 0%, 4.5y 0%, 4.75y 0%, 5y 11%
- Annualised return: average +6.84%, worst -11.34%
- Worst launch dates: 2007-06-01 (-11.3%), 2007-07-02 (-10.1%), 2007-05-02 (-9.3%), 2007-10-01 (-9.0%), 2007-11-01 (-8.8%)

Term sheet: [phoenix_worstof.md](phoenix_worstof.md)
