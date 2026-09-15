"""
experiments/exp_attribution.py -- where did the S3 rate go? (session 22b, D4)

THE QUESTION
-------------
`PLAN.md` D4 recommends **13.44 %** as the random-search baseline G3 must beat.
Session 22's task-0 pool measured **7.10 %** [6.05, 8.31] under the sampler,
evaluator and box the sweep will actually use. **A baseline the current
pipeline cannot reproduce is indefensible in a report**, so the gap has to be
attributed rather than corrected away.

Four candidate causes, and this file separates them:

  1. **DEFINITION** -- `prescreen.s3_true` tests two conditions (the `f_peak`
     window and the peaking band); `reward_v1.V0_SPECS` tests three, adding
     `S3_nyq_boost`. *Costs no simulation: re-score the stored population.*
  2. **LOAD** -- the population behind 13.44 % is `robust_geometry_data.csv`,
     and **every row of it has `cl` = 150 fF**, the legacy pin. Task 0 ran at
     `cl_mid` = 32.63 fF. *One arm.*
  3. **DRAWN PASSIVES** -- G66: `res_po`'s bottom plate adds up to +75 % to
     `cl` and moves `f_peak` by 0.1329 octaves. The session-11 population is
     ideal-passive. *One arm.*
  4. **REAL MIRROR** -- session 13: the mirror delivers 4-8 % less than
     `i_bias/2`. The session-11 population has ideal current sinks.
     **BLOCKED, and the block is stated rather than worked around** -- see
     `TAIL_AXIS_BLOCKED` below.

WHAT IS HELD FIXED
-------------------
Same sampler (`baselines._lhs`), same geometry mapping
(`rl.contract.sizing_from_u`), same evaluator (`rl.evaluator.evaluate`), same
S3 test (`exp_difficulty.margins_meet_s3`, which is `reward_v1.margins` on
`V0_SPECS` -- rule 9, one definition, imported not copied). Only the named
axis moves in each arm.

COST ACCOUNTING
----------------
Every ngspice invocation is charged through `SpiceBudget` (G65), including
retries and invalid designs. Runs SERIALLY (G70).

USAGE
    python -m nebula.experiments.exp_attribution --definition   # free, no SPICE
    python -m nebula.experiments.exp_attribution --run
    python -m nebula.experiments.exp_attribution --analyse FILE.jsonl
"""

from __future__ import annotations

import argparse
import csv
import math
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.experiments.baselines import _lhs, provenance
from nebula.experiments.cl_range import committed_cl_range
from nebula.experiments.exp_difficulty import margins_meet_s3
from nebula.rl import reward_v1 as R
from nebula.rl.contract import N_ACTIONS, f_peak_octaves, sizing_from_u
from nebula.rl.evaluator import SpiceBudget, Verdict, evaluate
from nebula.rl.runlog import RunLog
from nebula.rl.runlog import read as runlog_read

HERE = Path(__file__).resolve().parent
CALIBRATION_CSV: Path = HERE / "robust_geometry_data.csv"
LOG_PATH: Path = HERE / "attribution_run.jsonl"

_CL = committed_cl_range()

#: The load every row of `robust_geometry_data.csv` carries. **Not a choice --
#: read off the file** by `legacy_cl_f()`, which raises if the column is not
#: constant, so this cannot silently become wrong.
LEGACY_CL_F: float = 150e-15

#: Simulations per arm. Sized to separate 7.10 % from 13.44 %: at n = 1500 the
#: 95 % Wilson half-width is ~1.3 points at 7 % and ~1.7 at 13 %, so the two
#: candidate answers are ~4 half-widths apart.
ARM_SIMS: int = 1500

BASE_SEED: int = 220_260_818        # disjoint from baselines and exp_difficulty

#: **The mirror axis cannot be measured through the identical evaluator, and
#: that is a finding rather than an omission.** `rl.evaluator.validate`
#: REQUIRES the tail primitives -- with ideal current sinks `vds_tail` is not
#: in the ngspice output at all, so every ideal-tail design comes back
#: `invalid: vds_tail is missing`, not scorable. Measuring this axis therefore
#: needs the validator to treat "no tail device" as a configuration rather than
#: a failure, which changes validation semantics -- `BASELINES.md` §7f
#: territory and a human's call. Measured, not assumed: see
#: `test_the_tail_axis_is_blocked_and_says_why`.
TAIL_AXIS_BLOCKED: str = (
    "the real-mirror axis is NOT measured here. rl.evaluator.validate requires "
    "vds_tail/vdsat_tail, which ideal current sinks do not produce, so an "
    "ideal-tail arm returns 'invalid: vds_tail is missing from the ngspice "
    "output' for every design. Unblocking it means changing what validate() "
    "treats as a failure (BASELINES.md 7f) and is a human decision."
)


def legacy_cl_f(path: Path = CALIBRATION_CSV) -> float:
    """The `cl` the calibration population was measured at. Read, not assumed.

    Raises if the column is not constant, because "the population's load" would
    then not be a single number and every claim built on it would be a mean of
    something nobody chose.
    """
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        vals = {float(r["cl"]) for r in csv.DictReader(fh)}
    if len(vals) != 1:
        raise ValueError(
            f"{path.name} has {len(vals)} distinct cl values, not one: "
            f"{sorted(vals)[:5]}... -- 'the population's load' is not defined")
    return vals.pop()


# ─────────────────────────────────────────────────────────────────────────────
# Cause 1 — DEFINITION. Costs nothing: re-score the stored population.
# ─────────────────────────────────────────────────────────────────────────────


def definition_report(path: Path = CALIBRATION_CSV) -> dict:
    """Score the session-11 population under both S3 definitions.

    **No simulation.** Every row is a design that was already simulated; the
    only thing that changes between the two numbers is the test applied to it.
    """
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    col = lambda k: np.array([float(r[k]) for r in rows])
    fpk, pk, nb = col("f_pk_hz"), col("peaking_db"), col("nyquist_boost_db")
    gpk, gtop = col("g_pk_db"), col("g_top_db")
    vn, pw, vds, vdsat = (col("vn_in_vrms"), col("power_w"),
                          col("vds"), col("vdsat"))
    n = len(rows)

    # The same G44 guard `prescreen._has_interior_peak` applies, imported in
    # spirit rather than by reference because that helper takes its own dict.
    interior = (gpk - gtop > 0.25) & (fpk < 1.8e10) & (fpk > 1e7)

    lo, hi = SPEC_F_PEAK_HZ_RANGE
    pk_lo, pk_hi = SPEC_PEAKING_DB_RANGE
    two_row = (interior & (fpk >= lo) & (fpk <= hi)
               & (pk >= pk_lo) & (pk <= pk_hi))

    target = math.sqrt(lo * hi)
    v0 = np.zeros(n, dtype=bool)
    v1 = np.zeros(n, dtype=bool)
    for i in range(n):
        meas = {"peaking_db": pk[i], "f_peak_oct": f_peak_octaves(fpk[i]),
                "nyq_boost_db": nb[i], "inoise_vrms": vn[i], "power_w": pw[i],
                "pair_margin_v": vds[i] - vdsat[i],
                # No tail device exists in this population, so its margin is
                # not a measurement. Set clearly out of the way and EXCLUDED
                # from the headline, rather than defaulted to something that
                # looks measured.
                "tail_margin_v": float("inf")}
        m = R.margins(meas, target)
        v0[i] = bool(interior[i]) and margins_meet_s3(m)
        v1[i] = bool(interior[i]) and all(m[k] >= 0.0 for k in R.V1_SPECS)

    return {
        "n": n,
        "cl_f": legacy_cl_f(path),
        "s3_two_row_rate": float(two_row.mean()),
        "s3_v0_rate": float(v0.mean()),
        "s3_v1_rate_no_tail_row": float(v1.mean()),
        "killed_by_nyq_boost_alone": int((two_row & ~v0).sum()),
        "gained_by_v0_over_two_row": int((v0 & ~two_row).sum()),
        "definition_cost_points": float((two_row.mean() - v0.mean()) * 100.0),
        "note": ("the tail_saturation row is EXCLUDED (set to +inf): this "
                 "population has ideal current sinks and no tail margin was "
                 "ever measured on it"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Causes 2 and 3 — one simulated arm each.
# ─────────────────────────────────────────────────────────────────────────────


def run_arm(name: str, cl_f: float, real_passives: bool,
            n_sims: int = ARM_SIMS, seed_offset: int = 0,
            on_row=None) -> dict:
    """One arm: LHS over the box, one axis moved, the same S3 test applied."""
    rng = np.random.default_rng(BASE_SEED + seed_offset)
    budget = SpiceBudget()
    target = math.sqrt(SPEC_F_PEAK_HZ_RANGE[0] * SPEC_F_PEAK_HZ_RANGE[1])

    n_s3 = n_scorable = n_invalid = 0
    reasons: dict[str, int] = {}
    t0 = time.perf_counter()
    while budget.calls < n_sims:
        block = _lhs(max(2, n_sims - budget.calls), N_ACTIONS, rng)
        for u in block:
            if budget.calls >= n_sims:
                break
            sizing = sizing_from_u([float(x) for x in u], cl_f=cl_f)
            ev = evaluate(sizing, budget, real_passives=real_passives)
            if ev.verdict is Verdict.INVALID:
                n_invalid += 1
                key = (ev.reason or "?").split(":")[0][:40]
                reasons[key] = reasons.get(key, 0) + 1
                continue
            if ev.meas is None:
                continue
            n_scorable += 1
            m = R.margins(ev.meas, target)
            if margins_meet_s3(m):
                n_s3 += 1
    wall = time.perf_counter() - t0

    n = budget.calls
    return {
        "kind": "arm", "arm": name,
        "cl_f": cl_f, "cl_fF": cl_f * 1e15, "real_passives": real_passives,
        "real_tail": True,
        "seed": BASE_SEED + seed_offset,
        "n_sims": n, "n_scorable": n_scorable, "n_invalid": n_invalid,
        "n_s3": n_s3,
        "s3_rate": (n_s3 / n if n else None),
        "s3_rate_among_scorable": (n_s3 / n_scorable if n_scorable else None),
        "invalid_rate": (n_invalid / n if n else None),
        "invalid_reasons": reasons,
        "wall_s": wall, "sec_per_sim": (wall / n if n else None),
    }


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Two-sided Wilson interval. Same estimator `s3_yield.wilson_ci` uses."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


#: The arms. `cl_mid`/drawn is task 0's configuration and is re-run here at a
#: fresh seed rather than quoted, so all three rows come from one protocol.
ARMS: tuple[tuple[str, float, bool], ...] = (
    ("cl_mid_drawn", _CL.cl_mid_f, True),
    ("cl_legacy_drawn", LEGACY_CL_F, True),
    ("cl_mid_ideal_passives", _CL.cl_mid_f, False),
)


def run(n_sims: int = ARM_SIMS, log_path: Path = LOG_PATH) -> dict:
    rows: list[dict] = []
    header = {"experiment": "S3-rate attribution (session 22b, D4)",
              "arm_sims": n_sims, "base_seed": BASE_SEED,
              "legacy_cl_f": legacy_cl_f(),
              "tail_axis_blocked": TAIL_AXIS_BLOCKED,
              **provenance()}
    with RunLog(Path(log_path), header=header) as log:
        d = definition_report()
        d["kind"] = "definition"
        rows.append(d)
        log.event("definition", **d)
        print(f"  definition (no SPICE): two-row {d['s3_two_row_rate']*100:.2f} % "
              f"vs V0 {d['s3_v0_rate']*100:.2f} % -> the definition costs "
              f"{d['definition_cost_points']:+.2f} points", flush=True)
        for i, (name, cl_f, rp) in enumerate(ARMS):
            r = run_arm(name, cl_f, rp, n_sims=n_sims, seed_offset=i * 1000)
            rows.append(r)
            log.event(r["kind"], **r)
            lo, hi = wilson(r["n_s3"], r["n_sims"])
            print(f"  [{name:24s}] cl={r['cl_fF']:6.2f} fF passives="
                  f"{'drawn' if rp else 'ideal'}  S3 {r['s3_rate']*100:5.2f} % "
                  f"[{lo*100:.2f}, {hi*100:.2f}]  invalid {r['invalid_rate']*100:.1f} % "
                  f"{r['wall_s']:.0f} s", flush=True)
    return analyse(rows)


def analyse(rows: Sequence[dict]) -> dict:
    d = next((r for r in rows if r.get("kind") == "definition"), None)
    arms = {r["arm"]: r for r in rows if r.get("kind") == "arm"}
    out: dict = {"definition": d, "arms": arms,
                 "tail_axis_blocked": TAIL_AXIS_BLOCKED}
    for r in arms.values():
        r["wilson95"] = wilson(r["n_s3"], r["n_sims"])
    base = arms.get("cl_mid_drawn")
    if base and d:
        out["decomposition"] = {
            "published_two_row_at_legacy_cl": d["s3_two_row_rate"],
            "definition_points": d["definition_cost_points"],
            "load_points": (
                (arms["cl_legacy_drawn"]["s3_rate"] - base["s3_rate"]) * 100
                if "cl_legacy_drawn" in arms else None),
            "drawn_passive_points": (
                (base["s3_rate"] - arms["cl_mid_ideal_passives"]["s3_rate"]) * 100
                if "cl_mid_ideal_passives" in arms else None),
            "measured_at_sweep_conditions": base["s3_rate"],
        }
    return out


def load(path: Path) -> list[dict]:
    return [r for r in runlog_read(Path(path))
            if r.get("kind") in ("arm", "definition") and "event" in r]


def print_report(out: dict) -> None:
    d, arms = out["definition"], out["arms"]
    print()
    print("=" * 78)
    print("WHERE DID THE S3 RATE GO? -- 13.44 % vs 7.10 % (D4)")
    print("=" * 78)
    if d:
        print(f"\n1. DEFINITION (no simulation, n={d['n']}, "
              f"cl={d['cl_f']*1e15:.1f} fF)")
        print(f"   prescreen s3_true, 2 rows      {d['s3_two_row_rate']*100:6.2f} %"
              "   <- the published 13.44 %")
        print(f"   reward_v1 V0_SPECS, 3 rows     {d['s3_v0_rate']*100:6.2f} %"
              "   <- task 0's test")
        print(f"   reward_v1 V1_SPECS, 7 rows     {d['s3_v1_rate_no_tail_row']*100:6.2f} %"
              "   (tail row excluded)")
        print(f"   => the definition costs {d['definition_cost_points']:+.2f} points")
        print(f"   designs killed by the nyq_boost row alone: "
              f"{d['killed_by_nyq_boost_alone']}")
    print(f"\n2-3. THE SIMULATED ARMS ({', '.join(a['arm'] for a in arms.values())})")
    print(f"   {'arm':26s} {'cl (fF)':>8s} {'passives':>9s} {'S3 rate':>9s} {'95% Wilson':>18s}")
    for r in arms.values():
        lo, hi = r["wilson95"]
        print(f"   {r['arm']:26s} {r['cl_fF']:8.2f} "
              f"{'drawn' if r['real_passives'] else 'ideal':>9s} "
              f"{r['s3_rate']*100:8.2f} % [{lo*100:5.2f}, {hi*100:5.2f}] %")
    dec = out.get("decomposition")
    if dec:
        print("\n   DECOMPOSITION, in percentage points of S3 rate:")
        print(f"     definition                {dec['definition_points']:+6.2f}")
        if dec["load_points"] is not None:
            print(f"     cl 32.63 -> 150 fF        {dec['load_points']:+6.2f}")
        if dec["drawn_passive_points"] is not None:
            print(f"     drawn passives (G66)      {dec['drawn_passive_points']:+6.2f}")
        print(f"     measured at sweep conditions {dec['measured_at_sweep_conditions']*100:.2f} %")
    print(f"\n4. MIRROR AXIS: NOT MEASURED.\n   {out['tail_axis_blocked']}")
    print("=" * 78)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S3-rate attribution (D4)")
    ap.add_argument("--definition", action="store_true",
                    help="cause 1 only. No simulation.")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--n", type=int, default=ARM_SIMS)
    ap.add_argument("--log", type=Path, default=LOG_PATH)
    ap.add_argument("--analyse", type=Path, default=None)
    a = ap.parse_args(argv)

    if a.definition:
        d = definition_report()
        print_report({"definition": d, "arms": {},
                      "tail_axis_blocked": TAIL_AXIS_BLOCKED})
        return 0
    if a.analyse is not None:
        print_report(analyse(load(a.analyse)))
        return 0
    if a.run:
        print_report(run(n_sims=a.n, log_path=a.log))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
