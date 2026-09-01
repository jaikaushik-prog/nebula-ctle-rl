"""**Entry 47: the control arm must be the same loop, or it controls nothing.**

Session 31. Entry 46 compared refining against *doing nothing*, and a refiner
that may decline wins that by construction. Entry 47 asks whether 30 decks of
RL refinement beat 30 decks spent any other way from the same start.

The four ways this experiment could be dishonest, each with a test:

1. **The control is a different loop.** If arm B re-implements the refinement
   rather than reusing it, any difference could be the re-implementation.
2. **The arms are not budget-matched.** An arm with more simulations that wins
   has told you nothing.
3. **The population silently changes.** The 58 eligible requests must be the
   ones entry 46 measured, at their original indices and seeds.
4. **The default path drifts.** Adding the `actor` seam must leave the policy
   path bit-identical, or Q1's control is worthless.
"""

from __future__ import annotations

import inspect
import json

import numpy as np
import pytest

from nebula.experiments import exp_refine_control as M
from nebula.experiments import exp_rl_refine as R


# ── 4. the seam must not move the default path ──────────────────────────────


def test_the_actor_seam_leaves_the_POLICY_path_bit_identical():
    """Q1 reproduces entry 46 only if `actor=None` consumes no randomness and
    takes the same branch. The rng must be created lazily, for controls only."""
    src = inspect.getsource(R.refine_one)
    assert "actor=None" in src or "actor is None" in src
    assert "None if actor is None else np.random.default_rng" in src, (
        "the rng must not be created on the policy path, or the default "
        "behaviour changes and Q1's control stops being a control")
    assert "if actor is None:" in src


def test_refine_one_still_defaults_to_the_policy():
    """The signature's default is the thing entries 28 and 46 ran."""
    assert inspect.signature(R.refine_one).parameters["actor"].default is None


# ── 1. the control is THE SAME LOOP ─────────────────────────────────────────


def test_arm_B_REUSES_the_refinement_loop_rather_than_copying_it():
    """Rule 9. If arm B were its own loop, a difference between A and B could
    be the loop rather than the policy -- which is the one thing this
    experiment exists to distinguish."""
    src = inspect.getsource(M.run)
    assert src.count("refine_one(") >= 2, "both arms must call the same loop"
    assert "actor=random_actor" in src
    # and there must be no second implementation hiding in the module
    assert "env.step(" not in inspect.getsource(M), (
        "the control must not drive the environment itself")


def test_the_random_actor_is_UNIFORM_and_not_perturbed_policy():
    """A control that is 'the policy plus noise' measures noise, not the
    policy. Arm B must be the action an untrained agent would take."""
    from nebula.rl.contract import N_ACTIONS

    rng = np.random.default_rng(0)
    a = M.random_actor(None, rng)
    assert a.shape == (N_ACTIONS,)
    assert np.all(a >= -1.0) and np.all(a <= 1.0)
    # it must not consult the observation at all
    assert M.random_actor(np.zeros(18), np.random.default_rng(1)).shape == (N_ACTIONS,)
    src = inspect.getsource(M.random_actor)
    assert "uniform" in src
    assert "net" not in src and "policy" not in src.split('"""')[-1]


# ── 3. the population is entry 46's, unchanged ──────────────────────────────


def test_the_eligible_set_is_the_58_where_a_crossing_is_POSSIBLE():
    """Entry 46's defect 1: 70 of 128 requests began feasible and can never be
    counted as improved. Measuring a rate over all 128 understated it."""
    el = M.eligible()
    assert len(el) == 58
    assert M.ARM_A_BASELINE["n"] == 58


def test_every_eligible_request_carries_its_ORIGINAL_index_and_seed():
    """Arm A reproduces entry 46 only at the same per-request seed, which was
    `SEED + j` for position `j` in the 128-target test list."""
    el = M.eligible()
    for e in el:
        assert e["seed"] == R.SEED + e["index"]
    idx = [e["index"] for e in el]
    assert idx == sorted(idx), "order must follow the original run"
    assert max(idx) < 128


def test_the_eligible_set_is_READ_and_never_re_simulated():
    """Zero simulations: eligibility is deterministic given the same split,
    library and screen, so re-measuring it would spend 512 decks to learn what
    the log already records."""
    src = inspect.getsource(M.eligible)
    assert "read_text" in src
    assert "_score" not in src and "run_point" not in src


def test_it_reads_entry_46_s_log_and_does_not_write_it():
    """The source artifact backs a published result."""
    assert M.ELIGIBLE_SOURCE.name == "rl_refine_run_n128.jsonl"
    assert M.RESULTS != M.ELIGIBLE_SOURCE and M.RUN_LOG != M.ELIGIBLE_SOURCE


# ── 2. budget matching ──────────────────────────────────────────────────────


def test_arm_C_is_matched_to_what_arm_A_actually_SPENT():
    """Per-request matching, not an average. An arm handed the mean budget
    would be over-funded on cheap requests and starved on dear ones."""
    src = inspect.getsource(M.run)
    assert "budget_decks=int(a.pol_sims)" in src


def test_arm_C_stops_when_the_budget_is_spent():
    """The loop must break on decks, not on a candidate count."""
    src = inspect.getsource(M.retrieval_deeper)
    assert "if decks >= budget_decks:" in src
    assert "break" in src


def test_arm_C_shares_the_same_incumbent_as_the_other_arms():
    """Rank 1 is the start every arm is handed, and it competes in all three --
    the selector is identical, which is what isolates the action source."""
    src = inspect.getsource(M.retrieval_deeper)
    assert "cands[0]" in src
    assert "crossed" in src and "not start.feasible" in src


# ── the statistics ──────────────────────────────────────────────────────────


def test_the_primary_is_the_PAIRED_DELTA_not_the_crossing_count():
    """Entry 46's Q3 was underpowered by construction and entry 47 must not
    repeat it: at n=58 with only_B=0, McNemar needs 6 crossings to reach 0.05
    and arm A measured 5."""
    assert M._mcnemar_p(5, 0) == pytest.approx(0.0625)
    assert M._mcnemar_p(5, 0) > 0.05
    assert M._mcnemar_p(6, 0) < 0.05
    src = inspect.getsource(M._summarise)
    assert "Q2_primary" in src
    assert "wilcoxon" in src.lower()


def test_mcnemar_is_the_sign_test_on_DISCORDANT_pairs():
    """Two independent proportions would ignore the pairing that the shared
    start makes available. Reused, not re-derived (rule 9)."""
    assert M._mcnemar_p(3, 1) == R.sign_test_p(3, 1)
    assert M._mcnemar_p(0, 0) == 1.0


def test_the_summary_reports_DECKS_for_every_arm():
    """Q6's confound check: an arm that wins on more simulations has not won."""
    rows = [{"index": 0, "peaking_db": 9.0, "f_peak_hz": 2e9,
             "A_delta": 1.0, "A_crossed": True, "A_decks": 40, "A_steps": 8,
             "B_delta": 0.0, "B_crossed": False, "B_decks": 12, "B_steps": 3,
             "C_delta": 0.5, "C_crossed": False, "C_decks": 40, "C_scored": 9,
             "entry46_delta": 1.0, "entry46_improved": True,
             "A_reproduces_entry46": True}]
    s = M._summarise(rows)
    for arm in ("A", "B", "C"):
        assert "mean_decks" in s[arm]
    assert s["A"]["mean_decks"] == 40.0
    assert s["B"]["mean_decks"] == 12.0


def test_the_control_block_scores_arm_A_against_entry_46():
    """Q1 gates every other reading, so it must be computed, not asserted."""
    rows = [{"index": 0, "peaking_db": 9.0, "f_peak_hz": 2e9,
             "A_delta": 0.0, "A_crossed": False, "A_decks": 40, "A_steps": 8,
             "B_delta": 0.0, "B_crossed": False, "B_decks": 40, "B_steps": 8,
             "C_delta": 0.0, "C_crossed": False, "C_decks": 40, "C_scored": 9,
             "entry46_delta": 0.0, "entry46_improved": False,
             "A_reproduces_entry46": True}]
    s = M._summarise(rows)
    assert s["Q1_control"]["crossings_entry46"] == 5
    assert s["Q1_control"]["n_reproduced"] == 1
    # **Scored PER ROW, not on aggregate totals.** One row that reproduced its
    # own entry-46 outcome IS a passing control for that row; comparing its
    # count against the full set's 5 crossings would fail every truncated run
    # and refuse to print anything, which is what the smoke test caught.
    assert s["Q1_control"]["reproduced"] is True
    assert s["Q1_control"]["complete_run"] is False
    assert s["Q1_control"]["aggregate_matches"] is None
    # a row that did NOT reproduce must fail it
    bad = [dict(rows[0], A_reproduces_entry46=False)]
    assert M._summarise(bad)["Q1_control"]["reproduced"] is False


def test_the_verdict_is_applied_MECHANICALLY_from_entry_47_s_rule():
    """The three branches of the decision rule are printed by the code, so they
    cannot be softened in the writing."""
    src = inspect.getsource(M._report)
    assert "READ NOTHING ELSE" in src            # Q1 gates everything
    assert "beats a MATCHED BUDGET" in src       # Q2 hits
    assert "claim nothing" in src                # direction only
    assert "SELECTOR" in src                     # the strongest negative
    assert "Re-check the wiring" in src          # Q5 misses
