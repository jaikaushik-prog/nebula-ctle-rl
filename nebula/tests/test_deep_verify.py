"""
tests/test_deep_verify.py — gates on `exp_deep_verify`, stage 2 of entry 52
(`PREDICTIONS.md` entry 53).

WHY EACH GUARD EXISTS
----------------------
1.  **"Newly accepted" must mean the FIRST feasible candidate, not any of
    them.** Request 3 in the k=40 scan has feasible candidates at several
    ranks; a deployed proposer stops at the first. Counting a later one would
    overstate the depth needed and understate the deployed cost.
2.  **The verified design must be the one the scan accepted.** G124: `design_id`
    does not join across artifact boundaries, and the failure mode is a silent
    empty join that reads as a real finding. The `u` vector travels with the
    candidate for exactly this reason.
3.  **`gained` must count only requests that were NOT already compliant.**
    Entry 53's whole bound is that requests 6 and 10 were already 45/45 via the
    search, so a proposal passing there is a deck saving and not coverage. An
    implementation that counted all passes would have reported +4 and moved the
    headline to 12 of 16, which is false.
4.  **The control must be identifiable.** If a proposal that passed the 4-corner
    screen fails 45 corners on a request known to be solvable, the screen is
    indicted rather than the request -- so `control_all_pass` has to be reported
    separately from `gained` and not folded into it.

No SPICE and no artifacts: every test builds its own scan and baseline.
"""

from __future__ import annotations

import pytest

from nebula.experiments import exp_deep_verify as DV


def _scan(spec):
    """`spec` maps request index -> list of (rank, feasible)."""
    return {"requests": [
        {"index": i, "peaking_db": 6.0, "f_peak_hz": 1.8e9,
         "candidates": [{"rank": r, "feasible": f, "reward": 14.0 + 0.01 * r,
                         "u": [0.1 * r] * 7, "design_id": f"d{i}_{r}"}
                        for r, f in cands]}
        for i, cands in spec.items()]}


def _base(spec):
    """`spec` maps request index -> n_pvt45_pass."""
    return {i: {"n_pvt45_pass": n, "n_pvt45_total": 45, "pvt45_worst": 1.0,
                "which_path": "search"} for i, n in spec.items()}


# ── 1. the first feasible candidate, and only if it is deep ──────────────────


def test_takes_the_FIRST_feasible_candidate_not_a_later_one():
    scan = _scan({0: [(1, False), (17, True), (26, True)]})
    got = DV.newly_accepted(scan)
    assert len(got) == 1
    assert got[0]["rank"] == 17
    assert got[0]["design_id"] == "d0_17"


def test_a_shallow_acceptance_is_not_new():
    """Rank <= 8 was already scanned by entry 32; it is not a new acceptance."""
    scan = _scan({0: [(1, False), (5, True), (17, True)]})
    assert DV.newly_accepted(scan) == []


def test_the_boundary_rank_is_exclusive_at_8():
    assert DV.newly_accepted(_scan({0: [(8, True)]})) == []
    assert len(DV.newly_accepted(_scan({0: [(9, True)]}))) == 1


def test_a_request_with_no_feasible_candidate_is_skipped():
    scan = _scan({0: [(1, False), (17, False), (40, False)]})
    assert DV.newly_accepted(scan) == []


def test_candidates_are_sorted_by_rank_before_the_first_is_taken():
    """The artifact's list order must not decide which design gets verified."""
    scan = _scan({0: [(26, True), (17, True)]})
    assert DV.newly_accepted(scan)[0]["rank"] == 17


def test_the_u_vector_travels_with_the_candidate():
    """G124: the design must be carried, never re-looked-up by id.

    The scan fixture gives rank 17 the vector `[1.7]*7` and rank 26 `[2.6]*7`,
    so this fails if the wrong candidate's geometry is carried forward.
    """
    scan = _scan({0: [(17, True), (26, True)]})
    got = DV.newly_accepted(scan)[0]
    expected = [c["u"] for c in scan["requests"][0]["candidates"]
                if c["rank"] == 17][0]
    assert got["u"] == expected
    assert got["u"] != [c["u"] for c in scan["requests"][0]["candidates"]
                        if c["rank"] == 26][0]


# ── 2. `gained` counts only movable requests ─────────────────────────────────


def _rows(spec):
    """`spec` maps index -> n_pvt45_pass achieved by the proposal."""
    return [{"index": i, "rank": 17, "peaking_db": 6.0, "f_peak_hz": 1.8e9,
             "design_id": f"d{i}", "u": [0.5] * 7, "screen_reward": 14.2,
             "verified": True, "n_pvt45_pass": n, "n_pvt45_total": 45,
             "pvt45_worst": 1.0, "n_full135_pass": n, "full135_worst": 1.0,
             "n_unscorable": 45 - n, "failing_rows": []}
            for i, n in spec.items()]


def test_a_pass_on_an_ALREADY_COMPLIANT_request_is_not_a_coverage_gain():
    """**The defect that would have reported 12 of 16.**"""
    base = _base({3: 11, 5: 44, 6: 45, 10: 45})
    a = DV.analyse(_rows({3: 45, 5: 45, 6: 45, 10: 45}), base)
    assert a["gained"] == [3, 5]
    assert a["new_coverage"] == a["entry40_coverage"] + 2


def test_the_real_outcome_gains_nothing():
    """Stage 2 as it actually ran: 44, 37, 45, 45 -> coverage unchanged."""
    base = _base({3: 11, 5: 44, 6: 45, 10: 45})
    a = DV.analyse(_rows({3: 44, 5: 37, 6: 45, 10: 45}), base)
    assert a["gained"] == []
    assert a["new_coverage"] == a["entry40_coverage"] == 2


def test_a_proposal_that_makes_a_request_WORSE_is_still_not_a_gain():
    base = _base({5: 44})
    assert DV.analyse(_rows({5: 37}), base)["gained"] == []


def test_movable_and_control_partition_the_requests():
    base = _base({3: 11, 5: 44, 6: 45, 10: 45})
    a = DV.analyse(_rows({3: 44, 5: 37, 6: 45, 10: 45}), base)
    assert a["movable_requests"] == [3, 5]
    assert a["control_requests"] == [6, 10]
    assert set(a["movable_requests"]) & set(a["control_requests"]) == set()


def test_control_all_pass_is_reported_separately_from_gained():
    """A control failure indicts the SCREEN and must be visible on its own."""
    base = _base({3: 11, 6: 45})
    a = DV.analyse(_rows({3: 44, 6: 30}), base)
    assert a["gained"] == []
    assert a["control_all_pass"] is False


def test_control_all_pass_is_true_when_every_control_holds():
    base = _base({3: 11, 6: 45, 10: 45})
    a = DV.analyse(_rows({3: 44, 6: 45, 10: 45}), base)
    assert a["control_all_pass"] is True


def test_entry40_coverage_counts_only_full_45_of_45():
    base = _base({0: 32, 1: 45, 3: 11, 5: 44, 6: 45, 10: 45})
    a = DV.analyse(_rows({3: 44}), base)
    assert a["entry40_coverage"] == 3


# ── 3. the module does not silently become a search ──────────────────────────


def test_it_never_calls_the_searcher():
    """This is a verification stage; a stray search would change the cost claim
    and turn a 3-minute run into a 90-minute one."""
    import inspect

    src = inspect.getsource(DV)
    for banned in ("solve_request", "method_cmaes", "CmaConfig"):
        assert banned not in src, f"{banned} reachable from the verify stage"


def test_the_shallow_boundary_is_entry_52s_value():
    assert DV.SHALLOW_K == 8
