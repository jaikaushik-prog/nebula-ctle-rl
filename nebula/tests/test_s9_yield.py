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
from nebula.device.tail import W_PER_FINGER_MAX_UM, TailDevice
from nebula.experiments.cl_range import committed_cl_range
from nebula.experiments.s3_yield import PROPOSED_BOX
from nebula.experiments.s9_yield import (
    CL_LEGACY_PIN_F,
    LEGACY_150FF,
    NOMINAL_CORNER,
    NOMINAL_VDD,
    PROMOTION_LOADS,
    SCREEN_CORNERS,
    SCREEN_LOADS,
    TAIL_IS_IDEAL,
    TAIL_L_UM,
    TAIL_MIRROR_RATIO,
    TAIL_UM_PER_AMP,
    UNSCREENED_SPECS,
    VCM_TRACKS_VDD,
    tail_for_design,
    CornerResult,
    LoadCorner,
    SpecCheck,
    _range_check,
    _shortfall_max,
    _shortfall_min,
    _worst,
    assumptions_header,
    check_specs,
    cl_ladder,
    first_fail_table,
    fpeak_exponent,
    load_edge_table,
    load_grid,
    point_at_corner,
    screen_augmentation,
    widest_passing_ratio,
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


def test_cl_is_screened_over_the_derived_range_not_pinned():
    """Session 12b. `cl` used to be a single 150 fF pin -- the S3-yield maximum
    of five values tested. It is now a CONTEXT RANGE, derived in CL_RANGE.md,
    and the screen visits both of its edges."""
    rng = committed_cl_range()
    assert SCREEN_LOADS == (rng.cl_lo_f, rng.cl_hi_f)
    assert PROMOTION_LOADS == (rng.cl_lo_f, rng.cl_mid_f, rng.cl_hi_f)
    assert len(SCREEN_LOADS) == 2 and len(PROMOTION_LOADS) == 3


def test_the_screened_range_lies_entirely_below_the_legacy_pin():
    """THE FINDING behind the re-run, as a test: every number in S9_YIELD.md
    was measured at a load 1.9x above the top of the physically derived
    range."""
    assert CL_LEGACY_PIN_F == 150e-15
    assert max(SCREEN_LOADS) < CL_LEGACY_PIN_F
    assert CL_LEGACY_PIN_F / max(SCREEN_LOADS) > 1.5


def test_the_promotion_grid_adds_the_middle_of_the_range():
    """Two-edge screening cannot see a design that fails in the MIDDLE of the
    load range, and for a two-sided spec that is not impossible (G46's
    mechanism, on the load axis). The promotion tier covers it."""
    assert set(SCREEN_LOADS) < set(PROMOTION_LOADS)
    mid = committed_cl_range().cl_mid_f
    assert min(SCREEN_LOADS) < mid < max(SCREEN_LOADS)


def test_legacy_figures_are_the_ones_S9_YIELD_published():
    """Quoted in the comparison table so the new numbers sit next to the ones
    they supersede. 13.49 / 8.20 / 8.10 %."""
    assert LEGACY_150FF["TT / 1.00 / 27 C"] == (255, 1890)
    assert LEGACY_150FF["all 3 screen corners"] == (155, 1890)
    assert LEGACY_150FF["all 45 corners"] == (153, 1890)


def test_the_three_assumptions_are_all_stated_in_the_printed_header():
    """The header is the only thing a reader of the output sees. If an
    assumption is not in it, it is not disclosed."""
    h = assumptions_header(2000, 1)
    assert "ASSUMPTION" in h
    assert "SCREENED CONTEXT RANGE" in h
    assert "13.64" in h and "78.04" in h        # both edges, in fF
    assert "150 fF" in h                        # and what it supersedes
    assert "REAL CURRENT MIRROR" in h           # the tail, since session 13
    assert "tail_saturation" in h               # and the row it adds
    assert "VCM held CONSTANT" in h
    for spec in UNSCREENED_SPECS:
        assert spec.split()[0] in h     # S4, S7, S8 each named


def test_header_is_pure_ascii():
    """G10: the Windows console is cp1252 and a stray glyph crashes the run
    under redirection -- which is exactly how this output gets captured."""
    assumptions_header(2000, 1).encode("ascii")


def test_tail_is_no_longer_ideal_and_the_optimistic_caveat_is_gone():
    """Session 13 flipped this. The previous version of this test asserted
    `TAIL_IS_IDEAL is True` and that the header said "OPTIMISTIC", precisely so
    that adding a tail could not happen without the caveat coming out with it.
    It worked: this is the pairing being honoured."""
    assert TAIL_IS_IDEAL is False
    h = assumptions_header(1, 1)
    assert "OPTIMISTIC" not in h
    assert "REAL CURRENT MIRROR" in h
    # The ONE ideal element that remains must still be declared.
    assert "I_ref IS STILL IDEAL" in h


def test_the_tail_sizing_rule_is_a_current_density_and_is_stated_in_the_header():
    """The rule has to be visible in the output, because it is a design
    DECISION the reader may reject (rule 6) rather than a measurement."""
    h = assumptions_header(1, 1)
    assert f"{TAIL_UM_PER_AMP / 1e3:.1f}k um/A" in h
    assert "ss/0.95/125C" in h          # sized at the worst corner, deliberately
    assert "not searched" in h.lower() or "not searched" in h


def test_tail_width_scales_with_current():
    """A single fixed width cannot serve a 16x range of i_bias. Doubling the
    bias must double the tail."""
    a = tail_for_design({**BASE, "i_bias": 1.0e-3})
    b = tail_for_design({**BASE, "i_bias": 2.0e-3})
    assert b.w_tail == pytest.approx(2.0 * a.w_tail)
    assert a.l_tail == b.l_tail == TAIL_L_UM


def test_tail_sizing_rule_stays_inside_the_bin_ceiling_across_the_whole_box():
    """G53: the SKY130 bin ceiling is on W PER FINGER. The rule must pick an
    `nf` that honours it at the TOP of `i_bias`, or the widest designs in the
    box abort with "could not find a valid modelname" -- which G31 records as
    being read as a units error nine times out of ten."""
    lo, hi = PROPOSED_BOX["i_bias"][0], PROPOSED_BOX["i_bias"][1]
    for i_bias in (lo, hi, (lo + hi) / 2):
        t = tail_for_design({**BASE, "i_bias": i_bias})
        assert t.w_tail / t.nf_tail <= W_PER_FINGER_MAX_UM
        assert t.w_ref / t.nf_ref <= W_PER_FINGER_MAX_UM
        assert t.finger_matched          # else the mirror ratio drifts (sec 5)


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


# ---------------------------------------------------------------------------
# The (corner x load) grid -- session 12b's second axis.
# ---------------------------------------------------------------------------


def test_load_corner_prints_both_axes():
    """The tag is what `screen_augmentation` keys on and what lands in the
    JSON, so a result attributed to the wrong load edge would look perfectly
    well-formed. Both axes have to be in it."""
    g = LoadCorner(Corner("ss", 0.95, 125.0), 13.642e-15)
    assert "ss" in str(g) and "125" in str(g)
    assert "13.6f" in str(g)


def test_load_grid_is_corners_major():
    """So a report reads corner by corner rather than load by load."""
    corners = [Corner("tt", 1.0, 27.0), Corner("ss", 0.95, 125.0)]
    grid = load_grid(corners, (1e-15, 2e-15))
    assert len(grid) == 4
    assert [g.corner for g in grid] == [corners[0], corners[0],
                                        corners[1], corners[1]]
    assert [g.cl_f for g in grid] == [1e-15, 2e-15, 1e-15, 2e-15]


def test_the_screen_grid_is_a_subset_of_the_promotion_grid():
    """That subsetting is what makes the screen unable to produce false
    NEGATIVES (G47) and what makes the determinism check free. Adding a load
    axis must not break it."""
    screen = {str(g) for g in load_grid(SCREEN_CORNERS, SCREEN_LOADS)}
    promo = {str(g) for g in load_grid(all_corners(), PROMOTION_LOADS)}
    assert screen <= promo


def test_nominal_corner_is_not_one_of_the_screen_corners():
    """S9_YIELD sec 4: "0 designs fail nominal yet pass all three extremes"
    is a MEASUREMENT only because TT/1.00/27 C is not among the screened
    corners. Stage 0 relies on that too."""
    assert NOMINAL_CORNER not in SCREEN_CORNERS
    assert NOMINAL_CORNER in all_corners()


def _grid_results(grid, met_flags):
    return [CornerResult(corner=str(g), ok=True, cl_f=g.cl_f,
                         all_specs_met=m) for g, m in zip(grid, met_flags)]


def test_load_edge_table_separates_disjoint_from_empty():
    """THE PRE-REGISTERED FOLLOW-UP (PREDICTIONS.md entry 1). A joint count of
    zero means something completely different depending on whether each load's
    set is also empty, or whether they are large and DISJOINT -- the second
    says the topology works but the load has to be pinned down."""
    grid = load_grid([Corner("tt", 1.0, 27.0)], (1e-15, 2e-15))
    per_design = [
        _grid_results(grid, [True, False]),     # 0: lo only
        _grid_results(grid, [False, True]),     # 1: hi only
        _grid_results(grid, [True, True]),      # 2: both
        _grid_results(grid, [False, False]),    # 3: neither
    ]
    t = load_edge_table(per_design, grid, (1e-15, 2e-15))
    assert t["robust at cl 1.0f alone"] == 2        # designs 0 and 2
    assert t["robust at cl 2.0f alone"] == 2        # designs 1 and 2
    assert t["robust at EVERY load"] == 1
    assert t["robust at ANY load"] == 3
    assert t["robust at exactly one load"] == 2


def test_load_edge_table_requires_every_corner_at_that_load():
    """"Robust at cl_lo" means robust at cl_lo across ALL corners, not at one
    of them. Getting this wrong inflates both per-load counts."""
    corners = [Corner("tt", 1.0, 27.0), Corner("ss", 0.95, 125.0)]
    grid = load_grid(corners, (1e-15, 2e-15))
    # passes at cl_lo under tt, fails at cl_lo under ss
    per_design = [_grid_results(grid, [True, True, False, True])]
    t = load_edge_table(per_design, grid, (1e-15, 2e-15))
    assert t["robust at cl 1.0f alone"] == 0
    assert t["robust at cl 2.0f alone"] == 1


def test_evaluate_at_corner_task_may_carry_the_load():
    """A 5-tuple sets `cl` for that evaluation; a 4-tuple keeps the design's
    own, so `robust_geometry.py` -- which reproduces session 10d at its 150 fF
    pin -- keeps working untouched."""
    from nebula.experiments.s9_yield import evaluate_at_corner
    # A headroom-rejecting design, so no simulator is needed to reach the
    # return: rl x i_bias/2 drops the output below MIN_V_OUT_DC.
    bad = dict(BASE, i_bias=8e-3, rl=800)
    r4 = evaluate_at_corner((bad, "tt", 1.0, 27.0))
    r5 = evaluate_at_corner((bad, "tt", 1.0, 27.0, 13.642e-15))
    assert r4.first_fail == "headroom" and r5.first_fail == "headroom"
    assert r4.cl_f == pytest.approx(BASE["cl"])
    assert r5.cl_f == pytest.approx(13.642e-15)
    assert "150.0f" in r4.corner and "13.6f" in r5.corner


def test_evaluate_at_corner_does_not_mutate_the_caller_dict():
    """The load is overwritten per evaluation and the same design dict is
    reused across the whole grid, so a mutation would leak one point's load
    into every later one."""
    from nebula.experiments.s9_yield import evaluate_at_corner
    bad = dict(BASE, i_bias=8e-3, rl=800)
    before = dict(bad)
    evaluate_at_corner((bad, "tt", 1.0, 27.0, 13.642e-15))
    assert bad == before


def test_comparison_table_puts_both_treatments_side_by_side():
    from nebula.experiments.s9_yield import comparison_table
    txt = comparison_table(1890, 40, 38, 120)
    assert "13.49" in txt          # the legacy nominal figure
    assert "8.20" in txt or "8.20%" in txt
    assert "40/1890" in txt.replace(" ", "")
    txt.encode("ascii")            # G10


def test_comparison_table_says_not_measured_rather_than_zero():
    """A stage that did not run must not read as a stage that yielded zero."""
    from nebula.experiments.s9_yield import comparison_table
    txt = comparison_table(1890, 0, None, None)
    assert "not measured" in txt


# ---------------------------------------------------------------------------
# The pre-registered follow-up: how much load range CAN be absorbed.
# ---------------------------------------------------------------------------


def test_cl_ladder_is_geometric():
    """`cl` enters f_p2 multiplicatively, so equal RATIOS between rungs is what
    makes the ladder uniform in the coordinate the circuit responds to."""
    rungs = cl_ladder(5, 10e-15, 160e-15)
    assert rungs[0] == pytest.approx(10e-15)
    assert rungs[-1] == pytest.approx(160e-15)
    ratios = [b / a for a, b in zip(rungs, rungs[1:])]
    assert all(r == pytest.approx(2.0) for r in ratios), ratios


def test_cl_ladder_merges_the_included_loads_and_stays_sorted():
    """LOAD-BEARING, and it caught a real contradiction. Without the screen's
    own loads as rungs, the ladder reported the one corner-and-load-robust
    design as tolerating 4.32x -- while the screen that found it had passed it
    across 5.72x. The ladder was too coarse to contain the points the verdict
    was made at."""
    rungs = cl_ladder(5, 10e-15, 160e-15, include=(13.5e-15, 77.0e-15))
    assert list(rungs) == sorted(rungs)
    assert 13.5e-15 in rungs and 77.0e-15 in rungs
    assert len(rungs) == 7


def test_cl_ladder_does_not_duplicate_an_included_rung():
    rungs = cl_ladder(5, 10e-15, 160e-15, include=(20e-15,))
    assert len(rungs) == 5


def test_cl_ladder_needs_at_least_two_rungs():
    with pytest.raises(ValueError, match="at least two"):
        cl_ladder(1)


def test_widest_passing_ratio_requires_contiguity():
    """A design that passes at 10 and 100 fF but fails at 30 does NOT tolerate
    a 10x load range -- `cl` is a context it has to survive over an interval.
    S3 is two-sided, so leaving the window mid-range is a real possibility."""
    cls = (10e-15, 30e-15, 100e-15)
    assert widest_passing_ratio([True, False, True], cls)[0] == 1.0
    assert widest_passing_ratio([True, True, True], cls)[0] == pytest.approx(10.0)


def test_widest_passing_ratio_reports_the_span_it_measured():
    cls = (10e-15, 20e-15, 40e-15, 80e-15)
    ratio, span = widest_passing_ratio([False, True, True, False], cls)
    assert ratio == pytest.approx(2.0)
    assert span == (20e-15, 40e-15)


def test_widest_passing_ratio_picks_the_widest_of_several_runs():
    cls = (1e-15, 2e-15, 4e-15, 8e-15, 16e-15, 32e-15)
    ratio, span = widest_passing_ratio(
        [True, False, True, True, True, False], cls)
    assert ratio == pytest.approx(4.0)
    assert span == (4e-15, 16e-15)


def test_widest_passing_ratio_handles_a_run_reaching_the_last_rung():
    """Off-by-one guard: the sentinel that closes the final run must not read
    past the end of the ladder."""
    cls = (1e-15, 2e-15, 4e-15)
    assert widest_passing_ratio([False, True, True], cls)[0] == pytest.approx(2.0)


def test_widest_passing_ratio_of_nothing_is_zero_not_one():
    """"Passes nowhere" and "passes at exactly one load" are different facts."""
    assert widest_passing_ratio([False, False], (1e-15, 2e-15)) == (0.0, None)
    assert widest_passing_ratio([True, False], (1e-15, 2e-15))[0] == 1.0


def test_widest_passing_ratio_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="against"):
        widest_passing_ratio([True], (1e-15, 2e-15))


def test_fpeak_exponent_recovers_a_known_power_law():
    """f = C * cl^-0.5 must come back as -0.5 exactly."""
    cls = [10e-15, 20e-15, 40e-15, 80e-15]
    f = [1e9 * (c / 10e-15) ** -0.5 for c in cls]
    assert fpeak_exponent(cls, f) == pytest.approx(-0.5, abs=1e-12)


def test_fpeak_exponent_is_none_without_two_usable_points():
    assert fpeak_exponent([1e-15], [1e9]) is None
    assert fpeak_exponent([1e-15, 2e-15], [1e9, 0.0]) is None
    assert fpeak_exponent([], []) is None


def test_fpeak_exponent_drops_non_positive_values_rather_than_crashing():
    """A design with no peak reports f_pk = 0 or None; log of that is not a
    number, and the sample must shrink rather than the run dying."""
    cls = [10e-15, 20e-15, 40e-15]
    assert fpeak_exponent(cls, [1e9, None, 0.5e9]) == pytest.approx(-0.5,
                                                                   abs=1e-12)


# ─────────────────────────────────────────────────────────────────────────────
# `tail_saturation` — the row the tail adds, and the only one in the table that
# couples five box coordinates. Session 13.
# ─────────────────────────────────────────────────────────────────────────────


def _sky_tail(vds_tail=0.30, vdsat_tail=0.19, **kw):
    """A Sky130Point carrying tail primitives as well as the pair's."""
    p = _sky(**kw)
    p.vds_tail, p.vdsat_tail = vds_tail, vdsat_tail
    return p


def test_tail_saturation_row_is_absent_when_the_tail_is_ideal():
    """An ideal sink has no headroom requirement, so scoring one would invent a
    constraint the simulated circuit does not contain. Absent, not passing —
    a passing row would make an ideal-tail run look as though it had been
    checked."""
    names = [c.name for c in check_specs(_sky(), power_w=5e-3)]
    assert "tail_saturation" not in names


def test_tail_saturation_row_appears_when_a_tail_is_fitted():
    names = [c.name for c in check_specs(_sky_tail(), power_w=5e-3)]
    assert "tail_saturation" in names


def test_tail_saturation_passes_only_when_vds_exceeds_vdsat():
    ok = [c for c in check_specs(_sky_tail(vds_tail=0.30, vdsat_tail=0.19),
                                 power_w=5e-3) if c.name == "tail_saturation"][0]
    bad = [c for c in check_specs(_sky_tail(vds_tail=0.15, vdsat_tail=0.19),
                                  power_w=5e-3) if c.name == "tail_saturation"][0]
    assert ok.ok and ok.margin == pytest.approx(0.11)
    assert not bad.ok and bad.margin == pytest.approx(-0.04)
    # Shortfall must be <= 0 for the failure and exactly 0 for the pass, so the
    # "which spec binds" ranking can compare it against every other row.
    assert bad.shortfall < 0 and ok.shortfall == 0.0


def test_a_triode_tail_can_be_the_worst_failure_and_is_named_as_such():
    """The coupled constraint has to be able to WIN the ranking, or it will
    never appear in the binding-constraint table however often it fails."""
    r = _sky_tail(vds_tail=0.01, vdsat_tail=0.40,   # deeply in triode
                  peaking=6.0, f_pk=2.0e9)
    worst = _worst(check_specs(r, power_w=5e-3))
    assert worst is not None and worst.name == "tail_saturation"


def test_tail_saturation_is_the_only_row_that_reads_the_tail():
    """If any other check silently started reading tail primitives, an
    ideal-tail run and a real-tail run would stop being comparable on that row.
    Pin it: every other row must be identical with and without a tail."""
    a = {c.name: (c.ok, c.value, c.margin)
         for c in check_specs(_sky(), power_w=5e-3)}
    b = {c.name: (c.ok, c.value, c.margin)
         for c in check_specs(_sky_tail(), power_w=5e-3)}
    assert set(b) - set(a) == {"tail_saturation"}
    for name, vals in a.items():
        assert b[name] == vals, name
