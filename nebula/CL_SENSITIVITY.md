# `cl` sensitivity: what pinning the load capacitance does to the S3 yield

**Date:** 2026-08-04 (session 10b) · **Simulator:** ngspice 41, trimmed SKY130
library (G36) · **All numbers TT / 27 °C, VDD = 1.8 V.**

Follow-on to `BOUNDS_REDERIVATION.md`. That document re-derived the parameter
box and measured an 8.73 % S3 random-search yield inside it, and flagged `cl`
as the bound it had moved furthest — 6× tighter than the 1.2 V box, because
400 fF already drives the Nyquist boost negative. This measures what `cl` is
actually doing to the yield, by taking it out of the search entirely.

**Headline, and it is not the expected direction: searching over `cl` is worse
than not searching over it.** Pinning `cl` at 150 fF raises the S3 yield from
**8.73 % [7.54, 10.09]** to **13.54 % [12.08, 15.16]** — a 1.55× improvement,
on disjoint 95 % intervals, while *removing* a dimension from the search. The
`cl` axis is not buying the search anything; it is diluting it.

Reproduce:

```
python -m nebula.experiments.s3_yield --n 2000 --cl-fixed  50e-15
python -m nebula.experiments.s3_yield --n 2000 --cl-fixed 100e-15
python -m nebula.experiments.s3_yield --n 2000 --cl-fixed 150e-15
python -m pytest nebula/tests/test_sky130_runner.py -q
```

`common/params.py` is untouched. This is a measurement, not a bound change —
CLAUDEwa §8 rule 6 reserves that for a human, and §6 below is the proposal.

---

## 1. Method

`--cl-fixed FARADS` was added to `experiments/s3_yield.py`. It overwrites the
`cl` coordinate of the **same seeded Latin-hypercube design** rather than
re-sampling in eight dimensions. That choice is the reason the comparison
means anything:

- the other eight coordinates are **identical, sample by sample**, across all
  four runs, so a difference in yield is attributable to `cl` and to nothing
  else. Re-sampling in d−1 dimensions would have moved every coordinate at
  once and confounded the two effects;
- LHS stratification is per-dimension, so discarding one dimension's values
  leaves the remaining eight exactly as well stratified as they were.

`test_pinned_runs_at_different_values_are_paired` pins this: it asserts that
two pins of one design differ in `{"cl"}` and in no other key.

The pairing also shows up as a free consistency check. `headroom_ok_1v8()`
reads `i_bias`, `rl` and `vcm_in` and never `cl`, so the free-rejection count
**must** be identical across all four runs. It is: 110 rejected, 1890
simulated, every time. A run where that number moved would have meant the pin
had leaked into something it should not touch.

### Every proportion carries an interval

G40's lesson generalises one level up: a bare proportion invites a conclusion
its own sampling error does not support. All rates below are two-sided
**Wilson** 95 % intervals (`wilson_ci`), not the textbook normal
approximation — Wilson stays inside [0, 1] and returns a real upper bound at
zero successes, which is the case the 45-corner sweep will hit whenever a
corner kills a spec outright. It is the same algebra as
`python_models/pam4_chain.py::ber_wilson_upper`, deliberately re-implemented
rather than imported (`nebula/` is independent of `python_models/` by design)
and held to it by a test.

The coupling factor is a ratio of three proportions measured on the same rows,
so no closed form applies; it gets a **percentile bootstrap** over whole rows,
10 000 resamples, which preserves the correlation that is the entire point.
Its resolution at n = 1890 with these marginals is about **±10 %** — measured,
by bootstrapping synthetic independent data. That number is what makes
"1.04×" a statement rather than a decimal.

---

## 2. Results

2000 LHS samples per row, seed 20260804, 110 rejected free by the headroom
pre-check, **1890 simulated per row, 0 non-convergences**. Runtime ≈ 3 min per
row on 10 workers.

| `cl` | A: peaking 3–12 dB | B: f_peak 1.25–2.5 GHz | P(A)·P(B) | **S3 = A ∧ B** | **95 % CI** |
|---|---|---|---|---|---|
| *sampled, 10–500 fF* | 916 · 48.47 % | 303 · 16.03 % | 7.77 % | 165 · **8.73 %** | [7.54, 10.09] |
| 50 fF | 995 · 52.65 % | 314 · 16.61 % | 8.75 % | 165 · **8.73 %** | [7.54, 10.09] |
| 100 fF | 917 · 48.52 % | 414 · 21.90 % | 10.63 % | 213 · **11.27 %** | [9.92, 12.77] |
| 150 fF | 872 · 46.14 % | 454 · 24.02 % | 11.08 % | 256 · **13.54 %** | [12.08, 15.16] |

### Coupling factor at each

| `cl` | raw coupling | bootstrap 95 % | has-peak subset | conditional coupling | bootstrap 95 % |
|---|---|---|---|---|---|
| *sampled* | 0.89× | [0.81, 0.98] | 1578 | 1.04× | [0.95, 1.15] |
| 50 fF | **1.00×** | [0.92, 1.11] | 1673 | 1.08× | [0.99, 1.19] |
| 100 fF | 0.94× | [0.87, 1.03] | 1559 | 1.10× | [1.02, 1.20] |
| 150 fF | 0.82× | [0.76, 0.88] | 1469 | 1.01× | [0.94, 1.08] |

S5 (noise) and S6 (power) are 100 % — 1890/1890, [99.80, 100.00] — in every
row, and the input pair is saturated in 1872/1890 = 99.05 % in every row.
Neither depends on `cl`, which is the expected result and is reported because
a change there would have indicated a bug.

`n_s3_with_nyquist` equals `n_s3_joint` in all four rows, so CLAUDEwa §3's
reading-(a)-vs-(b) ambiguity does not bite anywhere in this box at any pinned
`cl`: every design that meets S3 on peak-to-DC also has positive boost at
Nyquist.

### The 50 fF row is a coincidence, and it was checked rather than assumed

165/1890 at `cl` = 50 fF is the same integer as the baseline. That is exactly
what a silently-ignored CLI flag looks like, so it was tested directly rather
than explained: **A moved 916 → 995 and B moved 303 → 314**, so both marginals
changed and only the joint landed twice on the same count. A three-point probe
sweeping one sample across cl = 50/100/150/500 fF confirms `f_peak` and
`peaking` both move with `cl` — e.g. one sample goes 9.55 → 6.61 → 5.50 →
3.16 GHz. The identical `n_simulated = 1890` is not a coincidence and is
explained above: the headroom pre-check does not read `cl`.

---

## 3. Why the yield rises: B is the whole story

Read down the two marginal columns. As `cl` goes 50 → 100 → 150 fF:

- **B rises hard: 16.61 % → 21.90 % → 24.02 %.** More load capacitance pulls
  f_p2 = 1/(2π·R_L·C_L) downward, and with it the peak, into S3's
  1.25–2.5 GHz window.
- **A falls gently: 52.65 % → 48.52 % → 46.14 %.** The same load pole eats
  peaking magnitude, exactly as session 9c found when it discovered that
  lowering f_p2 does not move the peak down so much as extinguish it.
- The count of designs with any interior peak at all falls with `cl`: 1673 →
  1559 → 1469.

So `cl` trades peak *magnitude* against peak *location*, and over 50–150 fF
the location term wins by roughly 2:1. It does not keep winning — §7 extends
the sweep to 400 fF and finds B turning over as well, once the load pole
starts extinguishing peaks rather than relocating them. The S3 yield is set by whichever
marginal is scarcer, and B is scarcer throughout — which is the same diagnosis
BOUNDS_REDERIVATION reached (f_peak lands in-window only 16 % of the time) now
shown to be a *lever*, not just a fact.

### An analytic prediction that failed, recorded because it is instructive

Before running this, the obvious model said the peak of a 1-zero/2-pole
response sits near f_p2, so S3's frequency condition should be a constraint on
the R_L·C_L product alone. That predicts **zero** yield at `cl` = 50 fF,
because no `rl` in the 50–800 Ω bound puts f_p2 inside 1.25–2.5 GHz (it would
need 1273–2547 Ω). Measured yield at 50 fF is **8.73 %**, so the prediction is
wrong, and by a wide margin: one probed sample has f_p2 = 55.3 GHz and peaks
at 9.55 GHz. **f_peak is set by the interaction of the zero with both poles,
not by the load pole alone.** Quantifying that relationship is exactly what
`ANALYTIC_SCREEN.md` is for, and this is the first evidence that a naive
closed form will not carry it.

---

## 4. What this says about the coupling claim

It reinforces G40 rather than complicating it, but the two statistics have to
be read in the right order.

The **raw** coupling factor is at or below 1.00× everywhere (1.00 / 0.94 /
0.82), i.e. the joint is *more* likely than independence predicts — the two
S3 conditions, if anything, help each other. There is no adverse coupling to
be found at any pinned `cl`.

The **conditional-on-a-peak-existing** factor is the one that survives
argument, because designs with no peak at all fail A and B together and
associate them for a reason unrelated to the claim. It reads 1.08 / 1.10 /
1.01×, and at `cl` = 100 fF the interval [1.02, 1.20] does exclude 1.0. So
there is a **real but ~10 % adverse effect** at one pinned value. State it
honestly, and state its size: a 10 % effect cannot explain a yield of 8.73 %,
and it is an order of magnitude too small to be the mechanism the retracted
sentence claimed. G40 stands.

Note also that the raw factor moves 1.00 → 0.82 across this sweep while the
conditional one stays at 1.0–1.1. The gap between them *is* the shared no-peak
region, and it grows as `cl` grows because more designs lose their peak. That
is G40's trap-inside-the-trap, visible as a trend rather than a footnote.

---

## 5. The consequence for the RL action space — including the awkward part

**`cl` is a bad search dimension.** Every value tested in 100–150 fF beats
searching the full 10–500 fF bound, and the best tested value beats it by
1.55× on disjoint intervals. A dimension whose *removal* improves the outcome
is not carrying information; it is spending samples.

There are two independent gains from pinning it:

1. the action space drops from 9 sampled parameters to 8 — and `nf_in` is
   already known to be near-dead and non-monotonic (G38), so this is the
   second dimension in a row that measurement says should not be there;
2. the yield roughly doubles relative to the low end.

**And here is the part that must not be buried: this makes G3 harder, not
easier.** CLAUDEwa §7 requires RL to beat random search. Improving the box
improves the random-search baseline it has to beat — from 8.73 % to 13.54 %,
i.e. from ~11 samples per hit to ~7. Choosing the better box is still the
right call, because a baseline that was only weak due to a badly chosen
dimension is not a baseline anyone should want to beat, and a judge will ask.
But it should be a deliberate decision recorded as such, not a silent
improvement that quietly raises the bar three weeks before G3.

---

## 6. Proposal (NOT written into `params.py`)

CLAUDEwa §8 rule 6 and G17 reserve parameter ranges for a human. This is the
proposal:

> **Fix `cl` at a constant in the 150–250 fF region and remove it from the
> action space**, on the evidence above, treating it as a fixed load
> representing the next stage's input capacitance plus routing — which is what
> it physically is. `cl` is not a knob a designer turns; it is what the layout
> hands you.

The optimum is now bracketed: §7 adds 250 fF and 400 fF, and the yield rises
to a maximum at 150 fF (13.54 %) then falls away on both sides. 150 fF is not
separable from 250 fF at this sample size, so the supportable statement is
**"the optimum lies in roughly 150–250 fF"**.

One thing is still needed before this is a decision rather than a suggestion:

- **`cl` is the one parameter here that is not really free.** It is set by the
  load the CTLE drives. Pinning it at whatever value maximises S3 yield, if
  that value is not physically justifiable, is choosing the answer. The honest
  version fixes it from an estimate of the following stage's input
  capacitance and reports the yield that follows — which is a G1 item (the
  slicer/DFE input is not modelled yet), not something this experiment can
  settle.

---

## 7. Exploratory extension: the optimum is bracketed at ~150 fF

Two further points beyond the requested three, to establish whether 150 fF is
a maximum or merely the largest value tested. Recorded separately because they
were not part of the specified experiment. Same 2000-sample paired design.

| `cl` | A: peaking | B: f_peak | **S3** | 95 % CI | raw coupling | has-peak | cond. coupling |
|---|---|---|---|---|---|---|---|
| 50 fF | 52.65 % | 16.61 % | **8.73 %** | [7.54, 10.09] | 1.00× | 1673 | 1.08× |
| 100 fF | 48.52 % | 21.90 % | **11.27 %** | [9.92, 12.77] | 0.94× | 1559 | 1.10× |
| **150 fF** | 46.14 % | **24.02 %** | **13.54 %** | [12.08, 15.16] | 0.82× | 1469 | 1.01× |
| 250 fF | 39.26 % | 22.80 % | **12.06 %** | [10.67, 13.61] | 0.74× | 1313 | 1.02× |
| 400 fF | 33.54 % | 19.21 % | **9.52 %** | [8.28, 10.93] | 0.68× | 1168 | 1.05× |

**150 fF is a genuine interior maximum, not an edge effect.** The yield rises
to it and falls away on both sides, and the fall to 400 fF is on disjoint
intervals ([12.08, 15.16] vs [8.28, 10.93]).

Stated honestly about resolution: **150 fF is not distinguishable from 250 fF
at this sample size** — the intervals overlap substantially. What the data
supports is "the optimum lies in roughly 150–250 fF", not "the optimum is
150 fF". Separating those two would need either more samples or a paired test
on the per-sample outcomes, and neither is worth doing for a parameter §6
argues should be fixed by the load, not by yield-maximisation.

Two mechanisms are now visible end to end:

- **B is non-monotonic too**, peaking at 150 fF (24.02 %) and falling to
  19.21 % at 400 fF. Beyond the optimum, extra load capacitance stops moving
  the peak into the window and starts *extinguishing* it — the count of
  designs with any interior peak falls monotonically, 1673 → 1168 — and an
  extinguished response reports `f_pk` at the 10 MHz sweep start, so it fails
  B as well as A. This is session 9c's "lowering f_p2 does not move the peak
  down, it EXTINGUISHES it", measured across 9450 designs instead of two.
- **The raw coupling factor falls monotonically with `cl`: 1.00 → 0.94 → 0.82
  → 0.74 → 0.68, while the conditional one sits flat at 1.01–1.10.** That gap
  is entirely the growing no-peak population, and seeing it move as a clean
  trend across five points is the strongest available demonstration of G40's
  trap-inside-the-trap: *the raw statistic tracks how many designs have no
  peak, not how much the two S3 conditions fight.* Anyone quoting a raw
  coupling factor without the conditional one next to it is quoting the
  no-peak fraction in disguise.

---

## 8. What this does NOT say

- It says nothing about corners. Every number here is TT/27 °C. `cl` is a
  passive and its S9 behaviour is not the device's; the corner-robust picture
  is `S9_YIELD.md`.
- It does not say 150 fF is optimal — only that it beats 50 and 100, and that
  it beats searching over the whole bound.
- It does not license removing `cl` from the *netlist*. The parameter stays;
  what is proposed is removing it from the **search**.
- The yields are S3-only. They are not conditioned on S8, on compression, or
  on the conjunction of the whole spec table, all of which are lower.
