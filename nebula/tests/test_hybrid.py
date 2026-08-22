"""**Stage 0 of `NEXT_AGENT_SAC.md`: propose, then fall back to the search.**

The brief's gate for this stage, quoted: *"a test that the fallback fires when
the proposal is infeasible, and that reported `n_sims` is the sum of both
paths."* Both are here, plus the properties that make the stage's claim
checkable rather than asserted:

* the fallback is **`exp_coverage.solve_request`**, called and not copied, with
  `exp_coverage`'s own seed formula — otherwise "coverage cannot get worse" is a
  hope about two similar code paths rather than a statement about one;
* the proposal is scored on the **live screen**, not a smaller one, so it does
  not get an easier bar than the fallback it is compared against;
* the artifacts and the run lock are the hybrid's **own**, because a completed
  run silently overwrote a completed run on 2026-08-21 (G113);
* a proposer that returns `None` or raises **loses the cost saving, never the
  request**.

The **proposals-only scan** (`--proposals`) is covered separately at the bottom
of this file: it runs no search, writes its own artifact and its own run lock,
and keeps *accepted* / *infeasible* / *unscorable* as three counters rather than
one pass/fail column (G107).

**No SPICE anywhere in this file.** `evaluate_at_points` and `solve_request` are
monkeypatched with fixed records, which is what lets the wrapper's accounting be
pinned exactly rather than approximately.
"""

from __future__ import annotations

import contextlib
import inspect
import json
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pytest

from nebula.experiments import exp_coverage as C
from nebula.experiments import exp_hybrid as H
from nebula.experiments.adaptive_screen import EDGE4_MANDATED, AdaptiveScreen

U7 = [0.5] * 7


@dataclass
class _Ev:
    """The subset of `adaptive_screen.DesignEval` this wrapper reads."""

    u: tuple = tuple(U7)
    ok: bool = True
    reward: float = -1.0
    feasible: bool = False
    n_sims: int = 4
    n_points: int = 4
    n_scorable: int = 4
    worst_point: Optional[str] = "ss/0.95/125C/46fF"
    worst_spec: Optional[str] = "S3_f_peak_match"
    reason: Optional[str] = None
    margins: dict = field(default_factory=dict)
    points: list = field(default_factory=list)
    peaking_db: Optional[float] = 6.0
    f_peak_hz: Optional[float] = 1.9e9
    power_w: Optional[float] = None
    hd3_nyq_dbc: Optional[float] = None
    eye_h_v: Optional[float] = None
    eye_w_ui: Optional[float] = None


def _screen() -> AdaptiveScreen:
    return AdaptiveScreen(EDGE4_MANDATED)


def _patch(monkeypatch, ev: Optional[_Ev], search_n_sims: int = 800,
           search_u=U7):
    """Replace both SPICE paths with records, and count the fallback's calls."""
    calls: dict = {"solve": 0, "evaluate": 0}

    def _eval(*a, **k):
        calls["evaluate"] += 1
        if ev is None:
            raise AssertionError("the proposal was evaluated when no proposal "
                                 "should have been made")
        return ev

    def _solve(pk, f, screen, budget=200, seed=0, log=None, archive=None):
        calls["solve"] += 1
        res = C.RequestResult(peaking_db=pk, f_peak_hz=f,
                              solved_on_screen=False, n_sims=search_n_sims,
                              n_design_evals=200, wall_s=1.0)
        res.u = None if search_u is None else list(search_u)
        res.screen_reward = -1.5
        calls["seed"] = seed
        calls["archive"] = archive
        return res, (None if search_u is None else _Ev(reward=-1.5))

    monkeypatch.setattr(H, "evaluate_at_points", _eval)
    monkeypatch.setattr(H.C, "solve_request", _solve)
    return calls


# ─────────────────────────────────────────────────────────────────────────────
# THE GATE, both halves.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_fallback_FIRES_when_the_proposal_is_infeasible(monkeypatch):
    """The stage's whole safety property. If this can fail silently, an
    unlucky proposer turns into lost coverage rather than a lost saving."""
    calls = _patch(monkeypatch, _Ev(feasible=False))
    hyb, res, best = H.propose_then_search(
        8.0, 1.627e9, _screen(), proposer=lambda f, p: np.asarray(U7))

    assert calls["solve"] == 1, "the search did not run on a rejected proposal"
    assert hyb.which_path == "search"
    assert hyb.proposal_made is True
    assert hyb.proposal_accepted is False
    assert res is not None and res.u is not None


def test_reported_n_sims_is_the_SUM_of_both_paths(monkeypatch):
    """The other half of the gate. A wrapper that reported only the winning
    path would understate exactly the requests that are expensive, in a project
    whose headline claim is a ratio of simulation counts."""
    _patch(monkeypatch, _Ev(feasible=False, n_sims=4), search_n_sims=800)
    hyb, res, _ = H.propose_then_search(
        8.0, 1.627e9, _screen(), proposer=lambda f, p: np.asarray(U7))

    assert hyb.n_sims_proposal == 4
    assert hyb.n_sims_search == 800
    assert hyb.n_sims == 804
    assert hyb.n_sims == hyb.n_sims_proposal + hyb.n_sims_search
    # And the coverage record handed to the verifier carries the same total, so
    # the two artifacts cannot disagree about what one request cost.
    assert res.n_sims == 804


def test_the_sum_holds_when_the_screen_has_GROWN(monkeypatch):
    """The proposal costs `len(screen)` decks, not the literal 4 in the brief.
    If the screen's self-check ever appends a point, a hard-coded 4 becomes an
    understatement that no test would catch."""
    _patch(monkeypatch, _Ev(feasible=False, n_sims=7), search_n_sims=250)
    hyb, res, _ = H.propose_then_search(
        4.0, 1.387e9, _screen(), proposer=lambda f, p: np.asarray(U7))
    assert (hyb.n_sims, res.n_sims) == (257, 257)


# ─────────────────────────────────────────────────────────────────────────────
# The cheap path.
# ─────────────────────────────────────────────────────────────────────────────


def test_an_accepted_proposal_SKIPS_the_search_entirely(monkeypatch):
    """The saving. 4 decks instead of ~800, and the search must not run at
    all — a wrapper that ran it anyway would measure nothing."""
    calls = _patch(monkeypatch, _Ev(feasible=True, reward=+14.2, n_sims=4))
    hyb, res, best = H.propose_then_search(
        6.0, 1.387e9, _screen(), proposer=lambda f, p: np.asarray(U7))

    assert calls["solve"] == 0, "the search ran despite a feasible proposal"
    assert hyb.which_path == "proposal"
    assert hyb.proposal_accepted is True
    assert hyb.n_sims == 4 and hyb.n_sims_search == 0
    assert res.solved_on_screen is True
    assert res.n_design_evals == 1
    assert res.screen_reward == pytest.approx(14.2)


def test_an_accepted_proposal_still_produces_a_VERIFIABLE_record(monkeypatch):
    """`verify_request` reads `u`, `design_id`, `screen_reward` and
    `screen_worst_point` off the record. A cheap path that produced a record the
    verifier cannot consume would deliver an unverified design, which is worse
    than spending the 800 decks."""
    _patch(monkeypatch, _Ev(feasible=True, reward=+14.2))
    _, res, _ = H.propose_then_search(
        6.0, 1.387e9, _screen(), proposer=lambda f, p: np.asarray(U7))

    for fld in ("u", "design_id", "screen_reward", "delivered_peaking_db",
                "delivered_f_peak_hz"):
        assert getattr(res, fld) is not None, f"{fld} is missing"
    sig = inspect.signature(C.verify_request)
    assert list(sig.parameters) == ["res", "best", "screen"]


# ─────────────────────────────────────────────────────────────────────────────
# A proposer is allowed to fail. A request is not.
# ─────────────────────────────────────────────────────────────────────────────


def test_a_proposer_returning_None_degrades_to_the_plain_search(monkeypatch):
    """An empty design pool or an untrained policy is a worse start, not a
    wrong answer — the same shape as `library_candidates` returning `[]`."""
    calls = _patch(monkeypatch, None, search_n_sims=800)
    hyb, res, _ = H.propose_then_search(
        8.0, 2.253e9, _screen(), proposer=H.null_proposer)

    assert calls["evaluate"] == 0, "a None proposal was evaluated anyway"
    assert calls["solve"] == 1
    assert hyb.proposal_made is False
    assert hyb.n_sims_proposal == 0
    assert hyb.n_sims == 800


def test_a_proposer_that_RAISES_does_not_lose_the_request(monkeypatch):
    """The expensive path is always available, so a broken policy is a cost
    regression and must not become a coverage regression."""
    calls = _patch(monkeypatch, None, search_n_sims=800)

    def _boom(f, p):
        raise RuntimeError("no checkpoint on disk")

    hyb, res, _ = H.propose_then_search(8.0, 2.253e9, _screen(),
                                        proposer=_boom)
    assert calls["solve"] == 1
    assert hyb.proposal_made is False and hyb.n_sims == 800
    assert res is not None


def test_the_null_proposer_really_proposes_nothing():
    """The ablation. With it, this wrapper is `exp_coverage` plus a schema, so
    any coverage difference between the two is a defect here and not a result."""
    assert H.null_proposer(1.7e9, 7.5) is None
    assert H.null_proposer(2.5e9, 12.0) is None


# ─────────────────────────────────────────────────────────────────────────────
# One search, one screen, one grid, one lock.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_search_is_CALLED_and_not_reimplemented():
    """Rule 9: exactly one definition. A second CMA-ES path here would be a
    second place the search can be wrong, and the reason "coverage cannot get
    worse" would stop being checkable."""
    src = inspect.getsource(H)
    assert "C.solve_request(" in src, "the fallback is not exp_coverage's search"
    for banned in ("method_cmaes", "CmaConfig", "BudgetExhausted"):
        assert banned not in src, (
            f"exp_hybrid references {banned!r}: the search is being rebuilt "
            f"here instead of called")


def test_the_fallback_gets_exp_COVERAGES_seed_formula():
    """`BASE_SEED + i`, character for character. A different seed means the
    fallback is not the run it is being compared against, and the safety
    property becomes a coincidence."""
    src = inspect.getsource(H._run)
    assert "seed=C.BASE_SEED + i" in src


def test_the_request_grid_is_exp_COVERAGES_grid():
    """A coverage number measured on a different grid is not comparable to the
    7/16 this exists to beat."""
    sig = inspect.signature(H.run)
    assert sig.parameters["peakings"].default is C.PEAKING_REQUESTS
    assert sig.parameters["freqs"].default is C.FREQ_REQUESTS
    src = inspect.getsource(H._run)
    assert "for pk in peakings for f in freqs" in src


def test_the_proposal_is_scored_on_the_LIVE_screen(monkeypatch):
    """Not on `EDGE4_MANDATED` directly. The search is graded on the live
    screen, so scoring the proposal on a smaller set would give it an easier
    bar than the fallback — two definitions of "passes the screen" (G32)."""
    seen: dict = {}

    def _eval(u, points, **k):
        seen["points"] = list(points)
        return _Ev(feasible=False)

    monkeypatch.setattr(H, "evaluate_at_points", _eval)
    monkeypatch.setattr(H.C, "solve_request",
                        lambda *a, **k: (C.RequestResult(
                            peaking_db=4.0, f_peak_hz=1.4e9,
                            solved_on_screen=False, n_sims=1), None))
    sc = _screen()
    sc.points = list(sc.points) + ["an_extra_point"]
    H.propose_then_search(4.0, 1.4e9, sc, proposer=lambda f, p: np.asarray(U7))
    assert seen["points"] == sc.points


def test_the_proposal_and_the_search_rank_on_the_SAME_scalar():
    """`_Objective` steers on `search_score.score_design_eval(ev, V6_SPECS)`.
    The proposal is logged with the same call, so the two paths' numbers are in
    one scale and the run log can be read as a single sequence."""
    hyb_src = inspect.getsource(H.propose_then_search)
    obj_src = inspect.getsource(C._Objective.evaluate)
    needle = "SS.score_design_eval(ev, R.V6_SPECS)"
    assert needle in obj_src
    assert "SS.score_design_eval(prop_ev, R.V6_SPECS)" in hyb_src


def test_the_hybrid_holds_its_OWN_run_lock():
    """Not `coverage`'s. Sharing a lock name would refuse to start alongside a
    coverage sweep for the wrong reason and, worse, would let a hybrid run and a
    coverage run believe they were the same experiment."""
    src = inspect.getsource(H.run)
    assert 'hold("hybrid"' in src
    assert 'hold("coverage"' not in src


def test_the_artifacts_do_not_collide_with_the_coverage_sweep():
    """G113: a completed run silently overwrote a completed run. Separate files
    are the cheapest possible defence and they only work if they are separate."""
    assert H.RESULTS != C.RESULTS
    assert H.RUN_LOG != C.RUN_LOG
    assert H.RESULTS.name == "hybrid_results.json"
    assert H.RUN_LOG.name == "hybrid_run.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# Cost accounting.
# ─────────────────────────────────────────────────────────────────────────────


def test_verification_points_are_NOT_folded_into_the_deck_count():
    """`exp_coverage` does not charge verification to `n_sims` either. Adding it
    here would make the amortisation curve incomparable to the coverage
    artifact, and it is a 135-point-per-request difference."""
    src = inspect.getsource(H._run)
    assert '"total_sims": sum(r.n_sims for r in out_rows)' in src
    assert '"total_verify_points": sum(r.n_verify_points for r in out_rows)' in src
    fields = set(H.HybridResult.__dataclass_fields__)
    assert {"n_sims", "n_sims_proposal", "n_sims_search",
            "n_verify_points"} <= fields


def test_the_cost_split_is_reported_as_THREE_lines_not_one():
    """Session 22u found this file's neighbour describing 400 design
    evaluations as "400 simulations" when they cost 2400 decks. The split is the
    result here, so it is in the artifact rather than derivable from it."""
    src = inspect.getsource(H._report)
    for line in ("total_sims_proposal", "total_sims_search",
                 "total_verify_points", "mean_sims_per_request"):
        assert line in src


def test_the_library_proposer_costs_ZERO_simulations():
    """It is the control, and a control that spends decks measures something
    else. Checked by source, because a stray import of the device layer is how
    that would stop being true."""
    src = inspect.getsource(H.library_proposer)
    for banned in ("run_point", "sky130_runner", "evaluate_at_points",
                   "ngspice", "probe_spread"):
        assert banned not in src, f"the library proposer references {banned!r}"
    assert "C.library_candidates(" in src, (
        "the library proposer must reuse exp_coverage's ranking, not restate it")


def test_the_hybrid_record_does_not_COPY_the_coverage_record():
    """The 45/135 verification fields live on `RequestResult` and are reached
    through `request`. A second copy on `HybridResult` is how the two would
    drift apart (G32), and one of them would be the one a figure was drawn
    from."""
    fields = set(H.HybridResult.__dataclass_fields__)
    for owned_by_coverage in ("n_pvt45_pass", "n_pvt45_total", "pvt45_worst",
                              "n_full135_pass", "failing_rows", "audit"):
        assert owned_by_coverage not in fields
    assert "request" in fields


def test_a_search_that_returns_nothing_is_recorded_as_such(monkeypatch):
    """`solve_request` can return `u=None` when every candidate was unscorable.
    That is a real outcome (G107) and must not be filed as a delivered design."""
    _patch(monkeypatch, _Ev(feasible=False), search_u=None)
    hyb, res, best = H.propose_then_search(
        10.0, 2.5e9, _screen(), proposer=lambda f, p: np.asarray(U7))
    assert hyb.which_path == "none"
    assert res.u is None and best is None


# ─────────────────────────────────────────────────────────────────────────────
# The proposals-only scan (--proposals): a partial measurement that runs NO
# search, writes its OWN artifact, and keeps the three verdicts apart.
# ─────────────────────────────────────────────────────────────────────────────


def _patch_scan(monkeypatch, tmp_path, evals):
    """Point the scan at throwaway paths, feed it a fixed sequence of evals, and
    turn the search into a tripwire: `scan_proposals` must never reach it.

    The library proposer is replaced with one that always returns a design, so
    exactly one eval is drawn per request and the eval sequence length is the
    grid size the caller chose.
    """
    seq = iter(evals)
    calls = {"solve": 0}

    def _tripwire(*a, **k):
        calls["solve"] += 1
        return (C.RequestResult(peaking_db=0.0, f_peak_hz=0.0,
                                solved_on_screen=False, n_sims=1,
                                n_design_evals=1, wall_s=1.0), None)

    monkeypatch.setattr(H, "evaluate_at_points", lambda *a, **k: next(seq))
    monkeypatch.setitem(H.PROPOSERS, "library", lambda f, p: np.asarray(U7))
    monkeypatch.setattr(H.C, "solve_request", _tripwire)
    monkeypatch.setattr(H, "PROPOSAL_SCAN", tmp_path / "scan.json")
    monkeypatch.setattr(H, "RESULTS", tmp_path / "results_SHOULD_NOT_EXIST.json")
    monkeypatch.setattr("nebula.experiments.runlock.hold",
                        lambda *a, **k: contextlib.nullcontext())
    return calls


def test_the_scan_runs_NO_search(monkeypatch, tmp_path):
    """--proposals measures the proposer alone. If it can fall through to the
    search it is neither cheap (~30 s) nor a measurement of the proposer — it is
    a slow, confounded coverage run wearing the scan's name."""
    calls = _patch_scan(monkeypatch, tmp_path,
                        [_Ev(ok=True, feasible=False)] * 3)
    H.scan_proposals(peakings=(4.0,), freqs=(1.5e9, 1.6e9, 1.7e9))
    assert calls["solve"] == 0, "the proposals scan called the search"
    src = inspect.getsource(H.scan_proposals)
    assert "solve_request" not in src, (
        "the scan references the search; it must not be able to run it")


def test_the_scan_writes_PROPOSAL_SCAN_and_not_RESULTS(monkeypatch, tmp_path):
    """A proposal-only run carries no coverage number, so writing it where a
    coverage result is expected is G113's shape with the ambiguity left in.
    It writes its own artifact and never the sweep's."""
    _patch_scan(monkeypatch, tmp_path, [_Ev(ok=True, feasible=True)] * 3)
    out = H.scan_proposals(peakings=(4.0,), freqs=(1.5e9, 1.6e9, 1.7e9))

    assert H.PROPOSAL_SCAN.exists(), "the scan wrote no artifact"
    assert not H.RESULTS.exists(), "the scan wrote the coverage artifact"
    parsed = json.loads(H.PROPOSAL_SCAN.read_text(encoding="utf-8"))
    # what it wrote is what it returned
    assert parsed["n_accepted"] == out["n_accepted"] == 3
    assert parsed["task"] == out["task"]
    assert "n_solved_pvt45" not in parsed, (
        "the scan reported a coverage number it never measured")


def test_the_scan_counts_THREE_buckets_separately(monkeypatch, tmp_path):
    """G107: 'cannot be scored' is not 'fails the specs'. A feasible, a
    measured-but-infeasible and an unscorable proposal must land in three
    different counters, never collapsed into one pass/fail column (the brief's
    failure mode #4)."""
    _patch_scan(monkeypatch, tmp_path, [
        _Ev(ok=True, feasible=True, reward=+14.2),          # accepted
        _Ev(ok=True, feasible=False, reward=-1.0),          # measured, infeasible
        _Ev(ok=False, feasible=False, reward=-15.5,         # eye not computable
            n_scorable=2),
    ])
    out = H.scan_proposals(peakings=(4.0,), freqs=(1.5e9, 1.6e9, 1.7e9))

    assert out["n_proposals_made"] == 3
    assert out["n_accepted"] == 1
    assert out["n_infeasible"] == 1
    assert out["n_unscorable"] == 1
    # the three verdicts partition the proposals that were actually made
    assert (out["n_accepted"] + out["n_infeasible"] + out["n_unscorable"]
            == out["n_proposals_made"])


def test_the_scan_partition_is_over_MADE_proposals_only(monkeypatch, tmp_path):
    """A proposal that was never made (empty pool / untrained policy) is not one
    of the three verdicts: it is counted out of n_proposals_made, so the
    partition holds over made proposals and n_requests still sees every row."""
    seq = iter([_Ev(ok=True, feasible=True)])   # only the first request evaluates
    made = {"n": 0}

    def _sometimes(f, p):
        made["n"] += 1
        return np.asarray(U7) if made["n"] == 1 else None

    monkeypatch.setattr(H, "evaluate_at_points", lambda *a, **k: next(seq))
    monkeypatch.setitem(H.PROPOSERS, "library", _sometimes)
    monkeypatch.setattr(H, "PROPOSAL_SCAN", tmp_path / "scan.json")
    # RESULTS is redirected even though correct code never writes it: when the
    # artifact-separation gate was sabotaged, this test wrote a real
    # hybrid_results.json into nebula/experiments/. A unit test must not be able
    # to leave a file that reads like a measurement (G113).
    monkeypatch.setattr(H, "RESULTS", tmp_path / "results_SHOULD_NOT_EXIST.json")
    monkeypatch.setattr("nebula.experiments.runlock.hold",
                        lambda *a, **k: contextlib.nullcontext())

    out = H.scan_proposals(peakings=(4.0,), freqs=(1.5e9, 1.6e9, 1.7e9))
    assert out["n_requests"] == 3
    assert out["n_proposals_made"] == 1
    assert (out["n_accepted"] + out["n_infeasible"] + out["n_unscorable"]
            == out["n_proposals_made"] == 1)


def test_the_scan_holds_its_OWN_run_lock():
    """Not 'coverage', not 'hybrid'. A proposals scan and a full sweep are
    different experiments and must refuse each other by name rather than
    silently share a lock or an artifact (G113)."""
    src = inspect.getsource(H.scan_proposals)
    assert 'hold("hybrid_proposal_scan"' in src
    assert 'hold("hybrid"' not in src      # not the full-sweep lock
    assert 'hold("coverage"' not in src    # not the coverage lock
    assert H.PROPOSAL_SCAN.name == "hybrid_proposal_scan.json"
    assert H.PROPOSAL_SCAN != H.RESULTS and H.PROPOSAL_SCAN != C.RESULTS


# ─────────────────────────────────────────────────────────────────────────────
# The CLI wires --proposals to the scan, and only the scan.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_proposals_FLAG_routes_to_the_scan(monkeypatch):
    """--proposals must call scan_proposals + _report_scan and must NOT start
    the full sweep. Routing it to run() would spend ~90 minutes where the user
    asked for ~30 seconds."""
    calls = {"scan": 0, "report_scan": 0, "run": 0}

    def _scan(*a, **k):
        calls["scan"] += 1
        calls["proposer"] = k.get("proposer")
        return {"scan_sentinel": True}

    def _report_scan(d):
        calls["report_scan"] += 1
        calls["reported"] = d

    def _run(*a, **k):
        calls["run"] += 1
        return {}

    monkeypatch.setattr(H, "scan_proposals", _scan)
    monkeypatch.setattr(H, "_report_scan", _report_scan)
    monkeypatch.setattr(H, "run", _run)

    rc = H.main(["--proposals"])
    assert rc == 0
    assert calls["scan"] == 1, "--proposals did not run the scan"
    assert calls["run"] == 0, "--proposals started the full sweep"
    assert calls["report_scan"] == 1
    assert calls["reported"] == {"scan_sentinel": True}


def test_the_proposals_flag_passes_the_chosen_proposer(monkeypatch):
    """--proposer none is the ablation and must reach the scan, or the ablation
    silently measures the library instead.

    `run` is patched to raise, not merely counted: when this gate was sabotaged
    (routing --proposals to the sweep) an earlier version of this test called the
    REAL `run` and started a live 200-eval SPICE sweep from inside the unit
    suite. A test file that claims "no SPICE anywhere" has to enforce it against
    the code being wrong, not assume it.
    """
    seen: dict = {}

    def _must_not_run(*a, **k):
        raise AssertionError("--proposals started the full sweep")

    monkeypatch.setattr(H, "run", _must_not_run)
    monkeypatch.setattr(H, "scan_proposals",
                        lambda *a, **k: (seen.update(k), {"x": 1})[1])
    monkeypatch.setattr(H, "_report_scan", lambda d: None)
    H.main(["--proposals", "--proposer", "none"])
    assert seen.get("proposer") == "none"


def test_run_does_NOT_trigger_the_scan(monkeypatch):
    """The scan is opt-in. --run must not write the scan artifact as a side
    effect, and --proposals must not start the sweep — the two paths are
    exclusive."""
    calls = {"scan": 0, "run": 0}

    def _scan(*a, **k):
        calls["scan"] += 1
        return {}

    def _run(*a, **k):
        calls["run"] += 1
        return {}

    monkeypatch.setattr(H, "scan_proposals", _scan)
    monkeypatch.setattr(H, "run", _run)
    monkeypatch.setattr(H, "_report", lambda d: None)
    H.main(["--run"])
    assert calls["run"] == 1 and calls["scan"] == 0
