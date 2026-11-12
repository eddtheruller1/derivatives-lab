# derivatives-lab

Two small projects on equity derivatives, on US and European indices. Both are plain Python (NumPy, SciPy, pandas, matplotlib), run offline on saved market data, and come with tests.

| Project | What it does |
|---|---|
| [vol-surface](vol-surface/) | Builds an implied volatility surface from listed option quotes on the S&P 500 (SPY) and the Euro Stoxx 50 (FEZ): forward from put-call parity, implied volatility solver, SVI fit per expiry, butterfly and calendar arbitrage checks, risk-neutral density, risk reversal and butterfly. |
| [structured-notes](structured-notes/) | Prices autocallable notes (Athena, Phoenix with memory coupon, worst-of) and barrier reverse convertibles under the Heston model by Monte Carlo: fair coupon, probabilities of early redemption and of capital loss, Greeks, and a historical backtest on the real index history. |

Each folder has its own `README.md` (how to run it, results, limits) and a `NOTES.md` (the maths behind it).

## Run

```
pip install -r vol-surface/requirements.txt
cd vol-surface && python run.py && python -m pytest -q
cd ../structured-notes && python run.py && python -m pytest -q
```

Salah Eddine Beraich
