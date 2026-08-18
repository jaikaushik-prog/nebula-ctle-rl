"""
experiments/exp_difficulty.py -- task 0. **How hard is the problem G3 will run?**

THE QUESTION, IN ONE LINE
--------------------------
How many random samples does it take to reach the +8.950669 reward ceiling
(G74), and how many to reach a design that meets S3?

WHY IT IS WORTH ASKING BEFORE THE 12-HOUR SWEEP
------------------------------------------------
Three already-measured numbers, taken together, predict that the G3 sweep as
specified cannot separate its arms:

  * random LHS meets S3 at **13.44 %** at `cl_mid` (`BASELINES.md` §5, and
    `PLAN.md` D4's recommended baseline);
  * the reward **saturates at +8.950669** (G74) -- a property of the
    `meas ac MAX` frequency lattice, not of the circuit;
  * one evaluation costs **0.28 s** (`G2_RESULTS.md` §3).

If random search reaches the ceiling in single-digit samples, every arm ties at
the ceiling, and `BASELINES.md` §8's own CI-overlap rule then forbids reporting
a ranking. That would make the sweep an expensive way to measure the AC grid.
**This file measures it instead of assuming it.**

WHAT IS HELD FIXED, DELIBERATELY
---------------------------------
Nothing about the problem definition changes. Same box
(`rl.contract.ACTION_SPACE`), same sampler (`baselines._lhs`), same evaluator
(`rl.evaluator.evaluate`), same reward (`rl.reward_v1`, `V1_SPECS`), same
conditions (TT / 1.00 / 27 C / `cl_mid`, drawn passives, real mirror). The two
arms differ ONLY by whether `experiments/prescreen.py` sits in front, which is
already a flag on `baselines.Objective`.

`test_the_restart_loop_matches_method_lhs_exactly` is the gate on that claim:
it asserts this module's sampling loop emits the identical `u` sequence
`baselines.method_lhs` does from the same seed.

THE TWO SUB-EXPERIMENTS, AND WHY THERE ARE TWO
------------------------------------------------
* **restarts** -- N independent runs per arm, each stopping the moment the
  ceiling is reached. `sims_to_ceiling` is a censored waiting time, so it needs
  independent replicates and a bootstrap CI; nothing after the ceiling informs
  it, so stopping there is free and not a bias.
* **pool** -- one long run per arm with NO early stop. The reward
  *distribution* and the count of *distinct designs tied at the ceiling* both
  need an unbiased sample of fixed size, which a ceiling-stopped run is not.

COST ACCOUNTING (G65's definition, unchanged)
----------------------------------------------
The budget is in SIMULATIONS and every ngspice invocation is charged, including
retries and invalid designs -- `Objective` already does this. A pre-screened
rejection costs **zero simulations and one proposal**, so both axes are
reported for both arms and neither is allowed to stand alone.

WALL CLOCK (G70, G71)
----------------------
Runs SERIALLY by default. One concurrent ngspice costs 4.8x per run against the
extended library, and this evaluator draws real passives so it uses the
extended library. Wall clock is reported as a secondary column and is only
meaningful when nothing else was simulating.

USAGE
    python -m nebula.experiments.exp_difficulty --probe          # cost only
    python -m nebula.experiments.exp_difficulty --run            # the experiment
    python -m nebula.experiments.exp_difficulty --analyse FILE.jsonl
    python -m nebula.experiments.exp_difficulty --plot FILE.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Mapping, Optional, Sequence

import numpy as np

from nebula.experiments.baselines import (
    BudgetExhausted,
    Objective,
    PROBLEMS,
    Trial,
    _lhs,
    bootstrap_median,
    provenance,
    reward_ceiling,
)
from nebula.rl import reward_v1 as R
from nebula.rl.contract import N_ACTIONS
from nebula.rl.runlog import RunLog
from nebula.rl.runlog import read as runlog_read

HERE = Path(__file__).resolve().parent
LOG_PATH: Path = HERE / "difficulty_run.jsonl"
FIG_PATH: Path = HERE.parents[0] / "figures" / "difficulty.png"

# ─────────────────────────────────────────────────────────────────────────────
# The experiment's constants. Every one is a COUNT or a SEED -- none is a
# parameter range, a reward weight or a spec tolerance (CLAUDEwa.md §8 rule 6,
# PLAN.md §7 rule 7). Changing any of them changes precision, not the problem.
# ─────────────────────────────────────────────────────────────────────────────

#: Independent restarts per arm. The brief asks for >= 20; 24 is the smallest
#: multiple of 8 above it, so a future parallel re-run maps cleanly onto the
#: 8 workers `BASELINES.md` §7f fixes.
RESTARTS: int = 24

#: Simulation budget per restart. Sized from the decision rule, not from taste:
#: the rule's upper band is "median > 500", so a budget of 600 lets that band
#: be reached rather than only bounded. A restart that exhausts it is CENSORED
#: and is reported as censored, never substituted (7c).
BUDGET_SIMS: int = 600

#: **A SIMULATION BUDGET DOES NOT TERMINATE A SCREENED ARM, and that is a real
#: hazard rather than a test artifact.** A pre-screened rejection costs zero
#: simulations by design (G65's accounting, and the whole point of the screen),
#: so an arm whose screen rejects every proposal never advances `n_sims` and
#: loops forever — quietly, at full CPU, reporting nothing. The cap is the
#: second termination condition, and hitting it is RECORDED (`proposal_cap_hit`)
#: rather than being indistinguishable from a run that simply found nothing.
#:
#: 100x is chosen against the measured screen: `BASELINES.md` §5 puts free
#: rejection at 61.7 %, i.e. ~2.6 proposals per simulation, and session 18
#: measured 63.9 % at benchmark conditions. 100x is ~38x that, so the cap
#: cannot bind on any screen resembling the one we have — it only catches a
#: screen that has become pathological.
PROPOSAL_CAP_FACTOR: int = 100

#: Simulations in the unbiased pooled sample, per arm. Sets the resolution on
#: the ceiling rate: at an expected ~1 % ceiling rate, 2000 simulations gives
#: ~20 ties, enough to count distinct designs and not enough to claim a rate
#: to three figures.
POOL_SIMS: int = 2000

#: The seed protocol, stated as a rule so a row identifies its own run:
#: `BASE_SEED + ARM_OFFSET[arm] + KIND_OFFSET[kind] + replicate`.
#:
#: **The leading 1 is not decoration.** `baselines.BASE_SEED` is 20 260 807 and
#: its offsets reach +304 000 before the replicate, so the benchmark occupies
#: roughly 20 260 807 .. 20 565 000. A bare 20 260 818 would sit INSIDE that
#: block and share streams with it — which the seed-collision test caught.
BASE_SEED: int = 120_260_818
ARM_OFFSET: dict[str, int] = {"unscreened": 0, "screened": 10_000}
KIND_OFFSET: dict[str, int] = {"restart": 0, "pool": 5_000}

ARMS: tuple[str, ...] = ("unscreened", "screened")

#: `sims_to_ceiling`'s comparison tolerance. The derived ceiling is
#: 8.950669295... and G74 measured designs at 8.950670, i.e. the float
#: arithmetic lands a few ULP above the closed form.
CEILING_TOL: float = 1e-6

#: The three rows that ARE S3 (`reward_v1.V0_SPECS`). "Meets S3" here means all
#: three margins >= 0, which is the same test `reward()` applies -- this module
#: does not reimplement a spec check (7f).
S3_SPECS: tuple[str, ...] = R.V0_SPECS


def run_seed(arm: str, kind: str, replicate: int) -> int:
    """The stated rule. Recorded on every logged row so a run is re-derivable."""
    if arm not in ARM_OFFSET:
        raise KeyError(f"unknown arm {arm!r}")
    if kind not in KIND_OFFSET:
        raise KeyError(f"unknown kind {kind!r}")
    return BASE_SEED + ARM_OFFSET[arm] + KIND_OFFSET[kind] + int(replicate)


# ─────────────────────────────────────────────────────────────────────────────
# Reading a trial. Two predicates, both derived from what `reward_v1` already
# computed -- nothing here re-tests a spec.
# ─────────────────────────────────────────────────────────────────────────────


def margins_meet_s3(m: Optional[Mapping[str, float]]) -> bool:
    """All three S3 margins >= 0. **THE definition, used by every caller.**

    Rule 9: `exp_attribution.py` asks the same question of a different
    population and must not answer it with a second copy of this test. A
    missing or empty margin dict is NOT a pass -- the design was never
    measured, which is different from measuring it and failing.
    """
    if not m:
        return False
    try:
        return all(float(m[k]) >= 0.0 for k in S3_SPECS)
    except KeyError:                                       # pragma: no cover
        return False


def meets_s3(tr: Trial) -> bool:
    """All three S3 margins >= 0 on the worst evaluated point.

    `Trial.margins` is `RewardBreakdown.margins` restricted to the scored spec
    set, so it is present exactly when the design was scorable. A screened-out
    or invalid trial has `margins=None` and is not an S3 pass -- which is the
    right reading: it was never measured.
    """
    return margins_meet_s3(tr.margins)


def at_ceiling(tr: Trial, ceiling: float, tol: float = CEILING_TOL) -> bool:
    """Did this trial score the AC-grid ceiling? Simulated trials only."""
    return tr.n_sims > 0 and float(tr.reward) >= ceiling - tol


# ─────────────────────────────────────────────────────────────────────────────
# The sampling loop. `baselines.method_lhs` with ONE addition: a stop predicate.
# ─────────────────────────────────────────────────────────────────────────────


def lhs_stream(obj: Objective, rng: np.random.Generator) -> Iterator[np.ndarray]:
    """The exact sequence `baselines.method_lhs` proposes, as a generator.

    Same `_lhs`, same block size, same "a fresh independent hypercube follows"
    continuation rule. Yielding instead of evaluating in place is what lets a
    caller stop on a condition; it changes no draw.
    """
    d = N_ACTIONS
    while True:
        n = max(2, math.ceil((obj.budget_sims - obj.n_sims)
                             / obj.problem.sims_per_design))
        for row in _lhs(n, d, rng):
            yield row


def run_restart(arm: str, replicate: int, budget_sims: int = BUDGET_SIMS,
                stop_at_ceiling: bool = True,
                max_proposals: Optional[int] = None,
                on_trial: Optional[Callable[[Trial], None]] = None) -> dict:
    """One independent restart. Returns its waiting times, censored honestly.

    Stops at the ceiling because nothing after it informs any of the three
    waiting times: `first_s3 <= first_feasible <= first_ceiling` by
    construction (the ceiling is on the feasible branch, and S3 feasibility is
    implied by V1 feasibility). `stop_at_ceiling=False` exists for the pool.

    Terminates on the SIMULATION budget or on `max_proposals`, whichever comes
    first — see `PROPOSAL_CAP_FACTOR` for why the second one has to exist.
    """
    seed = run_seed(arm, "restart", replicate)
    rng = np.random.default_rng(seed)
    cap = int(max_proposals if max_proposals is not None
              else PROPOSAL_CAP_FACTOR * budget_sims)
    obj = Objective(PROBLEMS["P1"], budget_sims=budget_sims,
                    prescreen=(arm == "screened"), on_trial=on_trial)
    ceiling = obj.ceiling

    first_s3: Optional[tuple[int, int]] = None          # (sims, proposals)
    first_feasible: Optional[tuple[int, int]] = None
    first_ceiling: Optional[tuple[int, int]] = None
    cap_hit = False

    t0 = time.perf_counter()
    try:
        for row in lhs_stream(obj, rng):
            obj.check_budget()
            if len(obj.trials) >= cap:
                cap_hit = True
                break
            tr = obj.evaluate(row)
            n_prop = len(obj.trials)
            if first_s3 is None and meets_s3(tr):
                first_s3 = (obj.n_sims, n_prop)
            if first_feasible is None and tr.n_sims > 0 and tr.feasible:
                first_feasible = (obj.n_sims, n_prop)
            if first_ceiling is None and at_ceiling(tr, ceiling):
                first_ceiling = (obj.n_sims, n_prop)
                if stop_at_ceiling:
                    break
    except BudgetExhausted:
        pass
    wall = time.perf_counter() - t0

    s = obj.summary()
    return {
        "arm": arm,
        "kind": "restart",
        "replicate": int(replicate),
        "seed": seed,
        "budget_sims": int(budget_sims),
        "max_proposals": cap,
        "proposal_cap_hit": cap_hit,
        "stop_at_ceiling": bool(stop_at_ceiling),
        "reward_ceiling": ceiling,
        "n_sims": obj.n_sims,
        "n_proposals": len(obj.trials),
        "n_screened_out": obj.n_screened_out,
        "wall_s": wall,
        "sims_to_first_s3": (first_s3[0] if first_s3 else None),
        "proposals_to_first_s3": (first_s3[1] if first_s3 else None),
        "sims_to_first_feasible": (first_feasible[0] if first_feasible else None),
        "proposals_to_first_feasible": (first_feasible[1] if first_feasible else None),
        "sims_to_ceiling": (first_ceiling[0] if first_ceiling else None),
        "proposals_to_ceiling": (first_ceiling[1] if first_ceiling else None),
        "censored_s3": first_s3 is None,
        "censored_feasible": first_feasible is None,
        "censored_ceiling": first_ceiling is None,
        "invalid_rate": s["invalid_rate"],
        "invalid_reasons": s["invalid_reasons"],
        "best_reward": s["best_reward"],
    }


def run_pool(arm: str, pool_sims: int = POOL_SIMS,
             max_proposals: Optional[int] = None,
             replicate: int = 0,
             on_trial: Optional[Callable[[Trial], None]] = None,
             ac_peak_interp: bool = False) -> dict:
    """One long unbiased run per arm: the reward distribution and the ties.

    No early stop, so the reward sample is not truncated at the first success
    and the ceiling ties can be counted over a FIXED number of simulations.
    """
    seed = run_seed(arm, "pool", replicate)
    rng = np.random.default_rng(seed)
    cap = int(max_proposals if max_proposals is not None
              else PROPOSAL_CAP_FACTOR * pool_sims)
    rewards: list[float] = []
    ceiling_ids: list[str] = []
    n_s3 = 0
    cap_hit = False

    obj = Objective(PROBLEMS["P1"], budget_sims=pool_sims,
                    prescreen=(arm == "screened"), on_trial=on_trial,
                    ac_peak_interp=ac_peak_interp)
    ceiling = obj.ceiling

    t0 = time.perf_counter()
    try:
        for row in lhs_stream(obj, rng):
            obj.check_budget()
            if len(obj.trials) >= cap:
                cap_hit = True
                break
            tr = obj.evaluate(row)
            if tr.n_sims > 0:
                rewards.append(float(tr.reward))
                if meets_s3(tr):
                    n_s3 += 1
                if at_ceiling(tr, ceiling):
                    ceiling_ids.append(tr.design_id or f"<unnamed:{tr.index}>")
    except BudgetExhausted:
        pass
    wall = time.perf_counter() - t0

    s = obj.summary()
    n_sim = len(rewards)
    return {
        "arm": arm,
        "kind": "pool",
        "seed": seed,
        "replicate": int(replicate),
        "pool_sims": int(pool_sims),
        "max_proposals": cap,
        "proposal_cap_hit": cap_hit,
        "reward_ceiling": ceiling,
        "reward_floor": obj.floor,
        "n_sims": obj.n_sims,
        "n_proposals": len(obj.trials),
        "n_simulated": n_sim,
        "n_screened_out": obj.n_screened_out,
        "wall_s": wall,
        "sec_per_sim": (wall / obj.n_sims if obj.n_sims else None),
        "rewards": rewards,
        "n_s3": n_s3,
        "s3_rate": (n_s3 / n_sim if n_sim else None),
        "n_feasible": s["n_feasible"],
        "feasible_rate": (s["n_feasible"] / n_sim if n_sim else None),
        "n_at_ceiling": len(ceiling_ids),
        "n_distinct_at_ceiling": len(set(ceiling_ids)),
        "ceiling_rate": (len(ceiling_ids) / n_sim if n_sim else None),
        "ceiling_design_ids": sorted(set(ceiling_ids)),
        "invalid_rate": s["invalid_rate"],
        "invalid_reasons": s["invalid_reasons"],
        "best_reward": s["best_reward"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Analysis. Censored waiting times, medians with a bootstrap band.
# ─────────────────────────────────────────────────────────────────────────────


def censored_summary(runs: Sequence[dict], key: str, alpha: float = 0.10,
                     seed: int = 0) -> dict:
    """Three numbers and never one (7c): reached-fraction, conditional median, censored count.

    The budget is **not** substituted for a censored run, infinity is not
    substituted, and censored runs are not dropped in favour of a mean of the
    rest. Each of those produces a plausible number that flatters the arm that
    got lucky. `alpha=0.10` gives the 90 % band the brief asks for.
    """
    vals = [r[key] for r in runs if r.get(key) is not None]
    n = len(runs)
    med, lo, hi = bootstrap_median(vals, alpha=alpha,
                                   rng=np.random.default_rng(seed))
    return {
        "metric": key,
        "n_runs": n,
        "n_reached": len(vals),
        "n_censored": n - len(vals),
        "reached_fraction": (len(vals) / n if n else None),
        "median_conditional": (med if vals else None),
        "ci90_lo": (lo if vals else None),
        "ci90_hi": (hi if vals else None),
        "min": (min(vals) if vals else None),
        "max": (max(vals) if vals else None),
        "values": sorted(vals),
    }


#: The pre-registered decision rule (`PREDICTIONS.md` entry 7). Encoded here so
#: the verdict is READ OFF the data rather than argued after it.
DECISION_LO: int = 50
DECISION_HI: int = 500


def decide(median_by_arm: dict[str, Optional[float]]) -> dict:
    """Apply the pre-registered rule to the measured medians.

    `< 50` in EITHER arm -> the thesis holds. `> 500` in BOTH -> it does not.
    Anything else -> report and stop; the call is the human's.
    """
    got = {k: v for k, v in median_by_arm.items() if v is not None}
    if not got:
        return {"verdict": "undecided",
                "reason": "every arm censored: no median exists",
                "medians": median_by_arm}
    if any(v < DECISION_LO for v in got.values()):
        return {"verdict": "thesis_holds",
                "reason": (f"median samples-to-ceiling < {DECISION_LO} in at "
                           f"least one arm -> the sweep as specified cannot "
                           f"separate arms; proceed to task 1"),
                "medians": median_by_arm}
    if all(v > DECISION_HI for v in got.values()) and len(got) == len(median_by_arm):
        return {"verdict": "thesis_fails",
                "reason": (f"median samples-to-ceiling > {DECISION_HI} in every "
                           f"arm -> launch the sweep roughly as PLAN.md §3 "
                           f"specifies"),
                "medians": median_by_arm}
    return {"verdict": "in_between",
            "reason": (f"median samples-to-ceiling is between {DECISION_LO} and "
                       f"{DECISION_HI} -> report and STOP; the human decides"),
            "medians": median_by_arm}


def analyse(rows: Sequence[dict]) -> dict:
    """Everything the deliverable needs, from the logged rows alone."""
    restarts = [r for r in rows if r.get("kind") == "restart"]
    pools = [r for r in rows if r.get("kind") == "pool"]

    per_arm: dict[str, dict] = {}
    for arm in ARMS:
        rr = [r for r in restarts if r["arm"] == arm]
        pp = [r for r in pools if r["arm"] == arm]
        if not rr and not pp:
            continue
        entry: dict = {"n_restarts": len(rr)}
        for key in ("sims_to_ceiling", "proposals_to_ceiling",
                    "sims_to_first_s3", "proposals_to_first_s3",
                    "sims_to_first_feasible", "proposals_to_first_feasible"):
            if rr:
                entry[key] = censored_summary(rr, key)
        if rr:
            entry["wall_s_total"] = sum(r["wall_s"] for r in rr)
            entry["sims_total"] = sum(r["n_sims"] for r in rr)
            entry["sec_per_sim"] = (entry["wall_s_total"] / entry["sims_total"]
                                    if entry["sims_total"] else None)
        if pp:
            p = pp[0]
            entry["pool"] = {k: p[k] for k in (
                "pool_sims", "n_sims", "n_proposals", "n_simulated",
                "n_screened_out", "s3_rate", "feasible_rate", "ceiling_rate",
                "n_at_ceiling", "n_distinct_at_ceiling", "ceiling_design_ids",
                "invalid_rate", "invalid_reasons", "best_reward", "wall_s",
                "sec_per_sim", "reward_ceiling", "reward_floor")}
            entry["pool"]["reward_quantiles"] = _quantiles(p["rewards"])
            entry["pool"]["screen_free_rejection"] = (
                p["n_screened_out"] / p["n_proposals"] if p["n_proposals"] else None)
        per_arm[arm] = entry

    medians = {arm: per_arm[arm].get("sims_to_ceiling", {}).get("median_conditional")
               for arm in per_arm if "sims_to_ceiling" in per_arm[arm]}
    # A censored arm has no median; the rule reads that as "not below 50".
    for arm, e in per_arm.items():
        c = e.get("sims_to_ceiling")
        if c and c["n_reached"] == 0:
            medians[arm] = None

    return {"per_arm": per_arm, "decision": decide(medians),
            "decision_rule": {"lo": DECISION_LO, "hi": DECISION_HI,
                              "source": "PREDICTIONS.md entry 7"}}


def _quantiles(x: Sequence[float]) -> dict:
    a = np.asarray([v for v in x if np.isfinite(v)], dtype=float)
    if a.size == 0:
        return {}
    qs = (0, 5, 10, 25, 50, 75, 90, 95, 99, 100)
    return {f"p{q}": float(np.percentile(a, q)) for q in qs} | {"n": int(a.size)}


# ─────────────────────────────────────────────────────────────────────────────
# The run.
# ─────────────────────────────────────────────────────────────────────────────


def run(restarts: int = RESTARTS, budget_sims: int = BUDGET_SIMS,
        pool_sims: int = POOL_SIMS, arms: Sequence[str] = ARMS,
        log_path: Path = LOG_PATH) -> dict:
    """Both arms, both sub-experiments, streamed to a log as they finish.

    The log streams for the reason session 18's pilot proved: it was killed one
    job from the end and every row survived.
    """
    rows: list[dict] = []
    header = {"experiment": "difficulty (task 0)",
              "restarts": restarts, "budget_sims": budget_sims,
              "pool_sims": pool_sims, "arms": list(arms),
              "base_seed": BASE_SEED,
              "seed_rule": "BASE_SEED + ARM_OFFSET[arm] + KIND_OFFSET[kind] + replicate",
              "decision_rule": {"lo": DECISION_LO, "hi": DECISION_HI},
              **provenance()}
    with RunLog(Path(log_path), header=header) as log:
        for arm in arms:
            for i in range(restarts):
                r = run_restart(arm, i, budget_sims=budget_sims)
                rows.append(r)
                # The event NAME is the row's own `kind`, not a second literal:
                # `RunLog.event` merges `**fields` over `{"kind": "event"}`, so a
                # mismatch here would give a row whose `kind` and `event`
                # disagree and a reader that silently finds nothing (rule 9).
                log.event(r["kind"], **r)
                print(f"  [{arm:10s}] restart {i + 1:2d}/{restarts}  "
                      f"sims={r['n_sims']:4d} prop={r['n_proposals']:5d}  "
                      f"ceiling={r['sims_to_ceiling']}  s3={r['sims_to_first_s3']}  "
                      f"{r['wall_s']:.1f} s", flush=True)
            p = run_pool(arm, pool_sims=pool_sims)
            rows.append(p)
            log.event(p["kind"], **p)
            print(f"  [{arm:10s}] pool  sims={p['n_sims']} prop={p['n_proposals']} "
                  f"s3={p['s3_rate']:.4f} ceiling_ties={p['n_at_ceiling']} "
                  f"distinct={p['n_distinct_at_ceiling']} {p['wall_s']:.1f} s",
                  flush=True)
    out = analyse(rows)
    out["log"] = str(log_path)
    return out


def run_more_pools(pool_sims: int = POOL_SIMS, replicate: int = 1,
                   arms: Sequence[str] = ARMS,
                   log_path: Optional[Path] = None) -> dict:
    """MORE pooled samples, fresh seeds -- G89's confirmation run.

    The suspicion is that the pre-screen discards ceiling-capable designs: the
    first pools put the per-proposal ceiling rate at 0.4500 % unscreened
    against 0.2408 % screened, a rate ratio of 0.535 whose **95 % CI
    [0.236, 1.211] spans 1.0** on 9 and 16 events. That interval is the whole
    problem, and the only fix is more events.

    These pools are drawn the same way at a DIFFERENT replicate, so their
    counts pool with the originals by simple addition -- independent samples of
    the same quantity, not a re-analysis of the same one.
    """
    rows: list[dict] = []
    path = Path(log_path) if log_path is not None else (
        HERE / f"difficulty_pool_r{replicate}.jsonl")
    header = {"experiment": f"difficulty pools, replicate {replicate} (G89)",
              "pool_sims": pool_sims, "replicate": replicate,
              "arms": list(arms), "base_seed": BASE_SEED,
              "pools_with": "difficulty_run.jsonl (replicate 0)",
              **provenance()}
    with RunLog(path, header=header) as log:
        for arm in arms:
            p = run_pool(arm, pool_sims=pool_sims, replicate=replicate)
            rows.append(p)
            log.event(p["kind"], **p)
            print(f"  [{arm:10s}] pool r{replicate} sims={p['n_sims']} "
                  f"prop={p['n_proposals']} s3={p['s3_rate']:.4f} "
                  f"ceiling_ties={p['n_at_ceiling']} "
                  f"distinct={p['n_distinct_at_ceiling']} {p['wall_s']:.1f} s",
                  flush=True)
    return {"rows": rows, "log": str(path)}


def ceiling_rate_ratio(pools: Sequence[dict]) -> dict:
    """G89's statistic: per-PROPOSAL ceiling rate, screened over unscreened.

    Per proposal rather than per simulation, because a screen can only REMOVE
    proposals -- so absent any bias the two arms must show the same rate on
    this axis, and a ratio below 1 means ceiling-capable designs were thrown
    away. The per-SIMULATION rate cannot answer this: the screen is supposed to
    raise that one.
    """
    def _sum(arm: str, key: str) -> int:
        return sum(int(p[key]) for p in pools if p["arm"] == arm)

    a, na = _sum("unscreened", "n_at_ceiling"), _sum("unscreened", "n_proposals")
    b, nb = _sum("screened", "n_at_ceiling"), _sum("screened", "n_proposals")
    if not (a and b and na and nb):
        return {"n_unscreened_events": a, "n_screened_events": b,
                "ratio": None,
                "note": "a zero event count makes the log-ratio undefined"}
    ru, rs = a / na, b / nb
    lr = math.log(rs / ru)
    se = math.sqrt(1.0 / a + 1.0 / b)
    lo, hi = math.exp(lr - 1.96 * se), math.exp(lr + 1.96 * se)
    return {
        "n_unscreened_events": a, "n_unscreened_proposals": na,
        "n_screened_events": b, "n_screened_proposals": nb,
        "rate_unscreened": ru, "rate_screened": rs,
        "ratio": math.exp(lr), "ci95": (lo, hi),
        "excludes_one": bool(hi < 1.0 or lo > 1.0),
        "implied_false_rejection": 1.0 - math.exp(lr),
        "implied_false_rejection_ci95": (1.0 - hi, 1.0 - lo),
    }


def load(path: Path) -> list[dict]:
    """Rebuild the rows from a log. `--analyse` works on a killed run."""
    return [r for r in runlog_read(Path(path))
            if r.get("kind") in ("restart", "pool") and "event" in r]


# ─────────────────────────────────────────────────────────────────────────────
# Reporting. ASCII only -- the console is cp1252 (CLAUDE.md rule 7).
# ─────────────────────────────────────────────────────────────────────────────


def print_report(out: dict) -> None:
    print()
    print("=" * 78)
    print("TASK 0 -- DIFFICULTY OF THE PROBLEM THE G3 SWEEP WILL RUN")
    print("=" * 78)
    for arm, e in out["per_arm"].items():
        print(f"\n-- {arm.upper()} " + "-" * (74 - len(arm)))
        if "sims_to_ceiling" in e:
            print(f"  restarts {e['n_restarts']}, "
                  f"{e['sims_total']} simulations, {e['wall_s_total']:.1f} s "
                  f"({e['sec_per_sim']:.4f} s/sim, SERIAL)")
            hdr = f"  {'metric':30s} {'reached':>9s} {'median':>10s} {'90% CI':>20s}"
            print(hdr)
            for key in ("sims_to_ceiling", "proposals_to_ceiling",
                        "sims_to_first_s3", "proposals_to_first_s3",
                        "sims_to_first_feasible", "proposals_to_first_feasible"):
                c = e[key]
                med = ("--" if c["median_conditional"] is None
                       else f"{c['median_conditional']:.1f}")
                ci = ("--" if c["ci90_lo"] is None
                      else f"[{c['ci90_lo']:.1f}, {c['ci90_hi']:.1f}]")
                print(f"  {key:30s} {c['n_reached']:4d}/{c['n_runs']:<4d} "
                      f"{med:>10s} {ci:>20s}")
        p = e.get("pool")
        if p:
            print(f"\n  pool: {p['n_sims']} simulations from {p['n_proposals']} "
                  f"proposals ({p['n_screened_out']} screened out)")
            print(f"    S3 rate          {p['s3_rate'] * 100:.2f} %   "
                  f"(BASELINES.md D4 baseline: 13.44 %)")
            print(f"    feasible rate    {p['feasible_rate'] * 100:.2f} %   "
                  f"(all 7 V1 specs)")
            print(f"    ceiling rate     {p['ceiling_rate'] * 100:.2f} %   "
                  f"({p['n_at_ceiling']} ties, "
                  f"{p['n_distinct_at_ceiling']} DISTINCT designs)")
            print(f"    invalid rate     {p['invalid_rate'] * 100:.2f} %   "
                  f"{p['invalid_reasons']}")
            q = p["reward_quantiles"]
            if q:
                print(f"    reward  p0 {q['p0']:+.3f}  p25 {q['p25']:+.3f}  "
                      f"p50 {q['p50']:+.3f}  p75 {q['p75']:+.3f}  "
                      f"p95 {q['p95']:+.3f}  p100 {q['p100']:+.3f}")
                print(f"    (floor {p['reward_floor']:+.4f}, "
                      f"ceiling {p['reward_ceiling']:+.6f})")
    d = out["decision"]
    print("\n" + "=" * 78)
    print(f"PRE-REGISTERED DECISION RULE (< {out['decision_rule']['lo']} / "
          f"> {out['decision_rule']['hi']} simulations to ceiling)")
    print(f"  medians: {d['medians']}")
    print(f"  VERDICT: {d['verdict'].upper()}")
    print(f"  {d['reason']}")
    print("=" * 78)


def plot(rows: Sequence[dict], path: Path = FIG_PATH) -> Path:
    """One figure, two panels: the reward SHAPE, and the waiting time.

    The brief asks for the reward distribution's shape rather than a summary,
    so the left panel is an ECDF -- every simulated design is a step in it and
    nothing is binned away.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pools = {r["arm"]: r for r in rows if r.get("kind") == "pool"}
    restarts: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("kind") == "restart":
            restarts.setdefault(r["arm"], []).append(r)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 5.0))
    colours = {"unscreened": "#1f77b4", "screened": "#d62728"}

    for arm, p in pools.items():
        a = np.sort(np.asarray(p["rewards"], dtype=float))
        if a.size:
            ax1.step(a, np.arange(1, a.size + 1) / a.size, where="post",
                     color=colours.get(arm, None),
                     label=f"{arm} (n={a.size})")
    ceil = next(iter(pools.values()))["reward_ceiling"] if pools else None
    if ceil is not None:
        ax1.axvline(ceil, ls="--", lw=1.0, color="k")
        ax1.text(ceil, 0.05, f"  ceiling {ceil:.6f} (G74)", fontsize=8,
                 rotation=90, va="bottom")
    ax1.set_xlabel("reward (v1, 7 specs)")
    ax1.set_ylabel("empirical CDF over simulated designs")
    ax1.set_title("The reward distribution, TT / cl_mid")
    ax1.grid(alpha=0.3)
    ax1.legend(loc="center left", fontsize=8)

    for arm, rr in restarts.items():
        budget = rr[0]["budget_sims"]
        v = sorted(r["sims_to_ceiling"] for r in rr
                   if r["sims_to_ceiling"] is not None)
        n = len(rr)
        if v:
            ax2.step(v, np.arange(1, len(v) + 1) / n, where="post",
                     color=colours.get(arm, None),
                     label=f"{arm}: {len(v)}/{n} reached")
        else:
            ax2.plot([], [], color=colours.get(arm, None),
                     label=f"{arm}: 0/{n} reached")
        ax2.axvline(budget, ls=":", lw=1.0, color="grey")
    for x, lab in ((DECISION_LO, "rule: < 50"), (DECISION_HI, "rule: > 500")):
        ax2.axvline(x, ls="--", lw=1.0, color="k")
        ax2.text(x, 0.02, f"  {lab}", fontsize=8, rotation=90, va="bottom")
    ax2.set_xscale("log")
    ax2.set_xlabel("simulations spent (log)")
    ax2.set_ylabel("fraction of restarts that reached the ceiling")
    ax2.set_ylim(0.0, 1.02)
    ax2.set_title("Simulations to the +8.950669 ceiling")
    ax2.grid(alpha=0.3)
    ax2.legend(loc="lower right", fontsize=8)

    fig.suptitle("Task 0 -- how hard is the nominal problem? "
                 "(LHS, TT/1.00/27C/cl_mid, drawn passives, reward v1)")
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return Path(path)


def probe(n: int = 25, arm: str = "unscreened") -> dict:
    """A cost probe. Reports s/sim so a budget is sized from measurement."""
    r = run_restart(arm, 999, budget_sims=n, stop_at_ceiling=False)
    r["sec_per_sim"] = r["wall_s"] / r["n_sims"] if r["n_sims"] else None
    return r


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--probe", type=int, nargs="?", const=25, default=None,
                    help="cost probe: N simulations, no analysis")
    ap.add_argument("--run", action="store_true", help="the experiment")
    ap.add_argument("--restarts", type=int, default=RESTARTS)
    ap.add_argument("--budget", type=int, default=BUDGET_SIMS)
    ap.add_argument("--pool", type=int, default=POOL_SIMS)
    ap.add_argument("--arms", nargs="+", default=list(ARMS))
    ap.add_argument("--log", type=Path, default=LOG_PATH)
    ap.add_argument("--analyse", type=Path, default=None)
    ap.add_argument("--plot", type=Path, nargs="?", const=LOG_PATH, default=None)
    ap.add_argument("--more-pools", type=int, default=None, metavar="REPLICATE",
                    help="G89: another pooled sample per arm, at a fresh seed")
    ap.add_argument("--ratio", type=Path, nargs="*", default=None,
                    help="G89: pool the ceiling counts across logs")
    a = ap.parse_args(argv)

    if a.probe is not None:
        r = probe(a.probe)
        print(f"probe: {r['n_sims']} sims in {r['wall_s']:.2f} s "
              f"= {r['sec_per_sim']:.4f} s/sim (SERIAL)")
        print(f"  best_reward {r['best_reward']}  ceiling {r['reward_ceiling']:.6f}")
        print(f"  invalid {r['invalid_rate'] * 100:.1f} % {r['invalid_reasons']}")
        return 0

    if a.analyse is not None:
        out = analyse(load(a.analyse))
        print_report(out)
        return 0

    if a.plot is not None:
        p = plot(load(a.plot))
        print(f"wrote {p}")
        return 0

    if a.more_pools is not None:
        out = run_more_pools(pool_sims=a.pool, replicate=a.more_pools,
                             arms=tuple(a.arms))
        print(f"\nwrote {out['log']}")
        return 0

    if a.ratio is not None:
        pools = [r for f in (a.ratio or [LOG_PATH]) for r in load(Path(f))
                 if r.get("kind") == "pool"]
        rr = ceiling_rate_ratio(pools)
        print("\nG89 -- does the pre-screen discard CEILING-capable designs?")
        print(f"  pooled over {len(pools)} pool rows")
        if rr.get("ratio") is None:
            print(f"  UNDEFINED: {rr['note']}")
            return 0
        print(f"  unscreened {rr['n_unscreened_events']}/"
              f"{rr['n_unscreened_proposals']} proposals = "
              f"{rr['rate_unscreened']*100:.4f} %")
        print(f"  screened   {rr['n_screened_events']}/"
              f"{rr['n_screened_proposals']} proposals = "
              f"{rr['rate_screened']*100:.4f} %")
        lo, hi = rr["ci95"]
        flo, fhi = rr["implied_false_rejection_ci95"]
        print(f"  rate ratio {rr['ratio']:.3f}  95% CI [{lo:.3f}, {hi:.3f}]")
        print(f"  implied false rejection on the ceiling population "
              f"{rr['implied_false_rejection']*100:.1f} % "
              f"[{flo*100:.1f}, {fhi*100:.1f}] %")
        print(f"  CI excludes 1.0: {rr['excludes_one']}  -> "
              f"{'CONFIRMED' if rr['excludes_one'] and rr['ratio'] < 1 else 'NOT ESTABLISHED'}")
        return 0

    if a.run:
        out = run(restarts=a.restarts, budget_sims=a.budget, pool_sims=a.pool,
                  arms=tuple(a.arms), log_path=a.log)
        print_report(out)
        p = plot(load(a.log))
        print(f"\nwrote {p}")
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
