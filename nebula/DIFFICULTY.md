# DIFFICULTY.md — how hard is the problem the G3 sweep will run? (task 0)

> **The sweep has never been run, and the question is whether it can produce a
> separable result at all.** This file measures that instead of arguing it.

**Session 22, 2026-08-18.** Pre-registered in `PREDICTIONS.md` entry 7 and
committed at **`e8b9b25`, before the run**.

| | |
|---|---|
| The experiment | `nebula/experiments/exp_difficulty.py` |
| Tests | `nebula/tests/test_exp_difficulty.py` (15) |
| Logged data | `nebula/experiments/difficulty_run.jsonl` (tracked, G49) |
| Figure | `nebula/figures/difficulty.png` |
| One command | `python -m nebula.experiments.exp_difficulty --run` |
| Re-analysis | `python -m nebula.experiments.exp_difficulty --analyse nebula/experiments/difficulty_run.jsonl` |

---

## 0. What a reader in a hurry needs

1. **The pre-registered verdict is `IN_BETWEEN`, so the rule says STOP and the
   decision is a human's.** Median simulations to the +8.950669 ceiling is
   **221** unscreened and **68.5** screened, against a rule of "< 50 in either
   arm → the thesis holds; > 500 in every arm → it fails".

2. **The thesis splits in half, and the two halves point opposite ways.**
   *"S3 is trivial"* is **confirmed**: a first S3-meeting design arrives at a
   median of **7.5 simulations** unscreened and **3** screened. *"Random search
   reaches the ceiling in single-digit samples"* is **falsified by a factor of
   ~30**: it takes 221.

3. **The consequence runs AGAINST the brief's conclusion, and this is the
   headline.** The sweep's per-run budget is **150 simulations**
   (`baselines.BUDGET_SIMS`). Only **8 of 24** unscreened restarts (**33 %**)
   reach the ceiling inside it. So best-reward-at-budget does **not** saturate
   for two thirds of unscreened runs, and "every arm ties at the ceiling,
   nothing separable" is **not** what the arithmetic says. The screened arm is
   the one at risk: **18 of 24 (75 %)** reach it within 150.

4. **`PLAN.md` D4's recommended baseline does not reproduce.** The measured S3
   rate over 2000 simulations is **7.10 %**, 95 % Wilson **[6.05, 8.31] %** —
   and **13.44 % lies outside that interval**. This is
   `PREDICTIONS.md` entry 7's falsification condition 4 firing. D4 is a human
   decision and is **not** adopted here; §6 states the options.

5. **The other four V1 specs never bind.** Simulations-to-first-feasible equals
   simulations-to-first-S3 **exactly** (7.5 and 3.0), and the pooled feasible
   rate equals the pooled S3 rate **to the digit** in both arms (7.10 % and
   25.55 %). Noise, power and the two saturation margins cost nothing on top of
   S3. This settles `PREDICTIONS.md` entry 6's falsification condition 3 in the
   *opposite* direction to the worry it was written about.

6. **G74 is reconfirmed at 2.8x the evidence.** 9 ceiling ties on **9 distinct
   designs** unscreened, 16 on **16 distinct** screened — 25 designs, 25 ids,
   one reward to six decimals. The ceiling is a property of the AC grid, not of
   a lucky design, and no design in 4000 simulations exceeded it.

---

## 1. The question, and why it had to be asked first

The G3 sweep is specified, costed at ~12 h, and has never been run. Three
already-measured numbers suggested it could not separate its arms:

* random LHS meets S3 at **13.44 %** (`BASELINES.md` §5, `PLAN.md` D4);
* the reward **saturates at +8.950669** (G74) — a property of the `meas ac MAX`
  lattice, not of the circuit;
* one evaluation costs **0.28 s** (`G2_RESULTS.md` §3).

If random search reaches the ceiling in single-digit samples, every arm ties,
and `BASELINES.md`'s own CI-overlap rule then forbids reporting a ranking. The
sweep would be an expensive way to measure the AC grid.

**Nothing about the problem definition was changed to measure this.** Same box
(`rl.contract.ACTION_SPACE`), same sampler (`baselines._lhs`), same evaluator
(`rl.evaluator.evaluate`), same reward (`rl.reward_v1`, `V1_SPECS`), same rung
(P1: TT / 1.00 / 27 °C / `cl_mid`, drawn passives, real mirror).
`test_the_restart_loop_matches_method_lhs_exactly` asserts this module's loop
emits the **identical draw sequence** `baselines.method_lhs` does from the same
seed, so the measurement is of the sweep's own search and not of a lookalike.

---

## 2. Results — the waiting times

24 independent restarts per arm, 600-simulation budget each, ceiling-stopped.
Medians are **conditional on reaching**, with a 90 % percentile-bootstrap band;
censored restarts are counted and **never substituted** (`BASELINES.md` §3).

### Unscreened

| metric | reached | median | 90 % CI |
|---|---|---|---|
| **simulations to ceiling** | 22/24 | **221.0** | [142.0, 315.0] |
| proposals to ceiling | 22/24 | 221.0 | [142.0, 315.0] |
| **simulations to first S3** | 24/24 | **7.5** | [5.0, 15.0] |
| simulations to first feasible | 24/24 | **7.5** | [5.0, 15.0] |

Two restarts never reached the ceiling in 600 simulations. The full ordered
sample, because the spread is the point:

```
15  25  31  67  67  95 127 142 174 181 198 244
267 273 315 324 359 381 404 410 440 452   (+2 censored at 600)
```

### Screened (`experiments/prescreen.py` in front)

| metric | reached | median | 90 % CI |
|---|---|---|---|
| **simulations to ceiling** | 24/24 | **68.5** | [42.0, 117.0] |
| **proposals to ceiling** | 24/24 | **228.0** | [149.0, 390.0] |
| **simulations to first S3** | 24/24 | **3.0** | [2.0, 4.0] |
| simulations to first feasible | 24/24 | **3.0** | [2.0, 4.0] |

```
 5  14  15  25  25  38  40  40  42  45  48  57
80  86  90 117 128 129 163 181 188 195 211 241   (0 censored)
```

**Read the two rows of the screened table together.** In *simulations* — the
cost G65 defines and the axis the sweep is budgeted in — the screen is worth
**3.2x** (221 → 68.5). In *proposals* it is worth **nothing**: 221 → 228. The
screen does not find the ceiling with fewer tries; it finds it having paid for
fewer of them. That is exactly what a free filter is supposed to do, and
stating both stops the saving being read as search quality.

---

## 3. Results — the distributions (2000 simulations per arm, no early stop)

| | unscreened | screened |
|---|---|---|
| proposals | 2000 | 6645 |
| **free rejection** | — | **69.90 %** |
| **S3 rate** | **7.10 %** | **25.55 %** |
| feasible rate (all 7 V1 rows) | **7.10 %** | **25.55 %** |
| **ceiling rate, per simulation** | **0.45 %** | **0.80 %** |
| ceiling ties / distinct designs | **9 / 9** | **16 / 16** |
| invalid rate | 37.80 % | 26.35 % |
| invalid: `peak_is_sweep_edge` | 752 | 522 |
| invalid: `ngspice` | 4 | 5 |
| best reward seen | 8.950670 | 8.950670 |

Reward quantiles (the shape, not a summary — `figures/difficulty.png` has the
full ECDF):

```
unscreened   p0 -10.000  p25 -10.000  p50 -2.645  p75 -1.000  p95 +8.286  p100 +8.951
screened     p0 -10.000  p25 -10.000  p50 -1.000  p75 +8.021  p95 +8.784  p100 +8.951
```

**The distribution is not unimodal and a mean of it would be meaningless.**
37.8 % of unscreened simulated designs sit exactly on the invalid floor at
−10.0, a further ~55 % lie in the infeasible band, and 7.1 % jump to above
+8.0. There is almost nothing between 0 and 8 — reward v1's feasibility bonus
`B = N + 1` is a cliff by construction, and the measurement shows the cliff has
essentially no population on it.

---

## 4. What the numbers say about the sweep

### 4.1 The primary metric does NOT saturate at the sweep's budget

| | reach the ceiling within 150 simulations |
|---|---|
| unscreened | **8 / 24 = 33.3 %** |
| screened | **18 / 24 = 75.0 %** |

`BASELINES.md` §3 introduced simulations-to-ceiling *because* best-reward-at-
budget was expected to saturate. On this measurement, at 150 simulations,
**best-reward-at-budget is still a live discriminator in the unscreened arms**
and is close to saturated in the screened ones. Both metrics are worth
reporting and neither is redundant.

### 4.2 The ceiling rate is the S3 rate divided by the lattice, and that is now measured

The octave window holds **15** `ac dec 50` lattice points (session 11, G74), and
the ceiling requires `f_peak` on the single nearest one. If `f_peak` were
uniform over those 15 among S3-meeting designs:

| | S3 rate / 15 | measured ceiling rate | |
|---|---|---|---|
| unscreened | 0.473 % | **0.450 %** | agrees to 5 % |
| screened | 1.703 % | **0.800 %** | **2.1x off** |

**The unscreened agreement is close enough to call the mechanism confirmed.**
The screened row missing by 2.1x is the interesting one and §4.3 is about it.

### 4.3 The pre-screen may be discarding ceiling-capable designs — SUSPECTED, NOT ESTABLISHED

The screen lifts the S3 rate by **3.60x** (7.10 → 25.55 %) but the ceiling rate
by only **1.78x** (0.45 → 0.80 %). Since the screen can only *remove*
proposals, the per-proposal ceiling rate compares directly:

```
unscreened   9 / 2000  = 0.4500 % of proposals
screened    16 / 6645  = 0.2408 % of proposals
rate ratio 0.535, 95 % CI [0.236, 1.211]
```

Point estimate: the screen removes **46.5 %** of ceiling-capable designs.
**The CI spans 1.0, so this is a suspicion and not a finding** — it rests on 9
and 16 events. It is recorded because it is checkable, because it agrees with
§4.2's independent 2.1x, and because it is exactly the failure mode G76 already
caught this screen in once (*population rates transfer, accuracy does not*).
The measured S3-population false-rejection rates are 0.39 % at calibration and
3.88 % at benchmark conditions; a rate near 46 % on the *ceiling* population
would be a different order of thing, because the ceiling is a narrow target on
the same `f_peak` axis the screen filters.

**Confirming or killing this costs one pooled re-run at larger n and no new
code.** It is not done here.

### 4.4 The screen's population rates moved, in the direction that flatters it

| | `BASELINES.md` §5 (calibration) | session 18 (benchmark) | **here** |
|---|---|---|---|
| free rejection | 61.7 % | 63.9 % | **69.90 %** |
| S3 yield lift | 2.60x | 2.66x | **3.60x** |

Both are *larger* here. The base rate they multiply is *smaller* (7.10 % rather
than 13.44 %), so a bigger multiplier lands in the same neighbourhood:
34.94 % predicted against **25.55 %** measured.

---

## 5. The pre-registration, scored

`PREDICTIONS.md` entry 7, committed at `e8b9b25` before the run. **Six hits,
two misses.**

| # | predicted | band | measured | |
|---|---|---|---|---|
| 1 | unscreened median sims-to-ceiling **90** | 30–400 | **221** | **HIT** |
| 2 | screened median sims-to-ceiling **35** | 12–160 | **68.5** | **HIT** |
| 3 | unscreened median sims-to-first-S3 **5** | 3–12 | **7.5** | **HIT** |
| 4 | screened median sims-to-first-S3 **2** | 1–6 | **3.0** | **HIT** |
| 5 | unscreened ceiling rate **0.8 %** | 0.2–3 % | **0.45 %** | **HIT** |
| 6 | ≥ 2 **distinct** designs tied at the ceiling | — | **9 of 9** | **HIT** |
| 7 | S3 rate **13 %** | 8–20 % | **7.10 %** | **MISS** |
| 8 | verdict **`thesis_holds`** | — | **`IN_BETWEEN`** | **MISS** |

**Miss 7 is the important one** and it is falsification condition 4, fired: the
13.44 % baseline comes from `robust_geometry_data.csv`, a session-11 population,
and the sweep's own sampler and evaluator produce 7.10 % [6.05, 8.31].

**Miss 8 followed from miss 7 and from a compensating error I should own.** The
prediction reasoned "ceiling rate = S3 rate / 15" and got the ceiling rate
right (0.45 % measured against 0.8 % predicted, in band) **while getting the S3
rate that feeds it wrong by 1.9x**. Feeding the *measured* S3 rate through the
same arithmetic gives 0.473 % against 0.450 % measured — so the mechanism was
right and one of its two inputs was wrong, and the band held for the wrong
reason. That is worth more than the hit it produced.

**What the prediction got right that matters:** it said the verdict and the
reason would come apart, that the unscreened arm would sit "an order of
magnitude above single-digit samples", and that any `thesis_holds` would fire
off the screened arm rather than the unscreened one. All three hold; the
screened arm simply landed at 68.5 rather than under 50.

---

## 6. What this does NOT license, and what needs a human

* **It does not adopt a baseline.** D4 is a human decision (`PLAN.md` §2). The
  measured options are now: **7.10 %** (this run — the sweep's own sampler,
  evaluator and box, n = 2000, 95 % CI [6.05, 8.31]); **13.44 %**
  (`BASELINES.md` §5, session-11 population); **13.54 %** (G42, `cl` pinned);
  **8.73 %** (G42, `cl` searched). They are not the same measurement and the
  gap is not noise. **Ask before quoting any of them as the bar G3 must beat.**
* **It does not re-fit or re-tune the pre-screen.** D3. §4.3's suspicion is a
  reason to *measure*, not to change a calibration.
* **It does not touch `V1_SPECS`, the box, the tolerances or the evaluator.**
  `params.py`, `contract.py`, `env.py` untouched.
* **It is P1 only** — TT / 1.00 / 27 °C, one load, drawn passives. Nothing here
  says anything about corners; that is task 3 and gate G4.
* **It says nothing about any search method.** LHS only. It measures the
  *problem*, which is the point: a difficulty measurement that used a tuned
  optimiser would confound the two.
* **The two arms' pools are separate LHS streams**, so §4.3's per-proposal
  comparison assumes only that both sample the same box, which they do.

---

## 7. Cost, and the isolation rule

| | |
|---|---|
| total | **8394 simulations**, 2244.5 s of restarts + 978.0 s of pools |
| unscreened restarts | 6191 sims, 1627.6 s, **0.2629 s/sim** |
| screened restarts | 2203 sims, 616.9 s, **0.2800 s/sim** |
| cost probe, cold | **0.2537 s/sim** |
| smoke test, warm | **0.1665 s/sim** |

**Every number above was measured with nothing else simulating**, per G70 —
one concurrent ngspice costs 4.8x against the extended library, and this
evaluator draws real passives so it uses the extended library. The spread
between the warm 0.167 and the cold 0.254 is G71's ordering effect and is why
no single figure is quoted as *the* cost.

**One violation happened and is recorded rather than hidden.** The first launch
was wrapped in a `timeout` that would have killed the run mid-flight; stopping
it killed the shell but not its Python child, and a second run started
alongside the first — two concurrent ngspice drivers writing one log. Both were
killed by PID, the contaminated log deleted, the machine verified idle, and the
run restarted from scratch. **No number in this file comes from those runs.**

---

## 8. Open, in the order a next session should take it

1. **D4 — which baseline G3 must beat.** Blocked on a human. §6 lists the four
   measured candidates.
2. **§4.3 — does the pre-screen discard ceiling-capable designs?** One pooled
   re-run at larger n, no new code. If the 46 % point estimate survives, every
   screened arm of the sweep is biased against the metric the sweep reports.
3. **Task 1 — remove the ceiling at its source** (parabolic interpolation of
   the AC peak). Note that §4.1 weakens the *urgency*: the ceiling is not
   reached by two thirds of unscreened runs at budget. It does not weaken the
   *case*, because 25 designs still tie at exactly one number.
4. **Task 3 — the corner axis.** Nominal-only is now measured as reachable but
   not trivial; the corner-robust problem is where the search difficulty
   actually lives (~1 in 1890, session 10d/11).
