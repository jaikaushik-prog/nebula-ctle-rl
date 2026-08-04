"""
Interface tests for common/types.py.

These test the CONTRACT, not an implementation: field names, units, the
ok/None invariant, and the S9 corner grid. If one of these fails, three
workstreams are about to disagree with each other.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from nebula.common import types as T
from nebula.common.types import (
    Corner,
    DeviceResult,
    LinkResult,
    TargetSpec,
    all_corners,
)


# ── the field lists, transcribed from CLAUDEwa.md §5.1 ──────────────────────

CORNER_FIELDS = ["process", "vdd_scale", "temp_c"]

TARGET_FIELDS = [
    "peaking_db", "f_peak_hz", "hd3_max_dbc", "vn_in_max_vrms",
    "power_max_w", "area_max_mm2", "eye_h_min_v", "eye_w_min_ui",
]

DEVICE_FIELDS = [
    "ok", "fail_reason", "g_dc", "f_zero_hz", "f_pole1_hz", "f_pole2_hz",
    "fit_residual_db", "peaking_db", "f_peak_hz", "hd3_dbc", "vn_in_vrms",
    "power_w", "area_mm2", "vout_swing_v", "ac_freq_hz", "ac_mag_db",
]

LINK_FIELDS = ["ok", "eye_h_v", "eye_w_ui", "ber", "dfe_tap", "bathtub"]


def _names(cls) -> list[str]:
    return [f.name for f in dataclasses.fields(cls)]


class TestFieldNames:
    """§5.1 is the contract. Renaming a field is a three-person breakage."""

    def test_corner_fields_match_spec(self):
        assert _names(Corner) == CORNER_FIELDS

    def test_target_spec_fields_match_spec(self):
        assert _names(TargetSpec) == TARGET_FIELDS

    def test_device_result_fields_match_spec(self):
        assert _names(DeviceResult) == DEVICE_FIELDS

    def test_link_result_carries_every_spec_field(self):
        # LinkResult gains `fail_reason` beyond §5.1 so that a failure says
        # why; the §5.1 fields must still all be present and in order.
        assert _names(LinkResult)[: len(LINK_FIELDS)] == LINK_FIELDS

    def test_corner_and_target_are_frozen(self):
        assert Corner.__dataclass_params__.frozen
        assert TargetSpec.__dataclass_params__.frozen

    def test_results_are_not_frozen(self):
        # §5.1 declares these as plain dataclasses; they hold ndarrays and are
        # normalised in __post_init__.
        assert not DeviceResult.__dataclass_params__.frozen
        assert not LinkResult.__dataclass_params__.frozen


class TestSpecConstants:
    """Every constant traceable to a row of the §3 table."""

    def test_signalling(self):
        assert T.BAUD_RATE_HZ == 5.0e9              # S1
        assert T.NYQUIST_HZ == T.BAUD_RATE_HZ / 2   # S1
        assert T.UI_SECONDS == pytest.approx(200e-12)

    def test_spec_table(self):
        assert T.SPEC_PEAKING_DB_RANGE == (3.0, 12.0)          # S3
        assert T.SPEC_F_PEAK_HZ_RANGE == (1.25e9, 2.5e9)       # S3
        assert T.SPEC_HD3_MAX_DBC == -30.0                     # S4
        assert T.SPEC_VN_IN_MAX_VRMS == 1.5e-3                 # S5
        assert T.SPEC_POWER_MAX_W == 15e-3                     # S6
        assert T.SPEC_AREA_MAX_MM2 == 0.05                     # S7
        assert T.SPEC_EYE_H_MIN_V == 100e-3                    # S8
        assert T.SPEC_EYE_W_MIN_UI == 0.4                      # S8

    def test_peak_range_lies_inside_the_signalling_band(self):
        # S3 says the peak sits in 1.25-2.5 GHz, i.e. between fbaud/4 and
        # Nyquist. Catches a 112G default leaking in (CLAUDEwa.md §12).
        lo, hi = T.SPEC_F_PEAK_HZ_RANGE
        assert lo == pytest.approx(T.BAUD_RATE_HZ / 4)
        assert hi == pytest.approx(T.NYQUIST_HZ)


class TestCornerGrid:
    """S9: 5 process x 3 VDD x 3 temp, and every spec must hold at all of them."""

    def test_grid_is_45_corners(self):
        corners = all_corners()
        assert len(corners) == 45
        assert len(set(corners)) == 45

    def test_nominal_is_first(self):
        # Truncated fidelity tiers must always evaluate TT/1.00/27 first.
        assert all_corners()[0] == T.TT_NOMINAL
        assert all_corners()[0].is_nominal

    def test_grid_axes(self):
        corners = all_corners()
        assert {c.process for c in corners} == set(T.PROCESS_CORNERS)
        assert {c.vdd_scale for c in corners} == {0.95, 1.00, 1.05}
        assert {c.temp_c for c in corners} == {0.0, 27.0, 125.0}

    def test_corner_is_hashable_and_usable_as_a_dict_key(self):
        # Per-corner result caches depend on this.
        assert len({Corner("tt", 1.0, 27.0), Corner("tt", 1.0, 27.0)}) == 1

    def test_corner_tag_is_stable_and_filesystem_safe(self):
        tag = str(Corner("ss", 0.95, 125.0))
        assert tag == "ss_vdd0.95_t125"
        assert not set(tag) & set(' /\\:*?"<>|')

    def test_rejects_unknown_process(self):
        with pytest.raises(ValueError, match="process must be one of"):
            Corner("xx", 1.0, 27.0)  # type: ignore[arg-type]


class TestTargetSpec:
    def test_pcie_gen2_transcribes_the_fixed_constraints(self):
        s = TargetSpec.pcie_gen2(peaking_db=6.0, f_peak_hz=2.0e9)
        assert s.hd3_max_dbc == T.SPEC_HD3_MAX_DBC
        assert s.vn_in_max_vrms == T.SPEC_VN_IN_MAX_VRMS
        assert s.power_max_w == T.SPEC_POWER_MAX_W
        assert s.area_max_mm2 == T.SPEC_AREA_MAX_MM2
        assert s.eye_h_min_v == T.SPEC_EYE_H_MIN_V
        assert s.eye_w_min_ui == T.SPEC_EYE_W_MIN_UI

    def test_pcie_gen2_requires_the_tunable_point(self):
        # There is no defensible default operating point inside S3, so the
        # caller must state it. Both arguments are positional-or-keyword and
        # neither has a default.
        with pytest.raises(TypeError):
            TargetSpec.pcie_gen2()  # type: ignore[call-arg]

    @pytest.mark.parametrize("peaking", [2.9, 12.1, -1.0])
    def test_rejects_peaking_outside_s3(self, peaking):
        with pytest.raises(ValueError, match="S3 tunable range"):
            TargetSpec.pcie_gen2(peaking_db=peaking, f_peak_hz=2.0e9)

    @pytest.mark.parametrize("f_peak", [1.0e9, 3.0e9, 28e9])
    def test_rejects_f_peak_outside_s3(self, f_peak):
        # 28e9 is the 112G CTLE pole default — exactly the §12 trap.
        with pytest.raises(ValueError, match="outside the S3 range"):
            TargetSpec.pcie_gen2(peaking_db=6.0, f_peak_hz=f_peak)

    def test_as_vector_is_declaration_ordered(self):
        s = TargetSpec.pcie_gen2(peaking_db=6.0, f_peak_hz=2.0e9)
        v = s.as_vector()
        assert v.shape == (len(TARGET_FIELDS),)
        assert np.allclose(v, [getattr(s, n) for n in TARGET_FIELDS])

    def test_is_immutable(self):
        s = TargetSpec.pcie_gen2(peaking_db=6.0, f_peak_hz=2.0e9)
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.power_max_w = 1.0  # type: ignore[misc]


# ── the ok/None invariant — §8 rules 1 and 2 ────────────────────────────────


def _ok_device(**over) -> DeviceResult:
    base = dict(
        ok=True, fail_reason=None, g_dc=4.0, f_zero_hz=1.0e9,
        f_pole1_hz=2.0e9, f_pole2_hz=8.0e9, fit_residual_db=0.05,
        peaking_db=6.0, f_peak_hz=2.0e9, hd3_dbc=-40.0, vn_in_vrms=1.0e-3,
        power_w=10e-3, area_mm2=0.02, vout_swing_v=0.6,
        ac_freq_hz=np.array([1e6, 1e9]), ac_mag_db=np.array([12.0, 14.0]),
    )
    base.update(over)
    return DeviceResult(**base)  # type: ignore[arg-type]


class TestResultInvariant:
    def test_ok_result_constructs(self):
        d = _ok_device()
        assert d.ok and d.fail_reason is None
        assert d.g_dc_db == pytest.approx(20 * np.log10(4.0))

    def test_failed_result_has_no_numbers(self):
        d = DeviceResult.failed("ngspice: singular matrix at node vout")
        assert d.ok is False
        assert "singular matrix" in d.fail_reason
        for name in T.DEVICE_NUMERIC_FIELDS:
            assert getattr(d, name) is None

    def test_failed_requires_a_specific_reason(self):
        for reason in ("", "   "):
            with pytest.raises(ValueError, match="non-empty"):
                DeviceResult.failed(reason)

    def test_ok_true_with_a_missing_number_is_rejected(self):
        # This is the failure mode the invariant exists to catch: a wrapper
        # that half-populates a result and calls it a success.
        with pytest.raises(ValueError, match="ok=True but power_w is None"):
            _ok_device(power_w=None)

    def test_ok_true_with_a_fail_reason_is_rejected(self):
        with pytest.raises(ValueError, match="must not carry a fail_reason"):
            _ok_device(fail_reason="converged, mostly")

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_nan_and_inf_are_rejected_on_success(self, bad):
        # nan is the dangerous one: it propagates through a reward silently.
        with pytest.raises(ValueError, match="must be reported as"):
            _ok_device(vn_in_vrms=bad)

    def test_failed_result_may_not_carry_numbers(self):
        with pytest.raises(ValueError, match="ok=False but"):
            DeviceResult(
                ok=False, fail_reason="did not converge", g_dc=4.0,
                f_zero_hz=None, f_pole1_hz=None, f_pole2_hz=None,
                fit_residual_db=None, peaking_db=None, f_peak_hz=None,
                hd3_dbc=None, vn_in_vrms=None, power_w=None, area_mm2=None,
                vout_swing_v=None,
            )

    def test_ok_result_must_carry_the_ac_sweep(self):
        with pytest.raises(ValueError, match="raw AC sweep"):
            _ok_device(ac_freq_hz=None)

    def test_ac_arrays_must_agree_in_shape(self):
        with pytest.raises(ValueError, match="same shape"):
            _ok_device(ac_freq_hz=np.array([1e6, 1e9]), ac_mag_db=np.array([1.0]))

    def test_g_dc_db_refuses_on_a_failed_result(self):
        with pytest.raises(ValueError, match="failed DeviceResult"):
            _ = DeviceResult.failed("nope").g_dc_db

    def test_link_result_invariant(self):
        good = LinkResult(ok=True, eye_h_v=0.15, eye_w_ui=0.55, ber=1e-15, dfe_tap=0.2)
        assert good.eye_h_mv == pytest.approx(150.0)

        bad = LinkResult.failed("device evaluation failed: no convergence")
        assert bad.ok is False and bad.eye_h_v is None

        with pytest.raises(ValueError, match="ber must lie"):
            LinkResult(ok=True, eye_h_v=0.15, eye_w_ui=0.55, ber=1.5, dfe_tap=0.2)
