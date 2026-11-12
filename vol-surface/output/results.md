# Results, snapshot 2026-11-11

All numbers below come from `python run.py` on the saved snapshot.

## Quotes

| Underlying | Spot | Raw quotes | Kept for the fit | Expiries fitted |
|---|---:|---:|---:|---:|
| SPY | 755.80 | 3232 | 1234 | 8 of 8 |
| FEZ | 67.50 | 522 | 62 | 5 of 8 |

Quotes removed by each filter, applied in this order:

| Underlying | zero_bid | wide_spread | no_open_interest | far_wing | not_otm | iv failed |
|---|---:|---:|---:|---:|---:|---:|
| SPY | 45 | 188 | 751 | 168 | 846 | 0 |
| FEZ | 125 | 133 | 121 | 7 | 74 | 0 |

FEZ 2026-11-27 not fitted: only 0 usable quotes.

FEZ 2026-12-04 not fitted: only 0 usable quotes.

FEZ 2026-12-24 not fitted: only 0 usable quotes.

## Fit quality and desk quotes per expiry

RMSE and max error are in vol points (1 vol point = 1% implied vol), unweighted, over the kept quotes. ATM is at the forward; RR and BF are 25-delta, forward delta, in vol points. RR and BF in brackets need a 25-delta strike outside the quoted strikes: they are SVI extrapolation, not market data.

| Underlying | Expiry | T (y) | Forward | DF | Quotes | RMSE | Max err | ATM vol | RR 25d | BF 25d | min g(k) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SPY | 2026-11-23 | 0.033 | 756.56 | 1.0101 | 102 | 0.15 | 0.74 | 13.63 | -3.68 | +0.39 | 0.062 |
| SPY | 2026-11-30 | 0.052 | 757.20 | 1.0125 | 198 | 0.18 | 1.03 | 13.09 | -3.87 | +0.44 | 0.067 |
| SPY | 2026-12-11 | 0.082 | 758.42 | 1.0220 | 123 | 0.23 | 0.98 | 14.10 | -4.82 | +0.66 | 0.131 |
| SPY | 2026-12-31 | 0.137 | 757.98 | 1.0094 | 272 | 0.21 | 1.14 | 14.18 | -5.25 | +0.69 | 0.146 |
| SPY | 2027-02-19 | 0.274 | 762.11 | 1.0161 | 90 | 0.15 | 0.53 | 14.73 | -5.45 | +0.70 | 0.134 |
| SPY | 2027-04-16 | 0.427 | 765.88 | 1.0092 | 91 | 0.14 | 0.50 | 15.40 | -5.92 | +0.69 | 0.144 |
| SPY | 2027-06-30 | 0.633 | 771.62 | 1.0003 | 181 | 0.08 | 0.26 | 16.08 | -6.32 | +0.62 | 0.259 |
| SPY | 2028-01-21 | 1.195 | 787.65 | 0.9914 | 177 | 0.16 | 0.57 | 17.05 | -5.99 | +0.40 | 0.175 |
| FEZ | 2026-12-18 | 0.101 | 67.82 | 1.0176 | 7 | 0.09 | 0.16 | 17.75 | n/a | n/a | 0.497 |
| FEZ | 2027-01-15 | 0.178 | 67.43 | 1.0114 | 11 | 0.50 | 1.08 | 17.71 | (-1.55) | (+1.48) | 0.486 |
| FEZ | 2027-02-19 | 0.274 | 67.46 | 1.0161 | 12 | 0.48 | 0.83 | 20.08 | -3.47 | +0.13 | 0.714 |
| FEZ | 2027-05-21 | 0.523 | 67.64 | 1.0050 | 9 | 0.70 | 1.79 | 21.04 | (-0.64) | (+0.32) | 0.367 |
| FEZ | 2028-01-21 | 1.195 | 68.84 | 0.9914 | 23 | 0.05 | 0.10 | 20.07 | -5.15 | +0.53 | 0.353 |

DF: SPY's discount factors come from its own parity regression; FEZ's are SPY's, interpolated to FEZ's expiries, and FEZ's forward is then solved from its own parity with that DF fixed.


Average RMSE per underlying (mean of the slice RMSEs):

- SPY: 0.16 vol points
- FEZ: 0.37 vol points

## Static arbitrage checks

Butterfly: Gatheral's g(k) on 401 points across each slice's quoted log-moneyness range. Calendar: total variance of the longer expiry minus the shorter one on 201 points of their common range. Violations are reported, not patched.

| Underlying | Expiry | Butterfly | Where g < 0 (k) |
|---|---|---|---|
| SPY | 2026-11-23 | ok | - |
| SPY | 2026-11-30 | ok | - |
| SPY | 2026-12-11 | ok | - |
| SPY | 2026-12-31 | ok | - |
| SPY | 2027-02-19 | ok | - |
| SPY | 2027-04-16 | ok | - |
| SPY | 2027-06-30 | ok | - |
| SPY | 2028-01-21 | ok | - |
| FEZ | 2026-12-18 | ok | - |
| FEZ | 2027-01-15 | ok | - |
| FEZ | 2027-02-19 | ok | - |
| FEZ | 2027-05-21 | ok | - |
| FEZ | 2028-01-21 | ok | - |

| Underlying | Shorter | Longer | Calendar | Min of w_long - w_short | Where negative (k) |
|---|---|---|---|---:|---|
| SPY | 2026-11-23 | 2026-11-30 | ok | 0.00019 | - |
| SPY | 2026-11-30 | 2026-12-11 | ok | 0.00056 | - |
| SPY | 2026-12-11 | 2026-12-31 | ok | 0.00058 | - |
| SPY | 2026-12-31 | 2027-02-19 | ok | 0.00169 | - |
| SPY | 2027-02-19 | 2027-04-16 | ok | 0.00169 | - |
| SPY | 2027-04-16 | 2027-06-30 | ok | 0.00250 | - |
| SPY | 2027-06-30 | 2028-01-21 | ok | 0.00966 | - |
| FEZ | 2026-12-18 | 2027-01-15 | ok | 0.00181 | - |
| FEZ | 2027-01-15 | 2027-02-19 | ok | 0.00420 | - |
| FEZ | 2027-02-19 | 2027-05-21 | ok | 0.00963 | - |
| FEZ | 2027-05-21 | 2028-01-21 | ok | 0.01786 | - |

## SVI parameters

| Underlying | Expiry | a | b | rho | m | sigma |
|---|---|---:|---:|---:|---:|---:|
| SPY | 2026-11-23 | -0.0056 | 0.0409 | -0.5874 | -0.0675 | 0.1782 |
| SPY | 2026-11-30 | -0.0094 | 0.0516 | -0.4375 | -0.0423 | 0.2138 |
| SPY | 2026-12-11 | -0.0160 | 0.0831 | 0.1093 | 0.0766 | 0.2075 |
| SPY | 2026-12-31 | -0.0271 | 0.1267 | 0.2779 | 0.1362 | 0.2369 |
| SPY | 2027-02-19 | -0.0569 | 0.1722 | 0.1623 | 0.1574 | 0.3572 |
| SPY | 2027-04-16 | -0.0927 | 0.2362 | 0.2317 | 0.2320 | 0.4309 |
| SPY | 2027-06-30 | -0.0378 | 0.1561 | -0.0326 | 0.1564 | 0.3042 |
| SPY | 2028-01-21 | -0.2544 | 0.4072 | 0.3157 | 0.4909 | 0.7123 |
| FEZ | 2026-12-18 | -0.0060 | 3.9924 | 0.9884 | 0.1329 | 0.0143 |
| FEZ | 2027-01-15 | 0.0054 | 0.0269 | -0.6959 | -0.0171 | 0.0001 |
| FEZ | 2027-02-19 | -0.0046 | 0.0826 | -0.9908 | -0.3681 | 0.4148 |
| FEZ | 2027-05-21 | 0.0232 | 0.0592 | -0.9990 | -0.0813 | 0.0001 |
| FEZ | 2028-01-21 | 0.0248 | 0.1092 | -0.9887 | -0.0507 | 0.2590 |

## Risk-neutral density

- SPY 2027-02-19: the Breeden-Litzenberger density integrates to 0.990 over the quoted strike range (the rest of the probability lies beyond the quoted strikes).
- FEZ 2027-02-19: the Breeden-Litzenberger density integrates to 0.661 over the quoted strike range (the rest of the probability lies beyond the quoted strikes).
