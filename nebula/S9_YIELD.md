# S9 corner-robust yield: what 45 corners take away, and how few of them you need

> ## ⚠ READ §8 FIRST — every number in §1–§7 was measured at `cl` = 150 fF
>
> **Session 12b (2026-08-06) re-ran this experiment with `cl` treated as a
> physically derived context RANGE instead of a pinned constant, and the yield
> fell from 8.20 % to 0.05 %.** `CL_RANGE.md` shows the 150 fF pin — chosen
> because it maximised the S3 yield among five values tested — is **1.92×
> above the top of the range the following stage can actually present**
> (13.6–78.0 fF).
>
> §1–§7 below are **not retracted**: they are correct, and they remain the
> reference for *what the PVT corners alone cost*, which is a real and separable
> result. But **8.20 % and 8.10 % are conditional on a load the circuit will
> not see**, and neither may be quoted as "the corner-robust yield" without
> §8 beside it. The three reusable findings (G46, G47, G48) survive unchanged.

**Date:** 2026-08-05 (session 10d), §8 added 2026-08-06 (session 12b) ·
**Simulator:** ngspice 41, trimmed SKY130 library (G36) · **20 205 SPICE runs,
47 min wall clock** (12 645 for the two stages, 7 560 for the TT baseline and
its paired re-screen in §4); §8 adds **15 255 runs, 49.3 min**.

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
python -m nebula.experiments.s9_yield --n 2000 --no-bench   # §8, ~49 min
python -m nebula.experiments.s9_yield --tolerance-only      # §8.4-8.5, ~3 min
python -m pytest nebula/tests/test_s9_yield.py -q
```

The §1–§7 numbers are NOT reproduced by that command any more — it screens the
derived `cl` range. To reproduce them, pin `cl` at `CL_LEGACY_PIN_F`; that pin
is kept in the script for exactly this reason and because
`robust_geometry.py` rebuilds session 10d's population from it.

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

   > **SUPERSEDED 2026-08-06 — and this is the assumption that broke.** The
   > paragraph above is right that `cl` is a load rather than a knob, and wrong
   > that a single number describes it. `CL_RANGE.md` derives the load from the
   > gate capacitance of the stages the CTLE drives and gets **13.6–78.0 fF**,
   > so 150 fF is not merely "a" load, it is **1.92× above the highest load the
   > following stage can present**. The parenthesis — *"that is not why it is
   > fixed"* — was an honest disclaimer that turned out not to be enough: the
   > value still came from a yield maximisation, and no other value had been
   > justified. See §8.
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
2. ~~**Re-cut the screen** with a hot fast corner~~ — still open, but see §8:
   the screen now has a **load** axis and was exact on this sample.
3. **Replace the `CHANNEL_DC_LOSS_DB` = 1.0 dB placeholder** before any
   compression verdict is quoted — it is still a made-up constant deciding a
   result (HANDOFF §8).
4. ~~**`cl` is pinned at a yield-maximising value**~~ — **DONE 2026-08-06,
   §8 below.** It cost the headline.

---

## 8. The load was an assumption, and it was the one that mattered

**Date:** 2026-08-06 (session 12b) · **15 255 SPICE runs, 49.3 min**, 8 workers.
Same box, same seed, same spec checker, **same 1890 designs** — `headroom_ok_1v8`
does not read `cl`, so the population is identical to §1's and the comparison
below is **paired**, not between two samples.

What changed is one assumption. `cl` is no longer pinned; it is a **context
variable with a physically derived range**, screened like a PVT corner. A design
counts only if it passes at **every (corner, load) pair**. The range comes from
`CL_RANGE.md`: **`cl_lo` = 13.64 fF, `cl_mid` = 32.63 fF, `cl_hi` = 78.04 fF**,
a 5.72× spread derived from the gate load of the 1-tap DFE summer and the slicer
plus routing.

### 8.1 The number

| | pinned 150 fF (§4) | range 13.6–78.0 fF |
|---|---|---|
| nominal PVT, TT/1.00/27 °C | 255/1890 = **13.49 %** | 15/1890 = **0.79 %** [0.48, 1.31] |
| screen (3 corners) | 155/1890 = **8.20 %** | 1/1890 = **0.05 %** [0.01, 0.30] |
| full sweep (45 corners) | 153/1890 = **8.10 %** | 1/1890 = **0.05 %** [0.01, 0.30] |

Grid: nominal 1 corner × 2 loads; screen 3 corners × 2 loads = 6 evaluations per
design; promotion 45 corners × 3 loads = 135 per survivor.

**The load range costs 99.4 % of the nominal winners. The PVT corners cost
39 %.** Both are computed on the same population, so they are directly
comparable, and the ordering is not close: **the load is now the binding
constraint and the corner set is second.**

Health: **0 hard simulator failures, 0 retries** across all 15 255 runs;
52 (design, corner, load) headroom rejections in the screen — exactly 2× the 26
of §1, which is the expected result because `headroom_ok_1v8` does not read
`cl` and each rejection is therefore duplicated across the two loads.
**0 screen/promotion mismatches.**

Cost, for the record: **192–199 ms per (design, corner, load) at 8 workers**,
against G48's 106 ms. G48 was measured on a quiet machine; this run shared the
box. The G48 lesson stands (parallelism stops paying at ~8 workers); its
absolute number is a floor, not a budget.

### 8.2 Why: the per-load sets are large and DISJOINT

This is the result, and it was pre-registered as the follow-up to run if the
joint count came out near zero (`PREDICTIONS.md` entry 1). It costs nothing —
it re-reads the same six evaluations.

| | designs | of 1890 |
|---|---|---|
| corner-robust at `cl_lo` = 13.6 fF alone | 43 | 2.28 % |
| corner-robust at `cl_hi` = 78.0 fF alone | 118 | 6.24 % |
| corner-robust at **every** load | **1** | **0.05 %** |
| corner-robust at **any** load | 160 | 8.47 % |
| corner-robust at **exactly one** load | 159 | 8.41 % |

**159 of the 160 designs that are corner-robust at one load edge are not
corner-robust at the other.** The joint set is not small because the per-load
sets are small: **8.47 % of the box is corner-robust *somewhere* in the load
range** — essentially §3's 8.20 %. It is small because the two sets barely
intersect. Under independence the joint would have been 2.68 designs; it is 1.

The nominal-PVT numbers show the same shape one level down: 75 designs pass at
`cl_lo`, 197 at `cl_hi`, **15 at both** against 7.8 expected under independence.
So at nominal the two loads are ~1.9× *positively* associated and the overlap
still only reaches 0.79 %; add corners and the overlap collapses to 1.

### 8.3 Which spec binds, and how it moves with the load

First failure by normalised shortfall (CLAUDEwa §9), of 1890 designs. The old
150 fF column is §2's table; the two new ones are the screen's load edges,
averaged over the three corners.

| spec | at `cl_lo` 13.6 fF | at 150 fF (§2) | at `cl_hi` 78.0 fF |
|---|---|---|---|
| **S3_f_peak** | **82.5–84.9 %** | 42 % | 56.1–57.0 % |
| S3_peaking | 10.4–12.0 % | 37 % | 29.9–31.1 % |
| S3_nyq_boost | 0.2–0.8 % | 8 % | 1.7–3.2 % |
| headroom | 0.7 % | 0.7 % | 0.7 % |
| saturation | ~0.1 % | 0.2 % | 0.1–0.2 % |
| S6_power | 0.1 % (2 runs) | 0.1 % (2 runs) | 0.1 % (2 runs) |

**`S3_f_peak`'s share is monotone in the load: 42 % → 57 % → 84 % as `cl` falls
from 150 to 78 to 13.6 fF.** The mechanism is the one the whole file is about —
less load capacitance puts f_p2 higher, which puts the peak higher, which
pushes it out through S3's 2.5 GHz top edge. **S5 is still never the first
failure anywhere**, and S6 is still twice in the whole sweep.

> **A number in that table needs reading carefully.** The median `S3_f_peak`
> margin at `cl_lo` is **−17.453 GHz**, which corresponds to f_pk = 19.953 GHz
> — and that is *exactly* the last `ac dec 50` grid point at or below the
> `meas ac MAX` search ceiling of 20 GHz. It is the **search-range edge, not a
> peak.** The honest reading is "the peak is above 20 GHz **or there is no peak
> at all**", not "the median design peaks at 19.95 GHz". This does not corrupt
> any verdict — such a design fails the 1.25–2.5 GHz window either way, which is
> why it is not a repeat of G44 — but the *median margin* is a property of the
> sweep setup at that end of the load range. §8.4 measures how much of it is
> genuinely "no peak at all".

### 8.4 Two failure modes, and the obvious model only explains one

`PREDICTIONS.md` entry 1 predicted this yield at essentially zero (0–10 of 1890;
measured 1) on the argument that f_peak moves as `cl^-0.5`, so a 5.72× load
range would shift it 1.26 octaves through a 1.00-octave window. **The number was
right and the argument was wrong**, which the follow-up measured directly on 200
designs at 5 loads spanning the range:

* **the median exponent is −0.349** (range −0.549 … −0.243), not −0.5. So the
  real shift is **1.84× = 0.88 octaves — less than the window**, which by the
  prediction's own logic should have left a few percent of designs alive;
* **but 146 of the 200 (73 %) do not keep an interior maximum across the load
  range at all.** They do not move out of the window; they **lose the peak**.
  An exponent cannot see this failure mode, because a design with no peak has
  no f_peak to differentiate. This is session 9c's *"lowering f_p2 does not move
  the peak down, it EXTINGUISHES it"*, measured along the load axis;
* and for the 27 % that do keep a peak, 0.88 octaves of movement inside a 1.00-
  octave window leaves **0.12 octaves** of centring slack — about **2 of the 15
  distinct f_peak values** the window holds at session 11's measured 0.0664-octave
  quantisation. The design must be centred to within roughly one grid point.

`CL_SENSITIVITY.md` §3's single probe measured −0.48 and was taken as
representative; across 54 designs with a peak throughout, it is at the extreme
end of the distribution. **One probed sample is one probed sample** — the same
lesson as G43, one experiment later.

### 8.5 How much load range this topology *can* absorb

A yield of 0.05 % says the derived range cannot be absorbed. It does not say
what range *could* be, and that is the number a designer needs — it is the
tolerance the following stage's input capacitance must be specified to.

Measured on the single surviving design (18-rung geometric ladder, 5–300 fF,
with the screen's own loads merged in, at the 3 screen corners):

```
design 432   [....#########.....]   passes 13.6 - 78.0 fF = 5.72x
             5 fF                300 fF        fails at 12.0 fF and 93.1 fF
```

**Its tolerance is at least 5.72× and at most 7.76×** (the next failing rungs).
It fits the demanded range with **less than one ladder step of margin on either
side**, and it is the only such design in 1890. Its sizing:

```
w_in 89.3 um   l_in 0.399 um   nf_in 8   i_bias 3.25 mA
rs 318.6 ohm   cs 1.90 pF      rl 565.0 ohm   vcm_in 1.407 V
```

Note `l_in` = 0.399 µm, well above the 0.15 µm minimum bin — a *slower*, longer
device than the box's centre. That is a single design and not evidence of a
rule, but it is the obvious first hypothesis for anyone looking for more of
them.

> **The ladder's first version reported 4.32× and was wrong**, because it did
> not contain `cl_lo` and `cl_hi` as rungs — so it contradicted the screen that
> had passed this design at both. `cl_ladder(include=...)` now merges the
> screen's own loads in, and a test pins it. A resolution artifact that
> contradicts a measurement you already have is the cheapest kind to catch, and
> it was nearly published.

### 8.6 What this changes, and what it does not

**Changes:**

- **The binding constraint is the load range, not the corner set.** Corners cost
  39 % of nominal winners; the load range costs 99.4 %. Any statement of the
  form "S9 is what makes this hard" now needs the load beside it.
- **`cl` must be specified, not assumed.** The actionable output is not 0.05 %,
  it is §8.5's tolerance: this topology absorbs a load spread of roughly
  6–8× *for one design in 1890*, so either the following stage's input
  capacitance is pinned down much more tightly than 5.72×, or the CTLE needs a
  knob (`CL_RANGE.md` §7b: capacitance can always be *added*, never removed).
- **A tunable part was never scored here.** S3 says the peaking is tunable via
  R_s/C_s, and `s9_yield.py` scores fixed sizing points. `CL_RANGE.md` §9 makes
  the same point: requiring one fixed sizing to work across a 5.72× load range
  is a harder question than silicon has to answer, and **0.05 % is a lower
  bound on what a tunable part could do.** Measuring the tunable version is the
  obvious next experiment and is not done.

**Does not change:**

- **G46, G47 and G48 all survive.** The screen was again **exact** (1 promoted,
  1 robust, 0 false positives), and the load axis did not introduce a
  mid-range blind spot on this sample — `cl_mid` caught nothing the edges
  missed, though with one survivor that is a weak test.
- **The coupling argument stays falsified** (G40). This is a *second* tax on the
  baseline, larger than the first. It is not evidence that S3 is coupled, and
  writing it as such would repeat the error §4 of `BOUNDS_REDERIVATION.md`
  documents.
- **The tail is still two ideal current sinks**, so 0.05 % remains an
  **optimistic** bound in exactly the same way 8.10 % was.

---

## 9. The tail was ideal, and now it is not

**Session 13, 2026-08-06.** `python -m nebula.experiments.s9_yield --n 2000`
re-run with a real current-mirror tail. **15 255 SPICE runs, 35.2 min.** Full
device write-up: `nebula/TAIL_DEVICE.md`. Prediction vs outcome:
`nebula/PREDICTIONS.md` entry 2, committed before the run.

Every number in §1–§8 of this file carried the caveat *"optimistic bound — the
tail is two ideal current sinks"* (G47). **That caveat is now discharged, and
the answer is that it was worth less than expected.**

### The headline: the yield did not move

```
                              12b (ideal tail)      13b (real tail)
      nominal PVT, both loads     15 / 1890            15 / 1890   0.79 %
      3 corners x 2 loads          1 / 1890             1 / 1890   0.05 %
      45 corners x 3 loads         1 / 1890             1 / 1890   0.05 %
```

Same box, same seed, **same 1890 designs**, and **the same surviving design**
(index 432, identical parameters). Health: 0 screen/promotion mismatches, 52
headroom rejections (exactly 12b's — `headroom_ok_1v8` does not read the tail
and was deliberately not changed), 12 hard failures in 15 255 runs (0.08 %, all
G54 NaN).

### What did move: 8.8 % of the corner-robust population

```
                              12b        13b       delta
      robust at cl_lo alone    43         39         −4
      robust at cl_hi alone   118        108        −10
      robust at ANY load      160        146        −14   (−8.8 %)
      robust at EVERY load      1          1         ±0
```

Per screen column: `−7, −7, +5, +7, +0, −8`. So the tail is **a real but
second-order tax**, and the comparison that matters is against §8's:

| what was assumed away | cost to the corner-robust population |
|---|---|
| the PVT corners (§4) | **39 %** of the nominal winners |
| the **load range** (§8) | **99.4 %** |
| the **ideal tail** (this section) | **8.8 %** |

**The load remains the binding constraint by a wide margin.**

### The mechanism, measured paired

600 designs at `cl_hi`, the *same* design evaluated with an ideal tail and with
the mirror:

| corner | pass with both | gained | lost | net |
|---|---|---|---|---|
| `ff / 1.05 / 0 °C` | 53 | 6 | 5 | **+1** |
| `ss / 0.95 / 125 °C` | 40 | 6 | **10** | **−4** |

The slow-hot losses are the tail's own constraint (4 of 10 ranked
`tail_saturation`, against 1 of 5 at fast-cold). The gains at both corners are
mostly designs pulled back inside the S3 window by the mirror's ~2 % `gm`
reduction. **The supportable statement is "the tail costs designs at slow-hot
and is roughly neutral at fast-cold"** — +1 on 600 paired designs is noise.

### A new spec row, and a new table that was needed to see it

`tail_saturation` is `vds_tail > vdsat_tail`, and it is **the only row in the
table that couples five box coordinates**: `vds_tail` *is* the input pair's
source node, so the constraint reads

```
      VCM − Vgs(I_tail, W_in, L_in)   >   vdsat_tail(I_tail, W_tail, L_tail)
```

| screen corner | **violated** | ranked worst |
|---|---|---|
| `ss / 0.95 / 125 °C` | **13.3 %** | 0.6–1.5 % |
| `ss / 0.95 / 0 °C` | 6.3 % | 0.4–0.8 % |
| `tt / 1.00 / 27 °C` | 5.2 % | 0.2–0.7 % |
| `ff / 1.05 / 0 °C` | 2.6 % | 0.1–0.2 % |

**The two columns differ by an order of magnitude and the gap is a
methodological finding, not a detail.** The first-failure ranking scores by
normalised shortfall, so a constraint missing by tens of millivolts always
loses to an `S3_f_peak` missing by 17 GHz. §2 of this file argues that *"which
spec binds"* is the headline output — **it now has two meanings and they
disagree**, so this script prints both. A constraint can bind on an eighth of
the population and appear as a 1 % footnote.

### What this settles, and what it retires

- **RETIRE:** HANDOFF §8's *"this is the one experiment that could still turn
  corner robustness into a real constraint rather than a tax."* It did not.
  `tail_saturation` is a genuine coupled inequality but it costs 8.8 %, against
  the load's 99.4 %. Retire it the way G40's coupling claim was retired, rather
  than letting it drift into a deliverable.
- **DISCHARGE:** every *"optimistic bound"* caveat in §1–§8. The optimism was
  worth 8.8 % of the corner-robust-at-some-load population and **zero** of the
  headline yield.
- **SURVIVES:** G46, G47 and G48. The screen was again **exact** (1 promoted,
  1 robust, 0 false positives) and the 45-corner promotion rejected nothing.
- **NEW, and it lowers a planned cost:** session 11's margin thresholds were
  flagged as lower bounds *because* the tail was ideal. A rule-sized tail moves
  a design's peaking by ~0.05 dB — below the 0.0664-octave `f_peak`
  quantisation. **Re-running `robust_geometry.py --collect` is now a low-value
  experiment**, which is worth knowing before spending 23 minutes on it.
- **STILL OPEN:** every design scored here is a FIXED sizing point, while S3
  says the peaking is tunable via `R_s`/`C_s`. 0.05 % remains a lower bound on
  what a tunable part achieves, and that experiment is still not written. It is
  now unambiguously the highest-value one left.
