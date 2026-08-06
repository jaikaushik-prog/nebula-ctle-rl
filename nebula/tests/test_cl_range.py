"""
`experiments/cl_range.py` — the derivation of `[cl_lo, cl_hi]`.

WHY THIS IS TESTED SEPARATELY FROM THE MEASUREMENT
--------------------------------------------------
`test_cap_probe.py` protects the measurement. This file protects everything
that happens *after* it: which extreme goes into which edge, whether the
routing allowance is added once or twice, and whether the committed table
still re-derives the published range.

Every test here is **simulator-free**. Two need the PDK, to read the vpp cap
model the routing figure comes out of.

The regression test at the bottom is the G49 rule made executable: the CSV is
committed precisely so a deliverable's numbers can be re-derived without
re-simulating, and a test asserts that they still are.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from nebula.experiments.cl_range import (
    A_VT_MV_UM,
    DATA_CSV,
    EDGE_STAGES,
    LOAD_STAGES,
    MET_MIN_WIDTH_UM,
    MIN_STAGE_GAIN,
    ROUTING_LENGTH_HI_UM,
    ROUTING_LENGTH_LO_UM,
    TEMPS_C,
    VCM_OUT_V,
    ClRange,
    RoutingAllowance,
    WireCap,
    check_stage_gains,
    committed_cl_range,
    derive_cl_range,
    fanout_scaled,
    read_csv,
    routing_allowances,
    sigma_offset_mv,
    sigma_vth_mv,
    stage_table,
    vpp_wire_cap,
    write_csv,
)

PDK_MODEL = Path(r"C:\Users\DELL\sky130A\libs.ref\sky130_fd_pr\spice")
needs_pdk = pytest.mark.skipif(
    not PDK_MODEL.exists(),
    reason="needs the SKY130 PDK install (HANDOFF G33)")


def _row(stage: str, c_ff: float, *, ok: bool = True, corner: str = "tt",
         temp_c: float = 27.0, vcm: float = 1.2, a_load: float = 2.0) -> dict:
    return {"stage": stage, "corner": corner, "temp_c": temp_c,
            "vcm_out_v": vcm, "ok": ok, "c_in_ff": c_ff, "cgg_ff": c_ff / 2.0,
            "a_load": a_load, "problems": "", "fail_reason": ""}


# ─────────────────────────────────────────────────────────────────────────────
# The sketch's own arithmetic.
# ─────────────────────────────────────────────────────────────────────────────


def test_pelgrom_sigma_is_hand_computable():
    """A_VT / sqrt(W*L): 3.356 / sqrt(16 * 0.15) = 3.356 / 1.549 = 2.166 mV."""
    assert sigma_vth_mv(16.0, 0.15) == pytest.approx(
        A_VT_MV_UM / math.sqrt(2.4), rel=1e-12)
    assert sigma_vth_mv(16.0, 0.15) == pytest.approx(2.166, abs=0.001)


def test_pair_offset_carries_the_root_two():
    """Two uncorrelated devices, not one. Dropping the sqrt(2) understates the
    slicer's offset by 41% and would justify a smaller device than the sketch
    can defend."""
    assert (sigma_offset_mv(16.0, 0.15)
            == pytest.approx(math.sqrt(2.0) * sigma_vth_mv(16.0, 0.15)))
    assert 3.0 * sigma_offset_mv(16.0, 0.15) == pytest.approx(9.19, abs=0.01)


def test_the_two_slicer_sizes_bracket_the_offset_decision():
    """The min/max sizes are a real design decision — trimmed vs untrimmed —
    not an arbitrary +/-, and the offsets have to show that."""
    small = 3.0 * sigma_offset_mv(LOAD_STAGES["slicer_min"].w_um,
                                  LOAD_STAGES["slicer_min"].l_um)
    large = 3.0 * sigma_offset_mv(LOAD_STAGES["slicer_max"].w_um,
                                  LOAD_STAGES["slicer_max"].l_um)
    assert small > 15.0        # needs an offset trim DAC against a 100 mV eye
    assert large < 10.0        # usable untrimmed


def test_all_stages_use_the_minimum_length_bin():
    """L is not a free parameter for these stages: f_T falls as 1/L^2 (G39)
    and neither stage needs output resistance."""
    assert {s.l_um for s in LOAD_STAGES.values()} == {0.15}


def test_edge_stages_name_real_stages():
    for edge, names in EDGE_STAGES.items():
        for n in names:
            assert n in LOAD_STAGES, (edge, n)


def test_each_edge_loads_the_node_with_one_summer_and_one_slicer():
    """S2's topology, as a test: the CTLE drives the DFE summer and the
    slicer, so each edge is exactly two gates. If a gate is ever added or
    removed this goes red rather than quietly changing the range."""
    for edge, names in EDGE_STAGES.items():
        assert len(names) == 2, (edge, names)
        assert sum("summer" in n for n in names) == 1
        assert sum("slicer" in n for n in names) == 1


# ─────────────────────────────────────────────────────────────────────────────
# The routing allowance.
# ─────────────────────────────────────────────────────────────────────────────


@needs_pdk
def test_wire_cap_matches_the_hand_computation():
    """m1: rat_m1 * ctot / (n_sq * width) = 0.387 * 0.7833 fF / (22 * 0.14 um)
    = 0.0984 fF/um. m2: 0.596 * 0.7833 / (28 * 0.14) = 0.1191 fF/um."""
    w = vpp_wire_cap()
    assert w.ctot_ff == pytest.approx(0.7833, abs=1e-4)
    assert w.rat_m1 == pytest.approx(0.387)
    assert w.rat_m2 == pytest.approx(0.596)
    assert w.n_sq_m1 == 22
    assert w.n_sq_m2 == 28
    assert w.width_um == MET_MIN_WIDTH_UM
    assert w.m1_ff_per_um == pytest.approx(0.387 * 0.7833 / (22 * 0.14),
                                           abs=1e-4)
    assert w.m2_ff_per_um == pytest.approx(0.596 * 0.7833 / (28 * 0.14),
                                           abs=1e-4)


@needs_pdk
def test_wire_cap_lands_in_the_range_a_130nm_routing_wire_should():
    """A sanity band, not a fit. Anything outside 0.02-0.5 fF/um for a
    min-width lower-metal wire means the squares-to-microns conversion or the
    fF/F scaling has gone wrong — both are silent errors of 1e3 or more."""
    w = vpp_wire_cap()
    assert 0.02 < w.lo_ff_per_um <= w.hi_ff_per_um < 0.5


@needs_pdk
def test_wire_cap_scales_inversely_with_the_assumed_metal_width():
    """The one declared geometric input is a DIVISOR, so a reader who thinks
    the fingers are drawn wider than minimum gets a SMALLER routing term."""
    narrow = vpp_wire_cap(width_um=0.14)
    wide = vpp_wire_cap(width_um=0.28)
    assert wide.m1_ff_per_um == pytest.approx(narrow.m1_ff_per_um / 2.0)


def test_routing_allowance_is_length_times_per_micron():
    r = RoutingAllowance(length_um=50.0, c_ff_per_um=0.1, why="")
    assert r.c_ff == pytest.approx(5.0)


@needs_pdk
def test_routing_edges_use_the_stated_lengths_and_bracket_each_other():
    lo, hi = routing_allowances()
    assert lo.length_um == ROUTING_LENGTH_LO_UM
    assert hi.length_um == ROUTING_LENGTH_HI_UM
    assert lo.c_ff < hi.c_ff
    assert lo.c_ff_per_um <= hi.c_ff_per_um


# ─────────────────────────────────────────────────────────────────────────────
# The derivation.
# ─────────────────────────────────────────────────────────────────────────────


def _fake_routing() -> tuple[RoutingAllowance, RoutingAllowance]:
    return (RoutingAllowance(10.0, 0.1, "lo"),
            RoutingAllowance(100.0, 0.1, "hi"))


def test_each_edge_takes_the_extreme_of_each_stage_independently():
    """The two stages are different devices; nothing requires their extremes
    to fall at the same corner. Pairing them corner-by-corner would produce a
    narrower range than the measurements support."""
    rows = [
        _row("A", 5.0, corner="ss"), _row("A", 9.0, corner="ff"),
        _row("B", 8.0, corner="ff"), _row("B", 3.0, corner="ss"),
    ]
    rng = derive_cl_range(rows, _fake_routing(),
                          edge_stages={"lo": ("A", "B"), "hi": ("A", "B")})
    assert rng.device_lo_ff == pytest.approx(5.0 + 3.0)
    assert rng.device_hi_ff == pytest.approx(9.0 + 8.0)
    assert rng.lo_witness["A"]["corner"] == "ss"
    assert rng.lo_witness["B"]["corner"] == "ss"
    assert rng.hi_witness["A"]["corner"] == "ff"
    assert rng.hi_witness["B"]["corner"] == "ff"


def test_routing_is_added_once_per_edge():
    rows = [_row("A", 5.0), _row("B", 5.0)]
    rng = derive_cl_range(rows, _fake_routing(),
                          edge_stages={"lo": ("A", "B"), "hi": ("A", "B")})
    assert rng.routing_lo_ff == pytest.approx(1.0)
    assert rng.routing_hi_ff == pytest.approx(10.0)
    assert rng.cl_lo_f == pytest.approx((10.0 + 1.0) * 1e-15)
    assert rng.cl_hi_f == pytest.approx((10.0 + 10.0) * 1e-15)


def test_rejected_rows_are_excluded_and_counted():
    """A load derived from an unknown number of discarded measurements is not
    derived from anything."""
    rows = [_row("A", 5.0), _row("A", 0.001, ok=False),
            _row("B", 5.0), _row("B", 999.0, ok=False)]
    rng = derive_cl_range(rows, _fake_routing(),
                          edge_stages={"lo": ("A", "B"), "hi": ("A", "B")})
    assert rng.n_rows_rejected == 2
    assert rng.device_lo_ff == pytest.approx(10.0)      # 0.001 not used
    assert rng.device_hi_ff == pytest.approx(10.0)      # 999 not used


def test_derivation_refuses_a_table_with_no_usable_rows_for_a_stage():
    rows = [_row("A", 5.0), _row("B", 5.0, ok=False)]
    with pytest.raises(ValueError, match="no usable measurement"):
        derive_cl_range(rows, _fake_routing(),
                        edge_stages={"lo": ("A", "B"), "hi": ("A", "B")})


def test_cl_mid_is_the_geometric_mean():
    """f_p2 = 1/(2*pi*RL*CL) is log-linear in cl and PROPOSED_BOX scales cl
    logarithmically, so the geometric centre is the midpoint in the coordinate
    the circuit responds to. The arithmetic mean of 13.6 and 78 fF would be
    45.8 fF — a third of an octave off centre."""
    rng = ClRange(cl_lo_f=10e-15, cl_hi_f=90e-15, device_lo_ff=0,
                  device_hi_ff=0, routing_lo_ff=0, routing_hi_ff=0,
                  lo_witness={}, hi_witness={}, n_rows_used=0,
                  n_rows_rejected=0)
    assert rng.cl_mid_f == pytest.approx(30e-15)
    assert rng.ratio == pytest.approx(9.0)
    assert rng.octaves == pytest.approx(math.log2(9.0))
    # The midpoint really is a midpoint in octaves.
    assert (math.log2(rng.cl_mid_f / rng.cl_lo_f)
            == pytest.approx(math.log2(rng.cl_hi_f / rng.cl_mid_f)))


def test_fanout_scaling_adds_whole_gates():
    """Two more identical gates on the node roughly doubles the device term.
    Reported, not folded into the bound — S2 names no CDR."""
    rows = [_row("A", 10.0), _row("B", 10.0)]
    rng = derive_cl_range(rows, _fake_routing(),
                          edge_stages={"lo": ("A", "B"), "hi": ("A", "B")})
    assert fanout_scaled(rng, 0) == pytest.approx(rng.cl_hi_f)
    assert fanout_scaled(rng, 2) == pytest.approx((20.0 + 20.0 + 10.0) * 1e-15)


# ─────────────────────────────────────────────────────────────────────────────
# The gain gate.
# ─────────────────────────────────────────────────────────────────────────────


def test_gain_gate_flags_an_attenuating_stage():
    """It fired for real: the first sizing of the minimum stages measured
    |A| = 0.85, i.e. a 'summer' worse than the wire it replaced."""
    name = next(iter(LOAD_STAGES))
    rows = [_row(name, 6.0, a_load=0.85, corner="ss", temp_c=125.0),
            _row(name, 6.0, a_load=1.5)]
    problems = check_stage_gains(rows)
    assert len(problems) == 1
    assert "0.850" in problems[0] and "ss" in problems[0]


def test_gain_gate_judges_a_stage_at_its_worst_corner():
    """A stage that clears unity only at TT stops working at SS/125 C, and the
    load it presents there would still have gone into cl_hi."""
    name = next(iter(LOAD_STAGES))
    rows = [_row(name, 6.0, a_load=1.4), _row(name, 6.0, a_load=0.9,
                                              corner="ss", temp_c=125.0)]
    assert check_stage_gains(rows)


def test_gain_gate_passes_when_every_stage_amplifies():
    rows = [_row(n, 6.0, a_load=1.4) for n in LOAD_STAGES]
    assert check_stage_gains(rows) == []


def test_min_stage_gain_is_unity_not_something_softer():
    assert MIN_STAGE_GAIN == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# The committed table. G49: an experiment's output is TRACKED if a deliverable
# quotes a number from it — and then the deliverable's numbers stay checkable.
# ─────────────────────────────────────────────────────────────────────────────


def test_csv_roundtrip_is_lossless(tmp_path):
    rows = [_row("A", 5.123456789012345), _row("B", 1e-3)]
    p = tmp_path / "t.csv"
    write_csv(rows, p)
    back = read_csv(p)
    assert back[0]["c_in_ff"] == rows[0]["c_in_ff"]
    assert back[0]["stage"] == "A"
    assert back[0]["ok"] is True


@pytest.mark.skipif(not DATA_CSV.exists(), reason="no committed table")
def test_committed_table_rederives_the_published_range():
    """CL_RANGE.md's headline numbers, re-derived from the CSV with NO
    simulator. If the table or the derivation moves, this says so."""
    rows = read_csv()
    assert len(rows) == len(LOAD_STAGES) * 5 * len(TEMPS_C) * len(VCM_OUT_V)
    rng = derive_cl_range(rows)
    assert rng.cl_lo_f * 1e15 == pytest.approx(13.64, abs=0.05)
    assert rng.cl_mid_f * 1e15 == pytest.approx(32.63, abs=0.05)
    assert rng.cl_hi_f * 1e15 == pytest.approx(78.04, abs=0.05)
    assert rng.ratio == pytest.approx(5.72, abs=0.02)
    assert rng.n_rows_rejected == 0


@pytest.mark.skipif(not DATA_CSV.exists(), reason="no committed table")
def test_committed_cl_range_is_the_single_definition():
    """Rule 9. Anything needing cl_lo/cl_mid/cl_hi calls this rather than
    repeating the numbers, so a value cannot drift between the write-up and
    the experiment that consumes it — and it needs no simulator."""
    a = committed_cl_range()
    b = committed_cl_range()
    assert a is b                                    # cached
    assert a.cl_lo_f < a.cl_mid_f < a.cl_hi_f
    assert a == derive_cl_range(read_csv())


@pytest.mark.skipif(not DATA_CSV.exists(), reason="no committed table")
def test_committed_table_passes_the_gain_gate():
    assert check_stage_gains(read_csv()) == []


@pytest.mark.skipif(not DATA_CSV.exists(), reason="no committed table")
def test_the_derived_range_sits_entirely_below_the_150ff_pin():
    """THE FINDING, as a test. Every corner result this project has published
    was measured at a load 1.9x above the top of the physically derived range.
    If a future sizing sketch moves the range up past 150 fF, that conclusion
    changes and this goes red."""
    rng = derive_cl_range(read_csv())
    assert rng.cl_hi_f < 150e-15
    assert rng.cl_lo_f > 10e-15          # still inside PROPOSED_BOX's floor


@pytest.mark.skipif(not DATA_CSV.exists(), reason="no committed table")
def test_the_sketch_dominates_the_corner_spread():
    """Which is why the range is wide and why the write-up leads on the
    sketch rather than on PVT: the sizing decision moves the load ~6x, the
    process corner ~1.16x."""
    rows = read_csv()
    per_stage = {}
    for n in LOAD_STAGES:
        c = [r["c_in_ff"] for r in rows if r["stage"] == n and r["ok"]]
        per_stage[n] = (min(c), max(c))
    within = max(hi / lo for lo, hi in per_stage.values())
    across = (max(hi for _, hi in per_stage.values())
              / min(lo for lo, _ in per_stage.values()))
    assert within < 1.4
    assert across > 5.0


@pytest.mark.skipif(not DATA_CSV.exists(), reason="no committed table")
def test_stage_table_renders_without_non_ascii():
    """G10: the Windows console is cp1252. A report that crashes under
    redirection loses the run it was reporting on."""
    stage_table(read_csv()).encode("cp1252")
