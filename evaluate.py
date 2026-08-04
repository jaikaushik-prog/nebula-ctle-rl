"""
circuits.py
-----------
Parameter-space definitions for the two 28nm ADC front-end circuits used in
"Balancing Speed and Accuracy for Robust Analog-Mixed Signal Circuit Design
using Closed-Loop Reinforcement Learning with Ensemble Neural Network
Surrogates" (Guo, Fu, Bhanushali, Zeng, Banerjee, Sanyal — ISCAS 2026).

The paper states 26 tunable parameters for the standalone bootstrapped
sampling switch and 38 for the input-buffer + bootstrapped-switch design,
and names the following as the dominant device-level / system-level knobs
(Sec. IV, Table I):

    device-level: samp_nmos, nmos1, nmos2, nmos3, nmos4, nmos5,
                   inv_nmos, inv_pmos, pmos1, pmos2
    system-level: Fs, CB, source_res, duty_cycle, CS, fbin

The paper does not publish the *complete* parameter list (this is normal for
an ISCAS 4-page paper). To reach the stated dimensionality (26 / 38) while
keeping every named parameter from Table I, we extend the device-level set
with per-transistor {W, L, nf (finger count)} sizing triples and per-block
bias/timing parameters, which is the standard analog sizing convention (and
matches Neeraj's own gm/ID-based sizing methodology). Anywhere we had to
invent a parameter to hit the stated count, it is tagged `derived=True` in
the metadata below so it is never confused with something stated verbatim
in the paper. Swap this file's bounds for your actual PDK corners when you
wire in real Spectre netlists.
"""

from dataclasses import dataclass, field
from typing import List, Dict
import numpy as np


@dataclass
class Param:
    name: str
    lo: float           # physical lower bound
    hi: float            # physical upper bound
    unit: str
    kind: str            # 'W' (width, um), 'L' (length, um), 'nf' (int), 'sys' (system-level)
    derived: bool = False  # True if not explicitly named in the paper (see module docstring)


def _tri(base: str, w_range, l_range, nf_range, derived=False) -> List[Param]:
    """Expand one named device (from Table I) into W/L/nf sizing triple."""
    return [
        Param(f"{base}_W", *w_range, "um", "W", derived),
        Param(f"{base}_L", *l_range, "um", "L", derived),
        Param(f"{base}_nf", *nf_range, "fingers", "nf", derived),
    ]


# ---------------------------------------------------------------------------
# Circuit 1: standalone bootstrapped sampling switch (26 params, paper Sec. V.A)
# ---------------------------------------------------------------------------
def bootstrapped_switch_params() -> List[Param]:
    p: List[Param] = []
    # Named device-level drivers from Table I / Sec. IV findings
    p += _tri("samp_nmos", (0.5, 20.0), (0.03, 0.5), (1, 32))     # sampling switch: top SNDR driver
    p += _tri("nmos1", (0.2, 10.0), (0.03, 0.3), (1, 16))
    p += _tri("nmos2", (0.2, 10.0), (0.03, 0.3), (1, 16))
    p += _tri("nmos3", (0.2, 10.0), (0.03, 0.3), (1, 16))
    p += _tri("inv_nmos", (0.2, 8.0), (0.03, 0.3), (1, 16))
    p += _tri("inv_pmos", (0.4, 16.0), (0.03, 0.3), (1, 16))
    p += _tri("pmos1", (0.4, 16.0), (0.03, 0.3), (1, 16))
    # Named system-level knobs
    p.append(Param("Fs", 100e6, 2.4e9, "Hz", "sys"))
    p.append(Param("CB", 50e-15, 2e-12, "F", "sys"))       # bootstrap capacitor
    p.append(Param("source_res", 1.0, 500.0, "ohm", "sys"))
    p.append(Param("duty_cycle", 0.3, 0.7, "-", "sys"))
    p.append(Param("CS", 50e-15, 1e-12, "F", "sys"))       # sampling cap, set by kT/C in practice
    assert len(p) == 26, f"expected 26 params, got {len(p)}"
    return p


# ---------------------------------------------------------------------------
# Circuit 2: input buffer + bootstrapped sampling switch (38 params, Sec. V.A)
# ---------------------------------------------------------------------------
def buffer_switch_params() -> List[Param]:
    p: List[Param] = []
    # Named device-level drivers from Table I / Sec. IV findings (10 named devices)
    p += _tri("samp_nmos", (0.5, 20.0), (0.03, 0.5), (1, 32))
    p += _tri("nmos1", (0.2, 10.0), (0.03, 0.3), (1, 16))
    p += _tri("nmos2", (0.2, 10.0), (0.03, 0.3), (1, 16))
    p += _tri("nmos3", (0.2, 10.0), (0.03, 0.3), (1, 16))
    p += _tri("nmos4", (0.2, 10.0), (0.03, 0.3), (1, 16))     # input-buffer specific
    p += _tri("nmos5", (0.2, 10.0), (0.03, 0.3), (1, 16))     # input-buffer specific
    p += _tri("inv_nmos", (0.2, 8.0), (0.03, 0.3), (1, 16))
    p += _tri("inv_pmos", (0.4, 16.0), (0.03, 0.3), (1, 16))
    p += _tri("pmos1", (0.4, 16.0), (0.03, 0.3), (1, 16))
    p += _tri("pmos2", (0.4, 16.0), (0.03, 0.3), (1, 16))     # input-buffer specific
    # Named system-level knobs
    p.append(Param("Fs", 100e6, 2.4e9, "Hz", "sys"))
    p.append(Param("CB", 50e-15, 2e-12, "F", "sys"))
    p.append(Param("source_res", 1.0, 500.0, "ohm", "sys"))
    p.append(Param("duty_cycle", 0.3, 0.7, "-", "sys"))
    p.append(Param("CS", 50e-15, 1e-12, "F", "sys"))
    p.append(Param("fbin", 1e5, 1e9, "Hz", "sys"))            # test-tone bin, buffer+switch only
    p.append(Param("Ibias_buf", 10e-6, 2e-3, "A", "sys", derived=True))
    p.append(Param("Rload_buf", 100.0, 5000.0, "ohm", "sys", derived=True))
    assert len(p) == 38, f"expected 38 params, got {len(p)}"
    return p


CIRCUITS: Dict[str, List[Param]] = {
    "bootstrapped_switch": bootstrapped_switch_params(),
    "buffer_switch": buffer_switch_params(),
}


def bounds_arrays(circuit: str):
    ps = CIRCUITS[circuit]
    lo = np.array([p.lo for p in ps], dtype=np.float64)
    hi = np.array([p.hi for p in ps], dtype=np.float64)
    return lo, hi


def denormalize(a_norm: np.ndarray, circuit: str) -> np.ndarray:
    """Map policy action a in [0,1]^d to physical units."""
    lo, hi = bounds_arrays(circuit)
    return lo + np.clip(a_norm, 0.0, 1.0) * (hi - lo)


def normalize(a_phys: np.ndarray, circuit: str) -> np.ndarray:
    lo, hi = bounds_arrays(circuit)
    return np.clip((a_phys - lo) / (hi - lo), 0.0, 1.0)


def param_names(circuit: str) -> List[str]:
    return [p.name for p in CIRCUITS[circuit]]


def dim(circuit: str) -> int:
    return len(CIRCUITS[circuit])


if __name__ == "__main__":
    for c in CIRCUITS:
        print(c, dim(c), "params")
