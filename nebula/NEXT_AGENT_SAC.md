# NEXT_AGENT_SAC.md — the SAC + CMA-ES hybrid, and where to pick up

**Written 2026-08-21, end of session 23.** Read this after
`nebula/PROGRESS.md`. It is the implementation brief for one specific change;
`PROGRESS.md` is the state of everything else.

**Before you write any code, read §1 and §2.** §2 contains two design traps
that were found by measurement and that will otherwise cost you a day each.

---

## 0. Read in this order

| # | file | why |
|---|---|---|
| 1 | `nebula/PROGRESS.md` | project state, decisions, the honest numbers |
| 2 | **this file** | the architecture and the surgical steps |
| 3 | `HANDOFF.md` §9 gotchas **G100–G115** | every one cost real time; **G109–G115 are from session 23** |
| 4 | `nebula/PREDICTIONS.md` entries **24–29** | how claims are made here: pre-register, commit, then run |
| 5 | `CLAUDEwa.md` §§7, 8 | the contract and the standing rules |

---

## 1. Where things stand, in numbers you can quote

**The framework works. The RL does not — yet — and that is measured, not
assumed.**

| measurement | value | artifact |
|---|---|---|
| Best design vs the competition spec | **11 of 11 rows at 45 of 45 mandated PVT corners** | `joint_verify_full_results.json` |
| Spec coverage, 16 held-out requests | **6 of 16** (first trustworthy number) | `coverage_results_BEFORE_seeding_fix.json` |
| CMA-ES, 16 held-out requests | **14 of 16**, 800 sims each | `corner_rl_results.json` |
| Library lookup | **9 of 16**, 4 sims each | same |
| Random search | 5 of 16, 800 sims each | same |
| **PPO, untrained, from scratch** | **0 of 16**, 8.1 sims each | `corner_rl_results.json` |
| **PPO, after 200k analytic steps** | **1 of 16**, 16.7 sims each | `rl_pretrain_results.json` |
| PPO, after SPICE fine-tuning | **0 of 16** — fine-tuning **erased** it (G114) | same |
| PPO refining a retrieved design | 11 of 16 vs 9 — **but p = 0.50, n = 16** | `rl_refine_results.json` |

**Those three PPO rows are three different policies and must not be merged.**
The best RL has ever done unaided is **1 of 16**, by the pre-trained policy
before fine-tuning destroyed it. Quoting "1 of 16" against
`corner_rl_results.json` is wrong — that artifact says 0.

**The coverage pipeline contains NO reinforcement learning.** It is
`library seed -> analytic pre-scan -> probe -> CMA-ES -> 135-point verify`.
Anyone reading `exp_coverage.py` will find `method_cmaes` in ninety seconds.
Do not describe it as RL.

### Why PPO failed, diagnosed rather than assumed

`log_std` is PPO's exploration parameter: it starts at 0.0 and **shrinks** as a
policy grows confident.

    1 200 SPICE steps        -0.05 .. +0.053   sigma 1.000   <- never trained
    200 000 analytic steps   -3.022 .. -0.719  sigma 0.199   <- trained hard
    then 3 000 SPICE steps   -0.097 .. +0.063  sigma 0.988   <- ERASED (G114)

One SPICE step = 4 decks = **1.26 s**, so the ~120 000 steps PPO needs is
**42 hours**. Budget was the blocker. Removing it was necessary and **not
sufficient**: the trained policy reached only 1 of 16 against the library's 9.

---

## 2. TWO TRAPS, BOTH MEASURED. READ BEFORE DESIGNING

### Trap 1 — **PPO cannot use the 74 526 designs on disk. That is the whole point of switching.**

PPO is **on-policy**: it uses each sample once and discards it. Every one of
the ~12 800 simulations CMA-ES spends per 16-request sweep is thrown away, and
the 74 526 already-simulated designs in `spec_pool` are unusable to it.

**SAC is off-policy.** It keeps a replay buffer and learns from data it did not
generate. That is the structural reason to switch, and it is worth more than
any hyper-parameter.

### Trap 2 — **CMA-ES samples are NOT valid MDP transitions. Measured.**

The obvious hybrid is "feed CMA-ES's evaluations into SAC's buffer". It does
not work naively:

    CMA-ES sigma0        0.30   (how far apart its samples land)
    contract.MAX_STEP    0.15   (how far ONE policy edit can move)
    -> CMA-ES pairs are ~2x further apart than one action can reach

A transition `(s, a, r, s')` is only valid if `s' = clip(s + MAX_STEP * a)` for
some `a` in `[-1, 1]^7`. **Most consecutive CMA-ES samples violate that**, and
inserting them anyway teaches the critic that impossible moves are available.

**Three ways out, in order of preference:**

1. **Filter.** Keep only pairs with `||u2 - u1||_inf <= MAX_STEP`. Honest,
   trivial, and throws away most of the data.
2. **Behaviour-clone instead.** Use CMA-ES's *winners* as supervised targets
   (`spec -> u`), not as transitions. No MDP validity needed.
3. **Raise `MAX_STEP` for the SAC variant.** A wrapper-level override (rule 7 —
   do NOT edit `contract.py`), which makes more pairs valid at the cost of a
   coarser policy.

### Trap 3 — the framing critique a judge will make, so decide your answer now

**Is this actually an MDP, or a contextual bandit?** The "state" is a design we
chose; the reward depends only on the final design and the request. If you
collapse the horizon to 1 — *given a spec, emit a design* — it is a **bandit**,
and "learn Q(spec, design), then argmax" is functionally a **surrogate model
plus an optimiser**, which is what `prescreen.py` and Bayesian optimisation
already are. The RL label gets thin.

**Recommended answer:** keep the sequential refinement MDP (horizon 8). Refining
a design over several measured steps genuinely is a sequential decision problem,
SAC handles it natively, and the framing survives scrutiny. **But write the
bandit critique into the report yourself** rather than letting a judge raise it.

---

## 3. The architecture

```
        request arrives
              |
              v
      +----------------+
      |   SAC policy   |   proposes a design, ~0 SPICE
      +--------+-------+
               v
        verify at the 4-corner screen        4 SPICE
          |                 |
       passes             fails
          |                 |
          v                 v
        done         CMA-ES searches         800 SPICE
                            |
                            v
      +--------------------------------------------+
      |  every evaluation from EITHER path goes     |
      |  into SAC's replay buffer (filtered, T2)    |
      +--------------------------------------------+
                            ^
              74 526 existing designs, day one
```

**CMA-ES is the teacher; SAC is the student. The student gets faster; the
teacher guarantees the answer.**

### The property that makes this safe

**Coverage cannot get worse.** If the policy's proposal fails verification,
CMA-ES runs exactly as it does today. The RL can only remove simulations, never
add failures. After a day that produced nine defects, a change with no downside
risk on the headline number is worth a great deal.

### What it claims, and how it is measured

Not "RL beats CMA-ES". The claim is an **amortisation curve**:

    requests 1-10     policy rarely right     ~800 sims/request
    requests 20-50    policy often right      ~200 sims/request
    requests 100+     policy usually right    ~50 sims/request

Plot simulations-per-request against request index. **That curve is the
deliverable's "fewer search spaces, lowest design time" answered directly**, and
it is a claim RL genuinely owns.

---

## 4. Surgical steps

**Each stage is independently useful. Stop after any of them and the project is
better than it was.** Do not build stage 2 before stage 1 is measured.

### Stage 0 — the fallback wrapper (~1 h). Do this first, it needs no SAC

**New file: `nebula/experiments/exp_hybrid.py`**

* `propose_then_search(target, policy, budget)`:
  1. policy proposes `u` (or the library does, if no policy exists yet);
  2. `evaluate_at_points(u, EDGE4_MANDATED, specs=V6_SPECS)` — 4 decks;
  3. if feasible: return it, record `n_sims = 4`;
  4. else: run today's CMA-ES path, record its cost.
* Record per request: `proposal_accepted`, `n_sims`, `which_path`.
* **Run it with the LIBRARY as the proposer.** That is a real measurement today
  and it is the control the SAC version must beat.

**Why first:** it builds the measurement harness and the no-downside guarantee
before any new learning code exists. If SAC never works, this still produces the
amortisation curve with the library as proposer.

**Gate:** a test that the fallback fires when the proposal is infeasible, and
that reported `n_sims` is the sum of both paths.

### Stage 1 — SAC replacing PPO (~4 h)

**New file: `nebula/rl/sac.py`**, alongside `rl/ppo.py`. **Do not modify
`ppo.py`** — every published RL number came from it.

Minimum viable, all standard:
* twin Q critics + target networks, `tau = 0.005`;
* Gaussian policy with `tanh` squashing (matches `contract.build_observation`'s
  action convention);
* automatic entropy tuning, target entropy `-dim(A) = -7`;
* replay buffer, `batch = 256`, one gradient step per environment step.

**Reuse, do not rebuild:**
* the env: `exp_corner_rl.SpecConditionedCornerEnv` (already spec-conditioned,
  already corner-aware, already a wrapper — rule 7 precedent);
* **the episode-termination fix**: `rl/analytic_env.py` reverts a bad edit
  instead of ending the episode. The SPICE env still TERMINATES (G114 trap 3);
  do the same revert in the SAC wrapper or the policy gets 1–3 of its 8 moves,
  which is exactly what crippled PPO;
* the evaluator: `exp_corner_rl._score` — **every arm must go through it**
  (`BASELINES.md` §7d).

**Pre-train on `rl/analytic_env.py` first.** 200 000 steps, ~17 min, zero SPICE,
measured to move `log_std` properly. Then fine-tune on SPICE — **and read
G114 before you do**: the last attempt erased the policy because three things
changed at once (fresh optimiser, different reward scale, different episode
dynamics). Change them one at a time and measure `log_std` after each.

**Add Hindsight Experience Replay.** It fits this problem unusually well: the
reward depends on the requested spec, and **any measured design can be re-scored
against any target for free** (`spec_pool.score_pool`). So every failed
trajectory can be relabelled with the target it *did* achieve and becomes a
success. This is the single highest-value addition after off-policy itself.

**Gate:** `log_std` (or SAC's entropy coefficient) must move. If it does not,
stop — the problem is not the algorithm, and say so.

### Stage 2 — feed the teacher's data to the student (~2 h)

Only after stage 1 is measured.

* Filter CMA-ES pairs by trap 2's validity rule before inserting them.
* Log how many survive. **If almost none do, say so and switch to behaviour
  cloning on CMA-ES winners** rather than forcing it.
* Seed the buffer from `spec_pool` via HER relabelling at startup.

### Stage 3 — the amortisation curve

Run 50–100 requests through `exp_hybrid` with the SAC proposer, plot
simulations-per-request against index, and compare against the library-proposer
control from stage 0. **That plot is the headline figure.**

---

## 5. Rules you must follow

These are not stylistic. Each was written after a specific failure.

1. **Update `HANDOFF.md` and `nebula/PROGRESS.md` in the same commit as any
   change.** A change without a handoff update is incomplete.
2. **Run the suite before and after.** `python -m pytest tests nebula/tests -q
   -m "not slow"` — **1670 tests, ~4 min**. Report both counts. Never commit red.
3. **Pre-register in `PREDICTIONS.md` BEFORE the run**, with bands and
   falsifiers, committed. **Entry 25 was written a minute late and entry 26 not
   at all; both say so in their first paragraph.** Do not repeat that.
4. **Every new gate is deliberately broken, watched go red, and restored.**
5. **Never fabricate a number.** A missing artifact raises; it never gets a
   placeholder.
6. **Do not modify without a human decision:** `common/params.py`,
   `rl/contract.py`, `rl/env.py`, `rl/ppo.py`, `V1_SPECS`, the box, the
   tolerances. **Wrap, do not replace** — `corner_env.py`, `analytic_env.py` and
   `SpecConditionedCornerEnv` are the precedents.
7. **New spec sets are new tuples by ENUMERATION**, never by exclusion (G101),
   never by addition without re-checking every inherited member (G106).
8. **One experiment at a time.** `experiments/runlock.py` enforces it; a
   finished run silently overwrote a finished run's artifact on 2026-08-21
   (G113) and the loss was invisible until a figure disagreed with the prose.
9. **ngspice's exit code is not a success signal.** Parse and assert (G26/G30).
   `ngspice_con.exe`, not `ngspice.exe` (G20). Run netlists from
   `nebula/device/spice/` (G29). Instance W/L are plain microns (G31).
10. Windows: no non-ASCII in `print()`. Run pytest from the repo root.
11. Commit as `Jai Kaushik <jaikaushik-prog@users.noreply.github.com>` (G12).
    **The repo is PRIVATE and stays private** (G1).

---

## 6. The five failure shapes session 23 kept hitting

Nine defects in one day, six in code written that day. **They were nearly all
one of these.** Check your work against them before running anything expensive.

1. **A set built by FILTERING loses members silently.**
   `[k for k in CONTRACT if k in available]` is a contract violation with no
   error. It hid a missing frequency constraint that verified a **10.818 GHz**
   peak — 4.3x outside spec — at **45 of 45 corners** (G115). Three separate
   instances in one day (G101, G106, G115). **Assert completeness; never
   filter.**
2. **A wrong value that FORMATS CLEANLY beats one that crashes.** A typo printed
   `None SPICE calls` for a whole training run without failing — and that value
   was the denominator of the break-even ratio (G112).
3. **A shortcut graded against the wrong reference manufactures failures and
   then "corrects" them, unboundedly.** The screen self-check was audited
   against a grid it does not cover; it "missed" 4 of 5 times and grew 4 -> 8
   points, inflating every later request (G110).
4. **"Cannot be measured" is not "fails."** Collapsing them either kills a
   search or fakes a pass (G107). It also put all four benchmark arms at the
   invalid floor and made them look tied.
5. **Read the delivered VALUES, not just the verdicts.** Every one of these
   produced a normal-looking pass column. The 10.818 GHz peak was caught because
   a *rendered figure* disagreed with the prose — not because any check fired.
   **Render the figure before quoting the number.**

---

## 7. What NOT to do

* **Do not call the coverage results RL.** They are CMA-ES. See §1.
* **Do not quote the refiner's 11/16 as a win.** n = 16, p = 0.50. Say both
  numbers or neither.
* **Do not quote the break-even figure** from `corner_rl_results.json`. It
  amortises the training cost of a policy that solved nothing.
* **Do not chase PPO's fine-tuning collapse** (G114). Three mechanisms are
  uncontrolled; separating them is three experiments for a path already
  measured as not competitive. SAC supersedes it.
* **Do not delete** the quarantined artifacts, the failed predictions, or any
  retraction. **The misses are the asset.**
* **Do not tune the tolerances to make coverage look better.** They are derived
  from measured PVT excursions (`S3_f_peak_match` 0.30 oct from a 0.23–0.30
  measured spread; `S3_peaking_match` 1.5 dB from 1.48–1.65 dB). Loosening them
  is the same defect as G111, deliberately.

---

## 8. Open decisions — human only

1. ~~**Does the rubric require RL to be the optimiser?**~~ **ANSWERED
   2026-08-26 — stages 1-3 are UNBLOCKED.** The competition mentor approved this
   architecture *conditionally*: the SAC + CMA-ES hybrid is acceptable **if the
   SAC contributes as RL**.
   **Read the condition as the deliverable, not as a formality.** It does not
   approve a hybrid in which the policy is decoration and CMA-ES does the work
   — which is precisely what today's numbers describe. The measurement that
   discharges it is `exp_hybrid`'s **accept rate**: how often the policy's
   proposal passes the 4-corner screen, against the **non-RL baseline of 6 of 16
   accepted and 35.6 % fewer decks** (`PREDICTIONS.md` entry 32). A SAC proposer
   that does not beat that has **not** contributed as RL, and reporting that is
   the honest outcome rather than a failure to be papered over.
2. **Which design ships**, if more than one is compliant.
3. **Whether to report the 135-point load-swept grid as compliance or as
   characterisation.** The slide mandates 45 PVT corners; the load axis is this
   project's own (G109). Current decision: **compliance = 45 corners,
   characterisation = 135 points, both shown, neither merged.**

---

## 9. The one-paragraph version

**The framework works and the RL does not, and both are measured.** A design
passes all 11 competition spec rows at 45 of 45 mandated PVT corners; the
framework answers 6 of 16 held-out spec requests end to end; and PPO, benchmarked
honestly against CMA-ES, a library lookup and random search on the same 16
requests through one shared evaluator, came last at 0 of 16 from scratch and
1 of 16 at its best (pre-trained, before fine-tuning erased it). The diagnosis is
not "RL is unsuitable" — it is that **PPO is on-policy and therefore cannot use
the 74 526 simulations this project has already paid for**, while one training
step costs 1.26 s of SPICE. **SAC can use them.** Build the fallback wrapper
first so coverage cannot regress, then SAC with hindsight relabelling, then feed
it CMA-ES's discarded evaluations — and check every CMA-ES pair against
`MAX_STEP` before inserting it, because they land twice as far apart as one
action can reach.
