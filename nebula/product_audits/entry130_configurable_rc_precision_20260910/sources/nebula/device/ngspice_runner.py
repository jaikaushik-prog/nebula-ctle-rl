"""
device/ngspice_runner.py — minimal batch-mode ngspice driver.

Not yet the full device layer (that owes a `DeviceResult` and PVT corners).
This is the piece needed to *verify* the G1 hand-design and its parameter
bounds against the simulator instead of against intuition, and it is the
foundation the real wrapper will be built on.

Why batch mode and not PySpice: see HANDOFF G23. `ngspice_con -b file.cir`
through `subprocess` has no FFI state to corrupt, parallelises across corners
by just running more processes, and turns a crash into an exit code rather
than a segfault inside the Python interpreter.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

# ngspice from the conda env (HANDOFF G20 — the _con build, not the GUI one).
_DEFAULT_NGSPICE = Path(
    r"C:\Users\DELL\miniforge3\envs\nebula\Library\bin\ngspice_con.exe"
)


def ngspice_path() -> Path:
    if _DEFAULT_NGSPICE.exists():
        return _DEFAULT_NGSPICE
    found = shutil.which("ngspice_con") or shutil.which("ngspice")
    if found:
        return Path(found)
    raise FileNotFoundError(
        "ngspice not found. Expected the conda env at "
        f"{_DEFAULT_NGSPICE}, or ngspice_con on PATH. See nebula/G0_RESULTS.md."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Netlist template — the S2 topology with an ideal tail (G1 stage).
#
# Deliberately kept byte-identical in structure to
# nebula/device/spice/g1_handdesign.cir so that anything measured here is
# measured on the same circuit the hand-design was done on.
# ─────────────────────────────────────────────────────────────────────────────

_NETLIST = """* auto-generated G1 sweep point
.param VDD_V={vdd} ITAIL={i_bias} RS_OHM={rs} CS_F={cs} RL_OHM={rl} CL_F={cl}
.param VCM_V={vcm_in} WIN={w_in} LIN={l_in} NF={nf_in}

vdd  vdd 0 {{VDD_V}}
vinp inp 0 dc {{VCM_V}} ac 0.5
vinn inn 0 dc {{VCM_V}} ac -0.5

m1 outp inp src1 0 nch W={{WIN}} L={{LIN}} m={{NF}}
m2 outn inn src2 0 nch W={{WIN}} L={{LIN}} m={{NF}}
rs src1 src2 {{RS_OHM}}
cs src1 src2 {{CS_F}}
it1 src1 0 dc {{ITAIL/2}}
it2 src2 0 dc {{ITAIL/2}}
rl1 vdd outp {{RL_OHM}}
rl2 vdd outn {{RL_OHM}}
cl1 outp 0 {{CL_F}}
cl2 outn 0 {{CL_F}}

.model nch nmos level=54 version=4.8.2
+ tnom=27 vth0=0.35 k1=0.5 k2=0.05 u0=0.045 toxe=2.8n toxp=2.8n ndep=2.4e17
+ lint=0.01u wint=0.01u rdsw=200 cgso=0.3n cgdo=0.3n

.control
set noaskquit
op
print @m1[gm] @m1[gmbs] @m1[gds] @m1[vds] @m1[vdsat] @m1[vth] @m1[id] @m1[vgs]
print v(outp) v(src1)

ac dec 50 1meg 100g
let vd = v(outp)-v(outn)
let vd_db = db(vd)
meas ac g_dc   FIND vd_db AT=1meg
meas ac g_nyq  FIND vd_db AT=2.5g
meas ac g_pk   MAX  vd_db FROM=10meg TO=50g

noise v(outp,outn) vinp dec 20 10meg 5g
print inoise_total
.endc
.end
"""


@dataclass
class SpicePoint:
    """Everything one ngspice run measures. `ok=False` => do not trust fields."""

    ok: bool
    fail_reason: Optional[str] = None
    gm: Optional[float] = None
    gmbs: Optional[float] = None
    gds: Optional[float] = None
    vds: Optional[float] = None
    vdsat: Optional[float] = None
    vth: Optional[float] = None
    vgs: Optional[float] = None
    id_a: Optional[float] = None
    v_out_dc: Optional[float] = None
    v_src: Optional[float] = None
    g_dc_db: Optional[float] = None
    g_nyq_db: Optional[float] = None
    g_pk_db: Optional[float] = None
    f_pk_hz: Optional[float] = None
    vn_in_vrms: Optional[float] = None

    @property
    def peaking_db(self) -> float:
        return self.g_pk_db - self.g_dc_db  # type: ignore[operator]

    @property
    def in_saturation(self) -> bool:
        return self.vds > self.vdsat  # type: ignore[operator]


_NUM = r"[-+0-9.eE]+"


def _scalar(text: str, name: str) -> Optional[float]:
    m = re.search(rf"^{re.escape(name)}\s*=\s*({_NUM})\s*$", text, re.M)
    return float(m.group(1)) if m else None


def _meas(text: str, name: str) -> tuple[Optional[float], Optional[float]]:
    """`meas` prints `name = value` and, for MAX, `at= x` on the same line."""
    m = re.search(rf"^{re.escape(name)}\s*=\s*({_NUM})(?:\s+at=\s*({_NUM}))?", text, re.M)
    if not m:
        return None, None
    at = float(m.group(2)) if m.group(2) else None
    return float(m.group(1)), at


def run_point(params: Mapping[str, float], vdd: float = 1.2,
              timeout_s: float = 60.0) -> SpicePoint:
    """Simulate one sizing point. Never raises — failures come back as ok=False."""
    try:
        text = _NETLIST.format(vdd=vdd, **{k: params[k] for k in
                                           ("i_bias", "rs", "cs", "rl", "cl",
                                            "vcm_in", "w_in", "l_in", "nf_in")})
    except KeyError as exc:
        return SpicePoint(ok=False, fail_reason=f"missing param {exc}")

    with tempfile.TemporaryDirectory() as td:
        cir = Path(td) / "pt.cir"
        cir.write_text(text, encoding="ascii")
        try:
            proc = subprocess.run(
                [str(ngspice_path()), "-b", str(cir)],
                capture_output=True, text=True, timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return SpicePoint(ok=False, fail_reason=f"ngspice timeout >{timeout_s}s")
        except OSError as exc:
            return SpicePoint(ok=False, fail_reason=f"ngspice launch failed: {exc}")

    out = proc.stdout + "\n" + proc.stderr
    if "doAnalyses: iteration limit reached" in out or "singular matrix" in out.lower():
        return SpicePoint(ok=False, fail_reason="ngspice: non-convergence")

    pt = SpicePoint(ok=True)
    pt.gm = _scalar(out, "@m1[gm]")
    pt.gmbs = _scalar(out, "@m1[gmbs]")
    pt.gds = _scalar(out, "@m1[gds]")
    pt.vds = _scalar(out, "@m1[vds]")
    pt.vdsat = _scalar(out, "@m1[vdsat]")
    pt.vth = _scalar(out, "@m1[vth]")
    pt.vgs = _scalar(out, "@m1[vgs]")
    pt.id_a = _scalar(out, "@m1[id]")
    pt.v_out_dc = _scalar(out, "v(outp)")
    pt.v_src = _scalar(out, "v(src1)")
    pt.g_dc_db, _ = _meas(out, "g_dc")
    pt.g_nyq_db, _ = _meas(out, "g_nyq")
    pt.g_pk_db, pt.f_pk_hz = _meas(out, "g_pk")
    pt.vn_in_vrms = _scalar(out, "inoise_total")

    missing = [n for n in ("gm", "vds", "vdsat", "g_dc_db", "g_pk_db", "vn_in_vrms")
               if getattr(pt, n) is None]
    if missing:
        head = "; ".join(l for l in out.splitlines() if "rror" in l)[:200]
        return SpicePoint(ok=False, fail_reason=f"could not parse {missing}. {head}")
    return pt


def analytic_a_dc(gm: float, rs: float, rl: float,
                  gmbs: float = 0.0) -> float:
    """CLAUDEwa.md §6 A_dc, optionally including the body effect.

    §6 gives `A_dc = gm*RL / (1 + gm*Rs/2)`. With the bulk tied to ground
    rather than to the source — which is what every NMOS in a bulk process
    does — the moving source node also drives the body terminal, and the
    degeneration factor becomes `1 + (gm + gmbs)*Rs/2`. Passing `gmbs=0`
    reproduces §6 exactly; passing the simulated `gmbs` is the honest model.
    """
    return gm * rl / (1.0 + (gm + gmbs) * rs / 2.0)
