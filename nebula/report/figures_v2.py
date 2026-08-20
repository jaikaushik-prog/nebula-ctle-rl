"""
report/figures_v2.py — **the figures a judge reads first.**

Session 23. `report/figures.py` has twelve figures and most of them document
how this project debugged itself. Those belong in an appendix. These four are
the ones that answer the questions the competition slide actually asks, in the
order it asks them:

    1. compliance    "meet across PVT"                -> fig_compliance_matrix
    2. coverage      "takes target specs as input"    -> fig_coverage_map
    3. efficiency    "lower time than sweeping ..."   -> fig_efficiency
    4. honesty       (nobody asks; everybody weighs)  -> fig_screen_audit

**No number here is typed by hand** — same rule as `figures.py`. Each figure
loads a run artifact and raises if it is missing, because a plot with invented
data is the one thing `CLAUDEwa.md` §8 rule 1 forbids and a report is the worst
place for it.

COLOUR, AND WHY THESE SPECIFIC HEXES
--------------------------------------
The categorical palette is **validated, not chosen by eye**:

    #0072B2  #D55E00  #009E73  #8B6914  #A0499B  #4C7A2E

run through the six checks (lightness band, chroma floor, colour-vision
separation on every adjacent pair, normal-vision floor, contrast against the
surface) in **both light and dark** modes: all pass, worst adjacent pair
ΔE 10.7 deuteranopia / 17.2 normal, every slot >= 3:1 contrast.

**`figures.py`'s `GOOD`/`WARN` pair is green-and-red and is deliberately NOT
used for pass/fail here.** Red-green is the pair ~8 % of readers cannot
separate, and an analog panel is not a forgiving audience for it. Pass/fail is
a POLARITY, so it gets a diverging pair — blue and orange — with a **neutral
grey at exactly zero margin**, and failures additionally carry a hatch, so
identity is never colour alone.

    python -m nebula.report.figures_v2
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

HERE = Path(__file__).resolve().parent
EXP = HERE.parent / "experiments"
OUT = HERE / "figures"

INK = "#1a1a1a"
GREY = "#8a8a8a"
LIGHT = "#d8d8d8"

#: The validated categorical order. **Assigned in this order, never cycled.**
CAT = ("#0072B2", "#D55E00", "#009E73", "#8B6914", "#A0499B", "#4C7A2E")

#: Diverging pair for margins: fail (warm) <- neutral grey -> pass (cool).
FAIL_HUE = "#D55E00"
PASS_HUE = "#0072B2"
MID = "#f2f2f2"
DIVERGING = LinearSegmentedColormap.from_list(
    "margin", [FAIL_HUE, "#f0b48a", MID, "#9dc3e0", PASS_HUE])

#: Sequential ramp for counts: ONE hue, light -> dark. Never a rainbow.
SEQUENTIAL = LinearSegmentedColormap.from_list(
    "count", ["#f4f8fb", "#c5dcec", "#7fb2d6", "#3a86bd", "#0072B2", "#004c78"])

plt.rcParams.update({
    "font.size": 9,
    "axes.edgecolor": GREY,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": GREY,
    "ytick.color": GREY,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 200,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
})


def _load(name: str) -> dict:
    p = EXP / name
    if not p.exists():
        raise FileNotFoundError(
            f"{p} is missing. Every figure here plots a REAL run; drawing it "
            f"without its artifact would put an invented number in a "
            f"deliverable.")
    return json.loads(p.read_text(encoding="utf-8"))


def _save(fig, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    fig.savefig(p, facecolor="white")
    plt.close(fig)
    print(f"  wrote {p.name}")
    return p


# ─────────────────────────────────────────────────────────────────────────────
# 1. THE COMPLIANCE MATRIX — page one.
# ─────────────────────────────────────────────────────────────────────────────


def fig_compliance_matrix(artifact: str = "joint_verify_full_results.json",
                          design_index: int = 0,
                          name: str = "f1_compliance_matrix.png") -> Path:
    """**Every spec row, at every mandated PVT corner. The judge's checklist.**

    Rows are spec rows; columns are the 45 mandated corners at the design load.
    Cell colour is the NORMALISED margin (margin / tolerance), so rows in
    volts, dB, watts and octaves are comparable in one picture — which is the
    only way eleven different units fit on one axis.

    **The load axis is deliberately absent and that is stated in the caption,
    not hidden.** The slide mandates 45 PVT corners and says nothing about
    load (G109); the load sweep is characterisation and gets its own figure.
    """
    d = _load(artifact)
    res = d["results"][design_index]
    pts = [p for p in res["points"] if p.get("ok")]
    if not pts:
        raise ValueError(f"{artifact}: no scored points to plot")

    loads = sorted({round(float(p["cl_f"]), 20) for p in pts})
    design_load = loads[len(loads) // 2]
    grid = [p for p in pts if abs(float(p["cl_f"]) - design_load) < 1e-20]
    rows = [r for r in res["spec_set"] if r in (grid[0].get("margins") or {})]

    from nebula.rl import reward_v1 as R
    M = np.full((len(rows), len(grid)), np.nan)
    for j, p in enumerate(grid):
        for i, r in enumerate(rows):
            v = (p.get("margins") or {}).get(r)
            if v is not None:
                M[i, j] = float(v) / R.TOL[r]

    fig, ax = plt.subplots(figsize=(11.0, 0.42 * len(rows) + 1.9))
    # **The scale is CLIPPED, and the caption says so.** Three rows sit at
    # 6-7x their tolerance while `S3_f_peak` sits at 0.6x, so an unclipped
    # scale spends its whole range separating "comfortable" from "very
    # comfortable" and renders every genuinely tight margin as the same white
    # as zero -- i.e. it hides exactly the cells a judge is looking for.
    # Anything past CLIP reads as saturated: the distinction between 3x and 7x
    # of tolerance is not a distinction anybody needs.
    CLIP = 3.0
    lo = float(np.nanmin(M))
    im = ax.imshow(np.clip(M, -CLIP, CLIP), aspect="auto", cmap=DIVERGING,
                   norm=TwoSlopeNorm(vmin=-CLIP, vcenter=0.0, vmax=CLIP))

    # Failures carry a HATCH as well as a colour: identity is never colour
    # alone, and a printed or colour-blind reading must still find them.
    n_fail = 0
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if np.isfinite(M[i, j]) and M[i, j] < 0:
                ax.add_patch(plt.Rectangle((j - .5, i - .5), 1, 1, fill=False,
                                           hatch="////", edgecolor=INK,
                                           linewidth=0.0))
                n_fail += 1

    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows, fontsize=8)
    step = max(1, len(grid) // 15)
    ax.set_xticks(range(0, len(grid), step))
    ax.set_xticklabels(
        [f"{grid[j]['corner']}/{grid[j]['vdd_scale']:.2f}/{grid[j]['temp_c']:g}"
         for j in range(0, len(grid), step)], rotation=90, fontsize=6.5)
    ax.set_xlabel(f"{len(grid)} mandated PVT corners "
                  f"(5 process x VDD +/-5% x 0-125 C), at the design load")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)

    cb = fig.colorbar(im, ax=ax, pad=0.012, fraction=0.022)
    cb.set_label(f"margin / tolerance   (0 = exactly at spec, "
                 f"clipped at {CLIP:g}x)", fontsize=8)
    cb.outline.set_visible(False)

    worst = float(np.nanmin(M))
    wi, wj = np.unravel_index(np.nanargmin(M), M.shape)
    # Point the eye at the binding cell. A judge's first question is "where is
    # this design closest to failing?", and a heatmap alone does not answer it.
    ax.add_patch(plt.Rectangle((wj - .5, wi - .5), 1, 1, fill=False,
                               edgecolor=INK, linewidth=1.6, zorder=5))
    ax.annotate(f"tightest: {worst:+.2f}x", xy=(wj, wi - .5),
                xytext=(wj, wi - 1.35), ha="center", fontsize=7.5, color=INK,
                arrowprops=dict(arrowstyle="-", color=INK, linewidth=0.9))
    n_pass_rows = sum(1 for i in range(len(rows))
                      if np.nanmin(M[i, :]) >= 0)
    ax.set_title(
        f"{n_pass_rows} of {len(rows)} spec rows pass at "
        f"{len(grid)} of {len(grid)} mandated PVT corners"
        + ("" if n_fail == 0 else f"   ({n_fail} failing cells, hatched)"),
        fontsize=11, color=INK, pad=10, loc="left")
    fig.text(0.005, -0.02,
             f"design {res['design_id']}   |   tightest margin "
             f"{worst:+.3f} x tolerance on {rows[wi]} at "
             f"{grid[wj]['corner']}/{grid[wj]['vdd_scale']:.2f}/"
             f"{grid[wj]['temp_c']:g}C   |   load capacitance is fixed at "
             f"layout and is characterised separately, not swept here",
             fontsize=7.5, color=GREY)
    return _save(fig, name)


# ─────────────────────────────────────────────────────────────────────────────
# 2. THE COVERAGE MAP — the deliverable, not the design.
# ─────────────────────────────────────────────────────────────────────────────


def fig_coverage_map(artifact: str = "coverage_results.json",
                     name: str = "f2_coverage_map.png") -> Path:
    """**For every spec a judge might type, does the framework answer?**

    One cell per request. Shade = how many of the 45 mandated corners passed;
    the text inside is what was actually DELIVERED against what was ASKED, so
    a cell that passed by delivering something else cannot hide.

    Sequential, one hue, light to dark — the quantity is a magnitude (a count),
    and a rainbow would imply categories that do not exist.
    """
    d = _load(artifact)
    reqs = d["requests"]
    pk = sorted({r["peaking_db"] for r in reqs})
    fz = sorted({r["f_peak_hz"] for r in reqs})
    C = np.full((len(pk), len(fz)), np.nan)
    for r in reqs:
        i, j = pk.index(r["peaking_db"]), fz.index(r["f_peak_hz"])
        if r.get("n_pvt45_pass") is not None:
            C[i, j] = r["n_pvt45_pass"]

    fig, ax = plt.subplots(figsize=(8.4, 5.6))
    im = ax.imshow(C, aspect="auto", cmap=SEQUENTIAL, vmin=0, vmax=45,
                   origin="lower")
    for r in reqs:
        i, j = pk.index(r["peaking_db"]), fz.index(r["f_peak_hz"])
        n = r.get("n_pvt45_pass")
        got = ("not solved" if r.get("delivered_peaking_db") is None else
               f"{r['delivered_peaking_db']:.1f} dB\n"
               f"{(r['delivered_f_peak_hz'] or 0) / 1e9:.2f} GHz")
        full = n == r.get("n_pvt45_total")
        ax.text(j, i, f"{'PASS' if full else str(n) + '/45'}\n{got}",
                ha="center", va="center", fontsize=7.2,
                color=("white" if (n or 0) > 28 else INK),
                fontweight=("bold" if full else "normal"))

    ax.set_xticks(range(len(fz)))
    ax.set_xticklabels([f"{f / 1e9:.2f}" for f in fz])
    ax.set_yticks(range(len(pk)))
    ax.set_yticklabels([f"{p:.0f}" for p in pk])
    ax.set_xlabel("peak frequency REQUESTED (GHz)   —   spec allows 1.25 – 2.5")
    ax.set_ylabel("HF peaking REQUESTED (dB)\nspec allows 3 – 12")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)

    cb = fig.colorbar(im, ax=ax, pad=0.015, fraction=0.03)
    cb.set_label("mandated PVT corners passing (of 45)", fontsize=8)
    cb.outline.set_visible(False)

    solved = d.get("n_solved_pvt45", 0)
    ax.set_title(f"The framework returned a fully PVT-compliant design for "
                 f"{solved} of {d['n_requests']} spec requests",
                 fontsize=11, color=INK, pad=10, loc="left")
    fig.text(0.005, -0.03,
             f"{d['total_sims']} SPICE runs total, "
             f"{d['wall_clock_s'] / 60:.0f} min   |   each cell is one "
             f"independent request: specs in, transistor-level design out, "
             f"no human intervention",
             fontsize=7.5, color=GREY)
    return _save(fig, name)


# ─────────────────────────────────────────────────────────────────────────────
# 3. EFFICIENCY — the slide's own success criterion.
# ─────────────────────────────────────────────────────────────────────────────


def fig_efficiency(sweep_artifact: str = "sweep_cost_results.json",
                   coverage_artifact: str = "coverage_results.json",
                   name: str = "f3_efficiency.png") -> Path:
    """**"Significantly lower time than sweeping all MOS, R, C, L parameters."**

    Log x-axis, and that is not a stylistic choice: the full factorial and this
    framework differ by ~4 orders of magnitude, so on a linear axis every bar
    except the sweep is invisible — which would hide the comparison the figure
    exists to make.

    The sweep bar is an **extrapolation** and is hatched and labelled as one.
    The framework bar is **measured**. Mixing an extrapolated number with
    measured ones without marking which is which is the failure mode this
    project has a standing rule against.
    """
    cov = _load(coverage_artifact)
    per_request = cov["total_sims"] / max(cov["n_requests"], 1)

    try:
        sw = _load(sweep_artifact)
        full = float(sw.get("n_sims_full_factorial")
                     or sw.get("total_sims") or 0) or None
    except FileNotFoundError:
        full = None

    labels, vals, kinds = [], [], []
    if full:
        labels.append("full parameter sweep\n(extrapolated)")
        vals.append(full)
        kinds.append("extrap")
    labels.append("this framework,\nper spec request")
    vals.append(per_request)
    kinds.append("measured")

    fig, ax = plt.subplots(figsize=(8.6, 2.2 + 0.5 * len(vals)))
    y = np.arange(len(vals))
    for k, (yy, v, kind) in enumerate(zip(y, vals, kinds)):
        ax.barh(yy, v, height=0.5, color=CAT[0] if kind == "measured" else GREY,
                hatch=("" if kind == "measured" else "////"),
                edgecolor="white", linewidth=1.2)
        ax.text(v * 1.25, yy, f"{v:,.0f} simulations", va="center",
                fontsize=9, color=INK,
                fontweight="bold" if kind == "measured" else "normal")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xscale("log")
    ax.set_xlabel("SPICE simulations  (log scale)")
    ax.set_xlim(left=max(1.0, min(vals) / 3), right=max(vals) * 12)
    ax.grid(axis="x", color=LIGHT, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.invert_yaxis()

    if full:
        ax.set_title(f"{full / per_request:,.0f}x fewer simulations than a "
                     f"full parameter sweep", fontsize=11, color=INK,
                     pad=10, loc="left")
    fig.text(0.005, -0.06,
             "hatched = extrapolated, solid = measured. The framework bar is "
             "the MEASURED mean over every request in the coverage sweep, "
             "including its 135-point verification.",
             fontsize=7.5, color=GREY)
    return _save(fig, name)


# ─────────────────────────────────────────────────────────────────────────────
# 4. THE SELF-CHECK — the figure that says we check our own work.
# ─────────────────────────────────────────────────────────────────────────────


def fig_screen_audit(artifact: str = "coverage_results.json",
                     name: str = "f4_screen_audit.png") -> Path:
    """**Did the 4-corner shortcut tell the truth about all 45?**

    x = what the shortcut predicted, y = what the full grid measured. On the
    diagonal means the shortcut was exact. **Below** the diagonal means the
    shortcut was OPTIMISTIC, which is the dangerous direction: a design shipped
    on a promise the full grid does not keep. Above it is merely wasteful.

    The shaded half-plane is the unsafe one, and it is shaded rather than
    described because the asymmetry is the entire point of the figure.
    """
    d = _load(artifact)
    rows = [(r["screen_reward"], r["audit"]["full_worst"], r["audit"])
            for r in d["requests"]
            if r.get("audit") and r.get("screen_reward") is not None]
    if not rows:
        raise ValueError(f"{artifact} carries no screen audits to plot")

    x = np.array([a for a, _, _ in rows])
    yv = np.array([b for _, b, _ in rows])
    ok = np.array([bool(c["was_predictive"]) for _, _, c in rows])

    fig, ax = plt.subplots(figsize=(6.4, 6.0))
    lo = float(min(x.min(), yv.min())) - 0.5
    hi = float(max(x.max(), yv.max())) + 0.5
    ax.fill_between([lo, hi], [lo, hi], [lo, lo], color=FAIL_HUE, alpha=0.07,
                    linewidth=0)
    ax.plot([lo, hi], [lo, hi], color=GREY, linewidth=1.2, linestyle="--",
            zorder=1)
    ax.text(hi, lo + (hi - lo) * 0.04, "shortcut OPTIMISTIC\n(unsafe)",
            ha="right", va="bottom", fontsize=8, color=FAIL_HUE)

    ax.scatter(x[ok], yv[ok], s=64, color=PASS_HUE, zorder=3,
               edgecolor="white", linewidth=1.5, label="shortcut held")
    if (~ok).any():
        ax.scatter(x[~ok], yv[~ok], s=76, color=FAIL_HUE, marker="X", zorder=3,
                   edgecolor="white", linewidth=1.2,
                   label="shortcut missed — corner added")

    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("worst score the 4-corner shortcut predicted")
    ax.set_ylabel("worst score the full 45-corner grid measured")
    ax.grid(color=LIGHT, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8, loc="upper left")

    sr = d["screen_report"]
    ax.set_title(f"The shortcut checked itself {sr['n_audits']} times and held "
                 f"{sr['n_predictive']} of them", fontsize=11, color=INK,
                 pad=10, loc="left")
    fig.text(0.005, -0.02,
             f"4 SPICE runs per candidate instead of 45. The check is free: "
             f"every shipped design is verified on the full grid anyway. "
             f"Screen grew from 4 to {sr['n_points']} points.",
             fontsize=7.5, color=GREY)
    return _save(fig, name)


# ─────────────────────────────────────────────────────────────────────────────


FIGURES = {
    "compliance": fig_compliance_matrix,
    "coverage": fig_coverage_map,
    "efficiency": fig_efficiency,
    "audit": fig_screen_audit,
}


def main() -> int:
    print("figures_v2 -> " + str(OUT))
    made, missing = 0, []
    for key, fn in FIGURES.items():
        try:
            fn()
            made += 1
        except FileNotFoundError as e:
            # A missing ARTIFACT is a run that has not happened, not a bug.
            # Named loudly and skipped; never drawn from a placeholder.
            missing.append(f"{key}: {e}")
    for m in missing:
        print(f"  SKIPPED {m}")
    print(f"  {made} of {len(FIGURES)} figures written")
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
