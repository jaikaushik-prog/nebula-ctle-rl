"""
link/dfe_ablation.py -- **how much of the eye is the ideal 1-tap DFE holding
up?**

WHY THIS EXISTS
----------------
The competition spec names the receiver as *"1-Stage CTLE w/ source
degeneration (variable Rs, Cs) + 1-Tap DFE"*, and the eye rows -- **> 0.4 UI and
> 100 mV** -- are measured *after* the DFE. This project models that DFE as an
**ideal tap cancelling the first post-cursor exactly**: `cursors.py` sets
`dfe_tap = taps[1] / h0` and `residual_abs_v` deliberately excludes `h1`. It is
flagged `NON_SILICON_PARAMS` and is not sized at transistor level.

**That is a fair thing to challenge, and this module answers the challenge
instead of enlarging the scope.** It re-derives the eye under four tap policies
from the *same* pulse response, so the question "what if the DFE were worse, or
absent?" gets a number rather than an argument. Pre-registered as entry 39.

    ideal        residual = pre + post                  the CURRENT behaviour
    none         residual = pre + |h1| + post           the DFE deleted
    misadapted   residual = pre + eps*|h1| + post       eps left uncancelled
    quantised    residual = pre + |h1 - q(h1)| + post   q = uniform, n bits

ONE DEFINITION OF AN EYE, NOT TWO
-----------------------------------
Height and width both come from `cursors_from_pulse` at each sampling phase --
**the same function `eye_opening_vs_phase` uses** -- with only the DFE term
changed. Nothing here re-implements a cursor, a pulse response or an opening.
That is CLAUDEwa.md section 8 rule 9, and this repo's third named failure mode:
a model card that differs between the netlist a human reads and the runner that
produced the numbers.

**`policy="ideal"` must reproduce `eye_opening_vs_phase` exactly.** It is not a
convenience path -- it is the control that licenses every other policy, and
`test_dfe_ablation.py` pins it.

NOTHING HERE IS A DFE DESIGN
------------------------------
No number this module produces describes a circuit that could be laid out. It
bounds an assumption; it does not implement a block.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from nebula.link.cursors import cursors_from_pulse

#: Entry 39's registered policy parameters.
MISADAPT_EPS: float = 0.20
QUANT_BITS: int = 4

POLICIES: tuple[str, ...] = ("ideal", "none", "misadapted", "quantised")


def _quantise(tap: float, bits: int = QUANT_BITS) -> float:
    """Uniform mid-tread quantisation of `h1/h0` on `[-0.5, +0.5]`.

    A real 1-tap DFE sets its tap from a finite-resolution DAC. The range is
    +-0.5 of the cursor because that is what the measured post-cursor
    distribution needs (median 0.070, max 0.185) with room to spare -- a range
    chosen to be generous to the ablation rather than flattering to it.
    """
    if bits < 1:
        raise ValueError(f"bits must be >= 1, got {bits}")
    step = 1.0 / (2 ** bits)              # full scale 1.0 spans [-0.5, +0.5]
    return float(np.clip(np.round(tap / step) * step, -0.5, 0.5))


def leftover_v(h1_v: float, h0_v: float, policy: str,
               eps: float = MISADAPT_EPS, bits: int = QUANT_BITS) -> float:
    """The post-cursor volts the DFE FAILS to cancel, under one policy.

    Split out so the arithmetic is testable on its own and so no policy can
    reach the eye without going through one place.
    """
    if policy == "ideal":
        return 0.0
    if policy == "none":
        return abs(h1_v)
    if policy == "misadapted":
        return abs(h1_v) * float(eps)
    if policy == "quantised":
        if h0_v == 0.0:
            return abs(h1_v)
        return abs(h1_v - _quantise(h1_v / h0_v, bits) * h0_v)
    raise ValueError(f"unknown policy {policy!r}; have {POLICIES}")


@dataclass(frozen=True)
class AblatedEye:
    """One design, one corner, one tap policy."""

    policy: str
    eye_h_v: float
    eye_w_ui: float
    best_phase_ui: float
    h0_v: float
    h1_v: float
    dfe_tap: float
    leftover_v: float
    n_phases_open: int


def eye_under_policy(pr, osr: int, cursor: int, policy: str = "ideal",
                     eps: float = MISADAPT_EPS,
                     bits: int = QUANT_BITS) -> AblatedEye:
    """Sweep the sampling phase and measure the eye with one DFE policy.

    Mirrors `eye_opening_vs_phase` step for step -- the same phase offsets, the
    same `cursors_from_pulse`, the same grow-outward contiguity rule -- and
    differs only in adding `leftover_v` to the residual before the height is
    taken. **Contiguity is required, not assumed**, for the same reason it is
    there: an isolated phase that happens to open elsewhere in the UI is not
    part of this opening.
    """
    pr = np.asarray(pr, dtype=float)
    osr = int(osr)
    if osr < 4:
        raise ValueError(f"osr must be at least 4 to resolve a phase, got {osr}")
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}; have {POLICIES}")

    offsets = np.arange(-(osr // 2), osr - (osr // 2))
    heights = np.empty(offsets.size)
    h0s = np.empty(offsets.size)
    h1s = np.empty(offsets.size)
    lefts = np.empty(offsets.size)
    for i, d in enumerate(offsets):
        cs = cursors_from_pulse(pr, osr, int(cursor + d), require_positive=False)
        h0 = float(cs.h0_v)
        h1 = float(cs.taps.get(1, 0.0))
        extra = leftover_v(h1, h0, policy, eps=eps, bits=bits)
        heights[i] = max(0.0, 2.0 * (h0 - cs.residual_abs_v - extra))
        h0s[i], h1s[i], lefts[i] = h0, h1, extra

    # **The height is reported at the CURSOR, not at the best phase.** The
    # bridge takes `eye_h_v` from `cursors_from_pulse(pr, osr, cursor)` -- the
    # argmax of the pulse response, i.e. offset 0 -- while the WIDTH comes from
    # the phase sweep. Reporting the best phase's height instead is a different
    # convention that disagrees by single millivolts, which is exactly enough
    # to fail the control and not enough to look wrong. Caught by entry 39's Q1.
    i_report = int(np.flatnonzero(offsets == 0)[0])
    i_best = int(np.argmax(heights))
    open_mask = heights > 0.0
    lo = hi = i_best
    while lo - 1 >= 0 and open_mask[lo - 1]:
        lo -= 1
    while hi + 1 < offsets.size and open_mask[hi + 1]:
        hi += 1
    width = (hi - lo + 1) / osr if open_mask[i_best] else 0.0

    h0r = float(h0s[i_report])
    return AblatedEye(
        policy=policy, eye_h_v=float(heights[i_report]), eye_w_ui=float(width),
        best_phase_ui=float(offsets[i_best]) / osr, h0_v=h0r,
        h1_v=float(h1s[i_report]),
        dfe_tap=(float(h1s[i_report]) / h0r) if h0r else 0.0,
        leftover_v=float(lefts[i_report]),
        n_phases_open=int(open_mask.sum()))


def all_policies(pr, osr: int, cursor: int, eps: float = MISADAPT_EPS,
                 bits: int = QUANT_BITS) -> dict:
    """Every policy from ONE pulse response. Zero extra simulations."""
    return {p: eye_under_policy(pr, osr, cursor, p, eps=eps, bits=bits)
            for p in POLICIES}


__all__ = ["AblatedEye", "POLICIES", "MISADAPT_EPS", "QUANT_BITS",
           "eye_under_policy", "all_policies", "leftover_v"]
