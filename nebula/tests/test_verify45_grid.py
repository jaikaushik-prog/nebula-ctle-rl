"""Gates for `exp_sac_q3.verify45` -- the verifier that could not report a pass.

**NO SPICE.** `verify_full` is patched with a fake that returns point records
of the REAL shape (`dataclasses.asdict(FullPointResult)`), because the defect
being pinned is precisely a mismatch between the fields the caller reads and
the fields the callee produces. A fake with invented keys would reproduce the
bug rather than catch it, so the field names are taken from the dataclass
itself (G125: the gate's data must separate the correct rule from the broken
one).

The two defects, both silent `dict.get` defaults:

  * `p.get("mandated", True)` on records with no `mandated` field kept all
    **135** load-swept points and reported them as `n_pvt45_total` -- merging
    G109's compliance grid with this project's own characterisation axis;
  * `p.get("pass")` on records whose field is `feasible` made `npass` **always
    zero**, so `compliant` was **always False for every input**.
"""

from __future__ import annotations

import dataclasses

import pytest

from nebula.experiments import exp_sac_q3 as Q
from nebula.experiments.adaptive_screen import EDGE4_MANDATED
from nebula.experiments.exp_g4_verify import FullPointResult

CL_DESIGN = float(EDGE4_MANDATED[0].cl_f)
# `verify_request`'s rule: the design load is the MEDIAN of the three
# `PROMOTION_LOADS`, so the fakes must straddle it.
CL_LO, CL_HI = 1.36e-14, 7.80e-14
assert CL_LO < CL_DESIGN < CL_HI
REQ = {"peaking_db": 10.0, "f_peak_hz": 1.921e9}


def _point(cl_f: float, feasible: bool) -> dict:
    """A point record of the REAL shape, built from the real dataclass."""
    return dataclasses.asdict(FullPointResult(
        corner="tt", vdd_scale=1.0, temp_c=27.0, cl_f=cl_f, ok=True,
        reason=None, margins={}, failed_specs=[], reward=14.2,
        feasible=feasible))


def _grid(pass_at_design: int = 45, pass_at_other: int = 0) -> list[dict]:
    """135 points: 45 at each of three loads, as `verify_full` returns."""
    pts = []
    for i in range(45):
        pts.append(_point(CL_DESIGN, i < pass_at_design))
    for cl in (CL_LO, CL_HI):
        for i in range(45):
            pts.append(_point(cl, i < pass_at_other))
    return pts


def _patch(monkeypatch, points, rescored=None, spy=None):
    """Patch both halves of the real path.

    `_rescore` is patched rather than exercised because its own behaviour is
    `exp_coverage`'s to test; what THIS module must guarantee is that it is
    called **with the request**, which is defect 3, and that its output is what
    the verdict is counted from.
    """
    import nebula.experiments.exp_coverage as C
    import nebula.experiments.exp_g4_verify as V

    monkeypatch.setattr(V, "verify_full", lambda cand, **kw: {"points": points})

    def _fake_rescore(pts, f_hz, pk_db):
        if spy is not None:
            spy.append((f_hz, pk_db))
        if rescored is not None:
            return rescored
        return [{"cl_f": float(q["cl_f"]), "reward": 14.0,
                 "feasible": bool(q["feasible"]), "failed": [],
                 "corner": q["corner"], "vdd_scale": q["vdd_scale"],
                 "temp_c": q["temp_c"]} for q in pts]

    monkeypatch.setattr(C, "_rescore", _fake_rescore)


# ---------------------------------------------------------------------------
# the real dataclass has neither field the old code read
# ---------------------------------------------------------------------------

def test_the_point_record_has_no_pass_and_no_mandated_field():
    """The root cause, pinned against the producer. If either field is ever
    added, this reddens and the reader can be simplified deliberately rather
    than two definitions drifting apart again."""
    names = {f.name for f in dataclasses.fields(FullPointResult)}
    assert "pass" not in names
    assert "mandated" not in names
    assert "feasible" in names and "cl_f" in names


# ---------------------------------------------------------------------------
# the grid
# ---------------------------------------------------------------------------

def test_verify45_scores_the_45_MANDATED_corners_not_all_135(monkeypatch):
    _patch(monkeypatch, _grid(pass_at_design=45, pass_at_other=0))
    got = Q.verify45([0.5] * 7, REQ)
    assert got["n_pvt45_total"] == 45
    assert got["n_pvt45_pass"] == 45
    assert got["compliant"] is True


def test_verify45_CAN_report_a_pass(monkeypatch):
    """The defect in one line: the old implementation returned
    `compliant=False` for a design passing every point of every grid."""
    _patch(monkeypatch, _grid(pass_at_design=45, pass_at_other=45))
    assert Q.verify45([0.5] * 7, REQ)["compliant"] is True


def test_verify45_reports_the_135_point_grid_SEPARATELY(monkeypatch):
    """G109: compliance and characterisation in separate columns, neither
    dropped. A design compliant at 45 and failing the load sweep must show
    both, not one merged number."""
    _patch(monkeypatch, _grid(pass_at_design=45, pass_at_other=0))
    got = Q.verify45([0.5] * 7, REQ)
    assert got["compliant"] is True
    assert got["n_full135_pass"] == 45 and got["n_full135_total"] == 135
    assert got["compliant_135"] is False


def test_verify45_is_not_compliant_when_one_mandated_corner_fails(monkeypatch):
    _patch(monkeypatch, _grid(pass_at_design=44, pass_at_other=45))
    got = Q.verify45([0.5] * 7, REQ)
    assert got["n_pvt45_pass"] == 44 and got["compliant"] is False


def test_verify45_ignores_load_sweep_failures_for_the_45_verdict(monkeypatch):
    """The old code could not distinguish these: a design that is compliant on
    the mandated grid and fails only at 13.6/78.0 fF was reported as failing,
    which is the understated-pass half of G109."""
    _patch(monkeypatch, _grid(pass_at_design=45, pass_at_other=0))
    got = Q.verify45([0.5] * 7, REQ)
    assert got["compliant"] is True and got["compliant_135"] is False


# ---------------------------------------------------------------------------
# it fails loudly instead of defaulting
# ---------------------------------------------------------------------------

def test_verify45_RAISES_when_a_point_carries_no_load(monkeypatch):
    """The load is what selects the mandated grid; a point without one cannot
    be placed and must stop the verdict rather than be dropped."""
    pts = _grid()
    for p in pts:
        p.pop("cl_f")
    _patch(monkeypatch, pts)
    with pytest.raises(KeyError):
        Q.verify45([0.5] * 7, REQ)


def test_verify45_RAISES_when_the_design_load_does_not_select_45(monkeypatch):
    """If the grid moves, the function must stop rather than report a verdict
    on a different population (G110's rule about the validation set).
    Three loads are kept so the failure is the 45-count, not the load axis."""
    pts = ([_point(CL_DESIGN, True) for _ in range(44)]
           + [_point(CL_LO, True) for _ in range(45)]
           + [_point(CL_HI, True) for _ in range(45)])
    _patch(monkeypatch, pts)
    with pytest.raises(ValueError, match="not the 45"):
        Q.verify45([0.5] * 7, REQ)


def test_verify45_selects_the_MEDIAN_load_as_the_design_load(monkeypatch):
    """`verify_request`'s own rule, mirrored: the design load is the median of
    the three `PROMOTION_LOADS`. Picking the first would select 13.6 fF, the
    lightest, where G109 measured the load axis doing 56-74 % of the f_peak
    excursion -- i.e. the hardest plane, not the mandated one."""
    pts = ([_point(CL_LO, False) for _ in range(45)]
           + [_point(CL_DESIGN, True) for _ in range(45)]
           + [_point(CL_HI, False) for _ in range(45)])
    _patch(monkeypatch, pts)
    got = Q.verify45([0.5] * 7, REQ)
    assert got["n_pvt45_pass"] == 45 and got["compliant"] is True
    assert got["n_full135_pass"] == 45


def test_verify45_RAISES_on_an_empty_verification(monkeypatch):
    _patch(monkeypatch, [])
    with pytest.raises(ValueError, match="measured nothing"):
        Q.verify45([0.5] * 7, REQ)


def test_verify45_selects_by_the_screens_own_design_load(monkeypatch):
    """One definition of the design load (rule 9): `EDGE4_MANDATED`'s. A
    hard-coded 32.6 fF would drift the moment the screen moved."""
    pts = ([_point(CL_DESIGN, True) for _ in range(45)]
           + [_point(CL_LO, True) for _ in range(45)]
           + [_point(CL_HI, True) for _ in range(45)])
    _patch(monkeypatch, pts)
    got = Q.verify45([0.5] * 7, REQ)
    assert got["n_pvt45_total"] == 45 and got["n_full135_total"] == 135


# ---------------------------------------------------------------------------
# defect 3 -- the request must actually be used
# ---------------------------------------------------------------------------

def test_verify45_scores_against_THE_REQUEST_not_LEGACY_TARGET(monkeypatch):
    """The defect that survived the first repair. `verify_full` scores
    `FULL_SPECS` -- 11 rows against `LEGACY_TARGET` (7.5 dB @ 1.7678 GHz) --
    and carries none of the three request-dependent rows. On entry 42's one
    screen-feasible design that difference was 45/45 against 44/45."""
    from nebula.rl.spec_dist import LEGACY_TARGET

    spy: list = []
    _patch(monkeypatch, _grid(), spy=spy)
    Q.verify45([0.5] * 7, REQ)
    assert spy, "_rescore was never called: the request is being ignored"
    f_hz, pk_db = spy[0]
    assert (f_hz, pk_db) == (REQ["f_peak_hz"], REQ["peaking_db"])
    assert f_hz != LEGACY_TARGET.f_peak_hz
    assert pk_db != LEGACY_TARGET.peaking_db


def test_verify45_counts_the_RESCORED_verdict_not_verify_fulls(monkeypatch):
    """`verify_full`'s own `feasible` is the 11-row legacy reading. The
    compliance verdict must come from the re-scored 13-row one."""
    pts = _grid(pass_at_design=45, pass_at_other=45)      # legacy says all pass
    rescored = [{"cl_f": float(q["cl_f"]), "reward": -2.0, "feasible": False,
                 "failed": ["S3_peaking_match"], "corner": q["corner"],
                 "vdd_scale": q["vdd_scale"], "temp_c": q["temp_c"]}
                for q in pts]
    _patch(monkeypatch, pts, rescored=rescored)
    got = Q.verify45([0.5] * 7, REQ)
    assert got["compliant"] is False and got["n_pvt45_pass"] == 0
    assert got["failing_rows_45"] == ["S3_peaking_match"]
    # the legacy reading is still reported, and named so it cannot be quoted
    assert got["legacy_11row_45_pass_DO_NOT_QUOTE"] == 45


def test_verify45_records_what_it_scored_against(monkeypatch):
    _patch(monkeypatch, _grid())
    got = Q.verify45([0.5] * 7, REQ)
    assert got["scored_against"] == {"peaking_db": 10.0,
                                     "f_peak_hz": 1.921e9}


def test_verify45_RAISES_when_the_load_axis_is_not_three(monkeypatch):
    """The design load is the MEDIAN of three. With two or four, 'median' is
    not the design load and the 45 would be selected from the wrong plane."""
    pts = [_point(CL_DESIGN, True) for _ in range(45)]
    pts += [_point(CL_LO, True) for _ in range(45)]
    _patch(monkeypatch, pts)
    with pytest.raises(ValueError, match="distinct loads"):
        Q.verify45([0.5] * 7, REQ)


def test_verify45_counts_an_unscorable_point_as_a_non_pass(monkeypatch):
    """G107: 'cannot be scored' is not 'fails', but it is not a PASS either."""
    pts = _grid()
    rescored = [{"cl_f": float(q["cl_f"]), "reward": None, "feasible": False,
                 "unscorable": True, "failed": ["EYE_UNMEASURABLE"],
                 "corner": q["corner"], "vdd_scale": q["vdd_scale"],
                 "temp_c": q["temp_c"]} for q in pts]
    _patch(monkeypatch, pts, rescored=rescored)
    got = Q.verify45([0.5] * 7, REQ)
    assert got["compliant"] is False
    assert got["n_unscorable_45"] == 45
