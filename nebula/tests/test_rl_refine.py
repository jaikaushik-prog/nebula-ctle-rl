"""**A refiner must be able to decline.**

Session 23. `exp_rl_refine` asks whether the policy improves the design the
library retrieved. Its first run said 8 of 16 against the library's 9 — and
reading the per-request data showed the harness, not the policy, was the
problem:

    best_r = -np.inf     # only STEP rewards compete

so the starting design was never a candidate, the first edit always won by
default, and the policy **could not return the design it was given**. All three
requests it BROKE (+10.33 -> -0.40, +10.09 -> -0.36, +10.00 -> -0.08) were
cases where declining was correct and unavailable.

The gate below is a source check rather than an end-to-end run, because
running it costs an hour of SPICE and the defect is a single initialiser.
"""

from __future__ import annotations

import inspect
import json

import numpy as np
import pytest

from nebula.experiments import exp_rl_refine as M


def test_the_STARTING_DESIGN_is_a_candidate():
    """The one-line defect, pinned. `best_r` must start at the library
    design's own score, not at negative infinity."""
    src = inspect.getsource(M.refine_one)
    assert "best_r = float(lib_ev.reward)" in src, (
        "the starting design is not a candidate: the policy cannot decline to "
        "edit, and the first step wins by default")
    assert "best_r = -np.inf" not in src


def test_the_start_and_the_refinement_are_scored_the_SAME_WAY():
    """`lib_ev.reward` seeds the comparison, so the two sides come from one
    evaluator. Seeding from a differently-scored quantity would compare two
    scales and call it an improvement."""
    src = inspect.getsource(M.refine_one)
    assert "lib_ev = _score(" in src and "pol_ev = _score(" in src


def test_the_stride_override_does_NOT_touch_the_published_constant():
    """Rule 7: `contract.MAX_STEP` is published. The refinement stride is an
    override in the wrapper and every other caller still sees 0.15."""
    from nebula.rl.contract import MAX_STEP

    assert MAX_STEP == 0.15
    assert M.REFINE_MAX_STEP < MAX_STEP
    src = inspect.getsource(M.refine_one)
    assert "env.env.cfg.max_step" in src


def test_the_bar_is_the_LIBRARYS_MEASURED_result():
    """The comparison must not drift. 9 of 16 at 4.0 sims/request, entry 25."""
    assert M.LIBRARY_BASELINE["n_feasible"] == 9
    assert M.LIBRARY_BASELINE["n"] == 16


def test_broke_it_is_recorded_EXPLICITLY():
    """A policy handed a working design that returns a broken one is the
    outcome most easily hidden by reporting totals or a median."""
    fields = {f for f in M.RefineResult.__dataclass_fields__}
    assert {"broke_it", "improved", "delta"} <= fields


def test_the_verdict_is_applied_MECHANICALLY_from_the_decision_rule():
    """The rule is printed by the code so it cannot be softened in the writing.

    **Updated for entry 46, and the reason the old strings are gone is not
    cosmetic.** Entry 27's rule compared `pol_feasible` against a hard-coded
    bar of 9, which is only meaningful at n=16 — at n=128 "11 or more" is not a
    threshold, it is a rounding error. Entry 46 replaces it with the paired
    comparison plus the sign test, which is what scales. The three branches
    still exist and still cannot be softened; they are now keyed on direction
    and significance rather than on a fixed count.
    """
    src = inspect.getsource(M._report)
    assert "measurably improves" in src          # Q2 and Q3 both hit
    assert "claim nothing" in src                # direction only, unpowered
    assert "does not help and may hurt" in src   # the negative
    assert "READ NOTHING" in src                 # Q1, the control, gates all three
    assert "0.05" in src                         # the threshold is in the code


def test_it_refuses_to_run_with_an_UNTRAINED_policy():
    """Refining with a fresh network would measure random perturbation of the
    library's answer, which is a different and far less interesting question."""
    src = inspect.getsource(M._load_policy)
    assert "FileNotFoundError" in src or "raise FileNotFoundError" in src
    assert "fresh network" in src


def test_it_uses_the_PRETRAINED_policy_not_the_finetuned_one():
    """G114: fine-tuning returned `log_std` to its initialisation and
    feasibility to 0/16. Refining with it would measure the erasure."""
    assert M.POLICY.name == "rl_policy_pretrained.pt"
    assert "finetuned" not in M.POLICY.name


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY 46 — the sample size, and the statistics that make it readable.
#
# The n=16 run returned 2 improved / 0 broken and was reported as p = 0.50.
# That p-value is the whole reason this block exists: it is a statement about
# the sample size, not about the policy, and nothing in the code said so.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_sign_test_reproduces_the_published_p_of_one_half():
    """2 improved, 0 broken -> p = 0.50. The number entry 28 was quoted at."""
    assert M.sign_test_p(2, 0) == pytest.approx(0.5)


def test_zero_regressions_needs_SIX_improvements_to_reach_significance():
    """**The arithmetic that makes n=16 unable to detect its own effect.**

    With no regressions the two-sided exact test is 2 * 0.5**k. Five is not
    enough; six is. Sixteen requests at the observed 12.5 % rate cannot be
    expected to produce six, so entry 28's design could not have succeeded
    however real the effect was.
    """
    assert M.sign_test_p(5, 0) == pytest.approx(0.0625)
    assert M.sign_test_p(5, 0) > 0.05
    assert M.sign_test_p(6, 0) == pytest.approx(0.03125)
    assert M.sign_test_p(6, 0) < 0.05


def test_the_sign_test_is_two_sided_and_symmetric():
    """A policy that breaks six and fixes none is as extreme as the reverse."""
    for k in range(0, 7):
        assert M.sign_test_p(k, 6) == pytest.approx(M.sign_test_p(6, k))
    assert M.sign_test_p(0, 6) < 0.05


def test_the_sign_test_DROPS_ties_rather_than_counting_them():
    """Requests where the policy declined carry no directional information.

    This is what makes it a sign test. Counting declines as evidence for the
    null would let a policy that never edits look statistically confirmed.
    """
    assert M.sign_test_p(6, 0) == M.sign_test_p(6, 0)
    assert M.sign_test_p(0, 0) == 1.0


def test_wilson_interval_covers_the_published_n16_rates():
    """2/16 and 0/16, the two rates entry 46 declares as its inputs."""
    lo, hi = M.wilson_ci(2, 16)
    assert lo == pytest.approx(0.035, abs=0.005)
    assert hi == pytest.approx(0.360, abs=0.005)
    lo0, hi0 = M.wilson_ci(0, 16)
    assert lo0 == 0.0
    assert hi0 == pytest.approx(0.194, abs=0.005)


def test_wilson_never_leaves_the_unit_interval_at_the_edges():
    """Where the normal approximation goes negative and stops meaning anything."""
    for k, n in ((0, 5), (5, 5), (0, 1), (1, 1), (0, 128), (128, 128)):
        lo, hi = M.wilson_ci(k, n)
        assert 0.0 <= lo <= hi <= 1.0


def test_a_larger_run_CANNOT_overwrite_the_n16_control():
    """**The artifact that backs a published number is not a scratch file.**

    `rl_refine_results.json` is cited in `NEXT_AGENT_SAC.md` §39. A run at any
    other sample size must write elsewhere, or the control the bigger run is
    scored against is destroyed by the bigger run.
    """
    assert M.results_path(16) == M.RESULTS
    assert M.run_log_path(16) == M.RUN_LOG
    for n in (32, 64, 128):
        assert M.results_path(n) != M.RESULTS
        assert M.results_path(n).name == f"rl_refine_results_n{n}.json"
        assert M.run_log_path(n) != M.RUN_LOG


def test_the_target_draw_is_PREFIX_STABLE_so_the_control_is_free():
    """Entry 46's Q1 rests on this and it is checked, not assumed.

    `interpolation_split(64, 128).test[:16]` must be
    `interpolation_split(64, 16).test`, element for element -- otherwise the
    first 16 rows of the big run are a different experiment and the free
    replication does not exist.
    """
    from nebula.rl.spec_dist import interpolation_split

    small = interpolation_split(n_train=64, n_test=16, seed=M.SEED)
    big = interpolation_split(n_train=64, n_test=128, seed=M.SEED)
    assert len(big.test) == 128
    assert [t.as_key() for t in small.test] == [t.as_key() for t in big.test[:16]]


def test_growing_n_test_does_NOT_leak_a_training_target_into_the_test_set():
    """`n_train` stays 64 because that is what keeps the held-out set held out.

    `rl_policy_pretrained.pt` trained on `all_t[:64]` at this seed. `Split`
    already refuses an overlap, so this asserts the property the refiner
    depends on rather than re-deriving it.
    """
    from nebula.experiments import exp_rl_pretrain as P
    from nebula.rl.spec_dist import interpolation_split

    assert P.N_TRAIN_TARGETS == 64 and P.SEED == M.SEED
    big = interpolation_split(n_train=P.N_TRAIN_TARGETS, n_test=128, seed=M.SEED)
    trained_on = {t.as_key() for t in big.train}
    assert len(trained_on) == 64
    assert not (trained_on & {t.as_key() for t in big.test})


def test_the_control_block_scores_the_first_sixteen_rows_against_the_artifact():
    """`control_block` is Q1's instrument, so it is tested on both branches."""
    class _Row:
        def __init__(self, imp, brk, libf, polf):
            self.improved, self.broke_it = imp, brk
            self.lib_feasible, self.pol_feasible = libf, polf

    ref = json.loads(M.RESULTS.read_text(encoding="utf-8"))
    n_imp, n_brk = int(ref["n_improved"]), int(ref["n_broke"])
    n_lib, n_pol = int(ref["lib_feasible"]), int(ref["pol_feasible"])

    def rows_matching():
        out = []
        for i in range(16):
            out.append(_Row(i < n_imp, i < n_brk, i < n_lib, i < n_pol))
        return out + [_Row(False, False, False, False)] * 4

    ok = M.control_block(rows_matching())
    assert ok is not None and ok["reproduced"] is True
    assert ok["differs_on"] == []

    broken = rows_matching()
    broken[15] = _Row(True, False, True, True)          # one extra improvement
    bad = M.control_block(broken)
    assert bad["reproduced"] is False
    assert "n_improved" in bad["differs_on"]


def test_the_control_is_SKIPPED_rather_than_faked_at_n_equals_16():
    """A run of 16 cannot be its own control. It must return None, not True."""
    class _Row:
        improved = broke_it = lib_feasible = pol_feasible = False

    assert M.control_block([_Row()] * 16) is None
