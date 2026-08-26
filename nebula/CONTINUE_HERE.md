# CONTINUE_HERE.md — the brief for the next agent

**Updated 2026-08-20 at the end of session 22u.** The 22s version's headline —
*"11 of 11 rows PASS at 135 points"* — **has been retracted.** It was measured
on the coarse frequency lattice; on the corrected instrument that design passes
10 of 11. Read §4, which is now the outcome rather than the warning. Everything
else in the 22s brief stands.

**24 days to the 15 Sept deadline. Demo 25 Sept at BITS Goa.**

> **2026-08-26 (session 28, LATEST). THE DFE QUESTION IS ANSWERED: the ideal
> 1-tap DFE is NOT load-bearing.** Entry 39, 5 of 5. The CTLE meets **both** eye
> rows at all 45 mandated corners **and** all 135 points **with the DFE removed
> entirely** -- 358.5 mV against a 100 mV floor (3.6x). Deleting the tap costs
> **2.9 %** of the eye; a 4-bit or 20 %-misadapted tap is indistinguishable from
> ideal. **Transistor-level DFE sizing stays OUT of scope for a measured
> reason.** The report says the narrower true thing: the compliance result does
> not rest on the DFE being ideal. Read `PROGRESS.md` section 5m.

> **2026-08-26 (session 28, LATEST -- SUPERSEDES EVERY BLOCK BELOW). THE
> SWING-AWARE REWARD RAN. The fix worked and it did not pay: 0-1 of 16 against
> the non-RL library's 6.** Entry 38, 4 of 6.
>
>     library (control)   6 of 16   [1,4,5,5,6]   med measured swing  595 mV
>     swing_random        0 of 16                                    1154 mV
>     swing_seeded        1 of 16                                    1162 mV
>
> **Every mechanism prediction hit.** Headroom nearly doubled, swing failures
> fell **96 % -> 28 %**, and the designs became *measurable* -- scorable corners
> **0.30 -> 2.84 of 4**, where the library's candidates are so compressed SPICE
> cannot score them 90 % of the time. **Accept rate did not move.** Failures
> shifted to **`S3_peaking_match` / `S3_f_peak_match`**: more bias current and a
> bigger load buy headroom *and move the poles*, so the policy paid for headroom
> with shape accuracy, and the corner screen charges for shape accuracy.
> **Fixing the blind spot exposed the next constraint** -- a single missing
> quantity was not the whole story, and **D9's condition remains unmet**.
> **`SWING_W` is NOT to be re-rolled** (G110, registered in advance): the
> binding constraint is no longer swing. What is left is row **4q** and it is
> **the owner's**: a reward scoring headroom AND shape *at corners*, or more
> training steps. Read `PROGRESS.md` section 5l, then entry 38's OUTCOME.
> **Coverage (7 of 16) and compliance (11 of 11 at 45 of 45) are untouched.**

> **2026-08-26 (session 28, LATEST). THE SWING SURROGATE PASSES -- entry 37,
> 4 of 4.** Output swing is predictable from the design vector with **no
> SPICE**: **4.7 % median error, rho 0.993** on the transfer split (trained on
> non-SAC designs, tested on the 245 the policies invented), 2 228 labelled
> designs harvested from every sweep. **So the fix stage 3 identified is now
> minutes of training instead of ~17 h**, and it is row **4p**: a swing-aware
> reward, retrain, re-measure accept rate against the same 6-of-16 bar.
> **NOT STARTED -- a reward-set change is the owner's decision** (standing
> rule 6). Two caveats that travel with it: **Q4 is a qualified hit** (AUC
> 0.794, CI [0.722, 0.854], only 18 designs have ever passed the screen), and
> **the training data is CENSORED** -- limits are recorded only where a design
> compressed, so the high-headroom region a policy would be steered toward is
> absent by construction. The surrogate **predicts**; `link/calibration.py`
> still **decides**, and `is_surrogate: true` is stamped on the artifact.
> Read `PROGRESS.md` section 5k, then entry 37's OUTCOME.

> **2026-08-26 (session 28, LATER -- THIS SUPERSEDES THE SESSION-28 BLOCK
> BELOW). STAGE 3 RAN AND THE ANSWER IS NO: SAC as a proposer scores 1 of 16
> against the non-RL library's 6 of 16.** Entry 36, 5 arms at k=5, 1 600 decks,
> 17.9 min, scored **5 of 6**.
>
>     library (control)      6 of 16   [1,4,5,5,6]   <- reproduced entry 32 EXACTLY
>     sac_random_analytic    2 of 16
>     sac_random_finetuned   0 of 16
>     sac_seeded_analytic    1 of 16
>     sac_seeded_finetuned   1 of 16
>
> Started on the library's own top-5 designs, the policy **kept 1 of the 6
> acceptances retrieval found by itself**. The mechanism was registered in
> advance: **95 % of all rejections are output-swing compression, and the
> reward the policy was trained on has no swing row.** One honest exception,
> n = 1: `S-finetuned` solved request 0, which the library could not answer at
> any rank. **Q5 missed and it is the most useful miss in the run** -- the SPICE
> fine-tune entry 35 measured as an improvement made the policy a WORSE
> proposer (analytic-only 2, fine-tuned 0), producing twice as many designs
> whose response cannot even be fitted. **D9's condition is NOT met by SAC as a
> proposer.** The three options -- retrain on a reward containing swing, move
> SAC inside the search as a refiner and measure decks-to-feasible, or ship
> retrieval + CMA-ES with the RL arm reported as a measured negative -- are
> **all the owner's decision**, and none permits touching tolerances, the
> screen or `reward_v1.py` (G111). Read `PROGRESS.md` section 5j, then entry
> 36's OUTCOME, then G127. **Nothing about coverage (7 of 16), compliance
> (11 of 11 at 45 of 45) or the 35.6 % deck saving changed.**

> **2026-08-26 (session 28) — READ THIS FIRST, IT SUPERSEDES EVERY BLOCK BELOW
> ON THE RL TRACK. `nebula/SESSION_27_HANDOFF.md`'s "immediate job" IS DONE:
> `exp_sac_finetune.py` RAN at full budget (53.1 min) and entry 35 scored 3 of
> 5. The policy SURVIVED the SPICE transfer that erased PPO.**
>
> `log_std` **-1.7788 -> -2.0902** (sigma 0.169 -> 0.124) and `alpha` flat at
> 0.075, where PPO came back at its initialisation (`-0.097..+0.063`). SPICE
> mean return over the 16 held-out targets went **-24.101 -> -19.012 on 465
> decks against 470** — 13 of 16 improved, paired median +8.0, sign test
> n = 16 two-sided **p = 0.021** — **but return variance more than doubled,
> 210.7 -> 497.0.** The body moved up; the tail got heavier. Absolute return is
> still **-19.0** with only **1 of 16** targets positive: it improved, it is
> not good. `_verdict()` printed the committed Q1-and-Q3 branch: **G114 is
> solved, not merely avoided — proceed to stage 3.**
>
> **Stage 3 is the only thing that discharges D9:** SAC as `exp_hybrid`'s
> proposer, measured on **accept rate against the non-RL baseline of 6 of 16**
> (entry 32, 35.6 % fewer decks). **Pre-register it before running it, and
> pre-register WHICH checkpoint proposes** — `sac_policy_analytic.pt` or
> `sac_policy_finetuned.pt` — because the fine-tuned one won the body and lost
> the tail, and accept rate is tail-sensitive. **Nothing from `exp_sac_gate` or
> `exp_sac_finetune` may be quoted as compliance or coverage: both score 5 of
> 13 rows.** Read `PROGRESS.md` §5i, then entry 35's OUTCOME, then G126.
> Mandated 45-corner coverage is unchanged at **7 of 16**; the ~90-minute full
> sweep still needs the owner's say-so; **20 days to 15 Sept, and the report
> does not exist.**

> **2026-08-22 (session 26c) — READ THIS FIRST: the lever the block below
> recommends does not exist. The one that replaced it RAN, and the answer is
> that the free proposal is good enough 6 times in 16, not 1 — the old number
> was measuring how DEEP it looked, not what the library holds.**
>
> Session 26b's closing recommendation (row 4h, repeated in the blockquote below)
> was *"rank the library on swing headroom too — the pool already carries
> `pair_margin_v` / `tail_margin_v`, so it costs zero simulations."* **That was
> asserted without being checked, and it is false.** `pair_margin_v` /
> `tail_margin_v` are DC operating-point headroom (`vds - vdsat`); the screen
> rejects on `vout_swing_v`, a **measured 1 dB compression point** that needs a
> swept simulation. **The pool has no swing field.** Separately, **no** nominal
> channel separates the 1 accepted design from the 14 failures — it has *less*
> pair margin than 12 of them and *more* power than 13 of them — and with n=1 in
> the positive class no ranking rule could be validated anyway. **Row 4h is
> withdrawn.**
>
> **What replaced it, and why it needs no model.** The k=1 scan's real defect was
> not its criterion — it was that **it looked at one candidate**. The library
> holds **2066–17478 in-tolerance candidates per request** (median 4986), a
> request's **top 8 are genuinely different designs** (nominal power spans
> 3.3x–11.9x, up to **0.98 apart** in the normalised [0,1] box, all 8 distinct),
> and **depth is nearly free in target match** (`dev` across ranks 1–8 stays
> under **8 %** of tolerance). So: `exp_hybrid.scan_topk` scores the top **k=8**
> on the same 4-corner screen and records the **rank of the first feasible one**.
> **512 decks, ~12 min** against 13 718 for the plain search. One run gives the
> whole hit-rate-vs-k curve for k=1..8, and its **k=1 column re-measures entry
> 31's 1-of-16 rather than assuming it**.
>
> **Informative either way** — a high hit rate means the library does hold
> corner-robust designs and yields ~128 labelled candidates (the first dataset a
> ranking could be *fitted* on; entry 31 had one positive); a low one kills the
> retrieval line cheaply and says the SAC proposer must **generate**, not
> retrieve. **The downside is stated in advance: a deployed k=8 proposer pays 32
> decks per MISS, so if depth does not help, k=8 is strictly WORSE than k=1**
> (2.4 % saving vs 5.78 %).
>
> Pre-registered as **`PREDICTIONS.md` entry 32** — central estimate **A = 6** of
> 16, predicted range **3 ≤ A ≤ 10**, three-branch decision rule pre-committed.
> **27 gates in `nebula/tests/test_hybrid_topk.py`, 15 of 15 sabotages fired.**
> `exp_coverage.library_candidates` is **not modified** (`choose_start` seeds the
> search from it), and `scan_topk` writes a **third** artifact so it cannot
> overwrite entry 31's (G113).
>
> **RAN, 315 s, exit 0. All 6 predictions HOLD and `A = 6` is the central
> estimate exactly.** `accepted_at_k = [1, 4, 5, 5, 6, 6, 6, 6]` — 128 candidates
> scored, **7 feasible / 5 infeasible / 116 unscorable**, and **115 of the 116
> (99.1 %) are still output-swing compression**. Entry 31's rank-1 proposals
> reproduced **bit-identically 16 of 16**, so entry 31's numbers stand — it is the
> *reading* of them this withdraws.
>
> **`k = 5` is the optimum, not the k=8 the run was configured at**: same `A = 6`
> for 120 fewer decks (260 vs 380), implying **8 834 decks against the search's
> 13 718 — 35.6 % saved**, where k=1 saved 5.8 %. The curve is flat from k=5, so
> ranks 6-8 buy nothing. This is what "one run yields the whole curve" was for; a
> k=1-then-k=8 pair would have missed it. **`DEFAULT_TOPK` is left at 8** —
> changing a constant on the run that measured it is tuning, and needs its own
> pre-registration.
>
> **The decision rule fires at `A >= 5`: retrieval is ALIVE**, so row **4k**
> (fit a ranking on the 128 labels, 7 positives) unblocks, and **the bar for SAC
> is now 35.6 %, not zero** — which is why the control was measured first. What
> this does **NOT** say: `A = 6` is not "6 of 16 meet spec", it is "6 of 16 got a
> usable *starting* design for free". Mandated-corner coverage is still **7/16**
> (entry 30) and this run does not move it. The
> ~90-minute **full sweep still needs the owner's say-so** — `A >= 5` makes it
> defensible, not authorised.
> New gotchas **G124** (`design_id` does not join across artifact boundaries —
> bit-identical sizing, different ids; the failure mode is a silent *empty* join
> that reads as a real finding) and **G125** (a sabotage that passes and a gate
> that cannot distinguish its own bug are the same thing — one of these gates was
> worthless while looking thorough). Read `PROGRESS.md` **§5h**, then entry 32.
> **Tests: 1861 passed, 11 deselected.**

> **2026-08-22 (session 26b) — stage 0 is built, committed, pre-registered AND
> measured. `PREDICTIONS.md` entry 31 scored 5 of 5, and the answer is that the
> free proposal is almost never good enough.** The SAC track began after the owner
> stopped the coverage/unclip line (entry 30 scored 2 of 5).
> `NEXT_AGENT_SAC.md` §4's stage 0 is `nebula/experiments/exp_hybrid.py` —
> propose a design, score it on the live 4-corner screen, deliver it if feasible,
> **else run today's CMA-ES search unchanged**. The proposer is the
> zero-simulation **library lookup**: the **control** a future SAC policy must
> beat. 28 tests, no SPICE.
>
> **The scan (`--proposals`, 16 requests, 64 decks, 250.4 s): 1 accepted /
> 1 measured-but-infeasible / 14 unscorable.** All **14 of 14** unscorable rows
> name the same physical cause — the output swing the signal needs exceeds what
> the stage can deliver linearly (needed 343.5–2179.8 mVpp vs available
> 112.2–1225.4 mVpp), and 13 of the 14 fail at **4 of 4** screen points. The
> library's answers are right on the axis it ranks on and cannot swing at the
> corners.
>
> **DO NOT run the ~90-minute full sweep without asking.** Entry 31's
> pre-committed rule fires against it: `n_accepted = 1` is `<= 1`, so the sweep
> would spend 90 minutes confirming arithmetic already known (the search is
> **budget-bound** — both prior sweeps cost *exactly* 13 718 decks — so the only
> saving is skipping requests, and at 1 acceptance that is 793 decks = 5.78 %).
> Coverage is predicted unchanged at 7/16 ±1. **It remains the owner's call.**
>
> Read `PROGRESS.md` **§5g** (result), **§5f** (what was predicted, unedited),
> entry 31's OUTCOME, and gotchas **G122–G123**. Two open items came out of it,
> both needing a human decision first: **row 4h** — the library ranks on target
> match and ignores swing headroom entirely, so a swing-aware re-ranking costs
> zero simulations but **redefines the control**; and **row 4i / G123** — the
> "zero simulation" lookup re-reads the whole 74 526-row pool *per call*
> (`load_pool` has no cache), which is 89–161 s of that 250.4 s. No result
> depends on G123 — every claim is in decks, not seconds.
>
> **↑ Row 4h in that last paragraph is WITHDRAWN — see the 26c block above. The
> pool has no swing field.** Everything else here stands.

> **2026-08-22 — the search-ranking fix is committed AND its sweep has run.**
> `nebula/experiments/search_score.py` fixed a plateau that made four coverage
> requests unrankable, and it worked: all four runaway peaks came home from
> 8-12 GHz to ~2 GHz. **But the mandated coverage number went 8/16 -> 7/16 and
> `PREDICTIONS.md` entry 30 scored only 2 of 5** — the aggregate improved
> (+27 % corner passes) while the binary all-45 metric fell by one. Read
> entry 30's OUTCOME, `PROGRESS.md` **§5e**, and gotchas **G120-G121** before
> concluding anything about it. The next lever is **reachability**, not scoring.

This file is the *entry point*, not a substitute for `HANDOFF.md`. It tells you
where the project stands, what changed in the last four sessions, what is
decided, what is open, and exactly what to do next.

---

## 0. Read in this order

| # | File | Why | Time |
|---|---|---|---|
| 0 | **`nebula/SESSION_26_HANDOFF.md`** then **`nebula/SESSION_25_HANDOFF.md`** | **read FIRST — 26 is the state of the uncommitted-then-committed stage 0 work; 25 is the reasoning behind the search-score fix** | 15 min |
| 1 | **this file**, §§1–9 | the situation and the direction | 20 min |
| 2 | `CLAUDEwa.md` §§1–3, §7, §8 | the contract, the spec table, the gates, the standing rules | 20 min |
| 3 | `HANDOFF.md` §9 gotchas **G100–G123** | the twenty-four traps found in the last seven sessions | 30 min |
| 4 | `nebula/PREDICTIONS.md` entries **18–23**, then **30–31** | how this project makes claims; **22 and 23 are session 22u's retraction and re-run**; **31 is stage 0, pre-registered and not yet scored** | 45 min |
| 5 | `nebula/CHANNEL_MODEL.md` §§6, 8 + the DFE table | **four measured results that are NOT in the report** — see §6.3 | 20 min |
| 6 | `nebula/BASELINES.md` §§13, 14 | the benchmark and the budget ladder | 20 min |

**Do not skim 3 and 4.** The gotchas are the highest-value-per-line thing in
the repo. `PREDICTIONS.md` is the discipline that makes the results worth
anything: **pre-register, commit, then run.** Recent entries include several
scored misses, one of which falsified an instruction given by the owner's own
reviewer — those are the asset, not an embarrassment.

---

## 1. The situation in 90 seconds

Two things changed the shape of the project since the last rewrite.

**The eye is no longer blocked.** For months, S8 could not be evaluated on the
delivered design at any corner: the stage is driven past its linear limit, so
the small-signal fit the eye rests on stops describing it. Session 22q measured
*why* — `linear input range at f = linear range at DC / |H(f)/H(0)|`, because
`Cs` shorts out the same `Rs` the linear range is made of, so **peaking and
drive handling are one knob read in opposite directions** (G103). Session 22r
then found designs in the same box whose eye computes at all 135 points. The
cause was never the circuit: **`V1_SPECS`, which every published search scores,
contains S3 and not S8, and the sets containing S8 had never been searched on.**
Session 22s asked for both at once and reported **11 of 11 rows passing at 135
points**. **Session 22u retracted that** (§4): it was scored on the coarse
frequency lattice, and so was the objective that found it. The eye result is
real and got better — the re-run's design measures an eye at **135 of 135
points, 368.8–497.3 mV** — but **no design currently meets all eleven rows at
all 135 points**, and the gap is 0.0076 octaves of centre frequency.

**The reward's real defect is the opposite of the one everyone assumes.** It is
a maximin, so exceeding a met spec buys nothing — `S5_noise` binds **0.0 %** of
the time and `S6_power` **0.6 %** across 33 214 feasible designs. What it does
instead is go **flat**: within 0.001 of the best score the population spans
**8.4× in tail current** (G102). The delivered operating point was drawn from a
plateau, not chosen. **The lever is an added term, not a removed one**, and
that has been measured but not yet exploited (§6.2 item 3).

RL is unchanged and still a null: **statistically indistinguishable from
uniform random search at every budget from 150 to 2400 simulations**, while
CMA-ES is separably better at every one. Session 22n closed 97 % of the gap by
fixing an objective/termination mismatch and it still did not win.

---

## 2. Gate status — honest

| Gate | Due | Criterion | Status |
|---|---|---|---|
| G0 | 2 Aug | toolchain runs four analyses | **passed** |
| G1 | 3 Aug | hand reference meets S3–S7 at TT | **substantially passed** (`device/spice/g1_handdesign.cir`, generic BSIM4 1.2 V card — **never re-measured on SKY130 and never in the benchmark table**) |
| G2 | 20 Aug | one full evaluation end to end | **PASSED** (`G2_RESULTS.md`) |
| G3 | 3 Sep | RL beats random **and** grid at TT | **FAILS one clause of two.** Grid clause MET (separable win, 22n). Random clause NOT met — indistinguishable, not a loss |
| G4 | 12 Sep | corner-robust design generated and verified | **MET** 2026-08-20, 23 days early, and **re-confirmed on the corrected instrument in 22u**. Found by uniform random, not by the policy. Note it is `V1_SPECS` (7 rows); the **eleven**-row claim does not hold for any design — §4.5 |
| G5 | 15 Sep | submitted | — |

**Both competition deliverables exist:** `python -m nebula.design` (specs in,
schematic + specs out) and `python -m nebula.llm` (natural language wrapper,
with a grounding guard). The report exists:
`nebula/report/Nebula_CTLE_Report.pdf`, 12 figures, rebuilt from run artifacts
by two commands.

---

## 3. What sessions 22q–22s established

**Read §4 first.** 3.3 below is retained as written and is partly retracted.

### 3.1 The linear-range mechanism (22q, G103)

Every swing limit in the repo was **output-referred**, so the S8 blockage read
*"output swing 903 mVpp exceeds the linear limit 333 mVpp"* — true, and
requiring the reader to divide by a gain they must look up.
`SwingLimits.linear_in_pp_v` now reads the same compression sample on the input
axis, in the same units as the transmitter's swing. On the delivered design at
135 points:

    linear input range at DC        504 /  520 /  560 mVpp
    linear input range at NYQUIST   153 /  172 /  219 mVpp
    link drive at the CTLE input              535 mVpp
    OVERDRIVE                      2.44 / 3.11 / 3.49 x

**At DC it is 1.03× over — essentially at its limit. All of the blockage is the
3.07× de-rate, and the de-rate is the peaking.**

### 3.2 The front, and the two half-designs (22r)

1 590 simulations across the box, filtered to designs actually meeting S3
(band **and** 1.25–2.5 GHz window **and** positive Nyquist boost — filtering on
peaking alone selects **wideband attenuators**, G104). The attainable linear
range at Nyquist hovers around **1.0× the drive** across the whole band.

That produced two half-designs — one meeting S3 at 135/135 with no computable
eye, one meeting S8 at 135/135 and failing S3 — and the observation that
**nothing had ever asked for both**.

### 3.3 The joint search (22s)

`V4_SPECS` = the eleven competition rows with S4 asked at the **operating
point** (2.5 GHz, 535 mVpp) rather than its stated 100 MHz / 200 mVpp.
`exp_joint_search.py`, local CMA-ES seeded at 22r's most linear S3-valid
design, 400 simulations.

| | delivered | joint winner, **as reported in 22s** |
|---|---|---|
| rows passing at 135 points | 9 of 11 | ~~11 of 11~~ → **10 of 11** (22u) |
| rows failing | 0 | ~~0~~ → **1**, `S3_f_peak` at 6 of 135 |
| eye measurable at | 0 of 135 | **98 of 135** |
| eye height / width | — | 377.1–539.4 mV / 0.844–0.875 UI |
| HD3 @ 2.5 GHz, 535 mVpp | −17.4 dBc **FAILS** | **−42.7 dBc** |
| peaking / power | 9.78 dB / 2.16 mW | 6.37 dB / 6.56 mW |

**Struck through rather than deleted, per rule 10.** The eye numbers stand; the
row counts were scored on the lattice and §4 has the corrected ones. All 37
eye gaps are at corners the 3-corner screen has no member of, 27 at VDD 0.95 —
the **fourth** measurement of that blind spot, and 22u made it five.

### 3.4 Tunability, which contradicted its own framing (22s)

Eight bank settings holding `Rs × Cs` constant on the **total** resistance so
the zero does not move (flat at 177.0 MHz to four figures), switch `Ron`
**measured** at 16.50 Ω rather than quoted. Result: `k` moves **2.5×** while
the linear input range at the signal band moves **1.25×, non-monotonically**.
**The tuning control does not trade drive for equalisation** — the `k`s cancel
at the signal band. What sets drive handling is the fixed part, chosen once.

### 3.5 The speed-up number the brief's success criterion asks for (22r)

**3 402 000 simulations, 92 hours** for a genuine full factorial against a
**measured** 41.12 s for `python -m nebula.design --method cmaes` — **8 086×**.
Levels are **derived**, not chosen: `1 + ceil(sensitivity / 0.0664386)`, the
`ac dec 50` spacing. Labelled an extrapolation and a lower bound throughout.

---

## 4. THE LATTICE DEFECT — FIXED, and it retracted a headline

The 22s brief carried this section as a live defect and a warning. Session 22u
fixed it, and the fix changed a published result. **This is now the first thing
to understand about the project's compliance numbers.**

### 4.1 What was wrong (G108)

`verify_full()` — the 135-point compliance matrix every S8 result and every
margin number is reported on — read `pt.f_pk_hz`, the raw `ac dec 50` peak,
while `verify()` **in the same file** scored the interpolated one. And
`exp_joint_search.evaluate_joint`, the **objective the joint search was steered
by**, did the same. Those were the only two sites in the repository that
hand-built `f_peak_oct`, and they were exactly the two code paths that bypass
`evaluator.evaluate`.

**S3's 1.2500 GHz floor falls between two lattice samples** — 1.202264 and
1.258925 GHz, with nothing in between — so **a true peak anywhere in
[1.230269, 1.250000) GHz is reported as 1.258925: a failing design rounded into
a passing one, across a 1.6 %-wide band of frequency.**

The controlled A/B, one design, one flag, same six points:

    ac_peak_interp=False   +12.0205  FEASIBLE    f_peak 1.2589 GHz
    ac_peak_interp=True     -0.0147  INFEASIBLE  f_peak 1.2437 GHz

**15.2 MHz of reading error decided a shipped result.** Over 135 PVT points the
lattice returns **15 distinct `f_peak` values; the parabola returns 135** — the
matrix was binning the whole corner sweep into fifteen buckets, which is why it
reported a **six-way exact tie** at its own minimum margin.

### 4.2 What it retracted

Session 22s's *"11 of 11 rows PASS at 135 points, zero failures"* is **10 of 11**
on the corrected instrument, with `S3_f_peak` failing at 6 of 135. The search
was then re-run on the corrected objective (`PREDICTIONS.md` entry 23):
**400 simulations, zero feasible designs, best −0.0006.**

### 4.3 The finding underneath, and it is the good one

For the re-run's best design, over 135 points:

    f_peak                                  1.2568 - 2.5132 GHz
    that PVT span                           0.99977 octaves
    S3's frequency window                   1.00000 octaves    <- 99.98 % FULL
    slack at the bottom / overflow at top   0.00783 / 0.00760 oct
    room left after a PERFECT re-centring   0.00023 oct

**PVT spread fills 99.98 % of S3's frequency window.** A compliant design exists
with two hundredths of one per cent of an octave to spare; this one misses it by
**0.0076 octaves = 0.53 % in frequency**. One lattice step is 0.0664 octaves —
**nine times the entire error being corrected**, which is why the reading had to
be right. *"Our margin is thin"* is properly *"the window is exactly as wide as
the process makes the quantity vary."*

(22t's *"97.9 % of the window"* could not be reproduced by any method and is
superseded by the measured 93.8 / 96.1 / 100.0 / 102.2 % above and in
`PREDICTIONS.md` entry 22.)

### 4.4 And the search did not fail — it solved the problem it was shown

It drove its worst **screened** corner to **−0.000576**, four decimal places
from feasible. **Three of the four real failures are at `sf`, a process corner
the 3-corner screen has no member of**, and the true binding point is
`sf`/1.05/0C at **−0.015150 — twenty-six times worse than anything the search
could see.** Fifth measurement of that blind spot, and **the first with the
correction quantified**: 0.0076 octaves, well inside what `cs` delivers at a
measured 3.243 oct/box. That makes §5 OPEN item 2 the highest-value decision on
the list.

### 4.5 Where S9 actually stands

**There is no design meeting all eleven rows at all 135 points.** Two miss by a
hair, in opposite directions, on the same row:

| | `57cba07581cd` (delivered) | `c507a3ba6f58` (re-run) |
|---|---|---|
| rows PASS / FAIL / NOT MEASURABLE | **9 / 0 / 2** | **10 / 1 / 0** |
| min normalised margin | **+0.021015** (+2.1 %) | **−0.015150** (−1.5 %) |
| binding point | `S3_f_peak` fs/0.95/125C/78fF | `S3_f_peak` sf/1.05/0C/14fF |
| eye | **not measurable anywhere** | **135 of 135**, 368.8–497.3 mV, 0.844–0.891 UI |

**G4 still stands**: it was `verify()` on `V1_SPECS`, which has always used the
interpolated peak, and the delivered design passes 135 of 135 there. What does
not stand is the eleven-row claim.

## 5. Decisions — made, and OPEN

### Made and recorded

| Decision | Where | Consequence |
|---|---|---|
| Do not build the hard-constraint reward flag | owner, 22r | It measures as a **no-op**: identical feasible set, 210 of 33 214 rewards move, best design unchanged. Recorded as a falsified external prediction, `PREDICTIONS.md` entry 18 |
| `i_bias` box stays 0.5–8 mA | owner, 22r | VDD is **1.8 V**, not 3.3; the ceiling is already S6's limit (8 mA × 1.8 V = 14.4 mW) |
| Ship the input-referred linear-range measurement | owner, 22r | Done; in the 135-point checklist at zero extra simulation cost |
| Order: report fixes → joint search → tunability → RL last | owner, 22s | Done through tunability |

### **OPEN — human only. Do not decide these.**

1. **Which design ships — and it is now a real trade, not an artifact.**
   §4.5 has the table. `57cba07581cd`: S3 passes at 135/135 with **+2.1 %**
   margin, **no measurable eye anywhere**. `c507a3ba6f58`: eye passes at
   **135/135** (368.8–497.3 mV), S3 **fails at 4/135** with −1.5 % margin.
   Neither is eleven-for-eleven. **A third option now exists and may be the
   right one: spend ~400 more simulations with `sf` and a low-VDD member in the
   search screen** (OPEN item 2), because §4.4 measured that the correction
   needed is 0.0076 octaves and the search is already at −0.000576 on the
   corners it can see. *The report's cover conflation is fixed and every
   compliance cell is now loaded from an artifact.*
2. **Extend the search screen with a mixed (`sf`/`fs`) and a low-VDD (0.95)
   member? — NOW THE HIGHEST-VALUE DECISION ON THIS LIST.** **Five** independent
   measurements: 8/135 (`G4_RESULTS.md`), 23/135 and 45/135 (`design.py`),
   37/135 (22s), and **4/135 in 22u where three of the four failures are at
   `sf` and the search had driven its screened worst case to −0.000576.** It is
   no longer "the screen has a blind spot"; it is **"the screen's blind spot is
   the only thing between this project and an eleven-row design, and the gap is
   0.0076 octaves."**
   **Cost:** more corners per design changes the benchmark's per-design cost,
   so keep the *benchmark* screen and the *delivery* screen separable or you
   trigger a `BASELINES.md` §7f re-run of every published arm.
3. **The compression decision, open since session 16** — `HANDOFF.md` §8 lists
   three routes (reach below S3's 3 dB floor; declare the low-loss end of the
   channel family out of scope; re-derive the `rl` range downward) and none has
   been chosen through four sessions and one full report. **An unmade decision
   reads as a defect; a made one reads as engineering.**
4. **Does the RL contribution claim survive?** `PLAN.md` §8 lists the
   spec-conditioned policy as first to cut. Session 22j measured that a lookup
   over already-simulated designs serves 32 of 32 held-out targets and that
   **50 random designs serve 100 % of them**. See §6.2 item 5 for the one
   experiment that could still produce an affirmative result.
5. **Should `target_peaking_db` become live?** It is accepted by
   `reward_v1.margins` and **deliberately ignored**, so one design scores
   identically against targets of 3, 5, 7.5, 10 and 12 dB. **The spec manifold
   is effectively 1-D**, which is why a lookup table is the optimal policy.
   Making it live would make the problem genuinely 2-D — and would move every
   published reward number (a §7f re-run event).

---

## 6. What to do next

An external review of the shipped PDF against `HANDOFF.md` produced a task
list. **I verified its load-bearing claims against the repo on 2026-08-20.**
Two premises are wrong (§4 above, and "there is no human reference point" —
`g1_handdesign.cir` exists and G1 passed). The rest is accurate. The ordering
below is mine, after that verification.

### 6.1 Do first — cheap, and one is a correctness bug

1. ~~**Fix `verify_full` to score the interpolated peak**~~ — **DONE, session
   22u**, and it retracted a headline (§4). The same defect was in
   `exp_joint_search.evaluate_joint` and was found by the gate written for the
   first one. `nebula/tests/test_verify_paths_agree.py` (14 tests) pins the
   seam, including `test_no_hand_built_f_peak_oct_anywhere_in_the_package`.
2. **Report numbering and cross-references.** Figures 6 and 7 each appear
   **twice**, and the sequence is out of document order
   (1, 2, 7, 3, 4, 5, 6, 6, 7, 8, 9, 10). "section 5a" does not exist. Three
   "section 9" cites now point at the amortisation section because session 22s
   added two sections and did not renumber. **Session 22s caused this.**
   Renumber from a single source of truth; add a test that numbers are unique
   and contiguous and that every internal cross-reference resolves.
3. **Point `llm/grounding.py`'s numeric-literal checker at report prose.**
   **Still open, and now much better motivated.** The three stale literals 22t
   found are corrected and the whole compliance table is generated (22u) — but
   a hand-typed number **stated a retracted result for a day**, which is the
   argument in one sentence. A miss must **fail the build**, not repair the
   text. Add a red-gate test that injects a wrong literal. Demoable: the
   grounding checker turned on its own report.
4. ~~**Fix the cover conflation**~~ — **DONE, 22u.** Both cover lines name one
   design and are read from its artifact, and the retraction is a callout in
   the body. What remains is the owner's call on which design ships (§5 item 1).

### 6.2 High value

5. **Corner-aware RL at scale — deferred three times, now first.**
   `rl/corner_env.py` is built and tested (10 tests, ngspice smoke passed) and
   has never been run. Session 22j identified the asymmetry that makes this the
   only defensible niche left: *a lookup provably cannot answer corners,
   because the pool is P1-only by construction.* Three arms on **worst-corner
   reward at held-out spec targets**: corner-conditioned PPO, library lookup
   (blind to corners by construction), fresh CMA-ES per spec.
   **Pre-register bands, falsifiers, and an explicit statement of what result
   would make us drop the RL contribution claim entirely.** Report either way —
   a completed negative beats a deferred one.
   **Also decide and record:** `CLAUDEwa.md` §7 says *reward* on the worst
   corner, not *observe* it. If the policy is to generalise across corners it
   may need corner context in the observation. `which_corner_binds()` is the
   first evidence.
6. **Write up the four measured results that never reached the report.** This
   is the best value-per-hour in the project — all four are already measured
   and sitting in `CHANNEL_MODEL.md`:
   * **DFE sufficiency.** Across 21 channel members a 1-tap DFE is sufficient;
     a second tap buys **14.7 %**; a twenty-tap DFE still leaves 31 %, because
     **31.2 % of the residual sits beyond 20 UI** — the √f algebraic tail,
     exactly what decision feedback is worst at. **This derives the mandated
     S2 topology rather than assuming it**, and it is the most
     analog-engineer-legible result in the repo. Today the DFE appears once, in
     a box in Figure 1, which is what invites *"did you actually do the DFE?"*
   * **The burden mismatch.** The mandated −3.5 dB TX de-emphasis is worth
     exactly 3.5 dB of the CTLE's job, so the required burden across the family
     spans **−0.5 … +8.5 dB**. **The top 3.5 dB of S3's range is never called
     for.** The delivered design sits at 9.78 dB — *outside the maximum burden
     the link ever needs*. It compresses because it is over-equalising a
     channel that needs less. Section 11 reports the failure without the cause.
   * **The channel construction.** `IL_dB(f) = A√f + B·f`, so **loss at DC is
     exactly 0 by construction** — which is what puts near-full TX swing at the
     CTLE input at low frequency, which sets the 535 mVpp drive, which fails S4
     and blocks S8. The construction and the failure are causally linked and
     the report presents only the failure. Add an **eye and HD3 vs channel
     loss** sweep.
   * **State plainly, currently buried:** S8's 100 mV vertical is met with the
     CTLE *attenuating* by 13–15 dB. **The eye-height spec was never binding.**
7. **Rescope the RL section to what was measured.** The report attributes the
   null to G100 (terminate-on-success vs a metric rewarding overshoot) — true
   and incomplete. The deeper cause is §5 OPEN item 5: the spec manifold is
   **1-D**, and on a 1-D manifold a lookup table *is* the optimal policy, which
   is exactly what the amortisation section measured. Write the claim as
   *"RL confers no advantage over random search on a 1-D spec manifold at
   d = 7, on this objective, at the budgets tested — and here is where the
   crossover would have to be"*, **not** the unscoped implication that RL does
   not work for analog sizing, which we cannot support and which reads as the
   project failing its own title.
8. **Harvest the maximin plateau — zero simulations.** Re-score the **74 526
   designs already on disk** through `spec_pool` with a lexicographic
   tiebreak: maximise `min(margin/tol)`, then minimise tail current among
   designs within ε of the maximum. Report the power reduction at unchanged
   compliance. Pre-register the expected reduction. This **executes** G102's
   "the fix is an added term" claim rather than describing it.
9. **Disclose or re-fit the pre-screen.** At benchmark conditions its
   false-rejection rate is **3.88 %** — ten times its 1 % design budget — and
   `f_peak` MdAPE is **15.85 %**. Six of twelve benchmark arms are `+screen`,
   including `cmaes+screen`, the arm behind the 8 086× headline, and the report
   says nothing. Prefer a re-fit: 457 valid rows exist in
   `baselines_pilot.jsonl`, `prescreen.accuracy_from_log()` is the measurement
   to beat, and the mechanism the numbers point at is the `I_D = i_bias/2`
   assumption, which is 4–8 % optimistic against the real mirror (session 13);
   `solve_bias` already takes `mirror_efficiency`. Pre-register the expected
   improvement. If the re-fit does not land, **put the caveat in the benchmark
   section and mark every screened arm.**

### 6.3 Worth doing, lower priority

10. **The hand-designed baseline as a benchmark row.** Not "we had no human
    baseline" — G1 passed and `g1_handdesign.cir` exists. What is missing is a
    **SKY130 re-measurement** of it and a row in the benchmark table with
    designer-hours attached. Natural home for the gm/I_D work
    (`GMID_MAP.md`), which is built, tested and unwired; note honestly that its
    stated mechanism was **falsified** (38.07 % device vs 37.74 % design
    coordinates) and its real benefit was **1.16×** on simulations per valid
    design. That honesty is an asset here.
11. **Report restructure**, leading with an **executive summary + hard
    compliance matrix** (spec / requirement / measured / PVT points passing /
    minimum normalised margin) on page one. Two framing rules: **lead with the
    measured number, not the extrapolated one** — *"spec in, PVT-verified
    transistor-level schematic out, in 41 seconds"* is unimpeachable while
    8 086× is an extrapolation we ourselves label as such, so it belongs in
    the benchmark section rather than the cover; and **every claim currently
    phrased as an apology gets a decision or a cause attached** — rigour that
    only ever points inward reads as a project that beat itself.
    **Sequence this after item 3**, so the grounding checker catches stale
    numbers introduced during the move.
12. **Demo capture:** `nebula.llm` → schematic → specs → verification.

---

## 7. Commands

```bash
conda activate nebula          # ngspice 41; use ngspice_con.exe, NOT ngspice.exe (G20)
                               # the TEST SUITE runs on the SYSTEM python (conda env has no torch)

# tests — before and after ANY change, from the repo root.
# 1806 passed, 11 deselected, ~5 min (4m44s / 5m19s, 2026-08-22, system Python 3.13.14)
python -m pytest tests nebula/tests -q -m "not slow"

# the deliverables
python -m nebula.design --peaking 9 --f-peak 1.9e9 --robust --verify --out out/
python -m nebula.llm "I need about 9 dB of peaking with the peak near 1.9 GHz"

# the report: figures then PDF, both from run artifacts
python -m nebula.report.figures
python -m nebula.report.build_pdf

# session 22q-22s experiments
python -m nebula.experiments.exp_linear_pareto --run      # 1590 sims, ~9 min
python -m nebula.experiments.exp_hd3_amplitude --run      # 31 sims
python -m nebula.experiments.exp_sweep_cost --run         # ~90 sims + 2 timed design runs
python -m nebula.experiments.exp_joint_search --run       # 400 sims, ~15 min
python -m nebula.experiments.exp_joint_search --verify    # 135 points, ~0.8 min
python -m nebula.experiments.exp_g4_verify --full         # 135 points x N, ~2.6 min
python -m nebula.experiments.exp_tunable_trade --run --base joint   # ~20 sims

# the benchmark
python -m nebula.experiments.baselines --sweep --interp   # 25 500 sims, ~42 min
python -m nebula.experiments.baselines --analyse <log.jsonl>
```

**Measured throughput: 0.0977 s/simulation at 8 workers**, 0.176 s serial.
A full-fidelity 11-row evaluation at one corner is **0.557 s**.

---

## 8. Traps that still bite

**The standing ones:** G20 (`ngspice_con`, not `ngspice`), G26/G30 (ngspice
reports failures as warnings and exits 0 — parse and assert), G29 (`.spiceinit`
read at parse time from the cwd), G31 (instance W/L are plain numbers in
**microns**), G36 (use the trimmed library), G44 (a peak at the sweep edge is
fictitious), G70 (**one concurrent ngspice = 4.8× slower** — do not run
experiments alongside the test suite; session 22r got a spurious
`test_pdk_trim` failure exactly this way), G71 (the first configuration pays
the cold cache).

**The eight from the last four sessions — all in `HANDOFF.md` §9:**

* **G100** — an episode that terminates on the condition your metric rewards
  exceeding is two objectives, not one.
* **G101** — a spec set defined by **exclusion** grows silently.
* **G102** — a **maximin** gives no credit for exceeding a spec, so "the
  optimiser bought margin" cannot be true of it. **Before removing a term from
  an objective, measure how often it BINDS.** A term binding 0 % of the time is
  already inert.
* **G103** — the peaking spec and the linear input range are **one knob**, and
  every swing limit was reported at the wrong end of the stage.
* **G104** — a constraint set that drops one clause selects a **different
  circuit family**. Filtering on peaking alone admitted a 19.95 GHz wideband
  attenuator that looked 3× more linear, and CMA-ES optimised into the same
  hole.
* **G105** — a finite difference on a **quantised** signal reports the quantum.
  Four of seven axes returned exactly one lattice step with **zero spread**;
  worth **1 296×** on the headline. **The tell is the zero spread.**
* **G106** — `A + (new,)` is a claim that every member of `A` is still
  measurable by whatever will score the result.
* **G107** — **"cannot be scored" is not "fails."** Collapsing them either
  kills a search or fakes a pass. Grade the invalid band by evaluability;
  **never loosen the gate.**
* **G108** — **a QUANTISED measurement rounds a marginal failure into a pass**
  whenever the spec threshold falls between two samples. S3's 1.2500 GHz floor
  sits between the `ac dec 50` samples 1.202264 and 1.258925 GHz, so every true
  peak in a **1.6 %-wide band** was reported as passing. **The tell is cheap:
  count the distinct values** — 15 across 135 PVT points where the refined
  reading gives 135. Same family as G105.

**Three process mistakes worth not repeating:**

* A scripted splice into `report/figures.py` matched the wrong anchor and
  deleted **five figure functions** (22s). Recovered only because the file had
  been committed minutes earlier. **Commit often; prefer a unique anchor or the
  edit tool over index-based splicing.**
* Writing a session's counters into the report **before** running the suite —
  1664 was written, 1653 was measured. Run first, then write.
* Pre-registering after a debug run has been seen. If it happens, **disclose
  the debug run in full inside the entry** (entry 19 does this).

---

## 9. Rules you must follow

1. **Update `HANDOFF.md` in the same commit as any change.** A change without a
   handoff update is incomplete.
2. **Run the suite before and after.** `python -m pytest tests nebula/tests -q
   -m "not slow"` — **1806 passed, 11 deselected, ~5 min** (measured 2026-08-22).
   Report the count both times. Never commit with failures.
3. **Pre-register anything whose result could be argued for afterwards.**
   `PREDICTIONS.md`, with acceptance bands and falsifiers, **committed before
   the run**. Record misses as misses. **Nothing above an outcome heading is
   ever edited.**
4. **Every new gate is deliberately broken, watched go red, and restored** —
   and say so in your report.
5. **Never fabricate a number.** A missing artifact raises; it does not get a
   placeholder. This applies to prose as much as to plots.
6. **ngspice's exit code is not a success signal.** Parse the output and assert.
7. **Do not modify without an explicit human decision:** `common/params.py`,
   `rl/contract.py`, `rl/env.py`, `V1_SPECS`, the box, the tolerances, the
   pre-screen. **Wrap, do not replace** — `rl/corner_env.py` is the precedent.
8. **Do not change `V1_SPECS`.** Anything that shifts `B = N + 1` invalidates
   every published reward, the +8.950669 ceiling, the whole `BASELINES.md`
   ranking and the G4 verdicts. New spec sets are **new tuples defined by
   enumeration**, never by exclusion (G101) and never by addition to another
   set without checking every inherited member (G106).
9. **Do not loosen the pole-zero fit residual limit** to make the eye
   evaluable. Session 22s established that this would make every downstream eye
   number unfounded.
10. **Do not delete** the unfiltered linear-range front, the failed
    predictions, or any retraction. **The misses are the asset.**
11. **Do not report a nominal design as corner-verified, or an extrapolation as
    a measurement**, anywhere.
12. **Do not let the LLM wrapper near the optimiser.** The grep test stays.
13. **You may not decide anything in §5's OPEN list.** State the options with
    the measured numbers behind each and ask.
14. Windows: no non-ASCII in `print()`; run pytest from the repo root.
15. Commit as `Jai Kaushik <jaikaushik-prog@users.noreply.github.com>` (G12).
    **The repo is PRIVATE and must stay private** (G1).
16. **If a task contradicts a measurement you make, stop and report the
    contradiction** rather than proceeding. Two items in the review that
    produced §6 did exactly this and the measurement won both times.

---

## 10. What is new on disk since the last rewrite

| Path | What |
|---|---|
| `device/sky130_runner.py` | `linear_in_pp_v` / `max_swept_in_pp_v`, `measured_linear_input_pp_v`, parameterised HD3 tone and amplitude |
| `experiments/exp_linear_pareto.py` | the attainable linear-range front, two arms, S3-filtered |
| `experiments/exp_hd3_amplitude.py` | HD3 vs amplitude at three tones |
| `experiments/exp_sweep_cost.py` | the 8 086× extrapolation, with derived levels |
| `experiments/exp_joint_search.py` | the S3+S8+HD3 joint search, `V4_SPECS` |
| `experiments/exp_tunable_trade.py` | the bank, and the `k`-cancellation |
| `rl/reward_v1.py` | `S4_hd3_nyq` tolerance row, `V4_SPECS` (V1–V3 untouched) |
| `experiments/baselines.py` | `CmaConfig.x0` — local seeding, used by nothing in `BASELINES.md` |
| `experiments/exp_g4_verify.py` | the drive-headroom row in the 135-point checklist |
| `report/figures.py` | `fig_hd3_amplitude`, `fig_sweep_cost`, `fig_tunable_trade`; Figure 1 fixed |
| `tests/test_linear_and_sweep_cost.py` | 19 tests |
| `PREDICTIONS.md` entries 18–21 | one falsified external prediction, three scored pre-registrations |
| `HANDOFF.md` §9 | gotchas **G102–G107** |
| **— session 22u —** | |
| `rl/evaluator.py` | `annotate_interpolated_peak`, `scored_meas` — **the one definition both verification paths and the joint objective now reach** |
| `experiments/exp_g4_verify.py` | `verify_full(ac_peak_interp=True)`; five per-point audit fields; the artifact states its own instrument |
| `experiments/exp_joint_search.py` | `--verify` (the 135-point checklist, promised since 22s and missing); the objective now scores the interpolated peak |
| `experiments/joint_verify_full_results.json` | **new** — the joint design's checklist, so the report stops typing it |
| `report/build_pdf.py` | every compliance cell **loaded**, the retraction callout, the 99.98 %-full-window table |
| `tests/test_verify_paths_agree.py` | 14 tests, four watched go red |
| `PREDICTIONS.md` entries 22–23 | the lattice defect, and the re-run: **7 hits, 5 misses across the two** |
| `HANDOFF.md` §9 | gotcha **G108** |

---

## 11. The one-paragraph version, if you read nothing else

**The compliance matrix was reading the peak frequency off a grid too coarse to
answer the question it was being asked, and fixing it retracted this project's
headline.** `verify_full` scored `pt.f_pk_hz` — the raw `ac dec 50` peak —
while `verify()` in the same file scored the interpolated one, and so did the
objective the joint search was steered by. S3's 1.2500 GHz floor falls between
two lattice samples, so **every true peak in a 1.6 %-wide band was rounded from
a fail into a pass**; on one design with one flag changed, `+12.0205 FEASIBLE`
becomes `−0.0147 INFEASIBLE`. Session 22s's *"11 of 11 rows at 135 points"* is
**10 of 11**, and re-running the search on the corrected objective found **zero
feasible designs in 400 simulations**. **That is a better result than a pass
would have been**, because of what it measured: over 135 PVT points `f_peak`
spans **0.99977 octaves against a specification window of exactly 1.00000** —
**the spread fills 99.98 % of the window** — so a compliant design exists with
0.00023 octaves to spare and the re-run misses it by **0.0076 octaves, 0.53 %
in frequency**. One lattice step is 0.0664 octaves, nine times that error,
which is why the instrument decided the verdict. **And the search did not
fail:** it drove its worst *screened* corner to −0.000576 while three of its
four real failures sit at `sf`, a corner the 3-corner screen has no member of —
the **fifth** measurement of that blind spot and the first with the correction
quantified. So the eye, unverifiable for months, is now measured and passing at
**135 of 135 points** on a design that misses S3 by half a per cent, while the
delivered design passes S3 at 135 of 135 and has no measurable eye at all.
**Nothing meets all eleven rows yet, the gap is one corner in a search screen,
and adding it is the highest-value decision on the list.**
