"""
experiments/invert_response.py — **Phase 1: solve the passives instead of
searching for them.**

    from nebula.experiments.invert_response import invert
    sol = invert(peaking_db=9.0, f_peak_hz=1.9e9, bias=bias_params, cl_f=cl)

WHY THIS EXISTS
----------------
Every search in this project treats `(rs, cs, rl)` as three of seven unknowns
in a black box. They are not unknowns. `prescreen.predict_response` is a
**one-zero, two-pole** model:

    k   = 1 + K_ALPHA * (gm + gmbs) * rs / 2
    fz  = 1 / (2*pi*rs*cs)          fp1 = k * fz          fp2 = 1 / (2*pi*rl*cl)
    |H| = sqrt(1+(f/fz)^2) / ( sqrt(1+(f/fp1)^2) * sqrt(1+(f/fp2)^2) )

and that model **inverts in closed form**. Given a target peak and peaking, the
passives are determined up to ONE free parameter -- which is exactly the
parameter you want left over, because it is the one you spend on output-swing
headroom, the constraint that actually binds (92.9 % of rejections, entry 53).

THE DERIVATION, BECAUSE A REVIEWER WILL WANT IT
-------------------------------------------------
Write `a = fz`, `b = fp1 = k*a`, `c = fp2`, and maximise |H|^2 over `u = f^2`:

    d/du [ (1+u/a^2) / ((1+u/b^2)(1+u/c^2)) ] = 0
      =>  u^2 + 2*a^2*u + (a^2*c^2 + a^2*b^2 - b^2*c^2) = 0
      =>  f_peak^2 = sqrt((b^2-a^2)(c^2-a^2)) - a^2

Substituting `c = m*a` makes it **scale-free**:

    S            = sqrt((k^2-1)(m^2-1))
    f_peak       = a * sqrt(S - 1)
    peaking_db   = 10*log10( S / ((1+(S-1)/k^2) * (1+(S-1)/m^2)) )

**`peaking_db` depends only on `(k, m)`** -- not on `a`. So the inversion is:

    1. pick `rs`            -> k = 1 + K_ALPHA*(gm+gmbs)*rs/2
    2. solve peaking(k, m)  -> m          (1-D, monotone, bisection)
    3. a = f_peak / sqrt(S-1)             (algebra)
    4. cs = 1/(2*pi*rs*a)    rl = 1/(2*pi*cl*m*a)      (algebra)

`rs` is the free parameter. Step 2 is the only numerical step and it is a
bisection on a monotone function.

THE FEASIBILITY CONDITION IS ALSO CLOSED FORM
-----------------------------------------------
`peaking_db(k, m)` rises monotonically from 0 to **`20*log10(k)`** as `m` goes
from its floor to infinity. So a target is reachable **only if**

    k > 10 ** (target_peaking_db / 20)

i.e. 12 dB needs `k > 3.98`, which sets a **minimum `rs` for a given bias**.
That inequality is a design rule this project has never had, and it explains
why high-peaking requests are the ones that fail: they need degeneration the
search has to stumble onto.

WHAT THIS IS NOT
-----------------
**It is not a claim about silicon.** It inverts `predict_response`, whose own
error against SPICE is measured and not small: f_peak median **4.93 %**, p99
**1.078 octaves**; peaking MAE **0.284 dB** (`PROGRESS.md` §6). So a design this
returns is **on-target in the model** and must still be simulated. That is the
point -- it starts the search on the manifold instead of hunting for it.

**Nothing in `prescreen.py` is modified** (standing rule 7: the pre-screen is
protected; wrap, do not replace). This module imports its constants and its
`predict_gm`, so there is exactly one definition of the forward model and this
is its inverse.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional

from nebula.experiments.prescreen import K_ALPHA, predict_gm

#: Bisection tolerance on `m`. Far below the grid resolution of the forward
#: model (1200 points over 3.3 decades = 0.0091 octaves), so the root find is
#: never the limiting error.
_M_TOL: float = 1e-10

#: Upper bracket for `m`. `peaking -> 20*log10(k)` only as `m -> inf`, so a
#: target within `_PEAK_EPS` dB of that ceiling is treated as unreachable
#: rather than chased to an absurd `m` -- which would put `fp2` so far out that
#: `rl` leaves the box.
_M_MAX: float = 1e6
_PEAK_EPS: float = 1e-6


#: `w_in` above this is microns pretending to be metres. The box tops out at
#: 1e-4 m, so anything at or above 1e-3 cannot be a legal width in metres.
_W_MICRON_TELL: float = 1e-3


def _require_metres(bias: Mapping[str, float]) -> None:
    """Raise if `w_in`/`l_in` were passed in microns. **Measured, not guessed.**

    `prescreen._gm_features` takes METRES and takes `log(l)` of them, so a
    micron-valued `l_in` shifts that feature by `log(1e6) = 13.8` and the fitted
    coefficients extrapolate far outside their calibration range. Measured on
    `w=60, l=0.5`: `gm` comes back **0.0186 S** in microns against **0.0075 S**
    in metres -- a factor of **2.5**, and `gmbs` a factor of **7**.

    It does not announce itself: the round trip `invert -> predict_response`
    still closes perfectly, because both halves use the same wrong `gm`. Only
    the physical passives are wrong. That is CLAUDE.md's failure mode 2 exactly
    -- "a factor of 10^3-10^6 that still simulates happily" -- and it cost this
    module one whole feasibility map, so the check is here rather than in a
    comment.
    """
    w = float(bias.get("w_in", 0.0))
    l = float(bias.get("l_in", 0.0))
    if w >= _W_MICRON_TELL or l >= _W_MICRON_TELL:
        raise ValueError(
            f"w_in={w!r}, l_in={l!r} look like MICRONS. `predict_gm` takes "
            f"METRES (the box is w_in 2e-5..1e-4, l_in 1.5e-7..1e-6) and takes "
            f"log(l), so microns shift that feature by log(1e6)=13.8 and give "
            f"gm ~2.5x wrong without failing. Pass metres.")


@dataclass(frozen=True)
class Inversion:
    """The passives that put the model exactly on target, and the workings."""

    rs: float
    cs: float
    rl: float
    k: float
    m: float
    fz_hz: float
    fp1_hz: float
    fp2_hz: float
    gm_s: float
    gmbs_s: float


def peaking_db_of(k: float, m: float) -> float:
    """Closed-form peaking of the one-zero/two-pole model. **Scale-free.**

    Returns 0.0 when `S <= 1`, i.e. when the response has no interior peak --
    which is a real answer (the magnitude is monotone), not an error.
    """
    if not (k > 1.0 and m > 1.0):
        return 0.0
    s = math.sqrt((k * k - 1.0) * (m * m - 1.0))
    if s <= 1.0:
        return 0.0
    g = s / ((1.0 + (s - 1.0) / (k * k)) * (1.0 + (s - 1.0) / (m * m)))
    return 10.0 * math.log10(g)


def f_peak_of(a_hz: float, k: float, m: float) -> Optional[float]:
    """The peak frequency for a zero at `a_hz` and ratios `(k, m)`."""
    if not (k > 1.0 and m > 1.0):
        return None
    s = math.sqrt((k * k - 1.0) * (m * m - 1.0))
    if s <= 1.0:
        return None
    return a_hz * math.sqrt(s - 1.0)


def max_peaking_db(k: float) -> float:
    """The ceiling `20*log10(k)`, approached as `fp2 -> inf`.

    This is the design rule the project has been missing: a target above this
    is unreachable at that `k` **no matter what the other passives do**.
    """
    return 20.0 * math.log10(k) if k > 1.0 else 0.0


def k_needed_for(peaking_db: float) -> float:
    """The `k` a target peaking requires. Inverse of `max_peaking_db`."""
    return 10.0 ** (float(peaking_db) / 20.0)


def rs_needed_for(peaking_db: float, gm: float, gmbs: float) -> float:
    """Smallest `rs` that can reach `peaking_db` at this bias.

    From `k = 1 + K_ALPHA*(gm+gmbs)*rs/2`. **A strict floor:** the ceiling is
    approached only as `fp2 -> inf`, so a usable design needs `rs` above it,
    not at it.
    """
    k = k_needed_for(peaking_db)
    denom = K_ALPHA * (gm + gmbs)
    if denom <= 0.0:
        return math.inf
    return 2.0 * (k - 1.0) / denom


def m_for_peaking(k: float, peaking_db: float) -> Optional[float]:
    """Solve `peaking_db_of(k, m) = peaking_db` for `m`. Monotone bisection.

    Returns None when the target is at or above this `k`'s ceiling, which is a
    feasibility answer rather than a failure -- the caller raises `rs`.
    """
    if k <= 1.0 or peaking_db <= 0.0:
        return None
    if peaking_db >= max_peaking_db(k) - _PEAK_EPS:
        return None
    # `m` floor: where S = 1 and the peak first appears at DC.
    lo = math.sqrt(1.0 + 1.0 / (k * k - 1.0)) * (1.0 + 1e-12)
    hi = _M_MAX
    if peaking_db_of(k, hi) < peaking_db:
        return None
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if peaking_db_of(k, mid) < peaking_db:
            lo = mid
        else:
            hi = mid
        if hi - lo < _M_TOL * max(1.0, lo):
            break
    return 0.5 * (lo + hi)


def invert(peaking_db: float, f_peak_hz: float, bias: Mapping[str, float],
           cl_f: float, rs: Optional[float] = None,
           rs_margin: float = 1.35) -> Optional[Inversion]:
    """The passives that put `predict_response` exactly on target.

    `bias` supplies `w_in`, `l_in`, `i_bias` (and optionally `nf_in`) -- the
    axes this does NOT solve, because they set `gm` and are what the remaining
    search is for.

    `rs` is the free parameter. Left as None it is placed at `rs_margin` times
    the feasibility floor: far enough above it that `m` stays finite and `fp2`
    stays inside the box, without being so large that the stage is over-
    degenerated. **`rs_margin` is a starting point for a 1-D search, not a
    tuned constant** -- callers sweeping `rs` for headroom should pass it.

    Returns None when the target is unreachable at this bias, which is
    information: it says raise `rs`, or raise the current.
    """
    _require_metres(bias)
    gm, gmbs = predict_gm(bias)
    if rs is None:
        floor = rs_needed_for(peaking_db, gm, gmbs)
        if not math.isfinite(floor):
            return None
        rs = floor * float(rs_margin)
    rs = float(rs)
    if rs <= 0.0:
        return None

    k = 1.0 + K_ALPHA * (gm + gmbs) * rs / 2.0
    m = m_for_peaking(k, float(peaking_db))
    if m is None:
        return None

    s = math.sqrt((k * k - 1.0) * (m * m - 1.0))
    a = float(f_peak_hz) / math.sqrt(s - 1.0)          # fz
    if not (math.isfinite(a) and a > 0.0):
        return None

    cs = 1.0 / (2.0 * math.pi * rs * a)
    fp2 = m * a
    rl = 1.0 / (2.0 * math.pi * float(cl_f) * fp2)
    if not all(math.isfinite(v) and v > 0.0 for v in (cs, rl)):
        return None

    return Inversion(rs=rs, cs=cs, rl=rl, k=k, m=m, fz_hz=a, fp1_hz=k * a,
                     fp2_hz=fp2, gm_s=gm, gmbs_s=gmbs)


def invert_drawn(peaking_db: float, f_peak_hz: float,
                 bias: Mapping[str, float], cl_f: float,
                 rs: Optional[float] = None, rs_margin: float = 1.35,
                 rounds: int = 3) -> Optional[dict]:
    """`invert`, then correct for the fact that real passives are QUANTISED.

    `predict_response(drawn=True)` snaps `rs`, `cs`, `rl` onto SKY130 devices
    and adds half the load resistor's bottom plate to `cl` (G66, up to +75 %).
    So the continuous solution is not on target once drawn, and the honest fix
    is to **re-solve against what the drawn design actually is** rather than to
    hope the error is small.

    Each round: invert, draw, measure the drawn design's predicted response,
    and aim the next inversion at a target corrected by the residual. Returns
    the design plus the residual it converged to, so a caller can see how well
    it worked instead of assuming.
    """
    from nebula.experiments.prescreen import predict_response

    tgt_pk, tgt_f = float(peaking_db), float(f_peak_hz)
    aim_pk, aim_f = tgt_pk, tgt_f
    best = None
    for _ in range(max(1, int(rounds))):
        sol = invert(aim_pk, aim_f, bias, cl_f, rs=rs, rs_margin=rs_margin)
        if sol is None:
            return best
        params = dict(bias)
        params.update({"rs": sol.rs, "cs": sol.cs, "rl": sol.rl, "cl": cl_f})
        try:
            pred = predict_response(params, drawn=True)
        except ValueError:
            return best
        d_pk = pred.peaking_db - tgt_pk
        d_oct = math.log2(pred.f_peak_hz / tgt_f) if pred.f_peak_hz > 0 else 0.0
        cand = {"params": params, "inversion": sol, "prediction": pred,
                "peaking_err_db": d_pk, "f_peak_err_oct": d_oct}
        if best is None or (abs(d_pk) + 6.0 * abs(d_oct)
                            < abs(best["peaking_err_db"])
                            + 6.0 * abs(best["f_peak_err_oct"])):
            best = cand
        # Aim off by the residual, in the same units the model reports.
        aim_pk = aim_pk - d_pk
        aim_f = aim_f * (2.0 ** -d_oct)
    return best


# ─────────────────────────────────────────────────────────────────────────────
# The DC operating point, which the transfer function does not contain.
# ─────────────────────────────────────────────────────────────────────────────
#
# **Entry 59 is why this exists.** `predict_response` is a transfer function: it
# places a zero and two poles and says nothing about whether the bias it implies
# can physically exist. The inversion inherited that blindness, and every one of
# entry 58's 80 candidates came back `out of saturation (tail -100 to -117 mV of
# vds - vdsat)` -- at NOMINAL, before any corner was involved. Solving the AC
# response is not sufficient to propose a design.
#
# The two constants below are **fitted on 4 000 pool designs with MEASURED
# margins**, not assumed:
#
#     tail margin   corr 0.9835   median |err| 29.6 mV
#     pair margin   corr 0.9903   median |err| 34.3 mV
#
# so this is a calibrated predictor with a stated error, in the same spirit as
# `prescreen.K_ALPHA`. It is a FILTER, never a measurement: `rl/evaluator`
# still decides.

#: `vth + vdsat_tail`, fitted. The tail is sized per amp (`s9_yield.
#: tail_for_design`), so its `vdsat` is roughly constant by construction, which
#: is why one constant works.
_DC_TAIL_C: float = 0.8367

#: The input pair's constant, same fit.
_DC_PAIR_C: float = -0.7664

#: Nominal supply. Imported rather than restated would be better, but
#: `common.params` is protected (rule 7) -- so it is stated here with its source.
_VDD_NOM: float = 1.8

#: Margin a candidate must clear to be proposed. **0.1 V is `reward_v1.TOL`'s
#: own `saturation` tolerance**, not a number chosen here, and it sits ~3x the
#: 30 mV fit error above zero.
DC_MARGIN_FLOOR_V: float = 0.1


def dc_margins(params: Mapping[str, float],
               vdd: float = _VDD_NOM) -> tuple[float, float]:
    """Predicted `(pair_margin_v, tail_margin_v)`. **No SPICE.**

    `pair_margin = (VDD - i_d*rl - vcm_in) - _DC_PAIR_C`
    `tail_margin = (vcm_in - 2*i_d/gm) - _DC_TAIL_C`

    with `i_d = i_bias/2`, each side of the pair carrying half the tail current
    (`prescreen._gm_features` states that once, and this follows it).

    Median error ~30 mV against measured pool values, so a caller should demand
    a margin well above zero -- `DC_MARGIN_FLOOR_V` is the project's own
    saturation tolerance and is ~3x the fit error.
    """
    _require_metres(params)
    gm, _ = predict_gm(params)
    i_d = 0.5 * float(params["i_bias"])
    vcm = float(params["vcm_in"])
    v_out = float(vdd) - i_d * float(params["rl"])
    vdsat_in = (2.0 * i_d / gm) if gm > 0.0 else math.inf
    pair = (v_out - vcm) - _DC_PAIR_C
    tail = (vcm - vdsat_in) - _DC_TAIL_C
    return pair, tail


def dc_ok(params: Mapping[str, float], floor: float = DC_MARGIN_FLOOR_V,
          vdd: float = _VDD_NOM) -> bool:
    """Is this design's operating point plausible? A filter, never a verdict."""
    pair, tail = dc_margins(params, vdd=vdd)
    return bool(pair >= floor and tail >= floor)


# ─────────────────────────────────────────────────────────────────────────────
# The mid-window solve: both constraints act on I_d x RL, so target it.
# ─────────────────────────────────────────────────────────────────────────────
#
# **Entries 58 and 60 are why this exists, and they failed for OPPOSITE
# reasons.** Measured `I_d * RL` on their candidates:
#
#     entry 58, ranked on current      median 2.278 V   -> 2x ABOVE the ceiling
#     entry 60, ranked on DC margin    median 0.160 V   -> 3x BELOW the floor
#     the feasible window                  ~0.55-1.15 V -> NEITHER run entered it
#
# The two constraints are not in conflict; they act on the **same quantity**:
#
#     swing capability  ~ 2 * I_d*RL             wants it LARGE
#     pair saturation     I_d*RL < VDD - vcm + c wants it SMALL
#
# A ranking that is MONOTONE in `I_d*RL` therefore always lands at one extreme
# of it, and both previous attempts did. **The fix is not a better proxy but a
# different SHAPE of criterion**: maximise the tightest margin (a max-min /
# Chebyshev criterion), which is stationary in the middle of the window instead
# of at its ends.

#: `g_dc = gm*RL/k`, in dB, plus this offset. **Fitted on 3 000 pool designs**:
#: corr 0.9880, median |error| 0.223 dB after the offset. The offset is the
#: r_o shunt and the finite-gm corrections the one-line formula omits.
_G_DC_OFFSET_DB: float = -0.707


def g_dc_linear(params: Mapping[str, float]) -> float:
    """Predicted DC gain, V/V. Fitted, with a stated 0.223 dB median error."""
    _require_metres(params)
    gm, gmbs = predict_gm(params)
    k = 1.0 + K_ALPHA * (gm + gmbs) * float(params["rs"]) / 2.0
    g = gm * float(params["rl"]) / k if k > 0 else 0.0
    return float(g * 10.0 ** (_G_DC_OFFSET_DB / 20.0))


def required_swing_pp_v(params: Mapping[str, float], nyq_boost_db: float,
                        v_in_pp_v: float) -> float:
    """Differential output swing the link will actually demand, volts.

    `v_in * g_dc * 10**(nyq_boost/20)` -- the input the transmitter and channel
    deliver, times the gain at the band that matters. This is the analytic
    cross-check `link/bridge.py` already computes as `v_out_pp`; the GATE there
    is the pulse response's own peak excursion, which is stricter. So this is a
    **lower bound on the demand** and the filter built on it is optimistic by a
    stated amount rather than by an unknown one.
    """
    return float(v_in_pp_v) * g_dc_linear(params) * 10.0 ** (
        float(nyq_boost_db) / 20.0)


def margins(params: Mapping[str, float], nyq_boost_db: float,
            v_in_pp_v: float, swing_limit_pp_v: float) -> dict:
    """The three margins the two failures identified, in volts, plus the min.

    `swing_limit_pp_v` is the CAPABILITY -- pass entry 37's surrogate
    prediction, or a measured `vout_swing_v`. Nothing here measures it.

    **`worst` is the max-min objective.** Maximising it is stationary in the
    middle of the feasible window; maximising any one of the three lands at an
    extreme, which is exactly what entries 58 and 60 did.
    """
    pair, tail = dc_margins(params)
    need = required_swing_pp_v(params, nyq_boost_db, v_in_pp_v)
    swing = float(swing_limit_pp_v) - need
    return {"pair_v": pair, "tail_v": tail, "swing_v": swing,
            "required_swing_pp_v": need,
            "i_d_rl_v": 0.5 * float(params["i_bias"]) * float(params["rl"]),
            "worst": min(pair, tail, swing)}
