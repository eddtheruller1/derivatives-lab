# The maths behind vol-surface

Short notes on every formula the code uses, and why. Notation: F forward, K strike,
T maturity in years, DF = exp(-rT) discount factor, k = ln(K/F) log-moneyness,
sigma implied vol, w = sigma^2 T total implied variance, N and n the standard
normal cdf and pdf.

## 1. Black-76, and why price on the forward

    C = DF [F N(d1) - K N(d2)],   P = DF [K N(-d2) - F N(-d1)]
    d1 = (ln(F/K) + sigma^2 T / 2) / (sigma sqrt T),   d2 = d1 - sigma sqrt T

Black-Scholes on a spot needs a rate and a dividend yield; the forward
F = S exp((r - q) T) already contains both. So with F read from the market
(section 3), the only unknown left is sigma, and nobody has to guess the
dividends of 500 or 50 stocks. Greeks used (`black.py`): delta = DF N(d1)
(call) or -DF N(-d1) (put), with respect to F; gamma = DF n(d1) / (F sigma sqrt T);
vega = DF F n(d1) sqrt T; theta = r V - DF F n(d1) sigma / (2 sqrt T).

## 2. Implied vol is solved numerically, and Newton can fail

The price is strictly increasing in sigma (vega > 0), so each price inside the
no-arbitrage bounds DF max(F-K, 0) < C < DF F (put: DF max(K-F, 0) < P < DF K)
has exactly one implied vol, but there is no closed form for it. Newton's step
sigma_new = sigma - (BS(sigma) - price) / vega converges in 3 to 5 steps near the
money. It fails when vega is close to zero (far wings, very short maturities,
very low vol): the step becomes enormous and jumps to a negative or absurd vol.
`implied.py` therefore checks the bounds first (a price outside them has no
implied vol: NaN with a reason), runs Newton while each step stays in
[1e-6, 10], and otherwise falls back to Brent's method on that bracket, which
always converges because the price error changes sign across it.

## 3. Forward and discount factor from put-call parity

    C(K) - P(K) = DF (F - K) = DF F - DF K

Across strikes of one expiry, call mid minus put mid is a line in K: the slope
is -DF, the intercept DF F. An ordinary least-squares fit over near-the-money
strikes gives both. Near the money because both options are liquid there and,
for American options, the early-exercise premium is smallest. In this data the
forward is robust (SPY's forward moves by about 0.1 when the strike window
changes) but the slope is not: early exercise of in-the-money puts makes C - P
fall slightly faster than DF times K, so the fitted DF on SPY comes out slightly
above 1 at short maturities, and FEZ's six wide quotes per expiry cannot pin the
slope at all. FEZ therefore uses SPY's discount factors (both are dollar-listed
ETFs, so they discount at the same dollar rate) and only solves its forward,
F = mean(K + (C - P) / DF).

## 4. SVI: five parameters and what each does

    w(k) = a + b ( rho (k - m) + sqrt((k - m)^2 + sigma^2) )

- **a**: vertical level of total variance; raises or lowers the whole smile.
- **b**: angle between the two wings; the wings become straight lines in k with
  slopes b(1 + rho) on the right and -b(1 - rho) on the left. Roger Lee's moment
  formula says those slopes cannot exceed 2.
- **rho**: tilt, between -1 and 1. Negative rho makes the left (put) wing steeper:
  the equity skew.
- **m**: moves the smile left or right; the bottom sits near k = m.
- **sigma**: rounds the bottom; small sigma gives a sharp V, large sigma a flat U.

The fit minimises sum_i vega_i (svi_vol_i - market_vol_i)^2, from several
starting points because the problem is not convex, under bounds and a penalty
keeping the minimum variance a + b sigma sqrt(1 - rho^2) non-negative.
Weighting by vega makes the fit close to a fit on prices: a vol error times vega
is a price error, so quotes where a price tells little about vol (far wings)
weigh little.

## 5. Butterfly and calendar arbitrage

**Butterfly**: a long butterfly (buy K-h, sell 2 K, buy K+h) pays off at least
zero, so its price must be at least zero, which means call prices are convex in
strike. Equivalently the risk-neutral density is non-negative. For a smile given
in total variance, Gatheral shows the density is proportional to

    g(k) = (1 - k w'/(2w))^2 - (w'^2 / 4)(1/w + 1/4) + w''/2

so no butterfly arbitrage means g(k) >= 0 for every k. If g < 0 somewhere, a
butterfly around that strike costs less than nothing: free money.

**Calendar**: at a fixed log-moneyness, a longer option is worth at least a
shorter one (with the forward moving), which in total variance reads
w(k, T2) >= w(k, T1) for T2 > T1. If the curves cross, sell the longer and buy
the shorter for a credit. `svi.py` checks both on grids and reports the
violations; nothing is patched.

## 6. Breeden-Litzenberger

    q(K) = (1/DF) d2C/dK2

Differentiating the call price twice in strike gives the risk-neutral density of
the underlying at expiry. `surface.py` prices calls from the SVI smile on a fine
evenly spaced grid and takes central second differences. Against a lognormal
with the at-the-money vol, the market density has a fatter left tail and less
mass just above the forward: that is the skew, seen as probabilities.

## 7. Risk reversal and butterfly, the numbers a desk quotes

The smile is quoted by delta, not strike. With the forward delta N(d1) at each
strike's own vol, find the strike where the call delta is 0.25 and where the put
delta is -0.25. Then

    RR25 = vol(25d call) - vol(25d put)
    BF25 = (vol(25d call) + vol(25d put)) / 2 - vol(ATM)

RR measures skew (negative on equity indices: crash protection is expensive), BF
measures how convex the smile is (the price of fat tails on both sides). ATM is
taken at the forward (k = 0). This is the "smile" butterfly; FX desks also quote
a "broker" (market strangle) butterfly, which differs slightly.

## 12 likely interview questions

1. **Why Black-76 and not Black-Scholes on spot?** The forward already contains
   rates and dividends, and I read it from parity, so I avoid guessing a dividend
   yield. For a stock index that is the main source of error.
2. **These are American options. Isn't Black-76 wrong?** Strictly yes. I use
   out-of-the-money options only, where early exercise is almost never optimal, so
   the premium is small. It still shows: the parity discount factor of SPY comes
   out slightly above 1 at short maturities. A proper fix is a de-Americanisation
   step with a binomial tree.
3. **Why can Newton fail and what do you do?** Vega near zero makes the step
   explode. I check the price bounds first, keep each step inside a sane range,
   and fall back to Brent, which is guaranteed to converge on a bracket.
4. **Why fit total variance and not vol?** Total variance is what adds up over
   time; the no-calendar-arbitrage condition is simple in it, and SVI's wings are
   linear in it, which matches Lee's moment formula.
5. **What does each SVI parameter do?** a level, b wing angle, rho tilt, m shift,
   sigma curvature at the bottom (section 4).
6. **Why weight by vega?** A vol error times vega is a price error. Without the
   weight, far-wing quotes, whose vol jumps with every tick, would drive the fit.
7. **How do you know the surface is arbitrage-free?** I don't assume it: I check
   g(k) >= 0 on each slice and w non-decreasing in T between slices, and report
   any violation. SVI slices fitted independently are not guaranteed to pass;
   SSVI or constrained fits are the next step.
8. **What is the risk-neutral density used for?** Pricing any European payoff
   (digitals, call spreads), and reading the market's implied tail
   probabilities. It is not a forecast: it includes risk premia.
9. **Why is the equity skew negative?** Demand for downside protection, and
   volatility rising when markets fall (leverage effect), so out-of-the-money puts
   trade at higher vols than calls.
10. **Why is the US skew different from Europe's here?** Different index
    composition and demand; but here the European leg is a thin US-listed ETF, so
    part of any difference is liquidity, not economics. I would check on Euro
    Stoxx 50 index options on Eurex before concluding.
11. **How would you interpolate between maturities?** Linearly in total variance
    at fixed log-moneyness. It keeps calendar no-arbitrage if the slices have it.
12. **What would you improve first?** De-Americanise the quotes, take the rate
    from an OIS curve instead of parity, use real index options (SPX, SX5E), fit
    SSVI for an arbitrage-free surface by construction, and track the surface
    over many days instead of one snapshot.
