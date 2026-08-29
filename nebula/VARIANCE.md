# VARIANCE.md — run-to-run consistency, measured

**Session 29, 2026-08-29.** Zero new simulations: this re-reads
`experiments/baselines_run_interp.jsonl.gz`, the committed benchmark sweep.

| | |
|---|---|
| The analysis | `nebula/experiments/exp_variance.py` |
| Artifact | `nebula/experiments/variance_results.json` |
| Tests | `nebula/tests/test_variance.py` (10) — no SPICE, safe to run beside an experiment |
| One command | `python -m nebula.experiments.exp_variance --run` |

---

## 0. What a reader in a hurry needs

1. **Consistency is measurable here, and it was an open question.**
   `CONTINUE_HERE.md` §5 recorded that whether our variance-across-repeats is
   measurable at all was unknown. It is, from data already on disk.

2. **The methods separate on consistency far more cleanly than on quality.**
   At a 150-simulation budget on P1 every arm lands within **1.2 %** of the same
   mean reward, but their run-to-run spread differs by **22x**
   (`cmaes+screen` sd 0.0051 against `uniform` sd 0.1110).

3. **CMA-ES is 6.78x more consistent than uniform random search**
   (95 % CI **[4.29, 10.54]**), and GP-BO is **17.86x** [11.07, 35.59].

4. **The RL arm is the least consistent method once the pre-screen is applied,
   and it is NOT distinguishable from screened random search.**
   `ppo+screen` sd 0.0584 against `uniform+screen` 0.0421 — ratio 1.39x with a
   CI of **[0.48, 3.73]**, which spans 1.0. Against `cmaes+screen` it is
   **11.51x** more variable [4.31, 24.73].

5. **This matters beyond our own report.** Proposal 001's paper (fRL-AD) claims
   **variance reduction, not a better mean**, as its contribution over AutoCkt.
   That is the axis measured here, and on this problem our RL arm shows no
   advantage on it either — extending the existing "indistinguishable from
   random search" finding from the mean to the **spread**.

6. **The honest limits, stated before the numbers are used:** P1 saturates near
   a reward ceiling of ~8.95 so the means are compressed by construction; n is
   10–20 replicates per arm; and on the hard problem **nothing is consistent**
   (§4).

---

## 1. Why this was measured

Proposal 002 (Vikas Vijay, a practising analog designer) lists four criteria a
sizing tool must meet before designers adopt it. The fourth:

> Adoption follows several silicon revisions of predictable results.
> **Unpredictable output sends designers back to manual methods.**

Three of his four criteria are business arguments we cannot act on. This one is
an engineering property of our own tool, it costs no simulations, and we had
never measured it.

## 2. Method

Every replicate within a `(problem, method, prescreen, budget)` cell differs
**only in seed**. So the spread of `best_reward` across replicates *is* the
run-to-run variation a designer would experience from the same tool on the same
request.

Two filters, neither optional:

* **`role == "measured"`.** The sweep also logs `warmup` and `control` rows.
  `BASELINES.md` §7g excludes warmup from timing and G71 records that the first
  configuration pays the cold cache; including them leaks a timing artifact into
  a quality metric.
* **One problem at a time.** See §5 — pooling problems inflates the answer by a
  factor of 42 and does not look wrong.

Intervals are percentile bootstrap on the **ratio of standard deviations**,
20 000 resamples, fixed seed. A ratio interval containing 1.0 is reported as
*not distinguishable* rather than rounded into a claim.

## 3. The result — P1, 150 simulations, `role=measured`

| arm | n | mean | **sd** | CV % | min | max |
|---|---|---|---|---|---|---|
| `cmaes+screen` | 10 | 8.9946 | **0.0051** | 0.1 | 8.9856 | 8.9995 |
| `gp_bo` | 10 | 8.9936 | **0.0062** | 0.1 | 8.9818 | 8.9995 |
| `gp_bo+screen` | 10 | 8.9911 | **0.0079** | 0.1 | 8.9773 | 8.9999 |
| `cmaes` | 10 | 8.9753 | **0.0164** | 0.2 | 8.9556 | 8.9987 |
| `lhs+screen` | 20 | 8.9634 | **0.0231** | 0.3 | 8.9137 | 8.9957 |
| `uniform+screen` | 20 | 8.9653 | **0.0421** | 0.5 | 8.8413 | 8.9993 |
| `ppo+screen` | 10 | 8.9220 | **0.0584** | 0.7 | 8.7804 | 8.9859 |
| `ppo` | 10 | 8.8859 | **0.0654** | 0.7 | 8.7770 | 8.9632 |
| `lhs` | 20 | 8.9101 | **0.0805** | 0.9 | 8.6966 | 8.9896 |
| `uniform` | 20 | 8.8963 | **0.1110** | 1.2 | 8.6791 | 8.9993 |

**Read the mean column first, then stop reading it.** Every arm is within 1.2 %
of every other. The mean is nearly uninformative at this budget on this problem
because P1 saturates. **The sd column spans 22x**, and that is the finding.

### Head to head

| comparison | ratio | 95 % CI | |
|---|---|---|---|
| `uniform` vs `cmaes` | **6.78x** | [4.29, 10.54] | CMA-ES more consistent |
| `uniform` vs `gp_bo` | **17.86x** | [11.07, 35.59] | GP-BO more consistent |
| `ppo` vs `cmaes` | **3.99x** | [1.87, 6.20] | CMA-ES more consistent |
| `ppo+screen` vs `cmaes+screen` | **11.51x** | [4.31, 24.73] | CMA-ES more consistent |
| `ppo+screen` vs `uniform+screen` | 1.39x | **[0.48, 3.73]** | **not distinguishable** |

### The pre-screen tightens almost everything — and barely helps the policy

| method | sd off | sd on | |
|---|---|---|---|
| `lhs` | 0.0805 | 0.0231 | **3.49x tighter** |
| `cmaes` | 0.0164 | 0.0051 | **3.23x tighter** |
| `uniform` | 0.1110 | 0.0421 | **2.64x tighter** |
| `ppo` | 0.0654 | 0.0584 | 1.12x tighter |
| `gp_bo` | 0.0062 | 0.0079 | **0.79x — wider** |

The physics pre-screen is a **consistency** device as much as a cost device: for
the three sampling-based methods it removes two-thirds of the run-to-run spread
for free. It does almost nothing for PPO, which is consistent with the policy's
variability coming from the policy rather than from where it happens to sample.
`gp_bo` gets slightly *wider*, and at sd 0.0062 vs 0.0079 on n = 10 that is not
a difference worth interpreting.

## 4. At a larger budget, and on a harder problem

**At 2 400 simulations P1 saturates for everyone**, and the ordering not only
survives — it sharpens (`--ladder`):

| arm | n | mean | sd | CV % |
|---|---|---|---|---|
| `cmaes` | 10 | 8.9999 | **0.0001** | 0.0 |
| `ppo` | 10 | 8.9906 | **0.0074** | 0.1 |
| `uniform` | 20 | 8.9913 | **0.0104** | 0.1 |

    uniform vs cmaes    145.26x   [ 41.25, 283.35]
    ppo     vs cmaes    104.32x   [ 23.86, 176.71]

**CMA-ES becomes effectively deterministic** — sd 0.0001 across ten seeds, a
range of 8.9998–9.0000 — while PPO and uniform remain two orders of magnitude
wider and stay indistinguishable from each other. So the small-budget finding is
not an artifact of a starved budget: given 16x the simulations, the gap in
*consistency* widens rather than closes, even as the gap in *mean* vanishes.

**On P3 nothing is consistent.** `cmaes` sd **2.4363** (CV 195 %), `uniform` sd
**2.5845** (CV 516 %), ratio 1.06x with a CI of **[0.09, 10.75]** — both with
means at or below zero, so the arms are mostly failing to find a feasible design
at all. A spread computed across mostly-infeasible runs measures how badly they
fail, not how reliably they succeed. **No consistency claim is made for P3**,
and quoting a CV of 516 % as a result would be meaningless.

Reproduce all three tables:

```
python -m nebula.experiments.exp_variance --run --problem P1     # section 3
python -m nebula.experiments.exp_variance --run --ladder         # section 4, 2400 sims
python -m nebula.experiments.exp_variance --run --problem P3     # section 4, hard problem
```

Each writes its own artifact (`variance_results_{baselines,ladder}_{P1,P3}.json`).
A single fixed filename let the P3 run silently overwrite the P1 result the first
time `--problem` was used — the same clobbering `runlock.py` exists to stop
(G113), caught here within a minute of introducing it.

## 5. A correction earned while building this

The first version grouped by `(method, prescreen)` and **not** by `problem`. It
reported `uniform`'s standard deviation as **4.6186** instead of **0.1110** — a
**42x** inflation — because P1's rewards saturate near +8.95 while P3's run
negative, so the "spread" was measuring the gap between two different problems.

It did not raise, it did not look wrong, and the derived bootstrap intervals were
internally consistent (one comparison read `742.85x [584.28, 1489.04]`, which is
absurd only if you already know the right answer). It is the same family as
**G105** and **G108**: *a number that is wrong by an order of magnitude and still
simulates, computes and reports happily.*

`load_summaries(problem="")` now **raises**, and
`test_pooling_problems_inflates_the_spread` pins the inflation so the trap stays
reproducible rather than becoming folklore.

## 6. What this does NOT say

* **Not that CMA-ES is a better optimiser than PPO here.** That claim is
  `BASELINES.md`'s and rests on the anytime curve. This is only about spread.
* **Not that PPO is worse than random search.** The measured statement is that
  the two are **not distinguishable** on consistency — CI [0.48, 3.73] — which
  is the same shape as the existing anytime finding, not a new defeat.
* **Nothing about corners, coverage or the 135-point load grid.** Every number
  here is P1, one budget, nominal.
* **Not a claim about the delivered design.** These are search-run outcomes, not
  the shipped operating point.
