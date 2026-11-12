"""Build the SPY and FEZ volatility surfaces from the saved snapshot and write output/.

Offline: reads only data/*.csv. Steps per expiry: implied forward from put-call
parity, quote filters, implied vols of out-of-the-money options, SVI fit,
arbitrage checks. Then figures and results.md.
"""

from collections import Counter
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from volsurf import black
from volsurf.clean import apply_filters
from volsurf.forward import forward_given_df, implied_forward
from volsurf.implied import implied_vols
from volsurf.surface import Slice, Surface, desk_quotes, lognormal_density, risk_neutral_density
from volsurf.svi import PARAM_NAMES, butterfly_check, calendar_check, fit_svi, svi_w

HERE = Path(__file__).parent
DATA, OUT = HERE / "data", HERE / "output"
UNDERLYINGS = {"SPY": "S&P 500 (SPY)", "FEZ": "Euro Stoxx 50 (FEZ)"}
COLORS = {"SPY": "#1f5fa8", "FEZ": "#c2571a"}
MIN_QUOTES = 6
DENSITY_TARGET_T = 0.25  # draw the risk-neutral density of the expiry closest to 3 months
# FEZ's chain is too thin to pin down the discount factor (the slope of the parity
# regression). FEZ and SPY are both USD-listed, so FEZ borrows SPY's discount curve
# and only its forward is solved from its own parity.
DF_FROM = {"FEZ": "SPY"}


def load_snapshot(symbol: str) -> pd.DataFrame:
    """The one saved CSV for this underlying."""
    files = sorted(DATA.glob(f"{symbol}_*.csv"))
    if not files:
        raise FileNotFoundError(f"no data/{symbol}_*.csv: run fetch_chain.py first")
    return pd.read_csv(files[-1])


def year_fraction(snapshot: str, expiry: str) -> float:
    """Calendar days / 365 from the snapshot close to expiry."""
    return (date.fromisoformat(expiry) - date.fromisoformat(snapshot)).days / 365.0


def discount_curve(u: dict):
    """DF(T) from an underlying's fitted slices, ln DF interpolated linearly in T."""
    rows = sorted(u["slices"].values(), key=lambda s: s["T"])
    T = np.array([s["T"] for s in rows])
    log_df = np.array([np.log(s["df"]) for s in rows])
    return lambda t: float(np.exp(np.interp(t, T, log_df)))


def build_slice(q: pd.DataFrame, spot: float, T: float, df_curve=None) -> dict:
    """Forward, filters, implied vols and SVI fit for one expiry."""
    F, df, n_parity = implied_forward(q, spot)
    df_source = "own parity regression"
    if df_curve is not None:
        df = df_curve(T)
        F, n_parity = forward_given_df(q, spot, df)
        df_source = "borrowed"
    r = -np.log(df) / T
    kept, removed = apply_filters(q, F, T)
    kept = kept.assign(mid=(kept["bid"] + kept["ask"]) / 2)
    vols, reasons = implied_vols(kept["mid"], F, kept["strike"], T, r, kept["type"] == "call")
    kept = kept.assign(iv=vols, iv_reason=reasons).dropna(subset=["iv"])
    kept = kept.assign(k=np.log(kept["strike"] / F), vega=black.vega(F, kept["strike"], T, r, kept["iv"]))
    out = {"T": T, "F": F, "df": df, "df_source": df_source, "r": r, "n_raw": len(q), "n_parity": n_parity,
           "removed": removed, "iv_failed": Counter(x for x in reasons if x != "ok"), "quotes": kept}
    if len(kept) < MIN_QUOTES:
        out["skip"] = f"only {len(kept)} usable quotes"
        return out
    params = fit_svi(kept["k"].to_numpy(), kept["iv"].to_numpy(), T, kept["vega"].to_numpy())
    err = np.sqrt(np.maximum(0, svi_w(kept["k"].to_numpy(), *params)) / T) - kept["iv"].to_numpy()
    out.update(params=params, rmse=float(np.sqrt(np.mean(err**2))), max_err=float(np.abs(err).max()),
               slice=Slice(T, F, r, params))
    out["butterfly"] = butterfly_check(params, np.linspace(kept["k"].min(), kept["k"].max(), 401))
    out.update(desk_quotes(out["slice"]))
    # RR and BF are only measured if both 25-delta strikes lie inside the quoted strikes.
    k = kept["k"]
    out["wings_quoted"] = bool(k.min() <= out["k_25p"] and out["k_25c"] <= k.max())
    return out


def build_underlying(symbol: str, df_curve=None) -> dict:
    """All slices, the surface and the calendar checks for one underlying."""
    raw = load_snapshot(symbol)
    spot, snap = float(raw["spot"].iloc[0]), str(raw["snapshot_date"].iloc[0])
    slices = {}
    for expiry, q in raw.groupby("expiry"):
        slices[expiry] = build_slice(q, spot, year_fraction(snap, expiry), df_curve)
    fitted = {e: s for e, s in slices.items() if "params" in s}
    calendar = []
    names = sorted(fitted, key=lambda e: fitted[e]["T"])
    for short, long in zip(names, names[1:]):
        a, b = fitted[short]["quotes"]["k"], fitted[long]["quotes"]["k"]
        grid = np.linspace(max(a.min(), b.min()), min(a.max(), b.max()), 201)
        calendar.append((short, long, calendar_check(fitted[short]["params"], fitted[long]["params"], grid)))
    surface = Surface([s["slice"] for s in fitted.values()])
    return {"symbol": symbol, "spot": spot, "snapshot": snap, "raw": raw, "slices": slices,
            "fitted": fitted, "calendar": calendar, "surface": surface}


# ---------- figures ----------

def plot_smiles(u: dict) -> str:
    """Market implied vols against the SVI curve, one panel per expiry."""
    fitted = sorted(u["fitted"].items(), key=lambda x: x[1]["T"])
    cols = 4
    rows = int(np.ceil(len(fitted) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(16, 3.6 * rows), squeeze=False)
    for ax, (expiry, s) in zip(axes.flat, fitted):
        q = s["quotes"]
        for kind, marker in (("put", "v"), ("call", "^")):
            part = q[q["type"] == kind]
            ax.scatter(part["k"], part["iv"] * 100, s=12, marker=marker, alpha=0.6, label=f"market {kind}s")
        grid = np.linspace(q["k"].min(), q["k"].max(), 200)
        ax.plot(grid, s["slice"].vol(grid) * 100, color="black", lw=1.4, label="SVI fit")
        ax.set_title(f"{expiry}  (T={s['T']:.2f}y)  RMSE {s['rmse'] * 100:.2f} vol pts", fontsize=9)
        ax.set_xlabel("log-moneyness ln(K/F)")
        ax.set_ylabel("implied vol (%)")
        ax.grid(alpha=0.3)
    for ax in list(axes.flat)[len(fitted):]:
        ax.axis("off")
    axes.flat[0].legend(fontsize=8)
    fig.suptitle(f"{UNDERLYINGS[u['symbol']]}: smile per expiry, snapshot {u['snapshot']}", fontsize=12)
    fig.tight_layout()
    name = f"smiles_{u['symbol']}.png"
    fig.savefig(OUT / name, dpi=110)
    plt.close(fig)
    return name


def plot_surfaces(units: list[dict]) -> str:
    """Heat map of implied vol over log-moneyness and maturity for each underlying."""
    fig, axes = plt.subplots(1, len(units), figsize=(7 * len(units), 4.8))
    for ax, u in zip(np.atleast_1d(axes), units):
        surf = u["surface"]
        rows = sorted(u["fitted"].values(), key=lambda s: s["T"])
        T = np.linspace(rows[0]["T"], rows[-1]["T"], 80)
        k = np.linspace(-0.3, 0.15, 90)
        vol = np.array([np.sqrt(surf.total_variance(k, t) / t) for t in T]) * 100
        # Show only the quoted region: outside it the colours would be SVI extrapolation.
        k_lo = np.interp(T, [s["T"] for s in rows], [s["quotes"]["k"].min() for s in rows])
        k_hi = np.interp(T, [s["T"] for s in rows], [s["quotes"]["k"].max() for s in rows])
        vol = np.where((k[None, :] < k_lo[:, None]) | (k[None, :] > k_hi[:, None]), np.nan, vol)
        mesh = ax.pcolormesh(k, T, vol, shading="auto", cmap="viridis", vmin=10, vmax=45)
        for s in surf.slices:
            ax.axhline(s.T, color="white", lw=0.5, alpha=0.5)
        fig.colorbar(mesh, ax=ax, label="implied vol (%)")
        ax.set_xlabel("log-moneyness ln(K/F)")
        ax.set_ylabel("maturity (years)")
        ax.set_title(f"{UNDERLYINGS[u['symbol']]}: quoted region only (white lines: fitted expiries)", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "surface_heatmap.png", dpi=110)
    plt.close(fig)
    return "surface_heatmap.png"


def plot_term_structure(units: list[dict]) -> str:
    """ATM vol, 25-delta risk reversal and 25-delta butterfly against maturity."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    for u in units:
        rows = sorted(u["fitted"].values(), key=lambda s: s["T"])
        for ax, key in zip(axes, ("atm", "rr25", "bf25")):
            # RR and BF only where both 25-delta strikes were quoted, never extrapolated
            pts = rows if key == "atm" else [s for s in rows if s["wings_quoted"]]
            ax.plot([s["T"] for s in pts], [s[key] * 100 for s in pts], "o-",
                    color=COLORS[u["symbol"]], label=UNDERLYINGS[u["symbol"]])
    for ax, title in zip(axes, ("ATM vol (%)", "25-delta risk reversal (vol pts)", "25-delta butterfly (vol pts)")):
        ax.set_title(title)
        ax.set_xlabel("maturity (years)")
        ax.grid(alpha=0.3)
    axes[1].axhline(0, color="grey", lw=0.8)
    axes[0].legend()
    fig.tight_layout()
    fig.savefig(OUT / "term_structure.png", dpi=110)
    plt.close(fig)
    return "term_structure.png"


def plot_density(u: dict) -> tuple[str, str, float]:
    """Breeden-Litzenberger density of the ~3-month expiry against a lognormal with the ATM vol."""
    expiry, s = min(u["fitted"].items(), key=lambda x: abs(x[1]["T"] - DENSITY_TARGET_T))
    sl = s["slice"]
    strikes = np.linspace(sl.F * np.exp(s["quotes"]["k"].min()), sl.F * np.exp(s["quotes"]["k"].max()), 400)
    q = risk_neutral_density(sl, strikes)
    ln = lognormal_density(sl.F, sl.T, s["atm"], strikes)
    mass = float(np.nansum(q) * (strikes[1] - strikes[0]))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(strikes, q, color=COLORS[u["symbol"]], lw=2, label="risk-neutral density from SVI (Breeden-Litzenberger)")
    ax.plot(strikes, ln, "--", color="grey", label=f"lognormal, flat ATM vol {s['atm'] * 100:.1f}%")
    ax.axvline(sl.F, color="black", lw=0.6, ls=":", label=f"forward {sl.F:.1f}")
    ax.set_xlabel(f"{u['symbol']} price at expiry {expiry}")
    ax.set_ylabel("density")
    ax.set_title(f"{UNDERLYINGS[u['symbol']]}: implied distribution at {expiry} (T={sl.T:.2f}y)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    name = f"density_{u['symbol']}.png"
    fig.savefig(OUT / name, dpi=110)
    plt.close(fig)
    return name, expiry, mass


def plot_skew_compare(us: dict, eu: dict) -> tuple[str, str, str]:
    """US against Europe smile at the closest pair of maturities near 3 months."""
    pick = lambda u: min(u["fitted"].items(), key=lambda x: abs(x[1]["T"] - DENSITY_TARGET_T))
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    chosen = []
    for u in (us, eu):
        expiry, s = pick(u)
        chosen.append(expiry)
        k = np.linspace(-0.25, 0.12, 200)
        v = s["slice"].vol(k)
        label = f"{UNDERLYINGS[u['symbol']]} {expiry}"
        axes[0].plot(k, v * 100, color=COLORS[u["symbol"]], label=label)
        z = k / (s["atm"] * np.sqrt(s["T"]))
        axes[1].plot(z, (v - s["atm"]) * 100, color=COLORS[u["symbol"]], label=label)
    axes[0].set_xlabel("log-moneyness ln(K/F)")
    axes[0].set_ylabel("implied vol (%)")
    axes[0].set_title("Smile level")
    axes[1].set_xlabel("standardised moneyness ln(K/F) / (ATM vol * sqrt(T))")
    axes[1].set_ylabel("vol minus ATM vol (vol pts)")
    axes[1].set_title("Smile shape, level removed")
    axes[1].set_xlim(-3, 1.5)
    for ax in axes:
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "skew_us_vs_europe.png", dpi=110)
    plt.close(fig)
    return "skew_us_vs_europe.png", chosen[0], chosen[1]


# ---------- results.md ----------

def fmt_k(x) -> str:
    return "-" if x is None else f"{x:+.3f}"


def wing(s: dict, key: str) -> str:
    """RR or BF in vol points; bracketed if extrapolated, n/a if no 25-delta strike was found."""
    if not np.isfinite(s[key]):
        return "n/a"
    text = f"{s[key] * 100:+.2f}"
    return text if s["wings_quoted"] else f"({text})"


def results_markdown(units: list[dict], extras: dict) -> str:
    """Fit quality, desk quotes, filter counts and arbitrage checks, from this run only."""
    lines = [f"# Results, snapshot {units[0]['snapshot']}", ""]
    lines += ["All numbers below come from `python run.py` on the saved snapshot.", ""]
    lines += ["## Quotes", "", "| Underlying | Spot | Raw quotes | Kept for the fit | Expiries fitted |",
              "|---|---:|---:|---:|---:|"]
    for u in units:
        kept = sum(len(s["quotes"]) for s in u["fitted"].values())
        lines.append(f"| {u['symbol']} | {u['spot']:.2f} | {len(u['raw'])} | {kept} | {len(u['fitted'])} of {len(u['slices'])} |")
    lines += ["", "Quotes removed by each filter, applied in this order:", "",
              "| Underlying | zero_bid | wide_spread | no_open_interest | far_wing | not_otm | iv failed |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for u in units:
        tot = Counter()
        fails = Counter()
        for s in u["slices"].values():
            tot.update(s["removed"])
            fails.update(s["iv_failed"])
        lines.append(f"| {u['symbol']} | " + " | ".join(str(tot[r]) for r in
                     ("zero_bid", "wide_spread", "no_open_interest", "far_wing", "not_otm")) + f" | {sum(fails.values())} |")
    for u in units:
        skipped = {e: s["skip"] for e, s in u["slices"].items() if "skip" in s}
        for e, why in skipped.items():
            lines.append(f"\n{u['symbol']} {e} not fitted: {why}.")
    lines += ["", "## Fit quality and desk quotes per expiry", "",
              "RMSE and max error are in vol points (1 vol point = 1% implied vol), unweighted, over the kept quotes. "
              "ATM is at the forward; RR and BF are 25-delta, forward delta, in vol points. "
              "RR and BF in brackets need a 25-delta strike outside the quoted strikes: they are SVI extrapolation, not market data.", "",
              "| Underlying | Expiry | T (y) | Forward | DF | Quotes | RMSE | Max err | ATM vol | RR 25d | BF 25d | min g(k) |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for u in units:
        for e, s in sorted(u["fitted"].items(), key=lambda x: x[1]["T"]):
            lines.append(f"| {u['symbol']} | {e} | {s['T']:.3f} | {s['F']:.2f} | {s['df']:.4f} | {len(s['quotes'])} | "
                         f"{s['rmse'] * 100:.2f} | {s['max_err'] * 100:.2f} | {s['atm'] * 100:.2f} | "
                         f"{wing(s, 'rr25')} | {wing(s, 'bf25')} | {s['butterfly']['min_g']:.3f} |")
    lines += ["", "DF: SPY's discount factors come from its own parity regression; FEZ's are SPY's, "
              "interpolated to FEZ's expiries, and FEZ's forward is then solved from its own parity with that DF fixed.", ""]
    lines += ["", "Average RMSE per underlying (mean of the slice RMSEs):", ""]
    for u in units:
        lines.append(f"- {u['symbol']}: {np.mean([s['rmse'] for s in u['fitted'].values()]) * 100:.2f} vol points")
    lines += ["", "## Static arbitrage checks", "",
              "Butterfly: Gatheral's g(k) on 401 points across each slice's quoted log-moneyness range. "
              "Calendar: total variance of the longer expiry minus the shorter one on 201 points of their common range. "
              "Violations are reported, not patched.", "",
              "| Underlying | Expiry | Butterfly | Where g < 0 (k) |", "|---|---|---|---|"]
    for u in units:
        for e, s in sorted(u["fitted"].items(), key=lambda x: x[1]["T"]):
            b = s["butterfly"]
            lines.append(f"| {u['symbol']} | {e} | {'ok' if b['ok'] else 'VIOLATION'} | "
                         f"{'-' if b['ok'] else fmt_k(b['bad_from']) + ' to ' + fmt_k(b['bad_to'])} |")
    lines += ["", "| Underlying | Shorter | Longer | Calendar | Min of w_long - w_short | Where negative (k) |",
              "|---|---|---|---|---:|---|"]
    for u in units:
        for short, long, c in u["calendar"]:
            lines.append(f"| {u['symbol']} | {short} | {long} | {'ok' if c['ok'] else 'VIOLATION'} | {c['min_diff']:.5f} | "
                         f"{'-' if c['ok'] else fmt_k(c['bad_from']) + ' to ' + fmt_k(c['bad_to'])} |")
    lines += ["", "## SVI parameters", "", "| Underlying | Expiry | " + " | ".join(PARAM_NAMES) + " |",
              "|---|---|" + "---:|" * len(PARAM_NAMES)]
    for u in units:
        for e, s in sorted(u["fitted"].items(), key=lambda x: x[1]["T"]):
            lines.append(f"| {u['symbol']} | {e} | " + " | ".join(f"{p:.4f}" for p in s["params"]) + " |")
    lines += ["", "## Risk-neutral density", ""]
    for sym, (expiry, mass) in extras["density"].items():
        lines.append(f"- {sym} {expiry}: the Breeden-Litzenberger density integrates to {mass:.3f} over the quoted strike range "
                     "(the rest of the probability lies beyond the quoted strikes).")
    return "\n".join(lines) + "\n"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    built: dict[str, dict] = {}
    for sym in UNDERLYINGS:
        lender = DF_FROM.get(sym)
        built[sym] = build_underlying(sym, discount_curve(built[lender]) if lender else None)
    units = list(built.values())
    figures = [plot_smiles(u) for u in units]
    figures += [plot_surfaces(units), plot_term_structure(units)]
    density = {}
    for u in units:
        name, expiry, mass = plot_density(u)
        figures.append(name)
        density[u["symbol"]] = (expiry, mass)
    figures.append(plot_skew_compare(units[0], units[1])[0])
    (OUT / "results.md").write_text(results_markdown(units, {"density": density}), encoding="utf-8")
    for u in units:
        rmse = np.mean([s["rmse"] for s in u["fitted"].values()]) * 100
        kept = sum(len(s["quotes"]) for s in u["fitted"].values())
        print(f"{u['symbol']}: {kept} quotes kept, {len(u['fitted'])} expiries fitted, mean RMSE {rmse:.2f} vol pts")
    print("wrote", ", ".join(figures), "and results.md to output/")


if __name__ == "__main__":
    main()
