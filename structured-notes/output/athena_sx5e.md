# Athena on Euro Stoxx 50

## Terms
- Underlying: SX5E
- Currency: EUR, maturity 5 years, annual observations
- Coupon: 9.00% per period (9.00% a year)
- Autocall barrier: 100% of initial level
- Coupons accumulate and are paid on early redemption or at maturity above the autocall barrier
- Capital protection barrier at maturity: 60%
- Below the capital barrier at maturity the investor gets the (worst) index performance

## Model value (Heston Monte Carlo, illustrative parameters)
- Price: **97.95%** of notional, standard error 0.07, 95% interval [97.80, 98.09], 100,000 paths
- Fair coupon (price = 100%): **10.972% per period** (10.97% a year)
- Probability of early redemption: 71.4%
- Probability of a capital loss at maturity: 12.5%
- Expected life: 2.41 years

| date (years) | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| redeemed here | 54.2% | 10.1% | 4.5% | 2.7% | 28.6% |

## Greeks (bump and reprice, common random numbers, in % of notional)
- Delta, +1% spot: +0.401
- Gamma, change of delta for +1% spot: -0.0242
- Vega, +1 vol point on initial and long-run vol: -0.572

## Backtest on real closes
- 262 monthly launches from 2000-01-03 to 2021-10-01
- Redeemed early: 80.9%; ended with a capital loss: 5.3%
- Where they ended: 1y 56%, 2y 11%, 3y 6%, 4y 8%, 5y 19%
- Annualised return: average +6.65%, worst -14.61%
- Worst launch dates: 2007-06-01 (-14.6%), 2007-07-02 (-12.5%), 2007-05-02 (-12.3%), 2000-05-02 (-11.5%), 2007-08-01 (-11.2%)

![payoff](athena_sx5e_payoff.png)
![spot](athena_sx5e_spot.png)
![vol](athena_sx5e_vol.png)
![convergence](athena_sx5e_convergence.png)
![backtest](athena_sx5e_backtest.png)
