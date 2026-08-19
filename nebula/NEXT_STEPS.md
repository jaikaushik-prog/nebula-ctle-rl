# NEXT_STEPS.md — the ordered plan, and prompts to execute it

> **SUPERSEDED 2026-08-19 by `nebula/CONTINUE_HERE.md`. Read that first.**
>
> This file was written on 2026-08-08 (session 18) and its §0 status table is
> now wrong in both of its load-bearing rows: **G2 is PASSED** (session 21) and
> **the G3 sweep HAS RUN** (session 22f, 25 869 simulations, 42 minutes). Its
> "38 days to the deadline" is now 27.
>
> **Kept, not deleted**, because its per-step reasoning and its prompts are
> still the best record of *why* the order was chosen, and because deleting a
> superseded plan hides the fact that the plan changed. Treat every status
> claim in it as of 2026-08-08 and every ordering claim as advisory.

**Written 2026-08-08, at the end of session 18, for whoever picks this up
next** — a Claude Code session, a chat agent working by copy-paste, or a human.

Read `HANDOFF.md` first. This file is not a substitute for it; it is the
*ordering*, with the reasoning for the order and a ready-to-use prompt per step.

---

## 0. Where the project actually is

**38 days to the 15 Sept deadline.** Gate dates from `CLAUDEwa.md` §7:

| Gate | Due | Criterion | Honest status |
|---|---|---|---|
| G0 | 2 Aug | toolchain runs all four analyses | **passed** |
| G1 | 3 Aug | hand-designed reference meets S3–S7 at TT | **substantially passed**; MIM-cap/poly-resistor area models still open |
| **G2** | **20 Aug** | **one full evaluation: params → ngspice → fit → eye → scalar reward** | **NOT STARTED. The link layer is a mock end to end (G16), so the eye half of this gate does not exist.** 12 days out. |
| G3 | 3 Sep | RL beats random **and** grid search, with a plot | baselines harness built and tested; **the sweep has not run**; no tuned policy |
| G4 | 12 Sep | corner-robust design generated and verified | blocked behind G2/G3 |
| G5 | 15 Sep | submitted | — |

### What is strong

The measurement infrastructure and the epistemic discipline. 1292 tests. Every
published number traces to a run. Six pre-registered predictions with the
misses recorded as misses. A documented failure catalogue (G1–G76) where a
majority of entries describe something that *reported success and exited zero*.
That is genuinely unusual and it is the project's best asset in front of a
panel of practising designers.

### What is at risk, stated plainly

**The competition asks for a framework that takes target specs in and emits a
sized schematic plus its specs. The link half of that does not exist yet**, and
G2 — the gate that would prove the loop closes — is 12 days away and not
started. Everything measured so far is device-layer. `S8` (eye) cannot be
scored, and `nebula/rl/reward_v1.py` says so explicitly and correctly.

**The second risk is throughput, and it has been the top open item since
session 17 without being done.** 99.7 % of a run is the simulator. The extended
library costs **2.07 s/evaluation against ~0.33 s** on the nfet-only one. Every
experiment below is bought at that rate; the 12-hour sweep becomes ~2 hours.

### The single most important judgement call for whoever is next

**Do not add scope before G2.** The temptation is more measurement — more
rungs, more surrogates, more corners. The project already has more measurement
than most entries will have. What it does not have is a closed loop from a spec
vector to a schematic, which is the literal deliverable.

---

## 1. The order, and why

Steps 1–2 are cheap and unblock everything. Step 3 is the deadline gate.
Steps 4–7 are the competition contribution. Steps 8–9 are finishing.

| # | Step | Cost | Unblocks |
|---|---|---|---|
| 1 | Trim the SPICE library | ~half a day | **everything**, at ~6× |
| 2 | Run the baselines sweep | 12 h unattended (2 h after step 1) | G3, the surrogate dataset |
| 3 | **G2: close the device→link→reward loop** | **days — start now** | G2, G4, the deliverable |
| 4 | Re-fit the pre-screen at benchmark conditions | hours | honest screened arms |
| 5 | Tune PPO enough to have a G3 answer | days | G3 |
| 6 | Spec-conditioned policy | days | contribution #2 + the live demo |
| 7 | LLM wrapper | ~a day | the stated bonus deliverable |
| 8 | Task 8 worst-corner surrogate | days | contribution #1, optional |
| 9 | Report, slides, figures | days | G5 |

**If time runs short, cut in this order: 8, then 6, then 5's tuning depth.**
Never cut 3.

---

## 2. The prompts

Each is self-contained. For a **chat agent with no repo access**, the "paste
alongside" line says exactly which files to paste. For a **Claude Code
session**, paste the prompt as-is.

Every prompt inherits the standing rules: read `HANDOFF.md` and `CLAUDEwa.md`
in full first; update `HANDOFF.md` in the same commit; run
`python -m pytest tests nebula/tests -q -m "not slow"` before and after and
report both counts; never fabricate a number; never let a check report failure
as a warning.

---

### STEP 1 — Trim the SPICE library (do this first, always)

> **Prompt.**
>
> Read `HANDOFF.md` and `CLAUDEwa.md` in full, then `nebula/PASSIVES.md` §6
> item 6 and gotchas G36, G58 and G70.
>
> **Task: cut the per-evaluation SPICE cost from 2.07 s to ~0.33 s by trimming
> the extended library, and prove the trim is bit-identical.**
>
> Session 17 measured that **99.7 % of a training run is the simulator**
> (environment 1585.8 s against a PPO update of 3.5 s) and that the extended
> trim costs **2.07 s per evaluation against ~0.33 s** on the nfet-only library
> for the same netlist. Every experiment in this project is bought at that
> rate, so this is the highest-value item in the repo and it has been the top
> open item since session 17 without being done.
>
> The extended library exists because drawn passives need the R and C model
> sections that `sky130_nfet_only.lib.spice` does not carry. Trim
> `parameters/typical.spice` and `invariant.spice` down to what the netlists
> actually reference.
>
> **The gate, and it is not optional (G36 set the precedent).** The trimmed
> library must produce **bit-identical** output to the untrimmed one on a set
> of designs that exercises every device the netlists use — the input pair, the
> tail mirror, `res_high_po`, `res_xhigh_po`, `cap_mim_m3_1`. Bit-identical
> means the parsed measurement vector agrees to **rel = 0, abs = 0**, not "to
> within tolerance". Write the comparison as a test that can fail: break the
> trimmed library deliberately, watch it go red, put it back.
>
> Report the measured before/after seconds per evaluation over at least 50
> designs, and the speed-up. Then update `baselines.SEC_PER_SIM_AT_8` and
> re-run `python -m nebula.experiments.baselines --budget` so the allocation
> reflects the new rate — the sweep may now afford the P2 rung and P3's
> screened arm, which were cut only for cost.
>
> **Traps.** G29: run netlists from `nebula/device/spice/` so `.spiceinit` is
> read at parse time. G20: `ngspice_con.exe`, never `ngspice.exe`. G26/G30/G35:
> ngspice reports many failures as warnings and exits 0 — parse the output and
> assert, never trust the exit code.

*Paste alongside (chat agent):* `nebula/PASSIVES.md` §6, the head of
`nebula/device/spice/sky130_nfet_only.lib.spice`, and the `.lib` include lines
from `nebula/device/sky130_runner.py`.

---

### STEP 2 — Run the baselines sweep

No prompt needed. One command, machine otherwise idle:

```
python -m nebula.experiments.baselines --sweep
```

25,500 simulations, **~12.0 h at the current rate, ~2 h after step 1**. It
streams `nebula/experiments/baselines_run.jsonl`, so an interrupted run is
recovered rather than lost:

```
python -m nebula.experiments.baselines --analyse nebula/experiments/baselines_run.jsonl
```

**Then** run this prompt:

> **Prompt.**
>
> Read `nebula/BASELINES.md` and `nebula/PREDICTIONS.md` entry 6 in full.
>
> The baselines sweep has now run. **Task: write up the outcome, and close the
> pre-registration honestly.**
>
> 1. Replace `nebula/BASELINES.md` §11 — currently PILOT numbers, clearly
>    labelled — with the sweep's. Keep the pilot section as a subsection
>    labelled "pilot, superseded"; do not delete it, because the pilot is what
>    moved the throughput constant and the allocation.
> 2. Fill in `PREDICTIONS.md` entry 6's **Outcome** section. It has seven
>    quantitative predictions with acceptance bands and five falsification
>    conditions. **Go through every one and record hit or miss.** Do not edit
>    anything above the Outcome heading. A miss is a result.
> 3. Report the timing control's disagreement. **If `timing_void` is true, the
>    wall-clock numbers are void and the sweep is repeated, not adjusted** —
>    say so and do not quote them.
> 4. Two things the pilot flagged that the sweep can now settle at proper
>    sample size: whether **PPO really is competitive on time-to-first-feasible
>    while worst on final reward** (pilot: 3/3 seeds, median 4.0 sims, final
>    8.252 — the worst of ten groups), and whether **LHS really is the worst
>    method** (pilot median 38.0 against uniform's 3.0, on an interval of
>    [3, 41] that may be noise).
> 5. Apply 7h's ranking rule without exception: **any ordering whose confidence
>    intervals overlap is reported as "not separable at this sample size", not
>    as a ranking.**
>
> **Guard the write-up against over-claiming in both directions**, using entry
> 6's own words: if PPO loses that is the expected result and is *not* evidence
> about the amortised spec-conditioned claim, because every run in this sweep
> optimises one fixed spec target from scratch. If PPO wins, that does not
> establish the amortised claim either.

*Paste alongside (chat agent):* the terminal output of `--analyse`, and
`PREDICTIONS.md` entry 6.

---

### STEP 3 — G2: close the loop. **START THIS NOW, IN PARALLEL WITH STEP 2.**

This is the deadline gate and the actual deliverable. It does not depend on
steps 1 or 2 and should not wait for them.

> **Prompt.**
>
> Read `HANDOFF.md` and `CLAUDEwa.md` in full, then `CLAUDEwa.md` §5.3 (the two
> things most likely to be silently wrong), `nebula/CHANNEL_MODEL.md`, and
> gotchas G16, G59 and G61.
>
> **Task: pass gate G2 — one full evaluation end to end, from a parameter
> vector to a scalar reward that includes a link-level eye metric, with no mock
> anywhere in the path.**
>
> Today the device layer is real and measured, and **the link layer is a mock
> end to end (G16)**, which is why `rl/reward_v1.py` correctly refuses to score
> S8. That refusal is right, and it is also the largest gap between this
> project and the competition's own stated deliverable ("outputs the final
> schematic and resulting specs"). Close it.
>
> **What exists to build on, all real and all measured:**
> * `nebula/rl/evaluator.py` returns a validated AC measurement vector per
>   (design, corner, load) with four verdict bands.
> * `nebula/CHANNEL_MODEL.md` defines a derived channel family
>   `IL(f) = A·√f + B·f`, 21 members, minimum-phase and causality-gated, with
>   the PCIe Gen2 −3.5 dB de-emphasis mandate accounted for.
> * `python_models/statistical_eye.py` is the semi-analytic BER engine, and
>   `python_models/equalizers.py` has a 1-tap DFE.
>
> **The bridge to build:** fit the measured AC response onto
> `(g_dc, f_zero, f_pole1, f_pole2)`, instantiate the CTLE model, run the
> channel + CTLE + 1-tap DFE through the statistical eye, and return eye height
> in **volts** and eye width in **UI**.
>
> **The two highest-risk bugs, both named in `CLAUDEwa.md` §5.3, and both must
> have a dedicated test with a hand-computed expected value:**
> * **(a) millivolt calibration.** `statistical_eye.py` works in normalised
>   amplitude; S8 demands volts. `vout_swing_v` must be carried through. A
>   wrong scale factor produces plausible-looking numbers that are meaningless.
> * **(b) pole-zero fit validity.** Cross-check the fit against the §6 design
>   equations and **reject fits with residual > 0.5 dB** rather than passing
>   garbage downstream.
>
> **Use the closed form, not the asymptote.** `nebula/experiments/task8_symbolic.py`
> derived the exact peak of a one-zero/two-pole magnitude:
> `f_peak = sqrt( sqrt((f_z² − f_p1²)(f_z² − f_p2²)) − f_z² )`, with no fitted
> constant, and measured that `20·log10(k)` over-predicts peaking by a median
> **+1.199 dB** across 1311 designs. Do not size anything from the asymptote.
>
> **Read G60 before integrating any waveform through the design equations:**
> *"never integrate a waveform through `deq.predict()`"* — it over-predicts the
> Nyquist boost by 0.8–1.5 dB and that became a 28 % error in a published
> compression ratio.
>
> **Deliverable:** `nebula/G2_RESULTS.md` with the measured wall-clock cost of
> each fidelity tier (that is part of the gate criterion), the two calibration
> tests and what they pin, and one worked example printed end to end: a
> parameter vector in, a schematic-defining sizing plus its measured specs and
> eye out. Then wire S8 into `reward_v1` and say what it changes.
>
> **If the gate fails, take the fallback the same day** (`CLAUDEwa.md` §7):
> reduce the corner count and simplify the link model. Sunk cost is how student
> projects miss deadlines.

*Paste alongside (chat agent):* `nebula/rl/reward_v1.py`, the `DeviceResult`
and `LinkResult` dataclasses from `nebula/common/types.py`, and
`nebula/CHANNEL_MODEL.md` §§4–5.

---

### STEP 4 — Re-fit the pre-screen at benchmark conditions

Cheap, and it has a measured bound on what it can buy — read that first.

> **Prompt.**
>
> Read `nebula/BASELINES.md` §5 and §11, and `HANDOFF.md`'s session 18b and 18c
> entries.
>
> **Task: fix the pre-screen's peaking bias at benchmark conditions.**
>
> The screen is calibrated on `robust_geometry_data.csv` (`cl` = 150 fF,
> `nf_in` varying, ideal R/C, **ideal tail**). Moved to the benchmark's own
> conditions its population rates transfer (free rejection 61.7 → 63.9 %, yield
> lift 2.60 → 2.66×) but **its accuracy does not**: `f_peak` MdAPE
> **4.93 → 15.85 %**, peaking bias **−0.009 → +0.361 dB**, false-rejection rate
> **0.39 → 3.88 %**, ten times the 1 % budget the operating point was chosen
> against. **Widening does not fix it** — measured, at 2.5× the widening the
> rate is still 2.33 % while free rejection falls from 64 % to 40 %. **A window
> absorbs variance; this is bias.**
>
> **Know the bound before you start.** Session 18c decomposed the error:
> grid discretisation **0.17 %**, predicted-`k` **1.20 %**, and the
> one-zero/two-pole **model itself 4.25 %**. So re-fitting the gm model can buy
> **at most ~1.2 %** of the `f_peak` spread. **Do it anyway, because the target
> is the +0.361 dB peaking bias and the 3.88 % false-rejection rate, which are
> a different failure from the spread.**
>
> **The mechanism to try first, and it is specific:** the gm/I_D model was
> fitted where `I_D = i_bias/2` exactly, which is true of an ideal tail; the
> real current mirror delivers **4–8 % less** (session 13, measured). That
> over-estimates `I_D`, hence `gm`, hence `k`, hence peaking — the right
> direction and about the right size.
>
> **Re-fit on the sweep's unscreened P1 rows** (~10,500 evaluations at
> benchmark conditions), not on the pilot's 900. Follow G60's procedure
> exactly: `f_z` and `f_p2` are exact, only `k` is fitted, and it is fitted
> **from the measured peaking alone** so that the `f_peak` error stays an
> independent check. Hold out a fraction and report held-out numbers.
>
> Then re-derive `MARGIN_OCT`/`MARGIN_DB` by the stated rule — the smallest
> widening on the ladder whose measured false-rejection rate is ≤ 1 % — and
> make sure `test_margins_follow_the_stated_rule` still re-derives your
> constants. Update `nebula/BASELINES.md` §5's tables and the
> `test_transfer_to_benchmark_conditions_is_measured_and_recorded` assertions,
> which are deliberately written to fail when this is fixed.

*Paste alongside (chat agent):* `nebula/experiments/prescreen.py` and
`nebula/BASELINES.md` §5.

---

### STEP 5 — G3: a real answer on RL vs the baselines

> **Prompt.**
>
> Read `nebula/BASELINES.md`, `nebula/RL_SMOKE.md` and `PREDICTIONS.md`
> entry 6 in full.
>
> **Task: produce gate G3's answer and its plot — does the RL policy beat
> random search and grid search at TT?**
>
> The baselines are measured and the harness is fair by construction (7f). What
> does not exist is a **tuned** policy: session 17's run was explicitly a smoke
> test, nothing was tuned, and no conclusion about learning was drawn from 142
> episodes. The pilot then found untuned PPO reaching feasibility as fast as
> uniform random while scoring the **worst final reward of ten groups** — fast
> to feasible, unable to climb.
>
> **That shape is the hypothesis to test.** The feasible branch of the reward
> is `B + min_i(margin_i / tol_i)`, so climbing after feasibility means
> improving the *worst* normalised margin. Check whether the policy is getting
> a useful gradient there at all before touching hyperparameters — a flat
> return curve caused by a flat objective is not a tuning problem.
>
> **Constraints on tuning, so the comparison stays honest:**
> * tune **only** on P1, and hold out the spec target used for the final claim;
> * report the tuning budget in simulations and **add it to PPO's cost** — a
>   method that needed 50,000 simulations of tuning to win a 150-simulation
>   comparison has not won it;
> * do not touch the evaluator, the reward tolerances, the box or the geometry
>   mapping. If any of those change, every baseline must be re-run.
>
> **Know what the metric can and cannot show.** On P1 the primary metric
> saturates: the AC sweep grid caps the reward at **+8.950669** and six of ten
> pilot groups sat exactly there. Use **simulations-to-ceiling** as the
> discriminator, and read `nebula/BASELINES.md` §3 before designing the plot.
>
> **If RL does not beat random search, `CLAUDEwa.md` §7's fallback is explicit:
> stop and debug the reward function; do not proceed to corners.** And write it
> up as a finding — "we measured that RL did not pay at this problem size, here
> is the comparison" is consistent with the standard this project has held, and
> §7 already says "if BO matches RL, say so. That is a finding, not a loss."

*Paste alongside (chat agent):* the `--analyse` output from step 2 and
`nebula/rl/ppo.py`.

---

### STEP 6 — The spec-conditioned policy (contribution #2, and the demo)

> **Prompt.**
>
> Read `CLAUDEwa.md` §7 ("our two claimed contributions") and
> `nebula/rl/contract.py` §3 in full.
>
> **Task: make the policy spec-conditioned, and evaluate it on held-out
> specs.**
>
> This is the contribution the paper this project is modelled on does *not*
> have, and it is the live demo: type in a new spec, get a sized netlist in
> seconds. `TargetSpec` already enters the observation —
> `contract.build_observation` carries a two-channel target block — so the
> plumbing exists and what is missing is training across a *distribution* of
> targets rather than the single mid-window point every run so far has used.
>
> **The comparison that makes it a contribution:** a classical optimiser must
> re-run from scratch for every new spec target; an amortised policy should
> not. So the metric is **simulations to reach a feasible design on a spec
> target never seen in training**, against CMA-ES and GP-BO starting fresh on
> that same target. That is the only comparison in this project that could
> favour RL on its actual merits, and **nothing measured so far tests it** —
> `PREDICTIONS.md` entry 6 says so explicitly.
>
> Pre-register the prediction in `PREDICTIONS.md` before running, per the
> file's own rule. Train on a spec distribution spanning S3's band, hold out
> targets, and report per-target results rather than a pooled average.

*Paste alongside (chat agent):* `nebula/rl/contract.py` and `nebula/rl/env.py`.

---

### STEP 7 — The LLM wrapper (the stated bonus deliverable)

> **Prompt.**
>
> Read `CLAUDEwa.md` §2 (deliverables) and §10 (repo layout).
>
> **Task: build `nebula/llm/` — natural-language spec entry and design
> explanation.** This is deliverable 2 in the competition's own words:
> *"LLM-based human interaction with a wrapper to fine-tune."*
>
> Scope it small and make it real: parse a natural-language request into a
> validated `TargetSpec`, run the existing pipeline, and produce a written
> explanation of the resulting design that cites **measured** numbers.
>
> **Two hard rules.** The LLM must never invent a number — every figure in its
> output is looked up from a result object, and a test must prove that a
> fabricated value cannot pass through. And the LLM must not be in the sizing
> loop: it converts language to a spec vector and explains the result, nothing
> else. The competition asks for zero human intervention in the *design*; an
> LLM steering the optimiser would undercut the entry's own claim.
>
> Use the Anthropic API. Keep a deterministic offline fallback so CI and the
> live demo do not depend on a network call.

*Paste alongside (chat agent):* `nebula/common/types.py`.

---

### STEP 8 — Task 8's worst-corner surrogate (optional; cut this first)

> **Prompt.**
>
> Read `HANDOFF.md`'s session 18c entry and
> `nebula/experiments/task8_blackbox.py`'s module docstring in full.
>
> **Task: build the per-corner dataset task 8d needs, then decide accept or
> abandon.**
>
> **The blocker, stated so you do not repeat the search:** task 8a's premise —
> *"we already have roughly 20,205 (design, corner) SPICE results from the S9
> sweep"* — **is false for this repo.** `s9_yield_results.json` kept only
> counts (`per_point_met`, `first_fail_counts`, index lists). The individual
> measurements were never written to disk. That is G49's failure mode one level
> up: the file is tracked, but it only ever stored aggregates.
>
> Per-corner *measured* rows that exist: `tail_device_data.csv` 261 (a
> tail-geometry study, not a box sample), `cl_range_data.csv` 180 (`gm` only),
> and the baselines sweep's P3 arm (~4,500 once step 2 has run).
>
> **So choose, and say which you chose and why:** re-run S9 with row-level
> JSONL logging (clean, a full box sample, costs hours — and cheap after
> step 1), or use the sweep's P3 arm (free, but it is 4,500 rows from a rung
> the pilot suggests is empty, so it is a biased sample of the box).
>
> Then apply 8d's rule **as written, without lowering the bar**: worst-corner
> `peaking_db` MAE < 0.5 dB, worst-corner `log10(f_peak)` MAE < 0.03, and
> boundary error no worse than 2× overall. **If it misses, abandon the
> surrogate and say so** — the 3-corner deterministic screen is only 3× the
> cost, needs no ML, and cannot silently mispredict.
>
> **What you are up against, measured in session 18c:** on TT, an exact closed
> form with one fitted scalar reached **4.25 % MdAPE** on `f_peak` against
> XGBoost's **4.64 %** held out. A black-box surrogate has to beat a one-line
> formula before it earns a place.
>
> **Note also:** `GroupKFold` is a genuine requirement for per-corner data —
> the repeat factor is 6–45× — and it was a **no-op** on the TT file, where
> every design appears once. Write the test that asserts no `design_id` appears
> in both folds, and make sure it can actually fail.

*Paste alongside (chat agent):* `nebula/experiments/task8_blackbox.py`.

---

### STEP 9 — The write-up

> **Prompt.**
>
> Read `README.md`, `docs/PROGRESS.md`, `nebula/BASELINES.md` and
> `nebula/PREDICTIONS.md`.
>
> **Task: draft the final report and slides for a panel of practising
> analog/SerDes design engineers**, who care about circuit correctness and
> honest results far more than ML novelty (`CLAUDEwa.md` §1).
>
> **Lead with the methodology, because that is this project's strongest
> asset**, and the evidence for it is already written: six pre-registered
> predictions with the misses recorded as misses; a retracted central claim
> (G40, "S3 is a coupled constraint", falsified by the measurement meant to
> confirm it); and a failure catalogue where most entries describe something
> that reported success and exited zero.
>
> **Three specific results are worth a slide each:**
> * **the cost table** — PVT corners cost 39 %, the load range 99.4 %, the
>   ideal-tail assumption 8.8 %. It shows what each assumption was worth;
> * **"physics does not solve this"** — the analytic pre-screen removes 61.7 %
>   of the box for free and lifts the yield 2.60×, and that is *not* enough;
> * **the reward ceiling** — the best achievable score is a property of the AC
>   sweep grid, not of the circuit, which is the kind of thing a measurement
>   engineer recognises immediately.
>
> **Declare the inheritance**, per `CLAUDEwa.md` §4.3's honesty rule: the
> SerDes framework is pre-existing team infrastructure; the RL sizing loop, the
> corner-aware fidelity hierarchy and the device→link bridge are new work.
>
> **Do not overstate the RL result in either direction.** `PREDICTIONS.md`
> entry 6 already contains the exact wording to reuse.

---

## 3. Traps that have already cost this project time

Give these to any agent that will touch the code. Every one is measured.

1. **ngspice reports failures as warnings and exits 0** (G26, G30, G35, G54,
   G63). Parse the output and assert. An exit code is never a success signal.
2. **A gate whose condition is unreachable is indistinguishable from a deleted
   gate** (G73). Count how often each guard fires. A "peak at the grid edge"
   test fired zero times on 1890 designs because that condition cannot occur.
3. **Units**: microns vs metres (G31), scale applied twice (G35),
   `inoise_total` is RMS volts and must not be square-rooted. Each is a factor
   of 10³–10⁶ that still simulates happily.
4. **Two definitions of one thing** (G32, rule 9). A model card that differs
   between the netlist a human reads and the runner that produced the numbers.
5. **A benchmark run in a fixed order measures the order** (G71). The first
   configuration always pays the cold file cache. Warm-up, randomise, control.
6. **A speed-up measured on isolated evaluations does not transfer to a
   workload whose workers also compute** (G75). 2.98× became 1.80×.
7. **An aggregate rate can hide a systematic bias completely** (G76). The
   pre-screen kept its rejection rate and lift while its error tripled.
8. **Look for the impossible number, not the disappointing one.** 2.55× from
   two processes was the tell that caught G71.
9. **Results are tracked, not gitignored** (G49), and aggregates are not
   results — session 18c found that S9's 20,205 measurements were never saved
   because only counts were written.

---

## 4. If you only get one more session

Do **step 1**, then start **step 3**. The library trim makes everything else
affordable, and G2 is the gate the deliverable depends on. The sweep, the
surrogate and the pre-screen re-fit are all improvements to measurement the
project already has enough of.
