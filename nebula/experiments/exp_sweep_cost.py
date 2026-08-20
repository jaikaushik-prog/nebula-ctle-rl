"""
experiments/exp_sweep_cost.py — **the number the brief's success criterion
actually asks for, and the arithmetic behind it.**

THE SENTENCE THIS FILE ANSWERS
-------------------------------
`CLAUDEwa.md` §2, quoting Astera verbatim:

    "Should take significantly lower time than **sweeping all MOS, R, C, L
     parameter space**, with zero human intervention."

`BASELINES.md` §13 answers a DIFFERENT and also necessary question: at a
**matched** 150-simulation budget, how does a factorial rank against five other
methods? (Last of six -- at d = 7, 150 simulations buys `150**(1/7)` = 2.06
levels per axis.) That is the right comparison for a fair benchmark and the
wrong one for the brief's sentence, which is not about a matched budget: it is
about what an ACTUAL exhaustive sweep would cost.

**Nothing in this repository has ever stated that number.** This file does.

WHAT IS MEASURED AND WHAT IS EXTRAPOLATED
------------------------------------------
Measured, from run artifacts already on disk and from fresh timing here:

* **the per-simulation cost**, from the 22h sweep's own end-to-end throughput;
* **the per-axis sensitivity of `f_peak` to the box coordinates**, by central
  differences at real designs (`--sensitivity`);
* **the wall-clock of `python -m nebula.design`**, by running it (`--design`).

**Extrapolated, and labelled as such everywhere it appears:** the wall clock of
the full factorial itself. Nobody has run 10^10 simulations and nobody will.
The extrapolation assumes the measured per-simulation cost holds at that scale,
which is optimistic in the sweep's favour -- at 10^10 rows the bookkeeping,
the disk traffic and the cache behaviour are all worse than at 10^4, and none
of that is modelled. **The ratio reported here is therefore a LOWER BOUND on
the speed-up.**

WHY THE LEVEL COUNT IS NOT 8
-----------------------------
Picking a round number per axis is the thing this file must not do, because the
answer is a power of it: at d = 7, choosing 8 instead of 6 changes the total by
**7.5x**, so an arbitrary choice IS the result.

The level count is derived from a resolution requirement this project already
measured and published:

> `PEAK_INTERP.md` / G74: `meas ac g_pk MAX` can only report frequencies on the
> `ac dec 50` lattice, whose spacing is **0.0664386 octaves**. That
> quantisation alone put a hard ceiling of **+8.950669** on the reward and made
> **57 distinct designs tie there across 8 000 simulations.**

So 0.0664386 octaves is the frequency resolution at which THIS PROJECT'S OWN
MEASUREMENT stops being able to tell two designs apart. A parameter grid whose
step moves `f_peak` by more than that cannot place a peak at a specified
frequency any better than the coarse lattice could -- and the coarse lattice is
the defect session 22e was spent removing. A grid whose step moves it by less
buys nothing measurable. **That is the natural spacing, and it is earned rather
than chosen.**

Per axis:

    L_i  =  1 + ceil( |d log2(f_peak) / d u_i|  /  0.0664386 )

with the sensitivity MEASURED, not taken from the design equations.

**Two ways this is wrong, both stated rather than hidden, and they push in
OPPOSITE directions:**

* **It over-counts.** A factorial's reachable set of `f_peak` values is the sum
  of seven per-axis contributions, so combinations resolve a derived scalar
  more finely than any single axis does. A cleverer analysis of the same grid
  would need fewer levels.
* **It under-counts.** `f_peak` is one of seven scored rows. The same grid must
  simultaneously place `peaking`, the Nyquist boost, noise, power and two
  saturation margins, and it has no more degrees of freedom with which to do
  it. A grid sized to resolve one row is not a grid that solves the problem.

Neither correction is applied. The number is reported as an order of magnitude
with both caveats attached, which is what it can honestly support.

    python -m nebula.experiments.exp_sweep_cost --run
    python -m nebula.experiments.exp_sweep_cost --analyse
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.rl.contract import ACTION_NAMES, N_ACTIONS

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "sweep_cost_results.json"

#: **The resolution requirement, and its provenance.** `ac dec 50` puts
#: `log10(f)` samples 1/50 of a decade apart, i.e. `log2` samples
#: `(1/50)/log10(2)` = 0.0664386 octaves apart. G74 / `PEAK_INTERP.md` measured
#: what that costs: a hard reward ceiling and 57 designs tied on it.
#: **Derived here rather than transcribed**, so it cannot drift from `dec 50`.
AC_DEC: int = 50
PEAK_RESOLUTION_OCT: float = (1.0 / AC_DEC) / math.log10(2.0)

#: Central-difference step in normalised box units.
#:
#: **THE FIRST VERSION OF THIS FILE MEASURED THE LATTICE INSTEAD OF THE
#: CIRCUIT, and the output said so plainly enough that it was caught.** At
#: `FD_STEP = 0.05`, reading the peak off the `dec 50` lattice, FOUR of the
#: seven axes returned a gradient of exactly **0.664386 oct/box** with a
#: [min, max] range of exactly [0.66, 0.66] -- which is `10 x
#: PEAK_RESOLUTION_OCT`, i.e. the `f_peak` change was exactly ONE LATTICE STEP
#: on every probe. That is the quantisation floor, not a derivative, and it
#: inflated those axes from 2 levels to 12 each: a factor of **1 296** on the
#: final answer.
#:
#: Two changes, and the first is the one that matters: the peak is now read
#: from the **parabolic sub-lattice interpolation** (`f_pk_interp_hz`, G74 /
#: `PEAK_INTERP.md`, measured 172x closer to the truth than the lattice), so
#: there is no quantisation floor to hit; and the step is doubled so the
#: signal is larger relative to whatever floor remains.
FD_STEP: float = 0.10

#: How many reference designs the sensitivity is measured at. The gradient is
#: not constant over the box (the `f_peak` regression on `u` has R^2 = 0.27),
#: so a single point would be a fluke; the MEDIAN across references is used and
#: the spread is reported.
N_REFS: int = 6


@dataclass
class AxisSensitivity:
    """`|d log2(f_peak) / d u_i|`, in octaves per full box width."""

    name: str
    median_oct: float
    min_oct: float
    max_oct: float
    n_usable: int
    n_probes: int
    levels: int


def _sec_per_sim_measured() -> dict:
    """Per-simulation cost, read out of the 22h sweep's own artifact.

    **Not typed here.** `BASELINES.md` §13's run recorded its end-to-end
    throughput and its measured 8-worker speed-up; both are read back so this
    file cannot drift from the run that produced them. G94 is why the pilot
    figure is not used: a rate calibrated at a fraction of the real budget was
    **17.4x wrong**.
    """
    p = HERE / "baselines_results_interp_grid.json"
    if not p.exists():
        raise FileNotFoundError(
            f"{p} is missing; the per-simulation cost has to come from a run "
            f"that happened, not from a constant in this file.")
    d = json.loads(p.read_text(encoding="utf-8"))
    b = d["header"]["budget"]
    at8 = float(b["sec_per_sim_at_8_workers"])
    speedup = float(b["speedup_at_8"])
    return {
        "sec_per_sim_at_8_workers": at8,
        "speedup_at_8_workers": speedup,
        "sec_per_sim_serial": at8 * speedup,
        "source": "baselines_results_interp_grid.json header.budget",
        "run_total_sims": int(b["total_sims"]),
        "run_wall_s": float(d["wall_s"]),
        "run_observed_sec_per_sim": float(d["wall_s"]) / int(b["total_sims"]),
    }


def _reference_u(n: int = N_REFS, seed: int = 22_073) -> list[tuple]:
    """Reference designs for the finite differences.

    Drawn from the pool of designs that are **feasible** against the delivered
    target, because the sensitivity that matters is the one in the region a
    search actually ends up in. A gradient averaged over the whole box would be
    dominated by sizings nothing would ever propose.
    """
    from nebula.experiments import spec_pool as SP
    from nebula.rl import reward_v1 as R
    from nebula.rl.spec_dist import SpecTarget

    pool = SP.load_pool()
    tgt = SpecTarget(peaking_db=9.0, f_peak_hz=1.9e9)
    ok = [i for i, m in enumerate(pool.meas)
          if R.reward(m, tgt.f_peak_hz, specs=R.V1_SPECS).feasible]
    rng = np.random.default_rng(seed)
    take = rng.choice(np.asarray(ok), size=min(n, len(ok)), replace=False)
    return [tuple(float(x) for x in pool.u[i]) for i in take]


def _f_peak_oct(u: Sequence[float]) -> tuple[Optional[float], bool]:
    """One simulation; `(log2(f_peak / 2.5 GHz), used_interpolation)`.

    **The interpolated peak, not the lattice one.** A finite difference taken
    on a quantised signal reports the quantum, and that is exactly what the
    first version of this analysis did (see `FD_STEP`). `interp_used` is
    returned rather than assumed so a probe that silently fell back to the
    lattice is counted instead of being averaged in.
    """
    from nebula.device.sky130_runner import run_point
    from nebula.experiments.cl_range import committed_cl_range
    from nebula.rl.contract import f_peak_octaves, sizing_from_u
    from nebula.rl.evaluator import build_point

    try:
        sizing = sizing_from_u(np.clip(np.asarray(u, dtype=float), 0.0, 1.0),
                               cl_f=committed_cl_range().cl_mid_f)
        point, _ = build_point(sizing, corner="tt", vdd_scale=1.0)
    except Exception:                                           # noqa: BLE001
        return None, False
    pt = run_point(point, "tt", temp_c=27.0, swing=False, ac_sweep=True,
                   ac_peak_interp=True)
    if not pt.ok or not pt.has_interior_peak or not pt.f_pk_hz:
        return None, False
    if pt.f_pk_interp_hz:
        return f_peak_octaves(float(pt.f_pk_interp_hz)), True
    return f_peak_octaves(float(pt.f_pk_hz)), False


def measure_sensitivity(n_refs: int = N_REFS,
                        step: float = FD_STEP) -> list[AxisSensitivity]:
    """`|d log2(f_peak)/d u_i|` by central differences at real designs.

    **A probe is usable when both ends simulated and BOTH used the sub-lattice
    interpolation.** A probe that fell back to the lattice at either end is
    dropped rather than averaged in, because mixing a quantised reading with an
    interpolated one produces a difference that is partly the quantum -- the
    defect `FD_STEP`'s note records. An axis with no usable probes gets
    `levels = 2`, the minimum a factorial can have, and its zero count is
    printed so a reader can see it was MEASURED as inert.
    """
    refs = _reference_u(n_refs)
    out: list[AxisSensitivity] = []
    for j, name in enumerate(ACTION_NAMES):
        grads, n_probe, n_use = [], 0, 0
        for u in refs:
            lo = list(u); hi = list(u)
            lo[j] = max(0.0, u[j] - step)
            hi[j] = min(1.0, u[j] + step)
            if hi[j] - lo[j] < step:        # pinned at a box edge; skip
                continue
            (a, ia), (b, ib) = _f_peak_oct(lo), _f_peak_oct(hi)
            n_probe += 1
            if a is None or b is None or not (ia and ib):
                continue
            n_use += 1
            grads.append(abs(b - a) / (hi[j] - lo[j]))
        if grads:
            med = float(np.median(grads))
            lv = max(2, 1 + int(math.ceil(med / PEAK_RESOLUTION_OCT)))
            out.append(AxisSensitivity(name, med, float(min(grads)),
                                       float(max(grads)), n_use, n_probe, lv))
        else:
            out.append(AxisSensitivity(name, 0.0, 0.0, 0.0, 0, n_probe, 2))
    return out


def sweep_cost(levels: Sequence[int], sec_per_sim: float,
               workers: int = 8) -> dict:
    """Simulations and wall clock for the full factorial. **EXTRAPOLATION.**"""
    sims = 1
    for l in levels:
        sims *= int(l)
    sec = sims * float(sec_per_sim)
    return {"levels": [int(l) for l in levels], "n_simulations": sims,
            "sec_per_sim": float(sec_per_sim), "workers": workers,
            "wall_clock_s": sec, "wall_clock_hours": sec / 3600.0,
            "wall_clock_years": sec / (3600.0 * 24 * 365.25),
            "is_extrapolation": True}


def measure_design_runtime(method: str, budget: int = 150,
                           peaking: float = 9.0,
                           f_peak_hz: float = 1.9e9) -> dict:
    """Wall-clock of the deliverable, by RUNNING it. Not a model."""
    cmd = [sys.executable, "-m", "nebula.design",
           "--peaking", str(peaking), "--f-peak", f"{f_peak_hz:g}",
           "--method", method]
    if method != "library":
        cmd += ["--budget", str(budget)]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True,
                       cwd=str(HERE.parent.parent))
    el = time.time() - t0
    return {"method": method, "budget": (0 if method == "library" else budget),
            "wall_clock_s": el, "returncode": p.returncode,
            "stderr_tail": p.stderr[-400:] if p.returncode else ""}


def run(n_refs: int = N_REFS, step: float = FD_STEP,
        workers: int = 8) -> dict:
    t0 = time.time()
    cost = _sec_per_sim_measured()
    sens = measure_sensitivity(n_refs, step)
    levels = [s.levels for s in sens]
    at8 = sweep_cost(levels, cost["sec_per_sim_at_8_workers"], workers)
    serial = sweep_cost(levels, cost["sec_per_sim_serial"], 1)

    designs = [measure_design_runtime(m) for m in ("library", "cmaes")]
    ratios = {}
    for d in designs:
        if d["returncode"] == 0 and d["wall_clock_s"] > 0:
            ratios[d["method"]] = at8["wall_clock_s"] / d["wall_clock_s"]

    out = {
        "resolution_oct": PEAK_RESOLUTION_OCT,
        "resolution_basis": (
            f"ac dec {AC_DEC}: log10(f) samples 1/{AC_DEC} of a decade apart, "
            f"so log2 samples (1/{AC_DEC})/log10(2) octaves apart. G74 / "
            f"PEAK_INTERP.md measured that this quantisation alone capped the "
            f"reward at +8.950669 and tied 57 designs across 8000 sims."),
        "fd_step_u": step,
        "n_reference_designs": n_refs,
        "sensitivity": [asdict(s) for s in sens],
        "levels": levels,
        "cost_model": cost,
        "full_factorial_at_8_workers": at8,
        "full_factorial_serial": serial,
        "design_runtimes": designs,
        "speedup_vs_design": ratios,
        "wall_clock_s_of_this_analysis": time.time() - t0,
        "caveats": [
            "The full-factorial wall clock is an EXTRAPOLATION, not a "
            "measurement: it assumes the measured per-simulation cost holds at "
            "10^N scale, which is optimistic in the sweep's favour, so the "
            "ratio is a LOWER BOUND on the speed-up.",
            "Levels are sized per-axis. A factorial's COMBINED resolution in a "
            "derived scalar is finer than any single axis, so this over-counts.",
            "f_peak is one of seven scored rows; the same grid must place all "
            "seven with no extra degrees of freedom, so this under-counts.",
            "The library method's zero simulations are amortised over ~600 "
            "already paid for (SPEC_CONDITIONED.md); the cmaes row is the "
            "from-scratch comparison.",
        ],
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(d: dict) -> None:
    print(f"resolution requirement: {d['resolution_oct']:.7f} octaves "
          f"(ac dec {AC_DEC})")
    print(f"\n  axis      |d log2 f_peak / du|   usable   levels")
    for s in d["sensitivity"]:
        print(f"  {s['name']:8s} {s['median_oct']:9.3f} oct/box "
              f"[{s['min_oct']:.2f}, {s['max_oct']:.2f}] "
              f"{s['n_usable']:3d}/{s['n_probes']:<3d} {s['levels']:8d}")
    ff = d["full_factorial_at_8_workers"]
    print(f"\n  levels             {ff['levels']}")
    print(f"  simulations        {ff['n_simulations']:,}")
    print(f"  at {ff['sec_per_sim']:.5f} s/sim, {ff['workers']} workers:")
    print(f"    wall clock       {ff['wall_clock_hours']:,.0f} hours "
          f"= {ff['wall_clock_years']:,.1f} years   [EXTRAPOLATION]")
    print()
    for r in d["design_runtimes"]:
        sp = d["speedup_vs_design"].get(r["method"])
        print(f"  nebula.design --method {r['method']:8s} "
              f"{r['wall_clock_s']:7.2f} s"
              + (f"   ->  speed-up {sp:,.3g}x" if sp else "   (FAILED)"))
    print("\n  caveats:")
    for c in d["caveats"]:
        print(f"    * {c}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--n-refs", type=int, default=N_REFS)
    ap.add_argument("--step", type=float, default=FD_STEP)
    a = ap.parse_args(argv)
    if a.analyse:
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0
    if not a.run:
        ap.print_help()
        return 2
    _report(run(a.n_refs, a.step))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
