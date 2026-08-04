"""
Interface tests for the device layer.

    def evaluate(params: dict[str, float], corner: Corner) -> DeviceResult

The mock is the subject under test only incidentally. What is actually being
pinned here is the behaviour any implementation must have — above all
CLAUDEwa.md §8 rule 2:

    A failed SPICE run returns ok=False, never raises.

When the real ngspice wrapper lands, point `EVALUATORS` at it and these tests
apply unchanged.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.common.params import PARAM_NAMES
from nebula.common.types import (
    Corner,
    DeviceResult,
    TT_NOMINAL,
    all_corners,
)
from nebula.device import mock as device_mock
from nebula.device.interface import (
    DeviceEvaluator,
    reject_bad_fit,
    safe_evaluate,
)


class TestProtocolConformance:
    def test_mock_satisfies_the_evaluator_protocol(self):
        assert isinstance(device_mock.MockDevice(), DeviceEvaluator)

    def test_module_level_evaluate_matches_the_5_1_signature(self):
        import inspect

        sig = inspect.signature(device_mock.evaluate)
        assert list(sig.parameters) == ["params", "corner"]


class TestHappyPath:
    def test_reference_params_evaluate_at_nominal(self, ref_params):
        d = device_mock.evaluate(ref_params, TT_NOMINAL)
        assert d.ok, d.fail_reason

    def test_every_numeric_field_is_populated_and_finite(self, ref_params):
        d = device_mock.evaluate(ref_params, TT_NOMINAL)
        assert d.ok
        for name in (
            "g_dc", "f_zero_hz", "f_pole1_hz", "f_pole2_hz", "fit_residual_db",
            "peaking_db", "f_peak_hz", "hd3_dbc", "vn_in_vrms", "power_w",
            "area_mm2", "vout_swing_v",
        ):
            v = getattr(d, name)
            assert v is not None and math.isfinite(v), name

    def test_ac_sweep_is_returned_for_diagnostics(self, ref_params):
        d = device_mock.evaluate(ref_params, TT_NOMINAL)
        assert isinstance(d.ac_freq_hz, np.ndarray)
        assert d.ac_freq_hz.shape == d.ac_mag_db.shape
        assert d.ac_freq_hz.size > 1

    def test_pole_zero_ordering_is_physical(self, ref_params):
        # A degenerated CTLE has f_zero < f_pole1 by construction:
        # w_p1 = (1 + gm*Rs/2) * w_z with the factor > 1.
        d = device_mock.evaluate(ref_params, TT_NOMINAL)
        assert d.f_zero_hz < d.f_pole1_hz

    def test_units_are_not_confused(self, ref_params):
        # g_dc is linear V/V, never dB. A stage with 12 dB of gain has
        # g_dc = 4, so a g_dc that already looks like a dB number (say 12)
        # would be a red flag. Bound it loosely but meaningfully.
        d = device_mock.evaluate(ref_params, TT_NOMINAL)
        assert 0.0 < d.g_dc < 1000.0
        assert -200.0 < d.hd3_dbc < 0.0     # dBc, a harmonic is below carrier
        assert 0.0 < d.vn_in_vrms < 1.0     # volts rms, not millivolts
        assert 0.0 < d.power_w < 1.0        # watts, not milliwatts
        assert 0.0 < d.area_mm2 < 10.0      # mm^2, not um^2


class TestFailuresAreValuesNotExceptions:
    """§8 rule 2. Every one of these must return, not raise."""

    @pytest.mark.parametrize(
        "mutate",
        [
            pytest.param({"i_bias": -1.0}, id="negative_current"),
            pytest.param({"rs": 0.0}, id="zero_resistance"),
            pytest.param({"cs": float("nan")}, id="nan_capacitance"),
            pytest.param({"rl": float("inf")}, id="inf_resistance"),
            pytest.param({"w_in": -5e-6}, id="negative_width"),
            pytest.param({"vcm_in": 1e-9}, id="no_tail_headroom"),
            pytest.param({"rl": 1e6}, id="load_drop_exceeds_vdd"),
            pytest.param({"i_bias": 5.0}, id="amps_of_tail_current"),
        ],
    )
    def test_bad_params_return_ok_false(self, ref_params, mutate):
        params = {**ref_params, **mutate}
        d = device_mock.evaluate(params, TT_NOMINAL)
        assert isinstance(d, DeviceResult)
        assert d.ok is False
        assert d.fail_reason and d.fail_reason.strip()

    def test_missing_params_return_ok_false(self, ref_params):
        params = dict(ref_params)
        params.pop("rs")
        d = device_mock.evaluate(params, TT_NOMINAL)
        assert d.ok is False and "rs" in d.fail_reason

    def test_empty_params_return_ok_false(self):
        d = device_mock.evaluate({}, TT_NOMINAL)
        assert d.ok is False

    def test_failed_result_carries_no_numbers(self, ref_params):
        d = device_mock.evaluate({**ref_params, "i_bias": -1.0}, TT_NOMINAL)
        assert d.g_dc is None and d.power_w is None


class TestSafeEvaluate:
    """The backstop for the failures nobody predicted."""

    def test_converts_an_exception_into_ok_false(self):
        def exploding(params, corner):
            raise RuntimeError("ngspice binary not found")

        d = safe_evaluate(exploding, {}, TT_NOMINAL)
        assert d.ok is False
        assert "ngspice binary not found" in d.fail_reason
        assert "RuntimeError" in d.fail_reason

    def test_reports_the_corner_in_the_failure_reason(self):
        def exploding(params, corner):
            raise ZeroDivisionError("bad operating point")

        corner = Corner("ss", 0.95, 125.0)
        d = safe_evaluate(exploding, {}, corner)
        assert str(corner) in d.fail_reason

    def test_catches_a_wrong_return_type(self):
        d = safe_evaluate(lambda p, c: {"g_dc": 4.0}, {}, TT_NOMINAL)  # type: ignore[arg-type]
        assert d.ok is False and "expected DeviceResult" in d.fail_reason

    def test_passes_a_good_result_straight_through(self, ref_params):
        d = safe_evaluate(device_mock.evaluate, ref_params, TT_NOMINAL)
        assert d.ok


class TestFitRejection:
    """§5.3(b): a bad pole-zero fit is a failure, not a result."""

    def test_good_fit_passes(self, ref_params):
        d = device_mock.evaluate(ref_params, TT_NOMINAL)
        assert reject_bad_fit(d).ok

    def test_residual_above_half_a_db_is_rejected(self, ref_params):
        d = device_mock.evaluate(ref_params, TT_NOMINAL)
        d.fit_residual_db = 0.9
        rejected = reject_bad_fit(d)
        assert rejected.ok is False
        assert "0.900 dB" in rejected.fail_reason

    def test_rejection_threshold_is_half_a_db(self, ref_params):
        d = device_mock.evaluate(ref_params, TT_NOMINAL)
        d.fit_residual_db = 0.5
        assert reject_bad_fit(d).ok           # exactly at the limit passes
        d.fit_residual_db = 0.5001
        assert reject_bad_fit(d).ok is False

    def test_already_failed_results_pass_through_unchanged(self):
        d = DeviceResult.failed("no convergence")
        assert reject_bad_fit(d) is d


class TestCornerBehaviour:
    """S9: the same sizing, evaluated at 45 corners, must spread."""

    def test_evaluates_at_every_corner_without_raising(self, ref_params):
        results = [device_mock.evaluate(ref_params, c) for c in all_corners()]
        assert len(results) == 45
        assert all(isinstance(r, DeviceResult) for r in results)

    def test_corners_actually_change_the_answer(self, ref_params):
        # If a sizing gives identical numbers at tt/1.00/27 and ss/0.95/125,
        # the corner argument is being ignored — which would make the entire
        # corner-robustness contribution vacuous.
        tt = device_mock.evaluate(ref_params, TT_NOMINAL)
        ss = device_mock.evaluate(ref_params, Corner("ss", 0.95, 125.0))
        assert tt.ok and ss.ok
        assert tt.g_dc != pytest.approx(ss.g_dc, rel=1e-6)
        assert tt.peaking_db != pytest.approx(ss.peaking_db, rel=1e-6)

    def test_power_scales_with_supply(self, ref_params):
        lo = device_mock.evaluate(ref_params, Corner("tt", 0.95, 27.0))
        hi = device_mock.evaluate(ref_params, Corner("tt", 1.05, 27.0))
        assert lo.ok and hi.ok
        assert hi.power_w > lo.power_w

    def test_worst_corner_is_not_always_nominal(self, ref_params):
        # The whole §12 trap in one assertion.
        results = [device_mock.evaluate(ref_params, c) for c in all_corners()]
        ok = [r for r in results if r.ok]
        assert len(ok) >= 2
        worst_noise = max(r.vn_in_vrms for r in ok)
        nominal = device_mock.evaluate(ref_params, TT_NOMINAL)
        assert worst_noise > nominal.vn_in_vrms


class TestMonotonicity:
    """The mock is synthetic, but its trends must be real — a reward function
    tuned against wrong trends would have to be retuned against ngspice."""

    def test_more_tail_current_costs_more_power(self, ref_params):
        lo = device_mock.evaluate({**ref_params, "i_bias": 3e-3}, TT_NOMINAL)
        hi = device_mock.evaluate({**ref_params, "i_bias": 5e-3}, TT_NOMINAL)
        assert lo.ok and hi.ok
        assert hi.power_w > lo.power_w

    def test_more_tail_current_lowers_input_referred_noise(self, ref_params):
        # gm ~ sqrt(I), input-referred noise ~ 1/sqrt(gm). This is the S5-vs-S6
        # tension CLAUDEwa.md §3 says will be one of the two real fights.
        lo = device_mock.evaluate({**ref_params, "i_bias": 3e-3}, TT_NOMINAL)
        hi = device_mock.evaluate({**ref_params, "i_bias": 5e-3}, TT_NOMINAL)
        assert hi.vn_in_vrms < lo.vn_in_vrms

    def test_more_degeneration_raises_peaking_and_lowers_dc_gain(self, ref_params):
        lo = device_mock.evaluate({**ref_params, "rs": 300.0}, TT_NOMINAL)
        hi = device_mock.evaluate({**ref_params, "rs": 600.0}, TT_NOMINAL)
        assert lo.ok and hi.ok
        assert hi.peaking_db > lo.peaking_db     # 20*log10(1 + gm*Rs/2)
        assert hi.g_dc < lo.g_dc                 # gm*RL / (1 + gm*Rs/2)

    def test_bigger_passives_cost_area(self, ref_params):
        lo = device_mock.evaluate({**ref_params, "cs": 300e-15}, TT_NOMINAL)
        hi = device_mock.evaluate({**ref_params, "cs": 900e-15}, TT_NOMINAL)
        assert lo.ok and hi.ok
        assert hi.area_mm2 > lo.area_mm2

    def test_degeneration_improves_linearity(self, ref_params):
        lo = device_mock.evaluate({**ref_params, "rs": 200.0}, TT_NOMINAL)
        hi = device_mock.evaluate({**ref_params, "rs": 800.0}, TT_NOMINAL)
        assert lo.ok and hi.ok
        assert hi.hd3_dbc < lo.hd3_dbc           # more negative dBc is better


class TestDeterminism:
    def test_same_input_gives_the_same_answer(self, ref_params):
        a = device_mock.evaluate(ref_params, TT_NOMINAL)
        b = device_mock.evaluate(ref_params, TT_NOMINAL)
        assert a.g_dc == b.g_dc and a.vn_in_vrms == b.vn_in_vrms

    def test_evaluate_does_not_mutate_the_params_dict(self, ref_params):
        before = dict(ref_params)
        device_mock.evaluate(ref_params, TT_NOMINAL)
        assert ref_params == before

    def test_param_names_are_the_contract(self, ref_params):
        assert set(ref_params) == set(PARAM_NAMES)
