"""
`device/cap_probe.py` — the gate load the CTLE output has to drive.

WHAT THESE TESTS ARE PROTECTING
-------------------------------
The number this module produces goes straight into `cl`, which sets
f_p2 = 1/(2*pi*RL*CL) and therefore where S3's peak lands. A capacitance that
is wrong by 2x moves f_peak by an octave — the entire width of S3's window —
and it would do so silently, because 6 fF and 13 fF are both perfectly
plausible gate capacitances for a small transistor.

Two failure modes get dedicated tests because both have real precedent here:

1. **Reading the wrong quantity.** `@m[cgg]` is the obvious probe and it is
   the wrong one: it excludes the gate overlap capacitance and the Miller
   multiplication of Cgd, and understates the load by 1.9-2.6x on these
   devices. `test_cgg_understates_the_load` pins that so nobody "simplifies"
   the AC measurement away.
2. **Reading the right quantity out of the wrong column.** `wrdata` emits an
   (x, re, im) triple per complex vector; the parser is held to a fixture of
   real captured output with hand-computed expected values.

Almost everything here runs on a checked-in fixture with **no simulator**.
The handful that need ngspice + the PDK skip cleanly.
"""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from nebula.device.cap_probe import (
    F_NYQUIST_HZ,
    F_WINDOW_LO_HZ,
    GateLoadPoint,
    LoadStage,
    analytic_load_ff,
    measure_gate_load,
    model_file_for_corner,
    overlap_cap_f_per_m,
    parse_gate_load_output,
    pdk_model_param,
    sanity_check_load,
)
from nebula.device.sky130_runner import TRIMMED_LIB, VALID_CORNERS

FIXTURES = Path(__file__).parent / "fixtures"
FIX_OUT = FIXTURES / "cap_probe_slicer_max_tt.txt"
FIX_CIN = FIXTURES / "cap_probe_slicer_max_tt.cin.txt"

NGSPICE = Path(
    r"C:\Users\DELL\miniforge3\envs\nebula\Library\bin\ngspice_con.exe")
PDK_MODEL = Path(r"C:\Users\DELL\sky130A\libs.ref\sky130_fd_pr\spice")

needs_pdk = pytest.mark.skipif(
    not PDK_MODEL.exists(),
    reason="needs the SKY130 PDK install (HANDOFF G33)")
needs_sim = pytest.mark.skipif(
    not (NGSPICE.exists() and PDK_MODEL.exists()),
    reason="needs ngspice + the SKY130 PDK install (HANDOFF G20/G33)")

#: The fixture's stage. Must match the sizing the fixture was captured with,
#: because `analytic_load_ff` multiplies the overlap constant by its W.
FIX_STAGE = LoadStage(name="slicer_max", w_um=16.0, l_um=0.15, nf=8,
                      i_side_a=1.0e-3, rld_ohm=800.0)


@pytest.fixture
def fixture_point() -> GateLoadPoint:
    """The captured run, parsed. TT / 27 C / vcm_out 1.2 V."""
    out = FIX_OUT.read_text(encoding="ascii")
    raw = np.loadtxt(FIX_CIN)
    return parse_gate_load_output(out, raw, stage=FIX_STAGE, corner="tt",
                                  temp_c=27.0, vcm_out_v=1.2, vdd=1.8)


# ─────────────────────────────────────────────────────────────────────────────
# The sizing point's conventions.
# ─────────────────────────────────────────────────────────────────────────────


def test_load_stage_tail_is_twice_the_side_current():
    """ONE shared tail, unlike the CTLE's two sinks.

    The CTLE needs two ideal sinks or Rdeg is shorted out; a slicer/summer
    pair is not degenerated and has one. Getting this backwards halves every
    bias current in the probe and moves the capacitance.
    """
    s = LoadStage("x", w_um=8.0, l_um=0.15, nf=4, i_side_a=0.5e-3,
                  rld_ohm=600.0)
    assert s.i_tail_total_a == pytest.approx(1.0e-3)


def test_load_stage_quiescent_output_is_vdd_minus_ir():
    s = LoadStage("x", w_um=8.0, l_um=0.15, nf=4, i_side_a=0.5e-3,
                  rld_ohm=600.0)
    assert s.v_out_dc_nominal(vdd=1.8) == pytest.approx(1.8 - 0.3)


# ─────────────────────────────────────────────────────────────────────────────
# Parsing: hand-computed expected values, not values produced by this code.
# ─────────────────────────────────────────────────────────────────────────────


def test_fixture_parses_cleanly(fixture_point):
    assert fixture_point.ok, fixture_point.fail_reason
    assert fixture_point.fail_reason is None


def test_c_in_matches_hand_computed_value(fixture_point):
    """C = Im{i(Vgp)} / (omega * v_gate), v_gate = 0.5 for a unit diff drive.

    From the fixture's last row: Im = 2.69737725e-04 A at 2.5 GHz.
        2.69737725e-4 / (2*pi*2.5e9*0.5) = 3.4344e-14 F
    Computed here from the literals, not by calling the code under test.
    """
    expected = 2.69737725e-04 / (2.0 * math.pi * 2.5e9 * 0.5)
    assert fixture_point.c_in_f == pytest.approx(expected, rel=1e-12)
    assert fixture_point.c_in_ff == pytest.approx(34.344, abs=0.01)


def test_c_in_is_read_at_nyquist_and_the_low_edge_separately(fixture_point):
    """First and last sweep rows, not the same row twice."""
    assert fixture_point.f_probe_hz == pytest.approx(F_NYQUIST_HZ)
    lo_expected = 1.35049297e-04 / (2.0 * math.pi * F_WINDOW_LO_HZ * 0.5)
    assert fixture_point.c_in_lo_f == pytest.approx(lo_expected, rel=1e-12)


def test_capacitance_barely_disperses_across_the_s3_window(fixture_point):
    """A lumped `cl` in the CTLE netlist is only honest if the load really is
    a constant capacitance over 1.25-2.5 GHz. Measured: 0.17% at worst."""
    rel = abs(fixture_point.c_in_lo_f - fixture_point.c_in_f) / fixture_point.c_in_f
    assert rel < 0.01


def test_a_load_is_the_differential_gain(fixture_point):
    """|v(outp) - v(outn)| under a unit differential drive."""
    outp = complex(-1.75275461, 0.136986841)
    outn = complex(1.75275461, -0.136986841)
    assert fixture_point.a_load == pytest.approx(abs(outp - outn), rel=1e-9)
    assert fixture_point.a_load == pytest.approx(3.516, abs=0.01)


def test_op_primitives_are_parsed(fixture_point):
    assert fixture_point.cgg_f == pytest.approx(1.270928e-14)
    assert fixture_point.cgs_f == pytest.approx(-9.56917e-15)
    assert fixture_point.gm == pytest.approx(5.914424e-03)
    assert fixture_point.id_a == pytest.approx(1.0e-03)
    assert fixture_point.vds == pytest.approx(8.012292e-01)
    assert fixture_point.vdsat == pytest.approx(1.598534e-01)
    assert fixture_point.v_src_dc == pytest.approx(1.987708e-01)


def test_bsim4_reports_cgs_and_cgb_negative(fixture_point):
    """dQg/dVs and dQg/dVb are negative by construction. A load is built out
    of MAGNITUDES; anyone summing the signed values gets a smaller number and
    no error."""
    assert fixture_point.cgs_f < 0
    assert fixture_point.cgb_f < 0
    assert fixture_point.cgg_f > 0


def test_parser_rejects_a_wrong_shaped_table(fixture_point):
    out = FIX_OUT.read_text(encoding="ascii")
    raw = np.loadtxt(FIX_CIN)[:, :6]          # two vectors, not three
    pt = parse_gate_load_output(out, raw, stage=FIX_STAGE)
    assert not pt.ok
    assert "shape" in (pt.fail_reason or "")


def test_parser_rejects_a_single_frequency_row(fixture_point):
    """`ac lin 2` returns one row from this ngspice build; the parser must say
    so rather than reading the same row as both band edges."""
    out = FIX_OUT.read_text(encoding="ascii")
    raw = np.loadtxt(FIX_CIN)[:1, :]
    pt = parse_gate_load_output(out, raw, stage=FIX_STAGE)
    assert not pt.ok
    assert "shape" in (pt.fail_reason or "")


def test_parser_reports_missing_primitives_rather_than_guessing():
    raw = np.loadtxt(FIX_CIN)
    pt = parse_gate_load_output("nothing useful here", raw, stage=FIX_STAGE)
    assert not pt.ok
    assert "could not parse" in (pt.fail_reason or "")


# ─────────────────────────────────────────────────────────────────────────────
# THE POINT OF THE MODULE: `@m[cgg]` is not the load.
# ─────────────────────────────────────────────────────────────────────────────


def test_cgg_understates_the_load(fixture_point):
    """G50. `@m[cgg]` is the INTRINSIC gate capacitance: no overlap, no Miller.

    On the fixture's 16 um device with a gain of 3.5 it reads 12.71 fF where
    the node has to supply 34.34 fF — 2.7x. If someone ever replaces the AC
    measurement with the cheap `.op` probe, this goes red.
    """
    assert fixture_point.cgg_understatement > 2.0
    assert fixture_point.cgg_ff == pytest.approx(12.709, abs=0.01)
    assert fixture_point.c_in_ff == pytest.approx(34.344, abs=0.01)


def test_analytic_reconstruction_matches_the_ac_measurement(fixture_point):
    """The falsifiable cross-check, with the arithmetic written out.

        C = (|cgs| + Cgso*W) + |cgb| + (|cgd| + Cgdo*W) * (1 + |A|)

    Cgso = Cgdo = 2.449068e-10 F/m (SKY130 tt card), W = 16 um:
        overlap        = 3.9185 fF each side
        gate-source    = 9.5692 + 3.9185 = 13.4877 fF
        gate-bulk      =                    3.1581 fF
        gate-drain     = (0.0180 + 3.9185) * (1 + 3.5162) = 17.7770 fF
        total                              = 34.42 fF   vs 34.34 measured
    """
    assert analytic_load_ff(fixture_point) == pytest.approx(34.42, abs=0.05)
    rel = abs(analytic_load_ff(fixture_point) - fixture_point.c_in_ff)
    assert rel / fixture_point.c_in_ff < 0.01


def test_the_miller_term_is_not_negligible(fixture_point):
    """Half the load on this device is gate-drain overlap times (1 + gain).

    Stated as a test because "Cgd is tiny in saturation" is true of the
    INTRINSIC Cgd (1.8e-17 F here) and false of the overlap, and the two are
    easy to conflate.
    """
    cgdo = overlap_cap_f_per_m("tt")[1]
    c_gd = (abs(fixture_point.cgd_f) + cgdo * FIX_STAGE.w_um * 1e-6) * 1e15
    miller = c_gd * (1.0 + fixture_point.a_load)
    assert miller / fixture_point.c_in_ff > 0.4
    # ...and the intrinsic part alone would have been negligible.
    assert abs(fixture_point.cgd_f) * 1e15 < 0.1


# ─────────────────────────────────────────────────────────────────────────────
# The gate. A measurement that cannot fail is not a measurement.
# ─────────────────────────────────────────────────────────────────────────────


def test_sanity_check_passes_on_a_good_point(fixture_point):
    assert sanity_check_load(fixture_point) == []


def test_sanity_check_flags_a_device_out_of_saturation(fixture_point):
    bad = replace(fixture_point, vds=0.05)
    assert any("saturat" in p for p in sanity_check_load(bad))


def test_sanity_check_flags_a_resistive_load(fixture_point):
    """A gate that draws in-phase current is not a capacitor, and `c_in_f`
    would then be an incomplete description of it."""
    b = 2.0 * math.pi * fixture_point.f_probe_hz * fixture_point.c_in_f
    bad = replace(fixture_point, g_in_s=0.5 * b)
    assert any("not capacitive" in p for p in sanity_check_load(bad))


def test_sanity_check_flags_disagreement_with_the_primitives(fixture_point):
    """Corrupt the AC number and the reconstruction must catch it. This is the
    test that says the cross-check is a gate rather than a comment."""
    bad = replace(fixture_point, c_in_f=fixture_point.c_in_f * 1.5)
    problems = sanity_check_load(bad)
    assert any("disagrees" in p for p in problems), problems


def test_sanity_check_refuses_a_failed_point():
    pt = GateLoadPoint(ok=False, fail_reason="boom")
    assert sanity_check_load(pt) == ["point is not ok: boom"]


# ─────────────────────────────────────────────────────────────────────────────
# PDK constants: referenced, never re-declared (CLAUDEwa.md §8 rule 9).
# ─────────────────────────────────────────────────────────────────────────────


@needs_pdk
@pytest.mark.parametrize("corner", VALID_CORNERS)
def test_model_file_is_read_out_of_the_trimmed_library(corner):
    p = model_file_for_corner(corner)
    assert p.name.endswith(f"__{corner}.pm3.spice")
    assert p.exists()


def test_model_file_rejects_an_unknown_corner():
    with pytest.raises(ValueError, match="unknown corner"):
        model_file_for_corner("xx")


def test_model_file_rejects_a_library_without_that_section(tmp_path):
    lib = tmp_path / "empty.lib.spice"
    lib.write_text("* nothing here\n", encoding="ascii")
    with pytest.raises(ValueError, match="no '.lib tt' section"):
        model_file_for_corner("tt", lib=lib)


@needs_pdk
def test_overlap_capacitance_differs_between_corners():
    """If it did not, the corner axis of this measurement would be doing
    nothing and the range's corner witnesses would be arbitrary."""
    vals = {c: overlap_cap_f_per_m(c)[0] for c in VALID_CORNERS}
    assert len(set(vals.values())) == len(VALID_CORNERS), vals
    assert vals["tt"] == pytest.approx(2.449068e-10)


@needs_pdk
def test_overlap_cgso_and_cgdo_are_equal_on_this_device():
    cgso, cgdo = overlap_cap_f_per_m("tt")
    assert cgso == cgdo


@needs_pdk
def test_pdk_param_refuses_a_parameter_the_bins_disagree_on():
    """`u0` is binned — 18 declarations, 5 distinct values across the W/L bins.

    Returning the first one silently is exactly how a per-bin parameter
    becomes a global constant in someone's Python. It must raise instead.
    `cgso` is safe to use precisely because all 180 bins agree on it, and that
    is checked rather than assumed on every call.
    """
    with pytest.raises(ValueError, match="differs across"):
        pdk_model_param("u0", "tt")


@needs_pdk
def test_pdk_param_refuses_a_parameter_written_as_an_expression():
    """`vth0` is `{0.519... + MC_MM_SWITCH*AGAUSS(...)}`, not a number.

    A regex that stripped the leading digits out of that expression would
    return a plausible threshold voltage and silently drop the mismatch term.
    The reader must be `None`-or-raise on anything that is not a plain value.
    """
    with pytest.raises(ValueError, match="not found"):
        pdk_model_param("vth0", "tt")


@needs_pdk
def test_pdk_param_raises_on_an_absent_parameter():
    with pytest.raises(ValueError, match="not found"):
        pdk_model_param("definitely_not_a_bsim4_parameter", "tt")


# ─────────────────────────────────────────────────────────────────────────────
# End to end, only where a simulator exists.
# ─────────────────────────────────────────────────────────────────────────────


@needs_sim
def test_measure_gate_load_end_to_end():
    pt = measure_gate_load(FIX_STAGE, corner="tt", temp_c=27.0, vcm_out_v=1.2)
    assert pt.ok, pt.fail_reason
    assert sanity_check_load(pt) == []
    assert pt.c_in_ff == pytest.approx(34.344, rel=1e-3)
    assert pt.cgg_understatement > 2.0


@needs_sim
def test_measure_gate_load_returns_not_raises_on_a_bad_corner():
    """CLAUDEwa.md §8 rule 2: a failed run is ok=False, never an exception."""
    pt = measure_gate_load(FIX_STAGE, corner="not_a_corner")
    assert not pt.ok
    assert "unknown corner" in (pt.fail_reason or "")


@needs_sim
def test_measure_gate_load_refuses_a_device_outside_the_trimmed_library():
    """The trim carries nfet_01v8 only (G36). Asking for anything else must
    fail by name, not with 'could not find a valid modelname' — which G31
    shows is read as a units error nine times out of ten."""
    pt = measure_gate_load(FIX_STAGE, device="sky130_fd_pr__nfet_g5v0d10v5")
    assert not pt.ok
    assert "trimmed library" in (pt.fail_reason or "")


@needs_sim
def test_a_slow_corner_loads_the_node_more_than_a_fast_one_does_not_hold():
    """The corner that maximises the LOAD is not the one that maximises gm.

    Recorded as a test because the intuition "slow corner = worse everything"
    is what G46 already had to correct once for S3. Measured here: `fs` and
    `ss` both load the node more than `tt`, and `ff` and `sf` load it less, so
    the ordering does not follow the process-speed axis at all.
    """
    got = {}
    for corner in ("ss", "tt", "ff", "sf", "fs"):
        pt = measure_gate_load(FIX_STAGE, corner=corner, temp_c=27.0,
                               vcm_out_v=1.2)
        assert pt.ok, (corner, pt.fail_reason)
        got[corner] = pt.c_in_ff
    assert got["ss"] > got["tt"] > got["ff"], got
    assert got["fs"] > got["ss"], got          # fast-nfet loads MORE than slow
    assert got["sf"] < got["ff"], got
