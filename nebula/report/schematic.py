"""
report/schematic.py — **the sized schematic, drawn FROM THE NETLIST that was
simulated.**

    from nebula.report.schematic import draw_schematic
    draw_schematic(netlist_text, "out/design_schematic.png")

WHY THIS EXISTS
----------------
`CLAUDEwa.md` §2 quotes the brief: the framework must output *"the final
schematic and resulting specs"*. `design.py --out` has always written
`design.cir` -- the assembled deck -- and a SPICE deck is a schematic only to
someone who reads SPICE. A judge asked to see the schematic should see one.

THE ONE DESIGN RULE: IT IS PARSED, NEVER RECOMPUTED
-----------------------------------------------------
The obvious implementation takes the `Sizing` object and draws its numbers.
**That is G32** -- the gotcha this repository has hit more than once: a model
card that differs between the netlist a human reads and the runner that
produced the numbers. A drawing is the most dangerous place for it, because a
picture is believed instantly and checked never.

So this module takes **the netlist text itself** -- the exact string
`run_point(keep_netlist=True)` returned and `design.cir` contains -- parses the
`.param` values out of it, and draws those. There is no second computation to
disagree with. If the deck says `RL=607.17`, the picture says 607.17 or the
picture does not render.

AND IT ASSERTS THE TOPOLOGY IT DRAWS
--------------------------------------
Parsing values is not enough: a drawing of the wrong circuit annotated with the
right numbers is worse than no drawing. `_check_topology` requires every
element this picture claims -- the pair, both loads, the degeneration `Rs`/`Cs`
between the two sources, both tail devices, the mirror reference, both load
capacitors -- to be present in the deck with the connectivity drawn here.
**If the netlist changes shape, this raises** rather than emitting a confident
picture of a circuit that no longer exists.

WHAT IS DRAWN AND WHAT IS NOT
-------------------------------
Drawn: the CTLE itself. Not drawn: the testbench sources (`Vid`, `Einp`,
`Einn`) that generate the differential stimulus -- they are measurement
apparatus, not the delivered circuit -- and the `.control` block. The input
common mode they establish IS shown, as a label on the gates, because it is a
sized quantity (`vcm_in`) the design chose.

The 1-tap DFE is shown as a **behavioural block**, clearly marked as such,
because that is exactly what it is in this project. Entry 39's ablation applies
only to its older circuit, not automatically to a newly exported design.
No transistor-level DFE was ever sized. Drawing it as if it were
sized silicon would be a fabrication; omitting it would hide a mandated part of
S2's topology. A labelled block with the ablation quoted beside it is the only
honest option.
"""

from __future__ import annotations

import re
from typing import Mapping, Optional  # noqa: F401

# ─────────────────────────────────────────────────────────────────────────────
# Parsing. Values come from the deck; nothing here recomputes a sizing.
# ─────────────────────────────────────────────────────────────────────────────

_PARAM = re.compile(r"^\s*\.param\s+(.*)$", re.IGNORECASE | re.MULTILINE)
_ASSIGN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([-+0-9.eE]+)")

#: Every element this picture draws, with the connectivity it assumes. A deck
#: that does not match is a different circuit and must not be drawn as this one.
_REQUIRED: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("XM1", ("outp", "inp", "s1")),
    ("XM2", ("outn", "inn", "s2")),
    ("Xrlp", ("vdd", "outp")),
    ("Xrln", ("vdd", "outn")),
    ("Xrs", ("s1", "s2")),
    ("Xcs", ("s1", "s2")),
    ("XMR", ("nbias", "nbias")),
    ("XMT1", ("s1", "nbias")),
    ("XMT2", ("s2", "nbias")),
    ("Iref", ("vdd", "nbias")),
    ("Cbyp", ("nbias", "0")),
    ("CLp", ("outp", "0")),
    ("CLn", ("outn", "0")),
)

#: `.param` names the drawing needs. Missing any of them is a parse failure,
#: never a default -- rule 4, a missing number raises.
_NEEDED: tuple[str, ...] = ("W", "L", "NF", "RL", "RS", "CS", "IT", "CL",
                            "VDD", "VCM", "WT", "LT", "NFT", "WREF", "IREF",
                            "CBYP")


def params_of(netlist: str) -> dict[str, float]:
    """Every `.param` assignment in the deck, as floats.

    Raises on a missing name rather than substituting one: a schematic with an
    invented value on it is the exact failure this module exists to prevent.
    """
    out: dict[str, float] = {}
    for line in _PARAM.findall(netlist):
        for name, val in _ASSIGN.findall(line):
            out[name.upper()] = float(val)
    missing = [k for k in _NEEDED if k not in out]
    if missing:
        raise ValueError(
            f"the netlist carries no {missing} -- this drawing annotates values "
            f"parsed from the deck and does not compute any of its own, so it "
            f"cannot render a deck that does not state them")
    return out


def _check_topology(netlist: str) -> None:
    """The drawn circuit must be the netlisted circuit (G32)."""
    lines = [ln.strip() for ln in netlist.splitlines()
             if ln.strip() and not ln.strip().startswith(("*", ".", "+"))]
    by_name = {ln.split()[0].upper(): ln.split()[1:] for ln in lines if ln.split()}
    problems = []
    for name, nodes in _REQUIRED:
        got = by_name.get(name.upper())
        if got is None:
            problems.append(f"{name} is absent")
            continue
        low = [g.lower() for g in got]
        for n in nodes:
            if n.lower() not in low:
                problems.append(f"{name} does not connect to {n} (got {low[:4]})")
    if problems:
        raise ValueError(
            "the netlist is not the topology this schematic draws, so drawing "
            "it would be a picture of a circuit that does not exist: "
            + "; ".join(problems))


# ─────────────────────────────────────────────────────────────────────────────
# Engineering notation. One definition, used for every label.
# ─────────────────────────────────────────────────────────────────────────────

_PREFIX = ((1e-15, "f"), (1e-12, "p"), (1e-9, "n"), (1e-6, "u"),
           (1e-3, "m"), (1.0, ""), (1e3, "k"), (1e6, "M"))


def eng(value: float, unit: str = "", sig: int = 3) -> str:
    """`607.173` -> `607 Ohm`; `6.039e-13` -> `604 fF`. Rounds, never truncates."""
    v = float(value)
    if v == 0.0:
        return f"0 {unit}".strip()
    mag, pre = _PREFIX[0]
    for m, p in _PREFIX:
        if abs(v) >= m:
            mag, pre = m, p
    scaled = v / mag
    txt = f"{scaled:.{max(0, sig - len(str(int(abs(scaled)))))}f}"
    # **Only strip zeros that are after a decimal point.** The first version
    # called `.rstrip("0")` unconditionally and turned `610 uA` into `61 uA`
    # -- a factor of ten, on a label, in a picture nobody re-derives.
    if "." in txt:
        txt = txt.rstrip("0").rstrip(".")
    return f"{txt} {pre}{unit}".strip()


# ─────────────────────────────────────────────────────────────────────────────
# The drawing. matplotlib, to match `figures_v2.py` — same ink, same accent,
# same 200-dpi PNG pipeline the report already embeds.
# ─────────────────────────────────────────────────────────────────────────────

INK = "#16202b"
GREY = "#5d6b7a"
ACCENT = "#0072B2"
WARM = "#D55E00"

#: Drawing coordinates, named because every wire refers to them. A schematic
#: whose geometry is scattered through its code cannot be adjusted.
VDD_Y, GND_Y = 8.10, 0.55
LX, RX = 4.30, 7.70
MID = (LX + RX) / 2
OUT_Y, PAIR_Y, SRC_Y = 6.90, 5.60, 4.55
RS_Y, CS_Y = 4.05, 3.30
TAIL_Y, NB_Y = 2.15, 1.15
REF_X = 11.00
PANEL_X = 12.30


def _wire(ax, *pts, lw: float = 1.7):
    ax.plot([q[0] for q in pts], [q[1] for q in pts], color=INK, lw=lw,
            solid_capstyle="round", solid_joinstyle="miter", zorder=2)


def _node(ax, x: float, y: float):
    ax.plot([x], [y], marker="o", ms=4.4, color=INK, zorder=4)


def _rail_with_hops(ax, y: float, x0: float, x1: float, crossings, gap=0.11):
    """A horizontal rail that BREAKS where it crosses an unrelated wire.

    A current mirror's bias node has to reach both sides of the pair, so it
    crosses the tail source wires no matter how the picture is arranged. The
    standard reading is "junction dot = connected, break = crossing", and this
    draws the break rather than leaving a plain intersection that a reader has
    to infer from the absence of a dot.
    """
    edges = [x0]
    for c in sorted(crossings):
        if x0 < c < x1:
            edges += [c - gap, c + gap]
    edges.append(x1)
    for a, b in zip(edges[0::2], edges[1::2]):
        if b > a:
            _wire(ax, (a, y), (b, y))


def _mos(ax, gate_x: float, y: float, *, flip: bool = False, h: float = 1.30):
    """An NMOS whose gate lead ends at `(gate_x, y)`.

    Returns `(rail_x, drain_y, source_y)`. The caller draws every wire that
    reaches those, so no connection in this picture is implied by a symbol's
    extent — which is how a schematic ends up showing a node the netlist does
    not have.
    """
    s = -1.0 if flip else 1.0
    gate, chan, rail = gate_x + s * 0.26, gate_x + s * 0.46, gate_x + s * 0.92
    top, bot = y + h / 2, y - h / 2
    _wire(ax, (gate_x, y), (gate, y))
    _wire(ax, (gate, top - 0.10), (gate, bot + 0.10))
    _wire(ax, (chan, top), (chan, bot))
    _wire(ax, (chan, top - 0.17), (rail, top - 0.17))
    _wire(ax, (chan, bot + 0.17), (rail, bot + 0.17))
    # bulk tie: the deck ties it to 0, and a reader will ask
    _wire(ax, (chan, y), (chan + s * 0.20, y))
    ax.plot([chan + s * 0.07], [y], marker=(3, 0, 90 if s > 0 else -90),
            ms=5.5, color=INK, zorder=4)
    return rail, top - 0.17, bot + 0.17


def _res_v(ax, x: float, y: float, h: float = 0.86, w: float = 0.19):
    from matplotlib.patches import Rectangle
    ax.add_patch(Rectangle((x - w, y - h / 2), 2 * w, h, facecolor="white",
                           edgecolor=INK, lw=1.7, zorder=3))


def _res_h(ax, x: float, y: float, w: float = 0.86, h: float = 0.19):
    from matplotlib.patches import Rectangle
    ax.add_patch(Rectangle((x - w / 2, y - h), w, 2 * h, facecolor="white",
                           edgecolor=INK, lw=1.7, zorder=3))


def _cap_v(ax, x: float, y: float, gap: float = 0.16, half: float = 0.28):
    _wire(ax, (x - half, y + gap / 2), (x + half, y + gap / 2))
    _wire(ax, (x - half, y - gap / 2), (x + half, y - gap / 2))


def _cap_h(ax, x: float, y: float, gap: float = 0.16, half: float = 0.28):
    _wire(ax, (x - gap / 2, y - half), (x - gap / 2, y + half))
    _wire(ax, (x + gap / 2, y - half), (x + gap / 2, y + half))


def _gnd(ax, x: float, y: float):
    _wire(ax, (x, y), (x, y - 0.13))
    for i, w in enumerate((0.24, 0.15, 0.07)):
        _wire(ax, (x - w, y - 0.13 - 0.09 * i), (x + w, y - 0.13 - 0.09 * i))


def draw_schematic(netlist: str, out_path, *,
                   title: str = "CTLE - sized schematic",
                   subtitle=None, extra=None, warning=None):
    """Render `netlist` to a PNG at `out_path`. Returns the path.

    Every annotated value is parsed from `netlist`; this function computes no
    sizing of its own, and `_check_topology` has already refused any deck whose
    shape is not the one drawn.

    **`warning` is not decoration.** A sizing run that FAILS still has a
    netlist, so this function will happily draw a circuit whose input pair is
    in triode -- and the first version did, under a panel headed "Delivered
    design", which is the exact failure this module's docstring warns about: a
    picture is believed on sight. When the caller knows the run did not
    deliver, it passes the verdict here and the drawing says so in the title,
    in a banner and in the panel heading. `design.py` passes it whenever
    `nominal.ok` is false.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, FancyBboxPatch

    _check_topology(netlist)
    p = params_of(netlist)

    fig, ax = plt.subplots(figsize=(14.6, 7.8))
    ax.set_xlim(0.05, 16.30)
    ax.set_ylim(-0.10, 9.70)
    ax.set_aspect("equal")
    ax.axis("off")

    # ── rails ───────────────────────────────────────────────────────────────
    _wire(ax, (2.60, VDD_Y), (REF_X, VDD_Y), lw=2.3)
    ax.text(2.60, VDD_Y + 0.18, f"VDD = {eng(p['VDD'], 'V')}", fontsize=9.5,
            color=INK, fontweight="bold")
    _wire(ax, (2.90, GND_Y), (REF_X, GND_Y), lw=2.3)
    _gnd(ax, MID, GND_Y)

    # ── loads ───────────────────────────────────────────────────────────────
    for x, side in ((LX, -1), (RX, +1)):
        _wire(ax, (x, VDD_Y), (x, 7.66))
        _res_v(ax, x, 7.23)
        _wire(ax, (x, 6.80), (x, OUT_Y))
        _node(ax, x, OUT_Y)
        ha = "left" if side > 0 else "right"
        ax.text(x + side * 0.30, 7.30, "RL", fontsize=9, color=INK, ha=ha,
                fontweight="bold")
        ax.text(x + side * 0.30, 7.04, eng(p["RL"], "Ohm"), fontsize=8.6,
                color=ACCENT, ha=ha, fontweight="bold")

    # ── load capacitance. Dropped ABOVE the gate leads so the two never meet ─
    for x, side in ((LX, -1), (RX, +1)):
        cx = x + side * 1.30
        _wire(ax, (x, OUT_Y), (cx, OUT_Y), (cx, 6.60))
        _cap_v(ax, cx, 6.48)
        _wire(ax, (cx, 6.36), (cx, 6.20))
        _gnd(ax, cx, 6.20)
        ha2 = "right" if side < 0 else "left"
        ax.text(cx + side * 0.36, 6.52, f"CL {eng(p['CL'], 'F')}", fontsize=8.4,
                color=INK, ha=ha2, fontweight="bold")
        ax.text(cx + side * 0.36, 6.30, "design load", fontsize=7.4,
                color=GREY, ha=ha2)

    # ── the input pair ──────────────────────────────────────────────────────
    for x, side, flip in ((LX, -1, False), (RX, +1, True)):
        gate_x = x + side * 0.92
        _mos(ax, gate_x, PAIR_Y, flip=flip)
        _wire(ax, (x, OUT_Y), (x, PAIR_Y + 0.48))
        _wire(ax, (x, PAIR_Y - 0.48), (x, SRC_Y))
        _node(ax, x, SRC_Y)
        lead = gate_x + side * 0.86
        _wire(ax, (gate_x, PAIR_Y), (lead, PAIR_Y))
        ha = "right" if side < 0 else "left"
        ax.text(lead + side * 0.10, PAIR_Y + 0.12, "inp" if side < 0 else "inn",
                fontsize=9.5, color=INK, ha=ha, fontweight="bold")
        ax.text(lead + side * 0.10, PAIR_Y - 0.32,
                f"VCM {eng(p['VCM'], 'V')}", fontsize=7.6, color=GREY, ha=ha)

    # Labels go in the empty box BETWEEN the two devices — the one region of a
    # differential schematic that carries no wires.
    ax.text(MID, PAIR_Y + 0.26, "M1 / M2", fontsize=9.2, color=ACCENT,
            ha="center", fontweight="bold")
    ax.text(MID, PAIR_Y - 0.02, f"W {p['W']:.2f} um   L {p['L']:.3f} um",
            fontsize=8.2, color=ACCENT, ha="center")
    ax.text(MID, PAIR_Y - 0.28, f"nf = {int(p['NF'])}", fontsize=8.2,
            color=ACCENT, ha="center")

    ax.text(LX + 0.13, OUT_Y + 0.14, "outp", fontsize=8, color=GREY,
            style="italic")
    ax.text(RX - 0.13, OUT_Y + 0.14, "outn", fontsize=8, color=GREY,
            style="italic", ha="right")
    ax.text(LX + 0.13, SRC_Y - 0.32, "s1", fontsize=8, color=GREY,
            style="italic")
    ax.text(RX - 0.13, SRC_Y - 0.32, "s2", fontsize=8, color=GREY,
            style="italic", ha="right")

    # ── degeneration: Rs and Cs, both between s1 and s2 ─────────────────────
    _wire(ax, (LX, SRC_Y), (LX, RS_Y), (MID - 0.43, RS_Y))
    _res_h(ax, MID, RS_Y)
    _wire(ax, (MID + 0.43, RS_Y), (RX, RS_Y), (RX, SRC_Y))
    ax.text(MID, RS_Y + 0.30, f"Rs   {eng(p['RS'], 'Ohm')}", fontsize=9,
            color=ACCENT, ha="center", fontweight="bold")

    _wire(ax, (LX, SRC_Y), (LX, CS_Y), (MID - 0.08, CS_Y))
    _cap_h(ax, MID, CS_Y)
    _wire(ax, (MID + 0.08, CS_Y), (RX, CS_Y), (RX, SRC_Y))
    ax.text(MID, CS_Y + 0.26, f"Cs   {eng(p['CS'], 'F')}", fontsize=9,
            color=ACCENT, ha="center", fontweight="bold")
    ax.text(MID, RS_Y + 0.54, "source degeneration (S2)", fontsize=7.6,
            color=GREY, ha="center")

    # ── tail current mirror ─────────────────────────────────────────────────
    for x, side, flip, gx2 in ((LX, -1, False, 2.90), (RX, +1, True, 9.20)):
        gate_x = x + side * 0.92
        _mos(ax, gate_x, TAIL_Y, flip=flip)
        _wire(ax, (x, SRC_Y), (x, TAIL_Y + 0.48))
        _wire(ax, (x, TAIL_Y - 0.48), (x, GND_Y))
        _wire(ax, (gate_x, TAIL_Y), (gx2, TAIL_Y), (gx2, NB_Y))
        _node(ax, gx2, NB_Y)

    ax.text(MID, TAIL_Y + 0.26, "MT1 / MT2", fontsize=9.2, color=ACCENT,
            ha="center", fontweight="bold")
    ax.text(MID, TAIL_Y - 0.02, f"W {p['WT']:.2f} um   L {p['LT']:.3f} um",
            fontsize=8.2, color=ACCENT, ha="center")
    ax.text(MID, TAIL_Y - 0.30, f"nf = {int(p['NFT'])}", fontsize=8.2,
            color=ACCENT, ha="center")
    ax.text(MID, TAIL_Y - 0.60, f"I_tail = {eng(p['IT'], 'A')} per side",
            fontsize=8.4, color=INK, ha="center", fontweight="bold")

    # ── the reference leg: Iref, the diode connection, the bypass ───────────
    _wire(ax, (REF_X, VDD_Y), (REF_X, 7.20))
    ax.add_patch(Circle((REF_X, 6.78), 0.42, facecolor="white", edgecolor=INK,
                        lw=1.7, zorder=3))
    _wire(ax, (REF_X, 7.02), (REF_X, 6.66))
    ax.plot([REF_X], [6.64], marker="v", ms=7, color=INK, zorder=4)
    _wire(ax, (REF_X, 6.36), (REF_X, TAIL_Y + 0.48))
    ax.text(REF_X + 0.18, 7.46, "Iref", fontsize=9, color=INK,
            fontweight="bold")
    ax.text(REF_X + 0.18, 7.22, eng(p["IREF"], "A"), fontsize=8.6,
            color=ACCENT, fontweight="bold")

    _mos(ax, REF_X - 0.92, TAIL_Y)
    _wire(ax, (REF_X, TAIL_Y - 0.48), (REF_X, GND_Y))
    _wire(ax, (REF_X - 0.92, TAIL_Y), (REF_X - 1.30, TAIL_Y),
          (REF_X - 1.30, NB_Y))
    _node(ax, REF_X - 1.30, NB_Y)
    # the diode connection, drawn as the wire it is rather than implied
    _node(ax, REF_X, TAIL_Y + 0.48)
    _wire(ax, (REF_X, TAIL_Y + 0.48), (REF_X + 0.52, TAIL_Y + 0.48),
          (REF_X + 0.52, NB_Y))
    _node(ax, REF_X + 0.52, NB_Y)
    ax.text(REF_X + 0.64, TAIL_Y + 0.36, "nbias", fontsize=8, color=GREY,
            style="italic")
    ax.text(REF_X + 0.30, TAIL_Y - 0.56, f"MR   W {p['WREF']:.2f} um",
            fontsize=7.8, color=GREY, ha="left")

    # The bias rail crosses the tail source wires; the breaks say so.
    _rail_with_hops(ax, NB_Y, 2.90, REF_X + 0.52, (LX, RX, REF_X))

    _wire(ax, (2.90, NB_Y), (2.90, 1.02))
    _cap_v(ax, 2.90, 0.90)
    _wire(ax, (2.90, 0.78), (2.90, GND_Y))
    _node(ax, 2.90, GND_Y)
    ax.text(2.48, 0.94, f"Cbyp {eng(p['CBYP'], 'F')}", fontsize=8.4, color=INK,
            ha="right", fontweight="bold")
    ax.text(2.48, 0.72, "bias-node bypass (G54)", fontsize=7.4, color=GREY,
            ha="right")

    # ── title ───────────────────────────────────────────────────────────────
    ax.text(0.05, 9.42,
            title + ("   -   NOT DELIVERED" if warning else ""),
            fontsize=14.5, color=(WARM if warning else INK),
            fontweight="bold")
    ax.text(0.05, 9.12,
            subtitle or "every value parsed from the simulated netlist - "
                        "nothing on this drawing is recomputed",
            fontsize=8.6, color=GREY)
    if warning:
        # Across the drawing, not tucked into the panel: this circuit does not
        # meet the request and nobody should have to read a table to find out.
        ax.text(0.05, 8.80, f"THIS DESIGN DID NOT PASS: {warning}",
                fontsize=9.6, color=WARM, fontweight="bold")

    # ── the values panel ────────────────────────────────────────────────────
    if extra:
        ax.text(PANEL_X, VDD_Y,
                "Design - NOT DELIVERED" if warning else "Delivered design",
                fontsize=10, color=(WARM if warning else INK),
                fontweight="bold")
        y = VDD_Y - 0.40
        for k, v in extra.items():
            ax.text(PANEL_X, y, str(k), fontsize=8.2, color=GREY)
            ax.text(16.25, y, str(v), fontsize=8.2, color=INK,
                    fontweight="bold", ha="right")
            y -= 0.33

    # ── the DFE, as the behavioural block it actually is ────────────────────
    # Drawn as a signal-path inset rather than wired into the transistor
    # schematic, because it is not sized silicon and putting it on the same
    # canvas as the devices would imply that it is.
    by = 3.30
    ax.add_patch(FancyBboxPatch((PANEL_X, by), 3.95, 1.55,
                                boxstyle="round,pad=0.03", facecolor="white",
                                edgecolor=GREY, lw=1.4, linestyle=(0, (5, 3)),
                                zorder=3))
    ax.text(PANEL_X + 0.18, by + 1.28, "Signal path", fontsize=9, color=INK,
            fontweight="bold", zorder=4)
    ax.text(PANEL_X + 0.18, by + 0.98,
            "outp / outn  ->  1-tap DFE  ->  slicer", fontsize=8.4,
            color=INK, zorder=4)
    ax.text(PANEL_X + 0.18, by + 0.70, "The DFE is BEHAVIOURAL, not sized.",
            fontsize=8, color=WARM, zorder=4, fontweight="bold")
    ax.text(PANEL_X + 0.18, by + 0.44,
            "Tap-sensitivity evidence is circuit-specific.", fontsize=7.6,
            color=GREY, zorder=4)
    ax.text(PANEL_X + 0.18, by + 0.24,
            "An open model eye does not implement", fontsize=7.6,
            color=GREY, zorder=4)
    ax.text(PANEL_X + 0.18, by + 0.04,
            "the DFE, slicer, clock or their area/power.", fontsize=7.6,
            color=GREY, zorder=4)

    from pathlib import Path as _P
    out = _P(out_path)
    if str(out.parent) not in ("", "."):
        out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out
