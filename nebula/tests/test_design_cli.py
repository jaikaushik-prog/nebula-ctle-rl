"""
Tests for `nebula/design.py` — the deliverable's front door.

**None of these runs ngspice.** What is under test is the CLI's honesty: that
it refuses a spec outside S3, that it says the peaking request is a band rather
than a target, and that it never reports a nominal design as corner-verified.

Three are gates in CLAUDEwa.md §8 rule 10's sense:

  * `test_the_report_never_calls_a_nominal_design_corner_verified` — the single
    most damaging thing a demo could imply. `G4_RESULTS.md` measured the cost:
    the best design at nominal failed 75 of 135 corner points.
  * `test_the_peaking_request_is_labelled_as_a_BAND_on_every_run` — the reward
    cannot see it, and a tool that quietly optimised a number its objective
    ignores would be advertising.
  * `test_a_target_outside_S3_is_refused_rather_than_clipped`
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from nebula import design as D
from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.rl.contract import N_ACTIONS


def _meas(peaking=7.5, f_oct=-0.5):
    return {"g_dc_db": 3.0, "peaking_db": peaking, "f_peak_oct": f_oct,
            "nyq_boost_db": 4.0, "inoise_vrms": 3.0e-4, "power_w": 5.0e-3,
            "pair_margin_v": 0.25, "tail_margin_v": 0.05}


def _fake_nominal(feasible=True, worst_spec="S3_f_peak"):
    return {"ok": True, "verdict": "valid", "meas": D._derived(_meas()),
            "params": {"w_in": 8.0e-5, "l_in": 2.2e-7, "nf_in": 4,
                       "i_bias": 1.1e-3, "rs": 430.0, "cs": 3.2e-12,
                       "rl": 240.0, "cl": 3.26e-14, "vcm_in": 1.58},
            "reward": 8.99, "feasible": feasible, "worst_spec": worst_spec,
            "design_id": "stub"}


# ─────────────────────────────────────────────────────────────────────────────


def test_a_target_outside_S3_is_refused_rather_than_clipped():
    lo_db, hi_db = SPEC_PEAKING_DB_RANGE
    lo_hz, hi_hz = SPEC_F_PEAK_HZ_RANGE
    with pytest.raises(ValueError, match="outside S3"):
        D.design(hi_db + 1.0, 1.9e9)
    with pytest.raises(ValueError, match="outside S3"):
        D.design((lo_db + hi_db) / 2, hi_hz * 2)
    # ... and the CLI turns that into an exit code, not a traceback
    assert D.main(["--peaking", str(hi_db + 1), "--f-peak", "1.9e9"]) == 2


def test_ghz_and_hz_are_both_accepted_and_mean_the_same_thing(monkeypatch):
    seen = {}

    def _fake_design(peaking_db, f_peak_hz, **kw):
        seen["f"] = f_peak_hz
        return {"request": {"peaking_db": peaking_db, "f_peak_hz": f_peak_hz,
                            "f_peak_ghz": f_peak_hz / 1e9},
                "method": "library", "robust_search": False,
                "nominal": {"ok": False, "verdict": "x", "reason": "stub"},
                "simulations": {"total": 0}, "wall_s": 0.0,
                "peaking_is_a_band_not_a_target": "..."}

    monkeypatch.setattr(D, "design", _fake_design)
    D.main(["--peaking", "9", "--f-peak", "1.9"])
    a = seen["f"]
    D.main(["--peaking", "9", "--f-peak", "1.9e9"])
    assert a == seen["f"] == pytest.approx(1.9e9), (
        "a GHz-shaped number and a Hz-shaped number must land on one target")


def test_the_peaking_request_is_labelled_as_a_BAND_on_every_run(monkeypatch):
    """**The gate.** `reward_v1` deliberately ignores `target_peaking_db`, so a
    tool that presented `--peaking` as an optimisation target would be claiming
    something its own objective cannot deliver."""
    monkeypatch.setattr(D, "solve_library",
                        lambda t, tb=True: {"u": [0.5] * N_ACTIONS,
                                            "reward": 8.99, "sims": 0,
                                            "n_candidates": 10,
                                            "n_tied_at_best": 1,
                                            "design_id": "stub"})
    monkeypatch.setattr(D, "measure", lambda *a, **k: _fake_nominal())
    d = D.design(9.0, 1.9e9)
    note = d["peaking_is_a_band_not_a_target"]
    assert "BAND" in note and "TIE-BREAK" in note
    assert "ignores target_peaking_db" in note
    # and it must survive into the human-readable report, not only the JSON
    assert "TIE-BREAK" in D.report(d)


def test_the_report_never_calls_a_nominal_design_corner_verified(monkeypatch):
    """**The most damaging thing a demo could imply.** Without `--robust` the
    search saw one corner. `G4_RESULTS.md` measured the cost: the strongest
    design at nominal failed **75 of 135** corner points."""
    monkeypatch.setattr(D, "solve_library",
                        lambda t, tb=True: {"u": [0.5] * N_ACTIONS,
                                            "reward": 8.99, "sims": 0,
                                            "n_candidates": 10,
                                            "n_tied_at_best": 1,
                                            "design_id": "stub"})
    monkeypatch.setattr(D, "measure", lambda *a, **k: _fake_nominal())
    text = D.report(D.design(9.0, 1.9e9))
    assert "NOT VERIFIED AT CORNERS" in text
    assert "75 of 135" in text
    # the real property: there is no POSITIVE claim of corner verification.
    # Every occurrence of "verified" must be negated -- the METHOD line
    # legitimately reads "NOT verified at corners", which is the point.
    low = text.lower()
    assert "corner verification" not in low and "all points pass" not in low
    i = 0
    while (i := low.find("verified", i)) != -1:
        assert low[max(0, i - 4):i] == "not ", (
            f"an un-negated 'verified' at offset {i}: "
            f"{text[max(0, i - 40):i + 30]!r}")
        i += 1


def test_the_peaking_tiebreak_only_breaks_TIES(monkeypatch):
    """It reorders designs that are already equal on the objective. If it ever
    started overriding the reward, the tool would be optimising a different
    problem from the one every published number was measured on."""
    import nebula.experiments.spec_pool as SP

    class _Pool:
        u = np.tile(np.linspace(0.1, 0.9, N_ACTIONS), (3, 1))
        meas = ({"peaking_db": 4.0}, {"peaking_db": 11.0}, {"peaking_db": 9.1})
        design_id = ("a", "b", "c")

        def __len__(self):
            return 3

    monkeypatch.setattr(SP, "load_pool", lambda *a, **k: _Pool())
    # b and c tie at the top; a is strictly worse
    monkeypatch.setattr(SP, "score_pool",
                        lambda pool, t: np.array([8.0, 8.9995, 8.9995]))
    t = D.SpecTarget(peaking_db=9.0, f_peak_hz=1.9e9)
    assert D.solve_library(t)["design_id"] == "c", "the tie-break lost"
    assert D.solve_library(t, peaking_tiebreak=False)["design_id"] == "b"

    # and when there is NO tie it must not override the objective
    monkeypatch.setattr(SP, "score_pool",
                        lambda pool, t: np.array([8.0, 8.9995, 8.5]))
    assert D.solve_library(t)["design_id"] == "b", (
        "the tie-break overrode a strictly better design")


def test_the_library_path_costs_zero_simulations(monkeypatch):
    import nebula.experiments.spec_pool as SP

    class _Pool:
        u = np.full((2, N_ACTIONS), 0.5)
        meas = ({"peaking_db": 7.0}, {"peaking_db": 8.0})
        design_id = ("a", "b")

        def __len__(self):
            return 2

    monkeypatch.setattr(SP, "load_pool", lambda *a, **k: _Pool())
    monkeypatch.setattr(SP, "score_pool", lambda pool, t: np.array([8.0, 8.9]))
    out = D.solve_library(D.SpecTarget(peaking_db=8.0, f_peak_hz=1.9e9))
    assert out["sims"] == 0


def test_every_reported_spec_row_names_its_requirement():
    """A measured number printed without the limit it is measured against is
    not a spec table."""
    for label, key, unit, req in D.SPEC_ROWS:
        assert label.strip() and key and unit and req
    keys = {k for _, k, _, _ in D.SPEC_ROWS}
    m = D._derived(_meas())
    assert keys <= set(m), f"the report asks for {keys - set(m)}"
    # the three S3 rows and both saturation margins must be present
    assert {"peaking_db", "_f_peak_ghz", "nyq_boost_db"} <= keys
    assert {"pair_margin_v", "tail_margin_v"} <= keys


def test_the_default_method_is_not_RL_and_the_choices_say_why():
    """CLAUDEwa §7: *"If BO matches RL, say so. That is a finding, not a
    loss."* The default is the measured-best answer, and `--help` states what
    PPO was measured to be rather than leaving a reader to assume."""
    import argparse

    p = [a for a in D.main.__doc__ or ""]          # main has no docstring; use the parser
    parser_help = D.__doc__
    assert "default method is not RL" in parser_help
    assert "indistinguishable from uniform random search" in parser_help
