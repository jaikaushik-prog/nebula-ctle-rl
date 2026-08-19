"""
Tests for the `terminate_on_feasible` seam — session 22n's experiment.

**None of these runs ngspice or PPO.** `_ObjectiveEnv` is driven directly with
a stubbed evaluator, because what is under test is the termination policy and
the accounting, not the policy network.

Three are gates in CLAUDEwa.md §8 rule 10's sense:

  * `test_the_flag_defaults_to_the_PUBLISHED_behaviour` — if the default ever
    flips, every number in `BASELINES.md` silently changes meaning.
  * `test_an_INVALID_evaluation_still_terminates` — §6d: there is no
    observation to continue from, so suppressing that termination would feed
    the policy a stale measurement and call it current.
  * `test_diagnostics_survive_BudgetExhausted` — the trap that cost session
    22g an arm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pytest

from nebula.experiments import baselines as B
from nebula.rl import env as ENV
from nebula.rl.contract import N_ACTIONS
from nebula.rl.env import EnvConfig
from nebula.rl.evaluator import Verdict


@dataclass
class _Stub:
    verdict: Verdict
    reason: Optional[str]
    meas: Optional[dict]
    headroom: Optional[dict] = None
    design_id: str = "stub"
    geometry_tag: str = "stub"
    n_spice: int = 1
    seconds: float = 0.0
    raw: dict = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return self.verdict is Verdict.VALID


def _meas(peaking=7.5, f_oct=-0.5):
    return {"g_dc_db": 3.0, "peaking_db": peaking, "f_peak_oct": f_oct,
            "nyq_boost_db": 4.0, "inoise_vrms": 3.0e-4, "power_w": 5.0e-3,
            "pair_margin_v": 0.25, "tail_margin_v": 0.05}


#: A design that meets every spec, so `rb.feasible` is True and the base env
#: would terminate on it.
FEASIBLE = _meas()
#: In the band but nowhere near: still feasible, lower reward.
INVALID = None


def _install(monkeypatch, factory):
    def _fake(sizing, budget, corner="tt", temp_c=27.0, vdd_scale=1.0,
              keep_raw_text=False, ac_peak_interp=False):
        r = factory()
        budget.charge(r.n_spice, 0.0)
        return r

    monkeypatch.setattr(ENV, "evaluate", _fake)
    monkeypatch.setattr(B, "evaluate", _fake)


def _env(monkeypatch, terminate, budget_sims=200, factory=None):
    factory = factory or (lambda: _Stub(Verdict.VALID, None, dict(FEASIBLE)))
    _install(monkeypatch, factory)
    obj = B.Objective(B.PROBLEMS["P1"], budget_sims, ac_peak_interp=False)
    cfg = EnvConfig(seed=3, cl_f=B.PROBLEMS["P1"].points[0].cl_f)
    return obj, B._ObjectiveEnv(obj, cfg, terminate_on_feasible=terminate)


# ─────────────────────────────────────────────────────────────────────────────


def test_the_flag_defaults_to_the_PUBLISHED_behaviour(monkeypatch):
    """**The gate.** Every number in `BASELINES.md` was measured with the
    episode ending at first feasibility. A flipped default would change what
    they mean without changing what they say."""
    import inspect

    assert "terminate_on_feasible: bool = True" in inspect.getsource(
        B._ObjectiveEnv.__init__)
    sig = inspect.signature(B.method_ppo)
    assert sig.parameters["terminate_on_feasible"].default is True

    obj, env = _env(monkeypatch, terminate=True)
    env.reset()
    _, _, terminated, _, info = env.step(np.zeros(N_ACTIONS))
    assert info["feasible"] and terminated, (
        "the default must still end the episode on success")
    assert env.n_suppressed == 0


def test_the_fix_keeps_a_FEASIBLE_episode_running(monkeypatch):
    obj, env = _env(monkeypatch, terminate=False)
    env.reset()
    for _ in range(3):
        _, _, terminated, truncated, info = env.step(np.zeros(N_ACTIONS))
        assert info["feasible"], "the stub must be feasible for this test"
        assert not terminated, "a feasible episode was still terminated"
    assert env.n_suppressed == 3


def test_the_horizon_still_truncates(monkeypatch):
    """Suppressing success-termination must not make an episode run forever."""
    obj, env = _env(monkeypatch, terminate=False, budget_sims=500)
    env.reset()
    seen = False
    for _ in range(env.env.cfg.horizon + 2):
        _, _, terminated, truncated, _ = env.step(np.zeros(N_ACTIONS))
        if truncated:
            seen = True
            break
    assert seen, f"no truncation within horizon {env.env.cfg.horizon}"


def test_an_INVALID_evaluation_still_terminates(monkeypatch):
    """**§6d.** An unusable measurement has no observation to continue from, so
    suppressing that termination would feed the policy a stale measurement and
    call it current. The flag suppresses SUCCESS only."""
    state = {"n": 0}

    def factory():
        state["n"] += 1
        if state["n"] <= 2:                     # reset + first step succeed
            return _Stub(Verdict.VALID, None, dict(FEASIBLE))
        return _Stub(Verdict.INVALID, "ngspice: no convergence", None)

    obj, env = _env(monkeypatch, terminate=False, factory=factory)
    env.reset()
    env.step(np.zeros(N_ACTIONS))               # valid, suppressed
    _, _, terminated, _, info = env.step(np.zeros(N_ACTIONS))
    assert info["valid"] is False
    assert terminated, "an invalid evaluation must still end the episode"


def test_the_mechanism_counter_separates_the_two_arms(monkeypatch):
    """`steps_from_feasible` is the mechanism check. The control cannot
    ACCUMULATE feasible-state experience -- but it is not exactly zero, because
    a reset can land feasible and the first step out of it precedes any
    termination. That distinction is asserted rather than glossed."""
    def _cycle():
        """Every third evaluation is feasible, so each episode goes
        infeasible -> infeasible -> feasible. An always-feasible stub makes
        both arms identical and measures nothing.

        **The cycle also exposes a state leak across the episode boundary.**
        The control terminates on its third call; its NEXT reset is
        infeasible, so a `_last_feasible` carried over from the terminal state
        would wrongly credit the new episode's first step.
        """
        _cycle.n += 1
        if _cycle.n % 3 in (1, 2):
            return _Stub(Verdict.VALID, None, _meas(peaking=1.0))   # below S3
        return _Stub(Verdict.VALID, None, dict(FEASIBLE))

    _cycle.n = 0
    obj_c, ctrl = _env(monkeypatch, terminate=True, budget_sims=200,
                       factory=_cycle)
    for _ in range(2):                       # TWO episodes: the leak needs both
        ctrl.reset()
        for _ in range(4):
            _, _, term, _, _ = ctrl.step(np.zeros(N_ACTIONS))
            if term:
                break

    _cycle.n = 0
    obj_t, fix = _env(monkeypatch, terminate=False, budget_sims=200,
                      factory=_cycle)
    fix.reset()
    for _ in range(5):
        fix.step(np.zeros(N_ACTIONS))

    assert ctrl.steps_from_feasible == 0, (
        "the control terminated on success, so it can never take a step FROM "
        "a feasible state within an episode -- a non-zero count here means "
        "`_last_feasible` leaked across the episode boundary")
    # The 3-cycle is what makes the control's episode boundary land on an
    # INFEASIBLE reset (see `_cycle`), and the price of that is that the fix
    # arm only meets a feasible state one call in three -- so the honest
    # assertion is separation, not a large count.
    assert fix.steps_from_feasible >= 1, (
        "the fix must accumulate feasible-state experience")
    assert fix.steps_from_feasible > ctrl.steps_from_feasible
    assert fix.n_suppressed >= 1, (
        "no success-termination was suppressed, so the flag did nothing")
    d = fix.diagnostics()
    assert set(d) >= {"terminate_on_feasible", "n_episodes", "n_steps",
                      "steps_from_feasible", "fraction_of_steps_from_feasible",
                      "n_terminations_suppressed"}
    assert d["terminate_on_feasible"] is False
    assert 0.0 <= d["fraction_of_steps_from_feasible"] <= 1.0


def test_diagnostics_survive_BudgetExhausted(monkeypatch):
    """**The trap that cost session 22g an arm.** The budget raises from deep
    inside PPO's rollout and unwinds past every `return`, so a run that
    completes NORMALLY is exactly the one whose diagnostics vanish. They are
    written in a `finally`, onto the objective."""
    import inspect

    src = inspect.getsource(B.method_ppo)
    assert "finally:" in src and "obj.method_diagnostics" in src, (
        "method_ppo must stash diagnostics where BudgetExhausted cannot take "
        "them")
    obj = B.Objective(B.PROBLEMS["P1"], 10)
    assert obj.method_diagnostics == {}, "the field must exist and start empty"


def test_every_simulation_is_still_counted_in_both_arms(monkeypatch):
    """7f rule 1 is not relaxed by the flag: a longer episode costs more
    simulations and must be charged for them."""
    for terminate in (True, False):
        obj, env = _env(monkeypatch, terminate=terminate, budget_sims=9)
        with pytest.raises(B.BudgetExhausted):
            env.reset()
            while True:
                env.step(np.zeros(N_ACTIONS))
        assert obj.n_sims == 9, f"terminate={terminate} overran its budget"
