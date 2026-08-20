"""
The two verification paths must read the SAME peak — session 22u.

`exp_g4_verify.py` holds two verification routines and they disagreed about
which peak they scored:

  * `verify()`      — 7 rows, `ac_peak_interp=True` since session 22e, scores
                      the sub-lattice interpolated peak.
  * `verify_full()` — 11 rows, **the 135-point compliance matrix every S8 and
                      every margin number in this project is reported on** —
                      read `pt.f_pk_hz` through `link/bridge.py`, the raw
                      `ac dec 50` lattice value.

That is G74's defect surviving in the place it mattered most, and rule 9's
failure (exactly one definition, referenced, never redeclared) in the file rule
9 was written for. One lattice step is **13.3 %** of `S3_f_peak`'s tolerance,
so the correction to the headline margin is a fraction of a step — but the
lattice **collapses six physically distinct corners onto one tied margin**, so
the matrix could not say which corner binds, which is the question the next
open decision (extend the 3-corner screen) turns on.

Gates here in CLAUDEwa.md §8 rule 10's sense — each was watched go red against
the pre-fix code:

  * `test_verify_full_scores_the_INTERPOLATED_peak`
  * `test_both_verification_paths_reach_the_peak_through_ONE_definition`
  * `test_the_two_paths_agree_on_f_peak_for_the_same_design` (simulator-backed)

Only the last needs ngspice.
"""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

from nebula.experiments import exp_g4_verify as G4
from nebula.rl.evaluator import (
    annotate_interpolated_peak,
    scored_meas,
)

#: Half an `ac dec 50` step. `SizingPoint.d_f_peak_octaves` is bounded by this
#: BY CONSTRUCTION, so a correction larger than it is not a refinement — it is
#: evidence that the Python argmax and `meas ac MAX` disagree about which
#: sample is the maximum.
HALF_STEP_OCT = math.log2(10.0 ** 0.02) / 2.0


def _meas(f_oct=-0.50, peaking=7.5):
    return {"g_dc_db": 3.0, "peaking_db": peaking, "f_peak_oct": f_oct,
            "nyq_boost_db": 4.0, "inoise_vrms": 3.0e-4, "power_w": 5.0e-3,
            "pair_margin_v": 0.25, "tail_margin_v": 0.05}


class _Pt:
    """The four attributes `annotate_interpolated_peak` reads off a result."""

    def __init__(self, peak_interp, f_hz=None, g_pk_db=None, g_dc_db=0.0):
        self.peak_interp = peak_interp
        self.f_pk_interp_hz = f_hz
        self.g_pk_interp_db = g_pk_db
        self._g_dc_db = g_dc_db
        self.f_pk_hz = 1.2589e9

    @property
    def has_interp_peak(self) -> bool:
        return self.f_pk_interp_hz is not None

    @property
    def peaking_interp_db(self) -> float:
        return self.g_pk_interp_db - self._g_dc_db

    @property
    def d_f_peak_octaves(self) -> float:
        return math.log2(self.f_pk_interp_hz / self.f_pk_hz)


# ─────────────────────────────────────────────────────────────────────────────
# The seam, without a simulator.
# ─────────────────────────────────────────────────────────────────────────────


def test_verify_full_scores_the_INTERPOLATED_peak():
    """**The gate.** Red against the pre-22u code, which passed no
    `ac_peak_interp` to `run_point` at all and read `dev.f_peak_hz`."""
    src = inspect.getsource(G4.verify_full)
    assert "ac_peak_interp=ac_peak_interp" in src, (
        "verify_full does not forward the flag to run_point, so the AC sweep "
        "never produces an interpolated peak to score")
    assert "scored_meas(" in src, (
        "verify_full does not route its measurement vector through the one "
        "definition of the swap")

    sig = inspect.signature(G4.verify_full)
    assert sig.parameters["ac_peak_interp"].default is True, (
        "the DEFAULT is the correctness fix; an opt-in flag leaves every "
        "caller on the lattice, which is where this defect came from")


def test_both_verification_paths_reach_the_peak_through_ONE_definition():
    """Rule 9, on the seam that broke it.

    `verify` holds an `EvalResult` and `verify_full` does not, so they call
    different entry points — but both must land on `evaluator`'s single rule
    rather than each re-implementing "which peak do I score".
    """
    assert "scoring_meas(" in inspect.getsource(G4.verify)
    assert "scored_meas(" in inspect.getsource(G4.verify_full)

    # …and the two entry points must BE one rule, not two that agree today.
    from nebula.rl import evaluator as E

    assert "scored_meas(" in inspect.getsource(E.scoring_meas), (
        "scoring_meas has stopped delegating; the two paths can now drift")


def test_the_artifact_states_which_peak_it_was_scored_on():
    """A margin quoted to four decimals off a lattice that quantises the row at
    13.3 % of its tolerance is a different measurement from the same margin off
    the parabola. The reader must not have to infer which one they hold."""
    src = inspect.getsource(G4.verify_full)
    assert '"ac_peak_interp": bool(ac_peak_interp)' in src
    for field in ("f_peak_oct_lattice", "f_peak_oct_scored",
                  "peaking_db_lattice", "peaking_db_scored",
                  "peak_interp_status"):
        assert field in G4.FullPointResult.__dataclass_fields__, field


# ─────────────────────────────────────────────────────────────────────────────
# `annotate_interpolated_peak` — the block lifted out of `evaluate`.
# ─────────────────────────────────────────────────────────────────────────────


def test_annotate_is_ADDITIVE_and_never_touches_the_lattice_pair():
    """The whole safety argument for G74: a reward computed from an un-swapped
    `meas` is bit-identical with the flag on or off."""
    m = _meas()
    annotate_interpolated_peak(
        m, None, _Pt({"ok": True}, f_hz=1.30e9, g_pk_db=7.6))
    assert m["f_peak_oct"] == -0.50 and m["peaking_db"] == 7.5
    assert m["f_peak_oct_interp"] != -0.50
    assert m["peaking_db_interp"] == pytest.approx(7.6)


def test_annotate_is_a_NO_OP_when_the_interpolation_was_not_asked_for():
    m = _meas()
    annotate_interpolated_peak(m, None, _Pt(None))
    assert m == _meas(), "the flag-off path must add nothing"


def test_a_refusal_adds_NOTHING_rather_than_defaulting_to_the_lattice():
    """"Absent" must mean "refused" and never "equal to the grid value" — a
    sentinel read as a measurement is G85's shape of mistake."""
    m = _meas()
    raw: dict = {}
    annotate_interpolated_peak(m, raw, _Pt({"ok": False, "edge": "top"}))
    assert "f_peak_oct_interp" not in m and "peaking_db_interp" not in m
    assert raw["peak_interp_status"] == "refused"
    # …and the scored vector then falls back to the LATTICE, not to the floor.
    assert scored_meas(m, True) == _meas()


def test_a_bottom_edge_carries_the_lattice_pair_forward_as_EXACT():
    """10 MHz is a grid point AND the boundary, so nothing was rounded. This is
    the right answer, not a fallback — and it must not read as a refusal."""
    m = _meas()
    raw: dict = {}
    annotate_interpolated_peak(m, raw, _Pt({"ok": False, "edge": "bottom"}))
    assert raw["peak_interp_status"] == "boundary_bottom_lattice_is_exact"
    assert raw["d_f_peak_octaves"] == 0.0
    assert m["f_peak_oct_interp"] == m["f_peak_oct"]
    assert scored_meas(m, True)["f_peak_oct"] == -0.50


def test_annotate_works_without_a_bookkeeping_dict():
    """`verify_full` keeps no `raw`; the `meas` side must be identical."""
    a, b = _meas(), _meas()
    pt = _Pt({"ok": True}, f_hz=1.30e9, g_pk_db=7.6)
    annotate_interpolated_peak(a, None, pt)
    annotate_interpolated_peak(b, {}, pt)
    assert a == b


# ─────────────────────────────────────────────────────────────────────────────
# Simulator-backed: the two paths, on one real design, at one real corner.
# ─────────────────────────────────────────────────────────────────────────────


def _have_sim() -> bool:
    import shutil

    from nebula.device.ngspice_runner import _DEFAULT_NGSPICE
    from nebula.device.sky130_runner import TRIMMED_LIB

    ng = _DEFAULT_NGSPICE.exists() or shutil.which("ngspice_con") is not None
    return ng and TRIMMED_LIB.exists()


#: The delivered design's box coordinates, read out of the published G4
#: artifact rather than transcribed — see the fixture below.
def _delivered_u():
    import json
    from pathlib import Path

    p = (Path(G4.__file__).parent / "g4_verify_results.json")
    if not p.exists():
        pytest.skip(f"{p.name} missing; run exp_g4_verify --run first")
    d = json.loads(p.read_text(encoding="utf-8"))
    row = next(r for r in d["results"] if r["role"] == "robust")
    return row["design_id"], tuple(float(x) for x in row["u"])


@pytest.mark.skipif(not _have_sim(), reason="ngspice/PDK not available")
def test_the_two_paths_agree_on_f_peak_for_the_same_design():
    """**The gate the whole session is about.**

    One design, one corner, one load, scored by both routines. Before the fix
    these differed by up to half a lattice step — 0.0332 octaves, 6.6 % of
    `S3_f_peak`'s tolerance — with nothing in either artifact to say so.

    They must now agree EXACTLY: `verify_full` and the search evaluator run
    different analysis decks (`swing`/`hd3` versus `.op+.ac+.noise`), but the
    `.ac` sweep and therefore the peak is the same measurement in both, so any
    disagreement at all is two definitions of one number.
    """
    from nebula.experiments.exp_g4_verify import Candidate
    from nebula.rl.contract import sizing_from_u
    from nebula.rl.evaluator import SpiceBudget, evaluate, scoring_meas

    class _C:
        process, vdd_scale, temp_c = "tt", 1.00, 27.0

    did, u = _delivered_u()
    cl = G4.PROMOTION_LOADS[1]

    full = G4.verify_full(
        Candidate(design_id=did, u=u, role="robust", source="test",
                  claimed_reward=0.0, claimed_worst_point=None),
        corners=[_C], loads=[cl])
    assert full["ac_peak_interp"] is True
    pt = full["points"][0]
    assert pt["ok"], pt["reason"]

    ev = evaluate(sizing_from_u(np.asarray(u), cl_f=float(cl)), SpiceBudget(),
                  corner="tt", temp_c=27.0, vdd_scale=1.00,
                  ac_peak_interp=True)
    search = scoring_meas(ev, True)
    assert search is not None

    assert pt["f_peak_oct_scored"] == pytest.approx(
        search["f_peak_oct"], rel=0, abs=1e-9), (
        "the compliance matrix and the search evaluator disagree about where "
        "the peak is")
    assert pt["peaking_db_scored"] == pytest.approx(
        search["peaking_db"], rel=0, abs=1e-9)

    # And the correction is a refinement, not a different reading (P4/P5).
    assert abs(pt["f_peak_oct_scored"] - pt["f_peak_oct_lattice"]) <= HALF_STEP_OCT
    assert pt["peaking_db_scored"] >= pt["peaking_db_lattice"] - 1e-12


# ─────────────────────────────────────────────────────────────────────────────
# The joint winner's checklist becomes an ARTIFACT — session 22u.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_joint_winner_is_verified_by_the_SAME_routine(monkeypatch):
    """**A comparison between two designs measured by two routines measures the
    routines.** The report's headline table puts the joint winner beside the
    delivered design; both columns must come from `verify_full`.
    """
    from nebula.experiments import exp_joint_search as J

    assert "verify_full" in inspect.getsource(J.verify), (
        "the joint winner is being checked by something other than the "
        "routine the delivered design is checked by")


def test_verify_RAISES_rather_than_inventing_a_design(tmp_path, monkeypatch):
    """CLAUDEwa.md §8 rule 1: a missing artifact fails loudly. It does not get
    a placeholder, and it does not get a design somebody typed in."""
    from nebula.experiments import exp_joint_search as J

    monkeypatch.setattr(J, "RESULTS", tmp_path / "absent.json")
    with pytest.raises(FileNotFoundError, match="run `--run` before"):
        J.verify(out_path=tmp_path / "out.json")

    bad = tmp_path / "bad.json"
    bad.write_text('{"spec_set": [], "best": {"ok": false, "u": [], '
                   '"reward": -10.0}}', encoding="utf-8")
    monkeypatch.setattr(J, "RESULTS", bad)
    with pytest.raises(ValueError, match="nothing to verify"):
        J.verify(out_path=tmp_path / "out.json")


def test_the_joint_artifact_records_WHAT_THE_SEARCH_SAW_too(monkeypatch,
                                                            tmp_path):
    """The search scored 6 points on `V4_SPECS`; the checklist scores 135 on
    `V3_SPECS`. Those are different questions, and an artifact that reports
    only the second invites the first's reward to be read as a 135-point one."""
    from nebula.experiments import exp_joint_search as J

    src = inspect.getsource(J.verify)
    assert '"searched_on"' in src
    for k in ("spec_set", "n_points", "reward"):
        assert k in src
