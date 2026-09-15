"""
link/calibration.py — normalised amplitude -> volts. THE conversion.

CLAUDEwa.md §5.3(a) calls this "the highest-risk silent bug in the project":

    `statistical_eye.py` works in normalized amplitude. S8 demands eye height
    in volts. `vout_swing_v` from the device layer must be carried through to
    convert. A wrong scale factor produces plausible-looking numbers that are
    meaningless.

A factor-of-two error here does not crash anything. It moves a 100 mV spec
line to 50 mV or 200 mV, and the design that comes out the other end is
either impossible or trivially easy — and you find out in September.

So the conversion lives in exactly one place, this file, and
`nebula/tests/test_mv_calibration.py` pins it against hand-computed values.
Nothing else in the codebase may multiply a normalised amplitude by a voltage.

The three conventions, stated once
----------------------------------
C1. **Normalised amplitude.** NRZ symbols are +/-1. So one symbol level is
    1.0, and a fully open ideal eye is 2.0 normalised units tall
    (`NRZ_IDEAL_EYE_NORM`). This matches `python_models/statistical_eye.py`,
    where the cursor is gain-calibrated to 1.0 and eye height is measured
    between the +1 and -1 levels.

    (The PAM-4 path uses +/-1, +/-3 with an ideal eye of 2.0 between adjacent
    levels; the NRZ retarget must not silently inherit the PAM-4 RMS scaling
    — see CLAUDEwa.md §4.3.)

C2. **`DeviceResult.vout_swing_v`** is the maximum linear DIFFERENTIAL
    PEAK-TO-PEAK output swing, in volts — a compression limit, a property of
    the device at that corner, independent of the input amplitude.

C3. **The actual output swing** is the input amplitude times the gain AT THE
    FREQUENCY THAT MATTERS — not the DC gain:

        v_out_pp = v_in_diff_pp * |H(f_nyquist)|

    and one normalised unit is `v_out_pp / 2` volts, because peak-to-peak
    spans amplitudes -1 to +1, i.e. 2 normalised units.

    Using `g_dc` here is a real bug, not a simplification. The whole purpose
    of a CTLE is that |H(f_nyq)| sits 3-12 dB above |H(0)| (S3), so a DC-gain
    calculation understates the eye by exactly the peaking the circuit exists
    to provide. `nebula.common.design_equations.gain_linear` is the one place
    that evaluates the fitted response.

C4. **Compression is a validity condition, NOT a clamp.** If the linear
    prediction exceeds `vout_swing_v`, the correct answer is not
    `min(prediction, limit)` — it is "the small-signal model does not apply
    here". A clamp silently converts an invalid operating point into a
    plausible number, and the RL policy will happily discover that region and
    live in it. This is the same physical condition `.disto` reports as
    collapsing HD3, so the reward already has a channel for it via S4; what it
    must not have is an eye height computed from an AC analysis that is no
    longer describing the circuit. `check_compression()` below returns a
    reason string, and the link layer turns that into `ok=False`.

Worked example, so the factor of two is unambiguous
---------------------------------------------------
    |H(f_nyq)| = 4.0 (12 dB), v_in_diff_pp = 100 mV, vout_swing_v = 600 mV
    -> v_out_pp = 4.0 * 100 mV = 400 mV   (400 < 600, model valid)
    -> one normalised unit = 200 mV
    -> a fully open eye (2.0 norm) = 400 mV
    -> the S8 threshold of 100 mV = 0.5 normalised units

If your mental model says the fully open eye there is 200 mV, or 800 mV, stop
and re-read C1-C4 before changing any code.
"""

from __future__ import annotations

import math

#: Height of a fully open, ISI-free, noiseless NRZ eye in normalised units.
#: Symbols are +/-1, so the eye spans 2.0. See convention C1.
NRZ_IDEAL_EYE_NORM: float = 2.0


def output_swing_pp_v(
    gain_at_signal_band: float,
    v_in_diff_pp_v: float,
) -> float:
    """Linear differential peak-to-peak output swing, volts (convention C3).

    No clamping. If the answer exceeds the device's compression limit that is
    a fact the caller needs to see, not a number to be quietly truncated —
    pass it to `check_compression()`.

    Parameters
    ----------
    gain_at_signal_band
        |H(f)| of the CTLE at the frequency that sets the eye — in practice
        Nyquist. Linear V/V, NOT dB. Get it from
        `design_equations.gain_linear(cfg.nyquist_hz, ss)`, never from
        `DeviceResult.g_dc` (see C3).
    v_in_diff_pp_v
        Differential peak-to-peak input amplitude at the CTLE input, volts
        (i.e. at the channel output).

    Raises
    ------
    ValueError
        on any non-positive or non-finite input. The link layer catches this
        and returns `LinkResult.failed(...)`.
    """
    _require_positive("gain_at_signal_band", gain_at_signal_band)
    _require_positive("v_in_diff_pp_v", v_in_diff_pp_v)

    if gain_at_signal_band > 1000.0:
        raise ValueError(
            f"gain_at_signal_band={gain_at_signal_band} V/V "
            f"({20 * math.log10(gain_at_signal_band):.1f} dB) is implausible for "
            f"a single CTLE stage — this is the classic linear/dB mix-up"
        )
    return gain_at_signal_band * v_in_diff_pp_v


def check_compression(
    v_out_pp_v: float,
    vout_swing_v: float,
    *,
    margin: float = 1.0,
) -> str | None:
    """Is the small-signal model still valid at this drive level? (C4)

    Returns None if it is, or a specific reason string if it is not. The
    caller turns that into `LinkResult.failed(reason)`.

    This deliberately does NOT clamp. A clamped result is indistinguishable
    from a legitimately-swing-limited design, and an RL policy searching for
    eye height will find the clamped region and stay there — every proposal in
    it scores as though it delivered the compression limit cleanly, when in
    fact the AC analysis behind the number stopped describing the circuit.

    `margin` scales the limit for callers that want to fail earlier than hard
    compression (e.g. 0.8 to require 20% of linear headroom). It is not a
    tuning knob for making designs pass: raising it above 1.0 is rejected.
    """
    _require_positive("v_out_pp_v", v_out_pp_v)
    _require_positive("vout_swing_v", vout_swing_v)
    if not 0.0 < margin <= 1.0:
        raise ValueError(
            f"margin must lie in (0, 1] — it may only make the check stricter, "
            f"never more permissive. Got {margin}."
        )

    limit = vout_swing_v * margin
    if v_out_pp_v > limit:
        return (
            f"output swing {v_out_pp_v * 1e3:.1f} mVpp exceeds the linear limit "
            f"{limit * 1e3:.1f} mVpp (vout_swing_v={vout_swing_v * 1e3:.1f} mVpp"
            + (f", margin={margin}" if margin != 1.0 else "")
            + "). The stage is compressing, so the AC/pole-zero model behind "
            f"every number in this DeviceResult no longer describes it — the "
            f"eye cannot be computed from it. This is the same physical "
            f"condition .disto reports as collapsing HD3."
        )
    return None


def normalized_to_volts(amplitude_norm: float, v_out_pp_v: float) -> float:
    """Convert a normalised amplitude to volts (convention C3).

    `amplitude_norm` is in the +/-1 symbol units of C1, so a fully open eye of
    `NRZ_IDEAL_EYE_NORM` = 2.0 maps to the full `v_out_pp_v`.
    """
    _require_positive("v_out_pp_v", v_out_pp_v)
    if not math.isfinite(amplitude_norm):
        raise ValueError(f"amplitude_norm must be finite, got {amplitude_norm}")
    if amplitude_norm < 0.0:
        raise ValueError(
            f"amplitude_norm={amplitude_norm} is negative — a closed eye is 0, "
            f"never negative. This usually means residual ISI exceeded the "
            f"cursor and the caller did not clamp."
        )
    if amplitude_norm > NRZ_IDEAL_EYE_NORM * (1.0 + 1e-9):
        raise ValueError(
            f"amplitude_norm={amplitude_norm} exceeds the ideal NRZ eye of "
            f"{NRZ_IDEAL_EYE_NORM}. Equalisation cannot open an eye wider than "
            f"the symbol spacing, so this is a units bug, not a good result."
        )
    return amplitude_norm * (v_out_pp_v / NRZ_IDEAL_EYE_NORM)


def volts_to_normalized(amplitude_v: float, v_out_pp_v: float) -> float:
    """Inverse of `normalized_to_volts`. Used to put the S8 spec line
    (100 mV) into the normalised units the eye engine actually works in."""
    _require_positive("v_out_pp_v", v_out_pp_v)
    if not math.isfinite(amplitude_v) or amplitude_v < 0.0:
        raise ValueError(f"amplitude_v must be finite and non-negative, got {amplitude_v}")
    return amplitude_v * NRZ_IDEAL_EYE_NORM / v_out_pp_v


def _require_positive(name: str, value: float) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a real number, got {value!r}")
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if float(value) <= 0.0:
        raise ValueError(f"{name} must be positive, got {value!r}")
