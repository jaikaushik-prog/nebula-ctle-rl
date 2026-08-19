"""
experiments/exp_g4_verify.py — **G4: a corner-robust design, generated and
verified.**

THE GATE, VERBATIM
-------------------
`CLAUDEwa.md` §7: *"**G4** | Sep 12 | Corner-robust design generated and
verified; results table drafted."* And S9: *"TT, SS, FF, SF, FS x VDD +/-5% x
0-125 C. **All specs must hold at every corner.** A design that meets everything
at TT/27 C and fails at SS/125 C is a failed design and must score as such."*

**Generated** is already done and was not done by hand. The benchmark's P3 rung
scores every design on the worst of 3 screen corners x 2 loads, and its
`uniform` arm found **2 corner-and-load-robust designs in 20 seeds**
(`BASELINES.md` §12): rewards 8.0342 and 8.0021, both just above the
feasibility bonus of exactly 8.0. Their sizing vectors are read out of the run
log here rather than transcribed, so nothing in this file is a number a human
retyped.

**Verified** is what this file adds. The screen is 3 corners; S9 asks for 45.
Session 10d measured that the 3 screen corners capture **98.7 %** of what all
45 catch (G47) -- *a 1.3 % gap that has never been checked on a design that
actually survived the screen.*

    3 screen corners x 2 loads   =   6 evaluations  <- what the search saw
    45 corners x 3 loads         = 135 evaluations  <- what S9 actually asks

THE PREDICTION, WRITTEN BEFORE THE RUN
----------------------------------------
Committed with this file and before it was executed, per the pre-registration
rule; the run is ~1 minute, below the 10-minute threshold, so this stands in
place of a `PREDICTIONS.md` entry rather than beside one.

* **Both designs pass all 135 points.** G47's 98.7 % is a population statistic
  over the whole box, and these two survived a screen chosen precisely because
  it is the hard corner set. Confidence: moderate. Band: **at least 1 of 2**
  passes; 0 of 2 would mean the screen is not a screen.
* **The binding corner is one of the three screened ones**, and the binding
  spec is `S3_f_peak` at both -- which is what the P3 log already says at the
  screen corners, and the frequency margin is the row with no slack anywhere.
* **The two designs bind at OPPOSITE ends**: 8.0342 worst at ss/0.95/125C with
  the HIGH load, 8.0021 worst at ff/1.05/0C with the LOW load. If that survives
  to 45 corners it is the physical story for the report -- the peak frequency
  is pushed down by slow-hot-heavy and up by fast-cold-light, and a robust
  design is one placed where neither excursion leaves S3's window.

**THE CONTROL IS WHAT MAKES THIS A GATE.** A verification that only ever runs
on designs expected to pass cannot fail, and G73 is explicit that a gate whose
condition is unreachable is indistinguishable from a deleted one. So the same
135 points are run on designs that were feasible **at TT only** -- P1 winners
that the P3 rung never certified. **Those must fail**, and if they do not, the
corner axis is not measuring anything and every corner number in this project
needs re-reading.

NOTHING HERE IS TUNED, SEARCHED OR SELECTED. It re-simulates designs the
benchmark already found, at points the spec table already names.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.experiments.s9_yield import PROMOTION_LOADS, SCREEN_CORNERS, all_corners
from nebula.rl import reward_v1 as R
from nebula.rl.contract import N_ACTIONS, sizing_from_u
from nebula.rl.evaluator import SpiceBudget, Verdict, evaluate, scoring_meas

HERE = Path(__file__).resolve().parent

#: Where the generated designs come from. The P3 arm of the published sweep.
SOURCE_LOG = HERE / "baselines_run_interp_grid.jsonl.gz"
OUT_PATH = HERE / "g4_verify_results.json"

#: The target every published run used, so the verification scores what the
#: search was scored on. Changing it would verify a different design problem.
from nebula.rl.spec_dist import LEGACY_TARGET  # noqa: E402


@dataclass(frozen=True)
class Candidate:
    """A design to verify, and the claim being made about it."""

    design_id: str
    u: tuple[float, ...]
    role: str                 # "robust" (the claim) or "nominal_only" (control)
    source: str               # method/replicate it came from
    claimed_reward: float
    claimed_worst_point: Optional[str]


def candidates(log: Path = SOURCE_LOG, n_control: int = 3) -> list[Candidate]:
    """Read the designs out of the run log. **Nothing is transcribed.**

    `robust` rows are P3-feasible: the benchmark scored them on the worst of
    3 screen corners x 2 loads and they cleared every spec there.

    `nominal_only` rows are the CONTROL: feasible on P1 (tt, cl_mid) and never
    certified at any corner. They are taken from the TOP of the P1 ranking, so
    the control is the strongest possible version of "optimised at nominal" --
    a weak nominal design failing at corners would prove nothing.
    """
    robust: dict[str, Candidate] = {}
    p1: list[tuple[float, dict]] = []
    with gzip.open(log, "rt", encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row.get("event") != "trial" or not row.get("feasible"):
                continue
            if row.get("problem") == "P3":
                did = row["design_id"]
                if did not in robust:
                    robust[did] = Candidate(
                        design_id=did, u=tuple(float(x) for x in row["u"]),
                        role="robust",
                        source=f"{row['method']}/{row['replicate']}",
                        claimed_reward=float(row["reward"]),
                        claimed_worst_point=row.get("worst_point"))
            elif row.get("problem") == "P1" and not row.get("prescreen"):
                p1.append((float(row["reward"]), row))

    p1.sort(key=lambda t: -t[0])
    seen = set(robust)
    control: list[Candidate] = []
    for reward, row in p1:
        did = row["design_id"]
        if did in seen:
            continue
        seen.add(did)
        control.append(Candidate(
            design_id=did, u=tuple(float(x) for x in row["u"]),
            role="nominal_only",
            source=f"{row['method']}/{row['replicate']}",
            claimed_reward=reward, claimed_worst_point="tt/1.00/27C/cl_mid"))
        if len(control) >= n_control:
            break
    return list(robust.values()) + control


@dataclass
class PointResult:
    corner: str
    vdd_scale: float
    temp_c: float
    cl_f: float
    reward: float
    feasible: bool
    valid: bool
    verdict: str
    worst_spec: Optional[str]


def verify(cand: Candidate, budget: SpiceBudget,
           corners: Optional[Sequence] = None,
           loads: Sequence[float] = PROMOTION_LOADS,
           ac_peak_interp: bool = True) -> dict:
    """Every (corner, load) point, no short-circuit.

    **The short-circuit is deliberately NOT used here**, unlike in the search
    loop. A search stops early because nothing below the floor exists and the
    remaining simulations buy nothing; a VERIFICATION has to be able to say
    *which* points failed and by how much, and a run that stops at the first
    failure cannot. This is the one place the extra simulations are worth it.
    """
    corners = list(corners if corners is not None else all_corners())
    rows: list[PointResult] = []
    for c in corners:
        for cl in loads:
            sizing = sizing_from_u(np.asarray(cand.u), cl_f=float(cl))
            ev = evaluate(sizing, budget, corner=c.process, temp_c=c.temp_c,
                          vdd_scale=c.vdd_scale, ac_peak_interp=ac_peak_interp)
            rb = R.reward(scoring_meas(ev, ac_peak_interp),
                          LEGACY_TARGET.f_peak_hz,
                          target_peaking_db=LEGACY_TARGET.peaking_db,
                          headroom=(ev.headroom if ev.verdict
                                    is Verdict.HEADROOM_ONLY else None))
            rows.append(PointResult(
                corner=c.process, vdd_scale=c.vdd_scale, temp_c=c.temp_c,
                cl_f=float(cl), reward=float(rb.reward),
                feasible=bool(rb.feasible), valid=bool(ev.valid),
                verdict=ev.verdict.value, worst_spec=rb.worst_spec))

    worst = min(rows, key=lambda r: r.reward)
    failed = [r for r in rows if not r.feasible]
    screen_labels = {(c.process, c.vdd_scale, c.temp_c) for c in SCREEN_CORNERS}
    failed_outside_screen = [
        r for r in failed
        if (r.corner, r.vdd_scale, r.temp_c) not in screen_labels]
    return {
        "design_id": cand.design_id, "role": cand.role, "source": cand.source,
        "claimed_reward": cand.claimed_reward,
        "claimed_worst_point": cand.claimed_worst_point,
        "u": list(cand.u),
        "n_points": len(rows), "n_corners": len(corners), "n_loads": len(loads),
        "n_failed": len(failed),
        "n_failed_outside_the_screen": len(failed_outside_screen),
        "all_points_pass": not failed,
        "worst_reward": worst.reward,
        "worst_point": f"{worst.corner}/{worst.vdd_scale:.2f}/"
                       f"{worst.temp_c:.0f}C/cl={worst.cl_f * 1e15:.1f}fF",
        "worst_spec": worst.worst_spec,
        "worst_is_a_screen_corner": (worst.corner, worst.vdd_scale,
                                     worst.temp_c) in screen_labels,
        "points": [asdict(r) for r in rows],
    }


def run(n_control: int = 3, out_path: Path = OUT_PATH) -> dict:
    cands = candidates(n_control=n_control)
    budget = SpiceBudget()
    t0 = time.perf_counter()
    results = []
    for c in cands:
        r = verify(c, budget)
        results.append(r)
        print(f"  {r['role']:<13} {r['design_id'][:12]:<14} "
              f"{'PASS' if r['all_points_pass'] else 'FAIL':<5} "
              f"{r['n_failed']:>3}/{r['n_points']} points failed  "
              f"worst {r['worst_reward']:8.4f} at {r['worst_point']}"
              f"  ({r['worst_spec']})", flush=True)
    out = {
        "task": "G4 -- corner-robust design generated and verified",
        "target": {"peaking_db": LEGACY_TARGET.peaking_db,
                   "f_peak_hz": LEGACY_TARGET.f_peak_hz},
        "grid": {"n_corners": 45, "loads_f": list(PROMOTION_LOADS),
                 "screen_corners": [str(c) for c in SCREEN_CORNERS]},
        "wall_s": time.perf_counter() - t0,
        "simulations": budget.calls,
        "results": results,
    }
    out_path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"\n  {budget.calls} simulations, {out['wall_s'] / 60:.1f} min")
    print(f"wrote {out_path}")
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--list", action="store_true",
                    help="which designs would be verified; no SPICE")
    ap.add_argument("--controls", type=int, default=3)
    args = ap.parse_args(argv)
    if not (args.run or args.list):
        ap.error("choose --list or --run")
    if args.list:
        for c in candidates(n_control=args.controls):
            print(f"  {c.role:<13} {c.design_id[:14]:<16} from {c.source:<12} "
                  f"claimed {c.claimed_reward:8.4f} "
                  f"worst at {c.claimed_worst_point}")
    if args.run:
        run(n_control=args.controls)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
