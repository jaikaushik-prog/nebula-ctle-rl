"""
The trimmed SKY130 library must be EQUIVALENT to the full one, not just faster.

`nebula/device/spice/sky130_nfet_only.lib.spice` includes only the
`nfet_01v8` model files, dropping the other 29 device families the full
`libs.tech/ngspice/sky130.lib.spice` pulls in per corner. That takes an
ngspice invocation from **16-35 s to 0.42 s** (HANDOFF G34), which is what
makes a PDK-backed RL loop possible at all.

A speedup obtained by dropping model cards is worthless unless it changes no
number. So:

  * `sky130_full_lib_golden.json` holds values captured from the **FULL**
    library across all five process corners and four (W, L) points chosen to
    land in DIFFERENT model bins.
  * The fast test runs only the trimmed library (~0.4 s per point) and demands
    an EXACT match against those goldens.
  * A slow, opt-in test (`-m slow`) re-derives the goldens from the full
    library, so the reference itself can be re-verified when the PDK moves.

These tests skip if ngspice or the PDK is absent — they are the only tests in
the suite that need a simulator.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

SPICE_DIR = Path(__file__).resolve().parents[1] / "device" / "spice"
GOLDEN = Path(__file__).parent / "fixtures" / "sky130_full_lib_golden.json"
TRIM_LIB = SPICE_DIR / "sky130_nfet_only.lib.spice"
FULL_LIB = Path(r"C:\Users\DELL\sky130A\libs.tech\ngspice\sky130.lib.spice")
NGSPICE = Path(
    r"C:\Users\DELL\miniforge3\envs\nebula\Library\bin\ngspice_con.exe")

pytestmark = pytest.mark.skipif(
    not (NGSPICE.exists() and TRIM_LIB.exists() and GOLDEN.exists()),
    reason="needs ngspice + the SKY130 PDK install (HANDOFF G33)",
)

_NETLIST = """* trimmed-library equivalence probe
.param VDD_V=1.8 ITAIL=5m RS_OHM=800 CS_F=0.8p RL_OHM=200 CL_F=0.8p
.param VCM_V=0.9 WIN={w} LIN={l} NF_IN=10
.param mc_mm_switch=0
.param mc_pr_switch=0
.lib "{lib}" {corner}
vdd  vdd 0 {{VDD_V}}
vinp inp 0 dc {{VCM_V}} ac 0.5
vinn inn 0 dc {{VCM_V}} ac -0.5
xm1 outp inp src1 0 sky130_fd_pr__nfet_01v8 W={{WIN}} L={{LIN}} nf={{NF_IN}} mult=1
xm2 outn inn src2 0 sky130_fd_pr__nfet_01v8 W={{WIN}} L={{LIN}} nf={{NF_IN}} mult=1
rs src1 src2 {{RS_OHM}}
cs src1 src2 {{CS_F}}
it1 src1 0 dc {{ITAIL/2}}
it2 src2 0 dc {{ITAIL/2}}
rl1 vdd outp {{RL_OHM}}
rl2 vdd outn {{RL_OHM}}
cl1 outp 0 {{CL_F}}
cl2 outn 0 {{CL_F}}
.control
set noaskquit
op
print @m.xm1.msky130_fd_pr__nfet_01v8[gm]
print @m.xm1.msky130_fd_pr__nfet_01v8[gmbs]
print @m.xm1.msky130_fd_pr__nfet_01v8[vth]
print @m.xm1.msky130_fd_pr__nfet_01v8[id]
ac dec 50 1meg 100g
let vd_db = db(v(outp)-v(outn))
meas ac g_dc FIND vd_db AT=1meg
meas ac g_pk MAX vd_db FROM=10meg TO=50g
noise v(outp,outn) vinp dec 20 10meg 5g
print inoise_total
quit
.endc
.end
"""

_OP_KEYS = ("gm", "gmbs", "vth", "id")
_AC_KEYS = ("g_dc", "g_pk", "inoise_total")


def _run(lib: Path, corner: str, w: float, l: float) -> dict[str, float]:
    text = _NETLIST.format(lib=lib.as_posix(), corner=corner, w=w, l=l)
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "p.cir"
        f.write_text(text, encoding="ascii")
        proc = subprocess.run(
            [str(NGSPICE), "-b", str(f)],
            capture_output=True, text=True, cwd=str(SPICE_DIR), timeout=900,
        )
    out = proc.stdout + "\n" + proc.stderr

    # A silent failure here would show up as a missing key, but say so plainly.
    assert "could not find a valid modelname" not in out, (
        f"model lookup failed for {corner} W={w} L={l} — if this is the "
        f"trimmed library, check `.option scale=1.0u` is present (the full "
        f"library sets it in all.spice, which the trim does not include)"
    )

    vals: dict[str, float] = {}
    for k in _OP_KEYS:
        m = re.search(rf"\[{k}\]\s*=\s*(\S+)", out)
        assert m, f"missing @m1[{k}] for {corner} W={w} L={l}"
        vals[k] = float(m.group(1))
    for k in _AC_KEYS:
        m = re.search(rf"^\s*{k}\s*=\s*(\S+)", out, re.M)
        assert m, f"missing {k} for {corner} W={w} L={l}"
        vals[k] = float(m.group(1))
    return vals


def _golden() -> dict[str, dict[str, float]]:
    return json.loads(GOLDEN.read_text(encoding="ascii"))


def _cases() -> list[tuple[str, str, float, float]]:
    out = []
    for key in sorted(_golden()):
        corner, wpart, lpart = key.split("|")
        out.append((key, corner, float(wpart[1:]), float(lpart[1:])))
    return out


@pytest.mark.parametrize("key,corner,w,l", _cases())
def test_trimmed_library_matches_full_library(key, corner, w, l):
    """Exact match, every corner, across model-bin boundaries.

    W = 4 / 6 / 9 um at L = 0.15 um sit in three DIFFERENT bins (edges at
    3, 5, 7 um), and L = 0.5 um is a different L bin again. If the trim
    dropped a card the bins depend on, at least one of these moves.
    """
    expected = _golden()[key]
    got = _run(TRIM_LIB, corner, w, l)
    for field, want in expected.items():
        assert got[field] == pytest.approx(want, rel=0, abs=0), (
            f"{key} field {field}: trimmed library gives {got[field]}, "
            f"full library gave {want}. The trim is NOT equivalent — do not "
            f"use it for any reported number until this is explained."
        )


def test_all_five_process_corners_are_present_in_the_trim():
    """S9 needs tt/ss/ff/sf/fs. A trim that silently dropped one would only
    fail much later, when corner verification starts."""
    text = TRIM_LIB.read_text(encoding="utf-8", errors="replace")
    for corner in ("tt", "ss", "ff", "sf", "fs"):
        assert re.search(rf"^\.lib\s+{corner}\s*$", text, re.M), \
            f"trimmed library has no `.lib {corner}` section"
        assert re.search(rf"^\.endl\s+{corner}\s*$", text, re.M)


def test_trim_declares_the_scale_option():
    """`.option scale=1.0u` lives in the full library's all.spice, which the
    trim does not include. Without it W=5 means five METRES."""
    text = TRIM_LIB.read_text(encoding="utf-8", errors="replace")
    assert len(re.findall(r"^\.option\s+scale\s*=\s*1\.0u\s*$", text, re.M)) == 5


@pytest.mark.slow
@pytest.mark.skipif(not FULL_LIB.exists(), reason="full SKY130 library absent")
@pytest.mark.parametrize("key,corner,w,l", _cases()[:2])
def test_golden_values_still_reproduce_from_the_full_library(key, corner, w, l):
    """Re-verify the reference itself. Slow (~30 s/point); opt in with -m slow.

    Run this after any PDK update. If it fails, the goldens are stale and the
    fast test above is checking the trim against the wrong answer.
    """
    assert _run(FULL_LIB, corner, w, l) == pytest.approx(_golden()[key],
                                                        rel=0, abs=0)
