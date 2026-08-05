"""
experiments/s9_yield.py — corner-robust yield, and WHICH SPEC BINDS WHERE.

WHAT THIS ANSWERS
-----------------
`BOUNDS_REDERIVATION.md` §7 item 3 and CLAUDEwa §7's claimed contribution #1:
every yield number this project has published is TT/27 C, and S9 requires all
specs to hold at **every** corner. A design that meets everything at nominal
and fails at SS/125 C is a failed design and must score as such.

Two stages, which is the fidelity hierarchy CLAUDEwa §7 claims, at its
cheapest useful scale:

1. **Screen** every sample at three deliberately chosen corners — the slow-hot
   one, the fast-cold one, and the slow-cold one. Three corners cost 3/45 of a
   full sweep and are expected to bracket most of the spread.
2. **Promote** the survivors to all 45 corners and re-verify.

The screen corners are a subset of the 45, so the promotion stage re-runs them.
That is deliberate: it costs 3/45 extra and buys a free consistency check —
a design's verdict at SS/125 C must be identical in both stages, and
`--verify-screen` asserts it. A mismatch would mean the corner plumbing is
not deterministic, which is exactly the class of bug that would invalidate
everything downstream.

THE HEADLINE OUTPUT IS NOT THE YIELD
-------------------------------------
It is **which spec fails first at each corner, and by how much**. A yield is
one number that mostly reflects how the box was drawn (G40). "S3 peaking is
what SS/125 C takes away from you, by a median of N dB" is a design fact that
survives a change of box, tells the RL reward what to weight, and tells a
human what to fix.

Ranking is by the **normalised shortfall** from CLAUDEwa §9,
`min((x - tau)/(|x| + |tau|), 0)` — the project's own reward normaliser, so
"which spec binds" here means the same thing it will mean to the policy. Every
check ALSO carries its margin in natural units (dB, GHz, mV, mW), because a
normalised number is unreadable in a report.

WHAT IS ASSUMED RATHER THAN MEASURED — read `ASSUMPTIONS` below before
quoting anything from this script. Three of them materially affect the answer,
and the tail one makes every corner spread here an UNDERSTATEMENT.

USAGE
    python -m nebula.experiments.s9_yield --n 2000
    python -m nebula.experiments.s9_yield --n 200 --bench-only
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from nebula.common.types import (
    SPEC_F_PEAK_HZ_RANGE,
    SPEC_PEAKING_DB_RANGE,
    SPEC_POWER_MAX_W,
    SPEC_VN_IN_MAX_VRMS,
    Corner,
    all_corners,
)
from nebula.device.sky130_runner import SizingPoint, run_point
from nebula.experiments.s3_yield import (
    PROPOSED_BOX,
    headroom_ok_1v8,
    pin_param,
    sample_box,
    wilson_ci,
)

# ─────────────────────────────────────────────────────────────────────────────
# ASSUMPTIONS. Printed in the output header of every run, and written into the
# results JSON, because each one is a decision a reader must be able to reject.
# ─────────────────────────────────────────────────────────────────────────────

#: `cl` is PINNED, and this is an ASSUMPTION, not an optimisation.
#:
#: CL_SENSITIVITY.md measured 150 fF to be the best of the values tested, but
#: that is not why it is fixed here. It is fixed because `cl` is not a knob a
#: designer turns — it is the following stage's input capacitance plus routing,
#: handed to you by the layout. Searching over it is searching over your own
#: load. This run therefore reports the corner behaviour OF A GIVEN LOAD, and
#: every number below is conditional on that load being 150 fF. A different
#: load gives different numbers and the experiment must be re-run, not scaled.
CL_FIXED_F: float = 150e-15

#: VCM is HELD CONSTANT as VDD moves +/-5%.
#:
#: The alternative — scaling VCM with the rail — assumes the bias network
#: tracks the supply, which is a statement about a circuit that does not exist
#: yet. Holding it fixed is the more conservative reading (the pair sees its
#: headroom squeezed at 0.95 VDD rather than the squeeze being shared), and it
#: matches the box's own provenance, which calls VCM a placeholder for a gate
#: bias that a real RX generates itself. Flagged because it is a choice.
VCM_TRACKS_VDD: bool = False

#: The tail is TWO IDEAL CURRENT SINKS. No simulation in this project has ever
#: contained a tail transistor (BOUNDS_REDERIVATION §6).
#:
#: THIS IS THE ASSUMPTION THAT MATTERS MOST HERE. An ideal sink delivers
#: exactly I_tail at every corner: it does not lose current at SS/125 C, does
#: not gain it at FF/0 C, and does not fall out of saturation when the rail
#: drops 5%. A real tail transistor does all three, and its variation feeds
#: straight into gm, gain, peaking and power. **Every corner spread reported by
#: this script is therefore an UNDERSTATEMENT of the real one**, and the 45-
#: corner yield is an OPTIMISTIC bound. Do not present it as a verified S9
#: result; present it as the corner spread attributable to the input pair
#: alone.
TAIL_IS_IDEAL: bool = True

#: Specs this script does NOT screen, and why. Listed so their absence is
#: explicit rather than inferred from what is missing.
UNSCREENED_SPECS: dict[str, str] = {
    "S4 (HD3 < -30 dBc)": "needs transient+FFT, ~4x the cost of AC+noise "
                          "(G21); belongs in the promotion tier, not the "
                          "screen. Measured ~60 dB inside spec at TT.",
    "S7 (area < 0.05 mm2)": "no MIM cap or poly resistor models pulled yet, "
                            "so there is nothing to compute an area from",
    "S8 (eye > 0.4 UI, > 100 mV)": "a link-layer metric; needs the "
                                   "device->link bridge, which is G2",
}


def assumptions_header(n: int, seed: int) -> str:
    L = [
        "=" * 78,
        "S9 CORNER-ROBUST YIELD",
        "=" * 78,
        f"  samples            {n} Latin-hypercube, seed {seed}",
        # ASCII only in print() -- the Windows console is cp1252 (G10).
        f"  box                PROPOSED_BOX (BOUNDS_REDERIVATION.md sec 6), "
        f"params.py untouched",
        "",
        "  ASSUMPTIONS (each one is a decision you may reject):",
        f"   1. cl PINNED at {CL_FIXED_F * 1e15:.0f} fF. This is an ASSUMPTION, "
        f"not an optimisation.",
        "      cl is the next stage's input capacitance plus routing -- a load,",
        "      not a knob. Every number below is conditional on that load.",
        f"   2. VCM held CONSTANT as VDD moves +/-5% "
        f"({'tracks VDD' if VCM_TRACKS_VDD else 'does not track'}).",
        "      The conservative reading; scaling it would assume a bias network",
        "      that does not exist yet.",
        "   3. The tail is TWO IDEAL CURRENT SINKS -- no tail transistor exists.",
        "      An ideal sink does not lose current at SS/125C or fall out of",
        "      saturation at 0.95 VDD. EVERY CORNER SPREAD BELOW IS THEREFORE",
        "      AN UNDERSTATEMENT, and the 45-corner yield is an OPTIMISTIC bound.",
        "",
        "  NOT SCREENED:",
    ]
    for spec, why in UNSCREENED_SPECS.items():
        L.append(f"   - {spec}: {why}")
    L.append("=" * 78)
    return "\n".join(L)


# ─────────────────────────────────────────────────────────────────────────────
# Corners.
# ─────────────────────────────────────────────────────────────────────────────

#: The three screen corners: slow-hot, fast-cold, slow-cold.
SCREEN_CORNERS: tuple[Corner, ...] = (
    Corner(process="ss", vdd_scale=0.95, temp_c=125.0),
    Corner(process="ff", vdd_scale=1.05, temp_c=0.0),
    Corner(process="ss", vdd_scale=0.95, temp_c=0.0),
)

NOMINAL_VDD: float = 1.8


def point_at_corner(params: dict[str, float], corner: Corner) -> SizingPoint:
    """Build the sizing point as seen at `corner`.

    VDD scaling lives here and nowhere else. VCM either tracks it or does not,
    per `VCM_TRACKS_VDD` — one flag, one place, so the assumption cannot end up
    being made differently in two spots (CLAUDEwa §8 rule 9).
    """
    vdd = NOMINAL_VDD * corner.vdd_scale
    p = dict(params)
    if VCM_TRACKS_VDD:
        p["vcm_in"] = float(p["vcm_in"]) * corner.vdd_scale
    return SizingPoint.from_params(p, vdd=vdd)


# ─────────────────────────────────────────────────────────────────────────────
# Specs, with margins in BOTH natural units and the §9 normalised shortfall.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SpecCheck:
    name: str
    ok: bool
    value: float
    margin: float          # natural units; negative = failed, by this much
    unit: str
    shortfall: float       # CLAUDEwa §9 normalised, <= 0; 0 means met


def _shortfall_min(x: float, tau: float) -> float:
    """`x` must be >= `tau`. §9's normalised form, saturating at 0."""
    denom = abs(x) + abs(tau)
    return min((x - tau) / denom, 0.0) if denom else 0.0


def _shortfall_max(x: float, tau: float) -> float:
    """`x` must be <= `tau`."""
    denom = abs(x) + abs(tau)
    return min((tau - x) / denom, 0.0) if denom else 0.0


def _range_check(name, x, lo, hi, unit, scale=1.0) -> SpecCheck:
    """A two-sided spec scores as the WORSE of its two sides."""
    s = min(_shortfall_min(x, lo), _shortfall_max(x, hi))
    margin = min(x - lo, hi - x)
    return SpecCheck(name=name, ok=(lo <= x <= hi), value=x * scale,
                     margin=margin * scale, unit=unit, shortfall=s)


def check_specs(r, power_w: float) -> list[SpecCheck]:
    """Every spec this script can evaluate, at one corner, for one design.

    Order is fixed so reports line up column-wise. `r` is a `Sky130Point`.
    """
    pk_lo, pk_hi = SPEC_PEAKING_DB_RANGE
    f_lo, f_hi = SPEC_F_PEAK_HZ_RANGE
    checks = [
        _range_check("S3_peaking", r.peaking_db, pk_lo, pk_hi, "dB"),
        _range_check("S3_f_peak", r.f_pk_hz, f_lo, f_hi, "GHz", scale=1e-9),
        SpecCheck("S5_noise", r.vn_in_vrms < SPEC_VN_IN_MAX_VRMS,
                  r.vn_in_vrms * 1e3,
                  (SPEC_VN_IN_MAX_VRMS - r.vn_in_vrms) * 1e3, "mV",
                  _shortfall_max(r.vn_in_vrms, SPEC_VN_IN_MAX_VRMS)),
        SpecCheck("S6_power", power_w < SPEC_POWER_MAX_W, power_w * 1e3,
                  (SPEC_POWER_MAX_W - power_w) * 1e3, "mW",
                  _shortfall_max(power_w, SPEC_POWER_MAX_W)),
        # Not an S3-S8 spec, but a VALIDITY condition: outside saturation the
        # small-signal numbers above describe a circuit that is not amplifying.
        # It gets a row so it can be named as a first failure.
        SpecCheck("saturation", bool(r.in_saturation), r.vds - r.vdsat,
                  r.vds - r.vdsat, "V",
                  _shortfall_min(r.vds, r.vdsat)),
        # S3's reading (b): CLAUDEwa §3 requires BOTH be reported.
        SpecCheck("S3_nyq_boost", r.nyquist_boost_db > 0.0, r.nyquist_boost_db,
                  r.nyquist_boost_db, "dB",
                  _shortfall_min(r.nyquist_boost_db, 0.0)),
    ]
    return checks


@dataclass
class CornerResult:
    """One design at one corner."""
    corner: str
    ok: bool                                  # simulated cleanly
    all_specs_met: bool = False
    fail_reason: Optional[str] = None
    #: Name of the spec with the WORST normalised shortfall, or None if all met.
    first_fail: Optional[str] = None
    first_fail_margin: Optional[float] = None
    first_fail_unit: Optional[str] = None
    first_fail_shortfall: Optional[float] = None
    checks: dict = field(default_factory=dict)   # name -> (ok, value, margin)
    has_interior_peak: Optional[bool] = None
    #: The raw measured scalars behind `checks`, so a downstream analysis can
    #: ask WHERE a design sits rather than only whether it passed. Populated on
    #: every successful evaluation and costs no extra SPICE — the numbers are
    #: already in hand when the verdict is computed. It exists so that
    #: `robust_geometry.py` reads its coordinates from the SAME evaluation that
    #: produced the pass/fail label, instead of re-deriving them in a second
    #: run that could drift from this one (CLAUDEwa §8 rule 9).
    measured: Optional[dict] = None
    #: True if the first ngspice attempt failed and a retry was made. Transient
    #: failures are real on a loaded Windows box and must not be counted as
    #: corner failures -- see evaluate_at_corner.
    retried: bool = False


def _worst(checks: Sequence[SpecCheck]) -> Optional[SpecCheck]:
    failed = [c for c in checks if not c.ok]
    return min(failed, key=lambda c: c.shortfall) if failed else None


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation. Module-level so ProcessPoolExecutor can pickle it.
# ─────────────────────────────────────────────────────────────────────────────


def evaluate_at_corner(task: tuple[dict, str, float, float]) -> CornerResult:
    """One (design, corner) pair. A fresh ngspice parse per point (G36 makes
    that affordable: 0.42 s, and `alter` is not safe for geometry, G35).

    RETRIES ONCE ON FAILURE, and says so in `retried`. Measured reason: a
    2000-point run under heavy load reported 20 failures that **did not
    reproduce at all** on a quiet machine (0/1890, identical inputs and seed).
    They are transient — process launch or temp-directory contention on
    Windows, not properties of the design.

    That distinction is not cosmetic here. A yield experiment that scores a
    transient launch failure as "this design fails at SS/125 C" biases the
    corner yield DOWNWARD by roughly the failure rate, and does it silently,
    because a failed corner and a failed spec look identical once counted. A
    single retry separates the two: a genuine non-convergence fails twice and
    is a real corner failure; a transient one succeeds on the retry and is
    reported as noise rather than as physics.
    """
    params, process, vdd_scale, temp_c = task
    corner = Corner(process=process, vdd_scale=vdd_scale, temp_c=temp_c)
    tag = str(corner)

    reason = headroom_ok_1v8(params, vdd=NOMINAL_VDD * vdd_scale)
    if reason is not None:
        return CornerResult(corner=tag, ok=False,
                            fail_reason=f"headroom: {reason}",
                            first_fail="headroom", first_fail_shortfall=-1.0)

    point = point_at_corner(params, corner)
    # swing=False: the .dc transfer curve costs ~0.05 s/point and feeds the
    # compression check, which is a link-layer question. Nothing screened here
    # reads it.
    r = run_point(point, corner=process, temp_c=temp_c, swing=False)
    retried = False
    if not r.ok:
        retried = True
        r = run_point(point, corner=process, temp_c=temp_c, swing=False)
    if not r.ok:
        return CornerResult(corner=tag, ok=False, fail_reason=r.fail_reason,
                            first_fail="sim_failed", first_fail_shortfall=-1.0,
                            retried=retried)

    checks = check_specs(r, power_w=point.power_w)
    worst = _worst(checks)
    measured = {
        "peaking_db": r.peaking_db, "f_pk_hz": r.f_pk_hz,
        "nyquist_boost_db": r.nyquist_boost_db,
        "g_dc_db": r.g_dc_db, "g_nyq_db": r.g_nyq_db, "g_pk_db": r.g_pk_db,
        "g_top_db": r.g_top_db, "vn_in_vrms": r.vn_in_vrms,
        "gm": r.gm, "gmbs": r.gmbs, "gds": r.gds, "vth": r.vth,
        "vds": r.vds, "vdsat": r.vdsat, "id_a": r.id_a,
        "v_src_dc": r.v_src_dc, "v_out_dc": r.v_out_dc,
        "power_w": point.power_w,
    }
    return CornerResult(
        corner=tag, ok=True,
        all_specs_met=(worst is None),
        first_fail=(worst.name if worst else None),
        first_fail_margin=(worst.margin if worst else None),
        first_fail_unit=(worst.unit if worst else None),
        first_fail_shortfall=(worst.shortfall if worst else None),
        checks={c.name: (c.ok, c.value, c.margin, c.unit) for c in checks},
        has_interior_peak=r.has_interior_peak,
        retried=retried,
        measured=measured,
    )


def run_tasks(tasks, workers: int):
    """Parallel map. workers <= 1 runs a plain serial loop — NOT a 1-worker
    pool, because the point of the serial baseline is to exclude pool overhead
    rather than to measure it."""
    if workers <= 1:
        return [evaluate_at_corner(t) for t in tasks]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(evaluate_at_corner, tasks, chunksize=4))


# ─────────────────────────────────────────────────────────────────────────────
# Reporting.
# ─────────────────────────────────────────────────────────────────────────────


def fmt_rate(k: int, n: int, label: str) -> str:
    lo, hi = wilson_ci(k, n)
    return (f"  {label:38} {k:5d}/{n:<5d} = {k / n * 100:6.2f}%  "
            f"[{lo * 100:5.2f}, {hi * 100:5.2f}]")


def first_fail_table(results: Sequence[CornerResult], title: str) -> str:
    """WHICH spec fails first, and BY HOW MUCH. The headline output."""
    n = len(results)
    failed = [r for r in results if not r.all_specs_met]
    L = [f"  --- {title}: {len(failed)}/{n} designs fail; first failure by spec ---"]
    if not failed:
        L.append("      (none)")
        return "\n".join(L)
    by: dict[str, list] = {}
    for r in failed:
        by.setdefault(r.first_fail or "?", []).append(r)
    L.append(f"      {'spec':14} {'count':>6} {'share':>7}   "
             f"{'median margin':>16}  {'worst margin':>14}")
    for name, rows in sorted(by.items(), key=lambda kv: -len(kv[1])):
        margins = sorted(r.first_fail_margin for r in rows
                         if r.first_fail_margin is not None)
        if margins:
            med = margins[len(margins) // 2]
            unit = next((r.first_fail_unit for r in rows if r.first_fail_unit), "")
            mtxt = f"{med:+10.3f} {unit:<5}"
            wtxt = f"{margins[0]:+9.3f} {unit:<4}"
        else:
            mtxt, wtxt = " " * 16, " " * 14
        L.append(f"      {name:14} {len(rows):6d} {len(rows) / n * 100:6.1f}%   "
                 f"{mtxt}  {wtxt}")
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260804)
    ap.add_argument("--workers", type=int, default=11)
    ap.add_argument("--bench-n", type=int, default=220,
                    help="tasks used for the serial-vs-parallel benchmark")
    ap.add_argument("--bench-only", action="store_true")
    ap.add_argument("--no-bench", action="store_true")
    # Next to the script, not in the cwd: a 28-minute run must not scatter its
    # only record wherever it happened to be launched from.
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent
                    / "s9_yield_results.json")
    args = ap.parse_args(argv)

    print(assumptions_header(args.n, args.seed))
    print()

    params = pin_param(sample_box(PROPOSED_BOX, args.n, args.seed),
                       "cl", CL_FIXED_F)
    # Population = designs feasible at the NOMINAL rail. Corner headroom is
    # then re-checked per corner inside evaluate_at_corner, so losing headroom
    # at 0.95 VDD counts as a corner failure rather than being screened out
    # silently up front.
    feasible = [p for p in params if headroom_ok_1v8(p, NOMINAL_VDD) is None]
    print(f"  {len(params)} sampled -> {len(feasible)} feasible at nominal "
          f"1.8 V ({len(params) - len(feasible)} rejected free)\n")

    results: dict = {"assumptions": {
        "cl_fixed_f": CL_FIXED_F, "vcm_tracks_vdd": VCM_TRACKS_VDD,
        "tail_is_ideal": TAIL_IS_IDEAL, "unscreened": UNSCREENED_SPECS,
        "n_sampled": args.n, "seed": args.seed}}

    # ---- benchmark ---------------------------------------------------------
    if not args.no_bench:
        bench = [(p, c.process, c.vdd_scale, c.temp_c)
                 for c in SCREEN_CORNERS[:1]
                 for p in feasible[:args.bench_n]]
        print(f"--- parallel scaling, {len(bench)} tasks "
              f"({str(SCREEN_CORNERS[0])}) ---")
        t0 = time.perf_counter()
        run_tasks(bench, workers=1)
        t_serial = time.perf_counter() - t0
        print(f"  serial (plain loop)  {t_serial:8.2f} s   "
              f"{t_serial / len(bench) * 1000:7.1f} ms/task   speedup 1.00x")
        bench_rows = {"1": t_serial}
        for w in (2, 4, 8, args.workers):
            if w <= 1 or str(w) in bench_rows:
                continue
            t0 = time.perf_counter()
            run_tasks(bench, workers=w)
            t = time.perf_counter() - t0
            bench_rows[str(w)] = t
            print(f"  {w:2d} workers           {t:8.2f} s   "
                  f"{t / len(bench) * 1000:7.1f} ms/task   "
                  f"speedup {t_serial / t:5.2f}x   "
                  f"efficiency {t_serial / t / w * 100:5.1f}%")
        results["benchmark"] = {"n_tasks": len(bench), "seconds": bench_rows}
        print()
        if args.bench_only:
            args.out.write_text(json.dumps(results, indent=1), encoding="ascii")
            return 0

    # ---- stage 1: screen at 3 corners --------------------------------------
    print(f"--- STAGE 1: screening {len(feasible)} designs at "
          f"{len(SCREEN_CORNERS)} corners "
          f"({len(feasible) * len(SCREEN_CORNERS)} runs) ---")
    for c in SCREEN_CORNERS:
        print(f"    {str(c)}")
    tasks = [(p, c.process, c.vdd_scale, c.temp_c)
             for p in feasible for c in SCREEN_CORNERS]
    t0 = time.perf_counter()
    flat = run_tasks(tasks, workers=args.workers)
    t_screen = time.perf_counter() - t0
    print(f"  {len(tasks)} runs in {t_screen:.1f} s "
          f"({t_screen / len(tasks) * 1000:.1f} ms/run)")
    print(_health(flat) + "\n")

    nc = len(SCREEN_CORNERS)
    per_design = [flat[i * nc:(i + 1) * nc] for i in range(len(feasible))]
    survivors_idx = [i for i, rs in enumerate(per_design)
                     if all(r.all_specs_met for r in rs)]

    n_feas = len(feasible)
    print(fmt_rate(len(survivors_idx), n_feas, "3-CORNER YIELD (all 3 met)"))
    for j, c in enumerate(SCREEN_CORNERS):
        k = sum(1 for rs in per_design if rs[j].all_specs_met)
        print(fmt_rate(k, n_feas, f"  met at {str(c)}"))
    print()
    for j, c in enumerate(SCREEN_CORNERS):
        print(first_fail_table([rs[j] for rs in per_design], str(c)))
        print()

    results["stage1"] = {
        "n_designs": n_feas, "n_survivors": len(survivors_idx),
        "seconds": t_screen, "n_runs": len(tasks),
        "corners": [str(c) for c in SCREEN_CORNERS],
        "per_corner_met": {str(c): sum(1 for rs in per_design
                                      if rs[j].all_specs_met)
                           for j, c in enumerate(SCREEN_CORNERS)},
        "first_fail_counts": {
            str(c): _count_first_fail([rs[j] for rs in per_design])
            for j, c in enumerate(SCREEN_CORNERS)},
    }

    # ---- stage 2: promote survivors to all 45 ------------------------------
    corners45 = all_corners()
    promo = [feasible[i] for i in survivors_idx]
    print(f"--- STAGE 2: promoting {len(promo)} survivors to all "
          f"{len(corners45)} corners ({len(promo) * len(corners45)} runs) ---")
    if not promo:
        print("  no survivors to promote")
        args.out.write_text(json.dumps(results, indent=1), encoding="ascii")
        return 0

    tasks45 = [(p, c.process, c.vdd_scale, c.temp_c)
               for p in promo for c in corners45]
    t0 = time.perf_counter()
    flat45 = run_tasks(tasks45, workers=args.workers)
    t45 = time.perf_counter() - t0
    print(f"  {len(tasks45)} runs in {t45:.1f} s "
          f"({t45 / len(tasks45) * 1000:.1f} ms/run)")
    print(_health(flat45) + "\n")

    n45 = len(corners45)
    per45 = [flat45[i * n45:(i + 1) * n45] for i in range(len(promo))]
    robust = [i for i, rs in enumerate(per45)
              if all(r.all_specs_met for r in rs)]

    print(fmt_rate(len(robust), n_feas,
                   "45-CORNER YIELD (of all sampled)"))
    print(fmt_rate(len(robust), len(promo),
                   "45-CORNER YIELD (of 3-corner survivors)"))
    print()

    # Which corner is deadliest, and what it takes away.
    print("  --- per-corner pass rate among the promoted designs ---")
    rows = []
    for j, c in enumerate(corners45):
        k = sum(1 for rs in per45 if rs[j].all_specs_met)
        ff = _count_first_fail([rs[j] for rs in per45])
        top = max(ff.items(), key=lambda kv: kv[1])[0] if ff else "-"
        rows.append((k / len(promo), str(c), k, top))
    rows.sort()
    print(f"      {'corner':24} {'passing':>16}   first failure")
    for frac, tag, k, top in rows[:8]:
        print(f"      {tag:24} {k:5d}/{len(promo):<5d} {frac * 100:6.1f}%   {top}")
    print("      ...")
    for frac, tag, k, top in rows[-3:]:
        print(f"      {tag:24} {k:5d}/{len(promo):<5d} {frac * 100:6.1f}%   {top}")
    print()
    print(first_fail_table([r for rs in per45 for r in rs],
                           "ALL 45 corners pooled"))

    # Which corner would have caught the screen's false positives. Printed
    # even when there are none, because "none" is itself the answer to
    # "is three corners enough?" and must not be inferred from silence.
    non_robust = [i for i in range(len(promo)) if i not in set(robust)]
    aug = screen_augmentation(per45, corners45, non_robust)
    screen_tags = {str(c) for c in SCREEN_CORNERS}
    print(f"\n  --- the screen's {len(non_robust)} false positive(s): which "
          f"corner would have caught them ---")
    if not non_robust:
        print("      none -- the 3-corner screen was exact on this sample")
    else:
        ranked = sorted(((len(v), k) for k, v in aug.items() if v),
                        reverse=True)
        for k, tag in ranked[:6]:
            mark = " (already screened)" if tag in screen_tags else ""
            print(f"      {tag:24} catches {k}/{len(non_robust)}{mark}")
        best = [t for k, t in ranked if k == len(non_robust)
                and t not in screen_tags]
        if best:
            print(f"      => adding ONE corner ({best[0]}) would have made "
                  f"the screen exact on this sample")

    results["stage2"] = {
        "n_promoted": len(promo), "n_robust": len(robust),
        "seconds": t45, "n_runs": len(tasks45),
        # Design indices are into `feasible`, so a later run can reproduce
        # any single design exactly: sample_box(PROPOSED_BOX, n, seed) ->
        # pin cl -> filter headroom -> index.
        "promoted_design_idx": list(survivors_idx),
        "robust_design_idx": [survivors_idx[i] for i in robust],
        "false_positive_design_idx": [survivors_idx[i] for i in non_robust],
        "false_positive_params": [promo[i] for i in non_robust],
        "screen_augmentation": {k: [survivors_idx[i] for i in v]
                                for k, v in aug.items() if v},
        "per_corner_met": {str(c): sum(1 for rs in per45 if rs[j].all_specs_met)
                           for j, c in enumerate(corners45)},
        "first_fail_counts": {
            str(c): _count_first_fail([rs[j] for rs in per45])
            for j, c in enumerate(corners45)},
        "pooled_first_fail": _count_first_fail(
            [r for rs in per45 for r in rs]),
    }

    # Free consistency check: the 3 screen corners are inside the 45.
    idx = {str(c): j for j, c in enumerate(corners45)}
    mismatches = 0
    for i, sidx in enumerate(survivors_idx):
        for j, c in enumerate(SCREEN_CORNERS):
            if per45[i][idx[str(c)]].all_specs_met != per_design[sidx][j].all_specs_met:
                mismatches += 1
    print(f"\n  screen/promotion consistency: {mismatches} mismatches "
          f"across {len(promo) * len(SCREEN_CORNERS)} repeated (design, corner) "
          f"pairs")
    results["consistency_mismatches"] = mismatches
    if mismatches:
        print("  *** NON-DETERMINISTIC CORNER EVALUATION -- do not trust the "
              "numbers above ***")

    args.out.write_text(json.dumps(results, indent=1), encoding="ascii")
    print(f"\nwrote {args.out}")
    return 0


def _health(results: Sequence[CornerResult]) -> str:
    """Simulator health, printed next to every stage.

    A yield is only as trustworthy as the fraction of runs that produced a
    number at all, and rule 10 says a failure that is not surfaced is not
    handled. Retries are reported separately from hard failures: retries are
    load noise, hard failures are either a design property or a bug, and
    collapsing them hides which.
    """
    n = len(results)
    retried = sum(1 for r in results if r.retried)
    hard = [r for r in results if r.first_fail == "sim_failed"]
    hroom = sum(1 for r in results if r.first_fail == "headroom")
    L = [f"  health: {n - len(hard) - hroom}/{n} simulated, "
         f"{hroom} headroom-rejected, {len(hard)} hard failures, "
         f"{retried} retried"]
    if hard:
        from collections import Counter
        for reason, k in Counter((r.fail_reason or "?")[:90]
                                 for r in hard).most_common(3):
            L.append(f"    {k:5d} x {reason}")
    return "\n".join(L)


def screen_augmentation(per_design45: Sequence[Sequence[CornerResult]],
                        corners: Sequence[Corner],
                        non_robust_idx: Sequence[int]) -> dict[str, list[int]]:
    """Which corner would have caught which of the screen's false positives.

    The screen can only ever be wrong in ONE direction. Its corners are a
    subset of the 45, so a design that fails the screen fails the full sweep by
    construction — there are no false negatives, and the 3-corner yield is a
    hard upper bound on the 45-corner one. The only error is a false positive:
    a design the screen passed and the full sweep rejected. This maps each
    candidate corner to the false positives IT rejects, so the question "what
    is the cheapest screen that would have been exact here?" is answered from
    the data rather than from corner intuition — which §3 of the write-up
    shows is wrong about which corner is worst.

    Returns `{corner_tag: [indices into per_design45]}`, empty lists included
    so a corner that catches nothing is visible as such.
    """
    return {str(c): [i for i in non_robust_idx
                     if not per_design45[i][j].all_specs_met]
            for j, c in enumerate(corners)}


def _count_first_fail(results: Sequence[CornerResult]) -> dict:
    out: dict = {}
    for r in results:
        if not r.all_specs_met:
            out[r.first_fail or "?"] = out.get(r.first_fail or "?", 0) + 1
    return out


if __name__ == "__main__":
    sys.exit(main())
