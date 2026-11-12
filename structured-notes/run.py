"""Price the three reference notes, backtest them, and write figures and Markdown to output/.

Runs offline from data/*.csv (made once by fetch_history.py).
"""
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from notes import params as P
from notes.backtest import DATA_DIR, FILES, historical_estimates, load_closes, run_backtest, summarise
from notes.heston import heston_price
from notes.pricing import (Market, fair_coupon, greeks, pair_values, price, probabilities,
                           run_simulation)
from notes.products import Athena, EuropeanOption, Phoenix, every

OUT = Path(__file__).parent / "output"
CURVE_PATHS = 20_000   # fewer paths for the sensitivity curves, which need many resimulations

NOTES = [
    Athena("Athena on Euro Stoxx 50", ("SX5E",), "EUR", every(1.0, 5.0), coupon=0.090,
           autocall_barrier=1.00, protection_barrier=0.60),
    Phoenix("Phoenix memory on S&P 500", ("SPX",), "USD", every(0.25, 5.0), coupon=0.01625,
            autocall_barrier=1.00, coupon_barrier=0.70, capital_barrier=0.60),
    Phoenix("Phoenix memory worst-of Euro Stoxx 50 / S&P 500", ("SX5E", "SPX"), "EUR", every(0.25, 5.0),
            coupon=0.01875, autocall_barrier=1.00, coupon_barrier=0.70, capital_barrier=0.60),
]
SLUGS = ["athena_sx5e", "phoenix_spx", "phoenix_worstof"]


def periods_per_year(note) -> int:
    return int(round(1 / note.obs_times[0]))


def term_sheet_lines(note) -> list[str]:
    """Plain-words description of the note's terms."""
    freq = {1: "annual", 4: "quarterly"}[periods_per_year(note)]
    under = " and ".join(note.underlyings) + (" (worst-of)" if len(note.underlyings) > 1 else "")
    lines = [f"- Underlying: {under}", f"- Currency: {note.currency}, maturity {note.obs_times[-1]:g} years, {freq} observations",
             f"- Coupon: {100 * note.coupon:.2f}% per period ({100 * note.coupon * periods_per_year(note):.2f}% a year)",
             f"- Autocall barrier: {100 * note.autocall_barrier:.0f}% of initial level"]
    if isinstance(note, Athena):
        lines += ["- Coupons accumulate and are paid on early redemption or at maturity above the autocall barrier",
                  f"- Capital protection barrier at maturity: {100 * note.protection_barrier:.0f}%"]
    else:
        lines += [f"- Coupon barrier: {100 * note.coupon_barrier:.0f}%, with memory of missed coupons",
                  f"- Capital barrier at maturity: {100 * note.capital_barrier:.0f}%"]
    lines.append("- Below the capital barrier at maturity the investor gets the (worst) index performance")
    return lines


def payoff_chart(note, slug: str) -> None:
    """What the note pays at maturity on a path that stayed below every barrier until the last date."""
    final = np.linspace(0.2, 1.6, 561)
    m = len(note.obs_times)
    perf = np.column_stack([np.full((len(final), m - 1), 0.5), final])
    paid = note.evaluate(perf, perf.min(axis=1)).cashflows.sum(axis=1)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(100 * final, paid, color="#1f4e79", lw=2, label="total paid at maturity")
    ax.plot(100 * final, 100 * final, color="grey", ls="--", lw=1, label="index performance")
    for level, label in barriers(note):
        ax.axvline(100 * level, color="#c0504d", ls=":", lw=1)
        ax.text(100 * level, ax.get_ylim()[1] * 0.97, label, rotation=90, va="top", ha="right", fontsize=8)
    ax.set(xlabel="final level of the (worst) index, % of initial", ylabel="% of notional",
           title=f"{note.name}: payoff at maturity\n(path that never triggered an earlier barrier)")
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / f"{slug}_payoff.png", dpi=110)
    plt.close(fig)


def barriers(note) -> list[tuple[float, str]]:
    if isinstance(note, Athena):
        return [(note.protection_barrier, "protection"), (note.autocall_barrier, "autocall")]
    return [(note.capital_barrier, "capital"), (note.coupon_barrier, "coupon"), (note.autocall_barrier, "autocall")]


def spot_chart(note, market, sim, slug: str) -> None:
    """Price, delta and gamma against today's spot, with barriers fixed at the original fixing."""
    moves = np.linspace(0.5, 1.4, 91)
    prices = np.array([pair_values(note, market, sim, m).mean() for m in moves])
    step = 100 * (moves[1] - moves[0])
    delta = np.gradient(prices, step)            # note points per 1% of spot
    gamma = np.gradient(delta, step)
    fig, axes = plt.subplots(3, 1, figsize=(7, 8), sharex=True)
    for ax, y, label in zip(axes, (prices, delta, gamma), ("price", "delta (per 1% spot)", "gamma (per 1%²)")):
        ax.plot(100 * moves, y, color="#1f4e79", lw=1.8)
        ax.set_ylabel(label)
        for level, _ in barriers(note):
            ax.axvline(100 * level, color="#c0504d", ls=":", lw=1)
    axes[0].set_title(f"{note.name}\nsensitivity to spot (barriers dotted)", fontsize=10)
    axes[-1].set_xlabel("spot today, % of the initial fixing")
    fig.tight_layout()
    fig.savefig(OUT / f"{slug}_spot.png", dpi=110)
    plt.close(fig)


def vol_corr_chart(note, market, slug: str) -> None:
    """Price against a scaling of both indices' volatility, and against correlation for a worst-of."""
    scales = np.linspace(0.6, 1.4, 5)
    by_vol = [price(note, market, run_simulation(note, market, CURVE_PATHS, vol_scale=s)).price for s in scales]
    panels = 2 if len(note.underlyings) == 2 else 1
    fig, axes = plt.subplots(1, panels, figsize=(5 * panels, 3.8), squeeze=False)
    ax = axes[0, 0]
    base_vol = 100 * np.sqrt(market.indices[note.underlyings[0]].heston.theta)
    ax.plot(base_vol * scales, by_vol, "o-", color="#1f4e79")
    ax.set(xlabel=f"long-run and initial vol of {note.underlyings[0]} (%, others scaled alike)",
           ylabel="price, % of notional", title="price against volatility")
    if panels == 2:
        corrs = np.linspace(0.1, 0.95, 5)
        by_corr = [price(note, market, run_simulation(note, market, CURVE_PATHS, spot_corr=c)).price for c in corrs]
        axes[0, 1].plot(corrs, by_corr, "o-", color="#1f4e79")
        axes[0, 1].set(xlabel="spot correlation between the two indices", title="price against correlation")
    fig.suptitle(note.name, fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / f"{slug}_vol.png", dpi=110)
    plt.close(fig)


def convergence_chart(note, market, sim, slug: str) -> None:
    """Running Monte Carlo estimate and its 95% band as the number of paths grows."""
    values = pair_values(note, market, sim)
    counts = np.unique(np.geomspace(250, len(values), 30).astype(int))
    means = np.array([values[:c].mean() for c in counts])
    ses = np.array([values[:c].std(ddof=1) / np.sqrt(c) for c in counts])
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.fill_between(2 * counts, means - 1.96 * ses, means + 1.96 * ses, color="#9dc3e6", alpha=0.6, label="95% interval")
    ax.plot(2 * counts, means, color="#1f4e79", lw=1.8, label="estimate")
    ax.set(xscale="log", xlabel="number of paths", ylabel="price, % of notional",
           title=f"{note.name}: Monte Carlo convergence")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / f"{slug}_convergence.png", dpi=110)
    plt.close(fig)


def backtest_chart(note, results, slug: str) -> None:
    """Outcome of each historical launch: annualised return, coloured by how it ended."""
    m = len(note.obs_times)
    fig, ax = plt.subplots(figsize=(8, 3.8))
    colours = np.where(results["capital_loss"], "#c0504d", np.where(results["end_index"] < m - 1, "#1f4e79", "#f0a830"))
    ax.bar(results["launch"], 100 * results["annual_return"], width=25, color=colours)
    ax.axhline(0, color="black", lw=0.8)
    ax.set(ylabel="annualised return, %", xlabel="launch date",
           title=f"{note.name}: launched every month on real closes\n"
                 "blue = redeemed early, orange = ran to maturity without loss, red = capital loss")
    fig.tight_layout()
    fig.savefig(OUT / f"{slug}_backtest.png", dpi=110)
    plt.close(fig)


def write_term_sheet(note, slug, res, coupon, probs, grk, bt) -> None:
    ppy = periods_per_year(note)
    low, high = res.ci95
    lines = [f"# {note.name}", "", "## Terms", *term_sheet_lines(note), "",
             "## Model value (Heston Monte Carlo, illustrative parameters)",
             f"- Price: **{res.price:.2f}%** of notional, standard error {res.std_error:.2f}, "
             f"95% interval [{low:.2f}, {high:.2f}], {res.n_paths:,} paths",
             f"- Fair coupon (price = 100%): **{100 * coupon:.3f}% per period** ({100 * coupon * ppy:.2f}% a year)",
             f"- Probability of early redemption: {100 * probs['early_redemption']:.1f}%",
             f"- Probability of a capital loss at maturity: {100 * probs['capital_loss']:.1f}%",
             f"- Expected life: {probs['expected_life']:.2f} years", "",
             "| date (years) | " + " | ".join(f"{t:g}" for t in note.obs_times) + " |",
             "|---|" + "---|" * len(note.obs_times),
             "| redeemed here | " + " | ".join(f"{100 * p:.1f}%" for p in probs["redemption_by_date"]) + " |", "",
             "## Greeks (bump and reprice, common random numbers, in % of notional)",
             f"- Delta, +1% spot: {grk['delta']:+.3f}",
             f"- Gamma, change of delta for +1% spot: {grk['gamma']:+.4f}",
             f"- Vega, +1 vol point on initial and long-run vol: {grk['vega']:+.3f}"]
    if "correlation" in grk:
        lines.append(f"- Correlation, +0.10 on spot correlation: {grk['correlation']:+.3f}")
    lines += ["", "## Backtest on real closes", *backtest_lines(note, bt), "",
              "![payoff](%s_payoff.png)" % slug, "![spot](%s_spot.png)" % slug,
              "![vol](%s_vol.png)" % slug, "![convergence](%s_convergence.png)" % slug]
    if bt is not None:
        lines.append("![backtest](%s_backtest.png)" % slug)
    lines.append("")
    (OUT / f"{slug}.md").write_text("\n".join(lines), encoding="utf-8")


NO_HISTORY = "- Not run: no index history in data/. Run `python fetch_history.py`, then `python run.py` again."


def backtest_lines(note, bt) -> list[str]:
    if bt is None:
        return [NO_HISTORY]
    worst = ", ".join(f"{d} ({100 * r:+.1f}%)" for d, r in bt["worst_launches"])
    by_date = ", ".join(f"{t:g}y {100 * p:.0f}%" for t, p in zip(note.obs_times, bt["redemption_by_date"]) if p > 0)
    return [f"- {bt['launches']} monthly launches from {bt['first_launch'].date()} to {bt['last_launch'].date()}",
            f"- Redeemed early: {100 * bt['early_redemption']:.1f}%; ended with a capital loss: {100 * bt['capital_loss']:.1f}%",
            f"- Where they ended: {by_date}",
            f"- Annualised return: average {100 * bt['mean_annual_return']:+.2f}%, worst {100 * bt['worst_annual_return']:+.2f}%",
            f"- Worst launch dates: {worst}"]


def validation_lines(market) -> list[str]:
    """The engine against the closed form on a 1-year at-the-money Euro Stoxx 50 call."""
    call = EuropeanOption("call", ("SX5E",), "EUR", (1.0,), strike=1.0)
    res = price(call, market, run_simulation(call, market))
    sx = market.indices["SX5E"]
    exact = heston_price(100.0, 100.0, 1.0, market.rates["EUR"], sx.dividend_yield, sx.heston)
    low, high = res.ci95
    return [f"1-year at-the-money call on SX5E: closed form {exact:.4f}, Monte Carlo {res.price:.4f} "
            f"(se {res.std_error:.4f}, 95% [{low:.4f}, {high:.4f}])"]


def history_lines(market, has_history: bool) -> list[str]:
    """Realised variance and weekly correlation of the downloaded closes, next to the model inputs."""
    inputs = {n: market.indices[n].heston.theta for n in ("SX5E", "SPX")}
    if not has_history:
        return [NO_HISTORY]
    est = historical_estimates()
    lines = [f"Daily closes {est['start']} to {est['end']}."]
    for n, theta in inputs.items():
        v = est["variance"][n]
        lines.append(f"- {n}: realised variance {v:.4f} ({100 * np.sqrt(v):.1f}% vol); model long-run variance "
                     f"{theta:.4f} ({100 * np.sqrt(theta):.1f}% vol)")
    lines.append(f"- Weekly log-return correlation {est['weekly_correlation']:.3f}; model input {market.spot_corr:.2f}")
    return lines


def main() -> None:
    start = time.time()
    OUT.mkdir(exist_ok=True)
    market = Market.default()
    has_history = all((DATA_DIR / f).exists() for f in FILES.values())
    closes = load_closes(["SX5E", "SPX"]) if has_history else None
    table = ["| note | price (se) | 95% interval | fair coupon a year | P(early) | P(loss) | expected life | "
             "backtest early | backtest loss | backtest avg / worst return |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    details = []
    for note, slug in zip(NOTES, SLUGS):
        sim = run_simulation(note, market)
        res = price(note, market, sim)
        coupon = fair_coupon(note, market, sim)
        probs = probabilities(note, sim)
        grk = greeks(note, market, sim)
        bt_results = run_backtest(note, closes) if has_history else None
        bt = summarise(bt_results, note) if has_history else None
        payoff_chart(note, slug)
        spot_chart(note, market, sim, slug)
        vol_corr_chart(note, market, slug)
        convergence_chart(note, market, sim, slug)
        if has_history:
            backtest_chart(note, bt_results, slug)
        write_term_sheet(note, slug, res, coupon, probs, grk, bt)
        low, high = res.ci95
        table.append(f"| {note.name} | {res.price:.2f} ({res.std_error:.2f}) | [{low:.2f}, {high:.2f}] | "
                     f"{100 * coupon * periods_per_year(note):.2f}% | {100 * probs['early_redemption']:.1f}% | "
                     f"{100 * probs['capital_loss']:.1f}% | {probs['expected_life']:.2f}y | "
                     + (f"{100 * bt['early_redemption']:.1f}% | {100 * bt['capital_loss']:.1f}% | "
                        f"{100 * bt['mean_annual_return']:+.2f}% / {100 * bt['worst_annual_return']:+.2f}% |"
                        if bt else "not run | not run | not run |"))
        greek_text = ", ".join(f"{k} {v:+.3f}" for k, v in grk.items())
        details += [f"## {note.name}", f"Stated coupon {100 * note.coupon * periods_per_year(note):.2f}% a year. "
                    f"Greeks: {greek_text}.", "", *backtest_lines(note, bt), "", f"Term sheet: [{slug}.md]({slug}.md)", ""]
        print(f"{note.name}: {res.price:.2f} (se {res.std_error:.2f}), fair coupon {100 * coupon * periods_per_year(note):.2f}% a year")

    elapsed = time.time() - start
    lines = ["# Results", "", f"Run of run.py, {P.N_PATHS:,} paths, weekly grid, seed {P.SEED}, {elapsed:.0f} s.",
             "Prices are in % of notional, at the stated coupon; the fair coupon is the one that makes the price 100%.",
             "Model parameters are illustrative assumptions (see notes/params.py), not a calibration.", "",
             *table, "", "## Engine check", *validation_lines(market), "",
             "## History behind the assumptions", *history_lines(market, has_history), "", *details]
    (OUT / "results.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"done in {elapsed:.0f} s")


if __name__ == "__main__":
    main()
