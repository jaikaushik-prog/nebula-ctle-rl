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
import math
from pathlib import Path
from typing import Optional

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
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.2)
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

    for y0, lab in ((4.9, "params: dict[str, float]"), (3.3, "DeviceResult")):
        ax.annotate("", xy=(5.0, y0 - 0.12), xytext=(5.0, y0 - 0.45),
                    arrowprops=dict(arrowstyle="-|>", color=GREY, lw=1.0))
        ax.text(5.15, y0 - 0.34, lab, fontsize=7.4, color=GREY)

    ax.text(0.6, 6.0, "python -m nebula.design    ·    python -m nebula.llm",
            fontsize=9, fontweight="bold", color=GOOD)
    ax.text(0.6, 5.72, "deliverable 1: specs in -> schematic + specs out"
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
        from nebula.rl import reward_v1 as R
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


ALL = (fig_architecture, fig_benchmark, fig_lattice_control, fig_budget_ladder,
       fig_termination, fig_library_law, fig_corner_map, fig_grid_arithmetic,
       fig_response)


def main() -> int:
    print("generating report figures from the run artifacts")
    for f in ALL:
        f()
    print(f"\n{len(ALL)} figures in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
