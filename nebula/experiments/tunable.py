"""
experiments/tunable.py — S3 says the peaking is TUNABLE. This scores that.

WHAT THIS ANSWERS
-----------------
Every yield this project has published scores a **fixed sizing point**. S3 says
the CTLE's peaking is *"3-12 dB, tunable"*, via `R_s` and `C_s`. Session 12b's
0.05 % and session 13's 0.05 % are therefore both **lower bounds on what a
tunable part achieves**, and `S9_YIELD.md` §8 and §9 both name measuring the
tunable version as the cheapest thing that could change the verdict.

**The design vector splits in two, and the split is the point:**

    FIXED     w_in, l_in, nf_in, i_bias, rl, vcm_in, and the tail geometry
              (which is derived from i_bias, TAIL_DEVICE.md §3)
    TUNABLE   rs, cs

A design is **tunable-robust** iff, for EVERY (corner, load) point, there
EXISTS an `(rs, cs)` setting meeting all specs. That is a strictly weaker and
strictly more realistic requirement than 12b/13b's "one fixed setting works
everywhere", and it is what a part with a tuning DAC actually has to satisfy.

WHY THIS IS AFFORDABLE AT ALL
------------------------------
`rs` and `cs` are the ideal R and C elements — exactly the case G35 licensed
`alter` for after proving it silently wrong for device geometry. So the whole
grid runs inside ONE ngspice process per (design, corner, load):
**13.6 ms per setting against ~150 ms** for a process each (G48), an 11x
speedup. `run_tunable_sweep` owns that, and its equivalence to a fresh parse is
held to rel=0 abs=0 by a test — without which this is exactly the G35 trap
again.

THE GRID CONTAINS EACH DESIGN'S OWN SETTING — G52
--------------------------------------------------
*"Merge the points a verdict was made at into any grid you then re-measure that
verdict on."* Session 12b's tolerance ladder did not, reported 4.32x against a
screen that had just passed 5.72x, and was nearly published. So the grid here
is the geometric ladder **plus the design's own `(rs, cs)`**, which makes three
things fall out of one run and be consistent by construction:

  * pass at its OWN setting at every (corner, load)  -> reproduces 13b's 1/1890
  * pass at its OWN setting at SOME load             -> reproduces 13b's 146
  * pass at SOME setting at every (corner, load)     -> the new answer

WHAT IS REPORTED BEYOND THE YIELD
----------------------------------
A yield is one number that mostly reflects how the box was drawn (G40). The
outputs a designer can use are:

1. **Is the required setting a function of the load only, or of load AND
   corner?** A real part adapts, so tuning per operating condition is
   legitimate; the question is how much adaptation the loop has to do.
2. **The required TUNING RANGE of `rs` and `cs`, and how many distinct settings
   cover every (corner, load) point.** That is a specification on the tuning
   DAC — *"the CTLE needs an N-bit R_s ladder spanning X-Y ohms"* is an output
   an analog engineer can act on.

USAGE
    python -m nebula.experiments.tunable --n 2000 --workers 8
    python -m nebula.experiments.tunable --n 60 --workers 8     # smoke
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from nebula.common.types import Corner
from nebula.device.sky130_runner import SizingPoint, TunableSetting, run_tunable_sweep
from nebula.experiments.cl_range import committed_cl_range
from nebula.experiments.s3_yield import (
    PROPOSED_BOX,
    headroom_ok_1v8,
    pin_param,
    sample_box,
    wilson_ci,
)
from nebula.experiments.s9_yield import (
    NOMINAL_VDD,
    SCREEN_CORNERS,
    SCREEN_LOADS,
    LoadCorner,
    check_specs,
    load_grid,
    point_at_corner,
    tail_for_design,
    _worst,
)

HERE = Path(__file__).resolve().parent
RESULTS_JSON = HERE / "tunable_results.json"

_CL = committed_cl_range()

#: Grid resolution. 11 x 6 = 66 settings, plus each design's own = 67.
#: `rs` gets the finer axis because it is the primary peaking knob:
#: `k = 1 + (gm + gmbs)*Rs/2` and `peaking_dB ~ 20*log10(k)`, while `cs` only
#: places the zero.
N_RS: int = 11
N_CS: int = 6

#: Session 13's population and its published fixed-sizing counts. The G52
#: consistency gate re-derives both from THIS run's own grid (which contains
#: each design's own setting) and compares. It only fires on the same
#: (n, seed), because at any other sample those counts mean nothing.
S13_POPULATION: tuple = (2000, 20260804)
S13_FIXED_ALL: int = 1
S13_FIXED_ANY_LOAD: int = 146


def tuning_grid(n_rs: int = N_RS, n_cs: int = N_CS,
                include: Sequence[tuple[float, float]] = ()) -> list[TunableSetting]:
    """The `(rs, cs)` grid, geometric over the box bounds.

    Geometric because both enter the response multiplicatively —
    `f_z = 1/(2*pi*Rs*Cs)` and `k = 1 + (gm+gmbs)*Rs/2` — so a linear ladder
    spends most of its rungs where nothing happens.

    **`include` is load-bearing, not a convenience (G52).** The caller passes
    each design's own `(rs, cs)` so that this grid contains the point 13b's
    verdict was made at, and the two are consistent by construction rather than
    consistent-if-the-resolution-happens-to-be-enough.
    """
    if n_rs < 2 or n_cs < 2:
        raise ValueError(f"grid needs >= 2 per axis, got {n_rs}x{n_cs}")
    rs_lo, rs_hi = PROPOSED_BOX["rs"][0], PROPOSED_BOX["rs"][1]
    cs_lo, cs_hi = PROPOSED_BOX["cs"][0], PROPOSED_BOX["cs"][1]
    rs_vals = [rs_lo * (rs_hi / rs_lo) ** (i / (n_rs - 1)) for i in range(n_rs)]
    cs_vals = [cs_lo * (cs_hi / cs_lo) ** (i / (n_cs - 1)) for i in range(n_cs)]
    out = [TunableSetting(r, c) for r in rs_vals for c in cs_vals]
    out += [TunableSetting(float(r), float(c)) for r, c in include]
    return out


def own_setting_index(settings: Sequence[TunableSetting]) -> int:
    """Index of the design's own setting — always the LAST one appended."""
    return len(settings) - 1


@dataclass
class PointResult:
    """One design at one (corner, load), over the whole tuning grid."""

    tag: str
    cl_f: float
    corner: str
    #: Per setting: did it meet every spec?
    met: list
    #: Per setting: the first failure name, or None.
    first_fail: list
    #: Per setting: EVERY spec violated, not just the worst.
    #:
    #: Session 13 measured that the first-failure ranking hides any constraint
    #: travelling with a larger one — `tail_saturation` was violated by 13.3%
    #: and ranked worst by 1.5%. S5 is the constraint most likely to be hidden
    #: that way here, because high `R_s` raises noise AND overshoots the 12 dB
    #: peaking ceiling at the same time. Recording only `first_fail` would make
    #: the pre-registered S5 question unanswerable.
    violated: list
    #: Per setting: measured scalars a downstream analysis needs.
    peaking_db: list
    f_pk_hz: list
    vn_in_vrms: list
    ok: bool = True
    fail_reason: Optional[str] = None

    @property
    def any_setting_works(self) -> bool:
        return any(self.met)

    @property
    def working_idx(self) -> set:
        return {i for i, m in enumerate(self.met) if m}


def evaluate_design_point(task: tuple) -> PointResult:
    """One (design, corner, load) over the full grid. Module-level: picklable."""
    params, process, vdd_scale, temp_c, cl_f, settings = task
    corner = Corner(process=process, vdd_scale=vdd_scale, temp_c=temp_c)
    tag = str(LoadCorner(corner, cl_f))
    n = len(settings)
    blank = [None] * n

    reason = headroom_ok_1v8(params, vdd=NOMINAL_VDD * vdd_scale)
    if reason is not None:
        # Headroom does not read rs or cs, so it kills EVERY setting at once.
        # That is the honest encoding: tuning cannot rescue a design whose
        # load drop leaves no output headroom.
        return PointResult(tag=tag, cl_f=cl_f, corner=str(corner),
                           met=[False] * n, first_fail=["headroom"] * n,
                           violated=[("headroom",)] * n,
                           peaking_db=blank, f_pk_hz=blank, vn_in_vrms=blank,
                           ok=False, fail_reason=f"headroom: {reason}")

    p = {**params, "cl": cl_f}
    point = point_at_corner(p, corner, tail_for_design(p))
    res = run_tunable_sweep(point, settings, corner=process, temp_c=temp_c)
    if res and not res[0].ok and "silent failure" in (res[0].fail_reason or ""):
        res = run_tunable_sweep(point, settings, corner=process, temp_c=temp_c)

    met, ff, vio, pk, fp, vn = [], [], [], [], [], []
    for r in res:
        if not r.ok:
            met.append(False)
            ff.append("sim_failed")
            vio.append(("sim_failed",))
            pk.append(None); fp.append(None); vn.append(None)
            continue
        checks = check_specs(r, power_w=r.power_measured_w)
        worst = _worst(checks)
        met.append(worst is None)
        ff.append(worst.name if worst else None)
        vio.append(tuple(c.name for c in checks if not c.ok))
        pk.append(r.peaking_db); fp.append(r.f_pk_hz); vn.append(r.vn_in_vrms)
    n_fail = sum(1 for f in ff if f == "sim_failed")
    return PointResult(tag=tag, cl_f=cl_f, corner=str(corner), met=met,
                       first_fail=ff, violated=vio, peaking_db=pk, f_pk_hz=fp,
                       vn_in_vrms=vn, ok=(n_fail == 0),
                       fail_reason=(next((r.fail_reason for r in res
                                          if not r.ok), None)
                                    if n_fail else None))


def run_tasks(tasks, workers: int):
    if workers <= 1:
        return [evaluate_design_point(t) for t in tasks]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(evaluate_design_point, tasks, chunksize=2))


# ─────────────────────────────────────────────────────────────────────────────
# Analysis. Pure, so it is tested without a simulator.
# ─────────────────────────────────────────────────────────────────────────────


def adaptation_class(points: Sequence[PointResult],
                     loads: Sequence[float]) -> str:
    """How much the tuning loop has to adapt for THIS design.

    Four outcomes, in increasing order of what they demand of the receiver:

    * `"none"`      — ONE setting works at every (corner, load). The part needs
                      no adaptation at all; the tuning DAC could be trimmed once
                      at test.
    * `"load"`      — one setting per LOAD works across every corner. A part
                      that adapts to its own load (which it must, since the load
                      is the next stage it drives) suffices.
    * `"load+corner"` — a different setting is needed per (corner, load). Still
                      legitimate for a part that adapts in the field from the
                      observed eye, but it demands the loop track PVT as well.
    * `"none_works"` — some (corner, load) has no working setting at all.

    The distinction that matters, and the reason this is reported rather than a
    bare yield: **per-condition tuning is legitimate only if the part can
    OBSERVE the condition.** A design that needs foreknowledge of the process
    corner at trim time is not a design.
    """
    if not points or not all(p.any_setting_works for p in points):
        return "none_works"
    common = set.intersection(*(p.working_idx for p in points))
    if common:
        return "none"
    for cl in loads:
        grp = [p for p in points if p.cl_f == cl]
        if grp and not set.intersection(*(p.working_idx for p in grp)):
            return "load+corner"
    return "load"


def required_settings(points: Sequence[PointResult],
                      settings: Sequence[TunableSetting],
                      loads: Sequence[float]) -> dict:
    """The tuning RANGE this design needs, and how many settings cover it.

    `n_settings` is a greedy set cover over the (corner, load) points — the
    smallest number of distinct DAC codes that leaves no point uncovered. It is
    greedy, not optimal; the greedy answer is an UPPER bound on the true
    minimum, and for a handful of points the two coincide almost always.
    Reported as an upper bound rather than as "the" minimum.
    """
    if not points or not all(p.any_setting_works for p in points):
        return {}
    uncovered = set(range(len(points)))
    chosen: list[int] = []
    while uncovered:
        best, best_cov = None, set()
        for si in range(len(settings)):
            cov = {i for i in uncovered if points[i].met[si]}
            if len(cov) > len(best_cov):
                best, best_cov = si, cov
        if best is None:
            break
        chosen.append(best)
        uncovered -= best_cov
    rs = [settings[i].rs for i in chosen]
    cs = [settings[i].cs for i in chosen]
    per_load = {}
    for cl in loads:
        grp = [p for p in points if p.cl_f == cl]
        common = set.intersection(*(p.working_idx for p in grp)) if grp else set()
        per_load[f"{cl * 1e15:.1f}f"] = sorted(common)
    return {
        "n_settings_upper_bound": len(chosen),
        "chosen_idx": chosen,
        "rs_range": [min(rs), max(rs)] if rs else None,
        "cs_range": [min(cs), max(cs)] if cs else None,
        "rs_ratio": (max(rs) / min(rs)) if rs and min(rs) > 0 else 1.0,
        "cs_ratio": (max(cs) / min(cs)) if cs and min(cs) > 0 else 1.0,
        "common_per_load": per_load,
    }


def dac_spec(all_required: Sequence[dict]) -> dict:
    """Aggregate the per-design tuning demands into ONE DAC specification."""
    rs_lo = [d["rs_range"][0] for d in all_required if d.get("rs_range")]
    rs_hi = [d["rs_range"][1] for d in all_required if d.get("rs_range")]
    cs_lo = [d["cs_range"][0] for d in all_required if d.get("cs_range")]
    cs_hi = [d["cs_range"][1] for d in all_required if d.get("cs_range")]
    n = [d["n_settings_upper_bound"] for d in all_required
         if d.get("n_settings_upper_bound")]
    if not rs_lo:
        return {}
    n_sorted = sorted(n)
    return {
        "rs_span_ohm": [min(rs_lo), max(rs_hi)],
        "cs_span_f": [min(cs_lo), max(cs_hi)],
        "n_settings_median": n_sorted[len(n_sorted) // 2],
        "n_settings_max": max(n),
        "bits_for_max": math.ceil(math.log2(max(n))) if max(n) > 1 else 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Reporting.
# ─────────────────────────────────────────────────────────────────────────────


def fmt_rate(k: int, n: int, label: str) -> str:
    lo, hi = wilson_ci(k, n)
    return (f"  {label:48} {k:5d}/{n:<5d} = {k / n * 100:6.2f}%  "
            f"[{lo * 100:5.2f}, {hi * 100:5.2f}]")


def header(n: int, seed: int, n_set: int, grid) -> str:
    L = ["=" * 78,
         "S3 IS TUNABLE. THIS SCORES THAT.",
         "=" * 78,
         f"  samples            {n} Latin-hypercube, seed {seed}",
         "  FIXED per design   w_in, l_in, nf_in, i_bias, rl, vcm_in, tail",
         f"  TUNABLE            rs, cs -- {N_RS} x {N_CS} geometric grid over "
         f"the box",
         "                     bounds, PLUS each design's own setting "
         f"({n_set} total)",
         f"  scored at          {len(grid)} (corner, load) points",
         "",
         "  FEASIBLE means: for EVERY (corner, load) point there EXISTS an",
         "  (rs, cs) setting meeting all specs. Strictly weaker than sessions",
         "  12b/13's 'one FIXED setting works everywhere', and it is what a",
         "  part with a tuning DAC actually has to satisfy.",
         "",
         "  ASSUMPTIONS (each is a decision you may reject):",
         "   1. The tail is a REAL current mirror, sized by TAIL_DEVICE.md",
         "      sec 3's rule. I_ref is still ideal.",
         "   2. cl is a SCREENED CONTEXT RANGE, not a design variable.",
         "   3. VCM does not track VDD.",
         "   4. Tuning is scored as 'a setting EXISTS'. It does NOT model the",
         "      adaptation loop that has to FIND it, nor DAC quantisation, nor",
         "      the R_s ladder's own parasitics. Every number below is an",
         "      UPPER bound on a real tunable part -- the mirror image of",
         "      12b/13's fixed-sizing LOWER bound.",
         "=" * 78]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260804)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=Path, default=RESULTS_JSON)
    args = ap.parse_args(argv)

    params = pin_param(sample_box(PROPOSED_BOX, args.n, args.seed),
                       "cl", _CL.cl_mid_f)
    feasible = [p for p in params if headroom_ok_1v8(p, NOMINAL_VDD) is None]
    n_feas = len(feasible)
    grid = load_grid(SCREEN_CORNERS, SCREEN_LOADS)
    settings_per = [tuning_grid(include=[(p["rs"], p["cs"])]) for p in feasible]
    n_set = len(settings_per[0])

    print(header(args.n, args.seed, n_set, grid))
    print(f"\n  {len(params)} sampled -> {n_feas} feasible at nominal 1.8 V")
    print(f"  {n_feas * len(grid)} ngspice processes x {n_set} settings = "
          f"{n_feas * len(grid) * n_set} evaluations\n")

    tasks = [(p, g.corner.process, g.corner.vdd_scale, g.corner.temp_c, g.cl_f,
              settings_per[i])
             for i, p in enumerate(feasible) for g in grid]
    t0 = time.perf_counter()
    flat = run_tasks(tasks, workers=args.workers)
    dt = time.perf_counter() - t0
    ng = len(grid)
    per_design = [flat[i * ng:(i + 1) * ng] for i in range(n_feas)]
    n_hard = sum(1 for r in flat if not r.ok and r.fail_reason
                 and "headroom" not in r.fail_reason)
    print(f"  {len(tasks)} processes in {dt:.1f} s "
          f"({dt / len(tasks) * 1000:.0f} ms/process, "
          f"{dt / (len(tasks) * n_set) * 1000:.1f} ms/evaluation)")
    print(f"  health: {len(flat) - n_hard}/{len(flat)} clean, "
          f"{n_hard} hard failures\n")

    own = own_setting_index(settings_per[0])
    fixed_all = sum(1 for rs in per_design if all(r.met[own] for r in rs))
    fixed_any_load = sum(
        1 for rs in per_design
        if any(all(r.met[own] for r in rs if r.cl_f == cl)
               for cl in SCREEN_LOADS))
    print("  --- G52 consistency: this grid CONTAINS each design's own")
    print("      setting, so it must reproduce session 13's fixed-sizing")
    print("      verdict as a special case ---")
    print(fmt_rate(fixed_all, n_feas,
                   "FIXED setting, every (corner,load)  [13b: 1]"))
    print(fmt_rate(fixed_any_load, n_feas,
                   "FIXED setting, robust at SOME load  [13b: 146]"))
    # The gate only APPLIES on session 13's own population. At any other
    # (n, seed) the sample is different and 1/146 are not the expected counts —
    # asserting them there would be a false alarm on every smoke run, which is
    # how a real gate gets ignored.
    if (args.n, args.seed) == S13_POPULATION:
        ok13 = (fixed_all == S13_FIXED_ALL and
                fixed_any_load == S13_FIXED_ANY_LOAD)
        print("      => " + ("CONSISTENT with session 13"
                             if ok13 else
                             f"*** DISAGREES WITH SESSION 13 "
                             f"(expected {S13_FIXED_ALL} and "
                             f"{S13_FIXED_ANY_LOAD}) -- do not trust the "
                             f"numbers below ***"))
    else:
        ok13 = None
        print(f"      => gate NOT APPLICABLE: it is defined on n="
              f"{S13_POPULATION[0]} seed={S13_POPULATION[1]}, this run is "
              f"n={args.n} seed={args.seed}")
    print()

    tunable = [i for i, rs in enumerate(per_design)
               if all(r.any_setting_works for r in rs)]
    print(fmt_rate(len(tunable), n_feas,
                   "TUNABLE-ROBUST (a setting EXISTS everywhere)"))
    for j, g in enumerate(grid):
        k = sum(1 for rs in per_design if rs[j].any_setting_works)
        print(fmt_rate(k, n_feas, f"  a setting works at {g}"))
    print()

    classes = {}
    for i in tunable:
        c = adaptation_class(per_design[i], SCREEN_LOADS)
        classes[c] = classes.get(c, 0) + 1
    print("  --- how much adaptation does the tuning loop have to do? ---")
    for c in ("none", "load", "load+corner", "none_works"):
        if c in classes:
            print(f"      {c:14} {classes[c]:5d}  "
                  f"{classes[c] / max(len(tunable), 1) * 100:6.1f}% of "
                  f"tunable-robust designs")
    print("      none        = ONE setting works everywhere; trim once at test")
    print("      load        = one setting per LOAD, across all corners. The")
    print("                    part must adapt to its load -- which it can")
    print("                    OBSERVE, since the load is the stage it drives")
    print("      load+corner = a setting per (corner, load); the loop must also")
    print("                    track PVT. Legitimate for a field-adaptive part,")
    print("                    NOT as a design-time trim, which would need")
    print("                    foreknowledge of the corner.")
    print()

    reqs = [required_settings(per_design[i], settings_per[i], SCREEN_LOADS)
            for i in tunable]
    spec = dac_spec([r for r in reqs if r])
    print("  --- the output an analog engineer can use: the TUNING DAC spec ---")
    if spec:
        rs_lo, rs_hi = spec["rs_span_ohm"]
        cs_lo, cs_hi = spec["cs_span_f"]
        print(f"      R_s must span   {rs_lo:8.1f} - {rs_hi:8.1f} ohm "
              f"({rs_hi / rs_lo:.2f}x)")
        print(f"      C_s must span   {cs_lo * 1e15:8.1f} - {cs_hi * 1e15:8.1f}"
              f" fF ({cs_hi / cs_lo:.2f}x)")
        print(f"      settings per design: median "
              f"{spec['n_settings_median']}, max {spec['n_settings_max']} "
              f"=> {spec['bits_for_max']} bits")
        print("      (per-design counts are a GREEDY set cover, so each is an")
        print("       UPPER bound on that design's true minimum.)")
    else:
        print("      (no tunable-robust design, so no DAC spec)")
    print()

    print("  --- PRE-REGISTERED: does S5 bind at the high-R_s end? ---")
    print("      Reported BOTH ways, because session 13 measured that the")
    print("      first-failure ranking hides constraints travelling with")
    print("      larger ones -- and high R_s raises noise AND overshoots the")
    print("      12 dB peaking ceiling at the same time.")
    rs_vals = sorted({st.rs for st in settings_per[0]})
    hi_rs = rs_vals[-3:]
    n_s5_first = n_s5_viol = n_any = 0
    worst_vn = 0.0
    worst_at = None
    by_rs: dict = {}
    for i, pts in enumerate(per_design):
        for r in pts:
            for si, st in enumerate(settings_per[i]):
                v = r.violated[si]
                if v:
                    n_any += 1
                if r.first_fail[si] == "S5_noise":
                    n_s5_first += 1
                if "S5_noise" in v:
                    n_s5_viol += 1
                    by_rs[st.rs] = by_rs.get(st.rs, 0) + 1
                if r.vn_in_vrms[si] and r.vn_in_vrms[si] > worst_vn:
                    worst_vn, worst_at = r.vn_in_vrms[si], st
    print(f"      S5_noise VIOLATED    in {n_s5_viol:7d} of {n_any} failing "
          f"evaluations ({n_s5_viol / max(n_any, 1) * 100:.3f}%)")
    print(f"      S5_noise RANKED WORST in {n_s5_first:6d} "
          f"({n_s5_first / max(n_any, 1) * 100:.3f}%)")
    if worst_at is not None:
        print(f"      worst input-referred noise anywhere on the grid: "
              f"{worst_vn * 1e3:.4f} mV")
        print(f"          at {worst_at.tag()}, against the 1.5 mV spec "
              f"({worst_vn / 1.5e-3 * 100:.1f}% of it)")
    if by_rs:
        print(f"      S5 violations by R_s (top of the ladder is "
              f"{rs_vals[-1]:.0f} ohm):")
        for rs in sorted(by_rs)[-5:]:
            print(f"          rs {rs:8.1f} ohm : {by_rs[rs]:7d}")
    else:
        print(f"      S5 is violated NOWHERE on the grid -- the highest R_s "
              f"tested is {rs_vals[-1]:.0f} ohm")

    results = {
        "n_designs": n_feas, "n_grid_points": len(grid), "n_settings": n_set,
        "seconds": dt, "n_hard_failures": n_hard,
        "fixed_all": fixed_all, "fixed_any_load": fixed_any_load,
        "consistent_with_13b": ok13,
        "n_tunable_robust": len(tunable), "tunable_idx": tunable,
        "adaptation_classes": classes, "dac_spec": spec,
        "s5_first_fail": n_s5_first, "s5_violated": n_s5_viol,
        "n_failing_evals": n_any, "worst_vn": worst_vn,
        "worst_vn_at_rs": (worst_at.rs if worst_at else None),
        "s5_violations_by_rs": {str(k): v for k, v in by_rs.items()},
        "per_point_any_setting": {
            str(g): sum(1 for rs in per_design if rs[j].any_setting_works)
            for j, g in enumerate(grid)},
        "per_design_required": {str(i): r for i, r in zip(tunable, reqs) if r},
    }
    args.out.write_text(json.dumps(results, indent=1, default=float),
                        encoding="ascii")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
