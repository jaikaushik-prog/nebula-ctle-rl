"""
§6c/§6d — the episode, and the rule that an invalid result never becomes an
observation.

MOST OF THIS RUNS WITHOUT A SIMULATOR, AND THAT IS DELIBERATE. The behaviour
under test is the env's CONTRACT — what terminates an episode, what an
invalidity does to the observation, what gets logged — and that is exactly the
part a simulator would make slow and non-deterministic to exercise. The
evaluator is stubbed with a scripted sequence of results, so a test can ask
"what happens on the third step if it comes back invalid?" and get an answer
in milliseconds. The tests that genuinely need ngspice are marked and skip
cleanly without it, in the style of the rest of this suite.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.rl import env as env_mod
from nebula.rl import reward_v1 as R
from nebula.rl.contract import (
    ACTION_NAMES,
    HORIZON,
    MAX_STEP,
    N_ACTIONS,
    N_OBS,
    sizing_from_u,
)
from nebula.rl.env import CtleSizingEnv, EnvConfig
from nebula.rl.evaluator import EvalResult, SpiceBudget, Verdict

def _have_ngspice() -> bool:
    """Ask the runner, not PATH.

    `shutil.which("ngspice_con")` misses the conda-env binary the whole project
    uses (G20), so a check written that way SKIPS the only test that exercises
    the real simulator — silently, and it reads as a pass. `ngspice_path()`
    knows where it lives.
    """
    from nebula.device.ngspice_runner import ngspice_path
    try:
        return ngspice_path().exists()
    except FileNotFoundError:
        return False


HAVE_NGSPICE = _have_ngspice()


# ── a scripted evaluator, so the episode logic is testable at speed ─────────

def _good(**over):
    m = {"g_dc_db": 6.0, "peaking_db": 7.5, "f_peak_oct": -0.5,
         "nyq_boost_db": 6.9, "inoise_vrms": 2.2e-4, "power_w": 6.0e-3,
         "pair_margin_v": 0.26, "tail_margin_v": 0.33}
    m.update(over)
    return m


def _headroom(pair=0.26, tail=0.33) -> dict:
    return {"pair_margin_v": pair, "tail_margin_v": tail,
            "v_src_dc": 0.465, "v_out_dc": 0.881,
            "i_supply_a": 3.3e-3, "power_w": 6.0e-3}


def _ok(meas=None, did="d0") -> EvalResult:
    m = meas or _good()
    return EvalResult(verdict=Verdict.VALID, meas=m,
                      headroom=_headroom(m["pair_margin_v"], m["tail_margin_v"]),
                      raw={"gm": 0.012},
                      design_id=did, geometry_tag="g", n_spice=1, seconds=0.01)


def _bad(reason="ngspice: singular matrix") -> EvalResult:
    """INVALID: nothing trustworthy. Note the default reason is deliberately
    NOT a triode one any more — a triode design is HEADROOM_ONLY under Call 1,
    and using it here would have made every 'invalid' test secretly test the
    graded band instead."""
    return EvalResult.invalid(reason, n_spice=1, seconds=0.01,
                              design_id_="dX", geometry_tag="g")


def _triode(pair=-0.05, tail=0.33) -> EvalResult:
    """HEADROOM_ONLY: `.op` converged, a device is out of saturation."""
    return EvalResult(verdict=Verdict.HEADROOM_ONLY,
                      reason=f"out of saturation (input pair {pair * 1e3:+.1f} mV)",
                      meas=None, headroom=_headroom(pair, tail),
                      raw={"vds": 0.05}, design_id="dT", geometry_tag="g",
                      n_spice=1, seconds=0.01)


class _Script:
    """Hand the env a fixed sequence of evaluation results."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def __call__(self, sizing, budget, **kw):
        r = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        budget.charge(r.n_spice, r.seconds)
        return r


@pytest.fixture
def scripted(monkeypatch):
    def _install(results):
        s = _Script(results)
        monkeypatch.setattr(env_mod, "evaluate", s)
        return s
    return _install


# ── construction-time gate proof ────────────────────────────────────────────

def test_constructing_the_env_proves_the_netlist_gates_can_fail(scripted):
    """§6a's two gates are asserted live at construction, every time."""
    scripted([_ok()])
    CtleSizingEnv(EnvConfig(seed=1))          # must not raise


def test_env_refuses_to_construct_if_a_gate_is_disabled(monkeypatch, scripted):
    scripted([_ok()])
    monkeypatch.setattr(env_mod, "assert_no_inert_writes", lambda text: None)
    with pytest.raises(AssertionError, match="did NOT reject"):
        CtleSizingEnv(EnvConfig(seed=1))


# ── shapes ──────────────────────────────────────────────────────────────────

def test_reset_returns_a_contract_shaped_observation(scripted):
    scripted([_ok()])
    env = CtleSizingEnv(EnvConfig(seed=1))
    obs, info = env.reset()
    assert obs.shape == (N_OBS,) and obs.dtype == float
    assert np.all(np.isfinite(obs))
    assert info["reset_attempts"] == 1


def test_step_rejects_a_wrong_width_action(scripted):
    scripted([_ok()])
    env = CtleSizingEnv(EnvConfig(seed=1))
    env.reset()
    with pytest.raises(ValueError, match="action dims"):
        env.step(np.zeros(N_ACTIONS + 1))


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_step_rejects_a_blown_up_policy(scripted, bad):
    """A nan action is a policy blow-up, not a design. It must not be clipped
    into something plausible."""
    scripted([_ok()])
    env = CtleSizingEnv(EnvConfig(seed=1))
    env.reset()
    a = np.zeros(N_ACTIONS); a[0] = bad
    with pytest.raises(ValueError, match="nan/inf"):
        env.step(a)


# ── the action is a CLIPPED DELTA ───────────────────────────────────────────

def test_an_action_moves_the_sizing_by_at_most_max_step(scripted):
    scripted([_ok()])
    env = CtleSizingEnv(EnvConfig(seed=1))
    env.reset(u0=np.full(N_ACTIONS, 0.5))
    before = env._u.copy()
    env.step(np.full(N_ACTIONS, 10.0))        # far outside [-1, 1]
    assert np.allclose(env._u - before, MAX_STEP), (
        "an out-of-range action must be CLIPPED to one MAX_STEP, not scaled")


def test_the_sizing_stays_inside_the_box(scripted):
    scripted([_ok()] * 50)
    env = CtleSizingEnv(EnvConfig(seed=1))
    env.reset(u0=np.full(N_ACTIONS, 0.5))
    for _ in range(HORIZON):
        env.step(np.full(N_ACTIONS, 1.0))
        assert np.all(env._u >= 0.0) and np.all(env._u <= 1.0)


# ── §6d: an invalid result terminates, and never becomes an observation ────

def test_an_invalid_evaluation_terminates_the_episode(scripted):
    """*'An invalid result is a hard negative reward and a terminated episode,
    never a missing value, never a silently substituted default.'*"""
    scripted([_ok(), _bad()])
    env = CtleSizingEnv(EnvConfig(seed=1, specs=R.V1_SPECS))
    env.reset()
    obs, r, terminated, truncated, info = env.step(np.zeros(N_ACTIONS))
    assert terminated and not truncated
    assert info["valid"] is False
    assert r == R.invalid_reward(len(R.V1_SPECS))


def test_the_observation_after_an_invalidity_is_the_last_VALID_one(scripted):
    """Not a zero-fill, not a default: a true statement about a circuit that
    was actually measured. PPO never bootstraps through it, because the step
    is TERMINATED rather than truncated."""
    scripted([_ok(_good(peaking_db=7.5)), _bad()])
    env = CtleSizingEnv(EnvConfig(seed=1))
    obs0, _ = env.reset()
    obs1, _, terminated, _, _ = env.step(np.zeros(N_ACTIONS))
    assert terminated
    # The measurement block is unchanged; only the sizing and step index moved.
    assert np.allclose(obs0[N_ACTIONS:N_ACTIONS + 8], obs1[N_ACTIONS:N_ACTIONS + 8])
    assert np.all(np.isfinite(obs1))


def test_an_invalid_result_is_never_retried_into_a_different_answer(scripted):
    """The env must not paper over an invalidity by evaluating again."""
    s = scripted([_ok(), _bad(), _ok()])
    env = CtleSizingEnv(EnvConfig(seed=1))
    env.reset()
    _, _, terminated, _, _ = env.step(np.zeros(N_ACTIONS))
    assert terminated
    assert s.calls == 2, (
        "the env evaluated again after an invalid result; a retry that quietly "
        "succeeds with different numbers is exactly what §6d forbids")


# ── termination vs truncation ───────────────────────────────────────────────

def test_success_terminates_early(scripted):
    scripted([_ok()] * 10)
    env = CtleSizingEnv(EnvConfig(seed=1, specs=R.V1_SPECS))
    env.reset()
    _, r, terminated, truncated, info = env.step(np.zeros(N_ACTIONS))
    assert info["feasible"] and terminated and not truncated


def test_the_horizon_truncates_rather_than_terminating(scripted):
    """A cut horizon is bootstrapped through; a failure is not. Conflating the
    two credits a broken circuit with the value of whatever came next."""
    infeasible = _good(peaking_db=1.0)         # outside the 3-12 dB band
    scripted([_ok(infeasible)] * 40)
    env = CtleSizingEnv(EnvConfig(seed=1, horizon=4, specs=R.V1_SPECS))
    env.reset()
    for i in range(3):
        _, _, terminated, truncated, _ = env.step(np.zeros(N_ACTIONS))
        assert not terminated and not truncated
    _, _, terminated, truncated, _ = env.step(np.zeros(N_ACTIONS))
    assert truncated and not terminated


# ── §6d: the invalid rate is measured ───────────────────────────────────────

def test_the_invalid_rate_and_its_mechanism_histogram_are_recorded(scripted):
    scripted([_ok(), _bad("input pair is in TRIODE: vds 0.0 V <= vdsat 0.3 V")])
    env = CtleSizingEnv(EnvConfig(seed=1))
    env.reset()
    env.step(np.zeros(N_ACTIONS))
    assert env.n_eval == 2 and env.n_invalid == 1
    assert env.invalid_rate == pytest.approx(0.5)
    assert env.invalid_reasons == {"pair_triode": 1}, (
        "the invalidity was not classified by MECHANISM; a single aggregate "
        "rate says the agent found holes but not which")


@pytest.mark.parametrize("reason,bucket", [
    ("unrealisable geometry: no realisable ... 40 ohm", "unrealisable_geometry"),
    ("the reported peak IS the sweep edge: f_pk 2e10 Hz", "peak_is_sweep_edge"),
    ("input pair is in TRIODE: vds 0.0 <= vdsat 0.3", "pair_triode"),
    ("tail is in TRIODE: vds_tail 0.0 <= vdsat_tail 0.2", "tail_triode"),
    ("DC node v(outp) = -0.3 V is outside the rails [..]", "outside_rails"),
    ("f_pk = 1e6 Hz is outside [1e+07, 1.8e+10]", "f_peak_range"),
    ("g_dc_db = 99 dB is outside [-80, 60] - not an amplifier", "gain_range"),
    ("ngspice: singular matrix", "ngspice"),
    ("something nobody predicted", "other"),
])
def test_every_documented_invalidity_lands_in_its_own_bucket(scripted, reason, bucket):
    scripted([_ok()])
    env = CtleSizingEnv(EnvConfig(seed=1))
    assert env._classify(reason) == bucket


# ── §6j: every evaluation is recorded ───────────────────────────────────────

def test_every_evaluation_including_the_reset_is_recorded(scripted):
    scripted([_ok()] * 10)
    env = CtleSizingEnv(EnvConfig(seed=1, horizon=3,
                                  specs=("S3_peaking",)))
    env.reset()
    assert len(env.records) == 1, "the reset evaluation must be logged too"
    env.step(np.zeros(N_ACTIONS))
    assert len(env.records) == 2


def test_a_record_carries_everything_task_8_needs(scripted):
    scripted([_ok()] * 4)
    seen = []
    env = CtleSizingEnv(EnvConfig(seed=1), on_step=seen.append)
    env.reset()
    rec = seen[0]
    for field in ("design_id", "geometry_tag", "action", "u", "params",
                  "meas", "raw", "reward", "margins", "shortfalls",
                  "n_spice", "seconds"):
        assert hasattr(rec, field), f"StepRecord has no {field}"
    assert rec.design_id, "a record without a design_id breaks the grouped split"
    assert set(rec.params) >= set(("w_in", "l_in", "nf_in", "i_bias", "rs",
                                   "cs", "rl", "cl", "vcm_in"))


def test_an_invalid_record_carries_its_reason_and_no_measurement(scripted):
    scripted([_ok(), _bad("tail is in TRIODE: x")])
    env = CtleSizingEnv(EnvConfig(seed=1))
    env.reset()
    env.step(np.zeros(N_ACTIONS))
    rec = env.records[-1]
    assert rec.valid is False
    assert rec.meas is None, "an invalid record must carry NO numbers (rule 1)"
    assert "TRIODE" in rec.invalid_reason


# ── §6i: the budget counts every call ───────────────────────────────────────

def test_the_budget_counts_reset_calls_as_well_as_step_calls(scripted):
    """*'every SPICE invocation counted, including those spent on setup, warm
    start, or discarded episodes.'*"""
    scripted([_ok()] * 10)
    b = SpiceBudget()
    env = CtleSizingEnv(EnvConfig(seed=1, horizon=3,
                                  specs=("S3_peaking",)), budget=b)
    env.reset()
    assert b.calls == 1, "the reset evaluation was not charged"
    env.step(np.zeros(N_ACTIONS))
    assert b.calls == 2


def test_discarded_reset_attempts_are_charged(scripted):
    """A reset that draws an invalid start retries — and every draw is a real
    SPICE call that must appear in the budget."""
    scripted([_bad(), _bad(), _ok()])
    b = SpiceBudget()
    env = CtleSizingEnv(EnvConfig(seed=1), budget=b)
    _, info = env.reset()
    assert info["reset_attempts"] == 3
    assert b.calls == 3, "the two discarded draws were not charged"


# ── seeding ─────────────────────────────────────────────────────────────────

def test_the_seed_travels_through_the_config_and_reproduces(scripted):
    """HANDOFF G3: never `np.random.seed()`."""
    scripted([_ok()] * 40)
    a = CtleSizingEnv(EnvConfig(seed=99)); a.reset()
    b = CtleSizingEnv(EnvConfig(seed=99)); b.reset()
    c = CtleSizingEnv(EnvConfig(seed=100)); c.reset()
    assert np.allclose(a._u, b._u)
    assert not np.allclose(a._u, c._u)


def test_a_seeded_start_that_is_not_a_circuit_raises_rather_than_redrawing(scripted):
    """A warm start must be MEASURED before it is used, not assumed."""
    scripted([_bad()])
    env = CtleSizingEnv(EnvConfig(seed=1))
    with pytest.raises(ValueError, match="not a valid circuit"):
        env.reset(u0=np.full(N_ACTIONS, 0.5))


def test_a_box_with_no_valid_point_raises_instead_of_looping(scripted):
    scripted([_bad()] * 100)
    env = CtleSizingEnv(EnvConfig(seed=1))
    with pytest.raises(RuntimeError, match="no valid start point"):
        env.reset()


# ── the real thing ──────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAVE_NGSPICE, reason="needs ngspice (HANDOFF G20/G33)")
def test_design_432_is_feasible_and_terminates_immediately():
    """The end-to-end path, against the one design the project trusts."""
    from nebula.experiments.rl_smoke import design_432_u

    b = SpiceBudget()
    env = CtleSizingEnv(EnvConfig(seed=1, specs=R.V1_SPECS), budget=b)
    obs, info = env.reset(u0=design_432_u())
    assert obs.shape == (N_OBS,) and np.all(np.isfinite(obs))
    assert info["reward"] > R.feasible_bonus(len(R.V1_SPECS)), (
        "design 432 must be FEASIBLE under reward v1; if it is not, the reward "
        "or the evaluator has moved and §6f's calibration is stale")
    assert b.calls == 1
