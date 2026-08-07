"""
§6f / §6h — the shortfall reward, and the properties the retraction is about.

The shape under test:

    if any shortfall_i > 0:   r = -sum( clip(shortfall_i, 0, 1) )
    else:                     r = B + min_i( margin_i / tol_i )

The three properties that matter, in order of how much they cost to discover:

1. **Every violated constraint contributes gradient.** A `min` reward reports
   `S3_f_peak` for as long as that misses by 17 GHz and gives the agent NO
   gradient on `tail_saturation`, which misses by tens of millivolts (session
   13's violation table; HANDOFF §8's retraction).
2. **`B` separates the bands.** Any feasible design must outrank any
   infeasible one, with no overlap at the boundary.
3. **Invalid is strictly below every valid score**, so a broken circuit can
   never be preferred to a bad one.
"""

from __future__ import annotations

import math

import pytest

from nebula.common.types import (
    SPEC_PEAKING_DB_RANGE,
    SPEC_POWER_MAX_W,
    SPEC_VN_IN_MAX_VRMS,
)
from nebula.rl import reward_v1 as R
from nebula.rl.contract import f_peak_octaves

TARGET_F = math.sqrt(1.25e9 * 2.5e9)          # mid-window, geometric


def meas(**over):
    """A comfortably feasible measurement vector, perturbable per test."""
    m = {"g_dc_db": 6.0, "peaking_db": 7.5,
         "f_peak_oct": f_peak_octaves(TARGET_F),
         "nyq_boost_db": 6.9, "inoise_vrms": 2.2e-4, "power_w": 6.0e-3,
         "pair_margin_v": 0.26, "tail_margin_v": 0.33}
    m.update(over)
    return m


# ── the tolerances are documented, not invented ─────────────────────────────

def test_every_tolerance_carries_its_basis():
    for t in R.TOLERANCES:
        assert t.basis.strip() and len(t.basis) > 20, f"{t.name}: {t.basis!r}"
        assert t.value > 0


def test_f_peak_tolerance_is_half_of_s3s_one_octave_window():
    """§6h: *'S3's window is 1.25-2.5 GHz, which is exactly one octave, so the
    natural form is -|log2(f_peak/f_target)| with a half-width of 0.5.'*"""
    assert R.TOL["S3_f_peak"] == 0.5
    assert f_peak_octaves(2.5e9) - f_peak_octaves(1.25e9) == pytest.approx(1.0)


def test_tail_saturation_is_scaled_to_a_hundred_millivolts():
    """THE tolerance the whole retraction is about."""
    assert R.TOL["tail_saturation"] == 0.1


def test_peaking_tolerance_is_in_db():
    assert R.TOL["S3_peaking"] == 1.0


# ── margins ──────────────────────────────────────────────────────────────────

def test_peaking_margin_is_distance_inside_the_band():
    lo, hi = SPEC_PEAKING_DB_RANGE
    assert R.margins(meas(peaking_db=7.5), TARGET_F)["S3_peaking"] == pytest.approx(4.5)
    assert R.margins(meas(peaking_db=lo), TARGET_F)["S3_peaking"] == pytest.approx(0.0)
    assert R.margins(meas(peaking_db=hi), TARGET_F)["S3_peaking"] == pytest.approx(0.0)
    # Outside on EITHER side is negative by exactly how far outside.
    assert R.margins(meas(peaking_db=1.0), TARGET_F)["S3_peaking"] == pytest.approx(-2.0)
    assert R.margins(meas(peaking_db=14.0), TARGET_F)["S3_peaking"] == pytest.approx(-2.0)


def test_f_peak_margin_is_symmetric_in_LOG_frequency():
    """An octave above and an octave below must cost the SAME.

    In linear hertz they do not — which is the whole reason for the unit.
    """
    up = R.margins(meas(f_peak_oct=f_peak_octaves(2 * TARGET_F)), TARGET_F)
    dn = R.margins(meas(f_peak_oct=f_peak_octaves(TARGET_F / 2)), TARGET_F)
    assert up["S3_f_peak"] == pytest.approx(dn["S3_f_peak"])
    assert up["S3_f_peak"] == pytest.approx(0.5 - 1.0)


def test_f_peak_margin_is_zero_at_the_half_window_edges():
    m = R.margins(meas(f_peak_oct=f_peak_octaves(TARGET_F) + 0.5), TARGET_F)
    assert m["S3_f_peak"] == pytest.approx(0.0, abs=1e-12)


def test_noise_and_power_margins_are_against_the_spec_limits():
    m = R.margins(meas(inoise_vrms=1.0e-3, power_w=10e-3), TARGET_F)
    assert m["S5_noise"] == pytest.approx(SPEC_VN_IN_MAX_VRMS - 1.0e-3)
    assert m["S6_power"] == pytest.approx(SPEC_POWER_MAX_W - 10e-3)


# ── THE PROPERTY THE RETRACTION IS ABOUT ────────────────────────────────────

def test_every_violated_spec_contributes_and_min_would_not():
    """*'score every violated constraint, not just the worst one.'*

    Two designs, both missing `S3_f_peak` by exactly the same huge amount. One
    also has the tail 50 mV into triode. A `min`-over-specs reward gives them
    the IDENTICAL score; this one does not, and the difference is the tail's
    entire gradient.
    """
    far = f_peak_octaves(TARGET_F) + 3.0        # 3 octaves off: shortfall >> 1
    ok_tail = R.reward(meas(f_peak_oct=far), TARGET_F, specs=R.V1_SPECS)
    bad_tail = R.reward(meas(f_peak_oct=far, tail_margin_v=-0.05), TARGET_F,
                        specs=R.V1_SPECS)
    assert not ok_tail.feasible and not bad_tail.feasible
    assert bad_tail.reward < ok_tail.reward, (
        "the tail violation produced NO change in reward — this is exactly the "
        "pathology HANDOFF §8 retracted the `min` reward over")
    assert bad_tail.reward - ok_tail.reward == pytest.approx(-0.5), (
        "50 mV of tail violation at a 100 mV tolerance must cost exactly 0.5")


def test_a_min_over_specs_really_would_hide_it():
    """The counter-example, asserted rather than asserted-in-a-comment."""
    far = f_peak_octaves(TARGET_F) + 3.0
    a = R.shortfalls(R.margins(meas(f_peak_oct=far), TARGET_F), R.V1_SPECS)
    b = R.shortfalls(R.margins(meas(f_peak_oct=far, tail_margin_v=-0.05),
                               TARGET_F), R.V1_SPECS)
    assert max(a.values()) == max(b.values()), (
        "the two designs differ in their WORST shortfall, so this test is not "
        "demonstrating what it claims")
    assert sum(a.values()) != sum(b.values())


def test_shortfalls_are_clipped_at_one_in_the_sum():
    """*'r = -sum( clip(shortfall_i, 0, 1) )'*. Without the clip, one
    catastrophic spec drowns out every other gradient again."""
    wild = f_peak_octaves(TARGET_F) + 50.0
    rb = R.reward(meas(f_peak_oct=wild), TARGET_F, specs=R.V1_SPECS)
    assert rb.shortfalls["S3_f_peak"] > 10.0        # raw shortfall is huge
    assert rb.reward >= -float(len(R.V1_SPECS))     # the SUM is still bounded


# ── the two bands ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("specs", [R.V0_SPECS, R.V1_SPECS])
def test_any_feasible_design_outranks_any_infeasible_one(specs):
    n = len(specs)
    worst_feasible = R.feasible_bonus(n) + 0.0      # min margin exactly 0
    best_infeasible = 0.0 - 1e-12                   # a hair violated
    assert worst_feasible > best_infeasible
    assert R.feasible_bonus(n) >= n, (
        "B must exceed the largest possible infeasible penalty, which is N")


@pytest.mark.parametrize("specs", [R.V0_SPECS, R.V1_SPECS])
def test_invalid_is_strictly_below_every_valid_score(specs):
    n = len(specs)
    floor = R.invalid_reward(n)
    assert floor == -(n + 1.0)
    assert floor < -float(n), (
        "an invalid evaluation must be worse than violating every spec "
        "maximally, or the policy can prefer a broken circuit to a bad one")
    rb = R.reward(None, TARGET_F, specs=specs)
    assert rb.reward == floor and not rb.valid and not rb.feasible


def test_invalid_is_a_distinct_branch_not_a_maxed_out_shortfall():
    """`meas=None` must not be representable as 'every spec missed'."""
    rb = R.reward(None, TARGET_F, specs=R.V1_SPECS)
    assert rb.margins == {} and rb.shortfalls == {}
    worst_valid = R.reward(meas(f_peak_oct=f_peak_octaves(TARGET_F) + 99,
                                peaking_db=-50.0, nyq_boost_db=-50.0,
                                inoise_vrms=1.0, power_w=1.0,
                                pair_margin_v=-9.0, tail_margin_v=-9.0),
                           TARGET_F, specs=R.V1_SPECS)
    assert rb.reward < worst_valid.reward


# ── feasible branch ──────────────────────────────────────────────────────────

def test_feasible_reward_seeks_the_worst_normalised_margin():
    a = R.reward(meas(), TARGET_F, specs=R.V1_SPECS)
    b = R.reward(meas(tail_margin_v=0.5), TARGET_F, specs=R.V1_SPECS)
    assert a.feasible and b.feasible
    assert b.reward >= a.reward


def test_feasible_reward_reports_which_spec_is_the_binding_margin():
    rb = R.reward(meas(tail_margin_v=0.02), TARGET_F, specs=R.V1_SPECS)
    assert rb.feasible
    assert rb.worst_spec == "tail_saturation"


def test_exactly_on_the_boundary_counts_as_satisfied():
    """`shortfall = max(0, -margin/tol)` is zero at margin = 0."""
    rb = R.reward(meas(peaking_db=SPEC_PEAKING_DB_RANGE[0]), TARGET_F,
                  specs=R.V0_SPECS)
    assert rb.feasible and rb.shortfalls["S3_peaking"] == 0.0


# ── v0 vs v1 ────────────────────────────────────────────────────────────────

def test_v0_is_s3_alone_and_all_three_readings_of_it():
    assert set(R.V0_SPECS) == {"S3_peaking", "S3_f_peak", "S3_nyq_boost"}


def test_v1_adds_the_specs_the_device_layer_can_measure():
    assert set(R.V1_SPECS) - set(R.V0_SPECS) == {
        "S5_noise", "S6_power", "saturation", "tail_saturation"}


def test_no_link_layer_spec_is_scored():
    """S8 cannot be here: the link layer is a mock (G16) and §6b forbids
    reaching it. S4 and S7 are absent for their own stated reasons."""
    for absent in ("eye_h_v", "eye_w_ui", "S8", "hd3", "S4", "area", "S7"):
        assert not any(absent.lower() in s.lower() for s in R.V1_SPECS)


def test_v0_ignores_specs_v1_scores():
    """A design with a triode tail is INFEASIBLE under v1 and FEASIBLE under
    v0 — which is what makes the second pass a wiring check, not a repeat."""
    m = meas(tail_margin_v=-0.05)
    assert R.reward_v0(m, TARGET_F).feasible
    assert not R.reward_v1(m, TARGET_F).feasible


# ── the cost term ────────────────────────────────────────────────────────────

def test_cost_term_is_off_by_default_and_subtracts_when_on():
    assert R.reward(meas(), TARGET_F).cost_penalty == 0.0
    rb = R.reward(meas(), TARGET_F, lambda_cost=0.25, sim_cost=4)
    assert rb.cost_penalty == pytest.approx(1.0)
    assert rb.reward == pytest.approx(rb.spec_reward - 1.0)


def test_cost_term_applies_to_the_invalid_branch_too():
    """Otherwise crashing becomes cheaper than simulating."""
    rb = R.reward(None, TARGET_F, lambda_cost=0.25, sim_cost=4)
    assert rb.reward == pytest.approx(R.invalid_reward(len(R.V1_SPECS)) - 1.0)


# ── determinism ──────────────────────────────────────────────────────────────

def test_reward_is_a_pure_function_of_its_inputs():
    a = R.reward(meas(), TARGET_F, specs=R.V1_SPECS).reward
    for _ in range(20):
        R.reward(meas(peaking_db=3.1), TARGET_F, specs=R.V1_SPECS)
    b = R.reward(meas(), TARGET_F, specs=R.V1_SPECS).reward
    assert a == b
