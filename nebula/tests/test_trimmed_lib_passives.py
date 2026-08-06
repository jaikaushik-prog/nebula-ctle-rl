"""
The EXTENDED trim must be equivalent to the full library, not just faster.

G36 verified `sky130_nfet_only.lib.spice` bit-identical on **nfet cards only**.
Adding resistor and capacitor cards invalidates that verification — the new
library pulls in `r+c/*.spice`, the `res_po` parasitic, the poly resistor
subckts and the MIM models, none of which G36's goldens touch. So the
equivalence is re-established here, over component values straddling every
geometry regime the design uses, across the passive corner axis the nfet-only
trim could not express at all.

**The criterion is rel=0, abs=0.** A speedup obtained by dropping model cards
is worthless unless it changes no number, and 4c says explicitly not to
quietly relax the criterion — if bit-identity cannot be reached, report the
largest disagreement and its cause rather than widening a tolerance.

These tests are marked `slow`: each comparison parses the FULL library, which
costs ~56 s. The fast suite uses the trimmed library on the strength of what
is asserted here.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from nebula.device.passives import lib_section

PDK = Path(r"C:\Users\DELL\sky130A")
SPICE_DIR = Path(__file__).resolve().parents[1] / "device" / "spice"
FULL_LIB = PDK / "libs.tech" / "ngspice" / "sky130.lib.spice"
CTLE_LIB = SPICE_DIR / "sky130_ctle.lib.spice"
NGSPICE = Path(
    r"C:\Users\DELL\miniforge3\envs\nebula\Library\bin\ngspice_con.exe")

pytestmark = pytest.mark.skipif(
    not (NGSPICE.exists() and FULL_LIB.exists() and CTLE_LIB.exists()),
    reason="needs ngspice + the SKY130 PDK install (HANDOFF G33)",
)

#: Geometries chosen to straddle the regimes the model distinguishes:
#: head-dominated (short, narrow), body-dominated (long), the narrow-width
#: knee at 0.69 um, the widest entry in `to_geometry`'s ladder, and `m > 1`.
_RESISTORS = [
    ("sky130_fd_pr__res_high_po",  0.35,  2.00, 1),   # below the narrow knee
    ("sky130_fd_pr__res_high_po",  0.69,  5.00, 1),   # at the knee
    ("sky130_fd_pr__res_high_po",  1.00,  1.78, 1),   # head ~ body
    ("sky130_fd_pr__res_high_po",  8.00, 14.785, 2),  # design 432's rs
    ("sky130_fd_pr__res_high_po", 10.00, 16.505, 1),  # design 432's rl
    ("sky130_fd_pr__res_high_po", 10.00,  0.50, 1),   # head-dominated floor
    ("sky130_fd_pr__res_xhigh_po", 1.00,  1.78, 1),   # the other family
    ("sky130_fd_pr__res_xhigh_po", 5.73, 20.00, 1),
]

#: MIM plates spanning the `cs` bound (100 fF - 10 pF).
_CAPS = [(7.5, 7.5, 1), (30.66, 30.66, 1), (30.0, 30.0, 4), (70.5, 70.5, 1)]

_PROBE = """* trimmed-vs-full equivalence probe
.lib "{lib}" {sect}
{body}
.control
set noaskquit
op
{r_prints}
ac lin 1 1meg 1meg
{c_prints}
quit
.endc
.end
"""


def _build(lib: Path, sect: str) -> str:
    body, r_prints, c_prints = [], [], []
    for i, (sub, w, l, m) in enumerate(_RESISTORS):
        mm = f" m={m}" if m > 1 else ""
        body.append(f"I{i} 0 r{i} 10u")
        body.append(f"X{i} r{i} 0 0 {sub} w={w} l={l}{mm}")
        r_prints.append(f"print v(r{i})")
    for j, (w, l, m) in enumerate(_CAPS):
        mm = f" m={m}" if m > 1 else ""
        body.append(f"Rd{j} c{j} 0 1G")
        body.append(f"Ic{j} 0 c{j} ac 1u")
        body.append(f"Xc{j} c{j} 0 sky130_fd_pr__cap_mim_m3_1 w={w} l={l}{mm}")
        c_prints.append(f"print vr(c{j}) vi(c{j})")
    # the nfet too: adding passive includes must not perturb the device G36
    # already verified.
    body.append("Vg g 0 0.9")
    body.append("Vd d 0 1.0")
    body.append("XM1 d g 0 0 sky130_fd_pr__nfet_01v8 W=40 L=0.15 nf=4")
    dev = "@m.xm1.msky130_fd_pr__nfet_01v8"
    r_prints.append(f"print {dev}[gm] {dev}[gmbs] {dev}[vth] {dev}[id]")
    return _PROBE.format(lib=lib.as_posix(), sect=sect, body="\n".join(body),
                         r_prints="\n".join(r_prints),
                         c_prints="\n".join(c_prints))


def _run(netlist: str) -> tuple[dict[str, str], float]:
    """Run and return every `name = value` printed, as RAW TEXT.

    Raw text, not floats: `rel=0, abs=0` is only meaningful if the comparison
    is on the digits ngspice actually emitted. Parsing to float and back would
    hide a difference below the printed precision, which is exactly the kind
    of "equivalent" this test exists to refuse.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        shutil.copy(SPICE_DIR / ".spiceinit", tmp / ".spiceinit")
        (tmp / "p.cir").write_text(netlist, encoding="ascii")
        t0 = time.perf_counter()
        proc = subprocess.run([str(NGSPICE), "-b", "p.cir"], cwd=str(tmp),
                              capture_output=True, text=True, timeout=600)
        dt = time.perf_counter() - t0
    out = proc.stdout + "\n" + proc.stderr
    vals = dict(re.findall(r"^(\S+)\s*=\s*(\S+)\s*$", out, flags=re.M))
    return vals, dt


#: The (MOS, passive) pairs the equivalence is checked on. Not all 25 — each
#: costs ~60 s — but chosen so every passive corner and every MOS corner
#: appears at least once, including two mixed sections.
_SECTIONS = [("tt", "typical"), ("tt", "hh"), ("ss", "hh"), ("ff", "ll"),
             ("sf", "hl"), ("fs", "lh")]


@pytest.mark.slow
@pytest.mark.parametrize("mos,passive", _SECTIONS)
def test_trimmed_library_is_bit_identical_to_full(mos, passive):
    sect = lib_section(mos, passive)
    full, t_full = _run(_build(FULL_LIB, sect))
    trim, t_trim = _run(_build(CTLE_LIB, sect))

    # A comparison of two empty dicts passes vacuously. Guard the guard.
    expected = len(_RESISTORS) + 2 * len(_CAPS) + 4
    assert len(full) >= expected, (
        f"full library produced {len(full)} values, expected >= {expected}; "
        f"the probe did not run")
    assert set(full) == set(trim), (
        f"different vectors: only-full={sorted(set(full) - set(trim))} "
        f"only-trim={sorted(set(trim) - set(full))}")

    diffs = {k: (full[k], trim[k]) for k in full if full[k] != trim[k]}
    assert not diffs, (
        f"section {sect} differs on {len(diffs)} value(s): "
        + "; ".join(f"{k}: full={a} trim={b}" for k, (a, b) in
                    list(diffs.items())[:6]))
    assert t_trim < t_full, f"trim ({t_trim:.1f}s) not faster than full ({t_full:.1f}s)"


@pytest.mark.slow
def test_trimmed_library_declares_all_twenty_five_sections():
    text = CTLE_LIB.read_text(errors="replace")
    have = set(re.findall(r"^\.lib\s+(\S+)", text, flags=re.M))
    want = {lib_section(m, p) for m in ("tt", "ss", "ff", "sf", "fs")
            for p in ("typical", "ll", "hh", "hl", "lh")}
    assert want == have, f"missing {sorted(want - have)}, extra {sorted(have - want)}"


def test_trimmed_library_sets_the_micron_scale_in_every_section():
    """G36's gotcha-within-the-gotcha: a trim MUST declare `.option scale=1.0u`
    itself, because the full library sets it in `all.spice`, which no trim
    includes. Omit it and W=5 means five METRES."""
    text = CTLE_LIB.read_text(errors="replace")
    sections = re.findall(r"^\.lib\s+\S+(.*?)^\.endl", text, flags=re.M | re.S)
    assert len(sections) == 25
    for body in sections:
        assert ".option scale=1.0u" in body
        assert "mc_mm_switch=0" in body
