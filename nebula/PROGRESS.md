# PROGRESS.md — the lean brief

**Purpose:** the 10-minute version of where Nebula stands. `HANDOFF.md` remains
the heart of the project and is still updated with every change; this file is
the index into it — decisions, architecture, and what to do next, with nothing
that a reader can reconstruct from the code.

**Read `CONTINUE_HERE.md` §§4, 5 and `HANDOFF.md` §9 gotchas before touching
anything.** This file does not replace them.

**Updated 2026-08-21, session 23.** 25 days to the 15 Sept deadline.

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
| Test suite | **1667 passed**, 11 deselected, 4m50s (`python -m pytest tests nebula/tests -q -m "not slow"`) |
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

## 5b. OPEN DEBT — **`S3_f_peak`'s tolerance is a CONSTRAINT tolerance being used as a REQUEST tolerance**

**Found 2026-08-21 mid-coverage-run. Owner has approved the fix; it is
sequenced AFTER the RL experiment and MUST NOT be dropped.**

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

## 6. Next steps, in order

| # | Task | Cost | Status |
|---|---|---|---|
| 1 | Pre-register `PREDICTIONS.md` entry 24 | — | **DONE**, committed before the run |
| 2 | `experiments/adaptive_screen.py` — EDGE-4, spread probe, D2 self-check | — | **DONE**, 15 tests, 2 gates watched red |
| 3 | `rl/reward_v1.py` — `S3_peaking_match` + `V5_SPECS` (D6) | — | **DONE**, 12 tests, 3 gates watched red |
| 4 | `experiments/exp_coverage.py` — the 16-request coverage sweep | ~10 000 sims, ~1.5 h | **RUNNING** |
| **5** | **Corner-aware RL vs random / CMA-ES / library lookup.** `rl/corner_env.py` is built, tested, and **has never been run** — deferred four times. **Owner moved this ahead of item 6 on 2026-08-21**, because a surprising result here changes what the report is about | ~2 h | **NEXT** |
| **6** | **Tighten the frequency request (§5b) and re-run the sweep.** Owner: *"polishing numbers is much needed for honesty."* Report both the loose and the honest coverage number | ~1.5 h | **committed, do not drop** |
| 7 | 2-D tuning bank (`Cs` axis) + the reading-(B) criterion | ~1 100 sims, ~8 min | built, not run |
| 8 | Fair benchmark — **all six methods**: uniform, LHS, **grid**, CMA-ES, GP-BO, PPO, plus the hybrid. **Grid is not optional**: *"significantly lower time than sweeping all MOS, R, C, L parameter space"* is the slide's own success criterion, so the sweep is the baseline we claim to beat. Dropping GP-BO would be dropping the strongest fair rival | ~1 h | |
| 9 | Option B: deliberate output loading, to desensitise the load axis. Measure device output capacitance with `device/cap_probe.py` first rather than inferring it (§4b infers ~90 fF) | ~30 sims | |
| 10 | Report: compliance matrix on page 1; renumber figures; point the grounding checker at report prose | ~2 h | |
| 11 | Demo capture: plain-English request → schematic → specs → verification | ~1 h | |

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
| `reward_v1.V5_SPECS` | the request is honoured | asking 10 dB and delivering 6.65 dB is now INFEASIBLE; was identical to asking 6.65 |
| `exp_coverage` | the coverage sweep | running |

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
