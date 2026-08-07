"""
link/cursors.py — the decisive measurement: is a 1-tap DFE enough?

WHY THIS CAN BE DONE TODAY
---------------------------
S2 fixes the topology at **one CTLE stage plus a 1-tap DFE**. A 1-tap DFE can
cancel **exactly one post-cursor**. If the channel at the top of the loss range
leaves significant energy in `h2` and beyond, the mandated topology cannot meet
S8 at that loss — and that is a finding about the problem statement itself, not
about our sizing.

Answering it needs convolution and sampling and nothing else. It does not touch
the PAM-4 BER path that the NRZ retarget has fenced off
(`NRZ_RETARGET_AUDIT.md`), so it does not wait on that work.

WHAT IS COMPUTED, IN ORDER
--------------------------
1. The transmitter's launched pulse (`tx.pulse`), including the mandated
   de-emphasis, is convolved with the channel's **minimum-phase** impulse
   response (`ChannelModel.impulse_response`).
2. Optionally through a CTLE — the same 1-zero/2-pole behavioural model the
   device layer fits (`common/design_equations.py`), at the boost matched to
   that channel.
3. The result is sampled at UI intervals at the phase that maximises `h0`,
   with `DEFAULT_OSR` samples per UI internally.
4. Cursors `h_-2 .. h_4` are reported normalised to `h0`.
5. Residual ISI after an **ideal** 1-tap DFE is `sum|h_k|` over every `k` that
   the DFE cannot reach — all pre-cursors plus every post-cursor from `k = 2`
   — as a fraction of `h0`.

THE METRIC THAT DOES NOT DEPEND ON THE CTLE'S RAW GAIN
-------------------------------------------------------
`residual_fraction >= 1` means the worst-case ISI equals or exceeds the cursor:
the eye is **closed**, and no amount of gain reopens it, because gain scales
signal and ISI identically. So "is a 1-tap DFE sufficient?" is answered by a
pure ratio, independent of every device number in the project. Only the
conversion of an OPEN eye into millivolts needs a gain, and that conversion is
reported separately and with its convention stated (`CtleEyeEstimate`).

CONVENTIONS
-----------
* Volts throughout are DIFFERENTIAL. `tx.pulse` carries
  `swing_diff_pp_v / 2` per symbol, and the channel is normalised to `H(0) = 1`,
  so a cursor is in differential volts directly.
* Worst-case eye height is `2 * (h0 - residual_abs)`, the standard NRZ
  peak-to-peak vertical opening: symbols are `+/-1`, so the worst `+1` sample
  sits at `h0 - residual_abs` and the worst `-1` sample at `-(h0 - residual_abs)`.
* The CTLE used here is normalised to **unity DC gain**. It carries the
  equalisation SHAPE and none of the raw gain, so eye numbers at its output are
  "per unit of DC gain" and `required_dc_gain_for` says what gain S8 then needs.
  Mixing in a raw gain here would make the answer depend on a device operating
  point that this measurement deliberately does not assume.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from nebula.common import design_equations as deq
from nebula.common.types import (
    BAUD_RATE_HZ,
    NYQUIST_HZ,
    SPEC_EYE_H_MIN_V,
    SPEC_PEAKING_DB_RANGE,
)
from nebula.link.channel import DEFAULT_N_FFT, DEFAULT_OSR, ChannelModel
from nebula.link.tx import PCIE_GEN2_TX, TxDeEmphasis

# ─────────────────────────────────────────────────────────────────────────────
# The CTLE's second pole. DERIVED from two already-published measurements, not
# chosen: `rl = 565 ohm` is the load of design 432, the single
# corner-and-load-robust survivor (S9_YIELD.md §8 / TAIL_DEVICE.md), and
# `cl_mid = 32.63 fF` is the geometric mean of the derived load range
# (CL_RANGE.md). f_p2 = 1/(2*pi*rl*cl).
#
# It is a REPORTING choice, in the sense that a different f_p2 moves how much
# degeneration is needed for a given boost — but not a free one: it is where
# this project's own measured design sits.
# ─────────────────────────────────────────────────────────────────────────────

DESIGN_432_RL_OHM: float = 565.0
CL_MID_F: float = 32.63e-15
DEFAULT_F_POLE2_HZ: float = 1.0 / (2.0 * math.pi * DESIGN_432_RL_OHM * CL_MID_F)

#: Cursors reported in the headline table (5e asks for exactly these).
REPORTED_TAPS: tuple[int, ...] = (-2, -1, 0, 1, 2, 3, 4)


# ─────────────────────────────────────────────────────────────────────────────
# The behavioural CTLE, matched to a boost
# ─────────────────────────────────────────────────────────────────────────────


def peak_frequency_hz(ss: deq.SmallSignal) -> Optional[float]:
    """Closed-form location of `max|H|` for the 1-zero/2-pole response.

    With `a = 1/fz^2`, `b = 1/fp1^2`, `c = 1/fp2^2` and `u = f^2`,
    `d|H|^2/du = 0` reduces to

        a*b*c*u^2 + 2*b*c*u + (b + c - a) = 0

    whose positive root is

        u* = ( -b*c + sqrt( b*c * (b*c - a*(b + c - a)) ) ) / (a*b*c)

    and a positive root exists **iff `a > b + c`**, i.e.

        1/fz^2  >  1/fp1^2 + 1/fp2^2

    That inequality is the exact form of session 9c's measured "f_z must sit
    below f_p2 or there is no peak at all" — and it is checkable by hand, which
    is why it is here rather than a grid search. Returns `None` when there is
    no interior maximum.
    """
    a = 1.0 / ss.f_zero_hz ** 2
    b = 1.0 / ss.f_pole1_hz ** 2
    c = 1.0 / ss.f_pole2_hz ** 2
    if a <= b + c:
        return None
    disc = b * c * (b * c - a * (b + c - a))
    if disc < 0.0:
        return None
    u = (-b * c + math.sqrt(disc)) / (a * b * c)
    if u <= 0.0:
        return None
    return math.sqrt(u)


@dataclass(frozen=True)
class MatchedCtle:
    """A 1-zero/2-pole CTLE placed to supply a requested boost at Nyquist.

    Solved so that **the peak sits at `f_peak_hz` AND the peak-to-DC ratio
    equals `target_boost_db`**. With `f_peak_hz` defaulting to Nyquist those
    two conditions coincide, so `peaking_db == nyquist_boost_db == target` —
    i.e. this CTLE passes S3 under BOTH of CLAUDEwa.md §3's readings at once,
    which removes the ambiguity from every number derived through it.

    `g_dc` is fixed at 1.0: shape only, no raw gain (see the module docstring).
    """

    ss: deq.SmallSignal
    target_boost_db: float
    f_peak_hz: float
    f_pole2_hz: float
    realised_peaking_db: float
    realised_f_peak_hz: float

    @property
    def meets_s3_peaking(self) -> bool:
        lo, hi = SPEC_PEAKING_DB_RANGE
        return lo - 1e-9 <= self.realised_peaking_db <= hi + 1e-9

    def response(self, f_hz) -> np.ndarray:
        """Complex `H(f)` on a SIGNED frequency axis (Hermitian, so real in time)."""
        f = np.asarray(f_hz, dtype=float)
        return (self.ss.g_dc
                * (1.0 + 1j * f / self.ss.f_zero_hz)
                / ((1.0 + 1j * f / self.ss.f_pole1_hz)
                   * (1.0 + 1j * f / self.ss.f_pole2_hz)))


def matched_ctle(
    target_boost_db: float,
    f_peak_hz: float = NYQUIST_HZ,
    f_pole2_hz: float = DEFAULT_F_POLE2_HZ,
) -> MatchedCtle:
    """Solve for `(f_zero, f_pole1)` giving `target_boost_db` peaking at `f_peak_hz`.

    Two conditions, two unknowns, both handled in closed form except for one
    1-D root find:

    * the peak-location condition gives `k^2 = a*(1 + 2*c*u + a*c*u^2)/(a - c)`;
    * the peak-height condition gives `k^2 = a*u / ( (1 + a*u)/(T*(1 + c*u)) - 1 )`
      with `T = 10**(target_boost_db/10)` (a POWER ratio — the response is
      squared here, which is the factor-of-two this project keeps finding);

    and `a = 1/f_zero^2` is bisected until the two agree. Raises on an
    unreachable request rather than returning a nearby design, because "the
    boost this f_p2 cannot deliver" is a result worth seeing.
    """
    if not math.isfinite(target_boost_db) or target_boost_db <= 0.0:
        raise ValueError(
            f"target_boost_db must be positive — a CTLE that does not boost is "
            f"not being matched to anything. Got {target_boost_db!r}."
        )
    for name, v in (("f_peak_hz", f_peak_hz), ("f_pole2_hz", f_pole2_hz)):
        if not math.isfinite(v) or v <= 0.0:
            raise ValueError(f"{name} must be positive and finite, got {v!r}")

    u = float(f_peak_hz) ** 2
    c = 1.0 / float(f_pole2_hz) ** 2
    t_power = 10.0 ** (float(target_boost_db) / 10.0)

    def k2_from_location(a: float) -> float:
        return a * (1.0 + 2.0 * c * u + a * c * u * u) / (a - c)

    def k2_from_height(a: float) -> float:
        q = (1.0 + a * u) / (t_power * (1.0 + c * u)) - 1.0
        return a * u / q if q > 0.0 else math.inf

    # `a` must exceed both `c` (else f_zero >= f_pole2 and there is no peak at
    # f_peak) and the value that makes the height condition's denominator zero.
    a_lo = max(c, (t_power * (1.0 + c * u) - 1.0) / u) * (1.0 + 1e-9)
    a_hi = a_lo * 1e9

    def f(a: float) -> float:
        return k2_from_location(a) - k2_from_height(a)

    grid = np.geomspace(a_lo * (1.0 + 1e-12), a_hi, 4000)
    vals = np.array([f(float(x)) for x in grid])
    finite = np.isfinite(vals)
    idx = None
    for i in range(len(grid) - 1):
        if finite[i] and finite[i + 1] and vals[i] * vals[i + 1] <= 0.0:
            idx = i
            break
    if idx is None:
        raise ValueError(
            f"no 1-zero/2-pole CTLE supplies {target_boost_db:.3f} dB of peaking "
            f"with its peak at {f_peak_hz / 1e9:.3f} GHz against a second pole at "
            f"{f_pole2_hz / 1e9:.3f} GHz. The second pole erodes the boost before "
            f"the zero can deliver it — session 9c's 'lowering f_p2 does not move "
            f"the peak down, it EXTINGUISHES it', in solver form."
        )

    from scipy.optimize import brentq

    a = float(brentq(f, float(grid[idx]), float(grid[idx + 1]), xtol=1e-30, rtol=1e-14))
    k2 = k2_from_location(a)
    if not math.isfinite(k2) or k2 <= 1.0:
        raise ValueError(
            f"solver returned a degeneration factor k^2 = {k2!r} <= 1, which is "
            f"not a peaking stage. Request: {target_boost_db} dB at "
            f"{f_peak_hz / 1e9} GHz, f_p2 = {f_pole2_hz / 1e9} GHz."
        )
    f_zero = 1.0 / math.sqrt(a)
    ss = deq.SmallSignal(
        g_dc=1.0,
        f_zero_hz=f_zero,
        f_pole1_hz=f_zero * math.sqrt(k2),
        f_pole2_hz=float(f_pole2_hz),
        peaking_db=20.0 * math.log10(math.sqrt(k2)),
    )

    f_pk = peak_frequency_hz(ss)
    if f_pk is None:
        raise ValueError("solved CTLE has no interior maximum — solver bug")
    realised = deq.transfer_db(f_pk, ss) - 20.0 * math.log10(ss.g_dc)

    ctle = MatchedCtle(
        ss=ss, target_boost_db=float(target_boost_db), f_peak_hz=float(f_peak_hz),
        f_pole2_hz=float(f_pole2_hz), realised_peaking_db=realised,
        realised_f_peak_hz=f_pk,
    )
    # The solve is the gate: if it did not land on both conditions, nothing
    # downstream is describing the CTLE we asked for (rule 10).
    if abs(realised - target_boost_db) > 1e-6 or abs(f_pk / f_peak_hz - 1.0) > 1e-6:
        raise ValueError(
            f"matched_ctle did not converge: asked {target_boost_db:.6f} dB at "
            f"{f_peak_hz / 1e9:.6f} GHz, got {realised:.6f} dB at "
            f"{f_pk / 1e9:.6f} GHz"
        )
    return ctle


# ─────────────────────────────────────────────────────────────────────────────
# Cursors
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CursorSet:
    """UI-spaced samples of one pulse response, and what a 1-tap DFE leaves.

    All voltages are DIFFERENTIAL volts. `taps` is keyed by cursor index: 0 is
    the cursor, negative is pre-cursor, positive is post-cursor.
    """

    taps: dict
    h0_v: float
    dfe_tap: float                  # h1/h0 — what the ideal 1-tap DFE cancels
    precursor_abs_v: float          # sum |h_k|, k < 0
    postcursor_residual_abs_v: float  # sum |h_k|, k >= 2
    residual_abs_v: float           # the two above; what the DFE cannot reach
    osr: int
    cursor_index: int
    n_ui_scanned: int
    label: str = ""

    @property
    def residual_fraction(self) -> float:
        """Residual ISI after an ideal 1-tap DFE, as a fraction of the cursor.

        **>= 1.0 means the eye is CLOSED** and no gain reopens it.
        """
        return self.residual_abs_v / self.h0_v

    @property
    def eye_open(self) -> bool:
        return self.residual_fraction < 1.0

    @property
    def eye_h_v(self) -> float:
        """Worst-case vertical eye opening, differential volts. 0 when closed."""
        return max(0.0, 2.0 * (self.h0_v - self.residual_abs_v))

    def normalised(self, k: int) -> float:
        return self.taps[k] / self.h0_v

    def reported_row(self, keys: Sequence[int] = REPORTED_TAPS) -> dict:
        return {k: self.normalised(k) for k in keys}


def pulse_response(
    channel: ChannelModel,
    tx: TxDeEmphasis = PCIE_GEN2_TX,
    ctle: Optional[MatchedCtle] = None,
    osr: int = DEFAULT_OSR,
    n_fft: int = DEFAULT_N_FFT,
    fbaud_hz: float = BAUD_RATE_HZ,
) -> np.ndarray:
    """TX pulse -> channel -> (optional) CTLE, in differential volts.

    Everything is done on one FFT grid. The channel contributes its
    minimum-phase impulse response (with any stated reflections already added
    in the time domain); the CTLE contributes an analytic Hermitian response on
    the SIGNED frequency axis, which is what keeps the result real.
    """
    h = channel.impulse_response(osr=osr, n_fft=n_fft, fbaud_hz=fbaud_hz)
    p = tx.pulse(osr)
    if p.size > n_fft:
        raise ValueError(f"TX pulse ({p.size}) does not fit in n_fft={n_fft}")
    p_pad = np.zeros(n_fft)
    p_pad[:p.size] = p

    spectrum = np.fft.fft(p_pad) * np.fft.fft(h)
    if ctle is not None:
        fs = float(fbaud_hz) * int(osr)
        spectrum = spectrum * ctle.response(np.fft.fftfreq(n_fft, d=1.0 / fs))
    return np.fft.ifft(spectrum).real


def extract_cursors(
    channel: ChannelModel,
    tx: TxDeEmphasis = PCIE_GEN2_TX,
    ctle: Optional[MatchedCtle] = None,
    osr: int = DEFAULT_OSR,
    n_fft: int = DEFAULT_N_FFT,
    fbaud_hz: float = BAUD_RATE_HZ,
    label: str = "",
) -> CursorSet:
    """Sample the pulse response at UI intervals at the phase maximising `h0`.

    The phase search is exactly `argmax` of the pulse response: the sampling
    instants are `cursor + k*osr`, so maximising the `k = 0` sample over the
    `osr` available phases is maximising the pulse response itself. Indexing is
    MODULAR, so a pre-cursor that would fall before the start of the buffer
    reads the wrapped (essentially zero) tail — and any energy found there is
    precisely the time-domain aliasing the causality gate measures.
    """
    pr = pulse_response(channel, tx, ctle, osr, n_fft, fbaud_hz)
    cursor = int(np.argmax(pr))
    h0 = float(pr[cursor])
    if h0 <= 0.0:
        raise ValueError(
            f"pulse response has a non-positive maximum ({h0!r}) — the channel or "
            f"CTLE inverted the pulse, which is a sign convention bug upstream"
        )

    # The scan window covers the whole buffer exactly once. Its low edge is the
    # true start of the pulse (`-(cursor // osr)`), pulled down further if
    # needed so every REPORTED_TAPS index is inside — otherwise a cursor within
    # two UI of the buffer start would leave `h_-2` outside the window, and
    # adding it afterwards would count one wrapped sample TWICE in the residual.
    n_ui = n_fft // osr
    k_lo = min(-(cursor // osr), min(REPORTED_TAPS))
    k_hi = k_lo + n_ui - 1
    taps: dict = {}
    pre_abs = 0.0
    post_abs = 0.0
    for k in range(k_lo, k_hi + 1):
        v = float(pr[(cursor + k * osr) % n_fft])
        taps[k] = v
        if k < 0:
            pre_abs += abs(v)
        elif k >= 2:
            post_abs += abs(v)

    return CursorSet(
        taps=taps,
        h0_v=h0,
        dfe_tap=taps[1] / h0,
        precursor_abs_v=pre_abs,
        postcursor_residual_abs_v=post_abs,
        residual_abs_v=pre_abs + post_abs,
        osr=int(osr),
        cursor_index=cursor,
        n_ui_scanned=k_hi - k_lo + 1,
        label=label,
    )


# ─────────────────────────────────────────────────────────────────────────────
# S8
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CtleEyeEstimate:
    """The S8 vertical-eye question, with the gain convention made explicit."""

    cursors: CursorSet
    #: Eye at the CTLE output for a CTLE of UNITY DC gain, differential volts.
    eye_h_v_at_unity_dc_gain: float
    #: DC gain the CTLE must supply for that eye to clear S8's 100 mV floor.
    #: `inf` when the eye is closed — no gain fixes a closed eye.
    required_dc_gain: float
    eye_open: bool

    @property
    def required_dc_gain_db(self) -> float:
        return (20.0 * math.log10(self.required_dc_gain)
                if math.isfinite(self.required_dc_gain) else math.inf)


def eye_estimate(cursors: CursorSet,
                 eye_h_min_v: float = SPEC_EYE_H_MIN_V) -> CtleEyeEstimate:
    """Turn a cursor set into the S8 verdict.

    Splitting the answer in two is deliberate. Whether the eye is OPEN is a
    property of the ISI alone and is what decides whether S2's mandated 1-tap
    DFE is sufficient. How many millivolts an open eye is worth depends on the
    CTLE's raw gain, which this measurement does not assume — so it is reported
    as the gain S8 then requires, which a device number can be checked against.
    """
    eye = cursors.eye_h_v
    return CtleEyeEstimate(
        cursors=cursors,
        eye_h_v_at_unity_dc_gain=eye,
        required_dc_gain=(float(eye_h_min_v) / eye if eye > 0.0 else math.inf),
        eye_open=cursors.eye_open,
    )
