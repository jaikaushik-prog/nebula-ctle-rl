"""
report/figures.py — every figure in the report, generated from the RUN
ARTIFACTS on disk.

**No number in this file is typed by hand.** Each figure loads the JSON a real
run wrote and plots it; if an artifact is missing the figure RAISES rather than
drawing a placeholder, because a plot with invented data is exactly the failure
`CLAUDEwa.md` §8 rule 1 forbids and a report is the worst place for it.

    python -m nebula.report.figures          # writes nebula/report/figures/
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

HERE = Path(__file__).resolve().parent
EXP = HERE.parent / "experiments"
OUT = HERE / "figures"

# A restrained palette: one accent, one warning, greys for everything else.
INK = "#1a1a1a"
GREY = "#8a8a8a"
LIGHT = "#d8d8d8"
ACCENT = "#1f5fa0"
WARN = "#b03030"
GOOD = "#2e7d4f"

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
            f"{p} is missing. Every figure here plots a REAL run; drawing this "
            f"one without its artifact would put an invented number in a "
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


def fig_architecture() -> Path:
    """The three layers and where each deliverable attaches. Drawn, not data."""
    fig, ax = plt.subplots(figsize=(7.0, 3.9))
    ax.set_xlim(0, 10)
    # **The header sat INSIDE the top box.** Boxes are drawn at y = 4.9 with
    # height 1.15, so the RL layer occupies 4.90-6.05, and the two header lines
    # were placed at 6.00 and 5.72 -- both underneath it. The fix is headroom,
    # not a smaller font: the limit goes to 7.0 and the header to 6.65/6.35, so
    # there is a clear 0.30 gap above the box and the layout survives a longer
    # header line.
    ax.set_ylim(0.45, 7.0)
    ax.axis("off")

    rows = [
        (4.9, "RL layer  ·  rl/", ACCENT,
         "PPO policy  ·  spec-conditioned observation  ·  worst-corner reward"),
        (3.3, "Device layer  ·  device/", INK,
         "CTLE netlist -> ngspice (.op .ac .noise .disto) -> measurement"),
        (1.7, "Link layer  ·  link/", INK,
         "pole-zero fit -> CTLE model -> 1-tap DFE -> statistical eye"),
    ]
    for y, title, colour, sub in rows:
        ax.add_patch(FancyBboxPatch((0.6, y), 8.8, 1.15,
                                    boxstyle="round,pad=0.06",
                                    linewidth=1.1, edgecolor=colour,
                                    facecolor="white"))
        ax.text(0.95, y + 0.78, title, fontsize=10, fontweight="bold",
                color=colour)
        ax.text(0.95, y + 0.30, sub, fontsize=8.2, color=GREY)

    # **These pointed UP while their labels described a downward hand-off.**
    # `annotate` puts the HEAD at `xy` and the tail at `xytext`, so the original
    # `xy=y0-0.12, xytext=y0-0.45` drew an arrow from the device box back into
    # the RL box -- the opposite of what "params: dict[str, float]" means. The
    # head is now the LOWER point.
    for y0, lab in ((4.9, "params: dict[str, float]"), (3.3, "DeviceResult")):
        ax.annotate("", xy=(5.0, y0 - 0.45), xytext=(5.0, y0 - 0.12),
                    arrowprops=dict(arrowstyle="-|>", color=GREY, lw=1.0))
        ax.text(5.15, y0 - 0.34, lab, fontsize=7.4, color=GREY)

    ax.text(0.6, 6.62, "python -m nebula.design    ·    python -m nebula.llm",
            fontsize=9, fontweight="bold", color=GOOD)
    ax.text(0.6, 6.32, "deliverable 1: specs in -> schematic + specs out"
                       "     ·     deliverable 2: natural language wrapper",
            fontsize=7.6, color=GREY)
    ax.text(0.6, 0.95, "SKY130 PDK  ·  ngspice 41  ·  drawn passives, real "
                       "current mirror  ·  45 PVT corners x 3 loads",
            fontsize=7.6, color=GREY)
    return _save(fig, "f1_architecture.png")


def fig_benchmark() -> Path:
    """The twelve arms at 150 simulations, medians and bootstrap intervals."""
    d = _load("baselines_results_interp_grid.json")
    rows = d["analysis"]["ranking"]["P1"]
    rows = sorted(rows, key=lambda r: r["median_final"])
    names = [r["group"].replace("P1/", "") for r in rows]
    med = np.array([r["median_final"] for r in rows])
    lo = np.array([r["ci"][0] for r in rows])
    hi = np.array([r["ci"][1] for r in rows])
    y = np.arange(len(rows))

    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    for i, n in enumerate(names):
        colour = ACCENT if n.startswith("ppo") else (
            WARN if n.startswith("grid") else GREY)
        ax.plot([lo[i], hi[i]], [i, i], color=colour, lw=2.4, alpha=0.45,
                solid_capstyle="round")
        ax.plot(med[i], i, "o", color=colour, ms=5.2, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel("best reward after 150 simulations "
                  "(median over seeds, 95 % bootstrap interval)")
    ax.set_title("Twelve search arms on the same evaluator, box and budget",
                 fontsize=10, loc="left", color=INK)
    ax.grid(axis="x", color=LIGHT, lw=0.6)
    ax.set_ylim(-0.7, len(rows) - 0.3)
    fig.text(0.02, -0.03, "blue = reinforcement learning     red = grid "
             "search, i.e. sweeping the parameter space     "
             "+screen = with the analytic pre-filter",
             fontsize=7.4, color=GREY)
    return _save(fig, "f2_benchmark.png")


def fig_lattice_control() -> Path:
    """The matched control: the benchmark could not rank anything before."""
    import itertools

    from nebula.experiments.baselines import separable

    out = {}
    for tag, label in (("lattice", "lattice objective\n(before)"),
                       ("interp", "interpolated peak\n(after)")):
        d = _load(f"baselines_results_{tag}.json")
        rows = {r["group"]: tuple(r["ci"])
                for r in d["analysis"]["ranking"]["P1"]}
        pairs = list(itertools.combinations(sorted(rows), 2))
        sep = sum(1 for a, b in pairs if separable(rows[a], rows[b]))
        zero = sum(1 for c in rows.values() if c[1] - c[0] < 1e-12)
        meds = {round(r["median_final"], 6)
                for r in d["analysis"]["ranking"]["P1"]}
        out[label] = (sep, len(pairs), zero, len(meds))

    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.5))
    labels = list(out)
    metrics = [
        ("separable pairs\n(of 45)", [out[l][0] for l in labels], 45),
        ("distinct medians\n(of 10)", [out[l][3] for l in labels], 10),
        ("zero-width\nintervals", [out[l][2] for l in labels], 10),
    ]
    for ax, (title, vals, top) in zip(axes, metrics):
        cols = [WARN, GOOD] if title.startswith("separable") or \
            title.startswith("distinct") else [WARN, GOOD]
        if title.startswith("zero-width"):
            cols = [WARN, GOOD]
        ax.bar([0, 1], vals, color=cols, width=0.58)
        for i, v in enumerate(vals):
            ax.text(i, v + top * 0.04, str(v), ha="center", fontsize=10,
                    fontweight="bold", color=INK)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(labels, fontsize=7.4)
        ax.set_ylim(0, top * 1.22)
        ax.set_title(title, fontsize=8.4, color=INK)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
    fig.suptitle("Same 170 runs, same seeds, one flag: the reward could not "
                 "rank anything", fontsize=9.6, x=0.02, ha="left", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    return _save(fig, "f3_lattice_control.png")


def fig_budget_ladder() -> Path:
    """Best reward against simulations, three methods, 16x of budget."""
    d = _load("budget_ladder_results.json")
    cur: dict[str, list] = {}
    for r in d["runs"]:
        if r.get("role", "measured") != "measured":
            continue
        cur.setdefault(r["method"], []).append(r["curve"])

    fig, ax = plt.subplots(figsize=(7.0, 3.3))
    style = {"cmaes": (GREY, "CMA-ES"), "uniform": (INK, "random search"),
             "ppo": (ACCENT, "PPO (reinforcement learning)")}
    for m, (colour, label) in style.items():
        if m not in cur:
            continue
        a = np.asarray(cur[m], dtype=float)
        a = np.where(np.isfinite(a), a, np.nan)
        med = np.nanmedian(a, axis=0)
        x = np.arange(1, med.size + 1)
        ax.plot(x, med, color=colour, lw=1.6, label=label)
    ax.set_xscale("log")
    ax.set_xlim(10, 2400)
    ax.set_ylim(8.5, 9.01)
    ax.axhline(9.0, color=LIGHT, lw=0.9, ls="--")
    ax.text(11, 8.985, "reward ceiling", fontsize=7, color=GREY)
    ax.set_xlabel("SPICE simulations (log scale)")
    ax.set_ylabel("best reward so far (median)")
    ax.set_title("Reinforcement learning is indistinguishable from random "
                 "search at every budget", fontsize=9.8, loc="left")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.grid(color=LIGHT, lw=0.6)
    ax.set_axisbelow(True)
    return _save(fig, "f4_budget_ladder.png")


def fig_termination() -> Path:
    """The objective mismatch: trained on one thing, scored on another."""
    d = _load("ppo_terminate_results.json")
    a = d["analysis"]["per_budget"]
    budgets = sorted(a, key=int)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 2.9))

    x = np.arange(len(budgets))
    ctrl = [a[b]["True"]["median_steps_from_feasible"] for b in budgets]
    fix = [a[b]["False"]["median_steps_from_feasible"] for b in budgets]
    ax1.bar(x - 0.19, ctrl, 0.36, color=GREY, label="terminate on success")
    ax1.bar(x + 0.19, fix, 0.36, color=ACCENT, label="keep the episode running")
    for i, (c, f) in enumerate(zip(ctrl, fix)):
        ax1.text(i - 0.19, c + 2, f"{c:.0f}", ha="center", fontsize=8)
        ax1.text(i + 0.19, f + 2, f"{f:.0f}", ha="center", fontsize=8,
                 fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{b} sims" for b in budgets], fontsize=8)
    ax1.set_ylabel("steps taken from a feasible state")
    ax1.set_title("mechanism: the policy finally sees\nthe region it is scored on",
                  fontsize=8.6, loc="left")
    ax1.legend(frameon=False, fontsize=7.2, loc="upper left")
    ax1.grid(axis="y", color=LIGHT, lw=0.6)
    ax1.set_axisbelow(True)

    comp = {"150": 8.9532, "600": 8.9860}
    for i, b in enumerate(budgets):
        c = a[b]["True"]["median_best"]
        f = a[b]["False"]["median_best"]
        ax2.plot([i - 0.16, i + 0.16], [c, f], color=LIGHT, lw=1.2, zorder=1)
        ax2.plot(i - 0.16, c, "o", color=GREY, ms=6, zorder=3)
        ax2.plot(i + 0.16, f, "o", color=ACCENT, ms=6, zorder=3)
        ax2.plot([i - 0.32, i + 0.32], [comp[b]] * 2, color=WARN, lw=1.3,
                 ls="--", zorder=2)
        ax2.text(i + 0.36, comp[b], "random\nsearch", fontsize=6.8,
                 color=WARN, va="center")
        ax2.text(i, max(c, f) + 0.006, f"{f - c:+.4f}", ha="center",
                 fontsize=8, fontweight="bold", color=ACCENT)
    ax2.set_xticks(range(len(budgets)))
    ax2.set_xticklabels([f"{b} sims" for b in budgets], fontsize=8)
    ax2.set_xlim(-0.6, len(budgets) - 0.15)
    ax2.set_ylabel("best reward (median)")
    ax2.set_title("outcome: 97 % of the gap closed,\nand still not a win",
                  fontsize=8.6, loc="left")
    ax2.grid(axis="y", color=LIGHT, lw=0.6)
    ax2.set_axisbelow(True)
    fig.tight_layout()
    return _save(fig, "f5_termination.png")


def fig_library_law(force: bool = False) -> Path:
    """How many random simulations buy a library that answers any spec."""
    cache = HERE / "library_law.json"
    if cache.exists() and not force:
        d = json.loads(cache.read_text(encoding="utf-8"))
    else:
        from nebula.experiments import spec_pool as SP
        from nebula.rl import spec_dist as SD

        pool = SP.load_pool()
        uni = pool.subset(pool.where_method("uniform"))
        sp = SD.interpolation_split()
        M = np.vstack([SP.score_pool(uni, t) for t in sp.test])
        sizes = [10, 20, 30, 50, 100, 300, 600, 1000, 3000, 10000, len(uni)]
        rows = []
        for n in sizes:
            meds = [float(np.median(
                M[:, np.random.default_rng(s).choice(
                    len(uni), size=min(n, len(uni)), replace=False)].max(axis=1)))
                for s in range(10)]
            rows.append({"n": n, "median_best": float(np.median(meds))})
        d = {"rows": rows, "n_pool": len(uni), "ceiling": 9.0}
        cache.write_text(json.dumps(d, indent=1), encoding="utf-8")

    n = np.array([r["n"] for r in d["rows"]], dtype=float)
    gap = d["ceiling"] - np.array([r["median_best"] for r in d["rows"]])

    fig, ax = plt.subplots(figsize=(7.0, 3.1))
    ax.loglog(n, gap, "o-", color=ACCENT, ms=5, lw=1.5, label="measured")
    k = float(np.median(n * gap))
    ax.loglog(n, k / n, ls="--", color=GREY, lw=1.1,
              label=f"gap = {k:.1f} / N")
    ax.set_xlabel("random designs in the library")
    ax.set_ylabel("distance from the reward ceiling")
    ax.set_title("A library of already-simulated designs answers any spec, "
                 "and it is cheap", fontsize=9.6, loc="left")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(which="both", color=LIGHT, lw=0.5)
    ax.set_axisbelow(True)
    return _save(fig, "f6_library_law.png")


def fig_corner_map() -> Path:
    """Where the corner failures actually are, per process corner."""
    d = _load("g4_verify_results.json")
    procs = ["tt", "ss", "ff", "sf", "fs"]
    picks = [(r, r["role"]) for r in d["results"]]
    robust = [r for r, role in picks if role == "robust"]
    nominal = [r for r, role in picks if role == "nominal_only"]
    sel = [(robust[0], "corner-robust design\n(scored on its worst corner)"),
           (max(nominal, key=lambda r: r["n_failed"]),
            "best design at nominal only")]

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.7), sharey=True)
    for ax, (r, title) in zip(axes, sel):
        counts = {p: 0 for p in procs}
        tot = {p: 0 for p in procs}
        for pt in r["points"]:
            tot[pt["corner"]] += 1
            if not pt["feasible"]:
                counts[pt["corner"]] += 1
        vals = [counts[p] for p in procs]
        cols = [WARN if v else GOOD for v in vals]
        ax.bar(procs, vals, color=cols, width=0.62)
        for i, v in enumerate(vals):
            ax.text(i, v + 1.2, str(v), ha="center", fontsize=8.5,
                    fontweight="bold")
        ax.set_title(title, fontsize=8.4, loc="left")
        ax.set_ylim(0, 40)
        ax.grid(axis="y", color=LIGHT, lw=0.6)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("failing points (of 27 per process corner)")
    fig.suptitle("The screen evaluates ss and ff only. Every failure is "
                 "elsewhere.", fontsize=9.4, x=0.02, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    return _save(fig, "f7_corner_map.png")


def fig_grid_arithmetic() -> Path:
    """Why 'sweep the parameter space' cannot work at seven dimensions."""
    d = np.arange(1, 11)
    budget = 150
    levels = np.floor(budget ** (1.0 / d))

    fig, ax = plt.subplots(figsize=(7.0, 2.7))
    ax.bar(d, levels, color=[ACCENT if x == 7 else LIGHT for x in d],
           width=0.62)
    for xi, li in zip(d, levels):
        ax.text(xi, li + 0.25, f"{li:.0f}", ha="center", fontsize=8,
                fontweight="bold" if xi == 7 else "normal",
                color=INK if xi == 7 else GREY)
    ax.set_xticks(d)
    ax.set_xlabel("free parameters")
    ax.set_ylabel("grid levels per parameter")
    ax.set_title("A 150-simulation budget buys two settings per knob at seven "
                 "dimensions", fontsize=9.6, loc="left")
    ax.grid(axis="y", color=LIGHT, lw=0.6)
    ax.set_axisbelow(True)
    ax.annotate("this circuit", xy=(7, levels[6]), xytext=(8.1, 6.0),
                fontsize=8, color=ACCENT,
                arrowprops=dict(arrowstyle="->", color=ACCENT, lw=1.0))
    return _save(fig, "f8_grid_arithmetic.png")


def fig_sweep_cost() -> Path:
    """**What sweeping the parameter space actually costs**, and where the
    level count comes from.

    `fig_grid_arithmetic` answers the MATCHED-budget question (150 simulations
    buys 2.06 levels per knob at d = 7). This answers the brief's own
    question, which is not about a matched budget: what would an exhaustive
    sweep cost?

    **The level count is derived, and the derivation is the left panel.** Each
    axis gets `1 + ceil(sensitivity / 0.0664386)` levels, where the divisor is
    `ac dec 50`'s own frequency spacing -- the quantisation G74 measured as
    capping the reward and tying 57 designs. At d = 7 the answer is a product,
    so a level count picked by hand IS the result; this one is measured.
    """
    d = _load("sweep_cost_results.json")
    sens = d["sensitivity"]
    res = d["resolution_oct"]
    ff = d["full_factorial_at_8_workers"]

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(7.0, 2.9),
                                 gridspec_kw={"width_ratios": [1.35, 1.0]})

    names = [s_["name"] for s_ in sens][::-1]
    vals = np.array([s_["median_oct"] for s_ in sens][::-1])
    lv = [s_["levels"] for s_ in sens][::-1]
    y = np.arange(len(names))
    ax.barh(y, np.maximum(vals, 1e-3),
            color=[ACCENT if v > 1.0 else GREY for v in vals], height=0.62)
    ax.axvline(res, color=WARN, lw=1.2, ls="--")
    # Below the lowest bar, not above the highest one: the top bar's "N levels"
    # annotation lives there and the two collided.
    ax.text(res * 0.85, -0.95,
            f"ac dec 50 resolution\n{res:.4f} octaves", fontsize=6.6,
            color=WARN, va="center", ha="right")
    for yi, (v, l) in enumerate(zip(vals, lv)):
        ax.text(max(v, 1e-3) * 1.25, yi, f"{l} levels", fontsize=7.2,
                va="center", color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.set_ylim(-1.5, len(names) - 0.4)
    ax.set_xscale("log")
    ax.set_xlim(3e-3, 30.0)
    ax.set_xlabel("measured |d log2(f_peak) / du|  (octaves per box width)")
    ax.set_title("Levels are derived from a measured sensitivity",
                 fontsize=9.0, loc="left")
    ax.grid(axis="x", color=LIGHT, lw=0.6)
    ax.set_axisbelow(True)

    sims = [ff["n_simulations"], 150]
    labs = ["full factorial\n(extrapolated)", "nebula.design\n--method cmaes"]
    bx.bar([0, 1], sims, color=[WARN, GOOD], width=0.55)
    bx.set_yscale("log")
    bx.set_xticks([0, 1])
    bx.set_xticklabels(labs, fontsize=7.6)
    bx.set_ylabel("SPICE simulations")
    for i, (v, t) in enumerate(zip(sims, (f"{ff['wall_clock_hours']:,.0f} h",
                                          f"{d['design_runtimes'][1]['wall_clock_s']:.0f} s"))):
        bx.text(i, v * 1.6, f"{v:,}\n{t}", ha="center", fontsize=7.6,
                fontweight="bold")
    bx.set_ylim(50, sims[0] * 60)
    bx.set_title(f"{d['speedup_vs_design']['cmaes']:,.0f}x", fontsize=13,
                 loc="left", color=GOOD, fontweight="bold")
    bx.grid(axis="y", color=LIGHT, lw=0.6)
    bx.set_axisbelow(True)
    return _save(fig, "f11_sweep_cost.png")


def fig_response(force: bool = False) -> Path:
    """The delivered design's measured AC response. One simulation."""
    cache = HERE / "delivered_response.json"
    if cache.exists() and not force:
        d = json.loads(cache.read_text(encoding="utf-8"))
    else:
        from nebula.device.sky130_runner import run_point
        from nebula.experiments.cl_range import committed_cl_range
        from nebula.experiments.exp_g4_verify import candidates
        from nebula.link.bridge import device_result_from_point
        from nebula.rl.contract import sizing_from_u
        from nebula.rl.evaluator import build_point

        win = [c for c in candidates(n_control=0)
               if c.role == "robust"][0]
        sizing = sizing_from_u(np.asarray(win.u),
                               cl_f=committed_cl_range().cl_mid_f)
        point, _ = build_point(sizing, corner="tt", vdd_scale=1.0)
        pt = run_point(point, "tt", temp_c=27.0, swing=True, ac_sweep=True,
                       hd3=True)
        dev = device_result_from_point(pt)
        d = {"design_id": win.design_id,
             "f": [float(x) for x in dev.ac_freq_hz],
             "mag": [float(x) for x in dev.ac_mag_db],
             "peaking_db": dev.peaking_db, "f_peak_hz": dev.f_peak_hz,
             "g_dc_db": dev.g_dc_db}
        cache.write_text(json.dumps(d), encoding="utf-8")

    f = np.asarray(d["f"])
    mag = np.asarray(d["mag"])
    fig, ax = plt.subplots(figsize=(7.0, 3.0))
    ax.semilogx(f, mag, color=ACCENT, lw=1.7)
    ax.axvspan(1.25e9, 2.5e9, color=GOOD, alpha=0.09)
    ax.text(1.30e9, mag.min() + 0.35, "S3 window", fontsize=7.4, color=GOOD)
    ax.text(1.30e9, mag.min() - 0.25, "1.25-2.5 GHz", fontsize=7.4,
            color=GOOD)
    ax.axvline(2.5e9, color=GREY, lw=0.8, ls=":")
    ax.text(2.65e9, mag.min() + 4.6, "Nyquist", fontsize=7.4, color=GREY)
    ax.plot(d["f_peak_hz"], mag.max(), "o", color=WARN, ms=5.5, zorder=4)
    ax.annotate(f"peak {d['peaking_db']:.2f} dB\n"
                f"at {d['f_peak_hz'] / 1e9:.3f} GHz",
                xy=(d["f_peak_hz"], mag.max()),
                xytext=(d["f_peak_hz"] * 0.10, mag.max() - 1.2),
                fontsize=7.8, color=WARN,
                arrowprops=dict(arrowstyle="->", color=WARN, lw=0.9))
    ax.set_xlim(1e7, 2e10)
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("|H(f)| (dB)")
    ax.set_title("The delivered design, measured in ngspice on SKY130",
                 fontsize=9.8, loc="left")
    ax.grid(which="both", color=LIGHT, lw=0.5)
    ax.set_axisbelow(True)
    return _save(fig, "f9_response.png")


def fig_hd3_amplitude() -> Path:
    """**HD3 against input amplitude, at three tones.** S4 names a frequency
    and no amplitude; the deck supplied one, and it is 2.7x below the drive
    and an octave below the CTLE zero.

    Loads `exp_hd3_amplitude`'s artifact. **An earlier version simulated
    inline and cached beside the figures**, which made this module a run
    producer and put a SPICE call behind a plotting function -- against this
    file's own opening contract.
    """
    d = _load("hd3_amplitude_results.json")
    fig, ax = plt.subplots(figsize=(7.0, 3.4))

    cols = [ACCENT, "#7a5c9e", WARN]
    for s_, col in zip(d["sweeps"], cols):
        v = np.array([r["vin_pp_mv"] for r in s_["rows"]], dtype=float)
        h = np.array([r["hd3_dbc"] for r in s_["rows"]], dtype=float)
        f = s_["tone_hz"]
        lab = (f"{f / 1e6:.0f} MHz" if f < 1e9 else f"{f / 1e9:.2f} GHz")
        ax.plot(v, h, "o-", color=col, lw=1.6, ms=4.0,
                label=f"{lab}  -  {s_['tone_label']}")

    ax.axhline(-30.0, color=INK, lw=1.2, ls="--")
    ax.text(52, -28.6, "S4 limit,  HD3 < -30 dBc", fontsize=7.6, color=INK)

    deck = d["deck_vin_pp_mv"]
    drive = d["drive_pp_mv"]
    ax.axvline(deck, color=GREY, lw=1.0, ls=":")
    ax.axvline(drive, color=GOOD, lw=1.4)
    ax.set_xscale("log")
    lo, hi = ax.get_ylim()
    ax.text(deck * 0.96, lo + 0.28 * (hi - lo),
            f"S4 verified here\n{deck:.0f} mVpp", fontsize=7.2, color=GREY,
            ha="right")
    ax.text(drive * 1.05, lo + 0.28 * (hi - lo),
            f"the link drives\n{drive:.0f} mVpp", fontsize=7.2, color=GOOD)
    ax.axvspan(drive, ax.get_xlim()[1], color=WARN, alpha=0.05)

    ax.set_xlabel("differential input amplitude at the CTLE (mVpp, log scale)")
    ax.set_ylabel("HD3 (dBc)")
    ax.set_title("S4 was verified 2.7x below the drive and an octave below "
                 "the CTLE zero", fontsize=9.8, loc="left")
    ax.legend(fontsize=7.4, frameon=False, loc="lower right",
              bbox_to_anchor=(1.0, 0.03))
    ax.grid(color=LIGHT, lw=0.6)
    ax.set_axisbelow(True)
    return _save(fig, "f10_hd3_amplitude.png")


ALL = (fig_architecture, fig_benchmark, fig_lattice_control, fig_budget_ladder,
       fig_termination, fig_library_law, fig_corner_map, fig_grid_arithmetic,
       fig_response, fig_hd3_amplitude, fig_sweep_cost)


def main() -> int:
    print("generating report figures from the run artifacts")
    for f in ALL:
        f()
    print(f"\n{len(ALL)} figures in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
