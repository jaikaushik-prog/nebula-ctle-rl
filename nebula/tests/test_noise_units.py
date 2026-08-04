"""
What units does ngspice's `inoise_total` / `onoise_total` carry?

This matters more than it looks. If the integrated noise were returned as V^2,
every input-referred noise figure in this project would need a square root,
and S5 (< 1.5 mV_rms) would flip from "comfortable" to "failing by ~16x".
The G1 reference point reports 0.275 mV; under the squared reading it would be
sqrt(2.75e-4) = 16.6 mV. That single convention decides whether S5 is free or
is the binding constraint.

It was settled by measurement, not by reading documentation: a circuit whose
noise has a closed-form answer.

    A resistor R at temperature T has thermal noise PSD 4kTR [V^2/Hz].
    Integrated over a bandwidth BW:   4kTR*BW  [V^2]
    RMS noise voltage:                sqrt(4kTR*BW)  [V]

ngspice returns **4.069e-06** for R = 1 kohm over 1 Hz - 1 MHz, and

    4kTR*BW      = 1.658e-11 V^2
    sqrt(4kTR*BW)= 4.071e-06 V     <-- matches, to 0.05%

So **inoise_total and onoise_total are already RMS VOLTS.** Do not square-root
them. Compare them to S5 directly.

This test exists so the answer cannot silently invert if ngspice changes
convention in a future version — the failure would otherwise show up as a
noise spec that suddenly looks 40x better or worse for no reason.
"""

from __future__ import annotations

import math
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

NGSPICE = Path(
    r"C:\Users\DELL\miniforge3\envs\nebula\Library\bin\ngspice_con.exe")

pytestmark = pytest.mark.skipif(not NGSPICE.exists(), reason="needs ngspice")

# Boltzmann constant and the temperature ngspice defaults to (27 C).
K_B = 1.380649e-23
T_KELVIN = 300.15

_R_OHM = 1000.0
_F_LO, _F_HI = 1.0, 1_000_000.0

_NETLIST = f"""* thermal noise of one resistor -- closed form, no device models
v1 in 0 dc 0 ac 1
r1 in out {_R_OHM}
rload out 0 1meg
.control
set noaskquit
noise v(out) v1 lin 100001 {_F_LO:g} {_F_HI:g}
print onoise_total
.endc
.end
"""


def _onoise_total() -> float:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "rn.cir"
        f.write_text(_NETLIST, encoding="ascii")
        proc = subprocess.run([str(NGSPICE), "-b", str(f)],
                              capture_output=True, text=True, timeout=300)
    out = proc.stdout + "\n" + proc.stderr
    m = re.search(r"^\s*onoise_total\s*=\s*(\S+)", out, re.M)
    assert m, f"ngspice did not report onoise_total:\n{out[-2000:]}"
    return float(m.group(1))


def test_integrated_noise_is_rms_volts_not_volts_squared():
    """The load point: `inoise_total` needs NO square root."""
    measured = _onoise_total()

    bandwidth = _F_HI - _F_LO
    v_squared = 4.0 * K_B * T_KELVIN * _R_OHM * bandwidth
    v_rms = math.sqrt(v_squared)

    # The resistor divider is 1k into 1meg, so essentially all of r1's noise
    # reaches the output; the 1meg load's own noise is negligible here.
    assert measured == pytest.approx(v_rms, rel=0.02), (
        f"ngspice onoise_total={measured:.6e} does not match the RMS "
        f"prediction {v_rms:.6e} V. If it matches {v_squared:.6e} V^2 "
        f"instead, ngspice has changed convention and EVERY noise figure in "
        f"this project needs a square root — S5 would move by ~40x."
    )

    # And state the alternative explicitly, so the test documents what it rules
    # out rather than only what it confirms.
    assert not (measured == pytest.approx(v_squared, rel=0.02)), \
        "onoise_total appears to be in V^2 — see this module's docstring"


def test_the_squared_reading_would_be_absurd():
    """Guard the reasoning, not just the number.

    If someone 'fixes' this by taking a square root, the 1 kohm resistor's
    noise becomes ~2 mV rms over a 1 MHz band, which is about 500x the
    textbook value. Encoding that here makes the error self-evident.
    """
    measured = _onoise_total()
    wrongly_rooted = math.sqrt(measured)
    assert wrongly_rooted > 100.0 * measured
    assert wrongly_rooted > 1e-3, (
        "sanity: the erroneous reading really is a milli-volt-scale number "
        "for a 1 kohm resistor, i.e. obviously wrong"
    )
