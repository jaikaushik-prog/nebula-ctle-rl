"""
common/design_space.py — search in DESIGN coordinates, size in DEVICE ones.

WHAT THIS IS
------------
A pure, side-effect-free inverse map:

    (gm_over_id, l_in, i_bias, f_z, k, rl, vcm_in)   <- design coordinates
                          |
                          v
    (w_in, l_in, i_bias, rs, cs, rl, vcm_in)         <- device coordinates

**Seven in, seven out.** Three coordinates are swapped and four pass straight
through:

    w_in  <- gm_over_id     the inversion level, 1/V
    rs    <- k              the degeneration factor, dimensionless
    cs    <- f_z            the zero frequency, Hz
    l_in, i_bias, rl, vcm_in                          unchanged

The dimensionality is deliberately IDENTICAL to `rl/contract.ACTION_SPACE`'s.
A reparameterization that also changed the dimension would confound two
effects, and the existing baselines could not be compared against it at all.

WHY REPARAMETERIZE — the two measured arguments
------------------------------------------------
**1. G44 becomes analytically visible instead of being discovered by
simulating.** `RL_SMOKE.md` §5: **159 of 203 invalid evaluations — 78.3 % of a
26.54 % invalid rate — were `peak_is_sweep_edge`**, a response still rising at
20 GHz reporting a large fictitious `peaking_db`. In device coordinates the
pole-zero triple is emergent, so whether a design has an interior peak is
unknown until ngspice says so. In design coordinates it is arithmetic before
anything is simulated, because all three critical frequencies are coordinates
or follow from one:

    f_z   is a coordinate
    f_p1  = k * f_z                      (CLAUDEwa.md §6: w_p1 = k/(Rs*Cs))
    f_p2  = 1 / (2*pi * RL * CL)         RL is a coordinate, CL is context

so the exact peak-existence condition `1/f_z^2 > 1/f_p1^2 + 1/f_p2^2`
(`link/cursors.py`, session 9c) and the closed-form peak location can both be
evaluated on the REQUEST. `predicted_peak()` does exactly that.

**BUT "unreachable by construction" WOULD BE AN OVERSTATEMENT, and the
experiment exists to measure the gap rather than assert it away.** Between the
request and the measurement sit three things that all move `f_peak`:

  * `to_geometry()` quantisation — **electrically stable, geometrically
    CHAOTIC** (G67): a 0.016 % change in `rs` flips the device;
  * the `res_po` bottom plate, which adds **+1.4 to +24.3 fF onto a 32.6 fF
    `cl`, up to +75 %** (G66), moving `f_p2` — which is one of the three
    frequencies above;
  * the one-zero/two-pole model itself, which session 18c decomposed at
    **4.25 %** of the `f_peak` spread, against 1.20 % for predicted-`k` and
    0.17 % for grid discretisation.

So the honest claim is "the sweep-edge region is *identifiable* before
simulating", not "unreachable". `experiments/exp_gmid_validation.py` measures
what fraction survives.

**2. The axes align with the specs.** `RL_SMOKE.md` §4 measured the seven
device dimensions differing in strength by **21x** under one `MAX_STEP`
(`vcm_in` 0.605 of a channel scale against `w_in`'s 0.0282), with `w_in` and
`l_in` the two weakest survivors, both acting on peaking through `gm` where
`rs` acts on the same channel **4-10x harder**. `k` is the coordinate those
two were reaching for.

WHAT THIS MODULE IS NOT
-----------------------
**It is not wired into the RL loop, and wiring it is a human decision.**
`common/params.py`, `rl/contract.py` and `rl/env.py` are untouched
(CLAUDEwa.md §8 rules 5 and 6). Changing the parameterization would also
invalidate every baseline comparison — `BASELINES.md` §5's box, the 8.73 %
random-search yield, the +8.950669 reward ceiling — so it is a measurement
brought back for a decision, not a decision.

**It never returns a clamped value.** Every function returns either a complete
result or a NAMED failure, in `rl/evaluator.py`'s style. Clamping an
infeasible request onto a box edge turns "you cannot have this" into a
plausible-looking sizing, which is G44's class of bug: a number that looks
answerable and is fiction.

**Nothing it produces is a RESULT.** It emits a request to simulate. Only
`sky130_runner` measures.

THE BIAS SOLVE IS A FIXED POINT, AND SAYING SO IS PART OF THE CONTRACT
----------------------------------------------------------------------
`Rs` follows from `k` in one division once `gm` and `gmbs` are known —

    k = 1 + (gm + gmbs)*Rs/2    =>    Rs = 2*(k - 1) / (gm + gmbs)

— and `gm` is immediate, because `gm = gm_over_id * I_D` and BOTH factors are
coordinates. What is not immediate is `gmbs`, and neither is `W`:

  * `gmbs` depends on `V_sb`, and `V_sb` IS the source node — `v(s1)` —
    which is `vcm_in - V_gs`, and `V_gs` is what the table is being asked for;
  * `W` is set by requiring the device to carry `I_D` at that `V_gs`;
  * `V_ds` is `(VDD - I_D*RL) - V_sb`, so it moves with `V_sb` too.

Three unknowns, mutually dependent, no closed form. `solve_bias()` iterates
with an explicit cap and returns `bias_no_convergence` rather than the last
iterate. **`Rs` does NOT enter the loop**, and that is a real simplification
rather than an approximation: `Rs` sits between the two SOURCES and carries no
DC current at balance, so it cannot shift the operating point. `Cs` likewise.
`RL` does, through `V_ds`, and it is a coordinate.

THE `k_alpha` KNOB, AND WHY IT DEFAULTS TO 1.0
-----------------------------------------------
G60: §6's equations neglect `r_o` and over-predict the Nyquist boost by
**+0.77 to +1.47 dB**; `experiments/prescreen.py` absorbs that into one fitted
scalar `K_ALPHA = 0.90`. This module defaults to `k_alpha = 1.0`, i.e. §6
**verbatim and unfitted**, for one reason: the validation experiment must be
able to report the map's own error without a fitted constant already having
absorbed part of it. Pass `prescreen.K_ALPHA` to get the calibrated behaviour;
it is deliberately not imported here, because `common/` importing
`experiments/` would invert the layering and because two modules owning one
constant is rule 9's failure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping, Optional, Sequence

import numpy as np

from nebula.common.design_equations import predict

if TYPE_CHECKING:                       # pragma: no cover
    # TYPE-ONLY ON PURPOSE. `device/` imports `common/`, so a runtime import
    # the other way would invert the layering and make `common` unusable
    # without a simulator on the path. This module never CONSTRUCTS a table —
    # it is handed one — so the annotation is all it needs, and
    # `from __future__ import annotations` makes that free.
    from nebula.device.gmid_lut import GmidLut

TWO_PI = 2.0 * math.pi

#: Names of the design coordinates, in the order the device names mirror.
DESIGN_NAMES: tuple[str, ...] = (
    "gm_over_id", "l_in", "i_bias", "f_z", "k", "rl", "vcm_in",
)

#: Names of the device coordinates. Deliberately the SAME SET AND ORDER as
#: `rl/contract.ACTION_NAMES`, and a test asserts it — if the action space ever
#: gains or loses a dimension, this map must be revisited rather than quietly
#: producing a dict the evaluator half-understands.
DEVICE_NAMES: tuple[str, ...] = (
    "w_in", "l_in", "i_bias", "rs", "cs", "rl", "vcm_in",
)


# ─────────────────────────────────────────────────────────────────────────────
# Results. `ok=False` is a VALUE with a NAMED reason — never an exception, and
# never a clamped number.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BiasSolution:
    """The operating point the map converged on. A REQUEST, not a measurement."""

    ok: bool
    fail_reason: Optional[str] = None
    w_um: Optional[float] = None
    vgs_v: Optional[float] = None
    vsb_v: Optional[float] = None
    vds_v: Optional[float] = None
    vdsat_v: Optional[float] = None
    gm_s: Optional[float] = None
    gmbs_s: Optional[float] = None
    gds_s: Optional[float] = None
    id_a: Optional[float] = None
    iterations: int = 0

    @classmethod
    def failed(cls, reason: str, iterations: int = 0) -> "BiasSolution":
        return cls(ok=False, fail_reason=reason, iterations=iterations)

    @property
    def gmbs_over_gm(self) -> float:
        if not self.gm_s:
            return math.nan
        return (self.gmbs_s or 0.0) / self.gm_s

    @property
    def predicted_in_saturation(self) -> Optional[bool]:
        """`V_ds > V_dsat` at the requested point.

        Reported, NOT used to reject. A device predicted into triode is a
        prediction about a circuit that the evaluator will classify for itself
        — `rl/evaluator.py` calls that `HEADROOM_ONLY`, a trustworthy
        measurement of a bad circuit, and grades it. Rejecting it here would
        make this module take a decision that belongs one layer up.
        """
        if self.vds_v is None or self.vdsat_v is None:
            return None
        return self.vds_v > self.vdsat_v


@dataclass(frozen=True)
class MapResult:
    """One design point mapped to device coordinates, or a named failure."""

    ok: bool
    fail_reason: Optional[str] = None
    params: Optional[Mapping[str, float]] = None
    bias: Optional[BiasSolution] = None
    #: The pole-zero triple the REQUEST implies, in Hz. Available even when the
    #: device box rejects the point, because "what did it ask for?" is the
    #: question a rejection makes you want to answer.
    f_z_hz: Optional[float] = None
    f_p1_hz: Optional[float] = None
    f_p2_hz: Optional[float] = None
    rs_ohm: Optional[float] = None
    cs_f: Optional[float] = None

    @classmethod
    def failed(cls, reason: str, **kw) -> "MapResult":
        return cls(ok=False, fail_reason=reason, **kw)


# ─────────────────────────────────────────────────────────────────────────────
# Interpolation over the table. Multilinear, and it REFUSES to extrapolate.
# ─────────────────────────────────────────────────────────────────────────────


def _axis_weights(axis: np.ndarray, x: float, name: str
                  ) -> tuple[int, int, float]:
    """`(lo, hi, frac)` for linear interpolation, or raise outside the axis.

    **Refusing to extrapolate is the point.** A table asked outside its grid
    has no error bar, and returning the edge value would be a clamp — the
    thing this module exists not to do.
    """
    if not math.isfinite(x):
        raise ValueError(f"{name} is not finite: {x!r}")
    if x < axis[0] - 1e-12 or x > axis[-1] + 1e-12:
        raise LookupError(
            f"{name}={x:g} is outside the table's axis "
            f"[{axis[0]:g}, {axis[-1]:g}]"
        )
    x = min(max(x, axis[0]), axis[-1])
    hi = int(np.searchsorted(axis, x, side="left"))
    if hi == 0:
        return 0, 0, 0.0
    lo = hi - 1
    span = axis[hi] - axis[lo]
    return lo, hi, (0.0 if span == 0 else (x - axis[lo]) / span)


def _slice_at(lut: GmidLut, ic: int, l_um: float, vds_v: float, vsb_v: float,
              keys: Sequence[str]) -> dict[str, np.ndarray]:
    """Interpolate over (L, V_ds, V_sb), leaving `(n_W, n_Vgs)` arrays.

    `W` stays an axis because it is the unknown the current requirement solves
    for, and `V_gs` stays an axis because the inversion searches along it.
    """
    il, ih, fl = _axis_weights(lut.l_um, l_um, "L")
    dl, dh, fd = _axis_weights(lut.vds_v, vds_v, "V_ds")
    sl, sh, fs = _axis_weights(lut.vsb_v, vsb_v, "V_sb")

    out: dict[str, np.ndarray] = {}
    for k in keys:
        a = lut.prim[k]
        acc = np.zeros(a.shape[1:2] + a.shape[-1:], dtype=float)
        for i, wi in ((il, 1 - fl), (ih, fl)):
            if wi == 0.0:
                continue
            for d, wd in ((dl, 1 - fd), (dh, fd)):
                if wd == 0.0:
                    continue
                for s, ws in ((sl, 1 - fs), (sh, fs)):
                    if ws == 0.0:
                        continue
                    acc += wi * wd * ws * a[ic, :, i, d, s, :]
        out[k] = acc
    return out


def _vgs_for_gm_over_id(vgs: np.ndarray, gm: np.ndarray, idc: np.ndarray,
                        target: float, min_id_a: float = 1e-9
                        ) -> Optional[float]:
    """Invert `gm/I_D(V_gs) = target` on one curve. None if unreachable.

    `gm/I_D` falls monotonically from weak to strong inversion, so the
    inversion is well posed — but ONLY where the current is resolvable.
    `min_id_a` cuts the deep-subthreshold tail where `gm` and `I_D` both
    underflow and the ratio is numerical noise rather than physics;
    `GmidLut.monotone_fraction` is the gate that says whether that band is
    clean.
    """
    live = idc > min_id_a
    if live.sum() < 3:
        return None
    v, g = vgs[live], (gm[live] / idc[live])
    # Monotone decreasing => flip for searchsorted.
    if not np.all(np.diff(g) < 0):
        order = np.argsort(-g)
        v, g = v[order], g[order]
    if target > g[0] or target < g[-1]:
        return None
    j = int(np.searchsorted(-g, -target))
    if j == 0:
        return float(v[0])
    g0, g1 = g[j - 1], g[j]
    if g0 == g1:
        return float(v[j])
    t = (target - g0) / (g1 - g0)
    return float(v[j - 1] + t * (v[j] - v[j - 1]))


def _interp_along_vgs(vgs: np.ndarray, y: np.ndarray, x: float) -> float:
    return float(np.interp(x, vgs, y))


# ─────────────────────────────────────────────────────────────────────────────
# The bias solve.
# ─────────────────────────────────────────────────────────────────────────────

#: Supply. Imported rather than invented would be better, but `VDD_NOMINAL_V`
#: lives in `rl/contract.py` and `common/` must not import `rl/`. It is a
#: DEFAULT ARGUMENT everywhere below, never a module-level constant that a
#: caller could forget to override, and the experiment passes the contract's
#: value explicitly so the two cannot drift apart unnoticed (rule 9).
_VDD_DEFAULT_V: float = 1.8

_BIAS_KEYS = ("gm", "id", "gmbs", "gds", "vdsat")


def solve_bias(lut: GmidLut, *, gm_over_id: float, l_in_m: float,
               i_bias_a: float, rl_ohm: float, vcm_in_v: float,
               process: str = "tt", temp_c: float = 27.0,
               vdd_v: float = _VDD_DEFAULT_V,
               mirror_efficiency: float = 1.0,
               max_iter: int = 40, tol_v: float = 2e-4,
               damping: float = 0.5) -> BiasSolution:
    """Find `(W, V_gs, V_sb, V_ds)` delivering `gm_over_id` at `I_D`.

    The fixed point, and why each unknown is in it, is in the module docstring.
    Returns `bias_no_convergence` rather than the last iterate: an unconverged
    operating point that gets returned anyway is a plausible number with no
    property, which is precisely what a named failure exists to prevent.

    `mirror_efficiency` scales `I_D` away from the ideal `i_bias/2`. Session 13
    measured the real current mirror delivering **4-8 % less than requested**
    (channel-length modulation across a 0.7 V `vds` mismatch, moving with
    corner: -5.4 % ff, -6.6 % tt, -8.1 % ss), and `BASELINES.md` §11 names that
    as the first mechanism to try for the pre-screen's peaking bias. It
    DEFAULTS TO 1.0 — the ideal — so that the validation experiment measures
    the deficit rather than assuming a correction for it.
    """
    if gm_over_id <= 0 or not math.isfinite(gm_over_id):
        return BiasSolution.failed(f"gm_over_id must be positive, got {gm_over_id!r}")
    if i_bias_a <= 0 or rl_ohm <= 0:
        return BiasSolution.failed("i_bias and rl must be positive")

    try:
        ic = lut.corner_index(process, temp_c)
    except KeyError as exc:
        return BiasSolution.failed(f"corner_not_in_table: {exc}")

    i_d = 0.5 * i_bias_a * mirror_efficiency
    v_out = vdd_v - i_d * rl_ohm
    l_um = l_in_m * 1e6

    # Start at the middle of the V_sb axis rather than at 0: V_sb = 0 is the
    # no-body-effect edge, and starting on an edge biases which side of a
    # multi-valued region the iteration lands on.
    vsb = float(np.clip(vcm_in_v - 0.7, lut.vsb_v[0], lut.vsb_v[-1]))
    last: Optional[dict] = None

    for it in range(1, max_iter + 1):
        vds = v_out - vsb
        try:
            sl = _slice_at(lut, ic, l_um, vds, vsb, _BIAS_KEYS)
        except LookupError as exc:
            return BiasSolution.failed(f"outside_table: {exc}", it)
        except ValueError as exc:
            return BiasSolution.failed(f"bad_request: {exc}", it)

        # For each W on the grid: the V_gs that gives the target gm/I_D, and
        # the current the device then carries.
        vgs_w = np.full(lut.w_um.size, np.nan)
        id_w = np.full(lut.w_um.size, np.nan)
        for iw in range(lut.w_um.size):
            v = _vgs_for_gm_over_id(lut.vgs_v, sl["gm"][iw], sl["id"][iw],
                                    gm_over_id)
            if v is None:
                continue
            vgs_w[iw] = v
            id_w[iw] = _interp_along_vgs(lut.vgs_v, sl["id"][iw], v)

        good = np.isfinite(id_w)
        if good.sum() < 2:
            return BiasSolution.failed(
                f"gm_over_id_unreachable: {gm_over_id:g} 1/V is outside the "
                f"table's inversion range at L={l_um:g} um, V_ds={vds:.3f} V, "
                f"V_sb={vsb:.3f} V", it)

        w_ax, id_ax, vgs_ax = lut.w_um[good], id_w[good], vgs_w[good]
        if not np.all(np.diff(id_ax) > 0):
            order = np.argsort(id_ax)
            w_ax, id_ax, vgs_ax = w_ax[order], id_ax[order], vgs_ax[order]
        if i_d < id_ax[0] or i_d > id_ax[-1]:
            return BiasSolution.failed(
                f"current_unreachable: I_D={i_d * 1e3:.4g} mA at "
                f"gm/I_D={gm_over_id:g} needs W outside "
                f"[{w_ax[0]:g}, {w_ax[-1]:g}] um "
                f"(the table spans I_D {id_ax[0] * 1e3:.4g}-"
                f"{id_ax[-1] * 1e3:.4g} mA there)", it)

        w_um = float(np.interp(i_d, id_ax, w_ax))
        vgs = float(np.interp(i_d, id_ax, vgs_ax))
        vsb_new = vcm_in_v - vgs

        if vsb_new < lut.vsb_v[0] - 1e-9 or vsb_new > lut.vsb_v[-1] + 1e-9:
            return BiasSolution.failed(
                f"source_node_outside_table: V_sb={vsb_new:.4f} V implied by "
                f"vcm_in={vcm_in_v:g} - V_gs={vgs:.4f} is outside "
                f"[{lut.vsb_v[0]:g}, {lut.vsb_v[-1]:g}]. A NEGATIVE V_sb means "
                f"the source is below the bulk and the junction is forward "
                f"biased -- session 9c's unbuildable-tail failure.", it)

        last = dict(w_um=w_um, vgs=vgs, vds=vds, vsb=vsb, sl=sl)
        if abs(vsb_new - vsb) < tol_v:
            # Converged. Re-read the primitives at the settled point.
            gm = gm_over_id * i_d
            gmbs = gm * _read_at(lut, sl, "gmbs", w_um, vgs) / max(
                _read_at(lut, sl, "gm", w_um, vgs), 1e-18)
            return BiasSolution(
                ok=True, w_um=w_um, vgs_v=vgs, vsb_v=vsb, vds_v=vds,
                vdsat_v=_read_at(lut, sl, "vdsat", w_um, vgs),
                gm_s=gm, gmbs_s=gmbs,
                gds_s=_read_at(lut, sl, "gds", w_um, vgs),
                id_a=i_d, iterations=it,
            )
        vsb = vsb + damping * (vsb_new - vsb)
        vsb = float(np.clip(vsb, lut.vsb_v[0], lut.vsb_v[-1]))

    return BiasSolution.failed(
        f"bias_no_convergence: |dV_sb| still above {tol_v} V after {max_iter} "
        f"iterations (last V_sb={last['vsb']:.4f} V)" if last else
        f"bias_no_convergence after {max_iter} iterations", max_iter)


def _read_at(lut: GmidLut, sl: Mapping[str, np.ndarray], key: str,
             w_um: float, vgs_v: float) -> float:
    """Bilinear read of one primitive at `(W, V_gs)` off an interpolated slice."""
    wl, wh, fw = _axis_weights(lut.w_um, w_um, "W")
    lo = _interp_along_vgs(lut.vgs_v, sl[key][wl], vgs_v)
    hi = _interp_along_vgs(lut.vgs_v, sl[key][wh], vgs_v)
    return float(lo + fw * (hi - lo))


# ─────────────────────────────────────────────────────────────────────────────
# The map.
# ─────────────────────────────────────────────────────────────────────────────


def to_device(lut: GmidLut, design: Mapping[str, float], *,
              cl_f: float,
              process: str = "tt", temp_c: float = 27.0,
              vdd_v: float = _VDD_DEFAULT_V,
              mirror_efficiency: float = 1.0,
              k_alpha: float = 1.0,
              box: Optional[Mapping[str, tuple[float, float]]] = None,
              ) -> MapResult:
    """Design coordinates -> device coordinates, or a named failure.

    `box`, if given, is `{device_name: (lo, hi)}` and a request landing outside
    it is REJECTED with the coordinate named and its value quoted — never
    clamped onto the edge. Pass `rl/contract.ACTION_SPACE`'s edges via
    `box_from_action_space()` in the experiment; this module deliberately does
    not import them, both to avoid a `common -> rl` cycle and because
    redeclaring a bound is rule 9's failure.

    `cl_f` has NO DEFAULT. It is the following stage's input capacitance — a
    screened CONTEXT variable with a derived range (`CL_RANGE.md`: 13.64 /
    32.63 / 78.04 fF), not a property of this circuit — and it enters `f_p2`,
    which is one of the three frequencies the whole argument for this
    reparameterization rests on. A default would be an invented context.
    """
    missing = [k for k in DESIGN_NAMES if k not in design]
    if missing:
        return MapResult.failed(f"design vector is missing {missing}")

    gm_id = float(design["gm_over_id"])
    l_in = float(design["l_in"])
    i_bias = float(design["i_bias"])
    f_z = float(design["f_z"])
    k = float(design["k"])
    rl = float(design["rl"])
    vcm = float(design["vcm_in"])

    if not (k > 1.0):
        return MapResult.failed(
            f"k_not_above_unity: k={k:g}. k = 1 + (gm+gmbs)*Rs/2 is 1.0 at "
            f"Rs = 0 and cannot be below it; k <= 1 has no Rs.")
    if f_z <= 0 or not math.isfinite(f_z):
        return MapResult.failed(f"f_z_not_positive: {f_z!r}")
    if k_alpha <= 0:
        return MapResult.failed(f"k_alpha_not_positive: {k_alpha!r}")

    bias = solve_bias(lut, gm_over_id=gm_id, l_in_m=l_in, i_bias_a=i_bias,
                      rl_ohm=rl, vcm_in_v=vcm, process=process, temp_c=temp_c,
                      vdd_v=vdd_v, mirror_efficiency=mirror_efficiency)
    if not bias.ok:
        return MapResult.failed(bias.fail_reason or "bias_failed", bias=bias)

    assert bias.gm_s is not None and bias.gmbs_s is not None
    g_tot = bias.gm_s + bias.gmbs_s
    if g_tot <= 0:
        return MapResult.failed("degeneration_transconductance_non_positive",
                                bias=bias)

    # §6 inverted. `k_alpha` is G60's r_o shunt; 1.0 is §6 verbatim.
    rs = 2.0 * (k - 1.0) / (k_alpha * g_tot)
    cs = 1.0 / (TWO_PI * rs * f_z)

    f_p1 = k * f_z
    f_p2 = 1.0 / (TWO_PI * rl * cl_f)

    params = {
        "w_in": bias.w_um * 1e-6,      # metres, like every other length here
        "l_in": l_in,
        "i_bias": i_bias,
        "rs": rs,
        "cs": cs,
        "rl": rl,
        "vcm_in": vcm,
    }
    common = dict(bias=bias, f_z_hz=f_z, f_p1_hz=f_p1, f_p2_hz=f_p2,
                  rs_ohm=rs, cs_f=cs)

    if box is not None:
        for name, value in params.items():
            if name not in box:
                continue
            lo, hi = box[name]
            if value < lo or value > hi:
                return MapResult.failed(
                    f"{name}_outside_box: {value:g} not in [{lo:g}, {hi:g}]",
                    params=params, **common)

    return MapResult(ok=True, params=params, **common)


# ─────────────────────────────────────────────────────────────────────────────
# The forward direction, and the analytic peak — both PREDICTIONS.
# ─────────────────────────────────────────────────────────────────────────────


def to_design(gm_s: float, gmbs_s: float, params: Mapping[str, float],
              k_alpha: float = 1.0) -> dict[str, float]:
    """Device coordinates + a MEASURED `(gm, gmbs)` -> design coordinates.

    The other direction, and it needs no table because `gm` and `gmbs` are
    given: this is what turns a simulated point back into design coordinates,
    which is how the round-trip test is written and how the design box is
    derived from the approved device box (by forward-mapping it, not by
    inventing one — CLAUDEwa.md §8 rule 6).
    """
    i_d = 0.5 * float(params["i_bias"])
    rs = float(params["rs"])
    cs = float(params["cs"])
    return {
        "gm_over_id": gm_s / i_d,
        "l_in": float(params["l_in"]),
        "i_bias": float(params["i_bias"]),
        "f_z": 1.0 / (TWO_PI * rs * cs),
        "k": 1.0 + k_alpha * (gm_s + gmbs_s) * rs / 2.0,
        "rl": float(params["rl"]),
        "vcm_in": float(params["vcm_in"]),
    }


@dataclass(frozen=True)
class PeakPrediction:
    """What the REQUEST implies about the peak. Never a measurement."""

    has_interior_peak: bool
    f_peak_hz: Optional[float]
    peaking_db: Optional[float]
    reason: str


def predicted_peak(f_z_hz: float, f_p1_hz: float, f_p2_hz: float,
                   search_top_hz: Optional[float] = None) -> PeakPrediction:
    """The exact peak of a one-zero/two-pole magnitude, in closed form.

    `f_peak = sqrt( sqrt((f_z^2 - f_p1^2)(f_z^2 - f_p2^2)) - f_z^2 )`, derived
    in `experiments/task8_symbolic.py` with **no fitted constant**, and the
    existence condition `1/f_z^2 > 1/f_p1^2 + 1/f_p2^2` from
    `link/cursors.py` (session 9c, stated exactly).

    **The asymptote is not used and must not be.** `task8_symbolic.py` measured
    `20*log10(k)` over-predicting peaking by a median **+1.199 dB** across 1311
    designs. `peaking_db` here is the magnitude AT the closed-form peak
    relative to DC, evaluated on the exact expression.

    This is the function that makes G44 visible before simulating: a request
    whose `has_interior_peak` is False is one that `meas ac MAX` would report
    at the sweep edge.

    **`search_top_hz` IS NOT OPTIONAL IF YOU ARE PREDICTING G44, and leaving it
    out is a measured mistake.** The two questions are different:

        this function, bare      does |H| have an interior maximum ANYWHERE?
        `peak_is_sweep_edge`     is the maximum WITHIN the 20 GHz search range
                                 sitting at the range edge?

    A design peaking at 37 GHz has a genuine interior peak — the bare condition
    is right to say so — and still trips the guard, because inside the search
    window the response is monotonically rising. Measured on the 159 simulated
    design-arm rows of `exp_gmid_validation`: the bare condition scored
    **TN = 0** against the guard; adding `search_top_hz = MAX_SEARCH_TOP_HZ`
    took it to TN = 8, FP 60 -> 52, accuracy 61.0 -> 66.0 %. It accounts for
    8 of the 60 misses; the other 52 are model error, not this.

    It is a PARAMETER rather than a constant because the ceiling belongs to the
    device layer (`sky130_runner.MAX_SEARCH_TOP_HZ`) and `common/` must not
    import `device/` at runtime. Pass it explicitly; the default of `None`
    keeps the pure algebra available and un-second-guessed.
    """
    fz2, fp1_2, fp2_2 = f_z_hz ** 2, f_p1_hz ** 2, f_p2_hz ** 2
    if not (1.0 / fz2 > 1.0 / fp1_2 + 1.0 / fp2_2):
        return PeakPrediction(False, None, None,
                              "no interior peak: 1/f_z^2 <= 1/f_p1^2 + 1/f_p2^2")
    inner = (fz2 - fp1_2) * (fz2 - fp2_2)
    if inner < 0:
        return PeakPrediction(False, None, None,
                              "no interior peak: negative radicand")
    val = math.sqrt(inner) - fz2
    if val <= 0:
        return PeakPrediction(False, None, None,
                              "no interior peak: sqrt term below f_z^2")
    f_pk = math.sqrt(val)
    if search_top_hz is not None and f_pk >= search_top_hz:
        return PeakPrediction(
            False, f_pk, None,
            f"peak at {f_pk / 1e9:.3g} GHz is above the "
            f"{search_top_hz / 1e9:.3g} GHz search ceiling: a real maximum, "
            f"but `meas ac MAX` will report the range edge (G44)")

    def _mag_db(f: float) -> float:
        num = math.hypot(1.0, f / f_z_hz)
        den = math.hypot(1.0, f / f_p1_hz) * math.hypot(1.0, f / f_p2_hz)
        return 20.0 * math.log10(num / den)

    return PeakPrediction(True, f_pk, _mag_db(f_pk) - _mag_db(0.0),
                          "interior peak")


def predicted_response(bias: BiasSolution, rs_ohm: float, cs_f: float,
                       rl_ohm: float, cl_f: float):
    """The §6 small-signal prediction at a solved bias point.

    Thin wrapper over `design_equations.predict` so the pole/zero/gain algebra
    has exactly ONE definition in the repo (rule 9) — this module inverts it
    and must not carry a second copy of the forward form.
    """
    assert bias.gm_s is not None
    return predict(bias.gm_s, rs_ohm, cs_f, rl_ohm, cl_f,
                   gmbs=bias.gmbs_s or 0.0)


__all__ = (
    "DESIGN_NAMES", "DEVICE_NAMES",
    "BiasSolution", "MapResult", "PeakPrediction",
    "solve_bias", "to_device", "to_design",
    "predicted_peak", "predicted_response",
)
