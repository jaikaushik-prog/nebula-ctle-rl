# BASELINES.md — the benchmark the final claim rests on (task 7)

> **The comparison is the result.** A win claim without a tuned baseline will
> not survive the panel. This file is the auditable record of what was
> allocated, what was run, what was measured, and what was predicted before any
> of it happened.

**Status.** The harness, the pre-screen, the pre-registration and the tests are
**done**. The 7e pivotal experiment is **measured and its verdict is in**. The
full 30 000-simulation sweep is **specified, costed and reproducible by one
command** but has **not been run** — a pilot at 1/10 the budget was run instead
to validate the harness end to end against real ngspice. Every number below is
labelled with which of those it came from. Nothing is estimated.

| | |
|---|---|
| Harness | `nebula/experiments/baselines.py` |
| Pre-screen | `nebula/experiments/prescreen.py` |
| Tests | `nebula/tests/test_baselines.py` (27), `nebula/tests/test_prescreen.py` (17) |
| Pre-registration | `nebula/PREDICTIONS.md` entry 6, committed **before** the run |
| One command | `python -m nebula.experiments.baselines --sweep` |
| Logged data | `nebula/experiments/baselines_pilot.jsonl` (tracked, G49) |

---

## 0. What a reader in a hurry needs

1. **7e's loud verdict does not fire.** The analytic pre-screen predicts
   `f_peak` to **4.93 %** median absolute percent error and removes **61.7 %**
   of the box for free, but the S3 rate among the designs it accepts is
   **34.9 %**, not the >50 % that would mean physics solves the nominal
   problem. It is a **2.60× yield multiplier**, which is a large saving and not
   a solution. *(And read §5's widening table before quoting that: the screen
   can be pushed to 76.4 % effective yield, but only by discarding 15.75 % of
   the designs that actually meet S3.)*
2. **The primary metric has a ceiling, and it is a property of the AC sweep
   grid rather than of the circuit.** On P1 no design can score above
   **+8.95067**, because `meas ac MAX` reports frequencies on a lattice
   0.0664 octaves apart and `S3_f_peak` is the binding reward row. Four
   independent pilot runs found four *different* designs all scoring 8.950670.
   So "best reward at budget" saturates on P1 and cannot separate methods
   there; **simulations to reach the ceiling** is the metric that can, and it
   is computed beside it.
3. **The full sweep does not fit and the cut is stated.** Fully crossed it is
   63 000 simulations = 23.5 h. What is allocated is 30 000 simulations =
   11.2 h. **P2 is cut entirely; P3 loses its pre-screened and PPO arms. No
   seed count and no per-run budget was reduced.**
4. **The highest-leverage change to this benchmark is not in this file.** At
   the measured 1.341 s/simulation the sweep is 11.2 h; at the ~0.33 s/eval
   the nfet-only library achieves it is **0.9 h**. HANDOFF §8's decided re-run
   order already puts that trim first.

---

## 1. (7a) The budget arithmetic

Reproduce with `python -m nebula.experiments.baselines --budget`.

### The measured inputs

All three are session 17 §6i, measured with a discarded warm-up, a randomised
configuration order and a control (G71 is the gotcha that made all three
necessary):

| what | measured | source |
|---|---|---|
| serial, **uniform box draws** | **3.999 s/sim** | 24-task 1-worker pass |
| serial, **policy trajectory** | **2.071 s/sim** | 500-step PPO run, 793 calls in 1585.8 s |
| **8 workers**, uniform box draws | **1.341 s/sim** | the same 24-task sweep |
| speed-up at 8 workers | **2.98×** | and 11 workers is *slower* than 8 |

**The two serial numbers disagree by 1.9× and that disagreement is itself a
finding**: the same evaluator costs twice as much on uniformly drawn box points
as on points a policy walked to. The benchmark's own task set is uniform box
draws, so **the arithmetic below uses the expensive one**. Sizing to the cheap
one would plan a 12-hour run that takes 23 hours.

### The design of the experiment as a budgeting problem

99.7 % of a run is the simulator, so cost = simulations × seconds-per-simulation
and nothing else matters. The budget is quoted **in simulations** throughout,
which makes a rung's cost independent of how many evaluation points a design
needs: a P3 run with a 150-simulation budget evaluates 25 designs, a P1 run
evaluates 150, and both spend 150 simulations.

**Budget per run: 150 simulations.** This is the x-axis of every plot here and
7a forbids shrinking it quietly, so it is fixed up front and held across every
method and every rung. Why 150: at P1's 13.44 % base rate uniform random
expects ~20 feasible designs in 150 simulations, so the anytime curve has
resolution and the secondary metric is only lightly censored; and it is ~6× the
designer baseline's twenty-odd runs, which is the comparison a judge will make.
Why not 60: CMA-ES at its default population of 10 would get six generations,
barely more than its initial distribution.

**Replicates (7h's floors):** uniform 20, LHS 20, CMA-ES 10, GP-BO 10, PPO 10.

### It does not fit

```
fully crossed = 3 rungs x 5 methods x 2 screen arms x (20+20+10+10+10) seeds-worth
              = 3 x 2 x 70 runs x 150 sims
              = 63,000 simulations
              = 63,000 x 1.341 s = 23.5 hours
```

### What was cut, and why

Per 7a the cut falls on **problems and pre-screen arms**, never on the per-run
budget and never on the seed counts.

| block | rung | screen | methods | runs | simulations |
|---|---|---|---|---|---|
| A | P1 | no | all five | 70 | 10 500 |
| B | P1 | yes | all five | 70 | 10 500 |
| C | P3 | no | four (no PPO) | 60 | 9 000 |
| | | | **total** | **200** | **30 000** |

```
30,000 x 1.341 s = 11.2 h   <- what this is sized to
30,000 x (2.071/2.98) s = 5.8 h   <- the optimistic bracket
```

* **P2 cut entirely.** It is the interpolation between P1 and P3, and the
  quantity it resolves — how much of the loss is corners and how much is load —
  is already measured twice: session 10d put the corner tax at 39 % of the
  nominal winners, session 12b put the load cost at 99.4 %. P2 buys a third
  estimate of a known split for a third of the night.
* **P3's pre-screened arm cut.** The screen is calibrated at TT and its
  false-rejection rate at corners is unmeasured. A screened P3 arm would
  confound "the screen helps" with "the screen is miscalibrated off nominal".
  Measuring that calibration is cheaper than running the arm.
* **P3's PPO arm cut**, structurally: `CtleSizingEnv` takes one corner and one
  load, so a worst-over-corners environment does not exist. Inventing one for a
  single method would make the comparison about corner handling rather than
  about search.

`test_the_cut_fell_on_problems_and_screen_arms_not_on_seeds` pins all of this,
and `test_the_allocation_fits_an_overnight_run_and_the_full_design_does_not`
fails if either half of the arithmetic stops being true.

---

## 2. (7b) The problem ladder

A benchmark on an infeasible problem measures nothing: every method scores
"never found one" and the comparison is empty. The robust problem **may be
infeasible** — session 12b left 1 design in 1890, and G66 then measured drawn
passives moving `f_peak` by 0.1329 octaves against the 0.12 octaves of centring
slack that selected that one design. So there is a ladder, and all rungs are
reported.

| rung | evaluation points | sims/design | expected base rate |
|---|---|---|---|
| **P1** | TT / 1.00 / 27 °C, `cl_mid` = 32.63 fF | 1 | **7.10 %** (measured at *these* conditions, session 22 — see the correction below) |
| **P2** | 3 screen corners, `cl_mid` | 3 | ~8 % (session 10d, at the legacy pin) |
| **P3** | 3 screen corners × {`cl_lo` 13.64 fF, `cl_hi` 78.04 fF} | 6 | **possibly empty** |
| **P4** | tunable: fixed geometry, inner `(rs, cs)` search per (corner, load) | — | **seam only** |

### CORRECTION, 2026-08-18 (session 22b): this table used to read 13.44 % on the P1 row, and that was a load mismatch

**13.44 % was never measured at `cl_mid`.** It is the rate on
`robust_geometry_data.csv`, and **every row of that file has `cl` = 150 fF** —
the legacy pin, **4.598× `cl_mid`**. `exp_attribution.legacy_cl_f()` reads it
off the file and raises if the column is not constant, so this cannot drift
back.

Two consequences, and the second is the one that matters:

* The P1 row above now carries **7.10 %** [6.05, 8.31] (n = 2000), measured by
  `exp_difficulty.py` through this benchmark's own sampler, evaluator, box and
  load. `nebula/DIFFICULTY.md` §3.
* **`PLAN.md` D4 rejected 13.54 % on the ground that it was "`cl` pinned at a
  load the next stage cannot present" — and 13.44 % was measured at that same
  load.** So the stated discriminator between the recommended baseline and its
  rejected alternative did not exist. D4 is now decided as **7.10 %**.

`nebula/ATTRIBUTION.md` decomposes the gap. Note what is *not* claimed here:
13.44 % is a correct number for its own population, and the two S3 definitions
(`prescreen.s3_true`'s two rows and `reward_v1.V0_SPECS`'s three) agree on it
**exactly** — the definition explains none of the difference.

The score is the **worst** over a rung's points — CLAUDEwa.md §12's first named
trap read the right way round. The evaluation short-circuits when a point
returns the invalid floor, and that is **exact rather than an approximation**:
`invalid_reward` is the global minimum of reward v1's four bands, so no later
point can lower the result. `test_the_floor_short_circuit_is_exact` fails if
that stops being true.

### P4 has not landed, and the blocker is not effort

`experiments/tunable.py` already runs a whole `(rs, cs)` grid inside one ngspice
process via `alter` on the **ideal** R and C elements — 13.6 ms per setting
against ~150 ms for a process each. **That 11× is exactly what G63 destroys**:
with drawn passives there is no `Rs` element to alter, `alter` fails silently,
and every sweep setting returns the first geometry's numbers and exits 0. So the
tunable rung needs either drawn-passive re-parses (which removes the 11× that
makes it affordable) or a proof that the ideal-element inner search transfers.
Neither is done.

**The seam:** add a `Problem` whose points carry an inner-search callable and an
`inner_search` hook on `Objective.evaluate`. Nothing else changes — the budget,
the metrics and the statistics are all in simulations already.

### Which box and which evaluator each rung ran against

The bounds proposal is **still not in `common/params.py`** (HANDOFF §8), so the
benchmark records what it ran against rather than assuming:

* **Box:** `rl/contract.ACTION_SPACE`, which is `s3_yield.PROPOSED_BOX`
  verbatim — seven dimensions, `nf_in` fixed at 4, the tail derived from
  `i_bias`. `common/params.py::BOUNDS` is **untouched** (CLAUDEwa.md §8 rule 6)
  and is *not* what this ran against.
* **Evaluator commit:** written into every run log's header row by
  `provenance()`, along with the library name, the seven tolerances and the
  pre-screen's own constants. An artifact that cannot say which evaluator
  produced it is not re-runnable.

---

## 3. (7c) Metrics

### Primary — the anytime curve, always defined

Best reward achieved as a function of simulations spent, per method, per
problem, **median over seeds with a percentile-bootstrap band**. It is defined
whether or not anything feasible exists, which is exactly why it is primary and
why P3 is worth running even if it is empty.

Medians and not means, for a reason that is not stylistic: the reward has a
hard floor at `invalid_reward` and a four-band structure, so one unlucky seed
drags a mean across a band boundary while the median stays where the typical
run is.

### **The ceiling, and why it changes how P1 is read**

Every netlist in this project sweeps `ac dec 50 1meg 100g`, so `meas ac MAX` can
only report a frequency on the lattice `f_k = 1 MHz · 10^(k/50)` — **0.066439
octaves apart**, which is the same quantisation session 11 used to say S3's
one-octave window holds exactly 15 distinct `f_peak` values.

`reward_v1`'s feasible branch scores `B + min_i(margin_i / tol_i)`, and the
binding row on P1 is essentially always `S3_f_peak`, whose margin is
`0.5 − |log2(f_peak / f_target)|`. With the target at the geometric centre of
S3's octave the nearest lattice point is **0.024665 octaves** away, so

```
ceiling = 8 + (0.5 - 0.024665)/0.5 = 8.950669
```

**Measured in the pilot: four independent runs, four different `design_id`s,
all scoring 8.950670.** The derivation and the measurement agree to six
decimals.

Two consequences, both of which had to be built into the harness rather than
noticed afterwards:

1. **Best-reward-at-budget saturates on P1** and cannot separate methods there.
   Any method that finds any design whose `f_peak` lands on the nearest grid
   point with all seven specs met scores exactly the ceiling.
2. So the harness also reports **simulations to reach the ceiling**, censored
   and handled identically to simulations-to-first-feasible.

This is not a defect in the reward. It is the reward faithfully reporting that
the measurement cannot resolve `f_peak` more finely than 0.066 octaves, which
is a fact about the AC sweep that a finer reward would hide.

### Secondary — simulations to first feasible, as censored data

Some seeds never find one. Reported as three numbers and never one:

* the **fraction of seeds** that found a feasible design within budget;
* the **median among those that did**, stated as **conditional**;
* the **count of censored seeds**.

The budget is **not** substituted, infinity is **not** substituted, and the
censored seeds are **not** dropped in favour of a mean of the rest. Each of
those produces a plausible number that flatters whichever method got lucky.
`test_censored_table_never_substitutes_the_budget` is the gate.

### Wall clock, reported separately

Simulation counts are the headline; wall clock is a secondary column. For PPO
the policy update is 0.3 % of a run (session 17, measured), but **GP-BO's model
fit is O(n³) in observations and is not free** — by the end of a 150-simulation
run it is fitting a GP to ~150 points before every proposal. A method that wins
on simulations and loses on wall clock must show both, so `model_seconds` is
tracked per run and printed beside `sec_per_sim`.

---

## 4. (7d) The methods

All six against the **identical** evaluator, the **identical** scalar objective
(reward v1 with its four bands and seven tolerances) and the **identical**
geometry mapping (`sizing_from_u`, which draws real SKY130 passives).

| method | what it is | notes |
|---|---|---|
| `uniform` | uniform random inside the box | the reference rate |
| `lhs` | centred Latin hypercube, one block per budget | independent permutation per dimension |
| `cmaes` | (μ/μ_w, λ)-CMA-ES, **Hansen's published defaults** | written out in ~70 lines: `cma` is not installed, the competition mandates open-source tooling, and a reviewer can check the equations |
| `gp_bo` | GP with Matérn(5/2)+White, Expected Improvement | sklearn; `scikit-optimize` is not installed. EI maximised over a 2000-point random candidate pool |
| `ppo` | **the existing untuned policy from task 6**, unchanged | P1 only; explicitly labelled untuned |
| `designer` | reconstruction from the session log | **not a run** — see below |

**CMA-ES and GP-BO get the same scalar reward as everything else rather than a
constraint-handling scheme of their own**, so the comparison is about search and
not about objective formulation. Reward v1's four bands do the constraint
handling for all of them identically.

**Nothing is tuned for any method.** CMA-ES uses `sigma0 = 0.3` and
`popsize = 4 + ⌊3 ln d⌋ = 10`; GP-BO uses `n_init = 2d+2 = 16` and `xi = 0.01`;
PPO's `PPOConfig` is session 17's, unmodified. The row has to read "CMA-ES with
its published defaults", not "CMA-ES after we fiddled with it".

### The designer baseline — a reconstruction, not a run

HANDOFF §12, session 9c (2026-08-04), verbatim:

> *"Human-led hand-sizing session at the ngspice prompt; these numbers come
> from **twenty-odd AC runs** done deliberately, not from a script."*

That session produced **twelve configurations meeting S3** (3–12 dB peaking,
`f_pk` in 1.25–2.5 GHz), spanning 4.63–10.01 dB at 1.32–2.30 GHz, after a
five-point width sweep that fixed a badly mis-biased operating point
(gm/I_D 1.7 → 8.4) and separate `Rs`, `Cs` and `RL`/`CL` probes.

**So the row is: ≈20–25 simulations, 12 S3-meeting designs.** And it is
**not commensurable with any rung**, which is stated rather than left for a
reader to discover:

* ideal R/C passives and **ideal tail sinks** — strictly easier than P1, which
  draws real SKY130 devices and a current mirror;
* `cl` = 100 fF, 3.1× above `cl_mid` and outside `CL_RANGE.md`'s derived range
  entirely;
* **S3 only** — noise, power and both saturation margins were not checked at
  those twelve points, and reward v1 scores all seven;
* one corner, no load range.

It is a **lower bound on the simulations a designer needs and an upper bound on
what those simulations established**. It is reported because it is the number
the judges have in their heads, and putting a number on it is more honest than
leaving it implicit. `test_designer_baseline_is_traceable_to_the_session_log`
greps HANDOFF.md for the quote, so the row cannot drift into a recalled number.

---

## 5. (7e) The pivotal experiment — does physics alone solve this?

Reproduce with `python -m nebula.experiments.baselines --prescreen`. **No
simulation was run to produce any number in this section.** The calibration and
the accuracy both come from `robust_geometry_data.csv` — 1890 already-paid-for
TT designs from session 11, tracked in the repo (G49).

### What is predicted, and which parts are free

```
f_z  = 1/(2 pi Rs Cs)              EXACT — passives only, no device quantity
f_p1 = k/(2 pi Rs Cs)              needs gm
f_p2 = 1/(2 pi RL CL)              EXACT — passives only
k    = 1 + K_ALPHA (gm + gmbs) Rs/2
```

Two of the three cost nothing and cannot be wrong. The predictor uses the
**drawn** passive values (`to_geometry`, 0.036 ms, pure Python) and adds half
the load resistor's `res_po` bottom plate to `cl` — **G66's mechanism, in the
predictor rather than as a caveat beside it**.

**The peak is computed, not assumed.** `f_peak` is the numerical maximum of the
full one-zero/two-pole magnitude over a log grid. Session 10b's pre-registered
"the peak sits near f_p2" is a recorded miss in `PREDICTIONS.md`, so an
asymptote would be repeating a falsified assumption.

**`gm` comes from a gm/I_D characterisation**, least-squares fitted once on the
1890 points: `log(gm/I_D)` against the inversion level `J = I_D/(W/L)`, `L` and
`nf`. That is a property of the transistor, not of this circuit, which is why
one fit transfers across the box. Measured error: **median 2.4 %, p90 7.6 %,
p99 24.1 %**.

### The G60 calibration — one scalar, fitted the way G60 prescribes

> *"`f_z` and `f_p2` are EXACT (passives), `g_dc` comes from the measurement,
> and only `k` is fitted, from the measured boost. Then the peaking and the
> peak frequency are INDEPENDENT checks."* — G60

So `K_ALPHA` is chosen to zero the **median peaking bias**, and nothing about
`f_peak` enters the fit. The f_peak error is then a check that was not
optimised for.

| `K_ALPHA` | median peaking bias | f_peak MdAPE *(the independent check)* |
|---|---|---|
| 0.800 | −0.288 dB | 7.02 % |
| 0.850 | −0.140 dB | 5.60 % |
| **0.900** | **−0.009 dB** | **4.93 %** ← chosen |
| 0.950 | +0.118 dB | 4.91 % |
| 1.000 | **+0.267 dB** | 5.53 % ← **§6 verbatim** |

`K_ALPHA = 1.0` is the uncalibrated §6 equation, and 7e forbids using it here.
Its bias is **+0.27 dB in the same direction as G60's +0.77 to +1.47 dB**,
which was measured on a different experiment whose designs sat at higher `Rs` —
where G60 says the error grows.

### Predictor accuracy

| | |
|---|---|
| `f_peak` MdAPE, **global** | **4.93 %** |
| `f_peak` MdAPE, **0.5–5 GHz** (the decision region) | **4.80 %** *(n = 1121)* |
| `f_peak` p90 absolute percent error | 20.07 % |
| peaking, median absolute error | 0.284 dB |
| peaking, median bias | −0.009 dB *(by construction)* |

The two MdAPE numbers being equal is worth a sentence: the predictor is **not**
worse near the decision boundary than it is globally, which is the only place
accuracy changes an outcome.

### The screen: free rejection against false rejection

The two errors are **not symmetric**. A rejected design is gone from the run for
good; a falsely accepted one costs one simulation and is then caught by the
evaluator. So the accept window is S3's window **widened**, and the widening
follows a stated rule against a declared cost rather than being chosen:
**the smallest widening whose measured false-rejection rate is ≤ 1 %.**

| widening (oct / dB) | free rejection | false rejection | effective S3 yield | lift |
|---|---|---|---|---|
| 0.00 / 0.0 | 85.2 % | **15.75 %** (40) | **76.4 %** | 5.69× |
| 0.10 / 0.5 | 80.1 % | 4.72 % (12) | 64.4 % | 4.79× |
| 0.20 / 1.0 | 75.6 % | 3.54 % (9) | 53.0 % | 3.95× |
| 0.30 / 1.5 | 69.0 % | 1.57 % (4) | 42.7 % | 3.18× |
| **0.40 / 2.0** | **61.7 %** | **0.39 %** (1) | **34.9 %** | **2.60×** ← chosen |
| 0.50 / 2.5 | 55.5 % | 0.39 % (1) | 30.1 % | 2.24× |
| 0.75 / 3.0 | 42.9 % | 0.00 % (0) | 23.5 % | 1.75× |
| 1.00 / 4.0 | 33.9 % | 0.00 % (0) | 20.3 % | 1.51× |

`test_margins_follow_the_stated_rule` re-derives the chosen row from the ladder
and fails if the constants are hand-edited — which is the defence against
CLAUDEwa.md §8 rule 6, since a widening *is* a spec-tightness heuristic.

### **The verdict, and it does not fire**

```
S3 base rate over the box        13.44 %
S3 rate among ACCEPTED designs   34.94 %      <- 7e's threshold is 50 %
```

**Physics does not solve the nominal problem.** The pre-screen removes
three-fifths of the box for nothing and multiplies the yield by 2.60×, which is
a large saving and not a solution. A learned method is still needed for search,
and the RL contribution does **not** collapse onto amortisation alone.

**The nuance that must travel with that number, in both directions:** the
screen *can* be pushed above the threshold — 76.4 % effective yield at zero
widening — but only by discarding **15.75 %** of the designs that actually meet
S3. Whether that trade is acceptable is a human's call, and the whole ladder is
printed so it can be made. `test_the_loud_verdict_does_not_fire_and_the_test_says_which_way`
pins the outcome **in both directions**: if a future change pushes the effective
yield above 50 %, that test fails and forces the result into HANDOFF.md rather
than letting it slip in as a silently-updated number.

### What the screen is actually removing

**84.3 % of the G44 population — 488 of the 579 designs with no interior peak
at all — is rejected before any simulation.** That is the class of design
session 17 measured as **78 % of everything its policy found** (G65), each of
which would otherwise cost a full simulation to reject. So the screen's value
is less "it finds good designs" than "it declines to simulate circuits that do
not equalise".

### A correction earned while building it

A **"the peak is at the grid edge" test can never fire** on a one-zero/two-pole
response: that magnitude falls as 1/f eventually, so its maximum is always
interior. The first version tested for an argmax at the top of the search grid
and fired **zero times on 1890 designs**, which is how the mistake was found.
What the *simulator* reports as an edge is a peak above its own 20 GHz search
top, so the predictor now uses `evaluator.F_PEAK_HZ_LIMITS[1]` — one definition,
shared (rule 9). The G44 population is caught anyway, under the `f_peak` label.

---

## 6. (7f) Fairness rules, enforced in code

Each is a property of the module, not a promise, and each has a test.

| rule | how it is enforced | test |
|---|---|---|
| Count **every** simulation, including invalid ones | the method loop terminates on the simulation count, never on an evaluation count; `EvalResult.n_spice` already includes retries | `test_every_simulation_is_counted_including_invalid_ones` |
| Identical validity handling (the G72 bands) | every method goes through `rl.evaluator.evaluate` and `rl.reward_v1.reward`; nothing reimplements a spec test | `test_the_budget_stops_every_method` |
| Identical box, geometry mapping, spec target | `rl.contract.sizing_from_u` for every method; one `target_f_peak_hz` on the `Objective` | `test_provenance_pins_the_evaluator_and_the_box` |
| Identical seed protocol, seeds recorded | `BASE_SEED + PROBLEM_OFFSET + METHOD_OFFSET + replicate`, on every logged row | `test_seed_protocol_is_a_stated_rule_and_collides_with_nothing` |
| Same worker count everywhere: **8** | `WORKERS = 8`, per the measured 2.98× (11 is slower) | `test_workers_is_eight_because_eleven_is_slower` |
| Evaluator commit pinned in every artifact | `provenance()` reads it from git into the run-log header | `test_provenance_pins_the_evaluator_and_the_box` |

**Invalid rates are reported per method**, because a method that finds more
invalid regions than another is telling you something. The reference points are
session 17's: 10.5 % over a uniform box sample and 26.5 % over a policy
trajectory.

### The parallelism is across runs, and that is a fairness decision

Parallelising *inside* a run would help the batch methods (uniform, LHS, one
CMA-ES generation) and be impossible for GP-BO, whose every proposal depends on
the previous answer — so the comparison would become a comparison of how
batchable each method is. Across runs, every method keeps its own sequential
decision structure and every one of them sees the same 8-worker machine.

### One asymmetry, declared

The pre-screen wraps PPO's **actions** but not its episode **resets**.
`CtleSizingEnv.reset` draws its own start and retries up to 25 times, and its
seeded form *raises* on a start that does not simulate — so screening the draw
means reimplementing reset, not passing a flag. The screened PPO arm therefore
still spends simulations on unscreened episode starts, roughly one per episode.
That makes it a **weaker wrapper than the other four methods get**, and it is
stated here so it is not read off the numbers as a property of PPO.

---

## 7. (7g) Timing discipline

The cold-cache effect that defeated randomisation on an idle machine is
measured, not hypothetical: session 17 found the same 8-worker configuration
reporting **2497 ms/task running first and 1558 ms/task running last** (G71).
The control was the detector. So:

* **jobs are interleaved** — the shuffle is over individual runs, not over
  blocks, so no method is systematically early or late (a block-level shuffle
  would still put all twenty `uniform` replicates together);
* a **warm-up** run of the first configuration executes first, alone, and is
  **discarded from the analysis**. This is the defence that actually works —
  with randomisation and a control but no warm-up the control still came back
  at 1.60×, because *the first configuration always pays, whichever one it is*;
* the **control** re-runs that same configuration last, also alone. Both are
  single-process, one before and one after the pool, so the ratio measures
  **machine drift** and is not confounded by a draining pool having fewer
  competitors;
* if they disagree by more than **[0.80, 1.25]** — session 17's own limits —
  the result carries `timing_void = True`, the wall-clock numbers for that
  sweep are **void, and the sweep is repeated rather than adjusted**;
* both the warm-up and the control cost real simulations and both are counted.

**Simulation counts are the headline and wall clock is a secondary column**,
because only one of the two is immune to this.

---

## 8. (7h) Statistics

* **Medians with percentile-bootstrap confidence intervals**, not means.
* **Pairwise Mann-Whitney** on simulations-to-first-feasible, **among
  uncensored seeds only**, with the common-language effect size
  `U/(n_a n_b) = P(a < b)` reported beside every p-value.
* **Multiple comparisons are stated, not silently corrected.** The tests are
  reported as a family and are not used to select a winner; the Bonferroni
  threshold at α = 0.05 is printed so any p above it can be read as
  uncorrected.
* **Any ranking whose intervals overlap is reported as "not separable at this
  sample size", not as a ranking.** `separable()` is an interval test and
  touching intervals count as overlapping.

---

## 9. (7i) The pre-registration

`nebula/PREDICTIONS.md` entry 6, committed as `c7e039c` **before**
`baselines.py` had ever touched ngspice. It carries the predicted ordering per
rung, seven quantitative predictions with acceptance bands, five falsification
conditions, and an explicit guard against over-claiming **in either direction**:

> If PPO loses, that is the expected result and must be reported as such. It is
> evidence that untuned PPO at this budget on a 7-dimensional problem loses to a
> tuned classical optimiser — which is unsurprising — and it is **not** evidence
> about the amortised, spec-conditioned claim, because that claim is not being
> tested here: every run in this sweep optimises one fixed spec target from
> scratch. Equally, if PPO were to win it would not establish the amortised
> claim either.

---

## 10. (7j) Artifacts

* **One command reproduces the whole sweep with fixed seeds:**
  `python -m nebula.experiments.baselines --sweep`.
* **Every evaluation is logged with its `design_id`**, in JSONL, one row per
  trial, with the header row carrying the seeds, the box, the tolerances, the
  library and the evaluator commit. The sweep therefore doubles as training
  data for the surrogate work — thousands of free labelled points that should
  not be regenerated later.
* **Results are tracked, not gitignored** (G49): the write-up quotes numbers
  from them.

---

## 11. Results — the pilot

**This is a PILOT, not the sweep.** 60 simulations per run instead of 150;
3 replicates instead of 10–20; 2 replicates on P3. **1992 simulations,
33 runs, 7.4 hours wall.** It exists to validate the harness against real
ngspice and to test whether the pre-screen transfers — not to rank methods.
**Nothing here is separable at 3 seeds and the tables say so.**

Reproduce: `python -m nebula.experiments.baselines --analyse
nebula/experiments/baselines_pilot.jsonl`.

### The run did not finish cleanly, and that is itself a result

33 of 34 jobs completed and the process was killed before it wrote its summary
or ran the timing control. **Every row survived, because the log streams.**
The analysis below was rebuilt from the `trial` rows by `analyse_log()`, which
now exists *because of* this — a 12-hour sweep interrupted in its last minute
would otherwise have produced 25 500 simulations and no result.

**Consequence, stated rather than hidden: the timing control never ran, so by
§7's own rule the wall-clock numbers in this pilot are unvalidated.** The
simulation counts stand; they are immune to this.

### Anytime curve — best reward at 60 simulations

| group | n | median | 95 % CI | invalid | screened out | s/sim |
|---|---|---|---|---|---|---|
| P1/uniform | 3 | **8.951** | [8.685, 8.951] | 33.3 % | — | 11.7 |
| P1/uniform+screen | 3 | **8.951** | [8.951, 8.951] | 21.7 % | 150 | 13.4 |
| P1/lhs | 3 | 8.651 | [8.651, 8.916] | 38.3 % | — | 13.1 |
| P1/lhs+screen | 3 | **8.951** | [8.916, 8.951] | 26.7 % | 137 | 11.7 |
| P1/cmaes | 3 | 8.916 | [8.818, 8.916] | 25.0 % | — | 11.7 |
| P1/cmaes+screen | 2 | 8.884 | [8.818, 8.951] | 9.2 % | 39 | 11.0 |
| P1/gp_bo | 3 | **8.951** | [8.951, 8.951] | 13.3 % | — | 11.7 |
| P1/gp_bo+screen | 3 | **8.951** | [8.951, 8.951] | **3.3 %** | 17 | 13.1 |
| P1/ppo | 3 | 8.252 | [8.080, 8.951] | 13.3 % | — | 11.0 |
| P1/ppo+screen | 3 | **8.951** | [8.818, 8.951] | 25.0 % | 17 | 18.6 |
| **P3/uniform** | 2 | **−0.445** | [−0.511, −0.378] | 52.1 % | — | 15.8 |
| **P3/cmaes** | 2 | **−4.709** | [−8.417, −1.000] | 44.9 % | — | 12.2 |

Six of the ten P1 groups sit exactly at the ceiling. **That is the saturation
§3 predicts, observed:** best-reward-at-budget is not a discriminating metric
on P1, and no P1 pair is separable except one degenerate zero-width interval.

### Simulations to first feasible — censored

| group | found / seeds | median \| found | 95 % CI |
|---|---|---|---|
| P1/uniform | 3/3 | **3.0** | [1, 6] |
| P1/uniform+screen | 3/3 | **1.0** | [1, 2] |
| P1/lhs | 3/3 | 38.0 | [3, 41] |
| P1/lhs+screen | 3/3 | 8.0 | [2, 13] |
| P1/cmaes | 3/3 | 6.0 | [4, 7] |
| P1/cmaes+screen | 2/2 | 1.5 | [1, 2] |
| P1/gp_bo | 3/3 | 6.0 | [2, 10] |
| P1/gp_bo+screen | 3/3 | 1.0 | [1, 6] |
| P1/ppo | 3/3 | 4.0 | [3, 9] |
| P1/ppo+screen | 3/3 | 4.0 | [3, 25] |
| **P3/uniform** | **0/2** | — | — |
| **P3/cmaes** | **0/2** | — | — |

Every median is **conditional**; the two P3 rows are fully censored and are
reported as "0 of 2 found", not as a number.

### Simulations to the ceiling (+8.95067) — also censored

| group | reached / seeds | median \| reached |
|---|---|---|
| P1/uniform | 2/3 | 4.5 |
| P1/uniform+screen | 3/3 | **2.0** |
| P1/lhs | **0/3** | — |
| P1/lhs+screen | 2/3 | 20.0 |
| P1/cmaes | **0/3** | — |
| P1/cmaes+screen | 1/2 | 20.0 |
| P1/gp_bo | 3/3 | 39.0 |
| P1/gp_bo+screen | 3/3 | 25.0 |
| P1/ppo | 1/3 | 4.0 |
| P1/ppo+screen | 2/3 | 29.0 |

### What the pilot says against what was pre-registered

**It is a pilot, so these are indications, not outcomes.** The entry-6 outcome
section stays empty until the sweep runs.

| prediction | pilot | reading |
|---|---|---|
| uniform finds a feasible design on ≥ 95 % of seeds | **3/3** | consistent |
| uniform median sims-to-feasible ≈ 5 (band 2–12) | **3.0** | consistent |
| pre-screened uniform ≈ 2 (band 1–5) | **1.0** | consistent |
| CMA-ES / GP-BO 5–20 | **6.0 / 6.0** | consistent |
| PPO finds one on ≤ 50 % of seeds | **3/3** | **MISS, and in PPO's favour** |
| screen's free-rejection rate 55–70 % inside the sweep | **63.9 %** | consistent |
| P3 empty | **0/4 seeds feasible** | consistent |

Two things stand out and neither is a conclusion at 3 seeds:

* **PPO was predicted to lose and did not obviously lose.** Median 4.0
  simulations to first feasible, 3/3 seeds — indistinguishable from uniform's
  3.0. Its *final* reward is the worst of the ten groups (8.252), which is the
  shape prediction 3 argued for: the episodic methods reach feasibility fast
  and then fail to climb. **Whether that survives 10 seeds is exactly what the
  sweep is for**, and the guard in entry 6 applies either way — this is one
  spec target optimised from scratch, which tests nothing about the amortised
  claim.
* **LHS is the worst method here (38.0 against uniform's 3.0)**, which is
  against the pre-registration's "LHS ≈ uniform or better". The interval is
  [3, 41] at 3 seeds, so it may be noise. A mechanism worth checking if it
  survives: the block is sized to the whole budget, so a 60-cell stratification
  visits its cells in a random order and the first few draws carry no more
  coverage than uniform's, while the stratification constrains later draws.

### Invalid rates, per method (7f)

`P1` unscreened ranges 13.3 % (GP-BO) to 38.3 % (LHS); `P3` 44.9–52.1 %. All
are far above session 17's 10.5 % on a uniform box sample. **The mechanism is
one thing, overwhelmingly: 392 of ~430 invalid evaluations — 91 % — are
`peak_is_sweep_edge`**, a response still rising at 20 GHz. Session 17 measured
78 % on a policy trajectory (G65); the pre-screen removes 84.3 % of that
population for free, which is why the screened arms' invalid rates are roughly
halved and why GP-BO+screen reaches **3.3 %**.

### **The pre-screen does not fully transfer, and a falsification condition fired**

Falsification condition 2 of entry 6 was: *"if the free-rejection rate measured
inside the sweep is far from 61.7 %, the calibration does not transfer."*
Measured on the pilot's 900 unscreened P1 evaluations
(`prescreen.accuracy_from_log`):

| | calibration set | benchmark conditions | verdict |
|---|---|---|---|
| free-rejection rate | 61.7 % | **63.9 %** | transfers |
| effective yield | 34.9 % | **38.2 %** | transfers |
| yield lift | 2.60× | **2.66×** | transfers |
| **`f_peak` MdAPE** | 4.93 % | **15.85 %** | **3.2× worse** |
| **`f_peak` MdAPE, 0.5–5 GHz** | 4.80 % | **14.89 %** | **3.1× worse** |
| **peaking bias** | −0.009 dB | **+0.361 dB** | **the bias is back** |
| **false-rejection rate** | 0.39 % | **3.88 %** (5 of 129) | **10× over its 1 % budget** |

**So the population-level rates transfer and the predictor's accuracy does
not.** The screen still rejects the right *fraction* of the box and still
lifts the yield 2.7×, but it is losing ~4 % of the feasible designs instead of
~0.4 %, and it breaches the declared budget the operating point was chosen
against.

**Widening cannot fix it, and that is the diagnosis.** Re-running the ladder at
benchmark conditions:

| widening | free rejection | false rejection | effective yield |
|---|---|---|---|
| 0.40 / 2.00 | 63.9 % | 3.88 % (5) | 38.2 % |
| 0.60 / 2.75 | 54.9 % | 3.10 % (4) | 30.8 % |
| **1.00 / 4.00** | 40.2 % | **2.33 %** (3) | 23.4 % |

Even at 2.5× the chosen widening the rate is 2.33 %, still over budget, while
free rejection falls from 64 % to 40 %. **A window cannot absorb a bias.**

**The likely mechanism, and it is checkable:** the gm/I_D model was fitted on a
population with an **ideal tail**, where `I_D` is exactly `i_bias/2`. The real
current mirror delivers **4–8 % less** than requested (session 13, measured),
so the model over-estimates `I_D`, hence `gm`, hence `k`, hence the peaking —
**+0.361 dB, the right direction and about the right size**. The drawn passives
add a second term: `to_geometry` quantises `rs` by up to ~6 %, and `k` is
linear in `rs`.

**The action, and it is deliberately NOT taken here.** Re-fitting `K_ALPHA` and
the gm model on benchmark-condition data would very likely restore the
accuracy — the procedure is G60's and the data now exists. It is not done in
this session because **re-fitting a calibrated constant on a 3-seed pilot,
without the ability to re-verify it, is what this repo's rules exist to
prevent**. It is the top open item in §12, the numbers above are what it must
beat, and until it happens **every screened arm in the sweep carries a known
3.9 % false-rejection rate and must be read with it**.

### The other measurement the pilot forced: 8 workers buy 1.80×, not 2.98×

| | s/sim | speed-up |
|---|---|---|
| single process (the discarded warm-up) | 3.060 | 1.00× |
| 8 workers, **this** task mix (33 runs, 1992 sims) | **1.698** | **1.80×** |
| 8 workers, session 17's isolated evaluations | 1.341 | 2.98× |

Each worker now runs Python *between* simulations — CMA-ES's
eigendecomposition, GP-BO's O(n³) fit, PPO's torch forward — where session 17's
probe ran nothing but ngspice. **The sweep's cost was therefore re-computed and
the allocation re-cut**: at 1.698 s/sim the previous 30 000-simulation plan is
14.2 h, not 11.2 h. P3 lost its LHS and GP-BO arms (the pilot found 0/2 seeds
feasible there for both methods it ran), giving **25 500 simulations = 12.0 h**.
Seeds and the per-run budget were again untouched.

---

## 12. What is not done

In the order a next session should take it.

1. **Re-fit the pre-screen at benchmark conditions.** §11 measured the
   predictor 3.2× less accurate and 10× over its false-rejection budget when
   moved from the calibration population to the benchmark's. `K_ALPHA` and the
   gm/I_D model should be re-fitted on the pilot's own 457 valid rows —
   `prescreen.accuracy_from_log` is the measurement and `fit_gm_model` is the
   fit. The mirror's measured 4–8 % current deficit is the first thing to try.
2. **Run the sweep.** `python -m nebula.experiments.baselines --sweep`,
   25 500 simulations, ~12 h, machine otherwise idle. It writes
   `baselines_run.jsonl` as it goes, so an interrupted run is recoverable with
   `--analyse`.
3. **Fill in `PREDICTIONS.md` entry 6's outcome** from the sweep, not from the
   pilot.
4. **P2**, if the throughput item below lands and makes it affordable.
5. **P4, the tunable rung** — the seam is in `TUNABLE_SEAM` and the blocker is
   G63, not effort.
6. **The library trim** (`PASSIVES.md` §6 item 6). It is already first in
   HANDOFF §8's decided order, and this file gives it another number: at
   ~0.33 s/eval the whole sweep is **1.3 h instead of 12.0 h**, which is the
   difference between running the ladder once and running it whenever a
   constant changes.
