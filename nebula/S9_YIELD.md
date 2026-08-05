# S9 corner-robust yield: what 45 corners take away, and how few of them you need

**Date:** 2026-08-05 (session 10d) · **Simulator:** ngspice 41, trimmed SKY130
library (G36) · **20 205 SPICE runs, 47 min wall clock** (12 645 for the two
stages, 7 560 for the TT baseline and its paired re-screen in §4).

Closes `BOUNDS_REDERIVATION.md` §7 item 3 and HANDOFF §8's third follow-on:
every yield this project has published is TT / 27 °C, and **S9 requires every
spec to hold at every corner**. A design that meets S3 at nominal and misses it
at SS / 0.95 V / 125 °C is a failed design and has to score as one.

Two headlines, and the second is the useful one:

1. **Corner robustness costs 39 % of the nominal winners.** The same 1890
   designs yield **13.49 %** at TT / 27 °C, **8.20 %** across three corners and
   **8.10 %** across all 45. Two in five designs that pass every spec at
   nominal are not designs. This is a real effect and a quotable one — but it
   is a *tax on the baseline*, not the coupled constraint that G40 retired.
2. **Three corners buy 98.7 % of the verdict of forty-five, at 3/45 of the
   per-design cost.** Of 155 designs that passed the 3-corner screen, 153
   passed all 45. In this run the full sweep consumed 64 % of the wall clock
   to reject **two** designs. That is a reward-cost result the RL loop can act
   on directly.

And one caveat that outranks both, stated before the numbers rather than after:
**the tail is still two ideal current sinks.** An ideal sink does not lose
current at SS / 125 °C and does not fall out of saturation at 0.95 VDD. Every
corner spread below is therefore an **understatement**, and 8.10 % is an
**optimistic bound** — the corner spread attributable to the input pair alone.
Both headlines have to be re-measured once a tail transistor exists.

Reproduce:

```
python -m nebula.experiments.s9_yield --n 2000
python -m pytest nebula/tests/test_s9_yield.py -q
```

`common/params.py` is untouched — this is a measurement, not a bound change
(CLAUDEwa §8 rule 6).

---

## 1. Method

2000 Latin-hypercube samples of `PROPOSED_BOX` (seed 20260804), `cl` pinned at
150 fF, 110 rejected free by `headroom_ok_1v8` at the nominal rail → **1890
designs simulated**. Then two stages:

| stage | designs × corners | runs | wall clock | share |
|---|---|---|---|---|
| 1 — screen | 1890 × 3 | 5 670 | 613 s | 36 % |
| 2 — promote survivors | 155 × 45 | 6 975 | 1 078 s | 64 % |

The screen corners are **ss / 0.95 / 125**, **ff / 1.05 / 0**, **ss / 0.95 /
0** — the slow-hot, fast-cold and slow-cold intuitions. They are members of the
45, so stage 2 re-runs them, which costs 3/45 and buys a free determinism
check: a design's verdict at a repeated corner must be identical in both
stages. **0 mismatches across 465 repeated (design, corner) pairs.** A mismatch
would have meant the corner plumbing is not deterministic, which invalidates
everything downstream, so it is checked rather than assumed.

Health, both stages: **0 hard simulator failures, 0 retries** across all
12 645 runs. 26 *(design, corner)* evaluations were rejected on headroom —
13 at each of the two 0.95 V slow corners, none at the fast one — and a
headroom rejection counts as a **corner failure**, not a silent drop
(G26/G30, rule 10). The retry-once policy (G45) never fired, which is the
expected result on a quiet machine and the reason it is reported separately
from hard failures rather than folded into them.

### What is assumed rather than measured

Printed in the run header and written into the results JSON, because a reader
has to be able to reject each one:

1. **`cl` pinned at 150 fF.** Not an optimisation. `cl` is the next stage's
   input capacitance plus routing — a load handed to you by layout, not a knob.
   Every number here is conditional on that load. (`CL_SENSITIVITY.md` measured
   150 fF as the best of five values tested; that is not why it is fixed.)
2. **VCM held constant as VDD moves ±5 %.** The alternative assumes a bias
   network that tracks the supply, i.e. a circuit that does not exist yet.
   Holding it is the more conservative reading.
3. **The tail is ideal.** See the caveat above. This is the one that matters.

Not screened, and why: **S4** (HD3) needs transient + FFT, ~4× the cost of
AC + noise (G21) — it belongs in the promotion tier, not the screen, and
measured ~60 dB inside spec at TT. **S7** (area) has no MIM-cap or poly-resistor
model to compute an area from. **S8** (eye) is a link-layer metric that needs
the device→link bridge (G2).

---

## 2. The headline output is not the yield — it is which spec binds

A yield is one number that mostly reflects how the box was drawn (G40). "S3
peaking is what this corner takes away from you, by a median of N dB" survives
a change of box. Ranking is by CLAUDEwa §9's normalised shortfall — the
project's own reward normaliser — so "which spec binds" means the same thing
here as it will to the policy.

First failure at each screen corner, of 1890 designs:

| spec | ss/0.95/125 | ff/1.05/0 | ss/0.95/0 | median margin |
|---|---|---|---|---|
| S3_f_peak | 800 (42.3 %) | 799 (42.3 %) | 786 (41.6 %) | −1.7 to −2.1 GHz |
| S3_peaking | 686 (36.3 %) | 719 (38.0 %) | 688 (36.4 %) | −3.000 dB |
| S3_nyq_boost | 162 (8.6 %) | 126 (6.7 %) | 144 (7.6 %) | ≈ −1.0 dB |
| headroom | 13 | — | 13 | |
| saturation | 5 | 1 | 3 | −0.05 to −0.11 V |
| S6_power | — | 2 | — | −0.03 mW |

Three things fall out of that table, and none of them is a yield.

**S5 (noise) never ranks as the binding constraint at any corner, and S6
(power) does so twice in 5 670 runs** — at the fast / high-rail corner, by
0.03 mW. Read this precisely: the table counts *first* failures, i.e. the worst
normalised shortfall, so it says S5 is never the worst thing wrong with a
design, not that S5 never fails. What binds in this box is **bandwidth
placement**, and it is not close.

**The median S3_peaking failure misses by exactly −3.000 dB, which means its
peaking is 0.000 dB.** The margin is `peaking − 3` at the low edge, so the
median failing design has *no peak at all* — it is a flat stage, not a stage
peaking by the wrong amount. That is the same population 9d found behind the
low P(B) marginal, seen from the other side: most of the box does not produce
a peak, and the ones that do mostly put it outside 1.25–2.5 GHz.

**The extreme f_peak failure is −17.45 GHz**, i.e. a peak at ~19.9 GHz. The
box's fast corner is far outside the S3 window, not marginally outside it.

---

## 3. Three corners are worth 98.7 % of forty-five

| | designs | of 1890 |
|---|---|---|
| passed the 3-corner screen | 155 | **8.20 %** [7.05, 9.52] |
| passed all 45 corners | 153 | **8.10 %** [6.95, 9.41] |
| of the screen's survivors | 153 / 155 | **98.71 %** [95.42, 99.65] |

The two intervals overlap almost entirely. Stage 2 cost 1 078 s — 64 % of the
run — and changed the answer by **two designs**.

This is not a coincidence of this sample, and half of it is guaranteed:

- **The screen has no false negatives, by construction.** Its corners are a
  subset of the 45, so any design it rejects would have been rejected by the
  full sweep. The 3-corner yield is therefore a hard **upper bound** on the
  45-corner yield, always.
- **The only error it can make is a false positive**, and here it made two, out
  of 155.

`screen_augmentation()` maps each of the 45 corners to the false positives it
would have caught, so "what is the cheapest exact screen?" is answered from
data rather than from corner intuition:

`TBD_AUG`

### Corner intuition is wrong about which corner is worst

Every promotion-stage failure — all 10 pooled — occurs at **125 °C**, and the
worst corners are **ff** and **sf** at 0.95 V, not **ss**:

```
ff_vdd0.95_t125   153/155    saturation + S3_f_peak
sf_vdd0.95_t125   153/155    saturation + S3_f_peak
tt/ff/sf @ t125   154/155    S3_f_peak   (6 corners)
ss_* (all 9)      155/155    -
fs_* (all 9)      155/155    -
```

Two of the nine `ss` rows — 0.95 V at 0 °C and 125 °C — are screen corners and
pass trivially, since every promoted design passed them by definition. The
other **seven** are not screened and are the informative ones. They are clean,
as are all nine `fs` corners.

The screen was built on the standard intuition that slow-hot is the killer.
For S3 it is not: a **faster** device pushes gm up, which pushes the peak up in
frequency and out through the 2.5 GHz top edge. `ss` never does that. The spec
that binds here is two-sided, and two-sided specs do not have a "worst corner"
in the way a one-sided spec (max power, max noise) does. **This is the reusable
finding of the section**, and it is the reason the screen needs a hot fast
corner rather than another slow one.

---

## 4. What corner robustness actually costs: 39 % of the nominal winners

A corner yield means nothing without its nominal denominator. The same 1890
designs were therefore re-run at **tt / 1.00 / 27 °C** — same box, same seed,
same `cl` pin, same spec checker, one corner changed — so the comparison is
paired design-by-design rather than inferred from two different populations.

|  | designs | of 1890 |
|---|---|---|
| pass at TT / 1.00 / 27 °C | 255 | **13.49 %** |
| pass all 3 screen corners | 155 | **8.20 %** |
| pass all 45 corners | 153 | **8.10 %** |

Cross-tabulated over the same 1890 designs:

```
TT pass, corners pass   155
TT pass, corners FAIL   100   <- corner-fragile
TT fail, corners pass     0
```

**39.2 % of designs that meet every spec at nominal fail at one of three
corners** (40.0 % against all 45). That is the number worth quoting: *two in
five nominal winners are not designs at all.* An optimiser scored at TT is
therefore not slightly optimistic — it is wrong about 39 % of the points it
would rank as successes, and it has no signal that tells it which ones.

The bottom-right cell is a real check, not a tautology: **tt / 1.00 / 27 °C is
not one of the three screen corners**, so "0 designs fail nominal yet pass all
three extremes" had to be measured. It came out 0, which is what a sane
corner-response should give.

**Consistency with session 10b.** `CL_SENSITIVITY.md` reports 13.54 % at
`cl` = 150 fF — **256** of the same 1890. That run counted S3 alone
(peaking ∧ f_peak); this one additionally requires Nyquist boost > 0, S5, S6
and saturation. Four extra conditions remove exactly **one** design. The two
measurements agree, and the near-identity is itself informative: outside S3,
nothing in this box binds at nominal.

---

## 5. Cost model: parallelism stops paying at ~8 workers

Measured on 220 tasks at ss/0.95/125, this machine (11 logical cores):

| workers | wall clock | ms/task | speedup | efficiency |
|---|---|---|---|---|
| 1 | 69.9 s | 317.9 | 1.00× | 100 % |
| 2 | 39.3 s | 178.8 | 1.78× | 88.9 % |
| 4 | 33.1 s | 150.3 | 2.11× | 52.9 % |
| 8 | 23.3 s | 105.9 | 3.00× | 37.5 % |
| 11 | 22.0 s | 100.1 | 3.18× | 28.9 % |

Efficiency collapses after 2 workers and the curve is flat past 8: going from
8 to 11 buys 6 %. Each run spawns a process, parses the trimmed library and
writes `wrdata` files, so the wall clock is dominated by process startup and
file I/O rather than by arithmetic — adding workers adds contention for the
same disk. **Budget the RL loop at ~100 ms per (design, corner) evaluation with
8 workers**, and treat more parallelism as free only up to that point. This
supersedes any per-point figure derived from the 0.42 s single-run number
(G36): under load it is 100 ms, not 420 ms, because the runs overlap — but only
3.2× overlap is available, not 11×.

---

## 6. What this changes, and what it does not

**Changes:**

- The RL reward should evaluate at **three to five corners, not 45**. The full
  sweep belongs in a final verification tier, not in the loop. At ~100 ms per
  (design, corner) that is the difference between 0.3 s and 4.5 s per candidate
  — a 15× throughput factor over the whole training run.
- The screen's corner set should gain a **hot fast** corner. It was chosen on
  an intuition this data contradicts.
- The inner reward's weight belongs on **S3's two readings plus the saturation
  validity check** — they carry essentially all of the discrimination in this
  box. S5 and S6 still have to be *evaluated* (they are nearly free, riding on
  the same `.op`/`.noise` run), but shaping the reward around them is shaping
  it around a constraint that is never the worst one.

**Does not change:**

- **The falsified coupling argument stays falsified.** S9 was listed in
  `BOUNDS_REDERIVATION.md` §4 as the cheapest route to a *measured* constraint
  to replace it. What it delivers is a **tax, not a coupling**: corners remove
  39 % of the nominal winners, which lowers the baseline RL must beat and
  raises the cost of finding each hit, but it does not make the constraint
  non-axis-aligned and must not be written as if it did. The defensible
  sentence is "an optimiser scored at nominal is wrong about two of every five
  designs it calls a success", not "S9 is a coupled constraint".
- `common/params.py::BOUNDS` — untouched, pending the human decision that
  CLAUDEwa §8 rule 6 reserves.

---

## 7. What to do next

1. **Add a real tail transistor**, then re-run this experiment unchanged. It is
   the single assumption that could move both headlines, and it is the only way
   to turn "the corner spread of the input pair" into an S9 result. Everything
   here is instrumented to be re-run as-is.
2. **Re-cut the screen** with a hot fast corner and confirm exactness on a
   fresh seed. One seed proving a screen exact is one seed.
3. **Replace the `CHANNEL_DC_LOSS_DB` = 1.0 dB placeholder** before any
   compression verdict is quoted — it is still a made-up constant deciding a
   result (HANDOFF §8).
