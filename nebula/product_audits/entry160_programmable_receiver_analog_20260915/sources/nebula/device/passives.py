"""
device/passives.py — the SKY130 resistor and capacitor families, MEASURED.

WHY THIS EXISTS
---------------
`rs`, `cs` and `rl` have been ideal `R`/`C` elements in every simulation this
project has ever run. Three consequences, and the third is the one that is
easy to miss:

1. **`f_z = 1/(2*pi*Rs*Cs)` is placed entirely by two components modelled as
   perfect.** Every corner result so far varies the transistors and holds the
   components that set the zero exactly constant.
2. **The competition asks the framework to output a SCHEMATIC.** A netlist
   carrying `rs = 217.4` is a parameter vector. Real device instances with real
   geometries are what makes the deliverable the thing the problem statement
   asked for.
3. **The passives may change which corners are worst.** The 3-corner screen
   (G47) was cut from MOS-only evidence, and SKY130 carries a SEPARATE passive
   corner axis — see `PASSIVE_CORNERS` below.

Everything in this module is a MEASURED fact or a model VALIDATED against a
measurement. Nothing is read off a datasheet line. `passive_probe.py` is the
instrument; `nebula/tests/test_passives.py` is the gate.

═══════════════════════════════════════════════════════════════════════════
THE THREE TRAPS FOUND WHILE ENUMERATING, ALL SILENT, ALL EXIT 0
═══════════════════════════════════════════════════════════════════════════

**(1) `mult` and `mf` DO NOTHING.** They are the parameter names the subckts
declare, so they look like device multipliers. They are not: in every SKY130
R and MIM model they appear ONLY inside mismatch terms, every one of which is
multiplied by `MC_MM_SWITCH`, which the corner files set to 0. Measured on
`res_high_po` w=1 l=1.78 at 10 uA:

      mult=1   942.896 mV/10uA = 942.90 ohm
      mult=4   942.896 mV/10uA = 942.90 ohm      <- IDENTICAL
      m=4      235.724 mV/10uA = 235.72 ohm      <- exactly /4

and on `cap_mim_m3_1` w=l=30: `mf=4` gives 1.8197 pF, `m=4` gives 7.2789 pF.
**Use ngspice's native `m=`.** It agrees with four explicitly instantiated
parallel devices to every printed digit (`test_passives.py`). Writing `mult=4`
and expecting a quarter of the resistance is a silent 4x error.

**(2) `w` DOES NOTHING on the fixed-width families.** `res_high_po_0p69` with
`w=0.69`, `w=2.85` and `w=99` all return **2893.64 ohm**, identical to every
digit, and `w=99` raises nothing. The width is encoded in the SUBCKT NAME and
baked into that subckt's `rsheet`; the `w` parameter survives only in mismatch
terms. So `res_high_po_0p69 w=2.85` is not a 2.85 um resistor — it is a
0.69 um one, and the device that IS 2.85 um wide (`res_high_po_2p85`, 718.61
ohm) differs from it by **4.03x**. `l` IS honoured on these families; only `w`
is inert. See `FIXED_WIDTH_UM`.

**(3) ngspice DISCARDS the generic families' non-linearity terms.** Loading
`res_high_po` prints `unrecognized parameter (p2) - ignored`, and the same for
`q2`, `p3`, `q3` — those are exactly the terms that make the resistor's value
depend on the voltage across it. ngspice's `.model r` has no place to put
them, so **the generic poly resistors simulate as perfectly linear**. The
FIXED-WIDTH families do not use them: they carry their voltage coefficients as
behavioural `r = {...}` expressions, which ngspice evaluates. So the two
families disagree about whether a poly resistor is linear, and the generic one
is optimistic. Recorded, not worked around — but it is why a linearity claim
must not be quoted off `res_high_po`.

═══════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional, Sequence

# ─────────────────────────────────────────────────────────────────────────────
# The corner axis. THIS IS THE 4f FINDING AND IT IS STRUCTURAL.
# ─────────────────────────────────────────────────────────────────────────────

#: SKY130 carries a passive corner axis that is INDEPENDENT of the MOS one.
#: All five MOS process corners (tt/ss/ff/sf/fs) include the SAME
#: `r+c/res_typical__cap_typical.spice`, so **every corner number this project
#: has published held the passives at typical** — not because that was decided,
#: but because the MOS corner names do not touch them.
#:
#: The library provides the FULL 5 x 5 cross product as named sections:
#:
#:      tt  ss  ff  sf  fs              MOS corner, passives TYPICAL
#:      ll  hh  hl  lh                  passives varied, MOS TYPICAL
#:      ss_ll ss_hh ss_hl ss_lh         ... and the same four for each of
#:      ff_ll ... sf_ll ... fs_ll ...   ss, ff, sf, fs
#:
#: so S9's 45 (5 process x 3 VDD x 3 temp) becomes **225** if the passive axis
#: is swept fully — not the 135 a 3-passive-corner guess would give.
#:
#: Naming: the first letter is the RESISTOR, the second the CAPACITOR.
#: `hl` = res_high + cap_low. "high" means higher resistance / higher
#: capacitance.
PASSIVE_CORNERS: tuple[str, ...] = ("typical", "ll", "hh", "hl", "lh")

#: Section name in `sky130.lib.spice` for a (MOS, passive) pair. `tt` + typical
#: is plain `tt`; `tt` + a passive corner drops the `tt` prefix entirely, which
#: is a naming trap worth having in one place rather than at call sites.
def lib_section(mos: str, passive: str = "typical") -> str:
    """The `.lib` section implementing (`mos`, `passive`).

    >>> lib_section("tt")            # passives typical
    'tt'
    >>> lib_section("tt", "hh")      # MOS typical, passives high-high
    'hh'
    >>> lib_section("ss", "hh")
    'ss_hh'
    """
    if mos not in ("tt", "ss", "ff", "sf", "fs"):
        raise ValueError(f"unknown MOS corner {mos!r}")
    if passive not in PASSIVE_CORNERS:
        raise ValueError(f"unknown passive corner {passive!r}; "
                         f"expected one of {PASSIVE_CORNERS}")
    if passive == "typical":
        return mos
    return passive if mos == "tt" else f"{mos}_{passive}"


#: What each passive corner multiplies, read out of
#: `libs.tech/ngspice/r+c/*__lin.spice`. These are the LIBRARY's own numbers,
#: parsed, not remembered — `test_passives.py` re-reads them from the PDK and
#: fails if they drift.
#:
#: `res_high_po__var` is a FRACTION applied to rsheet. `camimc` is the MIM
#: areal density in F/um^2 and `cpmimc` the perimeter term in F/um.
PASSIVE_CORNER_PARAMS: dict[str, dict[str, float]] = {
    "typical": {"res_high_po_var": 0.0,   "res_xhigh_po_var_mult": 0.0,
                "camimc": 2.000e-15, "cpmimc": 0.19e-15},
    "ll":      {"res_high_po_var": -0.125, "res_xhigh_po_var_mult": -0.15,
                "camimc": 1.778e-15, "cpmimc": 0.03e-15},
    "lh":      {"res_high_po_var": -0.125, "res_xhigh_po_var_mult": -0.15,
                "camimc": 2.231e-15, "cpmimc": 0.35e-15},
    "hl":      {"res_high_po_var": 0.125,  "res_xhigh_po_var_mult": 0.15,
                "camimc": 1.778e-15, "cpmimc": 0.03e-15},
    "hh":      {"res_high_po_var": 0.125,  "res_xhigh_po_var_mult": 0.15,
                "camimc": 2.231e-15, "cpmimc": 0.35e-15},
}


# ─────────────────────────────────────────────────────────────────────────────
# Resistors.
# ─────────────────────────────────────────────────────────────────────────────

#: The only widths the `_0pXX` families exist at. Passing any other `w` is
#: SILENTLY IGNORED (trap 2) — the width lives in the subckt name.
FIXED_WIDTH_UM: tuple[float, ...] = (0.35, 0.69, 1.41, 2.85, 5.73)


def fixed_width_subckt(family: str, w_um: float) -> str:
    """`res_high_po` + 0.69 um -> `sky130_fd_pr__res_high_po_0p69`.

    Raises on a width the PDK does not provide, because the alternative is
    ngspice silently handing back a different device (trap 2).
    """
    if w_um not in FIXED_WIDTH_UM:
        raise ValueError(
            f"{family} exists only at w = {FIXED_WIDTH_UM} um, not {w_um}. "
            f"Passing an unlisted w is SILENTLY IGNORED by the subckt — you "
            f"would get the width in its NAME, not the one you asked for."
        )
    return f"sky130_fd_pr__{family}_{str(w_um).replace('.', 'p')}"


@dataclass(frozen=True)
class PolyResistorModel:
    """The generic (`w`- and `l`-free) poly resistor, as an invertible model.

    Transcribed from the PDK subckt and **validated against simulation to
    0.006 %** — the residual is temperature, which `resistance()` includes
    because `tnom` is 30 C and the project simulates at 27 C by default.

    The head term is what makes this family non-obvious. A poly resistor is
    not `rsheet * l / w`: it carries a fixed contact/head resistance that does
    not scale with length, so short resistors are dominated by it. At
    `w = 1 um` the head is **299 ohm** before any body at all — which is why
    the low end of the `rs` bound (50 ohm) is unreachable at narrow widths and
    why `to_geometry` widens rather than shortens.
    """

    name: str
    rsheet_body: float          # ohm/square
    rsheet_head: float          # ohm/square, head segment
    head_l: float               # squares of head, fixed
    head_w_offset: float        # um added to weff for the head
    dw: float                   # um, body width offset
    dl: float                   # um, body length offset
    narrow_knee_um: float       # below this width an extra narrowing applies
    narrow_slope: float
    tc1_body: float
    tc2_body: float
    tc1_head: float
    tc2_head: float
    tnom_c: float = 30.0

    def weff(self, w_um: float) -> float:
        return (w_um + self.dw
                - self.narrow_slope * max(self.narrow_knee_um - w_um, 0.0))

    def leff(self, l_um: float) -> float:
        return l_um + self.dl

    def resistance(self, w_um: float, l_um: float, m: int = 1,
                   temp_c: float = 27.0, corner: str = "typical") -> float:
        """Nominal resistance, ohms. `m` is ngspice's native multiplier.

        NOT `mult` — see trap 1. `m` divides the result exactly.
        """
        if m < 1:
            raise ValueError(f"m must be >= 1, got {m}")
        we, le = self.weff(w_um), self.leff(l_um)
        if we <= 0:
            raise ValueError(f"w={w_um} um gives non-positive effective width")
        var = PASSIVE_CORNER_PARAMS[corner]["res_high_po_var"]
        dt = temp_c - self.tnom_c
        head = (self.rsheet_head * (1.0 + var) * self.head_l
                / (we + self.head_w_offset)
                * (1.0 + self.tc1_head * dt + self.tc2_head * dt * dt))
        body = (self.rsheet_body * (1.0 + var) * le / we
                * (1.0 + self.tc1_body * dt + self.tc2_body * dt * dt))
        return (head + body) / m

    def length_for(self, r_ohm: float, w_um: float, m: int = 1,
                   temp_c: float = 27.0, corner: str = "typical") -> float:
        """Invert `resistance` for `l`. Returns the raw (unquantised) length.

        Negative means the head alone already exceeds the target at this
        width — the caller must widen, not shorten.
        """
        we = self.weff(w_um)
        var = PASSIVE_CORNER_PARAMS[corner]["res_high_po_var"]
        dt = temp_c - self.tnom_c
        head = (self.rsheet_head * (1.0 + var) * self.head_l
                / (we + self.head_w_offset)
                * (1.0 + self.tc1_head * dt + self.tc2_head * dt * dt))
        body_target = r_ohm * m - head
        k = (self.rsheet_body * (1.0 + var) / we
             * (1.0 + self.tc1_body * dt + self.tc2_body * dt * dt))
        return body_target / k - self.dl

    def parasitic_to_bulk_f(self, w_um: float, l_um: float, m: int = 1,
                            corner: str = "typical") -> float:
        """TOTAL capacitance from the resistor body to substrate, farads.

        The PDK models this as `sky130_fd_pr__model__parasitic__res_po`, which
        puts HALF on each terminal. So the amount landing on the node the
        resistor drives is `parasitic_to_bulk_f() / 2` — that is the number
        that adds to `cl` when this device is used as `RL` (4g).

        The constants are the passive corner's own `crpf_precision` (areal,
        F/m^2) and `crpfsw_precision_1_1` (perimeter, F/m); the 2.08 um is the
        head enclosure the PDK expression carries.
        """
        area_f_per_um2 = _CRPF[corner]["area"]
        per_f_per_um = _CRPF[corner]["perim"]
        l_tot = l_um + 2 * 2.08
        return m * (l_tot * w_um * area_f_per_um2
                    + 2.0 * (l_tot + w_um) * per_f_per_um)


#: `crpf_precision` (F/um^2 after the PDK's 1e-12 scaling) and
#: `crpfsw_precision_1_1` (F/um after its 1e-6 scaling), per passive corner.
#: Read from `r+c/*.spice`; the test re-reads and compares.
_CRPF: dict[str, dict[str, float]] = {
    "typical": {"area": 1.06e-16, "perim": 5.04e-17},
    "ll":      {"area": 8.84e-17, "perim": 4.67e-17},
    "lh":      {"area": 1.39e-16, "perim": 5.59e-17},
    "hl":      {"area": 8.84e-17, "perim": 4.67e-17},
    "hh":      {"area": 1.39e-16, "perim": 5.59e-17},
}


#: The high-sheet poly resistor. Constants transcribed from
#: `sky130_fd_pr__res_high_po.model.spice`; `tc1_body`/`tc2_body` come from
#: `tc1rpolybody`/`tc2rpolybody` in `sky130_fd_pr__model__r+c.model.spice`.
#:
#: NOTE THE SIGNS: the body TC is **+514 ppm/C** and the head TC is
#: **-430 ppm/C**. They oppose, so a short resistor (head-dominated) drifts the
#: OTHER WAY from a long one. That is not a detail — 4e asks whether the
#: resistor's temperature coefficient cancels against `gm`'s in
#: `k = 1 + (gm + gmbs)*Rs/2`, and the answer depends on which term dominates,
#: i.e. on the geometry `to_geometry` picks.
RES_HIGH_PO = PolyResistorModel(
    name="sky130_fd_pr__res_high_po",
    rsheet_body=317.3885, rsheet_head=345.8312,
    head_l=1.0, head_w_offset=0.1558,
    dw=-0.001, dl=0.247,
    narrow_knee_um=0.69, narrow_slope=0.0672,
    tc1_body=0.514e-3, tc2_body=0.122e-5,
    tc1_head=-4.3e-4, tc2_head=12e-6,
)


# ─────────────────────────────────────────────────────────────────────────────
# Capacitors.
# ─────────────────────────────────────────────────────────────────────────────

#: SKY130's MIM capacitors, and they ARE available in this metal stack — the
#: first thing 4a said to confirm before doing anything else.
#:
#:   cap_mim_m3_1   capm  between m3 and m4    2.00 fF/um^2
#:   cap_mim_m3_2   cap2m between m4 and m5    2.00 fF/um^2
#:
#: Both measure **1.8197 pF at w = l = 30 um**, identical to every printed
#: digit; they differ only in series resistance (7.697 vs 7.696 ohm), because
#: the plates are different metals.
#:
#: **THE MIM SUBCKT HAS ONLY TWO TERMINALS.** There is no bulk node, so the
#: model carries NO bottom-plate capacitance to substrate at all. That is a
#: modelling absence, not a physical one — see `PASSIVES.md` 4g, where it is
#: derived the G51 way rather than quietly assumed to be zero.
#:
#: It is also **perfectly linear**: `c1 c0 a 'czero' tc1 = 0 tc2 = 0`, with no
#: voltage argument anywhere. So a MIM carries no HD3 penalty and no
#: temperature drift, which is what makes it the safe choice for `cs` — the
#: device that sits floating between the two sources at ~+0.34 V with the full
#: differential swing across it.
MIM_FAMILIES: tuple[str, ...] = ("sky130_fd_pr__cap_mim_m3_1",
                                 "sky130_fd_pr__cap_mim_m3_2")

#: Plate offset: the drawn `w` is shifted by `m3_dw + tol_m3` before the area
#: is computed. `m3_dw = -0.026 um` was extracted by inverting the PDK
#: expression against the 30x30 measurement (29.974 um effective for 30.0
#: drawn); `tol_m3` is read per corner out of `r+c/*.spice`.
#:
#: **THE MIM CAPACITANCE DEPENDS ON BOTH LETTERS OF THE PASSIVE CORNER, AND
#: THE SECOND ONE IS NOT THE CAPACITOR.** `camimc` follows the capacitor
#: letter as expected, but `tol_m3` — the metal width tolerance, which sets
#: the PLATE SIZE — follows the RESISTOR letter, because it is the same metal
#: layer the resistor's interconnect is drawn in. Wider metal means lower
#: resistance and a bigger plate, so `res_low` raises the capacitance:
#:
#:      corner  tol_m3     effect on C
#:      ll      +0.0455    res_low  -> bigger plate
#:      lh      +0.065     res_low  -> bigger plate
#:      hh      -0.0455    res_high -> smaller plate
#:      hl      -0.065     res_high -> smaller plate
#:
#: and note the magnitudes are NOT symmetric: the mixed corners (hl, lh) carry
#: 0.065 um against the matched ones' 0.0455. Treating "cap_high" as a single
#: capacitance would be wrong by ~0.7 % between `hh` and `lh`, which both
#: nominally have cap_high. Verified against simulation at four corners to
#: better than 1e-4 relative.
MIM_DW_UM: dict[str, float] = {
    "typical": -0.026,
    "ll":      -0.026 + 0.0455,
    "lh":      -0.026 + 0.065,
    "hh":      -0.026 - 0.0455,
    "hl":      -0.026 - 0.065,
}


def mim_capacitance_f(w_um: float, l_um: float, m: int = 1,
                      corner: str = "typical") -> float:
    """MIM capacitance, farads. `m` is ngspice's native multiplier (trap 1).

    Validated against simulation at 1.8197 pF for w = l = 30 um, TT.
    """
    if m < 1:
        raise ValueError(f"m must be >= 1, got {m}")
    p = PASSIVE_CORNER_PARAMS[corner]
    dw = MIM_DW_UM[corner]
    wc, lc = w_um + dw, l_um + dw
    if wc <= 0 or lc <= 0:
        raise ValueError(f"w={w_um} l={l_um} um gives a non-positive plate")
    return m * (p["camimc"] * wc * lc + p["cpmimc"] * 2.0 * (wc + lc))


def mim_side_for(c_f: float, m: int = 1, corner: str = "typical") -> float:
    """Side of the SQUARE MIM plate realising `c_f`, in um.

    Square because a square minimises perimeter for a given area, which
    minimises both the perimeter term's share and the routing around it.
    Solves `camimc*x^2 + 4*cpmimc*x = c_f/m` for the effective side, then adds
    the plate offset back to get the DRAWN dimension.
    """
    p = PASSIVE_CORNER_PARAMS[corner]
    a, b, c = p["camimc"], 4.0 * p["cpmimc"], -c_f / m
    disc = b * b - 4 * a * c
    if disc < 0:
        raise ValueError(f"no real plate size for {c_f} F")
    return (-b + math.sqrt(disc)) / (2 * a) - MIM_DW_UM[corner]


# ─────────────────────────────────────────────────────────────────────────────
# Discretisation: continuous (rs, cs, rl) -> realisable device geometry.
#
# THIS IS THE FUNCTION THAT MAKES THE DELIVERABLE A SCHEMATIC. The RL policy
# proposes real numbers; silicon has a layout grid, a minimum width, and a head
# resistance that does not scale with length. `to_geometry` is where those meet,
# and its round-trip error is a first-class result, not a rounding footnote.
# ─────────────────────────────────────────────────────────────────────────────

#: SKY130's layout grid. Every drawn dimension is an integer multiple of it.
GRID_UM: float = 0.005

#: Drawn-width limits for the generic poly resistor. The floor is the PDK's
#: minimum drawn poly-resistor width; the ceiling is a DECLARED design choice,
#: not a PDK limit — beyond ~10 um a resistor is mostly area for no benefit and
#: `m=` parallel instances are the better lever.
RES_W_MIN_UM: float = 0.35
RES_W_MAX_UM: float = 10.0

#: Drawn-length limits. Floor is a declared design rule; ceiling is where the
#: lumped-R assumption starts to be worth re-checking at 2.5 GHz (4g).
RES_L_MIN_UM: float = 0.50
RES_L_MAX_UM: float = 50.0

#: Widths `to_geometry` will try, narrowest first. Narrow is preferred because
#: it costs the least area and the least bottom-plate parasitic (4g) — but the
#: head resistance sets a FLOOR that rises as width falls, so wide entries have
#: to exist for the low end of the `rs` and `rl` bounds.
_WIDTH_LADDER: tuple[float, ...] = (0.35, 0.69, 1.0, 1.41, 2.0, 2.85, 4.0,
                                    5.73, 8.0, 10.0)


def _snap(x_um: float) -> float:
    """Round a drawn dimension onto the layout grid."""
    return round(x_um / GRID_UM) * GRID_UM


@dataclass(frozen=True)
class ResistorGeometry:
    """A realisable poly resistor: what to draw, and what it will measure."""

    w_um: float
    l_um: float
    m: int
    subckt: str
    r_target_ohm: float
    r_actual_ohm: float

    @property
    def rel_error(self) -> float:
        return (self.r_actual_ohm - self.r_target_ohm) / self.r_target_ohm

    @property
    def area_um2(self) -> float:
        """Drawn body area x multiplier. Head enclosure is added in 4h's
        budget, not here — this is the device, not the cell."""
        return self.w_um * self.l_um * self.m

    def parasitic_to_bulk_f(self, corner: str = "typical") -> float:
        return RES_HIGH_PO.parasitic_to_bulk_f(self.w_um, self.l_um, self.m,
                                               corner)


@dataclass(frozen=True)
class CapacitorGeometry:
    """A realisable MIM capacitor."""

    w_um: float
    l_um: float
    m: int
    subckt: str
    c_target_f: float
    c_actual_f: float

    @property
    def rel_error(self) -> float:
        return (self.c_actual_f - self.c_target_f) / self.c_target_f

    @property
    def area_um2(self) -> float:
        return self.w_um * self.l_um * self.m


def resistor_geometry(r_ohm: float, model: PolyResistorModel = RES_HIGH_PO,
                      temp_c: float = 27.0, corner: str = "typical",
                      m_max: int = 8) -> ResistorGeometry:
    """Nearest realisable geometry for `r_ohm`, on the generic poly family.

    Search order is deliberate and is the whole content of the function:

    1. **Narrowest width first.** Area and bottom-plate parasitic both scale
       with width, and the parasitic lands on `cl` when this is `RL` (4g).
    2. **`m = 1` first.** A multiplier buys reach at the low end but costs a
       factor of `m` in area and parasitic.
    3. **Reject anything off-grid or out of the length window**, rather than
       clamping. Clamping is how a geometry that cannot be drawn ends up in a
       netlist that simulates fine.

    Raises if nothing in the ladder reaches `r_ohm` — which is information
    (the target is below the head-resistance floor at every legal width), not
    a failure to be papered over with a clamp.
    """
    if r_ohm <= 0:
        raise ValueError(f"r_ohm must be positive, got {r_ohm}")
    best: Optional[ResistorGeometry] = None
    for m in range(1, m_max + 1):
        for w in _WIDTH_LADDER:
            if not (RES_W_MIN_UM <= w <= RES_W_MAX_UM):
                continue
            l_raw = model.length_for(r_ohm, w, m=m, temp_c=temp_c,
                                     corner=corner)
            if l_raw < RES_L_MIN_UM or l_raw > RES_L_MAX_UM:
                continue
            l = _snap(l_raw)
            if l < RES_L_MIN_UM:
                continue
            actual = model.resistance(w, l, m=m, temp_c=temp_c, corner=corner)
            cand = ResistorGeometry(w_um=w, l_um=l, m=m, subckt=model.name,
                                    r_target_ohm=r_ohm, r_actual_ohm=actual)
            if best is None or abs(cand.rel_error) < abs(best.rel_error):
                best = cand
        if best is not None and abs(best.rel_error) < 1e-4:
            break          # already at the grid floor; wider m only costs area
    if best is None:
        raise ValueError(
            f"no realisable {model.name} geometry for {r_ohm:.4g} ohm within "
            f"w {RES_W_MIN_UM}-{RES_W_MAX_UM} um, l {RES_L_MIN_UM}-"
            f"{RES_L_MAX_UM} um, m <= {m_max}. At w = {RES_W_MAX_UM} um the "
            f"head alone is "
            f"{model.resistance(RES_W_MAX_UM, RES_L_MIN_UM, temp_c=temp_c, corner=corner):.1f} "
            f"ohm — the target may be below the head-resistance floor."
        )
    return best


def capacitor_geometry(c_f: float, family: str = MIM_FAMILIES[0],
                       corner: str = "typical",
                       m_max: int = 4) -> CapacitorGeometry:
    """Nearest realisable MIM geometry for `c_f`, as a square plate.

    `m` is used only when a single plate would exceed `_MIM_SIDE_MAX_UM`; a
    very large square is worse for routing and for plate resistance than
    several smaller ones in parallel.
    """
    if c_f <= 0:
        raise ValueError(f"c_f must be positive, got {c_f}")
    if family not in MIM_FAMILIES:
        raise ValueError(f"unknown MIM family {family!r}")
    for m in range(1, m_max + 1):
        side = mim_side_for(c_f, m=m, corner=corner)
        if side <= _MIM_SIDE_MAX_UM:
            s = _snap(side)
            actual = mim_capacitance_f(s, s, m=m, corner=corner)
            return CapacitorGeometry(w_um=s, l_um=s, m=m, subckt=family,
                                     c_target_f=c_f, c_actual_f=actual)
    raise ValueError(
        f"{c_f:.4g} F needs a plate larger than {_MIM_SIDE_MAX_UM} um a side "
        f"even at m = {m_max}"
    )


#: Largest square MIM plate `capacitor_geometry` will draw before splitting
#: into parallel units. A DECLARED choice, not a PDK limit.
_MIM_SIDE_MAX_UM: float = 100.0


@dataclass(frozen=True)
class PassiveGeometry:
    """The three passives of the S2 CTLE, as drawable devices."""

    rs: ResistorGeometry
    cs: CapacitorGeometry
    rl: ResistorGeometry

    def worst_rel_error(self) -> float:
        return max(abs(self.rs.rel_error), abs(self.cs.rel_error),
                   abs(self.rl.rel_error))

    @property
    def area_um2(self) -> float:
        """Drawn passive area: Rs + Cs + **two** RL, um^2.

        **The factor of two on `rl` is the topology, not a fudge.** S2's CTLE
        is differential and `_PASSIVES_REAL` instantiates `Xrlp` and `Xrln` —
        one load resistor per side — while `Rs` and `Cs` sit BETWEEN the two
        sources and there is one of each. A budget that counted `rl` once
        would understate the load by a whole resistor.

        DEVICE area only. Head enclosure, routing and the guard ring are
        `PASSIVES.md` §4.5's 4h budget and are not folded in here, so this is a
        LOWER BOUND on the S7 number. The MOSFETs are excluded too: this is
        the passive area, which `PASSIVES.md` measured as the term that
        dominates S7.
        """
        return (self.rs.area_um2 + self.cs.area_um2 + 2.0 * self.rl.area_um2)

    @property
    def area_mm2(self) -> float:
        """`area_um2` in mm^2 — the unit S7 is written in (< 0.05 mm^2)."""
        return self.area_um2 * 1e-6

    def f_zero_hz(self) -> float:
        """`1 / (2*pi*Rs*Cs)` at the REALISED values."""
        return 1.0 / (2 * math.pi * self.rs.r_actual_ohm * self.cs.c_actual_f)

    def f_zero_target_hz(self) -> float:
        return 1.0 / (2 * math.pi * self.rs.r_target_ohm * self.cs.c_target_f)

    def f_zero_error_octaves(self) -> float:
        """Quantisation error in `f_z`, in OCTAVES.

        Octaves because that is the unit S3's window is measured in and the
        unit every other result in this project uses. A percentage on a
        component is not comparable to a spec window; an octave is.
        """
        return math.log2(self.f_zero_hz() / self.f_zero_target_hz())


def to_geometry(rs: float, cs: float, rl: float, corner: str = "typical",
                temp_c: float = 27.0) -> PassiveGeometry:
    """Map a continuous `(rs, cs, rl)` triple onto realisable devices.

    This is the function that turns the framework's output into a schematic,
    so it is a deliverable in its own right rather than a helper.
    `test_passives.py` round-trips it over the whole box and asserts the error
    stays inside a stated bound.
    """
    return PassiveGeometry(
        rs=resistor_geometry(rs, temp_c=temp_c, corner=corner),
        cs=capacitor_geometry(cs, corner=corner),
        rl=resistor_geometry(rl, temp_c=temp_c, corner=corner),
    )


__all__: Sequence[str] = (
    "PASSIVE_CORNERS", "PASSIVE_CORNER_PARAMS", "lib_section",
    "FIXED_WIDTH_UM", "fixed_width_subckt",
    "PolyResistorModel", "RES_HIGH_PO",
    "MIM_FAMILIES", "MIM_DW_UM", "mim_capacitance_f", "mim_side_for",
    "GRID_UM", "RES_W_MIN_UM", "RES_W_MAX_UM", "RES_L_MIN_UM", "RES_L_MAX_UM",
    "ResistorGeometry", "CapacitorGeometry", "PassiveGeometry",
    "resistor_geometry", "capacitor_geometry", "to_geometry",
)
