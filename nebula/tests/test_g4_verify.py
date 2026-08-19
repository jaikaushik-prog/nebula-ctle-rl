"""
Tests for `experiments/exp_g4_verify.py` — G4's verification harness.

**None of these runs ngspice.** The evaluator is stubbed; what is under test is
the harness's honesty, not the circuit.

Two are gates in CLAUDEwa.md §8 rule 10's sense:

  * `test_the_control_arm_is_the_STRONGEST_nominal_designs` — a verification
    that only runs on designs expected to pass cannot fail (G73). The control
    has to be the best nominal designs, not weak ones, or its failure proves
    nothing.
  * `test_verify_does_NOT_short_circuit` — the search stops at the floor
    because nothing below it exists; a verification that stops there cannot say
    which points failed, which is the only thing it is for.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pytest

from nebula.experiments import exp_g4_verify as G4
from nebula.rl.contract import N_ACTIONS
from nebula.rl.evaluator import SpiceBudget, Verdict


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


def _trial(design_id, problem, reward, feasible, method="uniform", rep=0,
           prescreen=False, worst_point="x"):
    return {"kind": "event", "event": "trial", "problem": problem,
            "design_id": design_id, "u": [0.5] * N_ACTIONS, "reward": reward,
            "feasible": feasible, "method": method, "replicate": rep,
            "prescreen": prescreen, "worst_point": worst_point, "n_sims": 1}


def _log(tmp_path, rows):
    p = tmp_path / "log.jsonl.gz"
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def test_robust_candidates_come_from_P3_and_controls_from_P1(tmp_path):
    log = _log(tmp_path, [
        _trial("r1", "P3", 8.03, True),
        _trial("n1", "P1", 8.99, True),
        _trial("x1", "P1", -2.0, False),          # infeasible, not a control
        _trial("x2", "P3", -2.0, False),
    ])
    cands = G4.candidates(log, n_control=5)
    roles = {c.design_id: c.role for c in cands}
    assert roles == {"r1": "robust", "n1": "nominal_only"}


def test_the_control_arm_is_the_STRONGEST_nominal_designs(tmp_path):
    """**G73's gate.** A weak nominal design failing at corners proves nothing;
    the control has to be the best thing the nominal search produced, so that
    its failure is a statement about CORNERS rather than about the design."""
    log = _log(tmp_path, [
        _trial("weak", "P1", 8.10, True),
        _trial("best", "P1", 8.99, True),
        _trial("mid", "P1", 8.50, True),
    ])
    cands = G4.candidates(log, n_control=2)
    ids = [c.design_id for c in cands if c.role == "nominal_only"]
    assert ids == ["best", "mid"], "the control is not the strongest designs"


def test_a_design_certified_at_P3_is_never_also_used_as_a_control(tmp_path):
    """The two arms must be disjoint or the control is contaminated."""
    log = _log(tmp_path, [_trial("d", "P3", 8.03, True),
                          _trial("d", "P1", 8.99, True)])
    cands = G4.candidates(log, n_control=5)
    assert [c.role for c in cands] == ["robust"]


def test_verify_does_NOT_short_circuit(monkeypatch):
    """**The gate.** The search short-circuits at the invalid floor because
    nothing below it exists. A verification that did the same could not report
    WHICH points failed, which is its only job."""
    n = {"calls": 0}

    def _fake(sizing, budget, corner="tt", temp_c=27.0, vdd_scale=1.0,
              keep_raw_text=False, ac_peak_interp=False):
        n["calls"] += 1
        budget.charge(1, 0.0)
        # every point is invalid: a short-circuiting verifier would stop at one
        return _Stub(Verdict.INVALID, "ngspice: no convergence", None)

    monkeypatch.setattr(G4, "evaluate", _fake)
    cand = G4.Candidate("d", tuple([0.5] * N_ACTIONS), "robust", "uniform/0",
                        8.0, "x")
    corners = G4.all_corners()[:4]
    loads = (1.0e-14, 3.0e-14)
    out = G4.verify(cand, SpiceBudget(), corners=corners, loads=loads)
    assert n["calls"] == len(corners) * len(loads) == 8
    assert out["n_points"] == 8 and out["n_failed"] == 8
    assert out["all_points_pass"] is False


def test_verify_reports_whether_the_worst_point_was_SCREENED(monkeypatch):
    """The whole finding of session 22k-run: the screen is 3 corners and the
    binding point need not be one of them. If this stops being reported the
    result becomes unreadable."""
    def _fake(sizing, budget, corner="tt", temp_c=27.0, vdd_scale=1.0,
              keep_raw_text=False, ac_peak_interp=False):
        budget.charge(1, 0.0)
        # make an UNSCREENED process corner the worst one
        pk = 3.05 if corner in ("sf", "fs") else 7.5
        return _Stub(Verdict.VALID, None, _meas(peaking=pk))

    monkeypatch.setattr(G4, "evaluate", _fake)
    cand = G4.Candidate("d", tuple([0.5] * N_ACTIONS), "robust", "uniform/0",
                        8.0, "x")
    out = G4.verify(cand, SpiceBudget(), loads=(3.0e-14,))
    assert out["worst_is_a_screen_corner"] is False
    assert out["worst_point"].split("/")[0] in ("sf", "fs")
    assert "n_failed_outside_the_screen" in out


def test_the_verification_grid_is_S9s_own(monkeypatch):
    """45 corners x 3 loads, not a subset chosen for cost."""
    assert len(G4.all_corners()) == 45
    assert len(G4.PROMOTION_LOADS) == 3
    # and the screen really is a strict subset of it
    grid = {(c.process, c.vdd_scale, c.temp_c) for c in G4.all_corners()}
    screen = {(c.process, c.vdd_scale, c.temp_c) for c in G4.SCREEN_CORNERS}
    assert screen < grid
    assert len(screen) == 3
    # the mixed process corners exist in the grid and are NOT screened -- which
    # is where session 22k-run's failures all landed
    assert {"sf", "fs"} <= {p for p, _, _ in grid}
    assert not ({"sf", "fs"} & {p for p, _, _ in screen})
