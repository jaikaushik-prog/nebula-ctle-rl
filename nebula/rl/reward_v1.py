"""
rl/reward_v1.py — the shortfall reward, in units where 1.0 means "meaningfully
off".

WHAT THIS SUPERSEDES, AND WHY
------------------------------
`rl/reward.py` implements CLAUDEwa.md §9's form: a sum of normalised
shortfalls, each divided by `|value| + |target|`. That form is kept and still
tested — it is the contract §9 specifies. This module implements the shape the
human decision of 2026-08-06 (HANDOFF §8) put in its place for the RL loop,
and the reasoning is worth restating because it is a retraction:

    "**`min` has the same pathology as the first-failure table, one layer
     down:** it reports `S3_f_peak` for as long as that misses by 17 GHz, so
     the agent gets **no gradient on `tail_saturation`** — a constraint binding
     on 13.3 % of the box at slow-hot — until S3 is nearly solved."

Session 13 measured that "ranked worst" and "ever violated" disagree by an
order of magnitude, because `tail_saturation` misses by tens of millivolts
while `S3_f_peak` misses by 17 GHz. A `min` reward can only ever see the
first. So:

    shortfall_i = max(0, -margin_i / tol_i)          # 0 when spec i is met

    if any shortfall_i > 0:          # INFEASIBLE
        r = -sum( clip(shortfall_i, 0, 1) )          # gradient on EVERY miss
    else:                            # FEASIBLE
        r = B + min_i( margin_i / tol_i )            # now seek margin

    r -= lambda * simulation_cost_of_this_step

THE NORMALISATION IS THE ENTIRE POINT
--------------------------------------
`§9`'s `(|x| + |tau|)` denominator is scale-free but it is not MEANINGFUL: it
makes a shortfall depend on the magnitude of the quantity rather than on how
badly the design misses. 17 GHz against 2.5 GHz and 40 mV against 200 mV both
normalise to something near -1, which destroys exactly the distinction session
13 paid to discover. Each `tol_i` here answers one question — *what miss is
worth caring about, in this quantity's own units?* — and every one is quoted:

  S3_f_peak       **0.5 octaves.** S3's window is 1.25-2.5 GHz, which is
                  EXACTLY one octave, so the half-width is 0.5 octaves and a
                  shortfall of 1.0 means "one full window off centre". The
                  margin is `0.5 - |log2(f_peak / f_target)|`, i.e. §6h's
                  `-|log2(...)|` form with the half-width folded in. Log
                  frequency throughout, per HANDOFF §8's note and because
                  `f_peak` is quantised at 0.0664 octaves by `meas ac MAX` on a
                  `dec 50` grid (session 11) — a linear-hertz tolerance would
                  be finer than the measurement at the bottom of the window and
                  coarser at the top.

  S3_peaking      **1.0 dB**, as distance OUTSIDE the 3-12 dB band. A dB is
                  already the unit the spec is written in, and 1 dB is the
                  granularity real CTLEs tune at (`RewardConfig` records that
                  argument), so a shortfall of 1.0 means "a whole tuning step
                  outside the band".

  S3_nyq_boost    **1.0 dB** below zero. CLAUDEwa.md §3 reads S3 as requiring
                  positive boost AT NYQUIST as well as a peak in the window; a
                  stage 1 dB below its own DC gain where the data lives is
                  meaningfully worse than a wire.

  S5_noise        **0.5 mV_rms**, a third of S5's 1.5 mV limit. Measured
                  free — 90.7 % of the box meets S5 — so the tolerance only has
                  to be fine enough to produce gradient in the rare region
                  where it binds.

  S6_power        **5 mW**, a third of S6's 15 mW limit, same argument.

  saturation      **0.1 V** of `vds - vdsat`. The reference point sits at
                  0.28 V, so 0.1 V is "a third of the way to triode".

  tail_saturation **0.1 V** of `vds_tail - vdsat_tail`. **This is the number
                  the whole retraction is about.** Session 13's tail misses are
                  tens of millivolts; at 100 mV they produce shortfalls of
                  0.2-0.5, which is real gradient, instead of the ~0.02 that
                  §9's denominator would give against a 17 GHz f_peak miss.

**These seven tolerances are HUMAN-SET, not agent-chosen.** CLAUDEwa.md §8
rule 6 forbids an agent choosing spec-tightness heuristics. Every one above
was specified in the task 6h brief ("f_peak in octaves ... half-width of
0.5 octaves", "peaking in dB, as distance outside the 3-12 dB band",
"tail_saturation in units of (vds - vdsat) scaled to something like 100 mV")
or follows from a spec limit by a stated rule. Where the brief said "something
like", the value is the round number nearest the brief's own figure and it is
recorded here as a reporting axis (`TOLERANCE_SCAN`), not as a hidden constant.

WHAT IS NOT IN THE REWARD, AND WHY
-----------------------------------
* **S4 (HD3).** Needs transient + FFT (`.disto` returns exactly 0.0 for BSIM4,
  G21) at ~4x the cost of AC + noise. Belongs in a promotion tier.
* **S7 (area).** `to_geometry` now yields drawn devices so a device-area number
  exists (1506 um^2 at design 432, 3 % of budget) — but routing, enclosure and
  the transistors are not in it, so it is a lower bound, and PASSIVES.md §6
  item 5 lists the real budget as open. Scoring a lower bound as if it were
  the area would let the policy buy reward with a number nobody measured.
* **S8 (eye).** A link-layer metric. The link layer is still a mock end to end
  (G16), and §6b makes any path from a training run to a mock structurally
  impossible. So S8 CANNOT be in this reward, and that is the correct
  outcome — not a limitation to be worked around.

**NO ANALYTIC QUANTITY IS USED ANYWHERE IN THE REWARD PATH.** §6a requires
this to be stated. Every number scored here is a MEASURED SPICE primitive or
arithmetic on measured primitives: `peaking_db = g_pk_db - g_dc_db`,
`nyq_boost_db = g_nyq_db - g_dc_db`, `f_peak` from `meas ac MAX`, `power` from
the MEASURED supply branch, margins from `@m[vds]` and `@m[vdsat]`. The §6
design equations appear in this session only as the EXPECTED DIRECTIONS of the
§6e sensitivity gate, never as a scored quantity — which matters because G60
measured them over-predicting the Nyquist boost by 0.8-1.5 dB, growing with
`R_s`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from nebula.common.types import (
    SPEC_F_PEAK_HZ_RANGE,
    SPEC_PEAKING_DB_RANGE,
    SPEC_POWER_MAX_W,
    SPEC_VN_IN_MAX_VRMS,
)

# ─────────────────────────────────────────────────────────────────────────────
# The tolerances. Human-set (see the module docstring). One definition.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Tol:
    """One spec's tolerance: the miss size at which shortfall reaches 1.0."""

    name: str
    value: float
    unit: str
    basis: str


TOLERANCES: tuple[Tol, ...] = (
    Tol("S3_f_peak", 0.5, "octaves",
        "S3's 1.25-2.5 GHz window is EXACTLY one octave; 0.5 is its half-width"),
    Tol("S3_peaking", 1.0, "dB",
        "distance outside the 3-12 dB band; 1 dB is production CTLE tuning "
        "granularity (RewardConfig.peaking_tol_db)"),
    Tol("S3_nyq_boost", 1.0, "dB",
        "boost at Nyquist below 0 dB; 1 dB below its own DC gain is "
        "meaningfully worse than a wire (CLAUDEwa.md §3 reading (b))"),
    Tol("S5_noise", 0.5e-3, "V rms", "one third of S5's 1.5 mV_rms limit"),
    Tol("S6_power", 5.0e-3, "W", "one third of S6's 15 mW limit"),
    Tol("saturation", 0.1, "V",
        "vds - vdsat; 0.28 V at the corrected reference point, so 0.1 V is a "
        "third of the way to triode"),
    Tol("tail_saturation", 0.1, "V",
        "vds_tail - vdsat_tail. THE tolerance the reward retraction is about: "
        "session 13's tail misses are tens of mV and must not be invisible "
        "next to a 17 GHz f_peak miss"),
)

TOL: dict[str, float] = {t.name: t.value for t in TOLERANCES}
SPEC_NAMES: tuple[str, ...] = tuple(t.name for t in TOLERANCES)
N_SPECS: int = len(TOLERANCES)

#: Reward v0's spec set: **S3 alone**, per §6f. Three rows, because CLAUDEwa.md
#: §3 reads S3 as constraining the peak magnitude, its location, AND the boost
#: at Nyquist, and requires all three to be reported.
V0_SPECS: tuple[str, ...] = ("S3_peaking", "S3_f_peak", "S3_nyq_boost")

#: Reward v1: everything the DEVICE layer can measure. See the module docstring
#: for why S4, S7 and S8 are absent and why that is a conclusion, not a gap.
V1_SPECS: tuple[str, ...] = SPEC_NAMES

#: The feasibility bonus. **`B` must be large enough that any feasible design
#: outranks any infeasible one**, and the bound is exact rather than tuned:
#: infeasible scores lie in `[-N, 0)` because every shortfall is clipped to 1,
#: and feasible scores are `B + min_i(margin_i / tol_i)` where the min is
#: >= 0 by definition of feasibility. So `B >= N` suffices; `B = N + 1` leaves
#: one unit of separation so the two bands cannot touch even at the boundary.
#: Nothing here is a knob: change `N` and `B` follows.
def feasible_bonus(n_specs: int) -> float:
    return float(n_specs) + 1.0


#: Top of the HEADROOM band: the reward an out-of-saturation design gets when
#: it is only infinitesimally into triode. **Strictly below the worst
#: infeasible score, which is `-N`.**
def headroom_band_top(n_specs: int) -> float:
    return -(float(n_specs) + 1.0)


#: The reward for an evaluation nothing can be believed from (§6d).
#: **Strictly below the whole headroom band**, whose floor is
#: `headroom_band_top - 1`. Every boundary here is derived from `N`; none is a
#: tuned number, and changing `N` moves all four together.
def invalid_reward(n_specs: int) -> float:
    return -(float(n_specs) + 3.0)


#: Scale on which "how far into triode" is measured, in volts of `vds - vdsat`.
#: Reuses `TOL["saturation"]`, so the graded band and the feasible branch's
#: margin term speak the SAME unit — a design 100 mV into triode and one with
#: 100 mV of margin are one tolerance either side of the same boundary.
def headroom_reward(worst_margin_v: float, n_specs: int) -> float:
    """The §Call-1 graded band. Ordered by `vds - vdsat`, strictly.

    `worst_margin_v` is the MORE NEGATIVE of the pair and tail margins — "how
    far into triode is the worse device". It must be <= 0; a positive value
    means the caller has misrouted a saturated design into this branch.

        r = headroom_band_top - h / (1 + h),   h = -worst_margin / tol >= 0

    **The bounded map, not the clip used everywhere else, and the reason is the
    whole point of the band.** `clip(h, 0, 1)` appears in the infeasible branch
    so that one catastrophic spec cannot drown out the others in a SUM. Here
    there is no sum — this is a single ordering quantity — so a clip buys
    nothing and costs exactly what the band exists to provide: a design 500 mV
    into triode would score identically to one 50 mV in, and the policy would
    have no direction out of the deep end. `h/(1+h)` is strictly monotone on
    [0, inf), maps into [0, 1), introduces no new constant, and keeps the band
    inside `(top - 1, top]`.
    """
    if worst_margin_v > 0.0:
        raise ValueError(
            f"headroom_reward got a POSITIVE margin ({worst_margin_v:+.4g} V). "
            f"A saturated design belongs in the feasible/infeasible bands; "
            f"routing it here would score a good circuit below every bad one."
        )
    h = -float(worst_margin_v) / TOL["saturation"]
    return headroom_band_top(n_specs) - h / (1.0 + h)


#: Reporting axis rather than a hidden setting, in the spirit of
#: `reward.TOLERANCE_SWEEP`: scale every tolerance by these factors and show
#: the ranking is unchanged.
TOLERANCE_SCAN: tuple[float, ...] = (0.5, 1.0, 2.0)


# ─────────────────────────────────────────────────────────────────────────────
# Margins. Each in the quantity's OWN unit, signed, >= 0 means satisfied.
# ─────────────────────────────────────────────────────────────────────────────


def margins(meas: Mapping[str, float],
            target_f_peak_hz: float,
            target_peaking_db: Optional[float] = None) -> dict:
    """Signed margins, in natural units. ONE definition (rule 9).

    `meas` is `evaluator.EvalResult.meas`: already in the units
    `contract.OBS_SCALES` declares, so `f_peak_oct` is octaves relative to
    Nyquist and the margins below never touch hertz.

    `target_peaking_db` is accepted for the spec-conditioned form but is NOT
    used: S3's peaking constraint is a BAND (3-12 dB), and CLAUDEwa.md §3 reads
    the band as the requirement. Scoring distance from a requested point inside
    the band instead would be a `match` term, which is what `reward.py` does
    and what §6h replaces. Kept in the signature so the caller cannot silently
    believe it is being honoured.
    """
    from nebula.rl.contract import f_peak_octaves

    pk_lo, pk_hi = SPEC_PEAKING_DB_RANGE
    pk = float(meas["peaking_db"])
    f_oct = float(meas["f_peak_oct"])
    target_oct = f_peak_octaves(float(target_f_peak_hz))

    return {
        # Distance OUTSIDE the band, as a margin: positive inside, negative by
        # exactly how far outside.
        "S3_peaking": min(pk - pk_lo, pk_hi - pk),
        # §6h's `-|log2(f_peak / f_target)|`, with the half-width folded in so
        # the quantity is a MARGIN like every other row.
        "S3_f_peak": TOL["S3_f_peak"] - abs(f_oct - target_oct),
        "S3_nyq_boost": float(meas["nyq_boost_db"]),
        "S5_noise": SPEC_VN_IN_MAX_VRMS - float(meas["inoise_vrms"]),
        "S6_power": SPEC_POWER_MAX_W - float(meas["power_w"]),
        "saturation": float(meas["pair_margin_v"]),
        "tail_saturation": float(meas["tail_margin_v"]),
    }


def shortfalls(margin: Mapping[str, float],
               specs: Sequence[str] = V1_SPECS) -> dict:
    """`max(0, -margin_i / tol_i)`. Zero exactly when spec i is satisfied."""
    return {name: max(0.0, -float(margin[name]) / TOL[name]) for name in specs}


# ─────────────────────────────────────────────────────────────────────────────
# The reward.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RewardBreakdown:
    """Everything the September results table needs, not just the scalar."""

    reward: float
    feasible: bool
    valid: bool
    #: True for the CALL 1 band: `.op` trustworthy, device in triode, AC spec
    #: set dropped. Distinct from `valid` (which is False here too) because the
    #: two need opposite handling — this one carries a graded score and a real
    #: headroom margin, the other carries nothing.
    headroom_only: bool
    spec_reward: float
    cost_penalty: float
    margins: dict
    shortfalls: dict
    worst_spec: Optional[str]
    n_violated: int

    def summary(self) -> str:
        if self.headroom_only:
            return (f"HEADROOM-ONLY r={self.reward:+.4f} "
                    f"(worst {self.worst_spec} "
                    f"{self.margins[self.worst_spec] * 1e3:+.1f} mV into triode)")
        if not self.valid:
            return f"INVALID r={self.reward:+.4f}"
        if self.feasible:
            return (f"FEASIBLE r={self.reward:+.4f} "
                    f"(min margin/tol {self.spec_reward - feasible_bonus(len(self.shortfalls)):+.4f} "
                    f"on {self.worst_spec})")
        return (f"infeasible r={self.reward:+.4f} on {self.n_violated} spec(s), "
                f"worst {self.worst_spec}")


def reward(
    meas: Optional[Mapping[str, float]],
    target_f_peak_hz: float,
    specs: Sequence[str] = V1_SPECS,
    lambda_cost: float = 0.0,
    sim_cost: float = 0.0,
    target_peaking_db: Optional[float] = None,
    headroom: Optional[Mapping[str, float]] = None,
) -> RewardBreakdown:
    """The §6h scalar plus its full decomposition. FOUR bands, exactly ordered.

        feasible          >= B = N + 1        every spec met; seek margin
        infeasible        [-N, 0)             gradient on EVERY violation
        headroom-only     (-(N+2), -(N+1)]    .op good, device in triode
        invalid           -(N+3)              nothing trustworthy

    The bands cannot overlap and the separation is arithmetic rather than
    tuned: the worst infeasible score is `-N` because each of `N` shortfalls
    is clipped to 1, the headroom band is bounded by construction, and every
    boundary is a function of `N` alone.

    Three ways to enter the non-scoring bands, and they are DIFFERENT:

    * `meas=None, headroom=<dict>` — `.op` converged, a device is out of
      saturation. **Graded**, ordered by `vds - vdsat`. This is Call 1.
    * `meas=None, headroom=None` — nothing is trustworthy. Floor, no gradient.
    * `meas=<dict>` — normal scoring.

    `lambda_cost * sim_cost` is subtracted from every branch, invalid included;
    otherwise crashing becomes cheaper than simulating. It is 0.0 by default:
    for this smoke run cost per step is constant (one SPICE call, one corner),
    so the term would be a constant offset that changes no ranking and only
    obscures the curve. It exists because the term becomes real the moment a
    fidelity scheduler makes cost vary per step, and it should not appear later
    as a new idea.
    """
    specs = tuple(specs)
    n = len(specs)
    penalty = float(lambda_cost) * float(sim_cost)

    if meas is None and headroom is not None:
        # CALL 1: .op converged, the device is in triode. The AC spec set is
        # gone by construction (`meas is None`), so nothing can score it; what
        # survives is the DC headroom, which is what we grade.
        worst = min(float(headroom["pair_margin_v"]),
                    float(headroom["tail_margin_v"]))
        spec_r = headroom_reward(worst, n)
        m = {"saturation": float(headroom["pair_margin_v"]),
             "tail_saturation": float(headroom["tail_margin_v"])}
        return RewardBreakdown(
            reward=spec_r - penalty, feasible=False, valid=False,
            headroom_only=True, spec_reward=spec_r, cost_penalty=penalty,
            margins=m, shortfalls={k: -v / TOL[k] for k, v in m.items()},
            worst_spec=("saturation"
                        if m["saturation"] <= m["tail_saturation"]
                        else "tail_saturation"),
            n_violated=sum(1 for v in m.values() if v <= 0.0))

    if meas is None:
        r = invalid_reward(n) - penalty
        return RewardBreakdown(reward=r, feasible=False, valid=False,
                               headroom_only=False,
                               spec_reward=invalid_reward(n),
                               cost_penalty=penalty, margins={}, shortfalls={},
                               worst_spec=None, n_violated=n)

    m_all = margins(meas, target_f_peak_hz, target_peaking_db)
    m = {k: m_all[k] for k in specs}
    s = shortfalls(m, specs)
    violated = [k for k, v in s.items() if v > 0.0]

    if violated:
        spec_r = -sum(min(v, 1.0) for v in s.values())
        worst = max(s, key=lambda k: s[k])
        return RewardBreakdown(
            reward=spec_r - penalty, feasible=False, valid=True,
            headroom_only=False, spec_reward=spec_r, cost_penalty=penalty,
            margins=m, shortfalls=s, worst_spec=worst,
            n_violated=len(violated))

    scaled = {k: m[k] / TOL[k] for k in specs}
    worst = min(scaled, key=lambda k: scaled[k])
    spec_r = feasible_bonus(n) + scaled[worst]
    return RewardBreakdown(
        reward=spec_r - penalty, feasible=True, valid=True,
        headroom_only=False, spec_reward=spec_r, cost_penalty=penalty,
        margins=m, shortfalls=s, worst_spec=worst, n_violated=0)


def reward_v0(meas: Optional[Mapping[str, float]],
              target_f_peak_hz: float, **kw) -> RewardBreakdown:
    """§6f: S3 alone."""
    return reward(meas, target_f_peak_hz, specs=V0_SPECS, **kw)


def reward_v1(meas: Optional[Mapping[str, float]],
              target_f_peak_hz: float, **kw) -> RewardBreakdown:
    """§6h: every spec the device layer can measure."""
    return reward(meas, target_f_peak_hz, specs=V1_SPECS, **kw)


__all__: Sequence[str] = (
    "Tol", "TOLERANCES", "TOL", "SPEC_NAMES", "N_SPECS",
    "V0_SPECS", "V1_SPECS", "TOLERANCE_SCAN",
    "feasible_bonus", "invalid_reward", "headroom_band_top",
    "headroom_reward",
    "margins", "shortfalls", "RewardBreakdown",
    "reward", "reward_v0", "reward_v1",
)
