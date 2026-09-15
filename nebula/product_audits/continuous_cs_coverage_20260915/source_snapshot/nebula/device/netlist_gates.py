"""
device/netlist_gates.py — refuse to emit a parameter SKY130 silently ignores.

WHY THIS IS A MODULE AND NOT A COMMENT
--------------------------------------
Session 15 measured two ways to write a number into a SKY130 netlist, have
ngspice accept it, exit 0, and simulate a **different device from the one you
asked for**:

* **G56 — `mult` and `mf` do nothing.** Every SKY130 resistor and MIM subckt
  declares one of them, and it reads exactly like a parallel-device
  multiplier. In every one of them the parameter appears ONLY inside mismatch
  terms, all multiplied by `MC_MM_SWITCH`, which the corner files set to 0.
  Measured on `res_high_po` w=1 l=1.78: `mult=1` and `mult=4` both give
  **942.90 ohm**, a silent 4x error. `m=4` gives 235.72 ohm, exactly a
  quarter, and agrees with four explicitly instantiated parallel devices to
  every printed digit.

* **G57 — `w` is inert on the fixed-width resistor families.**
  `res_high_po_0p69` with `w=0.69`, `w=2.85` and `w=99` all return
  **2893.64 ohm**, identical to every digit, and `w=99` raises nothing. The
  width lives in the SUBCKT NAME. The device that really is 2.85 um wide reads
  **718.61 ohm** — so asking the wrong subckt for a width is a **4.03x error,
  silently**.

Both were found by measurement, not by reading. Neither produces a warning,
an error, or a non-zero exit code. A comment saying "don't do this" is not a
gate (CLAUDEwa.md §8 rule 10); a function that raises is.

WHY IT GATES THE TEXT AND NOT THE CALL SITE
--------------------------------------------
The check runs on the **assembled netlist**, immediately before it is written
to disk, rather than on the arguments of whatever built it. That is
deliberate: an argument check protects one constructor, and this project has
already been bitten by two netlists describing "the same" circuit differently
(G32). Gating the text means no path through the device layer can emit an
inert write — including a path written later by someone who has not read this
file.

An RL policy makes that stronger still. The agent is an adversarial search
over the parameter box, and a region where a written parameter is ignored is a
region where the reward stops depending on part of the action. That is free
reward for a design that is not the design being scored.
"""

from __future__ import annotations

import re
from typing import Sequence

#: `res_high_po_0p69`, `res_xhigh_po_2p85`, ... — the families whose width is
#: encoded in the NAME and whose `w` parameter is inert (G57).
#:
#: Matched by SHAPE (`_<digit>p<digit>` suffix) rather than by an enumerated
#: list, so a width the PDK adds later is caught without an edit here.
_FIXED_WIDTH_SUBCKT = re.compile(
    r"\bsky130_fd_pr__res_x?high_po_\d+p\d+\b", re.I)

#: A `w=<value>` written anywhere on an instance line.
_W_ASSIGN = re.compile(r"\bw\s*=", re.I)

#: `mult=<value>` / `mf=<value>`. Captures the value so `mult=1` — which the
#: existing nfet instances write, harmlessly — is allowed through while
#: anything else raises. Allowing `1` is not a loophole: it is the identity,
#: and banning it outright would require editing netlists whose numbers are
#: published, for no change in behaviour.
_MULT_ASSIGN = re.compile(r"\b(mult|mf)\s*=\s*([-+0-9.eE]+)", re.I)


class InertParameterWrite(ValueError):
    """A netlist writes a parameter SKY130 accepts and then ignores.

    Raised, never warned. The whole failure mode is that ngspice does not
    complain, so anything short of an exception reproduces the bug.
    """


def _instance_lines(text: str) -> list[tuple[int, str]]:
    """Instance lines only: no comments, no dot-cards, no `.control` body.

    `.model` cards and `.param` lines legitimately carry `mult` as a formal
    parameter — that is where the mismatch expressions live — so scanning them
    would fire on the PDK's own definitions rather than on our writes.
    """
    out: list[tuple[int, str]] = []
    in_control = False
    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        low = line.lower()
        if low.startswith(".control"):
            in_control = True
            continue
        if low.startswith(".endc"):
            in_control = False
            continue
        if in_control or not line or line.startswith(("*", ".", "+")):
            continue
        out.append((i, line))
    return out


def check_inert_writes(text: str) -> list[str]:
    """Return one message per inert write. Empty list means clean."""
    problems: list[str] = []
    for lineno, line in _instance_lines(text):
        m = _FIXED_WIDTH_SUBCKT.search(line)
        if m and _W_ASSIGN.search(line):
            problems.append(
                f"line {lineno}: `w=` written to {m.group(0)}, a FIXED-WIDTH "
                f"family whose width is encoded in the subckt name. The "
                f"parameter is silently ignored (G57) and asking the wrong "
                f"subckt for a width is a 4.03x error that raises nothing. "
                f"Use the generic `sky130_fd_pr__res_high_po`, where `w` is "
                f"honoured, or select the named width. Line: {line!r}"
            )
        for mm in _MULT_ASSIGN.finditer(line):
            name, value = mm.group(1), mm.group(2)
            try:
                as_float = float(value)
            except ValueError:
                as_float = float("nan")
            if as_float != 1.0:
                problems.append(
                    f"line {lineno}: `{name}={value}` is a MISMATCH parameter, "
                    f"not a device multiplier. It appears only inside terms "
                    f"multiplied by MC_MM_SWITCH=0, so it does nothing at all "
                    f"(G56) — `mult=4` measured 942.90 ohm against `mult=1`'s "
                    f"942.90 ohm. Use ngspice's native `m=`, which divides "
                    f"exactly. Line: {line!r}"
                )
    return problems


def assert_no_inert_writes(text: str) -> None:
    """Raise `InertParameterWrite` if the netlist writes an ignored parameter.

    Call this on the ASSEMBLED text, immediately before writing it out.
    """
    problems = check_inert_writes(text)
    if problems:
        raise InertParameterWrite(
            f"{len(problems)} parameter write(s) SKY130 accepts and then "
            f"IGNORES. ngspice would simulate a different device and exit 0:\n"
            + "\n".join(f"  - {p}" for p in problems)
        )


__all__: Sequence[str] = (
    "InertParameterWrite", "check_inert_writes", "assert_no_inert_writes",
)
