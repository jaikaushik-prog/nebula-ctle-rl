# ATTRIBUTION.md — where did the S3 rate go? 13.44 % against 7.10 % (D4)

**Session 22b, 2026-08-18.** Pre-registered as `PREDICTIONS.md` entry 8,
committed at **`b6fe85e`, before the run**.

| | |
|---|---|
| The experiment | `nebula/experiments/exp_attribution.py` |
| Tests | `nebula/tests/test_exp_attribution.py` (11) |
| Logged data | `nebula/experiments/attribution_run.jsonl` (tracked, G49) |
| One command | `python -m nebula.experiments.exp_attribution --run` |
| Free half | `python -m nebula.experiments.exp_attribution --definition` |

---

## 0. What a reader in a hurry needs

1. **The published baseline was measured at a load the design will never see.**
   Every row of `robust_geometry_data.csv` — the population behind 13.44 % —
   has **`cl` = 150 fF**, the legacy pin, **4.598×** `cl_mid` = 32.63 fF.
   `PLAN.md` D4 called it "the measured rate at `cl_mid`" and `BASELINES.md`
   §2 put it on the `cl_mid` row. Both were wrong, and both are corrected.

2. **The consequence is sharper than a mislabel.** D4 rejected the 13.54 %
   candidate because it was *"`cl` pinned at a load the next stage cannot
   present"* — and 13.44 % was measured at **that same load**. The stated
   discriminator between the recommended baseline and its rejected alternative
   **did not exist**.

3. **The S3 *definition* explains none of the gap.** Two rows (`prescreen`)
   and three rows (`reward_v1.V0_SPECS`, adding `S3_nyq_boost`) score the same
   population at **13.44 % and 13.44 %**. Zero designs die to the Nyquist row.
   *No simulation was run to establish this.*

4. **The load explains most of what is left, and the mechanism is G44, not
   design quality.** Moving only `cl` from 32.63 to 150 fF takes the S3 rate
   from **6.93 % to 11.40 %** (+4.47 points). But the S3 rate **among designs
   that are scorable at all** is **13.94 % against 13.91 %** — flat. What the
   load changes is the fraction of the box with no interior peak inside the
   20 GHz search window: **40.13 % invalid at `cl_mid` against 8.67 % at
   150 fF**, essentially all of it `peak_is_sweep_edge`.

5. **Drawn passives cost nothing measurable, and that does NOT contradict
   G66.** 6.93 % drawn against 6.60 % ideal, CIs overlapping heavily
   (13.94 % against 14.16 % conditional). G66 is a **per-design** shift of
   0.1329 octaves that moves designs both into and out of the window; the
   population rate is the wrong instrument for it. *A design-level effect and a
   population-level rate are different measurements*, and using the second to
   test the first is the error §6 records against my own prediction B.

6. **2.04 points remain unattributed and the reason is named, not guessed.**
   The mirror axis is **unmeasurable through the current evaluator** (G90), and
   the two populations do not share a validity definition (G64) or a sampler.

---

## 1. The four candidate causes, and what each was worth

Base: **13.44 %** published, **6.93 %** measured at sweep conditions in this
run (task 0 measured **7.10 %** [6.05, 8.31] on an independent seed — the two
agree, which is the replication this decomposition rests on).

| # | cause | worth | how measured |
|---|---|---|---|
| 1 | **S3 definition** (2 rows vs 3) | **+0.00 pts** | re-scoring the stored population, **no simulation** |
| 2 | **load**, `cl` 32.63 → 150 fF | **+4.47 pts** | one arm, 1500 sims |
| 3 | **drawn passives** (G66) | **+0.33 pts**, not significant | one arm, 1500 sims |
| 4 | **real mirror** (session 13) | **BLOCKED** | see §4 — G90 |
| | *residual* | **≈ 2.04 pts** | §5 |

---

## 2. Cause 1 — the definition, for free

`prescreen.s3_true` asks two questions (the `f_peak` window and the peaking
band). `reward_v1.V0_SPECS` asks three, adding `S3_nyq_boost > 0`. On the same
1890 designs:

```
prescreen s3_true, 2 rows      13.44 %      <- the published number
reward_v1 V0_SPECS, 3 rows     13.44 %      <- task 0's test
reward_v1 V1_SPECS, 7 rows     13.39 %      (tail row excluded, see below)
designs killed by the nyq row alone:  0
```

**The Nyquist row is free on this population**: any design with 3–12 dB of
peaking inside the window already boosts at Nyquist. So the two definitions are
interchangeable here and none of the gap is bookkeeping.

**The 7-row number carries an independent confirmation of session 22's
headline.** 13.39 % against 13.44 % means noise, power and the pair-saturation
margin cost **0.05 points between them** — reproducing *"reward v1 has one
active dimension where it advertises seven"* on a **different population**,
with **ideal** passives and an **ideal** tail. That finding is now measured
twice, on disjoint data, by different routes.

*The `tail_saturation` row is excluded rather than defaulted:* this population
has ideal current sinks and no tail margin was ever measured on it. Defaulting
it to 0.0 would read as "exactly at the boundary" and fail every row; any other
default would fabricate a measurement (rule 1). It is set to `+inf` with the
exclusion stated in the report dict itself.

---

## 3. Causes 2 and 3 — the two simulated arms

1500 simulations each, LHS over `rl.contract.ACTION_SPACE`, the same evaluator,
the same geometry mapping, the same S3 test (`margins_meet_s3`, imported —
rule 9). Each arm moves **exactly one** axis from the baseline
(`test_each_arm_moves_exactly_the_axis_it_names`).

| arm | `cl` | passives | **S3 / all sims** | 95 % Wilson | **S3 / scorable** | invalid |
|---|---|---|---|---|---|---|
| `cl_mid_drawn` | 32.63 fF | drawn | **6.93 %** | [5.75, 8.33] | **13.94 %** | **40.13 %** |
| `cl_legacy_drawn` | 150.00 fF | drawn | **11.40 %** | [9.89, 13.11] | **13.91 %** | **8.67 %** |
| `cl_mid_ideal_passives` | 32.63 fF | ideal | **6.60 %** | [5.45, 7.97] | **14.16 %** | 43.47 % |

### The mechanism, and it is not what "the load halves the yield" suggests

**The conditional rate is flat to three significant figures: 13.94 / 13.91 /
14.16 %.** The load does not make the box worse at meeting S3. It changes how
much of the box is *measurable at all*:

```
invalid at cl_mid  = 40.13 %   of which peak_is_sweep_edge   597 / 602
invalid at 150 fF  =  8.67 %   of which peak_is_sweep_edge   130 / 130
```

At the lighter load `f_p2` moves up, so **two fifths of the box has no interior
maximum below the 20 GHz search ceiling** and is rejected by the G44 guard
before S3 is ever tested. At 150 fF that population is one twelfth. **The
baseline difference is a statement about how much of the search space is
wasted, not about how good the reachable designs are.**

Two consequences worth carrying forward:

* It explains why this project's pre-screen measures a **3.60× S3 lift here**
  against the **2.60×** published (`DIFFICULTY.md` §4.4): at `cl_mid` there is
  far more G44 population for it to remove (session 18 measured it removing
  **84.3 %** of that population), so the same screen has more work available.
* **G65's "78 % of everything an RL policy finds is G44" is a property of the
  load as much as of the policy.** At the legacy pin it would have been a much
  smaller number.

### Cause 3 — drawn passives, and why the null result is not a contradiction

6.93 % drawn against 6.60 % ideal: a **+0.33 point** difference with CIs
[5.75, 8.33] and [5.45, 7.97] overlapping across almost their whole width, and
conditional rates of 13.94 % against 14.16 %. **No measurable effect on the S3
rate**, and the sign is the opposite of the one predicted.

**This does not contradict G66, and reading it as a contradiction would be the
error.** G66 measured a **per-design** `f_peak` shift of up to 0.1329 octaves,
always negative. A systematic shift moves designs *out of* the window at one
edge and *into* it at the other, so a population rate can be flat while a large
fraction of individual verdicts flip. G66's own consequence — that design 432's
0.12 octaves of centring slack is exceeded — is a claim about **one design**
and is untouched by this measurement.

**The honest statement is: drawn passives do not move the S3 *rate*; nothing
here says they do not move *which designs* pass.** Measuring that needs a
paired per-design comparison, which this experiment did not run.

---

## 4. Cause 4 — the mirror axis is blocked, and the block is measured

`rl.evaluator.validate` requires `vds_tail` and `vdsat_tail`. Ideal current
sinks do not produce those primitives at all, so `evaluate(..., real_tail=False)`
returns `invalid: vds_tail is missing from the ngspice output` for **every**
design — not a measurement. The ideal-tail arm cannot be run through the
identical validator.

That is **G90**, and it is pinned by a test that runs one design and reads the
reason back, so `TAIL_AXIS_BLOCKED` cannot drift from the behaviour.

**Unblocking it is a human decision**: it means changing what `validate` treats
as a failure, which is `BASELINES.md` §7f territory. Session 13 measured the
real mirror delivering **4–8 % less** than `i_bias/2`, so this axis is the
leading candidate for part of §5's residual.

---

## 5. What is left, and what it is not

```
published, session-11 population, cl = 150 fF          13.44 %
this run,  legacy load, drawn passives, real mirror    11.40 %
                                                       -------
residual                                                2.04 points
```

Three candidates, none of them measured, **listed rather than apportioned**:

1. **The mirror** — blocked (§4). Session 13's 4–8 % current deficit lowers gm,
   which moves `f_p1` and the peak.
2. **The validity definition.** The session-11 population is filtered by
   `has_interior_peak`, a **conjunction** that also rejects genuine but small
   peaks; this run uses `peak_is_sweep_edge` alone. **That is G64, and it is
   exactly the difference G64 exists to record.** The two denominators are
   therefore not the same quantity, and the conditional rates across the two
   populations (19.37 % session-11 against 13.91 % here) **must not be compared
   directly** — a comparison this file deliberately does not make.
3. **The sampler and the box.** `robust_geometry_data.csv` was not drawn by
   `baselines._lhs` over `rl.contract.ACTION_SPACE`.

**None of this makes 13.44 % a wrong number.** It is a correct measurement of a
different population at a different load under a different validity rule. It is
simply not the number a run of the current pipeline will produce, which is the
whole reason D4 moved.

---

## 6. The pre-registration, scored

`PREDICTIONS.md` entry 8, committed at `b6fe85e` before the run.

| | predicted | band | measured | |
|---|---|---|---|---|
| **A** — legacy-load arm | 12.5 % | 10.5–15.5 % | **11.40 %** | **HIT** |
| **B** — ideal-passive arm | 8.2 % | 7.0–11.0 % | **6.60 %** | **MISS** (below the band) |
| definition cost | 0 pts | — | **0.00 pts** | **HIT** *(established pre-run)* |

**B is a clean miss and the direction is the interesting part.** I predicted
drawn passives would cost ~1.1 points; they are worth **−0.33** and the
difference is not significant. The pre-registration named this case in advance:
*"If B comes back at or below 7.10 %, drawn passives make the problem easier,
which would contradict G66's stated direction and would be the more interesting
result."* It came back at 6.60 %. §3 explains why that is a population-versus-
design distinction rather than a contradiction of G66 — but the prediction was
wrong, and the reasoning behind it (treating a per-design octave shift as if it
predicted a rate change) was the wrong instrument for the question.

**Falsification condition 3 also fired, partially.** I warned the causes might
not sum. They do not: 0.00 + 4.47 + 0.33 = 4.80 points against a 6.51-point gap.
**The decomposition is reported as non-additive**, with the 2.04-point residual
named and its candidates listed, rather than presented as a closed budget.

---

## 7. What this changes

* **D4 is decided: 7.10 %.** `PLAN.md` §2 and `BASELINES.md` §2 corrected in
  the same commit; the superseded recommendation is struck through, not deleted.
* **Any future baseline quote must state its load.** `legacy_cl_f()` reads the
  load off the population file and **raises if the column is not constant**, so
  "the rate on that population" can no longer be quoted without one.
* **`BASELINES.md` §2's P2 row still says "~8 % (session 10d, at the legacy
  pin)"** — that number carries the same 150 fF caveat and has **not** been
  re-measured at `cl_mid`. On this file's evidence it is optimistic.
* **The G44 fraction is now a first-class property of a load**, and it is the
  quantity that actually moved: 40.13 % at `cl_mid` against 8.67 % at 150 fF.
