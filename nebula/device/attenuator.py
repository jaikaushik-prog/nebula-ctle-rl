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
removed.** So the requirement is **6 dB of range**, and `ATTEN_MAX_X` below is
the measured 1.98x rather than a round number.

THE TOPOLOGY
--------------
A series-shunt divider per side, with a **binary-weighted 3-bit shunt bank**:

    inx --[ RSER ]--+-- inp (gate)
                    |
              +-----+-----+-----+
              |     |     |     |
            [2R0] [ R0 ] [R0/2]        <- drawn poly, switched to cm
              |     |     |
            [sw]  [sw]  [sw]           <- nfet, gate at VDD or 0

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

#: **Measured, not chosen.** The worst-case over-drive over all 2 117 scorable
#: (code, corner) points at the shortest channel in the family, from
#: `experiments/channel_probe_run.jsonl` (entry 72).
ATTEN_MAX_X: float = 1.98

#: Series arm. Small enough that the divider's pole stays far above Nyquist —
#: the worst-case `RSER || RSH` is 131.6 ohm, which is 12.1 GHz into a 100 fF
#: gate, against a 2.5 GHz Nyquist.
RSER_OHM: float = 150.0

#: 3 bits = 8 settings. The requirement is 6 dB and the channel family has seven
#: members, so eight codes cover it with one to spare.
N_BITS: int = 3
N_CODES: int = 2 ** N_BITS

#: Unit shunt conductance, sized so the TOP code reaches `ATTEN_MAX_X` exactly.
G0_S: float = (ATTEN_MAX_X - 1.0) / ((N_CODES - 1) * RSER_OHM)

#: The switch, and its **measured** on-resistance — a real SKY130 `nfet_01v8` at
#: `vgs = 1.8 V`, dV/dI over 5-45 mV of `vds`
#: (`experiments/tunable_trade_results.json`). Subtracted from each drawn leg so
#: the realised conductance is the designed one.
SWITCH_W_UM: float = 40.0
SWITCH_L_UM: float = 0.15
SWITCH_RON_OHM: float = 16.502243688504894


def leg_resistance_ohm(bit: int) -> float:
    """Drawn resistance of shunt leg `bit`, with the switch's Ron removed."""
    if not 0 <= bit < N_BITS:
        raise ValueError(f"bit {bit} outside 0..{N_BITS - 1}")
    return 1.0 / ((2 ** bit) * G0_S) - SWITCH_RON_OHM


def attenuation(code: int) -> float:
    """Voltage ratio `A` for `code`. `A = 1` at code 0, falling as code rises."""
    if not 0 <= code < N_CODES:
        raise ValueError(f"code {code} outside 0..{N_CODES - 1}")
    return 1.0 / (1.0 + code * RSER_OHM * G0_S)


def attenuation_db(code: int) -> float:
    return -20.0 * math.log10(attenuation(code))


def code_for(required_x: float) -> int:
    """The smallest code whose attenuation clears `required_x`. **Rounds UP.**

    Rounding up rather than to nearest: falling one step short leaves the stage
    compressed, which is a hard rejection, while overshooting costs a little eye
    and a little noise. The two errors are not symmetric.
    """
    need_db = 20.0 * math.log10(max(float(required_x), 1.0))
    for n in range(N_CODES):
        if attenuation_db(n) >= need_db - 1e-9:
            return n
    return N_CODES - 1


def attenuator_block(code: int, node_p: str = "inx", node_n: str = "iny",
                     gate_p: str = "inp", gate_n: str = "inn") -> str:
    """The SPICE text for one code. **All legs emitted, enabled ones switched on.**"""
    if not 0 <= code < N_CODES:
        raise ValueError(f"code {code} outside 0..{N_CODES - 1}")
    ser = resistor_geometry(RSER_OHM, RES_HIGH_PO)
    lines = [
        f"* Input attenuator (D11), code {code} of {N_CODES - 1}: "
        f"A = {attenuation(code):.4f} ({attenuation_db(code):.2f} dB).",
        "* Sized to the worst-case over-drive entry 72 measured at the shortest",
        "* channel (1.98x). Entry 73 measured why a load trim cannot do this:",
        "* RL scales the signal and the headroom together.",
        f"Xatt_sp {node_p} {gate_p} 0 {ser.subckt} "
        f"w={ser.w_um:g} l={ser.l_um:g}",
        f"Xatt_sn {node_n} {gate_n} 0 {ser.subckt} "
        f"w={ser.w_um:g} l={ser.l_um:g}",
    ]
    for bit in range(N_BITS):
        on = bool(code & (1 << bit))
        g = "vdd" if on else "0"
        geo = resistor_geometry(leg_resistance_ohm(bit), RES_HIGH_PO)
        for side, gate in (("p", gate_p), ("n", gate_n)):
            mid = f"att_{side}{bit}"
            lines.append(
                f"Xatt_r{side}{bit} {gate} {mid} 0 {geo.subckt} "
                f"w={geo.w_um:g} l={geo.l_um:g}")
            # Emitted whether or not it is on, so a disabled leg still presents
            # its switch capacitance to the input node.
            lines.append(
                f"Xatt_sw{side}{bit} {mid} {g} cm 0 sky130_fd_pr__nfet_01v8 "
                f"W={SWITCH_W_UM:g} L={SWITCH_L_UM:g} nf=1")
    return "\n".join(lines)


def netlist_fields(code: Optional[int]) -> dict:
    """What `assemble_netlist` needs. `None` -> the historical deck, unchanged."""
    if code is None:
        return {"in_p": "inp", "in_n": "inn", "atten_block": ""}
    return {"in_p": "inx", "in_n": "iny",
            "atten_block": attenuator_block(int(code))}


#: The measured requirement per channel, and what each code delivers. Recorded
#: here so the sizing can be checked against the artifact it came from without
#: re-deriving it. Losses in dB at Nyquist; `x` is the worst-case over-drive.
REQUIREMENT_BY_LOSS_DB: dict = {
    3.0: 1.98, 4.5: 1.79, 6.0: 1.62, 7.5: 1.45,
    9.0: 1.28, 10.5: 1.13, 12.0: 1.00,
}

__all__ = ("ATTEN_MAX_X", "RSER_OHM", "N_BITS", "N_CODES", "G0_S",
           "SWITCH_RON_OHM", "leg_resistance_ohm", "attenuation",
           "attenuation_db", "code_for", "attenuator_block", "netlist_fields",
           "REQUIREMENT_BY_LOSS_DB")
