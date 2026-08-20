# CONTINUE_HERE.md — the brief for the next agent

**Rewritten 2026-08-20, at the end of session 22s.** Supersedes the
2026-08-19 version, which was written at the end of session 22i and is now
wrong in its headline: it says the eye is unverifiable and that corners are the
only remaining niche for RL. The first is no longer true. The second still is.

**26 days to the 15 Sept deadline. Demo 25 Sept at BITS Goa.**

This file is the *entry point*, not a substitute for `HANDOFF.md`. It tells you
where the project stands, what changed in the last four sessions, what is
decided, what is open, and exactly what to do next.

---

## 0. Read in this order

| # | File | Why | Time |
|---|---|---|---|
| 1 | **this file**, §§1–9 | the situation and the direction | 20 min |
| 2 | `CLAUDEwa.md` §§1–3, §7, §8 | the contract, the spec table, the gates, the standing rules | 20 min |
| 3 | `HANDOFF.md` §9 gotchas **G100–G107** | the eight traps found in the last four sessions | 25 min |
| 4 | `nebula/PREDICTIONS.md` entries **18–21** | how this project makes claims, and four recent scorings | 30 min |
| 5 | `nebula/CHANNEL_MODEL.md` §§6, 8 + the DFE table | **four measured results that are NOT in the report** — see §6.3 | 20 min |
| 6 | `nebula/BASELINES.md` §§13, 14 | the benchmark and the budget ladder | 20 min |

**Do not skim 3 and 4.** The gotchas are the highest-value-per-line thing in
the repo. `PREDICTIONS.md` is the discipline that makes the results worth
anything: **pre-register, commit, then run.** Recent entries include several
scored misses, one of which falsified an instruction given by the owner's own
reviewer — those are the asset, not an embarrassment.

---

## 1. The situation in 90 seconds

Two things changed the shape of the project since the last rewrite.

**The eye is no longer blocked.** For months, S8 could not be evaluated on the
delivered design at any corner: the stage is driven past its linear limit, so
the small-signal fit the eye rests on stops describing it. Session 22q measured
*why* — `linear input range at f = linear range at DC / |H(f)/H(0)|`, because
`Cs` shorts out the same `Rs` the linear range is made of, so **peaking and
drive handling are one knob read in opposite directions** (G103). Session 22r
then found designs in the same box whose eye computes at all 135 points. The
cause was never the circuit: **`V1_SPECS`, which every published search scores,
contains S3 and not S8, and the sets containing S8 had never been searched on.**
Session 22s asked for both at once and got **11 of 11 rows passing at 135
points, zero failures**, eye 377–539 mV against a 100 mV floor.

**The reward's real defect is the opposite of the one everyone assumes.** It is
a maximin, so exceeding a met spec buys nothing — `S5_noise` binds **0.0 %** of
the time and `S6_power` **0.6 %** across 33 214 feasible designs. What it does
instead is go **flat**: within 0.001 of the best score the population spans
**8.4× in tail current** (G102). The delivered operating point was drawn from a
plateau, not chosen. **The lever is an added term, not a removed one**, and
that has been measured but not yet exploited (§6.2 item 3).

RL is unchanged and still a null: **statistically indistinguishable from
uniform random search at every budget from 150 to 2400 simulations**, while
CMA-ES is separably better at every one. Session 22n closed 97 % of the gap by
fixing an objective/termination mismatch and it still did not win.

---

## 2. Gate status — honest

| Gate | Due | Criterion | Status |
|---|---|---|---|
| G0 | 2 Aug | toolchain runs four analyses | **passed** |
| G1 | 3 Aug | hand reference meets S3–S7 at TT | **substantially passed** (`device/spice/g1_handdesign.cir`, generic BSIM4 1.2 V card — **never re-measured on SKY130 and never in the benchmark table**) |
| G2 | 20 Aug | one full evaluation end to end | **PASSED** (`G2_RESULTS.md`) |
| G3 | 3 Sep | RL beats random **and** grid at TT | **FAILS one clause of two.** Grid clause MET (separable win, 22n). Random clause NOT met — indistinguishable, not a loss |
| G4 | 12 Sep | corner-robust design generated and verified | **MET** 2026-08-20, 23 days early. Found by uniform random, not by the policy |
| G5 | 15 Sep | submitted | — |

**Both competition deliverables exist:** `python -m nebula.design` (specs in,
schematic + specs out) and `python -m nebula.llm` (natural language wrapper,
with a grounding guard). The report exists:
`nebula/report/Nebula_CTLE_Report.pdf`, 12 figures, rebuilt from run artifacts
by two commands.

---

## 3. What sessions 22q–22s established

### 3.1 The linear-range mechanism (22q, G103)

Every swing limit in the repo was **output-referred**, so the S8 blockage read
*"output swing 903 mVpp exceeds the linear limit 333 mVpp"* — true, and
requiring the reader to divide by a gain they must look up.
`SwingLimits.linear_in_pp_v` now reads the same compression sample on the input
axis, in the same units as the transmitter's swing. On the delivered design at
135 points:

    linear input range at DC        504 /  520 /  560 mVpp
    linear input range at NYQUIST   153 /  172 /  219 mVpp
    link drive at the CTLE input              535 mVpp
    OVERDRIVE                      2.44 / 3.11 / 3.49 x

**At DC it is 1.03× over — essentially at its limit. All of the blockage is the
3.07× de-rate, and the de-rate is the peaking.**

### 3.2 The front, and the two half-designs (22r)

1 590 simulations across the box, filtered to designs actually meeting S3
(band **and** 1.25–2.5 GHz window **and** positive Nyquist boost — filtering on
peaking alone selects **wideband attenuators**, G104). The attainable linear
range at Nyquist hovers around **1.0× the drive** across the whole band.

That produced two half-designs — one meeting S3 at 135/135 with no computable
eye, one meeting S8 at 135/135 and failing S3 — and the observation that
**nothing had ever asked for both**.

### 3.3 The joint search (22s)

`V4_SPECS` = the eleven competition rows with S4 asked at the **operating
point** (2.5 GHz, 535 mVpp) rather than its stated 100 MHz / 200 mVpp.
`exp_joint_search.py`, local CMA-ES seeded at 22r's most linear S3-valid
design, 400 simulations.

| | delivered | joint winner |
|---|---|---|
| rows passing at 135 points | 9 of 11 | **11 of 11** |
| rows failing | 0 | **0** |
| eye measurable at | 0 of 135 | **98 of 135** |
| eye height / width | — | 377.1–539.4 mV / 0.844–0.875 UI |
| HD3 @ 2.5 GHz, 535 mVpp | −17.4 dBc **FAILS** | **−42.7 dBc** |
| peaking / power | 9.78 dB / 2.16 mW | 6.37 dB / 6.56 mW |

**The qualifier is not small: the eye is measurable at 98 of 135.** All 37 gaps
are at corners the 3-corner search screen has no member of, 27 of them at
VDD 0.95. That is the **fourth** independent measurement of that blind spot.

### 3.4 Tunability, which contradicted its own framing (22s)

Eight bank settings holding `Rs × Cs` constant on the **total** resistance so
the zero does not move (flat at 177.0 MHz to four figures), switch `Ron`
**measured** at 16.50 Ω rather than quoted. Result: `k` moves **2.5×** while
the linear input range at the signal band moves **1.25×, non-monotonically**.
**The tuning control does not trade drive for equalisation** — the `k`s cancel
at the signal band. What sets drive handling is the fixed part, chosen once.

### 3.5 The speed-up number the brief's success criterion asks for (22r)

**3 402 000 simulations, 92 hours** for a genuine full factorial against a
**measured** 41.12 s for `python -m nebula.design --method cmaes` — **8 086×**.
Levels are **derived**, not chosen: `1 + ceil(sensitivity / 0.0664386)`, the
`ac dec 50` spacing. Labelled an extrapolation and a lower bound throughout.

---

## 4. **READ THIS BEFORE TOUCHING THE MARGIN NUMBERS — a live defect**

An external review asked for the **minimum normalised margin** to be reported
next to every pass count. That is a good idea and **it cannot be done honestly
today.** Measured 2026-08-20 while checking the review:

* Both the delivered design and the joint winner have a minimum normalised
  margin of **exactly +0.0205 (2.1 % of tolerance)** on `S3_f_peak`, at
  135 points. **They are identical** — so the review's premise that the
  delivered design "sits at ~99 % of tolerance" is **false**, and its argument
  against swapping designs does not hold.
* **That 2.05 % is below the measurement's own resolution.** Both designs'
  extreme margins land *exactly* on the `ac dec 50` lattice (indices
  **105.000** and **112.000**). One lattice step is **13.3 %** of the
  `S3_f_peak` tolerance, so "2.05 % of tolerance" is **0.154 lattice steps**.
* **The cause is a disagreement inside one file.** `verify()` takes
  `ac_peak_interp=True` and scores the interpolated peak;
  `verify_full()` goes through `link/bridge.py:205`, which uses `pt.f_pk_hz` —
  the **quantised** peak, i.e. exactly the defect session 22e was spent
  removing from the benchmark (G74 / `PEAK_INTERP.md`). **The 135-point
  compliance matrix everything is about is scored on the coarse lattice.**

**So: fix `verify_full` to score the interpolated peak BEFORE reporting any
margin number.** This is item 1 of §6.1 and it is a prerequisite for four other
tasks. It is not yet written up as a gotcha because it is not yet fixed —
write it up when you fix it.

**The physical finding underneath it, which is worth its own paragraph in the
report:** at the worst corner both designs' `f_peak` reaches **1.2589 GHz**
against S3's **1.2500 GHz** floor. **PVT spread consumes 97.9 % of S3's
one-octave frequency window.** Every design lands at the edge because the
window is almost exactly the size of the corner spread. That is a property of
the process, not of any design, and it reframes "our margin is thin" as "the
specification is thin".

---

## 5. Decisions — made, and OPEN

### Made and recorded

| Decision | Where | Consequence |
|---|---|---|
| Do not build the hard-constraint reward flag | owner, 22r | It measures as a **no-op**: identical feasible set, 210 of 33 214 rewards move, best design unchanged. Recorded as a falsified external prediction, `PREDICTIONS.md` entry 18 |
| `i_bias` box stays 0.5–8 mA | owner, 22r | VDD is **1.8 V**, not 3.3; the ceiling is already S6's limit (8 mA × 1.8 V = 14.4 mW) |
| Ship the input-referred linear-range measurement | owner, 22r | Done; in the 135-point checklist at zero extra simulation cost |
| Order: report fixes → joint search → tunability → RL last | owner, 22s | Done through tunability |

### **OPEN — human only. Do not decide these.**

1. **Which design ships?** The delivered V1 design (9 rows, no eye) or the
   joint winner (11 rows, eye at 98 of 135)? The cover of the report currently
   **conflates the two** — it reports "11 of 11 rows" beside "135 of 135
   points", which are different designs. This must be resolved before the PDF
   goes out.
2. **Extend the search screen with a mixed (`sf`/`fs`) and a low-VDD (0.95)
   member?** Four independent measurements now support it: 8/135
   (`G4_RESULTS.md`), 23/135 and 45/135 (`design.py`), 37/135 (joint search).
   **Cost:** more corners per design changes the benchmark's per-design cost,
   so keep the *benchmark* screen and the *delivery* screen separable or you
   trigger a `BASELINES.md` §7f re-run of every published arm.
3. **The compression decision, open since session 16** — `HANDOFF.md` §8 lists
   three routes (reach below S3's 3 dB floor; declare the low-loss end of the
   channel family out of scope; re-derive the `rl` range downward) and none has
   been chosen through four sessions and one full report. **An unmade decision
   reads as a defect; a made one reads as engineering.**
4. **Does the RL contribution claim survive?** `PLAN.md` §8 lists the
   spec-conditioned policy as first to cut. Session 22j measured that a lookup
   over already-simulated designs serves 32 of 32 held-out targets and that
   **50 random designs serve 100 % of them**. See §6.2 item 5 for the one
   experiment that could still produce an affirmative result.
5. **Should `target_peaking_db` become live?** It is accepted by
   `reward_v1.margins` and **deliberately ignored**, so one design scores
   identically against targets of 3, 5, 7.5, 10 and 12 dB. **The spec manifold
   is effectively 1-D**, which is why a lookup table is the optimal policy.
   Making it live would make the problem genuinely 2-D — and would move every
   published reward number (a §7f re-run event).

---

## 6. What to do next

An external review of the shipped PDF against `HANDOFF.md` produced a task
list. **I verified its load-bearing claims against the repo on 2026-08-20.**
Two premises are wrong (§4 above, and "there is no human reference point" —
`g1_handdesign.cir` exists and G1 passed). The rest is accurate. The ordering
below is mine, after that verification.

### 6.1 Do first — cheap, and one is a correctness bug

1. **Fix `verify_full` to score the interpolated peak** (§4). Prerequisite for
   every margin number. Add a test that the two verification paths agree on
   `f_peak` for the same design, and watch it go red against today's code.
2. **Report numbering and cross-references.** Figures 6 and 7 each appear
   **twice**, and the sequence is out of document order
   (1, 2, 7, 3, 4, 5, 6, 6, 7, 8, 9, 10). "section 5a" does not exist. Three
   "section 9" cites now point at the amortisation section because session 22s
   added two sections and did not renumber. **Session 22s caused this.**
   Renumber from a single source of truth; add a test that numbers are unique
   and contiguous and that every internal cross-reference resolves.
3. **Point `llm/grounding.py`'s numeric-literal checker at report prose.**
   `build_pdf._facts()` generates the cover counters, but the body carries
   hand-typed literals — line 706 says *"Seventeen entries"* and line 710
   *"a failure catalogue of 101 entries"* against actual values of **21** and
   **107**. Both understate us, which makes it worse: it shows the "no number
   is typed by hand" claim does not cover the body. A miss must **fail the
   build**, not repair the text. Add a red-gate test that injects a wrong
   literal. This is also demoable — the grounding checker turned on its own
   report.
4. **Fix the cover conflation** (§5 OPEN item 1) once the owner says which
   design ships, and put the eye-measurability qualifier **on the cover**.

### 6.2 High value

5. **Corner-aware RL at scale — deferred three times, now first.**
   `rl/corner_env.py` is built and tested (10 tests, ngspice smoke passed) and
   has never been run. Session 22j identified the asymmetry that makes this the
   only defensible niche left: *a lookup provably cannot answer corners,
   because the pool is P1-only by construction.* Three arms on **worst-corner
   reward at held-out spec targets**: corner-conditioned PPO, library lookup
   (blind to corners by construction), fresh CMA-ES per spec.
   **Pre-register bands, falsifiers, and an explicit statement of what result
   would make us drop the RL contribution claim entirely.** Report either way —
   a completed negative beats a deferred one.
   **Also decide and record:** `CLAUDEwa.md` §7 says *reward* on the worst
   corner, not *observe* it. If the policy is to generalise across corners it
   may need corner context in the observation. `which_corner_binds()` is the
   first evidence.
6. **Write up the four measured results that never reached the report.** This
   is the best value-per-hour in the project — all four are already measured
   and sitting in `CHANNEL_MODEL.md`:
   * **DFE sufficiency.** Across 21 channel members a 1-tap DFE is sufficient;
     a second tap buys **14.7 %**; a twenty-tap DFE still leaves 31 %, because
     **31.2 % of the residual sits beyond 20 UI** — the √f algebraic tail,
     exactly what decision feedback is worst at. **This derives the mandated
     S2 topology rather than assuming it**, and it is the most
     analog-engineer-legible result in the repo. Today the DFE appears once, in
     a box in Figure 1, which is what invites *"did you actually do the DFE?"*
   * **The burden mismatch.** The mandated −3.5 dB TX de-emphasis is worth
     exactly 3.5 dB of the CTLE's job, so the required burden across the family
     spans **−0.5 … +8.5 dB**. **The top 3.5 dB of S3's range is never called
     for.** The delivered design sits at 9.78 dB — *outside the maximum burden
     the link ever needs*. It compresses because it is over-equalising a
     channel that needs less. Section 11 reports the failure without the cause.
   * **The channel construction.** `IL_dB(f) = A√f + B·f`, so **loss at DC is
     exactly 0 by construction** — which is what puts near-full TX swing at the
     CTLE input at low frequency, which sets the 535 mVpp drive, which fails S4
     and blocks S8. The construction and the failure are causally linked and
     the report presents only the failure. Add an **eye and HD3 vs channel
     loss** sweep.
   * **State plainly, currently buried:** S8's 100 mV vertical is met with the
     CTLE *attenuating* by 13–15 dB. **The eye-height spec was never binding.**
7. **Rescope the RL section to what was measured.** The report attributes the
   null to G100 (terminate-on-success vs a metric rewarding overshoot) — true
   and incomplete. The deeper cause is §5 OPEN item 5: the spec manifold is
   **1-D**, and on a 1-D manifold a lookup table *is* the optimal policy, which
   is exactly what the amortisation section measured. Write the claim as
   *"RL confers no advantage over random search on a 1-D spec manifold at
   d = 7, on this objective, at the budgets tested — and here is where the
   crossover would have to be"*, **not** the unscoped implication that RL does
   not work for analog sizing, which we cannot support and which reads as the
   project failing its own title.
8. **Harvest the maximin plateau — zero simulations.** Re-score the **74 526
   designs already on disk** through `spec_pool` with a lexicographic
   tiebreak: maximise `min(margin/tol)`, then minimise tail current among
   designs within ε of the maximum. Report the power reduction at unchanged
   compliance. Pre-register the expected reduction. This **executes** G102's
   "the fix is an added term" claim rather than describing it.
9. **Disclose or re-fit the pre-screen.** At benchmark conditions its
   false-rejection rate is **3.88 %** — ten times its 1 % design budget — and
   `f_peak` MdAPE is **15.85 %**. Six of twelve benchmark arms are `+screen`,
   including `cmaes+screen`, the arm behind the 8 086× headline, and the report
   says nothing. Prefer a re-fit: 457 valid rows exist in
   `baselines_pilot.jsonl`, `prescreen.accuracy_from_log()` is the measurement
   to beat, and the mechanism the numbers point at is the `I_D = i_bias/2`
   assumption, which is 4–8 % optimistic against the real mirror (session 13);
   `solve_bias` already takes `mirror_efficiency`. Pre-register the expected
   improvement. If the re-fit does not land, **put the caveat in the benchmark
   section and mark every screened arm.**

### 6.3 Worth doing, lower priority

10. **The hand-designed baseline as a benchmark row.** Not "we had no human
    baseline" — G1 passed and `g1_handdesign.cir` exists. What is missing is a
    **SKY130 re-measurement** of it and a row in the benchmark table with
    designer-hours attached. Natural home for the gm/I_D work
    (`GMID_MAP.md`), which is built, tested and unwired; note honestly that its
    stated mechanism was **falsified** (38.07 % device vs 37.74 % design
    coordinates) and its real benefit was **1.16×** on simulations per valid
    design. That honesty is an asset here.
11. **Report restructure**, leading with an **executive summary + hard
    compliance matrix** (spec / requirement / measured / PVT points passing /
    minimum normalised margin) on page one. Two framing rules: **lead with the
    measured number, not the extrapolated one** — *"spec in, PVT-verified
    transistor-level schematic out, in 41 seconds"* is unimpeachable while
    8 086× is an extrapolation we ourselves label as such, so it belongs in
    the benchmark section rather than the cover; and **every claim currently
    phrased as an apology gets a decision or a cause attached** — rigour that
    only ever points inward reads as a project that beat itself.
    **Sequence this after item 3**, so the grounding checker catches stale
    numbers introduced during the move.
12. **Demo capture:** `nebula.llm` → schematic → specs → verification.

---

## 7. Commands

```bash
conda activate nebula          # ngspice 41; use ngspice_con.exe, NOT ngspice.exe (G20)
                               # the TEST SUITE runs on the SYSTEM python (conda env has no torch)

# tests — before and after ANY change, from the repo root. 1653 tests, ~4 min
python -m pytest tests nebula/tests -q -m "not slow"

# the deliverables
python -m nebula.design --peaking 9 --f-peak 1.9e9 --robust --verify --out out/
python -m nebula.llm "I need about 9 dB of peaking with the peak near 1.9 GHz"

# the report: figures then PDF, both from run artifacts
python -m nebula.report.figures
python -m nebula.report.build_pdf

# session 22q-22s experiments
python -m nebula.experiments.exp_linear_pareto --run      # 1590 sims, ~9 min
python -m nebula.experiments.exp_hd3_amplitude --run      # 31 sims
python -m nebula.experiments.exp_sweep_cost --run         # ~90 sims + 2 timed design runs
python -m nebula.experiments.exp_joint_search --run       # 400 sims, ~15 min
python -m nebula.experiments.exp_tunable_trade --run --base joint   # ~20 sims

# the benchmark
python -m nebula.experiments.baselines --sweep --interp   # 25 500 sims, ~42 min
python -m nebula.experiments.baselines --analyse <log.jsonl>
```

**Measured throughput: 0.0977 s/simulation at 8 workers**, 0.176 s serial.
A full-fidelity 11-row evaluation at one corner is **0.557 s**.

---

## 8. Traps that still bite

**The standing ones:** G20 (`ngspice_con`, not `ngspice`), G26/G30 (ngspice
reports failures as warnings and exits 0 — parse and assert), G29 (`.spiceinit`
read at parse time from the cwd), G31 (instance W/L are plain numbers in
**microns**), G36 (use the trimmed library), G44 (a peak at the sweep edge is
fictitious), G70 (**one concurrent ngspice = 4.8× slower** — do not run
experiments alongside the test suite; session 22r got a spurious
`test_pdk_trim` failure exactly this way), G71 (the first configuration pays
the cold cache).

**The eight from the last four sessions — all in `HANDOFF.md` §9:**

* **G100** — an episode that terminates on the condition your metric rewards
  exceeding is two objectives, not one.
* **G101** — a spec set defined by **exclusion** grows silently.
* **G102** — a **maximin** gives no credit for exceeding a spec, so "the
  optimiser bought margin" cannot be true of it. **Before removing a term from
  an objective, measure how often it BINDS.** A term binding 0 % of the time is
  already inert.
* **G103** — the peaking spec and the linear input range are **one knob**, and
  every swing limit was reported at the wrong end of the stage.
* **G104** — a constraint set that drops one clause selects a **different
  circuit family**. Filtering on peaking alone admitted a 19.95 GHz wideband
  attenuator that looked 3× more linear, and CMA-ES optimised into the same
  hole.
* **G105** — a finite difference on a **quantised** signal reports the quantum.
  Four of seven axes returned exactly one lattice step with **zero spread**;
  worth **1 296×** on the headline. **The tell is the zero spread.**
* **G106** — `A + (new,)` is a claim that every member of `A` is still
  measurable by whatever will score the result.
* **G107** — **"cannot be scored" is not "fails."** Collapsing them either
  kills a search or fakes a pass. Grade the invalid band by evaluability;
  **never loosen the gate.**

**Three process mistakes worth not repeating:**

* A scripted splice into `report/figures.py` matched the wrong anchor and
  deleted **five figure functions** (22s). Recovered only because the file had
  been committed minutes earlier. **Commit often; prefer a unique anchor or the
  edit tool over index-based splicing.**
* Writing a session's counters into the report **before** running the suite —
  1664 was written, 1653 was measured. Run first, then write.
* Pre-registering after a debug run has been seen. If it happens, **disclose
  the debug run in full inside the entry** (entry 19 does this).

---

## 9. Rules you must follow

1. **Update `HANDOFF.md` in the same commit as any change.** A change without a
   handoff update is incomplete.
2. **Run the suite before and after.** `python -m pytest tests nebula/tests -q
   -m "not slow"` — **1653 tests, ~4 min**. Report the count both times. Never
   commit with failures.
3. **Pre-register anything whose result could be argued for afterwards.**
   `PREDICTIONS.md`, with acceptance bands and falsifiers, **committed before
   the run**. Record misses as misses. **Nothing above an outcome heading is
   ever edited.**
4. **Every new gate is deliberately broken, watched go red, and restored** —
   and say so in your report.
5. **Never fabricate a number.** A missing artifact raises; it does not get a
   placeholder. This applies to prose as much as to plots.
6. **ngspice's exit code is not a success signal.** Parse the output and assert.
7. **Do not modify without an explicit human decision:** `common/params.py`,
   `rl/contract.py`, `rl/env.py`, `V1_SPECS`, the box, the tolerances, the
   pre-screen. **Wrap, do not replace** — `rl/corner_env.py` is the precedent.
8. **Do not change `V1_SPECS`.** Anything that shifts `B = N + 1` invalidates
   every published reward, the +8.950669 ceiling, the whole `BASELINES.md`
   ranking and the G4 verdicts. New spec sets are **new tuples defined by
   enumeration**, never by exclusion (G101) and never by addition to another
   set without checking every inherited member (G106).
9. **Do not loosen the pole-zero fit residual limit** to make the eye
   evaluable. Session 22s established that this would make every downstream eye
   number unfounded.
10. **Do not delete** the unfiltered linear-range front, the failed
    predictions, or any retraction. **The misses are the asset.**
11. **Do not report a nominal design as corner-verified, or an extrapolation as
    a measurement**, anywhere.
12. **Do not let the LLM wrapper near the optimiser.** The grep test stays.
13. **You may not decide anything in §5's OPEN list.** State the options with
    the measured numbers behind each and ask.
14. Windows: no non-ASCII in `print()`; run pytest from the repo root.
15. Commit as `Jai Kaushik <jaikaushik-prog@users.noreply.github.com>` (G12).
    **The repo is PRIVATE and must stay private** (G1).
16. **If a task contradicts a measurement you make, stop and report the
    contradiction** rather than proceeding. Two items in the review that
    produced §6 did exactly this and the measurement won both times.

---

## 10. What is new on disk since the last rewrite

| Path | What |
|---|---|
| `device/sky130_runner.py` | `linear_in_pp_v` / `max_swept_in_pp_v`, `measured_linear_input_pp_v`, parameterised HD3 tone and amplitude |
| `experiments/exp_linear_pareto.py` | the attainable linear-range front, two arms, S3-filtered |
| `experiments/exp_hd3_amplitude.py` | HD3 vs amplitude at three tones |
| `experiments/exp_sweep_cost.py` | the 8 086× extrapolation, with derived levels |
| `experiments/exp_joint_search.py` | the S3+S8+HD3 joint search, `V4_SPECS` |
| `experiments/exp_tunable_trade.py` | the bank, and the `k`-cancellation |
| `rl/reward_v1.py` | `S4_hd3_nyq` tolerance row, `V4_SPECS` (V1–V3 untouched) |
| `experiments/baselines.py` | `CmaConfig.x0` — local seeding, used by nothing in `BASELINES.md` |
| `experiments/exp_g4_verify.py` | the drive-headroom row in the 135-point checklist |
| `report/figures.py` | `fig_hd3_amplitude`, `fig_sweep_cost`, `fig_tunable_trade`; Figure 1 fixed |
| `tests/test_linear_and_sweep_cost.py` | 19 tests |
| `PREDICTIONS.md` entries 18–21 | one falsified external prediction, three scored pre-registrations |
| `HANDOFF.md` §9 | gotchas **G102–G107** |

---

## 11. The one-paragraph version, if you read nothing else

**The eye was never blocked by the circuit — it was blocked by the objective**,
which contains S3 and not S8, so nothing had ever asked for both. Asking for
both produced a design passing **11 of 11 rows at 135 points with zero
failures**, whose eye is measurable at **98** of them; all 37 gaps are at
corners the 3-corner search screen has no member of, which is now the
**fourth** measurement of that blind spot and the best-supported open decision
on the list. **Before you report any margin number, read §4:** the 135-point
compliance matrix is scored on the coarse `ac dec 50` lattice, so today's
"2.1 % of tolerance" is **0.154 lattice steps** — below the instrument — and
the two designs are identical on it, which falsifies the external review's
premise that we would be trading a 99 % margin for a 2 % one. The physical
finding underneath is better than the artifact: **PVT spread consumes 97.9 % of
S3's one-octave frequency window**, so every design lands at the edge because
the specification is thin, not because the design is. RL remains a null and is
**correctly** a null — the spec manifold is 1-D, and on a 1-D manifold a lookup
table is the optimal policy — but the one experiment that could still produce
an affirmative result, **corner-aware RL at scale**, is built, tested, deferred
three times, and is now first. After that, the highest value in the project is
writing: **four measured results in `CHANNEL_MODEL.md` never reached the
report**, and one of them — that a 1-tap DFE is sufficient because 31.2 % of
the residual sits beyond 20 UI — *derives the topology the brief mandates*
instead of assuming it.
