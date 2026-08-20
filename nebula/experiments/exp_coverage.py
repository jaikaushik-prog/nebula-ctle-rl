"""
experiments/exp_coverage.py — **the deliverable's actual success criterion:
for every spec a judge might request, does the framework return a design?**

WHY THIS IS THE CENTREPIECE AND THE SINGLE-DESIGN SEARCHES WERE NOT
--------------------------------------------------------------------
The competition deliverable is *"a framework that **takes target specs as
input**, seamlessly integrates with a spice simulator — outputs the final
schematic and resulting specs"*. **The framework is the deliverable; a design
is evidence that it works.** Every search in this project so far has optimised
ONE point — the centre of S3's window — and reported how compliant that one
design is. A judge will type their own numbers, and a tool that only answers
one question is not the tool that was asked for.

Most of the spec sheet is a fixed constraint (HD3, noise, power, area, eye,
PVT: identical for every user). Exactly two entries are a REQUEST:

    HF peaking boost     3 - 12 dB
    peak frequency       1.25 - 2.5 GHz

so "given specifications" is a 2-D request, and the number that matters is

    **of N requests spanning the full range, for how many does the framework
    return a design that passes every spec at every mandated PVT corner?**

That number has never been measured.

WHAT MAKES IT MEASURABLE ONLY NOW
----------------------------------
Two things had to be fixed first, both session 23:

1. **The peaking request was being discarded.** `margins()` accepted
   `target_peaking_db` and ignored it, so one design scored 8.999984 against
   targets of 3, 5, 7.5, 10 and 12 dB identically (`SPEC_CONDITIONED.md` §0).
   Coverage measured on that reward would have been a measurement of nothing:
   every request would "succeed" with the same circuit. `V5_SPECS` fixes it.
2. **The screen the search is graded on was optimistic**, by up to +10.03 —
   enough to place an infeasible design in the feasible band
   (`adaptive_screen`). Coverage measured through it would have counted
   failures as successes.

THE SELF-CHECK IS FREE, AND THAT IS THE DESIGN
-----------------------------------------------
Every request's winner has to be verified on the full grid anyway. So the
verification IS the screen audit: compare the screen's verdict against the
truth, and if the truth is worse, **append the offending point to the screen
for every subsequent request**. Sixteen requests therefore produce sixteen
independent audits of the screen at **zero extra simulation cost**, against the
three retrospective ones that justified it. A run in which the screen is never
extended is evidence FOR the screen, and is evidence only because the check ran.

WHY THE SPREAD PROBE SEEDS THE SEARCH RATHER THAN SCORING INSIDE IT
--------------------------------------------------------------------
`probe_spread` recovers a design's full 135-point f_peak excursion from **2
AC-only runs** (measured: exact to 5 decimals on both verified designs, 0.41 s
against ~50 s). The tempting use is to reject candidates mid-search and hand
back a cheap score. **That was rejected deliberately.** A probe scores 3 of the
12 rows, so its reward is systematically higher than a fully-evaluated
infeasible design's, and mixing the two biases the search toward whatever was
cheapest to evaluate — an objective that rewards not being measured. Rule 5's
shape, one level up. The probe is used where it is unambiguous: choosing the
CMA-ES starting point, and reporting.

    python -m nebula.experiments.exp_coverage --run
    python -m nebula.experiments.exp_coverage --analyse
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

import nebula.rl.reward_v1 as R
from nebula.experiments.adaptive_screen import (
    EDGE4,
    EDGE4_MANDATED,
    AdaptiveScreen,
    ScreenPoint,
    audit_screen,
    evaluate_at_points,
    probe_spread,
)
from nebula.rl.contract import N_ACTIONS, design_id, sizing_from_u

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "coverage_results.json"
RUN_LOG = HERE / "coverage_run.jsonl"

# ─────────────────────────────────────────────────────────────────────────────
# The request grid.
# ─────────────────────────────────────────────────────────────────────────────

#: Peaking requests, dB. The endpoints are S3's own band edges, inset by half a
#: tolerance so a request is not asking for something outside the constraint
#: the same spec imposes. Four values, evenly spaced in dB because that is the
#: unit the spec is written in.
PEAKING_REQUESTS: tuple[float, ...] = (4.0, 6.0, 8.0, 10.0)

#: Frequency requests, Hz. **Evenly spaced in OCTAVES, not in hertz** — S3's
#: window is exactly one octave and every frequency quantity in this project is
#: logarithmic, so a linear grid would sample the bottom of the window four
#: times as densely as the top. `1.25e9 * 2**k` for k = 0.15, 0.38, 0.62, 0.85:
#: inset from the edges by 0.15 octaves, because a request AT the edge is
#: unsatisfiable by construction the moment PVT moves the peak at all, and
#: measuring that would be measuring arithmetic rather than the framework.
FREQ_REQUESTS: tuple[float, ...] = tuple(
    1.25e9 * 2.0 ** k for k in (0.15, 0.38, 0.62, 0.85))

#: Design evaluations per request. Each costs `len(screen)` SPICE decks, so
#: the SPICE budget is `BUDGET_DESIGN_EVALS * 4` at the starting screen.
BUDGET_DESIGN_EVALS: int = 200

#: How many random candidates to probe when choosing a starting point. Each
#: costs 2 AC-only decks.
N_SEED_PROBES: int = 16

#: CMA-ES initial step. Larger than the joint search's 0.12 because this is a
#: fresh search per request rather than a refinement of a known design.
SIGMA0: float = 0.25

#: How many previously-solved designs to re-probe when seeding. Bounded so
#: the seeding cost does not grow with the sweep: 6 x 2 decks = 12.
ARCHIVE_MAX: int = 6

BASE_SEED: int = 23_0821


def spice_runs_for(n_design_evals: int, n_screen_points: int) -> int:
    """Design evaluations -> SPICE decks. **THE conversion (session 22u).**

    `BUDGET_DESIGN_EVALS` counts calls to the evaluator; each runs one deck per
    screen point. Session 22u found this project describing a 400-eval run as
    "400 simulations" when it cost 2400 decks — a 6x understatement in a
    project whose headline claim is a ratio of simulation counts.
    """
    return int(n_design_evals) * int(n_screen_points)


# ─────────────────────────────────────────────────────────────────────────────
# One request.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RequestResult:
    """What the framework did with one spec request."""

    peaking_db: float
    f_peak_hz: float
    solved_on_screen: bool
    design_id: Optional[str] = None
    u: Optional[list] = None
    screen_reward: Optional[float] = None
    screen_worst_point: Optional[str] = None
    screen_worst_spec: Optional[str] = None
    delivered_peaking_db: Optional[float] = None
    delivered_f_peak_hz: Optional[float] = None
    n_sims: int = 0
    n_design_evals: int = 0
    wall_s: float = 0.0
    seed_spread_oct: Optional[float] = None
    # -- filled by verification --
    verified: bool = False
    n_pvt45_pass: Optional[int] = None
    n_pvt45_total: Optional[int] = None
    pvt45_worst: Optional[float] = None
    n_full135_pass: Optional[int] = None
    full135_worst: Optional[float] = None
    n_unscorable: int = 0
    failing_rows: list = field(default_factory=list)
    audit: Optional[dict] = None
    reason: Optional[str] = None


class _Objective:
    """`method_cmaes`'s surface, scoring one spec request on the live screen."""

    def __init__(self, screen: AdaptiveScreen, target_f_peak_hz: float,
                 target_peaking_db: float, budget_design_evals: int, log):
        self.screen = screen
        self.tf = float(target_f_peak_hz)
        self.tp = float(target_peaking_db)
        self.budget = int(budget_design_evals)
        self.used = 0
        self.n_sims = 0
        self.log = log
        self.best = None

    def check_budget(self) -> None:
        from nebula.experiments.baselines import BudgetExhausted

        if self.used >= self.budget:
            raise BudgetExhausted(f"{self.used}/{self.budget} design evals")

    def evaluate(self, u):
        self.check_budget()
        self.used += 1
        ev = evaluate_at_points(u, self.screen.points,
                                target_f_peak_hz=self.tf,
                                target_peaking_db=self.tp,
                                specs=R.V6_SPECS)
        self.n_sims += ev.n_sims
        if self.log is not None:
            self.log.write(json.dumps({
                "i": self.used, "n_sims": self.n_sims,
                "target_peaking_db": self.tp, "target_f_peak_hz": self.tf,
                "u": list(ev.u), "ok": ev.ok, "reward": ev.reward,
                "feasible": ev.feasible, "worst_point": ev.worst_point,
                "worst_spec": ev.worst_spec, "peaking_db": ev.peaking_db,
                "f_peak_hz": ev.f_peak_hz, "reason": ev.reason}) + "\n")
            self.log.flush()
        if self.best is None or ev.reward > self.best.reward:
            self.best = ev
        return ev


def choose_start(target_f_peak_hz: float, target_peaking_db: float,
                 rng: np.random.Generator, n: int = N_SEED_PROBES,
                 archive: Optional[Sequence[Sequence[float]]] = None) -> tuple[Optional[np.ndarray], Optional[float], int]:
    """Probe `n` random candidates; start from the best `S3_f_peak` worst case.

    **Two AC-only decks each**, and the ranked quantity is not "spread" but
    `max_c |f_peak_oct - target_oct|` over the two probe points — which is
    exactly what the `S3_f_peak` row scores, since its margin is
    `TOL - max_c |...|`. Ranking on spread alone was the first attempt and it
    is wrong in a way worth recording: **spread ignores the request.** A design
    whose peak travels only 0.3 octaves but sits at 5 GHz has a superb spread
    and cannot serve any request in S3's window, and the first smoke run duly
    started from one. Centring and spread are one number here, and it is the
    number the objective already uses.

    Returns `(u, spread_oct, n_sims)` — `spread_oct` is still reported because
    it is what bounds the best achievable margin. `u` is `None` if every probe
    was unscorable, which is a real outcome and not an error.
    """
    tgt_oct = math.log2(float(target_f_peak_hz) / 2.5e9)
    best_u: Optional[np.ndarray] = None
    best_dev = float("inf")
    best_spread: Optional[float] = None
    n_sims = 0

    def _consider(u):
        nonlocal best_u, best_dev, best_spread, n_sims
        sp = probe_spread(u)
        n_sims += sp.n_sims
        if not sp.ok:
            return
        dev = max(abs(sp.lo_oct - tgt_oct), abs(sp.hi_oct - tgt_oct))
        if dev < best_dev:
            best_dev, best_u, best_spread = dev, np.asarray(u, float), sp.spread_oct

    # **The library first, and it costs ZERO simulations.** A measurement does
    # not know what it was aiming at, so the ~74 500 designs this project has
    # already simulated can be re-scored against a new request for free
    # (`SPEC_CONDITIONED.md`). This is the cheap-proposal tier: the library
    # says where to start, the probe checks it across PVT for 2 decks, and
    # CMA-ES spends the real budget from there. Starting from uniform random
    # was the first attempt; the smoke run's best of 12 random candidates had a
    # 1.375-octave excursion against a 1.000-octave window, i.e. the search
    # spent its budget walking out of a hole rather than refining.
    #
    # It is wrapped because the library is an ARTIFACT: if the pool logs are
    # absent this must degrade to random probing, not raise. A missing pool is
    # a worse start, not a wrong answer.
    try:
        from nebula.design import solve_library
        from nebula.rl.spec_dist import SpecTarget

        lib = solve_library(SpecTarget(peaking_db=float(target_peaking_db),
                                       f_peak_hz=float(target_f_peak_hz)))
        _consider(np.asarray(lib["u"], dtype=float))
    except Exception:                                           # noqa: BLE001
        pass

    # **Then every design this sweep has already produced.** Adjacent requests
    # have adjacent answers, so a solved neighbour is a far better start than
    # anything random -- and this is the amortisation the deliverable's "fewer
    # simulations than sweeping" claim actually rests on: the Nth request is
    # cheaper than the first BECAUSE of the first. Two decks to check each.
    for au in (archive or ()):
        _consider(np.asarray(au, dtype=float))

    for _ in range(n):
        _consider(rng.uniform(0.0, 1.0, N_ACTIONS))
    return best_u, best_spread, n_sims


def solve_request(peaking_db: float, f_peak_hz: float, screen: AdaptiveScreen,
                  budget: int = BUDGET_DESIGN_EVALS, seed: int = 0,
                  log=None, archive: Optional[Sequence[Sequence[float]]] = None
                  ) -> tuple[RequestResult, Optional[object]]:
    """Run the framework on one spec request. Returns (result, best eval)."""
    from nebula.experiments.baselines import BudgetExhausted, CmaConfig, method_cmaes

    t0 = time.time()
    rng = np.random.default_rng(seed)
    x0, spread, probe_sims = choose_start(f_peak_hz, peaking_db, rng,
                                          archive=archive)

    obj = _Objective(screen, f_peak_hz, peaking_db, budget, log)
    try:
        method_cmaes(obj, rng, CmaConfig(sigma0=SIGMA0,
                                         x0=(None if x0 is None else list(x0))))
    except BudgetExhausted:
        pass

    best = obj.best
    res = RequestResult(
        peaking_db=peaking_db, f_peak_hz=f_peak_hz,
        solved_on_screen=bool(best is not None and best.feasible),
        n_sims=obj.n_sims + probe_sims, n_design_evals=obj.used,
        wall_s=time.time() - t0, seed_spread_oct=spread)
    if best is None:
        res.reason = "no candidate was evaluated"
        return res, None
    res.u = list(best.u)
    res.design_id = design_id(sizing_from_u(np.asarray(best.u)))
    res.screen_reward = best.reward
    res.screen_worst_point = best.worst_point
    res.screen_worst_spec = best.worst_spec
    res.delivered_peaking_db = best.peaking_db
    res.delivered_f_peak_hz = best.f_peak_hz
    if not best.feasible:
        res.reason = best.reason or f"best on screen was infeasible ({best.worst_spec})"
    return res, best


# ─────────────────────────────────────────────────────────────────────────────
# Verification: the mandated 45 corners, and the load study on top of it.
# ─────────────────────────────────────────────────────────────────────────────


def verify_request(res: RequestResult, best, screen: AdaptiveScreen) -> None:
    """Verify one winner on the full grid, and AUDIT THE SCREEN with the result.

    **The 45-corner number and the 135-point number are reported separately and
    the difference is not cosmetic.** The competition mandates PVT — *"TT, SS,
    FF, SF, FS; VDD +/-5%; 0-125 C"* — which is 5 x 3 x 3 = **45 corners** and
    says nothing about load capacitance. The third axis is this project's own
    addition (`CL_RANGE.md`), a 5.7x uncertainty about a capacitance that is
    **fixed at layout and known to the designer**, not an operating condition.
    `CL_RANGE.md` §9 said so on 2026-08-06, before any of these results existed:
    *"screen cl like a PVT corner is a conservative reading, and arguably too
    conservative... the yield it produces should be read as a lower bound on
    what a tunable part could achieve."*

    So: the 45-corner column is **compliance**, the 135-point column is
    **robustness characterisation**, and collapsing them in either direction
    would be dishonest in one direction and self-defeating in the other.
    """
    from nebula.experiments.exp_g4_verify import Candidate, verify_full

    if res.u is None:
        res.reason = res.reason or "nothing to verify"
        return
    cand = Candidate(design_id=res.design_id or "?", u=tuple(res.u),
                     role="coverage",
                     source=f"coverage/{res.peaking_db:.1f}dB@"
                            f"{res.f_peak_hz / 1e9:.3f}GHz",
                     claimed_reward=float(res.screen_reward or 0.0),
                     claimed_worst_point=res.screen_worst_point)
    out = verify_full(cand, ac_peak_interp=True)
    pts = out.get("points") or []
    if not pts:
        raise ValueError(f"verify_full returned no points for {res.design_id}")

    # Re-score every point against THIS request's targets and V5. `verify_full`
    # scores its own default spec set, which does not carry the request.
    rescored = _rescore(pts, res.f_peak_hz, res.peaking_db)
    loads = sorted({round(float(p["cl_f"]), 20) for p in pts})
    design_load = loads[len(loads) // 2]

    m45 = [r for r in rescored if abs(r["cl_f"] - design_load) < 1e-20]
    res.n_pvt45_total = len(m45)
    res.n_pvt45_pass = sum(1 for r in m45 if r["feasible"])
    res.pvt45_worst = min((r["reward"] for r in m45
                           if r["reward"] is not None), default=None)
    res.n_full135_pass = sum(1 for r in rescored if r["feasible"])
    res.full135_worst = min((r["reward"] for r in rescored
                             if r["reward"] is not None), default=None)
    # Counted, never folded into the reward (G107).
    res.n_unscorable = sum(1 for r in rescored if r.get("unscorable"))
    rows: set = set()
    for r in rescored:
        rows.update(r["failed"])
    res.failing_rows = sorted(rows)
    res.verified = True

    if best is not None:
        # **AUDIT AGAINST THE GRID THE SCREEN TARGETS, NOT A DIFFERENT ONE.**
        # The screen is `EDGE4_MANDATED` -- four corners at the DESIGN load --
        # because D8 searches the mandated 45-corner grid. Auditing it against
        # all 135 points asks it to predict the worst case of a load sweep it
        # deliberately does not cover, so it "missed" on 4 of the first 5
        # requests and every point it was told to add was at 14 fF or 78 fF.
        # The screen was right and the reference was wrong: a self-check that
        # grades against the wrong grid manufactures failures and then
        # "corrects" them, growing the screen by one point per request and
        # inflating the cost of every request after it.
        audit = audit_screen(best, m45)
        added = screen.extend(audit)
        res.audit = {"was_predictive": audit.was_predictive,
                     "error": audit.error,
                     "full_worst_label": audit.full_worst_label,
                     "points_added": added}


def _rescore(points: Sequence[dict], target_f_peak_hz: float,
             target_peaking_db: float) -> list[dict]:
    """Re-score `verify_full` points against one request, on `V6_SPECS`.

    Uses the per-point margins the artifact already carries and adds the two
    request-dependent rows. **`S3_f_peak` is recomputed from
    `f_peak_oct_scored`** — the interpolated peak (G108) — because the
    artifact's own `S3_f_peak` margin was computed against a different target.
    """
    out = []
    for p in points:
        if not p.get("ok"):
            # **`reward=None`, NOT a large negative number — G107, and this
            # code committed the gotcha the same session it was written down.**
            # The first version scored an unscorable point at -1e3, and
            # `audit_screen` then compared the screen's -1.0 against it and
            # reported the screen "optimistic by +999.0", appending a bogus
            # point to the screen and contaminating every request after it.
            # "Cannot be scored" and "fails" are different verdicts: an
            # unscorable point is counted (below, and it still blocks
            # compliance) but it is not a NUMBER the screen can be audited
            # against, because the screen has no number to compare either.
            out.append({"cl_f": float(p["cl_f"]), "reward": None,
                        "feasible": False, "unscorable": True,
                        "failed": ["UNSCORABLE"],
                        "corner": p["corner"], "vdd_scale": p["vdd_scale"],
                        "temp_c": p["temp_c"]})
            continue
        m = dict(p.get("margins") or {})
        f_oct = p.get("f_peak_oct_scored")
        pk = p.get("peaking_db_scored")
        if f_oct is None or pk is None:
            raise ValueError(
                f"point {p.get('corner')} carries no scored peak; refusing to "
                f"re-score against an instrument that is not stated (G108)")
        tgt_oct = math.log2(float(target_f_peak_hz) / 2.5e9)
        m["S3_f_peak"] = R.TOL["S3_f_peak"] - abs(float(f_oct) - tgt_oct)
        m["S3_peaking_match"] = (R.TOL["S3_peaking_match"]
                                 - abs(float(pk) - float(target_peaking_db)))
        rows = [k for k in R.V6_SPECS if k in m]
        failed = [k for k in rows if m[k] < 0.0]
        s = {k: max(0.0, -m[k] / R.TOL[k]) for k in rows}
        if failed:
            reward = -sum(min(v, 1.0) for v in s.values())
        else:
            reward = (R.feasible_bonus(len(R.V6_SPECS))
                      + min(m[k] / R.TOL[k] for k in rows))
        out.append({"cl_f": float(p["cl_f"]), "reward": float(reward),
                    "feasible": not failed, "failed": failed,
                    "corner": p["corner"], "vdd_scale": p["vdd_scale"],
                    "temp_c": p["temp_c"], "margins": m})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# The run.
# ─────────────────────────────────────────────────────────────────────────────


def run(budget: int = BUDGET_DESIGN_EVALS,
        peakings: Sequence[float] = PEAKING_REQUESTS,
        freqs: Sequence[float] = FREQ_REQUESTS,
        verify: bool = True) -> dict:
    t0 = time.time()
    screen = AdaptiveScreen(EDGE4_MANDATED)
    results: list[RequestResult] = []
    #: Designs this sweep has already produced, newest first, capped so the
    #: seeding cost stays bounded. Each entry costs 2 AC-only decks to check.
    archive: list = []
    requests = [(pk, f) for pk in peakings for f in freqs]

    with RUN_LOG.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "event": "start", "budget_design_evals": budget,
            "spec_set": list(R.V6_SPECS), "n_requests": len(requests),
            "peaking_requests": list(peakings),
            "freq_requests": list(freqs),
            "screen": [p.label for p in screen.points]}) + "\n")
        for i, (pk, f) in enumerate(requests):
            print(f"[{i + 1}/{len(requests)}] request: {pk:.1f} dB @ "
                  f"{f / 1e9:.3f} GHz  (screen has {screen.n_points} points)",
                  flush=True)
            res, best = solve_request(pk, f, screen, budget=budget,
                                      seed=BASE_SEED + i, log=fh,
                                      archive=archive)
            if verify and res.u is not None:
                verify_request(res, best, screen)
            results.append(res)
            if res.u is not None:
                archive.insert(0, list(res.u))
                del archive[ARCHIVE_MAX:]
            print(f"      screen {'FEASIBLE' if res.solved_on_screen else 'infeasible'}"
                  f"  reward {res.screen_reward if res.screen_reward is None else round(res.screen_reward, 4)}"
                  f"  |  45-corner {res.n_pvt45_pass}/{res.n_pvt45_total}"
                  f"  135-point {res.n_full135_pass}/135"
                  f"  |  {res.n_sims} sims, {res.wall_s / 60:.1f} min",
                  flush=True)
            fh.write(json.dumps({"event": "request_done",
                                 **asdict(res)}) + "\n")
            fh.flush()

    solved45 = sum(1 for r in results if r.n_pvt45_pass is not None
                   and r.n_pvt45_total and r.n_pvt45_pass == r.n_pvt45_total)
    solved135 = sum(1 for r in results if r.n_full135_pass == 135)
    out = {
        "task": "spec coverage: does the framework answer every request?",
        "spec_set": list(R.V6_SPECS),
        "n_requests": len(requests),
        "n_solved_on_screen": sum(1 for r in results if r.solved_on_screen),
        "n_solved_pvt45": solved45,
        "n_solved_full135": solved135,
        "budget_design_evals": budget,
        "total_sims": sum(r.n_sims for r in results),
        "wall_clock_s": time.time() - t0,
        "screen_report": screen.report(),
        "requests": [asdict(r) for r in results],
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(d: dict) -> None:
    n = d["n_requests"]
    print()
    print("=" * 78)
    print(f"SPEC COVERAGE — {n} requests, {d['total_sims']} SPICE runs, "
          f"{d['wall_clock_s'] / 60:.1f} min")
    print("=" * 78)
    print(f"  solved on the search screen      {d['n_solved_on_screen']:3d} / {n}")
    print(f"  MANDATED 45-corner PVT grid      {d['n_solved_pvt45']:3d} / {n}"
          f"   <- the competition's requirement")
    print(f"  135-point load-robustness grid   {d['n_solved_full135']:3d} / {n}"
          f"   <- this project's extra axis")
    print()
    print(f"  {'request':>18s}  {'delivered':>18s}  {'45-corner':>11s}  "
          f"{'135-pt':>7s}  {'sims':>6s}")
    for r in d["requests"]:
        got = ("—" if r["delivered_peaking_db"] is None else
               f"{r['delivered_peaking_db']:.2f} dB @ "
               f"{(r['delivered_f_peak_hz'] or 0) / 1e9:.3f}G")
        print(f"  {r['peaking_db']:5.1f} dB @ {r['f_peak_hz'] / 1e9:.3f} GHz  "
              f"{got:>18s}  "
              f"{str(r['n_pvt45_pass']) + '/' + str(r['n_pvt45_total']):>11s}  "
              f"{str(r['n_full135_pass']) + '/135':>7s}  {r['n_sims']:6d}")
    sr = d["screen_report"]
    print()
    print(f"  SCREEN SELF-CHECK: {sr['n_predictive']} of {sr['n_audits']} "
          f"audits found the screen predictive; "
          f"{sr['n_points']} points now in the screen "
          f"(started at {len(EDGE4_MANDATED)})")
    if sr["worst_error"] is not None:
        print(f"    worst optimism: {sr['worst_error']:+.6f}")
    for a in sr["audits"]:
        if not a["was_predictive"]:
            print(f"    MISSED at {a['full_worst_label']}: screen said "
                  f"{a['screen_worst']:+.6f}, truth {a['full_worst']:+.6f}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--budget", type=int, default=BUDGET_DESIGN_EVALS)
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the 135-point verification (and the screen "
                         "self-check that rides on it)")
    a = ap.parse_args(argv)
    if a.run:
        _report(run(budget=a.budget, verify=not a.no_verify))
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
