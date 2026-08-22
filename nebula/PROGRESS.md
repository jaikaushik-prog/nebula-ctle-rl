# PROGRESS.md — the lean brief

**Purpose:** the 10-minute version of where Nebula stands. `HANDOFF.md` remains
the heart of the project and is still updated with every change; this file is
the index into it — decisions, architecture, and what to do next, with nothing
that a reader can reconstruct from the code.

**Read `CONTINUE_HERE.md` §§4, 5 and `HANDOFF.md` §9 gotchas before touching
anything.** This file does not replace them.

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
| Test suite | **1861 passed**, 11 deselected, ~4 min (254 s), measured 2026-08-22 on system Python 3.13.14 (`python -m pytest tests nebula/tests -q -m "not slow"`). The **system** interpreter, not the conda env — that env has no `torch`, and `ngspice_con.exe` is found by absolute path anyway (G69) |
| Gates G0–G2 | passed |
| G3 (RL beats random + grid) | **fails one clause** — RL is indistinguishable from random at every budget |
| G4 (corner-robust design) | met on `V1_SPECS` (7 rows); **not** on the 11 competition rows |
| Eleven-row compliance | **no design meets all 11 rows at all 135 points.** Two designs miss on opposite sides of one row |
| Report | `nebula/report/Nebula_CTLE_Report.pdf`, rebuilt from artifacts |

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

## 6. Next steps, in order

| # | Task | Cost | Status |
|---|---|---|---|
| 1 | Pre-register `PREDICTIONS.md` entry 24 | — | **DONE**, committed before the run |
| 2 | `experiments/adaptive_screen.py` — EDGE-4, spread probe, D2 self-check | — | **DONE**, 15 tests, 2 gates watched red |
| 3 | `rl/reward_v1.py` — `S3_peaking_match` + `V5_SPECS` (D6) | — | **DONE**, 12 tests, 3 gates watched red |
| 4 | `experiments/exp_coverage.py` — the 16-request coverage sweep | ~10 000 sims, ~1.5 h | **DONE.** Artifact `coverage_results_AFTER_seeding_fix.json`: 16 requests, 9 screen / **8 pvt45** / 0 full135, 13 718 sims, 5737.3 s (95.6 min) |
| **4b** | **Re-run the sweep with `rank_unclipped=True`** (§5d). Pre-registered as **entry 30**, committed ahead of the run | ~14 000 sims, ~1.6 h | **DONE 2026-08-22.** 13 718 sims, 96.6 min. **Entry 30 scored 2 of 5; coverage 8/16 -> 7/16 (§5e).** Mechanism confirmed, headline a miss |
| **4c** | **Reachability, not scoring** -- the branch entry 30 pre-committed to. Either the 2-D tuning bank (item 7) or raising `budget_design_evals` above 200. **Do NOT tune `SEARCH_TAIL_W`/`SEARCH_ROW_CAP`, `reward_v1.py`, the tolerances or `baselines.py`** to buy coverage | TBD | **owner's say-so required before starting** |
| **4d** | **Explain the unmeasurable eyes.** `n_unscorable` rose **74 -> 133** over the 135-point grid, and both 45-corner regressions are lost eyes rather than spec violations (G120). Decide whether the 45/45 cliff or the search is the binding constraint | ~0 sims to start (artifacts exist) | open, not spun as a finding |
| **4e** | **SAC brief stage 0 -- `experiments/exp_hybrid.py`.** Propose a design, score it on the live 4-corner screen, deliver if feasible, else call `exp_coverage.solve_request` **unchanged**. Proposer = zero-simulation library lookup = the **control** for a future SAC policy. Measures the **amortisation curve** (decks per request): a **cost** claim, not a coverage claim | 0 sims to build | **DONE 2026-08-22 (session 26).** 28 tests, no SPICE; 4 new gates watched red; pre-registered as **entry 31** |
| **4f** | **Run the 64-deck proposals-only scan** (`--proposals`, ~30 s). Entry 31 predicts **0 or 1 of 16** accepted at 75 %, dominant rejection bucket **unscorable not infeasible** (G107) | 64 sims, ~30 s | **DONE 2026-08-22 (session 26b).** 64 decks, 250.4 s. **1 accepted / 1 infeasible / 14 unscorable.** Entry 31 scored **5 of 5**; all 14 unscorable name output-swing compression |
| **4g** | **The ~90-minute full hybrid sweep -- THE OWNER'S CALL.** Entry 31 pre-commits the rule: run it if **>= 3** proposals are accepted; **do not** run it if **<= 1**. The search is *budget-bound* (both prior sweeps cost **exactly 13 718 decks**), so at zero acceptances the hybrid costs **64 decks MORE** than the plain search and its coverage number is predicted unchanged at 7/16 +-1 | ~14 000 sims, ~1.6 h | **RULE SAYS DO NOT RUN** -- 4f returned `n_accepted = 1`, which is `<= 1`. Recommendation is to skip it; **still the owner's decision**, not taken unilaterally |
| **4h** | ~~**The lever 4f identified: make the proposer swing-aware.**~~ **WITHDRAWN 2026-08-22 — the premise was false.** The pool has no swing field (`pair_margin_v` / `tail_margin_v` are DC `vds - vdsat`; the screen rejects on a *measured* 1 dB compression point), **no** nominal channel separates the 1 accepted design from the 14 failures, and n=1 in the positive class makes any fitted rule unfalsifiable. See §5h and `PREDICTIONS.md` entry 32's correction | — | **withdrawn, superseded by 4j** |
| **4i** | **Cache `spec_pool.load_pool` (G123).** It is called once per `library_candidates` invocation with no cache, so the 74 526-row pool is re-parsed per request: **89-161 s of the scan's 250.4 s**. An `lru_cache` is the whole fix. Also **unexplained**: the residual 1.4-2.5 s/deck vs the coverage sweep's 0.42 s/deck average | ~0 sims | open, low priority -- affects **no** result (every claim is in decks, not seconds), only wall-clock estimates. **Deliberately not done in 26c**: `load_pool` returns a mutable object shared by every caller, so memoising it changes aliasing, not just speed |
| **4j** | **Measure how DEEP the library must be searched (`exp_hybrid.scan_topk`, entry 32).** Score the top **k=8** candidates per request on the same 4-corner screen, record the rank of the first feasible one. Replaces 4h: it **measures** instead of predicting, needs no model, and one run yields the whole hit-rate-vs-k curve for k=1..8 -- whose k=1 column re-measures entry 31's 1-of-16 | **512 decks, 315 s measured** (vs 13 718 for the plain search) | **DONE 2026-08-22. 6 of 6 predictions HOLD. `accepted_at_k=[1,4,5,5,6,6,6,6]`: A=6 of 16, and k=5 is the optimum at 35.6 % fewer sims. See §5h** |
| **4k** | **Fit a ranking on the labels 4j produces.** Entry 31 gave 16 labelled candidates with **1** positive, which is unfittable. A k=8 scan gives ~128 labelled (design, pass/fail-at-corners) pairs. Only worth starting if 4j returns `A >= 5` -- the pre-committed branch | 0 sims to fit, 64-512 to re-measure | **UNBLOCKED: 4j returned A=6 >= 5.** 128 labels, **7** positives. Must predict output-swing compression (99.1 % of failures), a label that exists **only** in `hybrid_topk_scan.json` and never in the pool -- so held-out validation, not a re-fit on the same rows |
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
