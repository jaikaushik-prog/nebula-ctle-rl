"""
experiments/s9_yield.py — corner-AND-LOAD-robust yield, and WHICH SPEC BINDS.

WHAT THIS ANSWERS
-----------------
`BOUNDS_REDERIVATION.md` §7 item 3 and CLAUDEwa §7's claimed contribution #1:
every yield number this project has published is TT/27 C, and S9 requires all
specs to hold at **every** corner. A design that meets everything at nominal
and fails at SS/125 C is a failed design and must score as such.

**Session 12b adds a second axis: the LOAD.** `cl` used to be pinned at
150 fF — the value that maximised the S3 yield among five tested, which
`CL_SENSITIVITY.md` §6 itself flagged as choosing the answer. `CL_RANGE.md`
derives it instead from what physically hangs on the CTLE output and gets
13.6-78.0 fF, a range whose TOP is 1.92x BELOW the old pin. `cl` is neither a
design variable (nobody chooses the following stage's input capacitance) nor a
constant (it is not known to one value), so it is treated as a **context
variable with a derived range and screened like a PVT corner**: a design counts
only if it passes at every (corner, load) pair.

Three stages, which is the fidelity hierarchy CLAUDEwa §7 claims, at its
cheapest useful scale:

0. **Nominal**, at both load edges — the denominator. Without it, "the load
   costs X%" cannot be separated from "the corners cost X%".
1. **Screen** every sample at three deliberately chosen corners (slow-hot,
   fast-cold, slow-cold) x both load edges — 6 evaluations per design.
2. **Promote** the survivors to all 45 corners x three loads: both edges plus
   the geometric centre, because two-edge screening cannot see a design that
   fails in the MIDDLE of the range, and for a two-sided spec that is not
   impossible (G46's mechanism, on the load axis).

The screen grid is a subset of the promotion grid, so the promotion stage
re-runs it. That is deliberate: it buys a free consistency check — a design's
verdict at a repeated (corner, load) point must be identical in both stages,
and `main` counts the mismatches. A mismatch would mean the plumbing is not
deterministic, which is exactly the class of bug that would invalidate
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
    python -m nebula.experiments.s9_yield --n 2000 --no-bench
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
from nebula.experiments.cl_range import committed_cl_range
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

#: `cl` is a SCREENED CONTEXT RANGE, not a pin — session 12b.
#:
#: It used to be pinned at 150 fF, which was the best of five values tested for
#: S3 yield; `CL_SENSITIVITY.md` §6 flagged that as choosing the answer.
#: `CL_RANGE.md` derives it instead from what physically loads the CTLE output
#: (the 1-tap DFE summer input pair, the slicer input pair, and the routing
#: between them) and gets **13.64 / 32.63 / 78.04 fF** — a range whose TOP is
#: 1.92x BELOW the old pin.
#:
#: `cl` is therefore neither a design variable (nobody chooses the following
#: stage's input capacitance — G42 measured that searching it LOWERS the yield)
#: nor a constant (it is not known to one value). It is a **context variable
#: with a physically derived range**, and it is screened like a PVT corner: a
#: design is feasible only if it passes at EVERY (corner, load) pair.
#:
#: ONE DEFINITION (CLAUDEwa §8 rule 9): the numbers are re-derived from
#: `cl_range_data.csv` at import, never restated here.
_CL = committed_cl_range()

#: Screen: both edges of the range. The cheapest set that can see the spread.
SCREEN_LOADS: tuple[float, ...] = (_CL.cl_lo_f, _CL.cl_hi_f)

#: Promotion: both edges plus the geometric centre, in case a design fails in
#: the MIDDLE of the range — which two-edge screening cannot see, and which is
#: not impossible for a two-sided spec (G46's mechanism, on the load axis).
PROMOTION_LOADS: tuple[float, ...] = (_CL.cl_lo_f, _CL.cl_mid_f, _CL.cl_hi_f)

#: The load sessions 10d and 11 were run at. Kept ONLY so their published
#: results stay reproducible: `robust_geometry.py::population()` rebuilds 10d's
#: 1890 designs from it and `check_reproduction()` asserts 10d's counts, so
#: moving this breaks that gate loudly rather than silently. **It is not the
#: load this script screens at any more** and it is outside the derived range.
CL_LEGACY_PIN_F: float = 150e-15

#: Session 10d's published figures, at `CL_LEGACY_PIN_F`. Quoted in the report
#: so the new numbers sit next to the ones they supersede rather than in a
#: different document. Source: `S9_YIELD.md` §4.
LEGACY_150FF: dict[str, tuple[int, int]] = {
    "TT / 1.00 / 27 C": (255, 1890),
    "all 3 screen corners": (155, 1890),
    "all 45 corners": (153, 1890),
}

#: The nominal point. NOT one of the screen corners, which is what makes
#: "no design fails nominal yet passes the extremes" a measurement (S9_YIELD §4).
NOMINAL_CORNER: Corner = Corner(process="tt", vdd_scale=1.00, temp_c=27.0)

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
        "S9 CORNER-AND-LOAD-ROBUST YIELD",
        "=" * 78,
        f"  samples            {n} Latin-hypercube, seed {seed}",
        # ASCII only in print() -- the Windows console is cp1252 (G10).
        f"  box                PROPOSED_BOX (BOUNDS_REDERIVATION.md sec 6), "
        f"params.py untouched",
        f"  screen             {len(SCREEN_CORNERS)} corners x "
        f"{len(SCREEN_LOADS)} loads = "
        f"{len(SCREEN_CORNERS) * len(SCREEN_LOADS)} evaluations per design",
        f"  promotion          45 corners x {len(PROMOTION_LOADS)} loads = "
        f"{45 * len(PROMOTION_LOADS)} evaluations per survivor",
        "",
        "  ASSUMPTIONS (each one is a decision you may reject):",
        f"   1. cl is a SCREENED CONTEXT RANGE, "
        f"{SCREEN_LOADS[0] * 1e15:.2f} - {SCREEN_LOADS[-1] * 1e15:.2f} fF "
        f"({_CL.ratio:.2f}x, {_CL.octaves:.2f} octaves),",
        f"      derived in CL_RANGE.md from the gate load of the DFE summer "
        f"and slicer",
        f"      input pairs plus routing. It is NOT pinned any more. The old "
        f"pin was",
        f"      {CL_LEGACY_PIN_F * 1e15:.0f} fF -- "
        f"{CL_LEGACY_PIN_F / _CL.cl_hi_f:.2f}x ABOVE the top of this range -- "
        f"and every",
        f"      number in S9_YIELD.md was measured there. A design must pass "
        f"at EVERY",
        f"      (corner, load) pair; cl is a context, so it is screened, not "
        f"searched.",
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


@dataclass(frozen=True)
class LoadCorner:
    """One point of the (PVT corner x load) grid — the thing a design is now
    scored at.

    Exists so that "which corner would have caught this design?" keeps working
    unchanged once the grid gains a second axis: `screen_augmentation` keys on
    `str()`, so a load-corner is a corner as far as that bookkeeping is
    concerned.
    """

    corner: Corner
    cl_f: float

    def __str__(self) -> str:
        return f"{self.corner} @ cl {self.cl_f * 1e15:.1f}f"


def load_grid(corners: Sequence[Corner],
              loads: Sequence[float]) -> list[LoadCorner]:
    """Cross product, corners-major so a report reads corner by corner."""
    return [LoadCorner(c, cl) for c in corners for cl in loads]


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
    """One design at one (corner, load) point."""
    corner: str
    ok: bool                                  # simulated cleanly
    #: The load this evaluation used. Carried explicitly rather than inferred
    #: from `corner`'s string so that a result can never be attributed to the
    #: wrong edge of the range while still looking well-formed.
    cl_f: Optional[float] = None
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


def evaluate_at_corner(
    task: "tuple[dict, str, float, float] | tuple[dict, str, float, float, float]"
) -> CornerResult:
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

    A FIFTH element sets the LOAD for this evaluation, overwriting the design's
    own `cl`. It is optional so that a caller that has already pinned `cl` into
    the params (`robust_geometry.py`, which reproduces session 10d at its
    150 fF pin) keeps working untouched.
    """
    params, process, vdd_scale, temp_c = task[:4]
    cl_f = task[4] if len(task) > 4 else float(params["cl"])
    if cl_f != params["cl"]:
        params = {**params, "cl": cl_f}
    corner = Corner(process=process, vdd_scale=vdd_scale, temp_c=temp_c)
    tag = str(LoadCorner(corner, cl_f))

    reason = headroom_ok_1v8(params, vdd=NOMINAL_VDD * vdd_scale)
    if reason is not None:
        return CornerResult(corner=tag, ok=False, cl_f=cl_f,
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


def load_edge_table(per_design: Sequence[Sequence[CornerResult]],
                    grid: Sequence[LoadCorner],
                    loads: Sequence[float]) -> dict[str, int]:
    """How many designs are corner-robust at EACH load, and at all of them.

    Pre-registered in `PREDICTIONS.md` entry 1 before the run: if the joint
    count is near zero, "0 %" on its own says nothing, and the useful question
    becomes whether the per-load sets are large but DISJOINT. That would mean
    *"the CTLE can be made corner-robust at either load, but not at both"* — a
    statement about how tightly the load has to be specified, rather than a
    statement that the topology fails.

    Costs nothing: it re-reads the evaluations the screen already made.
    """
    out: dict[str, int] = {}
    per_load_sets: list[set[int]] = []
    for cl in loads:
        idx = [j for j, g in enumerate(grid) if g.cl_f == cl]
        s = {i for i, rs in enumerate(per_design)
             if all(rs[j].all_specs_met for j in idx)}
        per_load_sets.append(s)
        out[f"robust at cl {cl * 1e15:.1f}f alone"] = len(s)
    both = set.intersection(*per_load_sets) if per_load_sets else set()
    union = set.union(*per_load_sets) if per_load_sets else set()
    out["robust at EVERY load"] = len(both)
    out["robust at ANY load"] = len(union)
    out["robust at exactly one load"] = len(union) - len(both)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# The pre-registered follow-up (PREDICTIONS.md entry 1).
#
# A yield of 1/1890 says the load range cannot be absorbed. It does not say HOW
# MUCH load range CAN be absorbed, and that is the number a designer needs: it
# is the tolerance the following stage's input capacitance has to be specified
# to before this topology can be signed off.
#
# Both measurements below run on a handful of designs and cost seconds, unlike
# the 49-minute sweep they follow.
# ─────────────────────────────────────────────────────────────────────────────

#: Ladder for the tolerance measurement: 5 fF to 300 fF, geometric. Spans the
#: derived range (13.6-78.0 fF) with room on both sides, and includes the
#: superseded 150 fF pin's neighbourhood so the two are on one axis.
def cl_ladder(n: int = 15, lo_f: float = 5e-15, hi_f: float = 300e-15,
              include: Sequence[float] = ()) -> tuple[float, ...]:
    """Geometric ladder, with `include` merged in and the whole thing sorted.

    Geometric because `cl` enters f_p2 = 1/(2*pi*RL*CL) multiplicatively — a
    linear ladder spends most of its rungs where nothing happens.

    **`include` is load-bearing, not a convenience.** The first version of this
    ladder did not contain `cl_lo`/`cl_hi`, and it reported the one
    corner-and-load-robust design as tolerating 16.1-69.5 fF = 4.32x — which
    CONTRADICTS the screen that found it, since the screen passed it at 13.64
    and 78.04 fF. The ladder was simply too coarse to contain the points the
    verdict was made at. Merging the screen's own loads in makes the tolerance
    measurement consistent with the sweep by construction, instead of
    consistent-if-the-resolution-happens-to-be-enough.
    """
    if n < 2:
        raise ValueError("a ladder needs at least two rungs")
    r = (hi_f / lo_f) ** (1.0 / (n - 1))
    rungs = {lo_f * r ** i for i in range(n)} | {float(c) for c in include}
    return tuple(sorted(rungs))


def widest_passing_ratio(flags: Sequence[bool],
                         cls: Sequence[float]) -> tuple[float, Optional[tuple]]:
    """Widest `cl` ratio spanned by a CONTIGUOUS run of passes.

    Contiguous, not merely the min and max passing value: `cl` is a context a
    design has to tolerate over an INTERVAL, so a design that passes at 10 fF
    and at 100 fF but fails at 30 fF does not tolerate a 10x range. That is not
    hypothetical — S3 is two-sided, so a design can leave the window through
    either edge as the load moves (G46's mechanism, on the load axis).

    Returns `(ratio, (cl_first, cl_last))`, or `(0.0, None)` if nothing passes.
    A single passing rung gives a ratio of 1.0: it tolerates a point, not a
    range.
    """
    if len(flags) != len(cls):
        raise ValueError(f"{len(flags)} flags against {len(cls)} cl values")
    best, span, start = 0.0, None, None
    for i, ok in enumerate(list(flags) + [False]):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            r = cls[i - 1] / cls[start]
            if r > best:
                best, span = r, (cls[start], cls[i - 1])
            start = None
    return best, span


def fpeak_exponent(cls: Sequence[float],
                   f_pks: Sequence[float]) -> Optional[float]:
    """`d log(f_peak) / d log(cl)`, by least squares. None if not computable.

    THE PREDICTION'S MECHANISM, MADE MEASURABLE. `PREDICTIONS.md` entry 1 rests
    on f_peak moving as roughly `cl^-0.5` — supported by one probed sample in
    `CL_SENSITIVITY.md` (slope -0.48) and by the structural argument that the
    peak of a 1-zero/2-pole response sits near the geometric mean of f_p1 and
    f_p2. If the measured exponent across the box is materially weaker than
    0.5, the reasoning is wrong even where the number happened to be right,
    and that is the thing worth knowing.
    """
    pts = [(math.log(c), math.log(f)) for c, f in zip(cls, f_pks)
           if c > 0 and f and f > 0]
    if len(pts) < 2:
        return None
    n = len(pts)
    sx = sum(x for x, _ in pts)
    sy = sum(y for _, y in pts)
    sxx = sum(x * x for x, _ in pts)
    sxy = sum(x * y for x, y in pts)
    denom = n * sxx - sx * sx
    return (n * sxy - sx * sy) / denom if denom else None


def tolerance_main(args) -> int:
    """`--tolerance-only`: the follow-up, off the committed results JSON."""
    if not args.out.exists():
        print(f"  {args.out} not found -- run the sweep first")
        return 1
    saved = json.loads(args.out.read_text(encoding="ascii"))
    params = pin_param(sample_box(PROPOSED_BOX, args.n, args.seed),
                       "cl", _CL.cl_mid_f)
    feasible = [p for p in params if headroom_ok_1v8(p, NOMINAL_VDD) is None]

    ladder = cl_ladder(include=PROMOTION_LOADS)
    print("=" * 78)
    print("LOAD TOLERANCE -- how much cl range this topology CAN absorb")
    print("=" * 78)
    print(f"  ladder: {len(ladder)} rungs, {ladder[0] * 1e15:.1f} - "
          f"{ladder[-1] * 1e15:.1f} fF, geometric, with the screen's own "
          f"loads merged in")
    print(f"  demanded by CL_RANGE.md: {_CL.ratio:.2f}x "
          f"({_CL.octaves:.2f} octaves)\n")

    robust_idx = saved.get("stage2", {}).get("robust_design_idx", [])
    print(f"  --- the {len(robust_idx)} corner-and-load-robust design(s) ---")
    tol_rows = []
    for i in robust_idx:
        p = feasible[i]
        tasks = [(p, c.process, c.vdd_scale, c.temp_c, cl)
                 for cl in ladder for c in SCREEN_CORNERS]
        res = run_tasks(tasks, workers=args.workers)
        flags = [all(r.all_specs_met for r in res[k * len(SCREEN_CORNERS):
                                                 (k + 1) * len(SCREEN_CORNERS)])
                 for k in range(len(ladder))]
        ratio, span = widest_passing_ratio(flags, ladder)
        tol_rows.append((i, ratio, span))
        bar = "".join("#" if f else "." for f in flags)
        print(f"      design {i:5d}  [{bar}]  widest contiguous "
              f"{ratio:5.2f}x" + (f"  ({span[0] * 1e15:.1f} - "
                                  f"{span[1] * 1e15:.1f} fF)" if span else ""))
    print(f"      (rungs left to right: {ladder[0] * 1e15:.1f} .. "
          f"{ladder[-1] * 1e15:.1f} fF)")

    # The exponent, on designs that actually have a peak to move. ONE pool for
    # the whole block: a pool per design costs more in process startup than the
    # simulations do (155 pools took 15 min for 775 runs).
    print(f"\n  --- f_peak vs cl: is the prediction's cl^-0.5 model right? ---")
    probe_cls = cl_ladder(5, _CL.cl_lo_f, _CL.cl_hi_f)
    block = feasible[:args.exponent_n]
    tasks = [(p, "tt", 1.00, 27.0, cl) for p in block for cl in probe_cls]
    res = run_tasks(tasks, workers=args.workers)
    nc = len(probe_cls)
    exps: list[float] = []
    n_lost_peak = 0
    for k in range(len(block)):
        rs = res[k * nc:(k + 1) * nc]
        if not all(r.ok and r.has_interior_peak for r in rs):
            n_lost_peak += 1
            continue
        e = fpeak_exponent(probe_cls, [r.measured["f_pk_hz"] for r in rs])
        if e is not None:
            exps.append(e)
    print(f"      {len(block)} designs probed at {nc} loads spanning the "
          f"derived range")
    print(f"      {n_lost_peak} of them ({n_lost_peak / len(block) * 100:.0f}%)"
          f" do NOT keep an interior peak across it -- they lose the peak")
    print(f"      entirely rather than moving it out of the window, which is a "
          f"SECOND failure mode")
    if exps:
        exps.sort()
        med = exps[len(exps) // 2]
        moved = _CL.ratio ** abs(med)
        print(f"      the remaining {len(exps)}:")
        print(f"        d log f_peak / d log cl:  median {med:+.3f}   "
              f"range {exps[0]:+.3f} .. {exps[-1]:+.3f}")
        print(f"        PREDICTIONS.md assumed -0.500 (peak at the geometric "
              f"mean of f_p1, f_p2);")
        print(f"        CL_SENSITIVITY's single probe measured -0.48")
        print(f"        => a {_CL.ratio:.2f}x load range moves f_peak by "
              f"{moved:.2f}x = {math.log2(moved):.2f} octaves, against S3's "
              f"1.00-octave window,")
        print(f"           leaving {1.0 - math.log2(moved):.2f} octaves of "
              f"slack -- about "
              f"{(1.0 - math.log2(moved)) / 0.0664:.0f} of the 15 distinct "
              f"f_peak values that window holds (session 11)")
    else:
        print("      no design kept an interior peak across the whole range")

    saved["tolerance"] = {
        "ladder_f": list(ladder),
        "robust": [{"idx": i, "ratio": r,
                    "span_f": list(s) if s else None} for i, r, s in tol_rows],
        "fpeak_exponents": exps,
        "n_probed": len(block), "n_lost_peak": n_lost_peak,
    }
    args.out.write_text(json.dumps(saved, indent=1), encoding="ascii")
    print(f"\nwrote {args.out}")
    return 0


def comparison_table(n: int, n_screen: int, n_full: Optional[int],
                     n_nominal: Optional[int]) -> str:
    """The new numbers next to the ones they supersede.

    Both columns are the SAME 1890 designs — `headroom_ok_1v8` does not read
    `cl`, so the population is identical to session 10d's and the comparison is
    paired rather than between two samples.
    """
    L = ["  " + "=" * 74,
         "  THE COMPARISON: same designs, two treatments of cl",
         "  " + "=" * 74,
         f"      {'':34} {'pinned 150 fF':>16}   {'range 13.6-78 fF':>24}",
         f"      {'':34} {'(session 10d)':>16}   {'(this run)':>24}"]

    def _row(label: str, legacy: Optional[tuple], new: Optional[int]) -> str:
        if legacy is None:
            lt = " " * 16
        else:
            k, nn = legacy
            lt = f"{k:5d}/{nn:<5d}{k / nn * 100:6.2f}%"
        if new is None:
            nt = f"{'not measured':>24}"
        else:
            lo, hi = wilson_ci(new, n)
            nt = (f"{new:5d}/{n:<5d}{new / n * 100:6.2f}% "
                  f"[{lo * 100:.2f},{hi * 100:.2f}]")
        return f"      {label:34} {lt}   {nt}"

    L.append(_row("nominal PVT (TT/1.00/27 C)",
                  LEGACY_150FF["TT / 1.00 / 27 C"], n_nominal))
    L.append(_row("screen (3 corners)", LEGACY_150FF["all 3 screen corners"],
                  n_screen))
    L.append(_row("full sweep (45 corners)", LEGACY_150FF["all 45 corners"],
                  n_full))
    L += ["  " + "-" * 74,
          "      LEFT:  3 and 45 corners at ONE load -- the S3-yield maximum "
          "of five values",
          "             tested, and 1.92x above the top of the derived range.",
          "      RIGHT: the same corners x BOTH edges of the derived range. A "
          "design counts",
          "             only if it passes at every (corner, load) pair.",
          "  " + "=" * 74]
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
    ap.add_argument("--no-nominal", action="store_true",
                    help="skip stage 0; the TT denominator is then unmeasured")
    ap.add_argument("--tolerance-only", action="store_true",
                    help="skip the sweep; run the PREDICTIONS.md follow-up off "
                         "the committed results JSON (seconds, not minutes)")
    ap.add_argument("--exponent-n", type=int, default=40,
                    help="designs sampled for the f_peak-vs-cl exponent")
    # Next to the script, not in the cwd: a long run must not scatter its only
    # record wherever it happened to be launched from.
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent
                    / "s9_yield_results.json")
    args = ap.parse_args(argv)

    if args.tolerance_only:
        return tolerance_main(args)

    print(assumptions_header(args.n, args.seed))
    print()

    # `cl` is overwritten per evaluation from the screen/promotion grids, so
    # the value pinned here only has to be a valid placeholder. It is cl_mid,
    # so anything reading a design dict without a grid entry sees the centre of
    # the derived range rather than the superseded pin.
    params = pin_param(sample_box(PROPOSED_BOX, args.n, args.seed),
                       "cl", _CL.cl_mid_f)
    # Population = designs feasible at the NOMINAL rail. Corner headroom is
    # then re-checked per corner inside evaluate_at_corner, so losing headroom
    # at 0.95 VDD counts as a corner failure rather than being screened out
    # silently up front. `headroom_ok_1v8` never reads `cl`, so this population
    # is IDENTICAL to the one session 10d screened -- which is what makes the
    # comparison against 13.49/8.20/8.10 paired rather than inferred.
    feasible = [p for p in params if headroom_ok_1v8(p, NOMINAL_VDD) is None]
    n_feas = len(feasible)
    print(f"  {len(params)} sampled -> {n_feas} feasible at nominal 1.8 V "
          f"({len(params) - n_feas} rejected free)")
    print(f"  headroom_ok_1v8 does not read cl, so this is the SAME "
          f"population session 10d\n  screened at "
          f"{CL_LEGACY_PIN_F * 1e15:.0f} fF -- the comparison below is "
          f"paired, not between two samples.\n")

    results: dict = {"assumptions": {
        "cl_screened_f": list(SCREEN_LOADS),
        "cl_promotion_f": list(PROMOTION_LOADS),
        "cl_legacy_pin_f": CL_LEGACY_PIN_F,
        "cl_range_ratio": _CL.ratio, "cl_range_octaves": _CL.octaves,
        "vcm_tracks_vdd": VCM_TRACKS_VDD,
        "tail_is_ideal": TAIL_IS_IDEAL, "unscreened": UNSCREENED_SPECS,
        "n_sampled": args.n, "seed": args.seed},
        "legacy_150ff": {k: list(v) for k, v in LEGACY_150FF.items()}}

    # ---- benchmark ---------------------------------------------------------
    if not args.no_bench:
        c0 = SCREEN_CORNERS[0]
        bench = [(p, c0.process, c0.vdd_scale, c0.temp_c, SCREEN_LOADS[0])
                 for p in feasible[:args.bench_n]]
        print(f"--- parallel scaling, {len(bench)} tasks "
              f"({LoadCorner(c0, SCREEN_LOADS[0])}) ---")
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

    # ---- stage 0: the NOMINAL denominator, at both loads --------------------
    # S9_YIELD.md sec 4's 13.49% is TT/1.00/27 C at the 150 fF pin. Without the
    # same measurement at the new loads there is nothing to compare the corner
    # numbers against, and "the load costs X%" cannot be separated from "the
    # corners cost X%".
    nominal_grid = load_grid([NOMINAL_CORNER], SCREEN_LOADS)
    per_nom: list[list[CornerResult]] = []
    if not args.no_nominal:
        print(f"--- STAGE 0: {n_feas} designs at NOMINAL PVT x "
              f"{len(SCREEN_LOADS)} loads "
              f"({n_feas * len(nominal_grid)} runs) ---")
        for g in nominal_grid:
            print(f"    {g}")
        tasks0 = [(p, g.corner.process, g.corner.vdd_scale, g.corner.temp_c,
                   g.cl_f) for p in feasible for g in nominal_grid]
        t0 = time.perf_counter()
        flat0 = run_tasks(tasks0, workers=args.workers)
        t_nom = time.perf_counter() - t0
        print(f"  {len(tasks0)} runs in {t_nom:.1f} s "
              f"({t_nom / len(tasks0) * 1000:.1f} ms/run)")
        print(_health(flat0))
        ng0 = len(nominal_grid)
        per_nom = [flat0[i * ng0:(i + 1) * ng0] for i in range(n_feas)]
        for j, g in enumerate(nominal_grid):
            k = sum(1 for rs in per_nom if rs[j].all_specs_met)
            print(fmt_rate(k, n_feas, f"  met at {g}"))
        k_both = sum(1 for rs in per_nom if all(r.all_specs_met for r in rs))
        print(fmt_rate(k_both, n_feas, "NOMINAL PVT, BOTH loads"))
        print(f"      (session 10d at the {CL_LEGACY_PIN_F * 1e15:.0f} fF pin: "
              f"{LEGACY_150FF['TT / 1.00 / 27 C'][0]}/"
              f"{LEGACY_150FF['TT / 1.00 / 27 C'][1]} = 13.49%)")
        results["stage0"] = {
            "grid": [str(g) for g in nominal_grid], "seconds": t_nom,
            "n_runs": len(tasks0), "n_designs": n_feas,
            "per_point_met": {str(g): sum(1 for rs in per_nom
                                          if rs[j].all_specs_met)
                              for j, g in enumerate(nominal_grid)},
            "n_met_all": k_both,
            "first_fail_counts": {
                str(g): _count_first_fail([rs[j] for rs in per_nom])
                for j, g in enumerate(nominal_grid)},
        }
        print()
        for j, g in enumerate(nominal_grid):
            print(first_fail_table([rs[j] for rs in per_nom], str(g)))
            print()

    # ---- stage 1: screen at 3 corners x 2 loads ----------------------------
    screen_grid = load_grid(SCREEN_CORNERS, SCREEN_LOADS)
    print(f"--- STAGE 1: screening {n_feas} designs at {len(screen_grid)} "
          f"(corner, load) points ({n_feas * len(screen_grid)} runs) ---")
    for g in screen_grid:
        print(f"    {g}")
    tasks = [(p, g.corner.process, g.corner.vdd_scale, g.corner.temp_c, g.cl_f)
             for p in feasible for g in screen_grid]
    t0 = time.perf_counter()
    flat = run_tasks(tasks, workers=args.workers)
    t_screen = time.perf_counter() - t0
    print(f"  {len(tasks)} runs in {t_screen:.1f} s "
          f"({t_screen / len(tasks) * 1000:.1f} ms/run)")
    print(_health(flat) + "\n")

    ng = len(screen_grid)
    per_design = [flat[i * ng:(i + 1) * ng] for i in range(n_feas)]
    survivors_idx = [i for i, rs in enumerate(per_design)
                     if all(r.all_specs_met for r in rs)]

    print(fmt_rate(len(survivors_idx), n_feas,
                   "SCREEN YIELD (every corner AND every load)"))
    for j, g in enumerate(screen_grid):
        k = sum(1 for rs in per_design if rs[j].all_specs_met)
        print(fmt_rate(k, n_feas, f"  met at {g}"))
    print()

    # Pre-registered: is the joint set small because each load's set is small,
    # or because the two are DISJOINT? Free -- it re-reads the same runs.
    print("  --- corner-robust at each load edge separately "
          "(PREDICTIONS.md entry 1's follow-up) ---")
    edge = load_edge_table(per_design, screen_grid, SCREEN_LOADS)
    for label, k in edge.items():
        print(fmt_rate(k, n_feas, f"  {label}"))
    results["load_edges"] = edge
    print()

    for j, g in enumerate(screen_grid):
        print(first_fail_table([rs[j] for rs in per_design], str(g)))
        print()

    results["stage1"] = {
        "n_designs": n_feas, "n_survivors": len(survivors_idx),
        "seconds": t_screen, "n_runs": len(tasks),
        "grid": [str(g) for g in screen_grid],
        "per_point_met": {str(g): sum(1 for rs in per_design
                                      if rs[j].all_specs_met)
                          for j, g in enumerate(screen_grid)},
        "first_fail_counts": {
            str(g): _count_first_fail([rs[j] for rs in per_design])
            for j, g in enumerate(screen_grid)},
        "survivor_design_idx": list(survivors_idx),
    }

    # ---- stage 2: promote survivors to 45 corners x 3 loads ----------------
    corners45 = all_corners()
    promo_grid = load_grid(corners45, PROMOTION_LOADS)
    promo = [feasible[i] for i in survivors_idx]
    print(f"--- STAGE 2: promoting {len(promo)} survivors to "
          f"{len(corners45)} corners x {len(PROMOTION_LOADS)} loads "
          f"({len(promo) * len(promo_grid)} runs) ---")
    if not promo:
        print("  no survivors to promote\n")
        print(comparison_table(n_feas, len(survivors_idx), None,
                               results.get("stage0", {}).get("n_met_all")))
        args.out.write_text(json.dumps(results, indent=1), encoding="ascii")
        print(f"\nwrote {args.out}")
        return 0

    tasks45 = [(p, g.corner.process, g.corner.vdd_scale, g.corner.temp_c,
                g.cl_f) for p in promo for g in promo_grid]
    t0 = time.perf_counter()
    flat45 = run_tasks(tasks45, workers=args.workers)
    t45 = time.perf_counter() - t0
    print(f"  {len(tasks45)} runs in {t45:.1f} s "
          f"({t45 / len(tasks45) * 1000:.1f} ms/run)")
    print(_health(flat45) + "\n")

    n45 = len(promo_grid)
    per45 = [flat45[i * n45:(i + 1) * n45] for i in range(len(promo))]
    robust = [i for i, rs in enumerate(per45)
              if all(r.all_specs_met for r in rs)]

    print(fmt_rate(len(robust), n_feas, "FULL YIELD (45 corners x 3 loads)"))
    print(fmt_rate(len(robust), len(promo), "  of the screen's survivors"))
    print()

    # Which (corner, load) point is deadliest, and what it takes away.
    print("  --- per (corner, load) pass rate among the promoted designs ---")
    rows = []
    for j, g in enumerate(promo_grid):
        k = sum(1 for rs in per45 if rs[j].all_specs_met)
        ff = _count_first_fail([rs[j] for rs in per45])
        top = max(ff.items(), key=lambda kv: kv[1])[0] if ff else "-"
        rows.append((k / len(promo), str(g), k, top))
    rows.sort()
    print(f"      {'corner @ load':32} {'passing':>16}   first failure")
    for frac, tag, k, top in rows[:8]:
        print(f"      {tag:32} {k:5d}/{len(promo):<5d} "
              f"{frac * 100:6.1f}%   {top}")
    print("      ...")
    for frac, tag, k, top in rows[-3:]:
        print(f"      {tag:32} {k:5d}/{len(promo):<5d} "
              f"{frac * 100:6.1f}%   {top}")
    print()
    print(first_fail_table([r for rs in per45 for r in rs],
                           "ALL 45 corners x 3 loads pooled"))

    # Which point would have caught the screen's false positives. Printed even
    # when there are none, because "none" is itself the answer to "is the
    # screen enough?" and must not be inferred from silence. NOTE the screen
    # omits cl_mid, so a false positive can now be a LOAD blind spot rather
    # than a corner one -- and this table names which.
    non_robust = [i for i in range(len(promo)) if i not in set(robust)]
    aug = screen_augmentation(per45, promo_grid, non_robust)
    screen_tags = {str(g) for g in screen_grid}
    print(f"\n  --- the screen's {len(non_robust)} false positive(s): which "
          f"(corner, load) would have caught them ---")
    if not non_robust:
        print("      none -- the screen was exact on this sample")
    else:
        ranked = sorted(((len(v), k) for k, v in aug.items() if v),
                        reverse=True)
        for k, tag in ranked[:6]:
            mark = " (already screened)" if tag in screen_tags else ""
            print(f"      {tag:32} catches {k}/{len(non_robust)}{mark}")
        best = [t for k, t in ranked if k == len(non_robust)
                and t not in screen_tags]
        if best:
            print(f"      => adding ONE point ({best[0]}) would have made the "
                  f"screen exact on this sample")
        mid_tag = f"@ cl {_CL.cl_mid_f * 1e15:.1f}f"
        if any(t.endswith(mid_tag) for _k, t in ranked):
            print(f"      NOTE cl_mid appears above: a design can fail in the "
                  f"MIDDLE of the load\n           range while passing both "
                  f"edges, which two-edge screening cannot see.")

    results["stage2"] = {
        "n_promoted": len(promo), "n_robust": len(robust),
        "seconds": t45, "n_runs": len(tasks45),
        # Design indices are into `feasible`, so a later run can reproduce any
        # single design exactly: sample_box(PROPOSED_BOX, n, seed) -> pin cl ->
        # filter headroom -> index.
        "promoted_design_idx": list(survivors_idx),
        "robust_design_idx": [survivors_idx[i] for i in robust],
        "robust_params": [promo[i] for i in robust],
        "false_positive_design_idx": [survivors_idx[i] for i in non_robust],
        "false_positive_params": [promo[i] for i in non_robust],
        "screen_augmentation": {k: [survivors_idx[i] for i in v]
                                for k, v in aug.items() if v},
        "per_point_met": {str(g): sum(1 for rs in per45 if rs[j].all_specs_met)
                          for j, g in enumerate(promo_grid)},
        "first_fail_counts": {
            str(g): _count_first_fail([rs[j] for rs in per45])
            for j, g in enumerate(promo_grid)},
        "pooled_first_fail": _count_first_fail(
            [r for rs in per45 for r in rs]),
    }

    # Free consistency check: every screen point is inside the promotion grid.
    idx = {str(g): j for j, g in enumerate(promo_grid)}
    mismatches = 0
    for i, sidx in enumerate(survivors_idx):
        for j, g in enumerate(screen_grid):
            if (per45[i][idx[str(g)]].all_specs_met
                    != per_design[sidx][j].all_specs_met):
                mismatches += 1
    print(f"\n  screen/promotion consistency: {mismatches} mismatches across "
          f"{len(promo) * len(screen_grid)} repeated (design, corner, load) "
          f"triples")
    results["consistency_mismatches"] = mismatches
    if mismatches:
        print("  *** NON-DETERMINISTIC EVALUATION -- do not trust the numbers "
              "above ***")

    print()
    print(comparison_table(n_feas, len(survivors_idx), len(robust),
                           results.get("stage0", {}).get("n_met_all")))

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
