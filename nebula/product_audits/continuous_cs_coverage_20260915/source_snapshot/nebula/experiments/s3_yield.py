"""
experiments/s3_yield.py — the random-search baseline for G3, re-derived on the
corrected 1.8 V SKY130 bias.

WHAT THIS REPLACES
------------------
The "5.3% of random samples meet S3" figure in `common/params.py` was measured
on the **generic BSIM4, 1.2 V** hand-design that session 9c found mis-biased at
gm/I_D = 1.7 with its sources 0.44 V below ground. HANDOFF §8's START HERE
block requires it re-run on the corrected point before it is defended.

WHY THE NUMBER IS REPORTED AS A COUPLING FACTOR, NOT A BARE PERCENTAGE
----------------------------------------------------------------------
"5.3% of random samples meet S3" is only as meaningful as the box it was drawn
from. A tight box around a known-good point yields high; a generous one yields
low. The first question any judge asks is "how did you choose the bounds?",
and "we swept these ranges" is a weak answer.

So the statistic reported here is box-relative by construction. S3 is a
conjunction of two conditions on the same design:

    A: peaking      in 3-12 dB
    B: f_peak       in 1.25-2.5 GHz

If A and B were independent, P(A and B) would equal P(A)*P(B). They are not
independent — both are driven by the same (gm, Rs, Cs, RL, CL) — so the
measured joint falls BELOW the product, and

    coupling factor = P(A) * P(B) / P(A and B)

is how much harder the conjunction is than its parts suggest. Widening the box
drops P(A), P(B) and P(A and B) together, so the ratio is far more stable than
any of them alone. `--box-scan` measures exactly that: the same statistic at
three box widths, so the stability is demonstrated rather than claimed.

Costs the same 2000 simulations as the bare percentage did. Three counters
instead of one.

EVERY RATE IS REPORTED WITH A BINOMIAL 95% INTERVAL
----------------------------------------------------
G40's lesson generalises: a bare proportion invites a conclusion its own
sampling error does not support. 165/1890 is 8.73%, but 165 is a count with a
standard error of about 12, so the honest statement is 8.73% [7.53, 10.10].
`wilson_ci` supplies that interval for every proportion printed here, and the
coupling factor — a ratio of three correlated proportions, for which no closed
form applies — gets a percentile bootstrap over the same rows. Without it there
is no way to tell whether 0.89x and 1.04x differ from each other or from 1.00x.

--cl-fixed: WHY ONE AXIS GETS PINNED
-------------------------------------
`cl` is the bound the re-derivation moved furthest — 6x tighter than the 1.2 V
box, because f_p2 = 1/(2*pi*RL*CL) and 400 fF already drives the Nyquist boost
negative (BOUNDS_REDERIVATION §6). That makes it the natural candidate for
"how much of the 8.73% is just the cl bound being loose?", which `--cl-fixed`
answers by removing cl from the search entirely and re-measuring.

The pin is applied AFTER sampling, overwriting the cl coordinate of the SAME
Latin-hypercube design. That is deliberate and it matters: with the seed held,
the other eight coordinates are IDENTICAL across pinned runs, so a difference
between two cl values is attributable to cl and not to a different draw. LHS
stratification is per-dimension, so discarding one dimension's values leaves
the remaining eight exactly as well stratified as before.

USAGE
    python -m nebula.experiments.s3_yield --n 2000
    python -m nebula.experiments.s3_yield --n 2000 --box-scan
    python -m nebula.experiments.s3_yield --n 2000 --cl-fixed 100e-15
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.common.types import (
    SPEC_F_PEAK_HZ_RANGE,
    SPEC_PEAKING_DB_RANGE,
)
from nebula.device.sky130_runner import SizingPoint, run_point, swing_limits

# ─────────────────────────────────────────────────────────────────────────────
# THE PROPOSED BOX.
#
# NOT YET WRITTEN INTO `common/params.py::BOUNDS` — CLAUDEwa.md §8 rule 6 and
# HANDOFF G17 reserve parameter ranges for a human. This is the proposal, with
# every edge traced to a measurement made on 2026-08-04 against SKY130
# nfet_01v8 at VDD = 1.8 V, TT/27 C, via `nebula/device/sky130_runner.py`.
#
# Lengths are SI METRES here, as everywhere else in the repo;
# `SizingPoint.from_params` does the single conversion to the microns the
# netlist wants. `i_bias` is the TOTAL supply current, split across two sinks.
#
# THE THREE TAIL PARAMETERS ARE ABSENT ON PURPOSE. w_tail, l_tail and nf_tail
# cannot be derived from any measurement yet: the tail is still two ideal
# current sinks, so no simulation in this project has ever contained a tail
# transistor. Inventing ranges for a device that does not exist is exactly what
# rule 6 forbids. They are unblocked by the G1 open item ("add a real tail
# transistor"), not by this script.
# ─────────────────────────────────────────────────────────────────────────────

PROPOSED_BOX: dict[str, tuple[float, float, bool, str]] = {
    # name: (lo, hi, log_scale, provenance)
    "w_in": (
        20e-6, 100e-6, False,
        "gm/I_D measured 5.62 at W=20 um rising to 14.36 at W=100 um "
        "(i_tail 1.5 mA/side, VCM 1.25). Ceiling is the SKY130 nfet_01v8 W "
        "bin limit (wmax = 1.0e-4 m) — above it there is no model. Floor is "
        "where v(s1) still clears +0.25 V; at W=10 it is +0.093 V and at "
        "W=5 it is -0.178 V, which is session 9c's unbuildable-tail failure",
    ),
    "l_in": (
        0.15e-6, 1.0e-6, True,
        "0.15 um is the SKY130 nfet_01v8 minimum L bin (lmin = 1.5e-7 m). "
        "Ceiling measured: at L=1.0 um gm/I_D is 3.13 and peaking 2.37 dB, "
        "already below S3; at L=2.0 um f_peak lands at 47.9 GHz and the "
        "response is no longer a CTLE at all",
    ),
    "nf_in": (
        1, 8, False,
        "MEASURED NEAR-DEAD, and not what the old bound claimed. On SKY130 "
        "W is the TOTAL device width and nf only splits it into fingers: "
        "nf = 1,2,4,8,16,32 at W=40 gives gm = 14.22, 13.68, 12.62, 13.12, "
        "12.29, 11.79 mS — a +/-10% NON-MONOTONIC parasitic effect, not a "
        "width multiplier. The old provenance string ('1-32 multiplies "
        "effective W') described the generic-BSIM4 netlist, not the PDK",
    ),
    "i_bias": (
        0.5e-3, 8.0e-3, True,
        "TOTAL supply current (two sinks of half each). Ceiling is S6 at "
        "VDD=1.8 V: 8.0 mA x 1.8 V = 14.4 mW < 15 mW — the same argument the "
        "1.2 V box made with 12 mA, re-evaluated at the real supply. Floor "
        "0.5 mA total measured at gm/I_D 17.2, noise 0.275 mVrms, still "
        "inside S5. NOTE 8 mA total with rl=400 takes the pair out of "
        "saturation, which is what headroom_ok() is for",
    ),
    "rs": (
        50, 1000, True,
        "FULL source-to-source resistance. Measured at Cs=1.6p RL=400 "
        "CL=100f: Rs=50 gives 0.08 dB peaking, Rs=200 gives 4.63 dB, Rs=400 "
        "gives 8.54 dB, Rs=800 gives 13.25 dB — already through S3's 12 dB "
        "ceiling. The bound is the range that spans S3 with a little margin "
        "on each side",
    ),
    "cs": (
        100e-15, 10e-12, True,
        "Sets f_zero = 1/(2*pi*Rs*Cs). Measured at Rs=200 RL=400 CL=100f: "
        "Cs <= 200 fF produces NO PEAK AT ALL (f_z ends up above f_p2, which "
        "session 9c found extinguishes the peak rather than moving it), and "
        "Cs = 6.4 pF puts f_peak at 1.047 GHz, below the S3 window",
    ),
    "rl": (
        50, 800, True,
        "Per side. Measured at i_tail 1.5 mA/side VCM 1.25: RL=50 puts "
        "f_peak at 5.75 GHz (far above the S3 window), RL=800 leaves "
        "vds=0.30 V against vdsat=0.136 V, and RL=1000 takes the pair OUT "
        "of saturation (vds 0.09 < vdsat 0.167) and collapses the gain to "
        "-8.68 dB. Jointly constrained with i_bias — see headroom_ok()",
    ),
    "cl": (
        10e-15, 500e-15, True,
        "Per side; sets f_p2 = 1/(2*pi*RL*CL). MUCH tighter than the 1.2 V "
        "box's 0.1-3.0 pF, and measured: at Rs=200 Cs=1.6p RL=400, CL=400 fF "
        "already drives nyquist_boost NEGATIVE (-1.34 dB) and CL >= 800 fF "
        "extinguishes the peak entirely. The old ceiling was 6x into dead "
        "space at this supply",
    ),
    "vcm_in": (
        1.1, 1.6, False,
        "Measured: v(s1) tracks VCM almost 1:1 (VCM 0.9 -> v(s1) +0.050; "
        "VCM 1.25 -> +0.343; VCM 1.65 -> +0.681) while gm moves only 12.99 "
        "-> 12.08 mS. So VCM buys tail headroom at almost no gm cost, and "
        "the floor is set by needing v(s1) >= ~0.2 V for a real tail "
        "transistor. Ceiling: at VCM=1.65 vds is down to 0.52 V and shrinks "
        "further as rl rises",
    ),
}

#: The three §5.2 names this box deliberately does not cover, and why.
#:
#: **The reason CHANGED in session 13 and the conclusion did not.** It used to
#: be "no tail transistor exists yet — the netlist uses ideal sinks", i.e. the
#: bounds were underivable. A tail now exists (`nebula/device/tail.py`) and all
#: three edges have been measured (`TAIL_DEVICE.md` §6). They are still absent
#: from this box, for a different and stronger reason: **measurement says they
#: should not be SEARCHED at all.**
#:
#: - `w_tail` follows from `i_bias` by a current-density rule, because holding
#:   `vdsat_tail` on target is what the dimension is for. Searching it
#:   independently mostly produces tails that are the wrong size for their own
#:   current, and can move S3 peaking by up to 2.15 dB — more than session 11's
#:   entire 1.0 dB corner-robustness margin budget.
#: - `nf_tail` follows from `w_tail` and the mirror ratio via SKY130's
#:   per-finger bin ceiling (G53). Measured: with matched fingers, nf 8 to 32
#:   moves the delivered current by 0.6 %. It is a near-dead dimension, the
#:   same finding as G38 for `nf_in` and G42 for `cl`.
#: - `l_tail` is the only one with a genuine trade (output resistance and
#:   matching against width and area), and even it spans just 0.5-1.0 um.
#:
#: So this is a PROPOSAL to keep the action space at nine dimensions rather
#: than twelve, and it is a human's to accept (rule 6). The measured ranges are
#: in `TAIL_DEVICE.md` §6 for whoever decides otherwise.
UNDERIVABLE: dict[str, str] = {
    "w_tail": "measured (TAIL_DEVICE.md sec 6) but DERIVED from i_bias by a "
              "current-density rule, not searched",
    "l_tail": "measured (TAIL_DEVICE.md sec 6); 0.5-1.0 um, fixed at 0.5 "
              "rather than searched",
    "nf_tail": "measured NEAR-DEAD (0.6% effect); derived from w_tail and the "
               "per-finger bin ceiling, G53",
}

S5_NOISE_MAX_VRMS = 1.5e-3
S6_POWER_MAX_W = 15e-3

#: Minimum DC output voltage for the pair to stay usefully saturated at 1.8 V.
#: Measured: rl=800 at 1.5 mA/side leaves v_out = 0.60 V and still works;
#: rl=1000 leaves 0.30 V and does not.
MIN_V_OUT_DC = 0.5


def headroom_ok_1v8(params: dict[str, float], vdd: float = 1.8) -> Optional[str]:
    """Analytic pre-check, re-derived at 1.8 V. None if OK, else a reason.

    `common/params.py::headroom_ok` hard-codes the 1.2 V rail and a 0.2 V
    floor measured on the mis-biased device. Both move at 1.8 V, so the check
    moves with them rather than being reused across supplies.
    """
    v_drop = 0.5 * float(params["i_bias"]) * float(params["rl"])
    v_out = vdd - v_drop
    if v_out < MIN_V_OUT_DC:
        return (f"load drop {v_drop:.3f} V leaves v_out {v_out:.3f} V "
                f"(need >= {MIN_V_OUT_DC} V)")
    if float(params["vcm_in"]) >= vdd:
        return f"vcm_in {params['vcm_in']:.3f} V is at or above VDD {vdd:.2f} V"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Sampling.
# ─────────────────────────────────────────────────────────────────────────────


def scale_box(
    box: dict[str, tuple[float, float, bool, str]],
    factor: float,
) -> dict[str, tuple[float, float, bool, str]]:
    """Widen (factor > 1) or narrow (factor < 1) every bound about its centre.

    Log-scaled parameters scale about their geometric centre, linear ones about
    their arithmetic centre, so "1.5x wider" means the same thing in both.
    This exists to demonstrate that the coupling factor survives a change of
    box that moves the raw yield a great deal.
    """
    out: dict[str, tuple[float, float, bool, str]] = {}
    for name, (lo, hi, log, prov) in box.items():
        if log:
            c = math.sqrt(lo * hi)
            half = (math.log(hi) - math.log(lo)) / 2.0 * factor
            new_lo, new_hi = c * math.exp(-half), c * math.exp(half)
        else:
            c = (lo + hi) / 2.0
            half = (hi - lo) / 2.0 * factor
            new_lo, new_hi = c - half, c + half
        if name == "nf_in":
            new_lo = max(1.0, new_lo)
        if name == "vcm_in":                # never propose a gate above the rail
            new_lo, new_hi = max(0.6, new_lo), min(1.75, new_hi)
        if name == "w_in":                  # the SKY130 W bins simply stop
            new_lo, new_hi = max(1e-6, new_lo), min(100e-6, new_hi)
        if name == "l_in":
            new_lo = max(0.15e-6, new_lo)   # no model below the minimum bin
        out[name] = (new_lo, new_hi, log, f"{prov} [box x{factor}]")
    return out


def pin_param(
    rows: list[dict[str, float]],
    name: str,
    value: float,
) -> list[dict[str, float]]:
    """Overwrite one coordinate of an existing sample with a fixed value.

    Applied AFTER `sample_box` rather than by re-sampling in d-1 dimensions,
    so that two pinned runs at the same seed differ in EXACTLY one coordinate.
    That turns the comparison between them into a paired one — any difference
    in yield is caused by `name`, not by a different draw of the other eight
    parameters. Re-sampling in d-1 dimensions would move every coordinate and
    confound the two effects.

    Raises on an unknown name rather than silently adding a parameter the
    netlist will never read.
    """
    if not rows:
        return rows
    if name not in rows[0]:
        raise KeyError(f"{name!r} is not a sampled parameter; have {sorted(rows[0])}")
    return [{**r, name: float(value)} for r in rows]


def sample_box(
    box: dict[str, tuple[float, float, bool, str]],
    n: int,
    seed: int,
) -> list[dict[str, float]]:
    """Latin-hypercube sample, matching the method the 5.3% figure used."""
    from scipy.stats import qmc

    names = list(box)
    unit = qmc.LatinHypercube(d=len(names), seed=seed).random(n)
    rows: list[dict[str, float]] = []
    for u in unit:
        p: dict[str, float] = {}
        for ui, name in zip(u, names):
            lo, hi, log, _ = box[name]
            v = (math.exp(math.log(lo) + ui * (math.log(hi) - math.log(lo)))
                 if log else lo + ui * (hi - lo))
            p[name] = float(max(1, round(v))) if name == "nf_in" else float(v)
        rows.append(p)
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Row:
    ok: bool
    reason: Optional[str] = None
    skipped_headroom: bool = False
    peaking_db: Optional[float] = None
    f_pk_hz: Optional[float] = None
    nyquist_boost_db: Optional[float] = None
    #: Whether |H| has a genuine INTERIOR maximum, measured by the runner
    #: rather than inferred from where f_pk sits (G44). None on old data.
    has_interior_peak: Optional[bool] = None
    g_dc_db: Optional[float] = None
    g_top_db: Optional[float] = None
    g_nyq_db: Optional[float] = None
    vn_in_vrms: Optional[float] = None
    power_w: Optional[float] = None
    gm_over_id: Optional[float] = None
    v_src_dc: Optional[float] = None
    in_saturation: Optional[bool] = None
    swing_linear_pp_v: Optional[float] = None
    swing_sat_pp_v: Optional[float] = None
    params: Optional[dict] = None


def evaluate(params: dict[str, float]) -> Row:
    reason = headroom_ok_1v8(params)
    if reason is not None:
        return Row(ok=False, reason=reason, skipped_headroom=True, params=params)
    point = SizingPoint.from_params(params, vdd=1.8)
    r = run_point(point, swing=True, vid_max=0.9, vid_step=0.006)
    if not r.ok:
        return Row(ok=False, reason=r.fail_reason, params=params)
    lim = swing_limits(r.vid, r.vod, r.sat_ok, r.id_min,
                       i_ref_a=point.i_tail_per_side_a)
    return Row(
        ok=True,
        peaking_db=r.peaking_db, f_pk_hz=r.f_pk_hz,
        nyquist_boost_db=r.nyquist_boost_db,
        has_interior_peak=r.has_interior_peak,
        g_dc_db=r.g_dc_db, g_top_db=r.g_top_db, g_nyq_db=r.g_nyq_db,
        vn_in_vrms=r.vn_in_vrms, power_w=point.power_w,
        gm_over_id=r.gm_over_id, v_src_dc=r.v_src_dc,
        in_saturation=r.in_saturation,
        swing_linear_pp_v=lim.linear_pp_v,
        swing_sat_pp_v=lim.saturation_pp_v,
        params=params,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Uncertainty. Every proportion below is k successes out of n Bernoulli trials.
# ─────────────────────────────────────────────────────────────────────────────


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Two-sided Wilson score interval on a binomial proportion.

    WHY WILSON AND NOT THE TEXTBOOK `p +/- z*sqrt(p(1-p)/n)`. The normal
    approximation is built on a symmetry that does not hold near 0 or 1: at
    S3's 8.7% over 1890 trials it puts the lower edge in roughly the right
    place but keeps drifting below zero as p falls, and for a spec that yields
    0/1890 it returns the interval [0, 0] — a claim of certainty from a sample
    that has merely never seen the event. Wilson is the interval obtained by
    inverting the score test; it stays inside [0, 1] by construction and
    returns a non-degenerate upper bound at k = 0, which is the case this
    experiment hits whenever a corner kills a spec outright.

    `python_models/pam4_chain.py::ber_wilson_upper` is the same algebra, kept
    to the one-sided upper bound a BER needs. It is NOT imported: `nebula/` is
    independent of `python_models/` by design (CLAUDEwa.md §10), and a
    cross-project import for six lines of arithmetic would be the first thread
    of a dependency this repo deliberately does not have. The duplication is
    load-bearing; a test pins the two against each other.

    Returns (lo, hi). n <= 0 gives the vacuous (0.0, 1.0) — no data, no claim.
    """
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


def _fmt_ci(k: int, n: int) -> str:
    lo, hi = wilson_ci(k, n)
    return f"[{lo * 100:5.2f}, {hi * 100:5.2f}]"


def bootstrap_coupling_ci(
    a: Sequence[bool],
    b: Sequence[bool],
    n_boot: int = 10_000,
    seed: int = 20260805,
    z_pct: tuple[float, float] = (2.5, 97.5),
) -> tuple[float, float]:
    """Percentile-bootstrap interval for P(A)*P(B) / P(A and B).

    The coupling factor is a ratio of three proportions measured on the SAME
    rows, so they are correlated and no closed-form interval applies. The
    bootstrap resamples whole rows — preserving that correlation, which is the
    entire point — and reports the 2.5/97.5 percentiles of the resulting ratio.

    This is what makes "1.04x" a statement rather than a decimal: without it,
    there is no way to say whether the box-scan's 0.89 / 0.90 / 1.04 spread is
    signal or noise. Draws where the joint count is zero give an infinite
    ratio; they are dropped, and if too many are dropped the interval is
    reported as unbounded rather than quietly truncated.
    """
    a_arr = np.asarray(a, dtype=bool)
    b_arr = np.asarray(b, dtype=bool)
    n = a_arr.size
    if n == 0:
        return (math.nan, math.nan)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    pa = a_arr[idx].mean(axis=1)
    pb = b_arr[idx].mean(axis=1)
    pj = (a_arr & b_arr)[idx].mean(axis=1)
    live = pj > 0
    if live.sum() < 0.95 * n_boot:
        return (math.nan, math.inf)
    ratio = (pa[live] * pb[live]) / pj[live]
    lo, hi = np.percentile(ratio, z_pct)
    return (float(lo), float(hi))


# ─────────────────────────────────────────────────────────────────────────────
# The statistic.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class YieldStat:
    n_sampled: int
    n_headroom_rejected: int
    n_simulated: int
    n_peaking: int          # A
    n_fpeak: int            # B
    n_s3_joint: int         # A and B
    n_s3_with_nyquist: int  # A and B and nyquist_boost > 0
    n_s5: int
    n_s6: int
    n_saturated: int
    #: Samples that produce a genuine interior maximum at all. A design with
    #: NO peak fails A and B together, which makes the two conditions look
    #: positively associated for a reason that has nothing to do with the
    #: coupling the claim is about. The conditional counters below re-measure
    #: the statistic on this subset, which is the version that survives being
    #: argued with.
    n_has_peak: int = 0
    n_peaking_hp: int = 0
    n_fpeak_hp: int = 0
    n_s3_joint_hp: int = 0
    #: Percentile-bootstrap 95% interval on the coupling factor. NaN when not
    #: computed (a hand-built stat in a test), inf on the high edge when too
    #: many resamples had an empty joint to divide by.
    coupling_ci_lo: float = math.nan
    coupling_ci_hi: float = math.nan
    coupling_hp_ci_lo: float = math.nan
    coupling_hp_ci_hi: float = math.nan
    #: The pinned `cl` in farads, or None if cl was sampled. Recorded so a
    #: results file says what it is a result OF.
    cl_fixed: Optional[float] = None

    # ---- binomial 95% intervals, as (lo, hi) fractions ----
    @property
    def ci_joint(self) -> tuple[float, float]:
        return wilson_ci(self.n_s3_joint, self.n_simulated)

    @property
    def ci_a(self) -> tuple[float, float]:
        return wilson_ci(self.n_peaking, self.n_simulated)

    @property
    def ci_b(self) -> tuple[float, float]:
        return wilson_ci(self.n_fpeak, self.n_simulated)

    @property
    def p_a_hp(self) -> float:
        return self.n_peaking_hp / self.n_has_peak if self.n_has_peak else math.nan

    @property
    def p_b_hp(self) -> float:
        return self.n_fpeak_hp / self.n_has_peak if self.n_has_peak else math.nan

    @property
    def p_joint_hp(self) -> float:
        return self.n_s3_joint_hp / self.n_has_peak if self.n_has_peak else math.nan

    @property
    def coupling_factor_hp(self) -> float:
        return (self.p_a_hp * self.p_b_hp / self.p_joint_hp
                if self.p_joint_hp else math.inf)

    @property
    def p_a(self) -> float:
        return self.n_peaking / self.n_simulated

    @property
    def p_b(self) -> float:
        return self.n_fpeak / self.n_simulated

    @property
    def p_joint(self) -> float:
        return self.n_s3_joint / self.n_simulated

    @property
    def p_independent(self) -> float:
        return self.p_a * self.p_b

    @property
    def coupling_factor(self) -> float:
        """How much harder the conjunction is than independence predicts."""
        return self.p_independent / self.p_joint if self.p_joint else math.inf

    def report(self, title: str) -> str:
        n = self.n_simulated
        pin = ("cl sampled" if self.cl_fixed is None
               else f"cl PINNED at {self.cl_fixed * 1e15:.4g} fF")
        L = [f"--- {title} ({pin}) ---",
             f"  sampled                       {self.n_sampled}",
             f"  rejected by headroom (free)   {self.n_headroom_rejected}",
             f"  simulated                     {self.n_simulated}",
             "",
             "  (bracketed intervals are two-sided Wilson 95%)",
             f"  A: peaking in 3-12 dB         {self.n_peaking:5d}  "
             f"{self.p_a * 100:6.2f}%  {_fmt_ci(self.n_peaking, n)}",
             f"  B: f_peak in 1.25-2.5 GHz     {self.n_fpeak:5d}  "
             f"{self.p_b * 100:6.2f}%  {_fmt_ci(self.n_fpeak, n)}",
             f"  independence would predict          {self.p_independent * 100:6.2f}%",
             f"  A and B measured (S3)         {self.n_s3_joint:5d}  "
             f"{self.p_joint * 100:6.2f}%  {_fmt_ci(self.n_s3_joint, n)}",
             f"  ==> COUPLING FACTOR                 {self.coupling_factor:6.2f}x  "
             f"[{self.coupling_ci_lo:5.2f}, {self.coupling_ci_hi:5.2f}] boot",
             "",
             f"  conditional on a peak existing ({self.n_has_peak} samples):",
             f"    A {self.p_a_hp * 100:6.2f}%   B {self.p_b_hp * 100:6.2f}%   "
             f"A*B {self.p_a_hp * self.p_b_hp * 100:6.2f}%   "
             f"joint {self.p_joint_hp * 100:6.2f}%   "
             f"coupling {self.coupling_factor_hp:5.2f}x  "
             f"[{self.coupling_hp_ci_lo:5.2f}, {self.coupling_hp_ci_hi:5.2f}]",
             "",
             f"  S3 also with boost at Nyquist {self.n_s3_with_nyquist:5d}  "
             f"{self.n_s3_with_nyquist / n * 100:6.2f}%  "
             f"{_fmt_ci(self.n_s3_with_nyquist, n)}",
             f"  S5 noise < 1.5 mVrms          {self.n_s5:5d}  "
             f"{self.n_s5 / n * 100:6.2f}%  {_fmt_ci(self.n_s5, n)}",
             f"  S6 power < 15 mW              {self.n_s6:5d}  "
             f"{self.n_s6 / n * 100:6.2f}%  {_fmt_ci(self.n_s6, n)}",
             f"  input pair saturated          {self.n_saturated:5d}  "
             f"{self.n_saturated / n * 100:6.2f}%  {_fmt_ci(self.n_saturated, n)}"]
        return "\n".join(L)


def summarize(rows: Sequence[Row], cl_fixed: Optional[float] = None) -> YieldStat:
    pk_lo, pk_hi = SPEC_PEAKING_DB_RANGE
    f_lo, f_hi = SPEC_F_PEAK_HZ_RANGE
    sim = [r for r in rows if r.ok]
    if not sim:
        raise RuntimeError("no sample simulated — the box is entirely dead")

    a = [pk_lo <= r.peaking_db <= pk_hi for r in sim]
    b = [f_lo <= r.f_pk_hz <= f_hi for r in sim]
    # "A peak exists" = |H| has a genuine INTERIOR maximum: higher at f_pk than
    # at both ends of the MAX search range. The runner measures that directly
    # (`Sky130Point.has_interior_peak`).
    #
    # G44: the previous test here was `peaking_db > 0.25 and f_pk_hz > 50e6`,
    # which asks where the peak SITS. It catches a monotonically falling
    # response but not one still RISING at the top of the search range, which
    # reports f_pk at the range edge and a large fictitious peaking. Rows
    # predating the fix carry has_interior_peak=None and fall back to the old
    # heuristic so historical results files stay readable.
    hp = [(r.has_interior_peak if r.has_interior_peak is not None
           else (r.peaking_db > 0.25 and r.f_pk_hz > 50e6)) for r in sim]

    boot_lo, boot_hi = bootstrap_coupling_ci(a, b)
    a_hp = [x for x, h in zip(a, hp) if h]
    b_hp = [y for y, h in zip(b, hp) if h]
    hp_lo, hp_hi = (bootstrap_coupling_ci(a_hp, b_hp) if a_hp
                    else (math.nan, math.nan))

    return YieldStat(
        cl_fixed=cl_fixed,
        coupling_ci_lo=boot_lo, coupling_ci_hi=boot_hi,
        coupling_hp_ci_lo=hp_lo, coupling_hp_ci_hi=hp_hi,
        n_sampled=len(rows),
        n_headroom_rejected=sum(1 for r in rows if r.skipped_headroom),
        n_simulated=len(sim),
        n_peaking=sum(a),
        n_fpeak=sum(b),
        n_s3_joint=sum(x and y for x, y in zip(a, b)),
        n_s3_with_nyquist=sum(x and y and r.nyquist_boost_db > 0
                              for x, y, r in zip(a, b, sim)),
        n_s5=sum(1 for r in sim if r.vn_in_vrms < S5_NOISE_MAX_VRMS),
        n_s6=sum(1 for r in sim if r.power_w < S6_POWER_MAX_W),
        n_saturated=sum(1 for r in sim if r.in_saturation),
        n_has_peak=sum(hp),
        n_peaking_hp=sum(x and h for x, h in zip(a, hp)),
        n_fpeak_hp=sum(y and h for y, h in zip(b, hp)),
        n_s3_joint_hp=sum(x and y and h for x, y, h in zip(a, b, hp)),
    )


def passing_ranges(rows: Sequence[Row]) -> str:
    """What the S3-meeting points actually span — the evidence a bound needs."""
    pk_lo, pk_hi = SPEC_PEAKING_DB_RANGE
    f_lo, f_hi = SPEC_F_PEAK_HZ_RANGE
    good = [r for r in rows if r.ok
            and pk_lo <= r.peaking_db <= pk_hi and f_lo <= r.f_pk_hz <= f_hi]
    if not good:
        return "  (no S3-meeting samples)"
    out = [f"  {len(good)} S3-meeting samples span:"]
    for name in PROPOSED_BOX:
        vals = np.array([r.params[name] for r in good])
        lo, hi, *_ = PROPOSED_BOX[name]
        scale, unit = ((1e6, "um") if name in ("w_in", "l_in") else
                       (1e3, "mA") if name == "i_bias" else
                       (1e15, "fF") if name in ("cs", "cl") else (1.0, ""))
        out.append(f"    {name:8} {vals.min() * scale:10.3f} .. "
                   f"{vals.max() * scale:10.3f} {unit:3}   "
                   f"(bound {lo * scale:.3f} .. {hi * scale:.3f})")
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260804)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--box-scan", action="store_true",
                    help="repeat at 0.6x / 1.0x / 1.5x box width")
    ap.add_argument("--cl-fixed", type=float, default=None, metavar="FARADS",
                    help="pin cl instead of sampling it, e.g. --cl-fixed 100e-15. "
                         "Every other bound is held. The pin overwrites the cl "
                         "coordinate of the same seeded Latin-hypercube design, "
                         "so runs at different --cl-fixed values are PAIRED: "
                         "they differ in cl and in nothing else.")
    ap.add_argument("--out", type=Path, default=Path("s3_yield_results.json"))
    args = ap.parse_args(argv)

    factors = [0.6, 1.0, 1.5] if args.box_scan else [1.0]
    results: dict = {}
    if args.cl_fixed is not None:
        print(f"cl PINNED at {args.cl_fixed:.6g} F "
              f"({args.cl_fixed * 1e15:.4g} fF); all other bounds held\n")
    for f in factors:
        box = PROPOSED_BOX if f == 1.0 else scale_box(PROPOSED_BOX, f)
        params = sample_box(box, args.n, args.seed)
        if args.cl_fixed is not None:
            params = pin_param(params, "cl", args.cl_fixed)
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            rows = list(ex.map(evaluate, params, chunksize=8))
        stat = summarize(rows, cl_fixed=args.cl_fixed)
        title = "PROPOSED BOX" if f == 1.0 else f"box x{f}"
        print(stat.report(title))
        if f == 1.0:
            print()
            print(passing_ranges(rows))
        print()
        results[str(f)] = asdict(stat)

    if args.box_scan:
        print("--- box-width sensitivity: the point of reporting a ratio ---")
        print("  width   P(A)     P(B)     P(A)P(B)  P(A and B)   [Wilson 95%]"
              "    coupling  [bootstrap 95%]")
        for f in factors:
            s = YieldStat(**results[str(f)])
            print(f"  x{f:<5} {s.p_a * 100:6.2f}%  {s.p_b * 100:6.2f}%  "
                  f"{s.p_independent * 100:7.3f}%  {s.p_joint * 100:8.3f}%  "
                  f"{_fmt_ci(s.n_s3_joint, s.n_simulated)}  "
                  f"{s.coupling_factor:8.2f}x  "
                  f"[{s.coupling_ci_lo:.2f}, {s.coupling_ci_hi:.2f}]")

    args.out.write_text(json.dumps(results, indent=1), encoding="ascii")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
