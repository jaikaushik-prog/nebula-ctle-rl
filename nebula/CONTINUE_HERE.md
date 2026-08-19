# CONTINUE_HERE.md — the brief for the next agent

**Written 2026-08-19, at the end of sessions 22e–22g; updated the same day
at the end of sessions 22h and 22i, which built grid search, ran the
benchmark again, and then laddered the simulation budget 16x.** Supersedes
`nebula/NEXT_STEPS.md`, which was written 2026-08-08 and is now wrong in its
first table (it says G2 is not started and the sweep has not run; both are done).

**This file is not a substitute for `HANDOFF.md`.** It is the *entry point*:
where the project stands today, what the last four sessions changed, what is
decided, what is open, and what to do next. Every number below traces to a run
in this repository and to a commit.

---

## 0. Read in this order

| # | File | Why | Time |
|---|---|---|---|
| 1 | **this file**, §§1–8 | the situation and the decision | 10 min |
| 2 | `CLAUDEwa.md` §§1–3, §7 | the contract, the spec table, the gates | 15 min |
| 3 | `HANDOFF.md` §0 header, §9 gotchas **G92–G98** | state, and the seven traps found this week | 25 min |
| 4 | `nebula/BASELINES.md` §12 (+§12.6), then **§13** and **§14** | the sweep, its control, the grid arm, and the budget ladder | 35 min |
| 5 | `nebula/PEAK_INTERP.md` §0, §5, §7 | why the reward changed and what it cost | 10 min |
| 6 | `nebula/PREDICTIONS.md` entries 10–15 | how this project makes claims | 30 min |
| 7 | `PLAN.md` §2 (D1–D7), §7, §8 | the team's decisions and cut order | 10 min |

**Do not skim 3 and 6.** The gotchas are the highest-value-per-line thing in the
repo, and `PREDICTIONS.md` is the discipline that makes the results worth
anything: **pre-register, commit, then run.** Five predictions were missed this
week and all five are written up as misses — including entry 14's, where the
band held and the *claim* was wrong, which is scored as a miss on purpose.

---

## 1. The situation in 60 seconds

The reward function had a defect that made the benchmark unable to rank
anything. It is fixed, and the fix is proved by a matched control. The benchmark
then ran for the first time and produced a real ranking. **In that ranking PPO
— our RL method — is second-last, behind uniform random search.** Three separate
diagnoses of why have been made and two of them were wrong; the current one is
that at a 150-simulation budget the policy gradient is *uninformative*, not
absent, and no hyperparameter fixes that.

**Session 22i then laddered the budget 16×, and it produced the clearest
sentence this project has about its own method.** At 150 simulations PPO is
0.0426 behind uniform random. Give it 2400 and 23 policy updates instead of 1
and that deficit closes — **and PPO is *not separable* from uniform random at
any rung of the ladder.** Meanwhile CMA-ES reaches **8.9999** against a ceiling
of 9.0000 while PPO and random both stall at ~8.994, and that 0.006 **does not
close**: CMA-ES is separably better than PPO at **every single budget tested**.

> **PPO is not broken. It is a random search with extra steps.**

**Session 22h built the baseline G3 names and this project did not have —
grid search — and re-ran everything.** Grid comes **last**, below PPO, and the
reason is resolution rather than adaptivity: at d = 7 a 150-simulation budget
buys `150 ** (1/7)` = **2.06 levels per axis**, so even a policy that does not
learn out-resolves a factorial. **G3 now fails on both of its clauses and can
be *scored* on both, which it could not be before.** The same run reproduced
all twelve pre-existing group medians at **0.00e+00** — the benchmark is
bit-for-bit deterministic — and that determinism is what caught **G96**.

**27 days to the 15 Sept deadline.**

---

## 2. Gate status — honest

From `CLAUDEwa.md` §7.

| Gate | Due | Criterion | Status |
|---|---|---|---|
| G0 | 2 Aug | toolchain runs four analyses | **passed** |
| G1 | 3 Aug | hand reference meets S3–S7 at TT | **substantially passed** |
| G2 | 20 Aug | one full evaluation, params → ngspice → fit → eye → reward | **PASSED** (session 21, `G2_RESULTS.md`) |
| **G3** | **3 Sep** | **RL beats random search AND grid search at TT, with a plot** | **FAILING on BOTH clauses, and now scoreable on both — see §4** |
| G4 | 12 Sep | corner-robust design generated and verified | not started; see §4 for the ordering conflict |
| G5 | 15 Sep | submitted | — |

---

## 3. What sessions 22e–22h did

Thirteen commits, `9f9eca8` … the grid arm. ~92 000 simulations, ~4 hours of
compute.

### 3.1 The reward ceiling was removed at its source (`PEAK_INTERP.md`)

`meas ac g_pk MAX` can only report frequencies on the `ac dec 50` lattice —
0.0664386 octaves apart. `reward_v1`'s `S3_f_peak` margin is
`0.5 − |log2(f_peak/f_target)|`, so the reward inherited the lattice: the best
attainable score was **+8.950669** and **57 distinct designs tied there across
8000 simulations** (G74, `DIFFICULTY.md`).

Fixed by fitting a parabola through the three samples bracketing the discrete
maximum, in `(log2 f, dB)`, and taking its vertex. **Zero extra simulations** —
the curve is already dumped. `dec` was **not** raised.

* the 57 ties became **57 distinct rewards**, 29 above the old ceiling
* validated against a `dec 500` sweep: the vertex is **172× closer** to the
  truth, worse on **0 of 14** designs
* **63 designs in 8000 change feasibility** (39 gain, 24 lose) — this is a
  change of *problem*, not only of resolution
* opt-in everywhere; `V1_SPECS`, the tolerances, the box and every seed untouched

### 3.2 The G3 sweep ran for the first time (`BASELINES.md` §12)

`baselines_run.jsonl` had contained **a header and nothing else**. 170 runs,
25 869 simulations, **42.1 minutes** — not the 12 hours §7a predicted, because
that estimate predated the library trims.

```
cmaes+screen 8.9974 > gp_bo 8.9955 > gp_bo+screen 8.9921 > uniform+screen 8.9860
> cmaes 8.9736 > lhs+screen 8.9661 > uniform 8.9532 > lhs 8.9419
> ppo+screen 8.9288 > ppo 8.9106
```

**20 of 45 P1 pairs separate.** `PREDICTIONS.md` entry 6's ordering, written
months earlier, is confirmed wherever the sample resolves it.

### 3.3 The lattice control, which is the most persuasive table in the repo

Same 170 runs, same seeds, one flag off:

| | lattice | interpolated |
|---|---|---|
| **separable P1 pairs (of 45)** | **0** | **20** |
| groups whose median is 8.950670 | **8 of 10** | 0 of 10 |
| distinct median values | 3 | 10 |
| groups with a **zero-width** CI | 6 | 0 |

The benchmark did not rank coarsely. **It resolved nothing at all.**

### 3.4 PPO was diagnosed three times; twice wrongly

* **"exploration collapsed"** — **measured false.** Entropy *rises*
  (9.942 → 9.956) against 9.9326 for an untrained 7-D Gaussian; `log_std` is
  unchanged; `ent_coef` is already 0.0.
* **"PPO gets one gradient update"** — **true.** 1.57 simulations per env step
  (a third of the budget is episode resets), so 150 sims buys ~96 steps, and at
  `rollout_steps=64` that is one update.
* Fixing it (`rollout_steps` 64 → 8, eleven updates) bought **+0.0106,
  not separable** — **24.8 % of the gap to *uniform random***. Monotone, real,
  and far too small to matter.
* **"the policy never started"** — **RETRACTED, measured** (entry 13, 10 seeds
  per arm). Entropy sits within **0.02** of an untrained 7-D Gaussian and
  `log_std` within **0.008** of its initialisation in both arms: the spread
  never narrows. But the mean action moves **0.167 → 0.389** going from 2 to 12
  updates — 2.33× the movement for 6× the updates. **The policy moves; the
  design does not improve.** The gradient is *uninformative*, not absent, which
  is the worse of the two readings: more updates move the policy further along
  a direction that is not up. Median anytime gain over the final third is
  **0.0 in both arms** — though per seed it is 7 of 10 and 6 of 9 at exactly
  zero with a minority making one late jump, which is a search finding things
  by luck rather than by policy.

### 3.5 Session 22h — grid search, built and run (`BASELINES.md` §13)

`METHODS` had no grid, so **G3 was not failing its grid clause; it could not be
evaluated on it.** `method_grid` is a centred full factorial sized to the budget
and then refined. 210 runs, 31 879 simulations.

```
cmaes+screen 8.9974 > gp_bo 8.9955 > gp_bo+screen 8.9921 > uniform+screen 8.9860
> cmaes 8.9736 > lhs+screen 8.9661 > uniform 8.9532 > lhs 8.9419
> ppo+screen 8.9288 > ppo 8.9106 > grid+screen 8.8886 > grid 8.8886
```

**34 of 66 P1 pairs separate.** Four things to carry forward:

* **The arithmetic is the finding.** `L**d` at d = 7 means 150 simulations buys
  `150 ** (1/7)` = **2.06 levels per axis**: L = 2 is 128 points and fits,
  L = 3 is 2 187 and is 14.6× the budget. **The grid loses on RESOLUTION, not
  adaptivity** — `uniform` and `lhs` are not adaptive either and both beat it —
  because the binding reward row is a *distance to a target* and a continuous
  sampler resolves each axis 150 ways.
* **`P1/grid`'s CI is exactly zero wide, and that is the METHOD.** 19 of 20
  seeds return the identical 8.888648. **A different zero from §3.3's**, where
  the *objective* could not resolve. So its 20 replicates are one lattice plus
  20 short random tails, and a "separable at n = 20" verdict involving it is
  arithmetically true and inferentially weak.
* **The pre-screen bought the grid RESOLUTION — 5.19× more simulated points on
  the 3-level lattice — and moved the median by +0.0000**, the smallest delta
  of the six methods. Eleven of twenty screened seeds finished on the *same*
  design as the unscreened arm. **The coarse lattice's best point is a wall.**
* **Grid is the FASTEST method in the study to a feasible design (median 1.0
  simulation, screened) and the only one that never reaches the reward
  ceiling** — 0 of 20, twice, across 6 000 simulations. *Feasible is not good.*

And the run reproduced **all twelve** pre-existing group medians at
**0.00e+00**, which is how **G96** was caught: the separable-pair count still
moved 20 → 22 of 45 because `analyse` shared one bootstrap RNG across groups in
pool-completion order. Fixed; the ten arms then give 20 of 45 exactly and §3.3's
control still gives 0 of 45.

---

## 4. **The thing you most need to know: G3 is failing, and the plan says stop**

`CLAUDEwa.md` §7 states G3's criterion and its fallback verbatim:

> **G3** | Sep 3 | RL beats random search **and** grid search at TT, with a plot
> | *Fallback if failed:* **Stop and debug the reward function. Do not proceed
> to corners.**

Measured: **PPO 8.9106 against uniform random 8.9532.** RL does not beat random
search at TT. Two consequences, and neither is an agent's call:

1. **The prescribed fallback has already been executed once, and it worked
   without fixing G3.** The reward function *did* have a defect — the lattice
   ceiling — it was found, fixed, and proved fixed by a control. RL still loses.
   The current diagnosis (§3.4) says a second reward-debugging pass will not
   change it either, because the problem is the sample budget, not the reward.
2. **"Do not proceed to corners" conflicts with G4 being mandatory and with
   spec S9.** Someone has to decide whether that rule still binds now that the
   reward defect it was aimed at has been found and removed.

**The gap that made G3 unscoreable is CLOSED (session 22h).** `METHODS` held
`uniform, lhs, cmaes, gp_bo, ppo` and no grid, so G3 was not failing its grid
clause — it could not be evaluated on it. `method_grid` is now built, tested
and run, and `BASELINES.md` §13 is the write-up. **The verdict on the full
criterion:**

* **RL vs random search: LOSES.** `ppo` 8.9106 against `uniform` 8.9532.
* **RL vs grid search: does not separably win.** `ppo` sits above `grid`
  8.8886 on the point estimate, but `ppo`'s interval [8.8100, 8.9302] contains
  the grid's entire (zero-width) interval, so §7h's own rule reports **not
  separable at this sample size**.

So **G3 fails on both clauses.** Building the arm made the gate answerable, not
passable — which is what its pre-registration (`PREDICTIONS.md` entry 14) said
it would do.

---

## 5. Decisions — made, and open

### Made (by the owner, this session)

| # | Decision | Consequence |
|---|---|---|
| 1 | Switch the benchmark to the interpolated peak | Done. Every flag still defaults OFF; the lattice path is what runs unless asked |
| 2 | Run the sweep | Done, plus the lattice control |
| 3 | Tune PPO's `rollout_steps` | Done. Null result, reported as one |

### Made by the agent, flagged, and reversible

| Decision | Where | Why | Reverse by |
|---|---|---|---|
| A refused interpolation scores the **lattice** value, not the invalid floor | `evaluator.scoring_meas` | The floor punches a hole in the reward landscape for a numerical reason; the same mistake `validate`'s G44 comment records. **Fired 2 times in 25 869 simulations** | one argument |
| A **bottom**-edge peak carries the lattice pair forward; a **top**-edge one is refused | `evaluator.evaluate` | 10 MHz is both a grid point and the boundary, so nothing was rounded. Mirrors the asymmetry `peak_is_sweep_edge` already makes | one branch |

### **OPEN — human only. Do not decide these.**

1. **Does G3's "do not proceed to corners" rule still bind?** (§4)
2. **Should the benchmark's published baselines move onto the interpolated
   path permanently?** It changes 63 of 8000 S3 verdicts; `BASELINES.md` §7f
   makes it a re-run event.
3. **The two PPO environment-contract changes** (`PEAK_INTERP.md` §7,
   `PREDICTIONS.md` entry 12's closing section):
   * `reset()` spends a simulation per episode — a third of PPO's budget
   * `terminated = bool(rb.feasible)` ends the episode at first feasibility, so
     the policy is trained to *reach* the band while the benchmark scores how
     far *past* it you get
4. **`PLAN.md` §8 lists the spec-conditioned policy as the FIRST thing to cut.**
   That ordering was written before PPO was known to lose head-to-head. If it
   stands and time gets tight, the submission ships with no answer to *"why not
   just use CMA-ES?"*
5. Whether to re-run the corner and load screens on the interpolated peak
   (interacts with G66's own re-run scope — cost them together).
6. **NEW (22h): restore P2?** `SEC_PER_SIM_AT_8` was **17.4× wrong** — 1.698
   from a pre-library-trim pilot against the sweeps' own end-to-end 0.09773 and
   0.11095 s/sim. Fixing it means the **fully crossed** design (3 rungs × 6
   methods × 2 screen arms, 81 000 sims) costs **~2.2 h**, so **P2's cut, which
   was purely budgetary, no longer has a reason.** The other two cuts stand on
   reasons that were never about cost: P3's screened arm is EPISTEMIC (the
   screen's calibration off nominal is unmeasured, so the arm would confound
   "the screen helps" with "the screen is miscalibrated"), and P3's PPO arm is
   STRUCTURAL. Restoring P2 changes what the benchmark measures, so it is not
   an agent's call.
7. **NEW (22i): the repository is getting large, and part of it was my
   mistake.** `.git` was 98 MB before 22h and now carries an accidental 79 MB
   blob (commit `3ee4ea1`, a results JSON that duplicated its own run log —
   fixed forward, but the blob is in history) plus 32 MB of ladder log.
   Removing the blob needs a history rewrite. **Owner's call**, and it is not
   urgent — the repo is private and nothing is broken.
8. **NEW (22h): pin the warm-up/control configuration?** 7g takes it from
   `jobs[0]`, i.e. the head of the shuffle, so **adding a method silently
   changed which configuration the timing control measures** — it became
   `P3/uniform`, whose 6-simulations-per-design short-circuiting is far noisier
   per simulation, and the 22h sweep came back `timing_void` (ratio 1.408).
   Pinning it to a P1 arm is a two-line change with a fairness argument on both
   sides.

---

## 6. What to do next — recommended order

**Both of the top two map directly onto `CLAUDEwa.md` §7's own two claimed
contributions**, which is the strongest argument for them.

| # | Task | Time | Why | Maps to |
|---|---|---|---|---|
| ~~1~~ | ~~**Build `method_grid` and re-run**~~ | **DONE, session 22h** | G3 is now scoreable on both clauses and fails both. `BASELINES.md` §13 | G3's literal criterion |
| **2** | **Task 3 — corners in the loop (G4)** | 2–3 d | Mandatory: spec S9, and `PLAN.md` "never cut". P3 is now known **hard, not empty** — `uniform` found 2 of 20 | contribution **#1**, "reward on worst-case corner, not nominal" |
| **3** | **Task 4 — spec-conditioned policy** | 5–7 d | The only answer to *"why not CMA-ES?"*, **and** the only regime where the policy gets enough experience to learn | contribution **#2**, "this is the live demo" |
| **4** | **Report + slides** | ~7 d | Mandatory. Run it *alongside* 2–3, not after | — |
| 5 | `FAIRNESS.md` (task 2 leftover) | ½ d | One table: every asymmetry, which way it cut, what was done. Cheap credibility | — |
| — | ~~PPO contract changes~~ | 1–2 d | Measured ceiling on that path is small. Only if 3 stalls | — |

~13 days of work in 27, of which **task 1 is done**. **Task 2 (corners, G4)
is now the top item.** The slack is deliberate; `CLAUDEwa.md` §7 says protect
it.

### Three results already banked for the report

1. **0 → 20 separable pairs** (§3.3). One flag, matched control.
2. **The ranking table** (§3.2), with pre-registered predictions scored.
3. **The pre-screen's true cost**: free in simulations, **1.34× in wall clock**
   for model-based methods (GP-BO model time 127.1 s → 207.9 s), because a
   screened proposal costs no simulation but still costs a full acquisition
   optimisation. First measurement of this anywhere in the project.
4. **(22h) The answer to "why not just sweep the parameter space?"** — which is
   the competition's own sentence. At a matched 150-simulation budget the sweep
   is the **worst of six methods**, it is the **only one that never reaches the
   reward ceiling** (0 of 20 seeds, twice, across 6 000 simulations), and it is
   the **fastest of all twelve arms to a first feasible design** (median **1.0
   simulation** with the pre-screen). *Feasible is not good*, and this is the
   cleanest demonstration of that in the project.
5. **(22h) The benchmark is bit-for-bit deterministic** — twelve group medians
   reproduced at **0.00e+00** across two independently ordered sweeps.
6. **(22i) The budget ladder** (`BASELINES.md` §14). *At a matched budget, from
   150 to 2400 simulations, our PPO agent is statistically indistinguishable
   from uniform random search at every budget tested, while CMA-ES is
   separably better at every budget tested.* One table, one control, 96 000
   simulations — and it settles the "it just needs more data" objection that a
   panel will certainly raise.

---

## 7. Commands

```bash
# environment
conda activate nebula          # ngspice 41; use ngspice_con.exe, NOT ngspice.exe (G20)
                               # NOTE: the TEST SUITE runs on the SYSTEM python
                               # (the conda env has no torch). ngspice is found
                               # by absolute path either way.

# tests — before and after ANY change. 1510 tests, ~4 min, from the repo root
python -m pytest tests nebula/tests -q -m "not slow"

# the benchmark
python -m nebula.experiments.baselines --budget            # allocation, no SPICE
python -m nebula.experiments.baselines --sweep --interp    # 25 500 sims, ~42 min
python -m nebula.experiments.baselines --sweep --tag lattice   # the control
python -m nebula.experiments.baselines --analyse <log.jsonl>   # works on a PARTIAL log

# task 1's three sub-experiments
python -m nebula.experiments.exp_peak_interp --funnel      # 300 sims, ~2 min
python -m nebula.experiments.exp_peak_interp --dense 30    # 60 sims, dec 50 vs dec 500
python -m nebula.experiments.exp_peak_interp --pools       # 8000 sims, ~33 min
python -m nebula.experiments.exp_peak_interp --analyse --plot

# PPO
python -m nebula.experiments.exp_ppo_updates --run         # 6000 sims, ~24 min
python -m nebula.experiments.exp_ppo_updates --instrument  # entropy/log_std/curve
```

**Measured rate: 0.24–0.27 s/simulation** serial on this machine, ~1.80× at 8
workers (G75's figure *on this workload*, not the 2.98× measured on the
simulator alone). A 25 500-simulation sweep is **42 minutes**, not 12 hours.

---

## 8. Traps — the four found this week, and the ones that bit

**New gotchas, all in `HANDOFF.md` §9:**

* **G92** — *two arithmetics over the same events are ONE measurement.* G89 was
  called "supported two independent ways"; both statistics came from the same 9
  and 16 counts. Doubling the events killed it. Same family as G71.
* **G93** — `wrdata` writes **8 significant figures** while `meas` works on the
  full-precision vector, so on a flat response the two disagree about which
  sample is the maximum — **by a whole grid step**. Fired once in 4543. Caught
  only because `run_point(ac_peak_interp=True)` cross-checks its argmax.
* **G94** — *a per-simulation rate measured at a fraction of the real budget is
  wrong in both directions.* Calibrating at 40 simulations and extrapolating to
  150 put PPO at 2.33× (real: 1.01×) and GP-BO at 1.54× (real: 2.43×). Fixed
  startup over-charges the margin; `O(n³)` under-charges it.
* **G95** — *rule 9 applies to FILESYSTEM PATHS.* `sweep()` defaulted its output
  to `baselines_results.json`, the same name `--prescreen` writes, and silently
  destroyed 1890 samples of pre-screen calibration. Both writers reported
  success. Recovered with `git checkout HEAD~1 --`.

* **G96** — *one shared bootstrap RNG made a headline number depend on the
  completion order of an unrelated arm.* Adding the `grid` arm reproduced all
  twelve medians at **0.00e+00** and still moved the separable-pair count
  **20 → 22 of 45**. Seed per unit of analysis, from a stable function of that
  unit's identity. Same family as G71, one level up: there the order
  contaminated the measurement, here it contaminated the *analysis of* it.

**Three mistakes made this week that are not gotchas but are instructive:**

* **A diagnostic that consumed the resource it measured.** The policy-movement
  probe called `env.reset()`, which *simulates* — so it spent budget from the
  run it was reporting on, and (being outside the `try`) its `BudgetExhausted`
  killed the experiment at job 11 of 20. **An instrument must not consume the
  resource under measurement.**
* **A single probe point is not a function comparison.** The same seed reads
  0.633 on one observation and 0.209 averaged over 32. A tanh can be saturated
  at one point and steep at another.
* **G97** — *`anytime_curve` CLAMPS rather than truncates*, so asking it for a
  short prefix of a long run folds every later trial into the last cell. It
  manufactured "34 of 40 curves mismatched, worst difference 9.18" out of data
  that actually agreed at 0.0.
* **G98** — *a ratio metric must be run against its own reference.* Entry 15's
  headline read 0.960 / 0.893 / 0.632 / 0.988 / **0.623×** when the control was
  measured against itself, where it must read 1.000×, because a median of
  monotone step functions has plateaus. Three of eleven predictions were
  written against the wrong line. **The only reason it was catchable is that
  the control was in the run.**
* **A prediction band that spans zero cannot test a directional claim.** Entry
  14 predicted "grid beats PPO, by 0.02" with a band of −0.06…+0.10. Grid lost
  by 0.0220 — inside the band, and the claim was wrong. Scored as a miss on the
  claim rather than a hit on the band.

**Standing traps that still bite:** G20 (`ngspice_con`, not `ngspice`), G26/G30
(ngspice reports failures as warnings and exits 0 — parse and assert), G29
(`.spiceinit` is read at parse time from the cwd), G31 (instance W/L are plain
numbers in **microns**), G36 (use the trimmed library), G44 (a peak at the sweep
edge is fictitious), G70 (one concurrent ngspice = 4.8× slower), G71 (the first
configuration pays the cold cache, whichever one it is).

---

## 9. Rules you must follow

1. **Update `HANDOFF.md` in the same commit as any change.** A change without a
   handoff update is incomplete.
2. **Run the suite before and after.** `python -m pytest tests nebula/tests -q
   -m "not slow"` — **1510 tests, ~4 min**. Report the count both times. Never
   commit with failures.
3. **Pre-register anything costing more than ~10 minutes.** Write the prediction
   *and its acceptance band* into `PREDICTIONS.md`, **commit it**, then run.
   Record misses as misses; nothing above an Outcome heading may be edited.
4. **Every gate gets a test that proves it can fail.** Break the input, watch it
   go red, restore it, and say in your report that you did.
5. **Never fabricate a number.** Unknown stays empty and fails loudly.
6. **ngspice's exit code is not a success signal.** Parse the output and assert.
7. **Do not modify without asking:** `common/params.py`, `rl/contract.py`,
   `rl/env.py`, `V1_SPECS`, the box, the tolerances, the pre-screen. (`env.py`
   *was* touched this session, additively and default-off, with the reason
   recorded — see §5.)
8. **You may not decide anything in §5's OPEN list.** State the options with the
   measured numbers behind each and ask.
9. Windows: no non-ASCII in `print()`; run pytest from the repo root.
10. Commit as `Jai Kaushik <jaikaushik-prog@users.noreply.github.com>` (G12).
    **The repo is PRIVATE and must stay private** (G1).

---

## 10. What is new on disk

| Path | What |
|---|---|
| `nebula/PEAK_INTERP.md` | task 1: the ceiling, removed and validated |
| `nebula/BASELINES.md` §12, §12.6 | the sweep and the lattice control |
| `nebula/experiments/exp_peak_interp.py` | funnel replay, `dec 500` validation, pool replay |
| `nebula/experiments/exp_ppo_updates.py` | `rollout_steps` arms + `--instrument` |
| `nebula/experiments/baselines_run_{interp,lattice}.jsonl.gz` | 25 869 trial rows each (56 MB raw; committed gzipped) |
| `nebula/experiments/baselines_results_{interp,lattice}.json` | per-run summaries + analysis |
| `nebula/experiments/ppo_updates_run.jsonl` | 40 PPO runs across four `rollout_steps` |
| `nebula/figures/peak_interp.png` | the three-panel task-1 figure |
| `device/sky130_runner.py` | `interpolate_peak_log_f`, `parabolic_vertex`, `MAX_SEARCH_BOT_HZ`, 3 new `Sky130Point` fields |
| `rl/evaluator.py` | `scoring_meas`, `INTERP_KEYS`, `meas_with_interpolated_peak`, `interp_was_refused` |
| `nebula/tests/test_peak_interp.py` | 28 tests |
| `PREDICTIONS.md` entries 9–14 | six pre-registrations, five scored |
| `experiments/baselines.py` | **(22h)** `method_grid`, `grid_levels`, `grid_level_of`, `group_seed` (G96), the measured throughput constants |
| `experiments/baselines_run_interp_grid.jsonl.gz` | **(22h)** the 210-run sweep with the grid arm |
| `nebula/BASELINES.md` §13 | **(22h)** the grid arm, seven subsections |

---

## 11. The one-paragraph version, if you read nothing else

The reward could not rank anything and now it can — proved by a matched control
that separates **0 of 45** pairs against **20 of 45**, a contrast that survived
being re-derived under G96's fix. The benchmark has now run twice and produced
an honest ranking of **twelve** arms in which **grid search comes last and our
RL comes second-last, both behind uniform random search** — so **G3 fails on
both of its clauses**, and after session 22h it can at last be *scored* on both,
because the grid baseline its criterion names did not exist until then. PPO's
failure has been diagnosed three times, twice wrongly, and the current reading
is that a 150-simulation budget is smaller than a policy-gradient method's
minimum viable sample size — so no hyperparameter fixes it. **The grid's failure
is different and sharper: at seven dimensions 150 simulations buys `150**(1/7)`
= 2.06 levels per parameter, and the reward pays for resolution, so even a
policy that provably does not learn out-resolves a factorial.** The same run
proved the benchmark **bit-for-bit deterministic** (twelve medians at 0.00e+00)
and, through that, caught **G96**. Session 22i then laddered the budget 16×
and answered the objection a panel will certainly raise: **more simulations
close PPO's deficit to random search and never take it past random search**,
while CMA-ES is separably better at every budget tested — *PPO is not broken,
it is a random search with extra steps*. The two things worth the remaining 27 days
are the two contributions `CLAUDEwa.md` §7 already claims: **corner-aware
evaluation** (mandatory anyway, and now the top item) and the **spec-conditioned
policy**, which is the only regime where the policy gets enough experience to
learn and the only answer to *"why not just use CMA-ES?"*.
