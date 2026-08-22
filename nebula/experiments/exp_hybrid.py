"""
experiments/exp_hybrid.py — **propose first, fall back to the search. Stage 0 of
`NEXT_AGENT_SAC.md` §4.**

WHAT THIS IS
-------------
One request in, one design out, by the cheapest route that works:

    request -> proposer says `u`            0 SPICE (library) / 1 forward pass (policy)
            -> evaluate it on the screen    len(screen) decks, 4 today
            -> feasible?  deliver it.       total: 4 decks
               otherwise: run TODAY'S CMA-ES search, unchanged.

`exp_coverage.py` is the search; this file wraps it. **Nothing about the search
is reimplemented here** — the fallback is a call to `exp_coverage.solve_request`,
so there is exactly one CMA-ES path in this project and one place it can be
wrong (`CLAUDEwa.md` §8 rule 9).

WHY STAGE 0 EXISTS AT ALL, AND WHY IT COMES BEFORE ANY LEARNING CODE
---------------------------------------------------------------------
`NEXT_AGENT_SAC.md` §4: *"Each stage is independently useful... Why first: it
builds the measurement harness and the no-downside guarantee before any new
learning code exists. If SAC never works, this still produces the amortisation
curve with the library as proposer."*

The deliverable's claim is *"fewer search spaces, lowest design time"*, and the
honest form of that claim is not "RL beats CMA-ES" — it is an **amortisation
curve**: simulations-per-request falling as the proposer gets better. This file
is the instrument that measures that curve. Run with the library as proposer it
produces the **control**; run later with a SAC policy it produces the treatment,
against the same requests, the same screen, the same verification and the same
artifact schema.

THE SAFETY PROPERTY, STATED PRECISELY RATHER THAN GENEROUSLY
-------------------------------------------------------------
The brief calls it *"coverage cannot get worse"*. What is actually true, and the
difference matters:

* If the proposal is infeasible on the screen, the request is handed to
  `solve_request` with the **same** target, screen, budget and seed that
  `exp_coverage._run` would have handed it. Same code, same inputs, same answer.
* The one input that CAN differ is `archive` — the designs this sweep has
  already delivered, which `choose_start` re-probes as seeds. An accepted
  proposal puts its design in the archive, where the pure coverage run would
  have put the search's winner instead. So a fallback request is bit-identical
  **given the same archive**, not unconditionally.

That is a real caveat and it is written here rather than discovered later. It is
also bounded: the archive only ever holds designs that were good enough to
deliver, and `choose_start` **measures** every seed with the same 2-deck probe
before ranking it, so a worse archive entry is not preferred — it is probed and
rejected.

WHY THE PROPOSAL IS SCORED ON THE LIVE SCREEN, NOT ON `EDGE4_MANDATED`
----------------------------------------------------------------------
The brief's step 2 says `evaluate_at_points(u, EDGE4_MANDATED, ...)`. This file
uses `screen.points` instead, which **starts equal to `EDGE4_MANDATED`** and
grows only when the screen's own self-check catches it being optimistic. Reason:
the search is graded on the live screen, so scoring the proposal on a different
(smaller) set would give the proposal an easier bar than the fallback it is
being compared against — two definitions of "does this design pass the screen",
which is this repo's third named failure mode (G32). Accepting on a superset is
the conservative direction.

WHAT IS COUNTED AND WHAT IS NOT
--------------------------------
`n_sims` is **SPICE decks, and it is the sum of both paths** — the proposal's
decks plus, if it fell through, the search's. A wrapper that reported only the
path that won would understate the cost of exactly the requests that are
expensive, in a project whose headline claim is a ratio of simulation counts
(session 22u found this file's neighbour understating itself 6x).

The 135-point verification is **not** in `n_sims`, matching
`exp_coverage.verify_request`, which does not charge it either. Verification is
a compliance measurement made once per delivered design, not part of the search
budget, and `n_verify_points` records it separately so the two are never added
up by accident.

    python -m nebula.experiments.exp_hybrid --proposals             # cheap 64-deck scan, no search
    python -m nebula.experiments.exp_hybrid --topk 8                # 512-deck scan: how DEEP must it look?
    python -m nebula.experiments.exp_hybrid --run
    python -m nebula.experiments.exp_hybrid --run --proposer none   # the ablation
    python -m nebula.experiments.exp_hybrid --analyse
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np

import nebula.rl.reward_v1 as R
from nebula.experiments import exp_coverage as C
from nebula.experiments import search_score as SS
from nebula.experiments.adaptive_screen import (
    EDGE4_MANDATED,
    AdaptiveScreen,
    evaluate_at_points,
)
from nebula.rl.contract import design_id, sizing_from_u

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "hybrid_results.json"
RUN_LOG = HERE / "hybrid_run.jsonl"
#: **A separate file, deliberately.** `--proposals` is a partial measurement (it
#: runs no search and verifies nothing), and writing it into `RESULTS` would put
#: a file with no coverage number where a reader expects one — G113's shape with
#: the concurrency removed and the ambiguity left in.
PROPOSAL_SCAN = HERE / "hybrid_proposal_scan.json"
#: **A third file, for the same reason again (G113).** The top-K scan is a
#: different measurement of a different proposer; writing it into
#: `PROPOSAL_SCAN` would silently overwrite the k=1 result that entry 31's
#: OUTCOME quotes, which is G113's exact shape. `scan_topk` writes only this.
TOPK_SCAN = HERE / "hybrid_topk_scan.json"

#: A proposer is `(f_peak_hz, peaking_db) -> u | None`. `None` means "no
#: proposal", which is a legitimate answer (an empty design pool, a policy that
#: has not been trained) and must degrade to the plain search rather than raise.
Proposer = Callable[[float, float], Optional[np.ndarray]]

#: A candidate source is `(f_peak_hz, peaking_db, k) -> [u, ...]`, best first.
#: **Not a `Proposer`, deliberately.** A `Proposer` commits to one answer for
#: free; a source offers several and lets the caller pay to choose between them.
#: Keeping them as separate types is what stops the top-K measurement's deck
#: spend from being booked as a `Proposer`'s zero.
CandidateSource = Callable[[float, float, int], list]

#: How many library candidates `scan_topk` scores per request by default.
#: 8 * 4 decks * 16 requests = 512 decks, ~12 min. Chosen because one run at
#: k=8 yields the whole hit-rate-vs-k curve for k=1..8 (the rank of the first
#: feasible candidate is recorded), so there is no reason to run k=2 or k=4
#: separately, and its k=1 slice re-measures the committed entry-31 result as a
#: built-in consistency check.
DEFAULT_TOPK = 8


def library_proposer(f_peak_hz: float, peaking_db: float) -> Optional[np.ndarray]:
    """**Zero simulations.** The single best already-simulated design for this
    request, by both requested axes.

    This is `exp_coverage.library_candidates(..., k=1)` and deliberately not a
    reimplementation: the ranking (each axis divided by its own tolerance, the
    worse of the two deciding) is the one `choose_start` already uses, so the
    control proposer and the search's own seeding agree by construction instead
    of by coincidence.

    **A consequence worth stating before the run, because it bounds what stage 0
    can possibly show:** `choose_start` already probes the top
    `N_LIBRARY_SEEDS = 4` library candidates as search seeds. So this proposer
    cannot suggest anything the fallback search would not have looked at. The
    only thing it can do is **short-circuit** — deliver at 4 decks a design the
    search would have spent its budget refining. That is the whole of stage 0's
    claim, and it is a cost claim, not a coverage claim.
    """
    cands = C.library_candidates(float(f_peak_hz), float(peaking_db), k=1)
    return None if not cands else np.asarray(cands[0], dtype=float)


def null_proposer(f_peak_hz: float, peaking_db: float) -> Optional[np.ndarray]:
    """Proposes nothing. **The ablation**: with this, the wrapper is
    `exp_coverage` plus an artifact schema, and any coverage difference between
    the two is a defect in this file rather than a result."""
    return None


PROPOSERS: dict = {"library": library_proposer, "none": null_proposer}


def library_candidates_k(f_peak_hz: float, peaking_db: float,
                         k: int) -> list:
    """The best `k` already-simulated designs for this request, best first.

    **A wrapper on `exp_coverage.library_candidates`, which is NOT modified.**
    That function is also what `choose_start` uses to seed the search, so
    changing its ranking in place would change the fallback search as well and
    silently break comparability with the 13 718-deck baseline every published
    coverage number was measured against. Wrap, do not replace.

    `library_proposer` is the `k=1` special case of this and stays as its own
    function so the committed control cannot drift.
    """
    return list(C.library_candidates(float(f_peak_hz), float(peaking_db),
                                     k=int(k)))


def null_candidates(f_peak_hz: float, peaking_db: float, k: int) -> list:
    """Offers nothing. The ablation, matching `null_proposer`."""
    return []


CANDIDATE_SOURCES: dict = {"library": library_candidates_k,
                           "none": null_candidates}


@dataclass
class HybridResult:
    """One request, and which route answered it.

    The verification fields are NOT duplicated here. `request` carries the
    `exp_coverage.RequestResult` that whichever path produced, verified by
    `exp_coverage.verify_request` — the same record, the same verifier and the
    same 45/135 split as the coverage sweep, so the two artifacts are
    comparable row for row.
    """

    index: int
    peaking_db: float
    f_peak_hz: float
    proposer: str
    #: `"proposal"`, `"search"`, or `"none"` if nothing was evaluated at all.
    which_path: str
    proposal_made: bool
    proposal_accepted: bool
    #: Decks spent scoring the proposal (0 if none was made).
    n_sims_proposal: int
    #: Decks spent in the fallback: `choose_start`'s probes plus CMA-ES.
    n_sims_search: int
    #: **The sum of both.** Pinned by a test.
    n_sims: int
    wall_s: float
    proposal_reward: Optional[float] = None
    proposal_search_score: Optional[float] = None
    proposal_feasible: Optional[bool] = None
    proposal_worst_point: Optional[str] = None
    proposal_worst_spec: Optional[str] = None
    proposal_reason: Optional[str] = None
    proposal_design_id: Optional[str] = None
    #: 135 when the delivered design was verified, else 0. **Never added to
    #: `n_sims`** — see the module docstring.
    n_verify_points: int = 0
    request: dict = field(default_factory=dict)


def propose_then_search(peaking_db: float, f_peak_hz: float,
                        screen: AdaptiveScreen,
                        proposer: Proposer = library_proposer,
                        budget: int = C.BUDGET_DESIGN_EVALS,
                        seed: int = 0, log=None,
                        archive: Optional[Sequence[Sequence[float]]] = None,
                        index: int = 0,
                        proposer_name: str = "library",
                        ) -> tuple[HybridResult, Optional[object], Optional[object]]:
    """Answer one request by proposal if possible, by search if not.

    Returns `(hybrid, request_result, best_eval)`. The last two are what
    `exp_coverage.verify_request` needs, handed back rather than verified here so
    that verification stays optional exactly as it is in the coverage sweep.
    """
    t0 = time.time()

    u0 = None
    try:
        u0 = proposer(float(f_peak_hz), float(peaking_db))
    except Exception as exc:                                    # noqa: BLE001
        # **A proposer that raises must not lose the request.** The whole point
        # of the fallback is that the expensive path is always available; a
        # broken policy is a cost regression, not a coverage regression.
        if log is not None:
            log.write(json.dumps({"event": "proposer_failed",
                                  "index": index, "error": repr(exc)}) + "\n")
            log.flush()

    prop_ev = None
    n_prop = 0
    if u0 is not None:
        prop_ev = evaluate_at_points(u0, screen.points,
                                     target_f_peak_hz=float(f_peak_hz),
                                     target_peaking_db=float(peaking_db),
                                     specs=R.V6_SPECS)
        n_prop = int(prop_ev.n_sims)
        if log is not None:
            log.write(json.dumps({
                "event": "proposal", "index": index,
                "proposer": proposer_name,
                "target_peaking_db": float(peaking_db),
                "target_f_peak_hz": float(f_peak_hz),
                "u": list(prop_ev.u), "n_sims": n_prop,
                "ok": prop_ev.ok, "reward": prop_ev.reward,
                # The same rank score the search steers on, computed the same
                # way, so the two paths' numbers are in one scale (rule 9).
                "search_score": SS.score_design_eval(prop_ev, R.V6_SPECS),
                "feasible": prop_ev.feasible,
                "worst_point": prop_ev.worst_point,
                "worst_spec": prop_ev.worst_spec,
                "peaking_db": prop_ev.peaking_db,
                "f_peak_hz": prop_ev.f_peak_hz,
                "reason": prop_ev.reason}) + "\n")
            log.flush()

    common = dict(
        index=int(index), peaking_db=float(peaking_db),
        f_peak_hz=float(f_peak_hz), proposer=proposer_name,
        proposal_made=u0 is not None,
        n_sims_proposal=n_prop)
    if prop_ev is not None:
        common.update(
            proposal_reward=float(prop_ev.reward),
            proposal_search_score=float(SS.score_design_eval(prop_ev,
                                                             R.V6_SPECS)),
            proposal_feasible=bool(prop_ev.feasible),
            proposal_worst_point=prop_ev.worst_point,
            proposal_worst_spec=prop_ev.worst_spec,
            proposal_reason=prop_ev.reason,
            proposal_design_id=design_id(
                sizing_from_u(np.asarray(prop_ev.u, dtype=float))))

    # ── the cheap path ──────────────────────────────────────────────────────
    if prop_ev is not None and prop_ev.feasible:
        res = C.RequestResult(
            peaking_db=float(peaking_db), f_peak_hz=float(f_peak_hz),
            solved_on_screen=True, n_sims=n_prop, n_design_evals=1,
            wall_s=time.time() - t0)
        res.u = list(prop_ev.u)
        res.design_id = common["proposal_design_id"]
        res.screen_reward = prop_ev.reward
        res.screen_search_score = common["proposal_search_score"]
        res.screen_worst_point = prop_ev.worst_point
        res.screen_worst_spec = prop_ev.worst_spec
        res.delivered_peaking_db = prop_ev.peaking_db
        res.delivered_f_peak_hz = prop_ev.f_peak_hz
        hyb = HybridResult(which_path="proposal", proposal_accepted=True,
                           n_sims_search=0, n_sims=n_prop,
                           wall_s=time.time() - t0, **common)
        return hyb, res, prop_ev

    # ── the fallback: TODAY'S pipeline, called and not copied ───────────────
    res, best = C.solve_request(float(peaking_db), float(f_peak_hz), screen,
                                budget=budget, seed=seed, log=log,
                                archive=archive)
    n_search = int(res.n_sims)
    # **The reported cost is both paths.** `solve_request` knows nothing about
    # the proposal, so the addition happens here, once.
    res.n_sims = n_prop + n_search
    hyb = HybridResult(which_path=("search" if res.u is not None else "none"),
                       proposal_accepted=False, n_sims_search=n_search,
                       n_sims=n_prop + n_search, wall_s=time.time() - t0,
                       **common)
    return hyb, res, best


# ─────────────────────────────────────────────────────────────────────────────
# The sweep.
# ─────────────────────────────────────────────────────────────────────────────


def run(budget: int = C.BUDGET_DESIGN_EVALS,
        peakings: Sequence[float] = C.PEAKING_REQUESTS,
        freqs: Sequence[float] = C.FREQ_REQUESTS,
        verify: bool = True, proposer: str = "library") -> dict:
    from nebula.experiments.runlock import hold

    if proposer not in PROPOSERS:
        raise ValueError(f"unknown proposer {proposer!r}; "
                         f"have {sorted(PROPOSERS)}")
    with hold("hybrid", meta={"budget_design_evals": budget,
                              "proposer": proposer}):
        return _run(budget, peakings, freqs, verify, proposer)


def _run(budget, peakings, freqs, verify, proposer_name) -> dict:
    from nebula.experiments.runlock import stamp

    t0 = time.time()
    fn = PROPOSERS[proposer_name]
    screen = AdaptiveScreen(EDGE4_MANDATED)
    out_rows: list[HybridResult] = []
    archive: list = []
    # **The same request grid as `exp_coverage`, in the same order.** Not a new
    # one: a coverage number measured on a different grid is not comparable to
    # the 7/16 this is trying to beat, and building a second grid here is how
    # two definitions of "the 16 requests" would start.
    requests = [(pk, f) for pk in peakings for f in freqs]

    with RUN_LOG.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "event": "start", "budget_design_evals": budget,
            "proposer": proposer_name,
            "spec_set": list(R.V6_SPECS), "n_requests": len(requests),
            "peaking_requests": list(peakings), "freq_requests": list(freqs),
            "screen": [p.label for p in screen.points]}) + "\n")
        for i, (pk, f) in enumerate(requests):
            print(f"[{i + 1}/{len(requests)}] request: {pk:.1f} dB @ "
                  f"{f / 1e9:.3f} GHz  (screen has {screen.n_points} points)",
                  flush=True)
            hyb, res, best = propose_then_search(
                pk, f, screen, proposer=fn, budget=budget,
                # **`exp_coverage`'s seed formula, character for character.** A
                # fallback request must get the search it would have got.
                seed=C.BASE_SEED + i, log=fh, archive=archive, index=i,
                proposer_name=proposer_name)
            if hyb.proposal_accepted:
                print(f"      PROPOSAL ACCEPTED at {hyb.n_sims_proposal} decks"
                      f"  reward {hyb.proposal_reward:+.4f}", flush=True)
            elif hyb.proposal_made:
                print(f"      proposal rejected ({hyb.proposal_worst_spec}), "
                      f"falling back to the search", flush=True)
            if verify and res is not None and res.u is not None:
                C.verify_request(res, best, screen)
                hyb.n_verify_points = 135
            if res is not None:
                hyb.request = asdict(res)
                if res.u is not None:
                    archive.insert(0, list(res.u))
                    del archive[C.ARCHIVE_MAX:]
            out_rows.append(hyb)
            print(f"      {hyb.which_path:8s}  45-corner "
                  f"{hyb.request.get('n_pvt45_pass')}/"
                  f"{hyb.request.get('n_pvt45_total')}"
                  f"  135-point {hyb.request.get('n_full135_pass')}/135"
                  f"  |  {hyb.n_sims} decks "
                  f"({hyb.n_sims_proposal} + {hyb.n_sims_search})"
                  f", {hyb.wall_s / 60:.1f} min", flush=True)
            fh.write(json.dumps({"event": "request_done",
                                 **asdict(hyb)}) + "\n")
            fh.flush()

    rq = [r.request for r in out_rows]
    solved45 = sum(1 for q in rq if q.get("n_pvt45_pass") is not None
                   and q.get("n_pvt45_total")
                   and q["n_pvt45_pass"] == q["n_pvt45_total"])
    n_acc = sum(1 for r in out_rows if r.proposal_accepted)
    out = {
        "task": "hybrid: propose, then fall back to the search "
                "(NEXT_AGENT_SAC.md stage 0)",
        **stamp(),
        "proposer": proposer_name,
        "spec_set": list(R.V6_SPECS),
        "n_requests": len(requests),
        "n_proposals_made": sum(1 for r in out_rows if r.proposal_made),
        "n_proposals_accepted": n_acc,
        "n_solved_on_screen": sum(1 for q in rq
                                  if q.get("solved_on_screen")),
        "n_solved_pvt45": solved45,
        "n_solved_full135": sum(1 for q in rq
                                if q.get("n_full135_pass") == 135),
        "budget_design_evals": budget,
        # Three cost lines, never one. The split is the result.
        "total_sims": sum(r.n_sims for r in out_rows),
        "total_sims_proposal": sum(r.n_sims_proposal for r in out_rows),
        "total_sims_search": sum(r.n_sims_search for r in out_rows),
        "total_verify_points": sum(r.n_verify_points for r in out_rows),
        "mean_sims_per_request": (sum(r.n_sims for r in out_rows)
                                  / max(len(out_rows), 1)),
        "wall_clock_s": time.time() - t0,
        "screen_report": screen.report(),
        "requests": [asdict(r) for r in out_rows],
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def scan_proposals(peakings: Sequence[float] = C.PEAKING_REQUESTS,
                   freqs: Sequence[float] = C.FREQ_REQUESTS,
                   proposer: str = "library") -> dict:
    """Score every request's PROPOSAL on the screen and stop. No search.

    **`len(requests) * len(screen)` decks — 64 today, about 30 seconds.**

    Why this exists as its own mode rather than being read off a full sweep:

    * it answers the only question stage 0's control actually asks — *how often
      is the cheap proposal already good enough?* — for 0.5 % of the cost;
    * it is the instrument for stage 1. A SAC policy under development can be
      measured against the same 16 requests for 64 decks instead of ~90 minutes,
      which is the difference between checking a policy every iteration and
      checking it once;
    * it separates the two failure modes the reward keeps confusing. A proposal
      can be **infeasible** (measured, misses a row) or **unscorable** (the eye
      cannot be computed at that corner — G107). Those are different facts about
      a proposer and the aggregate reward hides which one it hit.

    It verifies nothing and delivers nothing, so it can never produce a coverage
    number and does not write `RESULTS`.
    """
    from nebula.experiments.runlock import hold, stamp

    if proposer not in PROPOSERS:
        raise ValueError(f"unknown proposer {proposer!r}; "
                         f"have {sorted(PROPOSERS)}")
    fn = PROPOSERS[proposer]
    screen = AdaptiveScreen(EDGE4_MANDATED)
    requests = [(pk, f) for pk in peakings for f in freqs]
    rows: list[dict] = []

    with hold("hybrid_proposal_scan", meta={"proposer": proposer}):
        t0 = time.time()
        for i, (pk, f) in enumerate(requests):
            u = None
            try:
                u = fn(float(f), float(pk))
            except Exception as exc:                            # noqa: BLE001
                rows.append({"index": i, "peaking_db": pk, "f_peak_hz": f,
                             "proposal_made": False, "error": repr(exc)})
                continue
            if u is None:
                rows.append({"index": i, "peaking_db": pk, "f_peak_hz": f,
                             "proposal_made": False, "n_sims": 0})
                continue
            ev = evaluate_at_points(u, screen.points,
                                    target_f_peak_hz=float(f),
                                    target_peaking_db=float(pk),
                                    specs=R.V6_SPECS)
            rows.append({
                "index": i, "peaking_db": float(pk), "f_peak_hz": float(f),
                "proposal_made": True, "n_sims": int(ev.n_sims),
                "u": list(ev.u),
                "design_id": design_id(sizing_from_u(
                    np.asarray(ev.u, dtype=float))),
                "ok": bool(ev.ok), "feasible": bool(ev.feasible),
                "reward": float(ev.reward),
                "search_score": float(SS.score_design_eval(ev, R.V6_SPECS)),
                # **The two failure modes, kept apart.** `n_scorable` is how
                # many screen points produced a number at all; a proposal that
                # is `ok=False` did not fail the specs, it could not be measured.
                "n_scorable": int(ev.n_scorable),
                "n_points": int(ev.n_points),
                "worst_point": ev.worst_point, "worst_spec": ev.worst_spec,
                "reason": ev.reason,
                "peaking_db_got": ev.peaking_db,
                "f_peak_hz_got": ev.f_peak_hz})
            print(f"  [{i + 1:2d}/{len(requests)}] {pk:5.1f} dB @ "
                  f"{f / 1e9:.3f} GHz  ->  "
                  f"{'FEASIBLE' if ev.feasible else ('infeasible' if ev.ok else 'UNSCORABLE')}"
                  f"  reward {ev.reward:+9.4f}  scorable "
                  f"{ev.n_scorable}/{ev.n_points}", flush=True)

    made = [r for r in rows if r.get("proposal_made")]
    out = {
        "task": "hybrid stage 0: how often is the cheap proposal already "
                "good enough on the screen?",
        **stamp(),
        "proposer": proposer,
        "spec_set": list(R.V6_SPECS),
        "screen": [p.label for p in screen.points],
        "n_requests": len(requests),
        "n_proposals_made": len(made),
        "n_accepted": sum(1 for r in made if r.get("feasible")),
        "n_infeasible": sum(1 for r in made
                            if r.get("ok") and not r.get("feasible")),
        "n_unscorable": sum(1 for r in made if not r.get("ok")),
        "total_sims": sum(int(r.get("n_sims") or 0) for r in rows),
        "wall_clock_s": time.time() - t0,
        "requests": rows,
    }
    PROPOSAL_SCAN.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def scan_topk(peakings: Sequence[float] = C.PEAKING_REQUESTS,
              freqs: Sequence[float] = C.FREQ_REQUESTS,
              source: str = "library", k: int = DEFAULT_TOPK) -> dict:
    """Score the top `k` library candidates per request. **`16*k*4` decks.**

    WHY THIS EXISTS, AND WHY IT IS NOT THE THING IT REPLACES
    ---------------------------------------------------------
    The k=1 scan (entry 31) accepted 1 of 16 proposals; 14 of the other 15 were
    unscorable and **all 14 on output-swing compression**. The obvious next move
    was to re-rank the library on swing headroom as well as on the two requested
    axes. That move is not available, and the reason is worth recording because
    it was asserted before it was checked:

    * **There is no swing field in the pool.** `spec_pool.REQUIRED_MEAS` carries
      `pair_margin_v` and `tail_margin_v`, which are DC operating-point headroom
      (`vds - vdsat`). The thing the screen actually rejects on is
      `vout_swing_v`, the **measured 1 dB compression point**, which comes from
      a swept simulation (`sky130_runner.measured_swing_pp_v`) and which
      deliberately refuses to fall back to a computed `4*I*RL`. They are
      different physical quantities and the pool only has the first.
    * **No nominal channel separates the outcomes anyway.** Every one of
      `pair_margin_v, tail_margin_v, g_dc_db, peaking_db, nyq_boost_db,
      inoise_vrms, power_w` overlaps between the accepted design and the 14
      failures. The accepted design has *less* pair margin than 12 of the 14 and
      *more* power than 13 of the 14. Pool rows are nominal (`tt/1.00/27C`); the
      failure is a corner phenomenon. A nominal predictor of a corner failure is
      not merely unfitted here, it is unfittable from this pool.
    * **n=1 in the positive class.** Any ranking rule fitted to one success is
      unfalsifiable. There is nothing to validate against.

    So this measures instead of predicting. It asks the question that does not
    need a model: **the library holds 2066-17478 in-tolerance candidates per
    request (median 4986); the k=1 scan tried exactly one of them. How many must
    it try before one survives the corners?**

    Informative in both directions, which is why it is worth 12 minutes:

    * a **high** hit rate means the library does hold corner-robust designs, the
      k=1 ranking was simply blind to them, and the measured rank distribution
      both bounds what any better ranking could achieve and supplies the
      labelled pass/fail candidates that a ranking could finally be fitted to;
    * a **low** hit rate means the library does not hold corner-robust designs
      at these targets at all. That kills the retrieval line cheaply and tells
      the SAC stage its proposer must **generate** rather than retrieve --
      which is a result about the deliverable, not a null.

    WHAT IS COUNTED
    ---------------
    Two deck numbers, never one, because they answer different questions:

    * `n_sims_measured` -- every candidate scored. What this scan costs.
    * `n_sims_deployed` -- what an early-exiting proposer would cost: candidates
      up to and including the first feasible one. This is the number that
      belongs in an amortisation claim, and it is smaller than the first.

    Reporting only the second would understate the experiment; reporting only
    the first would overstate the proposer. `exp_coverage`'s neighbour was
    caught understating itself 6x in session 22u by collapsing exactly this
    distinction.

    Verifies nothing and delivers nothing, so it can never produce a coverage
    number, and it writes `TOPK_SCAN` -- never `PROPOSAL_SCAN`, never `RESULTS`.
    """
    from nebula.experiments.runlock import hold, stamp

    if source not in CANDIDATE_SOURCES:
        raise ValueError(f"unknown candidate source {source!r}; "
                         f"have {sorted(CANDIDATE_SOURCES)}")
    if int(k) < 1:
        raise ValueError(f"k must be >= 1, got {k!r}")
    k = int(k)
    fn = CANDIDATE_SOURCES[source]
    screen = AdaptiveScreen(EDGE4_MANDATED)
    requests = [(pk, f) for pk in peakings for f in freqs]
    rows: list[dict] = []

    with hold("hybrid_topk_scan", meta={"source": source, "k": k}):
        t0 = time.time()
        for i, (pk, f) in enumerate(requests):
            try:
                cands = list(fn(float(f), float(pk), k))
            except Exception as exc:                            # noqa: BLE001
                rows.append({"index": i, "peaking_db": float(pk),
                             "f_peak_hz": float(f), "n_candidates": 0,
                             "accepted_rank": None, "n_sims_measured": 0,
                             "n_sims_deployed": 0, "candidates": [],
                             "error": repr(exc)})
                continue

            cand_rows: list[dict] = []
            accepted_rank: Optional[int] = None
            n_measured = 0
            n_deployed = 0
            for rank, u in enumerate(cands, start=1):
                try:
                    ev = evaluate_at_points(
                        np.asarray(u, dtype=float), screen.points,
                        target_f_peak_hz=float(f),
                        target_peaking_db=float(pk), specs=R.V6_SPECS)
                except Exception as exc:                        # noqa: BLE001
                    # **One bad candidate must not lose the other 500 decks.**
                    # Same reasoning as `propose_then_search`'s proposer guard: a
                    # component that breaks is a cost regression, not a lost
                    # measurement. The row is kept so the gap is visible rather
                    # than silently shortening the candidate list.
                    cand_rows.append({"rank": rank, "u": list(
                        np.asarray(u, dtype=float)), "error": repr(exc),
                        "n_sims": 0})
                    print(f"  [{i + 1:2d}/{len(requests)}] rank {rank}: "
                          f"ERROR {exc!r}", flush=True)
                    continue
                n_measured += int(ev.n_sims)
                if accepted_rank is None:
                    # Early-exit accounting: a deployed proposer stops here, so
                    # it pays for this candidate and every one before it.
                    n_deployed += int(ev.n_sims)
                cand_rows.append({
                    "rank": rank, "n_sims": int(ev.n_sims), "u": list(ev.u),
                    "design_id": design_id(sizing_from_u(
                        np.asarray(ev.u, dtype=float))),
                    "ok": bool(ev.ok), "feasible": bool(ev.feasible),
                    "reward": float(ev.reward),
                    "search_score": float(SS.score_design_eval(ev, R.V6_SPECS)),
                    "n_scorable": int(ev.n_scorable),
                    "n_points": int(ev.n_points),
                    "worst_point": ev.worst_point, "worst_spec": ev.worst_spec,
                    "reason": ev.reason,
                    "peaking_db_got": ev.peaking_db,
                    "f_peak_hz_got": ev.f_peak_hz})
                verdict = ("FEASIBLE" if ev.feasible
                           else ("infeasible" if ev.ok else "UNSCORABLE"))
                print(f"  [{i + 1:2d}/{len(requests)}] {pk:5.1f} dB @ "
                      f"{f / 1e9:.3f} GHz  rank {rank}/{len(cands)}  -> "
                      f"{verdict:>10s}  reward {ev.reward:+9.4f}  scorable "
                      f"{ev.n_scorable}/{ev.n_points}", flush=True)
                if ev.feasible and accepted_rank is None:
                    accepted_rank = rank
                    # **Scored anyway, not stopped.** The remaining candidates
                    # are what make the rank distribution and the k=1..k curve
                    # measurable; `n_sims_deployed` is what records that a real
                    # proposer would have stopped. `accepted_rank` is the FIRST
                    # feasible rank -- guarding on `is None` is load-bearing, not
                    # defensive: without it a later pass overwrites the earlier
                    # one and every deployment cost is reported too high.
            rows.append({
                "index": i, "peaking_db": float(pk), "f_peak_hz": float(f),
                "n_candidates": len(cands),
                "accepted_rank": accepted_rank,
                "n_sims_measured": n_measured,
                "n_sims_deployed": n_deployed,
                "candidates": cand_rows})

    made = [r for r in rows if r["n_candidates"] > 0]
    # The curve. `accepted_at_k[j]` is how many of the requests would have been
    # answered by a proposer allowed j+1 tries -- monotone by construction, and
    # its last entry is `n_accepted`.
    accepted_at_k = [sum(1 for r in rows
                         if r["accepted_rank"] is not None
                         and r["accepted_rank"] <= j + 1)
                     for j in range(k)]
    scored = [c for r in rows for c in r["candidates"] if "error" not in c]
    out = {
        "task": "hybrid stage 0: how DEEP into the library must the proposer "
                "look before a candidate survives the corners?",
        **stamp(),
        "source": source,
        "k": k,
        "spec_set": list(R.V6_SPECS),
        "screen": [p.label for p in screen.points],
        "n_requests": len(requests),
        "n_requests_with_candidates": len(made),
        "n_candidates_scored": len(scored),
        "n_accepted": accepted_at_k[-1] if accepted_at_k else 0,
        #: Per-CANDIDATE buckets, not per-request: the three-way partition of
        #: every candidate actually scored. G107 -- unscorable is not failing.
        "n_cand_feasible": sum(1 for c in scored if c["feasible"]),
        "n_cand_infeasible": sum(1 for c in scored
                                 if c["ok"] and not c["feasible"]),
        "n_cand_unscorable": sum(1 for c in scored if not c["ok"]),
        "accepted_at_k": accepted_at_k,
        "total_sims_measured": sum(r["n_sims_measured"] for r in rows),
        "total_sims_deployed": sum(r["n_sims_deployed"] for r in rows),
        "wall_clock_s": time.time() - t0,
        "requests": rows,
    }
    TOPK_SCAN.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report_scan(d: dict) -> None:
    n = d["n_requests"]
    print()
    print("=" * 78)
    print(f"PROPOSAL SCAN (proposer: {d['proposer']}) -- {n} requests, "
          f"{d['total_sims']} decks, {d['wall_clock_s']:.0f} s")
    print("=" * 78)
    print(f"  proposals made                   {d['n_proposals_made']:3d} / {n}")
    print(f"  ACCEPTED (feasible on screen)    {d['n_accepted']:3d} / {n}"
          f"   <- answered for {len(EDGE4_MANDATED)} decks")
    print(f"  measured but infeasible          {d['n_infeasible']:3d} / {n}")
    print(f"  UNSCORABLE (eye not computable)  {d['n_unscorable']:3d} / {n}"
          f"   <- not the same as failing (G107)")
    print()
    print(f"  {'#':>2s}  {'request':>18s}  {'delivered':>18s}  {'verdict':>11s}"
          f"  {'reward':>10s}  {'scorable':>8s}")
    for r in d["requests"]:
        if not r.get("proposal_made"):
            print(f"  {r['index'] + 1:2d}  {r['peaking_db']:5.1f} dB @ "
                  f"{r['f_peak_hz'] / 1e9:.3f} GHz  {'(no proposal)':>18s}")
            continue
        got = ("-" if r.get("peaking_db_got") is None else
               f"{r['peaking_db_got']:.2f} dB @ "
               f"{(r.get('f_peak_hz_got') or 0) / 1e9:.3f}G")
        verdict = ("FEASIBLE" if r["feasible"]
                   else ("infeasible" if r["ok"] else "UNSCORABLE"))
        print(f"  {r['index'] + 1:2d}  {r['peaking_db']:5.1f} dB @ "
              f"{r['f_peak_hz'] / 1e9:.3f} GHz  {got:>18s}  {verdict:>11s}"
              f"  {r['reward']:+10.4f}  {r['n_scorable']:d}/{r['n_points']:d}")


def _report_topk(d: dict) -> None:
    n = d["n_requests"]
    k = d["k"]
    print()
    print("=" * 78)
    print(f"TOP-K SCAN (source: {d['source']}, k={k}) -- {n} requests, "
          f"{d['n_candidates_scored']} candidates, "
          f"{d['total_sims_measured']} decks, "
          f"{d['wall_clock_s'] / 60:.1f} min")
    print("=" * 78)
    print(f"  requests ANSWERED by some candidate  {d['n_accepted']:3d} / {n}")
    print(f"  candidates: {d['n_cand_feasible']} feasible, "
          f"{d['n_cand_infeasible']} infeasible, "
          f"{d['n_cand_unscorable']} unscorable (G107: not the same thing)")
    print()
    print("  HIT RATE vs HOW MANY TRIES THE PROPOSER GETS")
    print(f"  {'k':>3s}  {'answered':>9s}  {'of':>3s}   {'decks if deployed':>18s}")
    for j, c in enumerate(d["accepted_at_k"], start=1):
        # What a proposer capped at j tries would have spent: every request
        # pays min(j, its own stopping rank) * len(screen).
        spent = sum(min(j, (r["accepted_rank"] or j)) * len(d["screen"])
                    for r in d["requests"] if r["n_candidates"])
        print(f"  {j:>3d}  {c:>9d}  {n:>3d}   {spent:>12d} decks")
    print()
    print(f"  decks measured {d['total_sims_measured']} "
          f"| decks an early-exiting proposer would spend "
          f"{d['total_sims_deployed']}")
    print()
    print(f"  {'#':>2s}  {'request':>18s}  {'first pass':>10s}  "
          f"{'worst spec at rank 1':>26s}")
    for r in d["requests"]:
        c1 = (r["candidates"] or [{}])[0]
        rank = ("-" if r["accepted_rank"] is None
                else f"rank {r['accepted_rank']}")
        print(f"  {r['index'] + 1:2d}  {r['peaking_db']:5.1f} dB @ "
              f"{r['f_peak_hz'] / 1e9:.3f} GHz  {rank:>10s}  "
              f"{str(c1.get('worst_spec') or c1.get('reason') or '-'):>26s}")


def _report(d: dict) -> None:
    n = d["n_requests"]
    print()
    print("=" * 78)
    print(f"HYBRID (proposer: {d['proposer']}) -- {n} requests, "
          f"{d['total_sims']} SPICE decks, {d['wall_clock_s'] / 60:.1f} min")
    print("=" * 78)
    print(f"  proposals accepted               "
          f"{d['n_proposals_accepted']:3d} / {d['n_proposals_made']}"
          f"   <- answered at {len(EDGE4_MANDATED)} decks")
    print(f"  solved on the search screen      {d['n_solved_on_screen']:3d} / {n}")
    print(f"  MANDATED 45-corner PVT grid      {d['n_solved_pvt45']:3d} / {n}"
          f"   <- the competition's requirement")
    print(f"  135-point load-robustness grid   {d['n_solved_full135']:3d} / {n}"
          f"   <- this project's extra axis")
    print()
    print(f"  decks: {d['total_sims_proposal']} proposal "
          f"+ {d['total_sims_search']} search = {d['total_sims']}"
          f"   ({d['mean_sims_per_request']:.1f} per request)")
    print(f"  verification: {d['total_verify_points']} points, NOT included "
          f"in the deck count above")
    print()
    print(f"  {'#':>2s}  {'request':>18s}  {'path':>8s}  {'45-corner':>11s}  "
          f"{'135-pt':>7s}  {'decks':>6s}")
    for r in d["requests"]:
        q = r.get("request") or {}
        print(f"  {r['index'] + 1:2d}  {r['peaking_db']:5.1f} dB @ "
              f"{r['f_peak_hz'] / 1e9:.3f} GHz  {r['which_path']:>8s}  "
              f"{str(q.get('n_pvt45_pass')) + '/' + str(q.get('n_pvt45_total')):>11s}  "
              f"{str(q.get('n_full135_pass')) + '/135':>7s}  {r['n_sims']:6d}")
    print()
    print("  AMORTISATION (decks per request, in order) -- the stage 3 figure's "
          "y-axis")
    print("   " + "  ".join(f"{r['n_sims']}" for r in d["requests"]))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--budget", type=int, default=C.BUDGET_DESIGN_EVALS)
    ap.add_argument("--proposer", default="library", choices=sorted(PROPOSERS))
    ap.add_argument("--proposals", action="store_true",
                    help="score every request's PROPOSAL on the screen and "
                         "stop: no search, no verification (~64 decks, ~30 s). "
                         "Writes hybrid_proposal_scan.json, never "
                         "hybrid_results.json -- it carries no coverage number.")
    ap.add_argument("--topk", nargs="?", type=int, const=DEFAULT_TOPK,
                    default=None, metavar="K",
                    help=f"score the top K library candidates per request "
                         f"instead of only the best one (default "
                         f"{DEFAULT_TOPK} = 512 decks, ~12 min). Measures how "
                         f"DEEP the proposer must look; writes "
                         f"hybrid_topk_scan.json only.")
    ap.add_argument("--source", default="library",
                    choices=sorted(CANDIDATE_SOURCES),
                    help="candidate source for --topk")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the 135-point verification (and the screen "
                         "self-check that rides on it)")
    a = ap.parse_args(argv)
    if a.run:
        _report(run(budget=a.budget, verify=not a.no_verify,
                    proposer=a.proposer))
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    elif a.proposals:
        _report_scan(scan_proposals(proposer=a.proposer))
    elif a.topk is not None:
        _report_topk(scan_topk(source=a.source, k=a.topk))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
