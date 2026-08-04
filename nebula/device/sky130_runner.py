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

    `i_tail_per_side_a` is the current in ONE branch. The topology uses two
    ideal sinks (a single shared tail would short out the degeneration
    network), so total supply current is `2 * i_tail_per_side_a` and that is
    what `power_w` bills for.
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

    @classmethod
    def from_params(
        cls,
        params: "dict[str, float]",
        vdd: float = 1.8,
        device: str = NFET_01V8,
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
        )

    @property
    def i_total_a(self) -> float:
        return 2.0 * self.i_tail_per_side_a

    @property
    def power_w(self) -> float:
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
    # --- .ac ---
    g_dc_db: Optional[float] = None
    g_nyq_db: Optional[float] = None
    g_pk_db: Optional[float] = None
    f_pk_hz: Optional[float] = None
    # --- .noise ---
    vn_in_vrms: Optional[float] = None
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
    def in_saturation(self) -> bool:
        return self.vds > self.vdsat            # type: ignore[operator]

    @property
    def gm_over_id(self) -> float:
        return self.gm / self.id_a              # type: ignore[operator]

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

_NETLIST = """* nebula sky130 sizing point (auto-generated; do not edit by hand)
.lib "{lib}" {corner}

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

* Two separate ideal sinks. A single shared tail would short the degeneration.
It1   s1 0 {{IT}}
It2   s2 0 {{IT}}

CLp   outp 0 {{CL}}
CLn   outn 0 {{CL}}

.control
set noaskquit
set filetype=ascii

op
print @m.xm1.m{device}[gm] @m.xm1.m{device}[gmbs] @m.xm1.m{device}[gds]
print @m.xm1.m{device}[vth] @m.xm1.m{device}[vds] @m.xm1.m{device}[vdsat]
print @m.xm1.m{device}[vgs] @m.xm1.m{device}[id]
print v(outp) v(s1)

ac dec 50 1meg 100g
let vd_db = db(v(outp) - v(outn))
meas ac g_dc  FIND vd_db AT=1meg
meas ac g_nyq FIND vd_db AT=2.5g
meas ac g_pk  MAX  vd_db FROM=10meg TO=50g

noise v(outp,outn) Vid dec 20 10meg 5g
print inoise_total
{swing_block}
quit
.endc

.end
"""

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
) -> Sky130Point:
    """Simulate one sizing point. Never raises — failures come back ok=False.

    CLAUDEwa.md §8 rule 2: a failed SPICE run is a bad reward, not a crash.
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
    text = _NETLIST.format(
        lib=lib.as_posix(), corner=corner, device=point.device,
        w=point.w, l=point.l, nf=int(point.nf),
        rl=point.rl, rs=point.rs, cs=point.cs, cl=point.cl,
        it=point.i_tail_per_side_a, vdd=point.vdd, vcm=point.vcm,
        swing_block=swing_block,
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
    pt.g_dc_db, _ = parse_meas(out, "g_dc")
    pt.g_nyq_db, _ = parse_meas(out, "g_nyq")
    pt.g_pk_db, pt.f_pk_hz = parse_meas(out, "g_pk")
    pt.vn_in_vrms = parse_scalar(out, "inoise_total")

    required = ("gm", "gmbs", "vds", "vdsat", "id_a",
                "g_dc_db", "g_nyq_db", "g_pk_db", "f_pk_hz", "vn_in_vrms")
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
    "SizingPoint", "Sky130Point", "SwingLimits",
    "run_point", "swing_limits", "measured_swing_pp_v", "textbook_swing_pp_v",
    "lib_for_device", "NFET_01V8", "NFET_G5V0", "VALID_CORNERS",
    "SPICE_DIR", "TRIMMED_LIB",
)
