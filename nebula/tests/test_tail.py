"""
Tests for `device/tail.py` and `experiments/tail_device.py` — the tail
transistor.

All of these run WITHOUT a simulator except the two marked `needs_ngspice`,
which pin the two facts that can only be measured: the SKY130 per-finger bin
ceiling (G53) and the `-nan(ind)` noise failure (G54). Both skip cleanly when
ngspice or the PDK is absent.

WHAT IS PINNED HERE, AND WHY EACH ONE
--------------------------------------
* The geometry gate raises instead of letting ngspice emit "could not find a
  valid modelname", which G31 records as being read as a units error nine times
  out of ten.
* The mirror's reference device is derived, never chosen, and its FINGER WIDTH
  matches the tail's — because a mismatch moves the mirror ratio by ~6 %
  (§5 of the write-up) and nothing about the netlist would look wrong.
* `identity_checks` can FAIL. CLAUDEwa §8 rule 10: a gate without a test that
  proves it can go red is not a gate.
* The noise attribution adds in QUADRATURE. A linear sum is 2.4x the true
  total and would silently re-rank every contributor.
"""

from __future__ import annotations

import math
import shutil

import pytest

from nebula.common.types import Corner
from nebula.device.sky130_runner import SizingPoint, Sky130Point
from nebula.device.tail import (
    C_BYPASS_F,
    L_MIN_UM,
    W_PER_FINGER_MAX_UM,
    TailDevice,
    TailGeometryError,
    min_nf_for_width,
    scale_w_for_current,
)
from nebula.experiments.tail_device import (
    DATA_CSV,
    MIRROR_RATIO,
    REFERENCE_IDEAL,
    REFERENCE_INPUT,
    SWEEP_CORNERS,
    VDSAT_TARGET_V,
    IdentityCheck,
    identity_checks,
    interp_width_at_vdsat,
    read_csv,
    saturation_floor_um_per_amp,
    sizing_rule,
    tail_for,
    w_ladder,
    width_per_amp,
)


def _has_sim() -> bool:
    from nebula.device.sky130_runner import TRIMMED_LIB
    try:
        from nebula.device.ngspice_runner import ngspice_path
        return TRIMMED_LIB.exists() and shutil.which(str(ngspice_path())) is not None
    except Exception:
        return False


needs_ngspice = pytest.mark.skipif(not _has_sim(),
                                   reason="ngspice or the SKY130 PDK is absent")


# ─────────────────────────────────────────────────────────────────────────────
# Geometry: the bin ceiling is on W PER FINGER (G53).
# ─────────────────────────────────────────────────────────────────────────────


def test_bin_ceiling_is_per_finger_not_total_width():
    """G53. 400 um total is fine over 4 fingers and impossible over 1. If this
    is read as a TOTAL-width limit, a tail sinking several mA at
    vdsat <= 0.2 V looks unbuildable when it is not."""
    TailDevice(w_tail=400.0, l_tail=0.5, nf_tail=8)          # 50 um/finger
    with pytest.raises(TailGeometryError, match="per finger"):
        TailDevice(w_tail=400.0, l_tail=0.5, nf_tail=1)      # 400 um/finger


def test_geometry_error_names_the_real_cause():
    """The message must say "per FINGER", because the ngspice error it prevents
    ("could not find a valid modelname") reads like a missing library."""
    with pytest.raises(TailGeometryError) as e:
        TailDevice(w_tail=1000.0, l_tail=0.5, nf_tail=2)
    assert "per finger" in str(e.value) and "Raise nf" in str(e.value)


def test_length_below_the_minimum_bin_is_rejected():
    TailDevice(w_tail=50.0, l_tail=L_MIN_UM, nf_tail=1)
    with pytest.raises(TailGeometryError, match="minimum"):
        TailDevice(w_tail=50.0, l_tail=L_MIN_UM / 2, nf_tail=1)


def test_a_zero_bypass_is_rejected():
    """A zero bypass re-opens G54's NaN, so it is a geometry error rather than
    a value that merely happens to be unusual."""
    with pytest.raises(TailGeometryError, match="G54"):
        TailDevice(w_tail=100.0, l_tail=0.5, nf_tail=8, c_bypass_f=0.0)


@pytest.mark.parametrize("w", [1.0, 99.0, 100.0, 800.0, 3000.0])
def test_min_nf_for_width_always_clears_the_ceiling(w):
    nf = min_nf_for_width(w, MIRROR_RATIO)
    assert w / nf <= W_PER_FINGER_MAX_UM
    # ...and stays a whole multiple of the ratio, so nf_ref is a whole number
    # and the fingers match.
    assert nf % int(MIRROR_RATIO) == 0


# ─────────────────────────────────────────────────────────────────────────────
# The mirror: the reference is DERIVED, and its fingers match.
# ─────────────────────────────────────────────────────────────────────────────


def test_reference_width_is_the_tail_divided_by_the_ratio():
    t = TailDevice(w_tail=160.0, l_tail=0.5, nf_tail=8, mirror_ratio=8.0)
    assert t.w_ref == pytest.approx(20.0)


def test_reference_fingers_match_the_tail_fingers():
    """THE DESIGN CHOICE, pinned. The reference is N unit fingers smaller, not
    a differently shaped device, so the ratio is set by geometry. Measured
    consequence of getting it wrong: nf_ref=8 against nf_tail=8 gives a
    realised ratio of 9.55 instead of 8, against 7.38 when matched."""
    t = TailDevice(w_tail=100.0, l_tail=0.5, nf_tail=8, mirror_ratio=8.0)
    assert t.nf_ref == 1
    assert t.finger_matched
    assert t.w_ref / t.nf_ref == pytest.approx(t.w_tail / t.nf_tail)


def test_fingers_do_not_match_when_nf_is_not_a_multiple_of_the_ratio():
    """Reported rather than hidden: an unmatched mirror's ratio error is a
    layout artifact, not physics, and the write-up separates the two."""
    t = TailDevice(w_tail=200.0, l_tail=0.5, nf_tail=2, mirror_ratio=8.0)
    assert t.nf_ref == 1
    assert not t.finger_matched


def test_reference_current_is_the_side_current_over_the_ratio():
    t = TailDevice(w_tail=100.0, l_tail=0.5, nf_tail=8, mirror_ratio=8.0)
    assert t.i_ref_a(1.6e-3) == pytest.approx(0.2e-3)


def test_default_bypass_is_the_committed_value():
    """One definition (rule 9): the netlist must not carry a second one."""
    assert TailDevice(w_tail=100.0, l_tail=0.5, nf_tail=8).c_bypass_f == C_BYPASS_F


# ─────────────────────────────────────────────────────────────────────────────
# The sizing rule.
# ─────────────────────────────────────────────────────────────────────────────


def test_width_per_amp_is_the_stated_direction():
    """um of width PER AMP, so a caller multiplies by a current to get a width.
    Quoted the other way round it is a current density and the arithmetic
    inverts silently."""
    assert width_per_amp(1.5e-3, 166.7) == pytest.approx(111_133.3, rel=1e-4)


def test_scale_w_for_current_is_linear():
    a = scale_w_for_current(1e-3, 111.2e3, 8)
    b = scale_w_for_current(2e-3, 111.2e3, 8)
    assert b == pytest.approx(2 * a)


@pytest.mark.parametrize("bad", [(0.0, 1e5, 8), (1e-3, 0.0, 8), (1e-3, 1e5, 0)])
def test_scale_w_for_current_rejects_nonsense(bad):
    with pytest.raises(ValueError):
        scale_w_for_current(*bad)


def test_interp_finds_the_width_at_the_vdsat_target():
    """Log-linear in width, which is how vdsat actually moves against it."""
    w = interp_width_at_vdsat([100.0, 400.0], [0.30, 0.10], 0.20)
    assert 100.0 < w < 400.0
    # exactly the geometric interpolation: half way in log W at half way in v
    assert w == pytest.approx(200.0, rel=1e-9)


def test_interp_returns_none_rather_than_extrapolating():
    """A sizing rule read off an extrapolation is a rule about the fit, not
    about the device."""
    assert interp_width_at_vdsat([100.0, 400.0], [0.30, 0.25], 0.20) is None
    assert interp_width_at_vdsat([100.0], [0.20], 0.20) is None


def test_w_ladder_is_geometric_and_ordered():
    L = w_ladder(25.0, 800.0, 9)
    assert len(L) == 9 and L[0] == pytest.approx(25.0) and L[-1] == pytest.approx(800.0)
    ratios = [b / a for a, b in zip(L, L[1:])]
    assert all(r == pytest.approx(ratios[0]) for r in ratios)


def test_tail_for_picks_a_buildable_nf_without_being_told():
    t = tail_for(600.0, 0.5)
    assert t.w_tail / t.nf_tail <= W_PER_FINGER_MAX_UM
    assert t.finger_matched


# ─────────────────────────────────────────────────────────────────────────────
# The identity checks — and the proof that they can FAIL (rule 10).
# ─────────────────────────────────────────────────────────────────────────────


def _point() -> SizingPoint:
    kw = dict(REFERENCE_INPUT)
    kw["nf"] = int(kw["nf"])
    return SizingPoint(**kw, tail=tail_for(100.0, 0.5))  # type: ignore[arg-type]


def _good(point: SizingPoint) -> Sky130Point:
    """A result in which all three identities hold, by construction."""
    vgs, vcm = 0.896179, point.vcm
    v_src = vcm - vgs
    r = Sky130Point(ok=True, point=point, vgs=vgs, v_src_dc=v_src,
                    vds_tail=v_src, vdsat_tail=0.1882,
                    i_tail_meas_a=0.9226 * point.i_tail_per_side_a)
    return r


def test_identity_checks_pass_on_a_consistent_result():
    p = _point()
    assert all(c.passed for c in identity_checks(_good(p), p))


def test_the_coupling_identity_goes_red_when_vds_tail_is_not_the_source_node():
    """This is the identity the whole experiment rests on: the tail's drain IS
    the pair's source node, which is what makes its headroom a constraint on
    VCM, W_in and i_bias rather than on the tail alone. Break it by 10 mV and
    the check must fail."""
    p = _point()
    r = _good(p)
    r.vds_tail = r.v_src_dc + 0.010
    c = [c for c in identity_checks(r, p) if "vds_tail" in c.name][0]
    assert not c.passed


def test_the_bias_equation_goes_red_when_v_source_disagrees_with_VCM_minus_Vgs():
    p = _point()
    r = _good(p)
    r.v_src_dc += 0.050
    r.vds_tail = r.v_src_dc              # keep the OTHER identity satisfied
    c = [c for c in identity_checks(r, p) if "VCM" in c.name][0]
    assert not c.passed


def test_a_grossly_wrong_mirror_ratio_goes_red():
    """The tolerance is loose on purpose -- the topology has a real ~8 % gain
    error from channel-length modulation -- but a mirror delivering 8x or
    nothing must still be caught."""
    p = _point()
    r = _good(p)
    r.i_tail_meas_a = 8.0 * p.i_tail_per_side_a
    c = [c for c in identity_checks(r, p) if "I_tail" in c.name][0]
    assert not c.passed


def test_the_real_mirror_gain_error_is_inside_the_tolerance():
    """-8 % is physics (the reference sits at ~1.0 V vds, the tail at ~0.34 V),
    so it must NOT trip the gate. If it did, the gate would be measuring the
    topology rather than checking the plumbing."""
    p = _point()
    r = _good(p)
    c = [c for c in identity_checks(r, p) if "I_tail" in c.name][0]
    assert c.passed and abs(r.mirror_gain_error) < 0.25


def test_identity_check_lines_are_ascii():
    """G10: this output is captured under redirection on a cp1252 console."""
    p = _point()
    for c in identity_checks(_good(p), p):
        c.line().encode("ascii")


# ─────────────────────────────────────────────────────────────────────────────
# Derived quantities on Sky130Point.
# ─────────────────────────────────────────────────────────────────────────────


def test_tail_margin_is_none_for_an_ideal_tail():
    """None, not zero. An ideal sink has no headroom requirement, and a zero
    would score as "exactly on the boundary" in every comparison."""
    r = Sky130Point(ok=True)
    assert r.tail_margin_v is None
    assert r.tail_in_saturation is None
    assert r.has_real_tail is False


def test_tail_margin_and_saturation_agree():
    r = Sky130Point(ok=True, vds_tail=0.35, vdsat_tail=0.19)
    assert r.tail_margin_v == pytest.approx(0.16)
    assert r.tail_in_saturation is True
    r.vds_tail = 0.10
    assert r.tail_margin_v == pytest.approx(-0.09)
    assert r.tail_in_saturation is False


def test_noise_shares_are_computed_on_POWER_not_amplitude():
    """The per-instance numbers are RMS volts and add in QUADRATURE. Sharing
    them linearly would over-report every small contributor: here the two
    equal 3-unit terms and one 4-unit term are 18/18/32 of 34.0... in power,
    not 30/30/40 as a linear split would say."""
    r = Sky130Point(ok=True, vn_in_vrms=math.sqrt(9 + 9 + 16),
                    noise_by_device={"a": 3.0, "b": 3.0, "c": 4.0})
    sh = r.noise_share_power()
    assert sh["a"] == pytest.approx(9 / 34)
    assert sh["c"] == pytest.approx(16 / 34)
    assert sum(sh.values()) == pytest.approx(1.0)
    assert sh["c"] != pytest.approx(4 / 10)      # the linear answer, and wrong


def test_the_attribution_gate_notices_a_missing_contributor():
    """If the parts do not reconstruct the total, a share read off them is
    meaningless. `noise_quadrature_residual` is what makes that checkable."""
    ok = Sky130Point(ok=True, vn_in_vrms=5.0,
                     noise_by_device={"a": 3.0, "b": 4.0})
    assert ok.noise_quadrature_residual() == pytest.approx(0.0, abs=1e-12)
    missing = Sky130Point(ok=True, vn_in_vrms=5.0, noise_by_device={"a": 3.0})
    assert missing.noise_quadrature_residual() == pytest.approx(0.4)


def test_measured_power_uses_the_measured_supply_current():
    """Not the requested one. With a mirror they differ: the reference branch
    is real current and the mirror delivers a few percent less than asked."""
    p = _point()
    r = Sky130Point(ok=True, point=p, i_supply_a=3.0e-3)
    assert r.power_measured_w == pytest.approx(1.8 * 3.0e-3)


def test_requested_total_current_includes_the_reference_branch():
    p = _point()
    assert p.i_ref_a == pytest.approx(p.i_tail_per_side_a / MIRROR_RATIO)
    assert p.i_total_a == pytest.approx(2 * p.i_tail_per_side_a + p.i_ref_a)
    # ...and is exactly 2x the side current when the tail is ideal.
    ideal = SizingPoint(**{**REFERENCE_INPUT, "nf": 4})  # type: ignore[arg-type]
    assert ideal.i_ref_a == 0.0
    assert ideal.i_total_a == pytest.approx(2 * ideal.i_tail_per_side_a)


# ─────────────────────────────────────────────────────────────────────────────
# The two facts that can only be measured.
# ─────────────────────────────────────────────────────────────────────────────


@needs_ngspice
def test_the_per_finger_bin_ceiling_is_real_in_the_pdk():
    """G53, against the library rather than against a comment. W/nf = 100 um
    builds; 101 um does not, at three different finger counts."""
    from nebula.device.sky130_runner import run_point
    from nebula.experiments.tail_device import _base_point

    corner = SWEEP_CORNERS[0]
    for nf, ok_w, bad_w in ((1, 100.0, 101.0), (2, 200.0, 210.0),
                            (4, 400.0, 410.0)):
        # ratio 1.0 so the reference is the same device as the tail and the
        # test is about the BIN, not about the mirror.
        t_ok = TailDevice(w_tail=ok_w, l_tail=0.5, nf_tail=nf, mirror_ratio=1.0)
        r = run_point(_base_point(1.5e-3, corner, t_ok), swing=False)
        assert r.ok, f"W={ok_w} nf={nf} should build: {r.fail_reason}"
        with pytest.raises(TailGeometryError):
            TailDevice(w_tail=bad_w, l_tail=0.5, nf_tail=nf, mirror_ratio=1.0)


@needs_ngspice
def test_the_bypass_capacitor_does_not_change_the_measured_noise():
    """G54. The bypass is there for a circuit reason and removes a numerical
    singularity; it must not be BUYING the answer. 10 pF and 100 pF have to
    agree, or the element is doing something to the result."""
    from nebula.device.sky130_runner import run_point
    from nebula.experiments.tail_device import _base_point

    corner = SWEEP_CORNERS[0]
    vals = []
    for c_byp in (C_BYPASS_F, 10 * C_BYPASS_F):
        t = TailDevice(w_tail=100.0, l_tail=0.5, nf_tail=8, c_bypass_f=c_byp)
        r = run_point(_base_point(1.5e-3, corner, t), swing=False)
        assert r.ok, r.fail_reason
        vals.append(r.vn_in_vrms)
    assert vals[0] == pytest.approx(vals[1], rel=1e-6)


@needs_ngspice
def test_the_reference_point_still_reproduces_what_HANDOFF_publishes():
    """The ideal-tail path must be untouched by session 13, or the comparison
    between "ideal tail" and "real tail" is between two different circuits."""
    from nebula.device.sky130_runner import run_point
    from nebula.experiments.tail_device import _base_point

    r = run_point(_base_point(REFERENCE_INPUT["i_tail_per_side_a"],
                              SWEEP_CORNERS[0], None), swing=False)
    assert r.ok, r.fail_reason
    for name, published in REFERENCE_IDEAL.items():
        assert getattr(r, name) == pytest.approx(published, rel=0.02), name


# ─────────────────────────────────────────────────────────────────────────────
# The netlist. `spice/ctle.cir` is the human-readable copy of the same two
# blocks; CLAUDEwa §8 rule 9 says exactly one definition, referenced, and G32
# is what happens when two drift apart by one parameter.
# ─────────────────────────────────────────────────────────────────────────────


def _netlist(tail, passives=None) -> str:
    """Render the runner's netlist for a point with/without a tail.

    `passives` defaults to None — the IDEAL R/C block — so every assertion
    below still describes the circuit session 13 measured. The runner grew a
    second independent switch in session 17 (drawn SKY130 passives), and
    `passive_block` is the one function that renders it, so this helper calls
    it rather than growing a second copy (rule 9).
    """
    import nebula.device.sky130_runner as R
    p = SizingPoint(**{**REFERENCE_INPUT, "nf": 4}, tail=tail,  # type: ignore[arg-type]
                    passives=passives)
    if tail is None:
        src, probe = R._TAIL_IDEAL.format(IT="{IT}"), ""
    else:
        src = R._TAIL_MIRROR.format(
            device=tail.device, n_mir=f"{tail.mirror_ratio:g}",
            w_tail=f"{tail.w_tail:.6g}", l_tail=f"{tail.l_tail:.6g}",
            nf_tail=int(tail.nf_tail), w_ref=f"{tail.w_ref:.6g}",
            nf_ref=int(tail.nf_ref),
            i_ref=f"{tail.i_ref_a(p.i_tail_per_side_a):.9g}",
            c_byp=f"{tail.c_bypass_f:.9g}")
        probe = R._TAIL_PROBE.format(device=tail.device)
    return R.assemble_netlist(
        lib="lib", corner="tt", device=p.device, w=p.w, l=p.l, nf=int(p.nf),
        rl=p.rl, rs=p.rs, cs=p.cs, cl=p.cl, it=p.i_tail_per_side_a,
        vdd=p.vdd, vcm=p.vcm, swing_block="", temp_c=27.0,
        tail_source=src, tail_probe=probe,
        passive_block=R.passive_block(passives),
        noise_summary="", noise_probe="", f_top="20g")


def test_the_ideal_passive_block_is_still_what_session_13_measured():
    """The two switches are INDEPENDENT, and the tail results must not have
    moved when the passives became switchable.

    Session 17 split `RLp`/`RLn`/`Rdeg`/`Cdeg` out of `_TOPOLOGY` so drawn
    SKY130 devices could take their place. The ideal branch has to render
    BYTE-IDENTICALLY, or every number in TAIL_DEVICE.md and S9_YIELD.md §9 is a
    measurement of a slightly different circuit.
    """
    n = _netlist(None)
    assert "RLp   vdd outp {RL}" in n
    assert "RLn   vdd outn {RL}" in n
    assert "Rdeg  s1 s2 {RS}" in n
    assert "Cdeg  s1 s2 {CS}" in n
    assert "sky130_fd_pr__res_high_po" not in n
    assert "cap_mim" not in n


def test_the_ideal_netlist_still_has_two_ideal_sinks_and_no_mirror():
    n = _netlist(None)
    assert "It1   s1 0" in n and "It2   s2 0" in n
    assert "XMR" not in n and "Iref" not in n and "nbias" not in n


def test_the_mirror_netlist_has_two_tails_one_reference_and_a_bypass():
    """TWO tail devices, not one. A single shared tail would put a low
    impedance across Rs/Cs and short out the degeneration — and it is also why
    the tail's noise is NOT common-mode (§4)."""
    n = _netlist(tail_for(100.0, 0.5))
    assert "XMT1  s1" in n and "XMT2  s2" in n     # one sink per side
    assert n.count("XMR ") == 1                    # exactly one reference
    assert "Cbyp  nbias 0" in n
    assert "It1" not in n and "It2" not in n       # the ideal sinks are gone


def test_the_mirror_netlist_carries_the_geometry_it_was_built_with():
    """G32: a netlist that describes a different device from the runner that
    produced the numbers is invisible and moved the body-effect term by 30 %."""
    t = tail_for(160.0, 0.75)
    n = _netlist(t)
    assert f"WT={t.w_tail:g}" in n and f"LT={t.l_tail:g}" in n
    assert f"NFT={t.nf_tail}" in n
    assert f"WREF={t.w_ref:g}" in n and f"NFREF={t.nf_ref}" in n


def test_the_reference_current_in_the_netlist_is_the_side_current_over_N():
    t = tail_for(100.0, 0.5)
    n = _netlist(t)
    i_side = REFERENCE_INPUT["i_tail_per_side_a"]
    assert f"IREF={i_side / t.mirror_ratio:.9g}" in n


def test_the_supply_branch_current_is_printed_on_every_run():
    """S6 is billed on the MEASURED supply current, so the probe must be there
    whether or not a tail is fitted."""
    for tail in (None, tail_for(100.0, 0.5)):
        assert "print i(Vdd)" in _netlist(tail)


def test_tail_primitives_are_probed_only_when_a_tail_exists():
    assert "xmt1" not in _netlist(None)
    n = _netlist(tail_for(100.0, 0.5))
    for prop in ("id", "vds", "vdsat", "gm"):
        assert f"@m.xmt1.msky130_fd_pr__nfet_01v8[{prop}]" in n


def test_the_sandbox_netlist_describes_the_same_mirror():
    """`spice/ctle.cir` is what a human opens. G32 says a netlist that has
    drifted from the runner is invisible and silently explains away
    discrepancies, so the sandbox must carry the same element names."""
    from nebula.device.sky130_runner import SPICE_DIR
    text = (SPICE_DIR / "ctle.cir").read_text(encoding="ascii")
    for element in ("XMR", "XMT1", "XMT2", "Iref", "Cbyp"):
        assert element in text, element
    # ...and the legacy ideal sinks must still be present, commented, so the
    # topology every published number through 12b used stays readable.
    assert "It1" in text and "It2" in text


# ─────────────────────────────────────────────────────────────────────────────
# The saturation floor — interpolated, not read off a ladder rung (G52).
# ─────────────────────────────────────────────────────────────────────────────


def _row(w, margin, i_side=1.5e-3, corner="ss_vdd0.95_t125", l=0.5):
    from nebula.experiments.tail_device import TailRow
    return TailRow(corner=corner, process="ss", vdd_scale=0.95, temp_c=125.0,
                   i_side_a=i_side, w_tail=w, l_tail=l, nf_tail=8, nf_ref=1,
                   ok=True, tail_margin_v=margin)


def test_saturation_floor_is_interpolated_not_the_smallest_passing_rung():
    """G52. Reading the smallest PASSING rung overstates the floor by up to one
    rung. On this ladder the crossing is at 200 um; the smallest passing rung
    is 400 um, which would be 2x wrong."""
    rows = [_row(100.0, -0.10), _row(400.0, +0.10)]
    got = saturation_floor_um_per_amp(rows, "ss_vdd0.95_t125", 0.5)
    assert got == pytest.approx(200.0 / 1.5e-3, rel=1e-9)
    assert got < 400.0 / 1.5e-3


def test_saturation_floor_is_below_the_vdsat_target_rule():
    """The consistency check that caught the ladder artifact. The saturation
    floor is by construction LOOSER than a vdsat = 0.20 V target when
    v(source) is ~0.33 V, so a floor above the rule is impossible and means the
    grid is being measured instead of the device."""
    rows = [r for r in read_csv(DATA_CSV) if r.ok]
    worst = str(SWEEP_CORNERS[1])
    floor = saturation_floor_um_per_amp(rows, worst, 0.5)
    rule = sizing_rule(rows).get(f"L=0.5 {worst}", {})
    assert floor is not None and rule
    assert floor < min(d["um_per_amp"] for d in rule.values())


def test_saturation_floor_declines_to_answer_when_not_bracketed():
    """Every rung saturated means the floor is BELOW the ladder. Returning the
    smallest rung would be a statement about the ladder."""
    assert saturation_floor_um_per_amp(
        [_row(100.0, +0.05), _row(400.0, +0.10)], "ss_vdd0.95_t125", 0.5) is None


def test_the_committed_sweep_reproduces_the_published_sizing_rule():
    """TAIL_DEVICE.md sec 3 and `s9_yield.TAIL_UM_PER_AMP` quote this number.
    If the CSV moves, the rule the S9 re-run was performed under moves with it,
    and this goes red rather than the two silently disagreeing (rule 9)."""
    from nebula.experiments.s9_yield import TAIL_L_UM, TAIL_UM_PER_AMP
    rows = [r for r in read_csv(DATA_CSV) if r.ok]
    rule = sizing_rule(rows)[f"L={TAIL_L_UM:g} {SWEEP_CORNERS[1]}"]
    per_amp = [d["um_per_amp"] for d in rule.values()]
    assert min(per_amp) <= TAIL_UM_PER_AMP <= max(per_amp)


def test_the_sizing_rule_really_is_a_current_density():
    """The claim in the write-up, as a test: width per amp must be roughly
    constant across a 4x change in current. If it drifted a lot, `w_tail` would
    not be derivable from `i_bias` and would have to go back in the box."""
    rows = [r for r in read_csv(DATA_CSV) if r.ok]
    for key, per_i in sizing_rule(rows).items():
        vals = [d["um_per_amp"] for d in per_i.values()]
        if len(vals) > 1:
            assert max(vals) / min(vals) < 1.30, key
