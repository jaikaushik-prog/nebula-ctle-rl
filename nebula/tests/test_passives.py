"""
The passive models must agree with the PDK and with the simulator.

Three tiers, deliberately separated so most of them run with no simulator:

  * **Pure** — geometry mapping, round-trip error, the guards that must raise.
  * **PDK-parsing** — every constant transcribed into `passives.py` is re-read
    from the installed SKY130 tree and compared. This is what stops a silent
    drift between a model card and the Python that claims to describe it
    (CLAUDEwa.md §8 rule 9, HANDOFF G32).
  * **Simulated** — the analytic models against ngspice, and the three silent
    traps (`mult`/`mf` do nothing; `w` is inert on the fixed-width families;
    `m=` is the multiplier that works). These skip cleanly without ngspice.

The simulated tier is the one that matters most: `passives.py` exists to be an
INVERTIBLE model of a device, and an invertible model that disagrees with the
device is worse than no model, because `to_geometry` would emit geometries
that look right and measure wrong.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest

from nebula.device.passives import (
    FIXED_WIDTH_UM,
    GRID_UM,
    MIM_FAMILIES,
    PASSIVE_CORNER_PARAMS,
    PASSIVE_CORNERS,
    RES_HIGH_PO,
    RES_L_MIN_UM,
    capacitor_geometry,
    fixed_width_subckt,
    lib_section,
    mim_capacitance_f,
    mim_side_for,
    resistor_geometry,
    to_geometry,
)

PDK = Path(r"C:\Users\DELL\sky130A")
SPICE_DIR = Path(__file__).resolve().parents[1] / "device" / "spice"
FULL_LIB = PDK / "libs.tech" / "ngspice" / "sky130.lib.spice"
#: The EXTENDED trim (task 4c): nfet + poly resistors + MIM, 25 corner
#: sections. ~4.2 s per invocation against the full library's ~56 s.
#: Equivalence is asserted by test_trimmed_lib_passives.py, so the fast
#: tests below may use it.
CTLE_LIB = SPICE_DIR / "sky130_ctle.lib.spice"
NGSPICE = Path(
    r"C:\Users\DELL\miniforge3\envs\nebula\Library\bin\ngspice_con.exe")

needs_pdk = pytest.mark.skipif(
    not PDK.exists(), reason="needs the SKY130 PDK install (HANDOFF G33)")
needs_sim = pytest.mark.skipif(
    not (NGSPICE.exists() and CTLE_LIB.exists()),
    reason="needs ngspice + the SKY130 PDK install (HANDOFF G33)")


# ─────────────────────────────────────────────────────────────────────────────
# Pure.
# ─────────────────────────────────────────────────────────────────────────────

def test_lib_section_maps_the_five_by_five_corner_grid():
    # tt + typical is plain `tt`; tt + a passive corner DROPS the tt prefix.
    assert lib_section("tt") == "tt"
    assert lib_section("tt", "typical") == "tt"
    assert lib_section("tt", "hh") == "hh"
    assert lib_section("ss", "typical") == "ss"
    assert lib_section("ss", "hh") == "ss_hh"
    assert lib_section("fs", "lh") == "fs_lh"


def test_lib_section_rejects_unknown_corners():
    with pytest.raises(ValueError, match="MOS corner"):
        lib_section("nope")
    with pytest.raises(ValueError, match="passive corner"):
        lib_section("tt", "nope")


def test_every_lib_section_actually_exists_in_the_pdk():
    """All 25 (MOS x passive) sections must be real `.lib` blocks.

    The 4f claim — that the passive axis is a full cross product, so S9's 45
    corners become 225 rather than 135 — rests on these existing. If a section
    were missing, ngspice would fail at parse time with a message that reads
    like a missing library.
    """
    if not FULL_LIB.exists():
        pytest.skip("needs the SKY130 PDK install")
    text = FULL_LIB.read_text(errors="replace")
    have = set(re.findall(r"^\.lib\s+(\S+)", text, flags=re.M))
    want = {lib_section(m, p)
            for m in ("tt", "ss", "ff", "sf", "fs") for p in PASSIVE_CORNERS}
    assert len(want) == 25
    assert want <= have, f"missing .lib sections: {sorted(want - have)}"


def test_fixed_width_family_rejects_an_unlisted_width():
    """Trap 2: an unlisted `w` is SILENTLY IGNORED by the subckt, so the
    wrapper must refuse rather than let it through."""
    assert fixed_width_subckt("res_high_po", 0.69).endswith("res_high_po_0p69")
    assert fixed_width_subckt("res_xhigh_po", 2.85).endswith("_2p85")
    with pytest.raises(ValueError, match="SILENTLY IGNORED"):
        fixed_width_subckt("res_high_po", 1.0)


def test_head_resistance_dominates_a_narrow_resistor():
    """The reason `to_geometry` widens instead of shortening.

    At minimum width the head alone puts the floor an order of magnitude
    above the bottom of the `rs` bound (50 ohm).
    """
    narrow = RES_HIGH_PO.resistance(0.35, RES_L_MIN_UM)
    wide = RES_HIGH_PO.resistance(10.0, RES_L_MIN_UM)
    assert narrow > 1400.0
    assert wide < 60.0
    assert narrow / wide > 20.0


def test_resistor_geometry_raises_rather_than_clamping():
    """A target under the floor at EVERY legal width must fail loudly.

    Clamping is how an undrawable geometry ends up in a netlist that
    simulates perfectly happily.
    """
    with pytest.raises(ValueError, match="head-resistance floor|no realisable"):
        resistor_geometry(1.0)


def test_resistor_geometry_snaps_to_the_layout_grid():
    for target in (50.0, 137.0, 319.0, 565.0, 1000.0):
        g = resistor_geometry(target)
        steps = g.l_um / GRID_UM
        assert abs(steps - round(steps)) < 1e-9, f"{g.l_um} is off-grid"
        assert g.l_um >= RES_L_MIN_UM


def test_capacitor_geometry_snaps_and_round_trips():
    for target in (100e-15, 500e-15, 1.83e-12, 1.90e-12, 10e-12):
        g = capacitor_geometry(target)
        steps = g.w_um / GRID_UM
        assert abs(steps - round(steps)) < 1e-9
        assert abs(g.rel_error) < 1e-3


def test_mim_side_for_inverts_mim_capacitance_f():
    for c in (100e-15, 1e-12, 5e-12, 10e-12):
        s = mim_side_for(c)
        assert mim_capacitance_f(s, s) == pytest.approx(c, rel=1e-12)


# ── the 4i result, pinned ────────────────────────────────────────────────────

#: The bound `to_geometry`'s round-trip error must stay inside, in OCTAVES of
#: `f_z`. Measured max over 4000 box samples is 1.04e-3 octaves; this is a 5x
#: headroom over that, so the test pins the RESULT without being brittle to a
#: width-ladder change.
F_ZERO_QUANTISATION_BOUND_OCTAVES: float = 5e-3

#: Session 12b: the designs that keep their peak across the load range have
#: about this much f_peak centring slack.
CENTRING_SLACK_OCTAVES: float = 0.12


def test_quantisation_error_is_a_small_fraction_of_the_centring_slack():
    """THE 4i RESULT, and it is a negative one.

    The concern was that rounding a continuous `(rs, cs)` onto realisable
    geometry might eat a significant share of the 0.12 octaves of centring
    slack. It does not: the worst case over the whole box is ~1e-3 octaves,
    under 1 % of the slack. Quantisation is not a first-order effect here,
    and the reason is that `l` is free on a 5 nm grid while `f_z` depends on
    it only through a ratio.
    """
    rng = np.random.default_rng(0)
    n = 2000
    rs = np.exp(rng.uniform(math.log(50), math.log(1000), n))
    cs = np.exp(rng.uniform(math.log(100e-15), math.log(10e-12), n))
    rl = np.exp(rng.uniform(math.log(50), math.log(800), n))
    worst = 0.0
    for a, b, c in zip(rs, cs, rl):
        g = to_geometry(float(a), float(b), float(c))
        worst = max(worst, abs(g.f_zero_error_octaves()))
    assert worst < F_ZERO_QUANTISATION_BOUND_OCTAVES
    assert worst < 0.05 * CENTRING_SLACK_OCTAVES


def test_every_point_in_the_box_is_realisable():
    """No corner of the proposed box is undrawable. If this goes red, the box
    and the device families disagree and one of them has to move."""
    for rs in (50.0, 1000.0):
        for cs in (100e-15, 10e-12):
            for rl in (50.0, 800.0):
                g = to_geometry(rs, cs, rl)
                assert g.worst_rel_error() < 1e-3


# ─────────────────────────────────────────────────────────────────────────────
# PDK-parsing: the transcribed constants must match the installed PDK.
# ─────────────────────────────────────────────────────────────────────────────

def _param(text: str, name: str) -> float:
    """Read `name = value` out of a PDK file.

    The PDK writes parameters three ways and all three appear in the files
    this module reads: `+ name = v` (continuation), `.param name= v` (leading
    keyword, no space before `=`), and bare `name = v`. Anchoring on `^\\+?`
    alone misses the second, which is how the poly tempco silently failed to
    parse. The name is word-bounded so `tc1rpolybody` cannot match inside a
    longer identifier.
    """
    m = re.search(rf"(?:^|^\.param\s+|\s|\+)\s*{re.escape(name)}\s*=\s*"
                  rf"([-+]?[\d.]+(?:[eE][-+]?\d+)?)", text, flags=re.M)
    assert m, f"{name} not found"
    return float(m.group(1))


@needs_pdk
def test_res_high_po_constants_match_the_model_card():
    card = (PDK / "libs.ref/sky130_fd_pr/spice"
            / "sky130_fd_pr__res_high_po.model.spice").read_text(errors="replace")
    assert _param(card, "rsheet") == pytest.approx(RES_HIGH_PO.rsheet_body)
    assert _param(card, "rhead_ps") == pytest.approx(RES_HIGH_PO.rsheet_head)
    assert _param(card, "rbody_dw") == pytest.approx(RES_HIGH_PO.dw)


@needs_pdk
def test_poly_body_and_head_temperature_coefficients_have_opposite_signs():
    """Transcription check AND the fact 4e's cancellation question turns on.

    Body +514 ppm/C, head -430 ppm/C. A short (head-dominated) resistor
    therefore drifts the OTHER WAY from a long one, so "the poly resistor's
    tempco" is not a single number — it is geometry-dependent.
    """
    rc = (PDK / "libs.tech/ngspice"
          / "sky130_fd_pr__model__r+c.model.spice").read_text(errors="replace")
    assert _param(rc, "tc1rpolybody") == pytest.approx(RES_HIGH_PO.tc1_body)
    assert RES_HIGH_PO.tc1_body > 0 > RES_HIGH_PO.tc1_head


@needs_pdk
@pytest.mark.parametrize("corner,file", [
    ("typical", "res_typical__cap_typical__lin.spice"),
    ("ll", "res_low__cap_low__lin.spice"),
    ("hh", "res_high__cap_high__lin.spice"),
    ("hl", "res_high__cap_low__lin.spice"),
    ("lh", "res_low__cap_high__lin.spice"),
])
def test_passive_corner_params_match_the_pdk(corner, file):
    text = (PDK / "libs.tech/ngspice/r+c" / file).read_text(errors="replace")
    want = PASSIVE_CORNER_PARAMS[corner]
    assert _param(text, "camimc") == pytest.approx(want["camimc"], rel=1e-9)
    assert _param(text, "cpmimc") == pytest.approx(want["cpmimc"], rel=1e-9)
    assert _param(text, "sky130_fd_pr__res_high_po__var") == pytest.approx(
        want["res_high_po_var"], rel=1e-9)


@needs_pdk
def test_the_five_mos_corners_all_hold_the_passives_at_typical():
    """THE 4f STRUCTURAL FINDING, asserted rather than asserted-in-prose.

    tt, ss, ff, sf and fs every one include `res_typical__cap_typical`. So
    every corner number this project has published held the passives fixed —
    not by decision, but because the MOS corner names do not touch them.
    """
    text = FULL_LIB.read_text(errors="replace")
    for mos in ("tt", "ss", "ff", "sf", "fs"):
        body = re.search(rf"^\.lib {mos}$(.*?)^\.endl {mos}$",
                         text, flags=re.M | re.S)
        assert body, f"no .lib {mos} section"
        assert "res_typical__cap_typical" in body.group(1)


@needs_pdk
def test_mim_families_exist_in_this_metal_stack():
    """4a said to stop and report if the MIM the design wants is unavailable.
    It is available; this is the check that keeps that true."""
    for fam in MIM_FAMILIES:
        short = fam.replace("sky130_fd_pr__", "")
        card = (PDK / "libs.ref/sky130_fd_pr/spice"
                / f"{fam}.model.spice")
        assert card.exists(), f"{short} not installed"
        assert ".subckt" in card.read_text(errors="replace")


@needs_pdk
def test_the_fixed_width_families_exist_at_exactly_the_declared_widths():
    d = PDK / "libs.ref/sky130_fd_pr/spice"
    for fam in ("res_high_po", "res_xhigh_po"):
        for w in FIXED_WIDTH_UM:
            tag = str(w).replace(".", "p")
            assert (d / f"sky130_fd_pr__{fam}_{tag}.model.spice").exists()


# ─────────────────────────────────────────────────────────────────────────────
# Simulated.
# ─────────────────────────────────────────────────────────────────────────────

def _run(netlist: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        shutil.copy(SPICE_DIR / ".spiceinit", tmp / ".spiceinit")
        (tmp / "p.cir").write_text(netlist, encoding="ascii")
        proc = subprocess.run([str(NGSPICE), "-b", "p.cir"], cwd=str(tmp),
                              capture_output=True, text=True, timeout=300)
    return proc.stdout + "\n" + proc.stderr


def _scalar(out: str, vec: str) -> float:
    m = re.search(rf"^{re.escape(vec)}\s*=\s*([-\d.eE+]+)", out, flags=re.M)
    assert m, f"{vec} not in output:\n{out[:2000]}"
    return float(m.group(1))


_R_PROBE = """* forced-current resistance probe
.lib "{lib}" {corner}
{body}
.control
set noaskquit
op
{prints}
quit
.endc
.end
"""


@needs_sim
def test_analytic_resistor_model_matches_simulation():
    """`passives.py` must invert the ACTUAL device, not a remembered formula.

    Forced 10 uA, V/I. Covers width scaling, the head term, and `m=`.
    """
    cases = [(1.0, 1.78, 1), (2.0, 1.78, 1), (1.0, 1.78, 4),
             (0.35, 2.0, 1), (5.73, 10.0, 1), (10.0, 0.5, 1)]
    body, prints = [], []
    for i, (w, l, m) in enumerate(cases):
        body.append(f"I{i} 0 n{i} 10u")
        mm = f" m={m}" if m > 1 else ""
        body.append(f"X{i} n{i} 0 0 sky130_fd_pr__res_high_po "
                    f"w={w} l={l}{mm}")
        prints.append(f"print v(n{i})")
    out = _run(_R_PROBE.format(lib=CTLE_LIB.as_posix(), corner="tt",
                               body="\n".join(body),
                               prints="\n".join(prints)))
    for i, (w, l, m) in enumerate(cases):
        meas = _scalar(out, f"v(n{i})") / 10e-6
        model = RES_HIGH_PO.resistance(w, l, m=m)
        assert model == pytest.approx(meas, rel=2e-3), (
            f"w={w} l={l} m={m}: model {model:.4f} vs measured {meas:.4f}")


@needs_sim
def test_mult_does_nothing_and_m_is_the_real_multiplier():
    """TRAP 1, pinned. If this ever goes red, `mult` started working and
    `passives.py`'s central warning needs revisiting."""
    body = """
I0 0 n0 10u
X0 n0 0 0 sky130_fd_pr__res_high_po w=1 l=1.78
I1 0 n1 10u
X1 n1 0 0 sky130_fd_pr__res_high_po w=1 l=1.78 mult=4
I2 0 n2 10u
X2 n2 0 0 sky130_fd_pr__res_high_po w=1 l=1.78 m=4
I3 0 n3 10u
Xa n3 0 0 sky130_fd_pr__res_high_po w=1 l=1.78
Xb n3 0 0 sky130_fd_pr__res_high_po w=1 l=1.78
Xc n3 0 0 sky130_fd_pr__res_high_po w=1 l=1.78
Xd n3 0 0 sky130_fd_pr__res_high_po w=1 l=1.78
"""
    prints = "\n".join(f"print v(n{i})" for i in range(4))
    out = _run(_R_PROBE.format(lib=CTLE_LIB.as_posix(), corner="tt",
                               body=body, prints=prints))
    base, mult4, m4, par4 = (_scalar(out, f"v(n{i})") for i in range(4))
    # `mult=4` changes NOTHING.
    assert mult4 == pytest.approx(base, rel=0, abs=0)
    # `m=4` quarters it, and agrees with four explicit devices exactly.
    assert m4 == pytest.approx(base / 4.0, rel=1e-9)
    assert m4 == pytest.approx(par4, rel=0, abs=0)


@needs_sim
def test_w_is_inert_on_the_fixed_width_family():
    """TRAP 2, pinned. `res_high_po_0p69` ignores `w` entirely — including a
    physically absurd one — and the device that really is 2.85 um wide
    differs by ~4x."""
    body = """
I0 0 n0 10u
X0 n0 0 0 sky130_fd_pr__res_high_po_0p69 w=0.69 l=5
I1 0 n1 10u
X1 n1 0 0 sky130_fd_pr__res_high_po_0p69 w=2.85 l=5
I2 0 n2 10u
X2 n2 0 0 sky130_fd_pr__res_high_po_0p69 w=99 l=5
I3 0 n3 10u
X3 n3 0 0 sky130_fd_pr__res_high_po_2p85 w=2.85 l=5
"""
    prints = "\n".join(f"print v(n{i})" for i in range(4))
    out = _run(_R_PROBE.format(lib=CTLE_LIB.as_posix(), corner="tt",
                               body=body, prints=prints))
    v = [_scalar(out, f"v(n{i})") for i in range(4)]
    assert v[1] == pytest.approx(v[0], rel=0, abs=0), "w changed 0p69 — trap 2 is stale"
    assert v[2] == pytest.approx(v[0], rel=0, abs=0), "w=99 was not ignored"
    assert v[3] / v[0] < 0.3, "the real 2p85 device should be ~4x smaller"


_C_PROBE = """* AC impedance capacitance probe
.lib "{lib}" {corner}
{body}
.control
set noaskquit
ac lin 1 {freq} {freq}
{prints}
quit
.endc
.end
"""


@needs_sim
def test_analytic_mim_model_matches_simulation():
    """Capacitance from the AC impedance, per 4b.

    1 MHz is chosen because the MIM's series resistance is ~8 ohm against a
    reactance of ~87 kohm there, so `Im{Z}` is the capacitance to 1 part in
    1e8 and no resonance is anywhere near. `Rdc` gives the floating node a DC
    path; at 1 G it is 4 orders above the reactance and does not perturb it.
    """
    cases = [(30.0, 30.0, 1), (30.0, 30.0, 4), (10.0, 10.0, 1),
             (50.0, 20.0, 1)]
    freq = 1e6
    body, prints = [], []
    for i, (w, l, m) in enumerate(cases):
        mm = f" m={m}" if m > 1 else ""
        body.append(f"Rdc{i} c{i} 0 1G")
        body.append(f"I{i} 0 c{i} ac 1u")
        body.append(f"X{i} c{i} 0 {MIM_FAMILIES[0]} w={w} l={l}{mm}")
        prints.append(f"print vi(c{i})")
    out = _run(_C_PROBE.format(lib=CTLE_LIB.as_posix(), corner="tt",
                               freq=f"{freq:g}", body="\n".join(body),
                               prints="\n".join(prints)))
    for i, (w, l, m) in enumerate(cases):
        im_z = _scalar(out, f"vi(c{i})") / 1e-6
        meas = -1.0 / (2 * math.pi * freq * im_z)
        model = mim_capacitance_f(w, l, m=m)
        assert model == pytest.approx(meas, rel=5e-3), (
            f"w={w} l={l} m={m}: model {model:.6e} vs measured {meas:.6e}")


@needs_sim
def test_mf_does_nothing_on_the_mim_cap():
    """TRAP 1 again, on the capacitor. `mf=4` is not four capacitors."""
    freq = 1e6
    body = f"""
Rdc0 c0 0 1G
I0 0 c0 ac 1u
X0 c0 0 {MIM_FAMILIES[0]} w=30 l=30
Rdc1 c1 0 1G
I1 0 c1 ac 1u
X1 c1 0 {MIM_FAMILIES[0]} w=30 l=30 mf=4
Rdc2 c2 0 1G
I2 0 c2 ac 1u
X2 c2 0 {MIM_FAMILIES[0]} w=30 l=30 m=4
"""
    prints = "\n".join(f"print vi(c{i})" for i in range(3))
    out = _run(_C_PROBE.format(lib=CTLE_LIB.as_posix(), corner="tt",
                               freq=f"{freq:g}", body=body, prints=prints))
    base, mf4, m4 = (_scalar(out, f"vi(c{i})") for i in range(3))
    assert mf4 == pytest.approx(base, rel=0, abs=0), "mf started working"
    # ngspice prints 6 significant digits, so the exact-quarter check cannot
    # be tighter than that regardless of how exact the underlying arithmetic
    # is. The `mf` comparison above IS exact because both sides are printed
    # at the same precision and must agree digit for digit.
    assert m4 == pytest.approx(base / 4.0, rel=1e-5)
