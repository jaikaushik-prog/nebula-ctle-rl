"""
link/fit.py — a measured AC sweep onto `(g_dc, f_zero, f_pole1, f_pole2)`.

WHAT THIS IS
------------
The first half of the device->link bridge, and the piece that did not exist.
`sky130_runner` measures a magnitude curve; `link/cursors.py` wants a
one-zero/two-pole CTLE object. This turns one into the other, and refuses when
it cannot.

    fit_ctle(freq_hz, mag_db) -> CtleFit

CLAUDEwa.md §5.3 names this as one of the **two things most likely to be
silently wrong** in the whole project:

> **(b) Pole-zero fit validity.** The bridge fits ngspice AC output onto
> `(g_dc, f_zero, f_pole1, f_pole2)` via `scipy.optimize.curve_fit`.
> Cross-check against the analytic design equations in §6. **Reject fits with
> residual > 0.5 dB rather than passing garbage downstream.**

So the rejection is not a quality-of-life feature; it is the contract. A fit
that has quietly converged on the wrong shape produces a CTLE that is not the
circuit, and every eye number after it is fiction that will look plausible.

WHY FIT AT ALL, WHEN §6 GIVES THE POLES IN CLOSED FORM
-------------------------------------------------------
Because §6 is measurably wrong about them, and the size of the error is
recorded. G60: the design equations **over-predict the Nyquist boost by +0.77
to +1.47 dB** because they neglect `r_o`, and that became a **28 % error** in a
published compression ratio before it was calibrated out. Session 18c
decomposed the `f_peak` error and found the **one-zero/two-pole model itself**
worth 4.25 % of the spread, against 1.20 % for the predicted `k`.

So §6 is the right INITIAL GUESS and the wrong final answer. It is used here
for exactly that — `initial_guess_from_design_equations` — and then the
measurement is fitted. The §6 prediction is also kept on the result so a
caller can see how far the circuit moved from the algebra, which is the
cross-check §5.3(b) asks for.

WHAT IS FITTED, AND IN WHICH UNITS
-----------------------------------
The model, on the SAME differential magnitude the device layer measures:

    |H(f)| = g_dc * |1 + jf/f_z| / (|1 + jf/f_p1| * |1 + jf/f_p2|)

fitted as **decibels against log-frequency**, not linear magnitude against
linear frequency. Three reasons, and the first one is the one that matters:

  * **dB is the unit the residual gate is written in.** §5.3(b) says
    "residual > 0.5 dB". Fitting in linear magnitude and converting afterwards
    would weight a 0.5 dB error at the peak differently from a 0.5 dB error at
    DC, so the number the gate reads would not be the number the fit minimised.
  * A CTLE response spans decades; least squares on a linear frequency axis
    would put essentially all its weight above 10 GHz, where S3 does not live.
  * The parameters are positive and span decades, so they are fitted as
    `log10` and exponentiated. That removes the positivity constraint entirely
    rather than enforcing it with a penalty, and a bounded optimiser cannot
    wander to a negative pole and report a "successful" fit.

WHAT THIS DELIBERATELY DOES NOT DO
-----------------------------------
**It does not touch `g_dc` from `.op`.** `g_dc` is fitted from the curve like
everything else, because the curve is what the eye sees. The device layer's
own `g_dc_db` (a `meas ... AT=1meg`) is carried alongside as an independent
check, and `CtleFit.g_dc_disagreement_db` reports the difference. They should
agree closely; if they ever do not, that is a finding, not something to
average away.

**It does not extrapolate.** The fit is reported over the band it was given.
A caller asking for the response at 40 GHz from a sweep that stopped at 20 is
asking the model, not the measurement, and `CtleFit.response()` says so in its
docstring rather than refusing -- the CTLE model is analytic and defined
everywhere; it is its AGREEMENT with silicon that is band-limited.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from nebula.common import design_equations as deq
from nebula.common.types import FIT_RESIDUAL_REJECT_DB

TWO_PI = 2.0 * math.pi

#: Frequencies below this are dropped before fitting. The `.ac` sweep starts at
#: 1 MHz and the model is flat there, so the decade below 10 MHz contributes
#: 50 points of pure DC-gain information and drags the fit's weight away from
#: the pole-zero region where the shape is. Not a tuning knob: it is the
#: bottom of the band `.noise` already integrates over (10 MHz - 5 GHz,
#: CLAUDEwa.md §3 S5), so it is a band this project already treats as "where
#: the signal is".
FIT_F_LO_HZ: float = 10e6

#: Top of the fit band. The `.ac` sweep runs to 100 GHz, but `meas ac MAX` is
#: bounded at 20 GHz (`sky130_runner.MAX_SEARCH_TOP_HZ`, G44's fix) because no
#: design that could meet S3 peaks anywhere near it. Fitting the 20-100 GHz
#: tail would spend the model's freedom describing a region no S3 verdict
#: reads, and a one-zero/two-pole form cannot represent the higher-order roll-
#: off up there anyway -- so including it makes the residual worse everywhere
#: that matters. Stated as a band, not silently trimmed.
FIT_F_HI_HZ: float = 20e9


class FitError(ValueError):
    """The fit could not be attempted. Distinct from a fit that was REJECTED."""


@dataclass(frozen=True)
class CtleFit:
    """One measured response, fitted. `ok=False` means DO NOT USE the poles.

    Mirrors `DeviceResult`'s discipline: a rejected fit still carries its
    numbers, because "what did it converge on, and how badly?" is the question
    a rejection makes you want to answer -- but `ok` is the only field a
    caller may branch on.
    """

    ok: bool
    fail_reason: Optional[str]
    g_dc: Optional[float]              # linear V/V
    f_zero_hz: Optional[float]
    f_pole1_hz: Optional[float]
    f_pole2_hz: Optional[float]
    #: RMS error over the fitted band, dB. The quantity §5.3(b)'s gate reads.
    residual_db: float
    #: Worst single-point error over the fitted band, dB. Reported because an
    #: RMS of 0.4 dB with a 3 dB spike at the peak is a bad fit that passes.
    max_residual_db: float
    n_points: int
    f_lo_hz: float
    f_hi_hz: float
    #: `meas ac g_dc` from the device layer, in dB, if the caller passed it.
    #: An INDEPENDENT number: the fit never reads it.
    measured_g_dc_db: Optional[float] = None

    @classmethod
    def from_poles(cls, g_dc: float, f_zero_hz: float, f_pole1_hz: float,
                   f_pole2_hz: float, residual_db: float = 0.0) -> "CtleFit":
        """Wrap an ALREADY-FITTED pole set as a usable CTLE.

        The seam the bridge uses: `DeviceResult` carries the poles (the
        contract puts the fit on the device side of the boundary), so the link
        layer receives them rather than re-fitting. Existing only so there is
        ONE response implementation in the repo rather than one per caller
        (rule 9) — it does no fitting and claims no residual it did not
        measure, which is why `residual_db` must be passed in.
        """
        for name, v in (("g_dc", g_dc), ("f_zero_hz", f_zero_hz),
                        ("f_pole1_hz", f_pole1_hz), ("f_pole2_hz", f_pole2_hz)):
            if not math.isfinite(v) or v <= 0.0:
                raise FitError(f"{name} must be positive and finite, got {v!r}")
        lo, hi = sorted((float(f_pole1_hz), float(f_pole2_hz)))
        return cls(ok=True, fail_reason=None, g_dc=float(g_dc),
                   f_zero_hz=float(f_zero_hz), f_pole1_hz=lo, f_pole2_hz=hi,
                   residual_db=float(residual_db),
                   max_residual_db=float(residual_db),
                   n_points=0, f_lo_hz=math.nan, f_hi_hz=math.nan)

    @property
    def small_signal(self) -> deq.SmallSignal:
        """The fitted response as the repo's own `SmallSignal` (rule 9).

        `peaking_db` is filled with the **asymptotic** `20*log10(f_p1/f_z)`
        because that is what `SmallSignal` documents that field to be. It is
        NOT the realised peaking -- `task8_symbolic.py` measured the asymptote
        over-predicting by a median +1.199 dB across 1311 designs -- so read
        `realised_peaking_db()` for anything that gets compared to S3.
        """
        if not self.ok:
            raise FitError("small_signal read from a rejected fit; check `ok`")
        assert self.f_pole1_hz is not None and self.f_zero_hz is not None
        return deq.SmallSignal(
            g_dc=float(self.g_dc),                      # type: ignore[arg-type]
            f_zero_hz=float(self.f_zero_hz),
            f_pole1_hz=float(self.f_pole1_hz),
            f_pole2_hz=float(self.f_pole2_hz),          # type: ignore[arg-type]
            peaking_db=20.0 * math.log10(self.f_pole1_hz / self.f_zero_hz),
        )

    @property
    def g_dc_db(self) -> float:
        return 20.0 * math.log10(self.g_dc)             # type: ignore[arg-type]

    @property
    def g_dc_disagreement_db(self) -> Optional[float]:
        """Fitted DC gain minus the device layer's own `meas`, dB.

        The §5.3(b) cross-check in its cheapest form. The fit never reads
        `measured_g_dc_db`, so agreement is evidence and disagreement is a
        finding -- neither is built in.
        """
        if self.measured_g_dc_db is None or not self.ok:
            return None
        return self.g_dc_db - self.measured_g_dc_db

    def response(self, f_hz) -> np.ndarray:
        """Complex `H(f)` on a SIGNED frequency axis (Hermitian => real in time).

        Signature and convention deliberately identical to
        `cursors.MatchedCtle.response`, so either can be handed to
        `cursors.pulse_response` (rule 9: one CTLE interface, two ways of
        arriving at one).

        Defined at every frequency, including outside the fitted band -- the
        model is analytic. What is band-limited is its AGREEMENT with silicon;
        `f_lo_hz`/`f_hi_hz` record where that was checked.
        """
        if not self.ok:
            raise FitError("response() read from a rejected fit; check `ok`")
        f = np.asarray(f_hz, dtype=float)
        return (self.g_dc
                * (1.0 + 1j * f / self.f_zero_hz)
                / ((1.0 + 1j * f / self.f_pole1_hz)
                   * (1.0 + 1j * f / self.f_pole2_hz)))

    def magnitude_db(self, f_hz) -> np.ndarray:
        return 20.0 * np.log10(np.abs(self.response(f_hz)))

    def realised_peaking_db(self, n_points: int = 4000) -> tuple[float, float]:
        """`(peaking_db, f_peak_hz)` of the FITTED model, computed not assumed.

        Delegates to `design_equations.realised_peaking_db`, which maximises
        the full magnitude expression numerically -- the same routine the
        pre-screen uses, so the fit and the screen cannot disagree about what
        "the peak" means.
        """
        return deq.realised_peaking_db(self.small_signal, n_points=n_points)


# ─────────────────────────────────────────────────────────────────────────────
# The model, in the units it is fitted in.
# ─────────────────────────────────────────────────────────────────────────────


def _model_db(log_f: np.ndarray, p: np.ndarray) -> np.ndarray:
    """`20*log10|H|` at `10**log_f`, from `p = [log10 gdc, lz, lp1, lp2]`.

    Everything positive is carried as a base-10 logarithm, so the optimiser
    works in an unconstrained space and cannot return a negative pole.
    """
    f = 10.0 ** log_f
    g_dc, fz, fp1, fp2 = 10.0 ** p[0], 10.0 ** p[1], 10.0 ** p[2], 10.0 ** p[3]
    return 20.0 * (np.log10(g_dc)
                   + 0.5 * np.log10(1.0 + (f / fz) ** 2)
                   - 0.5 * np.log10(1.0 + (f / fp1) ** 2)
                   - 0.5 * np.log10(1.0 + (f / fp2) ** 2))


def initial_guess_from_design_equations(
    freq_hz: np.ndarray, mag_db: np.ndarray) -> np.ndarray:
    """A starting point read off the curve itself, in `_model_db`'s parameters.

    NOT from `deq.predict()` — that needs `gm`, `Rs`, `Cs`, `RL`, `CL`, which
    the bridge may not have (a `DeviceResult` carries the response, not the
    netlist). The §6 STRUCTURE is used instead, applied to the measurement:

      * `g_dc` is the low-frequency plateau;
      * peaking `~= 20*log10(f_p1/f_z)` gives the pole-zero RATIO `k` directly
        from the measured peak height;
      * `f_z ~= f_peak / sqrt(k)` places the pair around the measured peak;
      * `f_p2` is the second corner, taken above the top of the band when the
        curve has not turned over inside it.

    **THE THIRD BULLET IS ONLY APPROXIMATE, AND THE FIRST VERSION OF THIS
    DOCSTRING CLAIMED MORE THAN IT SHOULD.** It said "the peak sits between
    `f_z` and `f_p1`", which is false whenever `f_p2` is close enough to pull
    the maximum upward: at `(g_dc, f_z, f_p1, f_p2) = (1.9, 0.6, 2.4, 9.0) GHz`
    the true peak is at **4.52 GHz, well above `f_p1`**, and this guess returns
    `f_z = 2.56 GHz` against a true 0.6 GHz — a factor of 4.

    That is fine, and saying why is the point: **the guess's job is the BASIN,
    not the answer.** `test_the_fit_converges_from_deliberately_bad_starts`
    is the evidence — the same data fitted from starts spanning two decades
    either side lands on the same parameters to 1e-6, so the objective has one
    minimum in the region and the start only buys iterations.
    """
    g_dc_db = float(np.median(mag_db[:3]))
    j = int(np.argmax(mag_db))
    peak_db = float(mag_db[j])
    f_peak = float(freq_hz[j])

    peaking_db = max(peak_db - g_dc_db, 0.05)
    k = 10.0 ** (peaking_db / 20.0)
    fz = max(f_peak / math.sqrt(k), freq_hz[0])
    fp1 = fz * k

    # Where does the response fall back through its own peak? That is f_p2's
    # neighbourhood. If it never does inside the band, put f_p2 above the top
    # rather than inside it, so the fit is not started with a pole in a place
    # the data says there is none.
    above = np.nonzero((freq_hz > f_peak) & (mag_db < g_dc_db))[0]
    fp2 = float(freq_hz[above[0]]) if above.size else float(freq_hz[-1]) * 2.0
    fp2 = max(fp2, fp1 * 1.05)

    return np.array([g_dc_db / 20.0, math.log10(fz), math.log10(fp1),
                     math.log10(fp2)])


def fit_ctle(freq_hz: Sequence[float], mag_db: Sequence[float], *,
             f_lo_hz: float = FIT_F_LO_HZ, f_hi_hz: float = FIT_F_HI_HZ,
             reject_above_db: float = FIT_RESIDUAL_REJECT_DB,
             measured_g_dc_db: Optional[float] = None,
             p0: Optional[Sequence[float]] = None,
             max_nfev: int = 20000) -> CtleFit:
    """Fit one measured magnitude curve. Never raises on a BAD fit; rejects it.

    Raises `FitError` only when the fit cannot be ATTEMPTED — empty input,
    non-finite samples, too few points in band. That distinction is the same
    one `run_point` draws: a circuit that fits badly is a fact about the
    circuit and comes back `ok=False`; a caller handing over garbage is a bug.
    """
    f = np.asarray(freq_hz, dtype=float).ravel()
    m = np.asarray(mag_db, dtype=float).ravel()
    if f.size == 0 or f.size != m.size:
        raise FitError(f"freq_hz and mag_db must be the same non-empty length, "
                       f"got {f.size} and {m.size}")
    if not np.all(np.isfinite(f)) or not np.all(np.isfinite(m)):
        raise FitError("freq_hz/mag_db contain non-finite samples — a NaN here "
                       "would be fitted as though it were data (G54's shape)")

    band = (f >= f_lo_hz) & (f <= f_hi_hz)
    if int(band.sum()) < 8:
        raise FitError(
            f"only {int(band.sum())} sample(s) in [{f_lo_hz:g}, {f_hi_hz:g}] Hz; "
            f"four free parameters cannot be fitted to that")
    fb, mb = f[band], m[band]
    log_f = np.log10(fb)

    # `p0` is exposed so the basin can be PROBED rather than assumed: a
    # four-parameter fit that only ever starts from one place cannot tell a
    # unique minimum from a lucky one.
    p0 = (np.asarray(p0, dtype=float) if p0 is not None
          else initial_guess_from_design_equations(fb, mb))
    if p0.shape != (4,):
        raise FitError(f"p0 must be 4 log10 parameters, got shape {p0.shape}")

    try:
        from scipy.optimize import least_squares
    except ImportError as exc:                              # pragma: no cover
        raise FitError(f"scipy is required for the pole-zero fit: {exc}")

    def residuals(p: np.ndarray) -> np.ndarray:
        return _model_db(log_f, p) - mb

    # Bounds in log10 space, wide but not unbounded: a pole below the fitted
    # band or above 1 THz is not a CTLE, it is the optimiser escaping. Stated
    # as decades either side of the data rather than as picked constants.
    lo_dec, hi_dec = math.log10(fb[0]) - 2.0, math.log10(fb[-1]) + 2.0
    bounds = (np.array([-6.0, lo_dec, lo_dec, lo_dec]),
              np.array([+6.0, hi_dec, hi_dec, hi_dec]))
    p0 = np.clip(p0, bounds[0] + 1e-9, bounds[1] - 1e-9)

    sol = least_squares(residuals, p0, bounds=bounds, max_nfev=max_nfev)
    r = residuals(sol.x)
    rms = float(np.sqrt(np.mean(r ** 2)))
    worst = float(np.max(np.abs(r)))

    g_dc = float(10.0 ** sol.x[0])
    fz, fp1, fp2 = (float(10.0 ** sol.x[1]), float(10.0 ** sol.x[2]),
                    float(10.0 ** sol.x[3]))

    # A one-zero/two-pole form is symmetric in its two poles: (fp1, fp2) and
    # (fp2, fp1) describe the SAME response, and the optimiser may return
    # either. §6 names f_p1 as the degeneration pole `k/(Rs*Cs)` and f_p2 as
    # the load pole `1/(RL*CL)`, and downstream code reads them by that
    # meaning -- `SmallSignal.degeneration_factor` is literally f_p1/f_z. So
    # the pair is ORDERED here, once, rather than every caller guessing.
    if fp2 < fp1:
        fp1, fp2 = fp2, fp1

    reason: Optional[str] = None
    if not sol.success:
        reason = f"least_squares did not converge: {sol.message}"
    elif not all(map(math.isfinite, (g_dc, fz, fp1, fp2))):
        reason = "fit returned a non-finite parameter"
    elif rms > reject_above_db:
        reason = (f"fit residual {rms:.3f} dB exceeds the "
                  f"{reject_above_db:.2f} dB gate (CLAUDEwa.md §5.3b): the "
                  f"one-zero/two-pole model does not describe this response, "
                  f"and its poles must not be used")

    return CtleFit(
        ok=reason is None, fail_reason=reason,
        g_dc=g_dc, f_zero_hz=fz, f_pole1_hz=fp1, f_pole2_hz=fp2,
        residual_db=rms, max_residual_db=worst,
        n_points=int(fb.size), f_lo_hz=float(fb[0]), f_hi_hz=float(fb[-1]),
        measured_g_dc_db=measured_g_dc_db,
    )


def fit_from_point(pt) -> CtleFit:
    """Fit a `Sky130Point` captured with `run_point(..., ac_sweep=True)`.

    The convenience seam the bridge uses, kept here so the "which fields carry
    the curve" knowledge lives next to the fitter rather than in the bridge.
    """
    if getattr(pt, "ac_freq_hz", None) is None or getattr(pt, "ac_mag_db", None) is None:
        raise FitError(
            "this Sky130Point carries no AC curve — it was run without "
            "`ac_sweep=True`, and four `meas` scalars cannot be fitted")
    return fit_ctle(pt.ac_freq_hz, pt.ac_mag_db,
                    measured_g_dc_db=getattr(pt, "g_dc_db", None))


__all__ = (
    "CtleFit", "FitError", "fit_ctle", "fit_from_point",
    "initial_guess_from_design_equations",
    "FIT_F_LO_HZ", "FIT_F_HI_HZ",
)
