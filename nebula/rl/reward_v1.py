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
* **S8 (eye).** WAS absent, and the reason has now been REMOVED rather than
  worked around. The paragraph that stood here said: *"A link-layer metric. The
  link layer is still a mock end to end (G16) ... So S8 CANNOT be in this
  reward, and that is the correct outcome — not a limitation to be worked
  around."* That was right when it was written and it is no longer true:
  session 21 built the device->link bridge (`link/bridge.py`, `link/fit.py`,
  `nebula/G2_RESULTS.md`), so a real eye in volts now exists.

  **S8 is therefore in `V2_SPECS`, and `V1_SPECS` is UNTOUCHED.** Adding two
  rows changes `len(specs)`, hence the feasibility bonus `B = N + 1`, hence
  every reward number this project has published — including the **+8.950669**
  ceiling (G74), which is a property of the spec set rather than of the
  circuit. `BASELINES.md` §7f forbids moving that without re-running every
  baseline, so v2 is opt-in until a human decides to.

  Costs no extra simulation: the eye is computed from the AC curve the same
  invocation already produced (+0.037 s, no simulator).

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
    SPEC_HD3_MAX_DBC,
    SPEC_AREA_MAX_MM2,
)

#: S3's frequency window in OCTAVES relative to 2.5 GHz, which is the unit
#: `contract.f_peak_octaves` puts every frequency in. One definition (rule 9):
#: `S3_f_peak_band` is the only consumer and must not rebuild it.
_F_LO_OCT: float = math.log2(SPEC_F_PEAK_HZ_RANGE[0] / 2.5e9)
_F_HI_OCT: float = math.log2(SPEC_F_PEAK_HZ_RANGE[1] / 2.5e9)

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
    # ── S8, added by G2 (session 21). See `V2_SPECS` below. ─────────────────
    Tol("S8_eye_h", 50.0e-3, "V",
        "half of S8's own 100 mV floor. A 50 mV miss on a 100 mV spec is a "
        "miss worth a full unit of shortfall; the eye spans 0 to ~450 mV "
        "across the box (G2_RESULTS.md), so this is not a knob that makes "
        "anything pass"),
    Tol("S8_eye_w", 0.2, "UI",
        "half of S8's own 0.4 UI floor, by the same argument. Also above the "
        "1/64 UI = 0.0156 UI phase resolution of the pulse-response grid, so "
        "the tolerance is coarser than the measurement rather than finer"),
    # ── S4 and S7, added by session 22o. See `V3_SPECS` below. ─────────────
    #
    # **These two rows are on the competition's own spec slide and had NO
    # tolerance row at all** -- they were measured (HD3 -61.10 dBc, area
    # 0.001092 mm^2 at G2) and never scored, so a judge ticking the slide
    # against the objective found two blanks. Both tolerances are ONE THIRD OF
    # THE LIMIT, which is exactly the rule S5_noise and S6_power already use;
    # nothing here is a new choice.
    Tol("S4_hd3", 10.0, "dB",
        "one third of S4's own 30 dB limit, the same rule S5 and S6 use. "
        "CLAUDEwa.md sec 3 calls S4 'relatively relaxed' and measured ~60 dB "
        "inside spec, so this row is expected never to bind -- which is the "
        "finding, not a reason to leave it unscored"),
    # ── S4 AT NYQUIST, added by session 22s. See `V4_SPECS` below. ────────
    #
    # **A SEPARATE ROW RATHER THAN A DIFFERENT CONDITION ON `S4_hd3`, and that
    # is rule 9 rather than fussiness.** `S4_hd3` means "HD3 at 100 MHz and
    # 200 mVpp" everywhere it has ever been published. Session 22r measured
    # the same circuit at -48.00 dBc there and **-17.38 dBc** at 2.5 GHz and
    # 535 mVpp -- a 30 dB difference under one name would be exactly G32: two
    # definitions of one quantity, with a reader unable to tell which produced
    # a given number. Same tolerance (one third of the 30 dB limit), different
    # row, both reportable side by side.
    Tol("S4_hd3_nyq", 10.0, "dB",
        "one third of S4's own 30 dB limit, as S4_hd3 uses -- but measured at "
        "NYQUIST and at the amplitude the link actually drives, not at S4's "
        "stated 100 MHz / 200 mVpp. S4's tone sits at 0.87x the CTLE zero "
        "where the degeneration is still intact; this row is the same spec "
        "asked at the operating point"),
    Tol("S7_area", SPEC_AREA_MAX_MM2 / 3.0, "mm^2",
        "one third of S7's own 0.05 mm^2 limit, the same rule S5 and S6 use. "
        "Passives dominate; G2 measured 0.001092 mm^2, 46x inside spec"),
    # ── THE REQUESTED PEAKING, added by session 23. See `V5_SPECS`. ────────
    #
    # **This row exists because the deliverable takes a spec as INPUT.** The
    # competition slide asks for "a framework that takes target specs as input
    # and outputs the final schematic and resulting specs". `S3_peaking` scores
    # the BAND (3-12 dB), which is the right reading of the constraint and the
    # wrong reading of a REQUEST: `margins()` accepts `target_peaking_db` and
    # deliberately discards it, so one fixed design scores 8.999984 against
    # targets of 3, 5, 7.5, 10 and 12 dB IDENTICALLY (SPEC_CONDITIONED.md §0).
    # A user asking for 11 dB and receiving 6.4 dB with a PASS beside it is a
    # tool ignoring its own input.
    #
    # **The tolerance is DERIVED FROM A MEASUREMENT, not chosen.** Peaking is
    # itself a PVT quantity: across the 45 mandated corners it moves 1.48-1.65
    # dB on the two compliant designs (and 2.09-2.45 dB on the one that fails).
    # This row is scored PER CORNER like every other row, so a tolerance at or
    # below half that excursion -- ~0.83 dB -- is unmeetable at ANY target by
    # construction, however well centred the design is. 1.5 dB is the smallest
    # round value that admits a correctly-centred design with ~0.67 dB of
    # centring slack left over. Anything tighter is a spec against physics
    # rather than against the circuit.
    # ── THE FREQUENCY BAND, added by session 23. See `V6_SPECS`. ──────────
    #
    # **THE ROW THAT WAS NEVER WRITTEN.** `S3_peaking` is a BAND -- both edges
    # of 3-12 dB enforced. `S3_f_peak` is a DISTANCE FROM TARGET. So until this
    # row existed, **nothing in any spec set required the peak to lie inside
    # S3's stated 1.25-2.5 GHz window.**
    #
    # It survived the whole life of the project because every published run
    # used the window CENTRE as its target, and at the centre the two are the
    # same statement:
    #
    #   target 1.768 GHz (centre) -> S3_f_peak accepts [1.250, 2.500] == window
    #   target 2.253 GHz          -> accepts [1.593, 3.186], +0.686 GHz over
    #   target 1.387 GHz          -> accepts [0.981, 1.962], -0.269 GHz under
    #
    # The coverage sweep was the first experiment ever to ask for an off-centre
    # target and it walked straight into the gap: **4 of 16 delivered designs
    # peaked outside the window and were not penalised**, one of them scoring
    # 45 of 45 corners at 3.174 GHz. G111.
    #
    # Tolerance 0.5 octaves = the window's own half-width, exactly the basis
    # `S3_f_peak` uses. Nothing new is chosen here; the number was always the
    # right one for a band and was being spent on a target instead.
    Tol("S3_f_peak_band", 0.5, "octaves",
        "distance INSIDE S3's 1.25-2.5 GHz window, in octaves -- the frequency "
        "twin of S3_peaking's 3-12 dB band. Half-width of a one-octave window, "
        "the same basis S3_f_peak uses. Positive inside, negative by exactly "
        "how far outside"),
    # **The frequency REQUEST, with a tolerance a user would recognise.**
    # `S3_f_peak`'s 0.5 octaves is +/-41 % in frequency -- half the entire
    # window -- so almost any design peaking anywhere in band "satisfied" any
    # request. Measured on the coverage sweep: asked 2.253 GHz, delivered
    # 1.776 GHz, scored a pass. The optimiser was not cheating; the row told
    # it the frequency request was free, so it spent its budget elsewhere.
    #
    # **0.30 octaves is DERIVED, not chosen.** The peak's own excursion across
    # the 45 mandated corners is **0.23-0.30 octaves** (session 23, measured off
    # the 135-point artifacts), so a tolerance below ~0.15 is unmeetable at any
    # target however well the design is centred, and one at 0.30 is the
    # tightest honest promise: "the peak you asked for, within what process
    # variation itself does to it". Same rule as S3_peaking_match, one axis
    # over.
    Tol("S3_f_peak_match", 0.30, "octaves",
        "distance from the REQUESTED peak frequency. Measured basis: f_peak's "
        "own PVT excursion is 0.23-0.30 octaves across the 45 mandated "
        "corners, so anything tighter is a spec against physics; 0.5 (the "
        "window half-width, which S3_f_peak uses) is +/-41 % and promises "
        "nothing"),
    Tol("S3_peaking_match", 1.5, "dB",
        "distance from the REQUESTED peaking, not from the band. Measured "
        "basis: peaking's own PVT excursion is 1.48-1.65 dB across the 45 "
        "corners on compliant designs, so half-excursion is ~0.83 dB and any "
        "tolerance below that is unmeetable at every target; 1.5 dB leaves "
        "~0.67 dB of centring slack. Parallel in form to S3_f_peak, which "
        "folds its half-width in the same way"),
)

TOL: dict[str, float] = {t.name: t.value for t in TOLERANCES}
SPEC_NAMES: tuple[str, ...] = tuple(t.name for t in TOLERANCES)
#: HOW MANY TOLERANCE ROWS EXIST — **not** how many the reward scores. Those
#: are different numbers since G2 added the two S8 rows: `reward()` sizes its
#: bands from `len(specs)`, so the default (`V1_SPECS`, 7) is what every
#: published number was computed with, while this is 9. Left as the count of
#: rows because that is what the name says; a caller wanting the scored count
#: reads `len(specs)`.
N_SPECS: int = len(TOLERANCES)

#: Reward v0's spec set: **S3 alone**, per §6f. Three rows, because CLAUDEwa.md
#: §3 reads S3 as constraining the peak magnitude, its location, AND the boost
#: at Nyquist, and requires all three to be reported.
V0_SPECS: tuple[str, ...] = ("S3_peaking", "S3_f_peak", "S3_nyq_boost")

#: Reward v1: everything the DEVICE layer can measure. **UNCHANGED by G2**, so
#: every reward number `RL_SMOKE.md` and `BASELINES.md` publish still
#: reproduces bit for bit — including the +8.950669 ceiling (G74), which is a
#: property of this spec set and would move if the set did.
#: **LISTED, NOT DERIVED, AND THAT IS A BUG FIX (session 22o).** This used to
#: read `tuple(n for n in SPEC_NAMES if not n.startswith("S8_"))` -- a rule of
#: EXCLUSION, so **every new tolerance row that was not S8-prefixed joined V1
#: automatically**. Adding S4 and S7 would silently have changed `len(specs)`
#: from 7 to 9, which changes the feasibility bonus `B = N + 1`, which changes
#: **every reward number this project has published**, with nothing in the
#: diff to show for it. Naming the seven makes the set a decision instead of a
#: side effect. `test_v1_is_listed_not_derived` pins it.
V1_SPECS: tuple[str, ...] = (
    "S3_f_peak", "S3_peaking", "S3_nyq_boost",
    "S5_noise", "S6_power", "saturation", "tail_saturation",
)

#: Reward v2: v1 **plus S8**, now that the device->link bridge exists and the
#: link layer is no longer a mock (G2, session 21).
#:
#: **THIS IS A SEPARATE SPEC SET RATHER THAN AN EDIT TO V1, AND THAT IS THE
#: WHOLE POINT.** Adding two rows changes `N_SPECS`, which changes the
#: feasibility bonus `B = N + 1`, which changes every reward number this
#: project has published. `BASELINES.md` §7f is explicit: *"do not touch the
#: evaluator, the reward tolerances, the box or the geometry mapping. If any of
#: those change, every baseline must be re-run."* So v1 keeps its exact
#: arithmetic and v2 is opt-in until a human decides to re-run the baselines
#: against it.
#:
#: What S8 costs to score: `link eval` measured at ~0.04 s on top of a ~0.28 s
#: full-fidelity evaluation, with NO extra simulator call — the eye is computed
#: from the AC curve the same invocation already produced (`G2_RESULTS.md`).
V2_SPECS: tuple[str, ...] = V1_SPECS + ("S8_eye_h", "S8_eye_w")

#: **Reward v3: every row on the competition's own spec slide.** V2 plus S4
#: (HD3) and S7 (area).
#:
#: **FOR VERIFICATION, NOT FOR SEARCH.** The benchmark scores V1 and every
#: published number depends on it; this set exists so the DELIVERED design can
#: be checked against all eleven rows the problem statement lists, which is the
#: checklist a judge holding that slide will run. Scoring the search on V3
#: would change the problem and force a full re-run (sec 7f).
#:
#: Neither new row is expected to bind -- HD3 measured -61.10 dBc against a
#: -30 limit and area 0.001092 mm^2 against 0.05 -- and **that is the finding**.
#: A spec that is free is worth demonstrating, not worth leaving unmeasured.
V3_SPECS: tuple[str, ...] = V2_SPECS + ("S4_hd3", "S7_area")

#: **Reward v4: the JOINT set -- every V3 row, with S4 asked at the operating
#: point instead of at its stated conditions.**
#:
#: Session 22r left the project with two half-designs: one meeting S3 at 135 of
#: 135 points whose eye cannot be computed at any of them, and one meeting S8
#: at 135 of 135 with 3.6x margin that fails S3. **Neither had ever been asked
#: for both**, because V1 (what every search scores) contains S3 and not S8,
#: and V2/V3 contain S8 and have never been searched on.
#:
#: **S8 alone is not enough and that is a measurement, not a guess.** The eye
#: is computed from a small-signal AC fit, so a design can satisfy S8 while
#: being large-signal non-linear at the drive -- the compression gate catches
#: the gross case, but HD3 at Nyquist is the transient-verified version and it
#: relocates rather than removes the failure. `S4_hd3_nyq` is in this set for
#: that reason.
#:
#: V1, V2 and V3 are UNTOUCHED. This set is for search; every published
#: baseline number stays scored on V1 (`BASELINES.md` sec 7f).
#: **`S4_hd3` is NOT in this set, and leaving it in was a bug caught on the
#: first run.** The deck that scores V4 runs ONE transient, at Nyquist and at
#: the drive amplitude. Keeping V3's `S4_hd3` row would have scored the
#: 100 MHz specification using the 2.5 GHz measurement -- 30 dB apart on the
#: delivered design -- which is precisely the two-definitions-of-one-quantity
#: failure `S4_hd3_nyq` was split out to avoid. The 100 MHz row is verified
#: separately by `verify_full`, which runs its own transient at S4's stated
#: conditions.
V4_SPECS: tuple[str, ...] = tuple(
    s for s in V3_SPECS if s != "S4_hd3") + ("S4_hd3_nyq",)

#: **Reward v5: V4 plus the REQUESTED peaking. The DELIVERABLE's spec set.**
#:
#: V1-V4 all read S3's peaking as a band and therefore score a design that
#: lands anywhere in 3-12 dB identically. That is the correct reading of a
#: CONSTRAINT and the wrong reading of a REQUEST, and the competition
#: deliverable is a request: *"takes target specs as input"*. Session 22j
#: measured the consequence -- one design scoring 8.999984 against five
#: different peaking targets -- and called the spec manifold "effectively 1-D".
#: **It is 1-D because this row was missing, not because the problem is.**
#:
#: `S3_peaking` is KEPT alongside `S3_peaking_match`, and that is deliberate
#: rather than redundant: the band is still a hard constraint (a request for
#: 2 dB must not be honoured by leaving S3), and the match row is the request.
#: A design satisfies both or neither is meaningful.
#:
#: **V1, V2, V3 and V4 are UNTOUCHED.** Adding a row moves `len(specs)`, which
#: moves the feasibility bonus `B = N + 1`, which moves every published reward
#: number (`BASELINES.md` §7f). This set is opt-in and is the one the coverage
#: map and the deliverable score on; the benchmark keeps scoring V1.
#: Listed by ENUMERATION, never by addition to another tuple (G101/G106).
V5_SPECS: tuple[str, ...] = (
    "S3_f_peak", "S3_peaking", "S3_peaking_match", "S3_nyq_boost",
    "S5_noise", "S6_power", "saturation", "tail_saturation",
    "S8_eye_h", "S8_eye_w", "S7_area", "S4_hd3_nyq",
)

#: **Reward v5-device: the rows `rl/env.py` can actually score, plus the
#: request.** `V1_SPECS` + `S3_peaking_match`.
#:
#: `CtleSizingEnv._evaluate_current` calls `reward()` with `target_peaking_db`
#: but with **no `link`, no `area_mm2` and no `hd3_nyq_dbc`** -- it measures the
#: device, and the eye needs the link bridge. So an RL run cannot score
#: `V5_SPECS` without either editing `rl/env.py` (rule 7 forbids it without a
#: human decision) or defaulting three rows nobody measured (rule 5 forbids
#: that outright, and `margins()` deliberately omits them so the attempt
#: raises rather than silently succeeds).
#:
#: **This is the honest subset, and the important property survives it:** the
#: spec manifold is still genuinely **2-D**, because `S3_peaking_match` is in
#: it. That was the whole reason RL could not win before -- with the request
#: discarded the manifold was 1-D and a lookup table was provably optimal
#: (`SPEC_CONDITIONED.md` §0).
#:
#: **Training reward and reporting reward are therefore different, and that is
#: stated rather than hidden**: policies train on this, and EVERY arm --
#: policy, library, CMA-ES, random -- is SCORED on the full `V5_SPECS` through
#: one shared evaluator, so the comparison is never between two rewards.
#: Listed by ENUMERATION (G101/G106).
V5D_SPECS: tuple[str, ...] = (
    "S3_f_peak", "S3_peaking", "S3_peaking_match", "S3_nyq_boost",
    "S5_noise", "S6_power", "saturation", "tail_saturation",
)

#: **Reward v6: the set that separates the CONSTRAINT from the REQUEST on BOTH
#: axes. The one the deliverable and the coverage map score on.**
#:
#: V5 carried `S3_f_peak` -- a distance-from-target row -- and nothing else
#: about frequency, so **no spec set in this project had ever required the peak
#: to lie inside S3's 1.25-2.5 GHz window** (G111). V6 replaces that one row
#: with the two it was standing in for, exactly mirroring what peaking already
#: had:
#:
#:     peaking    S3_peaking       (band 3-12 dB)   S3_peaking_match  (request)
#:     frequency  S3_f_peak_band   (band 1.25-2.5)  S3_f_peak_match   (request)
#:
#: **`S3_f_peak` is NOT in this set, and that is not an oversight.** Keeping it
#: alongside both replacements would score the frequency three times and count
#: one miss twice in the shortfall sum. It stays defined, and V1-V5 keep using
#: it, so every published number still reproduces.
#:
#: 13 rows. Listed by ENUMERATION (G101/G106).
V6_SPECS: tuple[str, ...] = (
    "S3_f_peak_band", "S3_f_peak_match",
    "S3_peaking", "S3_peaking_match",
    "S3_nyq_boost", "S5_noise", "S6_power",
    "saturation", "tail_saturation",
    "S8_eye_h", "S8_eye_w", "S7_area", "S4_hd3_nyq",
)

#: **Reward v6-device: V6 minus the rows `rl/env.py` cannot measure.**
#: The RL training set, for the same reason `V5D_SPECS` existed: the env has no
#: link bridge, so the eye, area and HD3 rows would raise rather than default.
#: 9 rows, and the manifold is still genuinely 2-D.
V6D_SPECS: tuple[str, ...] = (
    "S3_f_peak_band", "S3_f_peak_match",
    "S3_peaking", "S3_peaking_match",
    "S3_nyq_boost", "S5_noise", "S6_power",
    "saturation", "tail_saturation",
)

#: The S8 rows, named so a caller can ask "is this reward scoring the eye?"
S8_SPECS: tuple[str, ...] = ("S8_eye_h", "S8_eye_w")

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
            target_peaking_db: Optional[float] = None,
            link: Optional[object] = None,
            hd3_dbc: Optional[float] = None,
            area_mm2: Optional[float] = None,
            hd3_nyq_dbc: Optional[float] = None) -> dict:
    """Signed margins, in natural units. ONE definition (rule 9).

    `meas` is `evaluator.EvalResult.meas`: already in the units
    `contract.OBS_SCALES` declares, so `f_peak_oct` is octaves relative to
    Nyquist and the margins below never touch hertz.

    `target_peaking_db`, when given, produces the **`S3_peaking_match`** row --
    distance from the REQUESTED peaking -- alongside `S3_peaking`, which stays
    the BAND constraint (3-12 dB) that CLAUDEwa.md §3 reads as the requirement.
    Both, not either: the band is what the circuit must satisfy, the match is
    what the caller asked for, and a tool that honours only the first ignores
    its own input (session 23; `V5_SPECS`).

    **Until session 23 this argument was accepted and DISCARDED**, so one fixed
    design scored 8.999984 against targets of 3, 5, 7.5, 10 and 12 dB
    identically (`SPEC_CONDITIONED.md` §0). The row is emitted **only when the
    argument is supplied**, on the same terms as S4/S7/S8 below -- present when
    asked for, absent otherwise, never defaulted -- so `V1_SPECS` through
    `V4_SPECS` select exactly the keys they always did and every published
    reward number still reproduces bit for bit.

    `link` is a `LinkResult` (or None). When given AND `ok`, the two S8 rows are
    added; otherwise they are **ABSENT** from the returned dict rather than
    filled with a default — so a caller asking for `V2_SPECS` without a link
    result gets a `KeyError` in `shortfalls` rather than a reward computed from
    a missing eye. Deliberate: scoring an absent S8 as zero-margin would make
    every design look like it just failed the eye, and scoring it as satisfied
    would be worse.
    """
    from nebula.rl.contract import f_peak_octaves

    pk_lo, pk_hi = SPEC_PEAKING_DB_RANGE
    pk = float(meas["peaking_db"])
    f_oct = float(meas["f_peak_oct"])
    target_oct = f_peak_octaves(float(target_f_peak_hz))

    out = {
        # Distance OUTSIDE the band, as a margin: positive inside, negative by
        # exactly how far outside.
        "S3_peaking": min(pk - pk_lo, pk_hi - pk),
        # §6h's `-|log2(f_peak / f_target)|`, with the half-width folded in so
        # the quantity is a MARGIN like every other row.
        "S3_f_peak": TOL["S3_f_peak"] - abs(f_oct - target_oct),
        # **The BAND. Positive inside S3's window, negative by how far
        # outside** -- the frequency twin of `S3_peaking` above, and the row
        # whose absence let 4 of 16 coverage designs peak past 2.5 GHz
        # unpenalised (G111). Emitted ALWAYS: it is a property of the circuit,
        # not of anybody's request, so there is nothing to be conditional on.
        "S3_f_peak_band": min(f_oct - _F_LO_OCT, _F_HI_OCT - f_oct),
        "S3_nyq_boost": float(meas["nyq_boost_db"]),
        "S5_noise": SPEC_VN_IN_MAX_VRMS - float(meas["inoise_vrms"]),
        "S6_power": SPEC_POWER_MAX_W - float(meas["power_w"]),
        "saturation": float(meas["pair_margin_v"]),
        "tail_saturation": float(meas["tail_margin_v"]),
    }

    # The REQUESTED peaking, only when a request was actually made. Same form
    # as `S3_f_peak` above -- the tolerance folded in so the quantity is a
    # margin -- and present only when asked for, so V1..V4 are untouched.
    if target_peaking_db is not None:
        out["S3_peaking_match"] = (TOL["S3_peaking_match"]
                                   - abs(pk - float(target_peaking_db)))
    # The frequency request, on the same terms: present only when asked for.
    out["S3_f_peak_match"] = (TOL["S3_f_peak_match"]
                              - abs(f_oct - target_oct))

    # S8, only when a real link result is in hand. Both are MEASURED-minus-
    # SPEC margins in the spec's own units, like every other row.
    if link is not None and getattr(link, "ok", False):
        from nebula.common.types import SPEC_EYE_H_MIN_V, SPEC_EYE_W_MIN_UI
        out["S8_eye_h"] = float(link.eye_h_v) - SPEC_EYE_H_MIN_V
        out["S8_eye_w"] = float(link.eye_w_ui) - SPEC_EYE_W_MIN_UI

    # S4 and S7, on the same terms as S8: present only when MEASURED, absent
    # otherwise, never defaulted. A caller asking for `V3_SPECS` without them
    # gets a `KeyError` in `shortfalls` rather than a reward computed from a
    # spec nobody checked.
    #
    # Both are "limit minus measured" so that positive means satisfied, like
    # every other row. HD3 is a NEGATIVE dBc number and more negative is
    # better, so the margin is `limit - measured`: at -61.10 dBc against a -30
    # limit the margin is +31.10 dB.
    if hd3_dbc is not None:
        out["S4_hd3"] = SPEC_HD3_MAX_DBC - float(hd3_dbc)
    if hd3_nyq_dbc is not None:
        out["S4_hd3_nyq"] = SPEC_HD3_MAX_DBC - float(hd3_nyq_dbc)
    if area_mm2 is not None:
        out["S7_area"] = SPEC_AREA_MAX_MM2 - float(area_mm2)
    return out


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
    link: Optional[object] = None,
    lambda_cost: float = 0.0,
    sim_cost: float = 0.0,
    target_peaking_db: Optional[float] = None,
    headroom: Optional[Mapping[str, float]] = None,
    hd3_dbc: Optional[float] = None,
    area_mm2: Optional[float] = None,
    hd3_nyq_dbc: Optional[float] = None,
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

    # **`link` was accepted and never forwarded, so `V2_SPECS` raised
    # `KeyError('S8_eye_h')` through this function and the eye was UNSCORABLE
    # -- a spec set with tolerances, a docstring and no reachable caller
    # (G73's family). Fixed in session 22o along with S4 and S7.**
    m_all = margins(meas, target_f_peak_hz, target_peaking_db, link=link,
                    hd3_dbc=hd3_dbc, area_mm2=area_mm2,
                    hd3_nyq_dbc=hd3_nyq_dbc)
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
    "V0_SPECS", "V1_SPECS", "V2_SPECS", "V3_SPECS", "V4_SPECS", "V5_SPECS",
    "V5D_SPECS", "V6_SPECS", "V6D_SPECS",
    "S8_SPECS",
    "TOLERANCE_SCAN",
    "feasible_bonus", "invalid_reward", "headroom_band_top",
    "headroom_reward",
    "margins", "shortfalls", "RewardBreakdown",
    "reward", "reward_v0", "reward_v1",
)
