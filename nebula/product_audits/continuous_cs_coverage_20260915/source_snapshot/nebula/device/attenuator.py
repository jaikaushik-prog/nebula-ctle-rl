"""
device/attenuator.py — **the input attenuator: the block entry 73 showed the
CTLE is missing, sized to the spec entry 72 measured.**

WHY IT IS AT THE INPUT AND NOT ON THE LOAD
--------------------------------------------
Entry 72 found the stage saturating on every channel shorter than ~9 dB. Entry
73 tried the cheap fix — trimming the load `rl`, which is already an axis — and
measured **why it cannot work**:

    demand      = (signal arriving at the input pair)  x  A_v
    capability  = (the pair's LINEAR INPUT RANGE)      x  A_v

`RL` multiplies both, so the ratio that decides compression is **invariant in
`rl`** — measured 1.48x -> 1.46x across a 3.5x load sweep. Only something that
changes the signal *before* the pair can move it. That is this block, and it is
why a receiver's VGA sits ahead of its equaliser rather than around it.

THE SPEC, AND IT IS MEASURED RATHER THAN CHOSEN
-------------------------------------------------
`channel_probe_run.jsonl` carries a demand and a capability for every rejected
(code, corner, channel) point. The worst-case ratio per channel is:

    channel loss dB    3.0   4.5   6.0   7.5   9.0  10.5  12.0
    worst over-drive  1.98  1.79  1.62  1.45  1.28  1.13  1.00
    attenuation dB    5.94  5.06  4.17  3.20  2.16  1.05  0.00

which is close to linear: **~0.66 dB of attenuation per dB of channel loss
removed.** So the original D11 requirement was **6 dB of range**, derived as
1.98x rather than chosen as a round number.

Entry 86 then measured the adjacent 7.3 dB candidate over the complete
8-attenuator x 64-CTLE x 45-corner table. It closed all 16 requests at every
tested channel loss with zero hard device failures. Owner decision D16 adopts
that verified 2.3173946499684783x range as the production default. The measured
1.98x requirement remains in `REQUIREMENT_BY_LOSS_DB`; it is evidence for the
minimum need, not the adopted guard margin.

THE TOPOLOGY
--------------
A series-shunt divider per side, with a **binary-weighted 3-bit shunt bank**:

    inx --[ RSER ]--+-- inp (gate)
                    |
              +-----+-----+-----+
              |     |     |     |
            [2R0] [ R0 ] [R0/2]        <- drawn poly, switched to cm
              |     |     |
            [sw]  [sw]  [sw]           <- pfet, gate at 0 or VDD

Three resistors and three switches give eight settings instead of eight of
each. `A = 1 / (1 + n * RSER * G0)` for code `n`, so the codes are not evenly
spaced in dB — which is fine, because the requirement is met by **rounding up**
and the table below records the margin at each channel.

**Every leg is emitted at every code**, with its switch gate tied to VDD or to
0. Omitting the disabled legs would have been simpler and would have quietly
removed their switch capacitance from the input node — flattering the design by
exactly the parasitic a real part has to live with.

DC BIAS IS PRESERVED EXACTLY
------------------------------
The shunt legs return to `cm`, and the gate draws no DC current, so the gate
sits at `VCM` whatever the code — the same operating point the un-attenuated
deck has. The divider is therefore AC-only in effect, with no re-biasing.

WHAT `.noise` AND `.dc` DO WITH IT, FOR FREE
----------------------------------------------
Both analyses reference **`Vid`, which is upstream of the divider**. So:

* `inoise_total` is referred to the pre-attenuator input and therefore already
  carries the attenuation penalty **and** the divider's own thermal noise. S5 is
  scored honestly with no special-casing.
* the `.dc` swing sweep sees the attenuated drive, so the compression check's
  capability rises by exactly `1/A`.

Neither needed a change. That is the argument for putting the block here rather
than modelling an attenuation factor somewhere in Python.

STATED LIMITATION
-------------------
The deck drives the input from an **ideal VCVS**, so this divider sees zero
source impedance and does not load anything. A real receiver terminates its
input (100 ohm differential) and a resistive divider interacts with that
termination. **The termination interaction is out of scope at schematic level**
and this sizing is a bound, not a finished front end.
"""

from __future__ import annotations

import math
from typing import Optional

from nebula.device.passives import RES_HIGH_PO, resistor_geometry

#: **Verified, then owner-adopted (D16).** Entry 86 measured this exact range
#: across 23,040 real-PMOS bank/PVT points. It is `10 ** (7.3 / 20)`; the
#: literal below is the exact value stored in that result artifact.
ATTEN_MAX_X: float = 2.3173946499684783

#: Series arm. Entry 86's complete AC measurements include the adopted divider
#: geometry and verify the response against the 2.5 GHz Nyquist requirements.
RSER_OHM: float = 150.0

#: 3 bits = 8 settings. The requirement is 6 dB and the channel family has seven
#: members, so eight codes cover it with one to spare.
N_BITS: int = 3
N_CODES: int = 2 ** N_BITS

#: Unit shunt conductance, sized so the TOP code reaches `ATTEN_MAX_X` exactly.
G0_S: float = (ATTEN_MAX_X - 1.0) / ((N_CODES - 1) * RSER_OHM)

#: The switch, and its **measured** on-resistance — a real SKY130 `pfet_01v8`
#: at |Vgs| = 1.5 V, source at the 1.5 V input common mode, TT/27 C. Entry 75
#: measured Ron*W flat over W=40..400 um (`pmos_switch_results.json`).
SWITCH_W_UM: float = 40.0
SWITCH_L_UM: float = 0.15
SWITCH_RON_W_OHM_UM: float = 4086.824988354164
SWITCH_RON_OHM: float = SWITCH_RON_W_OHM_UM / SWITCH_W_UM


def _unit_conductance_s(atten_max_x: Optional[float] = None) -> float:
    """Resolve an explicit diagnostic/historical range or D16's default."""
    if atten_max_x is None:
        return G0_S
    value = float(atten_max_x)
    if not math.isfinite(value) or value <= 1.0:
        raise ValueError("atten_max_x must be finite and greater than 1")
    return (value - 1.0) / ((N_CODES - 1) * RSER_OHM)


def leg_resistance_ohm(bit: int,
                       atten_max_x: Optional[float] = None) -> float:
    """Drawn resistance of shunt leg `bit`, with the switch's Ron removed."""
    if not 0 <= bit < N_BITS:
        raise ValueError(f"bit {bit} outside 0..{N_BITS - 1}")
    return (1.0 / _unit_conductance_s(atten_max_x)
            - SWITCH_RON_OHM) / (2 ** bit)


def attenuation(code: int, atten_max_x: Optional[float] = None) -> float:
    """Voltage ratio `A` for `code`. `A = 1` at code 0, falling as code rises."""
    if not 0 <= code < N_CODES:
        raise ValueError(f"code {code} outside 0..{N_CODES - 1}")
    return 1.0 / (1.0 + code * RSER_OHM
                  * _unit_conductance_s(atten_max_x))


def attenuation_db(code: int, atten_max_x: Optional[float] = None) -> float:
    return -20.0 * math.log10(attenuation(code, atten_max_x=atten_max_x))


def code_for(required_x: float,
             atten_max_x: Optional[float] = None) -> int:
    """The smallest code whose attenuation clears `required_x`. **Rounds UP.**

    Rounding up rather than to nearest: falling one step short leaves the stage
    compressed, which is a hard rejection, while overshooting costs a little eye
    and a little noise. The two errors are not symmetric.
    """
    need_db = 20.0 * math.log10(max(float(required_x), 1.0))
    for n in range(N_CODES):
        if attenuation_db(n, atten_max_x=atten_max_x) >= need_db - 1e-9:
            return n
    return N_CODES - 1


def attenuator_block(code: int, node_p: str = "inx", node_n: str = "iny",
                     gate_p: str = "inp", gate_n: str = "inn",
                     switched: bool = True,
                     atten_max_x: Optional[float] = None) -> str:
    """The SPICE text for one code. **All legs emitted, enabled ones switched on.**

    `switched=False` wires the ENABLED legs straight to `cm` and omits the
    disabled ones and every switch. That is the divider with an ideal switch --
    a fixed pad at this code's attenuation.

    `switched=False` remains entry 74's ideal-switch measurement control. The
    delivered switched path uses entry 75's PMOS: gate low is ON, gate at VDD
    is OFF, and the n-well bulk is tied to VDD.
    """
    if not 0 <= code < N_CODES:
        raise ValueError(f"code {code} outside 0..{N_CODES - 1}")
    # **The multiplier is NOT optional.** `resistor_geometry` returns `m > 1`
    # whenever the target needs parallel instances, and dropping it emits a
    # resistor `m` times too large. That is exactly what happened on the first
    # build: a 153.1 ohm shunt asked for `m = 2`, was emitted as one 306.2 ohm
    # instance, and the divider realised 3.47 dB where 5.93 dB was designed --
    # which read as "the sizing model is wrong" until the geometry was printed.
    # `_m_suffix` is the ONE definition of this (rule 9); it emits ` m=`, never
    # `mult=` (G56), and `netlist_gates` enforces that on the assembled text.
    # Imported inside the function because `sky130_runner` imports this module.
    from nebula.device.sky130_runner import _m_suffix
    ser = resistor_geometry(RSER_OHM, RES_HIGH_PO)
    lines = [
        f"* Input attenuator (D16), code {code} of {N_CODES - 1}: "
        f"A = {attenuation(code, atten_max_x=atten_max_x):.4f} "
        f"({attenuation_db(code, atten_max_x=atten_max_x):.2f} dB).",
    ]
    if atten_max_x is None:
        # Production default: the exact range verified by Entry 86 and adopted
        # by owner decision D16.
        lines += [
            "* 7.3 dB range verified over 23,040 bank/PVT points by Entry 86.",
            "* D11's measured 1.98x minimum requirement remains reproducible",
            "* through the explicit atten_max_x argument.",
        ]
    else:
        lines += [
            f"* Explicit diagnostic/historical range: {float(atten_max_x):.6g}x.",
            f"* Production D16 default: {ATTEN_MAX_X:.6g}x maximum.",
        ]
    lines += [
        f"Xatt_sp {node_p} {gate_p} 0 {ser.subckt} "
        f"w={ser.w_um:g} l={ser.l_um:g}{_m_suffix(ser.m)}",
        f"Xatt_sn {node_n} {gate_n} 0 {ser.subckt} "
        f"w={ser.w_um:g} l={ser.l_um:g}{_m_suffix(ser.m)}",
    ]
    for bit in range(N_BITS):
        on = bool(code & (1 << bit))
        g = "0" if on else "vdd"
        if not switched and not on:
            continue                       # ideal switch: an off leg is absent
        geo = resistor_geometry(
            leg_resistance_ohm(bit, atten_max_x=atten_max_x), RES_HIGH_PO)
        for side, gate in (("p", gate_p), ("n", gate_n)):
            mid = f"att_{side}{bit}" if switched else "cm"
            lines.append(
                f"Xatt_r{side}{bit} {gate} {mid} 0 {geo.subckt} "
                f"w={geo.w_um:g} l={geo.l_um:g}{_m_suffix(geo.m)}")
            if not switched:
                continue
            # Emitted whether or not it is on, so a disabled leg still presents
            # its switch capacitance to the input node.
            lines.append(
                f"Xatt_sw{side}{bit} {mid} {g} cm vdd "
                f"sky130_fd_pr__pfet_01v8 W={SWITCH_W_UM * (2 ** bit):g} "
                f"L={SWITCH_L_UM:g} nf={2 ** bit}")
    return "\n".join(lines)


def netlist_fields(code: Optional[int], switched: bool = True,
                   atten_max_x: Optional[float] = None) -> dict:
    """What `assemble_netlist` needs. `None` -> the historical deck, unchanged."""
    if code is None:
        return {"in_p": "inp", "in_n": "inn", "atten_block": ""}
    return {"in_p": "inx", "in_n": "iny",
            "atten_block": attenuator_block(
                int(code), switched=switched, atten_max_x=atten_max_x)}


#: The measured requirement per channel, and what each code delivers. Recorded
#: here so the sizing can be checked against the artifact it came from without
#: re-deriving it. Losses in dB at Nyquist; `x` is the worst-case over-drive.
REQUIREMENT_BY_LOSS_DB: dict = {
    3.0: 1.98, 4.5: 1.79, 6.0: 1.62, 7.5: 1.45,
    9.0: 1.28, 10.5: 1.13, 12.0: 1.00,
}

__all__ = ("ATTEN_MAX_X", "RSER_OHM", "N_BITS", "N_CODES", "G0_S",
           "SWITCH_RON_W_OHM_UM", "SWITCH_RON_OHM", "leg_resistance_ohm", "attenuation",
           "attenuation_db", "code_for", "attenuator_block", "netlist_fields",
           "REQUIREMENT_BY_LOSS_DB")
