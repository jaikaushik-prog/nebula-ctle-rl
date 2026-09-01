# POSITIONING.md — what this work is positioned against, and what it measured differently

**Session 29, 2026-08-29.** Report-ready. No new simulations: every number is
cited to an artifact or a `PREDICTIONS.md` entry already in the repo.

**Why this document exists.** The project has never stated what it is being
compared *to*. The mentor-supplied `nebula_ctle_rl` package is in AutoCkt's
lineage (PPO, delta actions, spec-vector observation), and proposal 001's paper
positions itself explicitly against AutoCkt — so we are already inside a
conversation we have not joined. Three of the four external proposals evaluated in
session 29 turn out to bear on claims we have **already measured**; this collects
those into report prose.

---

## 1. AutoCkt — the thing we are actually positioned against

**AutoCkt** (Settaluri et al., DATE 2020 / arXiv:2001.01808) trains a policy over
~50 random target specs, each trajectory starting from the **centre of the design
space**, and at deployment serves an unseen target from the **closest learned
trajectory** — a warm start that needs far fewer subsequent iterations.

**`exp_hybrid` is structurally the same idea with one substitution: the learned
trajectory is replaced by a zero-simulation library lookup.** Propose a warm
start, accept it if the corner screen passes, else fall back to the full search.
And because both proposers were run on the same harness, we can report the
substitution as a controlled comparison rather than an assertion:

| Proposer | Accepted | Cost | Source |
|---|---|---|---|
| **Library lookup** (retrieval), k = 5 | **6 of 16** | **35.6 % fewer decks** than the 13 718-deck search | entry 32 |
| **Library lookup**, full sweep | mandated 45-corner coverage **7 → 8 of 16** | **25 % fewer simulations**; **1 284 decks per delivered compliant design against 1 960 — 34 % cheaper** | entry 40 |
| **SAC policy** (the learned warm start) | **1 of 16** | 1 600 decks over 5 arms | entry 36 |
| **SAC policy**, swing-aware retrain | **0–1 of 16** | — | entry 38 |

**The claim, stated as narrowly as the evidence allows:**

> On this problem, the **retrieval** warm start delivers the benefit AutoCkt
> claims — materially fewer simulations to a compliant design — and the
> **learned** warm start does not.

**And the mechanism is named, not hand-waved.** Two measured causes:

1. **The spec manifold is effectively 1-D — ON `V1_SPECS`** (`SCOPE_BOUNDARY.md`
   §3, corrected 2026-09-01). On a 1-D manifold a lookup table *is* the optimal
   policy, which is exactly what the amortisation result measured: a lookup
   serves 32 of 32 held-out targets.

   **The scope matters and was missing.** Decision D6 added `S3_peaking_match`,
   and `V6_SPECS` — which `exp_coverage` and `design.py --method auto` score —
   contains it, so **the delivered path's target axis is 2-D**. The 32-of-32
   amortisation was measured on `V1_SPECS` and **has never been re-measured on
   `V6_SPECS`**. So this remains the mechanism for every published benchmark
   number, and it is **not established** as the mechanism on the delivered
   path. Quote it with the spec set attached, or not at all.
2. **95 % of the policy's rejections are output-swing compression** (entry 36) —
   a quantity the reward it was trained on did not contain. When that blindness
   was fixed (entry 38), headroom nearly doubled and swing failures fell
   96 % → 28 %, but **accept rate did not move**: the failures migrated to
   `S3_peaking_match` / `S3_f_peak_match`. Fixing one blind spot exposed the next.

**Resolve the tension between the two papers, because a reader will ask.**
fRL-AD claims lower **variance** than AutoCkt; AutoCkt claims fewer
**simulations** than its own GA+ML baseline. **Neither is a claim about final
design quality.** Our headline metric — all-45-corner compliance coverage — *is*
a design-quality claim, and that is a deliberate difference in what is being
optimised for, not an accident of metric choice.

**Second-hand numbers not to quote without the primary paper:** ~10x fewer
iterations than the GA+ML baseline; 40 LVS-passing designs for a 2-stage OTA in
under 3 days on one CPU core. These reach us through a survey
(`003-bag-autockt-align-magical.md`) and must be checked against arXiv:2001.01808
before appearing in a deliverable.

## 2. Variance — the axis fRL-AD competes on, now measured here

fRL-AD's headline against AutoCkt is **variance reduction, not a better mean**.
That axis was unmeasured in this project until session 29. It now is
(`VARIANCE.md`), from existing logs, at zero simulation cost:

    P1, 150 simulations, spread of best_reward across seeds
      cmaes+screen   sd 0.0051        <- most consistent
      ppo+screen     sd 0.0584
      uniform        sd 0.1110        <- least consistent, 22x the best

    uniform     vs cmaes         6.78x  [ 4.29, 10.54]
    ppo+screen  vs cmaes+screen 11.51x  [ 4.31, 24.73]
    ppo+screen  vs uniform+screen 1.39x [ 0.48,  3.73]   <- NOT distinguishable

**So on the metric that this literature competes on, our RL arm is 4–11.5x more
variable than CMA-ES and statistically indistinguishable from screened random
search.** This extends the project's existing "indistinguishable from random
search" finding from the **mean** to the **spread** — a second, independent axis
producing the same answer. At 2 400 simulations CMA-ES becomes effectively
deterministic (sd 0.0001) and the gap *widens*.

It is also the direct answer to proposal 002's fourth adoption criterion
(consistency), which the same brief argues is what actually drives designer
adoption.

## 3. gm/ID — a measured negative, and a PDK finding worth more than the method

Any analog designer on the panel will ask why we did not use gm/ID, the standard
methodology, and it is the flagship mechanism of proposal 001's paper. **We built
it and measured it** (`GMID_MAP.md`, session 20: the table, the map
`common/design_space.py`, the validation `exp_gmid_validation.py`, 75 tests).

* **The motivating mechanism is falsified.** The hypothesis was that making `f_z`
  a coordinate would put the G44 sweep-edge region out of reach by construction.
  Measured: **38.07 % in device coordinates against 37.74 % in design
  coordinates.** Unchanged.
* **The residual benefit is real but small, and arrives by a different route than
  predicted:** 89.40 % of design-space proposals are rejected before any
  simulation, but because they are **not representable in the device box at all**
  (878 of 1341 = "no width in 20–100 µm carries this current at this inversion
  level"). Net effect: **1.90 → 1.64 simulations per valid design, 1.16x.**
* **The analytic peak predictor cannot serve as a pre-simulation filter as
  written:** TN = 0 — it never once correctly excluded a design — precision
  61.78 %; with the 20 GHz search-ceiling defect fixed, TN = 8, precision 65.10 %.
* **Two things worth keeping regardless:** `f_z` and `k` round-trip exactly
  through the geometry (algebraic, rel < 1e-9), and DC gain lands at a median
  **−0.20 dB** against SPICE. The bias solve is a measured table, not a fit.

**The finding that outlives the experiment, and it is a PDK result:**

> On SKY130 at fixed `nf`, **`I_D/W` varies 1.56x** across the `w_in` box, because
> `W/nf` sweeps the model bins. **Scaling current linearly in `W` — which is what
> the textbook gm/ID method does — is a 56 % width error** on a device that
> simulates perfectly happily.

That is why the 40 nm results in the literature do not transfer unexamined to this
PDK, and it is the most useful thing the experiment produced. **Report the
negative with the mechanism attached** — it converts the obvious question from an
opinion into a measurement.

**Why it was not adopted anyway:** `GMID_MAP.md` §0 states that doing so
invalidates every existing baseline comparison, which fires `BASELINES.md` §7f and
re-runs every published arm.

## 4. Scalarisation — a design choice two independent groups name as their weakness

Both fRL-AD (001 brief §5) and the Basso thesis (004 brief §3) name **weighted-sum
scalarisation** as their known limitation and multi-objective RL as future work.
Two unrelated groups, two unrelated domains, converging on the same admission.

**We did not use a weighted sum.** `reward_v1.py` is a **maximin** — the score is
the worst normalised margin — chosen so a satisfied spec cannot mask a failing
one, which is the exact failure mode a weighted sum permits.

**Claim only what is measured.** The honest paragraph is:

> Two independent groups name the scalarisation we did not choose as their known
> limitation. We chose a maximin instead, and we measured its own cost: it gives
> no credit for exceeding a met spec, so the objective goes flat. `S5_noise` binds
> **0.0 %** of the time and `S6_power` **0.6 %** across 33 214 feasible designs,
> and within 0.001 of the best score the population spans **8.4x in tail current**
> (G102) — the delivered operating point was drawn from a plateau, not chosen.

**Do not claim we avoided the limitation.** A maximin is a different
scalarisation with a different pathology, not a solution to multi-objective RL. A
plateau arguably gives an optimiser *less* to work with than a mis-weighted sum
does. The defensible position is a stated choice with a quantified cost on both
sides — and G102's own named fix (an added term, not a removed one) is on the task
list as a zero-simulation re-score of the 74 526 designs already on disk.

## 5. What none of this claims

* **Not that RL does not work for analog sizing.** The supportable statement is
  scoped: *RL confers no advantage over random search on a **1-D** spec manifold at
  d = 7, on this objective, at budgets from 150 to 2 400 simulations* — with the
  boundary stated (`SCOPE_BOUNDARY.md`) and the crossover named as unmeasured.
* **Not a comparison of final design quality with AutoCkt or fRL-AD.** We have not
  run their code on our problem or ours on theirs. §1's table compares two
  proposers **inside our own pipeline**, which is the only controlled comparison
  we own.
* **Nothing in §1–§4 is a coverage or compliance number.** Those are 8 of 16
  (entry 40) and 11 of 11 at 45 of 45, and are unaffected by anything here.
