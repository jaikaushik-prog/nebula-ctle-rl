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

#: A proposer is `(f_peak_hz, peaking_db) -> u | None`. `None` means "no
#: proposal", which is a legitimate answer (an empty design pool, a policy that
#: has not been trained) and must degrade to the plain search rather than raise.
Proposer = Callable[[float, float], Optional[np.ndarray]]


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
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
