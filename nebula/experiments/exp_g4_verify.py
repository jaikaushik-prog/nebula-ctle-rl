"""
experiments/exp_g4_verify.py — **G4: a corner-robust design, generated and
verified.**

THE GATE, VERBATIM
-------------------
`CLAUDEwa.md` §7: *"**G4** | Sep 12 | Corner-robust design generated and
verified; results table drafted."* And S9: *"TT, SS, FF, SF, FS x VDD +/-5% x
0-125 C. **All specs must hold at every corner.** A design that meets everything
at TT/27 C and fails at SS/125 C is a failed design and must score as such."*

**Generated** is already done and was not done by hand. The benchmark's P3 rung
scores every design on the worst of 3 screen corners x 2 loads, and its
`uniform` arm found **2 corner-and-load-robust designs in 20 seeds**
(`BASELINES.md` §12): rewards 8.0342 and 8.0021, both just above the
feasibility bonus of exactly 8.0. Their sizing vectors are read out of the run
log here rather than transcribed, so nothing in this file is a number a human
retyped.

**Verified** is what this file adds. The screen is 3 corners; S9 asks for 45.
Session 10d measured that the 3 screen corners capture **98.7 %** of what all
45 catch (G47) -- *a 1.3 % gap that has never been checked on a design that
actually survived the screen.*

    3 screen corners x 2 loads   =   6 evaluations  <- what the search saw
    45 corners x 3 loads         = 135 evaluations  <- what S9 actually asks

THE PREDICTION, WRITTEN BEFORE THE RUN
----------------------------------------
Committed with this file and before it was executed, per the pre-registration
rule; the run is ~1 minute, below the 10-minute threshold, so this stands in
place of a `PREDICTIONS.md` entry rather than beside one.

* **Both designs pass all 135 points.** G47's 98.7 % is a population statistic
  over the whole box, and these two survived a screen chosen precisely because
  it is the hard corner set. Confidence: moderate. Band: **at least 1 of 2**
  passes; 0 of 2 would mean the screen is not a screen.
* **The binding corner is one of the three screened ones**, and the binding
  spec is `S3_f_peak` at both -- which is what the P3 log already says at the
  screen corners, and the frequency margin is the row with no slack anywhere.
* **The two designs bind at OPPOSITE ends**: 8.0342 worst at ss/0.95/125C with
  the HIGH load, 8.0021 worst at ff/1.05/0C with the LOW load. If that survives
  to 45 corners it is the physical story for the report -- the peak frequency
  is pushed down by slow-hot-heavy and up by fast-cold-light, and a robust
  design is one placed where neither excursion leaves S3's window.

**THE CONTROL IS WHAT MAKES THIS A GATE.** A verification that only ever runs
on designs expected to pass cannot fail, and G73 is explicit that a gate whose
condition is unreachable is indistinguishable from a deleted one. So the same
135 points are run on designs that were feasible **at TT only** -- P1 winners
that the P3 rung never certified. **Those must fail**, and if they do not, the
corner axis is not measuring anything and every corner number in this project
needs re-reading.

NOTHING HERE IS TUNED, SEARCHED OR SELECTED. It re-simulates designs the
benchmark already found, at points the spec table already names.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.experiments.exp_g2_closed_loop import FUNNEL_LOSS_DB
from nebula.experiments.s9_yield import PROMOTION_LOADS, SCREEN_CORNERS, all_corners
from nebula.device.sky130_runner import run_point
from nebula.link.bridge import device_result_from_point, evaluate_link
from nebula.link.config import LinkConfig
from nebula.rl.evaluator import build_point
from nebula.rl import reward_v1 as R
from nebula.rl.contract import N_ACTIONS, f_peak_octaves, sizing_from_u
from nebula.rl.evaluator import (
    SpiceBudget,
    Verdict,
    annotate_interpolated_peak,
    evaluate,
    scored_meas,
    scoring_meas,
)

HERE = Path(__file__).resolve().parent

#: Where the generated designs come from. The P3 arm of the published sweep.
SOURCE_LOG = HERE / "baselines_run_interp_grid.jsonl.gz"
OUT_PATH = HERE / "g4_verify_results.json"

#: The target every published run used, so the verification scores what the
#: search was scored on. Changing it would verify a different design problem.
from nebula.rl.spec_dist import LEGACY_TARGET  # noqa: E402


@dataclass(frozen=True)
class Candidate:
    """A design to verify, and the claim being made about it."""

    design_id: str
    u: tuple[float, ...]
    role: str                 # "robust" (the claim) or "nominal_only" (control)
    source: str               # method/replicate it came from
    claimed_reward: float
    claimed_worst_point: Optional[str]


def candidates(log: Path = SOURCE_LOG, n_control: int = 3) -> list[Candidate]:
    """Read the designs out of the run log. **Nothing is transcribed.**

    `robust` rows are P3-feasible: the benchmark scored them on the worst of
    3 screen corners x 2 loads and they cleared every spec there.

    `nominal_only` rows are the CONTROL: feasible on P1 (tt, cl_mid) and never
    certified at any corner. They are taken from the TOP of the P1 ranking, so
    the control is the strongest possible version of "optimised at nominal" --
    a weak nominal design failing at corners would prove nothing.
    """
    robust: dict[str, Candidate] = {}
    p1: list[tuple[float, dict]] = []
    with gzip.open(log, "rt", encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row.get("event") != "trial" or not row.get("feasible"):
                continue
            if row.get("problem") == "P3":
                did = row["design_id"]
                if did not in robust:
                    robust[did] = Candidate(
                        design_id=did, u=tuple(float(x) for x in row["u"]),
                        role="robust",
                        source=f"{row['method']}/{row['replicate']}",
                        claimed_reward=float(row["reward"]),
                        claimed_worst_point=row.get("worst_point"))
            elif row.get("problem") == "P1" and not row.get("prescreen"):
                p1.append((float(row["reward"]), row))

    p1.sort(key=lambda t: -t[0])
    seen = set(robust)
    control: list[Candidate] = []
    for reward, row in p1:
        did = row["design_id"]
        if did in seen:
            continue
        seen.add(did)
        control.append(Candidate(
            design_id=did, u=tuple(float(x) for x in row["u"]),
            role="nominal_only",
            source=f"{row['method']}/{row['replicate']}",
            claimed_reward=reward, claimed_worst_point="tt/1.00/27C/cl_mid"))
        if len(control) >= n_control:
            break
    return list(robust.values()) + control


#: **The full slide.** `V3_SPECS` -- eleven rows, every line the competition's
#: own specification table lists. See `reward_v1.V3_SPECS` for why this is a
#: separate set from the one the search optimises.
FULL_SPECS = R.V3_SPECS


def _drive_headroom(pt, nyq_boost_db: float, cfg) -> dict:
    """The four drive-headroom fields, from the sweep `run_point` already ran.

    **Why the Nyquist de-rate is not an extra assumption.** A source-degenerated
    pair gets its linear input range from `Rs` and its peaking from `Cs`
    shorting that same `Rs` out at high frequency. So the measured peaking IS
    the measurement of how much degeneration survives at the signal band, and

        linear range at f  =  linear range at DC / |H(f)/H(0)|

    with the ratio read off the SAME `.ac` curve the peaking is read off. No
    new constant, no new simulation, one definition (rule 9).

    **THIS IS A READABLE PROXY, NOT THE GATE, and the difference is measured
    rather than assumed.** The gate in `link/bridge.py` compares the pulse
    response's own peak excursion (G61 convention C -- it carries the
    transmitter, the channel and the CTLE, so it needs no decision about which
    input level pairs with which gain) against the measured output limit. This
    number instead pairs the long-run input level with a single-frequency
    de-rate. Measured on the delivered design over all 135 points: this reads
    **1.18x to 1.26x (median 1.24x) HIGHER** than the gate's ratio, i.e. it is
    consistently the STRICTER of the two, and the two agree on the verdict at
    **135 of 135** points. Reported because "the drive is 3.1x the linear
    input range at the signal band" is a sentence a reader can act on and
    "output swing 903 mVpp exceeds the linear limit 333 mVpp" is not; used as
    a gate it would be wrong, and it is not used as one.
    """
    from nebula.device.sky130_runner import measured_linear_input_pp_v

    lin_dc = measured_linear_input_pp_v(pt)
    drive = float(cfg.v_in_diff_pp_v)
    if lin_dc is None:
        # Not reached inside the swept range -- a LOWER bound, never a
        # computed fallback. Absent stays absent (rule 1).
        return {"linear_in_dc_pp_v": None, "linear_in_nyq_pp_v": None,
                "drive_pp_v": drive, "drive_overdrive_x": None}
    lin_nyq = lin_dc / (10.0 ** (nyq_boost_db / 20.0))
    return {"linear_in_dc_pp_v": float(lin_dc),
            "linear_in_nyq_pp_v": float(lin_nyq),
            "drive_pp_v": drive,
            "drive_overdrive_x": float(drive / lin_nyq)}


@dataclass
class FullPointResult:
    """One (corner, load) point scored against ALL ELEVEN spec rows.

    `verify()` scores the seven the search optimises. This scores those plus
    S4 (HD3), S7 (area) and both S8 (eye) rows -- the three lines a judge
    holding the competition slide would otherwise find blank.
    """

    corner: str
    vdd_scale: float
    temp_c: float
    cl_f: float
    ok: bool
    reason: Optional[str]
    margins: dict
    failed_specs: list
    reward: float
    feasible: bool
    measured_specs: list = field(default_factory=list)
    unmeasured_specs: list = field(default_factory=list)
    hd3_dbc: Optional[float] = None
    area_mm2: Optional[float] = None
    vout_swing_v: Optional[float] = None
    eye_h_v: Optional[float] = None
    eye_w_ui: Optional[float] = None
    # ── which peak this row was scored on (session 22u) ─────────────────────
    #
    # **Both peaks, on every point, so the artifact states its own instrument.**
    # Until 22u this checklist read `pt.f_pk_hz` -- the `ac dec 50` lattice --
    # while `verify()` in the same file read the interpolated one. Recording
    # the pair makes the correction auditable from the artifact instead of
    # from a scratch script, and makes it impossible for a future reader to
    # have to guess which number a published margin came from.
    #
    #: `log2(f_pk / 1.7678 GHz)` off the raw `meas ac MAX` lattice reading.
    f_peak_oct_lattice: Optional[float] = None
    #: The same, off the parabola -- and the one the margins above use.
    f_peak_oct_scored: Optional[float] = None
    peaking_db_lattice: Optional[float] = None
    peaking_db_scored: Optional[float] = None
    #: `"vertex"`, `"boundary_bottom_lattice_is_exact"`, `"refused"`, or None
    #: when the interpolation was not asked for. **"not asked" and "asked and
    #: impossible" are different facts** and must not collapse (G85).
    peak_interp_status: Optional[str] = None
    # ── the drive-headroom row (session 22q) ────────────────────────────────
    #
    # S8 is blocked at every one of these points, and until now the blockage
    # was reported only in OUTPUT volts -- a number a reader has to divide by
    # a gain they must go and look up before it can be compared with anything
    # the link does. These four fields state the same fact on the INPUT axis,
    # in the units `PCIE_GEN2_TX_DIFF_PP_MIN_V` is written in, and cost **no
    # extra simulation**: `run_point(swing=True)` already ran here.
    #
    #: 1 dB gain compression, differential input Vpp, measured on the `.dc`
    #: transfer curve -- so it is the DEGENERATED linear range, i.e. at DC.
    linear_in_dc_pp_v: Optional[float] = None
    #: The same range **de-rated by the measured Nyquist boost**. The
    #: degeneration that buys the linear range is exactly what `Cs` shorts out
    #: to make the peaking, so the two are one knob read in opposite
    #: directions and the number the EYE sees is this one, not the one above.
    linear_in_nyq_pp_v: Optional[float] = None
    #: What the link layer actually drives this input with, same units.
    drive_pp_v: Optional[float] = None
    #: `drive / linear_in_nyq`. **> 1 means the stage is being driven past its
    #: linear range at the frequency the data lives at**, which is the S8
    #: blockage, stated as one number.
    drive_overdrive_x: Optional[float] = None


def verify_full(cand: "Candidate",
                corners: Optional[Sequence] = None,
                loads: Sequence[float] = PROMOTION_LOADS,
                loss_db: float = FUNNEL_LOSS_DB,
                ac_peak_interp: bool = True) -> dict:
    """**Every spec row on the slide, at every corner.** The judge's checklist.

    Runs the G2 closed-loop chain rather than the search evaluator, because
    three of the eleven rows are not in the search's measurement vector:

        run_point(swing=True, ac_sweep=True, hd3=True)   <- S4 needs the transient
          -> device_result_from_point()                  <- carries hd3 and area
            -> evaluate_link()                           <- S8, no extra SPICE

    `G2_RESULTS.md` measured the cost: 0.2787 s at full fidelity against
    0.1768 s for the search's `.op+.ac+.noise`, plus 0.0372 s of link
    evaluation with **no** simulator call -- the eye is computed from the AC
    curve the same invocation already produced.

    **`ac_peak_interp` defaults to True, and it did not used to exist (session
    22u).** `verify()` below has scored the sub-lattice interpolated peak since
    session 22e; this path did not, so the two verification routines in this
    one file disagreed about which peak they read, and the 135-point compliance
    matrix -- the artifact every S8 result and every margin number is reported
    on -- was the one still on the `ac dec 50` lattice. That is G74's defect,
    surviving in the place it mattered most, and rule 9's failure (two
    definitions of one quantity) in the place rule 9 was written for.

    **The cost was not the size of the correction.** One lattice step is 13.3 %
    of `S3_f_peak`'s tolerance, so the headline margin moved by a fraction of
    a step. What the lattice did was collapse **six physically distinct corners
    onto one tied margin**, so the matrix reported a six-way tie where the
    finer instrument reports an ordering that is monotone in process and in
    supply -- and the open decision it feeds is a decision about *which*
    corners.

    **Only the SCORED measurement vector changes.** `dev`, and therefore the
    eye, is untouched: `evaluate_link` fits the whole AC curve rather than
    reading the peak scalar, so S8 does not move and cannot be made to move by
    this flag. Kept as an argument, defaulting to the correct value, so the
    lattice behaviour stays reproducible for anyone re-deriving a published
    number -- the same shape as `verify()`.

    **No short-circuit**, for the same reason `verify` has none: a verification
    has to say WHICH rows failed and by how much.
    """
    corners = list(corners if corners is not None else all_corners())
    cfg = LinkConfig(channel_loss_db_at_nyquist=loss_db)
    rows: list[FullPointResult] = []
    for c in corners:
        for cl in loads:
            sizing = sizing_from_u(np.asarray(cand.u), cl_f=float(cl))
            base = dict(corner=c.process, vdd_scale=c.vdd_scale,
                        temp_c=c.temp_c, cl_f=float(cl))
            try:
                point, _ = build_point(sizing, corner=c.process,
                                       vdd_scale=c.vdd_scale)
            except Exception as exc:                        # noqa: BLE001
                rows.append(FullPointResult(
                    **base, ok=False, reason=f"unrealisable geometry: {exc}",
                    margins={}, failed_specs=list(FULL_SPECS),
                    reward=float("nan"), feasible=False))
                continue
            pt = run_point(point, c.process, temp_c=c.temp_c, swing=True,
                           ac_sweep=True, hd3=True,
                           ac_peak_interp=ac_peak_interp)
            if not pt.ok:
                rows.append(FullPointResult(
                    **base, ok=False, reason=pt.fail_reason, margins={},
                    failed_specs=list(FULL_SPECS), reward=float("nan"),
                    feasible=False))
                continue
            dev = device_result_from_point(pt)
            if not dev.ok:
                rows.append(FullPointResult(
                    **base, ok=False, reason=dev.fail_reason, margins={},
                    failed_specs=list(FULL_SPECS), reward=float("nan"),
                    feasible=False))
                continue
            lr = evaluate_link(dev, cfg)
            meas = {
                "g_dc_db": dev.g_dc_db, "peaking_db": dev.peaking_db,
                "f_peak_oct": f_peak_octaves(float(dev.f_peak_hz)),
                # **Read off `pt` exactly as `rl/evaluator` reads them, not
                # re-derived.** `DeviceResult` carries neither the Nyquist
                # boost nor the saturation margins, and computing them a second
                # way here would be two definitions of one number (rule 9).
                "nyq_boost_db": float(pt.nyquist_boost_db),
                "inoise_vrms": dev.vn_in_vrms, "power_w": dev.power_w,
                "pair_margin_v": float(pt.vds) - float(pt.vdsat),
                "tail_margin_v": float(pt.tail_margin_v),
            }
            # **THE PEAK THIS CHECKLIST IS SCORED ON**, through the same two
            # functions the search arms and the RL env reach it by, so this
            # file cannot drift away from them again (session 22u, rule 9).
            # `annotate_` is additive; `scored_meas` performs the swap and, on
            # a refusal, falls back to the lattice rather than to the invalid
            # floor -- see `scoring_meas` for the measured reason (1 valid
            # design in 4543).
            lattice = {k: meas[k] for k in ("f_peak_oct", "peaking_db")}
            bookkeeping: dict = {}
            annotate_interpolated_peak(meas, bookkeeping, pt)
            meas = scored_meas(meas, ac_peak_interp)
            peak_audit = {
                "f_peak_oct_lattice": float(lattice["f_peak_oct"]),
                "f_peak_oct_scored": float(meas["f_peak_oct"]),
                "peaking_db_lattice": float(lattice["peaking_db"]),
                "peaking_db_scored": float(meas["peaking_db"]),
                "peak_interp_status": bookkeeping.get("peak_interp_status"),
            }
            m = R.margins(meas, LEGACY_TARGET.f_peak_hz,
                          target_peaking_db=LEGACY_TARGET.peaking_db,
                          link=(lr if lr.ok else None),
                          hd3_dbc=dev.hd3_dbc, area_mm2=dev.area_mm2)
            # **Per ROW, not all-or-nothing.** A row that cannot be
            # measured at this point must not make the other ten unscorable:
            # the first version of this returned "0 of 135 scorable" because
            # S8 was blocked everywhere, which is true and useless. A checklist
            # with nine ticks and two stated blockers is the deliverable; a
            # blank page is not.
            measured = [k for k in FULL_SPECS if k in m]
            unmeasured = [k for k in FULL_SPECS if k not in m]
            rb = R.reward(meas, LEGACY_TARGET.f_peak_hz, specs=tuple(measured),
                          target_peaking_db=LEGACY_TARGET.peaking_db, link=lr,
                          hd3_dbc=dev.hd3_dbc, area_mm2=dev.area_mm2)
            rows.append(FullPointResult(
                **base, ok=True,
                reason=(None if not unmeasured else
                        (lr.fail_reason if not lr.ok
                         else f"unmeasured: {unmeasured}")),
                margins={k: float(m[k]) for k in measured},
                measured_specs=measured, unmeasured_specs=unmeasured,
                failed_specs=[k for k in measured if m[k] < 0.0],
                reward=float(rb.reward), feasible=bool(rb.feasible),
                hd3_dbc=dev.hd3_dbc, area_mm2=dev.area_mm2,
                vout_swing_v=dev.vout_swing_v,
                eye_h_v=(lr.eye_h_v if lr.ok else None),
                eye_w_ui=(lr.eye_w_ui if lr.ok else None),
                **peak_audit,
                **_drive_headroom(pt, float(pt.nyquist_boost_db), cfg)))

    scored = [r for r in rows if r.ok]
    # **The checklist, per ROW.** Three counts per spec, and they mean
    # different things: how many points it was checked at, how many it failed,
    # and how many it could not be measured at. Collapsing the third into the
    # second would report a blocked spec as a failing one.
    per_spec = {}
    for name in FULL_SPECS:
        checked = sum(1 for r in scored if name in r.measured_specs)
        per_spec[name] = {
            "checked_at": checked,
            "failed_at": sum(1 for r in scored if name in r.failed_specs),
            "unmeasurable_at": sum(1 for r in scored
                                   if name in r.unmeasured_specs),
            "verdict": ("PASS" if checked and not any(
                name in r.failed_specs for r in scored)
                else "FAIL" if checked else "NOT MEASURABLE"),
        }
    blocked = sorted({r.reason.split("(")[0].strip()
                      for r in scored if r.reason})
    return {
        "design_id": cand.design_id, "role": cand.role,
        # **The artifact states its own instrument.** A margin quoted to four
        # decimals off a lattice that quantises this row at 13.3 % of its
        # tolerance is a different measurement from the same margin off the
        # parabola, and a reader must not have to infer which one they hold.
        "ac_peak_interp": bool(ac_peak_interp),
        "spec_set": list(FULL_SPECS), "n_spec_rows": len(FULL_SPECS),
        "n_points": len(rows), "n_scored": len(scored),
        "n_unscorable": len(rows) - len(scored),
        "n_rows_passing": sum(1 for v in per_spec.values()
                              if v["verdict"] == "PASS"),
        "n_rows_failing": sum(1 for v in per_spec.values()
                              if v["verdict"] == "FAIL"),
        "n_rows_not_measurable": sum(1 for v in per_spec.values()
                                     if v["verdict"] == "NOT MEASURABLE"),
        "n_failed": sum(1 for r in scored if r.failed_specs),
        "all_measured_rows_pass": bool(scored) and not any(
            r.failed_specs for r in scored),
        "per_spec": per_spec,
        "blocking_reasons": blocked,
        "median_vout_swing_v": float(np.median(
            [r.vout_swing_v for r in scored if r.vout_swing_v is not None])
            ) if any(r.vout_swing_v is not None for r in scored) else None,
        # **The drive-headroom row, across the grid.** Reported as a range
        # rather than a median because the point of it is the SPREAD: the
        # corner that compresses worst is the one that decides S8.
        "drive_headroom": _drive_headroom_summary(scored),
        "worst_reward": (min((r.reward for r in scored), default=float("nan"))),
        "channel_loss_db_at_nyquist": loss_db,
        "points": [asdict(r) for r in rows],
    }


def _drive_headroom_summary(scored: Sequence["FullPointResult"]) -> Optional[dict]:
    """Min/median/max of the drive-headroom row over the whole grid.

    `n_compressed` is the count that matters: how many of the 135 points are
    driven past their own linear range at the signal band. **It is reported
    even when it is 135 of 135** -- a blocked spec with a measured reason is a
    result, and the version of this checklist that reported only "S8 NOT
    MEASURABLE" was true and useless.
    """
    ov = [r.drive_overdrive_x for r in scored if r.drive_overdrive_x is not None]
    if not ov:
        return None
    dc = [r.linear_in_dc_pp_v for r in scored if r.linear_in_dc_pp_v is not None]
    ny = [r.linear_in_nyq_pp_v for r in scored if r.linear_in_nyq_pp_v is not None]
    dr = [r.drive_pp_v for r in scored if r.drive_pp_v is not None]
    return {
        "n_points_with_a_measured_limit": len(ov),
        "n_points_without_one": len(scored) - len(ov),
        "drive_pp_v": float(np.median(dr)),
        "linear_in_dc_pp_v": {"min": float(np.min(dc)),
                              "median": float(np.median(dc)),
                              "max": float(np.max(dc))},
        "linear_in_nyq_pp_v": {"min": float(np.min(ny)),
                               "median": float(np.median(ny)),
                               "max": float(np.max(ny))},
        "overdrive_x": {"min": float(np.min(ov)),
                        "median": float(np.median(ov)),
                        "max": float(np.max(ov))},
        "n_compressed": int(sum(1 for v in ov if v > 1.0)),
    }


@dataclass
class PointResult:
    corner: str
    vdd_scale: float
    temp_c: float
    cl_f: float
    reward: float
    feasible: bool
    valid: bool
    verdict: str
    worst_spec: Optional[str]


def verify(cand: Candidate, budget: SpiceBudget,
           corners: Optional[Sequence] = None,
           loads: Sequence[float] = PROMOTION_LOADS,
           ac_peak_interp: bool = True) -> dict:
    """Every (corner, load) point, no short-circuit.

    **The short-circuit is deliberately NOT used here**, unlike in the search
    loop. A search stops early because nothing below the floor exists and the
    remaining simulations buy nothing; a VERIFICATION has to be able to say
    *which* points failed and by how much, and a run that stops at the first
    failure cannot. This is the one place the extra simulations are worth it.
    """
    corners = list(corners if corners is not None else all_corners())
    rows: list[PointResult] = []
    for c in corners:
        for cl in loads:
            sizing = sizing_from_u(np.asarray(cand.u), cl_f=float(cl))
            ev = evaluate(sizing, budget, corner=c.process, temp_c=c.temp_c,
                          vdd_scale=c.vdd_scale, ac_peak_interp=ac_peak_interp)
            rb = R.reward(scoring_meas(ev, ac_peak_interp),
                          LEGACY_TARGET.f_peak_hz,
                          target_peaking_db=LEGACY_TARGET.peaking_db,
                          headroom=(ev.headroom if ev.verdict
                                    is Verdict.HEADROOM_ONLY else None))
            rows.append(PointResult(
                corner=c.process, vdd_scale=c.vdd_scale, temp_c=c.temp_c,
                cl_f=float(cl), reward=float(rb.reward),
                feasible=bool(rb.feasible), valid=bool(ev.valid),
                verdict=ev.verdict.value, worst_spec=rb.worst_spec))

    worst = min(rows, key=lambda r: r.reward)
    failed = [r for r in rows if not r.feasible]
    screen_labels = {(c.process, c.vdd_scale, c.temp_c) for c in SCREEN_CORNERS}
    failed_outside_screen = [
        r for r in failed
        if (r.corner, r.vdd_scale, r.temp_c) not in screen_labels]
    return {
        "design_id": cand.design_id, "role": cand.role, "source": cand.source,
        "claimed_reward": cand.claimed_reward,
        "claimed_worst_point": cand.claimed_worst_point,
        "u": list(cand.u),
        "n_points": len(rows), "n_corners": len(corners), "n_loads": len(loads),
        "n_failed": len(failed),
        "n_failed_outside_the_screen": len(failed_outside_screen),
        "all_points_pass": not failed,
        "worst_reward": worst.reward,
        "worst_point": f"{worst.corner}/{worst.vdd_scale:.2f}/"
                       f"{worst.temp_c:.0f}C/cl={worst.cl_f * 1e15:.1f}fF",
        "worst_spec": worst.worst_spec,
        "worst_is_a_screen_corner": (worst.corner, worst.vdd_scale,
                                     worst.temp_c) in screen_labels,
        "points": [asdict(r) for r in rows],
    }


def run(n_control: int = 3, out_path: Path = OUT_PATH) -> dict:
    cands = candidates(n_control=n_control)
    budget = SpiceBudget()
    t0 = time.perf_counter()
    results = []
    for c in cands:
        r = verify(c, budget)
        results.append(r)
        print(f"  {r['role']:<13} {r['design_id'][:12]:<14} "
              f"{'PASS' if r['all_points_pass'] else 'FAIL':<5} "
              f"{r['n_failed']:>3}/{r['n_points']} points failed  "
              f"worst {r['worst_reward']:8.4f} at {r['worst_point']}"
              f"  ({r['worst_spec']})", flush=True)
    out = {
        "task": "G4 -- corner-robust design generated and verified",
        "target": {"peaking_db": LEGACY_TARGET.peaking_db,
                   "f_peak_hz": LEGACY_TARGET.f_peak_hz},
        "grid": {"n_corners": 45, "loads_f": list(PROMOTION_LOADS),
                 "screen_corners": [str(c) for c in SCREEN_CORNERS]},
        "wall_s": time.perf_counter() - t0,
        "simulations": budget.calls,
        "results": results,
    }
    out_path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"\n  {budget.calls} simulations, {out['wall_s'] / 60:.1f} min")
    print(f"wrote {out_path}")
    return out


FULL_OUT_PATH = HERE / "g4_verify_full_results.json"


def run_full(n_control: int = 0, out_path: Path = FULL_OUT_PATH) -> dict:
    """The eleven-row checklist, at 45 corners x 3 loads."""
    cands = candidates(n_control=n_control)
    t0 = time.perf_counter()
    results = []
    for c in cands:
        r = verify_full(c)
        results.append(r)
        print(f"  {r['role']:<13} {r['design_id'][:12]:<14} "
              f"{r['n_rows_passing']} rows PASS, "
              f"{r['n_rows_failing']} FAIL, "
              f"{r['n_rows_not_measurable']} not measurable "
              f"(over {r['n_scored']}/{r['n_points']} points)", flush=True)
        for name in r["spec_set"]:
            v = r["per_spec"][name]
            print(f"        {name:<16} {v['verdict']:<15} "
                  f"checked {v['checked_at']:>3}  failed {v['failed_at']:>3}  "
                  f"unmeasurable {v['unmeasurable_at']:>3}")
        for b in r["blocking_reasons"]:
            print(f"        blocked: {b[:96]}")
    out = {"task": "G4 -- every spec row on the competition slide",
           "spec_set": list(FULL_SPECS), "results": results,
           "wall_s": time.perf_counter() - t0}
    out_path.write_text(json.dumps(out, indent=1, default=str),
                        encoding="utf-8")
    print(f"  {out['wall_s'] / 60:.1f} min")
    print(f"wrote {out_path}")
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--list", action="store_true",
                    help="which designs would be verified; no SPICE")
    ap.add_argument("--controls", type=int, default=3)
    ap.add_argument("--full", action="store_true",
                    help="score ALL ELEVEN spec rows (V3_SPECS) at every "
                         "corner -- the competition slide's own checklist. "
                         "Adds the HD3 transient and the link evaluation, so "
                         "~0.3 s per point against ~0.2 s.")
    args = ap.parse_args(argv)
    if not (args.run or args.list or args.full):
        ap.error("choose --list, --run or --full")
    if args.list:
        for c in candidates(n_control=args.controls):
            print(f"  {c.role:<13} {c.design_id[:14]:<16} from {c.source:<12} "
                  f"claimed {c.claimed_reward:8.4f} "
                  f"worst at {c.claimed_worst_point}")
    if args.run:
        run(n_control=args.controls)
    if args.full:
        run_full(n_control=args.controls)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
