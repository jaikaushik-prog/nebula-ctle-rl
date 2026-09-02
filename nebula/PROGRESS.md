# PROGRESS.md — the lean brief

**Purpose:** the 10-minute version of where Nebula stands. `HANDOFF.md` remains
the heart of the project and is still updated with every change; this file is
the index into it — decisions, architecture, and what to do next, with nothing
that a reader can reconstruct from the code.

**Read `CONTINUE_HERE.md` §§4, 5 and `HANDOFF.md` §9 gotchas before touching
anything.** This file does not replace them.

**FRESH CHAT? READ `nebula/SESSION_27_HANDOFF.md` FIRST** — it is where
session 27 stopped, mid-experiment, and it names the one command to run next.

**If you are here to build the SAC + CMA-ES hybrid, read
`nebula/NEXT_AGENT_SAC.md`** — it is the implementation brief, and its §2
carries three design traps found by measurement that will otherwise cost a day
each.

**Updated 2026-08-22, session 26c.** 24 days to the 15 Sept deadline.

---

## 1. What this project is, in five lines

Given a target CTLE specification, produce a **transistor-level SKY130 design
that meets every competition spec across 45 PVT corners × 3 loads = 135
points**, using far fewer SPICE simulations than a parameter sweep, with no
human in the loop. Deliverables that already exist and run:

    python -m nebula.design --peaking 9 --f-peak 1.9e9 --robust --verify --out out/
    python -m nebula.llm "I need about 9 dB of peaking with the peak near 1.9 GHz"

---

## 2. Status at a glance

| | state |
|---|---|
| Test suite | **2433 passed**, 13 deselected, 346 s, measured 2026-09-02 (session 33); one timing-flaky test, **G136** (`python -m pytest tests nebula/tests -q -m "not slow"`). The **system** interpreter, not the conda env — that env has no `torch`, and `ngspice_con.exe` is found by absolute path anyway (G69) |
| Gates G0–G2 | passed |
| G3 (RL beats random + grid) | **fails one clause** — RL is indistinguishable from random at every budget |
| G4 (corner-robust design) | met on `V1_SPECS` (7 rows); **not** on the 11 competition rows |
| Eleven-row compliance | **no design meets all 11 rows at all 135 points.** Two designs miss on opposite sides of one row |
| **Mandated 45-corner coverage** | **14 of 16 ON THE DELIVERED PATH** (entry 69: `design.py --method auto`, verified end to end, 8 controls, none lost). Was 8 at the start of session 33. **The 135-point load grid stays 0 of 16** -- this project's own extra axis, which the brief does not mandate |
| **Tunable-bank compliance (D10)** | **45 of 45 mandated corners served by at least one bank setting**, one request (7.5 dB @ 1.768 GHz), design load, `V5_SPECS` (section 5z; `experiments/tuning_bank_results.json`). S3 frequency window **100 %** covered against the same fixed design's **0.0 %**. Boost range reaches only **4.41-8.56 dB** of S3's mandated 3-12; two corners have **one** passing setting and therefore no tuning margin |
| **Wide bank, one fixed part** | **8 of 16** requests served at all 45 mandated corners, `V6_SPECS`, 64 codes x 45 corners = 2 880 decks (section 5aa; entries 70-71). **Six of the eight need only ONE code**, so the knob is decoration across PVT and load-bearing only across REQUESTS. Not comparable with entry 69's 14 of 16 -- different evaluator and a stricter S4 row |
| **Channel axis (NEW, entry 72)** | **The stage saturates on SHORT channels.** Scorable points fall 2 117 -> 0 as loss falls 12.0 -> 3.0 dB; even the lowest-boost code over-drives by **1.43x** at 3 dB. No bank code fixes it -- the binding quantity is **total gain**, not peaking. **Gain control (VGA/AGC) is the missing knob**, and every number in this repo was measured at `FUNNEL_LOSS_DB = 12.0`, the family's worst member and this stage's easiest (section 5ab) |
| **The AGC question (entry 73)** | **The load is NOT a gain knob.** Cutting `rl` to 0.29x of base cut demand AND capability by ~69 %, leaving the compression ratio invariant at **1.48x -> 1.46x**. The missing block is **INPUT attenuation ahead of the CTLE**, not a load trim (section 5ac). No VGA built -- a topology decision for the owner; the requirement is now one number, **1.44-1.52x at 3 dB** |
| Deliverable output | `design.py --out` writes `design.json`, `design.cir` **and `design_schematic.png`** — a drawn schematic rendered FROM the deck, annotated with the sized values, marked **NOT DELIVERED** when the run did not pass (session 33) |
| Report | `nebula/report/Nebula_CTLE_Report.pdf`, rebuilt from artifacts. **Its RL chapter stops at PPO and the budget ladder** — entries 34-54 have not reached it |

### The two candidate designs

| | `57cba07581cd` (delivered) | `c507a3ba6f58` (joint winner) |
|---|---|---|
| rows PASS / FAIL / NOT MEASURABLE | 9 / 0 / 2 | **10 / 1 / 0** |
| min normalised margin | +0.021 | −0.015 |
| eye | not measurable anywhere | **135 of 135**, 368.8–497.3 mV |
| f_peak PVT spread | **0.938 oct** | 0.99979 oct |

---

## 3. Decisions made (session 23, by the owner)

| # | Decision | Consequence |
|---|---|---|
| D1 | **Extend the search screen with mixed `sf`/`fs` corners.** Closes `CONTINUE_HERE.md` §5 OPEN item 2 | Delivery screen becomes 4 (corner, load) pairs. `s9_yield.SCREEN_CORNERS` and every published benchmark arm stay untouched — no `BASELINES.md` §7f re-run |
| D2 | **The screen must re-check itself** against the full 135 points; any corner that beats the screen's prediction is added mid-run | Removes the dependence on the screen being guessed correctly. Implemented free: the audit rides on the verification every winner needs anyway |
| D3 | **Global, spread-first search** — global CMA-ES, seeded by the zero-simulation library lookup plus AC-only spread probes | Targets the low-excursion family the local search cannot reach |
| D4 | **Ship the tuning bank live, and report BOTH readings of S3** | See §5 |
| D5 | Maintain this file alongside `HANDOFF.md` | `HANDOFF.md` stays the source of truth; this is the entry point |
| **D6** | **Make `target_peaking_db` LIVE.** A judge asking for 11 dB must not be handed 6.4 dB with a PASS beside it | `V5_SPECS` + `S3_peaking_match`. **V1–V4 bit-identical**, pinned by test, so no `BASELINES.md` §7f re-run |
| **D7** | **The deliverable is the FRAMEWORK, not one design.** Measure *spec coverage* — for every request a judge might type, does the framework return a PVT-compliant circuit? | `exp_coverage.py` is now the centrepiece. The single-design searches are demoted to one cell of its grid |
| **D8** | **Search on the MANDATED 45-corner grid; report the 135-point load sweep separately** | The slide mandates PVT (5 process × VDD±5% × 0–125 °C = 45) and says nothing about load. See §5 |
| **D9** | **The competition mentor approved the SAC + CMA-ES hybrid — CONDITIONALLY** (2026-08-26): the approach is fine enough **if the SAC contributes as RL** | **Unblocks `NEXT_AGENT_SAC.md` stages 1–3**, which its §8 item 1 had gated on exactly this answer. **The condition is the deliverable, not a formality** — it does not approve a hybrid in which the policy is decoration and CMA-ES does the work, which is what today's numbers describe. Discharged by `exp_hybrid`'s **accept rate** against the non-RL baseline of **6 of 16 accepted / 35.6 % fewer decks** (entry 32). A SAC proposer that does not beat that has **not** contributed as RL, and reporting that is the honest outcome |
| **D10** | **Build the tunable bank as the delivered topology, and put the RL on the ADAPTATION problem** (owner, 2026-09-02, session 34). Reading (B) of S3: one sized part plus a switched `Rs`/`Cs` code, chosen per part. **This is a topology change and therefore required a human decision (CLAUDEwa.md sec 8 rule 5).** | Unblocks `exp_tuning_bank` (measured, section 5z) and the adaptation environment. The RL is scored on **trials-to-lock with an asymmetric false-lock penalty**, against an exhaustive control AND a hand-written bisection heuristic -- the matched control entry 47 established as mandatory. Architecture chosen: **wide bank on ONE fixed part**, not a per-request trim bank |

---

## 4. Architecture — the tiered evaluator

Replaces "score every candidate on a fixed 3-corner screen".

```
Tier 0   analytic prescreen (exists)                 0 SPICE
   |
Tier 1   SPREAD PROBE, AC only, 2 extremes           2 SPICE   f_peak spread + centre
   |     reject if spread > 0.97 octaves
Tier 2   EDGE-4 screen, full 11-row V4 reward        4 SPICE   == full-135 worst, exactly
   |
Tier 3   full 135-point verification               135 SPICE   winners + the self-check (D2)
```

### The EDGE-4 screen, and the evidence for it

```
TOP    of the window (f_peak too HIGH)   sf/1.05/0C @ 14 fF   and ff/1.05/0C @ 14 fF
BOTTOM of the window (f_peak too LOW)    fs/0.95/125C @ 78 fF and ss/0.95/125C @ 78 fF
```

Measured against the full 135 points on every design ever fully verified:

| design | true worst @135 | EDGE-4 says | current 3-corner screen says |
|---|---|---|---|
| `c507a3ba6f58` | −0.015150 | **−0.015150** (exact) | −0.000576 (+0.0146 wrong) |
| `57cba07581cd` | +10.021015 | **+10.021015** (exact) | +10.034191 (+0.0132 wrong) |
| `c9d52866743dc1ff` | −0.023681 | **−0.023681** (exact) | **+10.002082 — calls an infeasible design feasible** |

**Why it is a mechanism and not a curve fit.** The CTLE's peak is set by an
R×C product. `sf`/`fs` are the extreme **passive** corners (`sky130_runner.py`
line 101: the library carries the full 5×5 MOS × passive cross product), and
the circuit is nfet-only, so `sf ≈ ff` and `fs ≈ ss` in the transistors and
differ **only** in the R and C that set the peak. Additionally, over 135
points the peak frequency is **perfectly monotone in temperature (135/135) and
in load (135/135)**, so hottest+heaviest is always the low end and
coldest+lightest always the high end. Supply voltage is **not** reliably
monotone (27/43 on one design), which is why both supply ends are kept.

D2's self-check covers the residual risk: the evidence is 3 designs plus a
mechanism, which is good but is not proof.

---

## 4b. THE LOAD AXIS — the finding that reframed the project

**Two thirds of the difficulty this project has been fighting comes from an
axis the competition never asked for.**

The slide mandates *"PVT (TT, SS, FF, SF, FS; VDD ±5%; 0–125 °C)"* = 5 × 3 × 3
= **45 corners**. It says nothing about load capacitance. This project has been
grading itself on **135 points** — those 45 corners × 3 load capacitances
spanning **5.7×** — a third axis of our own (`CL_RANGE.md`).

Decomposing the f_peak PVT excursion by axis, over the 135-point artifacts:

| what varies | share of the total excursion |
|---|---|
| **load capacitance (our axis)** | **56 – 74 %** |
| temperature | 18 – 21 % |
| process | 8 – 22 % |
| supply voltage | 0.5 – 0.7 % |

| grid | excursion | headroom in S3's 1.000-oct window |
|---|---|---|
| 45 mandated corners, design load | **0.23 – 0.30 oct** | **+0.70 oct** |
| 135 points, load swept | 0.94 – 1.02 oct | ~0.00, sometimes negative |

**Consequence, verified bit-identically on an independent re-run
(max Δreward = 0.000e+00 over 135 points):** design `c507a3ba6f58` passes
**all 11 competition spec rows at 45 of 45 mandated PVT corners** at the design
load — every margin positive, tightest `S3_f_peak` at +0.296 of a 0.5
tolerance — and at the heavy load too. It fails only at the *lightest* load, at
4 corners.

**This is not a shortcut, and the reason is dated.** `CL_RANGE.md` §9, written
**2026-08-06**, two weeks before any of these results existed:

> *"'Screen `cl` like a PVT corner' is a conservative reading, and **arguably
> too conservative**. Temperature varies during operation; `cl` does not. It is
> **fixed the moment the following stage is laid out, and known to the designer
> at that point**… the yield it produces should be read as **a lower bound on
> what a tunable part could achieve**."*

The methodological error being corrected: we let a **design-time uncertainty**
("we have not built the DFE summer yet") masquerade as an **operating
condition** ("the load varies at runtime"). Only the second belongs in a PVT
grid. Process belongs because you cannot measure which die you got; load does
not, because you can read it off the layout you drew.

**Reporting rule (D8):** the 45-corner column is **compliance**; the 135-point
column is **robustness characterisation**, always shown, never merged into the
PVT claim, and never dropped. Dropping it would be the actual shortcut.

---

## 5. The S3 reading — the session's other big finding

The competition slide says:

> HF peaking boost 3–12 dB (**tunable** 1.25–2.5 GHz)

**Reading (A)** — one fixed design's peak stays inside 1.25–2.5 GHz at all 135
points. This is what every result in this project has assumed.

**Measured consequence of reading (A):** PVT alone moves the peak by ~0.94–1.00
octaves, and the window *is* exactly 1.000 octave. So the nominal peak has
almost no freedom:

| design | judge may request a peak anywhere in | as % of the requested range |
|---|---|---|
| `57cba07581cd` (spread 0.938) | **1.693 – 1.768 GHz** | **4.4 %** |
| `c507a3ba6f58` (spread 0.99979) | 1.768 GHz exactly | **0.0 %** |

**Under reading (A) the spec is unsatisfiable except at dead centre.** A judge
asking for a peak at 1.5 GHz or 2.2 GHz cannot be served by any design.

**Reading (B)** — "tunable" governs both ranges, exactly as it does for the
3–12 dB: the circuit carries a tuning bank covering 1.25–2.5 GHz, and PVT drift
is absorbed by re-tuning. This is how production adaptive CTLEs work, and the
same slide asks for *"source degeneration (**variable Rs, Cs**)"*.

**Decision D4: build for (B), report both.** The compliance criterion under (B)
is stated up front so it cannot be softened later:

> **At every one of the 135 PVT points, at least one bank setting meets all
> eleven spec rows** — and the setting used is reported per point.

### What the existing bank does and does not do

`experiments/exp_tunable_trade.py` holds **`Rs × Cs` constant** so the zero —
and the peak — deliberately **does not move**; it is a *peaking* bank (3–12 dB),
not a *frequency* bank. Reading (B) needs the second axis: `Cs` varied with
`Rs` held, which moves the zero and the peak. Measured sensitivity:
`cs_sensitivity_oct_per_box = 3.243 oct/box`, so ~2 octaves of `Cs` buys
~1 octave of peak frequency — comfortably inside the box.

**G63 applies:** the search path uses **drawn** passives
(`build_point(real_passives=True)`), so a bank setting **cannot** be applied
with ngspice `alter` — it needs a re-generated geometry and a real re-parse.
Budget each setting as a full SPICE run.

---

## 5a. THE COVERAGE SWEEP — first result, and the retraction it forced

**Run 2026-08-21. 16 requests, 16 094 SPICE runs, 149.7 min.**
`PREDICTIONS.md` entry 24 has the full scoring: **5 of 6 predictions hit**; Q6
was **not scorable because I pre-registered a quantity and then failed to log
it** — recorded as a miss of experimental design, not as a null.

    solved on the search screen        11 / 16
    MANDATED 45-corner PVT grid        10 / 16   <- RETRACTED, see below
    135-point load-swept grid           0 / 16
    screen self-check                  15 / 16 predictive, worst optimism +0.018427
    screen grew                        4 -> 5 points

**The screen works.** 15 of 16 audits found `EDGE4_MANDATED` predictive on the
grid it targets, worst error +0.018. The "4 corners instead of 45" claim is
sound, at a measured 1 046 SPICE runs and ~8.7 min per request.

**RETRACTION: 10 of 16 is at most 9 of 16.** The sweep exposed **G111** —
nothing in this project has ever required the peak to lie *inside* S3's
window — and 4 of 16 delivered designs peak outside it, one of them scoring
45/45 at **3.174 GHz**. Fixed (§5b); the corrected number comes from the
re-run, which is owed.

---

## 5b. **G111 — the frequency band constraint that was never written.** FIXED; RE-RUN OWED

**Found 2026-08-21 by the coverage sweep. Fixed the same day. The re-run is
committed work and MUST NOT be dropped.**

`S3_peaking` is a **band**: `min(pk - 3, 12 - pk)`, both edges enforced.
`S3_f_peak` is a **distance from target**: `0.5 - |f_oct - target_oct|`.
**So no spec set — V0 through V5, every published run, the whole benchmark —
ever required the peak to lie inside 1.25-2.5 GHz.**

It hid because **every published run targeted the window centre**, where the
two statements coincide exactly:

    target 1.768 GHz (the centre) -> accepts [1.250, 2.500] GHz == the window
    target 2.253 GHz              -> accepts [1.593, 3.186] GHz, +0.686 over
    target 1.387 GHz              -> accepts [0.981, 1.962] GHz, -0.269 under

The coverage sweep was the **first experiment ever to ask for an off-centre
target**. Measured consequence — 4 of 16 designs outside the window, unpenalised:

    asked 2.253 GHz -> delivered 3.174 GHz  (+0.674 past the ceiling)  45/45 PASS
    asked 2.253 GHz -> delivered 3.061 GHz                             43/45
    asked 1.921 GHz -> delivered 2.949 GHz                              9/45
    asked 1.627 GHz -> delivered 2.933 GHz                              0/45

**The general rule, now G111:** for every spec that is a RANGE, confirm that
one row enforces the range and a **different** row enforces the request. One
row cannot do both except at a single point.

### The fix, and the second half of the same defect

| axis | band (constraint) | match (request) |
|---|---|---|
| peaking | `S3_peaking`, 1.0 dB | `S3_peaking_match`, 1.5 dB |
| frequency | **`S3_f_peak_band`, 0.5 oct** (new) | **`S3_f_peak_match`, 0.30 oct** (new) |

`S3_f_peak`'s 0.5-octave tolerance was **also** too loose as a request: ±41 %,
half the whole window, so any design peaking anywhere in band satisfied any
request. Measured: *asked 2.253 GHz, delivered 1.776 GHz, scored a pass.* The
optimiser was not cheating — the row told it the frequency request was free.
0.30 octaves is **derived** from f_peak's own 0.23-0.30 octave PVT excursion:
anything tighter is a spec against physics.

**`V6_SPECS` (13 rows) carries both new rows and DROPS `S3_f_peak`** — keeping
all three would count one frequency miss three times in the shortfall sum.
`V6D_SPECS` (9 rows) is the device-measurable half, for RL training.
**V1–V5 untouched**, pinned by test.

**Owed:** re-run the coverage sweep on V6 and **publish both numbers**. The gap
between the loose and honest counts is itself the measurement of how much the
old rule was flattering us.

---

## 5c. OPEN DEBT — superseded, retained for the record

**The original §5b entry described only the loose-tolerance half of G111.**
Kept because rule 10 forbids deleting a superseded finding: the entry was
correct as far as it went, and it missed that the *band* row was absent
entirely, which is the larger half.

`S3_f_peak`'s margin is `0.5 - |f_oct - target_oct|`, and **0.5 octaves is half
of S3's entire window**. That is the right number for the question *"is the
peak inside 1.25-2.5 GHz?"* and close to meaningless for *"did you deliver what
was asked?"* — almost any design peaking anywhere in the window satisfies any
frequency request.

Measured, from the live coverage run:

    asked 4.0 dB @ 1.921 GHz  ->  delivered 4.98 dB @ 2.734 GHz  ->  scored PASS

**A 42 % miss on the number the user typed, reported as compliant.** Identical
in shape to the `target_peaking_db` defect fixed earlier the same session
(D6/`S3_peaking_match`): a row written for a constraint, later reused for a
request, without the tolerance being re-derived.

**The fix**, same shape as D6: a separate `S3_f_peak_match` row, tolerance
derived from measurement rather than convenience. The peak's own PVT excursion
across the 45 mandated corners is **0.23-0.30 octaves**, so a tolerance below
~0.15 octaves is unmeetable by construction; **~0.30-0.35 octaves** is the
honest promise. `S3_f_peak` stays as the band constraint, exactly as
`S3_peaking` stayed alongside `S3_peaking_match`.

**Deliberately NOT changed mid-run** — it would corrupt the sweep in progress.
Plan: report the sweep under the loose rule, re-run under the honest rule,
**and publish both.** The difference between the two coverage numbers is itself
the measurement of how much the loose tolerance was flattering us.

---

## 5d. THE SEARCH WAS RANKING ON A FLAT SCORE — fixed, pre-registered, SWEEP NOT YET RUN

**Sessions 25-26. `HANDOFF.md` §9 G116. This is the current front of the
project and the reason the sweep in §6 is owed.**

The seeding fix (§5a, `PREDICTIONS.md` entry 29) took coverage from 6/16 to
8/16 and then **traded one failure mode for another**: at 10 dB the requested
boost started landing accurately and the *frequency* blew out by a factor of
seven. Entry 29 recorded that as **unexplained rather than guessed at**. It is
now explained, and it was not the seeder.

**`reward_v1` scores an infeasible design as `-sum(min(v, 1.0))`**, where `v` is
each row's shortfall in units of its own tolerance. **Past one tolerance a row's
penalty stops growing**, and `TOL["S3_f_peak_match"]` is 0.30 octaves. So every
badly-placed peak scores the same. Read from
`coverage_results_AFTER_seeding_fix.json` — all four out-of-window requests
scored **exactly -2.000000**, an integer, because it is just *how many rows are
saturated*:

    ask  4.0 dB @ 2.253 GHz  ->   4.33 dB @  8.413 GHz  (+1.901 oct)  0/45
    ask 10.0 dB @ 2.253 GHz  ->  10.74 dB @ 11.778 GHz  (+2.386 oct)  0/45
    ask 10.0 dB @ 1.627 GHz  ->  10.55 dB @ 10.684 GHz  (+2.715 oct)  0/45
    ask 10.0 dB @ 1.387 GHz  ->  10.15 dB @ 10.303 GHz  (+2.893 oct)  0/45

**A CTLE peaking at 10.3 GHz and one peaking legally at 2.5 GHz were the same
number to the optimiser.** The gradient pulling a runaway peak back into the
window was exactly **0.0**. The search was not failing — it could not tell its
candidates apart.

**The fix is a wrapper, per §8 rule 7.** `experiments/search_score.py` gives the
*search* an uncapped score to rank on; the *verdict* stays `reward_v1`'s clipped
number. `reward_v1.py`, the tolerances, `V1_SPECS`, the box, the pre-screen and
`baselines.py` are **untouched** — measured, not asserted. Below one tolerance
the new score is the old one times a positive constant, so **the eight requests
that already pass provably cannot be re-ranked**. `rank_unclipped=False`
reproduces the old behaviour exactly, so the two regimes are comparable by test
rather than by argument.

**A second instance of the same bug** was found in
`adaptive_screen.evaluate_at_points`, which picked a design's worst PVT point on
the clipped number — so with two saturated points, "worst" was whichever tied
first, i.e. arbitrary. **Two consumers found; the grep for others is not done.**

**Status: 34 tests pass, including 3 that had never executed anywhere** (they
need the SKY130 PDK, which `rl/contract.py` reads at module load — G118); three
sabotage runs, one of which **stayed green and exposed a test that asserted
nothing** (G117). `PREDICTIONS.md` **entry 30 is committed ahead of the run**
with five falsifiable predictions, a 10-13/16 band, a no-regression clause, and
a disclosure that the plateau was confirmed by a zero-SPICE re-score first.

**THE SWEEP RAN on 2026-08-22** (`--run`, 16 requests, 13 718 sims, 96.6 min;
artifacts `coverage_results_AFTER_unclip_fix.json` + the matching `.jsonl`).
**Entry 30 scored 2 of 5. See §5e.**

**The pre-agreed decision rule, chosen by the owner before the run and not
renegotiable after it:** keep PPO if the sweep shows it can learn, defined as
**>= 5/16**; below that, drop PPO and implement SAC per `NEXT_AGENT_SAC.md`.
**Applied as written: 7/16 >= 5/16, so PPO stays.**

---

## 5e. THE SWEEP RESULT — the mechanism is confirmed, the headline is a MISS

**`PREDICTIONS.md` entry 30 OUTCOME. `HANDOFF.md` §9 G120, G121.**

**2 of 5 predictions confirmed, 3 falsified.** The mandated coverage number
**went down**, 8/16 -> 7/16, against a predicted 10-13/16.

| | prediction | falsifier | result | |
|---|---|---|---|---|
| Q1 | 45-corner coverage 10-13/16 | <= 9 | **7/16** (was 8) | **MISS** |
| Q2 | >= 2 of 4 plateau requests at 45/45 | <= 1 | **0 of 4** | **MISS** |
| Q3 | no peak above 4 GHz | any above | **all 4 below 2.4 GHz** | **HIT** |
| Q4 | >= 7 of 8 solved still pass | <= 6 | **6 of 8** | **MISS** |
| Q5 | sims within 12 346-15 090 | outside | **13 718, identical** | **HIT** |

**What worked.** Every runaway peak came home and every one rose off the
-2.0000 plateau:

    ask 10.0 dB @ 2.253 GHz   10.74 dB @ 11.778 GHz -> 10.79 dB @ 2.370 GHz
                              screen -2.0000, 0/45  -> screen +14.0472, 43/45

Three more went 0/45 -> 11, 20 and 6 of 45. **The G116 diagnosis is established:
the search could not tell its candidates apart, and now it can.**

**Why the headline still fell — this is the finding (G121).** The aggregate moved
strongly the right way while the binary moved the wrong way:

    solved on the search screen        9 -> 11
    MANDATED 45-corner (all 45)        8 ->  7    <- the falsified number
    AGGREGATE corner passes          459 -> 585 of 720   (+126, +27 %)
    improved / regressed / unchanged   8 /  2 / 6

**Neither regression violated a spec (G120).** `6.0 dB @ 1.387` (45->44) and
`8.0 dB @ 1.627` (45->34) both kept a **positive** `pvt45_worst` -- every corner
that could be *measured* passed. The lost corners are **unmeasurable eyes**. On
the 34/45 case the delivered design moved by **0.12 dB and 19 MHz** and 11
corners swung: **CMA-ES is path-dependent, and an invariance proof over the
scoring is not one over the route.** Entry 30's Q4 predicted that mechanism and
still got the number wrong; it is recorded as a miss, not a partial hit.

**Not done, on the pre-registered instruction:** `SEARCH_TAIL_W` and
`SEARCH_ROW_CAP` were **not touched** after seeing the result, and `reward_v1.py`,
the tolerances and `baselines.py` remain untouched. Entry 30 committed in advance
that this branch points at **reachability** -- the tuning bank (§6 item 7) or the
200-evaluation budget -- not at a third scoring heuristic.

**Open:** why `n_unscorable` rose 74 -> 133 over the 135-point grid, and whether
the 45/45 cliff (four requests now at 40, 43, 44, 44 of 45) is the binding
constraint rather than the search.

---

## 5f. STAGE 0 OF THE SAC BRIEF — the wrapper is built and pre-registered, NOT measured

> **Read §5g next: it HAS since been measured.** This section is the record of
> what was built and predicted *before* any number existed, kept unedited so the
> pre-registration stays readable in its original form. The result is in §5g.

After entry 30 scored 2 of 5, the owner stopped the coverage/unclip line and said
to start the SAC track. `NEXT_AGENT_SAC.md` §4 orders **stage 0 first, before any
learning code**: a wrapper that asks a *proposer* for a design, scores it on the
live 4-corner screen, **delivers it if feasible and otherwise runs today's CMA-ES
search unchanged**. That is `experiments/exp_hybrid.py` (session 26).

**What it is for.** The deliverable's claim is *"fewer search spaces, lowest
design time"*. The honest form of that is **not** "RL beats CMA-ES" — it is an
**amortisation curve**: simulations per request falling as the proposer improves.
With the library lookup as proposer this file produces the **control**; a future
SAC policy produces the treatment against the same grid, screen, verifier and
schema. **It is a cost claim. No coverage improvement is claimed.**

**Four decisions that make the claim checkable rather than hopeful.**
1. **Call, don't copy.** The fallback is a literal `exp_coverage.solve_request`
   call with `exp_coverage`'s own seed formula. A test bans `method_cmaes`,
   `CmaConfig` and `BudgetExhausted` from the source so nobody reimplements the
   search — one CMA-ES path, one place it can be wrong.
2. **The safety property, stated precisely.** Not "coverage cannot get worse" but
   **"no worse search"**: a fallback request is bit-identical *given the same
   archive*, and an accepted proposal changes what enters the archive. Written
   into the docstring rather than discovered later.
3. **The proposal is scored on the LIVE screen**, not on `EDGE4_MANDATED` as the
   brief literally says, so it cannot get an easier bar than the fallback it is
   compared against (G32). Deliberate, documented, pinned by a test.
4. **`n_sims` is the SUM of both paths**, and the 135-point verification is never
   added to it. Three cost lines in the report, never one.

**Two facts established before any measurement, both bounding what stage 0 can
possibly show.**
- **The search is budget-bound, not convergence-bound.** The pre-fix and post-fix
  coverage sweeps cost **exactly 13 718 decks each** (200 evaluations per
  request, essentially always spent). So amortisation is entirely about
  *skipping* requests, never about converging faster, and the total is
  arithmetic: `64 + (16 - n_accepted) x 857`. **At zero acceptances the hybrid
  costs 64 decks MORE than the plain search.**
- **The library proposer cannot outrank the search's own seeding.**
  `choose_start` already probes the top `N_LIBRARY_SEEDS = 4` library candidates,
  and the proposal is `k=1` — a subset. It can only ever **short-circuit**, never
  discover.

**The signal that makes the cheap scan worth running first.** All 16 requests
already have a library candidate within both tolerances (worst `dev` = 0.039 of
tolerance) that passes **all 9 pool-evaluable specs at nominal** — and yet the one
real-SPICE data point, request 5 (6.0 dB @ 1.387 GHz, nominally clean), scored
**-15.5 with 2 of 4 screen corners unscorable**: output swing 2179.8 mVpp against
a 520.5 mVpp linear limit. The stage compresses, so the AC/pole-zero eye model
stops applying and the eye **cannot be computed**. That is *"cannot be measured"*,
not *"fails a spec"* (G107), and it is why the 64-deck scan runs before the
90-minute sweep.

**Pre-registered as `PREDICTIONS.md` entry 31**, seven predictions with bands and
falsifiers: **0 or 1 of 16** accepted (75 %); dominant rejection bucket
**unscorable > infeasible** (65 %); swing compression named in the majority of
unscorable reasons (70 %); plumbing exactly 16 proposals / 64 decks (90 %); the
negative-saving consequence (85 % given the first); and conditionally, coverage
unchanged at **7/16 +-1** (70 %) with total decks within 10 % of the arithmetic
(70 %).

**Also learned, the hard way (G122).** Proving the new gates meant sabotaging
them. With `--proposals` mis-routed to the sweep, one test had patched only
`scan_proposals`, so it called the **real** `run()` — live ngspice, the run lock
taken, the unit suite hung and killed at 120 s. A second sabotage made the scan
write `RESULTS`, and the one test that had not redirected it (correct code never
writes it) dropped a real results file into `experiments/`. **A sabotage test must
not be able to spend money:** patch the expensive path with something that
*raises*, and redirect every output path the module owns — including the ones
correct code never writes, because the sabotage is exactly when it writes them.

---

## 5g. THE SCAN RESULT — 5 of 5 confirmed, and the free proposal dies on SWING

**Measured 2026-08-22 (session 26b).** `--proposals`: 16 requests, 16 proposals,
**64 decks**, 250.4 s, exit 0. Artifact `hybrid_proposal_scan.json` (tracked).
Full scoring in `PREDICTIONS.md` entry 31's OUTCOME; nothing above its OUTCOME
heading was edited.

**1 accepted / 1 measured-but-infeasible / 14 unscorable.** Entry 31 went **5 of
5** on the cheap mode: acceptance in the predicted 0–1 band; unscorable the
dominant bucket by 14 to 1; the swing mechanism named by **14 of 14** rows
(unanimous, where a bare majority was predicted); the plumbing exact at 16
proposals and 64 decks; and the saving exactly at its pre-registered ceiling of
**793 decks = 5.78 %**. Q6/Q7 concern the full sweep and are unmeasured.

**The finding, in plain terms: the library gives designs that hit the requested
peak and cannot swing hard enough to carry the signal at the corners.** Every one
of the 14 failures is the same condition — needed output swing **343.5–2179.8
mVpp** against available **112.2–1225.4 mVpp**. Thirteen of the 14 failed at
**4 of 4** screen points, so the single smoke data point that motivated the
prediction (2 of 4) was the *mildest* case, not a typical one.

**Why §5f's "all 16 are clean at nominal" and this are both true.** The screen
has **no nominal point** — its four points are PVT extremes — so nominal
cleanliness was never re-measured here, and the distance between the two is the
result. Related and easy to misread: the delivered values in the table are the
**worst corner**, not nominal, which is why one row shows a 0.72-octave frequency
error against a nominal match of ~0.012 octaves. That is corner drift, not a
lookup bug.

**The pre-committed rule fires against running the sweep.** `n_accepted = 1` is
`<= 1`, so the 90 minutes would buy a confirmation of arithmetic already known.
Applied as written rather than renegotiated after seeing the number — the same
discipline §5e used. **The owner decides.** Nothing was touched to make
acceptance look better (§8 rule: the tolerances, screen, `V6_SPECS`, box,
`reward_v1.py`, `SEARCH_TAIL_W`, `SEARCH_ROW_CAP` are all as they were).

**The lever, named but not pulled (row 4h).** The library ranks on target match
alone; swing headroom is nowhere in its criterion, though the pool already
records `pair_margin_v` and `tail_margin_v`. Re-ranking would cost zero
simulations — but it **redefines the control** a future SAC policy is scored
against, and that is a decision to take deliberately, not a tweak.

> **CORRECTION (2026-08-22, §5h).** The second half of that paragraph is wrong
> and was asserted without being checked. **`pair_margin_v` / `tail_margin_v` are
> not swing.** They are DC operating-point headroom (`vds - vdsat`); the screen
> rejects on `vout_swing_v`, a **measured 1 dB compression point** that needs a
> swept simulation. The pool has no swing field, and separately **no nominal
> channel separates the 1 accepted design from the 14 failures** — it has *less*
> pair margin than 12 of them. A swing-aware re-ranking of this pool is not
> available at zero cost. **Read §5h**, which pulls the lever that can actually
> be measured.

**And a cost caveat that is not physics (G123, row 4i).** The scan was estimated
at ~30 s and took 250.4 s. The gap is **not** the simulator: `library_candidates`
re-reads the whole 74 526-row pool on every call because `load_pool` has no
cache, which is **89–161 s** of the total. Every claim in entry 31 is in *decks*,
so no result moves; but "zero simulations" is not "zero cost", and the residual
1.4–2.5 s/deck against the sweep's 0.42 s/deck average stays **unexplained**.

---

## 5h. THE SWING LEVER WAS A FALSE LEAD — depth was the real one. Entry 32 RAN: **1 of 16 -> 6 of 16, 35.6 % fewer sims**

§5f named a lever and §5g recommended it: rank the library on **swing headroom**
as well as target match, for free, because "the pool already carries
`pair_margin_v` / `tail_margin_v`". **That premise was checked before anything was
built on it, and it is false.** Three independent reasons, each measured:

1. **The pool has no swing field.** `pair_margin_v` and `tail_margin_v` are DC
   operating-point headroom, `vds - vdsat`. What the screen actually rejects on is
   `vout_swing_v` — the **measured 1 dB compression point**, produced by a swept
   simulation (`sky130_runner.measured_swing_pp_v`) which deliberately refuses to
   fall back to a computed `4*I*RL`. They are different physical quantities and
   only the first is in the pool. "Swing-aware ranking at zero simulations" is not
   a thing this pool can support.
2. **No nominal channel separates the outcomes.** Joining all 16 scan rows back
   to their pool rows (on `u`, because `design_id` does not join across the
   boundary — **G124**), every one of `pair_margin_v`, `tail_margin_v`,
   `g_dc_db`, `peaking_db`, `nyq_boost_db`, `inoise_vrms`, `power_w`
   **overlaps** between the 1 accepted design and the 14 unscorable ones. The
   accepted design has **less** pair margin than 12 of the 14 (695 mV against up
   to 1190 mV) and **more** power than 13 of the 14. Pool rows are nominal
   (`tt/1.00/27C`); the failure is a **corner** phenomenon. A nominal predictor
   of a corner failure is not merely unfitted here, it is unfittable from this
   pool.
3. **n = 1 in the positive class.** A ranking rule fitted to one success cannot
   be validated. There is nothing to test it against.

### The lever that IS available, and why it needs no model

Two further zero-simulation diagnostics reframed the problem. The k=1 scan's real
defect is not that its criterion is blind to swing — it is that **it looked at
one candidate**:

* the library holds **2066–17478 in-tolerance candidates per request** (median
  4986, **115 261** across the 16), so the scan sampled roughly 1 in 5000;
* a request's **top 8 are genuinely different designs**, not near-duplicates:
  nominal power spans **3.3x–11.9x** (median 5.4x), `pair_margin_v` spans
  252–1174 mV, the designs sit up to **0.98 apart in the normalised [0,1] design
  box** (median max|du| 0.85), and all 8 are distinct rows in every request;
* **depth is nearly free in target match** — `dev` across ranks 1–8 stays within
  **0.003–0.080**, under 8 % of tolerance. The 8th candidate is not a worse
  answer to the request than the 1st.

So the question that needs no model: **how many candidates must it try before one
survives the corners?** `exp_hybrid.scan_topk` scores the top **k = 8** on the
same 4-corner screen and records the **rank of the first feasible one**. 512
decks, ~12 min, against 13 718 for the plain search. One run yields the whole
hit-rate-vs-k curve for k=1..8, so k=2 and k=4 are not separate experiments — and
its **k=1 column re-measures entry 31's 1-of-16 instead of assuming it**.

**It is informative in both directions, which is the point.** A high hit rate
means the library does hold corner-robust designs, the k=1 ranking was simply
blind to them, and the run yields ~128 labelled candidates — the first dataset a
ranking could actually be **fitted and validated** on (entry 31 had one positive).
A low one means the library does not hold corner-robust designs at these targets
at all, which kills the retrieval line cheaply and tells the SAC stage its
proposer must **generate** rather than retrieve. That is a result about the
deliverable, not a null.

### One incidental finding worth noticing

Some in-tolerance candidates have **strongly negative DC gain** — down to
**−14.9 dB** at 10 dB @ 1.387 GHz. Peaking is a *ratio*, so a heavily attenuating
stage can match both requested axes exactly. It is a plausible mechanism for the
swing failures, and it means **"in tolerance" is a weaker statement than it
sounds**.

### The bet, with its downside stated first

Pre-registered as `PREDICTIONS.md` entry 32 with five scored predictions, a cost
table, and a pre-committed three-branch decision rule. It discriminates two named
hypotheses: **H-independent** (the top 8 are 8 real tries at p≈1/16, so
`A ≈ 6.5` of 16) against **H-correlated** (`A ≈ 1–2`). Central estimate **A = 6**,
predicted range **3 ≤ A ≤ 10**.

**The downside is real and was written before the run.** A deployed k=8 proposer
pays `8 × 4 = 32` decks on every **miss**, not 4. So if depth does not help,
**k=8 is strictly worse than k=1** — a 2.4 % saving against k=1's 5.78 %. This is
a bet that can lose, which is what makes running it worth 12 minutes.

`exp_coverage.library_candidates` is **not modified** — `choose_start` seeds the
fallback search from it, so re-ranking it in place would change the search too and
break comparability with the 13 718-deck baseline every published coverage number
was measured against. `library_candidates_k` **wraps** it (pinned by source
inspection), and `scan_topk` writes a **third** artifact,
`hybrid_topk_scan.json`, because writing into `hybrid_proposal_scan.json` would
overwrite the result entry 31 quotes — G113's exact shape.

**Status: RAN, 315 s, exit 0. All 6 predictions HOLD and `A = 6` is the central
estimate exactly.** The ~90-minute full sweep remains unrun and needs the owner's
say-so in every branch. Two gotchas came out of the gate work: **G124** (`design_id` does
not join across artifact boundaries — bit-identical sizing, different ids, and the
failure mode is a silent *empty* join that reads as a real finding) and **G125** (a
sabotage that passes and a gate that cannot distinguish its own bug are the same
thing — one of these gates was worthless while looking thorough, because its test
data gave the same answer under the correct and the broken rule).

### THE RESULT: `accepted_at_k = [1, 4, 5, 5, 6, 6, 6, 6]`

**The 1-of-16 was not a property of the library. It was a property of looking
once.** Five candidates instead of one takes the hit rate to **6 of 16** — 6x,
for 260 decks against the search's 13 718. Nothing about the library, the
ranking, the tolerances, the screen or the specs changed; only the depth did.
128 candidates scored: **7 feasible, 5 infeasible, 116 unscorable**, and
**115 of the 116 (99.1 %) are still output-swing compression**. Entry 31's rank-1
proposals reproduced **bit-identically 16 of 16**, so entry 31's own numbers stand
— it is the *reading* of them that this withdraws.

| k | A | proposal decks | implied full-sweep | vs 13 718 |
|---|---|---|---|---|
| 1 | 1 | 64 | 12 925 | 5.8 % (entry 31) |
| 2 | 4 | 124 | 10 412 | 24.1 % |
| 3 | 5 | 172 | 9 603 | 30.0 % |
| **5** | **6** | **260** | **8 834** | **35.6 % — optimum** |
| 8 | 6 | 380 | 8 954 | 34.7 % |

**The pre-registration's one real miss was a cost claim, not a hypothesis:** it
costed the bet at k=8, but the curve is **flat from k=5**, so ranks 6-8 spend 120
decks and buy nothing. **`k = 5` dominates `k = 8`** — same `A`, 120 fewer decks.
This is exactly what "one run yields the whole curve" was for: the optimum was
**not** the value the run was configured at, and a k=1-then-k=8 pair of
experiments would have missed it. `DEFAULT_TOPK` is **left at 8** — changing a
constant on the run that measured it is tuning, and needs its own
pre-registration.

**The decision rule fires at `A >= 5`: retrieval is ALIVE.** The library does hold
corner-robust designs at these targets. Row **4k** unblocks — 128 labels with 7
positives, where entry 31 had 1. **And the bar for SAC is now 35.6 %, not zero**,
which is the entire reason the control was measured first. What it does **not**
say: `A = 6` is not "6 of 16 requests meet spec" — it is "6 of 16 got a usable
starting design for free". Mandated-corner coverage is still **7/16** (entry 30)
and this run does not move it.

## 5i. THE TRANSFER HELD. Entry 35 RAN: **SAC survived the SPICE fine-tune that erased PPO**

**2026-08-26 (session 28), `experiments/exp_sac_finetune.py`, 53.1 min,
artifact `sac_finetune_results.json`.**

G114 is this project's sharpest negative: 3 000 SPICE steps returned a PPO
policy trained for 200 000 analytic steps to its initialisation, taking
feasibility 1/16 -> 0/16 with it. G114's own instruction was *"change them one
at a time and measure"*. This experiment **held all three levers** -- the agent
**and its three optimisers** were kept (`lr_finetune = 3e-5` lowers the rate
instead of resetting it), the SPICE env was scored on **`V6A_SPECS`, the same
five rows the analytic env scores**, and `RevertOnInvalidEnv` made a bad edit
revert rather than terminate. **So exactly one thing changed between the legs:
the design equations were replaced by ngspice.**

    log_std_mean   analytic -1.7788  ->  after fine-tune -2.0902   sigma 0.169 -> 0.124
    alpha          analytic  0.0715  ->  after fine-tune  0.0747
    SPICE return   BEFORE  -24.101   ->  AFTER  -19.012   (+5.089, on 465 decks vs 470)
    episodes       8.00 of 8 BEFORE and AFTER
    PPO, contrast: log_std -3.022..-0.719 -> -0.097..+0.063  (erased to init)

**Entry 35 scored 3 of 5 and `_verdict()` printed the Q1-and-Q3 branch in code:
proceed to stage 3.** Q1 (survives), Q2 (`alpha` low) and Q3 (return does not
drop) hit -- Q3 in the opposite direction to its tolerance, the return *rose*.
Q4, the normalised critic test entry 34 demanded be registered *before* this
run, **missed at 2.393x against a 2.0x bar**. Q5 missed **fast**: 53.1 min
against 80-120, which produced **G126** -- leg A ran the same 50 000 steps as
entry 34 in **23.1 min against 40.5**, unexplained, so wall clocks in this
project are not comparable across runs and every cost claim stays in **decks**.

### The professor-ready version

**In plain language: the thing that killed the previous learning agent did not
kill this one.** Training an agent on fast approximate equations and then
letting it continue on the real circuit simulator used to wipe out everything
it had learned -- it came back as random as the day it started. With three
specific differences between the two training phases removed, the same move
made the new agent **more** decisive rather than less, and its scores on 16
unseen design requests **improved on 13 of them** (median +8.0; sign test
n = 16, two-sided **p = 0.021**).

**Two honest caveats, both in the artifact.** First, **the spread of outcomes
more than doubled** (return variance 210.7 -> 497.0): one request improved
enough to score positive for the first time, and two got sharply worse, one of
them hitting the floor. The typical case got better and the bad cases got
worse. Second, **the agent is still not good in absolute terms** -- mean score
-19.0, with only **1 of 16** requests scoring positive. It improved; it is not
solved.

### What this does NOT say

* **Which lever mattered.** All three were held together, on purpose: the
  question was whether the transfer is possible at all, not which of G114's
  three changes owns the failure. Attributing it needs three more runs.
* **Anything about compliance or coverage.** Both legs score **5 of 13 rows**
  on a model with a p99 error of a full octave. Mandated 45-corner coverage is
  untouched at **7 of 16**; the shipped design is still 11 of 11 at 45 of 45;
  the deck saving is still entry 32's **35.6 %**.
* **That D9's condition is met.** It is discharged **only** by `exp_hybrid`
  accept rate against **6 of 16**, and that is stage 3, unmeasured.

### The next decision, and why it is a measurement

Stage 3 must pre-register **which checkpoint proposes**. The fine-tuned policy
won on the *body* of the distribution and lost on the *tail*, and accept rate
is a tail-sensitive instrument -- a proposal that fails the corner screen buys
nothing regardless of how close it was. Both checkpoints exist and were opened
and verified to contain real weights (10 tensors each) before being relied on,
because `torch.save` in that file writes `state_dict: None` for an agent that
has none -- G113's shape exactly. **They are `.gitignore`d** (`*.pt`, 3.2 MB
each) and therefore exist only on this machine -- a fresh clone must re-run the
53-minute experiment before stage 3 can propose from either of them.

## 5j. STAGE 3 RAN: **SAC does not contribute as a proposer. 6 of 16 -> 1 of 16.**

**2026-08-26 (session 28), `experiments/exp_sac_propose.py`, 5 arms at k=5,
1 600 decks, 17.9 min, artifact `sac_propose_results.json`.**

This is the number mentor decision **D9** asked for — accept rate on the 16
coverage-grid requests, against the non-RL library proposer — and it is a
**negative, pre-registered as such** (entry 36, committed before the code
existed).

    arm                     A/16       accepted_at_k   decks  deployed  swing%
    library  (control)         6     [1, 4, 5, 5, 6]     320       260     96%
    sac_random_analytic        2     [1, 2, 2, 2, 2]     320       292     74%
    sac_random_finetuned       0     [0, 0, 0, 0, 0]     320       320     59%
    sac_seeded_analytic        1     [1, 1, 1, 1, 1]     320       304     92%
    sac_seeded_finetuned       1     [0, 0, 0, 0, 1]     320       320     85%

**Entry 36 scored 5 of 6.** The control reproduced entry 32 exactly — same six
accepted ranks on the same six requests — so every RL number is a measurement
of the policy, not of a moved instrument.

### The professor-ready version

**In plain language: we gave the trained agent the same job the simple
look-it-up method does, and it did that job much worse.** Handed the six
requests the library already answers, the agent broke five of them. Left to
design from scratch it answered two of sixteen, against the library's six.

**Why, and it is not mysterious.** 95 % of all rejections in this project are
*output swing* — the circuit distorts once the signal gets large. The agent was
never trained on output swing: its reward contains two frequency rows, two
peaking rows and the Nyquist boost, and nothing else. It optimised what it could
see and walked the designs straight into the thing it could not. **We wrote that
prediction down before running** (entry 36), precisely so the result could not
be explained away afterwards.

**One honest exception, n = 1.** The fine-tuned agent solved request 0, which
the library could not answer at any of its five ranks. One gain against six
losses; no claim is built on it, and it is recorded because leaving it out would
make the negative tidier than the data.

### The most useful thing in the run is the prediction that MISSED

Entry 36 predicted the choice of checkpoint would not matter. It does:

    random starts:   analytic-only  A = 2      fine-tuned  A = 0
    seeded starts:   analytic-only  A = 1      fine-tuned  A = 1

**The SPICE fine-tune that entry 35 measured as an improvement made the policy a
worse proposer.** Entry 35 recorded that its gain was in the *body* of the
distribution while the *tail* got heavier; entry 36 registered, in advance, that
accept rate is a tail-sensitive instrument. **The chain was written down before
the run and the data followed it.**

The mechanism is nameable. Counting why non-feasible candidates died:

    arm                   swing   pole-zero fit FAILED   other unscorable   infeasible
    sac_random_analytic      58            14                      1               5
    sac_random_finetuned     47            29                      1               3

**The fine-tuned policy produces roughly twice as many designs whose response
cannot even be fitted** — it is not being rejected by a spec, it is producing
circuits the measurement chain cannot describe.

### The cost claim goes the wrong way too

A proposer that accepts less early-exits less, so it pays for more of its own
candidate list: the library spent **260** deployed decks for 6 acceptances, the
RL arms **292-320** for 0-1. **More decks, fewer designs.** There is no
amortisation claim here in either direction.

### What this settles, and what it does not

* **D9's condition is not met by SAC as a proposer.** Measured on the
  deliverable's own metric it contributes negatively, 6 -> 1.
* **It does not say SAC failed to learn.** Entries 34 and 35 stand. What it says
  is that maximising a 5-row analytic reward does not produce designs that
  survive a 4-corner screen dominated by a 6th quantity the reward cannot see.
  **That is a statement about the reward, not about SAC.**
* **No coverage or compliance number moves.** Mandated 45-corner coverage stays
  **7 of 16**, the shipped design stays 11 of 11 rows at 45 of 45 corners, and
  the **35.6 %** deck saving stays the non-RL proposer's.

### The three options, and all three are the owner's call

1. **Retrain on a reward containing output swing.** It cannot come from the
   analytic model — it is a measured 1 dB compression point. Cost: SPICE-scored
   training (50 000 steps goes from ~23 min to ~17 h) or a fitted surrogate,
   which today has ~128 labelled points and no pool field to fit on.
2. **Move SAC inside the search as a refiner** and measure **decks-to-feasible**
   instead of accept rate. This run tested the policy in the hardest framing —
   one shot, no feedback from the screen.
3. **Ship retrieval + CMA-ES honestly**, with the RL arm reported as a measured
   negative with a named mechanism.

**None is started without the owner choosing it**, and none is a reason to touch
tolerances, the screen, `reward_v1.py`, `SEARCH_TAIL_W` or `SEARCH_ROW_CAP`
(G111, entry 30's pre-committed branch).

## 5k. THE SWING SURROGATE PASSES: **output swing is predictable to ~5 % with no SPICE**

**2026-08-26 (session 28), `experiments/exp_swing_surrogate.py`, 2 228 labelled
designs, no simulations, artifact `swing_surrogate_results.json`.**
Pre-registered as entry 37 before the file existed; **scored 4 of 4.**

    split                          model   n_te  med rel  p90 rel  med mV     rho
    A_random                       gbr      669     6.4%    27.3%    38.5   0.949
    B_transfer_to_policy_designs   gbr      245     4.7%    12.5%    19.5   0.993
    A_random                       ridge    669    20.4%    74.4%   130.5   0.832
    B_transfer_to_policy_designs   ridge    245    36.0%   100.0%   166.4   0.948

    Q4 separation: AUC 0.794, bootstrap 95 % CI [0.722, 0.854], on 18 feasible
                   vs 430 swing-failed

### Why this matters, in one line

Section 5j measured that SAC fails as a proposer because **the quantity doing
95 % of the rejecting is not in its reward and cannot be** -- output swing is a
large-signal compression point and the analytic model is a small-signal fit.
That left two ways to fix it: **~17 hours** of SPICE-scored training, or a
surrogate. **The surrogate works**, so it is now **minutes**.

### The professor-ready version

**From the design numbers alone, with no simulation, we can predict where the
circuit starts distorting to within about 5 % -- roughly 20 mV on a 500 mV
quantity.** The relationship turns out to be almost entirely *bias current x
load resistance* (permutation importance 1.77 against 0.05 for everything else),
which is what a textbook would say -- **but the mapping is nonlinear**, which is
why the textbook formula `4*I*R_L` overpredicts by **3.4x** and why a linear
model still sits at 36 % error. The tree learns the bend.

### The result was attacked before it was believed

Split B (transfer) scoring **better** than split A (random) is backwards, so the
obvious cheat was checked:

* nearest-neighbour distance test->train: SAC designs **0.235**, random-split
  designs **0.223** -- the policy's designs are **further** from training data;
* by arm family: designs edited from library seeds **4.7 %**, designs invented
  from random starts with no library ancestry **4.7 %** -- identical.

Split A is harder for a benign reason: 30 % less training data and a wider test
range (up to 2 147 mV vs 1 311 mV).

### Two caveats that travel with the number

1. **Q4 is a qualified hit.** The CI's lower bound (0.722) is **below** the 0.75
   bar, because only **18** designs in the whole project passed the screen. The
   direction is clear (median predicted limit 975 mV for passes vs 506 mV for
   swing failures); the number is not settled.
2. **The training data is CENSORED and the result does not relieve it.** A
   limit is recorded only where the design compressed, so the high-headroom
   region -- exactly where a swing-aware policy would be steered -- is absent by
   construction. If such a policy is ever trained, the first check is whether it
   parks in the high-predicted-swing region and whether SPICE agrees there.

### What it unlocks, and what it does not

* **Unlocks:** a swing-aware reward at minutes of training instead of ~17 h.
* **Does not:** say a retrained SAC would beat 6 of 16. Unmeasured; needs its
  own pre-registration; **section 5j's 1 of 16 stands**.
* **Does not:** produce any deliverable number. `is_surrogate: true` is stamped
  on the artifact and `link/calibration.py` goes on refusing to score a
  compressing stage. **The surrogate predicts; the measurement decides.**
* **The reward-set change is the OWNER's decision** (standing rule 6). Nothing
  has been retrained.

## 5l. THE SWING-AWARE REWARD: **the fix worked and it did not pay. 0-1 of 16.**

**2026-08-26 (session 28), `experiments/exp_sac_swing.py` + `rl/swing_env.py`,
50 000 analytic steps + 960 decks, 52.1 min, artifact `sac_swing_results.json`.**
Pre-registered as entry 38; authorised by the owner as row 4p. **Scored 4 of 6.**

    arm               A/16       accepted_at_k   decks   swing%   med measured swing
    library              6     [1, 4, 5, 5, 6]     320      96%        595 mV
    swing_random         0     [0, 0, 0, 0, 0]     320      28%       1154 mV
    swing_seeded         1     [0, 0, 0, 1, 1]     320      35%       1162 mV

### The professor-ready version

**We found what was blinding the agent, we fixed it, the fix demonstrably
worked, and the score did not move.**

Section 5j showed the agent was being judged on a quantity it had never been
shown -- output swing, which caused 95 % of all rejections. Section 5k showed
that quantity could be predicted with no simulation. This section put the
prediction into the agent's reward and retrained.

**The intervention did exactly what it was meant to.** The agent learned to
build designs with nearly **double the headroom** of the library's designs
(1 154 mV measured against 595 mV), and swing failures fell from 96 % to
**28 %**. Most striking: the library's candidates are so compressed that **SPICE
cannot score them at all 90 % of the time**, while the new agent's designs
simulate cleanly and get properly judged -- mean scorable corners rose from
**0.30 of 4 to 2.36-2.84 of 4**.

**And it produced no extra acceptances: 0 and 1 of 16, against the library's 6.**

### Where the rejections went, which is the real finding

    reason for rejection        library   swing_random   swing_seeded
    output swing compression       70          22             28
    unscorable, other               1          21              4
    INFEASIBLE on a spec            2          37             47
      of which S3_peaking_match     1          20             20
               S3_f_peak_match      1          13             19

**Fixing the blind spot exposed the next constraint.** Failures moved from "the
measurement is void" to "the response misses the requested peaking and peak
frequency at corners" -- rows the reward **already** scored. More bias current
and a bigger load buy headroom **and move the poles**: the agent paid for
headroom with shape accuracy, and the corner screen charges for shape accuracy.

**Entry 38 registered this as the leading counter-argument BEFORE the run.**

### What it settles

* **A single missing quantity was not the whole story.** The diagnosis in 5j was
  right about what rejects designs; correcting it did not move accept rate.
  **The corner screen rejects policy-generated designs for reasons that do not
  reduce to one quantity.**
* **D9's condition is still not met** -- 1 of 16 against 6 of 16 -- now with one
  more explanation ruled out rather than assumed.
* **The surrogate is vindicated as an instrument, not as a fix:** entry 37's
  4.7 % transfer error held in deployment (predicted ~0.9 V, measured ~1.15 V)
  on designs from a policy that did not exist when it was fitted.
* **`SWING_W` is NOT re-rolled** (G110, registered in advance). The binding
  constraint is no longer swing, so a second weight would be tuning the wrong
  knob.

### What it does not settle, and both are the owner's

1. Whether a reward scoring **headroom and shape together at corners** would do
   better. That is a bigger change than a penalty term -- the analytic model
   predicts a nominal response, not a corner spread.
2. Whether the policy is short of training. 50 000 steps was enough for the
   blind reward (entry 34 measured the plateau); nobody has measured it for this
   one.

## 5m. THE DFE IS NOT LOAD-BEARING: **the eye passes with it removed entirely**

**2026-08-26 (session 28), `link/dfe_ablation.py` + `experiments/exp_dfe_ablation.py`,
135 points, 0.8 min, artifact `dfe_ablation_results.json`.** Pre-registered as
entry 39 after the owner asked *"should we size the DFE as well?"*. **Scored 5 of 5.**

    policy        min eye_h    min eye_w    mandated 45    all 135
    ideal          382.4 mV     0.8594 UI      45/45       135/135
    none           358.5 mV     0.7344 UI      45/45       135/135
    misadapted     377.6 mV     0.8438 UI      45/45       135/135
    quantised      372.5 mV     0.8594 UI      45/45       135/135
    floors: eye_h > 100 mV, eye_w > 0.4 UI

### The answer to "should we size the DFE"

**No, and now for a measured reason rather than a scheduling one.**

The competition spec names the receiver as *"1-Stage CTLE + 1-Tap DFE"* and
measures the eye AFTER the DFE, which this project models as an ideal tap. So
the fair question is what that assumption is worth. It is worth **2.9 % of the
eye** (median; 9.8 % worst): the tap cancels a median **1.9 %** of the cursor on
this design, and deleting it entirely leaves **358.5 mV against a 100 mV floor
-- 3.6x -- at all 45 mandated corners, and 332.6 mV (3.3x) at all 135 points.**

**A 4-bit quantised tap and a 20 %-misadapted tap are also indistinguishable
from ideal** (372.5 and 377.6 mV against 382.4), so the eye numbers do not
depend on tap resolution or adaptation quality either.

**Sizing a summer, a slicer, a feedback DAC and a clock would consume weeks to
make rigorous a block holding up ~3 % of a 3.6x margin** -- and would put a
half-verified mixed-signal block into a submission whose CTLE story is already
complete.

### The sentence the report gets

> The CTLE meets both eye specifications at all 45 mandated PVT corners -- and
> at all 135 verification points -- **with the 1-tap DFE removed entirely.**

**What must still be said with it:** the receiver is specified as CTLE + 1-tap
DFE, this project designs the CTLE and models the DFE as an ideal tap, and the
eye width is a zero-height noiseless upper bound in every policy. Deleting a tap
in software is not a claim that a real link should have no DFE -- it is the
narrower and sufficient claim that **the compliance result does not rest on the
DFE being ideal.**

### Q1 caught a real defect, and that is why the rest is trustworthy

The first version read eye height **at the best sampling phase**; the bridge
reads it **at the cursor** (`argmax` of the pulse response) and takes only the
*width* from the phase sweep. The two disagreed by **7.0 mV on a 456 mV eye --
1.5 %**, comfortably inside what an eyeball would accept. The control failed,
the defect was found, the fix made the control **exact (0.000e+00 over 135
points)**. Q1 was registered at 0.9 as a formality and was the most valuable
prediction in the entry.

**The sabotage round then found the gate for that same defect was WORTHLESS**:
the synthetic pulses were symmetric, so their best phase *was* the cursor and
the swapped convention stayed green. A skewed pulse now separates them, with a
test asserting the test data itself can tell them apart. **G125, twice in one
session, on the two most load-bearing gates written.**

## 5n. THE HYBRID SWEEP: **coverage 7 -> 8 of 16 for 25 % fewer simulations**

**2026-08-26 (session 28), `exp_hybrid --run --topk-deliver 5`, 16 requests,
10 273 decks, 74.8 min, artifact `hybrid_results.json`.** Pre-registered as
entry 40. **Scored 5 of 5.**

    proposals accepted                 6 / 16    at ranks 2, 5, 2, 1, 2, 3
    MANDATED 45-corner PVT coverage    8 / 16    (entry 30's plain search: 7/16)
    135-point load grid                0 / 16    this project's extra axis
    decks   303 proposal + 9970 search = 10 273  against 13 718

### The headline, and it is the competition's own criterion

**The framework now answers 8 of 16 spec requests at full 45-corner PVT
compliance using 25 % fewer simulations than before** -- and per delivered
compliant design, **1 284 decks against 1 960: 34 % cheaper.**

    decks per request, in order
    868  870  8  874  20  1083  1085  10  1085  5  1085  10  1085  1085  15  1085

Six requests were answered for **5 to 20 simulations**; ten cost **868 to
1 085**. That split is the amortisation claim, in one artifact.

### The registered risk did not materialise, and that IS the result

Entry 40 expected coverage to FALL: an accepted proposal replaces whatever the
search would have found, the screen is 4 corners and compliance is 45, so a
cheap accept can cost a request. Q1 was registered at **0.55** for that reason.
**Coverage went up instead** -- 5 of the 6 short-circuited requests pass all 45
mandated corners, the sixth passes 44 of 45. **The 4-deck screen is a good
enough filter for 45-corner compliance on retrieved designs.** Not knowable in
advance; measured now.

### What must travel with the number

* **The 135-point column is 0 of 16.** That grid sweeps the load lighter and
  heavier than the design point and nothing survives all of it. It is **this
  project's stricter axis, not the competition's requirement** (45 mandated PVT
  corners). Quoting 8/16 without it would be quoting the easier of two numbers
  we hold.
* **8 of 16 = 50 %, 95 % CI [25 %, 75 %].** Sixteen requests is a 4x4 grid, not
  a sample. The **cost** figures are counts and carry no such uncertainty.
* **This is not an RL result.** Library lookup proposes; CMA-ES falls back.
  Entry 36's 1 of 16 for SAC stands.

## 5o. THE AMORTISATION INTERCEPT: **there is no small library. Break-even is 346 requests, not 2.**

**2026-09-01 (session 32), `experiments/exp_pool_size.py`, 87.2 s, ZERO
simulations, artifact `pool_size_results.json`.** Pre-registered as entry 51.
**Scored 3 of 5 -- and both misses were the convenient ones.**

Every deck saving this project publishes -- entry 32's **35.6 %**, entry 40's
**25 %**, **1 284 decks per compliant design against 1 960** -- is a
**marginal** cost. It prices the query and charges **nothing** for the 74 526-
design library the query reads, whose one-off cost `spec_pool.py` has always
stated: **~128 000 simulations**. No report or figure carried it. The sharpest
attack available on this project is *"that is a lookup table, not design
automation"*, and the answer to it is an amortisation curve with the library as
an intercept.

### The trap the entry was designed around

The obvious experiment -- subsample to `N`, re-rank, count corner-feasible
requests -- **cannot be run at zero simulations.** Only **128 of 74 526**
designs carry a corner label, so subsampling to `N = 1000` keeps a *specific*
labelled design with probability **1.3 %**. That curve would measure **label
survival** and would read as a real finding. So the entry measures **match
quality** (`dev`), which needs no labels, and names the weak link in its own
chain: match quality is **necessary, not sufficient**, so `N*` is a **lower
bound**.

### The result: a power law, no knee anywhere

           N        top-5 median dev      excess over full pool
          50            0.9292                   0.898
         300            0.4497                   0.424
       1 000            0.2639                   0.235
       3 000            0.1553                   0.121
      10 000            0.0857                   0.052
      30 000            0.0484                   0.016
      74 526            0.0259                   0.000

Deviation **halves for every ~3x** in library size, monotonically, on all 16
requests. The registered hypothesis was that in-tolerance candidates are
plentiful enough (§5h: 2 066-17 478 per request) that the top 5 saturate early.
**They do not -- plentiful is not close.**

    library charged at        0 decks  ->  break-even     0 requests  (by-product)
    library charged at   74 526 decks  ->  break-even   346 requests  (from scratch)

**The pre-committed branch fired as written** (Q1 misses -> report the question
OPEN, show bounding lines, do not estimate an intercept). **No band was retuned
after the run.**

### Q4 is the one that changes how §5h reads

`dev` -- the criterion the shipped proposer actually ranks on -- does **not**
separate the 6 solved requests from the 10 unsolved (**p = 0.8708**). Third and
strongest confirmation that nominal channels do not predict corner outcomes.

**Read with the power law it says something sharper than either half: a bigger
library buys MATCH QUALITY; match quality does not buy CORNER FEASIBILITY; and
coverage is made of the latter. The power law is NOT evidence that a larger
library would raise 8 of 16.**

### The professor-ready version

**Our speed numbers assume you already own the design library. If you have to
build one from scratch, you do not come out ahead until about 350 design
requests.** We looked for a cheaper library and there isn't one: shrinking it
degrades the match smoothly with no safe stopping point. And a bigger library
would not fix our coverage either -- we measured that how well a stored design
matches the request tells you nothing about whether it survives the corners.

**Named, not priced:** the pool was accumulated by random/LHS/CMA-ES benchmark
arms, so uniform subsampling models the library we **have**, not one somebody
sets out to **build**. A pool sampled deliberately across the two spec axes
would plausibly reach the same match quality far cheaper. **Unmeasured, costs
simulations, and it is the obvious attack on the 346.**

### Two report defects fixed in the same pass

1. **S7 area was quoted bare.** `bridge._area_mm2_of` sums **drawn passives
   only** -- no head enclosure, routing, guard ring or MOSFET area -- and its
   docstring said so while the report did not. Both tables now read **"lower
   bound"**. At 23x inside the limit nothing binds; the honest phrasing is
   *"at least 23x"*.
2. **The DFE ablation (entry 39) reached the report.** Writing it caught a
   defect: the first table took eye minima over **all 135 points** while every
   published figure is over the **mandated 45** -- one quantity, one name, two
   measurements (G32's shape). Both are now separate columns, reproducing
   entry 39 exactly (382.4 / 358.5 / 377.6 / 372.5 mV).

---

## 5p. THE LAST CORNER WAS A SIMULATOR BUG, NOT PHYSICS: **coverage 8 -> 9 of 16**

**2026-09-01 (session 33), `experiments/exp_unscorable.py` +
`experiments/exp_bypass_recover.py`, 450 decks, 239 s.** Pre-registered as
entry 54. **Scored 5 of 6**, and the miss is a defect in the question, not the
answer.

### Two failures had been merged in every artifact

`exp_coverage._rescore` emits two different verdicts and **discards the reason
string `FullPointResult` already carries**:

    ok = False                   -> "UNSCORABLE"        the POINT never ran
    ok = True, S8 rows missing   -> "EYE_UNMEASURABLE"  the LINK refused

So `n_unscorable = 46` was all anyone could read. Keeping the reason (90 decks)
splits it cleanly:

    request 5   8 blocked   ALL compression, ALL at VDD-5 %, 1.002-1.203x over
    request 3   1 blocked   ngspice: inoise_total = -nan(ind)   <- G54

Request 3's blocking corner **never reached the link layer at all**. It is
**G54**, documented 5 August: the mirror's reference-device noise is rejected to
machine zero by symmetry, ngspice's integrated-noise log-slope integration
evaluates `log(0)`, returns `-nan(ind)`, and **exits 0**.

### The control is the result; the coverage number is the consequence

Raising a circuit element until a number appears is indistinguishable from
buying the answer unless the invariance is measured **on this design**. All 45
mandated corners were re-run at 10 pF and 30 pF and compared with `==`:

    computed at both                            44
    differing in vn_in_vrms / g_dc_db / f_pk     0     <- 132 comparisons
    recovered 1 (tt/1.00/0C)      lost 0

Then, and only then: **request 3 goes 44/45 -> 45/45, and mandated coverage
goes 8 -> 9 of 16.** Request 5 does not move, exactly as registered -- its
failure is in the link layer, where a device-side bypass cannot reach.

### The professor-ready version

**One of our sixteen test requests was failing on a simulator bug, not a
circuit problem.** At one corner ngspice's noise integration divides by zero,
returns "not a number", and still reports success -- so our tool correctly
refused to certify the design. Adding a bias-node bypass capacitor, which every
current mirror has anyway, removes the numerical singularity. We checked on all
45 corners that this changes **no** computed value to any printed digit before
we accepted the corner it recovered. The circuit now meets every specification
at all 45 mandated PVT corners.

### What did NOT move, stated with it

* The **135-point load grid** is still **0 of 16**; request 3 went 44 -> 45 of
  135 points and its other two loads stay blocked.
* `pvt45_worst` is unchanged at **+14.2388** -- the recovered corner did not
  become the worst one, so no margin claim moves.
* **`C_BYPASS_F` stays 10 pF.** Every published number was measured against it;
  entry 54 patches one call site in a wrapper and restores it in a `finally`.
  Whether the delivered path should retry at 30 pF on a NaN is **the owner's
  call** (rule 7) and is row 4r below.
* **So 9 of 16 is measured WITH that wrapper, and `design.py` today ships
  WITHOUT it.** The shipped default still meets the NaN at that corner. The
  honest sentence is *"the framework reaches 9 of 16; wiring the retry into the
  delivered path is a one-line decision that has not been taken"* -- not
  *"design.py delivers 9 of 16"*. Row 4r is what closes that gap.
* 30 pF is a real capacitor whose area is **still not in any S7 estimate**.

### The habit this entry and the last one share

Entry 53's Q2 was a conditional whose antecedent could not be satisfied. Entry
54's Q4 asked whether a **0 C** noise value lies between its **27 C and 125 C**
neighbours -- and noise is cleanly banded by temperature (0 C, 27 C and 125 C
occupy three disjoint ranges over all 45 corners), so no outcome could have made
it true. Against the family the physics actually groups by -- the other 14
corners at 0 C -- the recovered value is **inside**. **A "not an outlier" check
must name the family the physics groups by, not the family the label groups by.**

---

## 5q. THE SCHEMATIC THE BRIEF ASKED FOR, AND IT IS PARSED RATHER THAN REDRAWN

**2026-09-01 (session 33), `report/schematic.py`, 28 tests, no new
simulations.** `CLAUDEwa.md` §2 quotes the brief: *"outputs the final schematic
and resulting specs"*. `design.py --out` wrote `design.cir`, which is a
schematic only to a reader who parses SPICE. It now also writes
**`design_schematic.png`**.

### The one design rule

The obvious implementation draws the `Sizing` object's numbers. **That is
G32** -- a model card that differs between the netlist a human reads and the
runner that produced the numbers -- and a drawing is the worst place for it,
because a picture is believed on sight and re-derived never. So the renderer
takes **the netlist string itself**, the same one written to `design.cir`,
parses its `.param` values, and draws those. There is no second computation to
disagree with.

It also **asserts the topology it draws**: the pair, both loads, `Rs` and `Cs`
between the two sources, both tail devices, the mirror reference and both load
capacitors, each with its connectivity. A deck that stops matching **raises**
rather than emitting a confident picture of a circuit that no longer exists.
Six deletion tests and two re-wiring tests hold that.

### Two defects the tests caught before anyone saw the output

1. **`eng()` turned `610 uA` into `61 uA`** -- an unconditional
   `.rstrip("0")` ate a significant digit. A factor of ten, on a label, in a
   picture nobody re-derives.
2. **The first end-to-end run drew a FAILED design under a panel headed
   "Delivered design".** `--peaking 9 --f-peak 1.9e9` comes back
   `headroom_only` (the input pair is out of saturation) and still has a
   netlist, so the renderer happily drew it. It now takes a `warning`, and that
   run produces a drawing titled **"NOT DELIVERED"** with the verdict in a
   banner and in the panel. This is the same class as the swing-compression
   trap: a number that exists is not a number that means what it looks like.

### What the drawing states, and what it refuses to

Every panel row is read off the run. **`--verify` not run reads "not verified
(--verify)"**, never a corner count; a measurement the run does not carry is
**omitted**, never defaulted. The **1-tap DFE is drawn as a labelled
behavioural block, outside the transistor canvas**, with entry 39's ablation
beside it -- it was never transistor-sized, so drawing it as silicon would be a
fabrication and omitting it would hide a mandated part of S2.

---

## 5r. THE RETRY IS IN THE SHIPPED TOOL: **9 of 16 with no wrapper**

**2026-09-01 (session 33), `device/sky130_runner.py`, 315 decks, 118 s.**
Pre-registered as entry 55. **Scored 4 of 4.**

### The gap this closes

Entry 54's `9 of 16` was the framework **with a test harness patched around
it**. `design.py` shipped without that patch and still met the NaN, so the
honest sentence was *"the framework reaches 9; the tool does not."* Now
`run_point` carries the retry itself:

    request 3   45 / 45 mandated corners, worst +14.238782573580623
    request 5   37 / 45                   (registered null, unmoved)
    retries fired over request 3's 45 corners   1   (tt/1.00/0C)
    corners still failing after the retry       0

**Q4 is what makes the rest mean something:** the wrapper and the built-in
retry agree on the worst margin to **every printed digit**, so entry 54's
invariance control -- 132 comparisons, zero differing -- carries over to the
shipped path instead of applying only to the harness it was measured in.

### How narrow it is, on purpose

* It fires on the **G54 signature only** (`= nan/inf`). The other eight silent
  failures `scan_for_silent_failures` catches mean the deck is wrong, and
  re-running one with a bigger capacitor is superstition.
* **One retry, never two.** The recursive call disables it.
* It does not fire when the tail is already at or above 30 pF -- a guaranteed
  identical second deck is cost with no chance of a different answer.
* **The branch is unreachable for any run that computed.** No measurement this
  project has published can change; what changes is that a corner which used to
  come back UNSCORABLE now comes back measured.
* `nan_retry_bypass_f=None` reproduces the pre-retry behaviour exactly, and
  **`C_BYPASS_F` is still 10 pF**.
* Every retried point is stamped `nan_retry_used`, whether the retry succeeded
  or not -- a corner still NaN at 30 pF is a different fact from one never
  retried.

### The consequence that is declared and NOT measured

**The retry can change what the SEARCH returns**, because a candidate that used
to die on a NaN now gets scored, and the search ranks on scores. Measuring that
costs a ~90-minute sweep and was not done. So **no `BASELINES.md` number may be
re-quoted as if it had been measured with the retry on**, and entries 30, 32,
40, 52 and 53 were all run without it. They are not invalidated -- the retry
only ever converts a failure into a measurement -- but they are not re-measured
either. Stated in advance so a later sweep returning different numbers is read
as *this change*, not as noise.

### The professor-ready version

**Our tool used to give up at one corner because the simulator returned "not a
number" and still reported success.** It now notices that specific failure,
adds the bias bypass capacitor every current mirror has anyway, and re-runs
that one simulation. We checked on all 45 corners that this changes no computed
value to any printed digit before we trusted the corner it recovers, and it
fires once in 45. The design now meets every specification at all 45 mandated
PVT corners **from the shipped command**, not from a test harness.

---

## 5s. THE RETRY MOVES THE SWEEP: **coverage 8 -> 9 of 16 on the delivered path**

**2026-09-01 (session 33), `exp_hybrid --run --topk-deliver 5` with the G54
retry live. ~10 300 decks, 67 min.** Pre-registered as entry 56 with the
exposure counted first at zero simulations. **Scored 6 of 6.**

### The effect size tracks the exposure, which is what makes it believable

Entry 56 counted, from `hybrid_run.jsonl` and **before the run**, that 29 of
2 082 design evaluations had been rejected on the G54 NaN, and that 24 of them
landed on four unsolved requests. The three requests that moved are the three
with the most, in order:

    request 13   10 G54 rows (8 single-point)   17/45 -> 45/45   GAINED
    request 12    8 G54 rows (5 single-point)    0/45 -> 41/45
    request 15    6 G54 rows (4 single-point)   37/45 -> 39/45

The two exposed requests that were **already solved** held at 45/45, and every
unexposed request reproduced **identically** -- same 45-corner count, same path.
**Q3 was the sharpest question** (registered at 0.55, because divergence is not
obviously local) and it held: exactly one request changed state, inside the
exposed set. **The retry is a local fix, not a global perturbation.**

### What it settles

* **`BASELINES.md` and entry 40 are NOT invalidated.** 14 of 16 identical. Row
  4t's debt is discharged: pre-retry numbers may be quoted with the retry named.
* **This 9 of 16 is NOT entries 54/55's 9 of 16**, and they may not be added.
  That one counts request 3 via a **rank-17 retrieved proposal**; this counts
  request 13 via the **search**, and here request 3 is still 11/45 because the
  delivered path reads to k=5 and never sees rank 17. **The delivered path,
  measured end to end, is 9 of 16.**
* **Request 12 went 0/45 -> 41/45 and is still unsolved.** The biggest single
  improvement in the run buys no coverage. That is the ordinary shape of this
  problem and it is why coverage moves so slowly.
* **The 135-point load grid is unchanged at 0 of 16.**

### The accounting gap Q4 exposed

`mean_sims_per_request` returned **642.0625, identical to entry 40 in every
digit**, because the retry is a recursive call inside `run_point` and the
caller's budget counter sees one call. **Retry decks are unbilled** -- ~30 in
~10 300 here. It changes no claim and it is now row 4u.

---

## 5t. THE RL LINE CLOSES ON A MECHANISM: **give the policy the control's spread and its direction is worth ZERO**

**2026-09-01 (session 33), `exp_refine_widened.py`, 58 requests, 12.9 min.**
Pre-registered as entry 57 and committed before the run. **Scored 5 of 5.**

    arm                       crossed    up  down   decks
    A  policy MEAN     1x8      5/58     30    2    30.2
    D  policy SAMPLED  1x8     10/58     31    3    29.8
    F  policy + B's SD 1x8     13/58     34    1    29.9
    B  uniform random  1x8     13/58     38    1    30.1

**13 against 13**, matched budget (-1.1 %), McNemar **p = 1.0** with 8 requests
solved only by F and 8 only by B.

### The mechanism, which is the whole point

The checkpoint's `log_std` gives sigma **0.0487 on `rs`** and **0.0530 on `cs`**
-- the two knobs that set the `Rs x Cs` peak -- against the control's
`1/sqrt(3) = 0.5774`. **11.85x and 10.90x narrower.** The shared selector is
best-of-visited, which pays for spread. So arm F gave the policy the control's
spread and kept its learned centre.

**The progression 5 -> 10 -> 13 -> 13 is entirely explained by spread, and once
spread is equalised the learned direction adds exactly zero.** The policy's
whole measurable contribution was how widely it sampled -- a property of its
`log_std`, not of anything it learned about the circuit.

### Why this negative is worth more than the earlier ones

Entry 47 said *"the refiner loses to noise"*, which invites *"then train it
longer"*. Entry 57 says **"we gave the policy the control's exploration and its
direction was worth nothing -- measured, n = 58, paired, identical start."**
That is a statement about what the policy learned, not about how long it
trained, and the obvious reply does not touch it.

### What it does NOT say

* **Not a claim against retrieval.** Entry 47 arm C -- the same decks spent
  reading the library deeper -- crossed **18 of 58**, more than every policy
  arm including F.
* **Not coverage, not compliance, not a corner claim.** Four screen points.
* **`SPREAD` MUST NOT NOW BE SWEPT.** It was derived as the control's own
  standard deviation and fixed before the run; a follow-up at 0.3 or 0.8 would
  be tuning and would retire this result rather than extend it.

### The professor-ready version

**We suspected our reinforcement-learning agent was losing to random search
only because it explored too timidly. So we gave it exactly the random
searcher's exploration and kept everything it had learned about which
direction to move. It scored identically to random -- 13 out of 58 either way.
The agent's only real contribution had been how widely it looked, not what it
had learned.**

---

## 5u. PHASE 1 -- THE PASSIVES INVERT IN CLOSED FORM, AND IT PROPOSES **0 of 16**

**2026-09-02 (session 33), `invert_response.py` + `exp_invert_screen.py`,
320 decks, 210 s.** Pre-registered as entry 58. **Scored 1 of 5.**

### What was built, and it is correct

`prescreen.predict_response` is a one-zero/two-pole model and it **inverts in
closed form**. With `fp2 = m*fz` the peaking becomes scale-free -- it depends
only on `(k, m)` -- so: pick `rs` -> `k`; solve `peaking(k,m)` for `m` by
monotone bisection; then `fz`, `cs` and `rl` are algebra.

Measured at **zero simulations**, and none of this is retracted:

* round trip against the forward model: **24 of 24**, within 0.024 dB and
  0.004 octaves (the model's own grid step is 0.0091 oct);
* a design rule the project did not have: **`peaking <= 20*log10(k)`**, so
  12 dB needs `k > 3.98` and hence a minimum `rs` at a given bias;
* **all 16 requests have in-box analytic solutions**, 132-813 of an 8 000-point
  grid, fewest exactly where the search fails.

### And it does not work as a proposer

    A = 0 of 16          (library baseline 6 of 16)

    80 rejections:  38 swing compression     47.5 %
                    18 S3_f_peak_match       22.5 %
                    18 S3_peaking_match      22.5 %   -> 52.5 % SHAPE
                     6 S3_peaking             7.5 %
                     0 S6_power               0.0 %

**The inversion solves for TT/1.00/27 C. The screen scores four corners at
+-5 % VDD and 0/125 C.** This project has already measured that `f_peak` moves
up to **0.94 octaves** across corners against a **0.3-octave** match tolerance,
so a nominal bullseye is a corner miss by construction. *"On-target by
construction" was construction at the wrong corner.*

The registered branch fires as written: **the fix is corner-aware targeting,
not a better ranker** -- invert against the worst-case `(gm, k)` over the four
screen corners rather than the typical one. That changes what `invert` is
aimed at, not how it works.

### Two things worth keeping from the miss

1. **Q6 was registered before the run and missed instructively.** Every top
   candidate did sit at `i_bias = 8 mA` = 14.4 mW as predicted, and power was
   the worst spec **zero times** -- the designs died on shape and swing before
   power could bind.
2. **A units defect was caught before it reached a claim.** The first
   feasibility map passed microns to `predict_gm`, which takes metres and takes
   `log(l)`: `gm` came back **2.5x** wrong, `gmbs` **7x**, and *the round trip
   still closed perfectly* because both halves used the same wrong `gm`.
   `_require_metres` now raises, and a test asserts that self-consistency could
   never have caught it.

**Any corner-aware successor must be measured against the same 6 of 16, on this
same screen, before it may be called an improvement.**

---

## 5v. PHASE 2 ON THE DELIVERED PATH: **re-ranking the library by predicted swing takes A from 6 to 8**

**2026-09-02 (session 33), entry 61, ZERO decks.** A counterfactual over
`hybrid_topk_scan_k40.json` -- 640 library candidates whose feasibility was
already measured -- re-ordered by `exp_swing_surrogate`'s predicted swing limit.
**Scored 4 of 4.**

    first-feasible rank, per request
      old (`dev`)   [-, -,  2, 17,  5, 17, 26,  2, -,  1, 19,  2, -, -,  3, -]
      new (swing)   [-, -,  4,  4, 11,  4,  1,  2, -,  5,  2,  1, -, -,  7, -]

      k= 5   old A= 6   new A= 8      <- today's delivered setting (AUTO_K)
      k= 8   old A= 6   new A= 9
      k=40   old A=10   new A=10      <- control, a re-order cannot change the set

`A = 6` is now reached at **k = 4** instead of 5. AUC of the predicted limit
against measured feasibility: **0.6128**; median predicted limit **1 104 mV on
feasible candidates against 973 mV on infeasible**.

### The registered weakness did not hold, and that is in the result's favour

Entry 61 declared prominently that this is an **in-sample** re-ranking and
therefore only a ceiling. **Measured afterwards: ZERO of the 55 scorable
candidates appear in the surrogate's 3 356 training rows.** The ranker is a
fixed model of a physical quantity, fitted on disjoint data, applied out of
sample -- it is not fitted to these labels at all.

### What is genuinely limited

* **AUC 0.6128 is weak separation.** The effect is real and the mechanism is
  right; the signal is modest. The k=3 column even moves the wrong way (5 -> 4),
  which is what a modest signal on `n = 16` looks like.
* **The candidate SET is still `dev`-selected** -- the surrogate re-orders the
  top 40 that `dev` chose. Selecting from the full in-tolerance pool
  (2 066-17 478 per request) by swing is a different, untested thing.
* **Screen acceptance, not coverage.** The newly accepted requests sit at ranks
  4, 5 and 7, and entry 53 measured the screen's filter quality **degrading with
  depth** (83 % -> 50 %).

### Before it is deployed

**Verify the newly accepted candidates at the 45 mandated corners.** Entry 53's
degradation is exactly the risk, and no coverage claim may be made from a
4-corner screen. That verification is row 4w and is not in entry 61.

**RETRACTED 2026-09-02 by entry 63 (row 4w).** Verified at the 45 mandated
corners, the re-ranking **loses a solved request**: request 10 is 45/45 by the
search and its swing-ranked proposal delivers **39/45**. Deploying it would take
coverage **9 -> 8**. Entry 61 measured **screen acceptance and only that**.
See section 5w.

---

## 5w. ROW 4w: **the control failed. The swing re-rank is screen-only and would LOSE a solved request.**

**2026-09-02 (session 33), entry 63, 540 decks, 194 s.** Pre-registered with the
upside bounded at +2 before the run. **Scored 1 of 4** (one question not
scorable).

    idx  swing-rank  45-corner   entry 56 (search)   verdict
      3      4         42/45          11/45          improved, NOT solved
      5      4         37/45          44/45          WORSE than the search
      6      1         45/45          45/45          control HOLDS
     10      2       **39/45**        45/45          ** CONTROL FAILS **

**Request 10 is the proof.** It is solved 45/45 by the search; the swing ranker
promotes a different design to rank 2, the 4-corner screen accepts it, and it
delivers **39 of 45**. Deploying the re-rank would take mandated coverage from
**9 of 16 to 8** -- it gains nothing and loses one. The registered rule fired as
written: **Q2 outranks the headline, and Q2 failed.**

### The mechanism, sharper than entry 53's version

Entry 53 found the screen's filter quality degrading with retrieval **depth**.
This is worse: **it degrades whenever the ranking is changed to something the
screen does not score.** The screen rates all four of these designs within
**0.34** of each other (+14.03 to +14.37) while their true 45-corner counts span
**37 to 45**.

### What Phase 2 on the delivered path actually established

* the swing surrogate **does** carry signal about screen feasibility (AUC 0.6128);
* re-ranking on it **does** raise 4-corner acceptance 6 -> 8 (+4 / -2);
* it **does not** raise 45-corner coverage and **would lower it by one**;
* so it must **not** be wired behind `AUTO_K`.

### The one encouraging number, in proportion

**Request 3 went 11/45 -> 42/45** on a ~20-deck proposal against a 1 085-deck
search. Still not solved, and one design is not a trend -- but it is the largest
single-request improvement any proposer in this project has produced, and it
names where to look next (row 4x).

---

## 5x. THE MID-WINDOW SOLVE: **coverage 9 -> 12 of 16, verified, with eight controls**

**2026-09-02 (session 33), entries 64 + 65.** 320 screening decks + ~1 485
verification decks. **Entry 64 scored 5 of 5, entry 65 hit both scorable
questions.**

### The diagnosis: both failures ranked on something MONOTONE in `I_d * RL`

`I_d * RL` is the single quantity **both** binding constraints act on:

    swing capability  ~ 2 * I_d*RL              wants it LARGE
    pair saturation     I_d*RL < VDD - vcm + c  wants it SMALL

Measured on the candidates each earlier run proposed:

    entry 58  ranked on current      median 2.278 V  -> DC died (tail in triode)
    entry 60  ranked on DC margin    median 0.160 V  -> SWING died (2.2-4.9x over)
    feasible window                       ~0.55-1.15 V -- NEITHER run entered it

**A monotone objective always lands at an extreme of the quantity it is
monotone in.** The defect was the *shape* of the criterion, not the proxy.

### The fix: max-min (Chebyshev), and two calibrated predictors

Maximise `min(pair_margin, tail_margin, swing_margin)` -- stationary in the
middle of the window instead of at its ends. Built on:

* `dc_margins`, fitted on 4 000 pool designs: tail corr **0.9835** / 29.6 mV,
  pair corr **0.9903** / 34.3 mV;
* `g_dc = gm*RL/k` with a -0.707 dB offset: corr **0.9880**, median 0.223 dB;
* required swing `= v_in * g_dc * 10^(nyq_boost/20)`, returning ~1.19 V against
  entry 53's measured ~1.1 V;
* capability from entry 37's swing surrogate.

### The result

    screen acceptance   A = 11 of 16   (entries 58 and 60 both scored 0; library 6)
    saturation rejections  0 of 47      swing rejections 100 % -> 12.8 %

    VERIFIED at 45 mandated corners, 11 designs:
      8 CONTROLS (already solved)   ALL 45/45 -- none lost
      3 MOVABLE                     ALL 45/45
        request 3   11/45 -> 45/45      request 5  44/45 -> 45/45
        request 8   35/45 -> 45/45

    MANDATED COVERAGE  9 -> 12 of 16

**Q1 -- all eight controls holding -- was registered at 0.4, below even, and
declared to outrank the headline**, because entry 63 had just lost one of two
controls doing exactly this. It held 8 of 8.

### What may NOT be said

* **Not that `design.py` delivers 12.** The analytic proposer is **not wired
  into `--method auto`**, which still reads the library. That is a code change
  needing its own measurement -- the same gap entries 54/55 had before row 4r.
* **Not a 135-point claim** (load grid untouched), and **not a deck saving**
  until the verification cost is amortised.

---

## 5y. ROW 4y: **`design.py` now delivers 13 of 16 at the mandated corners**

**2026-09-02 (session 33), entries 66 + 67.** The analytic proposer is wired
into `--method auto` as the first candidate source, library second.
**Entry 67 scored 4 of 4.**

    idx  source    rank  role      45 corners
      3  analytic    3   movable     45/45     <- was 11/45
      5  analytic    3   movable     45/45     <- was 44/45
      8  analytic    2   movable     45/45     <- was 35/45
     15  analytic    5   movable     45/45     <- was 39/45
     14  library     8   movable     44/45
     eight CONTROLS (1,2,4,6,7,9,10,11)        45/45, none lost

    COVERAGE 9 -> 13 OF 16, on the shipped path, verified end to end.

**12 of the 13 acceptances come from the analytic proposer**, at ranks 1-5, for
**8-20 decks each** against the search's ~1 085.

### Entry 66 found a defect in the deliverable on the way

`exp_swing_surrogate.load_surrogate` re-fits from `harvest()`, which globs
`*.jsonl` -- so **every experiment that writes a log changed the model, and
therefore which design the tool proposed.** Measured: 3 356 rows when entry 64
ran, 3 362 when entry 66 ran, and only **8 of 16** accepted ranks reproduced.
A judge running the tool twice with anything in between would have got different
circuits. **Fixed:** `frozen_surrogate()` fits once, pickles to
`swing_surrogate_frozen.pkl`, and the file is committed, so a clone reproduces
the run. It was invisible until the proposer was wired in, because every earlier
use fitted and used the model inside a single run.

### What may NOT be said

* **Not 135-point compliance.** The load grid is **0 of 16**; the best design
  reaches 63 of 135.
* **Not a deck saving** until the 45-corner verification each design needs is
  amortised.
* **The 3 unanswered requests** (idx 0, 12, 13) are the low-frequency,
  high-peaking corner -- row 4z.

---

## 5z. THE TUNING BANK: **the spec becomes satisfiable, 45 of 45 corners served**

**2026-09-02 (session 34), owner decision D10.** `exp_tuning_bank.py` was
written in session 22 and **never run**. It ran, unchanged, at its committed
defaults.

    base c507a3ba6f58b9a6   target 7.5 dB @ 1.768 GHz   V5_SPECS (12 rows)
    3 boost x 5 frequency = 15 settings, 690 SPICE runs, 4.4 min
    artifact: experiments/tuning_bank_results.json

                  C0       C1       C2       C3       C4       peaking
       R0      3.122    2.525    2.028    1.622    1.334 GHz   4.41 - 5.22 dB
       R1      2.981    2.400    1.923    1.535    1.261 GHz   6.02 - 6.78 dB
       R2      2.850    2.290    1.833    1.462    1.201 GHz   7.85 - 8.56 dB

    tuning range   1.201 - 3.122 GHz (1.379 oct)   S3 window covered 100 %
    PVT            45 of 45 mandated corners served by at least one setting
    codes used     R2C2 x20, R1C3 x12, R1C2 x11, R2C1 x2

**The two axes came out orthogonal**, as the design equations say they should:
`Cs` moves `f_peak` monotonically across the whole window and barely touches
boost; `Rs` moves boost monotonically and barely touches `f_peak`.

### Why this is the headline and not a refinement

The SAME base design, **fixed**, has an `f_peak` PVT spread of **0.99979
octaves** and therefore serves **0.0 %** of S3's window (`exp_tuning_bank.py`
docstring, from session 23's spread measurement). With the bank it serves
**100 %**. That is not a better search. It is **reading (B) of S3 -- the word
"tunable" -- being satisfiable where reading (A) is arithmetically not.**

### What may NOT be said

* **Not 3-12 dB.** The measured boost range is **4.41-8.56 dB**, 46 % of S3's
  own range. `RS_SPAN = 0.12` is the limiter. The frequency axis covers its
  whole spec range; the boost axis does not cover its.
* **Two corners have exactly ONE passing setting** -- `ff/0.95/125C` and
  `sf/0.95/125C`. Zero tuning margin there: the next lot of silicon walks off
  the end of the bank. Reported per the file's own rule that an aggregate
  must not hide which setting served which corner.
* **One request, one load.** 7.5 dB @ 1.768 GHz at the design load, 45 mandated
  corners. **Not** the 16-request grid and **not** the 135-point load sweep.
* **Only 4 of the 15 codes are ever used**, and never an extreme one. Good for
  margin; it also says the bank as spanned is oversized on frequency and
  undersized on boost.
* **The prediction on record before the run was that output-swing compression
  would limit compensation** (on the basis of `tunable_trade_results.json`'s
  `n_accepting_drive: 0`). **It did not: 45 of 45.** Recorded as a miss.

---


## 5aa. THE WIDE BANK: **8 of 16, and the knob is decoration on six of them**

**2026-09-02 (session 34), entries 70 + 71, row 4aa.** Both pre-registered and
committed before their runs. **Entry 70 scored 5 of 5, entry 71 scored 2 of 5.**

**Entry 70 — the knob's reach** (64 decks, 17.7 s, TT only, `--tt-only`).
Geometry derived from 5z's measured 14.04 dB/box slope and the spec tolerances,
not chosen: `RS_SPAN = 0.38`, 8x8 = **64 codes = 6 bits**, nearest-code error
0.76 dB against a 1.5 dB tolerance and 0.099 oct against 0.3 oct.

    peaking  1.78 - 13.05 dB    covers S3's mandated 3-12
    f_peak   1.109 - 3.387 GHz  1.611 oct, S3 window 100 % covered
    the code -> response map is MONOTONE and separable on every row and column

**Entry 71 — what it complies with** (2 880 decks, 16.0 min; 64 codes x 45
mandated corners at the design load, `V6_SPECS`, then all 16 requests re-scored
free because only three of the 13 rows depend on the request).

    REQUESTS SERVED AT ALL 45 MANDATED CORNERS: 8 of 16
    2 117 / 2 880 points scorable (73.5 %)

### The negative result, which is the point of the section

**Q3 was written to be able to falsify D10, and it did.** Six of the eight
served requests are met at all 45 mandated corners by a **single fixed code**:

    4.0 @ 1.627 -> code 21     6.0 @ 1.627 -> code 28     8.0 @ 1.921 -> 38/45 best
    4.0 @ 1.921 -> code 19     6.0 @ 1.921 -> code 27     8.0 @ 2.253 -> 37/45 best
    4.0 @ 2.253 -> code 19     6.0 @ 2.253 -> code 27

Only the two 8 dB requests genuinely need more than one code across PVT.

**This sharpens section 5z rather than contradicting it.** 5z measured the base
design *at its as-sized `(rs, cs)`* serving 0.0 % of S3's window. That was true,
and it meant the base was sized at a **poor point on the two tuned axes** — not
that PVT drift needs a knob to absorb it:

* **across REQUESTS the knob is load-bearing** — six distinct best-single codes
  across eight requests; no one code serves both 4 dB @ 1.627 and 8 dB @ 2.253;
* **across PVT at a fixed request it mostly is not.**

**What that does to the RL.** D10 framed adaptation as *infer the code from eye
measurements without knowing the corner*. That problem is only real where the
right code depends on the **hidden** state. It depends almost entirely on the
**request**, which the policy is handed — so a request→code lookup is
near-optimal, and a policy trained on this artifact would be learning a 16-row
table. **This is entry 36 and `POSITIONING.md` §1 arriving by a third road.**

### Where the bank actually fails, measured

Of the 54 unserved (request, corner) pairs:

    S3_f_peak_match  34     S3_peaking_match  16     S3_f_peak_band   4
    HD3 / eye / power / noise:  ZERO

Entry 71's Q2 predicted compression and **missed**. Compression is real — 763 of
2 880 points (26.5 %) are unscorable and every sampled reason is output swing
over the linear limit — but among codes that *can* be scored the bank fails
because it **cannot reach the requested response there**. With entry 70's Q3
(18 of 64 codes fall outside S3's 3-12 dB because a symmetric span overshoots
downward), the redesign is arithmetic: **move code budget from boost to
frequency resolution.**

### What may NOT be said

* **8 of 16 is not comparable with entry 69's 14 of 16.** Different evaluator
  (`evaluate_at_points`, not `verify_full`), and this scores `S4_hd3_nyq` at the
  operating point where entry 69 scores S4's literal 100 MHz row — so this set
  is **stricter**. They may not be added or traded.
* **One fixed part is not competitive with sixteen bespoke designs**, and no
  reading of these numbers makes it so. That was always the trade; it is now
  measured.
* **No policy has been trained.** Entry 71's pre-committed rule said Q1 < 10
  re-opens the architecture first. `rl/adapt_env.py` and
  `experiments/exp_adapt_controls.py` are committed **unrun**.

---


## 5ab. THE CHANNEL PROBE: **the stage saturates on SHORT channels, and gain control is the missing knob**

**2026-09-02 (session 34), entry 72.** Pre-registered and committed before the
run. **Q4 failed, Q5 hit, Q3 missed, and Q1/Q2 were NOT READ** under the rule
committed with them.

Entry 71 showed PVT is not the hidden variable adaptation needs. Entry 72 asked
whether the **channel** is — the thing a receiver genuinely does not know.

    2 880 decks x 7 channels (3.0 - 12.0 dB), 34.3 min
    artifacts: experiments/channel_probe_results.json, channel_probe_run.jsonl

    loss dB    3.0   4.5   6.0   7.5    9.0   10.5   12.0
    scorable     0    18   128   485   1179   1823   2117   (of 2 117)

### The premise was wrong, and precisely where

Entry 72 was registered on: *the family's loss at DC is exactly 0, so
`v_in_diff_pp_v` is identical at 3 dB and 12 dB, so compression is
channel-independent and only the eye moves.*

**The first clause is true** and a passing test asserts it. **The conclusion does
not follow.** `v_in_diff_pp_v` is the drive at DC; the link rejection is on the
CTLE's **output** swing, and a *shorter* channel delivers far more
high-frequency content for the stage to amplify.

    median output swing at 3 dB vs the measured linear limit, by boost row
    R0  1480.0 mVpp / 1035.5  = 1.43x      R4  1696.1 / 1110.5 = 1.53x
    R1  1518.0      / 1054.3  = 1.44x      R5  1738.9 / 1104.9 = 1.57x
    R2  1577.8      / 1082.8  = 1.46x      R6  1737.8 / 1023.5 = 1.70x
    R3  1638.0      / 1101.3  = 1.49x      R7  1548.0 /  832.9 = 1.86x

**Even the lowest-boost code over-drives by 1.43x.** The bank worsens it
(1.43x -> 1.86x) but did not cause it, and **no bank code fixes it**, because the
binding quantity is the stage's **total gain**, not its peaking.

> The delivered CTLE is sized for a 12 dB channel and **saturates on any channel
> shorter than about 9 dB**. The knob it is missing is not equalisation, it is
> **gain control**. A real PCIe receiver puts a VGA/AGC around the CTLE for
> exactly this reason; this design has none.

**This was invisible for the entire project** because every number in the
repository was measured at `FUNNEL_LOSS_DB = 12.0` — the channel family's worst
member and, for this stage, its **easiest** one.

### What may NOT be said

* **Q1 and Q2 are UNMEASURED, not refuted.** At five of the seven channels
  almost nothing is scorable, so framing (b)'s printed *"0 of 45 corners move"*
  is an artifact of having no scorable codes to move **between**. The rule
  committed before the run forbids reading them, and they are not read.
* **This is not a coverage retraction.** Every existing compliance number stands
  at the channel it was measured on. What is new is that the channel was never
  swept, and the axis is not benign.
* **No policy has been trained**, on this artifact or entry 71's.

---


## 5ac. THE AGC GATE: **the load is not a gain knob, and the missing block is INPUT attenuation**

**2026-09-02 (session 34), entry 73.** Pre-registered and committed before the
run; authorised as a **parallel** experiment, so the delivered path is untouched
and no committed number changes.

Entry 72 concluded the missing knob is gain. Before paying for a VGA -- a new
topology block that re-opens every number in this repository -- the cheap thing
was tried: `rl` is already an axis (50-800 ohm, base 254.63), and the design
equations say `RL` scales gain and output swing while **not** appearing in the
peaking expression. So gain control might have been a **third bank axis**.

    30 points, 0.3 min, TT only.  0 of 3 codes rescued at 3 dB.

    R0C3   rl 254.6 -> 73.1 ohm (0.29x)
           demand 1532.4 -> 472.0 mVpp     limit 1035.5 -> 323.0 mVpp
           ratio    1.48x ->   1.46x       <- never moves

### Why, exactly

Cutting `rl` by 71 % cut the demand by 69 %, as predicted. **It cut the
capability by 69 % too.** Both are the same gain:

    demand      = (signal arriving at the input pair)  x A_v
    capability  = (the pair's LINEAR INPUT RANGE)      x A_v

`RL` multiplies the numerator and denominator of the quantity that decides
compression, so the ratio is **invariant in `rl`** -- measured 1.48x -> 1.46x
across a 3.5x load sweep. The over-drive is set by

    (signal amplitude at the input pair) / (pair's linear input range)

and **no output-side scaling can change it.**

> **Entry 72's "the missing knob is gain control" was right in spirit and
> imprecise in a way that would have sent an implementer to the wrong node. The
> corrected statement: the missing block is INPUT ATTENUATION — a variable-gain
> stage AHEAD of the CTLE — not a trim on its load.** That is exactly where a
> receiver puts its VGA, and this is why.

### What else the sweep recorded

* **The bottom of the `rl` axis is not usable anyway.** `f_peak` runs
  2.436 -> 19.953 GHz as the load falls; 19.953 GHz is the G44 signature, i.e. a
  wideband attenuator rather than an equaliser.
* **R7C3 is unrealisable at TT at every `rl`** (`device_ok = False`, peaking
  `nan` at all ten steps).
* **Q3 HIT and is now a fact without a use.** Peaking drifted **1.25 dB** across
  the whole sweep, inside `TOL["S3_peaking_match"] = 1.5`, so `RL` genuinely is
  near-orthogonal to boost and a 3-axis bank *would* have been coherent. Not
  built, because the third axis does not buy the thing it was for.

### What this buys

Per the rule committed before the run, **no VGA is built** -- that is a topology
decision for the owner. What entry 73 buys is that the decision is now a
**specification rather than a search**: the ratio to close is **1.44-1.52x at
3 dB**, and it is constant in `rl`, so the new block's requirement is a single
number rather than an optimisation.

---


## 6. Next steps, in order

| # | Task | Cost | Status |
|---|---|---|---|
| 1 | Pre-register `PREDICTIONS.md` entry 24 | — | **DONE**, committed before the run |
| 2 | `experiments/adaptive_screen.py` — EDGE-4, spread probe, D2 self-check | — | **DONE**, 15 tests, 2 gates watched red |
| 3 | `rl/reward_v1.py` — `S3_peaking_match` + `V5_SPECS` (D6) | — | **DONE**, 12 tests, 3 gates watched red |
| 4 | `experiments/exp_coverage.py` — the 16-request coverage sweep | ~10 000 sims, ~1.5 h | **DONE.** Artifact `coverage_results_AFTER_seeding_fix.json`: 16 requests, 9 screen / **8 pvt45** / 0 full135, 13 718 sims, 5737.3 s (95.6 min) |
| **4b** | **Re-run the sweep with `rank_unclipped=True`** (§5d). Pre-registered as **entry 30**, committed ahead of the run | ~14 000 sims, ~1.6 h | **DONE 2026-08-22.** 13 718 sims, 96.6 min. **Entry 30 scored 2 of 5; coverage 8/16 -> 7/16 (§5e).** Mechanism confirmed, headline a miss |
| **4c** | **Reachability, not scoring** -- the branch entry 30 pre-committed to. Either the 2-D tuning bank (item 7) or raising `budget_design_evals` above 200. **Do NOT tune `SEARCH_TAIL_W`/`SEARCH_ROW_CAP`, `reward_v1.py`, the tolerances or `baselines.py`** to buy coverage | TBD | **owner's say-so required before starting** |
| **4d** | **Why is the eye unmeasurable?** `exp_unscorable.py` keeps the reason string `_rescore` discards. (Was: *"explain the unmeasurable eyes; decide whether the 45/45 cliff or the search is the binding constraint"*) | 90 decks, 28 s | **DONE 2026-09-01 (session 33).** **Two failures, not one:** request 5 is 8 compression corners **all at VDD-5 %**; request 3 is a single **G54 NaN**. Neither is "the search". See section 5p |
| **4e** | **SAC brief stage 0 -- `experiments/exp_hybrid.py`.** Propose a design, score it on the live 4-corner screen, deliver if feasible, else call `exp_coverage.solve_request` **unchanged**. Proposer = zero-simulation library lookup = the **control** for a future SAC policy. Measures the **amortisation curve** (decks per request): a **cost** claim, not a coverage claim | 0 sims to build | **DONE 2026-08-22 (session 26).** 28 tests, no SPICE; 4 new gates watched red; pre-registered as **entry 31** |
| **4f** | **Run the 64-deck proposals-only scan** (`--proposals`, ~30 s). Entry 31 predicts **0 or 1 of 16** accepted at 75 %, dominant rejection bucket **unscorable not infeasible** (G107) | 64 sims, ~30 s | **DONE 2026-08-22 (session 26b).** 64 decks, 250.4 s. **1 accepted / 1 infeasible / 14 unscorable.** Entry 31 scored **5 of 5**; all 14 unscorable name output-swing compression |
| **4g** | **The ~90-minute full hybrid sweep -- THE OWNER'S CALL.** Entry 31 pre-commits the rule: run it if **>= 3** proposals are accepted; **do not** run it if **<= 1**. The search is *budget-bound* (both prior sweeps cost **exactly 13 718 decks**), so at zero acceptances the hybrid costs **64 decks MORE** than the plain search and its coverage number is predicted unchanged at 7/16 +-1 | ~14 000 sims, ~1.6 h | **RULE SAYS DO NOT RUN** -- 4f returned `n_accepted = 1`, which is `<= 1`. Recommendation is to skip it; **still the owner's decision**, not taken unilaterally |
| **4h** | ~~**The lever 4f identified: make the proposer swing-aware.**~~ **WITHDRAWN 2026-08-22 — the premise was false.** The pool has no swing field (`pair_margin_v` / `tail_margin_v` are DC `vds - vdsat`; the screen rejects on a *measured* 1 dB compression point), **no** nominal channel separates the 1 accepted design from the 14 failures, and n=1 in the positive class makes any fitted rule unfalsifiable. See §5h and `PREDICTIONS.md` entry 32's correction | — | **withdrawn, superseded by 4j** |
| **4i** | **Cache `spec_pool.load_pool` (G123).** It is called once per `library_candidates` invocation with no cache, so the 74 526-row pool is re-parsed per request: **89-161 s of the scan's 250.4 s**. An `lru_cache` is the whole fix. Also **unexplained**: the residual 1.4-2.5 s/deck vs the coverage sweep's 0.42 s/deck average | ~0 sims | open, low priority -- affects **no** result (every claim is in decks, not seconds), only wall-clock estimates. **Deliberately not done in 26c**: `load_pool` returns a mutable object shared by every caller, so memoising it changes aliasing, not just speed |
| **4j** | **Measure how DEEP the library must be searched (`exp_hybrid.scan_topk`, entry 32).** Score the top **k=8** candidates per request on the same 4-corner screen, record the rank of the first feasible one. Replaces 4h: it **measures** instead of predicting, needs no model, and one run yields the whole hit-rate-vs-k curve for k=1..8 -- whose k=1 column re-measures entry 31's 1-of-16 | **512 decks, 315 s measured** (vs 13 718 for the plain search) | **DONE 2026-08-22. 6 of 6 predictions HOLD. `accepted_at_k=[1,4,5,5,6,6,6,6]`: A=6 of 16, and k=5 is the optimum at 35.6 % fewer sims. See §5h** |
| **4k** | **Fit a ranking on the labels 4j produces.** Entry 31 gave 16 labelled candidates with **1** positive, which is unfittable. A k=8 scan gives ~128 labelled (design, pass/fail-at-corners) pairs. Only worth starting if 4j returns `A >= 5` -- the pre-committed branch | 0 sims to fit, 64-512 to re-measure | **UNBLOCKED: 4j returned A=6 >= 5.** 128 labels, **7** positives. Must predict output-swing compression (99.1 % of failures), a label that exists **only** in `hybrid_topk_scan.json` and never in the pool -- so held-out validation, not a re-fit on the same rows |
| **4l** | **SAC stage 1 -- does the learner move at all?** `rl/sac.py` + `exp_sac_gate.py`, gated on the entropy coefficient, the same instrument that diagnosed PPO. Pre-registered as **entry 34** | 50 000 analytic steps, 0 SPICE, 40.5 min | **DONE 2026-08-26.** `alpha` **14x**, `log_std` -0.007 -> **-1.779**. **Scored 3 of 5**; both misses were the two least-confident predictions |
| **4m** | **SAC stage 2 -- does the policy SURVIVE the SPICE transfer that erased PPO (G114)?** `exp_sac_finetune.py`, all three G114 levers held, one variable changed. Pre-registered as **entry 35** | 50 000 analytic + 1 500 SPICE steps + 2x16 SPICE evals, **53.1 min, 935 decks** | **DONE 2026-08-26 (session 28). YES.** `log_std` -1.7788 -> **-2.0902**, return -24.101 -> **-19.012**. **Scored 3 of 5.** See section 5i |
| **4n** | **SAC stage 3 -- the number that discharges D9.** SAC as `exp_hybrid`'s proposer, scored on **accept rate against the non-RL baseline of 6 of 16** (entry 32), 5 arms x k=5 | **1 600 decks, 17.9 min measured** | **DONE 2026-08-26 (session 28). THE ANSWER IS NO: 6 of 16 -> 1 of 16.** Entry 36 scored **5 of 6**; the control reproduced entry 32 exactly. D9's condition is **NOT met by SAC as a proposer**. See section 5j |
| **4o** | **The swing surrogate (entry 37).** Fit `vout_swing_v` from the design vector on 2 228 labelled designs harvested from every sweep; validate on a TRANSFER split (train non-SAC, test the 245 designs the policies invented) | 0 sims, seconds | **DONE 2026-08-26. GO, 4 of 4: 4.7 % median error on transfer, rho 0.993.** A swing-aware reward is now minutes of training, not ~17 h. See section 5k |
| **4q** | **The two things entry 38 did NOT settle.** (a) a reward scoring headroom AND shape together AT CORNERS -- a bigger change than a penalty term, since the analytic model predicts a nominal response, not a corner spread; (b) whether 50 000 steps is enough for this reward (entry 34 measured the plateau for the blind one; nobody has for this one) | TBD | **OWNER'S DECISION -- NOT STARTED.** Neither is a reason to re-roll `SWING_W` (G110): the binding constraint is no longer swing |
| **4p** | **A swing-aware reward, and a retrained policy measured on accept rate.** Predicted-headroom shortfall penalty via a WRAPPER env (no surrogate number can reach the screen), retrain 50 000 steps, re-run the arms against the same 6-of-16 bar | 50 000 steps + 960 decks, 52.1 min measured | **DONE 2026-08-26. THE FIX WORKED AND IT DID NOT PAY: 0-1 of 16.** Entry 38 scored 4 of 6 -- headroom nearly doubled (1154 mV vs the library's 595), swing failures 96 % -> 28 %, scorable corners 0.30 -> 2.84 of 4, and accept rate did NOT move. Failures shifted to S3_peaking_match / S3_f_peak_match. See section 5l |
| **4q2** | **Clear the G54 singularity and re-verify (entry 54).** Invariance control first: 45 corners at 10 pF vs 30 pF, compared with `==` | 360 decks, 211 s | **DONE 2026-09-01. 5 of 6. 132 comparisons, ZERO differing; request 3 44/45 -> 45/45; MANDATED COVERAGE 8 -> 9 of 16.** See section 5p |
| **4r** | **The delivered path retries at 30 pF on a `-nan(ind)`.** Authorised by the owner 2026-09-01 and pre-registered as entry 55. Fires on the G54 signature only, once, never when the tail is already >= 30 pF; `nan_retry_bypass_f=None` reproduces the old behaviour; `C_BYPASS_F` stays 10 pF | 315 decks, 118 s | **DONE 2026-09-01. 4 of 4. Request 3 is 45/45 with NO wrapper — mandated coverage 9 of 16 on the DELIVERED path. See section 5r** |
| **4t** | **Re-run one sweep with the retry on.** Declared but unmeasured (entry 55) | ~10 300 decks, 67 min | **DONE 2026-09-01. 6 of 6. Coverage 8 -> 9 of 16 on the DELIVERED path; 14 of 16 requests reproduced IDENTICALLY. `BASELINES.md` is NOT invalidated — pre-retry numbers may be quoted with the retry named. See section 5s** |
| **4w** | **Verify entry 61's newly accepted candidates at 45 corners.** | 540 decks, 194 s | **DONE 2026-09-02. THE CONTROL FAILED.** Request 10 is 45/45 by the search and its re-ranked proposal gives **39/45**; deploying would take coverage 9 -> 8. Entry 61 is **screen-only and must NOT be deployed**. See section 5w |
| **4y** | **Wire the analytic proposer into `design.py --method auto`.** | 296 + 1 755 decks | **DONE 2026-09-02. 4 of 4. `design.py` delivers 13 of 16 at the mandated corners**, verified end to end with 8 controls, none lost. Entry 66 found and fixed a drift defect on the way (the ranker re-fitted itself every run). See section 5y |
| **4z** | **The 3 unanswered requests are all low-frequency, high-peaking** (idx 0, 12, 13 -- 4 dB @ 1.387 and 10 dB @ 1.387/1.627 GHz), which is where the analytic feasibility map was always thinnest (132 solutions of 8 000 at the worst). Whether the box admits a DC-valid, swing-feasible solution there at all is unmeasured | ~0 sims to start | open |
| **4x** | ~~A criterion that prices swing AND the rows the screen scores.~~ **SUPERSEDED by entry 64's max-min criterion**, which prices DC and swing jointly and took screen acceptance 0 -> 11 | Entry 63 showed a swing-only ranking picks designs the 4-corner screen cannot distinguish from good ones (it rates all four within 0.34 while their 45-corner counts span 37-45). Unmeasured; must be pre-registered | TBD | open |
| **4v** | **Phase 2: price DC headroom and output swing JOINTLY.** Entries 58 and 60 are 0 of 16 twice for OPPOSITE reasons -- ranking on current killed the DC point, ranking on DC margin killed the swing (2.23-4.90x over the limit). The two pull in opposite directions, and entry 37's measured swing surrogate (4.7 % error, zero SPICE) is the tool for a joint criterion. **100 % of entry 60's failures are in its domain.** Must be pre-registered on its own | ~320 decks | open, indicated |
| **4u** | **Retry decks are UNBILLED.** The retry is a recursive call inside `run_point`, so the caller's budget counter sees one call: `mean_sims_per_request` came back 642.0625, identical to entry 40 in every digit, despite ~30 extra decks. 0.3 % here and it changes no claim, but **every deck count in this repository excludes retry decks** | ~0 | open, stated |
| **4s** | **Request 5's eight corners are the next coverage point, and they are NOT this bug.** All eight are output-swing compression at **VDD-5 %**, only **1.002-1.203x** over the measured linear limit — the closest any blocked corner has been. Whether a slightly larger `rl` or `i_bias` clears them at fixed peaking is unmeasured | TBD | open |
| **4aa** | **The WIDE bank (entry 70).** Section 5z measured 4.41-8.56 dB against S3's mandated 3-12. Widen `RS_SPAN` and re-measure the tuning range and the drive-handling limit at TT only, before paying for 45 corners. Step sizes derived from the spec tolerances, not chosen: `S3_peaking_match` is 1.5 dB and `S3_f_peak_match` is 0.3 oct, so a code step must be no coarser than either | ~64-128 decks | pre-registered as entry 70 |
| **4ab** | **The adaptation environment + the two controls.** Cache (code, corner) -> `DeviceResult` once with SPICE; the 21-member channel family is then FREE because `evaluate_link` re-scores a cached device result in Python. Controls: exhaustive sweep (upper bound on compliance, `n_codes` trials) and a hand-written bisection on the eye metric (the matched control) | ~2 900 decks once, then 0 | blocked on 4aa |
| **4ac** | **The RL adaptation policy.** Discrete action over codes; observation is what a real RX can see (eye height/width from trials so far), NOT the corner label. Neither PPO nor SAC has a discrete head today -- both are Gaussian -- so this is new code. Scored on trials-to-lock at equal compliance against BOTH controls in 4ab | 0 new SPICE | blocked on 4ab |
| **5** | **Corner-aware RL vs random / CMA-ES / library lookup.** Pre-registered as entry 25 (with a disclosed rule-3 violation: written after launch, before any artifact existed) | ~2.5 h | **RUNNING** |
| **6** | **Re-run the coverage sweep on `V6_SPECS`** (§5b). Owner: *"polishing numbers is much needed for honesty."* **Publish both the old and the corrected coverage number** | ~2.5 h | **committed, do not drop** |
| 7 | 2-D tuning bank (`Cs` axis) + the reading-(B) criterion | ~1 100 sims, ~8 min | built, not run |
| 8 | Fair benchmark — **all six methods**: uniform, LHS, **grid**, CMA-ES, GP-BO, PPO, plus the hybrid. **Grid is not optional**: *"significantly lower time than sweeping all MOS, R, C, L parameter space"* is the slide's own success criterion, so the sweep is the baseline we claim to beat. Dropping GP-BO would be dropping the strongest fair rival | ~1 h | |
| 9 | Option B: deliberate output loading, to desensitise the load axis. Measure device output capacitance with `device/cap_probe.py` first rather than inferring it (§4b infers ~90 fF) | ~30 sims | |
| 10 | Report: compliance matrix on page 1; renumber figures; point the grounding checker at report prose | ~2 h | |
| 11 | Demo capture: plain-English request → schematic → specs → verification | ~1 h | |

### THE RL DIAGNOSIS (2026-08-21) — it is simulator cost, not the algorithm

**The policy is untrained, and the evidence is the parameter that tracks
learning rather than the score.** PPO's `log_std` starts at 0.0 and *shrinks*
as a policy grows confident. After 1200 steps it reads **−0.05 to +0.053** —
unmoved. Sigma ≈ 1.0 is also as large as the entire `tanh`-bounded action, so
what the policy chose was drowned out by its own sampling.

**1200 steps is ~1 % of one training run**, and the reason is arithmetic:

    one step = 4 SPICE decks = 1.26 s

      1 200 steps     0.4 h    <- what was run
    120 000 steps    42   h    <- roughly what PPO needs

**Second defect, measured:** `rl/env.py` **ends the episode on an unbuildable
design** (line ~425, `if not ev.valid: return ..., True, False, info`). At
evaluation the policy used **5, 13, 12 SPICE calls** against CMA-ES's 800 — it
was getting **1–3 of its 8 moves** and could never back out of a bad edit.

**Per simulation it was never losing.** Request 1: policy **−3.0 in 5 sims**,
CMA-ES **−2.0 in 800**.

#### The fix, built and tested, NOT yet run

`rl/analytic_env.py` — the same MDP off `prescreen.predict_response`:

| | SPICE | analytic |
|---|---|---|
| per step | 1.26 s | **0.00047 s** (measured) |
| 1 000 000 steps | 350 h | **7.9 min** |
| steps per episode | 1–3 | **8.00** (full horizon) |

Model accuracy, **measured** (`prescreen.accuracy()`), not quoted: f_peak
median error **4.93 %**, bias −0.023 oct; peaking MAE **0.284 dB**, bias
−0.009 dB; **p99 f_peak error 1.078 oct** — accurate and unbiased typically,
with a real tail. Right for pre-training, wrong for anything else.

**Three fences, because it invents 4 of 8 observation channels** (the equations
give no noise, power or saturation): it scores only `V6A_SPECS`, the 5 rows it
genuinely predicts; the invented channels are filled with their `OBS_SCALES`
centres so they normalise to **exactly 0.0** — no information rather than wrong
information; and every result is stamped `is_analytic`, with a source check
forbidding the module from importing the device layer at all.
**No number from that env is reportable.** 13 tests, three fences watched red.

**Plan:** pre-train ~1 M analytic steps (~8 min) → fine-tune on SPICE (~1 h) →
re-run the 16-request comparison (~3 h). The run in progress is the **"before"**
measurement and should be kept.

### Why the RL work is NOT hopeless, and the framing that follows

`BASELINES.md` measures PPO as indistinguishable from uniform random at every
budget. **That null was measured on a problem that was accidentally degenerate
in two ways, and one of them was fixed in this session:**

1. **The spec manifold was 1-D** because `target_peaking_db` was discarded, so
   "give me 4 dB" and "give me 11 dB" were the same question. On a 1-D manifold
   a lookup table is provably the optimal policy — RL had nothing to learn.
   **D6 fixed this.** The problem is now genuinely 2-D.
2. **The policy was never shown corners.** Every published RL run is P1,
   nominal only. `rl/corner_env.py` was built for exactly this and never run.

**The claim to test is NOT "RL beats CMA-ES on one request."** On a 7-D
continuous box a classical optimiser should win a single query, and claiming
otherwise would be a retraction waiting to happen. The claim is **amortised**:
the optimiser wins request #1; a trained policy wins request #50, answering in
milliseconds having already learned the space. That is what the slide's
*"lowest design time"* and *"fewer search spaces"* actually ask about.
**The library lookup is the honest competitor** — and it cannot answer corner
questions, because the pool is nominal-only by construction. That asymmetry is
the whole niche.

**Report the result either way.** A completed, well-explained negative beats a
fourth deferral.

### What is built and working (session 23)

| module | what it does | measured |
|---|---|---|
| `adaptive_screen.EDGE4` | 4 (corner, load) pairs, load-swept framing | reproduces the full-135 worst **exactly** on 3/3 designs; live re-check gave −0.015150 in **4 decks / 1.8 s** vs 135 decks / 50 s |
| `adaptive_screen.EDGE4_MANDATED` | the same 4 edges at the design load — **the search screen** (D8) | exact on 2/3, +0.146 on the third, all inside the feasible band |
| `adaptive_screen.probe_spread` | f_peak PVT excursion from **2 AC-only decks** | **exact to 5 dp** on both verified designs, 0.41 s vs ~50 s |
| `adaptive_screen.AdaptiveScreen` | the self-check; appends any corner that beats the screen | **already caught one miss**: +0.4807 at `tt/0.95/125C/14fF` |
| `reward_v1.V6_SPECS` | both axes get a band row AND a request row | asking 10 dB and delivering 6.65 dB is now INFEASIBLE (was identical to asking 6.65); a peak at 3.174 GHz now FAILS (was 45/45 PASS) |
| `exp_coverage` | the coverage sweep | **ran**: 10/16 (retracted to <=9), 16 094 sims, 149.7 min |
| `exp_corner_rl` | the RL experiment, deferred 4x | running |
| `report/figures_v2` | the four figures a judge reads first | compliance matrix rendered: 11/11 rows at 45/45 corners |

### Two things learned the hard way, worth not repeating

* **Rank seeds by worst-case `|f_oct − target|`, not by spread.** Spread
  ignores the request: a design whose peak travels 0.3 octaves but sits at
  5 GHz has a superb spread and serves nothing. The first smoke run started
  from exactly such a design.
* **The spread probe must NOT score inside the search loop.** It scores 3 of
  12 rows, so its reward is systematically higher than a fully-evaluated
  infeasible design's, and mixing them builds an objective that rewards *not
  being measured*. It seeds the search and reports; nothing else.
* **`EDGE4` was derived from designs where `S3_f_peak` binds.** A design whose
  binding row is `S6_power` or `saturation` has its worst corner elsewhere —
  which is exactly the miss the self-check caught. The screen is a good
  heuristic for one row, not a universal truth, and the self-check is what
  makes that safe.

---

## 7. The RL problem, stated plainly

The competition deliverable says *"a **Reinforcement Learning** based Python
framework"*. Our RL is a **measured null** — statistically indistinguishable
from uniform random search at every budget from 150 to 2400 simulations, while
CMA-ES is separably better at every one. The cause is understood: the spec
manifold is effectively **1-D** (`target_peaking_db` is accepted by
`reward_v1.margins` and deliberately ignored), and on a 1-D manifold a lookup
table is the optimal policy.

**Do not keep trying to make RL a better search.** The defensible reframing is
that RL's product is not a better search but an **instant designer**: a
spec-conditioned, corner-aware policy that emits a sizing for a *new* target in
milliseconds where CMA-ES needs ~400 simulations. A design-pool lookup cannot
compete there, because the pool is P1-only by construction and cannot answer
corner questions. That is task 7 above.

**Do not claim RL superiority unless the benchmark demonstrates it.**

---

## 8. Standing rules that bite (the short list)

Full list: `CONTINUE_HERE.md` §9 and `HANDOFF.md` §9.

1. Update `HANDOFF.md` in the same commit as any change. Update this file too.
2. Run the suite before and after; report both counts; never commit red.
3. Pre-register anything arguable in `PREDICTIONS.md` **before** the run.
   Record misses as misses. Nothing above an outcome heading is ever edited.
4. Never fabricate a number. A missing artifact raises; it never gets a
   placeholder.
5. ngspice's exit code is **not** a success signal — parse and assert (G26/G30).
6. `ngspice_con.exe`, not `ngspice.exe` (G20). Run netlists from
   `nebula/device/spice/` (G29). Instance W/L are plain microns (G31).
7. Do not modify without an explicit human decision: `common/params.py`,
   `rl/contract.py`, `rl/env.py`, `V1_SPECS`, the box, the tolerances, the
   pre-screen. **Wrap, do not replace.**
8. New spec sets are new tuples **by enumeration**, never by exclusion (G101)
   and never by addition without checking every inherited member (G106).
9. Do not run experiments alongside the test suite — one concurrent ngspice is
   4.8× slower (G70).
10. Windows: no non-ASCII in `print()`. Run pytest from the repo root.
11. Commit as `Jai Kaushik <jaikaushik-prog@users.noreply.github.com>` (G12).
    **The repo is PRIVATE and stays private** (G1).
