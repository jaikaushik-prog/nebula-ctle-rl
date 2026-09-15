"""
device/cap_probe.py — what the CTLE output node actually has to drive.

WHY THIS FILE EXISTS
--------------------
`cl` has been a *pinned constant* (150 fF) in every corner experiment this
project has run, and `S9_YIELD.md` §1 lists that pin as assumption #1 with the
note that "a different load gives different numbers and the experiment must be
re-run, not scaled". 150 fF came out of `CL_SENSITIVITY.md` as the S3-yield
maximum of five values tested — which is choosing the answer, not deriving it.

`cl` is neither a design variable (nobody chooses the following stage's input
capacitance) nor a constant (it is not known to one value). It is a **context
variable with a physically derived range**. This module measures that range
from the only thing that sets it: the gate load of the stages the CTLE drives.

THE MEASUREMENT, AND WHY IT IS NOT `@m[cgg]`
--------------------------------------------
The obvious probe is BSIM4's `@m[cgg]` instance parameter. **It is wrong for
this purpose, by about 2x, and it is wrong silently** — it is a plausible
number of the right order that leaves out two real terms:

1. **The gate overlap capacitances.** `@m[cgg]` reports the *intrinsic*
   charge-derivative capacitance. SKY130's `nfet_01v8` card carries
   `cgso = cgdo = 2.449e-10 F/m`, i.e. ~2 fF of overlap on an 8 um device,
   which the CTLE output has to charge just the same.
2. **Miller multiplication of the gate-drain term** by the loading stage's own
   voltage gain. A summer or slicer preamp with a gain of 2-3 multiplies its
   `Cgd` (which is nearly all overlap, since the intrinsic `Cgd` of a saturated
   device is ~0) by 3-4.

Measured on a W=8 um nf=4 pair at 0.5 mA/side into 600 ohm (gain 1.67 at
2.5 GHz): `@m[cgg]` = 6.27 fF, actual differential load = **13.47 fF**.

So the primary number here is measured the way the CTLE sees it: drive the
loading pair **differentially**, at the frequency the S3 window lives in, and
measure the AC current the driver has to deliver into one gate through a
zero-volt ammeter:

    C_in_per_side = Im{ i(Vgp) } / ( 2*pi*f * |v_gate| )

`@m[cgg]` and its `cgs`/`cgd`/`cgb` companions are recorded alongside, so the
size of the correction stays visible in every run rather than being folded
away — the same convention `crosscheck.CrossCheckResult` uses for the
body-effect term.

The decomposition is cross-checked in Python against the model card's own
overlap constants (`analytic_load_ff`), and the constants are **read out of the
PDK model file**, never re-declared here (CLAUDEwa.md §8 rule 9). At the point
above the two agree to 0.2%.

WHAT IS A SKETCH AND WHAT IS MEASURED
-------------------------------------
**Measured:** the capacitance of a given device at a given bias, corner and
temperature. **A sketch:** which devices, at which sizes, hang on the node.
The sizes come from `experiments/cl_range.py::LOAD_STAGES`, each with its
reasoning written down, and the width of the resulting `[cl_lo, cl_hi]` range
is dominated by that sketch — which is the honest situation and is why the
range is a range.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.device.crosscheck import (
    find_device_scalar,
    parse_scalar,
    scan_for_silent_failures,
)
from nebula.device.ngspice_runner import ngspice_path
from nebula.device.sky130_runner import (
    NFET_01V8,
    SPICE_DIR,
    TRIMMED_LIB,
    VALID_CORNERS,
)

#: Where the load is evaluated. S3's window is 1.25-2.5 GHz, so the load is
#: reported at both edges of it; `f_probe_hz` selects which one is primary.
#: 2.5 GHz (Nyquist) is the default because that is where S3's reading (b) and
#: the eye content both live.
F_NYQUIST_HZ: float = 2.5e9
F_WINDOW_LO_HZ: float = 1.25e9


# ─────────────────────────────────────────────────────────────────────────────
# The loading stage, as a sizing point.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LoadStage:
    """One stage hanging on the CTLE output, sized.

    `w_um`/`l_um` are **plain numbers in microns** — the trimmed library sets
    `.option scale=1.0u`, so `w=8` means 8 um and `w=8e-6` would mean 8
    picometres and abort with the misleading "could not find a valid
    modelname" (G31/G36). Same convention as `SizingPoint`.

    `rld_ohm` is this stage's OWN load resistor. It is not decoration: it sets
    the stage's voltage gain, and that gain Miller-multiplies the gate-drain
    overlap capacitance, which is a first-order term in what the CTLE sees.
    A stage specified without a gain has an under-specified input capacitance.
    """

    name: str
    w_um: float
    l_um: float
    nf: int
    i_side_a: float
    rld_ohm: float
    why: str = ""

    @property
    def i_tail_total_a(self) -> float:
        """One SHARED tail: unlike the CTLE this stage is not degenerated."""
        return 2.0 * self.i_side_a

    def v_out_dc_nominal(self, vdd: float = 1.8) -> float:
        return vdd - self.i_side_a * self.rld_ohm


@dataclass
class GateLoadPoint:
    """What one loading stage presents to the CTLE output, at one corner."""

    ok: bool
    fail_reason: Optional[str] = None
    stage: Optional[LoadStage] = None
    corner: str = "tt"
    temp_c: float = 27.0
    vcm_out_v: float = 1.2
    vdd: float = 1.8

    #: THE NUMBER. Differential-drive input capacitance per side, in farads,
    #: at `f_probe_hz`. This is what `cl` in the CTLE netlist represents.
    c_in_f: Optional[float] = None
    f_probe_hz: float = F_NYQUIST_HZ
    #: Same measurement at the other edge of the S3 window, so capacitance
    #: dispersion across the band is visible instead of assumed away.
    c_in_lo_f: Optional[float] = None
    #: Loading stage's own |gain| at `f_probe_hz` — the Miller multiplier.
    a_load: Optional[float] = None
    #: Real part of the driven gate current / (omega * v): a pure capacitor has
    #: none. Large values mean the load is not capacitive and `c_in_f` is not a
    #: complete description of it.
    g_in_s: Optional[float] = None

    # --- what `@m[cgg]` would have said, kept so the correction stays visible
    cgg_f: Optional[float] = None
    cgs_f: Optional[float] = None
    cgd_f: Optional[float] = None
    cgb_f: Optional[float] = None

    # --- bias, so "was this device even on?" is answerable from the record
    gm: Optional[float] = None
    id_a: Optional[float] = None
    vgs: Optional[float] = None
    vds: Optional[float] = None
    vdsat: Optional[float] = None
    v_src_dc: Optional[float] = None
    v_out_dc: Optional[float] = None
    runtime_s: float = 0.0

    @property
    def in_saturation(self) -> bool:
        return bool(self.vds is not None and self.vdsat is not None
                    and self.vds > self.vdsat)

    @property
    def c_in_ff(self) -> float:
        return self.c_in_f * 1e15                    # type: ignore[operator]

    @property
    def cgg_ff(self) -> float:
        return self.cgg_f * 1e15                     # type: ignore[operator]

    @property
    def cgg_understatement(self) -> float:
        """`c_in_f / cgg_f` — how badly the obvious probe would have lied."""
        return self.c_in_f / self.cgg_f              # type: ignore[operator]


# ─────────────────────────────────────────────────────────────────────────────
# PDK constants: referenced, never re-declared (CLAUDEwa.md §8 rule 9).
# ─────────────────────────────────────────────────────────────────────────────


def model_file_for_corner(corner: str, lib: Path = TRIMMED_LIB) -> Path:
    """The `.pm3.spice` model file the trimmed library includes for `corner`.

    Derived by reading the library rather than by rebuilding the path from a
    string, so there is exactly ONE statement in the repo of which model file
    belongs to which corner. If the trim is re-pointed, this follows it.
    """
    if corner not in VALID_CORNERS:
        raise ValueError(f"unknown corner {corner!r}; have {VALID_CORNERS}")
    text = lib.read_text(encoding="utf-8", errors="replace")
    m = re.search(rf"^\.lib\s+{corner}\s*$(.*?)^\.endl\s+{corner}\s*$",
                  text, re.M | re.S)
    if not m:
        raise ValueError(f"{lib} has no '.lib {corner}' section")
    includes = re.findall(r'^\s*\.include\s+"([^"]+)"', m.group(1), re.M)
    pm3 = [Path(p) for p in includes if p.endswith(".pm3.spice")]
    if len(pm3) != 1:
        raise ValueError(
            f"expected exactly one .pm3.spice include in '.lib {corner}', "
            f"found {len(pm3)}: {pm3}"
        )
    return pm3[0]


def pdk_model_param(name: str, corner: str = "tt",
                    lib: Path = TRIMMED_LIB) -> float:
    """Read one `.model` parameter out of the PDK card, asserting uniqueness.

    The SKY130 nfet card is binned: 180 `.model` sections, each repeating the
    full parameter list. A parameter is only usable as "the" value if every bin
    agrees on it, so this **raises** when they do not rather than silently
    returning the first. `cgso`, `cgdo` and `cgbo` do agree; `vth0` does not,
    and asking for it is supposed to fail loudly.
    """
    path = model_file_for_corner(corner, lib)
    text = path.read_text(encoding="utf-8", errors="replace")
    vals = re.findall(rf"^\+\s*{re.escape(name)}\s*=\s*([-+0-9.eE]+)\s*$",
                      text, re.M)
    if not vals:
        raise ValueError(f"{name!r} not found as a plain numeric parameter in "
                         f"{path.name}")
    uniq = {float(v) for v in vals}
    if len(uniq) != 1:
        raise ValueError(
            f"{name!r} differs across the {len(vals)} model bins in "
            f"{path.name} ({len(uniq)} distinct values, "
            f"{min(uniq):g}..{max(uniq):g}) — it is not a single constant and "
            f"must not be used as one"
        )
    return uniq.pop()


def overlap_cap_f_per_m(corner: str = "tt") -> tuple[float, float]:
    """`(cgso, cgdo)` in F/m, from the model card. Not re-declared here."""
    return (pdk_model_param("cgso", corner), pdk_model_param("cgdo", corner))


def analytic_load_ff(pt: GateLoadPoint) -> float:
    """The measured load, reconstructed from primitives — the falsifiable check.

        C_in = (|cgs| + Cgso*W) + |cgb| + (|cgd| + Cgdo*W) * (1 + |A|)

    Every term is either a parsed `.op` primitive or a model-card constant read
    out of the PDK; nothing here is fitted. Agreement with the AC measurement
    is what says the AC measurement is measuring gate capacitance and not, say,
    a resistive path or a numerical artefact. Measured agreement at the
    reference point: 13.50 fF predicted vs 13.47 fF measured, 0.2%.

    Signs: BSIM4 reports `cgs`/`cgb` as dQ_g/dV_s and dQ_g/dV_b, which are
    negative. Magnitudes are what a load is made of.
    """
    if pt.stage is None:
        raise ValueError("point carries no stage; cannot rebuild its load")
    for f in ("cgs", "cgd", "cgb", "a_load"):
        if getattr(pt, f if f == "a_load" else f + "_f") is None:
            raise ValueError(f"point is missing {f}; cannot rebuild its load")
    cgso, cgdo = overlap_cap_f_per_m(pt.corner)
    w_m = pt.stage.w_um * 1e-6
    c_gs = abs(pt.cgs_f) + cgso * w_m                # type: ignore[arg-type]
    c_gb = abs(pt.cgb_f)                             # type: ignore[arg-type]
    c_gd = abs(pt.cgd_f) + cgdo * w_m                # type: ignore[arg-type]
    return (c_gs + c_gb + c_gd * (1.0 + abs(pt.a_load))) * 1e15  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Netlist. ONE definition (rule 9); the library comes from sky130_runner.
# ─────────────────────────────────────────────────────────────────────────────

_NETLIST = """* nebula gate-load probe (auto-generated; do not edit by hand)
.lib "{lib}" {corner}
.temp {temp_c}

.param W={w} L={l} NF={nf}
.param RLD={rld} ITT={itt} VDD={vdd} VCM={vcm}

Vdd  vdd 0 {{VDD}}
* VCM here is the CTLE OUTPUT common mode -- this stage's gates hang on it.
Vcm  cm  0 {{VCM}}
Vid  vid 0 dc 0 ac 1
Einp gdp cm vid 0 0.5
Einn gdn cm vid 0 -0.5

* Zero-volt ammeters. i(Vgp) is the current the CTLE output must actually
* deliver into one gate -- overlap caps and Miller included, which is exactly
* what @m[cgg] leaves out.
Vgp  gdp inp dc 0
Vgn  gdn inn dc 0

XM1  outp inp s 0 {device} W={{W}} L={{L}} nf={{NF}}
XM2  outn inn s 0 {device} W={{W}} L={{L}} nf={{NF}}
RLp  vdd outp {{RLD}}
RLn  vdd outn {{RLD}}

* ONE shared tail: a slicer/summer input pair is not source-degenerated, so
* the tail node is a differential virtual ground -- unlike the CTLE, which
* needs two sinks so Rdeg is not shorted out.
Itail s 0 {{ITT}}

.control
set noaskquit
set filetype=ascii

op
print @m.xm1.m{device}[cgg] @m.xm1.m{device}[cgs]
print @m.xm1.m{device}[cgd] @m.xm1.m{device}[cgb]
print @m.xm1.m{device}[gm] @m.xm1.m{device}[id]
print @m.xm1.m{device}[vgs] @m.xm1.m{device}[vds] @m.xm1.m{device}[vdsat]
print v(s) v(outp)

* The bottom and the top of S3's f_peak window, so capacitance dispersion
* across the band is measured rather than assumed away. THREE points, not two:
* `ac lin 2` returns a single row from this ngspice build, which the parser
* would have to reject -- only the first and last rows are read.
ac lin 3 {f_lo} {f_hi}
wrdata cin.txt i(vgp) v(outp) v(outn)
quit
.endc

.end
"""


def measure_gate_load(
    stage: LoadStage,
    corner: str = "tt",
    temp_c: float = 27.0,
    vcm_out_v: float = 1.2,
    vdd: float = 1.8,
    device: str = NFET_01V8,
    timeout_s: float = 120.0,
) -> GateLoadPoint:
    """Measure what `stage` presents to the CTLE output. Never raises.

    CLAUDEwa.md §8 rule 2: a failed SPICE run is `ok=False`, not an exception.
    §8 rule 10: the exit code is not a success signal, so the output is grepped
    for warning-shaped failures before any number is believed.
    """
    base = GateLoadPoint(ok=False, stage=stage, corner=corner, temp_c=temp_c,
                         vcm_out_v=vcm_out_v, vdd=vdd)
    if corner not in VALID_CORNERS:
        base.fail_reason = f"unknown corner {corner!r}"
        return base
    if device != NFET_01V8:
        base.fail_reason = (f"{device!r} is not in the trimmed library; only "
                            f"{NFET_01V8} is (G36)")
        return base

    text = _NETLIST.format(
        lib=TRIMMED_LIB.as_posix(), corner=corner, temp_c=temp_c,
        device=device, w=stage.w_um, l=stage.l_um, nf=int(stage.nf),
        rld=stage.rld_ohm, itt=stage.i_tail_total_a, vdd=vdd, vcm=vcm_out_v,
        f_lo=f"{F_WINDOW_LO_HZ / 1e9:g}g", f_hi=f"{F_NYQUIST_HZ / 1e9:g}g",
    )

    import time
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # .spiceinit is read from the CURRENT DIRECTORY at parse time (G29), so
        # it travels with the netlist; wrdata also writes to cwd, which is what
        # keeps parallel runs from stepping on each other's cin.txt.
        shutil.copy(SPICE_DIR / ".spiceinit", tmp / ".spiceinit")
        cir = tmp / "cap.cir"
        cir.write_text(text, encoding="ascii")
        try:
            proc = subprocess.run(
                [str(ngspice_path()), "-b", cir.name],
                cwd=str(tmp), capture_output=True, text=True, timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            base.fail_reason = f"ngspice timeout >{timeout_s}s"
            return base
        except OSError as exc:
            base.fail_reason = f"ngspice launch failed: {exc}"
            return base
        out = proc.stdout + "\n" + proc.stderr
        cin_file = tmp / "cin.txt"
        raw = None
        if cin_file.exists() and cin_file.stat().st_size > 0:
            try:
                raw = np.loadtxt(cin_file)
            except ValueError as exc:
                base.fail_reason = f"unreadable cin.txt: {exc}"
                return base
    base.runtime_s = time.perf_counter() - t0

    offenders = scan_for_silent_failures(out)
    if offenders:
        base.fail_reason = f"ngspice silent failure: {offenders[0][:160]}"
        return base
    if raw is None:
        base.fail_reason = "ngspice produced no cin.txt"
        return base

    pt = parse_gate_load_output(out, raw, stage=stage, corner=corner,
                                temp_c=temp_c, vcm_out_v=vcm_out_v, vdd=vdd)
    pt.runtime_s = base.runtime_s
    return pt


def parse_gate_load_output(
    out: str,
    raw: np.ndarray,
    stage: LoadStage,
    corner: str = "tt",
    temp_c: float = 27.0,
    vcm_out_v: float = 1.2,
    vdd: float = 1.8,
    v_gate_ac: float = 0.5,
) -> GateLoadPoint:
    """Turn captured ngspice stdout + `cin.txt` into a `GateLoadPoint`.

    Split out from `measure_gate_load` so the parsing — which is where a wrong
    column index would produce a plausible wrong capacitance — is testable
    against a checked-in fixture with no simulator.

    `wrdata` writes an `(x, re, im)` triple per complex vector, in the order
    the vectors were listed: `i(vgp)`, `v(outp)`, `v(outn)` -> 9 columns.
    Only the first and last rows are read, so the number of sweep points does
    not have to be pinned here. `v_gate_ac` is 0.5 because the two VCVSs split
    a unit differential drive.
    """
    pt = GateLoadPoint(ok=False, stage=stage, corner=corner, temp_c=temp_c,
                       vcm_out_v=vcm_out_v, vdd=vdd)
    arr = np.atleast_2d(np.asarray(raw, dtype=float))
    if arr.ndim != 2 or arr.shape[1] != 9 or arr.shape[0] < 2:
        pt.fail_reason = (f"cin.txt has shape {arr.shape}, expected (>=2, 9) "
                          f"— frequency rows x (x, re, im) for 3 vectors")
        return pt

    pt.cgg_f = find_device_scalar(out, "cgg")
    pt.cgs_f = find_device_scalar(out, "cgs")
    pt.cgd_f = find_device_scalar(out, "cgd")
    pt.cgb_f = find_device_scalar(out, "cgb")
    pt.gm = find_device_scalar(out, "gm")
    pt.id_a = find_device_scalar(out, "id")
    pt.vgs = find_device_scalar(out, "vgs")
    pt.vds = find_device_scalar(out, "vds")
    pt.vdsat = find_device_scalar(out, "vdsat")
    pt.v_src_dc = parse_scalar(out, "v(s)")
    pt.v_out_dc = parse_scalar(out, "v(outp)")

    required = ("cgg_f", "cgs_f", "cgd_f", "cgb_f", "gm", "id_a",
                "vds", "vdsat")
    missing = [n for n in required if getattr(pt, n) is None]
    if missing:
        pt.fail_reason = f"could not parse {missing}"
        return pt

    # Rows come out in sweep order: F_WINDOW_LO_HZ first, F_NYQUIST_HZ second.
    lo_row, hi_row = arr[0], arr[-1]
    f_lo, f_hi = float(lo_row[0]), float(hi_row[0])
    if not (f_lo < f_hi):
        pt.fail_reason = f"cin.txt frequencies not increasing: {f_lo}, {f_hi}"
        return pt

    def _cap(row: np.ndarray, f: float) -> tuple[float, float]:
        i_re, i_im = float(row[1]), float(row[2])
        omega = 2.0 * math.pi * f
        return (i_im / (omega * v_gate_ac), i_re / v_gate_ac)

    pt.c_in_lo_f, _ = _cap(lo_row, f_lo)
    pt.c_in_f, pt.g_in_s = _cap(hi_row, f_hi)
    pt.f_probe_hz = f_hi

    outp = complex(hi_row[4], hi_row[5])
    outn = complex(hi_row[7], hi_row[8])
    pt.a_load = abs(outp - outn)          # unit differential drive => |A|

    if not (pt.c_in_f > 0.0):
        pt.fail_reason = (f"measured input capacitance is {pt.c_in_f:.3e} F, "
                          f"which is not a capacitance")
        return pt
    pt.ok = True
    return pt


def sanity_check_load(pt: GateLoadPoint, tol_frac: float = 0.05) -> list[str]:
    """Reasons `pt` should not be believed. Empty list = believable.

    A gate-load number that is quietly wrong looks exactly like one that is
    right, so this is the gate rather than a comment: the device must be ON
    and SATURATED (an off device has a completely different capacitance), the
    load must be essentially capacitive, and the AC measurement must agree with
    the primitives it should be reconstructible from (`analytic_load_ff`).
    """
    problems: list[str] = []
    if not pt.ok:
        return [f"point is not ok: {pt.fail_reason}"]
    if not pt.in_saturation:
        problems.append(
            f"device is not saturated (vds {pt.vds:.3f} <= vdsat "
            f"{pt.vdsat:.3f}) — its capacitance is not the operating one")
    if pt.id_a is not None and pt.gm is not None and pt.gm <= 0:
        problems.append(f"gm is {pt.gm:.3e}, so the device is off")
    # A purely capacitive load draws no in-phase current. Compare the
    # conductive part against the susceptance at the probe frequency.
    b = 2.0 * math.pi * pt.f_probe_hz * pt.c_in_f      # type: ignore[operator]
    if pt.g_in_s is not None and b > 0 and abs(pt.g_in_s) > 0.10 * b:
        problems.append(
            f"gate load is not capacitive: G/B = {abs(pt.g_in_s) / b:.3f}")
    try:
        pred = analytic_load_ff(pt)
    except ValueError as exc:
        problems.append(f"cannot rebuild the load from primitives: {exc}")
    else:
        meas = pt.c_in_ff
        if meas > 0 and abs(pred - meas) / meas > tol_frac:
            problems.append(
                f"AC measurement {meas:.3f} fF disagrees with the primitive "
                f"reconstruction {pred:.3f} fF by "
                f"{abs(pred - meas) / meas * 100:.1f}% (> {tol_frac * 100:.0f}%)")
    return problems


__all__: Sequence[str] = (
    "LoadStage", "GateLoadPoint", "measure_gate_load",
    "parse_gate_load_output", "sanity_check_load", "analytic_load_ff",
    "overlap_cap_f_per_m", "pdk_model_param", "model_file_for_corner",
    "F_NYQUIST_HZ", "F_WINDOW_LO_HZ",
)
