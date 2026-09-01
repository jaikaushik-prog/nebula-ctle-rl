"""**Coverage of the union: does the policy answer a request retrieval cannot?**

Session 31. `exp_union` intersects sets that committed scan artifacts already
contain. It runs no simulator and fits nothing, so the entire risk is that it
counts something other than what it says it counts. These tests are about that
risk and nothing else.

The three ways this analysis could be dishonest, each with a test:

1. **Unmatched depth.** The library scan ran at k=8 and the SAC scans at k=5.
   Counting the library at 8 and the policy at 5 would credit the policy with
   retrieval's missing depth.
2. **Selecting on the outcome.** A union over four policies is a multiple
   comparison. The headline must be a FIXED pair.
3. **A free lunch.** A coverage number without the decks that bought it.
"""

from __future__ import annotations

import json

import pytest

from nebula.experiments import exp_union as M


def test_it_runs_NO_simulator():
    """The whole claim rests on this: every number is read, none is produced."""
    d = M.analyse()
    assert d["simulations_run_by_this_file"] == 0


def test_the_library_is_re_counted_at_the_POLICY_S_depth():
    """k=8 vs k=5 is the one asymmetry that would fake this result.

    Entry 32 measured `accepted_at_k = [1, 4, 5, 5, 6, 6, 6, 6]`, so the
    library answers 6 at k=5 and also 6 at k=8 -- the re-count happens to cost
    nothing here, which is exactly why it must be asserted rather than assumed.
    """
    assert M.MATCHED_K == 5
    d = M.analyse()
    assert d["matched_k"] == 5
    assert d["retrieval"]["n_accepted"] == 6
    at8 = M.accepted_at(M.LIBRARY_SCAN, k=8)
    at5 = M.accepted_at(M.LIBRARY_SCAN, k=5)
    assert at5 <= at8, "a smaller k cannot accept a request a larger k did not"
    assert len(at5) == 6


def test_it_REFUSES_to_re_count_a_scan_upward():
    """Counting a k=5 scan at k=8 would credit it with unsimulated candidates."""
    with pytest.raises(ValueError, match="cannot be re-counted"):
        M.accepted_at(M.HERE / M.SAC_SCANS[0], k=8)


def test_the_headline_is_a_FIXED_PAIR_not_the_best_of_four():
    """Point 2. The reported method must be one named checkpoint, and the
    four-arm union must carry its multiple-comparison warning."""
    d = M.analyse()
    h = d["headline_pair"]
    assert h["arm"] in d["arms"], "the headline must name ONE deployable arm"
    assert "SELECTING ON THE OUTCOME" in d["five_arm_union"]["warning"]
    assert "multiple comparison" in d["five_arm_union"]["warning"]


def test_the_union_is_the_measured_seven_of_sixteen():
    """The result itself, pinned so a later edit cannot drift it.

    Retrieval answers {2,4,7,9,11,14}; `sac_seeded_finetuned` answers {0},
    which retrieval does not reach at any rank it scored. Entry 36 recorded
    request 0 as its 'one honest exception' before this file existed.
    """
    d = M.analyse()
    assert d["retrieval"]["accepted"] == [2, 4, 7, 9, 11, 14]
    assert d["headline_pair"]["adds"] == [0]
    assert d["headline_pair"]["n_retrieval"] == 6
    assert d["headline_pair"]["n_pair"] == 7
    assert d["five_arm_union"]["n"] == 7


def test_every_coverage_number_carries_its_DECKS():
    """Point 3. A proposer that answers more for more decks has not won yet."""
    d = M.analyse()
    assert d["retrieval"]["decks"] > 0
    for arm in d["arms"].values():
        assert arm["decks"] > 0
        assert arm["pair_decks"] == d["retrieval"]["decks"] + arm["decks"]
    assert d["headline_pair"]["decks"] > d["retrieval"]["decks"], (
        "adding a second proposer costs decks; a pair that looks free is a bug")


def test_the_caveat_states_it_is_BELOW_the_project_s_own_bar():
    """n = 1, against entry 28's stated minimum of 2. Not softened."""
    c = M.analyse()["headline_pair"]["caveat"]
    assert "n = 1" in c
    assert "TWO" in c


def test_it_does_not_claim_compliance_or_corner_coverage():
    """The screen here is the 4-corner delivery screen, not the mandated 45."""
    nc = " ".join(M.analyse()["not_claimed"])
    assert "45 of 45" in nc
    assert "8 of 16" in nc


def test_the_written_artifact_matches_what_analyse_returns():
    """The committed JSON is the same object the report prints, not a copy
    that can drift from it."""
    if not M.RESULTS.exists():                              # pragma: no cover
        pytest.skip("union_results.json not written yet")
    on_disk = json.loads(M.RESULTS.read_text(encoding="utf-8"))
    assert on_disk["retrieval"] == M.analyse()["retrieval"]
    assert on_disk["headline_pair"]["n_pair"] == 7
