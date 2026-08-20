"""
device/sky130_runner.py — one SKY130 sizing point, four analyses, one call.

WHY THIS EXISTS ALONGSIDE `ngspice_runner.py`
---------------------------------------------
`ngspice_runner.py` drives the **generic BSIM4, 1.2 V** netlist that the
original G1 hand-design was done on. Session 9c found that design point badly
mis-biased (gm/I_D = 1.7, sources 0.44 V below ground), and the corrected
reference is a **SKY130 nfet_01v8 device at VDD = 1.8 V**. The parameter
bounds and the 5.3% S3 yield were both measured inside the old point, so both
have to be re-derived here (HANDOFF §8, the START HERE block).

This module is that vehicle. One ngspice invocation per sizing point performs

    .op     bias primitives (gm, gmbs, vth, vds, vdsat, id, node voltages)
    .ac     g_dc / g_nyq / g_pk+f_pk           -> S3
    .noise  inoise_total, differential-referred -> S5
    .dc     differential transfer curve         -> the MEASURED output swing

and every derived quantity is computed in Python from parsed primitives.
Nothing is computed in `.control` (HANDOFF G26/G30, CLAUDEwa.md §8 rule 9),
and the output is grepped for warning-shaped failures before any number is
believed (§8 rule 10).

THE MEASURED SWING, AND WHY IT IS NOT `2*I_tail*RL`
---------------------------------------------------
Session 9c compared the required output amplitude against "available
differential swing = 2*IT*RL = 1.2 Vpp" at IT = 1.5 mA, RL = 400. Two
independent problems with that number:

1. **It is a peak, not a peak-to-peak.** Full current steering puts
   `2*IT*RL` across the load in EACH polarity, so the differential output
   spans `+/- 2*IT*RL` = 2.4 Vpp, not 1.2 Vpp.
2. **It is a steering limit, and the pair may leave saturation first** — the
   output can only fall until `vds < vdsat`, which is a supply-headroom
   property. Which of the two binds is a question about the operating point,
   not something the formula knows.

Neither is fixable by algebra, so `swing()` measures all three limits off a DC
transfer curve: the 1 dB gain-compression point (the honest *linear* swing,
and the number `DeviceResult.vout_swing_v` should carry), the saturation
limit, and the steering ceiling.

**All three are OUTPUT-referred, and for one whole question that is the wrong
end of the stage.** S8 fails on this project's delivered design because the
required output swing exceeds the compression limit, and a reader wanting to
know *how hard may I drive this input* has to divide that limit by a gain they
must go and look up. `SwingLimits.linear_in_pp_v` reports the SAME compression
event on the input axis, in the same differential-peak-to-peak volts as
`LinkConfig.v_in_diff_pp_v` and `PCIE_GEN2_TX_DIFF_PP_MIN_V`, so the
comparison the spec table needs is a subtraction rather than a conversion.
Both projections come off one swept sample; neither is computed from the
other.

NOISE REFERENCE — checked, and it is NOT a factor of two
--------------------------------------------------------
This netlist names `Vid` as the `.noise` input source; the older ones name
`vinp`, a single-ended source with `ac 0.5`. That looked like a 2x
input-referred-noise discrepancy waiting to happen, so it was measured
rather than reasoned about: the identical circuit gives
**inoise_total = 1.723594e-04 either way** (2026-08-04). ngspice normalises
by the named source's AC magnitude, so a symmetric `+0.5 / -0.5` pair and a
single unit differential source refer to the same 1 V differential input.
Recorded because "obviously a factor of two" is how the last three units bugs
in this project introduced themselves.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.device.crosscheck import (
    find_device_scalar,
    parse_meas,
    parse_scalar,
    scan_for_silent_failures,
)
from nebula.device.netlist_gates import assert_no_inert_writes
from nebula.device.ngspice_runner import ngspice_path
from nebula.device.passives import PassiveGeometry
from nebula.device.tail import TailDevice

#: Directory holding `.spiceinit` (ngbehavior=hsa, needed at PARSE time, G29)
#: and the trimmed SKY130 library (G36).
SPICE_DIR: Path = Path(__file__).resolve().parent / "spice"

#: The trimmed nfet_01v8-only library: 0.42 s per invocation instead of
#: 16-35 s, verified bit-identical on gm/gmbs/vth/id/g_dc/g_pk/inoise (G36).
TRIMMED_LIB: Path = SPICE_DIR / "sky130_nfet_only.lib.spice"

#: The EXTENDED trim: nfet_01v8 plus the poly resistor and MIM families, and
#: the full 5x5 (MOS x passive) corner cross product as 25 named sections
#: (G58). Verified rel=0 abs=0 against the full library
#: (`test_trimmed_lib_passives.py`). Needed the moment `to_geometry()` output
#: reaches a netlist. Costs 4655 ms against the nfet-only trim's 634 ms.
CTLE_LIB: Path = SPICE_DIR / "sky130_ctle.lib.spice"

#: SKY130's 1.8 V thin-oxide NMOS — the S2 input pair.
NFET_01V8: str = "sky130_fd_pr__nfet_01v8"

#: SKY130's thick-oxide device, 5.0 V gate rating. Present so the
#: "does a higher-voltage device dissolve the compression problem?" question
#: can be measured rather than argued. Needs its model files added to the
#: trimmed library (see `lib_for_device`).
NFET_G5V0: str = "sky130_fd_pr__nfet_g5v0d10v5"

VALID_CORNERS: tuple[str, ...] = ("tt", "ss", "ff", "sf", "fs")

#: Top of the `meas ac ... MAX` search, and the frequency `g_top` is read at.
#:
#: WAS 50 GHz, WHICH PRODUCED A FALSE PEAK (G44). `meas ac MAX` returns the
#: largest sample in its range; for a response still RISING at the top of that
#: range it returns the range edge, and the caller cannot tell that from a
#: genuine interior maximum. Measured example: rl=111, cl=50f reported
#: `f_pk = 47.863 GHz` — the sweep edge, not a peak.
#:
#: 20 GHz is 8x above S3's 1.25-2.5 GHz window, so no design that could meet S3
#: has its maximum anywhere near the edge.
#:
#: A CLAIM THAT WAS MADE HERE AND TURNED OUT TO BE FALSE, kept because it is
#: the kind of thing that gets assumed: "moving the edge 50 -> 20 GHz cannot
#: change an S3 verdict, since a design peaking above 20 GHz fails the window
#: either way." It can, and it does — measured, S3 moved 165 -> 166 at
#: cl = 50 fF. The reason is LOCAL maxima. `MAX` returns the largest sample in
#: its range; a response with a small in-band peak at 2 GHz and a larger one at
#: 30 GHz reported the 30 GHz one under the old edge and reports the 2 GHz one
#: under the new. The bounded search is the more useful of the two — an
#: equaliser is judged on the peak it puts where the data is — but it is a
#: BEHAVIOUR CHANGE, not merely a guard. Measured deltas: nebula/S9_YIELD.md §1.
MAX_SEARCH_TOP_HZ: float = 20e9

#: How far below the peak the response must have fallen by MAX_SEARCH_TOP_HZ
#: before the peak counts as interior, and how far it must have risen above
#: DC. Same number both sides; 0.25 dB is the existing rise threshold.
PEAK_MARGIN_DB: float = 0.25

#: Bottom of the `meas ac ... MAX` search, in Hz. `FROM=10meg` in the deck.
#:
#: **The netlist is the definition and this constant MIRRORS it**, which is a
#: deliberate exception to rule 9 rather than an oversight: turning `FROM=10meg`
#: into a `{f_bot}` placeholder edits a template every published number came
#: from, and the byte-identity argument that protects `ac_sweep` protects it by
#: NOT touching those bytes. What keeps the two one thing is a test --
#: `test_the_max_search_window_matches_the_netlist` parses `FROM=` and `TO=` out
#: of the assembled deck and asserts them against these two constants, so either
#: side moving alone goes red. G32 was a model card that differed between the
#: netlist and the runner WITH NO SUCH TEST; that is the failure this avoids.
MAX_SEARCH_BOT_HZ: float = 10e6


# ---------------------------------------------------------------------------
# The INTERPOLATED peak -- G74's reward ceiling, addressed at its source.
#
# `meas ac g_pk MAX vd_db` can only ever report a frequency that is ON the
# `ac dec 50 1meg 100g` lattice, i.e. a grid 0.066439 octaves apart. G74 traced
# the +8.950669 reward ceiling to exactly that: `reward_v1`'s feasible branch is
# `B + min_i(margin_i/tol_i)` with `S3_f_peak` binding, its margin is
# `0.5 - |log2(f_peak/f_target)|` octaves, and the nearest lattice point to the
# mid-window target is 0.024665 octaves away. So the best attainable score is a
# property of the SWEEP GRID -- four independent runs found four DIFFERENT
# designs all scoring 8.950670 -- and best-score-at-budget cannot separate two
# search methods on a problem whose optimum is a plateau.
#
# The fix is not a denser sweep: that costs simulation time on every evaluation
# and the grid would still be a grid. It is to stop reading the peak off the
# lattice. A `db()` magnitude response near its maximum is locally quadratic in
# LOG frequency, so the three samples bracketing the discrete maximum determine
# a parabola whose vertex locates the peak far inside one grid step. **Zero
# extra simulation cost:** the curve is already dumped by
# `run_point(ac_sweep=True)`, which session 21 proved changes no measured value.
#
# THREE THINGS THIS DELIBERATELY DOES NOT DO:
#
#  1. **It does not touch `f_pk_hz` / `g_pk_db`.** Those stay exactly what
#     `meas` said, so every published number still reproduces. The interpolated
#     pair lands in NEW fields and is opt-in (`run_point(ac_peak_interp=True)`).
#  2. **It does not widen the search window.** The parabola is fitted inside
#     `[MAX_SEARCH_BOT_HZ, MAX_SEARCH_TOP_HZ]`, the same window `meas` searches,
#     because a peak found outside that window is the G44 failure this project
#     already has a guard for.
#  3. **It does not rescue a sweep-edge peak.** A discrete maximum sitting ON a
#     window edge has no bracketing triple, so there is no vertex to report --
#     and an "interpolated" peak at or beyond the last grid point is the same
#     fictitious peak G44 rejects, whatever arithmetic produced it. That case
#     comes back `ok=False` with `edge` set, and the interpolated measurement
#     path REFUSES it rather than quietly substituting the grid point.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PeakInterp:
    """The parabolic-vertex peak, and everything needed to distrust it.

    `ok=False` is a normal outcome rather than an error: the discrete numbers
    are still good, it is only the sub-grid refinement that is unavailable, and
    the caller must be able to tell WHY (rule 1 -- unknown stays empty and says
    so, instead of silently becoming the grid point).
    """

    ok: bool
    #: Why not, when `ok` is False. `None` exactly when `ok` is True.
    reason: Optional[str] = None
    #: The vertex. `None` unless `ok`.
    f_hz: Optional[float] = None
    g_db: Optional[float] = None
    #: The DISCRETE maximum inside the search window -- what `meas ac MAX`
    #: should have reported. Present whenever the window held any samples, so
    #: a failed interpolation can still be cross-checked against `f_pk_hz`.
    f_grid_hz: Optional[float] = None
    g_grid_db: Optional[float] = None
    #: Index of `f_grid_hz` into the FULL curve, not into the window.
    index: Optional[int] = None
    n_in_window: int = 0
    #: "top" / "bottom" when the discrete maximum sits on a window edge, so
    #: there is no bracketing triple. `"top"` is the G44 condition.
    edge: Optional[str] = None
    #: Vertex offset from the grid point, in octaves. Signed. `None` unless ok.
    delta_octaves: Optional[float] = None
    #: The lattice step actually observed, in octaves. 0.066439 for `dec 50`.
    step_octaves: Optional[float] = None
    #: `y0 - 2*y1 + y2` in dB. Strictly negative at a true interior maximum;
    #: reported because a near-zero value means a flat top, where the vertex
    #: position is dominated by whatever numerical noise is left in the curve.
    curvature_db: Optional[float] = None

    def as_dict(self) -> dict:
        return {
            "ok": self.ok, "reason": self.reason,
            "f_hz": self.f_hz, "g_db": self.g_db,
            "f_grid_hz": self.f_grid_hz, "g_grid_db": self.g_grid_db,
            "index": self.index, "n_in_window": self.n_in_window,
            "edge": self.edge, "delta_octaves": self.delta_octaves,
            "step_octaves": self.step_octaves,
            "curvature_db": self.curvature_db,
        }


def parabolic_vertex(y0: float, y1: float, y2: float
                     ) -> Optional[tuple[float, float]]:
    """Vertex of the parabola through three EQUALLY SPACED samples.

    Returns `(delta, y_vertex)` where `delta` is the offset from the middle
    sample in units of the spacing, or `None` when no maximum-vertex exists.

    Split out as its own function for the reason G73 (the ARGMAX one)
    states in general terms: the
    two refusals below are UNREACHABLE from `interpolate_peak_log_f`, because
    `np.argmax` returns the FIRST maximal sample, which forces `y1 > y0` and
    `y1 >= y2`, hence `y0 - 2*y1 + y2 < 0` strictly and `|delta| <= 0.5`. A
    guard whose condition cannot be reached is indistinguishable from a guard
    that was deleted — so the arithmetic lives here, where a test can hand it a
    flat triple directly and watch it refuse, and the composition is asserted
    separately as the invariant it is.
    """
    curv = y0 - 2.0 * y1 + y2
    if not curv < 0.0:
        return None                    # a flat or convex triple has no maximum
    delta = 0.5 * (y0 - y2) / curv
    if not abs(delta) <= 0.5 + 1e-9:
        return None                    # the vertex is outside its own cell
    return delta, y1 - 0.25 * (y0 - y2) * delta


def interpolate_peak_log_f(
    freq_hz,
    mag_db,
    f_lo: float = MAX_SEARCH_BOT_HZ,
    f_hi: float = MAX_SEARCH_TOP_HZ,
) -> PeakInterp:
    """Locate the response maximum by parabolic interpolation in log frequency.

    Three points bracketing the discrete maximum, `x = log2(f)`, `y` in dB.
    With the samples equally spaced by `h` octaves the vertex sits at

        delta = 0.5 * (y0 - y2) / (y0 - 2*y1 + y2)        [in units of h]
        f     = f1 * 2**(delta * h)
        g     = y1 - 0.25 * (y0 - y2) * delta

    and `|delta| <= 0.5` identically when `y1` is the largest of the three.

    **Equal spacing is CHECKED, not assumed.** The deck sweeps `dec 50`, which
    is uniform in log frequency, but the formula above is the vertex of the
    fitted parabola only when it is -- a non-uniform grid would produce a
    plausible, slightly wrong answer rather than an error. So a mismatch is a
    named failure.
    """
    f = np.asarray(freq_hz, dtype=float).ravel()
    y = np.asarray(mag_db, dtype=float).ravel()
    if f.shape != y.shape:
        return PeakInterp(ok=False,
                          reason=f"freq {f.shape} and mag {y.shape} differ")
    inside = (f >= f_lo) & (f <= f_hi)
    n_in = int(inside.sum())
    if n_in < 3:
        return PeakInterp(ok=False, n_in_window=n_in,
                          reason=f"only {n_in} samples in [{f_lo:.4g}, "
                                 f"{f_hi:.4g}] Hz; a parabola needs 3")
    if not np.all(np.isfinite(y[inside])):
        return PeakInterp(ok=False, n_in_window=n_in,
                          reason="the response has non-finite samples inside "
                                 "the search window")

    idx = np.flatnonzero(inside)
    jw = int(np.argmax(y[idx]))            # index WITHIN the window
    j = int(idx[jw])                       # index into the full curve
    common = dict(f_grid_hz=float(f[j]), g_grid_db=float(y[j]),
                  index=j, n_in_window=n_in)

    if jw == n_in - 1:
        return PeakInterp(ok=False, edge="top",
                          reason=f"the maximum IS the top of the search window "
                                 f"({f[j]:.6g} Hz): the response is still "
                                 f"rising at {f_hi:.4g} Hz, so there is no "
                                 f"interior peak to interpolate (G44)",
                          **common)
    if jw == 0:
        return PeakInterp(ok=False, edge="bottom",
                          reason=f"the maximum IS the bottom of the search "
                                 f"window ({f[j]:.6g} Hz): the response falls "
                                 f"monotonically (G44's other half)",
                          **common)

    f0, f1, f2 = float(f[j - 1]), float(f[j]), float(f[j + 1])
    y0, y1, y2 = float(y[j - 1]), float(y[j]), float(y[j + 1])
    h_lo = math.log2(f1 / f0)
    h_hi = math.log2(f2 / f1)
    if h_lo <= 0.0 or abs(h_hi - h_lo) > 1e-6 * h_lo:
        return PeakInterp(ok=False, step_octaves=h_lo,
                          reason=f"the bracketing samples are not equally "
                                 f"spaced in log frequency ({h_lo:.9g} vs "
                                 f"{h_hi:.9g} octaves); the vertex formula "
                                 f"does not apply",
                          **common)

    curv = y0 - 2.0 * y1 + y2
    vertex = parabolic_vertex(y0, y1, y2)
    if vertex is None:
        # UNREACHABLE from here (see `parabolic_vertex`): an argmax-selected
        # interior sample forces a strictly concave triple with the vertex
        # inside its own cell. Kept as a refusal rather than an assert because
        # the invariant belongs to the argmax, and the argmax is one edit away
        # from someone's tie-breaking rule.
        return PeakInterp(ok=False, step_octaves=h_lo, curvature_db=curv,
                          reason=f"no maximum-vertex exists for the triple "
                                 f"bracketing the discrete maximum "
                                 f"(y0-2y1+y2 = {curv:+.6g} dB)",
                          **common)
    delta, g_pk = vertex
    f_pk = f1 * 2.0 ** (delta * h_lo)
    if f_pk >= float(f[idx[-1]]) or f_pk <= float(f[idx[0]]):
        # Cannot happen with an interior `j`, and it is checked anyway: an
        # interpolated peak at or beyond the last grid point is the SAME
        # fictitious peak G44 rejects, whatever arithmetic produced it.
        return PeakInterp(ok=False, edge="top", step_octaves=h_lo,
                          curvature_db=curv, delta_octaves=delta * h_lo,
                          reason=f"the interpolated peak {f_pk:.6g} Hz lands "
                                 f"on or outside the edge of the search window",
                          **common)
    return PeakInterp(ok=True, f_hz=f_pk, g_db=g_pk, step_octaves=h_lo,
                      curvature_db=curv, delta_octaves=delta * h_lo, **common)



# ─────────────────────────────────────────────────────────────────────────────
# The sizing point.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SizingPoint:
    """One CTLE sizing point, in the units the netlist wants.

    `w` and `l` are **plain numbers in microns** — the trimmed library sets
    `.option scale=1.0u`, so `w=40` means 40 um and `w=40e-6` would mean
    40 picometres and abort with the misleading "could not find a valid
    modelname" (G31/G36).

    `i_tail_per_side_a` is the current in ONE branch. The topology uses one
    sink per side (a single shared tail would short out the degeneration
    network), so total supply current is `2 * i_tail_per_side_a` plus, when a
    real tail is fitted, the mirror's reference branch.

    `tail` selects WHICH sink. `None` — the default — keeps the two ideal
    current sinks every published result in this project was measured with, so
    sessions 9d through 12b stay reproducible bit for bit. A `TailDevice`
    replaces them with a real current mirror; see `nebula/device/tail.py`.

    `passives` does the same for R and C, and for the same reason. `None`
    keeps the ideal `R`/`C` elements every result through session 16 was
    measured with; a `PassiveGeometry` from `passives.to_geometry()` replaces
    them with drawn SKY130 devices. Note what does NOT move: `cl` stays ideal
    either way, because it is the following stage's input capacitance — a
    screened context variable (CL_RANGE.md), not a device this circuit draws.
    """

    w: float                     # um
    l: float                     # um
    nf: int
    rs: float                    # ohm, FULL source-to-source (the /2 in §6)
    cs: float                    # F
    rl: float                    # ohm, per side
    cl: float                    # F, per side
    i_tail_per_side_a: float
    vcm: float                   # V
    vdd: float = 1.8             # V
    device: str = NFET_01V8
    #: None => two IDEAL current sinks (legacy, and the default). A TailDevice
    #: => a real current mirror. Every corner spread measured with `None` is an
    #: UNDERSTATEMENT (G47); that is the whole reason this field exists.
    tail: Optional[TailDevice] = None
    #: None => ideal R/C (legacy, and the default). A PassiveGeometry => drawn
    #: SKY130 devices, which also pulls in the extended library
    #: (`sky130_ctle.lib.spice`) and its 7.3x parse cost. `rs`/`cs`/`rl` above
    #: stay the REQUESTED values; what the drawn devices actually measure is
    #: `passives.rs.r_actual_ohm` and friends, and the two differ by the
    #: quantisation error `to_geometry` reports.
    passives: Optional[PassiveGeometry] = None

    @classmethod
    def from_params(
        cls,
        params: "dict[str, float]",
        vdd: float = 1.8,
        device: str = NFET_01V8,
        tail: Optional[TailDevice] = None,
        passives: Optional[PassiveGeometry] = None,
    ) -> "SizingPoint":
        """Build a point from a `common/params.py`-style dict.

        TWO UNIT CONVERSIONS LIVE HERE AND NOWHERE ELSE. Both are the shape of
        bug this project keeps hitting (HANDOFF's failure mode 2), so they are
        written down once and tested rather than repeated at call sites:

        1. **`w_in` / `l_in` are SI METRES in `BOUNDS`, microns in the netlist.**
           `BOUNDS` stays SI because that is what every other length in the repo
           is. The SKY130 libraries set `.option scale=1e-6`, so the netlist
           wants plain numbers in microns (G31). Multiply by 1e6, once, here.
        2. **`i_bias` is the TOTAL supply current; the netlist has two sinks.**
           The topology needs one ideal sink PER SIDE (a shared tail would
           short out the degeneration network), each carrying half. Getting
           this backwards doubles every power number and halves every swing.
        """
        missing = [k for k in ("w_in", "l_in", "nf_in", "i_bias", "rs", "cs",
                               "rl", "cl", "vcm_in") if k not in params]
        if missing:
            raise KeyError(f"params is missing {missing}")
        return cls(
            w=float(params["w_in"]) * 1e6,
            l=float(params["l_in"]) * 1e6,
            nf=int(round(float(params["nf_in"]))),
            rs=float(params["rs"]),
            cs=float(params["cs"]),
            rl=float(params["rl"]),
            cl=float(params["cl"]),
            i_tail_per_side_a=float(params["i_bias"]) / 2.0,
            vcm=float(params["vcm_in"]),
            vdd=vdd,
            device=device,
            tail=tail,
            passives=passives,
        )

    @property
    def i_ref_a(self) -> float:
        """The mirror's reference current. Zero when the tail is ideal."""
        return (0.0 if self.tail is None
                else self.tail.i_ref_a(self.i_tail_per_side_a))

    @property
    def i_total_a(self) -> float:
        """REQUESTED total supply current, including the mirror reference.

        A prediction, not a measurement. What the mirror actually delivers is
        `Sky130Point.i_supply_a`, read off the supply branch — and the two
        differ by the mirror's gain error, which at TT is around -8 %. Use the
        measured one for anything that reaches a deliverable (rule 1).
        """
        return 2.0 * self.i_tail_per_side_a + self.i_ref_a

    @property
    def power_w(self) -> float:
        """Requested static power. See `i_total_a` on why it is a prediction."""
        return self.vdd * self.i_total_a

    @property
    def v_out_dc_nominal(self) -> float:
        """VDD - I*RL, the quiescent output. A prediction, not a measurement —
        the run reports the actual node voltage."""
        return self.vdd - self.i_tail_per_side_a * self.rl


@dataclass
class Sky130Point:
    """Everything one invocation measures. `ok=False` => trust no field."""

    ok: bool
    fail_reason: Optional[str] = None
    # --- .op primitives ---
    gm: Optional[float] = None
    gmbs: Optional[float] = None
    gds: Optional[float] = None
    vth: Optional[float] = None
    vds: Optional[float] = None
    vdsat: Optional[float] = None
    vgs: Optional[float] = None
    id_a: Optional[float] = None
    v_out_dc: Optional[float] = None
    v_src_dc: Optional[float] = None
    #: Total current drawn from VDD, measured off the supply branch. Present on
    #: every run; it is what `power_measured_w` bills. With an ideal tail it
    #: equals `2 * i_tail_per_side_a` to rounding; with a mirror it also carries
    #: the reference branch AND the mirror's gain error, neither of which the
    #: requested `SizingPoint.power_w` knows about.
    i_supply_a: Optional[float] = None
    # --- .op primitives of the TAIL (None when the tail is ideal) ---
    i_tail_meas_a: Optional[float] = None
    vds_tail: Optional[float] = None
    vdsat_tail: Optional[float] = None
    vgs_tail: Optional[float] = None
    vth_tail: Optional[float] = None
    gm_tail: Optional[float] = None
    i_ref_meas_a: Optional[float] = None
    v_bias_dc: Optional[float] = None
    # --- .ac ---
    g_dc_db: Optional[float] = None
    g_nyq_db: Optional[float] = None
    g_pk_db: Optional[float] = None
    f_pk_hz: Optional[float] = None
    #: Gain at MAX_SEARCH_TOP_HZ. Exists solely so "is this an interior
    #: maximum?" is a MEASUREMENT (did the response come back down?) rather
    #: than a guess about where the peak sits relative to the sweep edge (G44).
    g_top_db: Optional[float] = None
    # --- .noise ---
    vn_in_vrms: Optional[float] = None
    #: Per-instance integrated input-referred noise, RMS volts, only when
    #: `run_point(noise_detail=True)`. Adds in QUADRATURE to `vn_in_vrms`.
    noise_by_device: Optional[dict] = None
    # --- .ac magnitude sweep (raw), only when run_point(ac_sweep=True) ---
    #: The curve the four `meas` scalars are read off, kept so the pole-zero
    #: fit (`link/fit.py`) has something to fit. `ac_mag_db` is the
    #: DIFFERENTIAL magnitude in dB — the same `vd_db` vector `meas` uses, so
    #: the fit and S3 cannot disagree about what the response is (rule 9).
    ac_freq_hz: Optional[np.ndarray] = field(default=None, repr=False)
    ac_mag_db: Optional[np.ndarray] = field(default=None, repr=False)
    # --- the interpolated peak, only when run_point(ac_peak_interp=True) ---
    #: The parabolic-vertex peak (see `interpolate_peak_log_f`). **A SECOND
    #: pair of fields rather than a correction to `f_pk_hz` / `g_pk_db`**, so
    #: every published number keeps reproducing and a caller has to ASK for the
    #: refined one. `None` when the flag was off OR when the interpolation
    #: refused -- `peak_interp["reason"]` says which, and the two must not be
    #: confused: "not asked for" and "asked for and impossible" are different
    #: facts about a design.
    f_pk_interp_hz: Optional[float] = None
    g_pk_interp_db: Optional[float] = None
    #: `PeakInterp.as_dict()`. Present whenever the flag was on, including on
    #: refusal -- it is where the refusal reason lives.
    peak_interp: Optional[dict] = field(default=None, repr=False)
    # --- S4: HD3 by transient + FFT, only when run_point(hd3=True) ---
    #: `20*log10(|V3|/|V1|)` at the S4 tone. Large and NEGATIVE when good.
    hd3_dbc: Optional[float] = None
    #: How it was measured — tone, drive level, window, bins. Reported beside
    #: the number because HD3 goes as ~Vin^2 and an unstated drive level makes
    #: it meaningless.
    hd3_detail: Optional[dict] = field(default=None, repr=False)
    # --- .dc swing curve (raw, so Python owns every derived number) ---
    vid: Optional[np.ndarray] = field(default=None, repr=False)
    vod: Optional[np.ndarray] = field(default=None, repr=False)
    sat_ok: Optional[np.ndarray] = field(default=None, repr=False)
    id_min: Optional[np.ndarray] = field(default=None, repr=False)
    # --- bookkeeping ---
    point: Optional[SizingPoint] = None
    corner: str = "tt"
    runtime_s: float = 0.0
    #: Raw ngspice stdout+stderr, kept ONLY when `run_point(keep_text=True)`.
    #: It exists so a second, independent code path can re-derive the numbers
    #: from the text this run actually produced (`rl/evaluator.py`'s §6d
    #: cross-check) instead of comparing a function against itself. Off by
    #: default because a training run holding 500 copies of ngspice's output is
    #: a memory leak with no reader.
    raw_text: Optional[str] = field(default=None, repr=False)
    #: The assembled SPICE deck, kept ONLY when `run_point(keep_netlist=True)`.
    #:
    #: **It is the deck that RAN, not a second copy of it**, and that is the
    #: whole reason it lives here instead of in whatever wants to print one.
    #: G32 is exactly this defect one level down: `g1_handdesign.cir` and the
    #: runner described "the same" reference point with `.model` cards that
    #: differed by one parameter, so anyone sanity-checking by opening the
    #: netlist was quietly reading a circuit that had never been simulated.
    #: Rule 9: a human reading this netlist must see the values that produced
    #: the published numbers, which is only guaranteed if it is the same
    #: string.
    netlist: Optional[str] = field(default=None, repr=False)

    # ---- derived: S3 ----
    @property
    def peaking_db(self) -> float:
        """max|H| relative to |H(DC)| — S3 reading (a)."""
        return self.g_pk_db - self.g_dc_db      # type: ignore[operator]

    @property
    def nyquist_boost_db(self) -> float:
        """|H(2.5 GHz)| relative to |H(DC)| — S3 reading (b). Not the same
        number as `peaking_db`; CLAUDEwa.md §3 requires reporting both."""
        return self.g_nyq_db - self.g_dc_db     # type: ignore[operator]

    @property
    def g_nyq_linear(self) -> float:
        return 10.0 ** (self.g_nyq_db / 20.0)   # type: ignore[operator]

    @property
    def g_dc_linear(self) -> float:
        return 10.0 ** (self.g_dc_db / 20.0)    # type: ignore[operator]

    @property
    def has_interior_peak(self) -> bool:
        """True iff |H| has a genuine interior maximum, not a sweep-edge one.

        THE G44 FIX. The old test was `peaking_db > 0.25 and f_pk_hz > 50e6`,
        which asks where the reported peak SITS. That catches a monotonically
        FALLING response — it reports f_pk at the 10 MHz sweep start — but
        sails straight past a response still RISING at the top of the range,
        which reports f_pk at the range edge with a large, entirely fictitious
        `peaking_db`.

        This asks the question directly instead: a maximum is interior iff the
        response is higher there than at BOTH ends of the search range. No
        frequency guard is involved, so nothing in S3's 1.25-2.5 GHz window is
        excluded by it — which a "reject anything within a decade of the edge"
        rule would do, since a decade below 20 GHz is 2 GHz and lands inside
        the spec window.
        """
        return (self.peaking_db > PEAK_MARGIN_DB
                and not self.peak_is_sweep_edge)

    @property
    def peak_is_sweep_edge(self) -> bool:
        """True iff the reported maximum IS the top of the search range.

        **The G44 condition on its own**, split out of `has_interior_peak`
        because the two halves of that test reject different things and only
        one of them is a broken measurement:

        * `g_pk - g_top <= margin` — the response is still RISING at 20 GHz, so
          `meas ac MAX` returned the range edge and `peaking_db` is FICTITIOUS
          and LARGE. Measured example: rl=800 at 3.25 mA reports 1.08 dB of
          "peaking" at 19.95 GHz with `g_pk - g_top` = -0.001 dB. That is free
          reward for a circuit with no peak, and it must be rejected.
        * `peaking_db <= margin` — the response has a genuine interior maximum
          that is merely SMALL. Measured example: rs = 50 ohm gives 0.165 dB of
          peaking at 1.318 GHz with `g_pk - g_top` = 9.23 dB. Nothing about
          that measurement is wrong; the circuit simply does not equalise.

        `has_interior_peak` keeps both halves, because `s3_yield.py`,
        `s9_yield.py` and `robust_geometry.py` publish counts that use it and
        those must not move. A VALIDITY gate wants only the first half — see
        `rl/evaluator.validate`. Rejecting the second half as invalid would
        erase the reward gradient over the entire low-peaking region of the
        box, which is where a randomly initialised policy starts.
        """
        return (self.g_pk_db - self.g_top_db) <= PEAK_MARGIN_DB  # type: ignore[operator]

    # ---- derived: the INTERPOLATED peak (G74) ------------------------------

    @property
    def has_interp_peak(self) -> bool:
        """True iff a trustworthy sub-grid peak exists on this result."""
        return self.f_pk_interp_hz is not None

    @property
    def peaking_interp_db(self) -> float:
        """max|H| relative to |H(DC)|, read off the parabola rather than the
        lattice. The interpolated counterpart of `peaking_db`, and strictly
        >= it, because the vertex of a concave parabola is at or above every
        sample that defined it."""
        return self.g_pk_interp_db - self.g_dc_db   # type: ignore[operator]

    @property
    def d_f_peak_octaves(self) -> float:
        """`log2(f_interp / f_discrete)`. How far the lattice was off, signed.

        Bounded by half a grid step (0.0332 octaves for `dec 50`) BY
        CONSTRUCTION, so a value outside that is not a small correction, it is
        evidence that the Python argmax and `meas ac MAX` disagree about which
        sample is the maximum.
        """
        return math.log2(float(self.f_pk_interp_hz)      # type: ignore[arg-type]
                         / float(self.f_pk_hz))          # type: ignore[arg-type]

    @property
    def peak_interp_is_sweep_edge(self) -> bool:
        """**The G44 condition, on the interpolated path.**

        `peak_is_sweep_edge` asks whether the response had come back down by
        `MAX_SEARCH_TOP_HZ`, using `g_top`. This asks the question the
        interpolation itself can answer: was the discrete maximum ON the top
        edge of the search window, so that no bracketing triple exists? An
        interpolated peak that lands on or beyond the last grid point is the
        same fictitious peak, whatever arithmetic produced it.

        **The two guards can disagree, and that is the point of having both.**
        A sharply peaked response whose maximum sits on the LAST in-window
        sample can still have fallen more than `PEAK_MARGIN_DB` by 20 GHz --
        the discrete guard passes it, this one rejects it, and this one is
        right about the interpolated number because a vertex fitted to two
        points is not a vertex.

        Raises when the interpolation was never run: "no interpolated peak was
        asked for" is not an answer to "is the interpolated peak fictitious",
        and returning False for it would be a fabricated pass.
        """
        if self.peak_interp is None:
            raise ValueError(
                "peak_interp_is_sweep_edge asked of a result that was not run "
                "with run_point(ac_peak_interp=True); there is no interpolated "
                "peak to judge")
        return self.peak_interp.get("edge") == "top"

    @property
    def in_saturation(self) -> bool:
        return self.vds > self.vdsat            # type: ignore[operator]

    @property
    def gm_over_id(self) -> float:
        return self.gm / self.id_a              # type: ignore[operator]

    # ---- derived: the tail ----
    @property
    def has_real_tail(self) -> bool:
        return self.vdsat_tail is not None

    @property
    def tail_margin_v(self) -> Optional[float]:
        """`vds_tail - vdsat_tail`. Negative => the tail is in triode.

        THE COUPLED INEQUALITY. `vds_tail` IS the input pair's source node, so
        this one number is where VCM, W_in, L_in, i_bias and the tail geometry
        meet. `None` when the tail is ideal, because an ideal sink has no such
        constraint — which is exactly the optimism G47 records.
        """
        if self.vds_tail is None or self.vdsat_tail is None:
            return None
        return self.vds_tail - self.vdsat_tail

    @property
    def tail_in_saturation(self) -> Optional[bool]:
        m = self.tail_margin_v
        return None if m is None else m > 0.0

    @property
    def mirror_gain_error(self) -> Optional[float]:
        """Realised mirror ratio divided by the requested one, minus 1.

        0.0 would be a perfect mirror. Measured around -8 % at TT, and it is
        real physics: the reference device sits at `vds = vgs` ~ 1.0 V while the
        tail sits at `v(source)` ~ 0.34 V, so channel-length modulation gives
        the reference more current per micron than the tail.
        """
        if (self.i_tail_meas_a is None or self.point is None
                or self.point.tail is None):
            return None
        asked = self.point.i_tail_per_side_a
        return (self.i_tail_meas_a / asked - 1.0) if asked else None

    def noise_share_power(self) -> dict:
        """Each contributor's share of the total noise POWER, summing to ~1.

        Squares first: the per-instance numbers are RMS volts and add in
        quadrature, so a linear normalisation would over-report every small
        contributor and under-report the dominant one.
        """
        if not self.noise_by_device:
            return {}
        sq = {k: v * v for k, v in self.noise_by_device.items() if v is not None}
        tot = sum(sq.values())
        return {k: v / tot for k, v in sq.items()} if tot > 0 else {}

    def noise_quadrature_residual(self) -> Optional[float]:
        """Relative gap between the quadrature sum of parts and `vn_in_vrms`.

        The gate on the attribution: if the parts do not reconstruct the total,
        the breakdown is missing a contributor and any share read off it is
        wrong. Verified at 6e-8 on the reference point.
        """
        if not self.noise_by_device or not self.vn_in_vrms:
            return None
        s = math.sqrt(sum(v * v for v in self.noise_by_device.values()
                          if v is not None))
        return abs(s - self.vn_in_vrms) / self.vn_in_vrms

    @property
    def power_measured_w(self) -> Optional[float]:
        """VDD x the MEASURED supply current. The number S6 should be scored on.

        `SizingPoint.power_w` is what was asked for. With a real tail those are
        not the same: the mirror adds a reference branch and delivers ~8 % less
        than requested into each side, and both effects are real power.
        """
        if self.i_supply_a is None or self.point is None:
            return None
        return self.point.vdd * self.i_supply_a

    # ---- derived: the measured swing ----
    def swing(self, compression_db: float = 1.0) -> "SwingLimits":
        if self.vid is None or self.vod is None:
            raise ValueError(
                "no DC transfer curve on this point — run with swing=True"
            )
        return swing_limits(
            self.vid, self.vod, self.sat_ok, self.id_min,
            compression_db=compression_db,
            i_ref_a=self.point.i_tail_per_side_a if self.point else None,
        )


@dataclass(frozen=True)
class SwingLimits:
    """The three ways a differential pair runs out of output swing.

    All values are **differential peak-to-peak volts**, i.e. `2 * |vod|_max`,
    which is the unit `nebula/link/calibration.py` conventions C2/C3 work in.
    `None` means the limit was not reached inside the swept input range —
    which is information, not a failure, but must not be read as "no limit".
    """

    g_dc_v_per_v: float
    linear_pp_v: Optional[float]        # 1 dB gain compression — use this one
    saturation_pp_v: Optional[float]    # first device with vds < vdsat
    steering_pp_v: Optional[float]      # a branch current reaching ~0
    max_swept_pp_v: float               # largest |vod| actually simulated
    compression_db: float
    #: **The same compression event, referred to the INPUT** — the differential
    #: input peak-to-peak amplitude at which incremental gain has fallen
    #: `compression_db` below its value at `vid = 0`. `linear_pp_v` answers
    #: *"how much output can this stage deliver"*; this answers *"how much
    #: input can it be driven with"*, which is the question S8 turns on and the
    #: one nothing in this project measured until now.
    #:
    #: **It is not `linear_pp_v / g_dc_v_per_v`.** That division is only exact
    #: while the gain is still `g_dc`, and by construction it is not — the
    #: point is defined by the gain having dropped. Both numbers come off the
    #: SAME swept sample, so there is one compression event with two
    #: projections rather than two definitions that can drift (rule 9).
    #:
    #: Units match `LinkConfig.v_in_diff_pp_v` and
    #: `PCIE_GEN2_TX_DIFF_PP_MIN_V` exactly — differential peak-to-peak volts
    #: — so the comparison the spec table needs is a subtraction, not a
    #: conversion.
    linear_in_pp_v: Optional[float] = None
    #: Largest differential input actually swept, i.e. `2 * vid_max`. The
    #: companion to `max_swept_pp_v`: when `linear_in_pp_v` is `None` the stage
    #: did not compress anywhere inside this range, which is information (a
    #: LOWER bound on its linear range) and not a failure.
    max_swept_in_pp_v: float = 0.0


def textbook_swing_pp_v(i_tail_per_side_a: float, rl: float) -> float:
    """The `2*I*RL` current-steering ceiling, as a PEAK-TO-PEAK number.

    Full steering drives one branch to `2*I` and the other to 0, so the
    differential output reaches `+/- 2*I*RL` and the peak-to-peak span is
    `4*I*RL`. HANDOFF session 9c used `2*I*RL` as a peak-to-peak figure, which
    understates the ceiling by exactly 2x. This function exists so the
    conversion is written down once.
    """
    return 4.0 * i_tail_per_side_a * rl


def swing_limits(
    vid: np.ndarray,
    vod: np.ndarray,
    sat_ok: Optional[np.ndarray] = None,
    id_min: Optional[np.ndarray] = None,
    compression_db: float = 1.0,
    steering_frac: float = 0.05,
    i_ref_a: Optional[float] = None,
) -> SwingLimits:
    """Extract swing limits from a differential DC transfer curve.

    The stage inverts (`vod = (id2 - id1) * RL`), so incremental gain is taken
    as a magnitude throughout. Limits are found by scanning OUTWARD from
    vid = 0, so a curve that folds back at large drive cannot produce a limit
    smaller than the one the signal actually meets first.
    """
    vid = np.asarray(vid, dtype=float)
    vod = np.asarray(vod, dtype=float)
    if vid.shape != vod.shape or vid.size < 5:
        raise ValueError(f"bad transfer curve: vid{vid.shape} vod{vod.shape}")

    g = np.abs(np.gradient(vod, vid))
    g0 = float(np.interp(0.0, vid, g))
    if not math.isfinite(g0) or g0 <= 0.0:
        raise ValueError(f"incremental gain at vid=0 is {g0}, not usable")

    outward = np.argsort(np.abs(vid))

    def _first(mask: np.ndarray) -> Optional[int]:
        """Index of the first sample OUTWARD from vid=0 that trips `mask`."""
        for i in outward:
            if mask[i]:
                return int(i)

        return None

    # ONE compression event, TWO projections. `_out` is the number this
    # function has always returned; `_in` is the same sample read on the input
    # axis. Deriving both from the same index is what stops the input-referred
    # limit becoming a second definition that can drift from the output one
    # (rule 9, G32).
    def _out(i: Optional[int]) -> Optional[float]:
        return None if i is None else 2.0 * abs(float(vod[i]))

    def _in(i: Optional[int]) -> Optional[float]:
        return None if i is None else 2.0 * abs(float(vid[i]))

    thr = g0 * 10.0 ** (-compression_db / 20.0)
    linear = _first(g < thr)
    sat = _first(~np.asarray(sat_ok, dtype=bool)) if sat_ok is not None else None
    steer = None
    if id_min is not None and i_ref_a:
        steer = _first(np.asarray(id_min, dtype=float) < steering_frac * i_ref_a)

    return SwingLimits(
        g_dc_v_per_v=g0,
        linear_pp_v=_out(linear),
        saturation_pp_v=_out(sat),
        steering_pp_v=_out(steer),
        max_swept_pp_v=2.0 * float(np.max(np.abs(vod))),
        compression_db=compression_db,
        linear_in_pp_v=_in(linear),
        max_swept_in_pp_v=2.0 * float(np.max(np.abs(vid))),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Netlist.
#
# ONE definition of the circuit (CLAUDEwa.md §8 rule 9). `spice/ctle.cir` is
# the human-readable sandbox of the same topology; if you change one, diff the
# other. The differences here are deliberate and listed:
#   * drive is a single `vid` source through two VCVSs, so `.dc` can sweep the
#     differential input and `.noise` can refer to a differential source;
#   * the analyses and the `wrdata` dump are added.
# ─────────────────────────────────────────────────────────────────────────────

# The circuit is defined ONCE, in `_TOPOLOGY`, and the analyses are bolted on
# separately. CLAUDEwa.md §8 rule 9 and G32: two netlists describing "the same"
# point drifted by one model parameter and silently explained away a
# discrepancy for a week. The tunable sweep (`run_tunable_sweep`) needs a
# DIFFERENT control block over the SAME circuit, so the split is what stops a
# second copy of the topology existing. `test_tail.py` asserts
# `_TOPOLOGY + _CONTROL_SINGLE == ` the historical `_NETLIST` text, so the
# split cannot drift either.

_TOPOLOGY = """* nebula sky130 sizing point (auto-generated; do not edit by hand)
.lib "{lib}" {corner}
.temp {temp_c}

.param W={w} L={l} NF={nf}
.param RL={rl} RS={rs} CS={cs} IT={it} CL={cl}
.param VDD={vdd} VCM={vcm}

Vdd   vdd 0 {{VDD}}
Vcm   cm  0 {{VCM}}

* One swept/AC source, two VCVSs: v(inp,inn) == v(vid) exactly. This makes the
* .noise input reference DIFFERENTIAL (see the module docstring) and lets .dc
* sweep the differential input directly.
Vid   vid 0 dc 0 ac 1{tran_src}
Einp  inp cm vid 0 0.5
Einn  inn cm vid 0 -0.5

XM1   outp inp s1 0 {device} W={{W}} L={{L}} nf={{NF}}
XM2   outn inn s2 0 {device} W={{W}} L={{L}} nf={{NF}}

{passive_block}
{tail_source}
CLp   outp 0 {{CL}}
CLn   outn 0 {{CL}}

"""

_CONTROL_SINGLE = """.control
set noaskquit
set filetype=ascii

op
print @m.xm1.m{device}[gm] @m.xm1.m{device}[gmbs] @m.xm1.m{device}[gds]
print @m.xm1.m{device}[vth] @m.xm1.m{device}[vds] @m.xm1.m{device}[vdsat]
print @m.xm1.m{device}[vgs] @m.xm1.m{device}[id]
print v(outp) v(s1)
* Supply branch current. The MEASURED power, so a mirror's reference branch and
* its gain error are billed rather than assumed (rule 1). Negated in Python:
* ngspice reports current INTO the source's + terminal.
print i(Vdd)
{tail_probe}

ac dec 50 1meg 100g
let vd_db = db(v(outp) - v(outn))
{ac_dump}
meas ac g_dc  FIND vd_db AT=1meg
meas ac g_nyq FIND vd_db AT=2.5g
* MAX is bounded at 20 GHz and g_top read AT the same edge, so `has_interior_
* peak` can test whether the response actually came back down (G44). The AC
* sweep still runs to 100 GHz -- only the MAX SEARCH is bounded.
meas ac g_pk  MAX  vd_db FROM=10meg TO={f_top}
meas ac g_top FIND vd_db AT={f_top}

noise v(outp,outn) Vid dec 20 10meg 5g{noise_summary}
print inoise_total
{noise_probe}
{swing_block}
{hd3_block}
quit
.endc

.end
"""

#: The historical single-point netlist, reassembled. Every existing caller uses
#: this and its bytes are unchanged by the split above.
_NETLIST = _TOPOLOGY + _CONTROL_SINGLE

# ── the two passive networks ────────────────────────────────────────────────
#
# ONE definition each (CLAUDEwa.md §8 rule 9), exactly as for the two tails
# below. `_PASSIVES_IDEAL` is BYTE-IDENTICAL to what `_TOPOLOGY` carried inline
# before the split, so every published number through session 16 reproduces.
#
# The `{RL}` / `{RS}` / `{CS}` here are `.param` references that ngspice
# resolves, NOT Python format fields: these blocks are substituted INTO
# `_TOPOLOGY` as a finished string, and `str.format` does not re-expand what it
# substitutes.

#: LEGACY, and the default. Ideal R and C — what every result through session 16
#: was measured with.
_PASSIVES_IDEAL = """RLp   vdd outp {RL}
RLn   vdd outn {RL}

* Between the two SOURCES, not source-to-ground: each half-circuit sees Rs/2,
* which is where the factor of two in k = 1 + (gm+gmbs)*Rs/2 comes from.
Rdeg  s1 s2 {RS}
Cdeg  s1 s2 {CS}
"""

#: REAL SKY130 devices, from `passives.to_geometry()`. This is what makes the
#: framework's output a SCHEMATIC rather than a parameter vector (PASSIVES.md
#: §4.3) and it is what an RL run must use from the outset — deferring it means
#: training a policy against a circuit nobody can draw.
#:
#: THREE THINGS THAT ARE NOT OBVIOUS FROM THE TEXT:
#:
#: 1. **The resistors have a THIRD terminal**, the substrate. That is not
#:    decoration: it connects `sky130_fd_pr__model__parasitic__res_po`, which
#:    puts half the body-to-bulk capacitance on each end (PASSIVES.md §4.4). So
#:    `RL`'s bottom plate lands on the output node and adds to `cl` — a real
#:    effect the ideal-R netlist does not have, and the reason the 4d
#:    regression check has to exist.
#: 2. **`m=` is the multiplier, never `mult=`** (G56). `mult` appears only
#:    inside mismatch terms, all multiplied by `MC_MM_SWITCH` = 0, so it is
#:    silently ignored. `device/netlist_gates.py` refuses to emit anything else.
#: 3. **`w=` is written only to the GENERIC families** (`res_high_po`), where it
#:    is honoured. On the `_0p69`-style fixed-width families it is INERT (G57)
#:    and asking the wrong subckt for a width is a silent 4.03x error; the same
#:    gate refuses those.
#:
#: `CL` stays an ideal capacitor deliberately. It is not a device we draw — it
#: is the NEXT stage's input capacitance, a screened context variable with a
#: derived range (CL_RANGE.md). Drawing it would be inventing a load.
_PASSIVES_REAL = """* Load resistors: SKY130 poly, drawn geometry from passives.to_geometry().
* Third terminal is the substrate -- it carries the res_po bottom-plate
* parasitic, half of which lands on the output node (PASSIVES.md 4.4).
Xrlp  vdd outp 0 {rl_subckt} w={rl_w:g} l={rl_l:g}{rl_m}
Xrln  vdd outn 0 {rl_subckt} w={rl_w:g} l={rl_l:g}{rl_m}

* Degeneration, between the two SOURCES (the /2 in k = 1 + (gm+gmbs)*Rs/2).
Xrs   s1 s2 0 {rs_subckt} w={rs_w:g} l={rs_l:g}{rs_m}
* MIM: two terminals, no bulk node -- the model carries no bottom plate at all
* (PASSIVES.md 4.4), which is a modelling absence, not a physical one.
Xcs   s1 s2 {cs_subckt} w={cs_w:g} l={cs_l:g}{cs_m}
"""


# ── the two tails ───────────────────────────────────────────────────────────
#
# ONE definition each (CLAUDEwa.md §8 rule 9). `spice/ctle.cir` carries the same
# two blocks for a human to read; if you change one, diff the other.

#: LEGACY. Two ideal sinks — what every published number through session 12b was
#: measured with, kept so those results stay reproducible. An ideal sink hands
#: over exactly IT at every corner, which is precisely what makes those corner
#: spreads understatements (G47).
_TAIL_IDEAL = """
* Two separate ideal sinks. A single shared tail would short the degeneration.
It1   s1 0 {IT}
It2   s2 0 {IT}
"""

#: The real tail: an ideal reference current into a diode-connected device,
#: mirrored to one tail per side at ratio N. Only `Iref` is still ideal, and
#: `nebula/device/tail.py` says why that one is defensible and a fixed gate bias
#: would not be.
_TAIL_MIRROR = """
* Current-mirror tail. N = W_tail/W_ref = {n_mir}; the reference device is one
* unit of the same finger width, so the mirror ratio is set by geometry and not
* by a voltage that would drift against vth across corners.
.param WT={w_tail} LT={l_tail} NFT={nf_tail}
.param WREF={w_ref} NFREF={nf_ref} IREF={i_ref} CBYP={c_byp}

Iref  vdd nbias {{IREF}}
XMR   nbias nbias 0 0 {device} W={{WREF}} L={{LT}} nf={{NFREF}}
XMT1  s1    nbias 0 0 {device} W={{WT}} L={{LT}} nf={{NFT}}
XMT2  s2    nbias 0 0 {device} W={{WT}} L={{LT}} nf={{NFT}}
* Bias-node bypass. A real element -- every current mirror grounds its gate
* node at signal frequencies so supply and reference noise do not reach the
* tail gates -- and it also removes an ngspice singularity (G54). It changes
* nothing else: the .op is unaffected (nbias carries no DC current into it),
* and the measured noise is IDENTICAL at 1 pF and 10 pF to seven digits.
Cbyp  nbias 0 {{CBYP}}
"""

#: Tail primitives. Read with `parse_scalar` against the FULL literal name, not
#: with `find_device_scalar`, which returns the first `@*[prop]` in the output
#: and would silently hand back the INPUT PAIR's number for every tail query.
_TAIL_PROBE = """print @m.xmt1.m{device}[id] @m.xmt1.m{device}[vds]
print @m.xmt1.m{device}[vdsat] @m.xmt1.m{device}[vgs]
print @m.xmt1.m{device}[vth] @m.xmt1.m{device}[gm]
print @m.xmr.m{device}[id] v(nbias)
"""

#: Per-instance integrated input-referred noise, emitted when `.noise` is given
#: a points-per-summary argument.
#:
#: **THE CONTRIBUTIONS ADD IN QUADRATURE, NOT LINEARLY**, and they are in RMS
#: VOLTS like `inoise_total` itself. Verified on the reference point: the eight
#: contributors sum linearly to 1.0825e-3 (2.4x the total, meaningless) and in
#: quadrature to 4.424650e-04, which equals `inoise_total` to every printed
#: digit. `noise_share_power` therefore squares before normalising. Getting this
#: backwards is the same class of error as square-rooting `inoise_total`
#: (`tests/test_noise_units.py`), and it flatters whichever contributor is
#: largest.
#:
#: NOTE the naming is INCONSISTENT between element types and it is not a typo:
#: devices use dots (`inoise_total.m.xm1.<model>`), resistors use underscores
#: (`inoise_total_rlp`). A single `print` line containing one bad name loses
#: the WHOLE line to a warning and exits 0 (G26), so each is printed separately.
_NOISE_PROBE_PAIR = """print inoise_total.m.xm1.m{device}
print inoise_total.m.xm2.m{device}
print inoise_total_rlp
print inoise_total_rln
print inoise_total_rdeg
"""

_NOISE_PROBE_TAIL = """print inoise_total.m.xmt1.m{device}
print inoise_total.m.xmt2.m{device}
print inoise_total.m.xmr.m{device}
"""

#: The order the `print` lines above appear in, paired with the key each lands
#: under in `Sky130Point.noise_by_device`. One definition (rule 9).
_NOISE_KEYS_PAIR: tuple[tuple[str, str], ...] = (
    ("in_pair_p", "inoise_total.m.xm1.m{device}"),
    ("in_pair_n", "inoise_total.m.xm2.m{device}"),
    ("rl_p", "inoise_total_rlp"),
    ("rl_n", "inoise_total_rln"),
    ("rs_deg", "inoise_total_rdeg"),
)
_NOISE_KEYS_TAIL: tuple[tuple[str, str], ...] = (
    ("tail_p", "inoise_total.m.xmt1.m{device}"),
    ("tail_n", "inoise_total.m.xmt2.m{device}"),
    ("mirror_ref", "inoise_total.m.xmr.m{device}"),
)

#: Dump the AC magnitude sweep, emitted only when `run_point(ac_sweep=True)`.
#:
#: **WHY THIS DID NOT EXIST UNTIL G2 NEEDED IT.** The `.ac` analysis has always
#: run, but only four `meas` scalars were ever extracted from it — `g_dc`,
#: `g_nyq`, `g_pk`/`f_pk` and `g_top`. That is everything S3 needs, so nothing
#: asked for more. **A pole-zero fit cannot be made to four numbers**, and
#: `DeviceResult` has declared `ac_freq_hz` / `ac_mag_db` since the interface
#: freeze precisely because the bridge would one day need the curve.
#:
#: **OFF BY DEFAULT, and that is a correctness decision rather than a
#: performance one.** With the flag off the netlist is byte-identical to the
#: one every published number came from, so no existing result can move.
#: `test_ac_sweep_capture_changes_no_measured_value` runs the same design both
#: ways and compares every parsed field at rel=0, abs=0 — the G36 discipline,
#: applied to an addition rather than a removal.
#:
#: `db()` is applied by ngspice on the same `vd_db` vector the `meas` lines
#: read, so the dumped curve and the four scalars cannot disagree about what
#: "the response" means (rule 9).
_AC_DUMP_BLOCK = """wrdata ac.txt vd_db"""


# ── S4: HD3 by transient + FFT ──────────────────────────────────────────────
#
# **`.disto` IS DEAD FOR BSIM4 (G21): it returns exactly 0.0.** Not "small" —
# zero, on a circuit with real distortion, with no warning. So S4 has to come
# from a time-domain run, and `spice/g0_hd3_tran_fft.cir` established the
# method during G0. This is that netlist's recipe, on the real PDK.
#
# THE THREE THINGS THAT MAKE THE NUMBER TRUSTWORTHY, all from the G0 prototype:
#
#  1. **The window is an exact integer number of cycles.** 20 cycles of a
#     100 MHz tone is 200 ns, captured from 50 ns to 250 ns. A non-integer
#     window leaks the fundamental across the whole spectrum and buries the
#     third harmonic under its own skirt — and the answer still looks like a
#     number.
#  2. **Five cycles of settling are DISCARDED** (the 50 ns start). The tone
#     starts at t=0 into a circuit at its DC operating point; the first cycles
#     carry the step response, not the steady state.
#  3. **The FFT is done in PYTHON, not in `.control`.** Rule 10, and the same
#     reason the §6 cross-check moved out: a `let`/`fft` sequence that errors
#     prints a warning and exits 0 (G26). Here the raw waveform is written out
#     and every derived number is computed from it where it can raise.
#
# 100 MHz and the drive level are S4's own: "HD3 < -30 dB @ 100 MHz
# differential input". The amplitude is a parameter because "differential
# input" does not state one, and HD3 depends on it strongly (square-law gives
# HD3 ~ Vin^2), so it is REPORTED beside the number rather than buried.
_HD3_BLOCK = """
* S4: HD3 from transient + FFT. `.disto` returns exactly 0.0 on BSIM4 (G21).
* Exactly {n_cycles:d} cycles captured after {n_settle:d} cycles of settling,
* so the FFT window has no leakage. The FFT itself is done in Python (rule 10).
tran {t_step:.6g} {t_stop:.6g} {t_start:.6g}
linearize
let vd_t = v(outp) - v(outn)
wrdata hd3.txt vd_t
"""
# `linearize` TAKES VECTOR NAMES, NOT A TIMESTEP, and getting that wrong is
# not a syntax error you find out about cleanly. Measured while building this:
# `linearize 1e-10` prints
#
#     Error: no such vector 1e-10
#     Warning from checkvalid: vector outp is not available or has zero length.
#     Error: RHS "v(outp) - v(outn)" invalid
#
# -- i.e. it DESTROYS THE PLOT, so every later line in the block fails too --
# and ngspice still exits normally. G26 again, in a new place. The `tran`
# already uses a fixed step, so bare `linearize` only resamples onto the
# uniform grid the FFT needs.

#: S4's stated conditions. "HD3 < -30 dB @ 100 MHz differential input"
#: (CLAUDEwa.md §3) names the frequency and not the amplitude, so the
#: amplitude is a parameter and is REPORTED with every HD3 number — HD3 goes
#: as roughly Vin^2 for a square-law pair, so an unstated drive level makes the
#: number meaningless.
HD3_TONE_HZ: float = 100e6
#: Differential PEAK amplitude at the CTLE input, volts. 100 mV pk = 200 mVpp,
#: the G0 prototype's level (`VIN_PK = 0.05` single-ended, ±, so 0.1 V
#: differential peak).
HD3_VIN_DIFF_PK_V: float = 0.1
#: Cycles discarded before the window opens, and cycles captured. Both from
#: the G0 prototype. The capture MUST be an integer number of cycles.
HD3_SETTLE_CYCLES: int = 5
HD3_CAPTURE_CYCLES: int = 20
#: Timesteps per cycle. 100 points/cycle at 100 MHz is a 100 ps step, and the
#: Nyquist limit of that grid is the 50th harmonic — far above the 3rd.
HD3_STEPS_PER_CYCLE: int = 100


_SWING_BLOCK = """
save all @m.xm1.m{device}[vds] @m.xm1.m{device}[vdsat] @m.xm1.m{device}[id]
+ @m.xm2.m{device}[vds] @m.xm2.m{device}[vdsat] @m.xm2.m{device}[id]
dc vid -{vid_max} {vid_max} {vid_step}
wrdata swing.txt v(outp) v(outn)
+ @m.xm1.m{device}[vds] @m.xm1.m{device}[vdsat] @m.xm1.m{device}[id]
+ @m.xm2.m{device}[vds] @m.xm2.m{device}[vdsat] @m.xm2.m{device}[id]
"""



#: Fields of `_NETLIST` that are OPTIONAL, with the value that means "absent".
#:
#: They exist because `ac_sweep` and `hd3` add blocks to the deck, and a
#: `str.format` template with an unsupplied field raises `KeyError`. Adding
#: them broke five `test_tail.py` tests and two `test_tunable.py` tests that
#: format the template directly — a mechanical break, but the lesson is not:
#: **a shared template with growing placeholders needs ONE place that knows the
#: defaults**, or every caller has to be found again next time. That place is
#: `assemble_netlist`.
_OPTIONAL_NETLIST_FIELDS: dict = {"ac_dump": "", "tran_src": "", "hd3_block": ""}


def assemble_netlist(template: str = None, **fields: object) -> str:
    """Format the single-point netlist, defaulting the optional blocks.

    Every caller that builds this deck goes through here, so adding a block
    later means editing this dict and nothing else (rule 9).
    """
    merged = dict(_OPTIONAL_NETLIST_FIELDS)
    merged.update(fields)
    return (template if template is not None else _NETLIST).format(**merged)


def lib_for_device(device: str, real_passives: bool = False,
                   section: Optional[str] = None) -> Path:
    """The library that carries `device`'s model cards.

    The nfet-only trim (G36) includes **only** `nfet_01v8`. Anything else has
    to come from the full library until its model files are added to a trim
    — and asking for it silently would produce "could not find a valid
    modelname", which G31 shows is read as a units error nine times out of ten.

    `real_passives=True` selects the EXTENDED trim, which adds the poly
    resistor and MIM families and the passive corner axis (G58). It is
    verified bit-identical to the full library
    (`test_trimmed_lib_passives.py`, rel=0 abs=0).

    `section` names the `.lib` section the netlist will ask for. **Pass it.**
    ngspice expands EVERY section in a `.lib` file, not only the requested one
    (G78), so the 25-section extended library costs 1.386 s to parse where one
    section costs 0.093 s. `device/pdk_trim.py` generates a one-section file
    per section and this returns it when one exists, falling back to the
    monolithic library otherwise — so an unsplit or not-yet-regenerated tree
    still runs, just slowly.

    TWO NUMBERS THAT USED TO BE HERE AND WERE WRONG, kept because both were
    quoted in `PASSIVES.md` and in G70 and both were believed for four
    sessions: the extended library's cost was attributed to the R/C corner
    files pulling in `parameters/typical.spice` (3023 lines) *and*
    `invariant.spice` (7340). **`invariant.spice` is not in the include tree at
    all** — only `parameters/montecarlo.spice` includes it, which no section
    this project uses reaches. And `typical.spice` was real but minor: removing
    8823 of its 8909 parameters bought 1.55x, against the 15x the section split
    bought. See `nebula/LIB_COST.md`.
    """
    if device == NFET_01V8:
        mono = CTLE_LIB if real_passives else TRIMMED_LIB
        if section:
            from nebula.device.pdk_trim import section_library_path
            per_section = section_library_path(section, mono.name.split(".")[0])
            if per_section.exists():
                return per_section
        return mono
    full = Path(r"C:/Users/DELL/sky130A/libs.tech/ngspice/sky130.lib.spice")
    if not full.exists():
        raise FileNotFoundError(
            f"device {device!r} is not in the trimmed library and the full "
            f"SKY130 library was not found at {full} (HANDOFF G33)."
        )
    return full


def _m_suffix(m: int) -> str:
    """` m=<n>` for n > 1, empty at 1.

    `m=`, NEVER `mult=` (G56). `netlist_gates` enforces it on the assembled
    text; this function is why there is nothing for it to catch.
    """
    if int(m) < 1:
        raise ValueError(f"multiplier m must be >= 1, got {m}")
    return f" m={int(m)}" if int(m) > 1 else ""


def passive_block(passives: Optional[PassiveGeometry]) -> str:
    """The R/C section of the netlist: ideal elements, or drawn devices.

    ONE definition (rule 9) — `run_point` and `run_tunable_sweep` both call it,
    so an ideal-vs-real difference can never appear in one path and not the
    other.
    """
    if passives is None:
        return _PASSIVES_IDEAL
    return _PASSIVES_REAL.format(
        rl_subckt=passives.rl.subckt, rl_w=passives.rl.w_um,
        rl_l=passives.rl.l_um, rl_m=_m_suffix(passives.rl.m),
        rs_subckt=passives.rs.subckt, rs_w=passives.rs.w_um,
        rs_l=passives.rs.l_um, rs_m=_m_suffix(passives.rs.m),
        cs_subckt=passives.cs.subckt, cs_w=passives.cs.w_um,
        cs_l=passives.cs.l_um, cs_m=_m_suffix(passives.cs.m),
    )


def _load_or_none(path: Path) -> Optional[np.ndarray]:
    """Read a `wrdata` dump, or None if it is absent, empty or unparseable.

    Deliberately returns None rather than raising: WHY it is missing is
    almost always in the ngspice output, and the caller checks that first.
    """
    try:
        if not (path.exists() and path.stat().st_size > 0):
            return None
        return np.loadtxt(path)
    except (OSError, ValueError):
        return None


def _hd3_source(vin_pk_v: float = None) -> str:
    """The transient tone, as a `sin()` spec appended to the AC source.

    Appending rather than replacing is what keeps `.op`, `.ac` and `.noise`
    untouched: ngspice reads `dc` for the operating point and `ac` for the
    small-signal analyses, and ignores `sin()` in both. So the same source
    serves all four analyses and there is ONE input definition in the netlist
    (rule 9) rather than a second one that could drift.
    """
    v = HD3_VIN_DIFF_PK_V if vin_pk_v is None else float(vin_pk_v)
    return f" sin(0 {v:.6g} {HD3_TONE_HZ:.6g})"


def _hd3_block() -> str:
    period = 1.0 / HD3_TONE_HZ
    return _HD3_BLOCK.format(
        n_cycles=HD3_CAPTURE_CYCLES, n_settle=HD3_SETTLE_CYCLES,
        t_step=period / HD3_STEPS_PER_CYCLE,
        t_start=HD3_SETTLE_CYCLES * period,
        t_stop=(HD3_SETTLE_CYCLES + HD3_CAPTURE_CYCLES) * period,
    )


def hd3_from_waveform(t: np.ndarray, vd: np.ndarray,
                      f_tone_hz: float = HD3_TONE_HZ) -> tuple[float, dict]:
    """Third-harmonic distortion in dBc, from a captured differential waveform.

    In PYTHON, from the raw samples, because rule 10: a `fft`/`let` sequence
    inside `.control` that errors prints a warning and exits 0 (G26), and an
    HD3 of "0.0 dBc" from a block that never ran looks exactly like a broken
    circuit.

    Returns `(hd3_dbc, detail)`. `hd3_dbc` is `20*log10(|V3| / |V1|)`, so a
    well-behaved stage gives a large NEGATIVE number and S4 asks for
    < -30 dBc.

    **The window must be an integer number of cycles and this checks it.**
    Leakage from a partial cycle spreads the fundamental across every bin and
    the third harmonic disappears under its skirt — while still producing a
    number. `detail["cycles_in_window"]` is reported so the check is visible.
    """
    t = np.asarray(t, dtype=float).ravel()
    vd = np.asarray(vd, dtype=float).ravel()
    if t.size < 64 or t.size != vd.size:
        raise ValueError(f"need at least 64 matched samples, got {t.size}/{vd.size}")
    if not np.all(np.isfinite(vd)):
        raise ValueError("waveform contains non-finite samples")

    span = float(t[-1] - t[0])
    dt = span / (t.size - 1)
    cycles = span * f_tone_hz
    if abs(cycles - round(cycles)) > 1e-6:
        raise ValueError(
            f"capture window is {cycles:.6f} cycles, not an integer. Spectral "
            f"leakage would bury the third harmonic under the fundamental's "
            f"skirt and still return a number.")

    # **DROP THE LAST SAMPLE.** `tran ... {t_stop} {t_start}` yields an
    # INCLUSIVE grid: 20 cycles at 100 points/cycle arrives as 2001 samples,
    # t[0] and t[-1] being the SAME PHASE one period apart. Feeding all 2001 to
    # an FFT describes a 20.01-cycle window, which is not periodic and leaks.
    # Dropping the duplicate endpoint leaves 2000 samples spanning exactly 20
    # cycles, so bin `k1 = 20` is the fundamental exactly.
    #
    # This is the failure the integer check above exists to catch, and it
    # caught it on the first real run -- the raise said "20.010000 cycles".
    vd = vd[:-1]
    n = vd.size
    spec = np.fft.rfft(vd - vd.mean())
    freqs = np.fft.rfftfreq(n, d=dt)
    k1 = int(round(f_tone_hz * n * dt))
    k3 = 3 * k1
    if k3 >= spec.size:
        raise ValueError(
            f"the third harmonic ({3 * f_tone_hz / 1e9:.3g} GHz) is above the "
            f"capture grid's Nyquist ({freqs[-1] / 1e9:.3g} GHz)")

    v1 = float(np.abs(spec[k1]))
    v3 = float(np.abs(spec[k3]))
    if v1 <= 0.0:
        raise ValueError("no energy at the fundamental — the tone never reached "
                         "the output")
    hd3 = 20.0 * math.log10(max(v3 / v1, 1e-15))
    return hd3, {
        "cycles_in_window": cycles,
        "n_samples": n,
        "bin_fundamental": k1,
        "bin_third": k3,
        "v1_v": v1,
        "v3_v": v3,
        "f_tone_hz": f_tone_hz,
        "vin_diff_pk_v": HD3_VIN_DIFF_PK_V,
    }


def run_point(
    point: SizingPoint,
    corner: str = "tt",
    swing: bool = True,
    vid_max: float = 0.8,
    vid_step: float = 0.004,
    timeout_s: float = 120.0,
    temp_c: float = 27.0,
    noise_detail: bool = False,
    keep_text: bool = False,
    keep_netlist: bool = False,
    ac_sweep: bool = False,
    ac_peak_interp: bool = False,
    hd3: bool = False,
    hd3_vin_pk_v: Optional[float] = None,
) -> Sky130Point:
    """Simulate one sizing point. Never raises — failures come back ok=False.

    CLAUDEwa.md §8 rule 2: a failed SPICE run is a bad reward, not a crash.

    `corner` selects the PROCESS corner (the `.lib` section) and `temp_c` the
    temperature. The third S9 axis, VDD, is carried by `point.vdd` — scale it
    at the call site, because it is a property of the sizing point's supply,
    not of the run.

    `ac_sweep=True` additionally dumps the AC magnitude curve into
    `ac_freq_hz` / `ac_mag_db`. **Default OFF so the netlist stays byte-
    identical to the one every published number came from**; the link bridge
    asks for it because a pole-zero fit cannot be made to four `meas` scalars.

    `hd3=True` adds S4's transient tone and dumps the waveform for a Python
    FFT. Also default OFF, and for a second reason besides byte-identity: it
    is the expensive tier. G0 measured a 175x cost spread across the analyses
    and this is the top of it.

    `ac_peak_interp=True` additionally locates the response maximum by
    parabolic interpolation on the dumped curve and fills `f_pk_interp_hz` /
    `g_pk_interp_db` (G74's ceiling, see `interpolate_peak_log_f`). **It
    IMPLIES `ac_sweep=True`** -- there is no curve to interpolate otherwise --
    and it costs **no extra simulation**: the same invocation, the same deck as
    `ac_sweep=True`, plus about ten floating-point operations in Python.
    Default OFF, and `f_pk_hz` / `g_pk_db` are untouched either way, so no
    published number can move.

    A refused interpolation is NOT a failed run. The discrete measurements are
    still good; only the sub-grid refinement is unavailable, the two new fields
    stay `None`, and `peak_interp["reason"]` says why.
    """
    # There is no curve to interpolate without the dump, and silently returning
    # `f_pk_interp_hz=None` for a caller who asked for it would be a missing
    # number that looks like a refusal (rule 1). Raise the flag instead.
    if ac_peak_interp:
        ac_sweep = True
    if corner not in VALID_CORNERS:
        return Sky130Point(ok=False, fail_reason=f"unknown corner {corner!r}",
                           point=point, corner=corner)
    try:
        lib = lib_for_device(point.device,
                             real_passives=point.passives is not None,
                             section=corner)
    except FileNotFoundError as exc:
        return Sky130Point(ok=False, fail_reason=str(exc), point=point, corner=corner)

    swing_block = ""
    if swing:
        swing_block = _SWING_BLOCK.format(device=point.device, vid_max=vid_max,
                                          vid_step=vid_step)

    # The tail: ideal sinks, or the mirror. A geometry outside the SKY130 bins
    # raises here rather than reaching ngspice, which would report it as
    # "could not find a valid modelname" — G31's misleading message.
    tail_probe = ""
    if point.tail is None:
        tail_source = _TAIL_IDEAL.format(IT="{IT}")
    else:
        t = point.tail
        tail_source = _TAIL_MIRROR.format(
            device=t.device, n_mir=f"{t.mirror_ratio:g}",
            w_tail=f"{t.w_tail:.6g}", l_tail=f"{t.l_tail:.6g}",
            nf_tail=int(t.nf_tail), w_ref=f"{t.w_ref:.6g}",
            nf_ref=int(t.nf_ref),
            i_ref=f"{t.i_ref_a(point.i_tail_per_side_a):.9g}",
            c_byp=f"{t.c_bypass_f:.9g}",
        )
        tail_probe = _TAIL_PROBE.format(device=t.device)

    # Per-device noise attribution. `noise_keys` is built from the SAME tables
    # the print lines come from, so a probe can never be parsed under the wrong
    # label (rule 9).
    noise_summary, noise_probe = "", ""
    noise_keys: list[tuple[str, str]] = []
    if noise_detail:
        noise_summary = " 1"          # points per summary => per-instance plots
        noise_probe = _NOISE_PROBE_PAIR.format(device=point.device)
        noise_keys = [(k, v.format(device=point.device))
                      for k, v in _NOISE_KEYS_PAIR]
        if point.tail is not None:
            noise_probe += _NOISE_PROBE_TAIL.format(device=point.tail.device)
            noise_keys += [(k, v.format(device=point.tail.device))
                           for k, v in _NOISE_KEYS_TAIL]

    text = assemble_netlist(
        lib=lib.as_posix(), corner=corner, device=point.device,
        w=point.w, l=point.l, nf=int(point.nf),
        rl=point.rl, rs=point.rs, cs=point.cs, cl=point.cl,
        it=point.i_tail_per_side_a, vdd=point.vdd, vcm=point.vcm,
        swing_block=swing_block, temp_c=temp_c,
        tail_source=tail_source, tail_probe=tail_probe,
        passive_block=passive_block(point.passives),
        noise_summary=noise_summary, noise_probe=noise_probe,
        f_top=f"{MAX_SEARCH_TOP_HZ / 1e9:g}g",
        ac_dump=(_AC_DUMP_BLOCK if ac_sweep else ""),
        tran_src=_hd3_source(hd3_vin_pk_v) if hd3 else "",
        hd3_block=_hd3_block() if hd3 else "",
    )

    # THE TWO SILENT WRITES, GATED ON THE ASSEMBLED TEXT (G56, G57). This
    # RAISES rather than returning ok=False on purpose: an inert write is a bug
    # in this file, not a property of the sizing point, and returning a bad
    # reward would let a training run absorb it as "that region scores poorly".
    assert_no_inert_writes(text)

    import time
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # .spiceinit is read from the CURRENT DIRECTORY at parse time (G29),
        # so it travels with the netlist rather than the netlist travelling to
        # it — that keeps runs parallel-safe (wrdata also writes to cwd).
        shutil.copy(SPICE_DIR / ".spiceinit", tmp / ".spiceinit")
        cir = tmp / "pt.cir"
        cir.write_text(text, encoding="ascii")
        try:
            proc = subprocess.run(
                [str(ngspice_path()), "-b", cir.name],
                cwd=str(tmp), capture_output=True, text=True, timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return Sky130Point(ok=False, fail_reason=f"ngspice timeout >{timeout_s}s",
                               point=point, corner=corner)
        except OSError as exc:
            return Sky130Point(ok=False, fail_reason=f"ngspice launch failed: {exc}",
                               point=point, corner=corner)

        out = proc.stdout + "\n" + proc.stderr
        swing_file = tmp / "swing.txt"
        raw = None
        if swing and swing_file.exists() and swing_file.stat().st_size > 0:
            try:
                raw = np.loadtxt(swing_file)
            except ValueError as exc:
                return Sky130Point(ok=False, fail_reason=f"unreadable swing.txt: {exc}",
                                   point=point, corner=corner)
        # THE DUMPED FILES ARE READ HERE BUT JUDGED LATER, and the order is
        # G68's: cause before symptom. "ngspice wrote no ac.txt" is a SYMPTOM;
        # the cause is whatever it printed as a warning first, and the
        # silent-failure scan below names it. An earlier version of this code
        # returned "wrote no hd3.txt" while the real message sitting in the
        # output was `Error: no such vector 1e-10` -- the useful half.
        ac_raw = _load_or_none(tmp / "ac.txt") if ac_sweep else None
        hd3_raw = _load_or_none(tmp / "hd3.txt") if hd3 else None

    runtime = time.perf_counter() - t0

    # §8 rule 10: the exit code is not a success signal. Grep first.
    offenders = scan_for_silent_failures(out)
    if offenders:
        return Sky130Point(ok=False, corner=corner, point=point, runtime_s=runtime,
                           fail_reason=f"ngspice silent failure: {offenders[0][:160]}")

    # Only NOW, with the output proven clean, is a missing dump a mystery worth
    # reporting in its own right (G68: cause before symptom).
    if ac_sweep and ac_raw is None:
        return Sky130Point(ok=False, corner=corner, point=point, runtime_s=runtime,
                           fail_reason="ac_sweep=True but ngspice wrote no "
                                       "readable ac.txt, and printed nothing "
                                       "to explain it")
    if hd3 and hd3_raw is None:
        return Sky130Point(ok=False, corner=corner, point=point, runtime_s=runtime,
                           fail_reason="hd3=True but ngspice wrote no readable "
                                       "hd3.txt, and printed nothing to "
                                       "explain it")

    pt = Sky130Point(ok=True, corner=corner, point=point, runtime_s=runtime,
                     raw_text=(out if keep_text else None),
                     netlist=(text if keep_netlist else None))
    pt.gm = find_device_scalar(out, "gm")
    pt.gmbs = find_device_scalar(out, "gmbs")
    pt.gds = find_device_scalar(out, "gds")
    pt.vth = find_device_scalar(out, "vth")
    pt.vds = find_device_scalar(out, "vds")
    pt.vdsat = find_device_scalar(out, "vdsat")
    pt.vgs = find_device_scalar(out, "vgs")
    pt.id_a = find_device_scalar(out, "id")
    pt.v_out_dc = parse_scalar(out, "v(outp)")
    pt.v_src_dc = parse_scalar(out, "v(s1)")
    # ngspice reports the current INTO the + terminal of a voltage source, so a
    # supply DELIVERING current reports it negative. Flip once, here.
    # ngspice lower-cases vector names on output: `print i(Vdd)` emits
    # `i(vdd) = ...`. Matching the netlist's capitalisation finds nothing.
    i_vdd = parse_scalar(out, "i(vdd)")
    pt.i_supply_a = None if i_vdd is None else -i_vdd

    if point.tail is not None:
        d = point.tail.device
        pt.i_tail_meas_a = parse_scalar(out, f"@m.xmt1.m{d}[id]")
        pt.vds_tail = parse_scalar(out, f"@m.xmt1.m{d}[vds]")
        pt.vdsat_tail = parse_scalar(out, f"@m.xmt1.m{d}[vdsat]")
        pt.vgs_tail = parse_scalar(out, f"@m.xmt1.m{d}[vgs]")
        pt.vth_tail = parse_scalar(out, f"@m.xmt1.m{d}[vth]")
        pt.gm_tail = parse_scalar(out, f"@m.xmt1.m{d}[gm]")
        pt.i_ref_meas_a = parse_scalar(out, f"@m.xmr.m{d}[id]")
        pt.v_bias_dc = parse_scalar(out, "v(nbias)")

    pt.g_dc_db, _ = parse_meas(out, "g_dc")
    pt.g_nyq_db, _ = parse_meas(out, "g_nyq")
    pt.g_pk_db, pt.f_pk_hz = parse_meas(out, "g_pk")
    pt.g_top_db, _ = parse_meas(out, "g_top")
    pt.vn_in_vrms = parse_scalar(out, "inoise_total")
    if noise_keys:
        pt.noise_by_device = {key: parse_scalar(out, vec)
                              for key, vec in noise_keys}
        # A probe that came back empty means the attribution is INCOMPLETE, and
        # an incomplete attribution silently re-weights every share computed
        # from it. Fail the run instead (rule 1: a missing number is a failure,
        # never a zero).
        blank = [k for k, v in pt.noise_by_device.items() if v is None]
        if blank:
            return Sky130Point(ok=False, corner=corner, point=point,
                               runtime_s=runtime,
                               fail_reason=f"noise attribution missing {blank}")

    required = ["gm", "gmbs", "vds", "vdsat", "id_a", "i_supply_a",
                "g_dc_db", "g_nyq_db", "g_pk_db", "f_pk_hz", "g_top_db",
                "vn_in_vrms"]
    # A tail that was asked for but did not parse is a FAILED run, not a run
    # with a missing extra. Without this the mirror could silently fall back to
    # "no tail data" and every tail verdict would read as unmeasured rather
    # than as broken (rule 10).
    if point.tail is not None:
        required += ["i_tail_meas_a", "vds_tail", "vdsat_tail", "gm_tail",
                     "i_ref_meas_a"]
    missing = [n for n in required if getattr(pt, n) is None]
    if missing:
        return Sky130Point(ok=False, corner=corner, point=point, runtime_s=runtime,
                           fail_reason=f"could not parse {missing}")

    if raw is not None:
        # wrdata emits an (x, y) PAIR per saved vector, in listed order:
        # outp, outn, vds1, vdsat1, id1, vds2, vdsat2, id2.
        if raw.ndim != 2 or raw.shape[1] != 16:
            return Sky130Point(ok=False, corner=corner, point=point, runtime_s=runtime,
                               fail_reason=f"swing.txt has shape {raw.shape}, expected (N, 16)")
        pt.vid = raw[:, 0]
        outp, outn = raw[:, 1], raw[:, 3]
        vds1, vdsat1, id1 = raw[:, 5], raw[:, 7], raw[:, 9]
        vds2, vdsat2, id2 = raw[:, 11], raw[:, 13], raw[:, 15]
        pt.vod = outp - outn
        pt.sat_ok = (vds1 > vdsat1) & (vds2 > vdsat2)
        pt.id_min = np.minimum(id1, id2)

    if ac_raw is not None:
        # `wrdata vd_db` on an AC analysis emits THREE columns, not two:
        # frequency, then the real and imaginary parts of the vector. `vd_db`
        # is already real (db() of a magnitude), so the imaginary column is
        # identically zero -- but it IS there, and reading column 1 as "the
        # value" only works because of that. Asserted rather than assumed,
        # because a silently complex column would be read as a magnitude.
        if ac_raw.ndim != 2 or ac_raw.shape[1] not in (2, 3):
            return Sky130Point(ok=False, corner=corner, point=point,
                               runtime_s=runtime,
                               fail_reason=f"ac.txt has shape {ac_raw.shape}, "
                                           f"expected (N, 2) or (N, 3)")
        if ac_raw.shape[1] == 3 and not np.allclose(ac_raw[:, 2], 0.0,
                                                    rtol=0, atol=0):
            return Sky130Point(ok=False, corner=corner, point=point,
                               runtime_s=runtime,
                               fail_reason="ac.txt imaginary column is not "
                                           "identically zero -- vd_db is not "
                                           "the real magnitude it is read as")
        pt.ac_freq_hz = ac_raw[:, 0]
        pt.ac_mag_db = ac_raw[:, 1]

        if ac_peak_interp:
            pi = interpolate_peak_log_f(pt.ac_freq_hz, pt.ac_mag_db)
            # THE CROSS-CHECK, and it is the one that matters: this Python
            # argmax and `meas ac g_pk MAX` are two independent readings of the
            # same `vd_db` vector, so they must name the SAME sample. If they
            # do not, the interpolation would be refining the wrong cell and
            # `d_f_peak_octaves` would come back larger than half a grid step
            # while still looking like a small correction. Caught here and
            # named, rather than surfacing as a distribution with a tail.
            if pi.ok and pt.f_pk_hz is not None and pi.f_grid_hz:
                off = abs(math.log2(float(pi.f_grid_hz) / float(pt.f_pk_hz)))
                if off > 0.5 * float(pi.step_octaves or 0.0):
                    pi = PeakInterp(
                        ok=False, f_grid_hz=pi.f_grid_hz,
                        g_grid_db=pi.g_grid_db, index=pi.index,
                        n_in_window=pi.n_in_window,
                        step_octaves=pi.step_octaves,
                        curvature_db=pi.curvature_db,
                        reason=(f"the Python argmax ({pi.f_grid_hz:.6g} Hz) and "
                                f"`meas ac MAX` ({float(pt.f_pk_hz):.6g} Hz) "
                                f"name different samples, {off:.6g} octaves "
                                f"apart; the bracketing triple is not the one "
                                f"the reported peak came from"))
            pt.peak_interp = pi.as_dict()
            if pi.ok:
                pt.f_pk_interp_hz = pi.f_hz
                pt.g_pk_interp_db = pi.g_db

    if hd3_raw is not None:
        if hd3_raw.ndim != 2 or hd3_raw.shape[1] < 2:
            return Sky130Point(ok=False, corner=corner, point=point,
                               runtime_s=runtime,
                               fail_reason=f"hd3.txt has shape {hd3_raw.shape}, "
                                           f"expected (N, 2)")
        try:
            pt.hd3_dbc, pt.hd3_detail = hd3_from_waveform(
                hd3_raw[:, 0], hd3_raw[:, 1])
        except ValueError as exc:
            # A distortion number computed from a bad window is worse than no
            # number: it is finite, plausible and wrong. Fail instead.
            return Sky130Point(ok=False, corner=corner, point=point,
                               runtime_s=runtime,
                               fail_reason=f"HD3 extraction failed: {exc}")
    return pt


# ─────────────────────────────────────────────────────────────────────────────
# The tunable sweep: many (rs, cs) settings, ONE ngspice process.
#
# WHY THIS IS ALLOWED, AND WHY IT NEEDED PROVING. G35 measured `alter` to be
# SILENTLY WRONG for subckt-wrapped device geometry — it writes the `w`
# instance parameter and leaves every geometry-derived parasitic at its old
# value, returning plausible numbers up to 24% off — and recorded that it is
# fine for the ideal R/C/I elements. "Recorded" is not "verified", and this
# path leans on it 67 times per process, so it was verified the way G35's
# failure was found: fresh-parse ground truth, exact comparison.
#
# `nebula/tests/test_tail.py::test_alter_on_rs_cs_is_bit_identical_to_fresh_parse`
# holds it to **rel=0, abs=0** on g_dc, g_nyq, g_pk, g_top, inoise_total,
# v(s1), gm and vdsat_tail, across 3 corners x 4 target settings x 2 starting
# settings. If that test goes red, this whole path is invalid.
#
# THE COST, MEASURED. One process doing N settings, serial:
#
#       settings      1       6      22      66
#       s/process   0.30    0.35    0.52    0.90
#       ms/setting   305      59      24    13.6
#
# So 66 settings cost 13.6 ms each against ~150 ms for one process per setting
# (G48) — an 11x speedup, and it is what makes a tunable sweep over the whole
# population affordable at all. This does NOT contradict G34/G35's conclusion
# that process reuse is not the answer for GEOMETRY: geometry is not what is
# being altered here.
# ─────────────────────────────────────────────────────────────────────────────

_CONTROL_SWEEP_HEAD = """.control
set noaskquit
set filetype=ascii
"""

#: One (rs, cs) setting. Repeated verbatim per setting, so the Nth block of
#: output is the Nth setting's — the parser relies on that ordering and a test
#: pins it.
#:
#: The `.op` prints come BEFORE `.ac`/`.noise` deliberately: after an analysis
#: the current plot changes and every `@m...` reference fails as a WARNING with
#: exit 0 (G26). That trap was re-hit while building this block.
_SWEEP_STEP = """alter Rdeg = {rs}
alter Cdeg = {cs}
op
print v(s1) i(Vdd)
print @m.xm1.m{device}[gm] @m.xm1.m{device}[vds] @m.xm1.m{device}[vdsat]
{tail_probe}ac dec 50 1meg 100g
let vd_db = db(v(outp) - v(outn))
meas ac g_dc  FIND vd_db AT=1meg
meas ac g_nyq FIND vd_db AT=2.5g
meas ac g_pk  MAX  vd_db FROM=10meg TO={f_top}
meas ac g_top FIND vd_db AT={f_top}
noise v(outp,outn) Vid dec 20 10meg 5g
print inoise_total
"""

_SWEEP_TAIL_PROBE = """print @m.xmt1.m{device}[vds] @m.xmt1.m{device}[vdsat]
"""


@dataclass(frozen=True)
class TunableSetting:
    """One (rs, cs) the sweep visits."""

    rs: float
    cs: float

    def tag(self) -> str:
        return f"rs{self.rs:.4g}/cs{self.cs * 1e15:.4g}f"


def run_tunable_sweep(
    point: SizingPoint,
    settings: Sequence[TunableSetting],
    corner: str = "tt",
    temp_c: float = 27.0,
    timeout_s: float = 600.0,
) -> "list[Sky130Point]":
    """Evaluate ONE sizing point at MANY (rs, cs) settings, in one process.

    Returns one `Sky130Point` per setting, in the order given. On a
    process-level failure EVERY entry comes back `ok=False` with the same
    reason — a partial result is never returned, because a caller handed 40 of
    67 back would silently score a design on a grid it did not run.

    `point.rs` and `point.cs` are what the netlist is BUILT with; the first
    `alter` overwrites them, so they only have to be valid.
    """
    if not settings:
        return []

    def _all_failed(reason: str) -> "list[Sky130Point]":
        return [Sky130Point(ok=False, point=point, corner=corner,
                            fail_reason=reason) for _ in settings]

    # `alter Rdeg` / `alter Cdeg` name the IDEAL elements. With drawn devices
    # those instances do not exist, ngspice reports the failed alter as a
    # WARNING and exits 0 (G26), and every setting would come back reporting
    # the FIRST geometry's numbers — 67 identical results that look like a
    # converged sweep. Refuse the combination rather than discover it later.
    if point.passives is not None:
        return _all_failed(
            "run_tunable_sweep cannot alter drawn passives: `alter Rdeg`/"
            "`alter Cdeg` name the ideal elements, and altering a subckt-"
            "wrapped device is G35's silent-wrong-answer path anyway. Re-emit "
            "the netlist per setting, or sweep with passives=None."
        )

    if corner not in VALID_CORNERS:
        return _all_failed(f"unknown corner {corner!r}")
    try:
        lib = lib_for_device(point.device,
                             real_passives=point.passives is not None,
                             section=corner)
    except FileNotFoundError as exc:
        return _all_failed(str(exc))

    if point.tail is None:
        tail_source = _TAIL_IDEAL.format(IT="{IT}")
        tail_probe = ""
    else:
        t = point.tail
        tail_source = _TAIL_MIRROR.format(
            device=t.device, n_mir=f"{t.mirror_ratio:g}",
            w_tail=f"{t.w_tail:.6g}", l_tail=f"{t.l_tail:.6g}",
            nf_tail=int(t.nf_tail), w_ref=f"{t.w_ref:.6g}",
            nf_ref=int(t.nf_ref),
            i_ref=f"{t.i_ref_a(point.i_tail_per_side_a):.9g}",
            c_byp=f"{t.c_bypass_f:.9g}")
        tail_probe = _SWEEP_TAIL_PROBE.format(device=t.device)

    body = "".join(
        _SWEEP_STEP.format(rs=f"{st.rs:.10g}", cs=f"{st.cs:.10g}",
                           device=point.device, tail_probe=tail_probe,
                           f_top=f"{MAX_SEARCH_TOP_HZ / 1e9:g}g")
        for st in settings)
    text = (assemble_netlist(_TOPOLOGY,
                lib=lib.as_posix(), corner=corner, device=point.device,
                w=point.w, l=point.l, nf=int(point.nf), rl=point.rl,
                rs=point.rs, cs=point.cs, cl=point.cl,
                it=point.i_tail_per_side_a, vdd=point.vdd, vcm=point.vcm,
                temp_c=temp_c, tail_source=tail_source,
                passive_block=passive_block(point.passives))
            + _CONTROL_SWEEP_HEAD + body + "quit\n.endc\n\n.end\n")
    assert_no_inert_writes(text)

    import time
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        shutil.copy(SPICE_DIR / ".spiceinit", tmp / ".spiceinit")
        (tmp / "sw.cir").write_text(text, encoding="ascii")
        try:
            proc = subprocess.run([str(ngspice_path()), "-b", "sw.cir"],
                                  cwd=str(tmp), capture_output=True, text=True,
                                  timeout=timeout_s)
        except (subprocess.TimeoutExpired, OSError) as exc:
            return _all_failed(f"ngspice: {exc}")
        out = proc.stdout + "\n" + proc.stderr
    runtime = time.perf_counter() - t0

    # NOTE the silent-failure scan is deliberately NOT applied to the whole
    # output here. G54's `-nan(ind)` hits INDIVIDUAL settings, and a
    # process-wide scan would throw away all 67 because one of them NaN'd —
    # measured at 6.1% of processes lost, against a 0.08% per-evaluation rate.
    # `_parse_sweep` scans each block separately; a truncated or malformed run
    # still fails everything, because the block COUNT will not match.
    return _parse_sweep(out, point, settings, corner, runtime)


def _parse_sweep(out, point, settings, corner, runtime):
    """Split one process's output into one `Sky130Point` per setting.

    Splitting on the `v(s1)` print is what makes the Nth block the Nth setting.
    If the count does not match, EVERY entry fails rather than the first N
    succeeding — a short list would score a design on a grid it never ran.
    """
    n = len(settings)
    blocks = re.split(r"(?=^\s*v\(s1\)\s*=)", out, flags=re.M)
    head, blocks = blocks[0], blocks[1:]
    # A process-level failure — bad library, a crash, a parse abort — shows up
    # BEFORE the first block and truncates the rest, so it fails everything.
    fatal = scan_for_silent_failures(head)
    if fatal or len(blocks) != n:
        why = (f"ngspice failed before the sweep: {fatal[0][:140]}" if fatal
               else f"sweep returned {len(blocks)} blocks for {n} settings")
        return [Sky130Point(ok=False, point=point, corner=corner,
                            runtime_s=runtime, fail_reason=why)
                for _ in settings]

    pts = []
    for st, blk in zip(settings, blocks):
        p2 = SizingPoint(w=point.w, l=point.l, nf=point.nf, rs=st.rs, cs=st.cs,
                         rl=point.rl, cl=point.cl,
                         i_tail_per_side_a=point.i_tail_per_side_a,
                         vcm=point.vcm, vdd=point.vdd, device=point.device,
                         tail=point.tail)
        # PER-SETTING silent-failure scan. One `-nan(ind)` (G54) fails ONE
        # setting, not the whole grid.
        bad = scan_for_silent_failures(blk)
        if bad:
            pts.append(Sky130Point(ok=False, point=p2, corner=corner,
                                   runtime_s=runtime / n,
                                   fail_reason=f"silent failure at "
                                               f"{st.tag()}: {bad[0][:120]}"))
            continue
        r = Sky130Point(ok=True, point=p2, corner=corner, runtime_s=runtime / n)
        r.v_src_dc = parse_scalar(blk, "v(s1)")
        i_vdd = parse_scalar(blk, "i(vdd)")
        r.i_supply_a = None if i_vdd is None else -i_vdd
        r.gm = find_device_scalar(blk, "gm")
        r.vds = find_device_scalar(blk, "vds")
        r.vdsat = find_device_scalar(blk, "vdsat")
        if point.tail is not None:
            d = point.tail.device
            r.vds_tail = parse_scalar(blk, f"@m.xmt1.m{d}[vds]")
            r.vdsat_tail = parse_scalar(blk, f"@m.xmt1.m{d}[vdsat]")
        r.g_dc_db, _ = parse_meas(blk, "g_dc")
        r.g_nyq_db, _ = parse_meas(blk, "g_nyq")
        r.g_pk_db, r.f_pk_hz = parse_meas(blk, "g_pk")
        r.g_top_db, _ = parse_meas(blk, "g_top")
        r.vn_in_vrms = parse_scalar(blk, "inoise_total")
        need = ["gm", "vds", "vdsat", "v_src_dc", "i_supply_a", "g_dc_db",
                "g_nyq_db", "g_pk_db", "f_pk_hz", "g_top_db", "vn_in_vrms"]
        if point.tail is not None:
            need += ["vds_tail", "vdsat_tail"]
        missing = [k for k in need if getattr(r, k) is None]
        if missing:
            r = Sky130Point(ok=False, point=p2, corner=corner,
                            runtime_s=runtime / n,
                            fail_reason=f"could not parse {missing} at {st.tag()}")
        pts.append(r)
    return pts


def measured_swing_pp_v(pt: Sky130Point, compression_db: float = 1.0) -> Optional[float]:
    """The number `DeviceResult.vout_swing_v` should carry, in Vpp.

    The 1 dB compression point if the sweep reached it, else `None` — never a
    fallback to `4*I*RL`, because substituting a computed ceiling for a
    measured linear limit is exactly the substitution this module exists to
    stop.
    """
    if not pt.ok or pt.vid is None or pt.point is None:
        return None
    lim = swing_limits(pt.vid, pt.vod, pt.sat_ok, pt.id_min,
                       compression_db=compression_db,
                       i_ref_a=pt.point.i_tail_per_side_a)
    return lim.linear_pp_v


def measured_linear_input_pp_v(pt: Sky130Point,
                               compression_db: float = 1.0) -> Optional[float]:
    """**The differential input the stage can take**, in Vpp. The other half
    of `measured_swing_pp_v`, and the one the eye actually turns on.

    S8 is blocked on this repository's delivered design because the required
    OUTPUT swing exceeds the measured linear limit. That verdict has always
    been reported in output volts, which is correct and is also the harder
    number for a reader to act on: an output limit has to be divided by a gain
    the reader has to look up before it can be compared with the amplitude the
    link drives. This returns the comparison directly.

    `None` on the same terms as `measured_swing_pp_v`: the sweep did not reach
    compression, which is a LOWER bound (`SwingLimits.max_swept_in_pp_v`) and
    never a fallback to a computed number.
    """
    if not pt.ok or pt.vid is None or pt.point is None:
        return None
    lim = swing_limits(pt.vid, pt.vod, pt.sat_ok, pt.id_min,
                       compression_db=compression_db,
                       i_ref_a=pt.point.i_tail_per_side_a)
    return lim.linear_in_pp_v


__all__: Sequence[str] = (
    "SizingPoint", "Sky130Point", "SwingLimits", "TunableSetting",
    "run_point", "run_tunable_sweep", "passive_block",
    "swing_limits", "measured_swing_pp_v", "measured_linear_input_pp_v",
    "textbook_swing_pp_v",
    "lib_for_device", "NFET_01V8", "NFET_G5V0", "VALID_CORNERS",
    "SPICE_DIR", "TRIMMED_LIB", "CTLE_LIB",
)
