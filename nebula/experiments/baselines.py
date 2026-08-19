"""
experiments/baselines.py — task 7. **The benchmark the final claim rests on.**

    "The comparison is the result. A win claim without a tuned baseline will
     not survive the panel."

WHAT THIS FILE IS, IN ONE PARAGRAPH
------------------------------------
Six search methods -- uniform random, Latin hypercube, GRID, CMA-ES, GP-BO and
PPO -- run against ONE evaluator, ONE scalar objective and ONE geometry
mapping, on a LADDER of problems, with every simulation counted and every seed
recorded. It answers "how many SPICE calls does each method need"
rather than "which method wins", because at this sample size the second
question is usually not answerable and saying so is part of the deliverable.

WHY A LADDER AND NOT ONE PROBLEM (7b)
--------------------------------------
The robust problem may be **infeasible**. Session 12b's load-range screen left
**1 design in 1890**, and session 17's 4d regression (G66) moves `f_peak` by
0.1329 octaves against the 0.12 octaves of centring slack that selected that
one design — so it may leave none. *A benchmark on an infeasible problem
measures nothing*: every method scores "never found one" and the comparison is
empty. So there are rungs, and all of them are reported:

    P1  TT only, cl = cl_mid                       ~13.5 % base rate
    P2  3 screen corners, cl = cl_mid              ~8 %
    P3  3 screen corners x {cl_lo, cl_hi}          possibly EMPTY
    P4  the tunable formulation                    seam only — see TUNABLE_SEAM

The anytime metric (7c) is defined on every rung whether or not anything
feasible exists, which is exactly why it is the primary metric.

FAIRNESS, ENFORCED IN CODE AND NOT IN A PARAGRAPH (7f)
-------------------------------------------------------
Every rule below is a property of this module, not a promise:

* **Every simulation is counted, including invalid ones.** `Objective` charges
  `EvalResult.n_spice` — which already includes retries (`evaluator` counts
  them) — and a method's loop terminates on the SIMULATION count, never on an
  evaluation count. An optimiser that wanders into the invalid region pays for
  it. The measured invalid rate was 10.5 % over a uniform box sample and 26.5 %
  over session 17's policy trajectory, and it is reported per method because a
  method that finds more invalid regions than another is telling you something.
* **Identical validity handling.** Every method goes through
  `rl.evaluator.evaluate` and `rl.reward_v1.reward`; the G72 bands are
  unchanged and nothing here reimplements a spec test.
* **Identical box and geometry mapping.** `rl.contract.sizing_from_u`, which
  draws real SKY130 passives, for every method including the designer row's
  re-evaluation.
* **Identical seed protocol.** One integer per (method, problem, replicate),
  derived by a stated rule from `BASE_SEED`, recorded on every logged row.
* **Same worker count everywhere.** `WORKERS = 8`, per session 17's measured
  2.98x — 11 workers is SLOWER than 8 on this library.
* **The evaluator commit is pinned in every artifact.** `provenance()` reads it
  from git and it goes in the run-log header; an artifact that cannot say which
  evaluator produced it is not re-runnable.

THE TWO THINGS THAT ARE NOT SYMMETRIC, STATED RATHER THAN HIDDEN
------------------------------------------------------------------
1. **PPO runs on P1 only.** `CtleSizingEnv` takes ONE corner and ONE load, so a
   worst-over-corners environment does not exist yet. Building one is a task,
   not a flag, and inventing a different corner treatment for one method would
   make the comparison about corner handling rather than about search.
2. **The designer row is a reconstruction, not a run.** Session 9c's
   hand-sizing is quoted from the session log with its own uncertainty, and it
   is on a strictly easier problem than P1 (ideal passives, ideal tail, no
   `cl_mid`, S3 only). It is reported because it is the number the judges have
   in their heads, and putting a number on it is more honest than leaving it
   implicit — not because it is commensurable.

USAGE
    python -m nebula.experiments.baselines --budget            # 7a, no SPICE
    python -m nebula.experiments.baselines --prescreen         # 7e, no SPICE
    python -m nebula.experiments.baselines --pilot             # small, real
    python -m nebula.experiments.baselines --sweep             # the 12 h run
    python -m nebula.experiments.baselines --analyse FILE.jsonl

WHY THERE IS A GRID ARM AT ALL (added 2026-08-19)
--------------------------------------------------
`CLAUDEwa.md` sec 7 states G3's criterion as *"RL beats random search AND grid
search at TT, with a plot"*, and until this was written the file held no grid
search -- so G3 could not be SCORED, let alone passed. The competition's own
problem statement is a sentence about grid search (*"significantly lower time
than sweeping all MOS, R, C, L parameter space"*), which makes this the one
baseline a judge is guaranteed to ask about. See `method_grid` and
`grid_levels`; the short version is that 150 simulations in 7 dimensions buys
150 ** (1/7) = 2.06 levels per axis, and that arithmetic is the result.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import subprocess
import sys
import time
import dataclasses
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Sequence

import numpy as np

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.experiments import prescreen as PS
from nebula.experiments.cl_range import committed_cl_range
from nebula.experiments.s9_yield import SCREEN_CORNERS
from nebula.rl import reward_v1 as R
from nebula.rl.contract import (
    ACTION_NAMES,
    ACTION_SPACE,
    CL_CONTEXT_F,
    N_ACTIONS,
    Sizing,
    sizing_from_u,
)
from nebula.rl.evaluator import (
    EvalResult,
    SpiceBudget,
    Verdict,
    evaluate,
    interp_was_refused,
    scoring_meas,
)
from nebula.rl.runlog import RunLog
from nebula.rl.runlog import read as runlog_read

HERE = Path(__file__).resolve().parent

# ─────────────────────────────────────────────────────────────────────────────
# 7f — the fairness constants. One definition each (rule 9).
# ─────────────────────────────────────────────────────────────────────────────

#: Session 17 §6i, measured with a warm-up and a control: 1 / 2 / 4 / 8 / 11
#: workers give 3999 / 2007 / 1628 / **1341** / 1548 ms per task, i.e. **2.98x
#: at 8 and 11 SLOWER than 8**. Same everywhere, per 7f.
WORKERS: int = 8

#: Measured cost per simulation, both numbers, because they disagree by 1.9x
#: and the disagreement is itself a finding:
#:
#:   * **2.07 s** — session 17's 500-step PPO run, 793 SPICE calls in 1585.8 s
#:     of environment time. Points on a POLICY TRAJECTORY.
#:   * **4.00 s** — session 17 §6i's 1-worker pass over 24 UNIFORM box draws.
#:
#: The benchmark's own task set is uniform box draws, so the budget arithmetic
#: uses the SECOND and the first is quoted as the optimistic bracket. Using the
#: cheaper number would size a 12-hour run that takes 23 hours.
SEC_PER_SIM_TRAJECTORY: float = 2.071
SEC_PER_SIM_UNIFORM: float = 3.999
#: Wall seconds per simulation at `WORKERS`, measured directly (not divided).
#:
#: **REVISED 2026-08-19, and this is the third value this constant has held.**
#: The first two were both PREDICTIONS of a run that had not happened; this one
#: is the run. `sweep()` timed itself end to end (`wall_s` is
#: `perf_counter()` around the whole pool, warm-up and control included) and
#: the answer is on disk in `baselines_results_interp.json`:
#:
#:     2528.055 s elapsed / 25 869 simulations  =  0.09773 s/sim
#:
#: **That is 17.4x cheaper than the 1.698 this constant held**, and the reason
#: is not a mistake in the old measurement: the 33-run pilot it came from
#: predates the library trims (G36 and the extended-library trim), and a
#: constant measured before the thing that made it stale is simply old. The
#: consequence is stated plainly in `CONTINUE_HERE.md` §3.2 -- the sweep 7a
#: sized at 12 hours took **42.1 minutes** -- and the same arithmetic now says
#: the FULLY CROSSED design costs ~2 h, so the cuts in `default_allocation()`
#: are no longer forced by cost. See that function's docstring.
#:
#: **What did NOT change: the simulation counts.** 7g asks for simulations as
#: the headline precisely so that a stale wall-clock constant can only mis-size
#: a run, never mis-rank a method.
SEC_PER_SIM_AT_8: float = 0.09773

#: The same measurement on the LATTICE control sweep -- same 170 runs, same
#: seeds, one flag off: 2869.637 s / 25 866 sims. It did strictly LESS work
#: and took **13.5 % longer**, which is why these two bracket the estimate
#: instead of one of them being "the" rate: the spread between two runs of the
#: same allocation on the same machine is larger than anything the objective
#: costs. `budget_report` quotes the slower one as pessimistic.
SEC_PER_SIM_AT_8_LATTICE: float = 0.11095

#: The pilot's value, kept because `BASELINES.md` §1 quotes it and because a
#: constant that changed by 17x should show its history rather than its last
#: state. 33 benchmark runs, 1992 simulations, single process 3.060 s/sim over
#: 8-worker aggregate 1.698 s/sim.
SEC_PER_SIM_AT_8_PILOT: float = 1.698

#: Measured on those same 33 runs: single-process 3.060 s/sim over 8-worker
#: aggregate 1.698 s/sim. Session 17's 2.98x stands for ITS task set and does
#: not transfer to this one; both are quoted in `BASELINES.md` §1.
#:
#: **Not re-derived from the sweep, deliberately.** The sweep's only
#: single-process rows are its warm-up and its control, which are ONE
#: configuration (`P1/uniform+screen`) rather than the task mix, and G94 is
#: exactly the trap of reading a per-simulation rate off a fraction of the
#: workload. The sweep's own warm-up/pool ratio is 1.90x and is reported as
#: what it is -- one configuration -- not promoted to a mix measurement.
SPEEDUP_AT_8: float = 1.802

#: Session 17 §6i, on 24 isolated evaluations. Kept because `BASELINES.md`
#: quotes both and the difference between them is the point.
SEC_PER_SIM_AT_8_SESSION_17: float = 1.341
SPEEDUP_AT_8_SESSION_17: float = 2.982

#: The seed protocol. Every run's seed is `BASE_SEED + PROBLEM_OFFSET[problem]
#: + METHOD_OFFSET[method] + replicate`, so a seed identifies its run and two
#: methods never share a random stream by accident.
BASE_SEED: int = 20260807

PROBLEM_OFFSET: dict[str, int] = {"P1": 0, "P2": 100_000, "P3": 200_000,
                                  "P4": 300_000}
METHOD_OFFSET: dict[str, int] = {"uniform": 0, "lhs": 1_000, "cmaes": 2_000,
                                 "gp_bo": 3_000, "ppo": 4_000, "grid": 5_000}


def run_seed(problem: str, method: str, replicate: int) -> int:
    """The stated rule. Recorded on every row so a run is re-derivable."""
    if problem not in PROBLEM_OFFSET:
        raise KeyError(f"unknown problem {problem!r}")
    if method not in METHOD_OFFSET:
        raise KeyError(f"unknown method {method!r}")
    return BASE_SEED + PROBLEM_OFFSET[problem] + METHOD_OFFSET[method] + int(replicate)


def provenance() -> dict:
    """What produced this artifact. Goes in every run log's header row.

    The evaluator commit is 7f's last rule: the bounds proposal is still not in
    `params.py` (HANDOFF §8), so the benchmark has to RECORD what it ran
    against and be re-runnable when that decision is made.
    """
    def _git(*args: str) -> Optional[str]:
        try:
            return subprocess.run(("git", *args), cwd=HERE.parents[1],
                                  capture_output=True, text=True,
                                  timeout=15).stdout.strip() or None
        except (OSError, subprocess.SubprocessError):        # pragma: no cover
            return None

    from nebula.device.sky130_runner import CTLE_LIB

    return {
        "commit": _git("rev-parse", "HEAD"),
        "commit_short": _git("rev-parse", "--short", "HEAD"),
        "dirty": bool(_git("status", "--porcelain")),
        "box": [{"name": d.name, "lo": d.lo, "hi": d.hi, "log": d.log,
                 "unit": d.unit} for d in ACTION_SPACE],
        "box_source": "rl.contract.ACTION_SPACE (= s3_yield.PROPOSED_BOX); "
                      "common/params.py::BOUNDS is UNTOUCHED (CLAUDEwa.md "
                      "§8 rule 6) and is NOT what this ran against",
        "specs": list(R.V1_SPECS),
        "tolerances": {t.name: {"value": t.value, "unit": t.unit}
                       for t in R.TOLERANCES},
        "library": CTLE_LIB.name,
        "prescreen": {"k_alpha": PS.K_ALPHA, "margin_oct": PS.MARGIN_OCT,
                      "margin_db": PS.MARGIN_DB,
                      "gm_beta": list(PS.GM_LOG_BETA)},
        "workers": WORKERS,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7b — the problem ladder.
# ─────────────────────────────────────────────────────────────────────────────

_CL = committed_cl_range()


@dataclass(frozen=True)
class EvalPoint:
    """One (corner, load) the design must survive. `cl` is CONTEXT, not action."""

    label: str
    corner: str
    vdd_scale: float
    temp_c: float
    cl_f: float


@dataclass(frozen=True)
class Problem:
    """One rung. `points` is evaluated in order; the score is the WORST.

    Worst-case-over-corners is CLAUDEwa.md §12's first named trap read the
    right way round: *"optimising at nominal and checking corners afterwards —
    score on worst corner from the start."*
    """

    name: str
    points: tuple[EvalPoint, ...]
    note: str
    #: Simulations one fully-evaluated design costs. The BUDGET is in
    #: simulations, so this is what converts a budget into designs.
    @property
    def sims_per_design(self) -> int:
        return len(self.points)


_NOMINAL = EvalPoint("tt/1.00/27C/cl_mid", "tt", 1.00, 27.0, _CL.cl_mid_f)


def _corner_points(loads: Sequence[float]) -> tuple[EvalPoint, ...]:
    out = []
    for cl in loads:
        for c in SCREEN_CORNERS:
            out.append(EvalPoint(
                f"{c.process}/{c.vdd_scale:.2f}/{c.temp_c:.0f}C/"
                f"cl={cl * 1e15:.1f}fF",
                c.process, float(c.vdd_scale), float(c.temp_c), float(cl)))
    return tuple(out)


PROBLEMS: dict[str, Problem] = {
    "P1": Problem(
        "P1", (_NOMINAL,),
        "TT only, cl = cl_mid. The SANITY rung: every method must solve this "
        "quickly, and a method that does not is broken rather than weak. "
        "Measured S3 base rate 13.49 % (session 10d, at the legacy 150 fF pin) "
        "and 13.44 % on the calibration population used by the pre-screen."),
    "P2": Problem(
        "P2", _corner_points((_CL.cl_mid_f,)),
        "3 screen corners at cl = cl_mid. Session 10d measured 3 corners worth "
        "98.7 % of 45 (G47), and the corner tax at the legacy pin was 39 % of "
        "the nominal winners -> ~8 %."),
    "P3": Problem(
        "P3", _corner_points((_CL.cl_lo_f, _CL.cl_hi_f)),
        "3 screen corners x {cl_lo, cl_hi} — THE ROBUST PROBLEM, and possibly "
        "EMPTY. Session 12b: 1 design in 1890 with IDEAL passives; G66 then "
        "measured drawn passives moving f_peak by 0.1329 octaves against that "
        "design's 0.12 octaves of centring slack. Run it anyway: the anytime "
        "metric stays defined and 'no method found one' is a result."),
}

#: 7b's P4. **A seam, declared, not a stub that pretends.**
#:
#: The tunable formulation is: the optimiser fixes the geometry, and an INNER
#: search solves `(rs, cs)` per (corner, load). The machinery for the inner
#: search exists — `experiments/tunable.py` runs a whole `(rs, cs)` grid inside
#: ONE ngspice process via `alter` on the IDEAL R and C elements, at 13.6 ms
#: per setting against ~150 ms for a process each.
#:
#: **It has not landed for this benchmark, and the blocker is not effort.**
#: `tunable.py`'s speed comes from `alter` on ideal elements, and G63 is
#: exactly the trap that creates: with DRAWN passives there is no `Rs` element
#: to alter, `alter` fails silently, and all 67 sweep settings return the FIRST
#: geometry's numbers and exit 0. So the tunable rung needs either drawn-
#: passive re-parses (which removes the 11x that makes it affordable) or a
#: proof that the ideal-element inner search transfers. Neither is done.
#:
#: The seam: add a `Problem` whose `points` carry an inner-search callable, and
#: an `inner_search` on `Objective.evaluate`. Nothing else in this file changes
#: — the budget, the metrics and the statistics are all in simulations.
TUNABLE_SEAM: str = (
    "P4 (tunable) NOT RUN. Inner (rs, cs) search per (corner, load) needs "
    "either drawn-passive re-parses or a proof that tunable.py's ideal-element "
    "`alter` path transfers to drawn passives (G63). See TUNABLE_SEAM."
)


# ─────────────────────────────────────────────────────────────────────────────
# The objective: one design -> one scalar, with every simulation charged.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Trial:
    """One design proposal and everything the analysis and 7j's log need."""

    index: int
    u: list
    design_id: Optional[str]
    geometry_tag: Optional[str]
    params: dict
    reward: float
    feasible: bool
    #: Worst point's verdict — "valid" | "headroom_only" | "invalid".
    verdict: str
    invalid_reason: Optional[str]
    worst_point: Optional[str]
    worst_spec: Optional[str]
    n_sims: int
    seconds: float
    cum_sims: int
    cum_seconds: float
    #: True when the pre-screen rejected it, so NO simulation was spent.
    screened_out: bool
    screen_reason: Optional[str]
    #: The nominal point's measurement, when there is one. Free training data
    #: for task 8's surrogate (7j), which is why the sweep is worth keeping.
    meas: Optional[dict]
    margins: Optional[dict]
    predicted: Optional[dict]


class BudgetExhausted(RuntimeError):
    """Raised inside a method's inner loop when the simulation budget is gone.

    An exception rather than a flag because PPO's `train()` owns its own loop
    and cannot be asked politely to stop mid-rollout. Every method catches it.
    """


class Objective:
    """The single scored function every method optimises. **Maximise.**

    One definition of the score, and every method imports it rather than
    building its own — which is 7d's requirement that the comparison be about
    SEARCH and not about objective formulation. CMA-ES and BO are unconstrained
    optimisers and they get exactly this scalar, with the four reward-v1 bands
    doing the constraint handling.
    """

    def __init__(self, problem: Problem, budget_sims: int,
                 prescreen: bool = False,
                 target_f_peak_hz: Optional[float] = None,
                 target_peaking_db: Optional[float] = None,
                 specs: Sequence[str] = R.V1_SPECS,
                 on_trial: Optional[Callable[[Trial], None]] = None,
                 spice: Optional[SpiceBudget] = None,
                 ac_peak_interp: bool = False):
        self.problem = problem
        self.budget_sims = int(budget_sims)
        self.prescreen = bool(prescreen)
        self.specs = tuple(specs)
        # ADDITIVE AND DEFAULT OFF (session 22c, G74). When on, `evaluate` puts
        # the sub-grid peak into `meas` under NEW keys and leaves the lattice
        # ones alone, so `_score_one` below scores exactly what it always did
        # and `Trial.reward` is bit-identical either way. A caller wanting the
        # interpolated objective re-scores `Trial.meas` through
        # `evaluator.meas_with_interpolated_peak`; nothing here does it for it,
        # because `Objective.ceiling` is a LATTICE quantity and would be wrong.
        self.ac_peak_interp = bool(ac_peak_interp)
        #: How often the sub-grid peak was asked for and refused (G93). Counted
        #: rather than assumed rare: `scoring_meas` falls back to the lattice
        #: value there, and a fallback nobody counts is indistinguishable from
        #: a fallback that never fires.
        self.n_interp_refused = 0
        # The same target the RL smoke run used: the geometric centre of S3's
        # octave and the arithmetic centre of its dB band. Mid-window in BOTH
        # axes, so the benchmark does not become a measurement of one edge.
        self.target_f_peak_hz = float(
            target_f_peak_hz if target_f_peak_hz is not None
            else math.sqrt(SPEC_F_PEAK_HZ_RANGE[0] * SPEC_F_PEAK_HZ_RANGE[1]))
        self.target_peaking_db = float(
            target_peaking_db if target_peaking_db is not None
            else sum(SPEC_PEAKING_DB_RANGE) / 2.0)
        self.on_trial = on_trial
        self.spice = spice if spice is not None else SpiceBudget()

        self.trials: list[Trial] = []
        self.n_sims = 0
        self.n_seconds = 0.0
        self.n_screened_out = 0
        self.n_zero_sim = 0
        self.invalid_reasons: dict[str, int] = {}

    # -- budget ---------------------------------------------------------------

    @property
    def exhausted(self) -> bool:
        return self.n_sims >= self.budget_sims

    def check_budget(self) -> None:
        if self.exhausted:
            raise BudgetExhausted(
                f"{self.n_sims}/{self.budget_sims} simulations spent")

    @property
    def floor(self) -> float:
        """The invalid reward. The global minimum of the four bands."""
        return R.invalid_reward(len(self.specs))

    @property
    def ceiling(self) -> float:
        """The best score the AC sweep grid permits. See `reward_ceiling`."""
        return reward_ceiling(self.target_f_peak_hz, self.specs)

    # -- scoring --------------------------------------------------------------

    def _score_one(self, sizing: Sizing, pt: EvalPoint
                   ) -> tuple[float, R.RewardBreakdown, EvalResult]:
        ev = evaluate(sizing, self.spice, corner=pt.corner,
                      temp_c=pt.temp_c, vdd_scale=pt.vdd_scale,
                      ac_peak_interp=self.ac_peak_interp)
        if interp_was_refused(ev):
            self.n_interp_refused += 1
        rb = R.reward(scoring_meas(ev, self.ac_peak_interp),
                      self.target_f_peak_hz, specs=self.specs,
                      target_peaking_db=self.target_peaking_db,
                      headroom=(ev.headroom
                                if ev.verdict is Verdict.HEADROOM_ONLY else None))
        return rb.reward, rb, ev

    def evaluate(self, u: Sequence[float]) -> Trial:
        """One design -> its worst-case score. Raises `BudgetExhausted` first.

        **The short-circuit is exact, not an approximation.** The score is the
        MINIMUM over points and `invalid_reward` is the global minimum of the
        reward's four bands, so once one point returns the floor no other point
        can lower the result and the remaining simulations would buy nothing.
        Every method gets the same short-circuit, which is what keeps it a
        property of the problem rather than of a method.
        """
        self.check_budget()
        idx = len(self.trials)
        t0 = time.perf_counter()

        # cl is CONTEXT: the design vector does not carry it, so the sizing is
        # rebuilt per point. `sizing_from_u` is THE geometry mapping (7f).
        u = [float(x) for x in np.clip(np.asarray(u, dtype=float).ravel(),
                                       0.0, 1.0)]
        if len(u) != N_ACTIONS:
            raise ValueError(f"expected {N_ACTIONS} coordinates, got {len(u)}")

        head = sizing_from_u(u, cl_f=self.problem.points[0].cl_f)
        pred = PS.predict_response(head.params)
        pred_d = {"f_peak_hz": pred.f_peak_hz, "peaking_db": pred.peaking_db,
                  "nyq_boost_db": pred.nyq_boost_db, "f_zero_hz": pred.f_zero_hz,
                  "f_pole2_hz": pred.f_pole2_hz, "gm_s": pred.gm_s}

        if self.prescreen:
            v = PS.screen(head.params, target_f_peak_hz=self.target_f_peak_hz)
            if not v.accept:
                self.n_screened_out += 1
                tr = Trial(index=idx, u=u, design_id=None, geometry_tag=None,
                           params=dict(head.params), reward=self.floor,
                           feasible=False, verdict="screened",
                           invalid_reason=None, worst_point=None,
                           worst_spec=None, n_sims=0,
                           seconds=time.perf_counter() - t0,
                           cum_sims=self.n_sims, cum_seconds=self.n_seconds,
                           screened_out=True, screen_reason=v.reason,
                           meas=None, margins=None, predicted=pred_d)
                self._emit(tr)
                return tr

        worst = math.inf
        worst_rb: Optional[R.RewardBreakdown] = None
        worst_ev: Optional[EvalResult] = None
        worst_label: Optional[str] = None
        n_sims = 0
        nominal_meas: Optional[dict] = None
        for pt in self.problem.points:
            sizing = sizing_from_u(u, cl_f=pt.cl_f)
            r, rb, ev = self._score_one(sizing, pt)
            n_sims += ev.n_spice
            if nominal_meas is None and ev.meas is not None:
                nominal_meas = dict(ev.meas)
            if r < worst:
                worst, worst_rb, worst_ev, worst_label = r, rb, ev, pt.label
            if r <= self.floor:
                break                       # exact: nothing can go lower

        assert worst_rb is not None and worst_ev is not None
        dt = time.perf_counter() - t0
        self.n_sims += n_sims
        self.n_seconds += dt
        if n_sims == 0:
            self.n_zero_sim += 1
        if not worst_ev.valid and worst_ev.verdict is Verdict.INVALID:
            key = _classify_invalid(worst_ev.reason or "")
            self.invalid_reasons[key] = self.invalid_reasons.get(key, 0) + 1

        tr = Trial(index=idx, u=u, design_id=worst_ev.design_id,
                   geometry_tag=worst_ev.geometry_tag,
                   params=dict(head.params), reward=float(worst),
                   feasible=bool(worst_rb.feasible),
                   verdict=worst_ev.verdict.value,
                   invalid_reason=worst_ev.reason, worst_point=worst_label,
                   worst_spec=worst_rb.worst_spec, n_sims=n_sims, seconds=dt,
                   cum_sims=self.n_sims, cum_seconds=self.n_seconds,
                   screened_out=False, screen_reason=None,
                   meas=nominal_meas,
                   margins=(dict(worst_rb.margins) if worst_rb.margins else None),
                   predicted=pred_d)
        self._emit(tr)
        return tr

    def _emit(self, tr: Trial) -> None:
        self.trials.append(tr)
        if self.on_trial is not None:
            self.on_trial(tr)

    # -- reporting ------------------------------------------------------------

    @property
    def simulated(self) -> list[Trial]:
        """Trials that actually cost a simulation — the anytime curve's domain."""
        return [t for t in self.trials if t.n_sims > 0]

    @property
    def best(self) -> float:
        s = self.simulated
        return max((t.reward for t in s), default=float("-inf"))

    @property
    def invalid_rate(self) -> float:
        s = self.simulated
        n = sum(1 for t in s if t.verdict == "invalid")
        return n / len(s) if s else 0.0

    def summary(self) -> dict:
        s = self.simulated
        first = next((t for t in s if t.feasible), None)
        return {
            "problem": self.problem.name,
            "budget_sims": self.budget_sims,
            "n_sims": self.n_sims,
            "n_trials": len(self.trials),
            "n_simulated": len(s),
            "n_screened_out": self.n_screened_out,
            "n_zero_sim": self.n_zero_sim,
            "wall_s": self.n_seconds,
            "best_reward": self.best if s else None,
            "n_feasible": sum(1 for t in s if t.feasible),
            "sims_to_first_feasible": (first.cum_sims if first else None),
            "censored": first is None,
            "reward_ceiling": self.ceiling,
            "sims_to_ceiling": sims_to_ceiling(self.trials, self.ceiling),
            "ac_peak_interp": self.ac_peak_interp,
            "n_interp_refused": self.n_interp_refused,
            "invalid_rate": self.invalid_rate,
            "invalid_reasons": dict(self.invalid_reasons),
        }


def _classify_invalid(reason: str) -> str:
    """The same buckets `rl.env.CtleSizingEnv._classify` uses. One taxonomy."""
    r = reason.lower()
    for key, needle in (
        ("unrealisable_geometry", "unrealisable geometry"),
        ("peak_is_sweep_edge", "peak is the sweep edge"),
        ("outside_rails", "outside the rails"),
        ("f_peak_range", "f_pk ="),
        ("gain_range", "not an amplifier"),
        ("noise_range", "integration collapsed"),
        ("supply_range", "i_supply ="),
        ("ngspice", "ngspice:"),
    ):
        if needle in r:
            return key
    return "other"


# ─────────────────────────────────────────────────────────────────────────────
# 7d — the methods. Each is `run(objective, rng)` and loops until the budget
# raises. None of them sees a spec, a corner or a geometry: only the scalar.
# ─────────────────────────────────────────────────────────────────────────────


def method_uniform(obj: Objective, rng: np.random.Generator) -> dict:
    """Uniform random inside the box — **the reference rate**.

    Not a straw man: G42 measured that removing `cl` from the search RAISES the
    random-search yield from 8.73 % to 13.54 %, which made the baseline RL has
    to beat HARDER, and HANDOFF records that as a result rather than hiding it.
    """
    while True:
        obj.check_budget()
        obj.evaluate(rng.uniform(0.0, 1.0, N_ACTIONS))


def _lhs(n: int, d: int, rng: np.random.Generator) -> np.ndarray:
    """Centred Latin hypercube, one independent permutation per dimension."""
    cut = (np.arange(n) + 0.5) / n
    return np.column_stack([rng.permutation(cut) for _ in range(d)])


def method_lhs(obj: Objective, rng: np.random.Generator) -> dict:
    """Latin hypercube — cheap, and often beats uniform enough to matter.

    The block size is the number of designs the budget buys, so ONE hypercube
    covers the run. If the budget outlives it (short-circuited designs cost
    fewer simulations than the worst case) a fresh independent hypercube
    follows, which is the honest continuation: extending a hypercube in place
    is not a hypercube.
    """
    d = N_ACTIONS
    while True:
        obj.check_budget()
        n = max(2, math.ceil((obj.budget_sims - obj.n_sims)
                             / obj.problem.sims_per_design))
        for row in _lhs(n, d, rng):
            obj.check_budget()
            obj.evaluate(row)


#: The most levels per axis `method_grid` will refine to before it gives up.
#: **A guard, not a tuning knob.** Six levels in seven dimensions is 279 936
#: points, four orders of magnitude past anything a 150-simulation budget can
#: reach, so arriving here means the budget is not being SPENT -- every design
#: screened out for free, or an evaluator returning `n_spice = 0` -- and that
#: is a condition to raise on, not to absorb. (`method_uniform` would spin
#: forever on the same condition and say nothing; the grid is finite per level,
#: so it is the one method that can name it.)
GRID_MAX_LEVELS: int = 6


def grid_levels(n_designs: int, d: int = N_ACTIONS) -> int:
    """Largest `L` with `L**d <= n_designs`. **This function is the finding.**

    Grid search does not have a step size you choose; it has one the budget
    chooses for you, and in seven dimensions that arithmetic is brutal:

        150 simulations, d = 7   ->   150 ** (1/7) = 2.06 levels per axis
        L = 2   ->    128 points   fits
        L = 3   ->  2 187 points   14.6x the budget

    So on P1 the benchmark's grid arm is a **two-level** factorial and there is
    no version of this method at this budget that is finer. That is not a
    handicap we imposed; it is what "sweep the parameter space" costs at d = 7,
    and it is the sentence the competition's own problem statement is about:
    *"should take significantly lower time than sweeping all MOS, R, C, L
    parameter space"*. The row exists to put a number on the thing we are
    asked to beat.

    Returns 1 -- the single box centre -- when not even a two-level factorial
    fits, which is what happens on P3 (150 / 6 = 25 designs).
    """
    if d < 1:
        raise ValueError(f"d must be >= 1, got {d}")
    if n_designs < 1:
        raise ValueError(f"n_designs must be >= 1, got {n_designs}")
    L = 1
    while (L + 1) ** d <= n_designs:
        L += 1
    return L


def _factorial(levels: int, d: int, rng: np.random.Generator) -> np.ndarray:
    """The centred full factorial at `levels` per axis, in a SHUFFLED order.

    **Centred**, at `(i + 0.5) / L`, for the same reason `_lhs` centres its
    cuts: an endpoint-inclusive grid at L = 2 is exactly the 128 corners of the
    box, which is a straw man rather than a baseline. Centring also makes the
    two low-tech methods differ in their POINT PATTERN and in nothing else.

    **Shuffled**, because the budget truncates. A lexicographic prefix of a
    factorial varies only the last coordinates and holds the first ones at a
    single value, so a truncated grid enumerated in order would be a
    measurement of the enumeration order rather than of the method. The
    shuffle is drawn from the run's own `rng`, so it is seeded and recorded
    like everything else here.
    """
    cut = (np.arange(levels) + 0.5) / levels
    g = np.stack(np.meshgrid(*([cut] * d), indexing="ij"), axis=-1)
    g = g.reshape(-1, d)
    return g[rng.permutation(len(g))]


def grid_level_of(u: Sequence[float], max_levels: int = GRID_MAX_LEVELS
                  ) -> Optional[int]:
    """Which factorial a logged point came from, recovered from `u` alone.

    The run log stores `u` and nothing about the grid, so this is how a
    write-up checks a claim like "the screened arm reached the three-level
    grid" against the artifact instead of against the code that wrote it.

    Returns the SMALLEST `L` whose centred lattice contains every coordinate,
    because the lattices nest -- L = 2's points are a subset of L = 6's -- and
    the smallest is the one the enumeration actually reached. `None` for a
    point on no lattice up to `max_levels`, which is what every non-grid
    method's rows return.
    """
    u = np.asarray(u, dtype=float).ravel()
    for L in range(1, int(max_levels) + 1):
        cut = (np.arange(L) + 0.5) / L
        if all(bool(np.any(np.isclose(x, cut, rtol=0.0, atol=1e-9)))
               for x in u):
            return L
    return None


def method_grid(obj: Objective, rng: np.random.Generator) -> dict:
    """Full-factorial grid search, sized to the budget, then refined.

    **The method the competition's problem statement names as the thing to
    beat**, and until now the one baseline `CLAUDEwa.md` sec 7's G3 criterion
    asks for that this file did not have. `python_models/statistical_eye.py`
    has an `optimize_ctle()` that grids CTLE *settings* inside the link model;
    it does not size devices and it does not see this box, so it is not this.

    The loop:

      1. take the largest complete factorial the budget affords
         (`grid_levels`) and run it, shuffled;
      2. if budget remains -- which happens when designs are short-circuited or
         screened out for free -- refine to `L + 1` and keep going;
      3. never re-evaluate a point already visited. A grid search that
         re-simulates a point it already has is being handicapped by an
         implementation detail rather than by its method -- no human sweeping
         parameters throws away the coarse pass -- so `seen` carries across
         levels.

    **G73 applies to that third item and it is declared rather than assumed.**
    Centred lattices nest only when `M / L` is an odd integer:
    `(i + 0.5)/L = (j + 0.5)/M` needs `(M/L - 1)/2` integral. So L = 2's points
    are NOT inside L = 3, L = 4 or L = 5, and first reappear at **L = 6** --
    which this loop reaches only after enumerating
    128 + 2187 + 16 384 + 78 125 = 96 824 designs. **At a 150-simulation budget
    the de-duplication cannot fire**, and a guard whose condition is
    unreachable is indistinguishable from a deleted one unless somebody says
    so. It is kept because `BUDGET_SIMS` is a constant, not a law, and it is
    named here so nobody reports it as a working defence.

    **What this buys the pre-screened arm, and it is worth watching.** For
    every other method the screen buys *throughput*: rejected proposals cost no
    simulation, so more proposals fit. For the grid it buys *resolution*: the
    two-level factorial is 128 points but only the accepted ones cost anything,
    so the budget can carry the arm into the three-level factorial that the
    unscreened arm cannot reach at all. The screen is the only thing in this
    benchmark that can change a grid's step size.

    Determinism is a property of the method and is reported, not engineered
    away: with the whole factorial affordable, every seed sees the same 128
    points and differs only in the order it sees them, so the spread across
    seeds is a measurement of TRUNCATION, not of search. If the arm's bootstrap
    interval comes back at zero width, that is the answer rather than a bug --
    and it is a different zero from `BASELINES.md` sec 12.6's, which was the
    objective failing to resolve rather than the method having no randomness.
    """
    d = N_ACTIONS
    seen: set[tuple[float, ...]] = set()
    n_designs = max(1, obj.budget_sims // obj.problem.sims_per_design)
    level = grid_levels(n_designs, d)

    while True:
        obj.check_budget()
        if level > GRID_MAX_LEVELS:
            # Rule 10: fail loudly. Reaching here means `budget_sims`
            # simulations were never charged, so the run would otherwise
            # enumerate ever-larger factorials in silence.
            raise RuntimeError(
                f"method_grid exhausted {GRID_MAX_LEVELS} levels "
                f"({GRID_MAX_LEVELS ** d:,} points) without spending its "
                f"{obj.budget_sims}-simulation budget "
                f"({obj.n_sims} spent, {obj.n_screened_out} screened out). "
                "Every design is costing zero simulations -- check the "
                "pre-screen and the evaluator, not this method.")
        for row in _factorial(level, d, rng):
            key = tuple(np.round(row, 12))
            if key in seen:
                continue
            seen.add(key)
            obj.check_budget()
            obj.evaluate(row)
        level += 1


@dataclass
class CmaConfig:
    """Textbook (mu/mu_w, lambda)-CMA-ES defaults. **Nothing here is tuned.**

    Hansen's standard settings, so the row reads "CMA-ES with its published
    defaults" rather than "CMA-ES after we fiddled with it" — which is the
    only version of the comparison a panel will accept from us. `sigma0 = 0.3`
    is the usual choice for a unit box.
    """

    sigma0: float = 0.3
    popsize: Optional[int] = None       # None -> 4 + floor(3 ln d)


def method_cmaes(obj: Objective, rng: np.random.Generator,
                 cfg: Optional[CmaConfig] = None) -> dict:
    """CMA-ES, self-contained. `cma` is not installed in this environment.

    Written out rather than pip-installed for one reason that matters to the
    deliverable: the competition mandates open-source tooling and a reviewer
    can read 70 lines and check they are Hansen's equations. The update below
    is the standard rank-mu + rank-one covariance adaptation with cumulative
    step-size control; the only non-standard line is the box handling, which
    CLIPS into [0,1] and scores the clipped point — the same treatment
    `params.denormalize` gives PPO's Gaussian head.
    """
    cfg = cfg or CmaConfig()
    d = N_ACTIONS
    lam = cfg.popsize or (4 + int(3 * math.log(d)))
    mu = lam // 2
    w = np.log(mu + 0.5) - np.log(np.arange(1, mu + 1))
    w /= w.sum()
    mueff = 1.0 / np.sum(w ** 2)

    cc = (4 + mueff / d) / (d + 4 + 2 * mueff / d)
    cs = (mueff + 2) / (d + mueff + 5)
    c1 = 2 / ((d + 1.3) ** 2 + mueff)
    cmu = min(1 - c1, 2 * (mueff - 2 + 1 / mueff) / ((d + 2) ** 2 + mueff))
    damps = 1 + 2 * max(0.0, math.sqrt((mueff - 1) / (d + 1)) - 1) + cs
    chiN = math.sqrt(d) * (1 - 1 / (4 * d) + 1 / (21 * d * d))

    xmean = rng.uniform(0.0, 1.0, d)
    sigma = cfg.sigma0
    pc = np.zeros(d)
    psig = np.zeros(d)
    C = np.eye(d)
    gen = 0

    while True:
        obj.check_budget()
        # Eigendecomposition every generation: d = 7, so it is free next to a
        # SPICE call and the usual lazy-update optimisation would only add a
        # place to be wrong.
        C = np.triu(C) + np.triu(C, 1).T
        eigval, B = np.linalg.eigh(C)
        eigval = np.maximum(eigval, 1e-20)
        D = np.sqrt(eigval)
        BD = B @ np.diag(D)

        z = rng.standard_normal((lam, d))
        y = z @ BD.T
        X = xmean + sigma * y
        f = np.empty(lam)
        for i in range(lam):
            obj.check_budget()
            f[i] = -obj.evaluate(X[i]).reward        # CMA-ES minimises

        order = np.argsort(f)
        xold = xmean
        # Recombine in the CLIPPED coordinates the objective actually scored,
        # so the distribution follows the points that were measured rather than
        # points outside the box that nothing evaluated.
        Xc = np.clip(X, 0.0, 1.0)
        xmean = w @ Xc[order[:mu]]
        yw = (xmean - xold) / sigma

        psig = (1 - cs) * psig + math.sqrt(cs * (2 - cs) * mueff) * \
            (B @ (np.diag(1.0 / D) @ (B.T @ yw)))
        gen += 1
        hsig = (np.linalg.norm(psig)
                / math.sqrt(1 - (1 - cs) ** (2 * gen)) / chiN) < (1.4 + 2 / (d + 1))
        pc = (1 - cc) * pc + hsig * math.sqrt(cc * (2 - cc) * mueff) * yw

        ymu = (Xc[order[:mu]] - xold) / sigma
        C = ((1 - c1 - cmu) * C
             + c1 * (np.outer(pc, pc) + (1 - hsig) * cc * (2 - cc) * C)
             + cmu * (ymu.T * w) @ ymu)
        sigma *= math.exp((cs / damps) * (np.linalg.norm(psig) / chiN - 1))
        sigma = float(np.clip(sigma, 1e-4, 1.0))


@dataclass
class BoConfig:
    """GP-BO defaults. `n_init` is 2d+2, the usual rule for a d-dim space."""

    n_init: int = 2 * N_ACTIONS + 2
    n_candidates: int = 2000
    xi: float = 0.01                      # EI exploration offset
    refit_every: int = 1


def method_gp_bo(obj: Objective, rng: np.random.Generator,
                 cfg: Optional[BoConfig] = None) -> dict:
    """Gaussian-process Bayesian optimisation with Expected Improvement.

    `scikit-optimize` is not installed; `scikit-learn` is, so the GP is
    sklearn's with a Matern(5/2) + White kernel — the standard BO prior. The
    acquisition is maximised over a random candidate pool rather than by a
    gradient optimiser, which is the usual cheap choice and, at 2000
    candidates in 7 dimensions, is not what limits this method.

    **7c requires the wall clock to be reported separately for exactly this
    method**: the GP fit is O(n^3) in observations and is NOT free, unlike
    PPO's update at 0.3 % of its run. A method that wins on simulations and
    loses on wall clock has to show both numbers.
    """
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel

    cfg = cfg or BoConfig()
    X: list[list[float]] = []
    y: list[float] = []

    for row in _lhs(cfg.n_init, N_ACTIONS, rng):
        obj.check_budget()
        t = obj.evaluate(row)
        X.append(list(t.u)); y.append(t.reward)

    fit_seconds = 0.0
    while True:
        obj.check_budget()
        kern = (ConstantKernel(1.0, (1e-3, 1e3))
                * Matern(length_scale=np.ones(N_ACTIONS), nu=2.5,
                         length_scale_bounds=(1e-2, 1e2))
                + WhiteKernel(1e-3, (1e-8, 1e1)))
        gp = GaussianProcessRegressor(kernel=kern, normalize_y=True,
                                      n_restarts_optimizer=1,
                                      random_state=int(rng.integers(1 << 31)))
        t0 = time.perf_counter()
        gp.fit(np.asarray(X), np.asarray(y))
        fit_seconds += time.perf_counter() - t0

        cand = rng.uniform(0.0, 1.0, (cfg.n_candidates, N_ACTIONS))
        t0 = time.perf_counter()
        mu, sd = gp.predict(cand, return_std=True)
        fit_seconds += time.perf_counter() - t0
        best = max(y)
        with np.errstate(divide="ignore", invalid="ignore"):
            z = (mu - best - cfg.xi) / np.where(sd > 0, sd, 1.0)
            from scipy.stats import norm
            ei = np.where(sd > 0, (mu - best - cfg.xi) * norm.cdf(z)
                          + sd * norm.pdf(z), 0.0)
        nxt = cand[int(np.argmax(ei))]
        obj.check_budget()
        t = obj.evaluate(nxt)
        X.append(list(t.u)); y.append(t.reward)
        obj_model_seconds(obj, fit_seconds)


def obj_model_seconds(obj: Objective, seconds: float) -> None:
    """Stash the model-fitting time on the objective, for 7c's wall-clock row."""
    setattr(obj, "model_seconds", float(seconds))


def method_ppo(obj: Objective, rng: np.random.Generator,
               steps: int = 100_000,
               rollout_steps: Optional[int] = None) -> dict:
    """The EXISTING, UNTUNED policy from task 6. At P1 only, and labelled.

    7i, in the brief's own words: *"If PPO loses, that is the expected result
    and must be reported as such. It is evidence that untuned PPO at 142
    episodes on a 7-dimensional problem loses to a tuned classical optimiser —
    which is unsurprising and not evidence about the amortised,
    spec-conditioned claim, because that claim is not being tested here."*

    Nothing about `PPOConfig` is changed from session 17. `steps` is set far
    above what the budget can buy so that the SIMULATION budget is what stops
    it, exactly as it stops every other method.
    """
    from nebula.rl.env import CtleSizingEnv, EnvConfig
    from nebula.rl.ppo import PPOConfig, train

    if obj.problem.name != "P1":
        raise ValueError(
            f"PPO runs on P1 only: CtleSizingEnv takes ONE corner and ONE "
            f"load, so a worst-over-corners environment does not exist yet. "
            f"Inventing one for a single method would make the comparison "
            f"about corner handling rather than about search ({obj.problem.name} "
            f"has {len(obj.problem.points)} points)."
        )
    pt = obj.problem.points[0]
    seed = int(rng.integers(1 << 31))
    # `ac_peak_interp` comes off the OBJECTIVE, never from a default here.
    # PPO is the one method that reaches the reward through `rl/env.py`, so a
    # default on this line would let the policy train on the lattice objective
    # while the other four are ranked on the interpolated one -- 7f's
    # "identical validity handling" broken in the least visible possible place.
    # `rollout_steps` is the ONLY hyperparameter this function exposes, and it
    # is exposed because session 22g measured it to be the binding one: at the
    # default 64, a 150-simulation budget buys PPO exactly ONE policy update
    # (the run spends ~1.57 simulations per environment step on episode
    # resets). `None` keeps `PPOConfig`'s default, so METHODS -- and therefore
    # every published sweep -- is unchanged.
    cfg = EnvConfig(seed=seed, cl_f=pt.cl_f, corner=pt.corner,
                    temp_c=pt.temp_c, vdd_scale=pt.vdd_scale,
                    specs=obj.specs,
                    target_f_peak_hz=obj.target_f_peak_hz,
                    target_peaking_db=obj.target_peaking_db,
                    ac_peak_interp=obj.ac_peak_interp)
    env = _ObjectiveEnv(obj, cfg)
    pcfg = PPOConfig(seed=seed, total_steps=steps)
    if rollout_steps is not None:
        pcfg = dataclasses.replace(pcfg, rollout_steps=int(rollout_steps))
    train(env, pcfg)


class _ObjectiveEnv:
    """`CtleSizingEnv` with its evaluations routed through the `Objective`.

    Why not just run the env and count its own `SpiceBudget`: the anytime
    curve, the invalid rate, the screening and the logging all live on the
    objective, and a second accounting path is the two-definitions failure this
    repo keeps hitting (rule 9). So the env is constructed with the objective's
    `SpiceBudget`, and its `on_step` callback converts each `StepRecord` into a
    `Trial`. The budget check happens in the callback, which is why
    `BudgetExhausted` has to be an exception: it fires inside PPO's rollout.

    **The pre-screen wraps PPO's ACTIONS but not its episode RESETS, and that
    asymmetry is a limitation rather than a choice.** `CtleSizingEnv.reset`
    draws its own start point and retries up to 25 times, and its seeded form
    RAISES on a start that does not simulate ("a seeded start must be measured
    before it is used, not assumed") — so screening the draw would mean
    reimplementing reset, not passing a flag. The consequence, stated so it is
    not read off the numbers as a property of PPO: the screened PPO arm still
    spends simulations on unscreened episode starts, roughly one per episode,
    which makes it a WEAKER wrapper than the one the other four methods get.
    """

    def __init__(self, obj: Objective, cfg):
        from nebula.rl.env import CtleSizingEnv

        self.obj = obj
        self.env = CtleSizingEnv(cfg, budget=obj.spice, on_step=self._on_step)
        self.observation_dim = self.env.observation_dim
        self.action_dim = self.env.action_dim

    def _on_step(self, rec) -> None:
        o = self.obj
        o.n_sims += rec.n_spice
        o.n_seconds += rec.seconds
        if rec.n_spice == 0:
            o.n_zero_sim += 1
        if rec.verdict == "invalid":
            key = _classify_invalid(rec.invalid_reason or "")
            o.invalid_reasons[key] = o.invalid_reasons.get(key, 0) + 1
        if o.prescreen:
            pass                      # applied in `step`, before the call
        o._emit(Trial(
            index=len(o.trials), u=list(rec.u), design_id=rec.design_id,
            geometry_tag=rec.geometry_tag, params=dict(rec.params),
            reward=float(rec.reward), feasible=bool(rec.feasible),
            verdict=rec.verdict, invalid_reason=rec.invalid_reason,
            worst_point=o.problem.points[0].label, worst_spec=rec.worst_spec,
            n_sims=rec.n_spice, seconds=rec.seconds, cum_sims=o.n_sims,
            cum_seconds=o.n_seconds, screened_out=False, screen_reason=None,
            meas=(dict(rec.meas) if rec.meas else None),
            margins=(dict(rec.margins) if rec.margins else None),
            predicted=None))
        o.check_budget()

    def reset(self, *a, **kw):
        self.obj.check_budget()
        return self.env.reset(*a, **kw)

    def step(self, action):
        self.obj.check_budget()
        if self.obj.prescreen:
            # The pre-screen as a WRAPPER on PPO: predict the point the action
            # would land on and, if the screen rejects it, terminate the
            # episode at the invalid floor WITHOUT a simulation. That is the
            # same treatment an invalid evaluation gets (§6d), which is what
            # makes it a wrapper rather than a different environment.
            u = np.clip(self.env._u
                        + np.clip(np.asarray(action, float).ravel(), -1, 1)
                        * self.env.cfg.max_step, 0.0, 1.0)
            s = sizing_from_u(u, cl_f=self.env.cfg.cl_f)
            v = PS.screen(s.params, target_f_peak_hz=self.obj.target_f_peak_hz)
            if not v.accept:
                self.obj.n_screened_out += 1
                self.obj._emit(Trial(
                    index=len(self.obj.trials), u=[float(x) for x in u],
                    design_id=None, geometry_tag=None, params=dict(s.params),
                    reward=self.obj.floor, feasible=False, verdict="screened",
                    invalid_reason=None, worst_point=None, worst_spec=None,
                    n_sims=0, seconds=0.0, cum_sims=self.obj.n_sims,
                    cum_seconds=self.obj.n_seconds, screened_out=True,
                    screen_reason=v.reason, meas=None, margins=None,
                    predicted=None))
                obs = self.env._observation(self.env._last)
                return obs, self.obj.floor, True, False, {"screened": True}
        return self.env.step(action)


METHODS: dict[str, Callable] = {
    "uniform": method_uniform,
    "lhs": method_lhs,
    "grid": method_grid,
    "cmaes": method_cmaes,
    "gp_bo": method_gp_bo,
    "ppo": method_ppo,
}

#: 7d's designer row. **A reconstruction from the session log, not a run.**
#:
#: HANDOFF §12, session 9c (2026-08-04): *"Human-led hand-sizing session at the
#: ngspice prompt; these numbers come from twenty-odd AC runs done
#: deliberately, not from a script."* That session found **twelve
#: configurations meeting S3** (3-12 dB peaking, f_pk in 1.25-2.5 GHz) spanning
#: 4.63-10.01 dB at 1.32-2.30 GHz, after a 5-point width sweep that fixed the
#: bias (gm/I_D 1.7 -> 8.4) and separate Rs, Cs and RL/CL probes.
#:
#: **What it is NOT comparable to, stated so the row cannot be misread:**
#:   * ideal R/C passives and IDEAL TAIL SINKS — a strictly easier problem than
#:     P1, which draws real SKY130 devices and a current mirror;
#:   * `cl` = 100 fF, which is 3.1x above `cl_mid` and outside CL_RANGE.md's
#:     derived range entirely;
#:   * S3 ONLY. Reward v1 scores seven rows; noise, power and both saturation
#:     margins were not checked at those twelve points;
#:   * ONE corner, no load range.
#: So it is a LOWER bound on the simulations a designer needs and an UPPER
#: bound on what those simulations established.
DESIGNER_BASELINE: dict = {
    "source": "HANDOFF sec 12, session 9c (2026-08-04), hand-sizing at the "
              "ngspice prompt",
    "sims_quoted": "twenty-odd AC runs",
    "sims_low": 20,
    "sims_high": 25,
    "n_s3_meeting_found": 12,
    "problem_solved": "S3 only, TT only, ideal passives, ideal tail, "
                      "cl = 100 fF",
    "comparable_rung": None,
    "caveat": "LOWER bound on simulations, UPPER bound on rigour -- see the "
              "constant's docstring. It is the number the judges have in their "
              "heads, which is why it is a row.",
}


# ─────────────────────────────────────────────────────────────────────────────
# 7a — the budget arithmetic, computed rather than asserted.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Allocation:
    """One (problem, method, pre-screen) block of the sweep."""

    problem: str
    method: str
    prescreen: bool
    replicates: int
    budget_sims: int

    @property
    def sims(self) -> int:
        return self.replicates * self.budget_sims


#: Simulations per run — **the x-axis of every plot here**, and therefore the
#: one thing 7a forbids shrinking quietly. 150 is stated up front and held
#: across every method and every rung.
#:
#: Why 150 and not 500: at P1's ~13.5 % base rate uniform random expects ~20
#: feasible designs in 150 simulations, so the anytime curve has resolution and
#: the secondary metric is only lightly censored; and 150 is ~6x the designer
#: baseline's twenty-odd runs, which is the comparison a judge will make.
#: Why not 60: CMA-ES at the default popsize of 10 would get six generations,
#: which is barely more than its initial distribution.
BUDGET_SIMS: int = 150

#: 7h's floors. Cutting these is forbidden before cutting a problem rung.
#: `grid` gets 20 like the other two model-free methods, and specifically the
#: same 20 as `uniform`, because "grid search against random search at equal
#: budget" is the comparison the problem statement is about and an unequal seed
#: count would make it a comparison of sample sizes.
REPLICATES: dict[str, int] = {"uniform": 20, "lhs": 20, "grid": 20,
                              "cmaes": 10, "gp_bo": 10, "ppo": 10}

#: Which methods run on P3, and this list is where the SECOND cut fell.
#:
#: **Re-cut 2026-08-08** after the pilot measured 8 workers buying 1.80x rather
#: than 2.98x: at 1.698 s/sim the previous allocation was 14.2 h, not 11.2 h,
#: and no longer fit. Per 7a the cut falls on problems, not on the per-run
#: budget and not on the seed counts, so P3 lost `lhs` and `gp_bo`.
#:
#: Why those two and not the others: the pilot found **0 of 2 seeds feasible on
#: P3 for both methods it ran**, at 60 simulations. P3's job is to establish
#: whether anything feasible exists at all and to keep the anytime metric
#: defined — `uniform` supplies the reference rate and `cmaes` is the strongest
#: classical optimiser on P1, so between them the rung is answered. Adding
#: `lhs` and `gp_bo` would spend 4 500 simulations to produce two more rows
#: reading "never found one". `ppo` cannot run P3 at all — see `method_ppo`.
#:
#: **`grid` is absent for a THIRD kind of reason, and it is arithmetic rather
#: than judgement.** P3 costs 6 simulations per design, so a 150-simulation
#: budget buys 25 designs, and the smallest complete factorial in 7 dimensions
#: is 128. `grid_levels(25, 7)` returns **1** -- the single box centre. A grid
#: arm on P3 would be one point, which is not a search, so the row would
#: measure the box centre and be labelled as a grid. Stated here rather than
#: left to be inferred from a missing row.
P3_METHODS: tuple[str, ...] = ("uniform", "cmaes")


def default_allocation() -> tuple[Allocation, ...]:
    """The overnight sweep, as three blocks. **What was cut is in the name.**

    The arithmetic is in `budget_report()`. It was that a fully crossed design
    (3 rungs x 6 methods x {screen, no screen} x these replicates x 150) is
    **81 000 simulations**, which at the pre-trim 1.698 s/sim was 38 hours and
    did not fit, so something had to go. Per 7a the cut fell on PROBLEMS and on
    pre-screen ARMS, never on the per-run budget and never on the seed counts:

    **2026-08-19: THE COST ARGUMENT IS GONE AND THE CUTS ARE NOT.** The sweep
    measured itself at 0.09773 s/sim end to end, so the fully crossed design is
    now **~2.2 hours**. That retires the budgetary reason for exactly one of
    the three cuts below -- P2 -- and leaves the other two standing on their
    own reasons, which were never about cost. Restoring P2 is a change to what
    the benchmark measures and therefore an OWNER'S CALL, recorded in
    `CONTINUE_HERE.md` sec 5; it is not taken here.

      Block A   P1, no pre-screen, all five methods
      Block B   P1, pre-screened, all five methods
      Block C   P3, no pre-screen, four methods (PPO cannot run it — see
                `method_ppo`)

    **Cut, and why:**
      * **P2 entirely** -- and this is the cut whose reason has now expired.
        It is the interpolation between P1 and P3, and the
        quantity it would resolve — how much of the loss is corners and how
        much is load — is already measured, twice: session 10d put the corner
        tax at 39 % of the nominal winners and session 12b put the load cost at
        99.4 %. P2 adds a third estimate of a known split at the price of a
        third of the night.
      * **P3's pre-screened arm.** EPISTEMIC, not budgetary, so it stands.
        The screen is calibrated on TT and its
        false-rejection rate at corners is unmeasured, so a screened P3 arm
        would confound "the screen helps" with "the screen is miscalibrated off
        nominal". Measuring that calibration first is cheaper than running the
        arm.
      * **P3's PPO arm**, for the structural reason in `method_ppo`.
      * **P3's grid arm**, for the arithmetic reason in `P3_METHODS`.
    """
    out: list[Allocation] = []
    for m, n in REPLICATES.items():
        out.append(Allocation("P1", m, False, n, BUDGET_SIMS))
    for m, n in REPLICATES.items():
        out.append(Allocation("P1", m, True, n, BUDGET_SIMS))
    for m in P3_METHODS:
        out.append(Allocation("P3", m, False, REPLICATES[m], BUDGET_SIMS))
    return tuple(out)


def budget_report(alloc: Optional[Sequence[Allocation]] = None) -> dict:
    """7a, computed from the measured constants. Auditable, not asserted."""
    alloc = tuple(alloc if alloc is not None else default_allocation())
    total = sum(a.sims for a in alloc)

    def _hours(sims: int, sec: float) -> float:
        return sims * sec / 3600.0

    full = 3 * 2 * sum(REPLICATES.values()) * BUDGET_SIMS
    return {
        "budget_sims_per_run": BUDGET_SIMS,
        "replicates": dict(REPLICATES),
        "blocks": [asdict(a) for a in alloc],
        "n_runs": sum(a.replicates for a in alloc),
        "total_sims": total,
        "fully_crossed_sims": full,
        "fully_crossed_hours_at_8": _hours(full, SEC_PER_SIM_AT_8),
        # The two brackets. **Both are now END-TO-END measurements of THIS
        # allocation** (2026-08-19) rather than two serial probes of two task
        # distributions: the interpolated sweep and its lattice control, same
        # 170 runs and same seeds, ran at 0.09773 and 0.11095 s/sim. The spread
        # between two runs of one allocation is the honest width of the
        # estimate, and it is 13.5 % rather than the 1.9x the serial probes
        # disagreed by.
        "hours_pessimistic": _hours(total, SEC_PER_SIM_AT_8_LATTICE),
        "hours_optimistic": _hours(total, SEC_PER_SIM_AT_8),
        "sec_per_sim_at_8_workers": SEC_PER_SIM_AT_8,
        "sec_per_sim_at_8_workers_lattice": SEC_PER_SIM_AT_8_LATTICE,
        "sec_per_sim_at_8_workers_pilot": SEC_PER_SIM_AT_8_PILOT,
        "sec_per_sim_at_8_workers_session_17": SEC_PER_SIM_AT_8_SESSION_17,
        "speedup_at_8_session_17": SPEEDUP_AT_8_SESSION_17,
        "sec_per_sim_serial_uniform": SEC_PER_SIM_UNIFORM,
        "sec_per_sim_serial_trajectory": SEC_PER_SIM_TRAJECTORY,
        "workers": WORKERS,
        "speedup_at_8": SPEEDUP_AT_8,
        # The item that was "highest value in the repo" for five sessions, now
        # DONE and priced. Kept as a row because the ratio is the argument for
        # every experiment this project can still afford.
        "library_trim_note": (
            "The extended-library trim is DONE. It was measured at 2.07 s/eval "
            "before and ~0.33 s serial after, and the end-to-end effect is "
            f"visible here: this allocation is {_hours(total, SEC_PER_SIM_AT_8):.1f} h "
            f"at the measured 0.098 s/sim against "
            f"{_hours(total, SEC_PER_SIM_AT_8_PILOT):.1f} h at the pre-trim "
            "1.698. **The cuts in default_allocation() were made against the "
            "pre-trim number and are no longer forced by cost** -- see that "
            "function's docstring for which of them are now epistemic or "
            "structural rather than budgetary."),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7c / 7h — metrics and statistics.
# ─────────────────────────────────────────────────────────────────────────────


# ── THE REWARD CEILING, and why it is a finding rather than a detail ────────
#
# Every netlist in this project sweeps `ac dec 50 1meg 100g`, so `meas ac MAX`
# can only ever report a frequency on the lattice
#
#     f_k = 1e6 * 10^(k/50)   ->   0.066439 octaves apart (session 11)
#
# `reward_v1`'s feasible branch scores `B + min_i(margin_i / tol_i)`, and on P1
# the binding row is essentially always `S3_f_peak`, whose margin is
# `0.5 - |log2(f_peak / f_target)|` in octaves. **So the reward a design can
# reach is capped by how close the LATTICE gets to the target**, not by the
# circuit: with the target at the geometric centre of S3's octave, the nearest
# grid point is 0.02466 octaves away and no design can score above
#
#     8 + (0.5 - 0.02466) / 0.5 = 8.95068
#
# Measured in the pilot: four independent runs, four DIFFERENT designs, all
# scoring 8.950670 to six decimals. That is the ceiling, and it means
# best-reward-at-budget saturates on P1 and cannot separate methods there. The
# metric that can is SIMULATIONS TO REACH THE CEILING, which is why it is
# computed beside the anytime curve rather than instead of it.
AC_GRID_START_HZ: float = 1e6
AC_GRID_PER_DECADE: int = 50
#: One grid step, in octaves. Session 11 measured exactly this and used it to
#: say S3's one-octave window holds 15 distinct f_peak values.
AC_GRID_OCTAVES: float = math.log2(10.0 ** (1.0 / AC_GRID_PER_DECADE))


def nearest_grid_offset_octaves(target_f_peak_hz: float) -> float:
    """|target - nearest AC grid point|, in octaves. The ceiling's whole cause."""
    from nebula.rl.contract import f_peak_octaves

    base = f_peak_octaves(AC_GRID_START_HZ)
    k = (f_peak_octaves(target_f_peak_hz) - base) / AC_GRID_OCTAVES
    return float(min(abs(k - math.floor(k)), abs(math.ceil(k) - k))
                 * AC_GRID_OCTAVES)


def reward_ceiling(target_f_peak_hz: float,
                   specs: Sequence[str] = R.V1_SPECS) -> float:
    """The highest reward any design can score, given the AC sweep grid.

    Assumes `S3_f_peak` is the binding row, which is what makes it a CEILING
    and not a prediction: any other binding row gives a LOWER score, because
    the feasible branch takes the minimum.
    """
    off = nearest_grid_offset_octaves(target_f_peak_hz)
    return float(R.feasible_bonus(len(specs))
                 + (R.TOL["S3_f_peak"] - off) / R.TOL["S3_f_peak"])


def sims_to_ceiling(trials: Sequence[Trial], ceiling: float,
                    tol: float = 1e-6) -> Optional[int]:
    """Simulations spent before the ceiling was first reached. `None` = never.

    Censored exactly like `sims_to_first_feasible`, and reported the same way
    (7c): fraction of seeds that got there, and a median CONDITIONAL on that.
    """
    for t in trials:
        if t.n_sims > 0 and t.reward >= ceiling - tol:
            return int(t.cum_sims)
    return None


def anytime_curve(trials: Sequence[Trial], budget: int) -> np.ndarray:
    """Best reward achieved as a function of simulations spent.

    A step function on `1..budget`, evaluated at every integer so curves from
    runs with different trial counts are directly comparable. Before the first
    simulation completes the value is `-inf`; callers plotting it should show
    the reward floor instead, and `summarise_curves` does.
    """
    out = np.full(int(budget), -np.inf)
    best = -np.inf
    for t in trials:
        if t.n_sims <= 0:
            continue
        best = max(best, t.reward)
        lo = min(int(t.cum_sims), int(budget))
        out[lo - 1:] = np.maximum(out[lo - 1:], best)
    return out


def bootstrap_median(x: Sequence[float], n_boot: int = 10_000,
                     alpha: float = 0.05,
                     rng: Optional[np.random.Generator] = None
                     ) -> tuple[float, float, float]:
    """`(median, lo, hi)` — percentile bootstrap. **Medians, not means (7h).**

    A mean over seeds is the wrong summary here for a reason that is not
    stylistic: the reward has a floor at `invalid_reward` and a hard band
    structure, so one unlucky seed drags a mean across a band boundary while
    the median stays where the typical run is.
    """
    a = np.asarray([v for v in x if np.isfinite(v)], dtype=float)
    if a.size == 0:
        return float("nan"), float("nan"), float("nan")
    rng = rng or np.random.default_rng(0)
    idx = rng.integers(0, a.size, size=(n_boot, a.size))
    meds = np.median(a[idx], axis=1)
    return (float(np.median(a)),
            float(np.percentile(meds, 100 * alpha / 2)),
            float(np.percentile(meds, 100 * (1 - alpha / 2))))


def censored_table(runs: Sequence[dict], key: str = "sims_to_first_feasible"
                   ) -> dict:
    """7c's secondary metric, handled as the censored data it is.

    *"Do not substitute the budget, or infinity, or drop the censored seeds and
    report the mean of the rest. Each of those produces a plausible number that
    flatters whichever method got lucky."*

    So this returns three things and never one: the FRACTION of seeds that
    found a feasible design inside budget, the median among THOSE — labelled
    conditional — and the count it was taken over.
    """
    n = len(runs)
    hits = [r[key] for r in runs if r.get(key) is not None]
    med, lo, hi = bootstrap_median(hits) if hits else (None, None, None)
    return {
        "metric": key,
        "n_seeds": n,
        "n_found": len(hits),
        "frac_found": (len(hits) / n) if n else float("nan"),
        "median_conditional": med,
        "ci_lo_conditional": lo,
        "ci_hi_conditional": hi,
        "conditional_on": "seeds that found a feasible design within budget; "
                          "the median is CONDITIONAL and is not an estimate of "
                          "the unconditional time-to-feasible",
        "censored_seeds": n - len(hits),
    }


def mann_whitney(a: Sequence[float], b: Sequence[float]) -> dict:
    """Pairwise test on the UNCENSORED seeds, with an effect size beside it.

    7h: *"effect sizes reported alongside p-values, and an explicit note about
    multiple comparisons."* The effect size is the common-language one — the
    probability that a draw from `a` is smaller than a draw from `b`, which is
    `U / (n_a n_b)` and is the same quantity the test statistic is built from.
    """
    from scipy.stats import mannwhitneyu

    a = np.asarray(list(a), float)
    b = np.asarray(list(b), float)
    if a.size < 2 or b.size < 2:
        return {"n_a": int(a.size), "n_b": int(b.size), "p": None,
                "effect": None,
                "note": "not enough uncensored seeds to test"}
    u, p = mannwhitneyu(a, b, alternative="two-sided")
    return {"n_a": int(a.size), "n_b": int(b.size), "u": float(u),
            "p": float(p), "effect": float(u / (a.size * b.size)),
            "effect_meaning": "P(a < b) + 0.5 P(a = b); 0.5 is no effect"}


def separable(ci_a: tuple[float, float], ci_b: tuple[float, float]) -> bool:
    """7h's ranking rule: overlapping intervals are NOT a ranking."""
    return not (ci_a[0] <= ci_b[1] and ci_b[0] <= ci_a[1])


# ─────────────────────────────────────────────────────────────────────────────
# The driver. 7g's interleaving and control live here.
# ─────────────────────────────────────────────────────────────────────────────

#: 7g. The control is the first configuration re-run LAST. If its per-simulation
#: wall clock disagrees with its own first pass by more than this, the TIMING
#: numbers for that sweep are void and the sweep is repeated — **not adjusted**.
#: The threshold is session 17's own: `parallel_throughput` flags
#: contamination outside [0.8, 1.25], and it was that detector that caught G71.
CONTROL_RATIO_LIMIT: tuple[float, float] = (0.8, 1.25)


@dataclass(frozen=True)
class Job:
    """One unit of work. Picklable, so a worker process can be handed one."""

    problem: str
    method: str
    replicate: int
    budget_sims: int
    prescreen: bool
    #: "measured" rows enter the analysis; "warmup" and "control" carry only
    #: timing, and 7g's control compares the two.
    role: str = "measured"
    #: Score the sub-grid peak rather than the `dec 50` lattice one (G74).
    #: **On the JOB rather than on the Allocation** because it is a property of
    #: the whole sweep, not of one block: a run log holding some jobs scored one
    #: way and some the other would be a benchmark comparing two objectives,
    #: which is 7f's whole prohibition. `sweep()` sets it once for every job and
    #: records it in the header.
    ac_peak_interp: bool = False

    @property
    def config(self) -> str:
        return f"{self.problem}/{self.method}{'+screen' if self.prescreen else ''}"


def run_one(job: Job) -> dict:
    """One (problem, method, replicate). Returns its summary AND its trials.

    Trials come back rather than being written here because this runs in a
    worker process (7f: `WORKERS` = 8 everywhere) and eight processes appending
    to one JSONL is how a log gets interleaved rows. The parent writes them.
    """
    # One BLAS/torch thread per worker. Eight workers each spawning a thread
    # pool oversubscribes the machine and would make the wall clock a
    # measurement of the thread scheduler.
    try:                                                    # pragma: no cover
        import torch

        torch.set_num_threads(1)
    except Exception:                                       # pragma: no cover
        pass

    prob = PROBLEMS[job.problem]
    seed = run_seed(job.problem, job.method, job.replicate)
    rng = np.random.default_rng(seed)

    obj = Objective(prob, job.budget_sims, prescreen=job.prescreen,
                    ac_peak_interp=job.ac_peak_interp)
    t0 = time.perf_counter()
    try:
        METHODS[job.method](obj, rng)
    except BudgetExhausted:
        pass
    wall = time.perf_counter() - t0

    s = obj.summary()
    s.update(problem=job.problem, method=job.method, replicate=job.replicate,
             seed=seed, prescreen=job.prescreen, role=job.role, wall_s=wall,
             ac_peak_interp=job.ac_peak_interp,
             model_seconds=float(getattr(obj, "model_seconds", 0.0)),
             sec_per_sim=(wall / obj.n_sims if obj.n_sims else float("nan")),
             curve=[float(v) for v in anytime_curve(obj.trials,
                                                    job.budget_sims)],
             trials=[asdict(t) for t in obj.trials])
    return s


def jobs_for(alloc: Sequence[Allocation], seed: int,
             ac_peak_interp: bool = False) -> list[Job]:
    """Every measured run, INTERLEAVED (7g).

    The shuffle is over individual jobs, not over blocks, so no method is
    systematically early and no method is systematically late — a block-level
    shuffle would still put all twenty `uniform` replicates next to each other
    and let a thermal drift land on one method.
    """
    out = [Job(a.problem, a.method, rep, a.budget_sims, a.prescreen,
               ac_peak_interp=ac_peak_interp)
           for a in alloc for rep in range(a.replicates)]
    np.random.default_rng(seed).shuffle(out)
    return out


def sweep(alloc: Optional[Sequence[Allocation]] = None,
          log_path: Optional[Path] = None,
          seed: int = BASE_SEED,
          control: bool = True,
          workers: int = WORKERS,
          out_path: Optional[Path] = None,
          ac_peak_interp: bool = False) -> dict:
    """The whole benchmark. ONE command, fixed seeds (7j).

    **The parallelism is across RUNS, not inside them, and that is a fairness
    decision.** Parallelising inside a run would help the batch methods
    (uniform, LHS, one CMA-ES generation) and be impossible for GP-BO, whose
    every proposal depends on the previous answer — so the comparison would
    become a comparison of how batchable each method is. Across runs, every
    method keeps its own sequential decision structure and every one of them
    sees the same `WORKERS` = 8 machine.

    **7g's timing discipline, enforced here rather than remembered:**

    * jobs are INTERLEAVED (`jobs_for`);
    * a **warm-up** run of the first configuration executes first, alone, and
      is **discarded from the analysis**. Session 17 measured that this is the
      defence that actually works: with randomisation and a control but no
      warm-up, on an idle machine, the control still came back at 1.60x,
      because *the first configuration always pays the cold file cache,
      whichever one it is* (G71);
    * the **control** re-runs that same configuration LAST, also alone, and is
      compared with the warm-up. Both are single-process, one before and one
      after the pool, so the comparison measures MACHINE DRIFT and is not
      confounded by a draining pool having fewer competitors;
    * if they disagree by more than `CONTROL_RATIO_LIMIT` the result carries
      `timing_void = True`. The WALL-CLOCK numbers for that sweep are then void
      and the sweep is **repeated, not adjusted**. The SIMULATION counts are
      unaffected, which is exactly why 7g asks for simulations as the headline.

    Both the warm-up and the control cost real simulations and both are counted
    (7f: every simulation, including ones whose results are discarded).
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    alloc = list(alloc if alloc is not None else default_allocation())
    jobs = jobs_for(alloc, seed, ac_peak_interp=ac_peak_interp)
    log_path = log_path or (HERE / "baselines_run.jsonl")
    header = {"task": "7 - baselines sweep", "base_seed": seed,
              # WHICH OBJECTIVE THIS SWEEP OPTIMISED. On the header rather than
              # only on the rows, because it is the one property that must be
              # the same for every row: a log mixing the two is a benchmark
              # comparing formulations instead of methods (7f).
              "ac_peak_interp": bool(ac_peak_interp),
              "allocation": [asdict(a) for a in alloc],
              "budget": budget_report(alloc),
              "problems": {k: {"note": v.note,
                               "points": [asdict(p) for p in v.points]}
                           for k, v in PROBLEMS.items()},
              "tunable_seam": TUNABLE_SEAM,
              "designer_baseline": DESIGNER_BASELINE,
              "job_order": [j.config for j in jobs],
              "started": time.strftime("%Y-%m-%d %H:%M:%S"),
              **provenance()}

    runs: list[dict] = []
    t_sweep = time.perf_counter()
    with RunLog(log_path, header) as log:

        def _emit(r: dict) -> None:
            trials = r.pop("trials", [])
            for t in trials:
                log.event("trial", problem=r["problem"], method=r["method"],
                          replicate=r["replicate"], seed=r["seed"],
                          prescreen=r["prescreen"], role=r["role"], **t)
            log.event("run_summary",
                      **{k: v for k, v in r.items() if k != "curve"})

        warm = None
        if control and jobs:
            j0 = jobs[0]
            # The warm-up and the control must run the SAME objective as the
            # pool, or 7g's ratio compares two different workloads and calls
            # the difference machine drift.
            warm = run_one(Job(j0.problem, j0.method, 0, j0.budget_sims,
                               j0.prescreen, role="warmup",
                               ac_peak_interp=ac_peak_interp))
            _emit(warm)
            print(f"  warm-up {j0.config}: {warm['sec_per_sim']:.3f} s/sim, "
                  f"{warm['n_sims']} sims, DISCARDED from the analysis",
                  flush=True)

        if workers <= 1:
            for j in jobs:
                r = run_one(j)
                runs.append(r)
                _emit(dict(r))
        else:
            with ProcessPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(run_one, j): j for j in jobs}
                for i, fut in enumerate(as_completed(futs), start=1):
                    r = fut.result()
                    runs.append(r)
                    _emit(dict(r))
                    print(f"  [{i:>3}/{len(jobs)}] {futs[fut].config:<18} "
                          f"rep {r['replicate']:>2}  best "
                          f"{r['best_reward']:.3f}  sims {r['n_sims']:>4}  "
                          f"{r['wall_s']:.1f} s", flush=True)

        ctrl = None
        if control and warm is not None:
            j0 = jobs[0]
            last = run_one(Job(j0.problem, j0.method, 0, j0.budget_sims,
                               j0.prescreen, role="control",
                               ac_peak_interp=ac_peak_interp))
            _emit(dict(last))
            ratio = (warm["sec_per_sim"] / last["sec_per_sim"]
                     if last["sec_per_sim"] else float("nan"))
            lo, hi = CONTROL_RATIO_LIMIT
            ctrl = {"config": j0.config,
                    "warmup_sec_per_sim": warm["sec_per_sim"],
                    "control_sec_per_sim": last["sec_per_sim"],
                    "ratio": float(ratio), "limit": list(CONTROL_RATIO_LIMIT),
                    "timing_void": bool(not (lo <= ratio <= hi)),
                    "note": "warm-up and control are both SINGLE-PROCESS runs "
                            "of the same configuration, before and after the "
                            "pool, so the ratio is machine drift and not pool "
                            "contention. If timing_void, the WALL-CLOCK "
                            "numbers are void and the sweep is repeated, not "
                            "adjusted; the simulation counts stand."}
            log.event("timing_control", **ctrl)

        analysis = analyse([r for r in runs if r.get("role", "measured")
                            == "measured"])
        total = sum(r["n_sims"] for r in runs) + \
            (warm["n_sims"] if warm else 0) + \
            (last["n_sims"] if ctrl else 0)
        out = {"header": header, "runs": runs, "control": ctrl,
               "warmup": {k: v for k, v in (warm or {}).items()
                          if k != "curve"},
               "wall_s": time.perf_counter() - t_sweep,
               "total_sims_including_discarded": total,
               "analysis": analysis}
        log.event("sweep_summary", control=ctrl, n_runs=len(runs),
                  total_sims_including_discarded=total,
                  wall_s=out["wall_s"])
    # **NOT `baselines_results.json`, and that is a bug fix.** That name was
    # already taken by the `--prescreen` stage's artifact -- 1890 samples of
    # pre-screen calibration that `BASELINES.md` §5 quotes -- and this default
    # silently overwrote it the first time the sweep ran (G95). Two writers
    # sharing one default path is rule 9 in the filesystem.
    _save(out, out_path or (HERE / "baselines_sweep_results.json"))
    return out


def analyse_log(path: Path) -> dict:
    """Rebuild the analysis from a run log alone. **The recovery path.**

    Why this exists rather than only `sweep()` returning its own analysis: a
    12-hour sweep that is interrupted in its last minute would otherwise have
    produced 30 000 simulations and no result. It happened on the first pilot —
    33 of 34 runs finished and the process was killed before it printed
    anything — and the log had every row.

    So the analysis is reconstructed from the `trial` rows, not from the
    `run_summary` rows: the summaries omit the anytime curve (it is 150 floats
    per run and would triple the log), and the trials contain strictly more
    information than the summaries do. A summary that disagrees with its own
    trials would be two definitions of one thing (rule 9); this way there is
    one.
    """
    rows = list(runlog_read(path))
    header = next((r for r in rows if r.get("kind") == "header"), {})
    trials: dict[tuple, list[dict]] = {}
    budgets: dict[tuple, int] = {}
    alloc = {(a["problem"], a["method"], a["prescreen"]): a["budget_sims"]
             for a in header.get("allocation", [])}
    for r in rows:
        if r.get("event") != "trial" or r.get("role") != "measured":
            continue
        key = (r["problem"], r["method"], bool(r["prescreen"]), r["replicate"])
        trials.setdefault(key, []).append(r)
        budgets[key] = alloc.get(key[:3], 0)

    runs = []
    for key, ts in sorted(trials.items()):
        prob, method, screen, rep = key
        ts.sort(key=lambda t: t["index"])
        budget = budgets[key] or max(t["cum_sims"] for t in ts)
        sim = [t for t in ts if t["n_sims"] > 0]
        first = next((t for t in sim if t["feasible"]), None)
        ceil = reward_ceiling(
            math.sqrt(SPEC_F_PEAK_HZ_RANGE[0] * SPEC_F_PEAK_HZ_RANGE[1]))
        hit = next((t for t in sim if t["reward"] >= ceil - 1e-6), None)
        curve = np.full(budget, -np.inf)
        best = -np.inf
        for t in sim:
            best = max(best, t["reward"])
            lo = min(int(t["cum_sims"]), budget)
            curve[lo - 1:] = np.maximum(curve[lo - 1:], best)
        runs.append({
            "problem": prob, "method": method, "prescreen": screen,
            "replicate": rep, "seed": ts[0].get("seed"),
            "curve": [float(v) for v in curve],
            "n_sims": sum(t["n_sims"] for t in ts),
            "n_simulated": len(sim), "n_trials": len(ts),
            "n_feasible": sum(1 for t in sim if t["feasible"]),
            "best_reward": (max(t["reward"] for t in sim) if sim else None),
            "sims_to_first_feasible": (first["cum_sims"] if first else None),
            "sims_to_ceiling": (hit["cum_sims"] if hit else None),
            "reward_ceiling": ceil,
            "n_screened_out": sum(1 for t in ts if t["screened_out"]),
            "invalid_rate": (sum(1 for t in sim if t["verdict"] == "invalid")
                             / len(sim) if sim else 0.0),
            "wall_s": sum(t["seconds"] for t in ts),
            "model_seconds": 0.0,
            "sec_per_sim": (sum(t["seconds"] for t in ts)
                            / max(sum(t["n_sims"] for t in ts), 1)),
        })
    return {"header": header, "runs": runs, "analysis": analyse(runs),
            "control": next((r for r in rows
                             if r.get("event") == "timing_control"), None)}


def analyse(runs: Sequence[dict]) -> dict:
    """7c + 7h, from run summaries. Pure — safe to re-run on a saved sweep."""
    groups: dict[str, list[dict]] = {}
    for r in runs:
        key = f"{r['problem']}/{r['method']}{'+screen' if r['prescreen'] else ''}"
        groups.setdefault(key, []).append(r)

    rng = np.random.default_rng(BASE_SEED)
    per_group: dict[str, dict] = {}
    for key, rs in groups.items():
        curves = np.asarray([r["curve"] for r in rs], dtype=float)
        finite = np.where(np.isfinite(curves), curves, np.nan)
        med = np.nanmedian(finite, axis=0)
        # Bootstrap the median curve at a handful of budget checkpoints rather
        # than at every integer: the band is for reading, and 150 bootstraps of
        # 10 000 resamples each would dominate the analysis time for nothing.
        n = curves.shape[1]
        marks = sorted({max(1, n // 8), max(1, n // 4), max(1, n // 2), n})
        band = {}
        for m in marks:
            col = curves[:, m - 1]
            band[str(m)] = bootstrap_median(col, rng=rng)
        per_group[key] = {
            "n_seeds": len(rs),
            "seeds": [r["seed"] for r in rs],
            "median_curve": [None if not np.isfinite(v) else float(v)
                             for v in med],
            "band_at": band,
            "final": bootstrap_median(curves[:, -1], rng=rng),
            "censored": censored_table(rs),
            "censored_ceiling": censored_table(rs, "sims_to_ceiling"),
            "reward_ceiling": rs[0].get("reward_ceiling"),
            "invalid_rate": float(np.median([r["invalid_rate"] for r in rs])),
            "wall_s": float(np.median([r["wall_s"] for r in rs])),
            "model_s": float(np.median([r["model_seconds"] for r in rs])),
            "sec_per_sim": float(np.nanmedian([r["sec_per_sim"] for r in rs])),
            "screened_out": int(np.median([r["n_screened_out"] for r in rs])),
        }

    # Pairwise, within a problem, on the uncensored seeds only.
    pairs: dict[str, dict] = {}
    keys = sorted(per_group)
    for i, ka in enumerate(keys):
        for kb in keys[i + 1:]:
            if ka.split("/")[0] != kb.split("/")[0]:
                continue
            a = [r["sims_to_first_feasible"] for r in groups[ka]
                 if r["sims_to_first_feasible"] is not None]
            b = [r["sims_to_first_feasible"] for r in groups[kb]
                 if r["sims_to_first_feasible"] is not None]
            pairs[f"{ka} vs {kb}"] = mann_whitney(a, b)

    n_tests = len(pairs)
    return {
        "groups": per_group,
        "pairwise_sims_to_feasible": pairs,
        "multiple_comparisons": (
            f"{n_tests} pairwise tests were run. No correction is APPLIED "
            f"because the tests are reported as a family and not used to "
            f"select a winner; at alpha = 0.05 a Bonferroni threshold would be "
            f"{0.05 / n_tests:.4g} and any p above it should be read as "
            f"uncorrected. 7h's ranking rule governs instead: an ordering "
            f"whose confidence intervals overlap is reported as 'not separable "
            f"at this sample size'."),
        "ranking": _ranking(per_group),
    }


def _ranking(per_group: Mapping[str, dict]) -> dict:
    """7h: report a ranking only where the intervals do not overlap."""
    out: dict[str, list] = {}
    by_problem: dict[str, list[tuple[str, tuple]]] = {}
    for k, v in per_group.items():
        by_problem.setdefault(k.split("/")[0], []).append(
            (k, tuple(v["final"])))
    for prob, items in by_problem.items():
        items.sort(key=lambda kv: -(kv[1][0] if np.isfinite(kv[1][0]) else -np.inf))
        rows = []
        for i, (k, ci) in enumerate(items):
            sep = (separable((ci[1], ci[2]), (items[i + 1][1][1],
                                              items[i + 1][1][2]))
                   if i + 1 < len(items) else None)
            rows.append({"group": k, "median_final": ci[0],
                         "ci": [ci[1], ci[2]],
                         "separable_from_next": sep})
        out[prob] = rows
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Printing and CLI.
# ─────────────────────────────────────────────────────────────────────────────


def print_budget(b: dict) -> None:
    print("\n" + "=" * 78)
    print("7a BUDGET ARITHMETIC -- computed, not asserted")
    print("=" * 78)
    print(f"  measured cost. The 8-worker rows are END-TO-END timings of THIS")
    print(f"  allocation (2026-08-19); the rest are kept for the history:")
    print(f"    {b['workers']} workers, interp sweep      "
          f"{b['sec_per_sim_at_8_workers']:.5f} s/sim  "
          f"(2528.06 s / 25 869 sims -- what this is sized to)")
    print(f"    {b['workers']} workers, lattice control  "
          f"{b['sec_per_sim_at_8_workers_lattice']:.5f} s/sim  "
          f"(less work, 13.5 % LONGER -- the pessimistic bracket)")
    print(f"    {b['workers']} workers, 33-run pilot     "
          f"{b['sec_per_sim_at_8_workers_pilot']:.3f} s/sim  "
          f"(PRE-library-trim; 17.4x too slow)")
    print(f"    serial, uniform box draws     {b['sec_per_sim_serial_uniform']:.3f} s/sim  (session 17)")
    print(f"    serial, policy trajectory     {b['sec_per_sim_serial_trajectory']:.3f} s/sim  (session 17)")
    print(f"    {b['workers']} workers, isolated evals    "
          f"{b['sec_per_sim_at_8_workers_session_17']:.3f} s/sim  "
          f"({b['speedup_at_8_session_17']:.2f}x, session 17 -- does NOT transfer)")
    print()
    print(f"  budget per run  {b['budget_sims_per_run']} simulations "
          f"(the x-axis; held across every method and rung)")
    print(f"  replicates      " + ", ".join(f"{k} {v}" for k, v in b["replicates"].items()))
    print()
    print(f"  FULLY CROSSED (3 rungs x {len(b['replicates'])} methods x 2 screen arms):")
    print(f"    {b['fully_crossed_sims']:,} sims = "
          f"{b['fully_crossed_hours_at_8']:.1f} h  "
          f"-> at the MEASURED rate this now FITS; the remaining cuts are "
          f"epistemic and structural, not budgetary")
    print()
    print(f"  ALLOCATED:")
    for blk in b["blocks"]:
        print(f"    {blk['problem']:<3} {blk['method']:<8}"
              f"{'+screen' if blk['prescreen'] else '       '}  "
              f"{blk['replicates']:>3} seeds x {blk['budget_sims']} = "
              f"{blk['replicates'] * blk['budget_sims']:>6,} sims")
    print("    " + "-" * 52)
    print(f"    {'TOTAL':<20} {b['n_runs']:>3} runs         "
          f"{b['total_sims']:>6,} sims")
    print()
    print(f"    {b['hours_pessimistic']:.2f} h  at the lattice sweep's rate "
          f"(the pessimistic bracket)")
    print(f"    {b['hours_optimistic']:.2f} h  at the interp sweep's rate "
          f"(what this is sized to)")
    print()
    print("  " + b["library_trim_note"].replace(". ", ".\n  "))
    print()


def print_prescreen(r: dict, margins: Sequence[dict],
                    alphas: Sequence[dict]) -> None:
    print("\n" + "=" * 78)
    print("7e THE PIVOTAL EXPERIMENT -- does physics alone solve this?")
    print("=" * 78)
    print(f"  calibration set: {r['n']} simulated designs "
          f"(robust_geometry_data.csv, session 11, already paid for)")
    print(f"  {r['n_interior_peak']} have an interior peak; "
          f"{r['n_no_interior_peak']} do not (G44's population)")
    print()
    print("  THE G60 CALIBRATION -- only k is fitted, from the measured boost")
    print(f"    {'alpha':>6} {'peaking bias':>13} {'f_peak MdAPE':>13}  (the "
          f"independent check)")
    for a in alphas:
        mark = "  <- chosen" if abs(a["k_alpha"] - PS.K_ALPHA) < 1e-9 else (
            "  <- sec 6 verbatim" if abs(a["k_alpha"] - 1.0) < 1e-9 else "")
        print(f"    {a['k_alpha']:>6.3f} {a['peaking_bias_db']:>+12.3f} dB "
              f"{100 * a['f_peak_mdape_global']:>12.2f} %{mark}")
    print()
    print("  PREDICTOR ACCURACY at the chosen operating point")
    print(f"    f_peak MdAPE, global               {100 * r['f_peak_mdape_global']:6.2f} %")
    print(f"    f_peak MdAPE, 0.5-5 GHz            {100 * r['f_peak_mdape_band']:6.2f} %"
          f"   (n = {r['n_band']}; the region near the decision boundary)")
    print(f"    f_peak p90 APE                     {100 * r['f_peak_p90_ape_global']:6.2f} %")
    print(f"    peaking median |error|             {r['peaking_mae_db']:6.3f} dB")
    print()
    print("  THE SCREEN -- what it rejects for free, and what it wrongly loses")
    print(f"    {'widen (oct/dB)':>15} {'free rej':>9} {'false rej':>11} "
          f"{'eff. yield':>11} {'lift':>7}")
    for m in margins:
        mark = ("  <- chosen"
                if (abs(m["margin_oct"] - PS.MARGIN_OCT) < 1e-9
                    and abs(m["margin_db"] - PS.MARGIN_DB) < 1e-9) else "")
        print(f"    {m['margin_oct']:>7.2f}/{m['margin_db']:<7.2f} "
              f"{100 * m['free_rejection_rate']:>8.1f}% "
              f"{100 * m['false_rejection_rate']:>9.2f}% "
              f"({m['n_false_rejected']:>2}) "
              f"{100 * m['effective_yield']:>9.1f}% {m['yield_lift']:>6.2f}x{mark}")
    print()
    print(f"    S3 base rate over the box          {100 * r['s3_base_rate']:6.2f} %")
    print(f"    S3 rate among ACCEPTED designs     {100 * r['effective_yield']:6.2f} %"
          f"   <- 7e's threshold is 50 %")
    print(f"    G44 population rejected for free   "
          f"{100 * r['g44_free_rejection_rate']:6.2f} %"
          f"   ({r['n_no_interior_peak'] - r['n_g44_accepted']} of "
          f"{r['n_no_interior_peak']})")
    print()
    verdict = ("FIRES" if r["effective_yield"] > 0.50 else "DOES NOT FIRE")
    print(f"  >>> 7e's loud verdict {verdict}: effective yield "
          f"{100 * r['effective_yield']:.1f} % against the 50 % threshold.")
    if r["effective_yield"] <= 0.50:
        print("  >>> Physics does NOT solve the nominal problem. It removes "
              f"{100 * r['free_rejection_rate']:.0f} % of the box for free and")
        print(f"  >>> multiplies the yield by {r['yield_lift']:.2f}x, which is a "
              "real saving and not a solution.")
        zero = next((m for m in margins
                     if m["margin_oct"] == 0.0 and m["margin_db"] == 0.0), None)
        if zero is not None:
            print("  >>> READ THE WIDENING TABLE BEFORE QUOTING THIS. The "
                  "screen CAN be pushed above 50 %")
            print(f"  >>> ({100 * zero['effective_yield']:.1f} % at zero "
                  f"widening) but only by discarding "
                  f"{100 * zero['false_rejection_rate']:.0f} % of the feasible "
                  f"designs. A rejected")
            print("  >>> design is gone from the run; a false acceptance costs "
                  "one simulation. Not symmetric.")
    print()


def print_sweep(out: dict, label: str = "SWEEP") -> None:
    """7c + 7h, on one screen. Simulations are the headline; wall clock is a
    secondary column, because only one of the two is immune to G71."""
    a = out["analysis"]
    print("\n" + "=" * 78)
    print(f"7c/7h {label} RESULTS")
    print("=" * 78)
    print(f"  {out['total_sims_including_discarded']:,} simulations including "
          f"the discarded warm-up and the control, "
          f"{out['wall_s'] / 60:.1f} min wall")
    c = out.get("control")
    if c:
        print(f"  TIMING CONTROL ({c['config']}): warm-up "
              f"{c['warmup_sec_per_sim']:.3f} s/sim -> control "
              f"{c['control_sec_per_sim']:.3f} s/sim, ratio {c['ratio']:.3f} "
              f"(limit {c['limit'][0]}-{c['limit'][1]})")
        print(f"  -> {'TIMING VOID; repeat the sweep, do not adjust it'if c['timing_void'] else 'clean'}")
    print()
    print("  ANYTIME CURVE -- best reward at the budget, median over seeds")
    print(f"  {'group':<20} {'n':>3} {'median':>9} {'95% CI':>20} "
          f"{'invalid':>8} {'screened':>9} {'s/sim':>7} {'model s':>8}")
    print("  " + "-" * 92)
    for k in sorted(a["groups"]):
        g = a["groups"][k]
        m, lo, hi = g["final"]
        print(f"  {k:<20} {g['n_seeds']:>3} {m:>9.3f} "
              f"[{lo:>8.3f},{hi:>8.3f}] {100 * g['invalid_rate']:>7.1f}% "
              f"{g['screened_out']:>9} {g['sec_per_sim']:>7.2f} "
              f"{g['model_s']:>8.1f}")
    print()
    print("  SIMULATIONS TO FIRST FEASIBLE -- CENSORED DATA, read all three "
          "columns")
    print(f"  {'group':<20} {'found/seeds':>12} {'median|found':>13} "
          f"{'95% CI':>20}")
    print("  " + "-" * 70)
    for k in sorted(a["groups"]):
        cz = a["groups"][k]["censored"]
        med = ("--" if cz["median_conditional"] is None
               else f"{cz['median_conditional']:.1f}")
        ci = ("--" if cz["ci_lo_conditional"] is None
              else f"[{cz['ci_lo_conditional']:.1f},{cz['ci_hi_conditional']:.1f}]")
        print(f"  {k:<20} {cz['n_found']:>5}/{cz['n_seeds']:<6} {med:>13} "
              f"{ci:>20}")
    print("    The median is CONDITIONAL on having found one. Censored seeds "
          "are NOT")
    print("    substituted with the budget, with infinity, or dropped from a "
          "mean.")
    print()
    ceil = next((g.get("reward_ceiling") for g in a["groups"].values()
                 if g.get("reward_ceiling") is not None), None)
    if ceil is not None:
        print(f"  SIMULATIONS TO THE REWARD CEILING (+{ceil:.5f}) -- also "
              f"censored")
        print("    The ceiling is a property of the `ac dec 50 1meg 100g` grid, "
              "not of the circuit:")
        print(f"    the nearest grid point to the target is "
              f"{nearest_grid_offset_octaves(math.sqrt(SPEC_F_PEAK_HZ_RANGE[0] * SPEC_F_PEAK_HZ_RANGE[1])):.5f} "
              f"octaves away, and S3_f_peak is the binding row.")
        print(f"  {'group':<20} {'reached/seeds':>14} {'median|reached':>15} "
              f"{'95% CI':>20}")
        print("  " + "-" * 72)
        for k in sorted(a["groups"]):
            cz = a["groups"][k]["censored_ceiling"]
            med = ("--" if cz["median_conditional"] is None
                   else f"{cz['median_conditional']:.1f}")
            ci = ("--" if cz["ci_lo_conditional"] is None
                  else f"[{cz['ci_lo_conditional']:.1f},{cz['ci_hi_conditional']:.1f}]")
            print(f"  {k:<20} {cz['n_found']:>6}/{cz['n_seeds']:<7} "
                  f"{med:>15} {ci:>20}")
        print()
    print("  RANKING -- only where the intervals do not overlap (7h)")
    for prob, rows in a["ranking"].items():
        print(f"    {prob}:")
        for r in rows:
            sep = r["separable_from_next"]
            tag = ("" if sep is None else
                   ("  > (separable)" if sep else
                    "  ~ NOT SEPARABLE AT THIS SAMPLE SIZE"))
            print(f"      {r['group']:<20} {r['median_final']:>9.3f} "
                  f"[{r['ci'][0]:.3f}, {r['ci'][1]:.3f}]{tag}")
    print()
    print("  " + a["multiple_comparisons"].replace(". ", ".\n  "))
    print()


def print_designer() -> None:
    d = DESIGNER_BASELINE
    print("\n" + "=" * 78)
    print("7d THE DESIGNER BASELINE -- a reconstruction, not a run")
    print("=" * 78)
    print(f"  source        {d['source']}")
    print(f"  quoted        \"{d['sims_quoted']}\" -> {d['sims_low']}-{d['sims_high']} simulations")
    print(f"  produced      {d['n_s3_meeting_found']} S3-meeting configurations")
    print(f"  on            {d['problem_solved']}")
    print(f"  NOT comparable to any rung: {d['caveat']}")
    print()


def _save(obj: dict, path: Path) -> None:
    """TRACKED, not gitignored (G49): the write-up quotes numbers from it."""
    path.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    print(f"wrote {path}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", action="store_true", help="7a. No SPICE.")
    ap.add_argument("--prescreen", action="store_true", help="7e. No SPICE.")
    ap.add_argument("--designer", action="store_true", help="7d's row.")
    ap.add_argument("--pilot", action="store_true",
                    help="a small real sweep: validates the harness end to end")
    ap.add_argument("--sweep", action="store_true", help="the full run")
    ap.add_argument("--analyse", type=Path, default=None,
                    help="re-analyse a run log (the recovery path; "
                         "works on a PARTIAL log)")
    ap.add_argument("--pilot-budget", type=int, default=40)
    ap.add_argument("--pilot-reps", type=int, default=3)
    ap.add_argument("--pilot-methods", type=str,
                    default="uniform,lhs,grid,cmaes,gp_bo,ppo")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--tag", type=str, default="",
                    help="suffix for the artifact names, so two sweeps can "
                         "coexist (e.g. --tag lattice writes "
                         "baselines_run_lattice.jsonl). The A/B that measures "
                         "what the interpolated objective bought needs both "
                         "logs side by side, and a run that overwrites its own "
                         "control is not a control.")
    ap.add_argument("--interp", action="store_true",
                    help="score the SUB-GRID peak instead of the dec-50 "
                         "lattice one (G74). Applies to every job in the run, "
                         "including the warm-up and the timing control, and is "
                         "recorded in the log header.")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if not any((args.budget, args.prescreen, args.designer, args.pilot,
                args.sweep, args.analyse)):
        ap.error("choose at least one stage; see the module docstring")

    # G95 in one line: `--tag` exists so two sweeps can coexist, and a
    # summary file that ignores it is a third writer sharing one path. The
    # suffix is computed HERE, before any stage runs, so every artifact this
    # invocation writes carries it.
    suffix = f"_{args.tag}" if args.tag else ""

    results: dict = {}
    if args.budget:
        b = budget_report()
        print_budget(b)
        results["budget"] = b
    if args.prescreen:
        r = PS.accuracy()
        m = PS.margin_scan()
        a = PS.alpha_scan((0.80, 0.85, 0.90, 0.95, 1.00))
        print_prescreen(r, m, a)
        results["prescreen"] = {"accuracy": r, "margin_scan": m,
                                "alpha_scan": a}
    if args.designer:
        print_designer()
        results["designer"] = DESIGNER_BASELINE
    if args.analyse:
        out = analyse_log(args.analyse)
        out["total_sims_including_discarded"] = sum(r["n_sims"]
                                                    for r in out["runs"])
        out["wall_s"] = sum(r["wall_s"] for r in out["runs"])
        print_sweep(out, f"RE-ANALYSIS of {args.analyse.name}")
        results["analysis"] = {"control": out["control"],
                               "analysis": out["analysis"],
                               "n_runs": len(out["runs"]),
                               "source": str(args.analyse)}

    if args.pilot:
        ms = [m.strip() for m in args.pilot_methods.split(",") if m.strip()]
        alloc = tuple(Allocation("P1", m, s, args.pilot_reps,
                                 args.pilot_budget)
                      for s in (False, True) for m in ms)
        # G95 again: `baselines_pilot.jsonl` is TRACKED and its 457 valid rows
        # are the re-fit population BASELINES.md sec 5 points at. `--tag` has
        # to reach this writer too, or a smoke test overwrites a dataset.
        out = sweep(alloc, log_path=HERE / f"baselines_pilot{suffix}.jsonl",
                    workers=args.workers, ac_peak_interp=args.interp,
                    out_path=HERE / f"baselines_pilot_results{suffix}.json")
        print_sweep(out, "PILOT")
        results["pilot"] = {"control": out["control"],
                            "analysis": out["analysis"],
                            "wall_s": out["wall_s"],
                            "total_sims_including_discarded":
                                out["total_sims_including_discarded"]}
    if args.sweep:
        out = sweep(workers=args.workers, ac_peak_interp=args.interp,
                    log_path=HERE / f"baselines_run{suffix}.jsonl",
                    out_path=HERE / f"baselines_results{suffix}.json")
        print_sweep(out, "SWEEP")
        results["sweep"] = {"control": out["control"],
                            "analysis": out["analysis"],
                            "wall_s": out["wall_s"],
                            "total_sims_including_discarded":
                                out["total_sims_including_discarded"]}

    if results:
        _save(results, args.out or (HERE / f"baselines_summary{suffix}.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
