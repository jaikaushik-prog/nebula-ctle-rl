"""
link/bridge.py — the device->link bridge. THE G2 deliverable.

    device_result_from_point(pt, ...) -> DeviceResult      # measurement -> contract
    evaluate_link(dev, cfg)           -> LinkResult        # contract -> eye

CLAUDEwa.md §5 calls this "the intellectually distinctive part of this
project ... nobody else in this competition will close the loop from
transistor W/L to a BER-1e-15 eye contour."

WHAT WAS ACTUALLY MISSING, because "the link layer is a mock" overstated it
----------------------------------------------------------------------------
Most of the chain was built and tested before this file existed: the channel
family, the PCIe Gen2 transmitter, the pulse response, the cursor extraction,
the volts conversion. Two things were not, and they were both structural
rather than large:

1. **Nothing ever built a `DeviceResult`.** `device/mock.py` was the only
   constructor in the repo. `sky130_runner` produced a `Sky130Point` and
   stopped, so the real device layer and the real link layer had never been
   connected by anything — which is exactly why the mock was the only way to
   exercise the bridge, and why G16 read as "the link layer is fake" when the
   truth was "the two halves were never joined".

2. **The AC sweep was measured and thrown away.** `.ac dec 50 1meg 100g` has
   always run, but only four `meas` scalars were parsed off it. A pole-zero
   fit cannot be made to four numbers; `run_point(ac_sweep=True)` now keeps
   the curve and `link/fit.py` fits it.

THE TWO §5.3 RISKS, AND WHERE EACH IS HANDLED
----------------------------------------------
**(a) The millivolt calibration.** Handled by NOT NEEDING A CONVERSION on this
path. `cursors.pulse_response` carries volts end to end — the TX contributes
its specified differential swing, the channel is a unitless attenuation, and
the CTLE contributes its measured `g_dc` — so `CursorSet.eye_h_v` is already
in volts and nothing here multiplies a normalised amplitude by a voltage.
`link/calibration.py` is still used, for the thing it is actually load-bearing
for: **convention C4, the compression check.**

That is the calibration risk in its real form. A CTLE with 12 dB of gain
driven by a 0.8 Vpp transmitter through a 3 dB channel predicts an output
swing larger than the device can produce, and the small-signal model that
produced every pole in the `DeviceResult` stops describing the circuit. C4 is
explicit that the answer is **not** `min(prediction, limit)`: a clamp turns an
invalid operating point into a plausible number, and an RL policy searching
for eye height will find that region and live in it. So compression returns
`ok=False` with the reason.

**(b) Pole-zero fit validity.** `link/fit.py` rejects residuals above
`FIT_RESIDUAL_REJECT_DB`, and `device_result_from_point` turns a rejected fit
into `DeviceResult.failed(...)` — the contract's own instruction: *"a bad fit
is a failed evaluation, not a result to pass downstream."*

WHAT THE BER ON THIS PATH IS, AND WHAT IT IS NOT
--------------------------------------------------
`LinkResult.ber` here is a **worst-case ISI bound**, not a statistical eye:

    BER = Q( (eye_h_v / 2) / sigma_out )

with `eye_h_v` the vertical opening after an ideal 1-tap DFE at the worst ISI
pattern, and `sigma_out` the device's integrated input-referred noise referred
forward through the gain where the data is. Every ISI combination is assumed
to land at its worst simultaneously, so **this is pessimistic by construction**
— a true statistical eye averages over the ISI distribution and lands above
it.

It is used because it is *honest and available*. `python_models/
statistical_eye.py` is the semi-analytic engine that would give the real
bathtub, and its NRZ path **deliberately raises `NotImplementedError`**
(`NRZ_RETARGET_AUDIT.md`) rather than reporting a BER 0.75x the truth from
four-level mathematics. Wiring it in requires that retarget; until then this
bound is the number, and `G2_RESULTS.md` says so.

`sigma_out` uses `|H(f_nyquist)|`, and that is an APPROXIMATION worth naming:
`vn_in_vrms` is already integrated over 10 MHz - 5 GHz with the response
shaped in, so referring it forward through a single gain is not the same as
integrating the shaped noise. It is the right order and the right direction;
the statistical engine's `_compute_noise_autocorr` is what does it properly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import numpy as np

from nebula.common import design_equations as deq
from nebula.common.types import DeviceResult, LinkResult
from nebula.link.calibration import check_compression, output_swing_pp_v
from nebula.link.config import LinkConfig
from nebula.link.cursors import (
    CursorSet,
    EyeOpening,
    cursors_from_pulse,
    eye_opening_vs_phase,
    pulse_response,
)
from nebula.link.fit import CtleFit, FitError, fit_ctle
from nebula.link.interface import propagate_device_failure

if TYPE_CHECKING:                                   # pragma: no cover
    from nebula.device.sky130_runner import Sky130Point


# ─────────────────────────────────────────────────────────────────────────────
# Measurement -> the frozen contract.
# ─────────────────────────────────────────────────────────────────────────────


def device_result_from_point(pt: "Sky130Point", *,
                             area_mm2: Optional[float] = None,
                             hd3_dbc: Optional[float] = None,
                             ) -> DeviceResult:
    """`Sky130Point` (measured) -> `DeviceResult` (the §5.1 contract).

    The adapter that did not exist. Duck-typed on `pt` rather than importing
    the device layer at runtime, so `link/` keeps no runtime dependency on
    `device/` — the type is imported under `TYPE_CHECKING` only.

    **THE CONTRACT REQUIRES EVERY NUMERIC FIELD ON SUCCESS** (§8 rule 1,
    enforced in `DeviceResult.__post_init__`), so a `DeviceResult` cannot be
    built from an AC run alone. Both remaining fields are MEASURED, not
    defaulted:

    * `hd3_dbc` — read off `pt.hd3_dbc`, which needs `run_point(hd3=True)`
      (transient + FFT; `.disto` returns exactly 0.0 on BSIM4, G21);
    * `area_mm2` — computed from the drawn passives on the point itself,
      `PassiveGeometry.area_mm2`.

    Either may be passed in to override, for a caller that measured them
    another way. Neither is invented: if the run did not produce one and the
    caller did not supply one, this returns a FAILED result naming which,
    because a `DeviceResult` with a made-up HD3 is exactly the fabrication
    rule 1 forbids.
    """
    if not getattr(pt, "ok", False):
        return DeviceResult.failed(
            f"device evaluation failed: {getattr(pt, 'fail_reason', None)!r}")

    if getattr(pt, "ac_freq_hz", None) is None:
        return DeviceResult.failed(
            "this Sky130Point carries no AC curve — it was run without "
            "ac_sweep=True, and a pole-zero fit cannot be made to four "
            "`meas` scalars")

    try:
        fit = fit_ctle(pt.ac_freq_hz, pt.ac_mag_db,
                       measured_g_dc_db=getattr(pt, "g_dc_db", None))
    except FitError as exc:
        return DeviceResult.failed(f"pole-zero fit could not be attempted: {exc}")

    if not fit.ok:
        # The contract's own instruction, verbatim: "a bad fit is a FAILED
        # evaluation, not a result to pass downstream" (§5.3b).
        return DeviceResult.failed(f"pole-zero fit rejected: {fit.fail_reason}")

    if hd3_dbc is None:
        hd3_dbc = getattr(pt, "hd3_dbc", None)
    if hd3_dbc is None:
        return DeviceResult.failed(
            "hd3_dbc is missing: run_point(hd3=True) was not used and no "
            "measured value was supplied. The contract requires every numeric "
            "field on success (§8 rule 1) and S4 must not be invented — "
            "`.disto` returns exactly 0.0 on BSIM4 (G21), so HD3 comes from "
            "the transient + FFT tier or not at all")

    if area_mm2 is None:
        area_mm2 = _area_mm2_of(pt)
    if area_mm2 is None:
        return DeviceResult.failed(
            "area_mm2 is missing: this point carries no drawn passives, so "
            "S7's area cannot be computed from it. Run with "
            "`SizingPoint(passives=to_geometry(...))` or pass a measured value")

    vout_swing_v, swing_is_lower_bound = swing_for_compression_check(pt)
    if vout_swing_v is None:
        return DeviceResult.failed(
            "vout_swing_v is missing: the `.dc` swing sweep did not yield a "
            "usable swing at all: run_point(swing=True) is required. It is "
            "load-bearing — "
            "without it the C4 compression gate is silently disabled, which is "
            "worse than failing here")

    # `peaking_db` and `f_peak_hz` come from the MEASUREMENT (`meas ac MAX`),
    # not from the fitted model. Two reasons: S3 is scored on what the circuit
    # does, and every published S3 number in this project came from those two
    # `meas` lines, so a DeviceResult reporting fitted values would quietly
    # disagree with `S9_YIELD.md` and `BASELINES.md`.
    #
    # Wrapped because the CONTRACT raises on a missing numeric field (§8
    # rule 1) and this adapter sits in an RL loop, which §8 rule 2 says cannot
    # tolerate exceptions. Each field is checked by name above so this is a
    # backstop, not the mechanism.
    try:
        return DeviceResult(
            ok=True, fail_reason=None,
            g_dc=fit.g_dc,
            f_zero_hz=fit.f_zero_hz,
            f_pole1_hz=fit.f_pole1_hz,
            f_pole2_hz=fit.f_pole2_hz,
            fit_residual_db=fit.residual_db,
            peaking_db=float(pt.peaking_db),
            f_peak_hz=float(pt.f_pk_hz),
            hd3_dbc=float(hd3_dbc),
            vn_in_vrms=float(pt.vn_in_vrms),
            power_w=_power_of(pt),
            area_mm2=float(area_mm2),
            vout_swing_v=float(vout_swing_v),
            ac_freq_hz=pt.ac_freq_hz,
            ac_mag_db=pt.ac_mag_db,
        )
    except ValueError as exc:
        return DeviceResult.failed(f"DeviceResult contract rejected it: {exc}")


def _power_of(pt) -> Optional[float]:
    """MEASURED supply power, watts.

    `power_measured_w` bills the current read off the supply branch, so a real
    mirror's reference branch and its 4-8 % gain error are both paid for
    (session 13). The REQUESTED `SizingPoint.power_w` is a prediction and must
    not be used here.
    """
    v = getattr(pt, "power_measured_w", None)
    if callable(v):
        v = v()
    return float(v) if v is not None else None


def _area_mm2_of(pt) -> Optional[float]:
    """Drawn passive area off the point's own geometry, mm^2.

    A LOWER BOUND on S7: device area only, no head enclosure, routing or guard
    ring (`PASSIVES.md` §4.5's 4h budget), and no MOSFET area — which
    `PASSIVES.md` measured as the smaller term, the passives dominating S7.
    Stated here so a reader of the S7 number knows which budget it is.
    """
    point = getattr(pt, "point", None)
    passives = getattr(point, "passives", None) if point is not None else None
    if passives is None:
        return None
    return float(passives.area_mm2)


def swing_for_compression_check(pt) -> tuple[Optional[float], bool]:
    """`(vout_swing_v, is_lower_bound)` for the C4 gate.

    **The obvious version of this rejected the BEST designs**, and the reason
    is worth writing down. `measured_swing_pp_v` returns the 1 dB compression
    point *or `None`*, and it is right to refuse a fallback to `4*I*RL` — a
    computed ceiling substituted for a measured linear limit is the exact
    substitution that module exists to stop.

    But `None` here does not mean "unknown". `SwingLimits` says so in its own
    docstring: *"`None` means the limit was not reached inside the swept input
    range — which is information, not a failure."* A stage that never
    compresses across a +/-0.8 V differential sweep is MORE linear than one
    that does, so failing it is backwards: the first version of this bridge
    rejected every design with `rs >= 400`, i.e. every heavily degenerated —
    and therefore most linear — sizing in the box.

    So the fallback is `max_swept_pp_v`, the largest output the sweep actually
    produced. That is still a MEASURED number, not a computed one, and it is a
    LOWER BOUND on the true limit — which keeps the C4 gate conservative
    rather than loosening it. The flag says which one came back so a caller
    can report it, and `BridgeDetail.swing_is_lower_bound` carries it up.

    For scale: the link drives this stage at `v_in_diff_pp_v` = 0.535 V at the
    defaults, so a +/-0.8 V sweep already covers the operating range with
    margin.
    """
    if not getattr(pt, "ok", False) or getattr(pt, "vid", None) is None:
        return None, False
    point = getattr(pt, "point", None)
    if point is None:
        return None, False
    from nebula.device.sky130_runner import swing_limits
    lim = swing_limits(pt.vid, pt.vod, pt.sat_ok, pt.id_min,
                       i_ref_a=point.i_tail_per_side_a)
    if lim.linear_pp_v is not None:
        return float(lim.linear_pp_v), False
    if lim.max_swept_pp_v and lim.max_swept_pp_v > 0.0:
        return float(lim.max_swept_pp_v), True
    return None, False


def _measured_swing_or_none(pt) -> Optional[float]:
    """The 1 dB compression swing, when the `.dc` sweep was run.

    `run_point(swing=False)` skips the sweep, so this is legitimately absent —
    and absent is what it must be, because the compression check is the one
    thing on this path that `vout_swing_v` is load-bearing for. Substituting a
    default would disable the C4 gate silently.
    """
    fn = getattr(pt, "measured_swing_pp_v", None)
    if callable(fn):
        try:
            return fn()
        except Exception:                                   # noqa: BLE001
            return None
    from nebula.device.sky130_runner import measured_swing_pp_v
    try:
        return measured_swing_pp_v(pt)
    except Exception:                                       # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# The contract -> the eye.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BridgeDetail:
    """Everything the bridge computed, for the write-up and the diagnostics.

    `LinkResult` is the frozen contract and carries only what §5.1 declares;
    this carries the rest, so a caller that wants to explain a number can,
    without widening the contract.
    """

    ctle: CtleFit
    cursors: CursorSet
    opening: EyeOpening
    gain_at_nyquist: float
    v_in_diff_pp_v: float
    v_out_pp_v: float
    peak_excursion_pp_v: float
    vout_swing_v: Optional[float]
    swing_is_lower_bound: bool
    sigma_out_v: Optional[float]
    snr_at_slicer: Optional[float]

    @property
    def gain_at_nyquist_db(self) -> float:
        return 20.0 * math.log10(self.gain_at_nyquist)


def evaluate_link(dev: DeviceResult, cfg: LinkConfig, *,
                  compression_margin: float = 1.0,
                  swing_is_lower_bound: bool = False,
                  detail: Optional[list] = None) -> LinkResult:
    """`(DeviceResult, LinkConfig) -> LinkResult`. Never raises (§8 rule 2).

    `detail`, if a list is passed, receives one `BridgeDetail`. A side channel
    rather than a second return value, so the frozen signature in §5.1 is
    exactly the signature.

    `swing_is_lower_bound` is passed IN rather than read off `dev` because
    `DeviceResult` is frozen (§5.1) and cannot carry it. It changes no
    arithmetic — it only labels the compression verdict, so a caller can say
    "this design did not compress across the swept range" rather than quoting
    a limit as though it were measured at compression.
    `bridge.swing_for_compression_check` returns it.
    """
    failed = propagate_device_failure(dev)
    if failed is not None:
        return failed

    try:
        return _evaluate(dev, cfg, compression_margin, swing_is_lower_bound,
                         detail)
    except Exception as exc:                                # noqa: BLE001
        # §8 rule 2: the loop cannot tolerate exceptions. A bug here costs one
        # bad reward, not a training run — and it says which layer it came
        # from so it is not mistaken for a bad circuit.
        return LinkResult.failed(
            f"uncaught {type(exc).__name__} in the device->link bridge: {exc}")


def _evaluate(dev: DeviceResult, cfg: LinkConfig,
              compression_margin: float, swing_is_lower_bound: bool,
              detail: Optional[list]) -> LinkResult:
    for name in ("g_dc", "f_zero_hz", "f_pole1_hz", "f_pole2_hz"):
        if getattr(dev, name) is None:
            return LinkResult.failed(
                f"DeviceResult.ok is True but {name} is None — the pole-zero "
                f"fit never ran, so there is no CTLE to build")

    ctle = CtleFit.from_poles(dev.g_dc, dev.f_zero_hz, dev.f_pole1_hz,
                              dev.f_pole2_hz,
                              residual_db=dev.fit_residual_db or 0.0)

    # ── convention C3: the gain that sets the eye is the one AT NYQUIST ──────
    # Using g_dc here would understate the eye by exactly the peaking the
    # circuit exists to provide. `deq.gain_linear` is the one evaluator.
    g_nyq = deq.gain_linear(cfg.nyquist_hz, ctle.small_signal)
    v_in_pp = cfg.v_in_diff_pp_v

    # ── the chain, in volts throughout ──────────────────────────────────────
    pr = pulse_response(cfg.channel, cfg.tx, ctle)
    cursor = int(np.argmax(pr))
    cs = cursors_from_pulse(pr, _osr_of(pr, cfg), cursor, label="bridge")
    opening = eye_opening_vs_phase(pr, _osr_of(pr, cfg), cursor)

    # ── convention C4: compression is a VALIDITY condition, not a clamp ──────
    #
    # The swing checked is the pulse response's own **peak excursion**
    # (G61 convention C, the one `CHANNEL_MODEL.md` §6 selects), NOT an
    # analytic `v_in * |H(f)|` product. The three conventions in this repo
    # disagree by 1.8x, and the pulse response is the only one that needs no
    # decision about which input level pairs with which gain — it carries the
    # transmitter, the channel and the CTLE already.
    #
    # `output_swing_pp_v(g_nyq, v_in_pp)` is still computed, and reported in
    # `BridgeDetail`, because it is the analytic cross-check: the two should
    # be the same order, and a large disagreement means the pulse response and
    # the fitted poles have stopped describing the same circuit.
    v_out_pp = output_swing_pp_v(g_nyq, v_in_pp)
    v_peak_pp = cs.peak_excursion_pp_v
    if dev.vout_swing_v is not None:
        why = check_compression(v_peak_pp, dev.vout_swing_v,
                                margin=compression_margin)
        if why is not None:
            return LinkResult.failed(why)

    eye_h_v = cs.eye_h_v
    eye_w_ui = opening.width_ui

    sigma_out: Optional[float] = None
    snr: Optional[float] = None
    if dev.vn_in_vrms is not None and dev.vn_in_vrms > 0.0:
        sigma_out = float(dev.vn_in_vrms) * g_nyq
    ber = _ber_bound(eye_h_v, sigma_out)
    if sigma_out and eye_h_v > 0.0:
        snr = (eye_h_v / 2.0) / sigma_out

    if detail is not None:
        detail.append(BridgeDetail(
            ctle=ctle, cursors=cs, opening=opening, gain_at_nyquist=g_nyq,
            v_in_diff_pp_v=v_in_pp, v_out_pp_v=v_out_pp,
            peak_excursion_pp_v=v_peak_pp, vout_swing_v=dev.vout_swing_v,
            swing_is_lower_bound=swing_is_lower_bound, sigma_out_v=sigma_out,
            snr_at_slicer=snr))

    return LinkResult(
        ok=True, eye_h_v=float(eye_h_v), eye_w_ui=float(eye_w_ui),
        ber=float(ber), dfe_tap=float(cs.dfe_tap),
        bathtub=opening.eye_h_v.copy(),
    )


def _osr_of(pr: np.ndarray, cfg: LinkConfig) -> int:
    """The oversampling ratio the pulse was built at.

    Read from the module default rather than inferred from the array, because
    inferring it would silently succeed with the wrong answer if the caller
    ever changes `n_fft`.
    """
    from nebula.link.channel import DEFAULT_OSR
    return DEFAULT_OSR


def _ber_bound(eye_h_v: float, sigma_out_v: Optional[float]) -> float:
    """`Q(margin / sigma)` at the worst-case ISI pattern. See the docstring.

    Returns 0.5 — a coin flip, the worst a binary decision can be — when the
    eye is closed, and 0.0 when there is no noise to close it. Both are
    limits, not sentinels: a closed eye really is undecidable, and a noiseless
    open eye really has no errors in this model.

    **0.0 IS ALSO WHAT AN OPEN EYE RETURNS IN PRACTICE, AND IT IS NOT A BUG.**
    Measured on the box midpoint: a 271.7 mV eye against 0.27 mV_rms of device
    noise is a Q-argument of ~424, and `erfc(424/sqrt(2))` underflows double
    precision. So 0.0 here means "below ~1e-308", not "verified error-free".
    **Read `BridgeDetail.snr_at_slicer` instead** — it is the informative
    number and it does not underflow.

    And the reason that SNR is absurd is worth naming rather than celebrating:
    **this models DEVICE noise only.** No reference-clock jitter, no
    crosstalk, no transmitter noise, and — the big one — the residual ISI is
    treated as a deterministic worst-case subtraction rather than as a
    distribution. A real link BER is set by those, which is exactly what
    `python_models/statistical_eye.py` exists to compute and why this is called
    a bound rather than a BER.
    """
    if eye_h_v <= 0.0:
        return 0.5
    if not sigma_out_v or sigma_out_v <= 0.0:
        return 0.0
    from math import erfc, sqrt
    q_arg = (eye_h_v / 2.0) / sigma_out_v
    return float(0.5 * erfc(q_arg / sqrt(2.0)))


__all__ = ("BridgeDetail", "device_result_from_point", "evaluate_link")
