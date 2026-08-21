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
    """Entry 27's rule has three branches and only one reopens the claim. The
    report prints the verdict itself so it cannot be softened in the writing."""
    src = inspect.getsource(M._report)
    assert "STAYS DROPPED" in src
    assert "actively degrades" in src


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
