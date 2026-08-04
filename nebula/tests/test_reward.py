"""
Interface tests for the reward. CLAUDEwa.md §9.

The properties being pinned, in order of how expensive it is to get them
wrong:

  1. non-positive, and exactly zero once every spec is met;
  2. no bonus for exceeding a spec (§9: "Do not add bonus terms") — this is
     what stops the policy trading a met spec against an unmet one;
  3. scored on the WORST corner, never nominal (§12, trap 1);
  4. a failed evaluation returns a number, never an exception (§8 rule 2);
  5. per-spec normalisation, so no single spec dominates the gradient.

If the reward is wrong, G3 fails and CLAUDEwa.md §7 says to stop and debug it
rather than proceed to corners. These tests are the first place to look.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.common.types import DeviceResult, LinkResult, TargetSpec, TT_NOMINAL
from nebula.device import mock as device_mock
from nebula.link import mock as link_mock
from nebula.rl.reward import (
    N_SPEC_TERMS,
    RewardConfig,
    SpecTerm,
    make_reward_fn,
    reward,
    shortfall,
    spec_terms,
    total_reward,
    worst_corner_reward,
)


def _device(**over) -> DeviceResult:
    """A DeviceResult that meets every device-side spec, with overrides."""
    base = dict(
        ok=True, fail_reason=None, g_dc=4.0, f_zero_hz=1.0e9,
        f_pole1_hz=2.0e9, f_pole2_hz=8.0e9, fit_residual_db=0.05,
        peaking_db=6.0, f_peak_hz=2.0e9, hd3_dbc=-40.0, vn_in_vrms=1.0e-3,
        power_w=10e-3, area_mm2=0.02, vout_swing_v=0.6,
        ac_freq_hz=np.array([1e6, 1e9]), ac_mag_db=np.array([12.0, 14.0]),
    )
    base.update(over)
    return DeviceResult(**base)  # type: ignore[arg-type]


def _link(**over) -> LinkResult:
    """A LinkResult that meets S8, with overrides."""
    base = dict(ok=True, eye_h_v=0.150, eye_w_ui=0.55, ber=1e-16, dfe_tap=0.2)
    base.update(over)
    return LinkResult(**base)  # type: ignore[arg-type]


class TestConfig:
    def test_human_set_tolerances_are_the_defaults(self):
        # Set by a human on 2026-08-03 and deliberately loose: at G3 the policy
        # has to be able to learn something, and real CTLEs tune in discrete
        # steps a dB or two apart, so +/-1 dB is already at production
        # granularity.
        cfg = RewardConfig()
        assert cfg.peaking_tol_db == 1.0
        assert cfg.f_peak_tol_frac == 0.10

    def test_f_peak_tolerance_is_fractional_so_it_scales_across_s3(self):
        # +/-10% of a 1.25 GHz request is 125 MHz; of a 2.5 GHz request,
        # 250 MHz. A fixed absolute tolerance would be absurdly tight at one
        # end of the S3 range.
        cfg = RewardConfig()
        assert cfg.f_peak_tol_hz(1.25e9) == pytest.approx(125e6)
        assert cfg.f_peak_tol_hz(2.5e9) == pytest.approx(250e6)

    def test_tolerance_sweep_axis_exists(self):
        from nebula.rl.reward import TOLERANCE_SWEEP

        # Tolerance is a reported axis, not a hidden constant.
        assert RewardConfig().peaking_tol_db in {p for p, _ in TOLERANCE_SWEEP}
        assert len(TOLERANCE_SWEEP) >= 3
        # Ordered loosest first.
        assert [p for p, _ in TOLERANCE_SWEEP] == sorted(
            (p for p, _ in TOLERANCE_SWEEP), reverse=True)

    @pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
    def test_rejects_nonsense_tolerances(self, bad):
        with pytest.raises(ValueError):
            RewardConfig(peaking_tol_db=bad)
        with pytest.raises(ValueError):
            RewardConfig(f_peak_tol_frac=bad)

    def test_rejects_a_fractional_tolerance_given_in_hz(self):
        # 250e6 passed where a fraction belongs is the obvious slip.
        with pytest.raises(ValueError, match="fraction of the target"):
            RewardConfig(f_peak_tol_frac=250e6)

    def test_failure_floor_defaults_to_the_mathematical_minimum(self):
        assert RewardConfig().failed_reward == -float(N_SPEC_TERMS)

    def test_failure_floor_cannot_be_positive(self):
        with pytest.raises(ValueError, match="non-positive"):
            RewardConfig(failed_reward=1.0)


class TestShortfallForm:
    """The §9 term itself: min((x - tau) / (|x| + |tau|), 0)."""

    def test_met_max_spec_scores_exactly_zero(self):
        assert shortfall(value=0.150, target=0.100, direction="max") == 0.0

    def test_met_min_spec_scores_exactly_zero(self):
        assert shortfall(value=10e-3, target=15e-3, direction="min") == 0.0

    def test_exactly_on_target_scores_zero(self):
        assert shortfall(value=0.100, target=0.100, direction="max") == 0.0
        assert shortfall(value=15e-3, target=15e-3, direction="min") == 0.0

    def test_violation_is_negative(self):
        assert shortfall(value=0.050, target=0.100, direction="max") < 0.0
        assert shortfall(value=20e-3, target=15e-3, direction="min") < 0.0

    def test_hand_computed_max_violation(self):
        # (0.05 - 0.10) / (0.05 + 0.10) = -0.05/0.15 = -1/3
        assert shortfall(0.050, 0.100, "max") == pytest.approx(-1.0 / 3.0)

    def test_hand_computed_min_violation(self):
        # (15 - 20)/(20 + 15) = -5/35 = -1/7
        assert shortfall(20e-3, 15e-3, "min") == pytest.approx(-1.0 / 7.0)

    def test_hand_computed_negative_valued_spec(self):
        # HD3: x = -25 dBc, tau = -30 dBc -> violated by 5 dB.
        # (-30 - -25)/(25 + 30) = -5/55 = -1/11
        assert shortfall(-25.0, -30.0, "min") == pytest.approx(-1.0 / 11.0)

    def test_every_term_is_bounded_below_by_minus_one(self):
        # This is what makes the per-spec normalisation meaningful and what
        # sets the failure floor at -N_SPEC_TERMS.
        for value, target, direction in [
            (1e-12, 1.0, "max"), (1e12, 1.0, "min"), (-1.0, 1.0, "max"),
            (0.0, 100.0, "max"), (1e9, 1e-9, "min"),
        ]:
            assert -1.0 - 1e-12 <= shortfall(value, target, direction) <= 0.0

    def test_normalisation_makes_unlike_specs_comparable(self):
        # 10% over on power (15 mW) and 10% over on noise (1.5 mV) must score
        # identically, despite four orders of magnitude between the raw units.
        p = shortfall(16.5e-3, 15e-3, "min")
        n = shortfall(1.65e-3, 1.5e-3, "min")
        assert p == pytest.approx(n)

    def test_match_direction_within_tolerance_scores_zero(self):
        assert shortfall(6.3, 6.0, "match", tol=0.5) == 0.0

    def test_match_direction_outside_tolerance_is_negative(self):
        assert shortfall(7.0, 6.0, "match", tol=0.5) < 0.0
        assert shortfall(5.0, 6.0, "match", tol=0.5) < 0.0

    def test_match_margin_is_symmetric_even_though_the_penalty_is_not(self):
        # The MARGIN is symmetric: 1 dB above and 1 dB below target are
        # equally wrong in dB.
        above = SpecTerm("p", 7.0, 6.0, "match", 0.5)
        below = SpecTerm("p", 5.0, 6.0, "match", 0.5)
        assert above.margin() == pytest.approx(below.margin())

        # The PENALTY is not, because §9 normalises by (|x| + |tau|), which is
        # smaller when x is smaller. Undershooting the requested peaking is
        # therefore penalised slightly harder than overshooting it. This is a
        # property of the §9 form, not a bug in this implementation — recorded
        # here so it is a known asymmetry rather than a surprise in September.
        assert below.shortfall() < above.shortfall() < 0.0

    def test_zero_denominator_is_not_a_division_by_zero(self):
        assert shortfall(0.0, 0.0, "max") == 0.0

    def test_spec_term_reports_met(self):
        assert SpecTerm("p", 10e-3, 15e-3, "min").met
        assert not SpecTerm("p", 20e-3, 15e-3, "min").met


class TestNoBonusForExceeding:
    """§9: 'Once met, further improvement should be worth nothing.'"""

    def test_doubling_a_met_margin_changes_nothing(self, target, reward_cfg):
        just = reward(_device(), _link(eye_h_v=0.101), target, reward_cfg)
        lots = reward(_device(), _link(eye_h_v=0.900), target, reward_cfg)
        assert just == lots

    def test_a_met_spec_cannot_pay_for_an_unmet_one(self, target, reward_cfg):
        # The failure mode a bonus term would create: buy a huge eye, overrun
        # the power budget, come out ahead. It must not come out ahead.
        balanced = reward(_device(power_w=14e-3), _link(eye_h_v=0.120),
                          target, reward_cfg)
        traded = reward(_device(power_w=30e-3), _link(eye_h_v=0.900),
                        target, reward_cfg)
        assert traded < balanced

    def test_a_fully_met_design_scores_exactly_zero(self, target, reward_cfg):
        assert reward(_device(), _link(), target, reward_cfg) == 0.0

    def test_reward_is_never_positive(self, target, reward_cfg):
        for eye_h in (0.0, 0.05, 0.1, 0.5, 5.0):
            r = reward(_device(), _link(eye_h_v=eye_h), target, reward_cfg)
            assert r <= 0.0


class TestPerSpecCoverage:
    def test_all_eight_terms_are_present(self, target, reward_cfg):
        terms = spec_terms(_device(), _link(), target, reward_cfg)
        assert [t.name for t in terms] == [
            "peaking_db", "f_peak_hz", "hd3_dbc", "vn_in_vrms",
            "power_w", "area_mm2", "eye_h_v", "eye_w_ui",
        ]
        assert len(terms) == N_SPEC_TERMS

    @pytest.mark.parametrize(
        "dev_over,link_over,term",
        [
            ({"peaking_db": 11.0}, {}, "peaking_db"),          # S3
            ({"f_peak_hz": 1.3e9}, {}, "f_peak_hz"),           # S3
            ({"hd3_dbc": -20.0}, {}, "hd3_dbc"),               # S4
            ({"vn_in_vrms": 3e-3}, {}, "vn_in_vrms"),          # S5
            ({"power_w": 25e-3}, {}, "power_w"),               # S6
            ({"area_mm2": 0.09}, {}, "area_mm2"),              # S7
            ({}, {"eye_h_v": 0.050}, "eye_h_v"),               # S8
            ({}, {"eye_w_ui": 0.20}, "eye_w_ui"),              # S8
        ],
    )
    def test_each_spec_can_independently_drive_the_reward_negative(
        self, target, reward_cfg, dev_over, link_over, term
    ):
        terms = spec_terms(_device(**dev_over), _link(**link_over), target, reward_cfg)
        by_name = {t.name: t for t in terms}
        assert by_name[term].shortfall() < 0.0
        assert reward(_device(**dev_over), _link(**link_over), target, reward_cfg) < 0.0
        # ...and only that one term is violated
        assert sum(1 for t in terms if t.shortfall() < 0.0) == 1

    def test_spec_terms_refuses_failed_results(self, target, reward_cfg):
        with pytest.raises(ValueError, match="requires ok results"):
            spec_terms(DeviceResult.failed("boom"), _link(), target, reward_cfg)


class TestFailureHandling:
    """§8 rule 2 — the RL loop cannot tolerate exceptions."""

    def test_failed_device_returns_the_floor(self, target, reward_cfg):
        r = reward(DeviceResult.failed("no convergence"), _link(), target, reward_cfg)
        assert r == reward_cfg.failed_reward

    def test_failed_link_returns_the_floor(self, target, reward_cfg):
        r = reward(_device(), LinkResult.failed("bad fit"), target, reward_cfg)
        assert r == reward_cfg.failed_reward

    def test_the_floor_is_no_worse_than_the_worst_real_design(self, target, reward_cfg):
        # If failing scored worse than any achievable design, the policy would
        # learn to avoid *simulating*; if it scored better, it would learn to
        # crash on purpose. The floor is exactly the bound.
        awful = reward(
            _device(peaking_db=12.0, f_peak_hz=2.5e9, hd3_dbc=-1.0,
                    vn_in_vrms=1.0, power_w=1.0, area_mm2=10.0),
            _link(eye_h_v=1e-9, eye_w_ui=1e-9),
            target, reward_cfg,
        )
        assert reward_cfg.failed_reward <= awful <= 0.0

    def test_reward_never_returns_nan(self, target, reward_cfg):
        r = reward(_device(vn_in_vrms=1e-30), _link(eye_h_v=1e-30), target, reward_cfg)
        assert math.isfinite(r)


class TestWorstCorner:
    """§12 trap 1: optimise on the worst corner from the start."""

    def test_takes_the_minimum(self):
        assert worst_corner_reward([0.0, -0.1, -2.0, -0.3]) == -2.0

    def test_a_single_bad_corner_dominates(self):
        # 44 perfect corners and one failure is a failed design (S9).
        assert worst_corner_reward([0.0] * 44 + [-8.0]) == -8.0

    def test_empty_is_an_error_not_a_pass(self):
        with pytest.raises(ValueError, match="empty corner set is a bug"):
            worst_corner_reward([])

    def test_nan_is_rejected(self):
        with pytest.raises(ValueError, match="nan"):
            worst_corner_reward([0.0, float("nan")])

    def test_end_to_end_over_the_real_corner_grid(self, ref_params, target,
                                                  link_cfg, reward_cfg):
        from nebula.common.types import all_corners

        per_corner = []
        for c in all_corners():
            d = device_mock.evaluate(ref_params, c)
            l = link_mock.evaluate_link(d, link_cfg)
            per_corner.append(reward(d, l, target, reward_cfg))

        assert len(per_corner) == 45
        worst = worst_corner_reward(per_corner)
        nominal = per_corner[0]   # all_corners() puts TT/1.00/27 first
        # The whole contribution in one assertion: scoring at nominal is
        # optimistic relative to scoring at the worst corner.
        assert worst <= nominal


class TestTotalReward:
    def test_adds_the_discriminator_penalty(self):
        assert total_reward(-1.5, -0.25) == pytest.approx(-1.75)

    def test_defaults_to_no_discriminator(self):
        assert total_reward(-1.5) == pytest.approx(-1.5)

    def test_a_positive_discriminator_term_is_rejected(self):
        # A positive OOD term would pay the policy to leave the surrogate's
        # trust region — the opposite of the paper's Eq. 3-4.
        with pytest.raises(ValueError, match="non-positive"):
            total_reward(-1.5, 0.25)


class TestSignature:
    def test_make_reward_fn_gives_the_5_1_signature(self, reward_cfg, target):
        import inspect

        fn = make_reward_fn(reward_cfg)
        assert list(inspect.signature(fn).parameters) == ["dev", "link", "target"]
        assert fn(_device(), _link(), target) == 0.0
