"""
device/gmid_lut.py — the SKY130 nfet as a MEASURED table, not a fitted model.

WHAT THIS IS
------------
A gm/I_D lookup table built by direct ngspice `.dc` sweep of one nfet_01v8,
indexed on `(process, temp, W, L, V_ds, V_sb, V_gs)` and storing the `.op`
PRIMITIVES at every node: `gm`, `id`, `gmbs`, `gds`, `vth`, `vdsat`, `cgg`,
`cgs`, `cgd`. Every derived quantity — `gm/I_D`, `f_T`, `gm*ro`, the current
density `I_D/W` — is computed **in Python from those primitives**
(CLAUDEwa.md §8 rule 10), never inside a `.control` block.

**`W` IS AN AXIS, AND IT SHOULD NOT HAVE HAD TO BE.** The classical gm/I_D
method's whole economy is that `gm/I_D` depends on the inversion level and not
on `W`, so one sweep at a reference width scales to any width through the
current density `I_D/W`. **Measured on SKY130 at the `nf = 4` this project
fixes (G38), that premise fails by too much to use.** At TT/27, L = 0.30 um,
V_ds = 0.75 V, V_sb = 0.40 V, V_gs = 0.90 V:

    W (um)      10       15       20       30       40       60       80      100
    W/nf       2.50     3.75     5.00     7.50    10.00    15.00    20.00    25.00
    I_D/W   1.25e-5  1.35e-5  1.43e-5  1.56e-5  1.72e-5  1.87e-5  1.92e-5  1.95e-5
    gm/I_D    10.74    10.47    10.23    10.00     9.63     9.31     9.19     9.14

`I_D/W` moves **1.56x across the `w_in` box** (20-100 um) and `gm/I_D` moves
15 %. The mechanism is G53's: the SKY130 model bins are cut on **W per
FINGER**, so holding `nf` at 4 and sweeping `W` from 20 to 100 um sweeps
W/nf from 5 to 25 um, straight across the bin set. The variation is **smooth
and monotone**, so it interpolates — but scaling `I_D` linearly in `W`, which
is what the textbook method does, would be a **56 % error in the proposed
width**, silently, on a device that simulates perfectly happily.

`check_width_independence()` is the measurement, `GMID_MAP.md` records it, and
the extra axis costs about 5x the build time and nothing at lookup.

It exists to support `common/design_space.py`, which inverts it: given a
target `gm/I_D` it returns the geometry that delivers it, so a search can be
run in DESIGN coordinates instead of device coordinates.

WHY A TABLE AND NOT THE FIT THAT ALREADY EXISTS — read this before adding a
third answer to "what is gm here?"
--------------------------------------------------------------------------
`experiments/prescreen.py::predict_gm` is already a gm/I_D characterisation:
`log(gm/I_D)` least-squares-fitted on `(1, logJ, logJ^2, logL, logJ*logL,
lognf)` over the 1890 already-paid-for TT operating points in
`robust_geometry_data.csv`. It is a good fit and it is not being replaced.

The two answer DIFFERENT questions, and stating the difference is the whole of
rule 9 here:

  * `prescreen.predict_gm` maps a DESIGN VECTOR `(w, l, nf, i_bias)` to `gm`
    with **no bias solve**. That is what a pre-screen needs: it must be
    callable on a candidate before deciding whether to simulate it.
  * this table maps a BIAS POINT `(L, V_ds, V_sb, V_gs)` to the primitives.
    Using it from a design vector REQUIRES a bias solve, because `V_gs` and
    `V_sb` are unknowns — that solve is `design_space.solve_bias`.

So neither can be expressed in terms of the other without the fixed point in
between, and the table is not a drop-in replacement for the fit. What it does
buy is threefold and each part is measurable rather than asserted:

  1. **`I_D` stops being assumed.** The fit was calibrated on a population
     where `I_D = i_bias/2` exactly, which is true of an IDEAL tail. The real
     mirror delivers **4-8 % less** (session 13, measured, `TAIL_DEVICE.md`),
     and `BASELINES.md` §11 names that as the first mechanism to try for the
     pre-screen's `+0.361 dB` peaking bias at benchmark conditions. A table
     indexed on the bias point does not care how `I_D` was arrived at.
  2. **`V_ds` and `V_sb` become axes rather than being marginalised out.** The
     fit's population carried whatever `V_ds`/`V_sb` its box happened to
     produce; those are real dependences and they are now resolvable.
  3. **It is a measurement, so its error is quantisation and interpolation,
     not extrapolation.** A regression asked outside its calibration
     population has no error bar. A table asked outside its grid RAISES.

`tests/test_gmid_lut.py::test_lut_and_prescreen_fit_agree_within_measured_band`
holds the two against each other and records the divergence, so if they ever
disagree it is a visible number rather than a silent fork.

WHAT THE TABLE IS NOT
---------------------
**It is not a result.** Nothing may ever be scored from a value read out of
here. The table produces a REQUEST — a geometry to simulate — and only what
`sky130_runner` measures afterwards is real. That is not pedantry: `to_geometry`
is electrically stable and geometrically CHAOTIC (G67 — a 0.016 % change in
`rs` flips the device, 15x area spread across a 0.16 % resistance spread), and
the `res_po` bottom plate then adds +1.4 to +24.3 fF onto a 32.6 fF `cl`
(G66). A requested `f_z` and a realised `f_z` are different numbers.

THREE THINGS MEASURED WHILE BUILDING THIS, all new
---------------------------------------------------
**(a) You write MICRONS and you read back METRES.** `W=40` in the netlist is
40 um (the library sets `.option scale=1e-6`, G31), but
`print @m.xm1.m<dev>[w]` returns `4.000000e-05`. Both are "40 microns" and
neither is wrong, but a read-back check written the obvious way — compare the
number you wrote against the number you read — fails by 1e6 on a correct
circuit, which is G31's failure mode wearing the opposite sign.
`_assert_geometry_applied` does the conversion in one place and says so.

**(b) `nf` does not divide the read-back width either.** G38 established that
`W` is the TOTAL width and `nf` only splits it into fingers. The read-back
confirms it from the other side: at `W=40 nf=4` the instance reports
`w = 4e-05`, i.e. the total, not the 10 um per finger. So a width read-back is
a genuine check that `W` was applied, and it is the only cheap one available.

**(c) `cgs` is NEGATIVE in BSIM4's reported convention.** Measured at
`W=40 L=0.15 nf=4 V_gs=0.7 V_ds=0.9 V_sb=0.3`: `cgg = 2.455e-14`,
`cgs = -1.663e-14`, `cgd = 1.199e-16`. These are the charge-derivative matrix
entries `dQ_g/dV_x`, not capacitances between terminals, and `|cgs|` is the
one a designer means. Stored RAW, exactly as ngspice reports them, and
`f_t_hz()` uses `abs()` with this note attached — because storing a
sign-corrected copy would be a second definition of the same primitive.

COST
----
Measured on this machine, nfet-only trimmed library (G36): **0.34 s per
invocation**, and one invocation carries the WHOLE `V_gs` axis because the
sweep is a `.dc`. So the table costs `n_corner * n_W * n_L * n_Vds * n_Vsb`
invocations, not one per grid point. The default grid is 4 corners x 5 W x
6 L x 5 V_ds x 5 V_sb = 3000 invocations, about 17 minutes serially and
around 6 at `--workers 6`.

**The VDD axis of S9 costs nothing here**, and that is a property of the
indexing rather than a saving that was negotiated: the table is indexed on
`(V_gs, V_ds, V_sb)` — terminal voltages — so a 5 % supply move changes which
part of the table a design lands in, not the table.

Regenerate with:

    python -m nebula.device.gmid_lut --build
    python -m nebula.device.gmid_lut --report
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence

import numpy as np

from nebula.device.crosscheck import parse_scalar, scan_for_silent_failures
from nebula.device.ngspice_runner import ngspice_path
from nebula.device.sky130_runner import (
    NFET_01V8,
    SPICE_DIR,
    TRIMMED_LIB,
    VALID_CORNERS,
)

# ─────────────────────────────────────────────────────────────────────────────
# Where the table lives.
# ─────────────────────────────────────────────────────────────────────────────

HERE: Path = Path(__file__).resolve().parent

#: The cached table. TRACKED, not gitignored (G49): `GMID_MAP.md` quotes
#: numbers derived from it, so it is an INPUT to a write-up, and an experiment
#: whose input cannot be reproduced from the repo is not reproducible.
LUT_PATH: Path = HERE / "data" / "gmid_lut_sky130_nfet01v8.npz"


# ─────────────────────────────────────────────────────────────────────────────
# The grid. Every edge has a reason; none is round-numbered for tidiness.
# ─────────────────────────────────────────────────────────────────────────────

#: Drawn channel lengths, microns. Spans `rl/contract.ACTION_SPACE`'s `l_in`
#: box (0.15-1.0 um) exactly, log-spaced because that box is log-scaled and a
#: linear grid would put four of six points above 0.6 um where the response is
#: flat. 0.15 um is SKY130's minimum L bin; at 1.0 um the box's own provenance
#: note records peaking already down at 2.37 dB.
L_GRID_UM: tuple[float, ...] = (0.15, 0.21, 0.30, 0.42, 0.60, 1.00)

#: Drawn total widths, microns. Spans `rl/contract.ACTION_SPACE`'s `w_in` box
#: (20-100 um) exactly. NOT a scaling reference — a real axis, because the
#: W-independence premise is measured false here (module docstring). Linear
#: because the box is linear (`ActionDim("w_in", ..., log=False)`).
W_GRID_UM: tuple[float, ...] = (20.0, 35.0, 55.0, 75.0, 100.0)

#: Drain-source voltage, volts, at the DEVICE (v_out - v_source).
#: Floor 0.15 V is below every measured `vdsat` in the box, so the table
#: carries the triode side rather than stopping at the edge of validity — a
#: design_space request that lands there must be REJECTED with a reason, and it
#: cannot be rejected from a table that has no data there.
#: Ceiling 1.50 V: VDD is 1.8 V, and the source node cannot be below ~0.2 V for
#: a real tail (`ACTION_SPACE`'s `vcm_in` floor provenance), so 1.5 V is
#: already generous.
VDS_GRID_V: tuple[float, ...] = (0.15, 0.35, 0.60, 0.95, 1.50)

#: Source-bulk voltage, volts. THE AXIS THE BODY EFFECT LIVES ON, and the
#: reason this table has four dimensions instead of three.
#:
#: Every NMOS here sits in the grounded p-substrate, so `V_sb` IS the source
#: node voltage, which `ACTION_SPACE`'s `vcm_in` moves almost 1:1 (RL_SMOKE §4
#: measured `d_obs` = +0.605 on the tail margin for one action step, the
#: strongest lever in the box). CLAUDEwa.md §6: omitting `gmbs` cost 2.33 dB on
#: the G1 point and FAILED the section's own 1 dB gate on a correct circuit.
#: A table without this axis reproduces that error exactly.
#:
#: 0.0 is included so the no-body-effect case is IN the table rather than being
#: an extrapolation, which is what makes the `gmbs = 0` comparison free.
VSB_GRID_V: tuple[float, ...] = (0.0, 0.20, 0.40, 0.60, 0.85)

#: Gate-source sweep, volts: start, stop, step. `.dc` carries this whole axis
#: in ONE invocation, so it is the cheap axis and it is the fine one.
#: 0.30 V is well into subthreshold at every corner (measured `vth` at TT/27 is
#: 0.766 V at V_sb = 0.3), and 1.80 V is the rail.
VGS_START_V: float = 0.30
VGS_STOP_V: float = 1.80
VGS_STEP_V: float = 0.01

#: The width `--check-width` measures the (false) W-independence premise
#: against, and the width the single-sweep helpers default to. NOT a scaling
#: reference any more — see the module docstring. `nf` is 4 because
#: `rl/contract.py` fixes it there (G38), and it is NOT an axis for the same
#: reason: G38 measured the finger effect as +/-10 % and NON-MONOTONIC, and an
#: axis you cannot interpolate is not an axis.
REF_W_UM: float = 40.0
REF_NF: int = 4

#: Widths for the W-independence check. Spans the `w_in` box (20-100 um).
WIDTH_CHECK_UM: tuple[float, ...] = (20.0, 40.0, 100.0)

#: The (process, temperature) pairs the table is built at.
#:
#: TT/27 plus the THREE SCREEN CORNERS `experiments/s9_yield.SCREEN_CORNERS`
#: uses — slow-hot, fast-cold, slow-cold. Not a full 5x3 cross product: the
#: corner runner screens on three and G47 measured three corners worth 98.7 %
#: of forty-five, so building fifteen would be paying for a resolution the rest
#: of the project has already decided it does not use.
#:
#: The VDD axis is absent BY CONSTRUCTION, not by omission — see the module
#: docstring. A supply move changes where a design lands in this table, not the
#: table.
CORNER_GRID: tuple[tuple[str, float], ...] = (
    ("tt", 27.0),
    ("ss", 125.0),
    ("ff", 0.0),
    ("ss", 0.0),
)

#: Primitives pulled out of the `.dc` sweep, in `wrdata` column order.
#: `vgs` is not here: `wrdata` interleaves the sweep variable before EVERY
#: column, so it arrives for free and is read off column 0.
SWEEP_PRIMITIVES: tuple[str, ...] = (
    "gm", "id", "gmbs", "gds", "vth", "vdsat", "cgg", "cgs", "cgd",
)


# ─────────────────────────────────────────────────────────────────────────────
# The netlist. ONE definition (rule 9); `spice/gmid_probe.cir` is generated
# from this same string by `--write-netlist` so a human reading the netlist
# sees the deck that produced the numbers (G32).
# ─────────────────────────────────────────────────────────────────────────────

_NETLIST = """* gm/I_D characterisation sweep -- GENERATED by device/gmid_lut.py.
* One nfet, terminal voltages forced. Bulk at 0: V_sb IS the source node, which
* is what makes gmbs an axis rather than an assumption (CLAUDEwa.md section 6).
.param mc_mm_switch=0
.param mc_pr_switch=0
.lib "{lib}" {corner}
.temp {temp_c}

Vsb  s 0 {vsb:.6f}
Vgs  g s {vgs_start:.6f}
Vds  d s {vds:.6f}
XM1  d g s 0 {device} W={w_um:g} L={l_um:g} nf={nf:d}

.control
set noaskquit
set filetype=ascii
op
* Geometry read-back. The ONLY cheap proof that W and L were applied rather
* than accepted and ignored, which is this repo's most frequent failure
* (G35/G56/G57). NOTE the units: written in microns, returned in METRES.
print @m.xm1.m{device}[w] @m.xm1.m{device}[l]
save {save_list}
dc Vgs {vgs_start:.6f} {vgs_stop:.6f} {vgs_step:.6f}
wrdata sweep.txt {save_list}
quit
.endc

.end
"""


def _instance(prop: str, device: str = NFET_01V8) -> str:
    """`@m.xm1.m<device>[prop]` — the subckt-qualified instance reference.

    SKY130 devices sit inside a subckt, so `@m1[gm]` does not exist and asking
    for it produces "is not available or has zero length", which ngspice prints
    as a WARNING and then exits 0 (G26). One definition, here.
    """
    return f"@m.xm1.m{device}[{prop}]"


# ─────────────────────────────────────────────────────────────────────────────
# Failures. Named, never silent — the `rl/evaluator.py` discipline.
# ─────────────────────────────────────────────────────────────────────────────


class LutBuildError(RuntimeError):
    """A sweep did not produce trustworthy data. Never swallowed."""


@dataclass(frozen=True)
class SweepResult:
    """One `.dc` sweep: the whole `V_gs` axis at one `(corner, L, V_ds, V_sb)`.

    `ok=False` means trust NOTHING here — same contract as `Sky130Point`.
    """

    ok: bool
    fail_reason: Optional[str] = None
    vgs_v: Optional[np.ndarray] = None
    prim: Mapping[str, np.ndarray] = field(default_factory=dict)
    w_read_um: Optional[float] = None
    l_read_um: Optional[float] = None
    runtime_s: float = 0.0

    @classmethod
    def failed(cls, reason: str, runtime_s: float = 0.0) -> "SweepResult":
        return cls(ok=False, fail_reason=reason, runtime_s=runtime_s)


def _assert_geometry_applied(w_read_m: Optional[float], l_read_m: Optional[float],
                             w_um: float, l_um: float, rel_tol: float = 1e-6) -> None:
    """Raise unless the instance reports the geometry that was requested.

    THE UNIT CONVERSION IS THE POINT. `W=40` in the netlist means 40 um because
    the library sets `.option scale=1e-6` (G31); the instance reports
    `4.000000e-05`, i.e. SI metres. Comparing the two numbers directly fails by
    1e6 on a perfectly correct circuit, so the conversion happens once, here,
    with the reason attached.

    `nf` does NOT enter: G38 established that `W` is the TOTAL width and the
    read-back confirms it from the other side (at `W=40 nf=4` the instance
    reports 4e-05, not the 1e-05 a per-finger width would give).
    """
    if w_read_m is None or l_read_m is None:
        raise LutBuildError(
            "instance geometry read-back missing: ngspice did not print "
            f"{_instance('w')} / {_instance('l')}. That is G26's shape — the "
            "print became a warning and the run still exited 0."
        )
    for name, read_m, want_um in (("W", w_read_m, w_um), ("L", l_read_m, l_um)):
        read_um = read_m * 1e6
        if abs(read_um - want_um) > rel_tol * max(want_um, 1e-12):
            raise LutBuildError(
                f"{name} was NOT applied: requested {want_um:g} um, instance "
                f"reports {read_um:g} um ({read_m:g} m). A silently ignored "
                f"geometry write is G35/G57's failure mode and it exits 0."
            )


def _parse_wrdata(text: str, n_cols: int) -> tuple[np.ndarray, list[np.ndarray]]:
    """Read an ngspice `wrdata` file: `(x, y0, x, y1, x, y2, ...)` per row.

    `wrdata` repeats the sweep variable before every column, which is not
    documented anywhere obvious and is the reason this parser exists rather
    than a `np.loadtxt` call. The repeated columns are asserted identical, so a
    silently misaligned file cannot pass.
    """
    rows = [r.split() for r in text.splitlines() if r.strip()]
    if not rows:
        raise LutBuildError("wrdata file is empty — the .dc sweep produced no rows")
    arr = np.array([[float(v) for v in r] for r in rows], dtype=float)
    if arr.shape[1] != 2 * n_cols:
        raise LutBuildError(
            f"wrdata has {arr.shape[1]} columns, expected {2 * n_cols} "
            f"({n_cols} saves, each preceded by the sweep variable)"
        )
    x = arr[:, 0]
    for c in range(1, n_cols):
        if not np.allclose(arr[:, 2 * c], x, rtol=0, atol=0):
            raise LutBuildError(
                f"wrdata column {2 * c} is not the sweep variable — the file "
                "is misaligned and every primitive after it would be read "
                "under the wrong V_gs"
            )
    return x, [arr[:, 2 * c + 1] for c in range(n_cols)]


def run_sweep(corner: str, temp_c: float, l_um: float, vds_v: float, vsb_v: float,
              w_um: float = REF_W_UM, nf: int = REF_NF,
              device: str = NFET_01V8, timeout_s: float = 120.0) -> SweepResult:
    """One `.dc` V_gs sweep. Never raises on a SIMULATOR failure; raises on a
    TRUST failure.

    The asymmetry is deliberate and it is the same one `run_point` draws. A
    non-converging sweep is a fact about the grid point and comes back
    `ok=False`. A geometry that was silently ignored, or output containing a
    warning-shaped failure, is a bug in THIS file and must stop the build —
    absorbing it would put fiction in the table under a plausible label.
    """
    if corner not in VALID_CORNERS:
        return SweepResult.failed(f"unknown corner {corner!r}")

    save_list = " ".join(_instance(p, device) for p in SWEEP_PRIMITIVES)
    text = _NETLIST.format(
        lib=TRIMMED_LIB.as_posix(), corner=corner, temp_c=f"{temp_c:g}",
        device=device, w_um=w_um, l_um=l_um, nf=int(nf),
        vsb=vsb_v, vds=vds_v,
        vgs_start=VGS_START_V, vgs_stop=VGS_STOP_V, vgs_step=VGS_STEP_V,
        save_list=save_list,
    )

    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # G29: .spiceinit is read from the CURRENT DIRECTORY at parse time, so
        # it travels with the netlist. wrdata also writes to cwd, which is why
        # each sweep gets its own directory and the build is parallel-safe.
        shutil.copy(SPICE_DIR / ".spiceinit", tmp / ".spiceinit")
        cir = tmp / "gmid.cir"
        cir.write_text(text, encoding="ascii")
        try:
            proc = subprocess.run(
                [str(ngspice_path()), "-b", cir.name],
                cwd=str(tmp), capture_output=True, text=True, timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return SweepResult.failed(f"ngspice timeout >{timeout_s}s",
                                      time.perf_counter() - t0)
        except OSError as exc:
            return SweepResult.failed(f"ngspice launch failed: {exc}",
                                      time.perf_counter() - t0)

        out = proc.stdout + "\n" + proc.stderr
        # G26/G30/G35: the exit code is never a success signal. Parse first.
        offenders = scan_for_silent_failures(out)
        if offenders:
            raise LutBuildError(
                f"ngspice printed {len(offenders)} failure(s) as warnings at "
                f"corner={corner} T={temp_c} L={l_um} Vds={vds_v} Vsb={vsb_v}:\n  "
                + "\n  ".join(offenders[:5])
            )

        _assert_geometry_applied(
            parse_scalar(out, _instance("w", device)),
            parse_scalar(out, _instance("l", device)),
            w_um, l_um,
        )

        f = tmp / "sweep.txt"
        if not f.exists():
            return SweepResult.failed("wrdata produced no file (.dc did not run)",
                                      time.perf_counter() - t0)
        vgs, cols = _parse_wrdata(f.read_text(encoding="ascii", errors="replace"),
                                  len(SWEEP_PRIMITIVES))

    return SweepResult(
        ok=True,
        vgs_v=vgs,
        prim={name: col for name, col in zip(SWEEP_PRIMITIVES, cols)},
        w_read_um=w_um,
        l_read_um=l_um,
        runtime_s=time.perf_counter() - t0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# The table.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GmidLut:
    """The table, in memory. Pure once built — no simulator, no I/O.

    Arrays are shaped `(n_corner, n_W, n_L, n_Vds, n_Vsb, n_Vgs)`. `corners`
    holds `"<process>@<temp_c>"` keys in `CORNER_GRID` order.

    EVERY STORED ARRAY IS A PRIMITIVE. The derived quantities are properties
    and methods, computed on read, so there is exactly one definition of each
    (rule 9) and a stale derived column cannot exist.
    """

    corners: tuple[str, ...]
    w_um: np.ndarray
    l_um: np.ndarray
    vds_v: np.ndarray
    vsb_v: np.ndarray
    vgs_v: np.ndarray
    prim: Mapping[str, np.ndarray]
    provenance: Mapping[str, object]

    # ── derived, computed on read ───────────────────────────────────────────

    @property
    def gm_over_id(self) -> np.ndarray:
        """`gm / I_D`, 1/V. The inversion coordinate.

        `I_D` is floored at a tiny positive value rather than being allowed to
        divide by zero: deep in subthreshold at V_gs = 0.3 the measured current
        is around 4e-08 A at the reference width and it does reach numerical
        zero at the slow corners. The floor makes the array finite; the
        MONOTONICITY GATE below is what actually keeps that region out of a
        lookup, and it is a gate rather than a clamp.
        """
        return self.prim["gm"] / np.maximum(self.prim["id"], 1e-18)

    @property
    def id_per_um(self) -> np.ndarray:
        """`I_D / W` in A/um, at each `W` on the axis.

        Reported as a DIAGNOSTIC, not used as a scaling law. The classical
        method would read this at one width and multiply; the module docstring
        records the measurement that forbids it (1.56x across the box).
        """
        shape = [1] * self.prim["id"].ndim
        shape[1] = self.w_um.size                 # axis 1 is W
        return self.prim["id"] / self.w_um.reshape(shape)

    @property
    def gm_ro(self) -> np.ndarray:
        """Intrinsic gain `gm / gds`, dimensionless."""
        return self.prim["gm"] / np.maximum(self.prim["gds"], 1e-18)

    @property
    def gmbs_over_gm(self) -> np.ndarray:
        """The body-effect ratio. CLAUDEwa.md §6's `gmbs/gm`, measured."""
        return self.prim["gmbs"] / np.maximum(self.prim["gm"], 1e-18)

    def f_t_hz(self) -> np.ndarray:
        """`gm / (2*pi*|cgg|)`.

        `abs` because BSIM4 reports the charge-derivative matrix, whose
        off-diagonal entries are negative by convention (`cgs` measured at
        -1.663e-14 against `cgg` +2.455e-14 at one probe point). `cgg` itself
        is positive, so the `abs` is defensive rather than load-bearing — but a
        silent sign flip here would look like a 1e0 error, not a 1e6 one, which
        is exactly the kind this repo misses.
        """
        return self.prim["gm"] / (2.0 * math.pi * np.maximum(np.abs(self.prim["cgg"]),
                                                             1e-21))

    # ── shape and lookup ────────────────────────────────────────────────────

    def corner_index(self, process: str, temp_c: float) -> int:
        key = f"{process}@{temp_c:g}"
        if key not in self.corners:
            raise KeyError(
                f"corner {key!r} is not in this table. Built: "
                f"{list(self.corners)}. Rebuild with --build to widen it; do "
                f"NOT extrapolate."
            )
        return self.corners.index(key)

    def monotone_fraction(self, min_gm_id: float = 2.0) -> float:
        """Fraction of `(corner, L, Vds, Vsb)` curves on which `gm/I_D` is
        strictly decreasing in `V_gs` over the usable band.

        THIS IS A GATE, NOT A DIAGNOSTIC. `design_space` inverts `gm/I_D` by
        assuming it is monotone — that is a physical fact (the ratio falls from
        roughly `2/(n*V_T)` in weak inversion to `2/V_ov` in strong inversion)
        and a numerical hazard, because in deep subthreshold both `gm` and
        `I_D` underflow and the ratio becomes noise. `min_gm_id` bounds the
        band where the inversion is allowed to look.
        """
        g = self.gm_over_id
        band = g >= min_gm_id
        total = ok = 0
        it = np.ndindex(g.shape[:-1])
        for idx in it:
            sel = band[idx]
            if sel.sum() < 3:
                continue
            total += 1
            d = np.diff(g[idx][sel])
            if np.all(d < 0):
                ok += 1
        return ok / total if total else 0.0

    # ── persistence ─────────────────────────────────────────────────────────

    def save(self, path: Path = LUT_PATH) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            corners=np.array(self.corners, dtype=object),
            w_um=self.w_um, l_um=self.l_um, vds_v=self.vds_v,
            vsb_v=self.vsb_v, vgs_v=self.vgs_v,
            provenance=np.array(json.dumps(dict(self.provenance), indent=1)),
            **{f"prim_{k}": v for k, v in self.prim.items()},
        )
        return path

    @classmethod
    def load(cls, path: Path = LUT_PATH) -> "GmidLut":
        if not path.exists():
            raise FileNotFoundError(
                f"no gm/I_D table at {path}. Build it with "
                f"`python -m nebula.device.gmid_lut --build` (about 17 min, "
                f"or 6 at --workers 6)."
            )
        z = np.load(path, allow_pickle=True)
        prim = {k[len("prim_"):]: z[k] for k in z.files if k.startswith("prim_")}
        return cls(
            corners=tuple(str(c) for c in z["corners"]),
            w_um=z["w_um"], l_um=z["l_um"], vds_v=z["vds_v"],
            vsb_v=z["vsb_v"], vgs_v=z["vgs_v"],
            prim=prim,
            provenance=json.loads(str(z["provenance"])),
        )


def _sweep_job(args: tuple) -> tuple[tuple[int, int, int, int, int], SweepResult]:
    """One grid point, as a picklable unit of work for the process pool."""
    idx, proc, temp_c, w_um, l_um, vds, vsb, nf, device = args
    try:
        return idx, run_sweep(proc, temp_c, l_um, vds, vsb, w_um, nf, device)
    except LutBuildError as exc:
        # A TRUST failure inside a worker must not vanish into a traceback the
        # parent never sees. Carry it back as a failed result whose reason says
        # it was a trust failure, and let the parent raise.
        return idx, SweepResult.failed(f"TRUST FAILURE: {exc}")


def build_lut(corner_grid: Sequence[tuple[str, float]] = CORNER_GRID,
              w_grid_um: Sequence[float] = W_GRID_UM,
              l_grid_um: Sequence[float] = L_GRID_UM,
              vds_grid_v: Sequence[float] = VDS_GRID_V,
              vsb_grid_v: Sequence[float] = VSB_GRID_V,
              nf: int = REF_NF,
              device: str = NFET_01V8,
              workers: int = 1,
              progress: bool = True) -> GmidLut:
    """Run the whole grid and assemble the table. Raises on any trust failure.

    A grid point whose sweep fails leaves NaN and is counted; the build then
    FAILS if any failed, rather than shipping a table with holes in it. **A
    hole would be indistinguishable from a region the design space cannot
    reach**, which is exactly the confusion `design_space`'s named failures
    exist to prevent — and it is G73's shape (a gate whose condition is
    unreachable is indistinguishable from a deleted gate).

    `workers` parallelises across grid points. This is a BUILD, not a
    benchmark, so G71's ordering discipline does not apply — but note G48 (11
    cores buy ~3.2x, flat past 8) before raising it, and that the wall clock
    recorded in the provenance is therefore not a per-sweep cost.
    """
    n_c, n_w, n_l = len(corner_grid), len(w_grid_um), len(l_grid_um)
    n_d, n_s = len(vds_grid_v), len(vsb_grid_v)
    n_g = int(round((VGS_STOP_V - VGS_START_V) / VGS_STEP_V)) + 1

    prim = {k: np.full((n_c, n_w, n_l, n_d, n_s, n_g), np.nan)
            for k in SWEEP_PRIMITIVES}
    jobs: list[tuple] = []
    for ic, (proc, temp_c) in enumerate(corner_grid):
        for iw, w_um in enumerate(w_grid_um):
            for il, l_um in enumerate(l_grid_um):
                for id_, vds in enumerate(vds_grid_v):
                    for is_, vsb in enumerate(vsb_grid_v):
                        jobs.append(((ic, iw, il, id_, is_), proc, temp_c,
                                     w_um, l_um, vds, vsb, nf, device))

    total = len(jobs)
    vgs_axis: Optional[np.ndarray] = None
    failures: list[str] = []
    done = 0
    t0 = time.perf_counter()

    def _absorb(idx, r: SweepResult) -> None:
        nonlocal vgs_axis
        if not r.ok:
            failures.append(f"{idx}: {r.fail_reason}")
            return
        assert r.vgs_v is not None
        if vgs_axis is None:
            vgs_axis = r.vgs_v
        elif len(r.vgs_v) != len(vgs_axis):
            raise LutBuildError(
                f"sweep length changed: {len(r.vgs_v)} vs {len(vgs_axis)}. "
                f"A ragged axis cannot be indexed."
            )
        for k in SWEEP_PRIMITIVES:
            prim[k][idx][:] = r.prim[k]

    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for idx, r in ex.map(_sweep_job, jobs, chunksize=4):
                _absorb(idx, r)
                done += 1
                if progress and done % 200 == 0:
                    el = time.perf_counter() - t0
                    print(f"  {done}/{total}  {el:6.1f} s elapsed", flush=True)
    else:
        for job in jobs:
            idx, r = _sweep_job(job)
            _absorb(idx, r)
            done += 1
            if progress and done % 200 == 0:
                el = time.perf_counter() - t0
                print(f"  {done}/{total}  {el:6.1f} s elapsed, "
                      f"{el / done:.3f} s/sweep", flush=True)

    if failures:
        raise LutBuildError(
            f"{len(failures)} of {total} grid sweeps failed. A table with "
            f"holes is worse than no table — a hole reads as 'unreachable' "
            f"and is really 'unmeasured'. First few:\n  "
            + "\n  ".join(failures[:5])
        )
    assert vgs_axis is not None

    prov = {
        "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "library": TRIMMED_LIB.as_posix(),
        "library_sha_prefix": _sha_prefix(TRIMMED_LIB),
        "ngspice": _ngspice_version(),
        "device": device,
        "ref_nf": nf,
        "vgs_start_v": VGS_START_V,
        "vgs_stop_v": VGS_STOP_V,
        "vgs_step_v": VGS_STEP_V,
        "n_sweeps": total,
        "workers": workers,
        "wall_clock_s": round(time.perf_counter() - t0, 2),
        "note": ("PRIMITIVES ONLY. gm/I_D, f_T, gm*ro and I_D/W are computed "
                 "in Python from these (CLAUDEwa.md rule 10). Nothing read out "
                 "of this table is a RESULT — it produces a request to "
                 "simulate; only sky130_runner measures."),
    }

    return GmidLut(
        corners=tuple(f"{p}@{t:g}" for p, t in corner_grid),
        w_um=np.asarray(w_grid_um, dtype=float),
        l_um=np.asarray(l_grid_um, dtype=float),
        vds_v=np.asarray(vds_grid_v, dtype=float),
        vsb_v=np.asarray(vsb_grid_v, dtype=float),
        vgs_v=vgs_axis,
        prim=prim,
        provenance=prov,
    )


def _sha_prefix(p: Path, n: int = 12) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()[:n] if p.exists() else "absent"


def _ngspice_version() -> str:
    try:
        out = subprocess.run([str(ngspice_path()), "-v"], capture_output=True,
                             text=True, timeout=30).stdout
        for line in out.splitlines():
            if "ngspice" in line.lower():
                return line.strip()
    except Exception:                                     # noqa: BLE001
        pass
    return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# The W-independence check — the premise, measured.
# ─────────────────────────────────────────────────────────────────────────────


def check_width_independence(widths_um: Sequence[float] = WIDTH_CHECK_UM,
                             corner: str = "tt", temp_c: float = 27.0,
                             l_um: float = 0.30, vds_v: float = 0.75,
                             vsb_v: float = 0.40,
                             min_gm_id: float = 4.0) -> dict:
    """Is `gm/I_D` really independent of `W`? Measure, do not assume.

    The whole gm/I_D method rests on this. If it fails, the table's `I_D/W`
    scaling is wrong and every geometry it proposes is wrong with it — quietly,
    because the design would still simulate.

    Reports the max spread in `gm/I_D` across widths at matched `V_gs`, over
    the band where `gm/I_D >= min_gm_id`, plus the same for `I_D/W`.
    """
    curves: dict[float, SweepResult] = {}
    for w in widths_um:
        r = run_sweep(corner, temp_c, l_um, vds_v, vsb_v, w_um=w)
        if not r.ok:
            raise LutBuildError(f"width check failed at W={w}: {r.fail_reason}")
        curves[w] = r

    ref = curves[widths_um[0]]
    assert ref.vgs_v is not None
    g_ref = ref.prim["gm"] / np.maximum(ref.prim["id"], 1e-18)
    band = g_ref >= min_gm_id

    gmid_spread, jd_spread = [], []
    for w, r in curves.items():
        g = r.prim["gm"] / np.maximum(r.prim["id"], 1e-18)
        jd = r.prim["id"] / w
        gmid_spread.append(g[band])
        jd_spread.append(jd[band])
    G = np.vstack(gmid_spread)
    J = np.vstack(jd_spread)

    def _rel_spread(a: np.ndarray) -> np.ndarray:
        lo, hi = a.min(axis=0), a.max(axis=0)
        return (hi - lo) / np.maximum(np.abs(lo), 1e-30)

    return {
        "widths_um": list(widths_um),
        "corner": f"{corner}@{temp_c:g}", "l_um": l_um,
        "vds_v": vds_v, "vsb_v": vsb_v, "min_gm_id": min_gm_id,
        "n_points_in_band": int(band.sum()),
        "gm_over_id_rel_spread_median": float(np.median(_rel_spread(G))),
        "gm_over_id_rel_spread_max": float(np.max(_rel_spread(G))),
        "id_per_um_rel_spread_median": float(np.median(_rel_spread(J))),
        "id_per_um_rel_spread_max": float(np.max(_rel_spread(J))),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI.
# ─────────────────────────────────────────────────────────────────────────────


def _report(lut: GmidLut) -> None:
    p = lut.provenance
    print("=" * 78)
    print("gm/I_D lookup table -- SKY130 nfet_01v8")
    print("=" * 78)
    print(f"  built          {p.get('built_utc')}")
    print(f"  ngspice        {p.get('ngspice')}")
    print(f"  library        {Path(str(p.get('library'))).name} "
          f"(sha {p.get('library_sha_prefix')})")
    print(f"  device         {p.get('device')}  nf={p.get('ref_nf')} (fixed, G38)")
    print(f"  corners        {', '.join(lut.corners)}")
    print(f"  W (um)         {', '.join(f'{v:g}' for v in lut.w_um)}")
    print(f"  L (um)         {', '.join(f'{v:g}' for v in lut.l_um)}")
    print(f"  Vds (V)        {', '.join(f'{v:g}' for v in lut.vds_v)}")
    print(f"  Vsb (V)        {', '.join(f'{v:g}' for v in lut.vsb_v)}")
    print(f"  Vgs (V)        {lut.vgs_v[0]:g} .. {lut.vgs_v[-1]:g} "
          f"step {p.get('vgs_step_v')}  ({len(lut.vgs_v)} points)")
    print(f"  sweeps         {p.get('n_sweeps')} invocations, "
          f"{p.get('wall_clock_s')} s")
    print()
    g = lut.gm_over_id
    print(f"  gm/I_D range   {np.nanmin(g):.2f} .. {np.nanmax(g):.2f} 1/V")
    print(f"  monotone       {lut.monotone_fraction() * 100:.2f} % of curves "
          f"strictly decreasing over the usable band")
    r = lut.gmbs_over_gm
    finite = np.isfinite(r) & (lut.prim["id"] > 1e-9)
    print(f"  gmbs/gm        {np.nanpercentile(r[finite], 5):.3f} .. "
          f"{np.nanpercentile(r[finite], 95):.3f}  (5th-95th pct, I_D > 1 nA)")
    print("=" * 78)
    print("NOTHING READ OUT OF THIS TABLE IS A RESULT. It produces a request;")
    print("only sky130_runner measures. See G66/G67 for why that matters.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--build", action="store_true",
                    help="run the grid and write the table (~17 min serial)")
    ap.add_argument("--check-width", action="store_true",
                    help="measure the W-independence premise")
    ap.add_argument("--report", action="store_true",
                    help="describe the cached table")
    ap.add_argument("--workers", type=int, default=1,
                    help="parallel sweeps; see G48 before raising past 8")
    ap.add_argument("--out", type=Path, default=LUT_PATH)
    a = ap.parse_args(argv)

    if not (a.build or a.check_width or a.report):
        a.report = True

    if a.build:
        print(f"building gm/I_D table (workers={a.workers}) ...", flush=True)
        lut = build_lut(workers=a.workers)
        path = lut.save(a.out)
        print(f"wrote {path} ({path.stat().st_size / 1e6:.2f} MB)")
        _report(lut)

    if a.check_width:
        print("\nW-independence check (the gm/I_D premise, measured):")
        res = check_width_independence()
        for k, v in res.items():
            print(f"  {k:32s} {v}")

    if a.report and not a.build:
        _report(GmidLut.load(a.out))

    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = (
    "GmidLut", "SweepResult", "LutBuildError",
    "W_GRID_UM", "L_GRID_UM", "VDS_GRID_V", "VSB_GRID_V", "CORNER_GRID",
    "SWEEP_PRIMITIVES", "REF_W_UM", "REF_NF", "LUT_PATH",
    "VGS_START_V", "VGS_STOP_V", "VGS_STEP_V",
    "run_sweep", "build_lut", "check_width_independence",
)
