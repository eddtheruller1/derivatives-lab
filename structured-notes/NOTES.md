# What to be able to defend

## How each note decomposes

**Barrier reverse convertible.** Note = zero-coupon bond + coupons − down-and-in put (strike 100%, barrier 60%).
The investor sells the put to the issuer; the put premium, invested with the bond, pays the above-market coupon.
`Note = 100·e^{-rT} + Σ c·100·e^{-r t_i} − DIP(K=100, B=60)`.

**Athena.** Without the autocall, the note is a bond minus a put that only exists below the protection barrier at maturity:
`100·e^{-rT} − Put(K=60) − 40·DigitalPut(K=60)` (the payoff falls from 100 straight to 60 at the barrier, hence the digital).
The test `test_athena_with_unreachable_autocall_is_bond_minus_put` checks exactly this against the Heston closed form.
The autocall adds a strip of digital calls on each date (pay 100 + accrued coupons if S ≥ 100%), each knocked out if an earlier one paid.
The investor is **short the down-and-in put**; that premium plus the shortened life is what pays the coupon.

**Phoenix with memory.** Bond − down-and-in put at maturity + a strip of digital calls struck at the coupon barrier (the coupons),
with the autocall again as knock-out digitals. Memory makes each coupon digital path-dependent: it pays k coupons if the last k dates were missed.

**Worst-of.** The same pieces, written on min(S1/S1₀, S2/S2₀). The investor is short a put on the worse index, which is worth more than a put on either one alone.

## Why the seller is long volatility, and why volatility lowers the note

The investor is short options (the put above all, and the digitals near the barriers). Higher volatility makes the
down-and-in put more likely to end in the money, so it is worth more, and the note (bond minus put) is worth less: vega of the note is negative
(see the `vega` lines in `output/results.md`). The issuer is long that put, so it is long volatility; it hedges by selling volatility in the market.
Desks issuing many autocalls end up structurally long vol, short correlation and long dividends' risk — a known industry position.

## Worst-of and correlation

The worst of two indices falls below a barrier more often than either one alone, so the short put is larger and the coupon must be higher.
With lower correlation the two indices drift apart more, the minimum is lower, so the note is worth less:
the note is **long correlation** (positive correlation sensitivity in the results); the issuer is short correlation.
At correlation 1 with equal vols, the worst-of collapses to a single-index note.

## Why one flat Black-Scholes volatility misprices barriers

A barrier note depends on the whole distribution, especially the left tail and the dynamics of volatility when the market falls.
Equity indices have a skew: low strikes trade at higher implied vol. One flat vol either underprices the 60% put (if taken at the money) or
overprices the digitals near 100%. No single number fits both. Heston generates a skew from five parameters:

- `v0` initial variance: level of short-dated vol.
- `theta` long-run variance: level of long-dated vol.
- `kappa` mean-reversion speed: how fast short vol moves to long vol (term-structure shape).
- `xi` vol of vol: curvature of the smile (fat tails, prices of far out-of-the-money options).
- `rho` spot-vol correlation: the slope of the skew; negative because vol rises when markets fall.

`test_negative_spot_vol_correlation_gives_a_skew` shows that a 80% put under Heston is dearer than Black-Scholes at the Heston at-the-money vol.

## Full-truncation Euler

Euler on the variance: `v_{t+dt} = v_t + κ(θ − v_t)dt + ξ√v_t √dt Z`. For a large negative Z the step can make `v` negative, and the next `√v` fails.
Full truncation (Lord, Koekkoek, van Dijk 2010) keeps the raw `v` but uses `v⁺ = max(v, 0)` everywhere it enters drift and diffusion:
`v_{t+dt} = v_t + κ(θ − v_t⁺)dt + ξ√(v_t⁺ dt) Z`, `ln S_{t+dt} = ln S_t + (r − q − v_t⁺/2)dt + √(v_t⁺ dt) W`.
Among the simple fixes it has the smallest bias. It matters here because the Feller condition `2κθ ≥ ξ²` fails with the chosen inputs
(2·2·0.045 = 0.18 < 0.36), so the true variance touches zero often.

## Antithetic variates and common random numbers

Antithetic: each normal draw Z is used twice, as Z and −Z. The two payoffs are negatively correlated, so their average has less variance.
The standard error must be computed on the pair averages (they are independent), not on the 100,000 single paths.
Common random numbers: two prices to be subtracted (a bump, a coupon change) use the same seed, so the same shocks.
Their noise is almost the same and cancels in the difference; without it a vega of 0.3 points would be lost in noise of the same size.
For a spot bump, Heston returns do not depend on the spot level, so moving spot is just rescaling the same paths.

## Standard error

`price = mean(X)`, `se = std(X) / √N` with X the pair averages. 95% interval `price ± 1.96·se`. Error falls like `1/√N`:
four times the paths halves the error (see the convergence charts). The standard error measures only Monte Carlo noise,
not the Euler bias or the error of the model itself.

## Why gamma and vega jump near barriers

Near a barrier the payoff is a step (digital): one point lower at fixing pays 100% less coupon or loses 40% of capital.
Close to the last date the value of a digital becomes a step function of spot; its delta becomes a spike and its gamma changes sign across the barrier.
The trader hedging a note close to the 60% barrier near maturity faces huge, sign-changing delta and gamma: re-hedging costs explode and
can move the market (the "pin risk" at barriers). Desks smooth this with a barrier shift (book the barrier slightly lower, a reserve),
or by spreading the digital into a call spread. The charts `*_spot.png` show the delta and gamma moving fast around the barriers;
bump-and-reprice Greeks with a fixed bump are noisy there for the same reason.

# Twelve likely interview questions

1. **Why does the investor get a high coupon on an autocall?** They sell a down-and-in put to the issuer and accept early redemption; the coupon is that put premium plus interest, minus the issuer's margin.
2. **Is the issuer long or short vol on an autocall book?** Long vol (long the put the investor sold), short correlation on worst-ofs, long the forward / dividend risk. They sell vol in the market to offset.
3. **What happens to the note price when vol rises?** It falls: the put the investor is short is worth more. Our runs give negative vega on all three notes.
4. **Why is a worst-of coupon higher, and what does correlation do?** The minimum hits the barrier more often. Lower correlation lowers the minimum, so the note gains from higher correlation.
5. **Why Heston instead of Black-Scholes?** Barriers live in the tail; Heston gives a skew and stochastic vol from five parameters with a semi-closed form for vanillas, which makes calibration fast. Local vol or local-stochastic vol is what desks use for exotics; Heston is the step between.
6. **What does each Heston parameter do?** v0 short vol, θ long vol, κ speed between them, ξ smile curvature, ρ skew slope.
7. **Why the "little trap" form?** The original Heston formula takes a complex log that crosses its branch cut for long maturities and gives wrong prices; the Albrecher form keeps it continuous.
8. **Why full truncation?** Euler can make variance negative; full truncation uses max(v, 0) inside drift and diffusion and has the smallest bias of the simple fixes, important when Feller fails.
9. **How do you know your Monte Carlo is right?** It matches the closed-form European call inside its 95% interval, collapses to Black-Scholes when ξ → 0, an Athena with no autocall matches bond − put − digital, and payoffs are tested on hand-written paths.
10. **How do you compute Greeks and what is wrong with them?** Bump and reprice on common random numbers. Near barriers the payoff is discontinuous, so finite-difference delta and gamma are noisy and depend on the bump size; pathwise or likelihood-ratio methods, or smoothing the barrier, are better.
11. **What does the backtest tell a client and what does it not?** How the same note would have ended on every past month start: early redemption share, losses, returns. It is one history, launches overlap (not independent), and it ignores the price paid at launch.
12. **What is missing before this could price a real trade?** Calibration to the live vol surface (and a local-stoch vol model), dividend and rate curves, quanto adjustment for the S&P leg of a EUR note, issuer credit and funding spread, daily barrier monitoring, and proper Greeks.
