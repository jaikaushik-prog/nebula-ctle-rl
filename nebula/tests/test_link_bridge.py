"""
The device->link bridge: G2's deliverable.

WHAT THESE PIN
--------------
1. **The mV path carries volts and never multiplies a normalised amplitude by
   one** (§5.3a). Checked with a hand-computed expected value.
2. **Compression is a validity condition, never a clamp** (calibration C4). A
   clamped eye is indistinguishable from a legitimately swing-limited one, and
   a policy hunting eye height would live in the clamped region.
3. **Every numeric field of the contract is MEASURED or the result FAILS.**
   No `hd3_dbc`, no area, no swing -> a named failure, not an invented number.
4. **A rejected fit becomes a failed evaluation**, per §5.3b's own wording.
5. **The bridge never raises**, whatever it is handed (§8 rule 2).
6. **S8 enters the reward without moving V1**, so the +8.950669 ceiling and
   every published reward number still reproduce.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.common.types import (
    SPEC_EYE_H_MIN_V,
    SPEC_EYE_W_MIN_UI,
    DeviceResult,
    LinkResult,
)
from nebula.link.bridge import (
    BridgeDetail,
    device_result_from_point,
    evaluate_link,
    swing_for_compression_check,
)
from nebula.link.config import LinkConfig
from nebula.link.cursors import cursors_from_pulse, eye_opening_vs_phase


def _device(**kw) -> DeviceResult:
    """A DeviceResult with every field populated. Synthetic but self-consistent."""
    f = np.logspace(6, 11, 251)
    d = dict(g_dc=1.45, f_zero_hz=0.27e9, f_pole1_hz=0.95e9, f_pole2_hz=5.6e9)
    d.update({k: v for k, v in kw.items() if k in d})
    s = 1j * f
    h = d["g_dc"] * (1 + s / d["f_zero_hz"]) / (
        (1 + s / d["f_pole1_hz"]) * (1 + s / d["f_pole2_hz"]))
    base = dict(
        ok=True, fail_reason=None, fit_residual_db=0.02,
        peaking_db=9.7, f_peak_hz=2.19e9, hd3_dbc=-61.0,
        vn_in_vrms=0.29e-3, power_w=5.3e-3, area_mm2=0.0011,
        vout_swing_v=1.96, ac_freq_hz=f, ac_mag_db=20 * np.log10(np.abs(h)),
        **d)
    base.update({k: v for k, v in kw.items() if k not in d})
    return DeviceResult(**base)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Volts, end to end.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_eye_comes_back_in_volts_not_normalised():
    """§5.3a in its strongest form: there is no conversion to get wrong.

    The pulse response carries the transmitter's specified swing, the channel
    is a unitless attenuation and the CTLE contributes its measured `g_dc`, so
    `eye_h_v` is volts by construction. A normalised eye would be O(1); a
    volts eye at a 0.8 Vpp transmitter is O(0.1-1).
    """
    dev = _device()
    lr = evaluate_link(dev, LinkConfig(channel_loss_db_at_nyquist=12.0))
    assert lr.ok, lr.fail_reason
    assert 0.05 < lr.eye_h_v < 2.0, "not a volts-scale eye"
    assert lr.eye_h_mv == pytest.approx(lr.eye_h_v * 1e3)


def test_eye_height_is_exactly_twice_the_cursor_minus_residual():
    """The hand-computable identity the eye rests on.

    `eye_h_v = 2*(h0 - sum|h_k|)` over k != 0, 1 — the cursor, minus every
    tap an ideal 1-tap DFE cannot cancel, doubled because the eye spans -1 to
    +1. If this drifts, every millivolt downstream is wrong.
    """
    from nebula.link.cursors import pulse_response
    from nebula.link.fit import CtleFit

    cfg = LinkConfig(channel_loss_db_at_nyquist=12.0)
    ctle = CtleFit.from_poles(1.45, 0.27e9, 0.95e9, 5.6e9)
    pr = pulse_response(cfg.channel, cfg.tx, ctle)
    cs = cursors_from_pulse(pr, 64, int(np.argmax(pr)))

    manual = 2.0 * (cs.h0_v - sum(abs(v) for k, v in cs.taps.items()
                                  if k not in (0, 1)))
    assert cs.eye_h_v == pytest.approx(max(0.0, manual), rel=1e-12)


def test_peak_excursion_is_twice_the_sum_of_all_taps():
    """G61 convention C, hand-computed. Every bit taking its worst sign."""
    from nebula.link.cursors import pulse_response
    from nebula.link.fit import CtleFit

    cfg = LinkConfig(channel_loss_db_at_nyquist=12.0)
    ctle = CtleFit.from_poles(1.45, 0.27e9, 0.95e9, 5.6e9)
    pr = pulse_response(cfg.channel, cfg.tx, ctle)
    cs = cursors_from_pulse(pr, 64, int(np.argmax(pr)))
    assert cs.peak_excursion_pp_v == pytest.approx(
        2.0 * sum(abs(v) for v in cs.taps.values()), rel=1e-12)
    # ... and it is at least the eye, since the eye subtracts what this adds.
    assert cs.peak_excursion_pp_v >= cs.eye_h_v


# ─────────────────────────────────────────────────────────────────────────────
# 2. Compression: a validity condition, not a clamp (C4).
# ─────────────────────────────────────────────────────────────────────────────


def test_a_compressing_design_FAILS_and_is_not_clamped():
    """C4's whole argument. `min(prediction, limit)` would turn an invalid
    operating point into a plausible number that an RL policy would find."""
    dev = _device(vout_swing_v=0.05)          # absurdly low limit
    lr = evaluate_link(dev, LinkConfig(channel_loss_db_at_nyquist=12.0))
    assert not lr.ok
    assert "output swing" in (lr.fail_reason or "")
    assert lr.eye_h_v is None, "a clamped eye must not be returned"


def test_the_compression_gate_is_not_always_on():
    """G73: a gate whose condition is unreachable is a deleted gate."""
    dev = _device(vout_swing_v=1.96)
    lr = evaluate_link(dev, LinkConfig(channel_loss_db_at_nyquist=12.0))
    assert lr.ok, lr.fail_reason


def test_the_margin_can_only_tighten_the_gate():
    """`check_compression`'s margin is not a knob for making designs pass."""
    dev = _device()
    strict = evaluate_link(dev, LinkConfig(channel_loss_db_at_nyquist=12.0),
                           compression_margin=0.1)
    loose = evaluate_link(dev, LinkConfig(channel_loss_db_at_nyquist=12.0),
                          compression_margin=1.0)
    assert loose.ok and not strict.ok
    from nebula.link.calibration import check_compression
    with pytest.raises(ValueError, match="stricter"):
        check_compression(1.0, 2.0, margin=1.5)


def test_a_missing_swing_limit_disables_nothing_silently():
    """`vout_swing_v=None` cannot reach here — the contract rejects it — so the
    gate cannot be silently skipped by omission."""
    with pytest.raises(ValueError, match="vout_swing_v"):
        _device(vout_swing_v=None)


def test_swing_falls_back_to_the_swept_maximum_and_says_so():
    """The bug that rejected the MOST LINEAR designs.

    A stage that never compresses across the +/-0.8 V sweep returns
    `linear_pp_v = None`, which the first version read as "unknown" and failed.
    `SwingLimits` says it is "information, not a failure". The fallback is the
    measured `max_swept_pp_v` — still measured, and a LOWER bound, so the gate
    stays conservative — and the flag records which one came back.
    """
    class _Pt:
        ok = True
        vid = np.linspace(-0.8, 0.8, 401)
        # A perfectly linear stage: gain 0.3, never compresses.
        vod = 0.3 * np.linspace(-0.8, 0.8, 401)
        sat_ok = np.ones(401, dtype=bool)
        id_min = np.full(401, 1e-3)

        class point:
            i_tail_per_side_a = 1e-3

    v, is_bound = swing_for_compression_check(_Pt())
    assert v is not None and is_bound is True
    assert v == pytest.approx(2.0 * 0.3 * 0.8, rel=0.02)


# ─────────────────────────────────────────────────────────────────────────────
# 3. The contract's every-field rule.
# ─────────────────────────────────────────────────────────────────────────────


class _FakePoint:
    """A minimal Sky130Point stand-in. Duck-typed, as the adapter is."""

    def __init__(self, **kw):
        f = np.logspace(6, 11, 251)
        s = 1j * f
        h = 1.45 * (1 + s / 0.27e9) / ((1 + s / 0.95e9) * (1 + s / 5.6e9))
        self.ok = True
        self.fail_reason = None
        self.ac_freq_hz = f
        self.ac_mag_db = 20 * np.log10(np.abs(h))
        self.g_dc_db = float(self.ac_mag_db[0])
        self.peaking_db = 9.7
        self.f_pk_hz = 2.19e9
        self.vn_in_vrms = 0.29e-3
        self.hd3_dbc = -61.0
        self.power_measured_w = 5.3e-3
        self.vid = np.linspace(-0.8, 0.8, 401)
        self.vod = 0.9 * np.tanh(np.linspace(-0.8, 0.8, 401) * 2.0)
        self.sat_ok = np.ones(401, dtype=bool)
        self.id_min = np.full(401, 1e-3)

        class _P:
            i_tail_per_side_a = 1.5e-3

            class passives:
                area_mm2 = 0.0011
                area_um2 = 1100.0
        self.point = _P()
        for k, v in kw.items():
            setattr(self, k, v)


def test_a_point_without_hd3_produces_a_NAMED_failure_not_an_invented_number():
    """§8 rule 1. `.disto` returns exactly 0.0 on BSIM4 (G21), so HD3 comes
    from the transient tier or not at all."""
    pt = _FakePoint(hd3_dbc=None)
    dev = device_result_from_point(pt)
    assert not dev.ok
    assert "hd3_dbc is missing" in (dev.fail_reason or "")


def test_a_point_without_drawn_passives_cannot_supply_S7():
    pt = _FakePoint()
    pt.point.passives = None
    dev = device_result_from_point(pt)
    assert not dev.ok
    assert "area_mm2 is missing" in (dev.fail_reason or "")


def test_a_point_without_an_ac_curve_is_refused_with_the_reason():
    pt = _FakePoint(ac_freq_hz=None)
    dev = device_result_from_point(pt)
    assert not dev.ok
    assert "ac_sweep=True" in (dev.fail_reason or "")


def test_a_rejected_fit_becomes_a_FAILED_evaluation():
    """§5.3b verbatim: "a bad fit is a failed evaluation, not a result to pass
    downstream". A resonance the 1z/2p model cannot represent."""
    pt = _FakePoint()
    f = pt.ac_freq_hz
    f0 = 2.5e9
    h = (1 + 1j * f / 0.6e9) / (1 - (f / f0) ** 2 + 1j * f / (8.0 * f0))
    pt.ac_mag_db = 20 * np.log10(np.abs(h))
    dev = device_result_from_point(pt)
    assert not dev.ok
    assert "fit rejected" in (dev.fail_reason or "")


def test_a_failed_point_propagates_rather_than_raising():
    dev = device_result_from_point(_FakePoint(ok=False, fail_reason="boom"))
    assert not dev.ok and "boom" in (dev.fail_reason or "")


def test_the_happy_path_builds_a_complete_contract():
    dev = device_result_from_point(_FakePoint())
    assert dev.ok, dev.fail_reason
    for name in ("g_dc", "f_zero_hz", "f_pole1_hz", "f_pole2_hz",
                 "fit_residual_db", "peaking_db", "f_peak_hz", "hd3_dbc",
                 "vn_in_vrms", "power_w", "area_mm2", "vout_swing_v"):
        assert getattr(dev, name) is not None, name
    # S3 comes from the MEASUREMENT, not the fitted model: every published S3
    # number in this project came from `meas ac MAX`.
    assert dev.peaking_db == 9.7
    assert dev.f_peak_hz == 2.19e9


# ─────────────────────────────────────────────────────────────────────────────
# 4. Never raises (§8 rule 2).
# ─────────────────────────────────────────────────────────────────────────────


def test_evaluate_link_propagates_a_failed_device_result():
    lr = evaluate_link(DeviceResult.failed("nope"),
                       LinkConfig(channel_loss_db_at_nyquist=12.0))
    assert not lr.ok and "nope" in (lr.fail_reason or "")


def test_evaluate_link_turns_an_internal_bug_into_ok_False():
    """A bug must cost one bad reward, not a training run."""
    class _Broken:
        ok = True
        fail_reason = None
        g_dc = float("nan")            # slips past the None checks
        f_zero_hz = 1e9
        f_pole1_hz = 2e9
        f_pole2_hz = 5e9
        fit_residual_db = 0.0
        vn_in_vrms = 1e-4
        vout_swing_v = 1.0
    lr = evaluate_link(_Broken(), LinkConfig(channel_loss_db_at_nyquist=12.0))
    assert not lr.ok
    assert lr.fail_reason


def test_missing_poles_on_an_ok_result_is_named_not_crashed():
    class _NoPoles:
        ok = True
        fail_reason = None
        g_dc = 1.0
        f_zero_hz = None
        f_pole1_hz = 2e9
        f_pole2_hz = 5e9
        fit_residual_db = 0.0
        vn_in_vrms = 1e-4
        vout_swing_v = 1.0
    lr = evaluate_link(_NoPoles(), LinkConfig(channel_loss_db_at_nyquist=12.0))
    assert not lr.ok
    assert "f_zero_hz is None" in (lr.fail_reason or "")


# ─────────────────────────────────────────────────────────────────────────────
# 5. The eye width.
# ─────────────────────────────────────────────────────────────────────────────


def test_eye_width_is_bounded_by_one_ui_and_quantised_by_the_grid():
    from nebula.link.cursors import pulse_response
    from nebula.link.fit import CtleFit

    cfg = LinkConfig(channel_loss_db_at_nyquist=12.0)
    ctle = CtleFit.from_poles(1.45, 0.27e9, 0.95e9, 5.6e9)
    pr = pulse_response(cfg.channel, cfg.tx, ctle)
    eo = eye_opening_vs_phase(pr, 64, int(np.argmax(pr)))
    assert 0.0 < eo.width_ui <= 1.0
    assert eo.phase_resolution_ui == pytest.approx(1.0 / 64)
    # the width is an integer number of phase steps
    assert eo.width_ui * 64 == pytest.approx(round(eo.width_ui * 64))


def test_more_boost_on_a_lossy_channel_opens_the_eye():
    """Monotonicity, so a reward built on this has a usable gradient."""
    from nebula.link.cursors import extract_cursors, matched_ctle

    cfg = LinkConfig(channel_loss_db_at_nyquist=12.0)
    eyes = [extract_cursors(cfg.channel, cfg.tx,
                            matched_ctle(b) if b else None).eye_h_v
            for b in (0.0, 4.0, 8.0)]
    assert eyes[0] < eyes[1] < eyes[2]


def test_the_width_scan_requires_contiguity():
    """An isolated open phase elsewhere in the UI must not inflate the width."""
    pr = np.zeros(64 * 8)
    pr[100] = 1.0                     # a single clean cursor
    eo = eye_opening_vs_phase(pr, 64, 100)
    assert eo.width_ui <= 1.0
    assert eo.eye_h_max_v == pytest.approx(2.0, rel=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# 6. S8 in the reward, without moving V1.
# ─────────────────────────────────────────────────────────────────────────────


def test_V1_specs_exclude_S8_so_published_rewards_reproduce():
    from nebula.rl import reward_v1 as R
    assert not any(n.startswith("S8_") for n in R.V1_SPECS)
    assert len(R.V1_SPECS) == 7
    # The +8.950669 ceiling is B + min margin with B = N + 1 = 8.
    assert R.feasible_bonus(len(R.V1_SPECS)) == pytest.approx(8.0)


def test_V2_specs_add_exactly_the_two_S8_rows():
    from nebula.rl import reward_v1 as R
    assert set(R.V2_SPECS) - set(R.V1_SPECS) == {"S8_eye_h", "S8_eye_w"}
    assert R.S8_SPECS == ("S8_eye_h", "S8_eye_w")


def test_S8_margins_are_measured_minus_spec_in_the_specs_own_units():
    from nebula.rl import reward_v1 as R
    meas = {"peaking_db": 9.7, "f_peak_oct": 0.0, "nyq_boost_db": 9.6,
            "inoise_vrms": 0.29e-3, "power_w": 5.3e-3,
            "pair_margin_v": 0.3, "tail_margin_v": 0.25}
    link = LinkResult(ok=True, eye_h_v=0.758, eye_w_ui=0.875, ber=0.0,
                      dfe_tap=-0.19)
    m = R.margins(meas, 2.0e9, link=link)
    assert m["S8_eye_h"] == pytest.approx(0.758 - SPEC_EYE_H_MIN_V)
    assert m["S8_eye_w"] == pytest.approx(0.875 - SPEC_EYE_W_MIN_UI)


def test_S8_rows_are_ABSENT_without_a_link_result_rather_than_defaulted():
    """Scoring an absent eye as satisfied would be worse than crashing; as
    zero-margin would make every design look like it just failed S8."""
    from nebula.rl import reward_v1 as R
    meas = {"peaking_db": 9.7, "f_peak_oct": 0.0, "nyq_boost_db": 9.6,
            "inoise_vrms": 0.29e-3, "power_w": 5.3e-3,
            "pair_margin_v": 0.3, "tail_margin_v": 0.25}
    m = R.margins(meas, 2.0e9, link=None)
    assert "S8_eye_h" not in m and "S8_eye_w" not in m
    with pytest.raises(KeyError):
        R.shortfalls(m, specs=R.V2_SPECS)


def test_a_failed_link_result_does_not_contribute_S8():
    from nebula.rl import reward_v1 as R
    meas = {"peaking_db": 9.7, "f_peak_oct": 0.0, "nyq_boost_db": 9.6,
            "inoise_vrms": 0.29e-3, "power_w": 5.3e-3,
            "pair_margin_v": 0.3, "tail_margin_v": 0.25}
    m = R.margins(meas, 2.0e9, link=LinkResult.failed("compressing"))
    assert "S8_eye_h" not in m


def test_the_S8_tolerances_are_half_the_spec_floors():
    from nebula.rl import reward_v1 as R
    assert R.TOL["S8_eye_h"] == pytest.approx(SPEC_EYE_H_MIN_V / 2.0)
    assert R.TOL["S8_eye_w"] == pytest.approx(SPEC_EYE_W_MIN_UI / 2.0)
    # ... and the width tolerance is coarser than the measurement's own grid.
    assert R.TOL["S8_eye_w"] > 1.0 / 64
