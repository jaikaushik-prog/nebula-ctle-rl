"""
tests/test_swing_env.py — gates on `rl/swing_env.py` and `exp_sac_swing`
(`PREDICTIONS.md` entry 38).

WHAT IS GUARDED, AND WHICH FAILURE EACH GUARD IS FOR
------------------------------------------------------
1.  **THE PENALTY MUST ACTUALLY REACH THE REWARD.** A term that is computed and
    discarded is this repo's most common silent failure: training would run,
    report a plausible curve, and measure nothing. Entry 38's Q2 exists to catch
    it after the fact; these gates catch it before.
2.  **The surrogate may steer training and nothing else.** No path from this
    wrapper to the screen, `exp_coverage` or the compliance matrix, and every
    row it produces is stamped `is_surrogate`.
3.  **The wrapper is a WRAPPER.** Observation dimension, action dimension and
    horizon pass through unchanged, or the checkpoint contract that makes
    "the reward is the only difference" true is broken.
4.  **The shortfall is bounded and one-sided.** Headroom above the target earns
    nothing: a reward that keeps paying for more swing buys it with the gain the
    frequency rows need, and the policy would ride that instead.
5.  **Q2 is measured, not predicted.** The verdict's headroom number must come
    from the SPICE-measured `vout_swing_v` in the reason string, never from the
    surrogate's own output — a model must not grade itself.
6.  **The Q1 branch dominates**: a control that did not reproduce makes every
    other number in the run uninterpretable.

No SPICE and no training here; the surrogate is a stub with a known answer, so
the arithmetic can be checked exactly.
"""

from __future__ import annotations

import numpy as np
import pytest

from nebula.experiments import exp_sac_swing as SW
from nebula.rl.swing_env import SWING_TARGET_V, SWING_W, SwingAwareEnv


class _Stub:
    """A surrogate that always predicts `v` volts, and REMEMBERS WHAT IT WAS
    ASKED ABOUT.

    Recording the inputs is not decoration: a gate that only counts calls stays
    green when the penalty is computed for the wrong design, which is exactly
    what the entry-38 sabotage round caught (G125 -- the test data has to
    separate the correct rule from the broken one)."""

    def __init__(self, v: float):
        self.v = float(v)
        self.calls = 0
        self.seen: list = []

    def predict(self, X):
        self.calls += 1
        self.seen.append(np.asarray(X, dtype=float).ravel().copy())
        return np.full(len(X), self.v)


class _Base:
    """The minimum of `AnalyticCtleEnv`'s duck type."""

    observation_dim = 18
    action_dim = 7
    horizon = 8

    def __init__(self, reward: float = 6.5):
        self.reward = reward
        self._u = np.full(7, 0.5)
        self.steps = 0

    @property
    def u(self):
        return self._u.copy()

    def reset(self, u0=None):
        if u0 is not None:
            self._u = np.asarray(u0, dtype=float).copy()
        return np.zeros(self.observation_dim), {"is_analytic": True}

    def step(self, a):
        self.steps += 1
        # **The design MOVES.** A base env whose `u` never changes cannot tell
        # "scored the current design" from "scored a constant".
        self._u = np.clip(self._u + 0.1, 0.0, 1.0)
        return (np.zeros(self.observation_dim), self.reward, False,
                self.steps >= self.horizon, {"is_analytic": True})

    def report(self):
        return {"is_analytic": True, "n_evals": self.steps}


# ---------------------------------------------------------------------------
# 1. the penalty reaches the reward
# ---------------------------------------------------------------------------

def test_a_design_at_the_target_is_not_penalised():
    env = SwingAwareEnv(_Base(reward=6.5), _Stub(SWING_TARGET_V))
    env.reset()
    _, r, _, _, info = env.step(np.zeros(7))
    assert r == pytest.approx(6.5)
    assert info["swing_penalty"] == 0.0


def test_a_design_at_half_the_target_loses_half_the_weight():
    env = SwingAwareEnv(_Base(reward=6.5), _Stub(SWING_TARGET_V / 2))
    env.reset()
    _, r, _, _, info = env.step(np.zeros(7))
    assert info["swing_shortfall"] == pytest.approx(0.5)
    assert r == pytest.approx(6.5 - SWING_W * 0.5)


def test_a_design_with_no_headroom_loses_the_whole_weight():
    env = SwingAwareEnv(_Base(reward=6.5), _Stub(0.0))
    env.reset()
    _, r, _, _, info = env.step(np.zeros(7))
    assert info["swing_shortfall"] == pytest.approx(1.0)
    assert r == pytest.approx(6.5 - SWING_W)


def test_the_surrogate_is_actually_consulted_every_step():
    """The silent failure this file exists for: a term computed and discarded."""
    stub = _Stub(0.5)
    env = SwingAwareEnv(_Base(), stub)
    env.reset()
    for _ in range(4):
        env.step(np.zeros(7))
    assert stub.calls == 4
    assert env.n_penalised == 4


def test_the_penalty_is_computed_for_THE_DESIGN_JUST_BUILT():
    """Counting calls is not enough. A penalty computed for a fixed design
    scores every step identically while looking busy — the sabotage round caught
    this gate passing when the env's `u` was replaced by a constant."""
    from nebula.experiments.exp_swing_surrogate import features

    stub = _Stub(0.5)
    base = _Base()
    env = SwingAwareEnv(base, stub)
    env.reset()
    seen_u = []
    for _ in range(3):
        env.step(np.zeros(7))
        seen_u.append(env.u.copy())
    assert len(stub.seen) == 3
    for u, x in zip(seen_u, stub.seen):
        assert np.allclose(x, features(u)), (
            "the surrogate was asked about a design the env is not at")
    assert not np.allclose(stub.seen[0], stub.seen[-1]), (
        "the inputs never changed, so this gate could not tell a constant "
        "from the real design")


# ---------------------------------------------------------------------------
# 2. the shortfall is bounded and one-sided
# ---------------------------------------------------------------------------

def test_headroom_above_the_target_earns_nothing_extra():
    plenty = SwingAwareEnv(_Base(reward=6.5), _Stub(SWING_TARGET_V * 3))
    exact = SwingAwareEnv(_Base(reward=6.5), _Stub(SWING_TARGET_V))
    plenty.reset(); exact.reset()
    _, r_plenty, _, _, _ = plenty.step(np.zeros(7))
    _, r_exact, _, _, _ = exact.step(np.zeros(7))
    assert r_plenty == pytest.approx(r_exact), (
        "a reward that keeps paying for swing buys it with the gain the "
        "frequency rows need")


def test_a_negative_prediction_cannot_exceed_the_full_penalty():
    env = SwingAwareEnv(_Base(reward=6.5), _Stub(-5.0))
    env.reset()
    _, r, _, _, info = env.step(np.zeros(7))
    assert info["swing_shortfall"] == pytest.approx(1.0)
    assert r == pytest.approx(6.5 - SWING_W)


# ---------------------------------------------------------------------------
# 3. it is a wrapper
# ---------------------------------------------------------------------------

def test_the_contract_passes_through_unchanged():
    base = _Base()
    env = SwingAwareEnv(base, _Stub(0.5))
    assert (env.observation_dim, env.action_dim, env.horizon) == (18, 7, 8)


def test_a_seeded_start_reaches_the_base_env():
    base = _Base()
    env = SwingAwareEnv(base, _Stub(0.5))
    env.reset(np.full(7, 0.25))
    assert np.allclose(env.u, 0.25)


def test_the_report_is_stamped_as_a_surrogate_and_keeps_the_base_report():
    env = SwingAwareEnv(_Base(), _Stub(0.5))
    env.reset()
    env.step(np.zeros(7))
    rep = env.report()
    assert rep["is_surrogate"] is True
    assert rep["is_analytic"] is True
    assert rep["swing_target_v"] == SWING_TARGET_V
    assert rep["swing_mean_shortfall"] == pytest.approx(0.5)


def test_every_step_is_stamped_so_a_consumer_cannot_mistake_it():
    env = SwingAwareEnv(_Base(), _Stub(0.5))
    env.reset()
    _, _, _, _, info = env.step(np.zeros(7))
    assert info["is_surrogate"] is True


def test_bad_constants_are_refused():
    with pytest.raises(ValueError, match="target"):
        SwingAwareEnv(_Base(), _Stub(0.5), target_v=0.0)
    with pytest.raises(ValueError, match="weight"):
        SwingAwareEnv(_Base(), _Stub(0.5), weight=-1.0)


def test_the_registered_constants_are_entry_38s():
    assert (SWING_TARGET_V, SWING_W) == (1.00, 6.0)


# ---------------------------------------------------------------------------
# 4. Q2 is MEASURED, not predicted
# ---------------------------------------------------------------------------

def test_the_headroom_number_comes_from_the_measured_value():
    scan = {"requests": [{"candidates": [
        {"feasible": False, "reason": "output swing 2518.0 mVpp exceeds the "
                                      "linear limit 1383.7 mVpp "
                                      "(vout_swing_v=1383.7 mVpp)"},
        {"feasible": False, "reason": "exceeds the linear limit 500.0 mVpp"},
        {"feasible": True, "reason": None},
        {"feasible": False, "reason": "pole-zero fit failed"},
    ]}]}
    assert SW._measured_limits_mv(scan) == [1383.7, 500.0]


# ---------------------------------------------------------------------------
# 5. the verdict is mechanical
# ---------------------------------------------------------------------------

def _arm(name, a, *, med=800.0, swing=0.3, measured=320, deployed=260):
    return {"arm": name, "accepted_at_k": ([1, 4, 5, 5, 6] if name == "library"
                                           else [0, 0, 0, 0, a]),
            "n_accepted": a, "accepted_ranks": [], "n_cand_feasible": 0,
            "n_cand_infeasible": 0, "n_cand_unscorable": 0,
            "n_sims_measured": measured, "n_sims_deployed": deployed,
            "swing_named": 0, "non_feasible": 0,
            "swing_fraction": (None if name == "library" else swing),
            "n_declined": 0, "artifact": None, "wall_clock_s": 1.0,
            "measured_limit_mv": {"n": 10, "median": med, "p25": med,
                                  "p75": med}}


def _res(*, lib=6, rnd=1, seeded=1, med=800.0, swing=0.3, lib_curve=None):
    a = _arm("library", lib)
    if lib_curve is not None:
        a["accepted_at_k"] = list(lib_curve)
    return {"k": 5, "arms": [a, _arm("swing_random", rnd, med=med, swing=swing),
                             _arm("swing_seeded", seeded, med=med, swing=swing)]}


def test_beating_the_library_is_the_d9_branch():
    v = SW._verdict(_res(seeded=7))
    assert v["Q3_beats_the_library"] and v["Q4_beats_its_blind_predecessor"]
    assert "D9'S CONDITION IS MET" in v["call"]


def test_beating_only_its_blind_predecessor_says_so_plainly():
    v = SW._verdict(_res(rnd=3))
    assert not v["Q3_beats_the_library"]
    assert v["Q4_beats_its_blind_predecessor"]
    assert "insufficient" in v["call"] and "DO NOT re-roll" in v["call"]


def test_TYING_the_library_is_not_beating_it():
    """The D9 bar is `>= 7`, not `>= 6`. The sabotage round found this gate
    green when `q3` was loosened to a tie, because no test case sat ON the
    boundary (G125)."""
    v = SW._verdict(_res(seeded=6))
    assert v["best_swing_arm"] == 6
    assert v["Q3_beats_the_library"] is False
    assert "D9'S CONDITION IS MET" not in v["call"]
    assert v["Q4_beats_its_blind_predecessor"] is True


def test_one_more_than_the_library_IS_beating_it():
    v = SW._verdict(_res(seeded=7))
    assert v["Q3_beats_the_library"] is True


def test_headroom_that_moved_without_converting_is_a_clean_negative():
    v = SW._verdict(_res(rnd=1, seeded=2, med=900.0))
    assert v["Q2_headroom_moved"] and not v["Q4_beats_its_blind_predecessor"]
    assert "did NOT convert" in v["call"]


def test_headroom_that_did_not_move_sends_you_to_the_wiring():
    v = SW._verdict(_res(med=400.0))
    assert not v["Q2_headroom_moved"]
    assert "CHECK THE WIRING" in v["call"]


def test_a_control_that_did_not_reproduce_dominates():
    v = SW._verdict(_res(seeded=9, lib_curve=[1, 4, 5, 5, 7]))
    assert not v["Q1_control_reproduced"]
    assert "D9'S CONDITION IS MET" not in v["call"]


def test_q5_wants_the_failure_mode_to_have_shifted():
    assert SW._verdict(_res(swing=0.3))["Q5_failure_mode_shifted"] is True
    assert SW._verdict(_res(swing=0.8))["Q5_failure_mode_shifted"] is False


def test_q6_catches_a_deck_count_that_does_not_add_up():
    r = _res()
    r["arms"][1]["n_sims_measured"] = 319
    assert SW._verdict(r)["Q6_accounting"] is False


def test_the_thresholds_are_entry_38s():
    assert SW.Q2_MIN_MEDIAN_SWING_MV == 700.0
    assert SW.Q3_BASELINE == 6 and SW.Q4_MIN_ACCEPT == 3
    assert SW.Q5_MAX_SWING_FRACTION == 0.50
