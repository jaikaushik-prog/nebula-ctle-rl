"""
Tests for `experiments/exp_attribution.py` — session 22b's D4 attribution.

The definition arm runs on the stored calibration CSV and needs no simulator.
The two simulated arms are stubbed, as `test_baselines.py` does.

Three of these are gates in CLAUDEwa.md §8 rule 10's sense, each checked by
deliberately breaking its input and watching it go red:

  * `test_the_legacy_load_is_read_from_the_file_not_assumed` — the 150 fF that
    reframes D4 must come from the data, and must fail loudly if the column is
    not constant.
  * `test_the_s3_test_is_imported_not_reimplemented` — rule 9: two files ask
    the same question and there must be one answer.
  * `test_the_tail_axis_is_blocked_and_the_block_is_measured` — the blocked
    axis is a measured fact about `validate`, not a claim in a docstring.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pytest

from nebula.experiments import exp_attribution as A
from nebula.experiments import exp_difficulty as D
from nebula.rl import evaluator as E
from nebula.rl import reward_v1 as R
from nebula.rl.contract import N_ACTIONS, sizing_from_u
from nebula.rl.evaluator import Verdict


# ─────────────────────────────────────────────────────────────────────────────
# Cause 1 — the definition. Real data, no simulator.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_legacy_load_is_read_from_the_file_not_assumed(tmp_path):
    """`LEGACY_CL_F` must equal what the calibration population actually used.

    This is the number that reframes D4 — `PLAN.md` calls 13.44 % "the measured
    rate at `cl_mid`" and the file says every row is 150 fF — so it may not be
    a constant somebody typed.

    **Proven able to fail:** setting `LEGACY_CL_F = 32.63e-15` turns the first
    assertion red; handing `legacy_cl_f` a two-load CSV raises rather than
    averaging, which is the second half.
    """
    assert A.legacy_cl_f() == pytest.approx(A.LEGACY_CL_F, rel=1e-12)
    # RATIO, not `!= approx(...)`. `pytest.approx` carries a default
    # **abs=1e-12**, and every capacitance in this project is femtofarads --
    # so 150 fF and 32.63 fF compare EQUAL under the default and the assertion
    # silently passes on any two loads. The repo's units footgun in miniature.
    assert abs(A.LEGACY_CL_F / A._CL.cl_mid_f - 1.0) > 0.5, (
        "the calibration population is NOT at cl_mid — that is the finding")
    assert A.LEGACY_CL_F / A._CL.cl_mid_f == pytest.approx(4.598, abs=1e-3)

    # A population without one load has no "the load", and saying so beats
    # returning a mean nobody chose.
    bad = tmp_path / "two_loads.csv"
    with bad.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cl"])
        w.writerow(["1.5e-13"])
        w.writerow(["3.263e-14"])
    with pytest.raises(ValueError, match="not one"):
        A.legacy_cl_f(bad)


def test_the_definition_report_reproduces_the_published_two_row_rate():
    """13.44 % must fall out of the stored population under its own test.

    If this drifts, either the CSV changed or `prescreen`'s S3 test did, and
    every attribution built on the difference is meaningless.
    """
    d = A.definition_report()
    assert d["n"] == 1890
    assert d["s3_two_row_rate"] == pytest.approx(0.1344, abs=5e-4)
    assert d["cl_f"] == pytest.approx(A.LEGACY_CL_F)


def test_the_s3_test_is_imported_not_reimplemented():
    """Rule 9: `exp_difficulty` and `exp_attribution` ask one question.

    **Proven able to fail:** giving `exp_attribution` its own copy of the
    predicate makes this identity check red the moment the two drift.
    """
    assert A.margins_meet_s3 is D.margins_meet_s3
    ok = {"S3_peaking": 0.1, "S3_f_peak": 0.0, "S3_nyq_boost": 3.0}
    assert A.margins_meet_s3(ok)
    assert not A.margins_meet_s3(dict(ok, S3_nyq_boost=-1e-9))
    assert not A.margins_meet_s3(None) and not A.margins_meet_s3({})


def test_the_tail_row_is_excluded_rather_than_defaulted():
    """The population has no tail device, so its margin is not a measurement.

    Defaulting it to 0.0 would read as "exactly at the saturation boundary" and
    silently fail every row; defaulting it to a plausible number would fabricate
    a measurement (rule 1). `+inf` plus an explicit note is the honest form.
    """
    d = A.definition_report()
    assert "tail" in d["note"].lower()
    # The 7-row rate must therefore be >= the 3-row rate minus the other rows'
    # effect, and must NOT be zero — which is what a 0.0 default would give.
    assert d["s3_v1_rate_no_tail_row"] > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Cause 4 — the blocked axis, measured rather than claimed.
# ─────────────────────────────────────────────────────────────────────────────


def _have_sim() -> bool:
    import shutil
    from nebula.device.ngspice_runner import _DEFAULT_NGSPICE
    from nebula.device.sky130_runner import TRIMMED_LIB
    ng = _DEFAULT_NGSPICE.exists() or shutil.which("ngspice_con") is not None
    return ng and TRIMMED_LIB.exists()


@pytest.mark.skipif(not _have_sim(), reason="ngspice or SKY130 absent")
def test_the_tail_axis_is_blocked_and_the_block_is_measured():
    """An ideal-tail design really does come back invalid, for the stated reason.

    `TAIL_AXIS_BLOCKED` claims `validate` requires the tail primitives. A
    docstring is not evidence, so this runs one and reads the reason.

    **Proven able to fail:** if `validate` is ever relaxed to treat a missing
    tail as a configuration, this goes red — which is exactly when the
    attribution's fourth cause becomes measurable and the constant must go.
    """
    sizing = sizing_from_u([0.5] * N_ACTIONS, cl_f=A._CL.cl_mid_f)
    ev = E.evaluate(sizing, E.SpiceBudget(), real_tail=False)
    assert ev.verdict is Verdict.INVALID
    assert "vds_tail" in (ev.reason or ""), (
        f"the tail axis is blocked for a DIFFERENT reason than recorded: "
        f"{ev.reason!r} — update TAIL_AXIS_BLOCKED")
    assert "vds_tail" in A.TAIL_AXIS_BLOCKED


# ─────────────────────────────────────────────────────────────────────────────
# The simulated arms, stubbed.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _Stub:
    verdict: Verdict
    reason: Optional[str]
    meas: Optional[dict]
    headroom: Optional[dict] = None
    design_id: str = "stub"
    geometry_tag: Optional[str] = "stub"
    n_spice: int = 1
    seconds: float = 0.0

    @property
    def valid(self) -> bool:
        return self.verdict is Verdict.VALID


def _meas(f_peak_oct: float = -0.5) -> dict:
    return {"g_dc_db": 5.0, "peaking_db": 7.5, "f_peak_oct": f_peak_oct,
            "nyq_boost_db": 6.0, "inoise_vrms": 2e-4, "power_w": 5e-3,
            "pair_margin_v": 0.26, "tail_margin_v": 0.33}


@pytest.fixture
def stub_pass(monkeypatch):
    seen = {"real_passives": [], "cl": []}

    def fake(sizing, budget, corner="tt", temp_c=27.0, vdd_scale=1.0,
             keep_raw_text=False, real_tail=True, real_passives=True):
        seen["real_passives"].append(real_passives)
        seen["cl"].append(sizing.params["cl"])
        budget.charge(1, 0.0)
        return _Stub(Verdict.VALID, None, _meas())

    monkeypatch.setattr(A, "evaluate", fake)
    return seen


def test_an_arm_charges_every_simulation_and_stops_on_the_budget(stub_pass):
    r = A.run_arm("t", 32.63e-15, True, n_sims=25)
    assert r["n_sims"] == 25 and len(stub_pass["real_passives"]) == 25
    assert r["s3_rate"] == pytest.approx(1.0)


def test_each_arm_moves_exactly_the_axis_it_names(stub_pass):
    A.run_arm("drawn", 32.63e-15, True, n_sims=8)
    assert all(stub_pass["real_passives"])
    assert all(c == pytest.approx(32.63e-15) for c in stub_pass["cl"])
    stub_pass["real_passives"].clear(); stub_pass["cl"].clear()

    A.run_arm("ideal", 32.63e-15, False, n_sims=8)
    assert not any(stub_pass["real_passives"]), "the passives axis did not move"
    stub_pass["real_passives"].clear(); stub_pass["cl"].clear()

    A.run_arm("legacy", A.LEGACY_CL_F, True, n_sims=8)
    assert all(stub_pass["real_passives"]), "the load arm must keep drawn passives"
    assert all(c == pytest.approx(A.LEGACY_CL_F) for c in stub_pass["cl"])


def test_an_invalid_design_still_costs_its_simulation(monkeypatch):
    def fake(sizing, budget, **kw):
        budget.charge(1, 0.0)
        return _Stub(Verdict.INVALID, "peak is the sweep edge: f_pk = 1.9e10",
                     None)
    monkeypatch.setattr(A, "evaluate", fake)
    r = A.run_arm("t", 32.63e-15, True, n_sims=10)
    assert r["n_sims"] == 10 and r["n_s3"] == 0
    assert r["invalid_rate"] == pytest.approx(1.0)
    assert r["s3_rate_among_scorable"] is None


def test_the_three_arms_isolate_the_two_measurable_causes():
    names = [a[0] for a in A.ARMS]
    assert names == ["cl_mid_drawn", "cl_legacy_drawn", "cl_mid_ideal_passives"]
    # The baseline arm is the sweep's own configuration...
    assert A.ARMS[0][1] == pytest.approx(A._CL.cl_mid_f) and A.ARMS[0][2] is True
    # ...and each other arm differs from it in exactly ONE axis.
    for name, cl_f, rp in A.ARMS[1:]:
        moved = [cl_f != A.ARMS[0][1], rp != A.ARMS[0][2]]
        assert sum(moved) == 1, f"{name} moves {sum(moved)} axes, not 1"


def test_wilson_separates_the_two_candidate_answers_at_this_n():
    """The arm size must be able to tell 7.10 % from 13.44 %.

    A sample size that cannot distinguish the two answers would produce an
    attribution that is a coin flip dressed as a measurement.
    """
    lo7, hi7 = A.wilson(int(0.0710 * A.ARM_SIMS), A.ARM_SIMS)
    lo13, hi13 = A.wilson(int(0.1344 * A.ARM_SIMS), A.ARM_SIMS)
    assert hi7 < lo13, (f"n={A.ARM_SIMS} cannot separate 7.10 % from 13.44 %: "
                        f"[{lo7:.4f},{hi7:.4f}] overlaps [{lo13:.4f},{hi13:.4f}]")


def test_wilson_matches_the_estimator_s3_yield_already_uses():
    from nebula.experiments.s3_yield import wilson_ci
    for k, n in ((0, 100), (7, 100), (134, 1000), (1, 3)):
        assert A.wilson(k, n) == pytest.approx(wilson_ci(k, n), rel=1e-12)
