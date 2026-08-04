"""
Tests for device/sky130_runner.py and experiments/s3_yield.py.

Two groups. The first needs no simulator: it pins the arithmetic that a wrong
answer would sail straight through — the two unit conversions in
`SizingPoint.from_params`, the peak-vs-peak-to-peak factor in the swing
ceiling, and the coupling-factor statistic. The second runs ngspice and skips
cleanly when it or the PDK is absent.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.device.sky130_runner import (
    NFET_01V8,
    SizingPoint,
    swing_limits,
    textbook_swing_pp_v,
)
from nebula.experiments.s3_yield import (
    PROPOSED_BOX,
    UNDERIVABLE,
    Row,
    YieldStat,
    headroom_ok_1v8,
    sample_box,
    scale_box,
    summarize,
)

# ─────────────────────────────────────────────────────────────────────────────
# Unit conversions. HANDOFF failure mode 2: each of these is a factor of 2 to
# 1e6 that still simulates happily.
# ─────────────────────────────────────────────────────────────────────────────


def test_from_params_converts_metres_to_microns():
    """BOUNDS carries SI metres; the netlist wants plain microns (G31)."""
    p = SizingPoint.from_params(dict(
        w_in=40e-6, l_in=0.15e-6, nf_in=4, i_bias=3.0e-3,
        rs=200, cs=1.6e-12, rl=400, cl=100e-15, vcm_in=1.25))
    assert p.w == pytest.approx(40.0)
    assert p.l == pytest.approx(0.15)


def test_from_params_halves_i_bias_across_the_two_sinks():
    """`i_bias` is TOTAL; the topology has one ideal sink per side."""
    p = SizingPoint.from_params(dict(
        w_in=40e-6, l_in=0.15e-6, nf_in=4, i_bias=3.0e-3,
        rs=200, cs=1.6e-12, rl=400, cl=100e-15, vcm_in=1.25))
    assert p.i_tail_per_side_a == pytest.approx(1.5e-3)
    assert p.i_total_a == pytest.approx(3.0e-3)
    assert p.power_w == pytest.approx(1.8 * 3.0e-3)


def test_from_params_rejects_missing_keys():
    with pytest.raises(KeyError):
        SizingPoint.from_params(dict(w_in=40e-6))


def test_textbook_swing_is_four_i_rl_not_two():
    """The peak-vs-peak-to-peak factor that session 9c lost.

    Full steering puts `2*I*RL` across the load in EACH polarity, so the
    differential output spans `+/- 2*I*RL` and the peak-to-PEAK figure is
    `4*I*RL`. Session 9c compared required swing against `2*I*RL` read as a
    peak-to-peak number, understating the ceiling by exactly 2x.
    """
    assert textbook_swing_pp_v(1.5e-3, 400) == pytest.approx(2.4)
    assert textbook_swing_pp_v(1.5e-3, 400) == pytest.approx(
        2.0 * 2.0 * 1.5e-3 * 400)


# ─────────────────────────────────────────────────────────────────────────────
# Swing extraction.
# ─────────────────────────────────────────────────────────────────────────────


def _tanh_curve(gain=1.789, vsat=1.14, n=801, span=0.8):
    """A synthetic differential pair transfer curve with a known 1 dB point.

    `vod = -vsat * tanh(gain * vid / vsat)` has small-signal slope `-gain` and
    saturates at `vsat`, so the compression point is analytic. Incremental
    gain is `gain * sech^2(x)` with `x = gain*vid/vsat`, so `c` dB of GAIN
    compression is `sech^2(x) = 10^(-c/20)` — a voltage ratio, hence /20 —
    and `|vod| = vsat * tanh(x) = vsat * sqrt(1 - 10^(-c/20))`.
    """
    vid = np.linspace(-span, span, n)
    vod = -vsat * np.tanh(gain * vid / vsat)
    return vid, vod


def test_swing_limits_finds_the_analytic_1db_point():
    gain, vsat = 1.789, 1.14
    vid, vod = _tanh_curve(gain, vsat)
    lim = swing_limits(vid, vod, compression_db=1.0)

    assert lim.g_dc_v_per_v == pytest.approx(gain, rel=2e-3)
    expected_pp = 2.0 * vsat * math.sqrt(1.0 - 10 ** (-1.0 / 20.0))
    assert lim.linear_pp_v == pytest.approx(expected_pp, rel=0.02)


def test_swing_limits_uses_magnitude_so_an_inverting_stage_works():
    """The stage inverts. A signed gradient would make every limit vanish."""
    vid, vod = _tanh_curve()
    assert swing_limits(vid, vod).linear_pp_v is not None
    assert swing_limits(vid, -vod).linear_pp_v == pytest.approx(
        swing_limits(vid, vod).linear_pp_v)


def test_swing_limits_returns_none_when_compression_is_not_reached():
    """A limit that was never reached is None, never a fallback to 4*I*RL.

    Substituting a computed ceiling for an unmeasured linear limit is exactly
    the substitution this module exists to prevent.
    """
    vid = np.linspace(-0.05, 0.05, 201)
    vod = -1.789 * vid                       # perfectly linear over the sweep
    assert swing_limits(vid, vod).linear_pp_v is None


def test_swing_limits_scans_outward_from_zero():
    """A fold-back at large drive must not be reported as the limit the
    signal meets first."""
    vid, vod = _tanh_curve()
    lim = swing_limits(vid, vod)
    assert lim.linear_pp_v < lim.max_swept_pp_v


def test_swing_limits_rejects_a_degenerate_curve():
    with pytest.raises(ValueError):
        swing_limits(np.array([0.0, 1.0]), np.array([0.0, 1.0]))


def test_saturation_and_steering_limits_are_reported_separately():
    vid, vod = _tanh_curve()
    sat_ok = np.abs(vid) < 0.5
    id_min = np.maximum(1.5e-3 * (1.0 - np.abs(vid) / 0.7), 0.0)
    lim = swing_limits(vid, vod, sat_ok=sat_ok, id_min=id_min, i_ref_a=1.5e-3)
    assert lim.saturation_pp_v is not None
    assert lim.steering_pp_v is not None
    # saturation is violated at |vid| = 0.5, steering at |vid| = 0.665
    assert lim.saturation_pp_v < lim.steering_pp_v


# ─────────────────────────────────────────────────────────────────────────────
# The proposed box and the coupling statistic.
# ─────────────────────────────────────────────────────────────────────────────


def test_proposed_box_has_provenance_on_every_bound():
    for name, (lo, hi, _log, prov) in PROPOSED_BOX.items():
        assert lo < hi, name
        assert len(prov) > 40, f"{name} has no real provenance"


def test_tail_parameters_are_absent_and_say_why():
    """Rule 6 forbids inventing ranges for a device that does not exist yet."""
    for name in ("w_tail", "l_tail", "nf_tail"):
        assert name not in PROPOSED_BOX
        assert name in UNDERIVABLE


def test_scale_box_widens_and_narrows_about_the_centre():
    wide = scale_box(PROPOSED_BOX, 1.5)
    narrow = scale_box(PROPOSED_BOX, 0.6)
    lo, hi, *_ = PROPOSED_BOX["rs"]
    wlo, whi, *_ = wide["rs"]
    nlo, nhi, *_ = narrow["rs"]
    assert wlo < lo and whi > hi
    assert nlo > lo and nhi < hi
    # log-scaled: the geometric centre is preserved
    assert math.sqrt(wlo * whi) == pytest.approx(math.sqrt(lo * hi), rel=1e-9)


def test_scale_box_never_proposes_a_width_outside_the_sky130_bins():
    """W above 100 um has no model card; L below 0.15 um has no bin."""
    wide = scale_box(PROPOSED_BOX, 3.0)
    assert wide["w_in"][1] <= 100e-6
    assert wide["l_in"][0] >= 0.15e-6
    assert wide["nf_in"][0] >= 1.0


def test_sample_box_is_inside_the_box_and_reproducible():
    a = sample_box(PROPOSED_BOX, 32, seed=7)
    b = sample_box(PROPOSED_BOX, 32, seed=7)
    assert a == b
    for row in a:
        for name, v in row.items():
            lo, hi, *_ = PROPOSED_BOX[name]
            assert lo - 1e-12 <= v <= hi + 1e-12, f"{name}={v}"


def test_headroom_rejects_a_jointly_infeasible_pair():
    base = dict(i_bias=1e-3, rl=100, vcm_in=1.25)
    assert headroom_ok_1v8(base) is None
    # 8 mA total through 800 ohm drops 3.2 V into a 1.8 V rail
    assert headroom_ok_1v8({**base, "i_bias": 8e-3, "rl": 800}) is not None
    assert headroom_ok_1v8({**base, "vcm_in": 1.9}) is not None


def _row(peak, fpk, nyq=1.0):
    return Row(ok=True, peaking_db=peak, f_pk_hz=fpk, nyquist_boost_db=nyq,
               vn_in_vrms=2e-4, power_w=5e-3, in_saturation=True, params={})


def test_coupling_factor_is_one_for_independent_conditions():
    """The statistic must report 1.0 when nothing is coupled — otherwise a
    coupling claim built on it means nothing."""
    rows = []
    for a in (True, False):
        for b in (True, False):
            for _ in range(25):     # a perfect 2x2 product distribution
                rows.append(_row(6.0 if a else 20.0,
                                 2.0e9 if b else 0.5e9))
    stat = summarize(rows)
    assert stat.p_a == pytest.approx(0.5)
    assert stat.p_b == pytest.approx(0.5)
    assert stat.coupling_factor == pytest.approx(1.0)


def test_coupling_factor_exceeds_one_when_conditions_conflict():
    """Adverse coupling = the joint falls below the product."""
    rows = ([_row(6.0, 0.5e9) for _ in range(50)]        # A only
            + [_row(20.0, 2.0e9) for _ in range(50)]     # B only
            + [_row(6.0, 2.0e9) for _ in range(2)])      # both, rarely
    stat = summarize(rows)
    assert stat.coupling_factor > 5.0


def test_yield_stat_survives_a_round_trip_through_json():
    from dataclasses import asdict
    stat = summarize([_row(6.0, 2.0e9), _row(20.0, 0.5e9)])
    assert YieldStat(**asdict(stat)).coupling_factor == pytest.approx(
        stat.coupling_factor)


def test_summarize_raises_rather_than_reporting_a_dead_box():
    with pytest.raises(RuntimeError):
        summarize([Row(ok=False, reason="x")])


# ─────────────────────────────────────────────────────────────────────────────
# Simulator-backed. Skips cleanly without ngspice or the PDK.
# ─────────────────────────────────────────────────────────────────────────────


def _have_sim() -> bool:
    from nebula.device.ngspice_runner import _DEFAULT_NGSPICE
    from nebula.device.sky130_runner import TRIMMED_LIB
    import shutil
    ng = _DEFAULT_NGSPICE.exists() or shutil.which("ngspice_con") is not None
    return ng and TRIMMED_LIB.exists()


needs_sim = pytest.mark.skipif(not _have_sim(), reason="ngspice or SKY130 absent")


@needs_sim
def test_corrected_g1_reference_point_reproduces():
    """Pins the session 9c corrected bias against the simulator.

    W=40 nf=4 L=0.15, 1.5 mA/side, VCM=1.25, VDD=1.8 -> gm 12.62 mS,
    gm/I_D 8.42, v(s1) +0.343 V. If this moves, the bounds below it moved too.
    """
    from nebula.device.sky130_runner import run_point

    p = SizingPoint(w=40, l=0.15, nf=4, rs=200, cs=1.6e-12, rl=400,
                    cl=100e-15, i_tail_per_side_a=1.5e-3, vcm=1.25, vdd=1.8)
    r = run_point(p, swing=False)
    assert r.ok, r.fail_reason
    assert r.gm == pytest.approx(12.62e-3, rel=0.01)
    assert r.gm_over_id == pytest.approx(8.42, rel=0.01)
    assert r.v_src_dc == pytest.approx(0.343, abs=0.005)
    assert r.in_saturation
    assert r.g_dc_db == pytest.approx(5.05, abs=0.05)
    assert r.peaking_db == pytest.approx(4.63, abs=0.05)
    assert 1.9e9 < r.f_pk_hz < 2.1e9
    assert p.device == NFET_01V8


@needs_sim
def test_measured_swing_is_larger_than_session_9c_assumed():
    """The correction that changes the compression conclusion.

    Session 9c used "available differential swing = 2*IT*RL = 1.2 Vpp" at
    IT = 1.5 mA, RL = 400. Measured at the same point: the 1 dB linear swing
    is ~1.43 Vpp and the hard ceiling ~2.28 Vpp. Both exceed 1.2 Vpp, so the
    compression verdict drawn against that number was too pessimistic.
    """
    from nebula.device.sky130_runner import run_point

    p = SizingPoint(w=40, l=0.15, nf=4, rs=200, cs=1.6e-12, rl=400,
                    cl=100e-15, i_tail_per_side_a=1.5e-3, vcm=1.25, vdd=1.8)
    r = run_point(p, swing=True)
    assert r.ok, r.fail_reason
    lim = r.swing()
    assert lim.linear_pp_v == pytest.approx(1.43, abs=0.05)
    assert lim.linear_pp_v > 1.2
    assert lim.steering_pp_v == pytest.approx(2.28, abs=0.05)
    # and the limit is steering, not headroom: the pair is still saturated
    # well past the 1 dB point.
    assert lim.saturation_pp_v > lim.linear_pp_v


@needs_sim
def test_nf_does_not_multiply_width_on_sky130():
    """`nf` splits W into fingers; it is NOT a width multiplier.

    The 1.2 V bound's provenance claimed "1-32 multiplies effective W", which
    is true of the generic-BSIM4 netlist (`m={NF}`) and false of the PDK
    subckt. Measured: gm moves by ~10%, non-monotonically, over nf 1..32.
    """
    from nebula.device.sky130_runner import run_point

    def gm_at(nf):
        p = SizingPoint(w=40, l=0.15, nf=nf, rs=200, cs=1.6e-12, rl=400,
                        cl=100e-15, i_tail_per_side_a=1.5e-3, vcm=1.25, vdd=1.8)
        r = run_point(p, swing=False)
        assert r.ok, r.fail_reason
        return r.gm

    gms = {nf: gm_at(nf) for nf in (1, 4, 32)}
    # a width multiplier would give gm(32)/gm(1) of order 32, not order 1
    assert 0.7 < gms[32] / gms[1] < 1.0
    assert abs(gms[4] / gms[1] - 1.0) < 0.2
