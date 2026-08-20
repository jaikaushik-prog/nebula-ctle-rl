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
| D2 | **The screen must re-check itself**, ~5× per run, against the full 135 points; any corner that beats the screen's prediction is added mid-run | Removes the dependence on the screen being guessed correctly |
| D3 | **Global, spread-first search** — global CMA-ES restarts over the whole box, gated on f_peak PVT spread | Targets the low-spread family the local search cannot reach |
| D4 | **Ship the tuning bank live, and report BOTH readings of S3** | See §5 — this is the session's largest change |
| D5 | Maintain this file alongside `HANDOFF.md` | `HANDOFF.md` stays the source of truth; this is the entry point |

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

## 5. The S3 reading — the session's biggest finding

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

## 6. Next steps, in order

| # | Task | Cost | Status |
|---|---|---|---|
| 1 | Pre-register `PREDICTIONS.md` entry 24 (bands + falsifiers) **before** any run | — | **do first, rule 3** |
| 2 | `experiments/adaptive_screen.py` — EDGE-4, spread probe, D2 self-check + tests | — | |
| 3 | `rl/reward_v1.py` — append `S3_spread` tolerance row + `V5_SPECS` (**by enumeration**, G101/G106) | — | |
| 4 | `experiments/exp_hybrid_search.py` — global CMA-ES on the tiered evaluator | ~1 600 sims, ~11 min | |
| 5 | 2-D tuning bank (`Cs` axis) + the reading-(B) 135-point criterion | ~1 100 sims, ~8 min | |
| 6 | Fair benchmark: random / CMA-ES / PPO / hybrid, one evaluator, equal budgets | ~6 400 sims, ~42 min | |
| 7 | **Corner-aware RL** — `rl/corner_env.py` is built, tested, and has never been run. The one defensible RL niche (a design lookup is nominal-only by construction and cannot answer corners) | ~2 h | |
| 8 | Report: compliance matrix on page 1; renumber figures; point the grounding checker at report prose | — | |

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
