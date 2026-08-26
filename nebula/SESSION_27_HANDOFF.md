# SESSION_27_HANDOFF.md — pick up here

> **STATUS 2026-08-26 (session 28): §3's "YOUR IMMEDIATE JOB" IS DONE. DO NOT
> RE-RUN IT.** `exp_sac_finetune.py` ran at full budget in **53.1 min** and
> entry 35 scored **3 of 5**: `log_std` **-1.7788 -> -2.0902**, `alpha` flat at
> 0.075, SPICE mean return **-24.101 -> -19.012** on 465 decks against 470.
> **Q1, Q2, Q3 HIT; Q4 (normalised critic, 2.393x vs a 2.0x bar) and Q5 (53.1
> min, under the 80-120 band) MISSED.** `_verdict()` printed §7's first branch:
> **the transfer works, G114 is solved not avoided, proceed to stage 3.**
> Artifacts: `experiments/sac_finetune_results.json`,
> `sac_finetune_run.jsonl`, `sac_policy_analytic.pt`,
> `sac_policy_finetuned.pt` (both verified to hold real weights). The rest of
> this file — §4's four design decisions, §6's quotable/unquotable lists, §8's
> standing rules, §9's five failure shapes — **still stands and is still the
> best short brief in the repo.** Current entry point: `PROGRESS.md` §5i and
> `CONTINUE_HERE.md`'s session-28 block.

**Written 2026-08-26, end of session 27, for a fresh chat.** The previous chat
hit its context limit mid-experiment. This file is written *now*, while the
state is exact, so you can continue **without re-deriving anything and without
guessing**. Every claim is checkable against the repo — do not trust this file
over the repo.

---

## 0. The one-paragraph version

**The mentor answered, and it unblocked everything.** He approved the SAC +
CMA-ES hybrid **conditionally**: *fine enough **if the SAC contributes as RL***
(decision **D9**). That closed `NEXT_AGENT_SAC.md` §8 item 1 and unblocked
stages 1–3. Since then: **`sac.py` ran for the first time and its stage-1 gate
PASSED** — `alpha` moved 14×, `log_std` went −0.007 → −1.779 (sigma 0.993 →
0.169), where PPO's equivalent parameter never left its initialisation
(`PREDICTIONS.md` entry 34). The next experiment,
**`experiments/exp_sac_finetune.py`, is written, committed, smoke-tested, and
NOT RUN at full budget.** It asks the one question that killed PPO: *does the
policy survive the SPICE transfer?* It is pre-registered as **entry 35**.
**Your immediate job: run it (~90 min), score it against entry 35, and follow
its committed decision rule.**

---

## 1. Read in this order

| # | file | why |
|---|---|---|
| 1 | `nebula/PROGRESS.md` | project state and the D1–D9 decision table |
| 2 | **this file** | exactly where session 27 stopped |
| 3 | `nebula/NEXT_AGENT_SAC.md` | the brief being executed — §2 traps, §4 stages, §5 rules, §7 what NOT to do |
| 4 | `nebula/PREDICTIONS.md` entries **34** (OUTCOME) and **35** (registered, not run) | the last measurement and the next one |
| 5 | `HANDOFF.md` §9 gotchas **G100–G115** | **G112, G113, G114 are load-bearing for this work** |

---

## 2. Exact git state

```
HEAD  41a9875  nebula: exp_sac_finetune -- the G114-controlled transfer experiment
      d5e90cd  nebula: pre-register entry 35
      ab14d45  nebula: the SAC gate PASSED -- 3 of 5
```

**Working tree clean. No run locks held. Nothing running.**
Suite: **1915 passed, 12 deselected, ~4m50s** (`python -m pytest tests
nebula/tests -q -m "not slow"`, system Python — the conda env has no `torch`).

---

## 3. YOUR IMMEDIATE JOB

```bash
python -m nebula.experiments.exp_sac_finetune --run      # ~90 min, unattended
python -m nebula.experiments.exp_sac_finetune --analyse  # re-read the artifact
```

It is **pre-registered as entry 35** and its `_verdict()` applies entry 35's
decision rule **mechanically**, so the call cannot drift in the writing. Do not
change thresholds, budgets or the reward set before running it — that is
tuning an experiment to fit its own prediction, and entry 34's outcome records
one place that was deliberately *not* done.

**When it finishes:** append an `### OUTCOME` block to entry 35 scoring all
five predictions honestly (misses recorded as misses), commit, then follow the
branch `_verdict()` printed.

---

## 4. What `exp_sac_finetune.py` does, and the four decisions inside it

It exists to answer **G114**, this project's sharpest negative: 3 000 SPICE
steps returned a PPO policy trained for 200 000 analytic steps to its
initialisation (`log_std −3.022..−0.719` → `−0.097..+0.063`), taking
feasibility 1/16 → 0/16 with it.

G114 named three uncontrolled changes and said *"change them one at a time"*.
**All three are held, and the third is removed rather than measured:**

| lever | how it is held | do not undo |
|---|---|---|
| **optimiser** | `sac_train(..., agent=agent)` keeps the agent **and its three optimisers**; `lr_finetune = 3e-5` lowers the rate instead of resetting it | passing a fresh agent reintroduces G114 lever 1 |
| **reward scale** | the SPICE env is scored on **`V6A_SPECS` — the same 5 rows the analytic env scores**, *not* V6D | scoring the legs differently is the confound that misdirected PPO's critic |
| **episode dynamics** | `RevertOnInvalidEnv(revert_on_invalid=True, keep_going_on_success=True)` | the bare SPICE env TERMINATES on a bad edit; that is what gave PPO 1–3 of its 8 moves |

**So exactly one thing changes between legs: the design equations are replaced
by ngspice.** That is the only variable and it is the one worth measuring.

**Fourth decision — the 16 held-out targets are run on real SPICE BEFORE and
AFTER** the fine-tune leg, so "did it help or hurt" is a *paired* measurement.
`log_std` and `alpha` are recorded at both points: they are the instrument that
caught G114 and the only reason it was caught.

---

## 5. What the smoke runs already established (do not re-derive)

Two API errors were caught by **300-step** smoke runs rather than by a 90-minute
one — G112's lesson applied:

1. **`agent.act()` does not exist.** It is **`agent.actor.act(obs,
   deterministic=True)`**. Already fixed in the file.
2. **A fine-tune leg below `learning_starts = 100` produces no updates**, and
   `sac.py`'s `gate_report()` correctly **raises** rather than reporting a gate
   for a run that measured nothing. That guard is right — do not weaken it. Any
   smoke run must use `--finetune-steps 120` or more.

**Measured in the smoke, and it matters:**

* **Episodes ran 8.00 of 8 on the SPICE env** with `RevertOnInvalidEnv`.
  **Lever 3 works.** The bare env gave PPO 1–3 of 8.
* One 16-target SPICE evaluation costs **420 decks / ~2.6 min**. Two of them
  (before + after) is ~5.2 min of the ~90.
* A 300-step analytic leg reached `log_std −0.113`, `alpha 0.942` — i.e.
  barely moved, exactly as expected at 0.6 % of the real budget. **Do not read
  a smoke leg as a result.**

**Smoke artifacts were deleted deliberately.** A 300-step checkpoint on disk
named `sac_policy_analytic.pt` is indistinguishable from the real 50 000-step
one, which is G113's shape (a wrong artifact that looks completely normal).

---

## 6. The numbers you may quote, and the ones you may not

**May quote (measured, artifact-backed):**

| claim | value | artifact |
|---|---|---|
| Best design vs the competition spec | **11 of 11 rows at 45 of 45 mandated PVT corners** | `joint_verify_full_results.json` |
| Mandated 45-corner coverage | **7 of 16** | entry 30 OUTCOME |
| Non-RL top-k proposer | **6 of 16 accepted, 35.6 % fewer decks** | entry 32, `hybrid_topk_scan.json` |
| CMA-ES / library / random / PPO on 16 held-out | **14 / 9 / 5 / 0–1 of 16** | `corner_rl_results.json` |
| SAC stage-1 gate | `alpha` **14×**, `log_std` −0.007 → **−1.779** | entry 34, `sac_gate_results.json` |
| Pool transition graph | 74 526 designs → **34 789 444 directed edges** | entry 33 |

**MUST NOT quote:**

* **The coverage results as "RL".** They are `library seed → analytic pre-scan →
  probe → CMA-ES → 135-point verify`. Anyone reading `exp_coverage.py` finds
  `method_cmaes` in ninety seconds.
* **The refiner's 11/16 vs 9/16** without `n = 16, p = 0.50`.
* **The break-even figure** in `corner_rl_results.json` — it amortises the
  training cost of a policy that solved nothing.
* **Anything from `exp_sac_gate` or `exp_sac_finetune`** as a compliance or
  coverage number. Both score **5 of 13 rows** on the analytic-model subset.
  D9's condition is discharged **only** by `exp_hybrid` accept rate.

---

## 7. After entry 35 — the three branches, already committed

`_verdict()` prints one of these. Follow it; do not re-argue it.

* **Q1 and Q3 hit** → the transfer works, **G114 is solved not avoided**.
  Proceed to **stage 3**: SAC as `exp_hybrid`'s proposer, measured on **accept
  rate against 6 of 16**. *That is the number D9's condition requires.*
* **Q1 hits, Q3 misses** → the policy survives but does not transfer usefully.
  **Report it; do not start tuning.** The next lever is more SPICE steps — an
  owner budget decision, not a hyper-parameter hunt.
* **Q1 misses** → fine-tuning erased SAC as it erased PPO **with all three
  levers held**. That is a strong, publishable negative: the sim-to-real gap is
  **not** an optimiser-state artifact. Report it, and use the **analytic-only**
  policy as the stage-3 proposer — a policy that cannot be fine-tuned can still
  be measured as a proposer.

**Stage 3 is what actually discharges D9.** Everything before it is
preparation.

---

## 8. Standing rules — each was written after a specific failure

1. **Update `HANDOFF.md` and `nebula/PROGRESS.md` in the same commit as any
   change.** Session 27 broke this once and fixed it in arrears *saying so*.
2. **Run the suite before and after**; report both counts; never commit red.
3. **Pre-register in `PREDICTIONS.md` BEFORE the run**, committed. Entries 25
   and 26 broke this and say so in their own first paragraphs. Entries 27–35
   did not.
4. **Every new gate is deliberately broken, watched go red, and restored.**
5. **Never fabricate.** A missing artifact raises; it never gets a placeholder.
   `replay.py` once cited an entry 33 that did not exist — the numbers were
   real, the citation was not, and closing that took a whole re-derivation.
6. **Do not modify without a human decision:** `common/params.py`,
   `rl/contract.py`, `rl/env.py`, `rl/ppo.py`, `V1_SPECS`, the box, the
   tolerances. **Wrap, do not replace** — `corner_env`, `analytic_env`,
   `episode_dynamics`, `SpecConditionedCornerEnv` are the precedents.
7. **New spec sets are new tuples by ENUMERATION** — never by exclusion (G101),
   never by addition without re-checking inherited members (G106).
8. **One experiment at a time.** `experiments/runlock.py` enforces it. A
   finished run silently overwrote a finished run's artifact once (G113) and it
   was invisible until a *figure disagreed with the prose*.
9. **ngspice's exit code is not a success signal** — parse and assert (G26/G30).
   `ngspice_con.exe` not `ngspice.exe` (G20); run netlists from
   `nebula/device/spice/` (G29); instance W/L are plain microns (G31).
10. **Do not run experiments alongside the test suite** — one concurrent
    ngspice is 4.8× slower (G70).
11. Windows: no non-ASCII in `print()`. Run pytest from the repo root.
12. Commit as `Jai Kaushik <jaikaushik-prog@users.noreply.github.com>` (G12).
    **The repo is PRIVATE and stays private** (G1).

---

## 9. The five failure shapes this project keeps hitting

Check your work against these before running anything expensive.

1. **A set built by FILTERING loses members silently.**
   `[k for k in CONTRACT if k in available]` is a contract violation with no
   error. It once verified a **10.818 GHz** peak — 4.3× outside spec — at
   **45 of 45 corners** (G115). Three instances in one day. **Assert
   completeness; never filter.**
2. **A wrong value that FORMATS CLEANLY beats one that crashes.** A typo printed
   `None SPICE calls` for a whole training run without failing — and that value
   was the denominator of a headline ratio (G112).
3. **A shortcut graded against the wrong reference manufactures failures and
   then "corrects" them, unboundedly** (G110).
4. **"Cannot be measured" is not "fails"** (G107). Collapsing them once put all
   four benchmark arms at the invalid floor and made them look tied.
5. **Read the delivered VALUES, not just the verdicts.** Every one of the above
   produced a normal-looking pass column. **Render the figure before quoting the
   number** — that cross-check is what caught G113 and G115.

---

## 10. Open decisions — human only

1. ~~Does the rubric require RL to be the optimiser?~~ **ANSWERED (D9)** —
   hybrid approved **if the SAC contributes as RL**. The condition is the
   deliverable, not a formality.
2. **The ~90-minute full coverage sweep still needs the owner's say-so.**
   Mandated coverage is 7/16 and `A >= 5` makes a sweep defensible, not
   authorised.
3. **Which design ships**, if more than one is compliant.
4. **The report and the demo do not exist.** The owner's instruction was *"lets
   not rush to report now, keep keeping logs of everything, will make the report
   at the end when we have satisfactory results."* **20 days to 15 Sept.** The
   thing most likely to be under-done at the deadline is the report, not the
   engineering.

---

## 11. If you read nothing else

**Run `exp_sac_finetune.py`, score it against entry 35, follow the branch it
prints.** It is the experiment that decides whether the RL track has a future,
it is already pre-registered and smoke-tested, and its verdict is applied in
code so it cannot be softened. **Then stage 3 — accept rate against 6 of 16 —
is the only number that discharges the mentor's condition.**
