"""**The analytic pre-training env: fast, and fenced.**

Session 23. The SPICE-trained policy learned nothing measurable in 1200 steps
(`log_std` unmoved from its initial 0.0), and the reason is arithmetic: one
step costs 4 SPICE decks = 1.26 s, so the ~120 000 steps PPO needs would take
42 hours. This env runs the same MDP off `prescreen.predict_response` at
**0.47 ms/step** -- a million steps in 7.9 minutes.

**The speed is the easy part. The fencing is what these tests are for.** An
env that invents four of eight observation channels is one careless import away
from putting an invented number in a deliverable, which is the single thing
this project's rules exist to prevent. Three fences, all pinned below:

1. it scores ONLY the rows the analytic model actually predicts;
2. the invented channels carry NO information (they normalise to exactly 0);
3. every result is stamped `is_analytic`, and no reporting path accepts one.

Plus the behavioural fix that motivated the module: episodes must run their
full horizon, because the SPICE env ends them on the first bad edit and the
policy was getting 1-3 of its 8 moves.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

import nebula.rl.reward_v1 as R
from nebula.rl.analytic_env import (
    UNPREDICTED_CHANNELS,
    V6A_SPECS,
    AnalyticCtleEnv,
    AnalyticStep,
)
from nebula.rl.contract import N_OBS, OBS_SCALES, normalise_measurements
from nebula.rl.spec_dist import SpecTarget

TARGETS = [SpecTarget(peaking_db=7.5, f_peak_hz=1.7677669529663687e9),
           SpecTarget(peaking_db=4.0, f_peak_hz=1.4e9)]


# ── 1. it scores only what it can predict ────────────────────────────────────


def test_V6A_scores_ONLY_rows_the_analytic_model_predicts():
    """Noise, power and both saturation margins are NOT predicted. Scoring them
    would be rule 5's failure with extra steps: a number nobody computed."""
    assert set(V6A_SPECS) <= set(R.V6D_SPECS), "V6A must be a subset of V6D"
    unpredicted_rows = {"S5_noise", "S6_power", "saturation", "tail_saturation"}
    assert not (set(V6A_SPECS) & unpredicted_rows), (
        f"V6A scores rows the model cannot predict: "
        f"{sorted(set(V6A_SPECS) & unpredicted_rows)}")


def test_V6A_keeps_the_rows_that_actually_BIND():
    """Both frequency rows and both peaking rows. If pre-training drops the
    binding constraints it teaches the policy the wrong problem."""
    assert {"S3_f_peak_band", "S3_f_peak_match",
            "S3_peaking", "S3_peaking_match"} <= set(V6A_SPECS)


def test_the_reward_never_touches_an_invented_channel():
    """The four filled channels must not appear in any scored row."""
    env = AnalyticCtleEnv(TARGETS, seed=0)
    env.reset()
    step = env._score(env._last_meas)
    assert set(step.margins) == set(V6A_SPECS)


# ── 2. the invented channels carry no information ────────────────────────────


def test_the_unpredicted_channels_NORMALISE_TO_ZERO():
    """Filled with each channel's own `OBS_SCALES` centre, so they contribute
    exactly nothing to the observation rather than contributing something
    wrong. A plausible-looking wrong constant would be worse than a blank."""
    env = AnalyticCtleEnv(TARGETS, seed=0)
    env.reset()
    v = normalise_measurements(env._last_meas)
    names = [s.name for s in OBS_SCALES]
    for ch in UNPREDICTED_CHANNELS:
        assert v[names.index(ch)] == pytest.approx(0.0, abs=1e-12), (
            f"{ch} was filled with a value that carries information")


def test_the_observation_is_THE_SAME_SHAPE_the_policy_meets_on_SPICE():
    """A policy pre-trained here has to load into the SPICE env unchanged."""
    env = AnalyticCtleEnv(TARGETS, seed=0)
    obs, _ = env.reset()
    assert obs.shape == (N_OBS,) and env.observation_dim == N_OBS


def test_an_UNFITTABLE_geometry_is_not_given_an_invented_response():
    """`_measure` returns None rather than a made-up curve. Inventing one would
    teach the policy that unrealisable designs are fine."""
    env = AnalyticCtleEnv(TARGETS, seed=0)
    assert env._measure(np.full(7, np.nan)) is None
    bad = env._score(None)
    assert bad.ok is False and bad.reward == R.invalid_reward(len(V6A_SPECS))


# ── 3. nothing analytic can be mistaken for a measurement ────────────────────


def test_every_result_is_STAMPED_analytic():
    assert AnalyticStep(ok=True, reward=0.0, feasible=False).is_analytic is True
    env = AnalyticCtleEnv(TARGETS, seed=0)
    _, info = env.reset()
    assert info["is_analytic"] is True
    _, _, _, _, info2 = env.step(np.zeros(7))
    assert info2["is_analytic"] is True
    assert env.report()["is_analytic"] is True


def test_the_analytic_env_makes_NO_SPICE_CALLS():
    """The entire point. Checked by source, because a stray import of the
    device layer is exactly how this would stop being true."""
    src = inspect.getsource(AnalyticCtleEnv)
    for banned in ("run_point", "sky130_runner", "evaluate_at_points",
                   "ngspice", "SpiceBudget"):
        assert banned not in src, (
            f"the analytic env references {banned!r}: it is no longer free, "
            f"and its numbers are no longer clearly non-measurements")


def test_the_module_states_that_its_numbers_are_NOT_REPORTABLE():
    """The fence is a claim in prose; if the claim disappears the fence has."""
    import nebula.rl.analytic_env as M

    doc = (M.__doc__ or "") + (AnalyticCtleEnv.__doc__ or "")
    assert "fine-tuned" in doc and "SPICE" in doc
    assert "deliverable" in doc


# ── 4. the behavioural fix ───────────────────────────────────────────────────


def test_episodes_run_their_FULL_HORIZON():
    """**The measured defect this module also fixes.** `rl/env.py` terminates
    on an unbuildable design, so at evaluation the SPICE policy got 1-3 of its
    8 moves and could never back out of a bad edit."""
    env = AnalyticCtleEnv(TARGETS, seed=3)
    rng = np.random.default_rng(0)
    for _ in range(5):
        env.reset()
        n = 0
        done = False
        while not done:
            _, _, term, trunc, _ = env.step(rng.normal(0, 1, 7))
            n += 1
            done = term or trunc
        assert n == env.horizon, f"episode ran {n} steps, horizon is {env.horizon}"


def test_a_bad_edit_is_REVERTED_and_the_episode_CONTINUES():
    """Undo the move, report the design we are actually at, charge the step."""
    env = AnalyticCtleEnv(TARGETS, seed=0)
    env.reset()
    before = env._u.copy()
    env._measure = lambda u: None            # force the next edit to fail
    _, _, term, _, info = env.step(np.ones(7))
    assert term is False, "a bad edit must not end the episode"
    assert info["reverted"] is True
    assert np.allclose(env._u, before), "the edit was not undone"
    assert env._step == 1, "the move must still be charged"


def test_there_is_NO_early_success_termination():
    """G100: an episode that ends on the condition the metric rewards
    exceeding is two objectives, not one."""
    src = inspect.getsource(AnalyticCtleEnv.step)
    assert "feasible" not in src.split("truncated =")[0].split("terminated")[0] \
        or "return obs, ev.reward, False" in src
    env = AnalyticCtleEnv(TARGETS, seed=0)
    env.reset()
    _, _, term, _, _ = env.step(np.zeros(7))
    assert term is False


def test_an_env_with_no_targets_RAISES():
    with pytest.raises(ValueError):
        AnalyticCtleEnv([], seed=0)
