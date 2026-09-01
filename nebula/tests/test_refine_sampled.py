"""**Entry 48: use the distribution the policy learned, not just its mean.**

Session 31. Entry 47 measured the trained policy losing to uniform noise at a
matched budget. That is a symptom, and the checkpoint names the cause:
`log_std` shrank from 0.0 to -3.02 on `rs` and -2.94 on `cs`, and
`refine_one`'s default throws all of it away by reading
`distribution(o).mean`.

The four ways this fix could be fake, each with a test:

1. **The restart secretly buys extra simulations.** If returning to the start
   re-measures it, arm E is handed decks the other arms never got.
2. **The restart does not actually return to the start.** Then E is a long
   walk with a reset counter, not four independent tries.
3. **The sampled actor is not really sampling**, or is sampling something other
   than the policy's own learned width.
4. **Arms A and B get re-run** instead of read, so the comparison is against a
   different measurement than the one entry 47 published.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from nebula.experiments import exp_refine_sampled as M
from nebula.experiments import exp_rl_refine as R


def _code(fn) -> str:
    """Source with the docstring and comment lines stripped.

    These tests assert on what the CODE does. Matching raw source also matches
    the prose explaining it -- and both of this module's first two assertions
    failed that way, on a docstring that quotes `.mean` precisely in order to
    say it is the bug, and on a comment that names `env.reset(` precisely in
    order to say it is paid once. Asserting on prose is how a guard starts
    passing for the wrong reason.
    """
    import ast
    import textwrap

    src = textwrap.dedent(inspect.getsource(fn))
    tree = ast.parse(src)
    node = tree.body[0]
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        node.body = node.body[1:]           # drop the docstring
    return ast.unparse(node)


# ── 3. the actor samples the POLICY'S OWN width ─────────────────────────────


def test_the_sampled_actor_calls_sample_and_not_mean():
    """The whole diagnosis is that `.mean` discards `log_std`."""
    from nebula.experiments.exp_refine_control import sampled_actor

    src = _code(sampled_actor)
    assert ".sample()" in src
    assert ".mean" not in src, "the actor must not fall back to the mean"


def test_the_checkpoint_really_did_LEARN_a_width():
    """If `log_std` were still at its initialisation the diagnosis would be
    empty -- sampling would just be noise with extra steps. It is not: the
    policy is confident precisely on the knobs that set the peak."""
    import torch

    from nebula.experiments.exp_rl_refine import POLICY

    if not POLICY.exists():                                 # pragma: no cover
        pytest.skip("policy checkpoint not present")
    sd = torch.load(POLICY, map_location="cpu", weights_only=False)["state_dict"]
    ls = [v for k, v in sd.items() if "log_std" in k][0].detach().numpy().ravel()
    assert ls.shape == (7,)
    # it MOVED from 0.0 -- every dimension is now narrower than its init
    assert np.all(ls < -0.5), f"policy did not learn a width: {ls}"
    # and it is tightest on rs (index 3) and cs (index 4), the Rs*Cs peak knobs
    assert ls[3] < -2.5 and ls[4] < -2.5


def test_sampling_actually_VARIES_where_the_mean_does_not():
    """Two draws from the same observation must differ, or arm D is arm A."""
    from nebula.experiments.exp_refine_control import sampled_actor
    from nebula.experiments.exp_rl_refine import _load_policy

    try:
        net, _ = _load_policy(7 + 8 + 2 + 1, 7, 0)
    except FileNotFoundError:                               # pragma: no cover
        pytest.skip("policy checkpoint not present")
    act = sampled_actor(net)
    obs = np.zeros(18, dtype=float)
    a1, a2 = act(obs, None), act(obs, None)
    assert a1.shape == (7,)
    assert not np.allclose(a1, a2), "sampling produced identical draws"


# ── 1 & 2. the restart is free and it really restarts ───────────────────────


def test_the_restart_does_NOT_re_measure_the_start():
    """Point 1. `env.reset(u0)` costs ~4 decks and every restart returns to the
    SAME start, whose evaluation is deterministic. Paying R times would spend
    half a 30-deck budget re-learning an identical fact and starve the arm
    under test."""
    src = _code(R.refine_one)
    assert "for attempt in range(" in src
    # exactly one reset in the CODE, before the restart loop
    assert src.count("env.reset(") == 1
    assert "_step = 0" in src and "_u = u0.copy()" in src


def test_the_restart_writes_to_BASE_and_not_through_the_wrapper():
    """Point 2, and it is a real trap: the wrappers delegate reads via
    `__getattr__`, which does NOT intercept writes. `env.env._u = ...` would
    create a shadowing attribute on the wrapper and leave the real episode
    state untouched -- so every 'restart' would silently continue the previous
    walk."""
    src = _code(R.refine_one)
    assert "env.env.base._u" in src
    assert "env.env.base._step" in src


def test_the_restart_replays_the_START_observation():
    """The observation is a function of `(_u, _step)` plus the start's
    measurements, so restoring the state and replaying `obs0` is bit-identical
    to a fresh reset -- which is what makes skipping the re-measurement sound
    rather than merely cheap."""
    src = _code(R.refine_one)
    assert "obs0" in src
    assert "obs = obs0" in src


def test_restarts_default_to_ONE_so_entries_28_46_and_47_are_unchanged():
    """Every earlier result must still reproduce."""
    sig = inspect.signature(R.refine_one)
    assert sig.parameters["restarts"].default == 1
    assert sig.parameters["max_steps"].default is None


def test_max_steps_caps_each_restart_rather_than_the_episode():
    """`E` is 4 restarts of 2 steps. If `max_steps` capped the total, E would
    be a 2-step arm with three no-ops."""
    src = _code(R.refine_one)
    assert "steps_here" in src
    assert "steps_here >= int(max_steps)" in src


# ── 4. A and B are READ, not re-run ─────────────────────────────────────────


def test_arms_A_and_B_are_read_from_entry_47_and_never_re_run():
    """Re-running them would compare against a second measurement of the same
    thing under different conditions, and the pairing would be lost."""
    src = _code(M.run)
    assert "control_arms()" in src
    assert src.count("refine_one(") == 2, "only D and E may be simulated here"
    # quote-style agnostic: `ast.unparse` normalises "..." to '...'
    assert "A_delta" in src and "B_delta" in src


def test_it_refuses_to_run_before_entry_47_has_finished():
    """Entry 48 is scored AGAINST entry 47's arms, so a missing artifact must
    stop the run with an explanation rather than silently measure nothing."""
    src = _code(M.control_arms)
    assert "SystemExit" in src
    assert "entry 47 must finish first" in src


# ── the registered schedule and the statistics ──────────────────────────────


def test_the_restart_schedule_is_the_REGISTERED_one():
    """R=4 x 2 steps, from entry 48. Not swept -- a sweep would be tuning."""
    assert M.RESTARTS == 4
    assert M.STEPS_PER_RESTART == 2


def test_Q3_is_the_bar_and_compares_E_against_RANDOM():
    """Beating the policy's own mean (Q2) is not the question; beating uniform
    noise at a matched budget is."""
    rows = [{"index": 0, "peaking_db": 9.0, "f_peak_hz": 2e9,
             "A_delta": 0.0, "A_crossed": False, "A_decks": 30,
             "B_delta": 1.0, "B_crossed": True, "B_decks": 30,
             "D_delta": 0.5, "D_crossed": False, "D_decks": 30, "D_steps": 8,
             "E_delta": 2.0, "E_crossed": True, "E_decks": 30, "E_steps": 8,
             "same_start": True, "lib_reward": -1.0}]
    s = M._summarise(rows)
    assert s["Q3_E_vs_B"]["hit"] is True          # 1 >= 1
    assert s["Q2_E_vs_A"]["hit"] is True          # 1 > 0
    assert s["Q1_control"]["reproduced"] is True


def test_Q5_flags_a_budget_that_drifted_out_of_band():
    """A restart re-scores an endpoint, so the arms could drift apart on cost.
    An arm that wins on more decks has not won."""
    rows = [{"index": 0, "peaking_db": 9.0, "f_peak_hz": 2e9,
             "A_delta": 0.0, "A_crossed": False, "A_decks": 30,
             "B_delta": 0.0, "B_crossed": False, "B_decks": 30,
             "D_delta": 0.0, "D_crossed": False, "D_decks": 31, "D_steps": 8,
             "E_delta": 0.0, "E_crossed": False, "E_decks": 60, "E_steps": 8,
             "same_start": True, "lib_reward": -1.0}]
    s = M._summarise(rows)
    assert s["Q5_budget"]["D"]["within_10pct"] is True
    assert s["Q5_budget"]["E"]["within_10pct"] is False
    assert s["Q5_budget"]["E"]["vs_A_pct"] == pytest.approx(100.0)


def test_the_verdict_is_applied_MECHANICALLY():
    """Three branches, printed by the code so they cannot soften in writing."""
    src = inspect.getsource(M._report)
    assert "READ NOTHING ELSE" in src
    assert "first genuine RL" in src
    assert "UNDERSTATED the policy" in src
    assert "diagnosis is wrong" in src
