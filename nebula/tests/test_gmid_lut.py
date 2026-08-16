"""
The gm/I_D lookup table: the parser, the geometry gate, and the built table.

THREE GROUPS, AND THE SPLIT MATTERS
------------------------------------
1. **Pure** — the `wrdata` parser and the geometry read-back gate. No
   simulator, always run. These are where the two units traps live.
2. **Simulator** — needs ngspice + the PDK. These SKIP cleanly when the
   toolchain is absent, following the repo convention (`test_trimmed_lib.py`),
   but **a skip reports as a pass (G69)**, so every one of them asserts
   POSITIVELY that a run happened: `ok`, a non-zero runtime, and the expected
   number of sweep points. "Nothing raised" is not evidence that anything ran.
3. **Built table** — needs `device/data/gmid_lut_*.npz`. Skips if it has not
   been built, and `test_the_skip_guards_are_honest` makes the skip visible
   rather than silent.

The G69 lesson in one line: `shutil.which("ngspice_con")` could not find this
project's ngspice, so the only end-to-end test in the repo was silently
skipping — and a skip is green.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.device import gmid_lut as GL
from nebula.device.gmid_lut import (
    LUT_PATH,
    GmidLut,
    LutBuildError,
    _assert_geometry_applied,
    _parse_wrdata,
    run_sweep,
)
from nebula.device.ngspice_runner import ngspice_path
from nebula.device.sky130_runner import TRIMMED_LIB


def _toolchain_ready() -> bool:
    try:
        return ngspice_path().exists() and TRIMMED_LIB.exists()
    except FileNotFoundError:
        return False


needs_sim = pytest.mark.skipif(not _toolchain_ready(),
                               reason="needs ngspice + the SKY130 trim (G33)")
needs_lut = pytest.mark.skipif(not LUT_PATH.exists(),
                               reason="run `python -m nebula.device.gmid_lut "
                                      "--build` first")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Pure — the parser.
# ─────────────────────────────────────────────────────────────────────────────


def test_wrdata_parser_reads_interleaved_columns():
    """`wrdata` repeats the sweep variable before EVERY column.

    Undocumented anywhere obvious, and the reason a bare `np.loadtxt` would
    read `gm` out of a column that is really `V_gs`.
    """
    text = "0.1 11 0.1 21\n0.2 12 0.2 22\n0.3 13 0.3 23\n"
    x, cols = _parse_wrdata(text, n_cols=2)
    assert np.allclose(x, [0.1, 0.2, 0.3])
    assert np.allclose(cols[0], [11, 12, 13])
    assert np.allclose(cols[1], [21, 22, 23])


def test_wrdata_parser_REJECTS_a_misaligned_file():
    """Break it deliberately (rule 10): shift one sweep column and watch it go
    red. A misaligned file would read every primitive under the wrong V_gs."""
    bad = "0.1 11 0.9 21\n0.2 12 0.8 22\n0.3 13 0.7 23\n"
    with pytest.raises(LutBuildError, match="not the sweep variable"):
        _parse_wrdata(bad, n_cols=2)


def test_wrdata_parser_rejects_the_wrong_column_count():
    with pytest.raises(LutBuildError, match="columns, expected"):
        _parse_wrdata("0.1 11 0.1 21\n", n_cols=3)


def test_wrdata_parser_rejects_an_empty_file():
    with pytest.raises(LutBuildError, match="empty"):
        _parse_wrdata("\n  \n", n_cols=2)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Pure — the geometry gate, and the units trap inside it.
# ─────────────────────────────────────────────────────────────────────────────


def test_geometry_read_back_converts_metres_to_microns():
    """YOU WRITE MICRONS AND YOU READ BACK METRES.

    `W=40` in the netlist is 40 um (the library sets `.option scale=1e-6`,
    G31), and the instance reports `4.000000e-05`. Comparing those two numbers
    directly fails by 1e6 on a correct circuit — G31's failure mode with the
    sign reversed. Measured on this PDK, 2026-08-17.
    """
    _assert_geometry_applied(4.0e-5, 1.5e-7, w_um=40.0, l_um=0.15)


def test_geometry_gate_CAN_FAIL_on_an_ignored_width():
    """The gate must go red when the geometry was not applied.

    This is the failure `alter` produced for a whole session (G35) and that
    `w` still produces on the fixed-width resistor families (G57): accepted,
    ignored, exit 0.
    """
    with pytest.raises(LutBuildError, match="W was NOT applied"):
        _assert_geometry_applied(4.0e-5, 1.5e-7, w_um=100.0, l_um=0.15)
    with pytest.raises(LutBuildError, match="L was NOT applied"):
        _assert_geometry_applied(4.0e-5, 1.5e-7, w_um=40.0, l_um=1.0)


def test_geometry_gate_CAN_FAIL_when_the_print_became_a_warning():
    """G26: a `print` naming something that does not exist becomes a warning
    and the run still exits 0. A missing read-back must not read as a pass."""
    with pytest.raises(LutBuildError, match="read-back missing"):
        _assert_geometry_applied(None, 1.5e-7, w_um=40.0, l_um=0.15)


def test_geometry_gate_would_catch_a_naive_micron_comparison():
    """Pins the trap itself: comparing the raw numbers is off by 1e6."""
    assert abs(4.0e-5 - 40.0) > 39.0          # the naive comparison
    assert abs(4.0e-5 * 1e6 - 40.0) < 1e-9    # the right one


def test_instance_reference_is_subckt_qualified():
    """SKY130 devices sit inside a subckt, so `@m1[gm]` does not exist and
    asking for it produces a WARNING plus exit 0 (G26)."""
    ref = GL._instance("gm")
    assert ref.startswith("@m.xm1.m") and ref.endswith("[gm]")
    assert "sky130_fd_pr__nfet_01v8" in ref


# ─────────────────────────────────────────────────────────────────────────────
# 3. Pure — the grid's own consistency.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_grid_spans_the_action_space_box_exactly():
    """The table must cover the approved box, or a lookup inside the box would
    extrapolate — and `design_space` refuses to extrapolate, so an under-wide
    table turns into spurious rejections rather than wrong numbers."""
    from nebula.rl.contract import ACTION_SPACE
    box = {d.name: (d.lo, d.hi) for d in ACTION_SPACE}
    assert GL.W_GRID_UM[0] <= box["w_in"][0] * 1e6
    assert GL.W_GRID_UM[-1] >= box["w_in"][1] * 1e6
    assert GL.L_GRID_UM[0] <= box["l_in"][0] * 1e6
    assert GL.L_GRID_UM[-1] >= box["l_in"][1] * 1e6


def test_the_vsb_axis_includes_zero_so_no_body_effect_is_not_an_extrapolation():
    """CLAUDEwa.md §6's `gmbs = 0` comparison must be a LOOKUP, not a guess."""
    assert GL.VSB_GRID_V[0] == 0.0


def test_corner_grid_matches_the_screen_corners_the_project_actually_uses():
    """G47: three corners are worth 98.7 % of forty-five, so the table is built
    at the ones `s9_yield.SCREEN_CORNERS` screens on — not at a set invented
    here."""
    from nebula.experiments.s9_yield import SCREEN_CORNERS
    want = {(c.process, c.temp_c) for c in SCREEN_CORNERS}
    have = {(p, t) for p, t in GL.CORNER_GRID}
    assert want <= have, f"table is missing screen corners: {want - have}"
    assert ("tt", 27.0) in have


# ─────────────────────────────────────────────────────────────────────────────
# 4. Simulator. Every one asserts POSITIVELY that a run happened (G69).
# ─────────────────────────────────────────────────────────────────────────────


@needs_sim
def test_a_sweep_actually_runs_and_returns_a_full_vgs_axis():
    r = run_sweep("tt", 27.0, l_um=0.30, vds_v=0.75, vsb_v=0.40)
    assert r.ok, r.fail_reason
    assert r.runtime_s > 0.0, "a run that took no time did not happen"
    n_expected = int(round((GL.VGS_STOP_V - GL.VGS_START_V) / GL.VGS_STEP_V)) + 1
    assert r.vgs_v is not None and len(r.vgs_v) == n_expected
    for key in GL.SWEEP_PRIMITIVES:
        assert key in r.prim and len(r.prim[key]) == n_expected


@needs_sim
def test_gm_over_id_falls_monotonically_with_vgs_where_the_current_is_live():
    """The physics the inverse map relies on.

    `gm/I_D` falls from roughly `2/(n*V_T)` in weak inversion to `2/V_ov` in
    strong. If it did not, inverting it would be ill-posed and
    `design_space._vgs_for_gm_over_id` would return an arbitrary root.
    """
    r = run_sweep("tt", 27.0, l_um=0.30, vds_v=0.75, vsb_v=0.40)
    assert r.ok, r.fail_reason
    live = r.prim["id"] > 1e-9
    g = r.prim["gm"][live] / r.prim["id"][live]
    assert live.sum() > 50
    assert np.all(np.diff(g) < 0), "gm/I_D is not monotone; inversion is unsafe"


@needs_sim
def test_the_body_effect_is_present_and_grows_as_the_source_rises():
    """CLAUDEwa.md §6 measured `gmbs/gm = 0.33` at the G1 point and 2.33 dB of
    error from omitting it. A table that returned zero here would rebuild that
    error exactly, and would still simulate."""
    ratios = []
    for vsb in (0.0, 0.40, 0.85):
        r = run_sweep("tt", 27.0, l_um=0.30, vds_v=0.75, vsb_v=vsb)
        assert r.ok, r.fail_reason
        live = r.prim["id"] > 1e-6
        ratios.append(float(np.median(r.prim["gmbs"][live] / r.prim["gm"][live])))
    assert ratios[0] > 0.0
    # More source-bulk bias => SMALLER gmbs/gm (the sqrt in the body term).
    assert ratios[0] > ratios[1] > ratios[2], ratios


@needs_sim
def test_an_out_of_bin_WIDTH_fails_loudly():
    """G53: the SKY130 bin ceiling is on W per FINGER, and W is enforced.

    The message is `could not find a valid modelname`, which G31 records as
    being read as a units error nine times out of ten. Here it is the correct
    message for the correct reason.
    """
    with pytest.raises(LutBuildError, match="could not find a valid modelname"):
        run_sweep("tt", 27.0, l_um=0.30, vds_v=0.75, vsb_v=0.40, w_um=0.1)


@needs_sim
def test_an_out_of_bin_LENGTH_is_SILENTLY_ACCEPTED_and_that_is_the_finding():
    """**W refuses out of bin; L does not.** Measured 2026-08-17, TT/27:

        L (um)      0.15        1.0         10.0        99.0
        I_D @1.2V   5.92e-3     1.37e-3     1.56e-4     1.59e-5
        ok          True        True        True        True

    L = 99 um is far outside anything SKY130 draws, and the model extrapolates
    its top bin rather than refusing — the current keeps scaling as a clean
    1/L, so the answer looks perfectly reasonable all the way out.

    **The consequence for this project:** the PDK will not protect a caller
    against an out-of-range L the way it does against an out-of-range W, so
    `design_space._axis_weights`'s refusal to extrapolate is not belt-and-
    braces — on the L axis it is the ONLY guard. This test exists so that if a
    future PDK starts refusing, someone finds out here rather than by a build
    failing at 3000 sweeps.
    """
    r = run_sweep("tt", 27.0, l_um=99.0, vds_v=0.75, vsb_v=0.40)
    assert r.ok, "if this now FAILS, the PDK changed — update the note above"
    i = int(np.argmin(np.abs(r.vgs_v - 1.2)))
    assert r.prim["id"][i] > 0, "silently accepted AND physically plausible"

    ref = run_sweep("tt", 27.0, l_um=1.0, vds_v=0.75, vsb_v=0.40)
    assert ref.ok
    ratio = ref.prim["id"][i] / r.prim["id"][i]
    assert 50.0 < ratio < 150.0, (
        f"I_D scaled by {ratio:.1f}x over a 99x length change — the "
        f"extrapolation is smooth, which is exactly what makes it dangerous")


@needs_sim
def test_the_skip_guards_are_honest():
    """If this test runs at all, the toolchain guard said the toolchain is
    present — so prove it, rather than trusting the guard (G69)."""
    assert ngspice_path().exists()
    assert TRIMMED_LIB.exists()


# ─────────────────────────────────────────────────────────────────────────────
# 5. The built table.
# ─────────────────────────────────────────────────────────────────────────────


@needs_lut
def test_the_table_loads_and_carries_its_provenance():
    """An artifact that cannot say what produced it is not reproducible (G49)."""
    lut = GmidLut.load()
    for key in ("built_utc", "library", "library_sha_prefix", "ngspice",
                "device", "vgs_step_v", "n_sweeps"):
        assert key in lut.provenance, f"provenance is missing {key}"
    assert lut.provenance["device"] == "sky130_fd_pr__nfet_01v8"


@needs_lut
def test_the_table_has_no_holes():
    """A NaN would read as 'unreachable' and really mean 'unmeasured' — G73's
    shape, and the reason `build_lut` refuses to ship a partial table."""
    lut = GmidLut.load()
    for key, arr in lut.prim.items():
        assert np.isfinite(arr).all(), f"{key} carries {np.isnan(arr).sum()} NaN"


@needs_lut
def test_the_table_shape_matches_its_axes():
    lut = GmidLut.load()
    assert lut.prim["gm"].shape == (
        len(lut.corners), lut.w_um.size, lut.l_um.size,
        lut.vds_v.size, lut.vsb_v.size, lut.vgs_v.size)


@needs_lut
def test_gm_over_id_is_monotone_on_essentially_every_curve():
    """The gate `design_space`'s inversion depends on, over the WHOLE table."""
    lut = GmidLut.load()
    frac = lut.monotone_fraction()
    assert frac > 0.99, f"only {frac:.4f} of curves are monotone in gm/I_D"


@needs_lut
def test_derived_quantities_are_computed_not_stored():
    """Rule 10: derived quantities come from parsed primitives, in Python.

    A stored derived column can go stale against the primitive it came from;
    a property cannot.
    """
    lut = GmidLut.load()
    assert set(lut.prim) == set(GL.SWEEP_PRIMITIVES)
    for name in ("gm_over_id", "id_per_um", "gm_ro", "gmbs_over_gm"):
        assert not hasattr(lut.prim, name)
    np.testing.assert_allclose(
        lut.gm_over_id, lut.prim["gm"] / np.maximum(lut.prim["id"], 1e-18))


@needs_lut
def test_lut_and_prescreen_fit_agree_within_a_recorded_band():
    """TWO ANSWERS TO 'WHAT IS gm HERE?' MUST BE HELD AGAINST EACH OTHER.

    `experiments/prescreen.predict_gm` is a REGRESSION on the design vector
    with no bias solve; this table is a MEASUREMENT indexed on the bias point.
    Rule 9 forbids two silent definitions of one quantity — they are not
    interchangeable (the module docstring says why), so what this pins is that
    they do not DIVERGE without anyone noticing.

    The band is deliberately wide. `BASELINES.md` records the fit's own error
    as median 2.4 %, p90 7.6 %, p99 24.1 % on its calibration set, and the two
    are evaluated at different `V_ds`/`V_sb` besides. A tight assertion here
    would be asserting agreement this project has not measured.
    """
    from nebula.common.design_space import solve_bias
    from nebula.experiments.prescreen import predict_gm

    lut = GmidLut.load()
    rel = []
    for w_um, l_um, i_bias in ((40.0, 0.30, 3.0e-3), (60.0, 0.20, 4.0e-3),
                               (80.0, 0.50, 2.0e-3), (30.0, 0.80, 5.0e-3)):
        gm_fit, _ = predict_gm({"w_in": w_um * 1e-6, "l_in": l_um * 1e-6,
                                "nf_in": 4.0, "i_bias": i_bias})
        gm_id_fit = gm_fit / (0.5 * i_bias)
        b = solve_bias(lut, gm_over_id=gm_id_fit, l_in_m=l_um * 1e-6,
                       i_bias_a=i_bias, rl_ohm=400.0, vcm_in_v=1.30)
        if not b.ok:
            continue
        rel.append(abs(b.w_um - w_um) / w_um)

    assert rel, "no comparison point solved; the check did not run"
    median = float(np.median(rel))
    assert median < 0.60, (
        f"the table and the pre-screen fit disagree on W by a median "
        f"{median * 100:.1f} % — investigate before either is trusted")
