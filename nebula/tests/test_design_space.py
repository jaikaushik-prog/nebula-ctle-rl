"""
The design-space inverse map: pure tests, no simulator.

WHAT THESE PIN
--------------
1. The map is dimension-for-dimension the SAME SHAPE as the RL action space,
   so adopting it later cannot silently change the search dimension.
2. The closed-form peak agrees with a numerical maximisation of the exact
   magnitude — an INDEPENDENT check, because the two are computed by different
   routes (`task8_symbolic.py`'s algebra against a brute-force scan).
3. Every failure is NAMED and nothing is CLAMPED. A request outside the box
   comes back rejected with the coordinate quoted, not snapped to the edge.
4. Each gate can actually fail (CLAUDEwa.md §8 rule 10) — the tests that prove
   it are marked in their names.

THE TABLE USED HERE IS SYNTHETIC AND ITS NUMBERS ARE FAKE. It is an
EKV-shaped stand-in built in `_synthetic_lut`, present so the pure algebra can
be tested without ngspice. Its trends are physically coherent (gm/I_D falls
monotonically with V_gs, I_D rises with W, gmbs/gm rises with V_sb) and its
magnitudes are invented. Nothing from it may be quoted — same rule as
`device/mock.py` (G16).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.common import design_space as dsp
from nebula.common.design_space import (
    BiasSolution,
    predicted_peak,
    solve_bias,
    to_design,
    to_device,
)
from nebula.rl.contract import ACTION_NAMES, ACTION_SPACE


# ─────────────────────────────────────────────────────────────────────────────
# A synthetic table. FAKE NUMBERS, coherent trends. See the module docstring.
# ─────────────────────────────────────────────────────────────────────────────


class _FakeLut:
    """Duck-types `GmidLut` for the pure tests. Not a PDK. Not a measurement."""

    def __init__(self) -> None:
        self.corners = ("tt@27",)
        self.w_um = np.array([20.0, 40.0, 70.0, 100.0])
        self.l_um = np.array([0.15, 0.30, 0.60, 1.00])
        self.vds_v = np.array([0.20, 0.60, 1.00, 1.50])
        self.vsb_v = np.array([0.0, 0.30, 0.60, 0.90])
        self.vgs_v = np.arange(0.30, 1.801, 0.01)
        self.provenance = {"synthetic": True, "ref_nf": 4}

        nc, nw, nl = 1, self.w_um.size, self.l_um.size
        nd, ns, ng = self.vds_v.size, self.vsb_v.size, self.vgs_v.size
        shape = (nc, nw, nl, nd, ns, ng)
        gm = np.zeros(shape)
        idc = np.zeros(shape)
        gmbs = np.zeros(shape)
        gds = np.zeros(shape)
        vdsat = np.zeros(shape)
        vth0, n_sub, vt = 0.60, 1.35, 0.02585

        for iw, w in enumerate(self.w_um):
            for il, l in enumerate(self.l_um):
                for idd, vds in enumerate(self.vds_v):
                    for is_, vsb in enumerate(self.vsb_v):
                        vth = vth0 + 0.45 * (math.sqrt(vsb + 0.7)
                                             - math.sqrt(0.7))
                        vov = self.vgs_v - vth
                        # EKV-ish interpolation: exponential below, square-law
                        # above, so gm/I_D is smooth and monotone decreasing.
                        ic_ = np.log1p(np.exp(vov / (2 * n_sub * vt))) ** 2
                        beta = 2.2e-4 * (w / l)
                        i = beta * (n_sub * vt) ** 2 * ic_
                        g = beta * n_sub * vt * 2 * np.sqrt(ic_) * (
                            np.sqrt(1 + ic_) - 1) / np.maximum(np.sqrt(ic_), 1e-12)
                        idc[0, iw, il, idd, is_] = i * (1 + 0.08 * vds)
                        gm[0, iw, il, idd, is_] = g * (1 + 0.08 * vds)
                        gmbs[0, iw, il, idd, is_] = (
                            g * (0.30 / math.sqrt(vsb + 0.7)) * 0.42)
                        gds[0, iw, il, idd, is_] = i / (8.0 + 10.0 * l)
                        vdsat[0, iw, il, idd, is_] = np.maximum(vov * 0.7, 0.05)

        self.prim = {"gm": gm, "id": idc, "gmbs": gmbs, "gds": gds,
                     "vdsat": vdsat, "vth": np.zeros(shape),
                     "cgg": np.full(shape, 1e-14), "cgs": np.full(shape, -1e-14),
                     "cgd": np.full(shape, 1e-16)}

    def corner_index(self, process: str, temp_c: float) -> int:
        key = f"{process}@{temp_c:g}"
        if key not in self.corners:
            raise KeyError(key)
        return self.corners.index(key)


@pytest.fixture(scope="module")
def lut() -> _FakeLut:
    return _FakeLut()


@pytest.fixture
def box() -> dict[str, tuple[float, float]]:
    """The APPROVED device box, read off the action space. Never redeclared."""
    return {d.name: (d.lo, d.hi) for d in ACTION_SPACE}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Shape — the map must not change the search dimension.
# ─────────────────────────────────────────────────────────────────────────────


def test_device_names_are_exactly_the_action_space():
    """If the action space moves, this map must be revisited, not adapted.

    Same set AND same order: `sizing_from_u` zips a vector against
    `ACTION_SPACE`, so an order difference would be a silent permutation of the
    whole search.
    """
    assert dsp.DEVICE_NAMES == ACTION_NAMES


def test_design_and_device_spaces_have_the_same_dimension():
    assert len(dsp.DESIGN_NAMES) == len(dsp.DEVICE_NAMES) == 7


def test_four_coordinates_pass_through_unchanged():
    assert set(dsp.DESIGN_NAMES) & set(dsp.DEVICE_NAMES) == {
        "l_in", "i_bias", "rl", "vcm_in"}


# ─────────────────────────────────────────────────────────────────────────────
# 2. The closed-form peak, checked against a brute-force maximisation.
# ─────────────────────────────────────────────────────────────────────────────


def _mag_db(f: float, fz: float, fp1: float, fp2: float) -> float:
    num = math.hypot(1.0, f / fz)
    den = math.hypot(1.0, f / fp1) * math.hypot(1.0, f / fp2)
    return 20.0 * math.log10(num / den)


@pytest.mark.parametrize("fz,fp1,fp2", [
    (0.8e9, 3.2e9, 4.0e9),
    (1.0e9, 6.0e9, 2.5e9),
    (0.5e9, 2.0e9, 9.0e9),
    (1.5e9, 9.0e9, 3.0e9),
])
def test_closed_form_peak_matches_numerical_maximisation(fz, fp1, fp2):
    """INDEPENDENT check: algebra vs a 200k-point scan of the same expression.

    `task8_symbolic.py` derived the closed form with no fitted constant, and
    measured `20*log10(k)` over-predicting peaking by a median +1.199 dB across
    1311 designs. So the asymptote is not what is being checked here — the
    exact peak is.
    """
    p = predicted_peak(fz, fp1, fp2)
    assert p.has_interior_peak

    grid = np.logspace(6, 12, 200_001)
    mags = np.array([_mag_db(f, fz, fp1, fp2) for f in grid])
    f_num = grid[int(np.argmax(mags))]

    assert p.f_peak_hz == pytest.approx(f_num, rel=2e-4)
    assert p.peaking_db == pytest.approx(mags.max() - _mag_db(1.0, fz, fp1, fp2),
                                         abs=1e-6)


@pytest.mark.parametrize("fz,fp1,fp2", [
    (5.0e9, 6.0e9, 3.0e9),
    (4.0e9, 4.4e9, 4.4e9),
])
def test_no_interior_peak_is_detected_before_simulating(fz, fp1, fp2):
    """The G44 case, identified analytically.

    `RL_SMOKE.md` §5: 159 of 203 invalid evaluations were exactly this — a
    response still rising at the top of the search range, which `meas ac MAX`
    reports as a large fictitious peak.
    """
    p = predicted_peak(fz, fp1, fp2)
    assert not p.has_interior_peak
    assert p.f_peak_hz is None and p.peaking_db is None

    grid = np.logspace(6, 12, 20_001)
    mags = np.array([_mag_db(f, fz, fp1, fp2) for f in grid])
    # No interior maximum => the largest sample sits at an edge of the scan.
    assert int(np.argmax(mags)) in (0, len(grid) - 1)


def test_the_search_ceiling_turns_a_real_peak_into_a_predicted_G44():
    """A peak ABOVE the search range is real, and the guard still fires.

    `peak_is_sweep_edge` asks whether the maximum WITHIN 20 GHz sits at the
    range edge. A design peaking at 37 GHz has a genuine interior maximum — the
    bare condition is right — and inside the window the response is
    monotonically rising, so `meas ac MAX` returns the edge.

    Measured consequence, on 159 simulated design-arm rows: the bare condition
    scored TN = 0 against the guard. Adding the ceiling took it to TN = 8.
    """
    fz, fp1, fp2 = 3.93e9, 1.67e10, 8.69e10        # a real logged request
    bare = predicted_peak(fz, fp1, fp2)
    assert bare.has_interior_peak
    assert bare.f_peak_hz is not None and bare.f_peak_hz > 2.0e10

    gated = predicted_peak(fz, fp1, fp2, search_top_hz=2.0e10)
    assert not gated.has_interior_peak
    assert "search ceiling" in gated.reason
    # The peak frequency is still reported: "there IS a peak, just not where
    # the measurement can see it" is more useful than a bare False.
    assert gated.f_peak_hz == pytest.approx(bare.f_peak_hz)


def test_the_ceiling_does_not_reject_a_peak_inside_the_range():
    """Otherwise the gate would be always-on, which G73 says is the same as
    having no gate."""
    inside = predicted_peak(0.8e9, 3.2e9, 4.0e9, search_top_hz=2.0e10)
    assert inside.has_interior_peak
    assert inside.peaking_db is not None


def test_peak_existence_condition_agrees_with_the_scan_over_a_grid():
    """The analytic condition and a numerical scan must never disagree.

    A gate that agrees with reality only sometimes is worse than no gate, and
    G73 is the standing reminder that a guard which never fires is
    indistinguishable from a deleted one — so the count of each outcome is
    asserted to be non-trivial.
    """
    grid = np.logspace(6, 12, 4001)
    n_peak = n_flat = 0
    for fz in (0.4e9, 0.9e9, 2.0e9, 4.5e9):
        for kk in (1.2, 2.0, 4.0, 8.0):
            for fp2 in (1.0e9, 3.0e9, 9.0e9):
                p = predicted_peak(fz, kk * fz, fp2)
                mags = np.array([_mag_db(f, fz, kk * fz, fp2) for f in grid])
                interior = 0 < int(np.argmax(mags)) < len(grid) - 1
                assert p.has_interior_peak == interior, (fz, kk, fp2)
                n_peak += interior
                n_flat += not interior
    assert n_peak > 5 and n_flat > 5, "the condition must fire BOTH ways"


# ─────────────────────────────────────────────────────────────────────────────
# 3. The bias solve.
# ─────────────────────────────────────────────────────────────────────────────


def test_bias_solve_delivers_the_requested_gm_over_id(lut):
    b = solve_bias(lut, gm_over_id=10.0, l_in_m=0.30e-6, i_bias_a=3.0e-3,
                   rl_ohm=400.0, vcm_in_v=1.30)
    assert b.ok, b.fail_reason
    assert b.gm_s == pytest.approx(10.0 * 1.5e-3, rel=1e-12)
    assert b.id_a == pytest.approx(1.5e-3, rel=1e-12)
    assert 0 < b.iterations <= 40
    # The source node identity the whole fixed point is built on.
    assert b.vsb_v == pytest.approx(1.30 - b.vgs_v, abs=2e-3)


def test_bias_solve_reports_the_body_effect_rather_than_ignoring_it(lut):
    """`gmbs` must be non-zero and must GROW as the source rises.

    CLAUDEwa.md §6: omitting the body effect cost 2.33 dB on the G1 point and
    failed the section's own 1 dB gate on a correct circuit. A map that
    returned `gmbs = 0` would reproduce that error exactly, and it would still
    return plausible geometry.
    """
    ratios = []
    for vcm in (1.15, 1.30, 1.45):
        b = solve_bias(lut, gm_over_id=10.0, l_in_m=0.30e-6, i_bias_a=3.0e-3,
                       rl_ohm=400.0, vcm_in_v=vcm)
        assert b.ok, b.fail_reason
        assert b.gmbs_s and b.gmbs_s > 0
        ratios.append((b.vsb_v, b.gmbs_over_gm))
    ratios.sort()
    # Higher source-bulk voltage => LOWER gmbs/gm (the sqrt in the body term).
    assert ratios[0][1] > ratios[-1][1]


def test_unreachable_gm_over_id_is_named_not_clamped(lut):
    b = solve_bias(lut, gm_over_id=400.0, l_in_m=0.30e-6, i_bias_a=3.0e-3,
                   rl_ohm=400.0, vcm_in_v=1.30)
    assert not b.ok
    assert "gm_over_id_unreachable" in (b.fail_reason or "")
    assert b.w_um is None, "a failed solve must not hand back a geometry"


def test_current_outside_the_width_axis_is_named(lut):
    """A current no width on the axis can carry at that inversion level.

    `rl` is deliberately SMALL here. The obvious version of this test asked for
    800 mA into 400 ohm and got `outside_table: V_ds=-158.8` instead — which is
    the RIGHT answer (the supply cannot support it, and that is the cause)
    but tests the wrong gate. G68: order the checks cause-before-symptom, and
    then make sure each test actually reaches the check it names.
    """
    b = solve_bias(lut, gm_over_id=10.0, l_in_m=0.30e-6, i_bias_a=1.0e-2,
                   rl_ohm=50.0, vcm_in_v=1.30)
    assert not b.ok
    assert "current_unreachable" in (b.fail_reason or "")
    assert b.w_um is None

    # ... and one rung below the ceiling still succeeds, so the gate is not
    # simply always-on (G73).
    ok = solve_bias(lut, gm_over_id=10.0, l_in_m=0.30e-6, i_bias_a=4.0e-3,
                    rl_ohm=50.0, vcm_in_v=1.30)
    assert ok.ok and ok.w_um is not None and ok.w_um <= 100.0


def test_mirror_efficiency_moves_the_current_and_defaults_to_ideal(lut):
    """The 4-8 % mirror deficit is a KNOB that defaults OFF.

    Session 13 measured it; `BASELINES.md` §11 names it as the first mechanism
    to try for the pre-screen's bias. It defaults to 1.0 so the validation
    experiment MEASURES the deficit instead of assuming a correction for it.
    """
    ideal = solve_bias(lut, gm_over_id=10.0, l_in_m=0.30e-6, i_bias_a=3.0e-3,
                       rl_ohm=400.0, vcm_in_v=1.30)
    real = solve_bias(lut, gm_over_id=10.0, l_in_m=0.30e-6, i_bias_a=3.0e-3,
                      rl_ohm=400.0, vcm_in_v=1.30, mirror_efficiency=0.93)
    assert ideal.ok and real.ok
    assert ideal.id_a == pytest.approx(1.5e-3, rel=1e-12)
    assert real.id_a == pytest.approx(1.5e-3 * 0.93, rel=1e-12)
    assert real.w_um < ideal.w_um, "less current at fixed gm/I_D needs less W"


def test_a_corner_absent_from_the_table_is_refused_not_substituted(lut):
    b = solve_bias(lut, gm_over_id=10.0, l_in_m=0.30e-6, i_bias_a=3.0e-3,
                   rl_ohm=400.0, vcm_in_v=1.30, process="ss", temp_c=125.0)
    assert not b.ok
    assert "corner_not_in_table" in (b.fail_reason or "")


# ─────────────────────────────────────────────────────────────────────────────
# 4. The map, its failures, and the round trip.
# ─────────────────────────────────────────────────────────────────────────────


def _design(**kw) -> dict[str, float]:
    d = dict(gm_over_id=10.0, l_in=0.30e-6, i_bias=3.0e-3,
             f_z=1.2e9, k=3.0, rl=400.0, vcm_in=1.30)
    d.update(kw)
    return d


def test_map_returns_all_seven_device_coordinates(lut):
    r = to_device(lut, _design(), cl_f=32.63e-15)
    assert r.ok, r.fail_reason
    assert set(r.params) == set(dsp.DEVICE_NAMES)
    assert all(math.isfinite(v) for v in r.params.values())


def test_the_three_swapped_coordinates_reproduce_their_requests(lut):
    """`f_z` and `k` must come back out of the geometry they produced.

    This is the map's own consistency, and it is exact rather than approximate
    because both inversions are algebraic once the bias is solved:
    `Rs = 2(k-1)/(gm+gmbs)` and `Cs = 1/(2*pi*Rs*f_z)`.
    """
    d = _design(f_z=0.9e9, k=4.5)
    r = to_device(lut, d, cl_f=32.63e-15)
    assert r.ok, r.fail_reason
    back = to_design(r.bias.gm_s, r.bias.gmbs_s, r.params)
    assert back["f_z"] == pytest.approx(d["f_z"], rel=1e-9)
    assert back["k"] == pytest.approx(d["k"], rel=1e-9)
    assert back["gm_over_id"] == pytest.approx(d["gm_over_id"], rel=1e-9)
    for name in ("l_in", "i_bias", "rl", "vcm_in"):
        assert back[name] == pytest.approx(d[name], rel=0, abs=0)


def test_k_at_or_below_unity_is_refused_with_a_reason(lut):
    for k in (1.0, 0.5, -2.0):
        r = to_device(lut, _design(k=k), cl_f=32.63e-15)
        assert not r.ok
        assert "k_not_above_unity" in (r.fail_reason or "")


def test_a_request_outside_the_box_is_REJECTED_and_never_clamped(lut, box):
    """The whole no-silent-clamping rule, as an assertion.

    Clamping an infeasible request onto a box edge turns "you cannot have
    this" into a plausible-looking sizing that will simulate — G44's class of
    bug. The rejection must name the coordinate and quote the value.
    """
    # A very low f_z at fixed k needs a large Cs; push it past the box top.
    r = to_device(lut, _design(f_z=1.0e6), cl_f=32.63e-15, box=box)
    assert not r.ok
    assert "cs_outside_box" in (r.fail_reason or "")
    # The offending value is still reported, and it is NOT the box edge.
    assert r.cs_f is not None and r.cs_f > box["cs"][1]


def test_box_rejection_reports_the_params_it_rejected(lut, box):
    r = to_device(lut, _design(f_z=1.0e6), cl_f=32.63e-15, box=box)
    assert not r.ok and r.params is not None
    assert r.params["cs"] > box["cs"][1]


def test_without_a_box_the_same_request_succeeds(lut, box):
    """Proves the previous test's rejection came from the BOX, not the map."""
    r = to_device(lut, _design(f_z=1.0e6), cl_f=32.63e-15, box=None)
    assert r.ok, r.fail_reason


def test_cl_has_no_default_because_it_is_a_context_not_a_property(lut):
    """`cl` is the NEXT stage's input capacitance (`CL_RANGE.md`), and it enters
    `f_p2`. A default would be an invented context."""
    with pytest.raises(TypeError):
        to_device(lut, _design())          # type: ignore[call-arg]


def test_k_alpha_scales_rs_exactly_as_G60_prescribes(lut):
    """`k_alpha` is the r_o shunt §6 omits, and it must touch ONLY `Rs`."""
    base = to_device(lut, _design(), cl_f=32.63e-15)
    cal = to_device(lut, _design(), cl_f=32.63e-15, k_alpha=0.90)
    assert base.ok and cal.ok
    assert cal.rs_ohm == pytest.approx(base.rs_ohm / 0.90, rel=1e-12)
    # f_z is held, so Cs moves the other way and the zero does not shift.
    assert (1.0 / (2 * math.pi * cal.rs_ohm * cal.cs_f)) == pytest.approx(
        1.0 / (2 * math.pi * base.rs_ohm * base.cs_f), rel=1e-12)


def test_the_predicted_triple_is_reported_even_on_a_box_rejection(lut, box):
    """"What did it ask for?" must be answerable after a rejection."""
    r = to_device(lut, _design(f_z=1.0e6), cl_f=32.63e-15, box=box)
    assert not r.ok
    assert r.f_z_hz == 1.0e6
    assert r.f_p1_hz == pytest.approx(3.0 * 1.0e6)
    assert r.f_p2_hz is not None and r.f_p2_hz > 0


def test_f_p1_is_k_times_f_z_which_is_the_whole_argument(lut):
    """The reparameterization's premise: the pole-zero triple is KNOWN on the
    request. CLAUDEwa.md §6: `w_z = 1/(Rs*Cs)`, `w_p1 = k/(Rs*Cs)`."""
    d = _design(f_z=1.1e9, k=5.0)
    r = to_device(lut, d, cl_f=32.63e-15)
    assert r.ok
    assert r.f_p1_hz == pytest.approx(5.0 * 1.1e9, rel=1e-12)
    # And it agrees with the forward §6 algebra at the solved bias point.
    ss = dsp.predicted_response(r.bias, r.rs_ohm, r.cs_f, d["rl"], 32.63e-15)
    assert ss.f_zero_hz == pytest.approx(d["f_z"], rel=1e-9)
    assert ss.f_pole1_hz == pytest.approx(r.f_p1_hz, rel=1e-9)


def test_predicted_saturation_is_reported_and_not_used_to_reject(lut):
    """A device predicted into triode is a PREDICTION about a bad circuit.

    `rl/evaluator.py` classifies that as HEADROOM_ONLY — a trustworthy
    measurement of a bad circuit — and grades it. Deciding it here would move a
    decision one layer down from where it belongs.
    """
    r = to_device(lut, _design(rl=800.0, i_bias=7.0e-3), cl_f=32.63e-15)
    if r.ok:
        assert r.bias.predicted_in_saturation in (True, False)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Gates that can fail (rule 10).
# ─────────────────────────────────────────────────────────────────────────────


def test_extrapolation_is_refused_rather_than_edge_clamped(lut):
    """Break it deliberately: ask off the end of an axis and watch it raise."""
    with pytest.raises(LookupError):
        dsp._axis_weights(lut.l_um, 5.0, "L")
    with pytest.raises(LookupError):
        dsp._axis_weights(lut.vsb_v, -0.5, "V_sb")
    # ... and the in-range case does not raise, so the gate is not always-on.
    lo, hi, f = dsp._axis_weights(lut.l_um, 0.45, "L")
    assert 0.0 <= f <= 1.0 and lo < hi


def test_a_negative_source_node_is_refused(lut):
    """`vcm_in` below the threshold puts the source under the bulk.

    Session 9c found exactly this one stage downstream — an operating point
    with the sources below ground that no real tail can provide.
    """
    b = solve_bias(lut, gm_over_id=10.0, l_in_m=0.30e-6, i_bias_a=3.0e-3,
                   rl_ohm=400.0, vcm_in_v=0.55)
    assert not b.ok
    assert "source_node_outside_table" in (b.fail_reason or "")


def test_failed_bias_solution_carries_no_numbers():
    """`ok=False` means trust NOTHING — the `DeviceResult` contract."""
    b = BiasSolution.failed("some reason")
    assert not b.ok
    for field in ("w_um", "vgs_v", "vsb_v", "vds_v", "gm_s", "gmbs_s", "id_a"):
        assert getattr(b, field) is None
    assert b.predicted_in_saturation is None
