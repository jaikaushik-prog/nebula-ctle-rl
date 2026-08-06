# PREDICTIONS — written before the run, kept whether or not they hold

**The rule.** Any experiment whose result could be argued for after the fact
gets a prediction committed to git **before** it runs. The commit timestamp is
the evidence. A failed prediction is a result and stays in this file with the
outcome written next to it; nothing here is ever edited to match what happened.

Precedent, from before this file existed:

* **G40** — the project's designated "strongest single sentence" (S3 is a
  coupled constraint) was falsified by the measurement that was supposed to
  confirm it. Retracted in `BOUNDS_REDERIVATION.md` §4.
* **10b's f_p2 prediction** — "the peak of a 1-zero/2-pole response sits near
  f_p2, so `cl` = 50 fF must give zero S3 yield." Measured: 8.73 %. Recorded in
  `CL_SENSITIVITY.md` §3 rather than quietly dropped, and it is the reason the
  analytic pre-screen is not expected to be a one-liner.

Format: **Prediction** (with the reasoning and the numbers it rests on) ·
**What would falsify the reasoning** · **Outcome** (filled in after, never
before).

---

## 1. `cl` as a screened context range — the corner-and-load-robust yield

**Written:** 2026-08-06, session 12, **before** `s9_yield.py` was changed to
screen over `cl` and before it was re-run.
**Experiment:** `python -m nebula.experiments.s9_yield --n 2000` with the
screen set extended to 3 corners × {`cl_lo`, `cl_hi`} = 6 evaluations per
design, promotion to 45 corners × {`cl_lo`, `cl_mid`, `cl_hi`}, using
`CL_RANGE.md`'s **`cl_lo` = 13.64 fF, `cl_mid` = 32.63 fF, `cl_hi` =
78.04 fF** (ratio 5.72×, 2.52 octaves).

### The owner's stated expectation

> *"I expect the yield to land between the 8.73 % swept figure and the 13.54 %
> pinned one."*

### My prediction: **it lands far below that, at essentially zero.**

**Point estimate: 0 / 1890 = 0.00 %**, Wilson 95 % [0.00, 0.20 %].
Consistent-with-my-reasoning band: **0 to 10 designs (0.00–0.53 %)**.

Reasoning, entirely from already-published numbers — no new simulation was run
to produce it:

1. **S3's f_peak window is exactly one octave** (1.25–2.5 GHz), and the
   derived `cl` range is **2.52 octaves**.
2. **f_peak moves as roughly `cl^-0.5`.** Two independent supports.
   *Measured:* `CL_SENSITIVITY.md` §2's probe moved one sample's f_pk
   9.55 → 6.61 → 5.50 → 3.16 GHz across `cl` = 50/100/150/500 fF; the log-log
   slope is **−0.48**. *Structural:* if the peak of the 1-zero/2-pole response
   sits near the geometric mean of f_p1 and f_p2, and only f_p2 depends on
   `cl`, the exponent is exactly **−0.5**. The two agree to 4 %.
3. **So a 5.72× spread in `cl` moves f_peak by 5.72^0.5 = 2.39×, i.e. 1.26
   octaves** — 26 % *wider* than the entire window it has to stay inside.
   A design centred in the window at `cl_mid` is 0.63 octaves from centre at
   each edge, against a half-width of 0.50.
4. **The escape route is closed by the physics.** A design could survive if its
   own f_peak were less `cl`-sensitive than `cl^-0.5`, which needs f_p2 far
   above the peak. But a 1-zero/1-pole response has no interior maximum at all
   — it plateaus — so f_p2 is what *creates* the peak. Pushing f_p2 away weakens
   or extinguishes the peak instead (session 9c, and `CL_SENSITIVITY.md` §7's
   hump-shaped peak count), which fails S3's other axis.
5. **The corner tax then applies on top**, at ~0.61× per `S9_YIELD.md` §4,
   to a number that is already near zero.

So the load spread, not the corner spread, is predicted to be the binding
mechanism — by a wide margin. **I expect this experiment to disagree with the
stated expectation, and to disagree in the direction of much lower.**

### Supporting predictions, all for the same run

| # | quantity | prediction |
|---|---|---|
| 1a | 3-corner yield at `cl_lo` **alone** (13.6 fF) | **2–5 %** — below the 8.20 % measured at 150 fF, because a small load pushes f_p2 and the peak *up*, out through S3's 2.5 GHz top edge |
| 1b | 3-corner yield at `cl_hi` **alone** (78 fF) | **5–8 %**, i.e. closer to the 150 fF figure but still under it |
| 1c | TT / 27 °C at **both** `cl` edges | **0–15 designs (0–0.8 %)**, against 13.49 % at the 150 fF pin. The load spread bites at nominal PVT too; corners are not what kills this |
| 1d | binding constraint, pooled | `S3_f_peak` share **rises above 45 %** (it is 42 % at 150 fF), and it becomes more dominant at `cl_lo` than at `cl_hi` |
| 1e | promotion tier | **empty, or ≤ 10 designs.** If non-empty, ≥ 90 % of promoted designs survive all 45 corners × 3 loads — G47's screen-exactness result should carry over |
| 1f | `S5_noise` / `S6_power` | still never the first failure. `cl` does not touch either |

### What would falsify the reasoning (as opposed to the number)

* A yield of a few percent **with** a measured per-design f_peak sensitivity
  materially weaker than `cl^-0.5` for a sizeable subpopulation. That would
  mean step 2 is wrong and the geometric-mean model of f_peak does not hold
  across the box — which would be a more interesting result than the yield.
* A yield near zero but for the **wrong reason** — e.g. dominated by
  `S3_peaking` or `saturation` rather than by `S3_f_peak`. The prediction is
  specifically that the *window* is what cannot be held, and 1d is the check.

### Planned follow-up, pre-registered so it is not a post-hoc rescue

If the screen yields **≤ 5 designs**, "0 %" on its own is not a useful number,
so the run will additionally report — from the six evaluations it already
makes, at no extra simulation cost — the counts passing all three corners at
`cl_lo` only, at `cl_hi` only, and at both. If those disjoint sets are large,
the honest statement is *"the CTLE can be made corner-robust at either load,
but not at both"*, and the quantitative follow-up is **the widest `cl` ratio,
centred on `cl_mid`, at which a non-zero corner-robust yield survives** —
measured on the union of the two sets only, which is cheap. That converts a
0 % into a specification: *how tightly the load must be pinned down before this
topology can be signed off.*

### Outcome — 2026-08-06, 15 255 SPICE runs, 49.3 min

**The number held. The reasoning behind it did not.** Both halves are worth
more than the number.

| | predicted | measured |
|---|---|---|
| **corner-and-load-robust yield** | **0 / 1890**, band 0–10 | **1 / 1890 = 0.05 %** [0.01, 0.30] | ✅ inside the band |
| owner's stated expectation | 8.73–13.54 % | 0.05 % | ❌ low by ~170× |
| 1a — 3 corners at `cl_lo` alone | 2–5 % | **2.28 %** (43/1890) | ✅ |
| 1b — 3 corners at `cl_hi` alone | 5–8 % | **6.24 %** (118/1890) | ✅ |
| 1c — nominal PVT at both loads | 0–15 designs (0–0.8 %) | **15 / 1890 = 0.79 %** | ✅ at the top edge of the band |
| 1d — `S3_f_peak` share > 45 %, worse at `cl_lo` | > 45 %, `cl_lo` > `cl_hi` | **82.5–84.9 % at `cl_lo`, 56.1–57.0 % at `cl_hi`** (42 % at the old 150 fF pin) | ✅ |
| 1e — promotion tier ≤ 10, ≥ 90 % survive | ≤ 10; ≥ 90 % | **1 promoted, 1/1 = 100 % survived** | ✅ |
| 1f — S5/S6 never the first failure | never | S5 **never**; S6 **twice** in 11 340 runs | ⚠️ wrong as worded |

**1f is a miss and is recorded as one.** "Never" is right for S5 and wrong for
S6 by two rows — both at `ff/1.05/0`, missing by 0.06 mW, which is exactly what
session 10d saw (2 occurrences in 5 670 runs). The claim should have been "S5
never; S6 at the noise floor of the count".

### The reasoning was wrong, and the follow-up measured how

Step 2 of the prediction assumed f_peak moves as `cl^-0.5`. Measured on 200
designs at 5 loads spanning the derived range:

* **the median exponent is −0.349**, range −0.549 … −0.243 — materially weaker
  than −0.5, and weaker than `CL_SENSITIVITY.md`'s single probe (−0.48), which
  turns out not to have been representative;
* so a 5.72× load range moves f_peak by **1.84× = 0.88 octaves**, *not* the
  1.26 octaves the prediction computed — **less than S3's 1.00-octave window**,
  which by the prediction's own logic should have left room for a few percent
  of designs to survive.

That is precisely the falsification condition pre-registered above ("a measured
f_peak sensitivity materially weaker than `cl^-0.5`"), except it arrived
alongside the predicted near-zero yield instead of alongside the few-percent
yield it was supposed to imply. **The right answer for a wrong reason is a
wrong reason.**

**What actually kills the designs** — two mechanisms, and the prediction only
had one:

1. **The slack is real but tiny.** 0.88 octaves of movement inside a 1.00-octave
   window leaves **0.12 octaves** of centring slack. Session 11 measured f_peak
   as quantised at **0.0664 octaves** by `meas ac MAX` on an `ac dec 50` grid,
   so that slack is about **2 of the 15 distinct f_peak values the window
   holds**. The design has to be centred to within one grid point.
2. **Most designs do not move out of the window — they lose the peak
   entirely.** **146 of 200 designs (73 %) do not keep an interior maximum
   across the load range at all.** This failure mode is invisible to an
   exponent, because a design with no peak has no f_peak to differentiate. It
   is session 9c's "lowering f_p2 does not move the peak down, it EXTINGUISHES
   it", now measured across the load axis.

### The result that turns 0.05 % into a specification

The per-load-edge counts (free, from the same six evaluations):

```
corner-robust at cl_lo = 13.6 fF alone     43 / 1890 = 2.28 %
corner-robust at cl_hi = 78.0 fF alone    118 / 1890 = 6.24 %
corner-robust at EVERY load                 1 / 1890 = 0.05 %
corner-robust at ANY load                 160 / 1890 = 8.47 %
corner-robust at exactly ONE load         159 / 1890 = 8.41 %
```

**159 of the 160 designs that are corner-robust at one load edge are not
corner-robust at the other.** The joint set is not small because the per-load
sets are small — 8.47 % of the box is corner-robust *somewhere* in the load
range, which is essentially session 10d's 8.20 %. It is small because the sets
are **disjoint**. Under independence the joint would have been 2.68 designs;
it is 1.

And the ladder measurement on the single survivor: it passes across
**13.6–78.0 fF = 5.72×** and fails at the next rung on both sides (12.0 fF and
93.1 fF), so its tolerance is **at least 5.72× and at most 7.76×**. It fits the
demanded range with **less than one ladder step of margin on either side**.
There is exactly one such design in 1890.

### What this changes

The load range, not the PVT corner set, is now the binding constraint: corners
cost 39 % of the nominal winners (session 10d), the load range costs **99.4 %**
of them. Written up in `S9_YIELD.md` §8.

---

## 2. The tail transistor — the S9 re-run with a real current mirror

**Written:** 2026-08-06, session 13, **before** `s9_yield.py` was re-run at
`--n 2000`. The code, the tests and this entry are committed together, before
the sweep.
**Experiment:** `python -m nebula.experiments.s9_yield --n 2000`, identical to
session 12b except that the tail is a **current mirror** instead of two ideal
current sinks — one tail device per side, gates driven by a diode-connected
reference at ratio `N = 8`, sized by the rule `w_tail = i_side x 111.2k um/A`
at `l_tail = 0.5 um` (the `ss/0.95/125 C` width for `vdsat_tail = 0.20 V`).
`I_ref` remains ideal. S6 is now billed on the **measured** supply current.

### What this is being compared against

Session 12b, same box, same seed, **same 1890 designs**:

```
nominal PVT, both loads      15 / 1890 = 0.79 %
3 corners x 2 loads           1 / 1890 = 0.05 %
45 corners x 3 loads          1 / 1890 = 0.05 %
headroom rejections           26 designs per (corner, load) column
```

### Pilot data I have seen, declared

A 38-design pilot (`--n 40`, a *different* Latin-hypercube draw from the
n = 2000 one) ran while the plumbing was being checked. It showed 0/38 robust,
and `tail_saturation` violated by 15.8 % of designs at `ss/0.95/125 C @ cl_lo`
while never once being ranked the *worst* failure. The predictions below are
informed by that, and it is stated here rather than presented afterwards as
foresight.

### Predictions

| # | quantity | prediction |
|---|---|---|
| 2a | **corner-and-load-robust yield (3 corners x 2 loads)** | **0 / 1890**, band **0-2**. Most likely 0 |
| 2b | nominal PVT at both loads | **6-16 designs**, i.e. down from 15 but not to zero |
| 2c | headroom rejections | **UNCHANGED at 26** per column |
| 2d | a `tail_saturation` row appears in the binding-constraint (first-failure) table | **YES, but at a SMALL share: 0-3 %** |
| 2e | `tail_saturation` **violation** share (the new table) | **10-20 %** at every screen point |
| 2f | S5 is still never the first failure | yes — noise rises ~1.6x to ~0.44-0.58 mV against a 1.5 mV spec |
| 2g | S6 first failures | **still ~2 in 11 340**; measured power lands within ±3 % of requested |
| 2h | `S3_f_peak` remains the dominant first failure, and still worse at `cl_lo` | yes |
| 2i | G54 NaN hard-failure rate | **0.1-1 %** of runs, all `inoise_total = -nan(ind)` |

### The reasoning

1. **2a is a coin flip weighted to zero.** 12b's single survivor "fits the
   demanded load range with less than one ladder rung of margin". Fitting a
   real tail perturbs it three ways, all of the same order as that margin:
   the mirror delivers **−7.7 %** of the requested current at TT (measured), so
   `gm` drops ~3 %; the tail's source-node capacitance and finite `r_o` shift
   S3 peaking by **−0.32 to +0.29 dB** for a rule-sized tail (measured); and
   `v(source)` moves by ~+10 mV. Any one of those can push a design with
   sub-rung margin out. I do not expect a *new* design to appear in its place,
   because the perturbation is not systematically favourable.
2. **2c is near-certain and is stated to make a point, not to be brave.**
   `headroom_ok_1v8` does not read the tail and was deliberately not changed.
   The tail's requirement is `VCM − Vgs(I, W_in, L_in) > vdsat_tail`, and
   neither `Vgs` nor `vdsat` exists without simulating, so it **cannot** be an
   analytic pre-check. It is enforced as a SPICE-measured spec row instead. If
   this number moves, something else changed.
3. **2d and 2e differ by an order of magnitude, and that gap is the
   prediction.** The first-failure table ranks by normalised shortfall, so a
   constraint that is usually accompanied by a larger one is systematically
   invisible to it. `tail_saturation` misses by tens of millivolts while
   `S3_f_peak` misses by **17 GHz**, so the tail will almost always lose the
   ranking. 12.2 % of the 1890 designs have `v(source) < 0.20 V` at TT
   (measured off `robust_geometry_data.csv`), and the rule puts `vdsat_tail` at
   ~0.20 V at SS by construction — hence 2e's 10-20 %.
4. **2f follows from headroom, not from the tail being quiet.** The tail is now
   the LARGEST noise contributor (66 % of the noise power, measured), but S5
   started 5.5x inside spec and ends 3.4x inside it.

### What would falsify the reasoning (as opposed to the number)

* **A yield ABOVE 12b's 1/1890.** That would mean the tail's perturbation is
  systematically *favourable* — plausible in one specific way I do not expect
  to dominate: at `cl_lo` the binding failure is `f_peak` too HIGH, and a
  mirror that delivers less current lowers `f_peak`. If the yield rises, that
  is the mechanism to look for, and it would be a real finding rather than
  noise.
* **`tail_saturation` at a large FIRST-failure share (>10 %).** That would mean
  the tail is failing on designs that otherwise pass S3 cleanly — i.e. it is
  carving out a genuinely new region rather than adding a constraint on top of
  an already-failing one. More interesting than the yield.
* **2c moving.** Would mean something reads the tail that should not.

### Outcome — 2026-08-06, 15 255 SPICE runs, 35.2 min, 8 workers

**The yield did not move: 1 / 1890, and it is the SAME design** (index 432,
identical parameters). 7 of 9 predictions held; **2e and half of 2g are
misses** and are recorded as such.

| # | predicted | measured | |
|---|---|---|---|
| 2a | 0/1890, band 0-2, "most likely 0" | **1 / 1890 = 0.05 %** [0.01, 0.30] | ✅ in band, though "most likely 0" was wrong |
| 2b | 6-16 designs | **15 / 1890 = 0.79 %** | ✅ (and *identical* to 12b) |
| 2c | headroom rejections UNCHANGED | **52, exactly as in 12b** (13 per 0.95-V column x 4) | ✅ |
| 2d | `tail_saturation` in the first-failure table at 0-3 % | **0.1-1.5 %** across the six screen points | ✅ |
| 2e | `tail_saturation` violated by 10-20 % **at every screen point** | **2.6 % (ff/1.05/0) to 13.3 % (ss/0.95/125)** | ❌ wrong as worded |
| 2f | S5 never the first failure | **never** — and it never appears in the violation table either | ✅ |
| 2g | S6 first failures still ~2 | **exactly 2**, both at `ff/1.05/0` | ✅ |
| 2g | measured power within ±3 % of requested | **−7.3 %** | ❌ |
| 2h | `S3_f_peak` dominant, worse at `cl_lo` | **84.4 % vs 56.2 %** at TT | ✅ |
| 2i | G54 NaN rate 0.1-1 % | **0.07 %** (8/11 340) and **0.11 %** (4/3 780) | ⚠ at/below the bottom edge |

### Why 2e missed, and it is the more interesting of the two

I predicted 10-20 % from the fact that **12.2 % of the 1890 designs have
`v(source) < 0.20 V` at TT**, reasoning that the sizing rule puts
`vdsat_tail` at ~0.20 V. That was right about the *rule* and wrong about where
it applies. **The rule sizes the tail at `ss/0.95/125 °C`, the corner that needs
the most width**, so at every *other* corner the tail is deliberately
oversized and its `vdsat` is well below 0.20 V — measured 0.134 V at
`ff/1.05/0` against 0.201 V at `ss/0.95/125` for the surviving design. The
violation rate therefore tracks the corner, not a single threshold:

```
        ss / 0.95 / 125 C      13.3 %      <- the corner the rule was sized at
        ss / 0.95 /   0 C       6.3 %
        tt / 1.00 /  27 C       5.2 %
        ff / 1.05 /   0 C       2.6 %
```

**The conservative sizing choice is what bought that**, and it is a result
rather than an accident: sizing at the worst corner costs width everywhere and
buys a 5x reduction in tail-saturation failures at the best corner.

### Why the second half of 2g missed

I said measured power would land within ±3 % of requested. It is **−7.3 %**,
and the arithmetic was available before the run: the mirror delivers −7.7 % into
each of two sides while the reference branch adds +1/2N = +6.25 % of one side,
so `1.971 / 2.125 = 0.928`. I compared against the wrong baseline. Against
**12b's** billing (2.000 units) it is only **−1.4 %**, which is why S6 did not
get harder — and that is the number the ±3 % claim should have been about.

### The pre-registered falsification condition, and what actually happened

I wrote:

> *A yield ABOVE 12b's 1/1890 ... would mean the tail's perturbation is
> systematically favourable — plausible in one specific way I do not expect to
> dominate: at `cl_lo` the binding failure is `f_peak` too HIGH, and a mirror
> that delivers less current lowers `f_peak`.*

**The mechanism is real and it is present; it just does not dominate.** A
paired run over 600 designs at `cl_hi` (same design, same corner, ideal tail vs
mirror — so the only difference is the tail):

```
        ff / 1.05 / 0 C     6 GAINED,  5 LOST     net  +1
        ss / 0.95 / 125 C   6 GAINED, 10 LOST     net  −4
```

and over the full 1890 the six screen columns moved
`−7, −7, +5, +7, +0, −8`. So the tail is **a small roughly symmetric reshuffle
across the S3 boundaries, plus a one-sided loss at slow-hot from
`tail_saturation`** — 4 of the 10 SS losses are ranked `tail_saturation`,
against 1 of the 5 at FF. The gains at both corners are mostly designs that had
been failing `S3_peaking`, pulled back inside the window by the mirror's ~2 %
`gm` reduction and ~0.05 dB peaking reduction.

**I should not claim "the tail helps at FF".** +1 on 600 paired designs is
noise; what the data supports is *"the tail costs designs at slow-hot and is
roughly neutral at fast-cold"*.

### What actually changed, given the headline did not

The **corner-robust-at-some-load** population fell **160 → 146 (−8.8 %)**:

```
                                  12b (ideal tail)   13b (real tail)
        robust at cl_lo alone            43                39
        robust at cl_hi alone           118               108
        robust at ANY load              160               146
        robust at EVERY load              1                 1
```

So the tail is a **real but second-order** tax on this population — against the
load range's 99.4 %. **The load remains the binding constraint by a wide
margin**, and the tail did not turn corner robustness into a coupled constraint
the way §8 of `S9_YIELD.md` hoped it might.

### The survivor, now with a real tail under it

Design 432 (`w_in 100 um, l_in 0.399 um, nf 8, i_bias 3.25 mA, rs 319,
cs 1.90 p, rl 565, vcm 1.407`) gets a tail of **W 180.8 um / L 0.5 um / nf 8**,
reference 22.6 um / nf 1, `I_ref` = 203 uA. Across the six screen points:

| corner @ load | `vds_tail` | `vdsat_tail` | margin | peaking | `f_peak` | mirror err |
|---|---|---|---|---|---|---|
| ss/0.95/125 @ lo | 0.4479 | 0.2006 | **+0.2473** | 6.058 dB | 1.995 GHz | −4.7 % |
| ss/0.95/125 @ hi | 0.4479 | 0.2006 | +0.2473 | 5.223 dB | **1.259 GHz** | −4.7 % |
| ff/1.05/0 @ lo | 0.4973 | 0.1342 | +0.3631 | 8.499 dB | **2.399 GHz** | −4.0 % |
| ff/1.05/0 @ hi | 0.4973 | 0.1342 | +0.3631 | 7.310 dB | 1.514 GHz | −4.0 % |
| ss/0.95/0 @ lo | 0.4358 | 0.1444 | +0.2914 | 7.659 dB | 2.188 GHz | −5.3 % |
| ss/0.95/0 @ hi | 0.4358 | 0.1444 | +0.2914 | 6.602 dB | 1.380 GHz | −5.3 % |

**Its tail has comfortable headroom** (+0.25 to +0.36 V), so it did not survive
by luck on that axis. What it does spend is the **window**: `f_peak` ranges
1.259-2.399 GHz, i.e. **0.93 of the 1.00-octave S3 window**, confirming 12b's
"less than one ladder rung of margin" from a second direction.

---

## 3. The tunable experiment — S3 says the peaking is tunable, so score that

**Written:** 2026-08-06, session 14, **before** `experiments/tunable.py` was run
at `--n 2000`. Code, tests and this entry are committed together, before the
run.
**Experiment:** the design vector splits into **FIXED** (`w_in, l_in, nf_in,
i_bias, rl, vcm_in`, tail geometry) and **TUNABLE** (`rs, cs`). A design is
*tunable-robust* iff, for **every** (corner, load) point, there **exists** an
`(rs, cs)` setting meeting all specs. Grid: 11 x 6 geometric over the box
bounds **plus each design's own setting** (67 total, G52), at the 3 screen
corners x 2 load edges.

### What this is compared against

Session 13, same box, same seed, same 1890 designs, **fixed** sizing:

```
fixed setting, every (corner, load)      1 / 1890 = 0.05 %
fixed setting, robust at SOME load     146 / 1890 = 7.72 %
```

### Pilot data I have seen, declared

Two smoke runs (`--n 30` and `--n 40`) on **different** Latin-hypercube draws
from the n = 2000 one, run while the plumbing was being checked. The n = 38
one gave 15.8 % tunable-robust, adaptation class `load` for 100 % of them, an
`R_s` span of 67.5-407 ohm, 2 settings per design, and **S5 violated nowhere**
with a worst input-referred noise of 1.38 mV against the 1.5 mV spec. The
predictions below are informed by that and it is stated here rather than
presented afterwards as foresight.

### Predictions

| # | quantity | prediction |
|---|---|---|
| 3a | **tunable-robust yield** | **10-25 %**, point estimate **~16 %**. Against 0.05 % fixed — a **~300x** improvement |
| 3b | G52 consistency gate | **PASSES**: the own-setting column reproduces exactly **1** and **146** |
| 3c | dominant adaptation class | **`load`**, at **> 60 %** of tunable-robust designs. `none` present but a minority; `load+corner` **< 20 %** |
| 3d | `R_s` tuning span | widens toward the full box, **> 5x**; `C_s` likewise |
| 3e | settings per design | median **2-3**, max **<= 8**, i.e. a **<= 3-bit** DAC |
| 3f | **S5 VIOLATED somewhere** (the pre-registered one) | **YES** — in **0.01-2 %** of failing evaluations, and the worst input-referred noise on the grid **exceeds 1.5 mV** |
| 3g | S5 RANKED WORST | **< 0.1 %** of failing evaluations — nearly always hidden behind an S3 failure |

### The reasoning

1. **3a rests on the mechanism 12b identified.** The load range kills 99.4 % of
   designs because the per-load robust sets are large (43 and 118) and almost
   **disjoint** — 159 of 160 designs were robust at exactly one load edge.
   Tuning is precisely the freedom to move *between* those two sets, so it
   should recover a large fraction of the 7.72 % that worked at *some* load,
   plus designs that worked at neither with their own `(rs, cs)` but do with
   another. ~16 % is roughly "the union, plus some".
2. **3c is the interesting one, and it is a claim about physics not statistics.**
   `cl` moves `f_p2` and hence `f_peak`; `rs`/`cs` move the zero and `k`. If a
   single setting per load holds across all three corners, the load-induced
   shift is bigger than the corner-induced one — which is exactly what the
   three-line cost table says (load 99.4 %, corners 39 %). **`load` dominating
   is the tunable-domain echo of that table.**
3. **3f is the first time noise has been predicted to bind anything in this
   project.** `R_s` contributes `4kT*R_s` directly to the input-referred noise,
   and the budget just lost 1.61x to the two tail devices (S5 headroom 5.5x ->
   3.4x, `TAIL_DEVICE.md` §4). The smoke already reaches **1.38 mV at
   `rs = 1000`, 92 % of the 1.5 mV spec**, on 28-38 designs. At 1890 designs
   there will be samples with lower `gm` (small `W_in`, low `i_bias`), where the
   same `R_s` refers more noise to the input. **This is the `vdsat` coupling in
   `TAIL_DEVICE.md` §4 becoming live**, one experiment after it was written
   down.
4. **3g follows from session 13's lesson.** High `R_s` raises noise *and*
   drives peaking through S3's 12 dB ceiling, so S5 will almost always travel
   with a larger S3 violation and lose the first-failure ranking. This is why
   `PointResult` records **every** violated spec and not just the worst — the
   question is unanswerable from a `first_fail` column alone.

### What would falsify the reasoning (as opposed to the number)

* **A high yield with `none` as the dominant adaptation class.** That would mean
  one setting covers both load edges, i.e. the load spread is *not* what tuning
  is fixing — and the 12b mechanism (disjoint per-load sets) would need
  re-examining.
* **S5 violated nowhere, even at `R_s` = 1000 ohm over 1890 designs.** Then
  noise has never bound anything in this project and the S5 spec is simply
  loose for this topology at this supply. That is a legitimate finding and
  should be stated as one rather than quietly dropped.
* **3b failing.** The grid contains each design's own setting, so a disagreement
  with session 13 means the `alter` path and the fresh-parse path differ —
  which the bit-identical test says they do not. It would invalidate the whole
  run, not just this line.

### Outcome

*(to be filled in after the run, whichever way it goes)*
