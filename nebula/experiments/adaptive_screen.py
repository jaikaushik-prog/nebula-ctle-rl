"""
experiments/adaptive_screen.py — **the screen the search is graded on, and the
self-check that catches it being wrong.**

WHY THIS EXISTS
----------------
Every published search in this project scores candidates on
`s9_yield.SCREEN_CORNERS` — three corners, all of them "everything slow" or
"everything fast" — and then verifies the winner at 135 points. Session 23
measured what that screen actually predicts, against the full 135-point
artifacts of every design this project has ever fully verified:

    design            true worst @135   3-corner screen says      error
    c507a3ba6f58        -0.015150          -0.000576            +0.014574
    57cba07581cd       +10.021015         +10.034191            +0.013176
    c9d52866743dc1ff    -0.023681         **+10.002082**       +10.025763

**The last row is the whole argument.** The screen did not merely mis-rank a
design; it placed an INFEASIBLE design in the feasible band, off by the entire
scale of the reward. A search steered by that screen is not weakly guided, it
is guided somewhere else.

THE FOUR POINTS, AND WHY THEY ARE A MECHANISM RATHER THAN A CURVE FIT
----------------------------------------------------------------------
S3's frequency window has TWO edges, and they bind at OPPOSITE conditions. The
peak frequency of this topology is set by an R x C product, so:

    TOP of the window (f_peak too HIGH)     fastest, coldest, LIGHTEST load
    BOTTOM of the window (f_peak too LOW)   slowest, hottest,  HEAVIEST load

Three independent reasons this is structural and not fitted to three examples:

1. **`sf` and `fs` are the extreme PASSIVE corners.** `sky130_runner` line 101:
   the extended library carries the full 5x5 (MOS x passive) cross product. The
   CTLE is nfet-only, so `sf ~= ff` and `fs ~= ss` in the TRANSISTORS and differ
   only in the R and C that set the peak. Measured per-process spans confirm it:
   `sf` was the highest and `fs` the lowest on 3 of 3 designs. **The current
   screen contains neither.**
2. **Temperature and load are perfectly monotone.** Across 135 points, holding
   everything else fixed, f_peak moved the same direction with temperature in
   **135 of 135** comparisons and with load in **135 of 135**. So hottest+
   heaviest is always one end and coldest+lightest always the other.
3. **Supply voltage is NOT reliably monotone** — 27 of 43 on one design — which
   is why both supply ends are kept rather than the "obviously" extreme one.

Measured against the full grid, these four points reproduce the 135-point worst
case **exactly, to all printed digits, on 3 of 3 corner-robust designs**, using
**four** SPICE runs where the current screen uses six. Cheaper AND correct.

AND THE SELF-CHECK, WHICH IS THE PART THAT MATTERS
---------------------------------------------------
The evidence above is three designs plus a mechanism. That is good and it is
not proof, and a screen chosen by looking at answers is exactly the shape of an
overfit. So the screen **verifies itself during the run**: every
`SELF_CHECK_EVERY` improvements, the incumbent is evaluated at all 135 points
and the screen's prediction is compared against the truth. Any point that beats
the screen's worst is **appended to the screen** and the search continues with
it.

Cost: one 135-point verification is ~50 s. Five of them in a run of ~1 h is
under 5 minutes. **If the screen is right this confirms it for almost nothing;
if it is wrong the run finds out during the run rather than after we ship.**
`ScreenAudit.was_predictive` is the number to report either way, and a run that
never fires the expansion is evidence FOR the screen rather than an absence.

WHAT THIS MODULE DOES NOT DO
-----------------------------
It does not touch `s9_yield.SCREEN_CORNERS`. The BENCHMARK screen and the
DELIVERY screen are different objects on purpose: `BASELINES.md` §7f makes
every published arm's per-design cost a function of the benchmark screen, so
changing it re-runs the whole ranking. Nothing in `BASELINES.md`, `design.py`
or any published number reads this file.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

import numpy as np

import nebula.rl.reward_v1 as R
from nebula.common.types import Corner
from nebula.experiments.s9_yield import PROMOTION_LOADS

HERE = Path(__file__).resolve().parent

#: The three loads the 135-point grid is built on: light, design, heavy.
CL_LO_F, CL_MID_F, CL_HI_F = PROMOTION_LOADS

#: The centre of S3's window in LOG frequency. `sqrt(1.25e9 * 2.5e9)`, because
#: every frequency quantity in this project is in octaves — the arithmetic
#: centre 1.875 GHz sits 0.085 octaves off centre and would quietly bias the
#: `S3_f_peak` row. One definition; callers import it (rule 9).
TARGET_F_PEAK_HZ: float = math.sqrt(1.25e9 * 2.5e9)

#: The centre of S3's peaking band, for callers that need a default request.
TARGET_PEAKING_DB: float = 7.5


@dataclass(frozen=True)
class ScreenPoint:
    """One (corner, load) pair the search is graded at, and WHY it is here.

    A pair rather than a member of a cross product, and that is the saving:
    the top edge only ever binds at the LIGHT load and the bottom edge only
    at the HEAVY one, so 4 pairs cover what a 5-corner x 2-load cross product
    would spend 10 runs on.
    """

    corner: Corner
    cl_f: float
    why: str

    @property
    def label(self) -> str:
        return (f"{self.corner.process}/{self.corner.vdd_scale:.2f}/"
                f"{self.corner.temp_c:g}C/{self.cl_f * 1e15:.0f}fF")

    def __str__(self) -> str:                                   # pragma: no cover
        return self.label


#: **THE DELIVERY SCREEN.** Four pairs; see the module docstring for the
#: measurement behind each.
EDGE4: tuple[ScreenPoint, ...] = (
    ScreenPoint(Corner(process="sf", vdd_scale=1.05, temp_c=0.0), CL_LO_F,
                "TOP edge: extreme passive corner, coldest, lightest load. "
                "Highest f_peak on 3 of 3 designs; binds at -0.015150 on "
                "c507a3ba6f58, which the 3-corner screen read as -0.000576"),
    ScreenPoint(Corner(process="ff", vdd_scale=1.05, temp_c=0.0), CL_LO_F,
                "TOP edge, fast-MOS variant. Kept because `sf` and `ff` swap "
                "order on designs whose peak is more device- than RC-limited"),
    ScreenPoint(Corner(process="fs", vdd_scale=0.95, temp_c=125.0), CL_HI_F,
                "BOTTOM edge: extreme passive corner, hottest, heaviest load. "
                "Lowest f_peak on 3 of 3; binds at +10.021015 on 57cba07581cd"),
    ScreenPoint(Corner(process="ss", vdd_scale=0.95, temp_c=125.0), CL_HI_F,
                "BOTTOM edge, slow-MOS variant. The one member this screen "
                "shares with the legacy 3-corner screen"),
)

#: **THE SEARCH SCREEN: the same four edges, at the DESIGN load.**
#:
#: `EDGE4` above spans the load sweep and therefore grades a design against
#: this project's 135-point grid. **That is not what the competition asks.**
#: The slide mandates *"PVT (TT, SS, FF, SF, FS; VDD +/-5%; 0-125 C)"* — 5 x 3
#: x 3 = **45 corners** — and says nothing about load capacitance. The third
#: axis is this project's own addition (`CL_RANGE.md`): a 5.7x uncertainty
#: about a capacitance that is **fixed at layout and known to the designer**,
#: not an operating condition. `CL_RANGE.md` §9 wrote that down on 2026-08-06,
#: before any of session 23's results existed, and called the load-swept yield
#: *"a lower bound on what a tunable part could achieve"*.
#:
#: Measured consequence of the difference, and it is the whole reason this
#: constant exists: across the 45 mandated corners a design's peak travels
#: **0.23-0.30 octaves** in a 1.000-octave window (+0.70 of headroom); add the
#: load sweep and it travels **0.94-1.02** (zero headroom, sometimes negative).
#: Two thirds of the difficulty this project has been fighting comes from an
#: axis nobody asked for.
#:
#: So: **search on this**, verify on all 135, and report the two columns
#: separately — compliance and robustness characterisation. Collapsing them
#: either way would be dishonest in one direction and self-defeating in the
#: other.
#:
#: Predictive accuracy against the 45-corner worst, measured on the three
#: fully-verified designs: **exact on 2 of 3, +0.146 on the third**, against
#: the legacy 3-corner screen's +0.009 / +0.014 / +0.166. All three errors sit
#: inside the feasible band, i.e. they cost margin rather than correctness --
#: unlike the load-swept case, where the legacy screen crossed the feasibility
#: boundary by +10.03.
EDGE4_MANDATED: tuple[ScreenPoint, ...] = tuple(
    ScreenPoint(sp.corner, CL_MID_F,
                sp.why.split(".")[0] + ". At the DESIGN load: the mandated "
                "grid is 45 PVT corners and does not sweep load")
    for sp in EDGE4)

#: **The spread probe: the two points that bracket the whole 135-point grid.**
#: AC only — no transient, no noise — because all it has to answer is "how far
#: does this design's peak travel across PVT?", and that is a property of the
#: AC curve alone. Roughly half the cost of a full-fidelity point.
SPREAD_PROBE: tuple[ScreenPoint, ...] = (EDGE4[0], EDGE4[2])

#: How wide an f_peak PVT excursion is still worth a full evaluation, in
#: octaves. **S3's window is EXACTLY 1.000 octave**, so a design whose peak
#: travels 0.97 octaves has 0.03 octaves of centring slack in the best case and
#: is a needle rather than a design. Session 22u's joint winner measured
#: 0.99979 — a 0.00021-octave target — which is what this gate exists to stop
#: the search converging on again.
#:
#: **Not a spec and not a tolerance**: purely a search filter, so it is allowed
#: to be an engineering choice. It is stated here rather than buried.
MAX_SPREAD_OCT: float = 0.97

#: How often the screen audits itself against the full grid, in IMPROVEMENTS
#: (not evaluations): the incumbent only changes when a candidate beats it, and
#: auditing an unchanged incumbent re-measures a known answer.
SELF_CHECK_EVERY: int = 5


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation at an explicit set of points. ONE definition (rule 9).
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PointResult:
    """What one (corner, load) point said. `ok=False` means UNSCORABLE."""

    label: str
    ok: bool
    reward: float = 0.0
    feasible: bool = False
    margins: dict = field(default_factory=dict)
    worst_spec: Optional[str] = None
    reason: Optional[str] = None
    f_peak_oct: Optional[float] = None
    peaking_db: Optional[float] = None
    power_w: Optional[float] = None
    hd3_nyq_dbc: Optional[float] = None
    eye_h_v: Optional[float] = None
    eye_w_ui: Optional[float] = None
    #: `{channel_loss_db: {"ok", "eye_h_v", "eye_w_ui"}}`, present ONLY when
    #: `evaluate_at_points(link_losses_db=...)` asked for it. The device is
    #: simulated once and the link re-evaluated per channel in Python, which is
    #: sound because the CTLE's input drive is channel-INDEPENDENT: the family's
    #: loss at DC is exactly 0 by construction (`CHANNEL_MODEL.md`), so
    #: `LinkConfig.v_in_diff_pp_v` is identical at 3 dB and 12 dB. Only the eye
    #: moves. Default None, so nothing that does not ask for it can see it.
    links_by_loss: Optional[dict] = None


@dataclass
class DesignEval:
    """A design's worst point over a screen, plus the audit fields.

    `n_sims` is SPICE DECKS, not design evaluations. Session 22u found this
    file's ancestor using one word for both and understating its own cost 6x,
    in a project whose headline claim is a ratio of simulation counts.
    """

    u: tuple
    ok: bool
    reward: float
    feasible: bool
    n_sims: int
    n_points: int
    n_scorable: int
    worst_point: Optional[str] = None
    worst_spec: Optional[str] = None
    reason: Optional[str] = None
    margins: dict = field(default_factory=dict)
    points: list = field(default_factory=list)
    peaking_db: Optional[float] = None
    f_peak_hz: Optional[float] = None
    power_w: Optional[float] = None
    hd3_nyq_dbc: Optional[float] = None
    eye_h_v: Optional[float] = None
    eye_w_ui: Optional[float] = None


def _attenuation_run_args(atten_code: Optional[int]) -> dict:
    """Runner arguments that keep the G140 swing instrument honest."""
    if atten_code is None:
        input_gain = 1.0
    else:
        from nebula.device.attenuator import attenuation
        input_gain = attenuation(int(atten_code))
    return {"vid_max": 0.8 / input_gain, "atten_code": atten_code}


def evaluate_at_points(u: Sequence[float],
                       points: Sequence[ScreenPoint],
                       target_f_peak_hz: float = TARGET_F_PEAK_HZ,
                       target_peaking_db: Optional[float] = TARGET_PEAKING_DB,
                       specs: Sequence[str] = R.V5_SPECS,
                       ac_only: bool = False,
                       ac_peak_interp: bool = True,
                       validity_gate: bool = False,
                       link_losses_db: Optional[Sequence[float]] = None,
                       atten_code: Optional[int] = None,
                       ) -> DesignEval:
    """Score one sizing at an explicit list of (corner, load) pairs.

    **The score is the WORST point**, which is CLAUDEwa.md §12's first named
    trap read the right way round: *"optimising at nominal and checking corners
    afterwards — score on worst corner from the start."*

    **`ac_peak_interp` defaults to True and must stay that way (G108).** S3's
    1.2500 GHz floor falls between the `ac dec 50` samples 1.202264 and
    1.258925 GHz, so the raw lattice peak rounds a 1.6 %-wide band of true
    FAILURES into passes. Session 22u measured one design moving from
    `+12.0205 FEASIBLE` to `-0.0147 INFEASIBLE` on this flag alone. The
    interpolation goes through `evaluator.annotate_interpolated_peak` and
    `evaluator.scored_meas` — the same two functions every other scoring path
    in this project reaches the peak through — rather than being rebuilt here,
    because rebuilding it here is the exact defect G108 names.

    **An unscorable point is not a failing point** (G107). A design whose eye
    cannot be COMPUTED at some corner lands in a graded invalid band ordered by
    how many points *were* scorable, strictly below every genuinely infeasible
    score. Collapsing the two either kills a search or fakes a pass.
    """
    from nebula.device.sky130_runner import run_point
    from nebula.experiments.exp_g2_closed_loop import FUNNEL_LOSS_DB
    from nebula.link.bridge import device_result_from_point, evaluate_link
    from nebula.link.config import LinkConfig
    from nebula.rl.contract import f_peak_octaves, sizing_from_u
    from nebula.rl.evaluator import (Verdict, annotate_interpolated_peak,
                                     build_point, scored_meas, validate)

    u = tuple(float(x) for x in np.clip(np.asarray(u, dtype=float), 0.0, 1.0))
    pts = list(points)
    n_points = len(pts)
    cfg = LinkConfig(channel_loss_db_at_nyquist=FUNNEL_LOSS_DB)
    drive_pk = 0.5 * float(cfg.v_in_diff_pp_v)

    results: list[PointResult] = []
    worst: Optional[PointResult] = None
    n_sims = 0
    first_bad: Optional[str] = None
    bad_point: Optional[str] = None

    for sp in pts:
        c = sp.corner
        try:
            sizing = sizing_from_u(np.asarray(u), cl_f=float(sp.cl_f))
            point, _ = build_point(sizing, corner=c.process,
                                   vdd_scale=c.vdd_scale)
        except Exception as exc:                                # noqa: BLE001
            return DesignEval(u=u, ok=False,
                              reward=R.invalid_reward(len(specs)),
                              feasible=False, n_sims=n_sims,
                              n_points=n_points, n_scorable=0,
                              reason=f"unrealisable: {exc}")
        # G140: with an input attenuator the DC sweep must be enlarged by the
        # inverse input gain, or the sweep boundary masquerades as the stage's
        # linear limit.  At ``None`` this is exactly the historical 0.8 V.
        pt = run_point(point, c.process, temp_c=c.temp_c,
                       swing=not ac_only, ac_sweep=True, hd3=not ac_only,
                       ac_peak_interp=ac_peak_interp,
                       hd3_vin_pk_v=(None if ac_only else drive_pk),
                       hd3_tone_hz=(None if ac_only else cfg.nyquist_hz),
                       **_attenuation_run_args(atten_code))
        n_sims += 1

        if not pt.ok:
            first_bad = first_bad or pt.fail_reason
            bad_point = bad_point or sp.label
            results.append(PointResult(sp.label, False, reason=pt.fail_reason))
            continue

        if ac_only:
            # **The probe reads the AC curve off `pt` DIRECTLY and does not go
            # through `device_result_from_point`.** That function enforces the
            # §8 rule 1 contract -- every numeric field present on success --
            # so it correctly REFUSES a point with no HD3, and the probe has
            # deliberately not run a transient. Asking it anyway returned
            # "hd3_dbc is missing" at every probe point, i.e. the gate working
            # as designed on a caller that wanted a different question
            # answered. The probe therefore builds only the two fields it
            # needs, and must not pretend to answer any of the others.
            if pt.f_pk_hz is None or not pt.has_interior_peak:
                # G44: a response still rising at the top of the sweep has a
                # FICTITIOUS peak. Unscorable, not "very high".
                reason = ("no interior AC peak: the response is still rising "
                          "at the sweep edge, so `meas ac MAX` reports the "
                          "boundary rather than a peak (G44)")
                first_bad = first_bad or reason
                bad_point = bad_point or sp.label
                results.append(PointResult(sp.label, False, reason=reason))
                continue
            m_ac = {"f_peak_oct": f_peak_octaves(float(pt.f_pk_hz)),
                    "peaking_db": float(pt.peaking_db)}
            annotate_interpolated_peak(m_ac, None, pt)
            m_ac = scored_meas(m_ac, ac_peak_interp)
            results.append(PointResult(
                sp.label, True, f_peak_oct=float(m_ac["f_peak_oct"]),
                peaking_db=float(m_ac["peaking_db"])))
            continue

        if validity_gate:
            # **THE G44 VALIDITY GATE, IMPORTED AND NOT RESTATED** (rule 9).
            # `rl/evaluator.validate` is this project's one definition of
            # "is this measurement trustworthy". `design.py`, `baselines.py`
            # and `rl/env.py` have always reached it; this function never did,
            # so a response still RISING at 20 GHz -- `meas ac MAX` returns the
            # range edge and `peaking_db` is fictitious (G44) -- was scored as
            # a merely-bad CTLE at about -2 instead of an invalid one at -16.
            #
            # **Measured before this was added** (`PREDICTIONS.md` entry 43,
            # 138 decks): no accepted design and neither published compliance
            # design moves, because `S3_f_peak_band` already rejects 19.95 GHz
            # by 6-8 tolerances. What moves is the TRAINING SIGNAL: 58.8 % of
            # entry 41's SAC proposals and 44.4 % of a straight line between
            # two real CTLEs live in that mis-labelled region, and that is
            # where the policy converged.
            #
            # **Only `INVALID` rejects.** `HEADROOM_ONLY` means the `.op` is
            # trustworthy and the device is out of saturation, which this
            # function already scores through its own `saturation` /
            # `tail_saturation` rows -- routing it here would count one failure
            # twice and erase the gradient over the low-peaking region
            # (`evaluator.validate`'s own docstring says why).
            #
            # **Default OFF.** Every published accept rate, coverage sweep and
            # compliance table was produced without it, and CMA-ES is
            # path-dependent (G121), so flipping the default would stop
            # committed runs reproducing for zero change in any verdict.
            # Callers that want it say so, and the call site shows it.
            verdict, why = validate(pt, point)
            if verdict is Verdict.INVALID:
                first_bad = first_bad or f"validity gate: {why}"
                bad_point = bad_point or sp.label
                results.append(PointResult(sp.label, False,
                                           reason=f"validity gate: {why}"))
                continue

        dev = device_result_from_point(pt)
        if not dev.ok:
            first_bad = first_bad or dev.fail_reason
            bad_point = bad_point or sp.label
            results.append(PointResult(sp.label, False, reason=dev.fail_reason))
            continue

        meas = {
            "g_dc_db": dev.g_dc_db, "peaking_db": dev.peaking_db,
            "f_peak_oct": f_peak_octaves(float(dev.f_peak_hz)),
            "nyq_boost_db": float(pt.nyquist_boost_db),
            "inoise_vrms": dev.vn_in_vrms, "power_w": dev.power_w,
            "pair_margin_v": float(pt.vds) - float(pt.vdsat),
            "tail_margin_v": float(pt.tail_margin_v),
        }
        annotate_interpolated_peak(meas, None, pt)
        meas = scored_meas(meas, ac_peak_interp)

        lr = evaluate_link(dev, cfg)
        # **An uncomputable eye only makes the point UNSCORABLE if the spec set
        # actually asks for the eye.** Session 23: scoring `V6D_SPECS` -- the
        # device rows, which is all `rl/env.py` can measure -- every point on
        # every arm came back at the invalid floor, because the link fit is
        # rejected whenever the stage is driven past its linear range (G103:
        # peaking and drive handling are one knob, so a 10 dB request
        # guarantees it). That is a real property of the CIRCUIT and it was
        # being reported as a property of the SEARCH, with all four benchmark
        # arms pinned at -16.0 and no gradient between them.
        #
        # A caller not scoring S8 must not be blocked by S8's instrument. The
        # eye's absence is still RECORDED (`eye_h_v` stays None) so nothing can
        # later mistake "not asked for" for "measured and fine".
        needs_eye = any(k in specs for k in R.S8_SPECS)
        if not lr.ok and needs_eye:
            first_bad = first_bad or lr.fail_reason
            bad_point = bad_point or sp.label
            results.append(PointResult(sp.label, False, reason=lr.fail_reason))
            continue

        rb = R.reward(meas, target_f_peak_hz, specs=specs,
                      link=(lr if lr.ok else None),
                      target_peaking_db=target_peaking_db,
                      area_mm2=dev.area_mm2, hd3_nyq_dbc=dev.hd3_dbc)
        pr = PointResult(
            sp.label, True, reward=float(rb.reward),
            feasible=bool(rb.feasible),
            margins={k: float(v) for k, v in rb.margins.items()},
            worst_spec=rb.worst_spec, f_peak_oct=float(meas["f_peak_oct"]),
            peaking_db=float(meas["peaking_db"]), power_w=dev.power_w,
            hd3_nyq_dbc=dev.hd3_dbc,
            eye_h_v=(lr.eye_h_v if lr.ok else None),
            eye_w_ui=(lr.eye_w_ui if lr.ok else None),
            reason=(None if lr.ok else lr.fail_reason))
        # **The channel axis, for one SPICE run.** Asked for explicitly or not
        # computed at all, so no existing caller changes behaviour or pays for
        # it. Scoring still uses `lr` at `FUNNEL_LOSS_DB`; these are recorded
        # beside it, never instead of it.
        if link_losses_db is not None:
            by = {}
            for loss in link_losses_db:
                lcfg = LinkConfig(channel_loss_db_at_nyquist=float(loss))
                lx = evaluate_link(dev, lcfg)
                by[float(loss)] = {
                    "ok": bool(lx.ok),
                    "eye_h_v": (float(lx.eye_h_v) if lx.ok else None),
                    "eye_w_ui": (float(lx.eye_w_ui) if lx.ok else None),
                    "reason": (None if lx.ok else lx.fail_reason)}
            pr.links_by_loss = by
        results.append(pr)
        if worst is None or pr.reward < worst.reward:
            worst = pr

    n_scorable = sum(1 for r in results if r.ok)

    if ac_only:
        return DesignEval(u=u, ok=(n_scorable == n_points), reward=0.0,
                          feasible=False, n_sims=n_sims, n_points=n_points,
                          n_scorable=n_scorable, points=results,
                          reason=(None if n_scorable == n_points else first_bad),
                          worst_point=bad_point)

    if n_scorable < n_points or worst is None:
        r = R.invalid_reward(len(specs)) + n_scorable / max(n_points, 1)
        return DesignEval(
            u=u, ok=False, reward=float(r), feasible=False, n_sims=n_sims,
            n_points=n_points, n_scorable=n_scorable, points=results,
            worst_point=bad_point,
            reason=(f"{n_points - n_scorable} of {n_points} points "
                    f"unscorable; first: {first_bad}"),
            margins=(worst.margins if worst else {}))

    return DesignEval(
        u=u, ok=True, reward=worst.reward, feasible=all(r.feasible for r in results),
        n_sims=n_sims, n_points=n_points, n_scorable=n_scorable,
        worst_point=worst.label, worst_spec=worst.worst_spec,
        margins=worst.margins, points=results,
        peaking_db=worst.peaking_db,
        f_peak_hz=(2.5e9 * 2.0 ** worst.f_peak_oct
                   if worst.f_peak_oct is not None else None),
        power_w=worst.power_w, hd3_nyq_dbc=worst.hd3_nyq_dbc,
        eye_h_v=worst.eye_h_v, eye_w_ui=worst.eye_w_ui)


# ─────────────────────────────────────────────────────────────────────────────
# The spread probe.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Spread:
    """How far a design's peak travels across PVT, and whether that fits.

    `slack_oct` is the headroom left in S3's window **after a perfect
    re-centring** — the best any amount of further tuning could achieve. It is
    the number that decides whether a design is worth a full evaluation.
    """

    ok: bool
    spread_oct: float = float("inf")
    lo_oct: float = 0.0
    hi_oct: float = 0.0
    slack_oct: float = float("-inf")
    n_sims: int = 0
    reason: Optional[str] = None
    #: **Peaking, measured by the same two AC decks.** The probe always had
    #: this number and threw it away, so `choose_start` could only rank
    #: candidates on FREQUENCY -- and an 8 dB request would happily start from
    #: a 5 dB design that sat near the right frequency, then have to climb 3 dB,
    #: which drags the peak up because peaking and peak frequency are
    #: multiplicatively coupled through the same `Rs`. Measured signature of
    #: that: every high-boost coverage failure missed with boost LOW and
    #: frequency HIGH, on both axes, every time.
    peaking_lo_db: float = 0.0
    peaking_hi_db: float = 0.0

    @property
    def worth_evaluating(self) -> bool:
        return self.ok and self.spread_oct <= MAX_SPREAD_OCT


def probe_spread(u: Sequence[float],
                 points: Sequence[ScreenPoint] = SPREAD_PROBE,
                 ac_peak_interp: bool = True) -> Spread:
    """**2 AC-only SPICE runs that answer the question that decides the design.**

    Session 23 measured that S3's window is exactly 1.000 octave and that a
    typical design's peak travels 0.94-1.02 octaves across the 135-point grid.
    So "is there any room at all?" is answerable from **two** points — the two
    that bracket the grid — before spending a full 4-point, 11-row evaluation
    on a design that cannot fit however well it is centred.
    """
    ev = evaluate_at_points(u, points, ac_only=True,
                            ac_peak_interp=ac_peak_interp)
    octs = [p.f_peak_oct for p in ev.points if p.ok and p.f_peak_oct is not None]
    if len(octs) < len(list(points)):
        return Spread(ok=False, n_sims=ev.n_sims,
                      reason=ev.reason or "probe point unscorable")
    lo, hi = min(octs), max(octs)
    spread = hi - lo
    pks = [p.peaking_db for p in ev.points
           if p.ok and p.peaking_db is not None]
    return Spread(ok=True, spread_oct=spread, lo_oct=lo, hi_oct=hi,
                  slack_oct=1.0 - spread, n_sims=ev.n_sims,
                  peaking_lo_db=(min(pks) if pks else 0.0),
                  peaking_hi_db=(max(pks) if pks else 0.0))


# ─────────────────────────────────────────────────────────────────────────────
# The self-check: does the screen actually predict the full grid?
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ScreenAudit:
    """One comparison of the screen's verdict against the full 135 points."""

    screen_worst: float
    full_worst: float
    full_worst_label: str
    was_predictive: bool
    error: float
    added: list = field(default_factory=list)
    n_full_points: int = 0

    def summary(self) -> str:                                   # pragma: no cover
        v = "PREDICTIVE" if self.was_predictive else "MISSED"
        return (f"screen {self.screen_worst:+.6f} vs full {self.full_worst:+.6f} "
                f"at {self.full_worst_label} -> {v} (error {self.error:+.6f})")


def audit_screen(screen_eval: DesignEval,
                 full_points: Sequence[Mapping],
                 tol: float = 1e-9) -> ScreenAudit:
    """Compare a screen verdict against a full-grid result.

    `full_points` is a sequence of per-point records carrying `corner`,
    `vdd_scale`, `temp_c`, `cl_f` and `reward` — i.e. exactly the shape
    `exp_g4_verify.verify_full` writes, so the audit reads the artifact the
    compliance matrix is reported on rather than re-deriving anything.

    **The screen is predictive when its worst is no HIGHER than the truth.** A
    screen that is pessimistic is safe; one that is optimistic is the failure
    mode that put an infeasible design in the feasible band.
    """
    rows = [(float(p["reward"]),
             f"{p['corner']}/{float(p['vdd_scale']):.2f}/"
             f"{float(p['temp_c']):g}C/{float(p['cl_f']) * 1e15:.0f}fF", p)
            for p in full_points if p.get("reward") is not None]
    if not rows:
        raise ValueError("no scored points in the full-grid result; refusing "
                         "to report an audit against nothing")
    rows.sort(key=lambda r: r[0])
    full_worst, label, rec = rows[0]
    err = screen_eval.reward - full_worst
    predictive = err <= tol
    added: list[ScreenPoint] = []
    if not predictive:
        added.append(ScreenPoint(
            Corner(process=str(rec["corner"]),
                   vdd_scale=float(rec["vdd_scale"]),
                   temp_c=float(rec["temp_c"])),
            float(rec["cl_f"]),
            f"ADDED BY SELF-CHECK: beat the screen by {err:+.6f}"))
    return ScreenAudit(screen_worst=screen_eval.reward, full_worst=full_worst,
                       full_worst_label=label, was_predictive=predictive,
                       error=err, added=added, n_full_points=len(rows))


class AdaptiveScreen:
    """The screen, plus the points the self-check has had to add to it.

    Starts at `EDGE4`. `extend()` appends whatever an audit found; the search
    keeps running with the wider screen. **The audit history is the reported
    artifact** — a run in which the screen was never extended is EVIDENCE FOR
    the screen, and is only evidence at all because the check ran.
    """

    def __init__(self, points: Sequence[ScreenPoint] = EDGE4):
        self.points: list[ScreenPoint] = list(points)
        self.audits: list[ScreenAudit] = []

    @property
    def n_points(self) -> int:
        return len(self.points)

    def extend(self, audit: ScreenAudit) -> int:
        """Record an audit; append any point it found. Returns how many."""
        self.audits.append(audit)
        have = {p.label for p in self.points}
        new = [p for p in audit.added if p.label not in have]
        self.points.extend(new)
        return len(new)

    @property
    def n_predictive(self) -> int:
        return sum(1 for a in self.audits if a.was_predictive)

    def report(self) -> dict:
        """What the run says about its own screen. Never a claim without data."""
        return {
            "screen": [{"label": p.label, "why": p.why} for p in self.points],
            "n_points": self.n_points,
            "n_audits": len(self.audits),
            "n_predictive": self.n_predictive,
            "worst_error": (max((a.error for a in self.audits), default=None)),
            "audits": [{"screen_worst": a.screen_worst,
                        "full_worst": a.full_worst,
                        "full_worst_label": a.full_worst_label,
                        "was_predictive": a.was_predictive,
                        "error": a.error,
                        "added": [p.label for p in a.added]}
                       for a in self.audits],
        }


__all__ = [
    "ScreenPoint", "EDGE4", "EDGE4_MANDATED", "SPREAD_PROBE", "MAX_SPREAD_OCT",
    "SELF_CHECK_EVERY", "TARGET_F_PEAK_HZ", "TARGET_PEAKING_DB",
    "PointResult", "DesignEval", "evaluate_at_points",
    "Spread", "probe_spread",
    "ScreenAudit", "audit_screen", "AdaptiveScreen",
]
