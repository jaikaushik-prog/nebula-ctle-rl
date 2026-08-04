"""
link/mock.py — SYNTHETIC stand-in for the device->link bridge.

======================================================================
  EVERY NUMBER THIS MODULE PRODUCES IS FAKE.
  It is not the statistical eye engine. No value from here may appear
  in the abstract, report, slides or results table (§8 rule 1).
======================================================================

The real implementation fits the ngspice AC sweep onto (g_dc, f_zero, f_pole1,
f_pole2), instantiates `python_models/rx_frontend.py::CTLE`, runs the pulse
response through `python_models/statistical_eye.py::StatisticalEye` with
`n_dfe=1`, and reads eye height / width off the BER bathtub. That is a
retarget job (112G PAM-4 -> 5 Gbps NRZ, CLAUDEwa.md §4.3) and it is not this
file.

What this file *does* do faithfully, because these are the parts the other two
layers integrate against:

* it consumes a `DeviceResult` through its poles, not through its raw AC
  array — i.e. it exercises the actual pole-zero bridge path;
* it propagates `ok=False` instead of substituting zeros;
* it converts to volts through `nebula.link.calibration` and nowhere else,
  so a calibration bug shows up in the mock as loudly as in the real thing;
* its eye responds monotonically to under- and over-equalisation, and its BER
  responds to input-referred noise, so a reward function that games this mock
  would game the real one too.

Trust the shape. Never the values.
"""

from __future__ import annotations

import math

import numpy as np

from nebula.common import design_equations as deq
from nebula.common.types import DeviceResult, LinkResult
from nebula.link.calibration import (
    NRZ_IDEAL_EYE_NORM,
    check_compression,
    normalized_to_volts,
    output_swing_pp_v,
)
from nebula.link.config import LinkConfig
from nebula.link.interface import propagate_device_failure

# ── Synthetic bridge constants. Invented, not measured. ─────────────────────
_ISI_PER_DB = 1.0 / 20.0     # normalised ISI tap produced per dB of mismatch
_ISI_TAP_CAP = 0.45          # a tap this large already closes the eye
_TAIL_ISI_FRACTION = 0.30    # postcursors beyond tap 1, which a 1-tap DFE
                             # cannot cancel
_SLOPE_UI_PER_ISI = 1.2      # eye-width closure per unit of residual ISI


def evaluate_link(dev: DeviceResult, cfg: LinkConfig) -> LinkResult:
    """(DeviceResult, LinkConfig) -> LinkResult. Never raises."""
    failed = propagate_device_failure(dev)
    if failed is not None:
        return failed

    try:
        assert dev.g_dc is not None and dev.vout_swing_v is not None
        assert dev.vn_in_vrms is not None

        # ── the bridge: poles -> CTLE response, exactly as the real one ─────
        ss = deq.SmallSignal(
            g_dc=dev.g_dc,
            f_zero_hz=dev.f_zero_hz,       # type: ignore[arg-type]
            f_pole1_hz=dev.f_pole1_hz,     # type: ignore[arg-type]
            f_pole2_hz=dev.f_pole2_hz,     # type: ignore[arg-type]
            peaking_db=dev.peaking_db,     # type: ignore[arg-type]
        )
        f_ny = cfg.nyquist_hz
        dc_db = 20.0 * math.log10(dev.g_dc)
        gain_at_nyquist = deq.gain_linear(f_ny, ss)
        boost_at_nyquist_db = deq.transfer_db(f_ny, ss) - dc_db

        # ── residual ISI after the CTLE, before the DFE ─────────────────────
        # The CTLE's boost is RELATIVE (|H(f_nyq)|/|H(0)|), so what it
        # equalises is the channel's TILT, not its absolute loss. Comparing
        # against absolute loss assumes a channel that is lossless at DC.
        # > 0 : under-equalised, energy spills into postcursors
        # < 0 : over-equalised, energy spills into the precursor
        mismatch_db = cfg.channel_tilt_db - boost_at_nyquist_db
        if mismatch_db >= 0.0:
            h_post1 = min(mismatch_db * _ISI_PER_DB, _ISI_TAP_CAP)
            h_pre = 0.0
        else:
            h_post1 = 0.0
            h_pre = min(-mismatch_db * _ISI_PER_DB, _ISI_TAP_CAP)

        # A 1-tap DFE (S2) cancels the first postcursor exactly and nothing
        # else. The precursor and the postcursor tail survive.
        dfe_tap = h_post1
        h_residual = _TAIL_ISI_FRACTION * h_post1 + h_pre

        eye_h_norm = max(NRZ_IDEAL_EYE_NORM * (1.0 - 2.0 * h_residual), 0.0)

        # ── output swing (convention C3) ────────────────────────────────────
        # Two different amplitudes matter, and confusing them is how the eye
        # and the compression check end up disagreeing:
        #
        #   eye     <- the Nyquist content, lifted by the PEAKED gain. Not
        #              g_dc: |H(f_nyq)| is 3-12 dB above it by construction (S3).
        #   swing   <- the LARGEST excursion the stage has to produce linearly,
        #              which is the greater of the equalised Nyquist level and
        #              the long-run level (DC amplitude through the DC gain).
        #              A run of identical bits sits at the latter.
        v_out_pp = output_swing_pp_v(
            gain_at_signal_band=gain_at_nyquist,
            v_in_diff_pp_v=cfg.v_in_nyquist_pp_v,
        )
        v_out_lf = dev.g_dc * cfg.v_in_diff_pp_v
        v_out_peak = max(v_out_pp, v_out_lf)

        # ── compression is a VALIDITY CHECK, not a clamp (convention C4) ────
        # If the stage is compressing, the AC/pole-zero model behind every
        # number in this DeviceResult has stopped describing the circuit, so
        # there is no eye to report. Clamping here would let the policy find
        # and colonise the compressed region, where every proposal scores as
        # though it cleanly delivered the compression limit.
        compressed = check_compression(
            v_out_peak, dev.vout_swing_v, margin=cfg.compression_margin
        )
        if compressed is not None:
            return LinkResult.failed(compressed)

        # Input-referred noise against the signal amplitude the eye is built
        # from (one normalised unit = half the differential peak-to-peak
        # swing, convention C1/C3).
        sigma_norm = dev.vn_in_vrms / (cfg.v_in_nyquist_pp_v / 2.0)
        # CTLE noise enhancement: the boost that lifts the signal at Nyquist
        # lifts the noise there too. This is the S3-vs-S5 tension.
        sigma_norm *= 10.0 ** (max(boost_at_nyquist_db, 0.0) / 40.0)

        if sigma_norm <= 0.0 or eye_h_norm <= 0.0:
            ber = 0.5
        else:
            ber = _q(eye_h_norm / 2.0 / sigma_norm)

        # ── volts. THE conversion, and it happens here only. ────────────────
        eye_h_v = normalized_to_volts(eye_h_norm, v_out_pp)

        # ── eye width ───────────────────────────────────────────────────────
        eye_w_ui = 1.0 - _SLOPE_UI_PER_ISI * h_residual - 6.0 * cfg.rj_ui_rms
        eye_w_ui = float(min(max(eye_w_ui, 0.0), 1.0))

        bathtub = _synthetic_bathtub(eye_w_ui, ber)

        return LinkResult(
            ok=True,
            eye_h_v=eye_h_v,
            eye_w_ui=eye_w_ui,
            ber=ber,
            dfe_tap=dfe_tap,
            bathtub=bathtub,
        )
    except BaseException as exc:  # noqa: BLE001 — §8 rule 2
        return LinkResult.failed(f"mock link {type(exc).__name__}: {exc}")


class MockLink:
    """Class form of `evaluate_link`, satisfying the `LinkEvaluator` protocol."""

    def evaluate_link(self, dev: DeviceResult, cfg: LinkConfig) -> LinkResult:
        return evaluate_link(dev, cfg)


def _q(x: float) -> float:
    """Gaussian tail Q(x) = 0.5*erfc(x/sqrt(2)).

    NRZ, so one crossing per decision — no PAM-4 0.75 prefactor. That
    prefactor in `statistical_eye.py` is one of the four PAM-4 assumptions
    CLAUDEwa.md §4.3 lists as needing audit during the retarget.
    """
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def _synthetic_bathtub(eye_w_ui: float, ber_min: float, n: int = 101) -> np.ndarray:
    """A BER-vs-phase curve with the right qualitative shape."""
    phase = np.linspace(-0.5, 0.5, n)
    if eye_w_ui <= 0.0:
        return np.full(n, 0.5)
    edge = eye_w_ui / 2.0
    excess = np.clip((np.abs(phase) - edge) / max(edge, 1e-6), 0.0, None)
    log_ber = math.log10(max(ber_min, 1e-300)) + excess * (
        math.log10(0.5) - math.log10(max(ber_min, 1e-300))
    )
    return np.clip(10.0 ** log_ber, 0.0, 0.5)
