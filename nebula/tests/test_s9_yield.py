"""
Tests for experiments/s9_yield.py.

All of these run WITHOUT a simulator. The corner sweep itself is expensive and
is exercised by running it; what is pinned here is the arithmetic and the
assumption-plumbing around it, which is where a wrong answer would be
invisible: a VDD scale applied to the wrong thing, a two-sided spec scored on
the wrong side, or a "which spec failed" ranking that picks the least-violated
constraint instead of the worst.
"""

from __future__ import annotations

import pytest

from nebula.common.types import (
    SPEC_F_PEAK_HZ_RANGE,
    SPEC_PEAKING_DB_RANGE,
    SPEC_POWER_MAX_W,
    SPEC_VN_IN_MAX_VRMS,
    Corner,
    all_corners,
)
from nebula.device.sky130_runner import Sky130Point
from nebula.experiments.s9_yield import (
    CL_FIXED_F,
    NOMINAL_VDD,
    SCREEN_CORNERS,
    TAIL_IS_IDEAL,
    UNSCREENED_SPECS,
    VCM_TRACKS_VDD,
    CornerResult,
    SpecCheck,
    _range_check,
    _shortfall_max,
    _shortfall_min,
    _worst,
    assumptions_header,
    check_specs,
    first_fail_table,
    point_at_corner,
    screen_augmentation,
)

BASE = dict(w_in=40e-6, l_in=0.15e-6, nf_in=4, i_bias=3.0e-3,
            rs=200, cs=1.6e-12, rl=400, cl=150e-15, vcm_in=1.25)


def _sky(peaking=6.0, f_pk=2.0e9, noise=2e-4, vds=1.0, vdsat=0.1, nyq=1.0):
    """A Sky130Point with the derived properties check_specs() reads."""
    return Sky130Point(ok=True, g_dc_db=0.0, g_pk_db=peaking,
                       g_nyq_db=nyq, g_top_db=-10.0, f_pk_hz=f_pk,
                       vn_in_vrms=noise, vds=vds, vdsat=vdsat)


# ─────────────────────────────────────────────────────────────────────────────
# The three assumptions. Each is a decision, so each gets a test that would go
# red if someone changed it silently.
# ─────────────────────────────────────────────────────────────────────────────


def test_cl_is_pinned_at_the_documented_value():
    assert CL_FIXED_F == 150e-15


def test_the_three_assumptions_are_all_stated_in_the_printed_header():
    """The header is the only thing a reader of the output sees. If an
    assumption is not in it, it is not disclosed."""
    h = assumptions_header(2000, 1)
    assert "ASSUMPTION" in h
    assert "150 fF" in h
    assert "IDEAL CURRENT SINKS" in h
    assert "UNDERSTATEMENT" in h        # the tail caveat, in the strong form
    assert "VCM held CONSTANT" in h
    for spec in UNSCREENED_SPECS:
        assert spec.split()[0] in h     # S4, S7, S8 each named


def test_header_is_pure_ascii():
    """G10: the Windows console is cp1252 and a stray glyph crashes the run
    under redirection -- which is exactly how this output gets captured."""
    assumptions_header(2000, 1).encode("ascii")


def test_tail_ideal_flag_is_true_and_therefore_results_are_optimistic():
    """If a tail transistor is ever added, this flips and the caveat in the
    header must come out with it. The test exists to force that pairing."""
    assert TAIL_IS_IDEAL is True
    assert "OPTIMISTIC" in assumptions_header(1, 1)


# ─────────────────────────────────────────────────────────────────────────────
# VDD scaling -- the S9 axis that is NOT in the .lib section.
# ─────────────────────────────────────────────────────────────────────────────


def test_vdd_scales_with_the_corner():
    hi = point_at_corner(BASE, Corner("tt", 1.05, 27.0))
    lo = point_at_corner(BASE, Corner("tt", 0.95, 27.0))
    assert hi.vdd == pytest.approx(NOMINAL_VDD * 1.05)
    assert lo.vdd == pytest.approx(NOMINAL_VDD * 0.95)


def test_power_follows_the_scaled_rail():
    """S6 is evaluated at the corner's supply, not the nominal one. Missing
    this makes every FF/1.05 power number 5% optimistic."""
    hi = point_at_corner(BASE, Corner("tt", 1.05, 27.0))
    assert hi.power_w == pytest.approx(NOMINAL_VDD * 1.05 * 3.0e-3)


def test_vcm_does_not_track_vdd_by_default():
    """The documented assumption, pinned so it cannot drift silently."""
    assert VCM_TRACKS_VDD is False
    for scale in (0.95, 1.00, 1.05):
        p = point_at_corner(BASE, Corner("tt", scale, 27.0))
        assert p.vcm == pytest.approx(BASE["vcm_in"])


def test_point_at_corner_does_not_mutate_the_caller_dict():
    before = dict(BASE)
    point_at_corner(BASE, Corner("tt", 1.05, 27.0))
    assert BASE == before


# ─────────────────────────────────────────────────────────────────────────────
# Shortfall arithmetic (CLAUDEwa section 9).
# ─────────────────────────────────────────────────────────────────────────────


def test_shortfall_saturates_at_zero_when_a_spec_is_met():
    """Section 9: no bonus for exceeding a spec, or a met spec could pay for
    an unmet one."""
    assert _shortfall_min(10.0, 5.0) == 0.0
    assert _shortfall_max(1.0, 5.0) == 0.0


def test_shortfall_is_negative_and_ordered_by_severity():
    mild = _shortfall_max(6.0, 5.0)
    bad = _shortfall_max(50.0, 5.0)
    assert bad < mild < 0.0


def test_range_check_scores_the_worse_side():
    lo, hi = 3.0, 12.0
    under = _range_check("x", 1.0, lo, hi, "dB")
    over = _range_check("x", 30.0, lo, hi, "dB")
    inside = _range_check("x", 6.0, lo, hi, "dB")
    assert not under.ok and not over.ok and inside.ok
    assert inside.shortfall == 0.0
    assert under.shortfall < 0.0 and over.shortfall < 0.0


def test_section9_normaliser_compresses_large_overshoots_ASYMMETRY():
    """A KNOWN DEFECT OF THE SECTION 9 FORM, pinned here because it biases the
    'which spec fails first' ranking and a reader must be told.

    The normaliser is (|x| + |tau|), whose denominator GROWS with x, so a large
    overshoot scores less badly than a small undershoot:

        2 dB BELOW the 3 dB floor    -> (1-3)/(1+3)   = -0.500
        18 dB ABOVE the 12 dB ceiling -> (12-30)/(30+12) = -0.429

    Being 2 dB out therefore outranks being 18 dB out. Session 6 recorded the
    same asymmetry for the S3 reward-match terms; this is that property showing
    up in the corner report. It is inherent to CLAUDEwa section 9, which is the
    contract, so it is NOT fixed here -- ranking stays reward-consistent on
    purpose. The mitigation is that every check also carries its margin in
    natural units, so the magnitude is visible even when the rank is not.
    """
    under = _range_check("x", 1.0, 3.0, 12.0, "dB")
    over = _range_check("x", 30.0, 3.0, 12.0, "dB")
    assert under.shortfall == pytest.approx(-0.5)
    assert over.shortfall == pytest.approx(-18.0 / 42.0)
    assert under.shortfall < over.shortfall          # the counter-intuitive bit
    assert abs(over.margin) > abs(under.margin)      # while the margin is honest


def test_range_check_margin_is_distance_to_the_nearer_edge():
    c = _range_check("x", 4.0, 3.0, 12.0, "dB")
    assert c.margin == pytest.approx(1.0)        # 1 dB above the floor
    c = _range_check("x", 11.0, 3.0, 12.0, "dB")
    assert c.margin == pytest.approx(1.0)        # 1 dB below the ceiling


def test_range_check_applies_the_display_scale_to_value_and_margin():
    """f_peak is reported in GHz but compared in Hz. A scale applied to one
    and not the other produces a margin nine orders of magnitude wrong."""
    c = _range_check("f", 2.0e9, 1.25e9, 2.5e9, "GHz", scale=1e-9)
    assert c.value == pytest.approx(2.0)
    assert c.margin == pytest.approx(0.5)


# ─────────────────────────────────────────────────────────────────────────────
# "Which spec fails first" -- the headline output.
# ─────────────────────────────────────────────────────────────────────────────


def test_worst_picks_the_most_violated_not_the_first_listed():
    checks = [
        SpecCheck("mild", False, 1.0, -0.1, "dB", -0.02),
        SpecCheck("severe", False, 1.0, -9.0, "dB", -0.80),
        SpecCheck("met", True, 1.0, 5.0, "dB", 0.0),
    ]
    assert _worst(checks).name == "severe"


def test_worst_returns_none_when_everything_is_met():
    assert _worst([SpecCheck("a", True, 1.0, 1.0, "dB", 0.0)]) is None


def test_all_specs_met_design_scores_clean():
    checks = check_specs(_sky(), power_w=5e-3)
    assert all(c.ok for c in checks), [c.name for c in checks if not c.ok]
    assert _worst(checks) is None


def test_a_noise_failure_is_named_and_quantified():
    checks = check_specs(_sky(noise=3.0e-3), power_w=5e-3)
    w = _worst(checks)
    assert w.name == "S5_noise"
    assert w.value == pytest.approx(3.0)                  # mV
    assert w.margin == pytest.approx((SPEC_VN_IN_MAX_VRMS - 3.0e-3) * 1e3)
    assert w.margin < 0                                    # failed, by 1.5 mV


def test_a_power_failure_is_named_and_quantified():
    w = _worst(check_specs(_sky(), power_w=20e-3))
    assert w.name == "S6_power"
    assert w.value == pytest.approx(20.0)
    assert w.margin == pytest.approx((SPEC_POWER_MAX_W - 20e-3) * 1e3)


def test_leaving_saturation_is_reported_as_its_own_failure():
    """Not an S3-S8 spec, but outside saturation the small-signal numbers
    describe a circuit that is not amplifying -- it must be nameable."""
    w = _worst(check_specs(_sky(vds=0.05, vdsat=0.20), power_w=5e-3))
    assert w.name == "saturation"


def test_the_two_s3_readings_are_scored_separately():
    """CLAUDEwa section 3 requires BOTH peak-to-DC and Nyquist boost."""
    names = {c.name for c in check_specs(_sky(), power_w=5e-3)}
    assert {"S3_peaking", "S3_f_peak", "S3_nyq_boost"} <= names


def test_negative_nyquist_boost_fails_even_when_peaking_is_in_band():
    """The reading-(a)-passes / reading-(b)-fails case: 3.82 dB of peaking at
    724 MHz, below its own DC gain where the data is."""
    checks = check_specs(_sky(peaking=3.82, f_pk=724e6, nyq=-0.99), power_w=5e-3)
    by = {c.name: c for c in checks}
    assert by["S3_peaking"].ok is True
    assert by["S3_f_peak"].ok is False
    assert by["S3_nyq_boost"].ok is False


def test_first_fail_table_handles_an_all_passing_population():
    assert "(none)" in first_fail_table([], "empty")


# ─────────────────────────────────────────────────────────────────────────────
# Corner set.
# ─────────────────────────────────────────────────────────────────────────────


def test_screen_corners_are_real_members_of_the_45():
    """The promotion stage re-runs the screen corners as a consistency check;
    that only works if they are genuinely in the 45."""
    assert set(SCREEN_CORNERS) <= set(all_corners())


def test_screen_corners_are_the_requested_three():
    assert SCREEN_CORNERS == (
        Corner("ss", 0.95, 125.0),
        Corner("ff", 1.05, 0.0),
        Corner("ss", 0.95, 0.0),
    )


def test_there_are_45_corners():
    assert len(all_corners()) == 45


# ─────────────────────────────────────────────────────────────────────────────
# The screen can only be wrong in one direction, and this is the bookkeeping
# that says which corner would have fixed it.
# ─────────────────────────────────────────────────────────────────────────────


def _cr(corner: str, met: bool) -> CornerResult:
    return CornerResult(corner=corner, ok=True, all_specs_met=met,
                        first_fail=None if met else "S3_f_peak")


def test_screen_augmentation_names_the_corner_that_catches_the_false_positive():
    """Design 1 passed the screen and failed the full sweep. The corner that
    rejected it is the one worth adding, and it must be named."""
    corners = all_corners()[:4]
    per45 = [
        [_cr(str(c), True) for c in corners],                    # 0: robust
        [_cr(str(c), j != 2) for j, c in enumerate(corners)],     # 1: fails c[2]
    ]
    aug = screen_augmentation(per45, corners, non_robust_idx=[1])
    assert aug[str(corners[2])] == [1]
    assert aug[str(corners[0])] == []


def test_screen_augmentation_lists_every_corner_including_the_useless_ones():
    """A corner that catches nothing has to appear with an empty list, not be
    absent — otherwise "not in the dict" reads as "not evaluated"."""
    corners = all_corners()[:3]
    per45 = [[_cr(str(c), True) for c in corners]]
    aug = screen_augmentation(per45, corners, non_robust_idx=[])
    assert set(aug) == {str(c) for c in corners}
    assert all(v == [] for v in aug.values())


def test_screen_augmentation_ignores_designs_that_were_already_robust():
    """Only the false positives are being explained. A robust design that
    happens to fail nothing must not inflate any corner's count."""
    corners = all_corners()[:3]
    per45 = [[_cr(str(c), True) for c in corners],
             [_cr(str(c), j != 1) for j, c in enumerate(corners)]]
    aug = screen_augmentation(per45, corners, non_robust_idx=[1])
    assert sum(len(v) for v in aug.values()) == 1
