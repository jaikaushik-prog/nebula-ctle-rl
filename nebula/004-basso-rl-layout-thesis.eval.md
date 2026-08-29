# Eval — Proposal 004 (Basso thesis: RL floorplanning and routing)

**Evaluated 2026-08-29, session 29. 17 days to G5 (15 Sept).**

The brief's scope warning is honoured: this is **not** evaluated as a sizing method.
It is evaluated on the two questions the brief names — (a) which RL formulation
techniques transfer independent of the layout domain, and (b) whether it changes the
answer on layout scope.

Same protocol deviation as evals 001-003: the sealed Stage 1 pass was not available,
so this is a combined Stage 1+2 pass.

**Headline: three of the four techniques are already implemented here, and the repo
has already measured the trade each one makes.** 2.1 exists as a soft screen with an
eight-row ladder printed; 2.2 exists as `scan_topk` with the k-curve measured; 2.4
exists in part as G72's graded band. The genuinely new content is **not a technique
at all** — it is §3's convergent limitation and §4's presentation template, both of
which are free report wins.

---

## 0. A live finding that came out of this eval and outranks it

While checking which environment these techniques would touch, I found that
**entry 41's run is dead and the lock file is stale.**

    experiments/.sac_screen.runlock.json   pid 18744 -- NOT RUNNING
    progress                               9 500 of 25 000 steps
    elapsed                                307.6 min (5.1 h)
    decks                                  45 436

It is **resumable by design** — the entry chunks at 500 steps with a checkpoint per
chunk, and `learning_starts` deliberately applies only to the first chunk so a
continuation does not re-inject 100 uniform-random actions. Two observations from the
19 progress rows, offered as **mid-run readings, not scored predictions** (entry 41
scores its Q's on the completed run):

* **Q1's thresholds are already cleared, comfortably.** `alpha` **0.9997 -> 0.1863**
  (**5.4x**, the gate asks 2x); `log_std` **-0.0028 -> -1.5486** (**1.55**, the gate
  asks 0.5). On the instrument that caught PPO, **SAC is demonstrably training on the
  true corner-screen objective.** That is the mismatch entry 41 was built to remove,
  and it looks removed.
* **Q2 is flat so far.** Screen-feasible steps, first five chunks **78**, most recent
  five chunks **75** — **0.96x** against a 2x gate. Per-chunk it oscillates 7-31 with
  no trend, while sigma falls monotonically 0.70 -> 0.21. The policy is converging;
  it is not yet converging on *feasible*.

**This is the highest-value thing on the desk and it is not in these four briefs.**
Resuming costs ~15 500 steps at the measured ~1.94 s/step ≈ **8.4 h** — far cheaper
than the 50 h the entry budgeted at 7.18 s/step, because the two budget leaks were
fixed before the run. Everything below is worth less than finishing that run.

---

## 1. Question (b), taken first because it is short: **NO, and it strengthens the skip.**

Nothing here changes the layout-scope verdict in the 002 and 003 evals.

* **The tooling is unavailable.** ANAGEN is Infineon-internal. The thesis is a report
  on a framework we cannot run, which is a weaker position than ALIGN — whose
  `ALIGN-pdk-sky130` port at least exists and has a documented entry point.
* **It calibrates the size of what we would be skipping.** Four successive
  floorplanning engines plus a routing flow, 137 pp, a PhD funded by an industrial
  partner. Read against 17 remaining days, this makes the ALIGN spike look *less*
  attractive, not more.
* **But it is a better citation than proposal 003's survey.** 003 is a secondary
  source; this is primary, with 20 industrial use cases and specific numbers —
  routability **+73.4 %**, layout time **-67.3 %** vs manual, mean area **-8.3 %** vs
  manual. **Cite Basso for the "layout automation is real and measured" claim; keep
  ALIGN as the named future-work tool** (it is the one with a SKY130 path).

**One genuinely useful import from §4, and it converges with two other evals.** The
*shape* of the headline claim — **time-to-produce versus a manual baseline, on a set
of real cases** — is exactly what our abstract promises and what our benchmark table
lacks. `g1_handdesign.cir` exists and G1 passed, but it has **never been re-measured
on SKY130 and has never appeared in the benchmark table with designer-hours
attached** (`CONTINUE_HERE.md` §6.3 row 10). That row is now pointed at by three
independent sources: 001 (a place to put the gm/ID negative), 003 (AutoCkt's
positioning), and this thesis (the presentation template). **Three pointers at one
missing table row is a strong signal to write it.**

---

## 2. Question (a) — the four techniques

### 2.1 Action masking — **SKIP.** The trade is already measured at eight operating points, and the decision not to mask is already made and pinned by a test.

The brief asks the right question: *masking only pays where invalidity is predictable
a priori.* The repo has a measured, two-sided answer.

**Yes, the dominant invalid mode IS predictable — and we already exploit it.**
`experiments/prescreen.py` rejects **84.3 % of the G44 population — 488 of the 579
designs with no interior peak at all — before any simulation** (`BASELINES.md` §5).
That is the class session 17 measured as **78 % of everything its policy found**
(G65), inside a 26.54 % invalid rate. So "prevent rather than gate" is **not a third
option we have not considered — it is implemented, as a soft screen.**

**The difference between Basso's mask and our screen is the error asymmetry, and
`BASELINES.md` §5 states it in as many words:**

> A rejected design is gone from the run for good; a falsely accepted one costs one
> simulation and is then caught by the evaluator.

which is precisely why the accept window is S3's window **widened**. A hard mask is
the **zero-widening row of a ladder we have already printed**:

| widening | free rejection | false rejection | effective S3 yield |
|---|---|---|---|
| 0.00 / 0.0 — **this is masking** | 85.2 % | **15.75 %** | 76.4 % |
| **0.40 / 2.0 — chosen** | 61.7 % | **0.39 %** | 34.9 % |

**Masking costs 15.75 % of the designs that actually meet S3, permanently and
unrecoverably.** The chosen row is the decision not to mask, taken against a stated
rule (*the smallest widening whose measured false-rejection rate is ≤ 1 %*) and
pinned by `test_margins_follow_the_stated_rule`, which fails if the constants are
hand-edited — the defence against CLAUDEwa §8 rule 6, since a widening is a
spec-tightness heuristic.

**The mechanism-level reason the technique does not transfer.** Basso masks on
non-overlap and spatial constraints over a discretised 32×32 grid: invalidity there is
an **exact geometric fact, computable in closed form, zero error**. Ours would mask on
a **predictor whose `f_peak` MdAPE is 4.93 % at design conditions and 15.85 % at
benchmark conditions**, with false rejection degrading **0.39 % -> 3.88 %** — ten times
its 1 % design budget (`CONTINUE_HERE.md` §6.2 item 9, an open disclosure item).
**Masking with an exact oracle is free; masking with an errorful predictor removes
good designs from reachability forever.** That is not a tuning matter.

**A second, sharper reason: G72 forbids masking the other half of the invalid
region.** Our invalidity is not one thing. `rl/evaluator.py` returns three verdicts,
and **HEADROOM_ONLY** — device in triode — is a *trustworthy measurement of a bad
circuit*, deliberately **graded** rather than floored, because `tail_saturation` binds
on **2.6-13.3 % of the box** so a fresh policy lands there often and *"a flat floor
there gives it no direction out; a graded band does"*. Measured on design 432:
**-10.0 -> -8.746**, strictly ordered at 1 / 10 / 50 / 100 / 300 / 1000 mV of triode
depth. **Masking that region would destroy exactly the gradient G72 was built to
create** — for that band, masking is not a third option beyond gate-and-penalise, it
is a regression to the flat floor G72 removed.

**Where masking could genuinely pay — and it is already deployed in the safe form.**
Output swing is a priori predictable: entry 37's surrogate gives **4.7 % median
error, rho 0.993, no SPICE**, and swing compression is **95-99 %** of all rejections
(entries 32, 36). Two things follow, both already recorded:

* Entry 38 put swing into the **reward** and **accept rate did not move** — failures
  migrated to `S3_peaking_match` / `S3_f_peak_match`. Masking on the same quantity
  has no reason to behave differently.
* Entry 41 **already uses the surrogate as a start filter** (predicted headroom
  ≥ 0.9 V) — masking at the *reset distribution* rather than the action space. That
  is the cheap, reversible form of the idea, and the live log shows it working:
  **1 811 of 1 859 warm starts filtered.**

**Verdict: skip.** The idea is implemented where it is safe, measured where it is
not, and forbidden by G72 where it would hurt.

### 2.2 Beam search at inference — **ALREADY BUILT AND MEASURED.** Adopt the convergence as a report claim; the tunability half is blocked on a decision already on the list.

`exp_hybrid.scan_topk` **is** a beam over the proposer at inference with no
finetuning: it scores the top k candidates on the same 4-corner screen and records the
rank of the first feasible one. Measured, entry 32:

    accepted_at_k = [1, 4, 5, 5, 6, 6, 6, 6]
    k = 5 optimum     A = 6 of 16     35.6 % fewer simulations   (k = 1 saved 5.8 %)

**The brief says the beam-vs-simulator-call trade "needs measuring, not assuming."
We measured it, and one run produced the whole curve** — including the flat region
from k=5 that a k=1-then-k=8 pair would have missed. The downside was registered in
advance: a deployed k=8 proposer pays **32 decks per miss**, so if depth did not help,
k=8 would have been strictly worse than k=1.

**The convergence is the reportable part and it costs nothing.** Basso reports
5-85 % improvement across metrics from an inference-time beam over a trained policy,
without finetuning and without a GPU. We report **35.6 % fewer decks** from an
inference-time beam over a retrieved proposer, without finetuning. **Two unrelated
domains, same structural finding: the inference-time beam is where the cheap gain
is.** One line in the report, one in the deck.

**The user-set-weights half is blocked, by the same thing that blocks 001 §2.2.**
Re-weighting objectives at inference — "favour peaking here, favour power there" — is
a direct fit for our automation-and-tunability framing, but `target_peaking_db` is
accepted by `reward_v1.margins` and **deliberately ignored**, so one design scores
identically against targets of 3, 5, 7.5, 10 and 12 dB and **the spec manifold is
effectively 1-D** (`CONTINUE_HERE.md` §5 OPEN item 5). **You cannot re-weight at
inference against an objective that ignores the weight.** Making it live moves every
published reward number — a §7f re-run event, and rule 6.

Note this is now the **second** proposal whose most attractive piece is blocked on
that one open decision (001 §2.2 was the first). That is worth telling the owner: the
1-D manifold is not just an awkward fact about our results, it is the gate on two
independent external ideas.

### 2.3 Pretrain a reward predictor, reuse it as the state encoder — **SKIP for 15 Sept.** The convergence is worth a deck line; the change is not worth making now.

**The convergence is real and is the best thing in this section.** Basso trains an
R-GCN supervised to predict placement reward, freezes it, and reuses it as the
encoder feeding the agent's state. The mentor-supplied ISCAS 2026 direction (ensemble
surrogates + OOD discriminator) points at the same structure from an unrelated domain.
**Two independent works converging on "learn a predictor of the objective, reuse it as
representation" is worth a line in the deck**, exactly as the brief says.

**We have the ingredients and they are free.** 74 526 designs with rewards sit on
disk, and the methodology is proven here — entry 37's swing surrogate hit rho 0.993
on a transfer split (trained on non-SAC designs, tested on the 245 the policies
invented).

**Three reasons to skip anyway, in increasing order of force:**

1. It changes `rl/env.py`'s observation encoder — not a §7f re-run event on its own
   (a new arm invalidates no published baseline), but it needs a fair comparison
   built, and that is days.
2. Expected value is low on the measured record: this improves representation
   learning for an RL agent that has been measured **worse than a zero-simulation
   lookup twice** as a proposer — 1 of 16 (entry 36) and 0-1 of 16 (entry 38) against
   the library's 6.
3. **It would confound entry 41, which is the cleanest RL measurement this project
   will ever get.** Entry 41 exists to remove *the last mismatch*, and its decision
   rule names the prize: *"Q1 and Q2 hit, Q3 and Q4 miss -> the authoritative
   negative. Every mismatch anyone has named — analytic-vs-SPICE, reward blindness,
   nominal-vs-corner, cold starts, coarse steps — has been removed and measured."*
   **Adding a sixth mismatch-fix mid-stream forfeits that result.** Finish the run,
   then consider the encoder.

The censoring caveat also travels with any surrogate here: entry 37's labels are
recorded only where a design compressed, so the high-headroom region a policy would be
steered toward is **absent by construction**.

### 2.4 Dense partial reward plus terminal reward — **SKIP**, and there is a reason beyond the re-run cost.

The cost reason first: `reward_v1.py` may not be touched without an owner decision
(CLAUDEwa rule 6; G111 names it specifically), and doing so is a §7f re-run event
that moves every published reward number with 17 days left.

**The more interesting reason is that this would not fix the defect it looks like it
fixes.** Basso's per-step reward is *the negative increase in the proxy metrics caused
by that action* — a difference of potentials, i.e. potential-based in form.
**Potential-based shaping is policy-invariant by construction: it changes learning
speed, not the optimum.** G102's defect is that the *objective itself* is flat —
within 0.001 of the best score the population spans **8.4x in tail current**, and the
delivered operating point was drawn from a plateau rather than chosen. **Shaping that
preserves the optimum preserves the plateau.** The fix G102 names is an **added
term**, which is a different change; the zero-simulation version of it is already
`CONTINUE_HERE.md` §6.2 item 8 (lexicographic re-score of the 74 526 designs on disk).

**And density already exists where it was measured to matter.** Our reward is not a
bare maximin — G72 gives it four exactly-separated bands, and the HEADROOM_ONLY band
is a **graded** dense signal precisely in the region a fresh policy actually lands
(2.6-13.3 % of the box). The idea is implemented where the evidence said to implement
it.

What dense shaping would genuinely buy is faster learning — and see the 001 eval
§2.3: our RL is statistically **indistinguishable from uniform random search at every
budget from 150 to 2 400 simulations**. Reaching the same null faster is not a result.

---

## 3. §3's convergent limitation — the free win in this brief

Both fRL-AD (001 §5) and this thesis (§3) name **weighted-sum scalarisation** as their
known weak point, and both name multi-objective RL as future work.

**We do not use a weighted sum. We use a maximin** — chosen so a satisfied spec cannot
mask a failing one. So the report line writes itself, and it is a *design decision
with measurements on both sides*, which is the strongest kind:

> Two independent groups, in unrelated domains, name the scalarisation we did not
> choose as their known limitation. We chose maximin instead. Its own cost is measured
> and stated: it gives no credit for exceeding a met spec, so the objective goes flat
> — `S5_noise` binds 0.0 % and `S6_power` 0.6 % of the time across 33 214 feasible
> designs, and within 0.001 of the best score the population spans 8.4x in tail
> current (G102).

Cost: one paragraph. Blast radius: none. This is the single best value-per-line item
in the brief.

---

## 4. Verdicts

| Piece | Verdict | Why |
|---|---|---|
| 2.1 Action masking | **SKIP** | Implemented as a soft screen (84.3 % of G44 rejected pre-sim); the mask row of the ladder costs **15.75 %** false rejection; predictor error 4.93-15.85 % vs Basso's exact geometry; **G72 forbids masking the graded triode band**; the safe form (start filtering) is already live in entry 41 |
| 2.2 Beam at inference | **ALREADY BUILT** — adopt the convergence as a report claim | `scan_topk`, k=5, **35.6 % fewer decks**, curve measured. Tunability half blocked on the 1-D manifold (§5 OPEN item 5) |
| 2.3 Pretrained reward predictor as encoder | **SKIP for 15 Sept**; deck line for the convergence | Would confound entry 41, the cleanest RL measurement available |
| 2.4 Dense partial reward | **SKIP** | Potential-based shaping preserves the plateau it is hoped to fix; `reward_v1.py` is rule-6 + §7f; density already present in G72's graded band |
| §3 scalarisation convergence | **DO** | One paragraph, zero risk, turns a design choice into a defended one |
| §4 presentation template | **DO** | Third independent pointer at the missing designer-hours benchmark row |
| §1, §5 layout content | **SKIP** | ANAGEN unavailable; cite Basso for the layout-automation claim, keep ALIGN as the named future-work tool |

---

## 5. Strongest argument against these verdicts

**Against SKIP on 2.1 — and this is the best counterargument in the file.** Everything
above equates *masking* with *tightening the pre-screen to zero widening*, and that
equation is not obviously right. Basso masks **per-step, in the action space,
conditional on the current state** — the admissible set is recomputed after every
placement. Our pre-screen is a **one-shot filter on a whole candidate design**. Those
are different objects: a state-conditional mask can forbid *the step that would enter
triode* while leaving the triode region reachable by other routes, which is not the
same as deleting 15.75 % of the feasible set, and it does not obviously conflict with
G72 either — G72 says grade the region you *land in*, not that every path into it must
stay open. A reviewer wanting masking would say we refuted a strawman by measuring the
wrong instrument, and that `MAX_STEP = 0.05` in entry 41 is already a crude,
state-independent version of the same idea. **The honest answer is that a
state-conditional action mask has *not* been measured here and the ladder does not
settle it** — what settles it for 15 Sept is that building one means touching
`screen_env.py` mid-run, which forfeits entry 41.

**Against SKIP on 2.3.** The argument "RL loses to a lookup twice, so do not improve
RL" is close to circular, and entry 41's own existence contradicts it — we are
currently spending ~13 h of SPICE precisely because the previous losses were
attributed to *fixable mismatches* rather than to RL. If reward-blindness and
nominal-vs-corner were worth removing, representation quality is a candidate for the
next named mismatch, and 74 526 labelled designs make it nearly free. The counter is
purely about sequencing, not merit: measure entry 41 clean first, or the negative it
was built to produce is worthless.

**Against DO on §3's scalarisation line.** Someone hostile would note that maximin is
not obviously *better* than a weighted sum — it is a different scalarisation with a
different, measured pathology (G102's plateau, and the flatness is arguably worse for
search than a weighted sum's mis-weighting, since a plateau gives an optimiser no
gradient at all). Presenting "we chose maximin" as an answer to their limitation
risks a judge replying that we chose a different problem, not a better solution. **The
paragraph should therefore claim only what is measured: that we made a different
choice and that we quantified its cost — not that we avoided the limitation.**
