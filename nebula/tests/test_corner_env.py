"""
Tests for `rl/corner_env.py` — **reward on the worst corner, not on nominal.**

**None of these runs ngspice.** Both the base env's evaluator and this module's
are stubbed, and the stub is keyed on the corner so a design can be made good
at nominal and bad at SS — which is the only interesting case and the one the
whole module exists for.

Three are gates in CLAUDEwa.md §8 rule 10's sense:

  * `test_termination_follows_the_WORST_point_not_the_nominal_one` — §12's
    named trap, *"optimising at nominal and checking corners afterwards"*. If
    this relaxes, a run can end the moment TT is happy and report a design that
    fails at SS.
  * `test_every_extra_simulation_is_charged_to_the_budget` — 7f rule 1.
  * `test_points_zero_must_be_the_point_the_config_describes` — the footgun:
    `EnvConfig` defaults to tt/27 C while `PROBLEMS["P3"].points[0]` is
    ss/0.95/125 C.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pytest

from nebula.rl import corner_env as CE
from nebula.rl import env as ENV
from nebula.rl import reward_v1 as R
from nebula.rl.contract import N_ACTIONS
from nebula.rl.env import EnvConfig
from nebula.rl.evaluator import Verdict


@dataclass
class _Point:
    label: str
    corner: str
    vdd_scale: float
    temp_c: float
    cl_f: float


NOMINAL = _Point("tt/1.00/27C", "tt", 1.00, 27.0, 32.6e-15)
SS_HOT = _Point("ss/0.95/125C", "ss", 0.95, 125.0, 32.6e-15)
FF_COLD = _Point("ff/1.05/0C", "ff", 1.05, 0.0, 32.6e-15)


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


def _meas(peaking=7.5, f_oct=-0.5, power=5e-3):
    return {"g_dc_db": 3.0, "peaking_db": peaking, "f_peak_oct": f_oct,
            "nyq_boost_db": 4.0, "inoise_vrms": 3.0e-4, "power_w": power,
            "pair_margin_v": 0.25, "tail_margin_v": 0.05}


def _install(monkeypatch, by_corner):
    """Stub BOTH evaluators — the base env has its own import."""
    calls = {"n": 0, "corners": []}

    def _fake(sizing, budget, corner="tt", temp_c=27.0, vdd_scale=1.0,
              keep_raw_text=False, ac_peak_interp=False):
        calls["n"] += 1
        calls["corners"].append(corner)
        r = by_corner(corner, temp_c)
        budget.charge(r.n_spice, 0.0)
        return r

    monkeypatch.setattr(ENV, "evaluate", _fake)
    monkeypatch.setattr(CE, "evaluate", _fake)
    return calls


def _env(monkeypatch, by_corner, points=(NOMINAL, SS_HOT, FF_COLD)):
    calls = _install(monkeypatch, by_corner)
    e = CE.CornerCtleEnv.from_points(points, seed=1)
    return e, calls


# ─────────────────────────────────────────────────────────────────────────────


def test_the_reward_is_the_WORST_point_not_the_nominal_one(monkeypatch):
    """The four words §7 rests on. Nominal is feasible and SS is not, so the
    reward must come from SS."""
    def by_corner(corner, temp_c):
        if corner == "ss":
            return _Stub(Verdict.VALID, None, _meas(power=14.9e-3))
        return _Stub(Verdict.VALID, None, _meas())

    e, _ = _env(monkeypatch, by_corner)
    obs, info = e.reset()
    ss = [p for p in info["points"] if p["label"] == SS_HOT.label][0]
    nom = [p for p in info["points"] if p["label"] == NOMINAL.label][0]
    assert ss["reward"] < nom["reward"], "the stub did not make SS worse"
    assert info["reward"] == pytest.approx(ss["reward"])
    assert info["worst_point"] == SS_HOT.label
    assert info["nominal_reward"] == pytest.approx(nom["reward"])


def test_termination_follows_the_WORST_point_not_the_nominal_one(monkeypatch):
    """**CLAUDEwa §12's named trap, as a gate.**

    *"Optimising at nominal and checking corners afterwards. Score on worst
    corner from the start."* The base env terminates the moment ITS point is
    feasible. If that leaked through, an episode would end with TT happy and
    SS failing, and the run would report a design it never checked.
    """
    def by_corner(corner, temp_c):
        if corner == "ss":
            # valid, measured, and INFEASIBLE: peaking below S3's floor
            return _Stub(Verdict.VALID, None, _meas(peaking=1.0))
        return _Stub(Verdict.VALID, None, _meas())

    e, _ = _env(monkeypatch, by_corner)
    e.reset()
    obs, reward, terminated, truncated, info = e.step(np.zeros(N_ACTIONS))
    nominal_feasible = R.reward(_meas(), e.cfg.target_f_peak_hz,
                                specs=e.cfg.specs).feasible
    assert nominal_feasible, "the stub's nominal point must be feasible"
    assert info["nominal_reward"] > reward
    assert not terminated, (
        "the episode ended on NOMINAL feasibility while SS was infeasible")
    assert info["feasible"] is False


def test_it_terminates_when_EVERY_point_is_feasible(monkeypatch):
    def by_corner(corner, temp_c):
        return _Stub(Verdict.VALID, None, _meas())

    e, _ = _env(monkeypatch, by_corner)
    e.reset()
    _, _, terminated, _, info = e.step(np.zeros(N_ACTIONS))
    assert terminated and info["feasible"] is True


def test_every_extra_simulation_is_charged_to_the_budget(monkeypatch):
    """7f rule 1. A corner-aware method that did not pay for its corners would
    look free next to a nominal one."""
    def by_corner(corner, temp_c):
        return _Stub(Verdict.VALID, None, _meas())

    e, calls = _env(monkeypatch, by_corner)
    e.reset()
    before = e.budget.calls
    e.step(np.zeros(N_ACTIONS))
    assert e.budget.calls - before == 3, "one simulation per point"
    assert e.n_extra_sims > 0
    assert calls["corners"][-3:] == ["tt", "ss", "ff"]


def test_the_short_circuit_is_exact_and_saves_simulations(monkeypatch):
    """`invalid_reward` is the global minimum of the four bands, so once a
    point returns the floor nothing can lower the minimum. Skipping the rest is
    exact, and it is the SAME argument `baselines.Objective` makes."""
    def by_corner(corner, temp_c):
        if corner == "ss":
            return _Stub(Verdict.INVALID, "ngspice: no convergence", None)
        return _Stub(Verdict.VALID, None, _meas())

    e, calls = _env(monkeypatch, by_corner)
    e.reset()
    n0 = calls["n"]
    _, reward, _, _, info = e.step(np.zeros(N_ACTIONS))
    # tt then ss -> ss floors it -> ff is never simulated
    assert calls["n"] - n0 == 2, "the third point should have been skipped"
    assert reward == pytest.approx(R.invalid_reward(len(e.cfg.specs)))
    assert e.n_short_circuited >= 1
    assert [p["label"] for p in info["points"]] == [NOMINAL.label, SS_HOT.label]


def test_an_invalid_NOMINAL_skips_every_corner(monkeypatch):
    """The base env already terminated on an unusable measurement and the
    floor is the global minimum, so no corner can lower it."""
    def by_corner(corner, temp_c):
        return _Stub(Verdict.INVALID, "the reported peak IS the sweep edge",
                     None)

    calls = _install(monkeypatch, by_corner)
    e = CE.CornerCtleEnv.from_points((NOMINAL, SS_HOT, FF_COLD), seed=3)
    # reset retries until nominal is valid; it never is, so it must RAISE
    # rather than return a design nothing was measured on
    with pytest.raises(Exception):
        e.reset()


def test_points_zero_must_be_the_point_the_config_describes():
    """**The footgun.** `EnvConfig` defaults to tt/27 C/1.00 while
    `PROBLEMS["P3"].points[0]` is ss/0.95/125 C, so a caller building both by
    hand can silently evaluate the wrong corner at the observation point."""
    cfg = EnvConfig(seed=0)                       # tt / 27 C / 1.00
    with pytest.raises(ValueError, match="points\\[0\\] must be the point"):
        CE.CornerCtleEnv(cfg, (SS_HOT, NOMINAL))
    with pytest.raises(ValueError, match="at least one point"):
        CE.CornerCtleEnv(cfg, ())


def test_from_points_derives_the_config_so_nobody_has_to_remember():
    e = CE.CornerCtleEnv.from_points((SS_HOT, NOMINAL), seed=7)
    assert e.cfg.corner == "ss"
    assert e.cfg.temp_c == 125.0
    assert e.cfg.vdd_scale == 0.95
    assert e.cfg.seed == 7
    # and it still refuses a mismatch it cannot derive away
    assert e.points[0] is SS_HOT


def test_which_corner_binds_is_the_table_G4_reports(monkeypatch):
    """If one corner binds nearly always, a fixed screen would do; if it moves,
    worst-case scoring is doing real work. Either reading is a result, and
    neither is available without counting."""
    def by_corner(corner, temp_c):
        pk = {"tt": 7.5, "ss": 4.0, "ff": 11.0}[corner]
        return _Stub(Verdict.VALID, None, _meas(peaking=pk))

    e, _ = _env(monkeypatch, by_corner)
    e.reset()
    for _ in range(4):
        e.step(np.zeros(N_ACTIONS))
    w = e.which_corner_binds()
    assert w["n_designs"] == 5
    assert set(w["binding_counts"]) <= {p.label for p in e.points}
    assert sum(w["binding_counts"].values()) == 5
    assert w["most_binding"] is not None
    assert pytest.approx(sum(w["binding_fraction"].values())) == 1.0
    assert w["points"] == [p.label for p in e.points]


def test_a_single_point_env_reduces_to_the_base_env(monkeypatch):
    """The degenerate case must not be a special case: one point means no
    extra simulations and the nominal reward IS the worst reward."""
    def by_corner(corner, temp_c):
        return _Stub(Verdict.VALID, None, _meas())

    e, calls = _env(monkeypatch, by_corner, points=(NOMINAL,))
    e.reset()
    n0 = calls["n"]
    _, reward, _, _, info = e.step(np.zeros(N_ACTIONS))
    assert calls["n"] - n0 == 1
    assert e.n_extra_sims == 0
    assert reward == pytest.approx(info["nominal_reward"])
