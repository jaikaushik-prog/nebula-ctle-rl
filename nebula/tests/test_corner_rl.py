"""**The corner-aware, spec-conditioned RL experiment: its contract, pinned.**

Session 23. `exp_corner_rl` is the run this project deferred four times, and
the two ways it could quietly become worthless are both structural rather than
statistical:

1. **The target stops varying.** If `reset()` does not resample, every episode
   asks the same question and the "spec-conditioned" policy is just a policy.
   The published null was measured on exactly that degeneracy — with
   `target_peaking_db` discarded the manifold was 1-D and a lookup table was
   provably optimal.
2. **The arms stop sharing an evaluator.** The moment the policy is scored on
   a different reward from CMA-ES, the benchmark measures objective
   formulation instead of search, which is the one thing `BASELINES.md` §7d
   forbids.

Both are pinned here. Anything needing ngspice is marked `slow`.

Gates watched go red (rule 4): removing the resample in `reset()` reddens the
first group; pointing `arm_library` at a different spec set reddens the second.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

import nebula.rl.reward_v1 as R
from nebula.experiments.exp_corner_rl import (
    SpecConditionedCornerEnv,
    _env_points,
    _screen,
    _summarise,
)
from nebula.rl.spec_dist import SpecTarget, interpolation_split


# ── 1. the target actually varies ────────────────────────────────────────────


def test_the_wrapper_RESAMPLES_the_target_between_episodes():
    """**The degeneracy that made the published RL null uninformative.**

    Checked without a simulator: `_set_target` is the whole mechanism, so
    driving it directly proves the config the observation is built from moves.
    """
    targets = [SpecTarget(peaking_db=4.0, f_peak_hz=1.3e9),
               SpecTarget(peaking_db=11.0, f_peak_hz=2.4e9)]
    env = SpecConditionedCornerEnv.__new__(SpecConditionedCornerEnv)

    class _Cfg:
        target_peaking_db = 7.5
        target_f_peak_hz = 1.77e9

    class _Base:
        cfg = _Cfg()

    class _Env:
        cfg = _Cfg()
        base = _Base()

    env.env = _Env()
    seen = set()
    for t in targets:
        env._set_target(t)
        seen.add((env.env.cfg.target_peaking_db, env.env.cfg.target_f_peak_hz))
        # BOTH configs must move: the observation is built from the base's.
        assert env.env.base.cfg.target_peaking_db == t.peaking_db
        assert env.env.base.cfg.target_f_peak_hz == t.f_peak_hz
    assert len(seen) == 2, "the target did not change between episodes"


def test_reset_DRAWS_from_the_target_list_rather_than_using_a_constant():
    """Read from the source: `reset` must consult `self.targets`."""
    src = inspect.getsource(SpecConditionedCornerEnv.reset)
    assert "self.targets" in src and "_set_target" in src


def test_an_env_with_NO_targets_raises_rather_than_defaulting():
    """Rule 5: a missing input raises; it does not get a placeholder."""
    with pytest.raises(ValueError):
        SpecConditionedCornerEnv(_screen(), [], seed=0)


# ── 2. the spec set the policy can actually be trained on ────────────────────


def test_V6D_is_scorable_by_the_RL_ENV_which_has_no_link_or_area():
    """`rl/env.py` calls `reward()` with a target but **no `link`, no
    `area_mm2`, no `hd3_nyq_dbc`**. Asking it for `V5_SPECS` raises, which is
    `margins()` refusing to default a spec nobody measured — correct behaviour,
    and the reason `V5D_SPECS` exists."""
    meas = dict(g_dc_db=-3.4, peaking_db=6.65, f_peak_oct=-0.0749,
                nyq_boost_db=6.65, inoise_vrms=2.1e-4, power_w=7.1e-3,
                pair_margin_v=0.64, tail_margin_v=0.35)
    tf = 1.7677669529663687e9
    # V5D scores with exactly what the env has.
    rb = R.reward(meas, tf, specs=R.V6D_SPECS, target_peaking_db=7.5)
    assert rb.valid and set(rb.margins) == set(R.V6D_SPECS)
    # V5 does not, and must not silently succeed.
    with pytest.raises(KeyError):
        R.reward(meas, tf, specs=R.V6_SPECS, target_peaking_db=7.5)


def test_V6D_keeps_the_manifold_TWO_dimensional():
    """The single property that makes RL worth running at all. Without the
    request row a lookup table is provably optimal and the experiment is a
    foregone conclusion."""
    assert "S3_peaking_match" in R.V6D_SPECS
    meas = dict(g_dc_db=-3.4, peaking_db=6.65, f_peak_oct=-0.0749,
                nyq_boost_db=6.65, inoise_vrms=2.1e-4, power_w=7.1e-3,
                pair_margin_v=0.64, tail_margin_v=0.35)
    tf = 1.7677669529663687e9
    scores = {t: R.reward(meas, tf, specs=R.V6D_SPECS,
                          target_peaking_db=t).reward
              for t in (3.0, 5.0, 7.5, 10.0, 12.0)}
    assert len(set(scores.values())) > 1, (
        f"one design scores identically against five peaking requests: "
        f"{scores}")


def test_V6D_is_the_DEVICE_MEASURABLE_half_of_V6():
    """It must not quietly acquire rows the env cannot measure."""
    assert set(R.V6D_SPECS) < set(R.V6_SPECS), "V6D must be a subset of V6"
    # the rows the env genuinely cannot measure: no link bridge, no area,
    # no transient. Absent by necessity, not by preference.
    assert set(R.V6_SPECS) - set(R.V6D_SPECS) == {
        "S8_eye_h", "S8_eye_w", "S7_area", "S4_hd3_nyq"}


# ── 3. the arms share one evaluator ──────────────────────────────────────────


def test_every_arm_is_scored_through_the_SAME_evaluator_and_spec_set():
    """`BASELINES.md` §7d: the comparison must be about SEARCH, not about who
    got the friendlier objective. Every arm's reward comes from `_score`."""
    import nebula.experiments.exp_corner_rl as M

    for name in ("arm_policy", "arm_library", "arm_cmaes", "arm_random"):
        src = inspect.getsource(getattr(M, name))
        assert "_score(" in src, f"{name} does not score through _score()"
    assert "specs=R.V6D_SPECS" in inspect.getsource(M._score), (
        "every arm must go through ONE spec set. V6D and not V6: scored on "
        "V6 the first run returned the invalid floor (-16.0) for every arm on "
        "every request, because the eye's pole-zero fit is rejected under "
        "compression (G103) -- a property of the circuit reported as a "
        "property of the search")
    # ...and the eye is still MEASURED, just not folded into the reward.
    assert "n_eye_ok" in inspect.getsource(M.arm_library)


def test_the_screen_has_ONE_definition_shared_by_the_env_and_the_scorer():
    """`_env_points` converts; it must not build a second screen that could
    drift from the first (rule 9 / G32)."""
    pts = _screen()
    ev = _env_points(pts)
    assert len(ev) == len(pts)
    for a, b in zip(pts, ev):
        assert b.corner == a.corner.process
        assert b.vdd_scale == pytest.approx(a.corner.vdd_scale)
        assert b.temp_c == pytest.approx(a.corner.temp_c)
        assert b.cl_f == pytest.approx(a.cl_f)


def test_the_screen_carries_BOTH_mixed_process_corners():
    """If the env is graded on a screen with no `sf`/`fs`, the corner-aware
    claim is being tested against the blind spot it exists to fix."""
    procs = {p.corner.process for p in _screen()}
    assert {"sf", "fs"} <= procs


# ── 4. held-out targets are genuinely held out ───────────────────────────────


def test_train_and_test_targets_do_not_OVERLAP():
    split = interpolation_split(n_train=64, n_test=16, seed=23_0821)
    tr = {(round(t.peaking_db, 9), round(t.f_peak_hz, 3)) for t in split.train}
    te = {(round(t.peaking_db, 9), round(t.f_peak_hz, 3)) for t in split.test}
    assert not (tr & te), "a test target appears in training"
    assert len(split.test) == 16 and len(split.train) == 64


# ── 5. the summary cannot flatter one arm ────────────────────────────────────


def test_the_summary_reports_SIMS_AND_WALL_CLOCK_separately():
    """GP-BO's model fit and PPO's rollout make wall clock and simulation count
    tell different stories; merging them flatters whichever we prefer."""
    rows = [{"arm": "policy", "reward": 1.0, "feasible": True, "n_sims": 4,
             "wall_s": 0.5},
            {"arm": "cmaes", "reward": 2.0, "feasible": True, "n_sims": 800,
             "wall_s": 300.0}]
    s = _summarise(rows)
    assert s["policy"]["mean_sims"] == 4 and s["cmaes"]["mean_sims"] == 800
    assert "mean_wall_s" in s["policy"] and "median_reward" in s["policy"]
    assert s["policy"]["n_feasible"] == 1


def test_the_summary_counts_FEASIBILITY_not_just_reward():
    """A high median reward with nothing feasible is not a win, and the table
    must be unable to report it as one."""
    rows = [{"arm": "x", "reward": 5.0, "feasible": False, "n_sims": 1,
             "wall_s": 1.0}]
    assert _summarise(rows)["x"]["n_feasible"] == 0


# ── 6. the cost accounting is real (the 19-minute bug) ───────────────────────


def test_the_budget_reader_uses_the_attribute_SpiceBudget_ACTUALLY_HAS():
    """**19.3 minutes of training died on this.**

    `SpiceBudget` exposes `calls`. This file asked for `n_calls` in three
    places. Two were guarded by `hasattr(env, "budget")` — which is True — so
    they raised at run time; the third was an f-string that printed
    `None SPICE calls` for an entire training run **without failing at all**.

    A wrong attribute that formats cleanly is worse than one that crashes, and
    both shapes were live in one file. Pinned against the real class rather
    than a mock, so a rename in `evaluator.py` reddens this instead of
    silently reintroducing `None` into a benchmark table.
    """
    from nebula.experiments.exp_corner_rl import _budget_calls
    from nebula.rl.evaluator import SpiceBudget

    assert hasattr(SpiceBudget(), "calls")
    assert not hasattr(SpiceBudget(), "n_calls")

    class _Env:
        budget = SpiceBudget()

    e = _Env()
    e.budget.charge(7, 1.0)
    assert _budget_calls(e) == 7


def test_a_missing_budget_RAISES_rather_than_reporting_zero():
    """Rule 5. An arm whose SPICE cost cannot be stated must not appear in a
    benchmark table with a plausible-looking 0 beside it."""
    from nebula.experiments.exp_corner_rl import _budget_calls

    with pytest.raises(AttributeError):
        _budget_calls(object())


def test_the_policy_is_CHECKPOINTED_before_the_arms_run():
    """Training is the expensive, slow part; the arms after it are cheap. A
    downstream crash must not cost the policy again."""
    import inspect

    from nebula.experiments import exp_corner_rl as M

    src = inspect.getsource(M.run)
    i_save = src.index("torch.save")
    i_arms = src.index("arm_policy(")
    assert i_save < i_arms, "the policy must be saved BEFORE the arms run"
