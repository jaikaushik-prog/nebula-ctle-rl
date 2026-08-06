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
from nebula.device.ngspice_runner import ngspice_path
from nebula.device.tail import TailDevice

#: Directory holding `.spiceinit` (ngbehavior=hsa, needed at PARSE time, G29)
#: and the trimmed SKY130 library (G36).
SPICE_DIR: Path = Path(__file__).resolve().parent / "spice"

#: The trimmed nfet_01v8-only library: 0.42 s per invocation instead of
#: 16-35 s, verified bit-identical on gm/gmbs/vth/id/g_dc/g_pk/inoise (G36).
TRIMMED_LIB: Path = SPICE_DIR / "sky130_nfet_only.lib.spice"

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

    @classmethod
    def from_params(
        cls,
        params: "dict[str, float]",
        vdd: float = 1.8,
        device: str = NFET_01V8,
        tail: Optional[TailDevice] = None,
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
    # --- .dc swing curve (raw, so Python owns every derived number) ---
    vid: Optional[np.ndarray] = field(default=None, repr=False)
    vod: Optional[np.ndarray] = field(default=None, repr=False)
    sat_ok: Optional[np.ndarray] = field(default=None, repr=False)
    id_min: Optional[np.ndarray] = field(default=None, repr=False)
    # --- bookkeeping ---
    point: Optional[SizingPoint] = None
    corner: str = "tt"
    runtime_s: float = 0.0

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
                and (self.g_pk_db - self.g_top_db) > PEAK_MARGIN_DB)  # type: ignore[operator]

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

    def _first(mask: np.ndarray) -> Optional[float]:
        for i in outward:
            if mask[i]:
                return 2.0 * abs(float(vod[i]))

        return None

    thr = g0 * 10.0 ** (-compression_db / 20.0)
    linear = _first(g < thr)
    sat = _first(~np.asarray(sat_ok, dtype=bool)) if sat_ok is not None else None
    steer = None
    if id_min is not None and i_ref_a:
        steer = _first(np.asarray(id_min, dtype=float) < steering_frac * i_ref_a)

    return SwingLimits(
        g_dc_v_per_v=g0,
        linear_pp_v=linear,
        saturation_pp_v=sat,
        steering_pp_v=steer,
        max_swept_pp_v=2.0 * float(np.max(np.abs(vod))),
        compression_db=compression_db,
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
Vid   vid 0 dc 0 ac 1
Einp  inp cm vid 0 0.5
Einn  inn cm vid 0 -0.5

XM1   outp inp s1 0 {device} W={{W}} L={{L}} nf={{NF}}
XM2   outn inn s2 0 {device} W={{W}} L={{L}} nf={{NF}}

RLp   vdd outp {{RL}}
RLn   vdd outn {{RL}}

* Between the two SOURCES, not source-to-ground: each half-circuit sees Rs/2,
* which is where the factor of two in k = 1 + (gm+gmbs)*Rs/2 comes from.
Rdeg  s1 s2 {{RS}}
Cdeg  s1 s2 {{CS}}

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
quit
.endc

.end
"""

#: The historical single-point netlist, reassembled. Every existing caller uses
#: this and its bytes are unchanged by the split above.
_NETLIST = _TOPOLOGY + _CONTROL_SINGLE

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

_SWING_BLOCK = """
save all @m.xm1.m{device}[vds] @m.xm1.m{device}[vdsat] @m.xm1.m{device}[id]
+ @m.xm2.m{device}[vds] @m.xm2.m{device}[vdsat] @m.xm2.m{device}[id]
dc vid -{vid_max} {vid_max} {vid_step}
wrdata swing.txt v(outp) v(outn)
+ @m.xm1.m{device}[vds] @m.xm1.m{device}[vdsat] @m.xm1.m{device}[id]
+ @m.xm2.m{device}[vds] @m.xm2.m{device}[vdsat] @m.xm2.m{device}[id]
"""


def lib_for_device(device: str) -> Path:
    """The library that carries `device`'s model cards.

    The trimmed library (G36) includes **only** `nfet_01v8`. Anything else has
    to come from the full library until its model files are added to the trim
    — and asking for it silently would produce "could not find a valid
    modelname", which G31 shows is read as a units error nine times out of ten.
    """
    if device == NFET_01V8:
        return TRIMMED_LIB
    full = Path(r"C:/Users/DELL/sky130A/libs.tech/ngspice/sky130.lib.spice")
    if not full.exists():
        raise FileNotFoundError(
            f"device {device!r} is not in the trimmed library and the full "
            f"SKY130 library was not found at {full} (HANDOFF G33)."
        )
    return full


def run_point(
    point: SizingPoint,
    corner: str = "tt",
    swing: bool = True,
    vid_max: float = 0.8,
    vid_step: float = 0.004,
    timeout_s: float = 120.0,
    temp_c: float = 27.0,
    noise_detail: bool = False,
) -> Sky130Point:
    """Simulate one sizing point. Never raises — failures come back ok=False.

    CLAUDEwa.md §8 rule 2: a failed SPICE run is a bad reward, not a crash.

    `corner` selects the PROCESS corner (the `.lib` section) and `temp_c` the
    temperature. The third S9 axis, VDD, is carried by `point.vdd` — scale it
    at the call site, because it is a property of the sizing point's supply,
    not of the run.
    """
    if corner not in VALID_CORNERS:
        return Sky130Point(ok=False, fail_reason=f"unknown corner {corner!r}",
                           point=point, corner=corner)
    try:
        lib = lib_for_device(point.device)
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

    text = _NETLIST.format(
        lib=lib.as_posix(), corner=corner, device=point.device,
        w=point.w, l=point.l, nf=int(point.nf),
        rl=point.rl, rs=point.rs, cs=point.cs, cl=point.cl,
        it=point.i_tail_per_side_a, vdd=point.vdd, vcm=point.vcm,
        swing_block=swing_block, temp_c=temp_c,
        tail_source=tail_source, tail_probe=tail_probe,
        noise_summary=noise_summary, noise_probe=noise_probe,
        f_top=f"{MAX_SEARCH_TOP_HZ / 1e9:g}g",
    )

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

    runtime = time.perf_counter() - t0

    # §8 rule 10: the exit code is not a success signal. Grep first.
    offenders = scan_for_silent_failures(out)
    if offenders:
        return Sky130Point(ok=False, corner=corner, point=point, runtime_s=runtime,
                           fail_reason=f"ngspice silent failure: {offenders[0][:160]}")

    pt = Sky130Point(ok=True, corner=corner, point=point, runtime_s=runtime)
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

    if corner not in VALID_CORNERS:
        return _all_failed(f"unknown corner {corner!r}")
    try:
        lib = lib_for_device(point.device)
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
    text = (_TOPOLOGY.format(
                lib=lib.as_posix(), corner=corner, device=point.device,
                w=point.w, l=point.l, nf=int(point.nf), rl=point.rl,
                rs=point.rs, cs=point.cs, cl=point.cl,
                it=point.i_tail_per_side_a, vdd=point.vdd, vcm=point.vcm,
                temp_c=temp_c, tail_source=tail_source)
            + _CONTROL_SWEEP_HEAD + body + "quit\n.endc\n\n.end\n")

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


__all__: Sequence[str] = (
    "SizingPoint", "Sky130Point", "SwingLimits", "TunableSetting",
    "run_point", "run_tunable_sweep",
    "swing_limits", "measured_swing_pp_v", "textbook_swing_pp_v",
    "lib_for_device", "NFET_01V8", "NFET_G5V0", "VALID_CORNERS",
    "SPICE_DIR", "TRIMMED_LIB",
)
