# PLAN.md — from here to submission

**Written 2026-08-17.** The team's operating plan for the remaining **29 days**
to the 15 Sept deadline, and the 10 days after it to the live presentation.

**Relationship to `nebula/NEXT_STEPS.md`:** that file was the session-18 ordered
plan, written when G2 had not started. **Its steps 1 and 3 are now done** (the
library trim; the closed loop). Its remaining steps are folded in below. Where
the two disagree, **this file is newer**; where either disagrees with
`HANDOFF.md` or `CLAUDEwa.md`, **those win**.

Companion files: [`decisions.md`](decisions.md) (why every choice was made),
[`flow.md`](flow.md) (how the code fits together).

---

## 0. Where we actually are

| Gate | Due | Status |
|---|---|---|
| G0 toolchain | 2 Aug | **passed** |
| G1 hand-designed reference | 3 Aug | **passed** |
| **G2 full evaluation, params → eye → reward** | 20 Aug | **PASSED 17 Aug**, three days early |
| **G3 RL beats random *and* grid search** | **3 Sep** | **not started** — the sweep has never been run |
| **G4 corner-robust design, verified** | **12 Sep** | not started |
| **G5 submitted** | **15 Sep** | — |
| Live presentation, BITS Goa | 25 Sep | — |

**What exists and works:** the whole pipeline, end to end. A parameter vector
produces a drawn SKY130 schematic meeting **all of S3–S8 at nominal
conditions**. 1448 tests green. One full evaluation costs **0.28 s**.

**What does not exist:** any evidence that RL beats simpler search (G3), any
corner verification (G4), the LLM wrapper, and the report.

**The single biggest risk** is not technical — it is that G3 turns into a
tuning rabbit hole. Budget it and stop on time. A measured negative result is
an acceptable G3 answer and the contract says so.

---

## 1. The three lanes

| | owner | one-line job |
|---|---|---|
| **A** | the ML/RL person | Prove the AI beats random and grid search — **gate G3** |
| **B** | the analog person | Decide the design questions no one else can, and catch wrong numbers — **gate G4** |
| **C** | you | Own the deliverable, the demo and the schedule; keep A and B unblocked |

Lanes run in parallel. The only hard dependency is **Decision D1 → A's sweep**
(§2), and it is deliberately at the very top so it never blocks anything.

---

## 2. Decisions to make, with owners and deadlines

Nothing below may be decided by an AI agent — `CLAUDEwa.md` §8 rule 6.

| # | Decision | Owner | By | Blocks |
|---|---|---|---|---|
| **D1** | **Compression**: accept it as part of the problem, or change the parameter box? | **B** | **Day 2** | A's sweep, the pre-screen, every baseline |
| D2 | Run the sweep with the device-only reward (V1), or the new eye reward (V2)? | A + C | Day 2 | the sweep |
| D3 | Re-fit the pre-screen before the sweep, or run against the current one? | A | Day 2 | the sweep's screened arms |
| D4 | Which baseline G3 must beat | A | Day 3 | G3's claim |
| D5 | Adopt the gm/I_D reparameterization? | A + B | Day 3 | must be settled *before* the sweep |
| D6 | Which corners for G4, and what margin is acceptable | **B** | Day 14 | G4 |
| D7 | Do the NRZ retarget for a real BER bathtub, or ship the bound? | B + C | Day 18 | the strength of the S8 claim |

### The recommended answers, so you are deciding rather than starting from blank

**D1 — recommend: accept it, do not change the box.** 61 % of the box is
unusable because the amplifier overloads on a real PCIe input. The framework's
job is to *find* the 3 % that works, and a hard search problem makes the RL
result more interesting, not less. **But B should first check the premise:** is
comparing a worst-case bit-pattern peak against the 1 dB compression point the
right validity test, or too strict? If B says too strict, the alternative is to
loosen it to a stated criterion — *not* to clamp, ever.
⚠️ **Tell A either way:** compression rejects ~60 % of proposals as invalid,
which is a large flat floor exactly where an untrained policy starts.

**D2 — recommend: V1, the device-only reward.** Keeps `BASELINES.md` valid,
needs no re-runs, and treats the eye as a promotion tier. Cheapest correct path.

**D3 — recommend: run against the current screen and label it.** The re-fit can
buy at most ~1.2 % of the `f_peak` spread (measured). Not worth delaying the
sweep. Just state that the screened arms carry a known 3.88 % false-rejection
rate.

**D4 — ~~recommend: 13.44 %, the measured rate at `cl_mid`~~. DECIDED
2026-08-18: the baseline is 7.10 %.**

**The recommendation above was wrong on its own facts and is kept struck
through rather than deleted.** 13.44 % was *not* measured at `cl_mid`: it is
the rate on `robust_geometry_data.csv`, **every row of which has `cl` = 150 fF**
— the legacy pin, 4.598× `cl_mid`. So the reason given here for rejecting
13.54 % ("`cl` pinned at a load the next stage cannot present") applies to
13.44 % **equally**, and the stated discriminator between them never existed.

**The decision: 7.10 %** [6.05, 8.31], n = 2000 — the only one of the four
candidates measured under the sampler, evaluator, box **and load** the sweep
will actually use (`nebula/DIFFICULTY.md` §3). A baseline the current pipeline
cannot reproduce does not survive a report. The gap is decomposed in
`nebula/ATTRIBUTION.md`; the S3 *definition* explains none of it.

**D5 — recommend: no.** Measured benefit is 1.16× on simulations per usable
design, against invalidating every baseline. But **decide before the sweep** —
afterwards it costs a re-run. `nebula/GMID_MAP.md` §8 has the full argument.

**D7 — recommend: decide at Day 18 based on where G3 and G4 stand.** It is the
difference between "a worst-case eye bound" and "a BER-10⁻¹⁵ contour", which is
the project's most distinctive claim. Worth ~3–5 days. Cut it if G4 is late.

---

## 3. Phase 0 — unblock (Days 1–3, by 20 Aug)

**Goal: nothing is waiting on a decision, and the sweep is running.**

**B**
- [ ] Read `nebula/G2_RESULTS.md` §5 (the worked design) and §7 (what it does
      not prove).
- [ ] **Make decision D1.** Write the answer and the reasoning into
      `decisions.md` §J.
- [ ] **Sanity-check the worked design.** Does a 38.9 µm × 0.188 µm pair at
      3.08 mA plausibly give 9.67 dB of peaking at 2.19 GHz? Is 0.29 mV of
      input-referred noise sensible? 5.3 mW? **If anything looks wrong, say
      so** — no test can catch this and the project has been wrong this way
      before.

**A**
- [ ] Read `nebula/BASELINES.md` §§0–3 and `nebula/RL_SMOKE.md` §§4–5.
- [ ] Re-measure the throughput constant at 8 workers, then re-run
      `python -m nebula.experiments.baselines --budget`. **Do not divide the
      single-process number** — measured, isolated speed-ups do not transfer
      (2.98× became 1.80×).
- [ ] Settle D2–D5.
- [ ] **Launch the sweep.** ~1–2 h now that an evaluation costs 0.28 s. It
      streams to disk, so an interrupted run is recovered, not lost.

**C**
- [ ] Report skeleton — section headings only, so A and B know where their
      results land.
- [ ] Start `nebula/llm/` (the stated bonus deliverable).
- [ ] Brief both specialists on the standing rules in §7 below.

**Done when:** D1–D5 are written down, the sweep has finished, and B has either
signed off the worked design or raised a specific objection.

---

## 4. Phase 1 — G3 (Days 4–17, due 3 Sep)

**Goal: an honest answer to "does RL beat random and grid search", with a plot.**

**A — the critical path**
- [ ] Analyse the sweep. Fill in `PREDICTIONS.md` entry 6's outcome — seven
      quantitative predictions with acceptance bands. **Go through every one
      and record hit or miss.** A miss is a result.
- [ ] Apply the ranking rule without exception: **any ordering whose confidence
      intervals overlap is reported as "not separable at this sample size",
      not as a ranking.**
- [ ] **Before touching hyperparameters**, check the policy is getting a usable
      gradient. A flat learning curve caused by a flat objective is not a
      tuning problem.
- [ ] Tune PPO. **Tune only on the easy problem, hold out the target used for
      the final claim, and add the tuning budget to PPO's cost.**
- [ ] Produce the G3 plot. Use **simulations-to-ceiling**, not best-score —
      the score saturates at +8.950669, which is a property of the simulator's
      frequency grid rather than of the circuit.

**Hard stop:** if PPO is not beating random search by **Day 14**, stop tuning
and write it up as a measured negative result. `CLAUDEwa.md` §7 is explicit:
*"stop and debug the reward function; do not proceed to corners."*

**B**
- [ ] Prepare G4: choose the corner set and the acceptable margin (**D6**).
- [ ] Keep sanity-checking numbers as they land.

**C**
- [ ] Finish the LLM wrapper. **Two hard rules:** it must never invent a
      number (every figure looked up from a result object, with a test proving
      a fabricated value cannot pass through), and it must never touch the
      sizing loop — an LLM steering the optimiser would undercut our own
      "zero human intervention" claim.
- [ ] Build the live demo: type a spec, get a sized circuit.
- [ ] Draft the report's methodology section — our strongest asset.

**Done when:** G3 has an answer and a plot, whichever way it went.

---

## 5. Phase 2 — G4 (Days 18–26, due 12 Sep)

**Goal: a design proven to work across manufacturing variation and temperature.**

**B + C**
- [ ] Run the corner sweep on the G3 winner. The bridge already takes one
      result per corner — nothing structural is missing. At 0.28 s per
      evaluation, 3 corners × 2 loads is 1.7 s per design.
- [ ] Report **which spec fails first at each corner**, not just a pass rate.
      That table has been the useful output every previous time.
- [ ] B signs off the final design.

**A** *(only if G3 landed early)*
- [ ] The spec-conditioned policy — train across a *distribution* of targets
      and evaluate on targets never seen in training. **This is the one
      comparison that could favour RL on its actual merits**, and nothing
      measured so far tests it. Pre-register the prediction before running.

**C**
- [ ] Report and slides in earnest. Three results deserve a slide each:
      the cost table (what each assumption was worth), *"physics does not solve
      this"* (the analytic screen removes 61.7 % of the box for free and that
      is **not** enough), and the reward ceiling.
- [ ] **Declare the inheritance**: the SerDes framework is pre-existing team
      infrastructure; the RL sizing loop, the corner-aware fidelity hierarchy
      and the device→link bridge are new work.

**Done when:** one design is verified across corners and the results table is
drafted.

---

## 6. Phase 3 — submit (Days 27–29, by 15 Sep)

- [ ] **Day 27: freeze the code.** No new features. Bug fixes only.
- [ ] Full test suite green; every number in the report traced to a run.
- [ ] Re-read `HANDOFF.md` §7 (known limitations) and make sure the report
      does not overclaim past any of them.
- [ ] Push, tag the submission commit, submit **the morning of 15 Sept**.

Then, to 25 Sept: rehearse the presentation and prepare Q&A. Expect
*"why RL and not Bayesian optimisation?"* and *"how do you know the simulator
is telling the truth?"* — you have measured answers to both.

---

## 7. Standing rules for everyone

These are not bureaucracy. **Every one was written after a specific failure**
that produced a wrong number while reporting success.

1. **Never fabricate a number.** If a value is unknown it stays empty and fails
   loudly. Every figure in a deliverable traces to a run we actually did.
2. **ngspice's exit code is never a success signal.** It reports many failures
   as warnings and exits 0. Parse the output and assert.
3. **Every gate gets a test that proves it can fail.** Break the input
   deliberately, watch it go red, put it back.
4. **Update `HANDOFF.md` in the same commit as any change.** A change without a
   handoff update is an incomplete change.
5. **Commit daily. Push often.** The repo is private and must stay private —
   it contains copyrighted reference PDFs.
6. **Pre-register predictions before running an experiment**, in
   `PREDICTIONS.md`, with acceptance bands. Record misses as misses.
7. **Humans decide anything where being wrong costs a week.** An AI agent may
   never choose a parameter range, a reward weight or a spec tolerance.

---

## 8. If time runs short, cut in this order

1. The spec-conditioned policy (§5's optional item).
2. The NRZ retarget / real BER bathtub (D7) — ship the bound and say what it is.
3. Depth of PPO tuning — take the measured answer at Day 14 and write it up.

**Never cut:** G4 corner verification, or the report. A framework with no
corner result and no write-up is not a submission.

---

## 9. The 30-second story, for whenever anyone asks

> When you send data down a wire at gigabits per second, the wire smears the
> bits into each other until the signal is unreadable. **Equalization** is the
> receiver circuit that undoes that. Designing one normally takes an
> experienced analog engineer weeks of manual tuning.
>
> **We built a framework that does it automatically:** you give it a target
> specification, and reinforcement learning searches transistor dimensions,
> simulates each candidate in a real open-source chip process, and outputs a
> finished circuit plus its measured performance — including a bit-error-rate
> eye, which means we can prove the circuit actually works at the link level
> rather than just meeting a frequency-response spec.
>
> As of 17 Aug the loop is closed end to end and we have a circuit meeting
> every target. What remains is proving the AI finds them faster than brute
> force, and that the design survives manufacturing variation.
