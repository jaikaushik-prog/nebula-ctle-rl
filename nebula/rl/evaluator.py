"""
rl/evaluator.py — one sizing point -> a VALIDATED measurement vector, or a
named invalidity. Nothing in between.

WHY THIS IS THE HIGHEST-RISK FILE IN THE TASK
----------------------------------------------
An RL policy is an adversarial search for regions where the reward is high.
A garbage result that happens to score well is free reward, so the policy will
find it and live there — and every one of this repo's documented ngspice
failure modes produces exactly that: a plausible number, a clean parse, and
exit code 0.

The catalogue this file is written against, all measured, none of them
raising anything on their own:

  G26  `let` failures are WARNINGS and the run exits 0
  G30  `.param` names are not visible as `.control` vectors; exits 0
  G35  `alter` on subckt geometry returns STALE values; exits 0
  G54  `.noise` can return `inoise_total = -nan(ind)`; exits 0
  G56  `mult=` is silently ignored
  G57  `w=` is silently ignored on the fixed-width resistor families
  G44  `meas ac MAX` reports the SWEEP EDGE as a peak

The last one is the one an optimiser loves most: a response still rising at
20 GHz reports a large `peaking_db` at a frequency that is not a peak. Under
reward v0 (S3 peaking) that is a high score for a circuit with no peak at all.

THE RULE THAT REPLACED THE FIRST ONE
-------------------------------------
The first version of this module was two-valued: VALID or INVALID. That was
wrong in a specific and costly way, and the correction is the organising idea
of the file.

**A validity gate answers "can I trust this measurement?" A reward answers "is
this circuit good?" Conflating them destroys the gradient exactly where a
fresh policy lives.** Two results can look identical — no usable AC spec set —
and need opposite handling:

  * a peak reported at 19.95 GHz is an UNTRUSTWORTHY measurement. `meas ac MAX`
    returned the edge of its own search range; the number is fiction. Nothing
    can be scored from it.
  * a device in TRIODE is a trustworthy measurement of a bad circuit. `.op`
    converged; `vds` and `vdsat` are both real. What is untrustworthy is only
    the AC-derived spec set, because the small-signal response of a device in
    triode describes a circuit nobody asked for.

So trustworthiness is **per analysis**, not per evaluation, and there are three
verdicts:

    VALID          .op and .ac both trustworthy. Full measurement vector.
    HEADROOM_ONLY  .op converged and its primitives are trustworthy, but a
                   device is out of saturation, so the AC spec set is DROPPED
                   and only the DC headroom margins survive. Graded reward,
                   ordered by how far into triode it is.
    INVALID        nothing is trustworthy. Floor, no gradient, nothing to say.

Why this matters rather than being tidy: `tail_saturation` binds on 2.6-13.3 %
of the box, so a fresh policy lands in triode often, and a FLAT floor there
gives it no direction out. The graded band is the way out, and it is graded on
`vds - vdsat`, which is a `.op` quantity and therefore still true.

An invalid result is NEVER:
  * a missing value the observation fills with a default,
  * a clamped value ("the swing can't exceed the supply, so use the supply"),
  * a retry that quietly succeeds with different numbers.

The retry point deserves its own sentence, because `s9_yield.py` DOES retry
once and is right to (G45: transient Windows process-launch failures do not
reproduce). The difference is what the retry is allowed to do. There, a retry
that succeeds replaces a failure. Here, a retry that succeeds with DIFFERENT
numbers would mean the environment is non-deterministic in a way the policy
can exploit, so this module retries only on a **launch-shaped** failure and
counts every retry as a SPICE call in the cost accounting either way.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Sequence

from nebula.device.crosscheck import (
    derived_ac,
    find_device_scalar,
    parse_meas,
    parse_scalar,
)
from nebula.device.passives import PassiveGeometry, to_geometry
from nebula.device.sky130_runner import (
    Sky130Point,
    SizingPoint,
    run_point,
)
from nebula.device.tail import TailDevice, TailGeometryError
from nebula.rl.contract import (
    CL_CONTEXT_F,
    TAIL_MIRROR_RATIO,
    VDD_NOMINAL_V,
    Sizing,
    design_id,
    f_peak_octaves,
)

# ─────────────────────────────────────────────────────────────────────────────
# Plausibility limits. Every one is a PHYSICAL bound, not a tuned threshold —
# a number outside these describes a circuit that does not exist, not a bad
# design. They are deliberately GENEROUS: this is a validity gate, not a spec
# check, and tightening it would silently do the reward's job.
# ─────────────────────────────────────────────────────────────────────────────

#: |H| outside this at any measured frequency is not an amplifier.
G_DB_LIMITS: tuple[float, float] = (-80.0, 60.0)

#: `meas ac MAX` searches to 20 GHz (`MAX_SEARCH_TOP_HZ`). A peak within this
#: factor of the edge is not distinguishable from the edge itself, so it is
#: rejected regardless of `has_interior_peak` — belt and braces on G44, because
#: G44's own guard is a 0.25 dB margin and 0.25 dB is inside the noise of a
#: `dec 50` grid.
F_PEAK_HZ_LIMITS: tuple[float, float] = (1e7, 1.8e10)

#: Input-referred noise. 1 nV_rms would mean the integration collapsed; 1 V_rms
#: means it diverged. S5's limit is 1.5 mV, three orders inside both.
NOISE_VRMS_LIMITS: tuple[float, float] = (1e-9, 1.0)

#: Supply current. The box tops out at 8 mA plus a mirror reference; 100 mA
#: means a short, and <= 0 means the supply is SOURCING current, which for an
#: NMOS-tail stage means the operating point is not the one requested.
I_SUPPLY_A_LIMITS: tuple[float, float] = (1e-6, 0.1)

#: How far outside the rails a DC node may sit before the operating point is
#: rejected. 50 mV of slack absorbs the diode drop of a legitimately-biased
#: node without admitting a node that has genuinely left the supply.
RAIL_SLACK_V: float = 0.05


class Verdict(str, Enum):
    """How much of one evaluation may be believed. See the module docstring."""

    VALID = "valid"
    HEADROOM_ONLY = "headroom_only"
    INVALID = "invalid"


@dataclass
class EvalResult:
    """One evaluation, classified. Read `verdict` before reading anything else.

    Deliberately mirrors `DeviceResult`'s ok/None invariant (`common/types.py`):
    numeric fields are `None` when they may not be believed, never `nan`,
    because `nan` propagates silently into a reward and `None` explodes on the
    first arithmetic.

        verdict           meas          headroom
        VALID             populated     populated
        HEADROOM_ONLY     **None**      populated
        INVALID           None          None

    `meas` is `None` on HEADROOM_ONLY **by construction, not by convention**:
    the AC spec set of a device in triode describes a different circuit, and
    the only way to guarantee nothing scores it is for it not to exist.
    """

    verdict: Verdict = Verdict.INVALID
    reason: Optional[str] = None
    #: The 8 channels of the observation's measurement block, in the units
    #: `contract.OBS_SCALES` declares. Populated ONLY on VALID.
    meas: Optional[dict] = None
    #: `.op`-derived headroom, populated on VALID and HEADROOM_ONLY. These are
    #: trustworthy whenever `.op` converged, in triode or out.
    headroom: Optional[dict] = None
    #: Everything else the reward and the log need, raw.
    raw: dict = field(default_factory=dict)
    design_id: Optional[str] = None
    geometry_tag: Optional[str] = None
    #: SPICE invocations this evaluation consumed, INCLUDING retries. Counted
    #: here so §6i's budget can never miss one.
    n_spice: int = 0
    seconds: float = 0.0
    #: Raw ngspice stdout+stderr, kept only when `keep_raw_text=True`, for the
    #: §6d independent cross-check sample.
    text: Optional[str] = None

    @property
    def valid(self) -> bool:
        """True only for a fully trustworthy evaluation.

        Kept so every existing caller and test keeps meaning what it meant: a
        HEADROOM_ONLY result is NOT valid, and must never reach code that
        expects `meas`.
        """
        return self.verdict is Verdict.VALID

    @property
    def scorable(self) -> bool:
        """True when the reward has SOMETHING real to grade — i.e. not the floor."""
        return self.verdict in (Verdict.VALID, Verdict.HEADROOM_ONLY)

    @classmethod
    def invalid(cls, reason: str, n_spice: int = 0, seconds: float = 0.0,
                design_id_: Optional[str] = None,
                geometry_tag: Optional[str] = None) -> "EvalResult":
        if not reason or not reason.strip():
            raise ValueError("an invalid result must name its reason")
        return cls(verdict=Verdict.INVALID, reason=reason, meas=None,
                   headroom=None, n_spice=n_spice, seconds=seconds,
                   design_id=design_id_, geometry_tag=geometry_tag)


# ─────────────────────────────────────────────────────────────────────────────
# Geometry.
# ─────────────────────────────────────────────────────────────────────────────


def geometry_tag(geo: PassiveGeometry) -> str:
    """A stable, human-readable key for one drawn passive set.

    Used as part of `design_id` so two continuous `rs` values that quantise
    onto the same resistor group together — they are the same silicon.
    """
    def _r(g) -> str:
        return f"{g.subckt.rsplit('__', 1)[-1]}:w{g.w_um:g}l{g.l_um:g}m{g.m}"
    return f"rs[{_r(geo.rs)}]cs[{_r(geo.cs)}]rl[{_r(geo.rl)}]"


def build_point(sizing: Sizing, corner: str = "tt",
                vdd_scale: float = 1.0,
                real_tail: bool = True,
                real_passives: bool = True
                ) -> tuple[SizingPoint, Optional[PassiveGeometry]]:
    """Sizing -> a `SizingPoint` carrying a real tail and drawn passives.

    Raises rather than returning a bad point: an ungrowable geometry is an
    invalidity the CALLER must name, and swallowing it here would let it become
    a silent default.

    **`real_tail` and `real_passives` DEFAULT TO THE PUBLISHED CONFIGURATION
    AND MUST STAY THAT WAY.** They exist for one purpose — session 22b's
    attribution of the 13.44 % -> 7.10 % S3-rate gap, which needs the SAME
    validation and the SAME scoring applied to the ideal-tail / ideal-passive
    configuration `experiments/s3_yield.py` measured on. Setting either False
    reproduces a LEGACY configuration; it is not a modelling option and nothing
    in the RL path or the benchmark may pass them.
    `test_build_point_defaults_are_byte_identical_to_the_published_path` is the
    gate (BASELINES.md §7f: touching the evaluator means re-running every
    baseline, and a default-off flag is how that is avoided).

    With `real_passives=False` there is no drawn geometry, so the second
    element is `None` and the caller gets no `geometry_tag` — which is correct
    rather than a gap: G67's `design_id` grouping is a property of drawn
    silicon and does not exist for ideal elements.
    """
    geo = (to_geometry(sizing.params["rs"], sizing.params["cs"],
                       sizing.params["rl"]) if real_passives else None)
    tail = (TailDevice(w_tail=sizing.w_tail_um, l_tail=sizing.l_tail_um,
                       nf_tail=sizing.nf_tail, mirror_ratio=TAIL_MIRROR_RATIO)
            if real_tail else None)
    point = SizingPoint.from_params(sizing.params,
                                    vdd=VDD_NOMINAL_V * vdd_scale,
                                    tail=tail, passives=geo)
    return point, geo


# ─────────────────────────────────────────────────────────────────────────────
# Validation. Every check names what it rejects and why it is not a spec.
# ─────────────────────────────────────────────────────────────────────────────


def _finite(name: str, v) -> Optional[str]:
    if v is None:
        return f"{name} is missing from the ngspice output"
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return f"{name} parsed as {type(v).__name__}, not a number"
    if not math.isfinite(float(v)):
        return f"{name} is {v} — nan/inf must never reach an observation (G54)"
    return None


def validate(pt: Sky130Point, point: SizingPoint) -> tuple[Verdict, Optional[str]]:
    """Classify one result. Returns `(verdict, reason)`; reason is None on VALID.

    **Trustworthiness is per ANALYSIS, not per evaluation.** The stages below
    run in order and each may only assume the earlier ones passed:

        A. `.op` parsed and is finite            -> else INVALID
        B. DC nodes inside the rails             -> else INVALID
        C. the device is ON                      -> else INVALID
        D. both devices in saturation            -> else HEADROOM_ONLY
        E. `.ac` / `.noise` parsed and plausible -> else INVALID

    Stage D is the one that changed. It used to return INVALID, which threw
    away a trustworthy `.op` because an untrusted `.ac` came with it — and a
    flat floor over a region that binds on 2.6-13.3 % of the box leaves a fresh
    policy no direction out. `vds` and `vdsat` both come from `.op`; if `.op`
    converged they are true whether or not the device is saturated. What is
    untrustworthy is only the AC spec set.

    The A-before-B-before-D ordering is load-bearing for a second reason: it
    reports the CAUSE rather than a symptom. `rl` at the box ceiling takes the
    pair out of saturation AND pushes the peak to the sweep edge; checked the
    other way round the log says "f_pk out of range", which sends whoever reads
    it to the wrong file.
    """
    if not pt.ok:
        return Verdict.INVALID, f"ngspice: {pt.fail_reason}"

    # ---- A. the `.op` primitives, present and finite ------------------------
    #
    # The tail is not optional. `run_point` already fails a run whose tail did
    # not parse, but an evaluator that would ACCEPT a missing tail margin is one
    # `tail=None` away from scoring the coupled inequality as
    # satisfied-by-absence.
    op_required = {
        "gm": pt.gm, "gmbs": pt.gmbs, "vth": pt.vth, "vds": pt.vds,
        "vdsat": pt.vdsat, "vgs": pt.vgs, "id_a": pt.id_a,
        "v_out_dc": pt.v_out_dc, "v_src_dc": pt.v_src_dc,
        "i_supply_a": pt.i_supply_a,
        "vds_tail": pt.vds_tail, "vdsat_tail": pt.vdsat_tail,
        "i_tail_meas_a": pt.i_tail_meas_a, "gm_tail": pt.gm_tail,
    }
    for name, value in op_required.items():
        why = _finite(name, value)
        if why:
            return Verdict.INVALID, why

    # ---- B. DC nodes inside the rails ---------------------------------------
    #
    # A node outside the rails on a converged `.op` means the netlist or the
    # topology is wrong, not that a device is in triode — so this is INVALID and
    # not HEADROOM_ONLY. There is no trustworthy headroom to grade when the bias
    # point is not physical.
    vdd = float(point.vdd)
    for name, v in (("v(outp)", pt.v_out_dc), ("v(s1)", pt.v_src_dc),
                    ("v(nbias)", pt.v_bias_dc)):
        if v is None:
            continue
        if not (-RAIL_SLACK_V <= float(v) <= vdd + RAIL_SLACK_V):
            return Verdict.INVALID, (
                f"DC node {name} = {float(v):.4f} V is outside the rails "
                f"[{-RAIL_SLACK_V:.2f}, {vdd + RAIL_SLACK_V:.2f}] V")

    # ---- C. the device is on ------------------------------------------------
    if float(pt.gm) <= 0.0:
        return Verdict.INVALID, (
            f"gm = {float(pt.gm):.4g} S is not positive — the device is off, so "
            f"there is no operating point to grade")

    # ---- D. saturation -> HEADROOM_ONLY, not INVALID -------------------------
    #
    # THE CALL 1 CHANGE. A device in triode is a TRUSTWORTHY measurement of a
    # BAD circuit: `.op` converged and `vds`/`vdsat` are real. Only the
    # AC-derived spec set has to be dropped, because the small-signal response
    # of a device in triode describes a circuit nobody asked for.
    pair_margin = float(pt.vds) - float(pt.vdsat)
    tail_margin = float(pt.vds_tail) - float(pt.vdsat_tail)
    if pair_margin <= 0.0 or tail_margin <= 0.0:
        who = []
        if pair_margin <= 0.0:
            who.append(f"input pair {pair_margin * 1e3:+.1f} mV")
        if tail_margin <= 0.0:
            who.append(f"tail {tail_margin * 1e3:+.1f} mV")
        return Verdict.HEADROOM_ONLY, (
            f"out of saturation ({', '.join(who)} of vds - vdsat). The `.op` is "
            f"trustworthy and is graded on headroom; the AC spec set is dropped "
            f"because a device in triode is not the circuit that was asked for")

    # ---- E. the `.ac` / `.noise` result -------------------------------------
    ac_required = {
        "g_dc_db": pt.g_dc_db, "g_nyq_db": pt.g_nyq_db, "g_pk_db": pt.g_pk_db,
        "f_pk_hz": pt.f_pk_hz, "g_top_db": pt.g_top_db,
        "vn_in_vrms": pt.vn_in_vrms,
    }
    for name, value in ac_required.items():
        why = _finite(name, value)
        if why:
            return Verdict.INVALID, why

    lo, hi = G_DB_LIMITS
    for name, v in (("g_dc_db", pt.g_dc_db), ("g_nyq_db", pt.g_nyq_db),
                    ("g_pk_db", pt.g_pk_db), ("g_top_db", pt.g_top_db)):
        if not lo <= float(v) <= hi:
            return Verdict.INVALID, (
                f"{name} = {float(v):.3g} dB is outside [{lo}, {hi}] — "
                f"not an amplifier")

    # THE SWEEP-EDGE TEST COMES BEFORE THE f_peak RANGE TEST, for the same
    # reason the operating point comes before the AC result: it names the
    # MECHANISM rather than the symptom. A response still rising at 20 GHz
    # reports `f_pk` near the edge, so the range test fires too — and then the
    # log says "f_pk out of range", which reads as a numerical oddity, instead
    # of "the peak is fictitious". Measured on the first trial run: 6 of 6
    # invalid evaluations were reported by the range test and the mechanism was
    # invisible.
    #
    # **The G44 half only**, NOT `has_interior_peak`. The two halves of that
    # property reject different things and only one of them is a broken
    # measurement (see `Sky130Point.peak_is_sweep_edge`):
    #
    #   * still RISING at 20 GHz -> `meas ac MAX` returned the range edge and
    #     `peaking_db` is FICTITIOUS AND LARGE. That is free reward for a
    #     circuit with no peak, and it is what an adversarial search finds
    #     first. Reject.
    #   * a genuine interior maximum that is merely SMALL (rs = 50 ohm gives
    #     0.165 dB at 1.318 GHz) -> nothing is wrong with the measurement; the
    #     circuit simply does not equalise. ACCEPT, and let the reward score it
    #     as the large S3 shortfall it is.
    #
    # Rejecting both made every low-boost design INVALID — erasing the reward
    # gradient over the whole bottom of the box, which is where a randomly
    # initialised policy starts. Found by the sec 6f calibration.
    if pt.peak_is_sweep_edge:
        return Verdict.INVALID, (
            f"the reported peak IS the sweep edge: f_pk "
            f"{float(pt.f_pk_hz):.4g} Hz, g_pk - g_top "
            f"{float(pt.g_pk_db) - float(pt.g_top_db):+.3f} dB. The response is "
            f"still rising at the top of the search range, so peaking "
            f"{pt.peaking_db:.3f} dB is fictitious (G44)")

    lo, hi = F_PEAK_HZ_LIMITS
    if not lo <= float(pt.f_pk_hz) <= hi:
        return Verdict.INVALID, (
            f"f_pk = {float(pt.f_pk_hz):.4g} Hz is outside [{lo:.3g}, {hi:.3g}] "
            f"— a peak below 10 MHz means `meas ac MAX` returned the BOTTOM of "
            f"its range on a monotonically falling response (G44's other half)")

    lo, hi = NOISE_VRMS_LIMITS
    if not lo <= float(pt.vn_in_vrms) <= hi:
        return Verdict.INVALID, (
            f"inoise_total = {float(pt.vn_in_vrms):.4g} V_rms is outside "
            f"[{lo:.3g}, {hi:.3g}] — the integration collapsed or diverged")

    lo, hi = I_SUPPLY_A_LIMITS
    if not lo <= float(pt.i_supply_a) <= hi:
        return Verdict.INVALID, (
            f"i_supply = {float(pt.i_supply_a):.4g} A is outside [{lo:.3g}, "
            f"{hi:.3g}]; <= 0 means VDD is SOURCING current, i.e. this is not "
            f"the requested operating point")

    return Verdict.VALID, None


# ─────────────────────────────────────────────────────────────────────────────
# The evaluator.
# ─────────────────────────────────────────────────────────────────────────────

#: Failure reasons that are LAUNCH-shaped and are the only ones retried (G45).
#: A retry on anything else would let the environment be non-deterministic in a
#: way the policy can exploit.
_TRANSIENT = re.compile(
    r"ngspice launch failed|ngspice timeout|unreadable swing\.txt", re.I)


@dataclass
class SpiceBudget:
    """§6i's counter. EVERY invocation, including setup and discards.

    Kept as an object rather than a module global so two environments in one
    process cannot silently share a budget, and so a test can assert on it.
    """

    calls: int = 0
    seconds: float = 0.0

    def charge(self, n: int, seconds: float) -> None:
        self.calls += int(n)
        self.seconds += float(seconds)


def evaluate(
    sizing: Sizing,
    budget: SpiceBudget,
    corner: str = "tt",
    temp_c: float = 27.0,
    vdd_scale: float = 1.0,
    keep_raw_text: bool = False,
    real_tail: bool = True,
    real_passives: bool = True,
    ac_peak_interp: bool = False,
) -> EvalResult:
    """One sizing point -> a validated measurement vector, or a named reason.

    NEVER RAISES for anything a policy can cause. A geometry the PDK cannot
    build, a target below the poly head-resistance floor, a tail outside the
    bin ceiling — all of them are invalidities with names, because §8 rule 2
    says the RL loop cannot tolerate exceptions and every one of these is
    reachable from inside the box.

    `real_tail` / `real_passives` default to the published configuration and
    exist only for session 22b's attribution experiment — see `build_point`.

    `ac_peak_interp=True` (session 22c, G74) adds the sub-grid peak to `meas`
    under **new keys** — `f_peak_oct_interp`, `peaking_db_interp` — and leaves
    `f_peak_oct` and `peaking_db` exactly as they were. That is the whole
    safety argument: a reward computed from `meas` is bit-identical with the
    flag on or off, so no published number can move, and a caller who wants the
    interpolated objective has to swap the keys explicitly through
    `meas_with_interpolated_peak`. It costs no extra simulation — the curve is
    dumped by the same invocation (`ac_sweep`, session 21, proven inert).

    Three outcomes, distinguished in `raw["peak_interp_status"]`:

    * `"vertex"` — a genuine interior maximum, refined off the parabola.
    * `"boundary_bottom_lattice_is_exact"` — the maximum sits at 10 MHz, which
      is both a grid point and the edge of the searched interval, so the
      lattice value IS the maximum and is carried forward unchanged. Not a
      fallback: nothing was rounded.
    * `"refused"` — no trustworthy peak, the G44 top edge being the case that
      matters. The two new keys are then ABSENT rather than defaulted, and
      `meas_with_interpolated_peak` raises, which is how the interpolated arm
      inherits the rejection instead of scoring a peak the curve never had.
    """
    t0 = time.perf_counter()
    try:
        point, geo = build_point(sizing, corner=corner, vdd_scale=vdd_scale,
                                 real_tail=real_tail,
                                 real_passives=real_passives)
    except (ValueError, TailGeometryError) as exc:
        # `to_geometry` REJECTS rather than clamps (PASSIVES.md §4.3), and a
        # clamped geometry is how an undrawable device ends up in a netlist
        # that simulates fine. So this branch is the gate working, not a bug.
        return EvalResult.invalid(
            f"unrealisable geometry: {exc}", n_spice=0,
            seconds=time.perf_counter() - t0,
            design_id_=design_id(sizing))

    # No drawn passives -> no geometry, and therefore no geometry tag. G67's
    # `design_id` grouping is a property of drawn silicon; inventing a tag for
    # ideal elements would make two different configurations look like one.
    tag = geometry_tag(geo) if geo is not None else None
    did = design_id(sizing, tag) if tag is not None else design_id(sizing)

    n_spice = 0
    pt = run_point(point, corner=corner, temp_c=temp_c, swing=False,
                   ac_peak_interp=ac_peak_interp)
    # **`pt.n_decks`, not 1** (row 4u). The G54 retry runs a second deck inside
    # `run_point`, and counting one call per call under-billed it -- entry 56
    # reproduced entry 40's `mean_sims_per_request` to every digit while
    # spending ~30 decks more. The transient re-run below has always been
    # charged explicitly; this makes the two consistent.
    n_spice += pt.n_decks
    if not pt.ok and _TRANSIENT.search(pt.fail_reason or ""):
        pt = run_point(point, corner=corner, temp_c=temp_c, swing=False,
                       ac_peak_interp=ac_peak_interp)
        n_spice += pt.n_decks
    dt = time.perf_counter() - t0
    budget.charge(n_spice, dt)

    verdict, why = validate(pt, point)
    if verdict is Verdict.INVALID:
        return EvalResult.invalid(why, n_spice=n_spice, seconds=dt,
                                  design_id_=did, geometry_tag=tag)

    # The `.op` headroom. Trustworthy on BOTH surviving verdicts, because it is
    # built only from `.op` primitives that stage A proved present and finite.
    headroom = {
        "pair_margin_v": float(pt.vds) - float(pt.vdsat),
        "tail_margin_v": float(pt.vds_tail) - float(pt.vdsat_tail),
        "v_src_dc": float(pt.v_src_dc),
        "v_out_dc": float(pt.v_out_dc),
        "i_supply_a": float(pt.i_supply_a),
        "power_w": float(point.vdd) * float(pt.i_supply_a),
    }

    if verdict is Verdict.HEADROOM_ONLY:
        # `meas=None` is the WHOLE mechanism, not a convention: the AC spec set
        # of a device in triode cannot be scored because it does not exist on
        # this object. `headroom` is what the graded band grades.
        return EvalResult(verdict=verdict, reason=why, meas=None,
                          headroom=headroom,
                          raw={"vds": float(pt.vds), "vdsat": float(pt.vdsat),
                               "vds_tail": float(pt.vds_tail),
                               "vdsat_tail": float(pt.vdsat_tail),
                               "gm": float(pt.gm), "id_a": float(pt.id_a),
                               "w_tail_um": sizing.w_tail_um,
                               "nf_tail": sizing.nf_tail,
                               "runtime_s": pt.runtime_s},
                          design_id=did, geometry_tag=tag,
                          n_spice=n_spice, seconds=dt)

    # Everything below is arithmetic on validated primitives, in Python
    # (G26/G30: no derived quantity is computed in `.control`).
    power_w = pt.power_measured_w
    meas = {
        "g_dc_db": float(pt.g_dc_db),
        "peaking_db": float(pt.peaking_db),
        "f_peak_oct": f_peak_octaves(float(pt.f_pk_hz)),
        "nyq_boost_db": float(pt.nyquist_boost_db),
        "inoise_vrms": float(pt.vn_in_vrms),
        "power_w": float(power_w),
        "pair_margin_v": float(pt.vds) - float(pt.vdsat),
        "tail_margin_v": float(pt.tail_margin_v),
    }
    raw = {
        "f_pk_hz": float(pt.f_pk_hz),
        "g_nyq_db": float(pt.g_nyq_db), "g_pk_db": float(pt.g_pk_db),
        "g_top_db": float(pt.g_top_db),
        "gm": float(pt.gm), "gmbs": float(pt.gmbs), "gds": float(pt.gds),
        "vth": float(pt.vth), "vds": float(pt.vds), "vdsat": float(pt.vdsat),
        "vgs": float(pt.vgs), "id_a": float(pt.id_a),
        "v_out_dc": float(pt.v_out_dc), "v_src_dc": float(pt.v_src_dc),
        "i_supply_a": float(pt.i_supply_a),
        "i_tail_meas_a": float(pt.i_tail_meas_a),
        "vds_tail": float(pt.vds_tail), "vdsat_tail": float(pt.vdsat_tail),
        "gm_tail": float(pt.gm_tail),
        "mirror_gain_error": pt.mirror_gain_error,
        "w_tail_um": sizing.w_tail_um, "nf_tail": sizing.nf_tail,
        "runtime_s": pt.runtime_s,
    }
    annotate_interpolated_peak(meas, raw, pt)

    if geo is not None:
        # The REALISED passive values, not the requested ones. The reward and
        # the log must be able to tell a quantisation error from a design move.
        #
        # **ABSENT rather than defaulted when the passives are ideal** (session
        # 22b). A `0.0` quantisation error for an element that was never drawn
        # is a fabricated number, and it would read as a perfectly-drawn device
        # rather than as no device at all -- which is the exact shape of G85's
        # mistake (a sentinel meaning one thing handled as if it meant another).
        raw.update({
            "rs_actual_ohm": geo.rs.r_actual_ohm,
            "cs_actual_f": geo.cs.c_actual_f,
            "rl_actual_ohm": geo.rl.r_actual_ohm,
            "rs_rel_error": geo.rs.rel_error,
            "cs_rel_error": geo.cs.rel_error,
            "rl_rel_error": geo.rl.rel_error,
            "f_zero_error_octaves": geo.f_zero_error_octaves(),
        })
    return EvalResult(verdict=Verdict.VALID, meas=meas, headroom=headroom,
                      raw=raw, design_id=did, geometry_tag=tag,
                      n_spice=n_spice, seconds=dt, text=None)


#: The two keys `ac_peak_interp=True` adds, paired with the discrete key each
#: one replaces. **ONE definition** (rule 9): every caller that wants the
#: interpolated objective goes through `meas_with_interpolated_peak` rather than
#: writing its own swap, so "which measurement is the reward scoring?" has a
#: single answer that can be read in one place.
INTERP_KEYS: tuple[tuple[str, str], ...] = (
    ("f_peak_oct", "f_peak_oct_interp"),
    ("peaking_db", "peaking_db_interp"),
)


def annotate_interpolated_peak(meas: dict, raw: Optional[dict], pt) -> None:
    """Add the parallel `_interp` pair to `meas`, in place. **One definition.**

    ADDITIVE, ALWAYS. `f_peak_oct` and `peaking_db` are left exactly as they
    were; these are the parallel pair, and a caller who wants the refined
    objective has to swap them explicitly through `meas_with_interpolated_peak`
    (or `scored_meas`). That is the whole safety argument for G74: a reward
    computed from an un-swapped `meas` is bit-identical with the flag on or
    off, so no published number can move.

    The keys are present ONLY when the interpolation succeeded, so "absent"
    means "refused" and never "equal to the grid value" — G85's shape of
    mistake, a sentinel read as a measurement.

    **Why this is a function and not four lines inside `evaluate`.** Session
    22u found `exp_g4_verify.verify_full` — the 135-point compliance matrix
    every S8 and margin number is reported on — scoring `pt.f_pk_hz`, the
    QUANTISED peak, while `verify()` beside it scored the interpolated one.
    Two verification paths in one file disagreeing about which peak they read
    is rule 9's failure (exactly one definition, referenced, never redeclared),
    and the cost was not the 0.15-lattice-step error in the headline margin: it
    was that the lattice collapses six physically distinct corners onto one
    tied value, so the matrix could not say WHICH corner binds.

    `raw` may be `None` for a caller that keeps no bookkeeping dict; the `meas`
    side is identical either way.
    """
    if pt.peak_interp is None:                  # the flag was off; nothing to add
        return
    if raw is not None:
        raw["peak_interp_ok"] = bool(pt.peak_interp.get("ok"))
        raw["peak_interp_reason"] = pt.peak_interp.get("reason")
        raw["peak_interp_edge"] = pt.peak_interp.get("edge")
        raw["peak_interp_curvature_db"] = pt.peak_interp.get("curvature_db")
    if pt.has_interp_peak:
        meas["f_peak_oct_interp"] = f_peak_octaves(float(pt.f_pk_interp_hz))
        meas["peaking_db_interp"] = float(pt.peaking_interp_db)
        if raw is not None:
            raw["peak_interp_status"] = "vertex"
            raw["f_pk_interp_hz"] = float(pt.f_pk_interp_hz)
            raw["g_pk_interp_db"] = float(pt.g_pk_interp_db)
            raw["d_f_peak_octaves"] = float(pt.d_f_peak_octaves)
    elif pt.peak_interp.get("edge") == "bottom":
        # **THE MAXIMUM IS AT THE BOTTOM OF THE WINDOW, AND THE LATTICE
        # VALUE IS THEN EXACT RATHER THAN APPROXIMATE.** 10 MHz is a grid
        # point AND the boundary, so `meas ac MAX` reported the true
        # maximum of the searched interval; there is no sub-grid position
        # to find and nothing has been rounded. Carrying the lattice pair
        # forward is the RIGHT answer here, not a fallback.
        #
        # WHY THE TWO EDGES ARE TREATED DIFFERENTLY, since geometrically
        # they are the same situation. It mirrors a decision this repo
        # already made deliberately and wrote down: `peak_is_sweep_edge`
        # is the TOP half of `has_interior_peak` only, because a response
        # still rising at 20 GHz has a FICTITIOUS peak (G44) while a
        # monotonically falling one has a real, correctly measured, merely
        # useless one. `validate` rejects the first and accepts the second,
        # and its comment records why: rejecting the second erased the
        # reward gradient over the whole low-peaking region of the box,
        # which is where a randomly initialised policy starts. Refusing
        # these designs on the interpolated path would rebuild exactly that
        # hole, one layer up — the interpolated arm would see an invalid
        # floor where the discrete arm sees a large, graded S3 miss.
        meas["f_peak_oct_interp"] = float(meas["f_peak_oct"])
        meas["peaking_db_interp"] = float(meas["peaking_db"])
        if raw is not None:
            raw["peak_interp_status"] = "boundary_bottom_lattice_is_exact"
            raw["d_f_peak_octaves"] = 0.0
    elif raw is not None:
        raw["peak_interp_status"] = "refused"


def meas_with_interpolated_peak(meas: Optional[Mapping[str, float]]) -> dict:
    """`meas`, with the lattice peak replaced by the interpolated one.

    THE POINT OF THE SWAP. `reward_v1`'s feasible branch scores
    `0.5 - |log2(f_peak/f_target)|` octaves against a 0.5-octave tolerance, and
    `meas ac MAX` can only report frequencies 0.066439 octaves apart, so the
    best attainable score is a lattice property: +8.950669, G74's ceiling, tied
    by 57 distinct designs across 8000 simulations. Scoring the SAME reward
    function on the interpolated peak makes the objective continuous, which is
    the difference between a plateau at the optimum and a gradient into it.

    BOTH keys move together, from the SAME parabola. Taking the interpolated
    frequency and the lattice magnitude would be reading one peak in two
    places, which is precisely the failure rule 9 exists to prevent.

    **Raises rather than falling back.** A missing pair means the interpolation
    refused, and the commonest refusal is a sweep-edge maximum (G44). Silently
    substituting the grid value there would hand the interpolated arm exactly
    the fictitious peak the guard exists to reject; and substituting it for a
    design where nothing was wrong would misreport a lattice number as a
    refined one. Callers treat the exception as an invalid design.
    """
    if not meas:
        raise ValueError("no measurement vector to interpolate")
    missing = [new for _, new in INTERP_KEYS if new not in meas]
    if missing:
        raise ValueError(
            f"{missing} absent: this evaluation either did not run with "
            f"`ac_peak_interp=True`, or the interpolation refused (a sweep-edge "
            f"maximum is the commonest reason — see raw['peak_interp_reason']). "
            f"There is no interpolated peak to score.")
    out = dict(meas)
    for old, new in INTERP_KEYS:
        out[old] = float(out.pop(new))
    return out


def scoring_meas(ev: "EvalResult", ac_peak_interp: bool) -> Optional[dict]:
    """**THE measurement vector the reward scores.** One definition (rule 9).

    Every search method in this project must optimise the same objective or the
    benchmark measures formulation instead of search (`BASELINES.md` §7f). Four
    of them reach the reward through `baselines.Objective._score_one` and the
    fifth (PPO) through `rl.env.CtleSizingEnv._evaluate_current`, so the choice
    of WHICH peak the reward reads has to live in one place that both call.
    This is that place.

    `ac_peak_interp=False` returns `ev.meas` unchanged, which is what every
    published number was computed from.

    **On a refusal the LATTICE value is used, and the design is NOT dropped to
    the invalid floor.** That is a change from the rule
    `PEAK_INTERP.md` §7 item 2 recorded as "today's behaviour", and the reason
    is measured: the interpolation refused on **1 valid design in 4543**
    (0.022 %), and the alternative punches a hole in the reward landscape —
    a design the discrete path grades at −2.018 would score −10 for a reason
    that is a property of the SWEEP's numerical resolution rather than of the
    circuit. This repo has already paid for that mistake once: `validate`'s G44
    comment records that rejecting merely-small peaks "erased the reward
    gradient over the entire low-peaking region of the box, which is where a
    randomly initialised policy starts". A 1-in-4543 event is not worth
    rebuilding it. The count is returned so it cannot hide — callers increment
    a counter on `refused`, and a run that reports zero refusals has either
    seen none or is not counting.

    Reversible in one argument if a human decides otherwise; nothing in the
    ranking can turn on 0.022 % of the population either way.
    """
    return scored_meas(ev.meas, ac_peak_interp)


def scored_meas(meas: Optional[Mapping[str, float]],
                ac_peak_interp: bool) -> Optional[dict]:
    """`scoring_meas`'s rule, at the level of a measurement vector.

    `scoring_meas` takes an `EvalResult` because that is what the four search
    arms and the RL env hold. **`verify_full` holds no `EvalResult`** — it runs
    the G2 closed-loop chain, not the search evaluator, because three of the
    eleven rows are not in the search's measurement vector. Before session 22u
    that meant it scored the lattice peak while `verify()` beside it scored the
    interpolated one. Splitting the rule out here rather than re-implementing
    the two lines there is rule 9: one definition, referenced.

    Flag off returns the argument itself, unwrapped and uncopied, so the
    identity property `test_scoring_meas_is_the_identity_when_the_flag_is_off`
    pins survives the split.
    """
    if not ac_peak_interp or meas is None:
        return meas                                     # type: ignore[return-value]
    try:
        return meas_with_interpolated_peak(meas)
    except ValueError:
        return dict(meas)


def interp_was_refused(ev: "EvalResult") -> bool:
    """Did this evaluation ask for a sub-grid peak and not get one?

    Distinct from "was the flag off": `raw['peak_interp_status']` is absent in
    that case and present on every evaluation that asked. G93 is the reason
    this is counted rather than assumed rare.
    """
    st = (ev.raw or {}).get("peak_interp_status")
    return st is not None and st == "refused"


# ─────────────────────────────────────────────────────────────────────────────
# §6d's independent cross-check.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CrossCheck:
    """One evaluation re-derived from raw SPICE text by a second code path."""

    design_id: str
    agrees: bool
    detail: str
    worst_rel: float


def independent_recompute(text: str) -> dict:
    """Re-derive the AC quantities from raw ngspice output, via `crosscheck.py`.

    Deliberately a DIFFERENT path from `evaluate`: `crosscheck.derived_ac`
    parses the `meas` lines itself and computes `peaking_db` and
    `nyquist_boost_db` from its own `DerivedAc`, so agreement is evidence that
    the parse and the arithmetic are both right rather than that one function
    is self-consistent.

    Raises `SilentFailure` on warning-shaped failures, which is the point:
    `derived_ac` refuses to run on output that printed one.
    """
    d = derived_ac(text)
    return {
        "g_dc_db": d.g_dc_db,
        "peaking_db": d.peaking_db,
        "nyq_boost_db": d.nyquist_boost_db,
        "f_pk_hz": d.f_pk_hz,
        "inoise_vrms": parse_scalar(text, "inoise_total"),
        "gm": find_device_scalar(text, "gm"),
    }


def cross_check_sample(sizing: Sizing, budget: SpiceBudget,
                       rel_tol: float = 1e-9) -> CrossCheck:
    """Re-run one sizing point and recompute it independently.

    This costs a SPICE call and it is CHARGED to the budget (§6i: every
    invocation, including those spent on setup or discarded work). A
    cross-check that did not appear in the cost accounting would flatter the
    steps-per-hour number by exactly the sampling rate.
    """
    ev = evaluate(sizing, budget, keep_raw_text=True)
    if not ev.valid:
        return CrossCheck(ev.design_id or "?", False,
                          f"evaluation invalid: {ev.reason}", math.nan)
    # A SECOND RUN, not a cached one. Two things that only a re-run can catch:
    # a simulator that is not deterministic for a fixed netlist, and a parse
    # that depends on something outside the netlist. It costs a SPICE call and
    # the call is CHARGED (§6i counts every invocation, including this one).
    point, _ = build_point(sizing)
    t0 = time.perf_counter()
    pt = run_point(point, swing=False, keep_text=True)
    budget.charge(pt.n_decks, time.perf_counter() - t0)
    if not pt.ok:
        return CrossCheck(ev.design_id or "?", False,
                          f"cross-check re-run failed: {pt.fail_reason}", math.nan)

    # THE INDEPENDENT PATH: `crosscheck.derived_ac` re-parses the raw text and
    # forms `peaking_db` / `nyquist_boost_db` from its own `DerivedAc`, so
    # agreement is evidence that the parse AND the arithmetic are right —
    # rather than evidence that one function agrees with itself.
    ref = independent_recompute(pt.raw_text or "")
    mine = {
        "g_dc_db": ev.meas["g_dc_db"], "peaking_db": ev.meas["peaking_db"],
        "nyq_boost_db": ev.meas["nyq_boost_db"],
        "f_pk_hz": ev.raw["f_pk_hz"], "inoise_vrms": ev.meas["inoise_vrms"],
        "gm": ev.raw["gm"],
    }
    worst, where = 0.0, ""
    for k in ref:
        a, b = float(ref[k]), float(mine[k])
        denom = max(abs(a), abs(b), 1e-30)
        rel = abs(a - b) / denom
        if rel > worst:
            worst, where = rel, k
    agrees = worst <= rel_tol
    detail = ("exact" if worst == 0.0
              else f"worst {worst:.3g} relative on {where}")
    return CrossCheck(ev.design_id or "?", agrees, detail, worst)


__all__: Sequence[str] = (
    "Verdict", "EvalResult", "SpiceBudget", "CrossCheck",
    "evaluate", "validate", "build_point", "geometry_tag",
    "independent_recompute", "cross_check_sample",
    "annotate_interpolated_peak", "meas_with_interpolated_peak",
    "scoring_meas", "scored_meas", "interp_was_refused", "INTERP_KEYS",
    "G_DB_LIMITS", "F_PEAK_HZ_LIMITS", "NOISE_VRMS_LIMITS",
    "I_SUPPLY_A_LIMITS", "RAIL_SLACK_V",
)
