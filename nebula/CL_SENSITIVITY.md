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

**All numbers below are POST-G44-FIX** (see §9). The peak-detection bug found
after the first pass inflated the has-peak population by up to 42 %, so every
conditional statistic was re-measured. S3 itself barely moved.

| `cl` | A: peaking 3–12 dB | B: f_peak 1.25–2.5 GHz | P(A)·P(B) | **S3 = A ∧ B** | **95 % CI** |
|---|---|---|---|---|---|
| *sampled, 10–500 fF* | 916 · 48.47 % | 303 · 16.03 % | 7.77 % | 165 · **8.73 %** | [7.54, 10.09] |
| 50 fF | 1046 · 55.34 % | 315 · 16.67 % | 9.22 % | 166 · **8.78 %** | [7.59, 10.14] |
| 100 fF | 926 · 48.99 % | 415 · 21.96 % | 10.76 % | 213 · **11.27 %** | [9.92, 12.77] |
| **150 fF** | 868 · 45.93 % | 455 · 24.07 % | 11.06 % | 256 · **13.54 %** | [12.08, 15.16] |

### Coupling factor at each

| `cl` | raw coupling | bootstrap 95 % | has-peak subset | **conditional coupling** | bootstrap 95 % |
|---|---|---|---|---|---|
| *sampled* | 0.89× | [0.81, 0.98] | 1578 | 1.04× | [0.95, 1.15] |
| 50 fF | 1.05× | [0.96, 1.17] | 969 | 1.06× | **[0.98, 1.16]** |
| 100 fF | 0.95× | [0.88, 1.04] | 1181 | 1.06× | **[0.99, 1.15]** |
| 150 fF | 0.82× | [0.76, 0.88] | 1244 | 0.97× | **[0.91, 1.04]** |

**Every conditional interval covers 1.00.** There is no adverse coupling at any
pinned `cl`. See §4 — this retracts a wrinkle reported in the first pass.

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

- **B rises hard: 16.67 % → 21.96 % → 24.07 %.** More load capacitance pulls
  f_p2 = 1/(2π·R_L·C_L) downward, and with it the peak, into S3's
  1.25–2.5 GHz window.
- **A falls gently: 55.34 % → 48.99 % → 45.93 %.** The same load pole eats
  peaking magnitude, exactly as session 9c found when it discovered that
  lowering f_p2 does not move the peak down so much as extinguish it.
- The count of designs with a genuine interior peak *rises* over this range,
  969 → 1181 → 1244, then falls again past the optimum (§7).

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

It reinforces G40, and more cleanly after the G44 fix than before it.

**A retraction first.** The first pass of this experiment reported a real
adverse effect at one pinned value: conditional coupling 1.10× with a
bootstrap interval of [1.02, 1.20] at `cl` = 100 fF, which excluded 1.0. **That
does not survive.** With peak detection fixed it reads **1.06× [0.99, 1.15]**,
which covers 1.0. The signal was an artifact of the inflated has-peak
denominator — G44 was counting 1559 designs as having a peak where only 1181
do, and diluting the conditional statistic with designs that have no interior
maximum at all.

Post-fix, **every conditional interval at every pinned `cl` covers 1.00**:
1.06 [0.98, 1.16] · 1.06 [0.99, 1.15] · 0.97 [0.91, 1.04] · 1.00 [0.94, 1.08] ·
1.05 [0.97, 1.15]. There is no measurable coupling anywhere in this sweep,
adverse or otherwise. G40 does not merely stand; the one apparent
counter-example to it was a measurement error.

**The raw factor, meanwhile, moves a great deal: 1.05 → 0.95 → 0.82 → 0.74 →
0.68**, monotonically, while the conditional one stays inside 0.97–1.06. Two
statistics computed from the same simulations, one swinging 35 % and one flat.
The difference between them is entirely the no-peak population, which fails A
and B together and makes them look positively associated for a reason that has
nothing to do with S3.

*A correction to how the first pass explained this.* It claimed the raw factor
moved "in lockstep with the falling peak count". Post-fix that is not true —
the peak count is **hump-shaped** (969 · 1181 · 1244 · 1210 · 1148, maximal at
150 fF) while the raw factor falls monotonically, so it is not a one-to-one
tracking relationship. What the data supports is the weaker and sufficient
claim: **the raw statistic is contaminated by the no-peak population, is not
stable under a change of box, and must never be quoted without the conditional
one beside it.** How exactly it is contaminated is not established here.

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

| `cl` | A: peaking | B: f_peak | **S3** | 95 % CI | raw coupling | has-peak | cond. coupling (95 %) |
|---|---|---|---|---|---|---|---|
| 50 fF | 55.34 % | 16.67 % | **8.78 %** | [7.59, 10.14] | 1.05× | 969 | 1.06× [0.98, 1.16] |
| 100 fF | 48.99 % | 21.96 % | **11.27 %** | [9.92, 12.77] | 0.95× | 1181 | 1.06× [0.99, 1.15] |
| **150 fF** | 45.93 % | **24.07 %** | **13.54 %** | [12.08, 15.16] | 0.82× | 1244 | 0.97× [0.91, 1.04] |
| 250 fF | 39.04 % | 22.94 % | **12.09 %** | [10.69, 13.64] | 0.74× | 1210 | 1.00× [0.94, 1.08] |
| 400 fF | 33.49 % | 19.21 % | **9.52 %** | [8.28, 10.93] | 0.68× | 1148 | 1.05× [0.97, 1.15] |

*(The 250 fF row was measured on 1870 rather than 1890 simulated designs: that
run hit 20 transient ngspice failures under machine load, which did not
reproduce at all on a quiet re-run — 0/1890, identical seed. The effect on the
rate is immaterial, 12.09 % against 12.06 %, but it is why `s9_yield.py`
retries. See §9.)*

**150 fF is a genuine interior maximum, not an edge effect.** The yield rises
to it and falls away on both sides, and the fall to 400 fF is on disjoint
intervals ([12.08, 15.16] vs [8.28, 10.93]).

Stated honestly about resolution: **150 fF is not distinguishable from 250 fF
at this sample size** — the intervals overlap substantially. What the data
supports is "the optimum lies in roughly 150–250 fF", not "the optimum is
150 fF". Separating those two would need either more samples or a paired test
on the per-sample outcomes, and neither is worth doing for a parameter §6
argues should be fixed by the load, not by yield-maximisation.

Two mechanisms are visible end to end:

- **B is non-monotonic too**, peaking at 150 fF (24.07 %) and falling to
  19.21 % at 400 fF. Beyond the optimum, extra load capacitance stops moving
  the peak into the window and starts *extinguishing* it, and an extinguished
  response reports `f_pk` at the 10 MHz sweep start, so it fails B as well as
  A. This is session 9c's "lowering f_p2 does not move the peak down, it
  EXTINGUISHES it", measured across 9450 designs instead of two.
- **A falls monotonically throughout** (55.34 → 33.49 %), so past the optimum
  both marginals are being eaten at once, which is why the yield falls away
  faster on the high side than it climbed on the low side.

The count of designs with a genuine interior peak is itself hump-shaped —
969 · 1181 · 1244 · 1210 · 1148, maximal at 150 fF, the same place the yield
is. That is the cleanest single statement of what `cl` does: **there is a load
capacitance at which this topology is most able to produce a peak at all, and
S3's yield tracks it.**

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

---

## 9. Revision: every number here was re-measured after the G44 fix

The first pass of this experiment used a peak detector that could not tell a
genuine interior maximum from the edge of the `meas ac ... MAX` search range.
A response still rising at 50 GHz reported `f_pk` there, with a large and
entirely fictitious `peaking_db`, and the has-peak test (`peaking > 0.25 dB
and f_pk > 50 MHz`) passed it. Recorded as G44 at the time, fixed before the
corner work because every conditional statistic here depends on it.

The fix bounds the `MAX` search at 20 GHz and adds a `g_top` probe at the same
frequency, so `has_interior_peak` asks the question directly: **is the gain at
the peak above the gain at BOTH ends of the search range?** No frequency guard
is involved — a "reject anything within a decade of the edge" rule would reject
everything below 2 GHz, which lands inside S3's own 1.25–2.5 GHz window.

What changed, and what did not:

| | before | after |
|---|---|---|
| S3 yield, 50 fF | 165 · 8.73 % | 166 · 8.78 % |
| S3 yield, 100 fF | 213 · 11.27 % | 213 · 11.27 % |
| S3 yield, 150 fF | 256 · 13.54 % | 256 · 13.54 % |
| has-peak, 50 fF | 1673 | **969** (−42 %) |
| conditional coupling, 100 fF | 1.10× **[1.02, 1.20]** | 1.06× **[0.99, 1.15]** |

**The headline is untouched and the one contested statistic is retracted.**
150 fF remains the best tested value at 13.54 %, and the apparent adverse
coupling at 100 fF is gone.

One claim made while fixing it turned out to be **false**, and is recorded
because it is the sort of thing that gets assumed rather than checked: that
moving the search edge 50 → 20 GHz *cannot* change an S3 verdict, since a
design peaking above 20 GHz fails the window either way. It can — S3 moved
165 → 166 at 50 fF. `MAX` returns the largest sample in its range, so a design
with a small in-band peak and a larger out-of-band one reported the out-of-band
one before and reports the in-band one now. The bounded search is the more
useful of the two, since an equaliser is judged on the peak it puts where the
data is, but it is a behaviour change and not merely a guard.

**A second operational finding, which is why `s9_yield.py` retries.** One
2000-point run reported 20 ngspice failures; an identical re-run on a quiet
machine reported **zero**. They are transient — process launch or
temp-directory contention on Windows under load — not properties of any
design. Harmless here, because a failed run is simply excluded from the
denominator, but not harmless in a corner experiment, where scoring a
transient failure as "this design fails at SS/125 C" would bias the corner
yield downward and silently.
