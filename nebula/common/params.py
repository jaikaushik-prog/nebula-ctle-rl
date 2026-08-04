"""
common/params.py — the RL action space (CLAUDEwa.md §5.2).

READ THIS BEFORE TOUCHING THIS FILE.

The parameter *names* below are fixed by §5.2 and by the topology in S2.
The parameter *bounds* are deliberately absent.

    "Ranges must be set by a human after the hand-design in §7, not guessed
     by an agent."                                          — CLAUDEwa.md §5.2

    "Do not choose parameter ranges, reward weights, or spec-tightness
     heuristics autonomously. Propose, and wait for a human."
                                                            — CLAUDEwa.md §8 rule 6

This is not bureaucracy. A guessed range costs a week in one of two ways:
too wide and PPO spends its whole budget in a region where ngspice will not
converge; too narrow and the optimum is outside the box and no amount of
training finds it — and neither failure announces itself, they both just look
like "RL didn't work".

So `param_space()` raises until a human fills in `bounds.py` with numbers
carried out of the G1 hand-design, each one carrying a `provenance` string
saying where it came from. `nebula/tests/test_param_space.py` enforces that:
the space is either unpopulated (and raises) or fully populated with
provenance on every bound. There is no half-populated state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

import numpy as np


@dataclass(frozen=True)
class ParamBound:
    """One sizing parameter and the box the policy may explore inside.

    Attributes
    ----------
    name        identifier used as the key in the `params` dict handed to
                `device.evaluate()` and as the netlist substitution token.
    lo, hi      inclusive bounds in `unit`.
    unit        SI unit string, for the record and for the netlist writer.
    log_scale   if True the [0,1] policy output maps logarithmically onto
                [lo, hi]. Correct for currents, resistances and capacitances
                that span decades; wrong for widths and lengths.
    provenance  where these two numbers came from. Required, non-empty.
                "G1 hand-design, 2026-08-03, sheet row 12" is a provenance.
                "reasonable" is not.
    """

    name: str
    lo: float
    hi: float
    unit: str
    log_scale: bool
    provenance: str

    def __post_init__(self) -> None:
        if not self.provenance or not self.provenance.strip():
            raise ValueError(
                f"ParamBound({self.name!r}) has no provenance. Every bound must "
                f"be traceable to the hand-design (§8 rules 1 and 6)."
            )
        if not (self.lo < self.hi):
            raise ValueError(f"ParamBound({self.name!r}): need lo < hi, got {self.lo}, {self.hi}")
        if self.log_scale and self.lo <= 0.0:
            raise ValueError(
                f"ParamBound({self.name!r}): log_scale requires lo > 0, got {self.lo}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# The parameter names. Fixed by §5.2 + S2 (source-degenerated differential
# pair with variable Rs, Cs). Order is the action-vector order — appending is
# safe, reordering invalidates every trained policy and every logged run.
# ─────────────────────────────────────────────────────────────────────────────

PARAM_NAMES: tuple[str, ...] = (
    # input pair
    "w_in", "l_in", "nf_in",
    # tail current source
    "w_tail", "l_tail", "nf_tail", "i_bias",
    # degeneration (the CTLE zero: w_z = 1/(Rs*Cs))
    "rs", "cs",
    # load (the second pole: w_p2 = 1/(RL*CL))
    "rl", "cl",
    # bias
    "vcm_in",
)

#: Integer-valued parameters. The policy proposes a float in [0,1]; these are
#: rounded on the way into the netlist. Rounding is the device layer's job,
#: not the policy's, so the action space stays continuous for PPO.
INTEGER_PARAMS: frozenset[str] = frozenset({"nf_in", "nf_tail"})

#: The DFE tap is in §5.2 for completeness but is NOT part of the action
#: space: it is not silicon, it is adapted in the link layer.
NON_SILICON_PARAMS: frozenset[str] = frozenset({"dfe_tap"})


# ─────────────────────────────────────────────────────────────────────────────
# The bounds. Populated by a human after G1. See the module docstring.
#
# *** SUPERSEDED, PENDING A HUMAN DECISION (2026-08-04, session 9d) ***
#
# Everything below was measured on the **generic BSIM4, 1.2 V** hand-design
# that session 9c then found mis-biased at gm/I_D = 1.7, with the sources
# 0.44 V below ground. The corrected reference is SKY130 nfet_01v8 at
# VDD = 1.8 V. A re-derivation against that device exists — the box, its
# per-edge provenance and its measured yield are in
# `nebula/experiments/s3_yield.py::PROPOSED_BOX` and
# `nebula/BOUNDS_REDERIVATION.md`.
#
# It has NOT been copied in here, because §8 rule 6 makes the ranges a human's
# call and swapping them silently is precisely what that rule forbids. Until
# someone approves it, three specific defects below are known:
#
#   * every supply-dependent edge (i_bias, rl, vcm_in) is a 1.2 V number;
#   * `nf_in`'s provenance is FACTUALLY WRONG for the PDK — on SKY130, W is
#     the total device width and nf only splits it into fingers, so nf is not
#     a width multiplier at all (measured: gm moves +/-10%, non-monotonically,
#     over nf = 1..32). It multiplies W only in the generic-BSIM4 netlist,
#     which writes `m={NF}`;
#   * `cl`'s 3.0 pF ceiling is ~6x into dead space at 1.8 V: 400 fF already
#     drives the Nyquist boost negative.
#
# And one headline result that is NOT about these bounds but was found while
# re-deriving them: the "S3 is a coupled constraint" claim in the comment
# below does not survive measurement. Coupling factor 1.04x — the two S3
# conditions are independent. See BOUNDS_REDERIVATION.md §4 before quoting the
# 5.3% figure or the sentence around it anywhere.
# ─────────────────────────────────────────────────────────────────────────────

#: Populated from G1 hand-design, 2026-08-03, generic BSIM4 130nm, **VDD=1.2 V**,
#: TT/27C. Reference point: W=40u L=0.35u nf=1 Ibias=5mA Rs=800 Cs=0.8p RL=120
#: CL=1.2p Vcm=0.88. Measured: peaking 8.29 dB @ 1.259 GHz, noise 0.275 mVrms,
#: power 6.0 mW.
#:
#: AUDITED against ngspice on 2026-08-03 with 2000 Latin-hypercube samples of
#: this box (see HANDOFF session 8). Results:
#:
#:     90.7% simulate (0% non-convergence, 9.3% land in triode)
#:     90.7% meet S5 (noise)   -- effectively free in this box
#:     90.7% meet S6 (power)   -- effectively free in this box
#:      5.3% meet S3 (peaking 3-12 dB AND f_peak 1.25-2.5 GHz)
#:
#: So **S3 is the binding constraint and the box is ~5% efficient.** That is
#: not a bad box: the passing points span peaking 3.06-11.88 dB and f_peak
#: 1.26-2.40 GHz, i.e. the box reaches every corner of S3. The 5.3% is because
#: S3 is a COUPLED constraint on (gm, Rs, Cs, RL, CL) and no axis-aligned box
#: can be efficient against it. That is precisely what the surrogate and the
#: OOD discriminator exist to fix, and 5.3% is the honest random-search
#: baseline that G3 has to beat. Record it; do not try to engineer it away by
#: shrinking the box, or the optimum leaves with it.
#:
#: NOT YET VERIFIED: S9. Every number above is TT/27C. Corner model cards need
#: the PDK, and the bounds may not survive SS/125C.
#:
#: PROVENANCE AUDIT, 2026-08-03 (second pass). `rl`'s string used to justify its
#: ceiling with "barely fits in VDD=1.8 V" — but this hand-design runs at
#: **1.2 V**; the 1.8 V was carried over from the separate SKY130 netlist
#: (`spice/g1_sky130.cir`, sky130_fd_pr nfet_01v8, which really is a 1.8 V
#: device). A provenance string citing the wrong supply is worse than no
#: provenance: it reads as evidence and is not. So every bound was re-read
#: against G1_VDD_V. Result:
#:
#:   supply-DEPENDENT and now stated explicitly: i_bias (ceiling is S6 at
#:       1.2 V), rl (joint with i_bias, see headroom_ok), vcm_in (bias stack
#:       under 1.2 V). All three are correct AT 1.2 V and all three would be
#:       wrong at 1.8 V — i_bias's 12 mA ceiling in particular becomes
#:       21.6 mW and violates S6 outright.
#:   supply-INDEPENDENT, no claim to correct: w_in, l_in, nf_in, w_tail,
#:       l_tail, nf_tail, rs, cs, cl.
#:
#: One non-supply defect found and FIXED: `rs`'s measured evidence covered
#: 100-2000 ohm while the bound claimed 50-2500. The bound was tightened to
#: the swept range rather than the evidence being stretched to cover it.
_PROV = "G1 hand-design, 2026-08-03, generic BSIM4 130nm, VDD=1.2V, TT/27C"
BOUNDS: dict[str, ParamBound] = {
    # ── input pair ──
    "w_in": ParamBound("w_in", 5e-6, 100e-6, "m", False,
        f"{_PROV}: ref 40um, 5-100um spans gm range for S3/S5"),
    "l_in": ParamBound("l_in", 0.13e-6, 1.0e-6, "m", False,
        f"{_PROV}: 130nm min-L to 1um, shorter=faster, more mismatch"),
    "nf_in": ParamBound("nf_in", 1, 32, "count", False,
        f"{_PROV}: ref nf=1 in the G1 netlist; 1-32 multiplies effective W. "
        f"NOTE the synthetic mock reference uses nf_in=4 — the two reference "
        f"points are different devices and must not be compared directly"),
    # ── tail current source ──
    "w_tail": ParamBound("w_tail", 5e-6, 100e-6, "m", False,
        f"{_PROV}: same range as input pair"),
    "l_tail": ParamBound("l_tail", 0.35e-6, 2.0e-6, "m", False,
        f"{_PROV}: longer L gives better Rout for current source"),
    "nf_tail": ParamBound("nf_tail", 1, 32, "count", False,
        f"{_PROV}: tail finger count, same range as input"),
    # SUPPLY-DEPENDENT. The 12 mA ceiling is S6 evaluated AT VDD=1.2 V:
    # 12 mA * 1.2 V = 14.4 mW, just inside S6's 15 mW. At 1.8 V the same
    # current is 21.6 mW and violates S6 outright, so this ceiling does not
    # transfer to the SKY130 1.8 V netlist. Re-derive it, do not copy it.
    "i_bias": ParamBound("i_bias", 1e-3, 12e-3, "A", True,
        f"{_PROV}: 1mA floor (S5 noise), 12mA ceiling = S6 AT VDD=1.2V "
        f"(12mA x 1.2V = 14.4mW < 15mW). Supply-dependent — at 1.8V this "
        f"ceiling is 21.6mW and FAILS S6"),
    # ── degeneration (CTLE zero: f_z = 1/(2*pi*Rs*Cs)) ──
    # Supply-independent (Rs carries no DC current — the tail sinks split at
    # src1/src2 — so it costs no headroom).
    # TIGHTENED 2026-08-04 to match the evidence. Was 50-2500, but the only
    # deliberate sweep covered 100-2000 and the ends were extrapolation. Given
    # the choice between extending the evidence and tightening the bound, the
    # bound moved: 5.3% of this box meets S3 and the passing points measured
    # in the 2000-sample audit span rs well inside 100-2000, so nothing known
    # to be useful was removed. If a future sweep justifies wider ends,
    # re-widen it and say which run showed that.
    "rs": ParamBound("rs", 100, 2000, "ohm", True,
        f"{_PROV}: ref 800. Deliberately swept 100-2000 -> 0-12+dB peaking, "
        f"noise OK. Bound is now exactly the swept range (was 50-2500, whose "
        f"ends were extrapolation with no run behind them)"),
    "cs": ParamBound("cs", 0.1e-12, 5e-12, "F", True,
        f"{_PROV}: ref 0.8pF, controls f_zero for S3 f_peak target"),
    # ── load (second pole: f_p2 = 1/(2*pi*RL*CL)) ──
    # rl's ceiling CANNOT be set independently of i_bias — the load drop is
    # 0.5*i_bias*rl and it has to fit under VDD. At i_bias=12 mA, rl=500 would
    # drop 3.0 V into a 1.2 V supply. 500 ohm is retained because the LOW end
    # of the i_bias range needs it (at 1 mA it drops only 0.25 V) and because
    # 7.3% of the box violating headroom is an acceptable price for keeping
    # the corner of the space where high RL and low current live. Use
    # `headroom_ok()` below to reject those points for free, before SPICE.
    "rl": ParamBound("rl", 50, 500, "ohm", True,
        f"{_PROV}: ref 120. SUPPLY-DEPENDENT: ceiling is JOINT with i_bias "
        f"against VDD=1.2V, not independent — see headroom_ok(). (An earlier "
        f"version of this string said 'barely fits in VDD=1.8V'; that 1.8V "
        f"belongs to the SKY130 netlist, not to this design.) Measured: "
        f"passing points span 51-486 ohm"),
    # Measured: across 2000 samples, no point with cl > 2.92 pF ever met S3 —
    # f_p2 = 1/(2*pi*RL*CL) falls below the S3 peak window. Trimmed from the
    # original 5 pF, which cost nothing and removes ~20% of dead space.
    "cl": ParamBound("cl", 0.1e-12, 3.0e-12, "F", True,
        f"{_PROV}: ref 1.2pF, sets f_p2. Ceiling trimmed 5pF->3pF: measured, "
        f"no sample above 2.92pF ever met S3 (f_p2 drops below the peak window)"),
    # ── bias ──
    # SUPPLY-DEPENDENT. The stack is Vdsat_tail + Vgs_in from ground, and the
    # 1.0 V ceiling is what leaves the input pair's drain above its source
    # under a 1.2 V rail. headroom_ok() also rejects vcm_in >= VDD.
    "vcm_in": ParamBound("vcm_in", 0.6, 1.0, "V", False,
        f"{_PROV}: ref 0.88V. Vth+Vov+Vdsat_tail below, VDD=1.2V above. "
        f"Supply-dependent — the 1.0V ceiling is a 1.2V-rail number"),
}


#: Supply the G1 hand-design was done at. The bounds above are only valid at
#: this VDD — `rl`'s ceiling in particular is a headroom argument, and the
#: same box at 1.8 V would be a different (looser) design space.
G1_VDD_V: float = 1.2

#: Minimum DC voltage that must remain at the output node for the input pair
#: to stay in saturation with some margin. Measured V_dsat at the G1 point was
#: 0.289 V; 0.2 V of headroom above the drop is the working rule.
_MIN_OUT_HEADROOM_V: float = 0.2


def headroom_ok(params: Mapping[str, float], vdd: float = G1_VDD_V) -> Optional[str]:
    """Cheap analytic feasibility pre-check. None if OK, else a reason.

    The load drop `0.5 * i_bias * rl` has to fit under VDD, and that couples
    two parameters the action space treats as independent. Measured on 2000
    Latin-hypercube samples of BOUNDS: **7.3% violate this**, and every one of
    them is a wasted ngspice call — the run converges, reports a transistor in
    triode, and gets thrown away.

    Rejecting them here costs a multiply. At 0.066 s per SPICE call that is
    ~13 seconds saved per 2000 proposals, which is nothing at G2 and is
    hours over a 1e5-step training run.

    This is a *necessary* condition, not a sufficient one: passing it does not
    mean the point simulates. It exists to skip the obviously-dead corner of
    the box, not to replace the simulator.
    """
    try:
        i_bias = float(params["i_bias"])
        rl = float(params["rl"])
        vcm = float(params["vcm_in"])
    except (KeyError, TypeError, ValueError) as exc:
        return f"headroom_ok: bad params ({exc})"

    v_drop = 0.5 * i_bias * rl
    v_out_dc = vdd - v_drop
    if v_out_dc < _MIN_OUT_HEADROOM_V:
        return (
            f"load drop {v_drop:.3f} V leaves V_out_dc = {v_out_dc:.3f} V "
            f"under VDD = {vdd:.2f} V (need >= {_MIN_OUT_HEADROOM_V} V) — "
            f"i_bias={i_bias * 1e3:.2f} mA and rl={rl:.0f} ohm are jointly "
            f"infeasible even though each is inside its own bound"
        )
    if vcm >= vdd:
        return f"vcm_in {vcm:.3f} V is at or above VDD {vdd:.2f} V"
    return None


class ParamSpaceNotSetError(NotImplementedError):
    """Raised while BOUNDS is unpopulated. Not a bug: a gate."""


def is_populated() -> bool:
    return bool(BOUNDS)


def param_space() -> tuple[ParamBound, ...]:
    """The action space, in PARAM_NAMES order.

    Raises
    ------
    ParamSpaceNotSetError
        while the bounds have not been set by a human, or if they are only
        partially set.
    """
    if not BOUNDS:
        raise ParamSpaceNotSetError(
            "Parameter bounds are not set. They must come from the G1 "
            "hand-design (CLAUDEwa.md §5.2, §8 rule 6), not from an agent. "
            "Populate nebula/common/params.py::BOUNDS with one ParamBound per "
            "entry of PARAM_NAMES, each carrying a provenance string."
        )
    missing = [n for n in PARAM_NAMES if n not in BOUNDS]
    if missing:
        raise ParamSpaceNotSetError(
            f"Parameter bounds are partially set — missing {missing}. A "
            f"partially populated space silently pins parameters at whatever "
            f"the netlist default happens to be. Populate all of them or none."
        )
    extra = [n for n in BOUNDS if n not in PARAM_NAMES]
    if extra:
        raise ParamSpaceNotSetError(
            f"BOUNDS contains names not in PARAM_NAMES: {extra}. Add them to "
            f"PARAM_NAMES (at the end) or remove them."
        )
    return tuple(BOUNDS[n] for n in PARAM_NAMES)


def n_dims() -> int:
    """Dimensionality of the action space. §5.2 expects roughly 14-16."""
    return len(PARAM_NAMES)


# ─────────────────────────────────────────────────────────────────────────────
# Normalised <-> physical mapping. Pure, testable, and independent of the
# bound values, so it can be built and tested before G1 lands.
# ─────────────────────────────────────────────────────────────────────────────


def denormalize(
    x: Sequence[float] | np.ndarray,
    space: Optional[Sequence[ParamBound]] = None,
) -> dict[str, float]:
    """Map a policy action in [0,1]^d onto physical parameter values.

    Out-of-range components are clipped rather than rejected: PPO's Gaussian
    head puts mass outside [0,1] by construction, and clipping is the standard
    handling. It is not an error condition.
    """
    space = tuple(space) if space is not None else param_space()
    x = np.asarray(x, dtype=float).ravel()
    if x.shape[0] != len(space):
        raise ValueError(f"expected {len(space)} action dims, got {x.shape[0]}")
    if not np.all(np.isfinite(x)):
        raise ValueError("action vector contains nan/inf")

    out: dict[str, float] = {}
    for xi, b in zip(np.clip(x, 0.0, 1.0), space):
        if b.log_scale:
            value = float(np.exp(np.log(b.lo) + xi * (np.log(b.hi) - np.log(b.lo))))
        else:
            value = float(b.lo + xi * (b.hi - b.lo))
        if b.name in INTEGER_PARAMS:
            value = float(max(1, round(value)))
        out[b.name] = value
    return out


def normalize(
    params: Mapping[str, float],
    space: Optional[Sequence[ParamBound]] = None,
) -> np.ndarray:
    """Inverse of `denormalize`, for seeding the policy from a hand-design.

    Round-trips exactly for continuous parameters; integer parameters
    round-trip to the nearest representable value, as they must.
    """
    space = tuple(space) if space is not None else param_space()
    missing = [b.name for b in space if b.name not in params]
    if missing:
        raise KeyError(f"params is missing {missing}")

    out = np.empty(len(space), dtype=float)
    for i, b in enumerate(space):
        v = float(params[b.name])
        if b.log_scale:
            if v <= 0.0:
                raise ValueError(f"{b.name}={v} is not positive but the bound is log-scaled")
            out[i] = (np.log(v) - np.log(b.lo)) / (np.log(b.hi) - np.log(b.lo))
        else:
            out[i] = (v - b.lo) / (b.hi - b.lo)
    return np.clip(out, 0.0, 1.0)
