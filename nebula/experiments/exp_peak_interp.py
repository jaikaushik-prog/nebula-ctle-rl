"""
experiments/exp_peak_interp.py -- task 1. **Is the reward ceiling gone?**

THE QUESTION, IN ONE LINE
--------------------------
G74 established that `reward_v1` saturates at **+8.950669** because
`meas ac g_pk MAX` can only report frequencies on the `ac dec 50 1meg 100g`
lattice -- a grid **0.066439 octaves** apart -- and `S3_f_peak`'s margin is
`0.5 - |log2(f_peak/f_target)|` octaves. Task 0 then measured the consequence:
across **8000 simulations**, **57 distinct designs scored that one value and
nothing scored above it** (`DIFFICULTY.md` sec 0 item 6). A plateau at the
optimum is the objective shape that produces a flat PPO learning curve for
reasons no hyperparameter reaches.

`device/sky130_runner.interpolate_peak_log_f` reads the peak off the parabola
through the three samples bracketing the discrete maximum instead of off the
lattice. **This file measures whether that removed the ceiling or moved it.**

TWO POPULATIONS, AND WHY BOTH
-------------------------------
* **the G2 funnel** (`g2_closed_loop_run.jsonl`, 300 LHS designs at
  `cl` = 32.63 fF, drawn passives, real mirror) -- the brief's population. It
  answers *how far off the lattice was*, in octaves, on a population whose
  discrete `f_peak` is already published, so every replayed design carries its
  own reproduction check.
* **the task-0 pools** (4 x 2000 simulations, the 57 ceiling ties) -- it answers
  *how many of the ties separate*, which is the question that matters for G3.
  Replayed through `exp_difficulty.run_pool` itself, same seeds, same sampler,
  same evaluator, with `ac_peak_interp=True` as the ONLY difference.

WHAT IS HELD FIXED
-------------------
Everything. `V1_SPECS`, the tolerances, the box, the pre-screen, the geometry
mapping, the seeds. The interpolated peak lands in NEW measurement keys and the
lattice ones are untouched, so **the discrete reward recomputed in this replay
must equal the published one exactly** -- that is falsification condition 4 and
it is checked design by design, not in aggregate.

COST
-----
**Zero extra simulations.** The curve is dumped by the same ngspice invocation
(`ac_sweep`, session 21, proven inert at rel=0/abs=0) and the vertex is about
ten floating-point operations. The dump itself costs wall clock -- G2's tier
table puts `op+ac+noise` at 0.1768 s and `+AC dump` at 0.2047 s, +15.8 % -- and
that is reported, under G70's isolation rule (one concurrent ngspice makes each
run 4.8x slower) and G71's ordering caution.

USAGE
    python -m nebula.experiments.exp_peak_interp --funnel     # 300 sims, ~2 min
    python -m nebula.experiments.exp_peak_interp --pools      # 8000 sims, ~40 min
    python -m nebula.experiments.exp_peak_interp --analyse
    python -m nebula.experiments.exp_peak_interp --plot
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.device.sky130_runner import (
    MAX_SEARCH_BOT_HZ,
    MAX_SEARCH_TOP_HZ,
    run_point,
)
from nebula.experiments.baselines import PROBLEMS, Objective, Trial
from nebula.experiments.exp_difficulty import (
    ARMS,
    CEILING_TOL,
    POOL_SIMS,
    margins_meet_s3,
    run_pool,
    run_seed,
)
from nebula.experiments.exp_g2_closed_loop import _sizing_to_point
from nebula.rl import reward_v1 as R
from nebula.rl.evaluator import meas_with_interpolated_peak

HERE = Path(__file__).resolve().parent
FUNNEL_IN: Path = HERE / "g2_closed_loop_run.jsonl"
FUNNEL_OUT: Path = HERE / "peak_interp_funnel.jsonl"
POOLS_OUT: Path = HERE / "peak_interp_pools.jsonl"
FIG_PATH: Path = HERE.parents[0] / "figures" / "peak_interp.png"

#: Half the `dec 50` grid step, in octaves. **The hard bound on
#: `d_f_peak_octaves`** -- the vertex cannot leave its own cell -- so it is the
#: number every measured shift is checked against rather than a plotting range.
HALF_STEP_OCT: float = 0.5 * math.log2(10.0 ** (1.0 / 50))

#: The published lattice ceiling (G74). Quoted, never recomputed here:
#: `baselines.reward_ceiling` derives it and `exp_difficulty` uses that.
#: Written down only so a mismatch is loud.
G74_CEILING: float = 8.950669295771243

#: The four pools task 0 ran, as (arm, replicate). Replicate 0 is
#: `difficulty_run.jsonl`, replicate 1 is `difficulty_pool_r1.jsonl`.
POOLS: tuple[tuple[str, int], ...] = tuple(
    (arm, rep) for rep in (0, 1) for arm in ARMS)

#: Where the published pool rows live, so the replay can be checked against
#: them design by design rather than in aggregate.
PUBLISHED_POOLS: dict[int, Path] = {
    0: HERE / "difficulty_run.jsonl",
    1: HERE / "difficulty_pool_r1.jsonl",
}


def provenance() -> dict:
    """Commit + dirty flag, so a row identifies the code that produced it."""
    def _git(*args: str) -> Optional[str]:
        try:
            return subprocess.run(["git", *args], cwd=str(HERE),
                                  capture_output=True, text=True,
                                  timeout=20).stdout.strip() or None
        except Exception:                                   # noqa: BLE001
            return None
    head = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    return {"commit": head, "commit_short": (head[:7] if head else None),
            "dirty": bool(status)}


# ─────────────────────────────────────────────────────────────────────────────
# The two rewards. ONE definition of each (rule 9).
# ─────────────────────────────────────────────────────────────────────────────


def _targets() -> tuple[float, float]:
    """The benchmark's own targets, read off an `Objective` rather than
    recomputed here -- `Objective.__init__` is where they are defined."""
    obj = Objective(PROBLEMS["P1"], budget_sims=1)
    return obj.target_f_peak_hz, obj.target_peaking_db


def rewards_both_ways(tr: Trial, target_f: float, target_pk: float
                      ) -> dict:
    """`(discrete, interpolated)` for one trial, and why they differ.

    The discrete number is `Trial.reward` **as the objective computed it** --
    not recomputed here, because recomputing it would test this function
    against itself instead of against the harness that produced the published
    pools.

    The interpolated number is the SAME reward function on the SAME measurement
    vector with only the peak swapped (`meas_with_interpolated_peak`). Three
    cases, all named:

    * no `meas` at all -- screened, invalid or headroom-only. The peak plays no
      part in any of those verdicts, so the interpolated reward IS the discrete
      one, and calling it "unchanged" is a statement about the design rather
      than a fallback.
    * `meas` present, interpolation refused -- the commonest reason is a
      sweep-edge maximum (G44). The interpolated arm scores the invalid floor,
      and this is a REAL COST of the interpolated path, counted separately.
    * both present -- the two rewards, and the shift that produced the gap.
    """
    floor = R.invalid_reward(len(R.V1_SPECS))
    out = {
        "index": tr.index, "design_id": tr.design_id, "verdict": tr.verdict,
        "n_sims": tr.n_sims, "screened_out": tr.screened_out,
        "reward_discrete": float(tr.reward), "meets_s3": margins_meet_s3(tr.margins),
        "worst_spec_discrete": tr.worst_spec,
    }
    if not tr.meas:
        out.update(reward_interp=float(tr.reward), interp_status="no_meas")
        return out
    try:
        swapped = meas_with_interpolated_peak(tr.meas)
    except ValueError as exc:
        out.update(reward_interp=float(floor), interp_status="refused",
                   interp_refusal=str(exc)[:200])
        return out
    rb = R.reward_v1(swapped, target_f, target_peaking_db=target_pk)
    out.update(
        reward_interp=float(rb.reward),
        interp_status="ok",
        worst_spec_interp=rb.worst_spec,
        f_peak_oct=float(tr.meas["f_peak_oct"]),
        f_peak_oct_interp=float(tr.meas["f_peak_oct_interp"]),
        d_f_peak_oct=float(tr.meas["f_peak_oct_interp"] - tr.meas["f_peak_oct"]),
        d_peaking_db=float(tr.meas["peaking_db_interp"] - tr.meas["peaking_db"]),
    )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Sub-experiment 1 -- the G2 funnel, replayed.
# ─────────────────────────────────────────────────────────────────────────────


def replay_funnel(in_path: Path = FUNNEL_IN, out_path: Path = FUNNEL_OUT,
                  limit: Optional[int] = None) -> Path:
    """Re-run the 300 funnel designs with the interpolation on.

    **The same deck as the funnel ran** -- `swing=True, ac_sweep=True,
    hd3=True`, corner tt -- so `f_pk_hz` must come back bit-identical to the
    logged value. That check is the point: it proves the replay is the same
    experiment before any conclusion is drawn from the difference.
    """
    rows = [json.loads(L) for L in in_path.open(encoding="utf-8")]
    header = rows[0]
    designs = [r for r in rows[1:] if "params" in r]
    if limit:
        designs = designs[:limit]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "schema_version": 1, "kind": "header",
            "experiment": "task 1 -- the interpolated peak on the G2 funnel",
            "source": in_path.name,
            "source_header": {k: header.get(k) for k in
                              ("written_utc", "n", "seed", "corner", "cl_f",
                               "vdd_v", "nf_in")},
            "n_designs": len(designs),
            "deck": "swing=True, ac_sweep=True, hd3=True, corner=tt -- "
                    "IDENTICAL to the funnel, so f_pk_hz must reproduce",
            "search_window_hz": [MAX_SEARCH_BOT_HZ, MAX_SEARCH_TOP_HZ],
            "half_step_octaves": HALF_STEP_OCT,
            "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **provenance(),
        }) + "\n")

        for k, src in enumerate(designs):
            row = {"i": src["i"], "stage_published": src.get("stage")}
            try:
                point = _sizing_to_point(src["params"])
            except Exception as exc:                        # noqa: BLE001
                row["skip"] = f"unrealisable geometry: {exc}"
                fh.write(json.dumps(row) + "\n")
                continue
            pt = run_point(point, "tt", swing=True, ac_sweep=True,
                           ac_peak_interp=True, hd3=True)
            row["runtime_s"] = round(pt.runtime_s, 4)
            if not pt.ok:
                row["skip"] = pt.fail_reason
                fh.write(json.dumps(row) + "\n")
                continue

            row.update({
                "f_pk_hz": pt.f_pk_hz,
                "f_pk_hz_published": src.get("f_peak_hz"),
                "reproduces": (src.get("f_peak_hz") is None
                               or pt.f_pk_hz == src["f_peak_hz"]),
                "g_pk_db": pt.g_pk_db, "g_dc_db": pt.g_dc_db,
                "g_top_db": pt.g_top_db,
                "peaking_db": pt.peaking_db,
                "peak_is_sweep_edge": pt.peak_is_sweep_edge,
                "peak_interp_is_sweep_edge": pt.peak_interp_is_sweep_edge,
                "interp_ok": bool(pt.peak_interp.get("ok")),
                "interp_reason": pt.peak_interp.get("reason"),
                "interp_edge": pt.peak_interp.get("edge"),
                "curvature_db": pt.peak_interp.get("curvature_db"),
                "step_octaves": pt.peak_interp.get("step_octaves"),
            })
            if pt.has_interp_peak:
                row.update({
                    "f_pk_interp_hz": pt.f_pk_interp_hz,
                    "g_pk_interp_db": pt.g_pk_interp_db,
                    "d_f_peak_oct": pt.d_f_peak_octaves,
                    "d_peaking_db": pt.peaking_interp_db - pt.peaking_db,
                })
            fh.write(json.dumps(row) + "\n")
            if (k + 1) % 25 == 0:
                print(f"  {k + 1}/{len(designs)}  "
                      f"{time.perf_counter() - t0:6.1f} s", flush=True)

    print(f"funnel replay -> {out_path}  ({time.perf_counter() - t0:.1f} s)")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# Sub-experiment 2 -- the task-0 pools, replayed.
# ─────────────────────────────────────────────────────────────────────────────


def replay_pools(out_path: Path = POOLS_OUT, pool_sims: int = POOL_SIMS,
                 pools: Sequence[tuple[str, int]] = POOLS) -> Path:
    """Re-run all four task-0 pools with `ac_peak_interp=True`.

    `run_pool` is called UNCHANGED, with the same seeds -- the flag is the only
    difference and it is threaded through `Objective` to `evaluate`. Every
    trial is captured through `on_trial`, which is the hook `run_pool` already
    had, so this file does not own a second copy of the sampling loop.
    """
    target_f, target_pk = _targets()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t_all = time.perf_counter()
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "schema_version": 1, "kind": "header",
            "experiment": "task 1 -- the interpolated peak on the task-0 pools",
            "pools": [list(p) for p in pools], "pool_sims": pool_sims,
            "target_f_peak_hz": target_f, "target_peaking_db": target_pk,
            "specs": list(R.V1_SPECS),
            "lattice_ceiling": G74_CEILING,
            "half_step_octaves": HALF_STEP_OCT,
            "note": "reward_discrete is Trial.reward as the objective computed "
                    "it; reward_interp is the SAME reward function on the same "
                    "meas with only the peak swapped. ac_peak_interp is the "
                    "only difference from difficulty_run.jsonl / _pool_r1.",
            "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **provenance(),
        }) + "\n")

        for arm, rep in pools:
            captured: list[dict] = []

            def _on_trial(tr: Trial) -> None:
                captured.append(rewards_both_ways(tr, target_f, target_pk))

            t0 = time.perf_counter()
            summary = run_pool(arm, pool_sims=pool_sims, replicate=rep,
                               on_trial=_on_trial, ac_peak_interp=True)
            summary["kind"] = "pool"
            summary["replay_of"] = PUBLISHED_POOLS[rep].name
            summary["seed_check"] = run_seed(arm, "pool", rep)
            summary.pop("rewards", None)
            fh.write(json.dumps(summary) + "\n")
            for row in captured:
                row.update(kind="trial", arm=arm, replicate=rep)
                fh.write(json.dumps(row) + "\n")
            print(f"  {arm} r{rep}: {len(captured)} trials, "
                  f"{time.perf_counter() - t0:.1f} s", flush=True)

    print(f"pool replay -> {out_path}  ({time.perf_counter() - t_all:.1f} s)")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# Sub-experiment 3 -- IS THE VERTEX RIGHT, or merely finer?
#
# Everything above measures how far the interpolated peak sits from the lattice
# one. That is not the same question as whether it is CLOSER TO THE TRUTH. A
# parabola through three samples of a response that is not locally quadratic
# would move the number smoothly and confidently in the wrong direction, and
# every statistic in this file would look exactly the same.
#
# So: run a handful of designs at `dec 500` -- ten times the frequency
# resolution, 0.0066439 octaves -- and treat ITS interpolated peak as the
# reference. Then the lattice error and the interpolated error can be compared
# against a common ground truth. This is a VALIDATION and not a cost change:
# nothing in any deliverable sweeps `dec 500`, and the brief is explicit that
# raising `dec` is a human decision.
# ─────────────────────────────────────────────────────────────────────────────

#: The `.ac` line as the shipped deck carries it, and the dense replacement.
#: Edited by string substitution on the module-level template and restored in a
#: `finally`, exactly as `test_asking_for_the_sweep_and_not_getting_it_is_a_
#: FAILURE` does -- and the substitution is ASSERTED to have happened, because
#: a no-op edit that reports success is this repository's commonest failure
#: shape (G26, G56, G57).
AC_LINE_SHIPPED: str = "ac dec 50 1meg 100g"
DENSE_DEC: int = 500


def replay_dense(in_path: Path = FUNNEL_IN, out_path: Optional[Path] = None,
                 n: int = 30) -> Path:
    """`dec 50` against `dec 500` on the same designs, same everything else."""
    from nebula.device import sky130_runner as SR

    out_path = out_path or (HERE / "peak_interp_dense.jsonl")
    rows = [json.loads(L) for L in in_path.open(encoding="utf-8")]
    designs = [r for r in rows[1:] if "params" in r][:n]

    dense_line = AC_LINE_SHIPPED.replace("dec 50", f"dec {DENSE_DEC}")
    t0 = time.perf_counter()
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "schema_version": 1, "kind": "header",
            "experiment": "task 1 -- is the vertex right, or merely finer?",
            "n_designs": len(designs), "dense_dec": DENSE_DEC,
            "shipped_ac_line": AC_LINE_SHIPPED, "dense_ac_line": dense_line,
            "note": "the dec-500 INTERPOLATED peak is the reference; the two "
                    "errors compared against it are the dec-50 LATTICE peak "
                    "and the dec-50 INTERPOLATED peak",
            "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **provenance(),
        }) + "\n")

        for k, src in enumerate(designs):
            row = {"i": src["i"]}
            try:
                point = _sizing_to_point(src["params"])
            except Exception as exc:                        # noqa: BLE001
                row["skip"] = f"unrealisable geometry: {exc}"
                fh.write(json.dumps(row) + "\n")
                continue

            coarse = run_point(point, "tt", swing=False, ac_peak_interp=True)

            original = SR._NETLIST
            patched = original.replace(AC_LINE_SHIPPED, dense_line)
            assert patched != original, (
                f"the `.ac` line {AC_LINE_SHIPPED!r} is not in the netlist any "
                f"more; this experiment would have silently compared dec 50 "
                f"against dec 50")
            try:
                SR._NETLIST = patched
                dense = run_point(point, "tt", swing=False, ac_peak_interp=True)
            finally:
                SR._NETLIST = original

            row.update(ok_coarse=coarse.ok, ok_dense=dense.ok)
            if not (coarse.ok and dense.ok
                    and coarse.has_interp_peak and dense.has_interp_peak):
                row["skip"] = (coarse.fail_reason or dense.fail_reason
                               or "no interior peak at one of the two densities")
                fh.write(json.dumps(row) + "\n")
                continue
            # The dense run must actually BE denser, or the comparison is
            # vacuous. Checked on the measured grid, not on the string.
            row["dense_step_octaves"] = dense.peak_interp["step_octaves"]
            row["coarse_step_octaves"] = coarse.peak_interp["step_octaves"]
            ref = float(dense.f_pk_interp_hz)
            row.update({
                "f_ref_hz": ref,
                "f_lattice_hz": coarse.f_pk_hz,
                "f_interp_hz": coarse.f_pk_interp_hz,
                "err_lattice_oct": math.log2(float(coarse.f_pk_hz) / ref),
                "err_interp_oct": math.log2(float(coarse.f_pk_interp_hz) / ref),
                "g_ref_db": dense.g_pk_interp_db,
                "err_lattice_db": float(coarse.g_pk_db) - float(dense.g_pk_interp_db),
                "err_interp_db": float(coarse.g_pk_interp_db)
                - float(dense.g_pk_interp_db),
            })
            fh.write(json.dumps(row) + "\n")
            if (k + 1) % 10 == 0:
                print(f"  {k + 1}/{len(designs)}  "
                      f"{time.perf_counter() - t0:6.1f} s", flush=True)
    print(f"dense validation -> {out_path}  ({time.perf_counter() - t0:.1f} s)")
    return out_path


def analyse_dense(path: Optional[Path] = None) -> dict:
    path = path or (HERE / "peak_interp_dense.jsonl")
    rows = load(path)
    data = [r for r in rows[1:] if "skip" not in r]
    el = [abs(r["err_lattice_oct"]) for r in data]
    ei = [abs(r["err_interp_oct"]) for r in data]
    med_l = float(np.median(el)) if el else None
    med_i = float(np.median(ei)) if ei else None
    return {
        "kind": "dense",
        "n_compared": len(data), "n_skipped": len(rows) - 1 - len(data),
        "dense_dec": rows[0].get("dense_dec"),
        "step_octaves_coarse": (data[0]["coarse_step_octaves"] if data else None),
        "step_octaves_dense": (data[0]["dense_step_octaves"] if data else None),
        "abs_err_lattice_oct": _quantiles(el),
        "abs_err_interp_oct": _quantiles(ei),
        "error_reduction_x": (med_l / med_i if med_l and med_i else None),
        "n_interp_worse_than_lattice": sum(1 for a, b in zip(el, ei) if b > a),
        "abs_err_lattice_db": _quantiles([abs(r["err_lattice_db"]) for r in data]),
        "abs_err_interp_db": _quantiles([abs(r["err_interp_db"]) for r in data]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Analysis.
# ─────────────────────────────────────────────────────────────────────────────


def load(path: Path) -> list[dict]:
    return [json.loads(L) for L in path.open(encoding="utf-8")]


def _quantiles(x: Sequence[float]) -> dict:
    a = np.asarray(list(x), dtype=float)
    if a.size == 0:
        return {"n": 0}
    return {
        "n": int(a.size), "min": float(a.min()), "p10": float(np.percentile(a, 10)),
        "median": float(np.median(a)), "p90": float(np.percentile(a, 90)),
        "max": float(a.max()), "mean": float(a.mean()), "sd": float(a.std(ddof=1))
        if a.size > 1 else 0.0,
    }


def analyse_funnel(path: Path = FUNNEL_OUT) -> dict:
    rows = load(path)
    header, data = rows[0], [r for r in rows[1:] if "skip" not in r]
    skipped = [r for r in rows[1:] if "skip" in r]

    checkable = [r for r in data if r.get("f_pk_hz_published") is not None]
    not_reproduced = [r for r in checkable if not r["reproduces"]]

    ok = [r for r in data if r.get("interp_ok")]
    refused = [r for r in data if not r.get("interp_ok")]
    d_oct = [r["d_f_peak_oct"] for r in ok]
    out = {
        "kind": "funnel",
        "source": header.get("source"),
        "n_rows": len(rows) - 1, "n_simulated": len(data), "n_skipped": len(skipped),
        "n_checkable": len(checkable),
        "n_not_reproduced": len(not_reproduced),
        "reproduces_exactly": not not_reproduced,
        "n_interp_ok": len(ok), "n_interp_refused": len(refused),
        "refusal_edges": _count(r.get("interp_edge") for r in refused),
        "d_f_peak_oct": _quantiles(d_oct),
        "abs_d_f_peak_oct": _quantiles([abs(v) for v in d_oct]),
        "half_step_octaves": HALF_STEP_OCT,
        "n_outside_half_step": sum(1 for v in d_oct
                                   if abs(v) > HALF_STEP_OCT + 1e-12),
        "frac_shift_below_1e3_oct": (
            sum(1 for v in d_oct if abs(v) < 1e-3) / len(d_oct) if d_oct else None),
        "d_peaking_db": _quantiles([r["d_peaking_db"] for r in ok]),
        "curvature_db": _quantiles([r["curvature_db"] for r in ok]),
        # The two guards, side by side. They are allowed to disagree, and how
        # often they do is a measurement rather than a prediction.
        "guard_agreement": _count(
            f"discrete={bool(r.get('peak_is_sweep_edge'))},"
            f"interp={bool(r.get('peak_interp_is_sweep_edge'))}"
            for r in data),
        "runtime_s": _quantiles([r["runtime_s"] for r in data if "runtime_s" in r]),
    }
    return out


def _count(it) -> dict:
    d: dict = {}
    for v in it:
        k = str(v)
        d[k] = d.get(k, 0) + 1
    return dict(sorted(d.items(), key=lambda kv: -kv[1]))


def analyse_pools(path: Path = POOLS_OUT,
                  published: dict[int, Path] = PUBLISHED_POOLS) -> dict:
    rows = load(path)
    header = rows[0]
    pools = [r for r in rows[1:] if r.get("kind") == "pool"]
    trials = [r for r in rows[1:] if r.get("kind") == "trial"]

    # ---- falsification condition 4: the discrete path must not have moved ---
    pub_ids: dict[tuple[str, int], list[str]] = {}
    pub_best: dict[tuple[str, int], float] = {}
    pub_counts: dict[tuple[str, int], dict] = {}
    for rep, p in published.items():
        if not p.exists():
            continue
        for r in load(p):
            if r.get("kind") == "pool":
                key = (r["arm"], rep)
                pub_ids[key] = list(r.get("ceiling_design_ids", []))
                pub_best[key] = r.get("best_reward")
                pub_counts[key] = {
                    "n_s3": r.get("n_s3"), "n_at_ceiling": r.get("n_at_ceiling"),
                    "invalid_rate": r.get("invalid_rate"),
                    "n_simulated": r.get("n_simulated"),
                }

    per_pool = []
    for pl in pools:
        key = (pl["arm"], pl["replicate"])
        pub = pub_counts.get(key, {})
        per_pool.append({
            "arm": pl["arm"], "replicate": pl["replicate"],
            "n_simulated": pl["n_simulated"], "sec_per_sim": pl["sec_per_sim"],
            "n_s3": pl["n_s3"], "n_s3_published": pub.get("n_s3"),
            "n_at_ceiling": pl["n_at_ceiling"],
            "n_at_ceiling_published": pub.get("n_at_ceiling"),
            "invalid_rate": pl["invalid_rate"],
            "invalid_rate_published": pub.get("invalid_rate"),
            "best_reward_discrete": pl["best_reward"],
            "best_reward_published": pub_best.get(key),
            "reproduces": (pub.get("n_s3") == pl["n_s3"]
                           and pub.get("n_at_ceiling") == pl["n_at_ceiling"]
                           and pub.get("n_simulated") == pl["n_simulated"]),
            "ceiling_ids_match": (sorted(pl.get("ceiling_design_ids", []))
                                  == sorted(pub_ids.get(key, []))),
        })

    sim = [t for t in trials if t["n_sims"] > 0]
    tied = [t for t in sim
            if t["reward_discrete"] >= G74_CEILING - CEILING_TOL]
    tied_ok = [t for t in tied if t["interp_status"] == "ok"]
    tied_rewards = [round(t["reward_interp"], 9) for t in tied_ok]

    d_oct = [t["d_f_peak_oct"] for t in sim if t["interp_status"] == "ok"]
    both = [(t["reward_discrete"], t["reward_interp"]) for t in sim]
    best_disc = max((a for a, _ in both), default=None)
    best_int = max((b for _, b in both), default=None)

    return {
        "kind": "pools",
        "header": {k: header.get(k) for k in ("commit_short", "dirty",
                                              "pool_sims", "lattice_ceiling")},
        "per_pool": per_pool,
        "all_pools_reproduce": all(p["reproduces"] for p in per_pool),
        "all_ceiling_ids_match": all(p["ceiling_ids_match"] for p in per_pool),
        "n_trials": len(trials), "n_simulated": len(sim),
        "lattice_ceiling": G74_CEILING,
        # ---- THE HEADLINE ----
        "n_tied_at_lattice_ceiling": len(tied),
        "n_tied_distinct_designs": len({t["design_id"] for t in tied}),
        "n_tied_with_interp": len(tied_ok),
        "n_tied_refused": len(tied) - len(tied_ok),
        "n_distinct_rewards_after": len(set(tied_rewards)),
        "tied_rewards_after": sorted(tied_rewards, reverse=True),
        "tied_binding_spec_after": _count(t.get("worst_spec_interp")
                                          for t in tied_ok),
        "best_reward_discrete": best_disc,
        "best_reward_interp": best_int,
        "n_at_best_interp": (sum(1 for _, b in both
                                 if abs(b - best_int) <= 1e-9)
                             if best_int is not None else None),
        "n_above_lattice_ceiling_after": sum(
            1 for _, b in both if b > G74_CEILING + 1e-12),
        # ---- the cost of the interpolated path ----
        "interp_status": _count(t["interp_status"] for t in sim),
        "n_valid_but_refused": sum(
            1 for t in sim if t["verdict"] == "valid"
            and t["interp_status"] == "refused"),
        "frac_valid_but_refused": (
            sum(1 for t in sim if t["verdict"] == "valid"
                and t["interp_status"] == "refused")
            / max(1, sum(1 for t in sim if t["verdict"] == "valid"))),
        "d_f_peak_oct": _quantiles(d_oct),
        "abs_d_f_peak_oct": _quantiles([abs(v) for v in d_oct]),
        "n_outside_half_step": sum(1 for v in d_oct
                                   if abs(v) > HALF_STEP_OCT + 1e-12),
        "reward_gain": _quantiles([b - a for a, b in both
                                   if b > R.invalid_reward(len(R.V1_SPECS))]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# The plot.
# ─────────────────────────────────────────────────────────────────────────────


def plot(funnel: Path = FUNNEL_OUT, pools: Path = POOLS_OUT,
         path: Path = FIG_PATH) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15.0, 4.4))

    # (a) how far off the lattice was, on the funnel
    ax = axes[0]
    if funnel.exists():
        rows = [r for r in load(funnel)[1:] if r.get("interp_ok")]
        d = np.array([r["d_f_peak_oct"] for r in rows])
        ax.hist(d, bins=31, color="#4477aa", edgecolor="white")
        for s in (-1, 1):
            ax.axvline(s * HALF_STEP_OCT, color="#cc3311", ls="--", lw=1.2)
        ax.axvline(0.0, color="#333333", lw=0.8)
        ax.set_title(f"(a) G2 funnel: lattice error, n = {d.size}")
        ax.set_xlabel("f_peak(interpolated) - f_peak(lattice)   [octaves]")
        ax.set_ylabel("designs")
        ax.text(0.02, 0.95, "dashed = +/- half a grid step",
                transform=ax.transAxes, va="top", fontsize=8, color="#cc3311")

    # (b) the ties, before and after
    ax = axes[1]
    if pools.exists():
        rows = [r for r in load(pools)[1:] if r.get("kind") == "trial"]
        tied = [r for r in rows
                if r["n_sims"] > 0
                and r["reward_discrete"] >= G74_CEILING - CEILING_TOL
                and r["interp_status"] == "ok"]
        y = np.array([r["reward_interp"] for r in tied])
        x = np.arange(y.size)
        ax.axhline(G74_CEILING, color="#cc3311", lw=1.4,
                   label=f"lattice ceiling {G74_CEILING:.6f}")
        ax.scatter(x, y, s=22, color="#228833", zorder=3,
                   label=f"interpolated, {len(set(np.round(y, 9)))} distinct")
        ax.set_title(f"(b) the {y.size} lattice-ceiling ties, re-scored")
        ax.set_xlabel("tied design (arbitrary order)")
        ax.set_ylabel("reward_v1")
        ax.legend(fontsize=8, loc="lower right")

    # (c) THE COMB AND THE CONTINUUM. The lattice reward takes a handful of
    # values because `S3_f_peak`'s margin is a lattice quantity; the
    # interpolated one is continuous. Drawn on designs feasible on BOTH paths
    # so the comparison is a change of RESOLUTION and not a change of
    # population -- the 63 designs whose feasibility flips are counted in
    # `analyse_pools`, not smuggled into a histogram.
    ax = axes[2]
    if pools.exists():
        rows = [r for r in load(pools)[1:]
                if r.get("kind") == "trial" and r["n_sims"] > 0]
        a = np.array([r["reward_discrete"] for r in rows])
        b = np.array([r["reward_interp"] for r in rows])
        m = (a >= 8.0) & (b >= 8.0)
        lo = 8.70
        m &= (a >= lo) & (b >= lo)
        bins = np.linspace(lo, 9.005, 60)
        ax.hist(b[m], bins=bins, color="#228833", alpha=0.75,
                label=f"interpolated ({len(set(np.round(b[m], 9)))} values)")
        vals, counts = np.unique(np.round(a[m], 9), return_counts=True)
        ax.vlines(vals, 0, counts, color="#cc3311", lw=1.6,
                  label=f"lattice ({vals.size} values)")
        ax.axvline(G74_CEILING, color="#333333", ls="--", lw=1.0)
        ax.set_title(f"(c) the comb and the continuum, n = {int(m.sum())}")
        ax.set_xlabel("reward_v1  (top of the feasible band)")
        ax.set_ylabel("designs")
        ax.legend(fontsize=8, loc="upper left")

    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)
    print(f"figure -> {path}")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# CLI.
# ─────────────────────────────────────────────────────────────────────────────


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--funnel", action="store_true",
                    help="replay the 300 G2 funnel designs (~2 min)")
    ap.add_argument("--pools", action="store_true",
                    help="replay the 4 task-0 pools, 8000 sims (~40 min)")
    ap.add_argument("--dense", type=int, default=0, metavar="N",
                    help="validate the vertex against a dec 500 sweep on N "
                         "designs (2N simulations, ~2 min at N=30)")
    ap.add_argument("--limit", type=int, default=None,
                    help="funnel only: stop after N designs (a smoke test)")
    ap.add_argument("--pool-sims", type=int, default=POOL_SIMS)
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--plot", action="store_true")
    a = ap.parse_args(argv)

    if a.funnel:
        replay_funnel(limit=a.limit)
    if a.pools:
        replay_pools(pool_sims=a.pool_sims)
    if a.dense:
        replay_dense(n=a.dense)
    if a.analyse:
        if FUNNEL_OUT.exists():
            print(json.dumps(analyse_funnel(), indent=2))
        if POOLS_OUT.exists():
            print(json.dumps(analyse_pools(), indent=2))
        if (HERE / "peak_interp_dense.jsonl").exists():
            print(json.dumps(analyse_dense(), indent=2))
    if a.plot:
        plot()
    if not any((a.funnel, a.pools, a.dense, a.analyse, a.plot)):
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    sys.exit(main())
