"""
link/channel.py — the channel, as a derived family instead of an invented scalar.

WHAT THIS REPLACES, AND WHY THE OLD THING WAS WRONG
---------------------------------------------------
`link/config.py` used to carry a hard-coded 1.0 dB "channel loss at DC"
constant, with a comment admitting it had no measured provenance, and that constant
decided every compression verdict this project has published
(`BOUNDS_REDERIVATION.md` §2's blockquote says so explicitly). It is deleted,
not re-valued, and `nebula/tests/test_channel_model.py` asserts the symbol is
gone from every executable file in the tree.

**The constant's own name encoded the mistake.** For a lossy transmission line
the insertion loss at DC is essentially zero — conductor DC resistance across
a few inches of copper is milliohms against a 50 ohm line. What is non-zero,
and what an equaliser exists to undo, is the loss at NYQUIST. A "DC loss" of
1.0 dB was a number attached to a quantity that is physically ~0.

WHERE THE REPLACEMENT COMES FROM (the derivation, stated)
---------------------------------------------------------
There is **no PCIe Gen2 reference receiver to copy**. Gen1 and Gen2 specify
*transmitter de-emphasis only*, at a fixed -3.5 dB with a -6 dB option;
receiver CTLE and DFE entered the specification at **Gen3**. So the channel is
ours to define, and the defensible construction is to read it off the
specification we were actually given:

    industry practice sets CTLE boost at Nyquist ~= channel insertion loss at
    Nyquist, so S3's own 3-12 dB tunable boost requirement implies a channel
    family spanning roughly 3-12 dB of insertion loss at 2.5 GHz.

That is the same reasoning `DEFAULT_LOSS_SWEEP_DB` already used for the loss
axis; this module extends it from a scalar per point to a *response*.

THE MODEL, AND THE HALF PEOPLE GET WRONG
----------------------------------------
Two loss mechanisms with different frequency dependence:

    IL_dB(f) = A*sqrt(f) + B*f          A, B >= 0
    |H(f)|   = 10 ** (-IL_dB(f) / 20)

`A*sqrt(f)` is skin effect (current crowds into a depth that shrinks as
1/sqrt(f)); `B*f` is dielectric loss (loss tangent is roughly constant, so the
loss per wavelength is, and the loss per unit length grows linearly with f).

**The magnitude is the easy half. The phase is where this goes wrong.** A
magnitude-only response with zero phase is NON-CAUSAL: its impulse response is
symmetric about t = 0, so half of its energy arrives before the pulse was
launched, and every ISI cursor and eye number computed from it is wrong in a
way that looks entirely plausible. This is the project's failure mode #1
(HANDOFF: "produces a finite, plausible, wrong answer and raises nothing").

So the phase is built properly — **minimum-phase reconstruction via the
Hilbert transform of ln|H(f)|**, done as the standard real-cepstrum fold — and
then GATED: `causality_report()` computes the impulse response and measures
the energy at t < 0, and `assert_causal()` refuses a response above a stated
threshold. `zero_phase_impulse_response()` exists purely so the gate can be
watched to fail on the thing it is there to catch (CLAUDEwa.md §8 rule 10:
every gate gets a test that proves it can fail).

Passivity and monotonicity are gated the same way: |H(f)| <= 1 everywhere, and
|H| non-increasing in f.

PARAMETERISATION
----------------
`ChannelModel(il_db_at_nyquist=..., skin_fraction=...)`. The insertion loss at
Nyquist is the **primary constructor argument** and a first-class attribute,
because it is the number the rest of the project indexes on: it is what the
APCCAS LUT is indexed on, it is what differs between protocol generations, and
it is the natural conditioning variable for a spec-conditioned policy. (Design
note only — no RL plumbing is built here.)

`skin_fraction` is `r = A*sqrt(f_N) / (A*sqrt(f_N) + B*f_N)` evaluated at
Nyquist, so (IL, r) determines (A, B) in closed form:

    A = r * IL / sqrt(f_N)          B = (1 - r) * IL / f_N

**A scalar cannot represent a channel, and r is why.** Two channels with
identical loss at Nyquist have materially different pulse-response shapes
depending on which mechanism dominates: skin effect's sqrt(f) rolls off slowly
and leaves a long, slowly-decaying post-cursor tail; dielectric loss rolls off
faster in-band and produces a shorter, deeper one. Same headline number,
different DFE problem. This is the one genuinely reusable idea in the APCCAS
paper the mentor supplied.

DO NOT PICK A LENGTH AND DERIVE THE LOSS
----------------------------------------
The family targets the loss and *reports* the equivalent length for a stated
stackup (`Stackup`, below), so a reader can sanity-check that 3-12 dB at
2.5 GHz corresponds to a few inches to a foot and a half of FR-4 rather than
to something absurd. Going the other way would smuggle a trace geometry in as
an assumption and hide it inside a loss number.

WHAT THIS DOES NOT MODEL — declared here, not left for a reviewer
-----------------------------------------------------------------
A smooth `A*sqrt(f) + B*f` form has **no impedance discontinuities**. Real
channels have connectors, vias, package balls and stubs, all of which produce
REFLECTIONS, and reflections are exactly the ISI a DFE handles worst: they
arrive many UI after the cursor, so a 1-tap DFE cannot reach them, and they do
not decay monotonically the way a smooth-loss tail does. Nothing in this
module's magnitude form can represent one.

An **optional two-reflection term** is provided (`Reflection`) so the
sensitivity can be measured rather than argued about. Its amplitudes and
delays are STATED, not measured — they are a probe, not a channel — and every
number derived with reflections enabled must say so.

Also absent: crosstalk, mode conversion, fibre-weave skew, the connector's own
insertion loss, and any frequency-dependent impedance. The Touchstone intake
below profiles a real file and fits its insertion-loss trend, but it does not
pretend that this two-term model preserves measured phase, reflections or mode
conversion.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.common.types import BAUD_RATE_HZ, NYQUIST_HZ

# ─────────────────────────────────────────────────────────────────────────────
# Physical constants. Declared once (CLAUDEwa.md §8 rule 9) and never
# redeclared at a call site.
# ─────────────────────────────────────────────────────────────────────────────

#: Nepers -> dB. 20 / ln(10).
NP_TO_DB: float = 20.0 / math.log(10.0)

#: Speed of light in vacuum, m/s.
C0_M_PER_S: float = 2.99792458e8

#: Vacuum permeability, H/m.
MU0_H_PER_M: float = 4.0e-7 * math.pi

#: Annealed copper conductivity at 20 C, S/m.
COPPER_SIGMA_S_PER_M: float = 5.8e7

# ─────────────────────────────────────────────────────────────────────────────
# The family grid (5c). These are the axes, not a chosen point.
# ─────────────────────────────────────────────────────────────────────────────

#: Insertion loss at 2.5 GHz, dB. Read off S3's 3-12 dB tunable boost range on
#: the standing reasoning that a CTLE is sized to undo roughly the tilt it can
#: boost. Seven points, 1.5 dB apart, endpoints included.
FAMILY_IL_DB: tuple[float, ...] = (3.0, 4.5, 6.0, 7.5, 9.0, 10.5, 12.0)

#: Skin fraction at Nyquist. Three named regimes, deliberately spanning the
#: physically plausible range rather than clustering near the middle.
SKIN_DOMINATED: float = 0.8
BALANCED: float = 0.5
DIELECTRIC_DOMINATED: float = 0.2

FAMILY_SKIN_FRACTIONS: tuple[float, ...] = (
    SKIN_DOMINATED, BALANCED, DIELECTRIC_DOMINATED,
)

SPLIT_NAMES: dict[float, str] = {
    SKIN_DOMINATED: "skin-dominated",
    BALANCED: "balanced",
    DIELECTRIC_DOMINATED: "dielectric-dominated",
}

# ─────────────────────────────────────────────────────────────────────────────
# Numerical grid. Stated because 5b's causality number is meaningless without
# it: the pre-t=0 energy of a truncated impulse response is partly real
# non-causality and partly time-domain aliasing of the tail, and only the grid
# says which.
# ─────────────────────────────────────────────────────────────────────────────

#: Samples per UI used internally. 5e asks for at least 32; 64 is used because
#: the sqrt(f) tail is the thing being measured and it is worth resolving the
#: cursor phase to 3.1 ps rather than 6.2 ps. Every cursor number in
#: CHANNEL_MODEL.md is at this value.
DEFAULT_OSR: int = 64

#: Pre-t=0 energy fraction above which a response is declared non-causal and
#: refused. 1e-6 is -60 dB of energy, i.e. -30 dB of amplitude — three orders
#: below the smallest cursor this project reports. **Stated before the family
#: was run**, and NOT moved afterwards: when the first grid missed it, the grid
#: was lengthened (below), which is a numerical fix. Relaxing the threshold to
#: fit the measurement would have been the other kind of fix.
CAUSALITY_ENERGY_THRESHOLD: float = 1e-6

#: Length of the FFT buffer, samples. 32768 at osr=64 is 512 UI = 102.4 ns.
#:
#: THIS NUMBER WAS CHOSEN BY MEASUREMENT, and the measurement is worth keeping
#: because it is how you tell a broken minimum-phase reconstruction from an
#: adequately-long-but-truncated one. The pre-t=0 energy of the worst family
#: member (12 dB, skin-dominated) falls smoothly with buffer length:
#:
#:      n_fft     4096      8192     16384     32768     65536
#:      pre E   8.7e-05   1.3e-05   1.8e-06   2.5e-07   3.5e-08
#:
#: — a clean power law, i.e. it is **time-domain aliasing of the sqrt(f) tail
#: wrapping into negative time**, not an error in the phase. A broken
#: reconstruction would have sat at a floor instead. 32768 is the first power
#: of two that clears the threshold above at every family member, and it also
#: converges the residual-ISI sum to better than 0.5% (65536 moves the worst
#: case 0.6133 -> 0.6134).
DEFAULT_N_FFT: int = 32768


# ─────────────────────────────────────────────────────────────────────────────
# Stackup — for REPORTING an equivalent length, never for deriving the loss.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Stackup:
    """A stated PCB cross-section, used only to convert loss into a length.

    The direction of the arrow matters and is the whole point of 5c: the
    family targets a LOSS and this class answers "how long a trace would that
    be?", so a reader can sanity-check the numbers. Deriving the loss from a
    chosen length would hide a geometry assumption inside every result.

    Formulas, both standard and both stated so they can be checked by hand:

        dielectric   alpha_d [Np/m] = pi * f * sqrt(Dk) * tan(delta) / c
        conductor    alpha_c [Np/m] = K_gnd * R_s / (Z0 * w),
                     R_s = sqrt(pi * f * mu0 / sigma)

    `ground_return_factor` (K_gnd) accounts for the loss in the return path.
    2.0 is the usual first-order allowance for a microstrip over a solid
    plane — the return current is confined under the trace and dissipates
    comparably to the signal conductor. It is an ALLOWANCE, not a measurement,
    and it is a multiplier on the skin term only.
    """

    name: str
    dk: float
    tan_delta: float
    z0_ohm: float
    trace_width_m: float
    sigma_s_per_m: float = COPPER_SIGMA_S_PER_M
    ground_return_factor: float = 2.0

    def __post_init__(self) -> None:
        for attr in ("dk", "tan_delta", "z0_ohm", "trace_width_m",
                     "sigma_s_per_m", "ground_return_factor"):
            v = float(getattr(self, attr))
            if not math.isfinite(v) or v <= 0.0:
                raise ValueError(f"Stackup.{attr} must be positive and finite, got {v!r}")

    @property
    def b_db_per_ghz_per_m(self) -> float:
        """Dielectric loss coefficient, dB per GHz per metre."""
        return (NP_TO_DB * math.pi * 1e9 * math.sqrt(self.dk)
                * self.tan_delta / C0_M_PER_S)

    @property
    def a_db_per_sqrt_ghz_per_m(self) -> float:
        """Conductor (skin-effect) loss coefficient, dB per sqrt(GHz) per m."""
        rs_per_sqrt_ghz = math.sqrt(math.pi * 1e9 * MU0_H_PER_M / self.sigma_s_per_m)
        return (NP_TO_DB * self.ground_return_factor * rs_per_sqrt_ghz
                / (self.z0_ohm * self.trace_width_m))

    def il_db_per_m(self, f_hz: float) -> float:
        """Total insertion loss of one metre of this trace at `f_hz`."""
        f_ghz = f_hz / 1e9
        return (self.a_db_per_sqrt_ghz_per_m * math.sqrt(f_ghz)
                + self.b_db_per_ghz_per_m * f_ghz)

    def natural_skin_fraction(self, f_hz: float = NYQUIST_HZ) -> float:
        """The split ratio a homogeneous trace of THIS stackup actually has.

        A family member whose `skin_fraction` differs from this is not a
        length of this trace at all — it is a different cross-section, or a
        trace plus something else. Reporting both lengths (see
        `ChannelModel.equivalent_length`) is how far off it is, made visible.
        """
        f_ghz = f_hz / 1e9
        skin = self.a_db_per_sqrt_ghz_per_m * math.sqrt(f_ghz)
        diel = self.b_db_per_ghz_per_m * f_ghz
        return skin / (skin + diel)


#: The stackup every length in CHANNEL_MODEL.md is quoted against: a 10 mil
#: (0.254 mm) microstrip on standard FR-4, 50 ohm single-ended / 100 ohm
#: differential, 1 oz copper. Dk 4.3 and tan(delta) 0.02 are the usual
#: mid-band FR-4 figures. STATED, not measured here — the point of quoting a
#: length is to let a reader recognise a plausible board, and swapping in a
#: measured stackup changes only the reported length, never the family.
FR4_MICROSTRIP = Stackup(
    name="FR-4 microstrip, 10 mil trace, 50 ohm",
    dk=4.3,
    tan_delta=0.02,
    z0_ohm=50.0,
    trace_width_m=0.254e-3,
)


@dataclass(frozen=True)
class EquivalentLength:
    """How long a trace each of the two loss terms corresponds to.

    `from_skin_m` and `from_dielectric_m` agree only when the member's own
    `skin_fraction` equals the stackup's `natural_skin_fraction`. The gap is
    the honest statement that most of the family is not a homogeneous length
    of one trace, and is reported rather than smoothed over.
    """

    stackup_name: str
    from_skin_m: float
    from_dielectric_m: float
    from_total_m: float
    natural_skin_fraction: float

    @property
    def from_total_inch(self) -> float:
        return self.from_total_m / 0.0254

    @property
    def self_consistent(self) -> bool:
        """True iff the two mechanisms imply the same length to within 10%."""
        lo = min(self.from_skin_m, self.from_dielectric_m)
        hi = max(self.from_skin_m, self.from_dielectric_m)
        return hi <= 1.10 * lo


# ─────────────────────────────────────────────────────────────────────────────
# Reflections — the declared omission, made optional and measurable (5h)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Reflection:
    """One echo: an attenuated, delayed copy of the whole channel response.

    `rho` is the ROUND-TRIP product of two reflection coefficients (a signal
    that reflects off a far discontinuity and again off a near one), so it is
    already the small number. `delay_ui` is the round-trip delay in UI.

    THESE ARE STATED VALUES, NOT MEASURED ONES. They exist so "how much would
    reflections change the cursor set?" is a number instead of an argument.
    Anything computed with reflections enabled must say so and must not be
    presented as a property of the analytic family.

    Applied in the TIME domain, after the minimum-phase reconstruction, at a
    strictly positive delay — so causality is preserved by construction and
    the causality gate is not being asked to certify something the model just
    broke. Passivity is NOT preserved: an echo in phase with the main response
    raises |H| above 1 at some frequencies, which is physically correct for a
    reflective structure viewed as a two-port with energy stored between the
    discontinuities, and is why `assert_passive()` is applied to the smooth
    part only.
    """

    rho: float
    delay_ui: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.rho) or not 0.0 <= abs(self.rho) < 1.0:
            raise ValueError(f"Reflection.rho must satisfy |rho| < 1, got {self.rho!r}")
        if not math.isfinite(self.delay_ui) or self.delay_ui <= 0.0:
            raise ValueError(
                f"Reflection.delay_ui must be positive — a reflection arrives "
                f"AFTER the pulse that caused it. Got {self.delay_ui!r}"
            )


#: The stated two-reflection probe: a connector-like echo two UI out and a
#: weaker via-like one five UI out. Amplitudes are round-trip products of
#: ~22% and ~14% single-interface reflection coefficients, which is the order
#: a mediocre connector launch gives. Numbers are STATED (see `Reflection`).
STATED_REFLECTION_PROBE: tuple[Reflection, ...] = (
    Reflection(rho=0.05, delay_ui=2.0),
    Reflection(rho=0.02, delay_ui=5.0),
)


# ─────────────────────────────────────────────────────────────────────────────
# Causality / passivity reports
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CausalityReport:
    """The measured, per-member causality number. Reported, not just asserted.

    `pre_energy_fraction` is the fraction of the impulse response's total
    energy sitting at t < 0, where the time axis of the circular FFT buffer is
    read as [-N/2, N/2) samples. For a correctly reconstructed minimum-phase
    response this is time-domain aliasing of the tail and nothing else; for a
    zero-phase magnitude-only response it is ~0.5, which is the failure this
    gate exists to catch.
    """

    pre_energy_fraction: float
    pre_energy_db: float
    peak_index: int
    n_fft: int
    osr: int

    @property
    def passes(self) -> bool:
        return self.pre_energy_fraction <= CAUSALITY_ENERGY_THRESHOLD


@dataclass(frozen=True)
class PassivityReport:
    """|H| <= 1 everywhere, and non-increasing in f."""

    max_magnitude: float
    max_magnitude_excess: float          # max(|H|) - 1, <= 0 when passive
    worst_monotonicity_violation: float  # max(|H(f_{n+1})| - |H(f_n)|), <= 0
    n_points: int

    @property
    def passes(self) -> bool:
        return (self.max_magnitude_excess <= 1e-12
                and self.worst_monotonicity_violation <= 1e-12)


# ─────────────────────────────────────────────────────────────────────────────
# The channel
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChannelModel:
    """One member of the channel family.

    Parameters
    ----------
    il_db_at_nyquist
        Insertion loss at `f_nyquist_hz`, dB, positive. THE primary argument
        and a first-class attribute — see the module docstring on why.
    skin_fraction
        `r`, the share of that loss carried by the sqrt(f) term, evaluated at
        Nyquist. 0 = purely dielectric, 1 = purely skin effect.
    f_nyquist_hz
        The frequency `il_db_at_nyquist` refers to. Defaults to S1's 2.5 GHz.
    reflections
        Optional stated echoes (5h). Empty by default; anything non-empty must
        be declared wherever the result is quoted.

    There is no random element anywhere in this class, so `LinkConfig.seed`
    never enters it. That is the strongest available form of the repo's
    determinism rule: the response is not merely seeded reproducibly, it is a
    pure function of the two parameters above.
    """

    il_db_at_nyquist: float
    skin_fraction: float = BALANCED
    f_nyquist_hz: float = NYQUIST_HZ
    reflections: tuple[Reflection, ...] = ()

    def __post_init__(self) -> None:
        il = float(self.il_db_at_nyquist)
        if not math.isfinite(il) or il < 0.0:
            raise ValueError(
                f"il_db_at_nyquist is an insertion LOSS and must be >= 0 dB, got {il!r}"
            )
        r = float(self.skin_fraction)
        if not math.isfinite(r) or not 0.0 <= r <= 1.0:
            raise ValueError(
                f"skin_fraction is the sqrt(f) share of the loss at Nyquist and "
                f"must lie in [0, 1], got {r!r}. Outside that range one of A, B "
                f"is negative, which is a gain, not a loss."
            )
        if not math.isfinite(self.f_nyquist_hz) or self.f_nyquist_hz <= 0.0:
            raise ValueError(f"f_nyquist_hz must be positive, got {self.f_nyquist_hz!r}")
        object.__setattr__(self, "reflections", tuple(self.reflections))

    # ---- the two coefficients, in closed form ------------------------------

    @property
    def f_nyquist_ghz(self) -> float:
        return self.f_nyquist_hz / 1e9

    @property
    def a_db_per_sqrt_ghz(self) -> float:
        """Skin-effect coefficient A, dB per sqrt(GHz)."""
        return (self.skin_fraction * self.il_db_at_nyquist
                / math.sqrt(self.f_nyquist_ghz))

    @property
    def b_db_per_ghz(self) -> float:
        """Dielectric coefficient B, dB per GHz."""
        return (1.0 - self.skin_fraction) * self.il_db_at_nyquist / self.f_nyquist_ghz

    @property
    def split_name(self) -> str:
        return SPLIT_NAMES.get(self.skin_fraction, f"r={self.skin_fraction:.2f}")

    def __str__(self) -> str:
        return f"IL{self.il_db_at_nyquist:g}dB/r{self.skin_fraction:g}"

    # ---- magnitude ---------------------------------------------------------

    def il_db(self, f_hz):
        """Insertion loss in dB at `f_hz` (scalar or array). IL(0) = 0 exactly."""
        f_ghz = np.asarray(f_hz, dtype=float) / 1e9
        if np.any(f_ghz < 0.0):
            raise ValueError("il_db is defined for f >= 0")
        out = self.a_db_per_sqrt_ghz * np.sqrt(f_ghz) + self.b_db_per_ghz * f_ghz
        return out if out.ndim else float(out)

    def magnitude(self, f_hz):
        """|H(f)| = 10 ** (-IL_dB(f) / 20). Scalar in, scalar out."""
        il = self.il_db(f_hz)
        out = np.power(10.0, -np.asarray(il, dtype=float) / 20.0)
        return out if out.ndim else float(out)

    @property
    def il_db_at_dc(self) -> float:
        """0.0, by construction, and that is the point.

        `A*sqrt(0) + B*0 = 0`. This property exists so that code which used to
        read the invented DC-loss placeholder reads the MODEL's own answer
        instead, and so the zero is visible rather than implicit.
        """
        return float(self.il_db(0.0))

    # ---- phase: minimum-phase reconstruction -------------------------------

    def frequency_grid(self, osr: int = DEFAULT_OSR, n_fft: int = DEFAULT_N_FFT,
                       fbaud_hz: float = BAUD_RATE_HZ) -> np.ndarray:
        """The full (two-sided, in FFT order) frequency grid, Hz, non-negative.

        Magnitudes are Hermitian-symmetric, so the grid is folded: bin n and
        bin N-n both carry |H(f_n)|.
        """
        _check_grid(osr, n_fft)
        fs = float(fbaud_hz) * osr
        k = np.arange(n_fft)
        return np.minimum(k, n_fft - k) * (fs / n_fft)

    def transfer_function(self, osr: int = DEFAULT_OSR, n_fft: int = DEFAULT_N_FFT,
                          fbaud_hz: float = BAUD_RATE_HZ) -> np.ndarray:
        """Complex minimum-phase H on the full FFT grid.

        The construction is the standard real-cepstrum fold, which is the
        Hilbert transform of `ln|H|` computed by FFT:

            c      = IFFT( ln|H| )                     real cepstrum
            c_min  = c * [1, 2, 2, ..., 2, 1, 0, ..., 0]   causal fold
            H_min  = exp( FFT(c_min) )

        `|H_min|` reproduces the target magnitude exactly (to float error) and
        the phase is the unique minimum-phase one consistent with it. No
        bulk propagation delay is included: minimum phase means zero excess
        delay, so the response starts at t = 0. That is what we want — a pure
        delay is not ISI and equalising it is not the CTLE's job.
        """
        mag = self.magnitude(self.frequency_grid(osr, n_fft, fbaud_hz))
        return _min_phase_from_magnitude(mag)

    def zero_phase_transfer_function(self, osr: int = DEFAULT_OSR,
                                     n_fft: int = DEFAULT_N_FFT,
                                     fbaud_hz: float = BAUD_RATE_HZ) -> np.ndarray:
        """The WRONG one: magnitude with zero phase. Non-causal by construction.

        Present so the causality gate can be watched to fail on exactly the
        error it exists to catch (CLAUDEwa.md §8 rule 10). Never use it for a
        result.
        """
        return self.magnitude(self.frequency_grid(osr, n_fft, fbaud_hz)).astype(complex)

    # ---- time domain -------------------------------------------------------

    def impulse_response(self, osr: int = DEFAULT_OSR, n_fft: int = DEFAULT_N_FFT,
                         fbaud_hz: float = BAUD_RATE_HZ) -> np.ndarray:
        """Real impulse response, length `n_fft`, index 0 == t = 0.

        Any configured `reflections` are added here, in the time domain, at
        strictly positive delays.
        """
        h = np.fft.ifft(self.transfer_function(osr, n_fft, fbaud_hz)).real
        return _apply_reflections(h, self.reflections, osr)

    def zero_phase_impulse_response(self, osr: int = DEFAULT_OSR,
                                    n_fft: int = DEFAULT_N_FFT,
                                    fbaud_hz: float = BAUD_RATE_HZ) -> np.ndarray:
        """The non-causal control. See `zero_phase_transfer_function`."""
        h = np.fft.ifft(self.zero_phase_transfer_function(osr, n_fft, fbaud_hz)).real
        return _apply_reflections(h, self.reflections, osr)

    # ---- gates -------------------------------------------------------------

    def causality_report(self, osr: int = DEFAULT_OSR, n_fft: int = DEFAULT_N_FFT,
                         fbaud_hz: float = BAUD_RATE_HZ) -> CausalityReport:
        """Measure the energy at t < 0. Reported per family member, not just asserted."""
        return causality_of(self.impulse_response(osr, n_fft, fbaud_hz), osr)

    def assert_causal(self, osr: int = DEFAULT_OSR, n_fft: int = DEFAULT_N_FFT,
                      fbaud_hz: float = BAUD_RATE_HZ) -> CausalityReport:
        rep = self.causality_report(osr, n_fft, fbaud_hz)
        if not rep.passes:
            raise ValueError(
                f"{self} is NON-CAUSAL: {rep.pre_energy_fraction:.3e} of the "
                f"impulse-response energy ({rep.pre_energy_db:.1f} dB) sits at "
                f"t < 0, against a threshold of {CAUSALITY_ENERGY_THRESHOLD:.1e}. "
                f"Every cursor and eye number derived from this response would be "
                f"finite, plausible and wrong."
            )
        return rep

    def passivity_report(self, n_points: int = 20001,
                         f_max_hz: Optional[float] = None) -> PassivityReport:
        """|H(f)| <= 1 and non-increasing, on a linear grid up to `f_max_hz`.

        Applies to the SMOOTH part only — `reflections` deliberately break
        passivity and say so.
        """
        if f_max_hz is None:
            f_max_hz = 20.0 * self.f_nyquist_hz
        f = np.linspace(0.0, float(f_max_hz), int(n_points))
        mag = np.asarray(self.magnitude(f), dtype=float)
        return PassivityReport(
            max_magnitude=float(mag.max()),
            max_magnitude_excess=float(mag.max() - 1.0),
            worst_monotonicity_violation=float(np.max(np.diff(mag))) if len(mag) > 1 else 0.0,
            n_points=int(n_points),
        )

    def assert_passive(self, n_points: int = 20001,
                       f_max_hz: Optional[float] = None) -> PassivityReport:
        rep = self.passivity_report(n_points, f_max_hz)
        if not rep.passes:
            raise ValueError(
                f"{self} is NOT PASSIVE: max|H| = {rep.max_magnitude:.6f} "
                f"(excess {rep.max_magnitude_excess:.3e}), worst rise between "
                f"adjacent samples {rep.worst_monotonicity_violation:.3e}. A "
                f"passive channel cannot deliver more than it was given, and a "
                f"lossy one cannot be less lossy at a higher frequency."
            )
        return rep

    # ---- reporting ---------------------------------------------------------

    def equivalent_length(self, stackup: Stackup = FR4_MICROSTRIP) -> EquivalentLength:
        """How long a trace of `stackup` each loss term corresponds to.

        Reported, never used to derive anything. See `EquivalentLength`.
        """
        a_per_m = stackup.a_db_per_sqrt_ghz_per_m
        b_per_m = stackup.b_db_per_ghz_per_m
        total_per_m = stackup.il_db_per_m(self.f_nyquist_hz)
        return EquivalentLength(
            stackup_name=stackup.name,
            from_skin_m=self.a_db_per_sqrt_ghz / a_per_m,
            from_dielectric_m=self.b_db_per_ghz / b_per_m,
            from_total_m=self.il_db_at_nyquist / total_per_m,
            natural_skin_fraction=stackup.natural_skin_fraction(self.f_nyquist_hz),
        )

    def with_reflections(self, refl: Sequence[Reflection] = STATED_REFLECTION_PROBE
                         ) -> "ChannelModel":
        """A copy carrying the stated reflection probe. Declare it when quoting."""
        return ChannelModel(
            il_db_at_nyquist=self.il_db_at_nyquist,
            skin_fraction=self.skin_fraction,
            f_nyquist_hz=self.f_nyquist_hz,
            reflections=tuple(refl),
        )


# ─────────────────────────────────────────────────────────────────────────────
# The family
# ─────────────────────────────────────────────────────────────────────────────


def channel_family(
    il_db: Sequence[float] = FAMILY_IL_DB,
    skin_fractions: Sequence[float] = FAMILY_SKIN_FRACTIONS,
    f_nyquist_hz: float = NYQUIST_HZ,
) -> tuple[ChannelModel, ...]:
    """The grid: every insertion loss crossed with every split ratio.

    Ordered loss-major so that a truncated run still covers the full loss axis
    at the first split.
    """
    if not il_db or not skin_fractions:
        raise ValueError("the channel family needs at least one loss and one split")
    return tuple(
        ChannelModel(il_db_at_nyquist=float(x), skin_fraction=float(r),
                     f_nyquist_hz=f_nyquist_hz)
        for r in skin_fractions
        for x in il_db
    )


# ─────────────────────────────────────────────────────────────────────────────
# Ingestion path for real data (5i)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FitResult:
    """An (A, B) fit to a measured insertion loss, with its residual.

    The residual is the number that decides whether the two-term form is good
    enough for the data. A smooth cable fits to a few tenths of a dB; a board
    with connectors will NOT, because resonant dips from reflections are
    exactly what `A*sqrt(f) + B*f` cannot represent — so a large residual is
    informative rather than a failure, and it is reported, never suppressed.
    """

    channel: ChannelModel
    rms_residual_db: float
    max_residual_db: float
    n_points: int
    f_lo_hz: float
    f_hi_hz: float


def fit_insertion_loss(
    f_hz: Sequence[float],
    il_db: Sequence[float],
    f_nyquist_hz: float = NYQUIST_HZ,
) -> FitResult:
    """Least-squares fit of `IL_dB(f) = A*sqrt(f) + B*f` to measured data.

    `il_db` is a POSITIVE insertion loss in dB (i.e. `-20*log10|S21|`). The fit
    has no intercept term on purpose: IL(0) = 0 is the physics, and letting the
    fit invent a DC offset is how the constant this module deletes got there in
    the first place.

    A and B are constrained non-negative. If the unconstrained solution puts one
    of them negative — which happens on data whose curvature the two-term form
    cannot follow — that term is pinned to zero and the other re-fitted, and the
    residual will say so.
    """
    f = np.asarray(f_hz, dtype=float)
    il = np.asarray(il_db, dtype=float)
    if f.shape != il.shape or f.ndim != 1 or f.size < 2:
        raise ValueError("f_hz and il_db must be matching 1-D arrays with >= 2 points")
    keep = f > 0.0
    f, il = f[keep], il[keep]
    if f.size < 2:
        raise ValueError("need at least two points at f > 0 to fit A and B")
    if np.any(il < -1e-9):
        raise ValueError(
            "il_db must be a POSITIVE insertion loss in dB. Negative values mean "
            "you passed 20*log10|S21| (a gain) instead of -20*log10|S21|."
        )

    f_ghz = f / 1e9
    design = np.column_stack([np.sqrt(f_ghz), f_ghz])
    coeffs, *_ = np.linalg.lstsq(design, il, rcond=None)
    a, b = float(coeffs[0]), float(coeffs[1])

    # Non-negativity: with only two columns the constrained solution is either
    # the unconstrained one or a single-column fit, so this is exact, not a
    # heuristic.
    if a < 0.0 or b < 0.0:
        col = 1 if a < 0.0 else 0
        x = design[:, col]
        c = float(x @ il / (x @ x))
        a, b = (0.0, c) if col == 1 else (c, 0.0)
        a, b = max(a, 0.0), max(b, 0.0)

    resid = il - (a * np.sqrt(f_ghz) + b * f_ghz)
    f_ny_ghz = f_nyquist_hz / 1e9
    il_ny = a * math.sqrt(f_ny_ghz) + b * f_ny_ghz
    skin = a * math.sqrt(f_ny_ghz)
    r = skin / il_ny if il_ny > 0.0 else BALANCED

    return FitResult(
        channel=ChannelModel(il_db_at_nyquist=il_ny, skin_fraction=r,
                             f_nyquist_hz=f_nyquist_hz),
        rms_residual_db=float(np.sqrt(np.mean(resid ** 2))),
        max_residual_db=float(np.max(np.abs(resid))),
        n_points=int(f.size),
        f_lo_hz=float(f.min()),
        f_hi_hz=float(f.max()),
    )


_TOUCHSTONE_SUFFIX = re.compile(r"\.s([1-9][0-9]*)p$", re.IGNORECASE)
_FREQUENCY_SCALE = {
    "hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9,
}


def _read_touchstone_1(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Return frequency and ``S[f, out, in]`` from Touchstone 1.x ASCII."""
    source = Path(path)
    match = _TOUCHSTONE_SUFFIX.search(source.name)
    if not match:
        raise ValueError("Touchstone path must end in .sNp, for example .s4p")
    n_ports = int(match.group(1))
    if not source.is_file():
        raise FileNotFoundError(f"Touchstone file does not exist: {source}")

    unit, parameter, data_format = "ghz", "s", "ma"
    numeric: list[float] = []
    for lineno, raw in enumerate(
            source.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.split("!", 1)[0].strip()
        if not line:
            continue
        if line.startswith("["):
            raise ValueError(
                f"{source.name}:{lineno}: Touchstone 2.x sections are not "
                "supported; refusing a partial interpretation")
        if line.startswith("#"):
            if numeric:
                raise ValueError(
                    f"{source.name}:{lineno}: option line occurs after data")
            tokens = line[1:].lower().split()
            if len(tokens) < 3:
                raise ValueError(f"{source.name}:{lineno}: incomplete option line")
            unit, parameter, data_format = tokens[:3]
            if unit not in _FREQUENCY_SCALE:
                raise ValueError(f"unsupported Touchstone frequency unit {unit!r}")
            if parameter != "s":
                raise ValueError(
                    f"Touchstone file contains {parameter.upper()} parameters, "
                    "not S-parameters")
            if data_format not in ("ri", "ma", "db"):
                raise ValueError(
                    f"unsupported Touchstone data format {data_format!r}")
            if "r" in tokens:
                r_index = tokens.index("r")
                if r_index + 1 >= len(tokens):
                    raise ValueError("Touchstone R option is missing its value")
                try:
                    reference = float(tokens[r_index + 1])
                except ValueError as exc:
                    raise ValueError(
                        "Touchstone reference impedance is invalid") from exc
                if not math.isfinite(reference) or reference <= 0.0:
                    raise ValueError(
                        "Touchstone reference impedance must be positive")
            continue
        for token in line.split():
            try:
                numeric.append(float(token.replace("D", "E").replace("d", "e")))
            except ValueError as exc:
                raise ValueError(
                    f"{source.name}:{lineno}: non-numeric data token "
                    f"{token!r}") from exc

    fields_per_record = 1 + 2 * n_ports * n_ports
    if not numeric or len(numeric) % fields_per_record:
        raise ValueError(
            f"Touchstone data are truncated: {len(numeric)} numeric values do "
            f"not form {fields_per_record}-value records for {n_ports} ports")
    records = np.asarray(numeric, dtype=float).reshape(-1, fields_per_record)
    if not np.all(np.isfinite(records)):
        raise ValueError("Touchstone data contain NaN or infinite values")
    frequency = records[:, 0] * _FREQUENCY_SCALE[unit]
    if np.any(frequency < 0.0) or np.any(np.diff(frequency) <= 0.0):
        raise ValueError(
            "Touchstone frequencies must be non-negative and increasing")

    pairs = records[:, 1:].reshape(-1, n_ports * n_ports, 2)
    first, second = pairs[:, :, 0], pairs[:, :, 1]
    if data_format == "ri":
        values = first + 1j * second
    else:
        magnitude = first if data_format == "ma" else 10.0 ** (first / 20.0)
        values = magnitude * np.exp(1j * np.deg2rad(second))
    # Touchstone 1.x uses row-wise matrix order for 3+ ports. Two-port files
    # are the historical exception: S11,S21,S12,S22 (IBIS Touchstone 2.1,
    # Network Data syntax). Keep that exception explicit and testable.
    s = values.reshape(-1, n_ports, n_ports)
    if n_ports == 2:
        s = s.transpose(0, 2, 1)
    return frequency, s


def insertion_loss_from_touchstone(
    path: str | Path,
    ports: tuple[int, int] = (1, 3),
    f_max_hz: Optional[float] = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Read `(f_hz, IL_dB)` out of a Touchstone file. The seam for real data.

    `ports` is the (out, in) pair, 1-based, in the file's own numbering. The
    default (1, 3) is the common `.s4p` convention where ports 1/3 are the two
    ends of one differential half — **check the supplied file's port map before
    trusting it**, because a wrong pair reads a return loss as an insertion
    loss and every downstream number is nonsense while looking fine.

    Touchstone 1.x S-parameter files are parsed locally, including RI, MA and
    DB encodings and legal continuation lines. No optional RF package is
    required. Touchstone 2.x bracketed sections are refused rather than partly
    interpreted, because a partial parse is worse than a loud error.
    """
    f, s = _read_touchstone_1(path)
    n_ports = s.shape[1]
    if (len(ports) != 2 or any(isinstance(value, bool) for value in ports)
            or any(int(value) != value for value in ports)):
        raise ValueError("ports must be two integer, 1-based port numbers")
    i_out, i_in = int(ports[0]) - 1, int(ports[1]) - 1
    if not (0 <= i_out < n_ports and 0 <= i_in < n_ports):
        raise ValueError(
            f"port map {ports!r} is outside this {n_ports}-port file")
    s21 = s[:, i_out, i_in]
    il = -20.0 * np.log10(np.abs(s21) + 1e-300)
    if f_max_hz is not None:
        keep = f <= float(f_max_hz)
        f, il = f[keep], il[keep]
        if f.size == 0:
            raise ValueError("f_max_hz removes every Touchstone sample")
    return f, il


def fit_from_touchstone(
    path: str,
    ports: tuple[int, int] = (1, 3),
    f_max_hz: Optional[float] = None,
    f_nyquist_hz: float = NYQUIST_HZ,
) -> FitResult:
    """`insertion_loss_from_touchstone` -> `fit_insertion_loss`, in one call.

    This is the reduced-model ingestion path: a real `.s4p` supplies the
    insertion-loss data, then the existing link consumes the fitted
    ``ChannelModel``. Measured phase, reflections and mode conversion are not
    retained; the residual reports magnitude structure the fit cannot follow.
    """
    f, il = insertion_loss_from_touchstone(path, ports, f_max_hz)
    return fit_insertion_loss(f, il, f_nyquist_hz=f_nyquist_hz)


# ─────────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────────


def _check_grid(osr: int, n_fft: int) -> None:
    if int(osr) < 32:
        raise ValueError(
            f"osr must be at least 32 samples per UI — the cursor phase search "
            f"resolves the UI to 1/osr and the sqrt(f) tail is what is being "
            f"measured. Got {osr!r}."
        )
    if int(n_fft) % 2 or int(n_fft) < 4 * int(osr):
        raise ValueError(
            f"n_fft must be even and at least 4 UI long, got {n_fft!r} at osr={osr!r}"
        )


def _min_phase_from_magnitude(mag: np.ndarray) -> np.ndarray:
    """Minimum-phase complex response from a Hermitian magnitude grid.

    The real-cepstrum fold. Equivalent to `phase = -Hilbert{ln|H|}` and
    numerically better behaved than differentiating an unwrapped phase.
    """
    mag = np.asarray(mag, dtype=float)
    n = mag.size
    if n % 2:
        raise ValueError("magnitude grid must have an even number of points")
    if np.any(mag <= 0.0):
        raise ValueError(
            "magnitude must be strictly positive everywhere — ln|H| is taken. A "
            "zero means the model has infinite loss at some frequency, which the "
            "A*sqrt(f) + B*f form cannot produce, so this is a caller bug."
        )
    cepstrum = np.fft.ifft(np.log(mag)).real
    fold = np.zeros(n)
    fold[0] = 1.0
    fold[1:n // 2] = 2.0
    fold[n // 2] = 1.0
    return np.exp(np.fft.fft(cepstrum * fold))


def _apply_reflections(h: np.ndarray, refl: Sequence[Reflection],
                       osr: int) -> np.ndarray:
    """Add stated echoes at strictly positive delays. Causal by construction."""
    if not refl:
        return h
    out = h.copy()
    for r in refl:
        shift = int(round(r.delay_ui * osr))
        if shift <= 0 or shift >= h.size:
            raise ValueError(
                f"reflection at {r.delay_ui} UI does not fit in a {h.size / osr:g} UI "
                f"buffer at osr={osr}"
            )
        out[shift:] += r.rho * h[:h.size - shift]
    return out


def causality_of(h: np.ndarray, osr: int = DEFAULT_OSR) -> CausalityReport:
    """Energy at t < 0, where the FFT buffer's second half IS negative time.

    Split at N/2: sample n carries t = n/fs for n < N/2 and t = (n-N)/fs for
    n >= N/2. For a response that has decayed long before the wrap point this
    measures real non-causality plus time-domain aliasing of the tail, and
    nothing else.
    """
    h = np.asarray(h, dtype=float)
    n = h.size
    total = float(h @ h)
    if total <= 0.0:
        raise ValueError("impulse response has zero energy")
    pre = float(h[n // 2:] @ h[n // 2:])
    frac = pre / total
    return CausalityReport(
        pre_energy_fraction=frac,
        pre_energy_db=10.0 * math.log10(frac) if frac > 0.0 else -math.inf,
        peak_index=int(np.argmax(np.abs(h))),
        n_fft=n,
        osr=int(osr),
    )
