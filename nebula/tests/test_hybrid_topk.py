"""
tests/test_hybrid_topk.py — gates on `exp_hybrid.scan_topk`, the top-K library
scan (`PREDICTIONS.md` entry 32).

WHY THIS IS A SEPARATE FILE FROM `test_hybrid.py`
-------------------------------------------------
`test_hybrid.py`'s 28 tests pin the k=1 control that entry 31's OUTCOME quotes.
Entry 32 adds a second, deeper measurement of a *different* proposer; keeping its
gates here means a failure names which measurement broke, and the committed
control's test count stays a fixed reference point.

WHAT IS GUARDED, AND WHICH PAST FAILURE EACH GUARD IS FOR
----------------------------------------------------------
1.  **The artifact cannot collide** (G113). A completed run silently overwrote
    another once. `scan_topk` must write `TOPK_SCAN` and never `PROPOSAL_SCAN`
    or `RESULTS`, and must hold a lock name distinct from both other modes'.
2.  **The deck count cannot be understated.** `exp_coverage`'s neighbour was
    caught reporting 1/6th of its true cost in session 22u by counting only the
    path that won. `n_sims_measured` is every candidate; `n_sims_deployed` is
    the early-exit cost; both are pinned, separately.
3.  **The search cannot run.** This is a proposals-only mode; a stray
    `solve_request` would turn a 12-minute scan into a 90-minute one and quietly
    make it a coverage measurement. `_patch` installs a tripwire that RAISES
    (G122: a sabotage test must not be able to spend money).
4.  **`library_candidates` cannot be modified in place.** `choose_start` seeds
    the fallback search from it, so a changed ranking would break comparability
    with the 13 718-deck baseline. Pinned by source inspection and by the
    wrapper agreeing with `library_proposer` at k=1.
5.  **`accepted_at_k` is monotone and consistent.** It is a cumulative curve; a
    non-monotone one would be an arithmetic bug presented as a result.
6.  **Unscorable is not infeasible** (G107). The per-candidate partition must
    keep the two apart, because entry 31's whole finding was that the failures
    were unscorable rather than out-of-spec.

No SPICE runs here: `evaluate_at_points` is monkeypatched with fixed records,
which is what lets the accounting be checked exactly rather than approximately.
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

U7 = [0.5] * 7


@dataclass
class _Ev:
    """The subset of `adaptive_screen.DesignEval` the scan reads."""

    u: tuple = tuple(U7)
    ok: bool = True
    reward: float = -1.0
    feasible: bool = False
    n_sims: int = 4
    n_points: int = 4
    n_scorable: int = 4
    worst_point: Optional[str] = "ss/0.95/125C/33fF"
    worst_spec: Optional[str] = "S8_output_swing"
    reason: Optional[str] = None
    margins: dict = field(default_factory=dict)
    points: list = field(default_factory=list)
    peaking_db: Optional[float] = 6.0
    f_peak_hz: Optional[float] = 1.9e9
    power_w: Optional[float] = None
    hd3_nyq_dbc: Optional[float] = None
    eye_w_ui: Optional[float] = None
    eye_h_v: Optional[float] = None


def _patch(monkeypatch, tmp_path, evals, n_cands: int = 3):
    """Replace SPICE with records; redirect EVERY module-owned output path.

    The paths correct code never writes are redirected too, deliberately: that
    is the only way the "it wrote the wrong file" gates can fail loudly instead
    of quietly clobbering a committed artifact (G122).
    """
    seq = iter(evals)
    calls: dict = {"evaluate": 0, "lock": []}

    def _eval(u, points, **kw):
        calls["evaluate"] += 1
        return next(seq)

    def _tripwire(*a, **k):
        raise AssertionError("the top-K scan must run NO search")

    @contextlib.contextmanager
    def _hold(name, meta=None):
        calls["lock"].append(name)
        yield

    monkeypatch.setattr(H, "evaluate_at_points", _eval)
    monkeypatch.setattr(H.C, "solve_request", _tripwire)
    monkeypatch.setitem(
        H.CANDIDATE_SOURCES, "library",
        lambda f, p, k: [np.asarray(U7, dtype=float)] * min(k, n_cands))
    monkeypatch.setattr(H, "TOPK_SCAN", tmp_path / "topk.json")
    # **`HERE` too.** Since G128 the destination is keyed on `(source, k)`, so a
    # scan at a non-default k derives its own filename from `HERE` -- and an
    # un-redirected `HERE` would write that file into the real experiments
    # directory from inside a test.
    monkeypatch.setattr(H, "HERE", tmp_path)
    monkeypatch.setattr(H, "PROPOSAL_SCAN",
                        tmp_path / "scan_SHOULD_NOT_EXIST.json")
    monkeypatch.setattr(H, "RESULTS", tmp_path / "results_SHOULD_NOT_EXIST.json")
    monkeypatch.setattr(H, "RUN_LOG", tmp_path / "log_SHOULD_NOT_EXIST.jsonl")
    monkeypatch.setattr("nebula.experiments.runlock.hold", _hold)
    return calls


def _one(monkeypatch, tmp_path, evals, k=3, n_cands=3):
    """Run the scan over a single request."""
    calls = _patch(monkeypatch, tmp_path, evals, n_cands=n_cands)
    out = H.scan_topk(peakings=[6.0], freqs=[1.9e9], k=k)
    return out, calls


# ─────────────────────────────────────────────────────────────────────────────
# 1. The artifact cannot collide with either other mode's (G113).
# ─────────────────────────────────────────────────────────────────────────────


def test_the_three_modes_write_three_DIFFERENT_files():
    """G113 was a completed run silently overwriting another. The k=1 scan's
    artifact is quoted by entry 31's OUTCOME; the top-K scan must not touch it."""
    assert len({H.RESULTS, H.PROPOSAL_SCAN, H.TOPK_SCAN}) == 3


def test_the_scan_writes_TOPK_SCAN_and_nothing_else(monkeypatch, tmp_path):
    """**At the DEFAULT k**, which since G128 is half of what identifies the
    baseline artifact: `(source, k)`, not `source`."""
    out, _ = _one(monkeypatch, tmp_path, [_Ev()] * 8, k=H.DEFAULT_TOPK)
    assert (tmp_path / "topk.json").exists()
    assert not (tmp_path / "scan_SHOULD_NOT_EXIST.json").exists()
    assert not (tmp_path / "results_SHOULD_NOT_EXIST.json").exists()
    assert not (tmp_path / "log_SHOULD_NOT_EXIST.jsonl").exists()
    on_disk = json.loads((tmp_path / "topk.json").read_text(encoding="utf-8"))
    assert on_disk["k"] == out["k"] == H.DEFAULT_TOPK


def test_the_library_at_a_NON_default_k_does_not_touch_the_baseline(
        monkeypatch, tmp_path):
    """G128. Stage 3's control runs the library at k=5; before this rule it
    overwrote entry 32's k=8 artifact with a k=5 one that looked legitimate."""
    out, _ = _one(monkeypatch, tmp_path, [_Ev()] * 3, k=3)
    assert not (tmp_path / "topk.json").exists()
    assert (tmp_path / "topk_scan_library_k3.json").exists()
    assert out["artifact"] == str(tmp_path / "topk_scan_library_k3.json")


def test_the_scan_holds_its_OWN_lock_name(monkeypatch, tmp_path):
    """Three modes, three lock names -- otherwise a top-K scan and a coverage
    sweep can believe they are the same run (G113)."""
    _, calls = _one(monkeypatch, tmp_path, [_Ev()] * 3)
    assert calls["lock"] == ["hybrid_topk_scan"]
    assert "coverage" not in calls["lock"] and "hybrid" not in calls["lock"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. The search cannot run. The tripwire RAISES rather than counting (G122).
# ─────────────────────────────────────────────────────────────────────────────


def test_the_scan_runs_NO_search(monkeypatch, tmp_path):
    out, calls = _one(monkeypatch, tmp_path, [_Ev()] * 3)
    assert calls["evaluate"] == 3
    assert out["n_candidates_scored"] == 3
    # No coverage keys at all: this mode delivers and verifies nothing, so a
    # reader cannot mistake it for a coverage measurement.
    for k in ("n_solved_pvt45", "n_solved_full135", "total_verify_points"):
        assert k not in out


# ─────────────────────────────────────────────────────────────────────────────
# 3. Deck accounting: measured vs deployed, pinned separately.
# ─────────────────────────────────────────────────────────────────────────────


def test_measured_decks_count_EVERY_candidate(monkeypatch, tmp_path):
    """Understating the experiment's own cost is the session-22u failure."""
    out, _ = _one(monkeypatch, tmp_path, [_Ev(n_sims=4)] * 3)
    assert out["total_sims_measured"] == 12
    assert out["requests"][0]["n_sims_measured"] == 12


def test_deployed_decks_STOP_at_the_first_feasible_candidate(monkeypatch,
                                                             tmp_path):
    """rank 2 passes, so a real proposer pays for ranks 1-2 and not rank 3 --
    while the scan still measures all three."""
    out, _ = _one(monkeypatch, tmp_path,
                  [_Ev(feasible=False), _Ev(feasible=True), _Ev(feasible=True)])
    r = out["requests"][0]
    assert r["accepted_rank"] == 2
    assert r["n_sims_deployed"] == 8, "must not charge rank 3 to a deployed run"
    assert r["n_sims_measured"] == 12, "but the scan did spend all 12"
    assert out["total_sims_deployed"] == 8


def test_deployed_equals_measured_when_NOTHING_passes(monkeypatch, tmp_path):
    out, _ = _one(monkeypatch, tmp_path, [_Ev(feasible=False)] * 3)
    r = out["requests"][0]
    assert r["accepted_rank"] is None
    assert r["n_sims_deployed"] == r["n_sims_measured"] == 12


def test_deployed_is_never_greater_than_measured(monkeypatch, tmp_path):
    for evs in ([_Ev(feasible=True)] * 3,
                [_Ev(feasible=False), _Ev(feasible=True), _Ev(feasible=False)],
                [_Ev(feasible=False)] * 3):
        out, _ = _one(monkeypatch, tmp_path, list(evs))
        assert out["total_sims_deployed"] <= out["total_sims_measured"]


def test_a_first_rank_pass_costs_ONE_screen(monkeypatch, tmp_path):
    """The amortisation claim lives on this number: 4 decks, not 12."""
    out, _ = _one(monkeypatch, tmp_path, [_Ev(feasible=True)] * 3)
    assert out["requests"][0]["accepted_rank"] == 1
    assert out["total_sims_deployed"] == 4


# ─────────────────────────────────────────────────────────────────────────────
# 4. `library_candidates` is wrapped, never modified.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_wrapper_does_not_reimplement_the_ranking():
    """`choose_start` seeds the fallback search from `library_candidates`. If the
    top-K source ranked differently, the fallback would change too and no
    published coverage number would still be comparable. So the wrapper must
    CALL it -- checked by source, because a copied argsort would pass any
    behavioural test on a mocked pool."""
    src = inspect.getsource(H.library_candidates_k)
    assert "C.library_candidates" in src
    assert "argsort" not in src, "the ranking must not be reimplemented here"


def test_the_wrapper_agrees_with_the_k1_proposer(monkeypatch):
    """The committed control is the k=1 case of the new source, not a parallel
    definition of it (CLAUDEwa.md rule 9: one definition, referenced)."""
    fake = [np.arange(7, dtype=float) + i for i in range(4)]
    monkeypatch.setattr(H.C, "library_candidates",
                        lambda f, p, k=4: fake[:k])
    top = H.library_candidates_k(1.9e9, 6.0, 1)
    one = H.library_proposer(1.9e9, 6.0)
    assert len(top) == 1
    assert np.array_equal(np.asarray(top[0], dtype=float),
                          np.asarray(one, dtype=float))


def test_an_empty_library_is_not_an_error(monkeypatch, tmp_path):
    """A missing pool is a worse start, not a wrong answer -- and it must not be
    booked as a rejected candidate."""
    out, calls = _one(monkeypatch, tmp_path, [], k=3, n_cands=0)
    assert calls["evaluate"] == 0
    assert out["n_requests"] == 1
    assert out["n_requests_with_candidates"] == 0
    assert out["n_accepted"] == 0
    assert out["total_sims_measured"] == 0
    assert out["requests"][0]["accepted_rank"] is None


def test_the_null_source_offers_nothing():
    assert H.null_candidates(1.9e9, 6.0, 8) == []
    assert set(H.CANDIDATE_SOURCES) == {"library", "none"}


# ─────────────────────────────────────────────────────────────────────────────
# 5. `accepted_at_k` is a cumulative curve, and it is arithmetic, not a vibe.
# ─────────────────────────────────────────────────────────────────────────────


def test_accepted_at_k_is_MONOTONE_and_ends_at_n_accepted(monkeypatch,
                                                          tmp_path):
    """**The data has to discriminate.** A single rank-3 acceptance gives
    `[0, 0, 1]` under BOTH a cumulative rule and a broken `== j+1` one, so it
    proves nothing. Mixing a rank-1 and a rank-3 acceptance separates them:
    cumulative says `[1, 1, 2]`, the broken rule says `[1, 0, 1]`."""
    calls = _patch(monkeypatch, tmp_path,
                   # request 1: rank 1 passes.  request 2: rank 3 passes.
                   [_Ev(feasible=True), _Ev(feasible=False), _Ev(feasible=False),
                    _Ev(feasible=False), _Ev(feasible=False), _Ev(feasible=True)],
                   n_cands=3)
    out = H.scan_topk(peakings=[6.0], freqs=[1.9e9, 2.2e9], k=3)
    assert calls["evaluate"] == 6
    assert [r["accepted_rank"] for r in out["requests"]] == [1, 3]
    assert out["accepted_at_k"] == [1, 1, 2]
    assert all(b >= a for a, b in zip(out["accepted_at_k"],
                                      out["accepted_at_k"][1:]))
    assert out["accepted_at_k"][-1] == out["n_accepted"] == 2
    assert len(out["accepted_at_k"]) == out["k"] == 3


def test_accepted_at_k_counts_a_request_at_EVERY_k_past_its_rank(monkeypatch,
                                                                tmp_path):
    """A request answered at rank 2 is still answered by a proposer allowed 3
    tries. Reading the curve as a histogram instead of a cumulative count would
    understate every k above the mode."""
    _patch(monkeypatch, tmp_path,
           [_Ev(feasible=False), _Ev(feasible=True), _Ev(feasible=False)],
           n_cands=3)
    out = H.scan_topk(peakings=[6.0], freqs=[1.9e9], k=3)
    assert out["accepted_at_k"] == [0, 1, 1]


def test_the_k1_slice_reproduces_a_k1_scan(monkeypatch, tmp_path):
    """The whole point of running k=8 once: its rank-1 column IS the k=1 scan,
    so entry 31's result is re-measured rather than assumed."""
    out, _ = _one(monkeypatch, tmp_path,
                  [_Ev(feasible=True), _Ev(feasible=True), _Ev(feasible=True)])
    assert out["accepted_at_k"][0] == 1
    assert out["requests"][0]["candidates"][0]["rank"] == 1


def test_k_below_one_is_refused(monkeypatch, tmp_path):
    """**Patched even though the call is supposed to raise before doing
    anything** (G122). When the sabotage round removes this guard, an unpatched
    version of this test runs the real `scan_topk` against the real pool and the
    real `TOPK_SCAN` path -- which is how the first sabotage round left an
    orphaned artifact in `nebula/experiments/`. A test for a guard must be safe
    in the world where the guard is gone."""
    _patch(monkeypatch, tmp_path, [])
    for bad in (0, -1):
        with pytest.raises(ValueError, match="k must be"):
            H.scan_topk(peakings=[6.0], freqs=[1.9e9], k=bad)
    assert not (tmp_path / "topk.json").exists()


def test_an_unknown_source_is_refused(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, [])
    with pytest.raises(ValueError, match="unknown candidate source"):
        H.scan_topk(peakings=[6.0], freqs=[1.9e9],
                    source="policy_that_does_not_exist")
    assert not (tmp_path / "topk.json").exists()


# ─────────────────────────────────────────────────────────────────────────────
# 6. G107: unscorable is not infeasible. Entry 31's finding depends on it.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_candidate_partition_keeps_THREE_buckets_apart(monkeypatch,
                                                           tmp_path):
    out, _ = _one(monkeypatch, tmp_path, [
        _Ev(ok=True, feasible=True),
        _Ev(ok=True, feasible=False),                 # measured, out of spec
        _Ev(ok=False, feasible=False, n_scorable=1),  # could not be measured
    ])
    assert out["n_cand_feasible"] == 1
    assert out["n_cand_infeasible"] == 1
    assert out["n_cand_unscorable"] == 1
    total = (out["n_cand_feasible"] + out["n_cand_infeasible"]
             + out["n_cand_unscorable"])
    assert total == out["n_candidates_scored"] == 3


def test_an_unscorable_candidate_keeps_its_scorable_COUNT(monkeypatch,
                                                          tmp_path):
    """`n_scorable/n_points` is how entry 31 established that 13 of 14 failures
    failed at 4 of 4 corners rather than one. Losing it loses the finding."""
    out, _ = _one(monkeypatch, tmp_path,
                  [_Ev(ok=False, feasible=False, n_scorable=0)] * 3)
    c = out["requests"][0]["candidates"][0]
    assert c["n_scorable"] == 0 and c["n_points"] == 4
    assert c["ok"] is False and c["feasible"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 7. One broken candidate must not lose the other 500 decks.
# ─────────────────────────────────────────────────────────────────────────────


def test_a_candidate_that_RAISES_does_not_lose_the_request(monkeypatch,
                                                           tmp_path):
    boom = RuntimeError("ngspice fell over")

    def _eval(u, points, **kw):
        calls["evaluate"] += 1
        if calls["evaluate"] == 2:
            raise boom
        return _Ev(feasible=calls["evaluate"] == 3)

    calls = _patch(monkeypatch, tmp_path, [])
    monkeypatch.setattr(H, "evaluate_at_points", _eval)
    out = H.scan_topk(peakings=[6.0], freqs=[1.9e9], k=3)

    cands = out["requests"][0]["candidates"]
    assert len(cands) == 3, "the failed candidate must still appear"
    assert "error" in cands[1] and "ngspice fell over" in cands[1]["error"]
    # The error row is not scored, and is not silently counted as a rejection.
    assert out["n_candidates_scored"] == 2
    assert out["requests"][0]["accepted_rank"] == 3


def test_a_source_that_RAISES_does_not_lose_the_scan(monkeypatch, tmp_path):
    calls = _patch(monkeypatch, tmp_path, [])

    def _boom(f, p, k):
        raise RuntimeError("pool is corrupt")

    monkeypatch.setitem(H.CANDIDATE_SOURCES, "library", _boom)
    out = H.scan_topk(peakings=[6.0], freqs=[1.9e9], k=3)
    assert calls["evaluate"] == 0
    assert out["n_requests"] == 1 and out["n_accepted"] == 0
    assert "pool is corrupt" in out["requests"][0]["error"]


# ─────────────────────────────────────────────────────────────────────────────
# 8. The scan is graded on the SAME screen as the k=1 scan and the search.
# ─────────────────────────────────────────────────────────────────────────────


def test_every_candidate_is_scored_on_the_MANDATED_four(monkeypatch, tmp_path):
    """Two definitions of "passes the screen" is this repo's third named failure
    mode (G32). All three modes start from EDGE4_MANDATED."""
    seen: list = []

    def _eval(u, points, **kw):
        seen.append([p.label for p in points])
        return _Ev()

    _patch(monkeypatch, tmp_path, [])
    monkeypatch.setattr(H, "evaluate_at_points", _eval)
    out = H.scan_topk(peakings=[6.0], freqs=[1.9e9], k=3)

    from nebula.experiments.adaptive_screen import EDGE4_MANDATED
    want = [p.label for p in EDGE4_MANDATED]
    assert len(seen) == 3 and all(s == want for s in seen)
    assert out["screen"] == want
    assert not any("27C" in lb for lb in want), \
        "the screen is PVT extremes only -- a nominal point would make it easier"


def test_the_request_grid_is_exp_coverages(monkeypatch, tmp_path):
    """A hit rate measured on a different 16 requests is not comparable to
    entry 31's 1-of-16."""
    sig = inspect.signature(H.scan_topk)
    assert sig.parameters["peakings"].default is C.PEAKING_REQUESTS
    assert sig.parameters["freqs"].default is C.FREQ_REQUESTS
    assert len(C.PEAKING_REQUESTS) * len(C.FREQ_REQUESTS) == 16


def test_the_default_k_costs_what_the_docstring_claims():
    """512 decks. If DEFAULT_TOPK changes, the ~12 min in the docs is wrong and
    this test says so before a reader budgets for it."""
    assert H.DEFAULT_TOPK == 8
    n_req = len(C.PEAKING_REQUESTS) * len(C.FREQ_REQUESTS)
    from nebula.experiments.adaptive_screen import EDGE4_MANDATED
    assert n_req * H.DEFAULT_TOPK * len(EDGE4_MANDATED) == 512


# ─────────────────────────────────────────────────────────────────────────────
# 9. The CLI reaches it, and cannot reach it by accident.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_topk_flag_routes_to_the_topk_scan(monkeypatch):
    seen: dict = {}

    def _scan(source="library", k=H.DEFAULT_TOPK):
        seen.update(source=source, k=k)
        return {"k": k, "source": source, "n_requests": 0, "requests": [],
                "accepted_at_k": [], "n_accepted": 0, "screen": [],
                "n_candidates_scored": 0, "total_sims_measured": 0,
                "total_sims_deployed": 0, "wall_clock_s": 0.0,
                "n_cand_feasible": 0, "n_cand_infeasible": 0,
                "n_cand_unscorable": 0}

    monkeypatch.setattr(H, "scan_topk", _scan)
    monkeypatch.setattr(H, "scan_proposals",
                        lambda **k: pytest.fail("wrong mode"))
    monkeypatch.setattr(H, "run", lambda **k: pytest.fail("wrong mode"))

    assert H.main(["--topk"]) == 0
    assert seen == {"source": "library", "k": 8}
    assert H.main(["--topk", "3"]) == 0
    assert seen["k"] == 3


def test_no_flag_still_runs_NOTHING(monkeypatch):
    """A bare invocation must print help, not spend 512 decks."""
    monkeypatch.setattr(H, "scan_topk", lambda **k: pytest.fail("spent money"))
    monkeypatch.setattr(H, "scan_proposals",
                        lambda **k: pytest.fail("spent money"))
    monkeypatch.setattr(H, "run", lambda **k: pytest.fail("spent money"))
    assert H.main([]) == 0


# ---------------------------------------------------------------------------
# entry 40: the top-k proposer DELIVERS, not only scores
# ---------------------------------------------------------------------------

def test_the_sweep_refuses_topk_with_a_source_that_offers_nothing():
    """**Written after starting a real 90-minute sweep by accident, twice.**

    The first version of this guard trusted the NAME: `none` is in
    `CANDIDATE_SOURCES` because it is the ablation, so `topk=5,
    proposer="none"` sailed past it and began a full sweep that would have paid
    top-k bookkeeping to propose nothing. The second time was inside the
    SABOTAGE ROUND proving this very guard worked -- with the guard removed,
    the test called `run` and the sweep started again.

    **So the check is now a pure function and this test never calls `run`.**
    G122: a gate's test must not be able to spend money. G129."""
    with pytest.raises(ValueError, match="offers no candidates"):
        H.check_topk_source("none", 5)


def test_the_sweep_refuses_an_unknown_proposer_before_spending_anything():
    with pytest.raises(ValueError, match="unknown proposer"):
        H.check_topk_source("nope", 5)


def test_the_guard_permits_the_configurations_that_should_run():
    H.check_topk_source("library", 5)
    H.check_topk_source("library", 1)
    H.check_topk_source("none", 1)      # k=1 ablation stays legal


def test_run_calls_the_guard_before_taking_the_lock(monkeypatch):
    """The guard is worthless if the lock is taken first: a refused run would
    still leave a lock file behind, which is what the killed sweeps did."""
    order: list = []
    monkeypatch.setattr(H, "check_topk_source",
                        lambda p, k: order.append("guard"))
    import contextlib

    @contextlib.contextmanager
    def _hold(name, meta=None):
        order.append("lock")
        raise AssertionError("must not reach the lock in this test")
        yield

    monkeypatch.setattr("nebula.experiments.runlock.hold", _hold)
    monkeypatch.setattr(H, "_run", lambda *a, **k: order.append("run") or {})
    with pytest.raises(AssertionError):
        H.run(topk=5)
    assert order[0] == "guard"


def test_topk_1_is_the_committed_control_and_is_the_default():
    import inspect
    assert inspect.signature(H.run).parameters["topk"].default == 1


def test_propose_then_search_walks_the_ranks_and_stops_at_the_first_feasible(
        monkeypatch, tmp_path):
    """Deck accounting: every candidate scored is charged, and scoring stops at
    the first feasible rank -- past it and every deployment cost is too high."""
    evals = [_Ev(feasible=False), _Ev(feasible=False), _Ev(feasible=True),
             _Ev(feasible=False)]
    _patch(monkeypatch, tmp_path, evals)
    hyb, res, ev = H.propose_then_search(
        6.0, 1.9e9, H.AdaptiveScreen(H.EDGE4_MANDATED),
        candidates=lambda f, p, k: [np.asarray(U7)] * k, k=4)
    assert hyb.proposal_accepted is True
    assert hyb.proposal_rank == 3, "the FIRST feasible rank"
    assert hyb.n_candidates == 4
    assert hyb.n_sims_proposal == 3 * 4, "three candidates scored, four decks each"
    assert hyb.n_sims == 3 * 4 and hyb.n_sims_search == 0


def test_a_topk_proposal_that_never_becomes_feasible_falls_back_and_pays_both(
        monkeypatch, tmp_path):
    calls = _patch(monkeypatch, tmp_path, [_Ev(feasible=False)] * 3)
    seen = {}

    def _solve(pk, f, screen, budget=None, seed=None, log=None, archive=None):
        seen["called"] = True
        r = C.RequestResult(peaking_db=pk, f_peak_hz=f, solved_on_screen=False,
                            n_sims=100, n_design_evals=10, wall_s=0.0)
        r.u = list(U7)
        return r, None

    monkeypatch.setattr(H.C, "solve_request", _solve)
    hyb, res, _ = H.propose_then_search(
        6.0, 1.9e9, H.AdaptiveScreen(H.EDGE4_MANDATED),
        candidates=lambda f, p, k: [np.asarray(U7)] * k, k=3)
    assert seen.get("called"), "the fallback must still run"
    assert hyb.proposal_accepted is False and hyb.proposal_rank is None
    assert hyb.n_sims_proposal == 12 and hyb.n_sims_search == 100
    assert hyb.n_sims == 112, "the cost is BOTH paths"


def test_the_single_proposer_path_is_unchanged_by_the_topk_wiring(
        monkeypatch, tmp_path):
    """Entry 31's committed control must not drift."""
    _patch(monkeypatch, tmp_path, [_Ev(feasible=True)])
    hyb, _, _ = H.propose_then_search(
        6.0, 1.9e9, H.AdaptiveScreen(H.EDGE4_MANDATED))
    assert hyb.n_candidates == 1 and hyb.proposal_rank == 1
    assert hyb.n_sims_proposal == 4
