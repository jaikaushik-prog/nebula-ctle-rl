"""
Tests for the action space. CLAUDEwa.md §5.2 and §8 rule 6.

The load-bearing test in this file is `test_bounds_are_either_unset_or_fully
_provenanced`. It enforces the rule that an agent must not invent parameter
ranges: the space is either empty (and raises loudly) or completely populated
with every bound traceable to the G1 hand-design. There is no state in which
a guessed number sits quietly in the middle of the action space.

The normalisation maths is tested against a synthetic space, so it is fully
covered before G1 lands.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.common import params as P
from nebula.common.params import ParamBound, ParamSpaceNotSetError


class TestParameterNames:
    def test_dimensionality_matches_5_2(self):
        # §5.2: "roughly 14-16 dimensions". 12 silicon parameters plus the
        # DFE tap, which is explicitly not silicon and not in the action space.
        assert 10 <= P.n_dims() <= 16

    def test_names_cover_every_group_in_5_2(self):
        names = set(P.PARAM_NAMES)
        assert {"w_in", "l_in", "nf_in"} <= names                       # input pair
        assert {"w_tail", "l_tail", "nf_tail", "i_bias"} <= names       # tail
        assert {"rs", "cs"} <= names                                    # degeneration
        assert {"rl", "cl"} <= names                                    # load
        assert {"vcm_in"} <= names                                      # bias

    def test_the_dfe_tap_is_not_in_the_action_space(self):
        # §5.2: "not silicon, adapted in the link layer".
        assert "dfe_tap" not in P.PARAM_NAMES
        assert "dfe_tap" in P.NON_SILICON_PARAMS

    def test_names_are_unique_and_ordered(self):
        assert len(set(P.PARAM_NAMES)) == len(P.PARAM_NAMES)
        assert isinstance(P.PARAM_NAMES, tuple)   # order is the action order

    def test_integer_params_are_declared(self):
        assert P.INTEGER_PARAMS <= set(P.PARAM_NAMES)
        assert "nf_in" in P.INTEGER_PARAMS


class TestBoundsGate:
    """§8 rule 6, mechanised."""

    def test_bounds_are_either_unset_or_fully_provenanced(self):
        if not P.is_populated():
            with pytest.raises(ParamSpaceNotSetError, match="G1 hand-design"):
                P.param_space()
            return

        # Once a human fills them in, this is what they must satisfy.
        space = P.param_space()
        assert len(space) == len(P.PARAM_NAMES)
        for b in space:
            assert b.provenance.strip(), f"{b.name} has no provenance"
            assert b.lo < b.hi
            assert math.isfinite(b.lo) and math.isfinite(b.hi)
            assert b.unit.strip()

    def test_a_partially_populated_space_is_rejected(self, monkeypatch):
        partial = {
            "w_in": ParamBound("w_in", 1e-6, 50e-6, "m", False, "test fixture"),
        }
        monkeypatch.setattr(P, "BOUNDS", partial)
        with pytest.raises(ParamSpaceNotSetError, match="partially set"):
            P.param_space()

    def test_unknown_names_are_rejected(self, monkeypatch):
        full = {n: ParamBound(n, 1.0, 2.0, "u", False, "test") for n in P.PARAM_NAMES}
        full["w_mystery"] = ParamBound("w_mystery", 1.0, 2.0, "u", False, "test")
        monkeypatch.setattr(P, "BOUNDS", full)
        with pytest.raises(ParamSpaceNotSetError, match="not in PARAM_NAMES"):
            P.param_space()

    def test_a_bound_without_provenance_cannot_be_constructed(self):
        for empty in ("", "   "):
            with pytest.raises(ValueError, match="provenance"):
                ParamBound("w_in", 1e-6, 50e-6, "m", False, empty)

    def test_inverted_bounds_are_rejected(self):
        with pytest.raises(ValueError, match="lo < hi"):
            ParamBound("w_in", 50e-6, 1e-6, "m", False, "test")

    def test_log_scaled_bounds_must_be_positive(self):
        with pytest.raises(ValueError, match="log_scale requires lo > 0"):
            ParamBound("i_bias", 0.0, 10e-3, "A", True, "test")


# ── the normalisation maths, on a synthetic space ───────────────────────────

SYNTHETIC = (
    ParamBound("w_in", 1e-6, 100e-6, "m", False, "test fixture, not a design"),
    ParamBound("nf_in", 1.0, 8.0, "count", False, "test fixture, not a design"),
    ParamBound("i_bias", 100e-6, 10e-3, "A", True, "test fixture, not a design"),
)


class TestNormalisation:
    def test_zero_maps_to_the_lower_bound(self):
        out = P.denormalize([0.0, 0.0, 0.0], SYNTHETIC)
        assert out["w_in"] == pytest.approx(1e-6)
        assert out["i_bias"] == pytest.approx(100e-6)

    def test_one_maps_to_the_upper_bound(self):
        out = P.denormalize([1.0, 1.0, 1.0], SYNTHETIC)
        assert out["w_in"] == pytest.approx(100e-6)
        assert out["i_bias"] == pytest.approx(10e-3)

    def test_linear_midpoint_hand_computed(self):
        # 1 um + 0.5*(100 - 1) um = 50.5 um
        out = P.denormalize([0.5, 0.0, 0.0], SYNTHETIC)
        assert out["w_in"] == pytest.approx(50.5e-6)

    def test_log_midpoint_is_geometric_hand_computed(self):
        # sqrt(100 uA * 10 mA) = sqrt(1e-6) = 1 mA
        out = P.denormalize([0.0, 0.0, 0.5], SYNTHETIC)
        assert out["i_bias"] == pytest.approx(1e-3)

    def test_integer_params_are_rounded(self):
        # nf_in spans 1..8; 0.5 -> 4.5 -> 4 (banker's rounding on .5)
        out = P.denormalize([0.0, 0.5, 0.0], SYNTHETIC)
        assert out["nf_in"] == float(round(4.5))
        assert out["nf_in"] == out["nf_in"] // 1     # integral

    def test_integer_params_never_go_below_one(self):
        out = P.denormalize([0.0, 0.0, 0.0], SYNTHETIC)
        assert out["nf_in"] >= 1.0

    def test_out_of_range_actions_are_clipped_not_rejected(self):
        # PPO's Gaussian head puts mass outside [0,1] by construction. That is
        # normal, not an error condition.
        out = P.denormalize([-3.0, 5.0, 2.0], SYNTHETIC)
        assert out["w_in"] == pytest.approx(1e-6)
        assert out["i_bias"] == pytest.approx(10e-3)

    def test_nan_actions_are_rejected(self):
        with pytest.raises(ValueError, match="nan/inf"):
            P.denormalize([float("nan"), 0.5, 0.5], SYNTHETIC)

    def test_wrong_dimensionality_is_rejected(self):
        with pytest.raises(ValueError, match="expected 3 action dims"):
            P.denormalize([0.5, 0.5], SYNTHETIC)

    def test_round_trip_is_exact_for_continuous_params(self):
        x = np.array([0.17, 0.0, 0.83])
        params = P.denormalize(x, SYNTHETIC)
        back = P.normalize(params, SYNTHETIC)
        assert back[0] == pytest.approx(x[0])
        assert back[2] == pytest.approx(x[2])

    def test_normalize_reports_missing_params(self):
        with pytest.raises(KeyError, match="i_bias"):
            P.normalize({"w_in": 10e-6, "nf_in": 4.0}, SYNTHETIC)

    def test_normalize_rejects_a_nonpositive_log_param(self):
        with pytest.raises(ValueError, match="log-scaled"):
            P.normalize({"w_in": 10e-6, "nf_in": 4.0, "i_bias": 0.0}, SYNTHETIC)

    def test_denormalize_falls_back_to_the_real_space(self):
        # With BOUNDS unset this must raise the gate error, not silently
        # invent a space.
        if not P.is_populated():
            with pytest.raises(ParamSpaceNotSetError):
                P.denormalize([0.5] * P.n_dims())


class TestHeadroomPreFilter:
    """The (i_bias, rl) coupling the axis-aligned box cannot express.

    Measured: 7.3% of Latin-hypercube samples of BOUNDS violate this and are
    wasted ngspice calls. Rejecting them costs a multiply.
    """

    def test_the_g1_reference_point_passes(self):
        ref = dict(i_bias=5e-3, rl=120.0, vcm_in=0.88)
        assert P.headroom_ok(ref) is None

    def test_high_current_into_high_load_is_rejected(self):
        # 12 mA x 500 ohm / 2 = 3.0 V of drop into a 1.2 V supply. Both values
        # are individually inside their bounds; the pair is not feasible.
        reason = P.headroom_ok(dict(i_bias=12e-3, rl=500.0, vcm_in=0.88))
        assert reason is not None
        assert "jointly infeasible" in reason

    def test_low_current_makes_high_load_feasible_again(self):
        # 1 mA x 500 ohm / 2 = 0.25 V. Fine — which is why rl's ceiling stays.
        assert P.headroom_ok(dict(i_bias=1e-3, rl=500.0, vcm_in=0.88)) is None

    def test_vcm_above_supply_is_rejected(self):
        assert P.headroom_ok(dict(i_bias=5e-3, rl=120.0, vcm_in=1.3)) is not None

    def test_it_is_necessary_not_sufficient(self):
        # Passing the pre-filter says nothing about saturation, S3 or noise.
        # Documented so nobody mistakes it for a feasibility oracle.
        assert "necessary" in P.headroom_ok.__doc__
        assert "not a sufficient" in P.headroom_ok.__doc__

    def test_bad_params_return_a_reason_not_an_exception(self):
        assert P.headroom_ok({}) is not None

    def test_bounds_are_declared_against_the_g1_supply(self):
        assert P.G1_VDD_V == 1.2
