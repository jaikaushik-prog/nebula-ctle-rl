# SPEC_CONDITIONED.md — the amortised claim, and what a table lookup does to it

**Session 22j, 2026-08-20.** Written while building `CLAUDEwa.md` §7's second
claimed contribution — *"`TargetSpec` enters the observation. Train across a
distribution of specs; evaluate on held-out specs never seen in training. This
is the live demo."*

**No policy was trained.** Two measurements made before training changed what
training would be worth, and both are reported here. Pre-registration and
scoring: `PREDICTIONS.md` entry 16.

---

## 0. The two findings, up front

> **SCOPE CORRECTION, 2026-09-01 (session 31). Every measurement in this file
> is on `V1_SPECS` and is correct there. Finding 1's *reason* is not.**
> `margins()` does emit `S3_peaking_match` when a request is passed; what
> decides whether it is scored is the spec set. `V1_SPECS` has no such row —
> hence everything below. **`V5`/`V6_SPECS` do**, and `V6_SPECS` is what
> `exp_coverage` and `design.py --method auto` score, so **on the delivered
> path the problem is 2-D**. Nothing here is retracted; it is scoped. What is
> **open** is whether finding 2 — a 600-design library answering every
> held-out spec — survives on `V6_SPECS`. It has not been re-measured.
> See `SCOPE_BOUNDARY.md` §3 and `POSITIONING.md` §1.

**1. The spec-conditioned problem is ONE-dimensional, not two — on
`V1_SPECS`.** That set carries no `S3_peaking_match` row, because S3's peaking
constraint is a **band** (3–12 dB) and `CLAUDEwa.md` §3 reads the band as the
requirement. Measured:
one fixed design scores **8.999984 against targets of 3, 5, 7.5, 10 and 12 dB,
identically**, while the same design moves `8.000 → 8.996 → −0.000` across a
sweep of `target_f_peak_hz`. The observation's target block has two channels
and **one of them can never change any reward.**

**2. A library of designs we have already simulated answers every held-out
spec, for free — and it does not need to be large.**

| uniform-random designs in the library | held-out targets served | median best reward |
|---|---|---|
| 10 | 77 % | 8.5193 |
| 20 | 96 % | 8.7385 |
| **50** | **100 %** | 8.8576 |
| 100 | 100 % | 8.9305 |
| 300 | 100 % | 8.9757 |
| **600** | 100 % | **8.9899** |
| 3 000 | 100 % | 8.9970 |
| 24 480 | 100 % | **8.9997** |

**Fifty random simulations answer every spec in S3. Six hundred answer them at
8.99 out of a 9.0 ceiling.** Zero simulations per query thereafter.

---

## 1. Why a measurement can be re-scored for free

`evaluator.evaluate` returns a measurement — `peaking_db`, `f_peak_oct`,
`inoise_vrms`, `power_w`, the saturation margins. `reward_v1.reward` then
scores that measurement **against a target**. The target enters only at the
scoring step.

**So a measurement does not know what it was aiming at.** Every trial row this
project has logged can be re-scored against any target, exactly, for no
simulations at all. `experiments/spec_pool.py` does that.

| | |
|---|---|
| logs read | `baselines_run_interp_grid.jsonl.gz`, `budget_ladder_run.jsonl.gz` |
| trial rows | 146 597 |
| **distinct valid P1 designs** | **74 526** |
| by proposer | cmaes 25 044 · uniform 24 480 · ppo 19 010 · lhs 2 799 · gp_bo 2 568 · grid 625 |
| dropped | 60 495 invalid · 10 176 duplicate designs · 1 400 P3 rows |

**P3 rows are excluded by construction.** `Trial.meas` is the *nominal*
measurement, which on P1 is tt/1.00/27 °C/cl_mid; on P3 the first evaluated
point is a corner, so the same field means something else. One name, two
meanings, is rule 9 in the data.

**All claims about library size use the `uniform` sub-pool only** — 24 480
designs. CMA-ES and PPO rows were steered toward the legacy target and are a
biased sample of the box; a claim of the form *"N simulations buy a library"*
made on them would be a claim about the optimiser.

---

## 2. What the library already serves

`spec_dist.py` draws targets from S3's own band — uniform in dB, uniform in
**octaves** in frequency, because S3's window is exactly one octave — and
provides the two splits the owner asked for: **interpolation** (random targets
held out) and **extrapolation** (train on the low half of the peaking band,
test on the high half).

Against the full 74 526-design pool, **32 of 32 held-out targets — 16
interpolation, 16 extrapolation — are served by a feasible design at a median
best reward of 9.0000**, against a practical ceiling of 9.0.

**The extrapolation split is not harder**, and that is expected rather than
surprising: a lookup has no notion of train and test, so the two target sets
differ only by where they were drawn from.

---

## 3. The scaling law

Distance to the ceiling against library size, on the uniform sub-pool:

| N | gap to 9.0 | **N × gap** |
|---|---|---|
| 30 | 0.24893 | 7.47 |
| 100 | 0.06332 | 6.33 |
| 300 | 0.02544 | 7.63 |
| 1 000 | 0.00641 | 6.41 |
| 3 000 | 0.00272 | 8.17 |
| 10 000 | 0.00092 | 9.24 |
| 24 480 | 0.00032 | 7.85 |

> **gap ≈ 7.6 / N**, constant to ±20 % across three orders of magnitude.

**To halve the distance from the optimum, double the library.** The library's
quality is entirely predictable, which is more than can be said for any search
method in this project.

---

## 4. The crossover — the number that matters

A library costs `N` simulations **once** and nothing per query. CMA-ES costs
its full budget **per spec, forever**, because it has no memory.

From `BASELINES.md` §14, CMA-ES's median best reward is **8.9736 at 150
simulations** and **8.9999 at 2400**. Inverting the scaling law:

| to match | library needs | crossover |
|---|---|---|
| CMA-ES at 150 sims/spec (8.9736) | **≈ 290 designs** | **≈ 2 specs** |
| CMA-ES at 2400 sims/spec (8.9999) | ≈ 76 000 designs | ≈ 32 specs |

**After two different spec requests, a library of 300 random simulations has
already paid for itself and gives better answers than CMA-ES does for 150
simulations every single time.**

---

## 5. What this does to the claimed contribution

`CLAUDEwa.md` §7's second contribution is a policy that answers a new spec
without re-optimising. **The opponent everyone reaches for is CMA-ES starting
fresh, and that is the wrong opponent** — a policy beats it trivially, because
CMA-ES has no memory and the policy does.

The honest opponent is the cheapest thing that *also* has memory: keep every
design you ever simulated and look one up. No model, no training, no
simulation. **A panel of practising designers will think of it immediately —
several of them keep exactly such a database.**

So a spec-conditioned policy here would have to beat **zero simulations at
8.99**, on a target space that is two-dimensional with one dimension inert, and
that ~600 random simulations already cover. **That is not a contribution.**

### Where a library provably cannot answer

**Corners.** The pool is P1 only — one process corner, one supply, one
temperature, one load. Nothing in this document says anything about S9, and
`Trial.meas` on a corner row means something different, so the exclusion is
structural rather than a gap that more data would fill.

A corner-robust answer needs the worst case over 3 corners × 2 loads, and the
library holds nominal measurements for its designs and nothing else. **The
place a lookup provably has nothing to say is exactly where gate G4 lives.**

---

## 6. What this does NOT show

* **Not that RL is worthless.** It shows this *target space* is too small for
  amortisation to be interesting: two dimensions, one inert, densely covered by
  designs already on hand.
* **Not that the library is a finished design method.** It returns a nominal
  design. Whether that design survives PVT is unmeasured and is G4's question.
* **Not a re-score of any gate.** G3 is a comparison of search methods at a
  fixed budget on a fixed target; nothing here touches it.
* **Not an argument to change the reward.** Making `target_peaking_db` live
  would make the problem 2-D and might make amortisation interesting again —
  and it would also move **every published reward number** and is a
  `BASELINES.md` §7f re-run event. That is a human decision, recorded in
  `CONTINUE_HERE.md` §5, not an agent's.

---

## 7. Files

| path | what |
|---|---|
| `nebula/rl/spec_dist.py` | the target distribution (S3's band, not a choice) and the two splits |
| `nebula/experiments/spec_pool.py` | the pool, `lookup_best`, `nearest_in_spec_space`, `coverage` |
| `nebula/tests/test_spec_conditioned.py` | 16 tests, four of them rule-10 gates |
| `nebula/PREDICTIONS.md` entry 16 | pre-registration and scoring |
