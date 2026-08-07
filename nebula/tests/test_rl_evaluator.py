"""
§6d — the poison-safe evaluator, and the real-passive netlist path it needs.

*"There are four documented classes of ngspice failure that report success and
exit zero, plus `alter` returning stale values, plus `w` and `mult` being
silently ignored. An RL agent is an adversarial search for exactly those
regions, because a garbage result that happens to score well is a free
reward."*

Every rejection below is exercised by CONSTRUCTING the pathological result and
asserting the gate names it. That is the only way to test a failure mode whose
defining property is that ngspice exits 0 — you cannot wait for it to happen.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.device.passives import to_geometry
from nebula.device.sky130_runner import (
    CTLE_LIB,
    TRIMMED_LIB,
    SizingPoint,
    Sky130Point,
    lib_for_device,
    passive_block,
    run_point,
)
from nebula.device.tail import TailDevice
from nebula.rl import evaluator as E
from nebula.rl.contract import N_ACTIONS, sizing_from_u


def _have_ngspice() -> bool:
    from nebula.device.ngspice_runner import ngspice_path
    try:
        return ngspice_path().exists()
    except FileNotFoundError:
        return False


HAVE_NGSPICE = _have_ngspice()


# ─────────────────────────────────────────────────────────────────────────────
# The real-passive netlist path.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_ideal_passive_block_is_byte_identical_to_the_old_inline_text():
    """Every published number through session 16 was measured with these four
    lines inline in `_TOPOLOGY`. Splitting them out must not move a byte, or
    the reproduction gates in `robust_geometry.py` and `s9_yield.py` become
    comparisons against a different circuit."""
    assert passive_block(None) == (
        "RLp   vdd outp {RL}\n"
        "RLn   vdd outn {RL}\n"
        "\n"
        "* Between the two SOURCES, not source-to-ground: each half-circuit sees Rs/2,\n"
        "* which is where the factor of two in k = 1 + (gm+gmbs)*Rs/2 comes from.\n"
        "Rdeg  s1 s2 {RS}\n"
        "Cdeg  s1 s2 {CS}\n"
    )


def test_the_real_passive_block_emits_drawable_devices():
    geo = to_geometry(318.58, 1.9012e-12, 565.03)
    text = passive_block(geo)
    assert "sky130_fd_pr__res_high_po" in text
    assert "sky130_fd_pr__cap_mim_m3_1" in text
    # Three terminals on the resistors (the third is the substrate, which
    # carries the res_po bottom-plate parasitic), two on the MIM.
    assert text.count("Xrlp") == 1 and text.count("Xrln") == 1
    assert "mult" not in text and "mf=" not in text, "G56: never `mult`"


def test_cl_stays_an_ideal_capacitor_even_with_drawn_passives():
    """`cl` is the NEXT stage's input capacitance — a screened context variable
    (CL_RANGE.md), not a device this circuit draws. Drawing it would be
    inventing a load."""
    text = passive_block(to_geometry(318.58, 1.9e-12, 565.0))
    assert "CL" not in text and "cap_mim" in text
    from nebula.device.sky130_runner import _TOPOLOGY
    assert "CLp   outp 0 {{CL}}" in _TOPOLOGY


def test_real_passives_select_the_extended_library():
    """Drawn devices need the R/C model cards, which the nfet-only trim lacks —
    and asking for them silently produces G31's misleading message."""
    from nebula.device.sky130_runner import NFET_01V8

    assert lib_for_device(NFET_01V8, real_passives=False) == TRIMMED_LIB
    assert lib_for_device(NFET_01V8, real_passives=True) == CTLE_LIB


def test_multiplier_helper_uses_m_and_refuses_a_bad_count():
    from nebula.device.sky130_runner import _m_suffix

    assert _m_suffix(1) == ""
    assert _m_suffix(2) == " m=2"
    with pytest.raises(ValueError):
        _m_suffix(0)


def test_the_tunable_sweep_refuses_drawn_passives():
    """`alter Rdeg` names an element that does not exist once the passives are
    drawn. ngspice reports the failed alter as a WARNING and exits 0 (G26), so
    all 67 settings would come back carrying the FIRST geometry's numbers — a
    converged-looking sweep of one point."""
    from nebula.device.sky130_runner import TunableSetting, run_tunable_sweep

    geo = to_geometry(318.58, 1.9e-12, 565.0)
    pt = SizingPoint(w=89.3, l=0.4, nf=4, rs=318.58, cs=1.9e-12, rl=565.0,
                     cl=32.6e-15, i_tail_per_side_a=1.6e-3, vcm=1.4,
                     tail=TailDevice(w_tail=180.0, l_tail=0.5, nf_tail=8),
                     passives=geo)
    out = run_tunable_sweep(pt, [TunableSetting(100.0, 1e-12)] * 3)
    assert len(out) == 3
    assert all((not p.ok) and "alter" in (p.fail_reason or "") for p in out)


# ─────────────────────────────────────────────────────────────────────────────
# validate() — every documented poison, constructed.
# ─────────────────────────────────────────────────────────────────────────────


def _point() -> SizingPoint:
    return SizingPoint(w=89.3, l=0.4, nf=4, rs=318.58, cs=1.9e-12, rl=565.0,
                       cl=32.6e-15, i_tail_per_side_a=1.626e-3, vcm=1.407,
                       vdd=1.8,
                       tail=TailDevice(w_tail=180.8, l_tail=0.5, nf_tail=8),
                       passives=None)


def _clean(**over) -> Sky130Point:
    """A healthy result, perturbable one field at a time."""
    pt = Sky130Point(ok=True, point=_point(), corner="tt")
    base = dict(gm=0.01243, gmbs=0.002164, gds=4.7e-4, vth=0.7166,
                vds=0.4160, vdsat=0.1881, vgs=1.0, id_a=1.626e-3,
                v_out_dc=0.881, v_src_dc=0.465, i_supply_a=3.311e-3,
                g_dc_db=6.007, g_nyq_db=12.96, g_pk_db=13.23,
                f_pk_hz=1.738e9, g_top_db=3.74, vn_in_vrms=2.23e-4,
                vds_tail=0.465, vdsat_tail=0.138, i_tail_meas_a=1.5e-3,
                gm_tail=0.008, v_bias_dc=1.0)
    base.update(over)
    for k, v in base.items():
        setattr(pt, k, v)
    return pt


# ── the two readings of `validate`, so assertions stay about the circuit ─────

def _why_invalid(pt, point) -> str:
    """Assert the result is INVALID and hand back the reason."""
    verdict, reason = E.validate(pt, point)
    assert verdict is E.Verdict.INVALID, (
        f"expected INVALID, got {verdict.value}: {reason}")
    return reason


def _why_headroom(pt, point) -> str:
    """Assert the result is HEADROOM_ONLY and hand back the reason."""
    verdict, reason = E.validate(pt, point)
    assert verdict is E.Verdict.HEADROOM_ONLY, (
        f"expected HEADROOM_ONLY, got {verdict.value}: {reason}")
    return reason


def _verdict(pt, point):
    return E.validate(pt, point)[0]


def test_a_healthy_result_validates():
    assert _verdict(_clean(), _point()) is E.Verdict.VALID


def test_a_failed_run_is_rejected_with_its_own_reason():
    bad = Sky130Point(ok=False, fail_reason="singular matrix", point=_point())
    assert "singular matrix" in _why_invalid(bad, _point())


@pytest.mark.parametrize("field", [
    "gm", "gmbs", "vth", "vds", "vdsat", "vgs", "id_a", "v_out_dc",
    "v_src_dc", "i_supply_a", "g_dc_db", "g_nyq_db", "g_pk_db", "f_pk_hz",
    "g_top_db", "vn_in_vrms", "vds_tail", "vdsat_tail", "i_tail_meas_a",
    "gm_tail",
])
def test_every_required_vector_is_actually_required(field):
    """A missing vector must be a failure, never a zero (rule 1)."""
    assert field in _why_invalid(_clean(**{field: None}), _point())


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_a_nan_or_inf_never_reaches_an_observation(bad):
    """G54: `.noise` can return `inoise_total = -nan(ind)` and exit 0. A laxer
    parser would carry NaN into a spec check, where `nan < tau` is False and
    reads as a genuine FAILURE — biasing a yield downward, silently."""
    assert "vn_in_vrms" in _why_invalid(_clean(vn_in_vrms=bad), _point())


def test_the_tail_is_not_optional():
    """An evaluator that ACCEPTS a missing tail margin is one `tail=None` away
    from scoring the coupled inequality as satisfied-by-absence."""
    assert "vds_tail" in _why_invalid(_clean(vds_tail=None), _point())
    assert "vdsat_tail" in _why_invalid(_clean(vdsat_tail=None), _point())


# ---- G44: the fictitious peak ----------------------------------------------

def test_a_response_still_rising_at_the_search_edge_is_rejected():
    """`meas ac MAX` returns the RANGE EDGE, and the caller cannot tell that
    from a real maximum. Measured: rl=800 at 3.25 mA reports 1.08 dB of
    peaking at 19.95 GHz with g_pk - g_top = -0.001 dB."""
    why = _why_invalid(_clean(g_pk_db=7.09, g_top_db=7.09, f_pk_hz=1.995e10),
                       _point())
    assert "sweep edge" in why


def test_a_SMALL_but_GENUINE_peak_is_accepted():
    """The other half of `has_interior_peak`, and it must NOT be rejected.

    rs = 50 ohm measures 0.165 dB of peaking at 1.318 GHz with
    g_pk - g_top = 9.23 dB. Nothing about that measurement is wrong; the
    circuit simply does not equalise, and the reward scores it as the large S3
    shortfall it is. Rejecting it would erase the gradient over the entire
    low-peaking region of the box — which is where a random policy starts.
    """
    pt = _clean(g_dc_db=6.0, g_pk_db=6.165, g_top_db=-3.07, f_pk_hz=1.318e9)
    assert not pt.has_interior_peak, (
        "this test is not exercising what it claims: `has_interior_peak` "
        "should reject this design and the validity gate should not")
    assert _verdict(pt, _point()) is E.Verdict.VALID


# ---- operating point --------------------------------------------------------

def test_the_operating_point_is_checked_BEFORE_the_ac_result():
    """The order is load-bearing, and under Call 1 it decides the VERDICT too.

    `rl` at the box ceiling takes the pair out of saturation AND pushes the
    peak to the sweep edge. Checked AC-first, this reports "f_pk out of range"
    and lands in INVALID — a flat floor. Checked `.op`-first it reports the
    triode and lands in HEADROOM_ONLY, which is graded. So the ordering is not
    only about which file the reader is sent to; it is about whether the
    policy gets a gradient at all.
    """
    why = _why_headroom(_clean(vds=0.055, vdsat=0.349,
                               g_pk_db=7.09, g_top_db=7.09, f_pk_hz=1.995e10),
                        _point())
    assert "out of saturation" in why and "sweep edge" not in why


def test_a_pair_in_triode_is_HEADROOM_ONLY_not_invalid():
    """CALL 1. `.op` converged, so `vds` and `vdsat` are trustworthy; only the
    AC spec set is not. Returning INVALID here put a FLAT floor over the whole
    triode region, and `tail_saturation` binds on 2.6-13.3 % of the box, so a
    fresh policy lands there often and had no direction out."""
    why = _why_headroom(_clean(vds=0.05, vdsat=0.35), _point())
    assert "input pair" in why and "out of saturation" in why


def test_a_tail_in_triode_is_HEADROOM_ONLY_not_invalid():
    why = _why_headroom(_clean(vds_tail=0.10, vdsat_tail=0.20), _point())
    assert "tail" in why and "out of saturation" in why


def test_both_devices_in_triode_names_both():
    why = _why_headroom(_clean(vds=0.05, vdsat=0.35,
                               vds_tail=0.10, vdsat_tail=0.20), _point())
    assert "input pair" in why and "tail" in why


def test_a_triode_result_carries_headroom_and_NO_measurement():
    """`meas is None` is the mechanism, not a convention: the AC spec set of a
    device in triode must not be scorable, and the only way to guarantee that
    is for it not to exist on the object."""
    import numpy as np

    from nebula.rl.contract import N_ACTIONS as NA
    from nebula.rl.contract import sizing_from_u as sfu

    class _Stub:
        def __call__(self, *a, **k):
            return _clean(vds=0.05, vdsat=0.35)

    import nebula.rl.evaluator as EV
    orig = EV.run_point
    EV.run_point = _Stub()
    try:
        b = E.SpiceBudget()
        ev = EV.evaluate(sfu(np.full(NA, 0.5)), b)
    finally:
        EV.run_point = orig
    assert ev.verdict is E.Verdict.HEADROOM_ONLY
    assert ev.meas is None, "the AC spec set must not survive a triode design"
    assert ev.headroom is not None
    assert ev.headroom["pair_margin_v"] < 0.0
    assert not ev.valid and ev.scorable


@pytest.mark.parametrize("node,value", [("v_out_dc", -0.5), ("v_out_dc", 2.5),
                                        ("v_src_dc", -0.4), ("v_bias_dc", 3.0)])
def test_a_dc_node_outside_the_rails_is_rejected(node, value):
    """INVALID, not HEADROOM_ONLY: a node outside the rails on a converged
    `.op` means the netlist or the topology is wrong, so there is no
    trustworthy headroom to grade."""
    assert "outside the rails" in _why_invalid(_clean(**{node: value}), _point())


def test_a_device_that_is_off_is_rejected():
    assert "not positive" in _why_invalid(_clean(gm=0.0), _point())


# ---- plausibility -----------------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("g_dc_db", 999.0), ("g_dc_db", -999.0), ("g_pk_db", 1e4),
])
def test_an_implausible_gain_is_rejected(field, value):
    assert "not an amplifier" in _why_invalid(_clean(**{field: value}), _point())


def test_a_collapsed_or_diverged_noise_integration_is_rejected():
    assert "collapsed or diverged" in _why_invalid(_clean(vn_in_vrms=1e-15), _point())
    assert "collapsed or diverged" in _why_invalid(_clean(vn_in_vrms=99.0), _point())


def test_a_supply_sourcing_current_is_rejected():
    """`i_supply <= 0` means VDD is SOURCING, i.e. this is not the requested
    operating point."""
    assert "SOURCING" in _why_invalid(_clean(i_supply_a=-1e-3), _point())


def test_a_peak_below_the_sweep_floor_is_rejected():
    """G44's other half: a monotonically falling response reports f_pk at the
    10 MHz sweep START."""
    assert "f_pk" in _why_invalid(_clean(f_pk_hz=1e6), _point())


# ─────────────────────────────────────────────────────────────────────────────
# The budget and the geometry gate.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_whole_rs_rl_box_is_realisable():
    """MEASURED, and it is the opposite of what the head-resistance floor
    suggests.

    PASSIVES.md §4.2 records that `res_high_po`'s fixed head term puts a floor
    of **1444 ohm at w = 0.35 um**, which reads like the low end of the
    50-1000 ohm `rs`/`rl` bound being unreachable. It is not: that is a
    PER-WIDTH floor, and `to_geometry`'s width ladder plus `m <= 8` clears it
    everywhere. Every value in [50, 1000] builds, and so does everything down
    to 20 ohm.

    Consequence, and it is why this is a test rather than a note: the
    `unrealisable_geometry` invalidity can never fire from inside the box, so
    if it ever appears in a run's histogram something else has changed.
    """
    from nebula.device.passives import resistor_geometry
    from nebula.rl.contract import ACTION_SPACE

    for name, i in (("rs", 3), ("rl", 5)):
        d = ACTION_SPACE[i]
        assert d.name == name
        for u in np.linspace(0.0, 1.0, 25):
            r = d.to_physical(float(u))
            g = resistor_geometry(r)            # must not raise
            assert abs(g.rel_error) < 1e-3


def test_an_unrealisable_geometry_is_an_invalidity_not_an_exception():
    """`to_geometry` REJECTS rather than clamps (PASSIVES.md §4.3). §8 rule 2
    says the RL loop cannot tolerate exceptions, so the rejection must arrive
    as a named invalidity — even though the test above shows the box itself
    cannot reach one."""
    from nebula.device import passives as P

    class _Boom:
        def __call__(self, *a, **k):
            raise ValueError("no realisable sky130_fd_pr__res_high_po geometry")

    import nebula.rl.evaluator as EV
    orig = EV.to_geometry
    EV.to_geometry = _Boom()
    try:
        b = E.SpiceBudget()
        ev = EV.evaluate(sizing_from_u(np.full(N_ACTIONS, 0.5)), b)
    finally:
        EV.to_geometry = orig
    assert not ev.valid
    assert "unrealisable geometry" in ev.reason
    assert ev.n_spice == 0, "an unbuildable geometry must not cost a SPICE call"
    assert ev.design_id, "even an invalid evaluation needs an id for the log"


def test_the_budget_accumulates():
    b = E.SpiceBudget()
    b.charge(2, 1.5)
    b.charge(1, 0.5)
    assert b.calls == 3 and b.seconds == pytest.approx(2.0)


def test_geometry_tag_is_a_function_of_the_drawn_device():
    a = E.geometry_tag(to_geometry(318.58, 1.9012e-12, 565.03))
    b = E.geometry_tag(to_geometry(318.58, 1.9012e-12, 565.03))
    c = E.geometry_tag(to_geometry(700.00, 1.9012e-12, 565.03))
    assert a == b
    assert a != c


def test_to_geometry_is_electrically_stable_and_GEOMETRICALLY_CHAOTIC():
    """MEASURED, and it changes what `design_id` grouping can be expected to do.

    Near `rs` = 318.6 ohm, a **0.016 % change in the target flips the chosen
    device entirely**:

        318.50 ohm -> w=8     l=6.720   m=1     area  53.8 um^2
        318.55 ohm -> w=10    l=18.780  m=2     area 375.6 um^2
        318.58 ohm -> w=2.85  l=4.445   m=2     area  25.3 um^2
        318.60 ohm -> w=10    l=8.730   m=1     area  87.3 um^2
        319.00 ohm -> w=8     l=14.785  m=2     area 236.6 um^2   <- PASSIVES.md

    Every one lands within 1e-4 relative of its target, so the ELECTRICAL
    answer is stable to four figures. The GEOMETRY is not, because
    `resistor_geometry` scans a width ladder and keeps whichever candidate
    happens to land nearest after `l` is snapped to the 5 nm grid — and which
    one wins is essentially arbitrary at that resolution.

    Two consequences that must not be discovered later:

    1. **`design_id` grouping by geometry is FINE-GRAINED, not coarse.** It is
       still CORRECT — identical geometry gives an identical id — but task 8
       must not expect it to collapse many continuous `rs` values into one
       group. It will not.
    2. **Area is not a stable function of the electrical target.** A 15x area
       spread across a 0.16 % resistance spread means any S7 number quoted for
       a design is a property of the quantiser as much as of the design. That
       matters for `PASSIVES.md` §4.5's 1506 um^2 figure, which is the
       `rs = 319` row above.
    """
    from nebula.device.passives import resistor_geometry

    geoms = {r: resistor_geometry(r) for r in
             (318.50, 318.55, 318.58, 318.60, 318.65, 318.70, 319.00)}
    for r, g in geoms.items():
        assert abs(g.rel_error) < 1e-4, (
            f"{r} ohm realised at {g.r_actual_ohm} — the ELECTRICAL answer "
            f"should be stable even though the geometry is not")
    shapes = {(g.w_um, g.l_um, g.m) for g in geoms.values()}
    assert len(shapes) >= 5, (
        f"expected the geometry choice to be unstable across a 0.16% span; "
        f"got only {len(shapes)} distinct shapes: {sorted(shapes)}. If this "
        f"has become stable, `to_geometry` changed and the design_id grouping "
        f"note above needs re-measuring, not deleting.")
    areas = sorted(g.area_um2 for g in geoms.values())
    assert areas[-1] / areas[0] > 5.0, (
        "the area spread across a 0.16% resistance span was expected to be "
        "large; S7 numbers inherit it")


# ─────────────────────────────────────────────────────────────────────────────
# The real simulator.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not HAVE_NGSPICE, reason="needs ngspice (HANDOFF G20/G33)")
def test_design_432_evaluates_valid_with_drawn_passives():
    from nebula.experiments.rl_smoke import design_432_u

    b = E.SpiceBudget()
    ev = E.evaluate(sizing_from_u(design_432_u()), b)
    assert ev.valid, ev.reason
    assert set(ev.meas) == {"g_dc_db", "peaking_db", "f_peak_oct",
                            "nyq_boost_db", "inoise_vrms", "power_w",
                            "pair_margin_v", "tail_margin_v"}
    assert all(math.isfinite(v) for v in ev.meas.values())
    # The realised passives, not the requested ones — the log must be able to
    # tell a quantisation error from a design move.
    for k in ("rs_actual_ohm", "cs_actual_f", "rl_actual_ohm",
              "f_zero_error_octaves"):
        assert k in ev.raw
    assert b.calls == 1


@pytest.mark.skipif(not HAVE_NGSPICE, reason="needs ngspice (HANDOFF G20/G33)")
def test_the_independent_cross_check_agrees_exactly():
    """§6d. `crosscheck.derived_ac` re-parses the raw text and forms peaking
    from its own `DerivedAc`, so agreement is evidence that the parse AND the
    arithmetic are right — not that one function agrees with itself."""
    from nebula.experiments.rl_smoke import design_432_u

    b = E.SpiceBudget()
    cc = E.cross_check_sample(sizing_from_u(design_432_u()), b)
    assert cc.agrees, cc.detail
    assert b.calls >= 2, "the cross-check re-run must be CHARGED to the budget"


@pytest.mark.skipif(not HAVE_NGSPICE, reason="needs ngspice (HANDOFF G20/G33)")
def test_run_point_keeps_raw_text_only_when_asked():
    from nebula.experiments.rl_smoke import design_432_u

    point, _ = E.build_point(sizing_from_u(design_432_u()))
    assert run_point(point, swing=False).raw_text is None
    assert run_point(point, swing=False, keep_text=True).raw_text
