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

---

## 4. The channel family — is a 1-tap DFE enough?

**Written:** 2026-08-07, session 16, **before** `experiments/channel_family.py`
was run over the full grid and before `--compression` was run at all. Code,
tests and this entry are committed together, before the run.

**Experiment:** the invented 1.0 dB DC-loss constant is deleted and replaced by
a derived channel family, `IL_dB(f) = A*sqrt(f) + B*f`, parameterised by
**insertion loss at 2.5 GHz** (7 points, 3-12 dB, read off S3's own tunable
range) crossed with the **skin/dielectric split** `r` (0.8 / 0.5 / 0.2) — 21
members. Phase is minimum-phase, reconstructed from `ln|H|` by the
real-cepstrum fold, and gated on pre-`t = 0` energy. The PCIe Gen2 transmitter
enters as a 2-tap FIR at the mandated **-3.5 dB** de-emphasis, with the -6 dB
option and a no-de-emphasis control. Cursors `h_-2..h_4` are sampled at 64
samples/UI at the phase maximising `h0`; residual ISI after an ideal 1-tap DFE
is `(sum|h_k|, k<0) + (sum|h_k|, k>=2)` over the whole 512 UI buffer, `/ h0`.

### THE PRE-REGISTERED QUESTION (task 5e, verbatim)

> *At what insertion loss, if any, does a 1-tap DFE become insufficient? If the
> answer is "below 12 dB", say so plainly — it means S3's top of range and S8
> cannot both be met with the mandated topology.*

### My answer, committed before the grid was run: **nowhere in 3-12 dB.**

The eye stays **open** at every member of the family, channel-only and with a
matched CTLE, at every de-emphasis setting. **S2's mandated topology is
adequate for the channel S3 implies**, and the interesting number is not a
failure point but how little margin is left at the top of the range.

### Pilot data I have seen, declared

Four family members were run while the numerics were being checked, and they
inform everything below. Stated here rather than presented afterwards as
foresight:

* channel-only residual, mandated de-emphasis: **0.612 at (12 dB, r = 0.8)**,
  **0.383 at (12 dB, r = 0.2)**, **0.080 at (3 dB, r = 0.8)**;
* (12 dB, r = 0.5) with an 8.5 dB matched CTLE: residual **0.280**, eye
  **484 mV** at unity CTLE DC gain, against **159 mV** channel-only;
* pre-`t = 0` energy falls as a clean power law with buffer length —
  8.7e-05 / 1.3e-05 / 1.8e-06 / 2.5e-07 / 3.5e-08 at n_fft = 4096 ... 65536 —
  so it is tail aliasing, not a phase error, and 32768 clears the 1e-6 gate;
* `FR4_MICROSTRIP.natural_skin_fraction(2.5 GHz) = 0.654`, and a balanced
  12 dB member is **17.3 inch** of it;
* a lossless channel reproduces the TX pulse to 1e-12, and the UI-spaced
  cursors sum to the transmitter's long-run level to 7 figures;
* the reference device reproduces its published numbers exactly at
  `l = 0.15 um` — gm 12.62 mS, gm/I_D 8.42, v(src) +0.343 V, A_dc 5.05 dB,
  1 dB swing **1426.9** mVpp against a published **1427**.

**Not seen:** the full 21-member grid, any CTLE-in-front number other than the
one above, every reflection number, and the entire `--compression` stage.

### Predictions

| # | quantity | prediction |
|---|---|---|
| 4a | **eye closed anywhere in the family** (any split, any de-emphasis, channel-only) | **NO.** Worst residual **0.55-0.70**, at (12 dB, r = 0.8), no de-emphasis |
| 4b | worst residual **with a matched CTLE** in front | **< 0.40** across the whole family |
| 4c | split sensitivity at fixed 12 dB: residual(r = 0.8) / residual(r = 0.2) | **1.5-1.8x**, and the ratio holds to within +/-0.2 at 9 dB and 6 dB too |
| 4d | de-emphasis effect on the DFE tap at 12 dB | `h1/h0` falls **40-70%** from no-de-emphasis to -3.5 dB, while the residual (which a 1-tap FIR barely touches) moves **< 25% relative** |
| 4e | the stated reflection probe (rho 0.05 @ 2 UI, 0.02 @ 5 UI) | residual rises by **+0.05 to +0.09 absolute** — two modest echoes worth as much as the entire smooth tail beyond ~5 UI |
| 4f | **S8 vertical (100 mV)** at the matched CTLE, unity-DC-gain normalisation | met everywhere, with **required A_dc in 0.15-0.45 V/V** — comfortably below the reference device's measured 1.79 V/V. S8 vertical is **not** the binding spec |
| 4g | compression, convention C (peak distortion through the real pulse response) | lands **between** conventions A and B; **2-5 of the 7 loss points compress** |
| 4h | the "1.22x at 3 dB" reading | **does not survive as 1.22x.** Under C at 3 dB I expect **0.9-1.6**; under B it should fall ~25% from its old value, because de-emphasis cuts the long-run level from 0.713 V to 0.535 V |
| 4i | how much of S3's range is actually called for | with the mandate the burden spans **-0.5 to +8.5 dB**, so **the top 3.5 dB of S3 is never required on this family**, and at 3 / 4.5 / 6 dB of loss the burden sits BELOW S3's 3 dB floor |

### The reasoning

1. **4a rests on arithmetic that was available before the run.** 12 dB at
   Nyquist is a *mild* channel at 5 Gbps: one UI is 200 ps, and a channel whose
   loss at the symbol rate is a factor of four spreads a pulse over a handful of
   UI, not tens. The pilot's 0.612 at the worst corner of the family is already
   the answer; the prediction is that no other member exceeds it, because the
   residual rises monotonically in loss and in `r`, and (12 dB, r = 0.8) is the
   corner of both.
2. **4c is the claim that a scalar cannot represent a channel**, and it is the
   one genuinely reusable idea in the APCCAS paper. Skin effect's `sqrt(f)`
   spends its loss early and rolls off slowly, leaving a long algebraic tail a
   DFE cannot reach; dielectric loss is linear in `f`, rolls off faster in-band
   and leaves a shorter one. Same headline number, different DFE problem. **If
   4c comes out near 1.0, the split axis is decoration** and the family should
   collapse back to seven members.
3. **4d follows from what the FIR is.** A 2-tap TX FIR with one post-cursor tap
   is a post-cursor pre-canceller: it subtracts `|c1|` of the previous symbol,
   which is exactly what `h1` describes. It cannot touch `h2` and beyond, so the
   residual — which excludes `h1` by definition — should barely move.
4. **4e is where the honest limit of this model sits.** `A*sqrt(f) + B*f` has no
   impedance discontinuities, and reflections are the ISI a DFE handles worst.
   Two echoes with round-trip amplitudes summing to 0.07 land at 2 and 5 UI,
   both outside a 1-tap DFE's reach, so to first order they add ~0.07 to the
   residual directly. If they add materially MORE, the echo is interacting with
   the smooth tail and "reflections are a small correction" is wrong.
5. **4g/4h are the ones I am least confident about**, and the reason is worth
   stating: conventions A and B are both *proxies* for a worst-case pattern, and
   nobody in this project has ever computed the actual worst-case pattern. C
   does. I expect C to exceed B, because B pairs a long-run level (a DC
   quantity) with the peak gain (an AC quantity) and that combination is not a
   real waveform; and to exceed A, because A ignores the low-frequency content
   entirely. **If C comes out BELOW both, I have the direction of the
   peak-distortion bound wrong and should say so.**

### What would falsify the reasoning (as opposed to the number)

* **An eye that closes channel-only at 12 dB but opens with the CTLE.** That
  would mean the residual is dominated by content the CTLE can equalise, which
  contradicts the framing that a long smooth tail is what a 1-tap DFE cannot
  reach — and it would make the CTLE, not the DFE, the load-bearing block.
* **4c near 1.0.** Then the split axis carries no information, and "a scalar
  cannot represent a channel" is *our assertion* rather than a measurement. It
  must not then be presented as measured.
* **4e materially above +0.09.** Then reflections are not a small correction,
  and the whole analytic family is a lower bound on the DFE's difficulty — a
  bigger caveat than the one currently written into `link/channel.py`.
* **4f failing** — a required DC gain above the measured 1.79 V/V — would move
  S8 vertical from "not binding" to "binding", and would be the first time an
  eye-height spec constrained anything in this project.

### Outcome — 2026-08-07, 21 channels x 3 de-emphasis settings + 66 SPICE runs

**The headline held; four of the nine supporting predictions did not.** The
misses are the more useful half and two of them changed a published number.
Full write-up: `nebula/CHANNEL_MODEL.md`.

| # | predicted | measured | |
|---|---|---|---|
| **4a headline** | eye OPEN everywhere in 3-12 dB; a 1-tap DFE is sufficient | **open at all 21 members, all 3 de-emphasis settings, with and without a CTLE** | ✅ |
| 4a band | worst residual **0.55-0.70** at (12 dB, r = 0.8), no de-emphasis | **0.8467** at exactly that point | ❌ location right, band wrong |
| 4b | worst residual with a matched CTLE **< 0.40** across the family | **0.4914** (12 dB, dielectric, no de-emphasis); **0.3007** under the Gen2 mandate | ❌ as worded |
| 4c | split ratio at 12 dB **1.5-1.8x**, holding to +/-0.2 at 9 and 6 dB | **1.598** at 12 dB ✅; 1.660 at 9 dB ✅; **1.804** at 6 dB and **1.985** at 3 dB | ⚠ number right, "roughly constant" wrong |
| 4d | `h1/h0` falls **40-70%** with de-emphasis; residual moves **< 25%** | h1/h0 **0.3334 -> 0.1405 = -57.9%** ✅; residual **0.8467 -> 0.6133 = -27.6%** ❌ | ⚠ half |
| 4e | reflection probe adds **+0.05 to +0.09** absolute | **+0.064 … +0.122**, median +0.085 | ⚠ true at low loss, exceeded at high |
| 4f | S8 met everywhere, required A_dc **0.15-0.45 V/V** | **0.181-0.217 V/V** (-13.3 to -14.9 dB) | ✅ |
| 4g | convention C lands **between** A and B; **2-5 of 7** compress | **5/7 compress** ✅; but **C exceeds BOTH** A and B at 3-7.5 dB | ⚠ count right, ordering wrong |
| 4h | 1.22x at 3 dB does **not** survive; C at 3 dB in **0.9-1.6** | C at 3 dB = **1.51** ✅; **1.22x survives EXACTLY under convention A** ❌ | ⚠ half |
| 4i | burden **-0.5 … +8.5 dB**; top 3.5 dB of S3 never called for | exactly that (it is arithmetic, and is recorded as such, not as foresight) | ✅ |

### The four things I got wrong, and why each one matters

**1. The 4a band was computed from the wrong configuration.** I quoted 0.55-0.70
from a pilot measured **with** the mandated de-emphasis and then attached it to a
row **without** de-emphasis. With de-emphasis the measurement is **0.6133** —
dead centre of my band. Without it, 0.8467. The location was right, the number
was an apples-to-oranges slip, and it is recorded as a miss rather than
retro-fitted with the qualifier that would rescue it.

**2. 4c's mechanism was wrong in an interesting direction.** I predicted the
skin/dielectric ratio would be roughly constant across the loss axis. It is
**monotonically decreasing**: 1.985 at 3 dB down to 1.598 at 12 dB. The reason is
that at high loss *both* mechanisms have spread the pulse over many UI and the
residual is dominated by the shared long tail, while at low loss the difference
between "a small early spread" and "a small late spread" is proportionally
larger. **The split axis matters MOST where the channel is easiest** — which is
the opposite of where I would have said to look.

**3. 4d underestimated what a TX FIR does.** I reasoned that a 2-tap FIR is a
`h1` pre-canceller and therefore cannot move a residual that excludes `h1` by
definition. It moved it **27.6%**, not "< 25%". The reasoning is not wrong so
much as incomplete: the FIR reshapes the whole pulse, so `h2, h3, ...` all move
too. A separate observation from the same table, not predicted: at **-6 dB**
de-emphasis, `h1/h0` on a 12 dB skin channel is **+0.0066** — the Gen2 option
almost exactly annihilates the first post-cursor on its own.

**4. 4g/4h — the peak-distortion number is the biggest miss and the most
valuable result.** I predicted convention C would land *between* A and B.
It **exceeds both** at 3-7.5 dB (1.51 vs 1.22 and 1.16 at 3 dB). And 4h's first
clause is simply wrong: **the 1.22x at 3 dB survives digit for digit** under its
own convention, because that convention reads Nyquist content through Nyquist
gain and neither the deleted constant nor the de-emphasis touches either one.
So `BOUNDS_REDERIVATION.md` §2's blockquote was right that a made-up constant
decided the *C3* table, and wrong to imply the headline 1.22x hung on it.
**The honest measurement is worse than either proxy: 1.51x at 3 dB, and 5 of 7
loss points compress.**

### The pre-registered falsification conditions, and what happened to them

* *"An eye that closes channel-only at 12 dB but opens with the CTLE"* — did not
  occur; the eye never closes.
* *"4c near 1.0 — then the split axis is decoration"* — **did not occur.** The
  ratio is 1.60-1.99, so the split axis carries real information and "a scalar
  cannot represent a channel" is now **measured** rather than asserted.
* *"4e materially above +0.09 — then reflections are not a small correction"* —
  **FIRED, at the top of the family.** +0.122 at 12 dB skin-dominated, which
  takes the channel-only eye from 118 mV to **81 mV, below S8's floor**. The
  mechanism I had not stated: an echo is a copy of the *whole* response, so at
  high loss it brings its own spread tail. **Every residual in this task is
  therefore a lower bound**, and `CHANNEL_MODEL.md` §8 and §12 say so.
* *"4f failing"* — did not occur. S8 vertical is met with the CTLE
  **attenuating** by 13-15 dB, i.e. 8.6x more gain available than needed.

### One thing measured that no prediction covered, and it should have

The §6 design equations **over-predict the Nyquist boost by +0.77 to +1.47 dB**
on this sweep, growing with `R_s`, because they neglect `r_o`. Convention C
integrates the pulse response *through* that model, so using it uncalibrated put
3 dB at **1.93x** instead of 1.51x — **a 28% error in the headline from a 1.5 dB
error in a gain.** The fix is a one-parameter calibration to the measured boost
with the peaking and peak frequency left as independent checks (residuals
+0.094-0.232 dB against §5.3b's 0.5 dB limit). I should have predicted that the
analytic model would need checking before being integrated; I did not, and the
first version of the compression table was wrong because of it.

---

## 5. The `RL` bottom-plate parasitic COMPRESSES the load range, and may help

**Written:** 2026-08-07, session 17, **before** the `cl` budget is re-derived
and before the load screen is re-run with drawn passives. Registered by the
owner in the session-17 review; recorded here in their words and reasoning
rather than paraphrased, because the prediction is theirs.

**Experiment it applies to:** `PASSIVES.md` §6 item 4 — fold the `res_po`
bottom-plate parasitic into `CL_RANGE.md`'s budget, then re-run
`s9_yield.py`'s load screen against the corrected range.

### The state of play that makes this worth predicting

Session 17 measured (G66) that drawn passives move `f_peak` by up to **0.1329
octaves**, against the **0.12 octaves of centring slack** that made design 432
the sole load-and-corner-robust survivor. The obvious reading is that this is
bad news: a systematic shift larger than the slack should eliminate the one
design the project has.

**The prediction says the opposite, and the mechanism is the interesting part.**

### The prediction

> *"The parasitic may help. It adds a floor to both ends of the load range, and
> the range's damage comes from its RATIO, not its width. If it adds ~10 fF,
> 13.64–78 fF becomes roughly 24–88 fF — 3.7× instead of 5.72×. It won't be a
> constant offset since it scales with RL geometry, but the direction is
> compression, and compression is what design 432 needed."*

The reasoning rests on what session 12b actually measured: the load range
costs **99.4 %** of the corner-robust population, and it does so because of a
**5.72× ratio**, not because of an absolute capacitance. `f_peak` moves as
`cl^-0.349` (measured, session 12b), so what a design has to survive is the
ratio between the ends. **A parasitic that is present at BOTH ends raises both,
and a floor raises the small end proportionally more.** 13.64 → 23.6 is 1.73×;
78.0 → 88.0 is 1.13×.

### What would falsify the reasoning

1. **The parasitic is not roughly constant across the range.** It scales with
   the `RL` geometry, and G67 measured `to_geometry` choosing geometries that
   vary by 15× in area across a 0.16 % resistance span — so "adds ~10 fF" may
   be "adds 1.4 to 24.3 fF depending on which resistor the quantiser picked",
   which is the spread session 17 actually measured. If the parasitic tracks
   the design rather than sitting under it, it is not a floor and the ratio
   does not compress.
2. **The ratio compresses but the yield does not improve.** Session 12b's
   mechanism was that **146 of 200 designs (73 %) LOSE their interior peak
   entirely** across the load range, rather than moving out of the window. A
   narrower ratio does not obviously rescue a design whose peak is
   extinguished, and if the 73 % is the binding effect then compression buys
   little.
3. **The shift moves `f_peak` out of the window before the ratio helps.** The
   parasitic lowers `f_p2` and pulls `f_peak` down at BOTH ends. Design 432
   sits at −0.525 octaves relative to Nyquist, inside the window; a systematic
   −0.13 octave shift on top of a compressed range could still put it outside.

### The number to check it against

`cl_lo` = 13.64 fF and `cl_hi` = 78.04 fF today, ratio **5.72×**. The
prediction is a ratio **materially below 5.72×** — nominally ~3.7× — and a
corner-and-load-robust count **at or above** session 12b's 1/1890.

### Outcome

*Not yet run.* Blocked behind `PASSIVES.md` §6 item 6 (the R/C corner-file
trim), per the session-17 re-run ordering in HANDOFF §8: re-running the screen
before the `cl` range is corrected would re-run it with the wrong range.

---

## 6. The baseline benchmark — which search method wins, per problem rung

**Written:** 2026-08-07, session 18, **before** `experiments/baselines.py` was
run against ngspice for the first time. The 7e pre-screen numbers below were
measured first, on already-paid-for data (`robust_geometry_data.csv`, session
11), and they are declared as seen data rather than predicted.

**Experiment:** `python -m nebula.experiments.baselines --sweep` —
150 simulations per run, five methods (uniform random, Latin hypercube,
CMA-ES, GP-BO, untuned PPO), with and without the analytic pre-screen, on
P1 (TT, `cl_mid`) and P3 (3 screen corners × {`cl_lo`, `cl_hi`}). Scored by
`reward_v1` on all seven spec rows, worst case over the problem's evaluation
points. Seeds by the rule in `baselines.run_seed`.

### The owner's stated expectation

> *"CMA-ES and BO ahead of pre-screened random, ahead of random, ahead of
> untuned PPO at this budget."*

### Pilot data I have seen, declared

* The **pre-screen's own numbers**, measured before this was written: f_peak
  MdAPE **4.93 %** globally and **4.80 %** in 0.5–5 GHz; the screen rejects
  **61.7 %** of the box for free at a **0.39 %** false-rejection rate, taking
  the S3 rate among accepted designs from **13.44 % to 34.94 %** — a **2.60×**
  lift that does **not** clear 7e's 50 % threshold.
* **Session 17's** measured invalid rate (26.5 % on a policy trajectory, of
  which 78 % was the G44 fictitious peak) and its reward calibration
  (design 432 **+8.951**, flat **−1.155**, op-fail **−8.000**).
* Nothing from `baselines.py` itself. It has never touched ngspice.

### Predictions

**P1 — ordering, best final reward at 150 simulations.**

> **CMA-ES ≈ GP-BO > pre-screened uniform ≈ pre-screened LHS > LHS ≈ uniform
> > PPO**, with *CMA-ES and GP-BO not separable from each other* at 10 seeds.

**P1 — the numbers each of those rests on.**

| quantity | prediction | band I would accept as consistent |
|---|---|---|
| uniform, fraction of seeds finding a feasible design | **≥ 0.95** | 0.85–1.00 |
| uniform, median simulations to first feasible | **≈ 5** | 2–12 |
| pre-screened uniform, median simulations to first feasible | **≈ 2** | 1–5 |
| CMA-ES / GP-BO, median simulations to first feasible | **5–20** | 1–40 |
| PPO, fraction of seeds finding a feasible design | **≤ 0.5** | 0.0–0.8 |
| every method's median best-reward at 150 sims | **feasible band, ≥ +8** | — |
| pre-screen's measured free-rejection rate inside the sweep | **55–70 %** | 45–80 % |

**P2 is not run** and no prediction is offered for it.

**P3 — I predict it is EMPTY, and that this is the informative outcome.**

> **No method finds a feasible design in 150 simulations on any seed**, so the
> censored table reads 0/20 and 0/10 everywhere and the *only* defined
> comparison is the anytime curve. On that curve I predict the same ordering as
> P1 but with **no pair separable**, because 150 simulations buys only 25
> designs at 6 simulations each and the reward differences between methods will
> be inside the seed-to-seed spread.

**Cross-cutting.**

> The **pre-screen helps every method it wraps**, and it helps *uniform random
> most and CMA-ES least* — because CMA-ES's covariance adaptation already
> learns the same region the screen encodes, so the screen is partly redundant
> with it, while uniform random has no memory at all.

> **Wall clock will not rank the same as simulations.** GP-BO's model fitting
> is O(n³) and it will end the run fitting a GP to ~150 observations every
> proposal; I predict GP-BO's median wall clock is **≥ 1.15×** its own
> simulation-implied time while every other method is within 1.05×.

### The reasoning

1. **P1 is easy and the sanity rung says so.** The base rate is 13.44 %, so
   uniform random's simulations-to-first-feasible is geometric with p ≈ 0.134
   and a median of `ln 2 / 0.134` ≈ **5**. Any method that needs materially
   more than that on P1 is broken, not weak, which is what makes P1 a gate.
2. **The pre-screen is a 2.60× yield multiplier, measured.** 0.134 → 0.349
   gives a median of `ln 2 / 0.349` ≈ **2**. That is the whole prediction for
   the screened arms; it needs no assumption about search at all.
3. **CMA-ES and BO win on the ANYTIME curve, not on time-to-first.** Both need
   an initialisation phase — GP-BO burns 2d+2 = 16 designs on its initial
   design before it models anything, and CMA-ES's first generation is a draw
   from an isotropic Gaussian — so on time-to-FIRST-feasible neither should
   beat uniform random on a 13 % problem. Where they should win is the *best*
   reward at 150, because reward v1's feasible branch keeps rewarding margin
   after feasibility and only a method that models the objective climbs it.
4. **PPO loses, and it is expected to.** 150 simulations is ~19 episodes at
   horizon 8, against the 142 episodes session 17 ran and drew no conclusion
   from. A policy gradient with 19 episodes of experience on a 7-dimensional
   continuous problem is an untrained network; its proposals are close to its
   random initialisation and it pays the horizon's early-termination cost
   (an invalid evaluation ends the episode) that no other method pays.
5. **P3 is empty because 12b measured it empty and G66 made it worse.** One
   design in 1890 with ideal passives; drawn passives shift `f_peak` by 0.1329
   octaves against 0.12 octaves of slack, always in the same direction. At
   150 simulations a method evaluates 25 designs — I would not expect to find
   a 1-in-1890 design in 25 draws even if it still exists.

### What would falsify the reasoning (as opposed to the number)

1. **PPO beats uniform random on P1.** That would mean either the policy is
   learning something in 19 episodes — which would contradict session 17's
   refusal to draw a conclusion from 142 — or that PPO's *episodic structure*
   (edit an existing design rather than draw a fresh one) is worth more than
   its untrained policy costs. The second would be a genuinely interesting
   result and would say the comparison should be against a local-search
   baseline, not against random search.
2. **The pre-screen does not help, or hurts.** The screen is calibrated at
   TT with `nf_in` varying and `cl` = 150 fF; the benchmark runs `nf_in` = 4
   at `cl_mid` = 32.63 fF with drawn passives. If the free-rejection rate
   measured inside the sweep is far from 61.7 %, the calibration does not
   transfer and every screened number is about the calibration set rather than
   about the box.
3. **Uniform random's median time-to-feasible is far from 5.** That would mean
   reward v1's seven-row feasibility is materially harder than the S3 rate the
   prediction is built on — i.e. that noise, power or a saturation margin binds
   more often than "90.7 % free" implies. That is a fact about the box worth
   more than the ordering.
4. **P3 turns out non-empty.** Then session 12b's 1/1890 understates the
   tunable-free robust population and the load screen needs re-reading, which
   is HANDOFF §8's decided re-run anyway.
5. **CMA-ES and GP-BO separate from each other at 10 seeds.** I predict they
   do not. If they do, the effect is larger than I think and the sample size
   argument in 7h is too conservative.

### Guard against over-claiming, in both directions

If PPO loses, that is **the expected result and must be reported as such**. It
is evidence that untuned PPO at this budget on a 7-dimensional problem loses to
a tuned classical optimiser — which is unsurprising — and it is **not** evidence
about the amortised, spec-conditioned claim, because that claim is not being
tested here: every run in this sweep optimises ONE fixed spec target from
scratch, which is the setting classical optimisers are built for and the
setting a learned policy has no opportunity to amortise over.

Equally, if PPO were to win it would **not** establish the amortised claim
either. It would establish that on one spec target, at 150 simulations, one
untuned configuration beat four classical ones — which is a much smaller
statement than the one the project wants to make in September.

### Outcome

*Filled in after the sweep runs. Nothing above is edited.*

---

## 7. Task 0 — how many random samples reach the +8.950669 ceiling?

**Written:** 2026-08-18, session 22, **before** `exp_difficulty.py` was run at
full size. The 25-simulation cost probe and a 2x8 + 2x10 plumbing smoke test
had been run (they are quoted below as inputs); nothing at experiment size had.
**Experiment:** `python -m nebula.experiments.exp_difficulty --run`
— 24 independent LHS restarts per arm at a 600-simulation budget, plus one
2000-simulation unbiased pool per arm, on **P1** (TT / 1.00 / 27 C / `cl_mid`),
drawn passives, real mirror, reward v1 / `V1_SPECS`, the existing box, the
existing sampler, the existing evaluator. Two arms: **unscreened** and
**`experiments/prescreen.py` in front**.

### The thesis being tested (the owner's, stated in the brief)

> Random search reaches the reward ceiling in single-digit samples and seconds
> of wall clock, so the G3 sweep is arithmetically incapable of separating its
> arms and the likely outcome is "all arms tie at the ceiling".

### The pre-registered decision rule, encoded in `decide()`

| measured median simulations-to-ceiling | verdict |
|---|---|
| **< 50** in either arm | thesis holds — proceed to task 1 |
| **> 500** in every arm | thesis fails — launch the sweep as `PLAN.md` §3 specifies |
| in between | report and **stop**; the human decides |

### My prediction: **`thesis_holds`, but NOT for the stated reason — and the unscreened arm alone would not deliver it.**

Point estimates and consistent-with-my-reasoning bands, in **simulations**:

| | median sims-to-ceiling | band | median sims-to-first-S3 | band |
|---|---|---|---|---|
| unscreened | **90** | 30–400 | **5** | 3–12 |
| screened | **35** | 12–160 | **2** | 1–6 |

**Pooled rates:** S3 rate **13 %** (band 8–20 %, i.e. consistent with
`BASELINES.md`'s 13.44 %); ceiling rate **0.8 %** unscreened (band 0.2–3 %);
**at least 2 DISTINCT designs** tied at the ceiling in the 2000-simulation
unscreened pool, and I expect **every ceiling-tied design to score the same
number to six decimals**, because that is what G74 says the number is.

The reasoning, entirely from already-published numbers plus one new arithmetic
step:

1. **S3 alone is easy and the brief's arithmetic is right about that.**
   13.44 % gives `ln 2 / 0.1344` = **5** simulations to a first S3 pass, and the
   smoke test found one at simulation 7 and 8 on its two unscreened restarts.
   So "single-digit samples" is very likely correct **for S3**.
2. **The ceiling is not S3.** It requires `S3_f_peak` to bind *at the nearest
   lattice point*, which is one point of the **15** the octave window holds at
   `ac dec 50`'s 0.066439-octave spacing (session 11, G74). If `f_peak` among
   feasible designs were uniform over those 15, the ceiling rate would be
   `0.1344 / 15` = **0.9 %**, i.e. a median of `ln 2 / 0.009` = **77**.
3. **And it is not even that**, because the feasible branch is
   `B + min_i(margin_i/tol_i)`: for `S3_f_peak` to be the binding row at
   0.950669, **every other margin/tol must exceed 0.9507** — noise below
   1.025 mV_rms, power below 10.25 mW, peaking inside 3.95–11.05 dB, Nyquist
   boost above 0.95 dB, and both saturation margins above 95 mV. That is
   strictly harder than feasibility, so 0.9 % is an **upper** bound on the
   ceiling rate and 77 a **lower** bound on the median. Hence a point estimate
   of 90 rather than 77.
4. **The pre-screen's 2.60x lift carries to the ceiling roughly unchanged.**
   It filters on predicted `f_peak` and predicted peaking, which is the same
   axis the ceiling binds on, so `0.009 x 2.60` = 2.3 % gives `ln 2 / 0.023` =
   **30**. That is what puts an arm under 50 and produces the verdict.
5. **So the verdict and the reason come apart, and that matters more than the
   verdict.** I expect `thesis_holds` to fire off the **screened** arm at
   ~35 simulations, while the unscreened arm sits near 90 — an order of
   magnitude above "single-digit samples". If that is what happens, the brief's
   *conclusion* survives and its *arithmetic* does not, and the honest report
   says so: the sweep's arms would tie at the ceiling not in seconds but in a
   few tens of simulations, which is still far inside a 150-simulation per-run
   budget and still forbids a ranking.
6. **Wall clock is a footnote and is measured serially.** The probe measured
   **0.2537 s/sim** cold and the smoke test **0.168 s/sim** warm, against
   `G2_RESULTS.md`'s 0.28 s. G70 forbids reading anything into a wall-clock
   number gathered while something else simulates, so the run is serial and
   nothing else may run beside it.

### What would falsify the reasoning (as opposed to the number)

1. **The unscreened median lands in single digits.** Then the ceiling is not
   the 1-in-15 lattice event I think it is — most likely because `f_peak` among
   feasible designs is strongly concentrated near the window centre rather than
   spread across the 15 lattice points. That would be a fact about the box
   worth more than the verdict, and it would mean `BASELINES.md` §3's
   "simulations to ceiling" metric is far weaker than it was introduced to be.
2. **The pre-screen does not lift the ceiling rate**, or lifts it by much less
   than 2.60x. The screen's lift was measured on S3 membership, not on landing
   on one particular lattice point, and G76 has already caught this screen
   transferring its population rates while failing to transfer its accuracy.
   If the lift does not carry, the verdict rests on the unscreened arm alone.
3. **Every ceiling-tied design is the SAME design.** G74's evidence is four
   different `design_id`s at 8.950670. If a 2000-simulation pool finds ties
   that are all one design, the ceiling is narrower than G74 says and the
   "cannot separate arms" argument weakens.
4. **The pooled S3 rate is far from 13.44 %.** That number comes from
   `robust_geometry_data.csv`, a session-11 population, and this pool is drawn
   through `sizing_from_u` with drawn passives at `cl_mid`. A large gap means
   `PLAN.md`'s D4 baseline is quoting a rate the sweep will not reproduce, and
   D4 has to be re-decided before it can be the bar G3 must beat.
5. **The feasible rate is materially below the S3 rate.** The smoke test found
   them equal at n = 10, which is no evidence. If noise, power or a saturation
   margin binds often, then reward v1's seven-row feasibility is harder than
   the S3 rate everyone quotes — which is `PREDICTIONS.md` entry 6's own
   falsification condition 3, still untested at size.

### Guard against over-claiming, in both directions

A `thesis_holds` verdict does **not** say PPO cannot beat random search. It
says that **on this reward, at nominal, the primary metric saturates too early
for the comparison to be decidable** — which is a statement about the
measurement, not about the methods. Equally, a `thesis_fails` verdict would not
vindicate the sweep design; it would only remove one specific objection to it.

### Outcome — **six hits, two misses.** Run 2026-08-18, `nebula/DIFFICULTY.md`.

Verdict: **`IN_BETWEEN`** — the rule says report and stop.

| # | predicted | band | measured | |
|---|---|---|---|---|
| 1 | unscreened median sims-to-ceiling **90** | 30-400 | **221** | **HIT** |
| 2 | screened median sims-to-ceiling **35** | 12-160 | **68.5** | **HIT** |
| 3 | unscreened median sims-to-first-S3 **5** | 3-12 | **7.5** | **HIT** |
| 4 | screened median sims-to-first-S3 **2** | 1-6 | **3.0** | **HIT** |
| 5 | unscreened ceiling rate **0.8 %** | 0.2-3 % | **0.45 %** | **HIT** |
| 6 | >= 2 DISTINCT designs tied at the ceiling | -- | **9 of 9** | **HIT** |
| 7 | S3 rate **13 %** | 8-20 % | **7.10 %** | **MISS** |
| 8 | verdict **`thesis_holds`** | -- | **`IN_BETWEEN`** | **MISS** |

**Falsification condition 4 FIRED.** The pooled S3 rate is **7.10 %**, 95 %
Wilson **[6.05, 8.31] %**, and 13.44 % is outside that interval. `PLAN.md` D4's
recommended baseline does not reproduce under the sweep's own sampler,
evaluator and box. D4 goes back to a human.

**Falsification condition 5 fired in the OPPOSITE direction to the worry.**
Simulations-to-first-feasible equals simulations-to-first-S3 exactly (7.5 and
3.0) and the pooled feasible rate equals the pooled S3 rate to the digit in
both arms. The other four V1 rows never bind, so reward v1's seven-row
feasibility is **not** harder than the S3 rate everyone quotes. This also
settles entry 6's falsification condition 3.

**Conditions 1, 2 and 3 did NOT fire.** The unscreened median is 221, not
single digits; the screen lifts the ceiling rate (1.78x on simulations, 3.2x on
time-to-ceiling); and the ceiling ties are **25 designs with 25 distinct
`design_id`s** across the two pools, which reconfirms G74 at 2.8x its original
evidence.

**The miss I want on the record properly.** The prediction's mechanism --
"ceiling rate = S3 rate / 15, because the octave holds 15 lattice points" -- is
**right**: feeding the MEASURED 7.10 % through it gives 0.473 % against 0.450 %
measured, a 5 % agreement. Prediction 5 landed in its band with the WRONG input
(13 % rather than 7.10 %) and a compensating error. A hit obtained that way is
worth recording as a near-miss, because the next person to use the arithmetic
should use the measured base rate, not the published one.

**What the reasoning got right and is worth keeping:** it predicted that the
verdict and its reason would come apart, that the unscreened arm would sit an
order of magnitude above "single-digit samples", and that any `thesis_holds`
would have to fire off the screened arm. All three hold. The screened arm
simply landed at 68.5 rather than under 50, which is why the verdict is
`IN_BETWEEN` rather than `thesis_holds`.

**The consequence the brief did not anticipate.** At the sweep's own
150-simulation per-run budget, only **8 of 24** unscreened restarts reach the
ceiling (33 %), against 18 of 24 screened (75 %). So best-reward-at-budget does
**not** saturate for most unscreened runs, and the "all arms tie, nothing
separable" objection to the sweep is not what the arithmetic supports.

*Nothing above the Outcome heading was edited.*

---

## 8. Session 22b — where did the S3 rate go, and does the pre-screen throw away winners?

**Written:** 2026-08-18, session 22b, **before** either run. Two questions the
task-0 result forced, both decided by the owner in the session-22 review.

**Experiments:**
`python -m nebula.experiments.exp_attribution --run` (3 arms x 1500 simulations)
and `python -m nebula.experiments.exp_difficulty --more-pools 1` (2 arms x 2000).

### What is already known before the run, and is NOT a prediction

Two facts were established with **no simulation at all**, by re-scoring the
stored calibration population, and they are recorded here as inputs rather than
as predictions because they were measured before this entry was written:

1. **The definition accounts for none of the gap.** On
   `robust_geometry_data.csv`, `prescreen.s3_true` (2 rows) gives **13.44 %**
   and `reward_v1.V0_SPECS` (3 rows, adding `S3_nyq_boost`) gives **13.44 %**.
   Zero designs are killed by the Nyquist row. The 7-row `V1_SPECS` rate is
   **13.39 %** — which independently reproduces task 0's "the other specs never
   bind" on a different population, with ideal passives and an ideal tail.
2. **Every row of that population has `cl` = 150 fF**, the legacy pin — *not*
   `cl_mid` = 32.63 fF. `PLAN.md` D4 describes 13.44 % as "the measured rate at
   `cl_mid`", and `BASELINES.md` §2's ladder table puts it on the `cl_mid` row.
   **Both are wrong**, and the ratio is 4.598x.

### Prediction A: the load explains most of the gap

**Point estimate: the `cl` = 150 fF arm comes back at 12.5 %**, band
**10.5–15.5 %**, against **7.10 %** [6.05, 8.31] at `cl_mid`.

Reasoning, from published numbers only:

* `f_peak` moves as roughly `cl^-0.5` (`PREDICTIONS.md` entry 1 §2, measured
  slope −0.48 over `cl` = 50–500 fF). A 4.598x load change moves `f_peak` by
  **1.10 octaves** — more than S3's entire one-octave window.
* So the window selects a *different slice of the box* at each load, and there
  is no reason for the two slices to have equal S3 density. G42 already
  measured the direction: pinning `cl` at 150 fF gave **13.54 %** where
  searching `cl` over 10–500 fF gave 8.73 %.
* I expect the legacy arm to land near 13 % and therefore to account for
  roughly **5 of the 6.34 points**, leaving ~1 point for drawn passives.

### Prediction B: drawn passives cost about a point

**Point estimate: the ideal-passive arm at `cl_mid` comes back at 8.2 %**,
band **7.0–11.0 %**, i.e. drawn passives cost **~1.1 points** (band 0–4).

G66's mechanism is a `res_po` bottom plate adding **1.4–24.3 fF to a `cl` of
32.6 fF, up to +75 %**, always lowering `f_peak`. At `cl^-0.5` a +75 % load is
**0.40 octaves** — large against a 0.5-octave half-window — but the *median*
shift G66 measured is 0.1329 octaves, so the typical design moves ~13 % of the
window and only designs near the edge change verdict.

**If B comes back at or below 7.10 %**, drawn passives make the problem
*easier*, which would contradict G66's stated direction and would be the more
interesting result.

### Prediction C (G89): the screen does discard ceiling-capable designs

**Point estimate: the pooled rate ratio stays near 0.535 and its 95 % CI
excludes 1.0**, i.e. **CONFIRMED**, with implied false rejection on the
ceiling-capable population of **45 %**, band **25–65 %**.

Reasoning: the effect already has two independent supports. The direct one is
9/2000 against 16/6645 proposals. The indirect one is that "ceiling rate = S3
rate / 15" predicts the unscreened ceiling rate to **5 %** (0.473 % against
0.450 % measured) and misses the screened one by **2.1x** (1.703 % predicted,
0.800 % measured) — two different routes to the same ~2x. Doubling the events
should move the interval below 1.0 without moving the point estimate much.

**The mechanism I expect, and it is checkable:** the screen filters on
predicted `f_peak` with a 0.40-octave widening, and the ceiling is a
**0.0664-octave** target. A predictor with 4.93 % MdAPE at calibration and
**15.85 %** at benchmark conditions (G76) cannot resolve a lattice step, so it
rejects near-centre designs essentially at random with respect to the ceiling.
**A filter with a tolerance 6x coarser than the target it is being judged on is
a coin flip on that target.**

### What would falsify the reasoning (as opposed to the numbers)

1. **The legacy-load arm comes back near 7 %.** Then the load is not the cause,
   and the gap must be the sampler, the box, or the mirror — the last of which
   is currently unmeasurable (`TAIL_AXIS_BLOCKED`) and would have to be
   unblocked, which is a human decision about `validate`.
2. **The ideal-passive arm comes back far ABOVE 11 %.** Then drawn passives
   alone explain most of the gap, G66 is larger than its own measurement said,
   and every ideal-passive number in the repo is optimistic by more than the
   caveat admits.
3. **The two arms together over-explain the gap** (their effects sum to well
   over 6.34 points). The causes are not independent — both act on `f_peak`
   through the load — so a simple sum is not guaranteed to close, and if it
   over-closes the decomposition must be reported as non-additive rather than
   presented as a budget.
4. **C's ratio moves toward 1.0 with more events.** Then the first pools were
   an unlucky draw, G89 is killed, and the screened arms of the sweep are fine.
   That is the outcome that saves a 12-hour run from a caveat.
5. **C's ratio goes below ~0.2.** That would be a screen rejecting four fifths
   of ceiling-capable designs, which is too large to be predictor noise and
   would point at a systematic edge in the accept window rather than a
   resolution limit.

### Guard against over-claiming

Prediction A confirming does **not** make 13.44 % a valid baseline — it makes
it a baseline **at a load the next stage cannot present**, which is the exact
ground `PLAN.md` D4 uses to reject 13.54 %. The consequence of A is that D4's
recommended number and its rejected alternative were measured at the *same*
load, so the stated reason for preferring one over the other does not exist.

Prediction C confirming does **not** condemn the pre-screen: 61.7 % free
rejection at a 2.60x yield lift is a large, real saving on the S3 problem. It
would mean the screen is a **population filter and not a design filter**, and
that screened arms cannot be used to rank methods on a metric as narrow as the
ceiling. Those are different claims and the report must not blur them.

### Outcome — **A hit, B miss, C miss.** Run 2026-08-18, `nebula/ATTRIBUTION.md` and `nebula/DIFFICULTY.md` sec 4.3.

| | predicted | band | measured | |
|---|---|---|---|---|
| **A** legacy-load arm | 12.5 % | 10.5–15.5 % | **11.40 %** [9.89, 13.11] | **HIT** |
| **B** ideal-passive arm | 8.2 % | 7.0–11.0 % | **6.60 %** [5.45, 7.97] | **MISS**, below the band |
| **C** G89 rate ratio | 0.535, CI excludes 1 | 0.35–0.75 | **0.917**, CI [0.502, 1.677] | **MISS** |
| definition cost | 0 pts | — | **0.00 pts** | established pre-run |

**A: the load is the cause, and the mechanism is not the one the number
suggests.** Moving only `cl` from 32.63 to 150 fF takes the S3 rate 6.93 ->
11.40 %. But the S3 rate **among scorable designs** is **13.94 % against
13.91 %** — flat. What the load changes is the G44 population: **40.13 %
sweep-edge invalid at `cl_mid` against 8.67 % at 150 fF**. The published
baseline is not measuring a better box, it is measuring a box less of which is
wasted.

**B: drawn passives cost nothing measurable, and the pre-registration named
this case.** 6.93 % drawn against 6.60 % ideal, CIs overlapping across almost
their whole width. The entry said in advance: *"If B comes back at or below
7.10 %, drawn passives make the problem easier, which would contradict G66's
stated direction and would be the more interesting result."* It came back at
6.60 %. **The reasoning error was using a population rate to test a per-design
effect**: G66's 0.1329-octave shift moves designs both into and out of the
window, so the rate can be flat while individual verdicts flip. G66 is
untouched; my instrument was wrong.

**C: FALSIFICATION CONDITION 4 FIRED, exactly as written** — *"C's ratio moves
toward 1.0 with more events. Then the first pools were an unlucky draw, G89 is
killed, and the screened arms of the sweep are fine. That is the outcome that
saves a 12-hour run from a caveat."* Doubling the events took the ratio from
0.535 to **0.917**, implied false rejection **8.3 %** with CI [-67.7, 49.8].
Both arms regressed from opposite directions (9 -> 5 and 16 -> 27).

**And the reasoning behind C was worse than the number.** I wrote that the
effect *"has two independent supports"* — the direct rate ratio, and the
lattice arithmetic `ceiling = S3/15` missing the screened arm by 2.1x. **Those
are not independent: both are computed from the same 9 and 16 counts.** On the
pooled data the arithmetic over-predicts by 1.36x unscreened and 1.56x
screened, i.e. uniformly, with no arm-specific effect. *Different arithmetic on
the same small sample is not a second measurement*, and calling it one is how a
noise artifact acquired a mechanism and a paragraph.

**Falsification condition 3 also fired.** The causes do not sum:
0.00 + 4.47 + 0.33 = 4.80 points against a 6.51-point gap. The decomposition is
reported as **non-additive**, with the 2.04-point residual named (mirror axis —
blocked by G90; the G64 validity-definition difference; the sampler and box)
rather than apportioned.

*Nothing above the Outcome heading was edited.*



---

## 9. Session 22c, task 1 — does interpolating the peak remove the reward ceiling, or move it?

**Written:** 2026-08-19, session 22c, **before** the three runs below and before
any of their numbers existed. Task 1 of the session-22c brief, authorised by the
owner in the session-22b review with the justification restated: the case is no
longer separability of the unscreened arms (settled, and the owner's own reading
of it was wrong), it is **75 % of screened restarts saturating inside budget**
and **57 designs tied at exactly one reward value across 8000 simulations**.

**Experiments:**
```
python -m nebula.experiments.exp_peak_interp --funnel    # 300 sims, replays g2_closed_loop_run.jsonl
python -m nebula.experiments.exp_peak_interp --dense 30  # 60 sims, dec 50 vs dec 500
python -m nebula.experiments.exp_peak_interp --pools     # 8000 sims, replays the four task-0 pools
```

### What I have already seen, and am therefore not predicting

Declared because these numbers are **inputs** to the predictions below rather
than tests of them, and pretending otherwise is exactly the move entry 8's
outcome section criticises.

1. A **6-design smoke test** of the funnel replay was run to prove it reproduces
   the published `f_pk_hz`. All 6 reproduced at rel=0. Four had an interior
   peak, with shifts **+0.0184, +0.0215, −0.0087, −0.0054 octaves**; one was
   refused at the bottom edge and one at the top.
2. A **1-design smoke test** of the dense comparison: lattice error
   **0.01857 octaves**, interpolated error **0.000195 octaves**.
3. The vertex arithmetic is exact on a synthetic parabola to 1e-12, and the
   lattice ceiling is arithmetically escapable — `test_THE_LATTICE_CEILING_IS_
   NOT_A_CEILING_ON_THE_INTERPOLATED_PATH` scores a perfectly centred synthetic
   design at exactly 9.0. Both are algebra, not measurement.

### The arithmetic the predictions are built from

All published, none re-derived here:

* the AC grid is `dec 50`, step **h = 0.0664386 octaves**, half-step
  **0.0332193** — the hard bound on any vertex offset;
* the mid-window target is `sqrt(1.25 × 2.5) GHz` = **1.767767 GHz**;
* the nearest lattice point is **1.737801 GHz**, i.e. **0.0246654 octaves
  BELOW** the target;
* hence G74's ceiling `8 + (0.5 − 0.0246654)/0.5` = **8.950669**;
* task 0's pools: **14 ties unscreened + 43 screened = 57**, on 57 distinct
  designs, over 8000 simulations, with nothing above.

### Prediction A: the lattice error is spread across the whole cell

If a design's true peak is locally uniform in frequency, its offset from the
reported lattice point is uniform on ±h/2, so:

| quantity | point | band |
|---|---|---|
| median \|Δf_peak\| on the funnel | **0.0166 oct** (= h/4) | 0.012–0.021 |
| fraction with \|Δ\| < 0.001 oct | **3.0 %** (= 2×0.001/h) | 0–8 % |
| designs with \|Δ\| > h/2 | **0** | exactly 0 — a hard bound |

### Prediction B: the vertex is right, not merely finer

Against the `dec 500` reference (step 0.00664 oct):

| quantity | point | band |
|---|---|---|
| median \|lattice error\| | **0.0166 oct** | 0.012–0.021 |
| median \|interpolated error\| | **0.0010 oct** | < 0.004 |
| error reduction | **16×** | ≥ 5× |
| designs where interpolation is WORSE than the lattice | **0** | ≤ 2 of 30 |

The point estimate for the interpolated error is not from the smoke test's
0.000195 — one design is not a distribution, and a real response is only
approximately quadratic near its peak. 0.0010 oct assumes the quadratic
approximation leaves about a sixth of a dense grid step.

### Prediction C: the 57 ties separate completely

| quantity | point | band |
|---|---|---|
| distinct interpolated rewards among the 57 | **57** | ≥ 55 |
| of the 57, how many score **above** 8.950669 | **28** | 18–38 |
| of the 57, how many are refused by the interpolation | **0** | ≤ 2 |
| designs at the new maximum | **1** | 1 |
| best interpolated reward over 8000 sims | **8.985** | 8.955–9.000 |

The "28 above" is not a guess: the lattice point sits 0.0247 octaves **below**
the target, so a tied design's interpolated peak lands closer to the target
exactly when its vertex offset is positive, and that is **half** the cell —
0.5 × 57 = 28.5. **This is the prediction I most want tested**, because it is
the one that fails if peaks cluster on the lattice for some reason nobody has
thought of, which would mean G74's model of the ceiling is incomplete.

The new supremum is **9.0** and is unattainable: it needs `f_peak` exactly on
target, and the reward is `min` over specs, so another spec binds first for any
real design.

### Prediction D: the discrete path does not move, at all

| quantity | point |
|---|---|
| pools reproducing published `n_s3`, `n_at_ceiling`, `n_simulated` | **4 of 4** |
| pools reproducing the published `ceiling_design_ids` set | **4 of 4** |
| funnel designs reproducing published `f_pk_hz` at rel=0 | **all** |
| valid designs the interpolated path refuses | **≤ 0.5 %** |

The last row is the one with a real mechanism behind it rather than a hope. The
two guards *can* disagree: `validate` accepts a monotonically falling response
(`f_pk` = 10 MHz is inside `F_PEAK_HZ_LIMITS`) and scores it as a large graded
S3 miss, deliberately, because rejecting it "would erase the reward gradient
over the entire low-peaking region of the box". The interpolation has no vertex
to offer there. Refusing on that basis would rebuild that hole one layer up, so
`evaluate` carries the lattice pair forward for a **bottom**-edge maximum — not
as a fallback, but because 10 MHz is both a grid point and the boundary, so
`meas ac MAX` reported the true maximum of the interval and nothing was
rounded. **Top**-edge maxima stay refused; those are G44 and the discrete path
already rejects them twice over (`peak_is_sweep_edge`, and
`F_PEAK_HZ_LIMITS[1]` = 18 GHz sitting below the last in-window sample at
19.95 GHz).

### What would falsify the reasoning (as opposed to the numbers)

1. **Any pool fails to reproduce.** Then `ac_peak_interp` is not additive, every
   number in this entry is measured on a different experiment from the one it
   claims to extend, and task 1 stops until that is understood. This is the one
   condition that invalidates the task rather than the prediction.
2. **Any \|Δ\| exceeds h/2.** The Python argmax and `meas ac MAX` would be
   naming different samples, and the runner's cross-check would have failed to
   catch it.
3. **Median \|Δ\| < 0.005 octaves.** The interpolation is returning
   near-lattice values, i.e. it is not doing anything, and the whole task is a
   no-op dressed as a fix.
4. **Fewer than 45 of the 57 separate.** Then the ceiling has **moved** rather
   than gone — most likely because a different spec now binds at a value shared
   across designs — and the honest headline is "moved", not "removed".
5. **"Above the old ceiling" lands outside 18–38.** The vertex offsets are not
   uniform over the cell. That is more interesting than the fix: it would mean
   the tied designs are selected by something other than rounding.
6. **The dense comparison shows no improvement, or the interpolation is worse.**
   Then the response is not locally quadratic at its peak on this circuit, the
   vertex is a smoother number rather than a truer one, and the correct move is
   to say so and stop — not to keep it because it separates the ties.

### Guard against over-claiming, in both directions

**Removing the ceiling does not make the problem hard.** Task 0 measured the S3
rate at **7.10 %** and **75 % of screened restarts saturating inside budget**; a
continuous objective over the same population is still that population. The
claim here is narrowly about the **shape of the objective at its optimum** — a
plateau becomes a gradient — and it says nothing about whether PPO can climb it.
Anyone reading "the ceiling is gone" as "G3 is now winnable" has read more than
this measures. Task 3 (corners in the loop) is where difficulty comes from.

**And a separable metric is not automatically the right metric.** If the ties
separate by 1e-4 of reward, they separate — but a benchmark that ranks methods
on differences that small is measuring the fourth decimal of a spice
measurement. The spread of the separated rewards is reported for exactly this
reason, and if it is negligible the honest statement is "the ties are broken but
the ranking they support is not meaningful", which is a different result from
either "removed" or "moved".

**Nothing here changes a published number.** `V1_SPECS`, the tolerances, the
box, the pre-screen and the seeds are untouched; the ceiling **8.950669** is
still the ceiling of the path every baseline lives on, and the interpolated path
is opt-in. Whether to move the benchmark onto it is a human decision (D-series),
not a consequence of this entry.

### Outcome — **every band hit, one point estimate badly off, and two findings nobody registered.** Run 2026-08-19, `nebula/PEAK_INTERP.md`.

| | predicted | band | measured | |
|---|---|---|---|---|
| **A** median \|Δf_peak\|, funnel | 0.0166 oct | 0.012–0.021 | **0.015858** | HIT |
| **A** fraction \|Δ\| < 0.001 oct | 3.0 % | 0–8 % | **2.5 %** | HIT |
| **A** designs beyond ±h/2 | 0 | exactly 0 | **0** of 160 | HIT |
| **B** median \|lattice error\| vs `dec 500` | 0.0166 oct | 0.012–0.021 | **0.017265** | HIT |
| **B** median \|interpolated error\| | 0.0010 oct | < 0.004 | **0.000100** | band hit, **point 10× off** |
| **B** error reduction | 16× | ≥ 5× | **172×** | band hit, **point 11× off** |
| **B** designs where interpolation is worse | 0 | ≤ 2 of 30 | **0** of 14 | HIT |
| **C** distinct rewards among the 57 | 57 | ≥ 55 | **57** | HIT |
| **C** of the 57, above 8.950669 | 28 | 18–38 | **29** | HIT |
| **C** of the 57, refused | 0 | ≤ 2 | **0** | HIT |
| **C** designs at the new maximum | 1 | 1 | **1** | HIT |
| **C** best interpolated reward / 8000 | 8.985 | 8.955–9.000 | **8.999160** | HIT |
| **D** pools reproducing counts | 4 of 4 | — | **4 of 4** | HIT |
| **D** pools reproducing ceiling ids | 4 of 4 | — | **4 of 4** | HIT |
| **D** funnel designs reproducing `f_pk_hz` at rel=0 | all | — | **276 of 276** | HIT |
| **D** valid designs the interpolation refuses | ≤ 0.5 % | — | **0.022 %** (1 of 4543) | HIT |

**The headline prediction was the mechanism, and it held to one design.** 28 of
the 57 were predicted above the old ceiling on the reasoning that the nearest
lattice point sits 0.0247 octaves *below* the target, so exactly half the grid
cell moves closer. Measured: **29 above, 28 below**, and — the direct check —
**29 of the 57 have a positive vertex offset.** The uniform-over-the-cell model
of the ties is right, which is a second, independent confirmation that G74's
account of the ceiling was complete rather than approximate.

**Sixteen hits is not a good sign on its own, and one of them was luck.**
Prediction B's point estimate for the interpolated error, 0.0010 octaves, was
**ten times too pessimistic** — the measured median is 0.000100 — and the
reduction factor was predicted at 16× against a measured **172×**. The band
(≥ 5×) was wide enough to absorb an order of magnitude, so it "hit" while the
reasoning behind it was wrong: I assumed the quadratic approximation would leave
about a sixth of a dense grid step of residual, and on this circuit it leaves
about a sixtieth. **A band that survives a 10× error in its own point estimate
was not a strong test**, and the honest reading is that B tested "is the vertex
better than the lattice" (it is, decisively) and did not test how much.

### What was NOT predicted, and should have been

1. **63 designs in 8000 change feasibility** — 39 gain, 24 lose, net +15 on
   1291. `S3_f_peak`'s margin crosses zero at S3's window edges, and moving
   `f_peak` by up to a third of a grid step moves designs across them. **This
   entry predicted a change of RESOLUTION and got a change of PROBLEM as well**,
   0.79 % of the population, in both directions. It is the same per-design
   versus population distinction entry 8's prediction B ran into with G66, and
   it should have been foreseen from that entry, one day earlier. `PEAK_INTERP.md`
   §5 records it as a change to the problem rather than folding it into the
   metric, and §7 makes adopting it a human decision.
2. **The one refusal is not the refusal that was predicted.** The entry named
   the sweep edge as the case that matters. The single refusal in 4543 valid
   designs is the **argmax cross-check** firing on a response flat to
   2 × 10⁻¹⁰ dB: `meas` works on the full-precision vector, `wrdata` writes 8
   significant figures, and the rounding was enough for the two argmaxes to pick
   samples one grid step apart. Without that check the interpolation would have
   refined the wrong cell and reported a shift of a full grid step — twice the
   hard bound — silently. Now **G93**.

### The over-claiming guard, honoured

The entry warned that "a separable metric is not automatically the right
metric". Measured: the 57 span **0.1135** reward units with a median adjacent
gap of **1.28 × 10⁻³**, which is **647×** the vertex uncertainty at a typical
curvature and **14×** the worst-case one. The ranking is measuring the circuit.
**But the closest pair is separated by 6.86 × 10⁻⁵, inside the worst-case
bound**, so those two are not strictly ordered by this measurement — and the
pool log does not carry per-design curvature, so which pair it is cannot be
recovered from the run. Stated rather than rounded away.

The entry's other warning also stands unchanged: **removing the ceiling does not
make the problem hard.** The S3 rate is still 7.10 %, 75 % of screened restarts
still saturate inside budget, and nothing here says an arm of the G3 sweep would
separate from another. What changed is the shape of the objective at its
optimum.

*Nothing above the Outcome heading was edited.*


---

## 10. Session 22f — the G3 sweep, on the interpolated objective. **An ADDENDUM to entry 6, not a replacement.**

**Written:** 2026-08-19, session 22e/f, **before** the sweep was launched and
before any sweep row existed. Authorised by the owner ("okay lets do it") after
the task-1 result, which is the thing that makes this run worth its two hours.

**Experiment:** `python -m nebula.experiments.baselines --sweep --interp`
— 170 runs, **25 500 simulations**, 150 simulations per run, at
`ac_peak_interp=True` for every job including the warm-up and the timing
control.

### Entry 6 stands. This entry changes exactly one thing about it

Entry 6 pre-registered this sweep on the **lattice** objective, and its
predicted ordering was never testable on the metric it was stated in: the pilot
put **six of ten P1 groups at exactly +8.950669** (`BASELINES.md` §11), which is
G74's grid ceiling, not a result. Task 1 removed that ceiling
(`PEAK_INTERP.md`). **Entry 6's ordering prediction is therefore carried
forward unchanged and is being tested for the first time**; nothing in it is
edited, and this entry adds only what the change of objective makes newly
predictable.

**One thing the reader should hold onto:** this is not a re-run. The sweep has
**never been run** — `baselines_run.jsonl` contains a header and nothing else.

### What is already known before the run, and is NOT a prediction

Measured on 2026-08-19 while costing the run — nine single-replicate
calibration jobs at a 40-simulation budget, which is a quarter of the sweep's
budget and one seed rather than ten or twenty. Recorded as inputs:

* the aggregate rate is **0.2672 s/sim**, so the sweep is **1.89 h serial**;
* **GP-BO (0.3700) and PPO (0.5603) are the two configs above the pack**, both
  of which compute between simulations;
* `P1/uniform` at a 40-simulation budget reached **8.990174**, i.e. **above the
  old ceiling**, on one seed. That is the interpolated objective doing what
  task 1 said it would, and it is not evidence about any ordering.

### Prediction A: best-reward-at-150 becomes a discriminating metric

This is the whole reason the sweep is now worth running.

| quantity | point | band |
|---|---|---|
| P1 groups whose median best-reward is **exactly** 8.950669 | **0** of 10 | 0 |
| distinct median best-reward values across the 10 P1 groups | **10** | ≥ 8 |
| at least one P1 pair separable by the CI-overlap rule | **yes** | — |
| P1 groups with median best-reward in the feasible band (≥ +8) | **10** of 10 | 9–10 |

### Prediction B: entry 6's ordering, now testable

> **CMA-ES ≈ GP-BO > pre-screened uniform ≈ pre-screened LHS > LHS ≈ uniform
> > PPO**, CMA-ES and GP-BO not separable from each other at 10 seeds.

Carried forward verbatim. **My own confidence in it is lower than entry 6's**,
and the reason is measured: on a saturating metric the ordering was untestable,
so nothing has ever been evidence for it. The one calibration data point points
the other way — `uniform` at 8.990174 beat `cmaes` at 8.79122 and `gp_bo` at
8.733982 at a 40-simulation budget — but that is one seed at a quarter budget
and I am explicitly **not** revising a pre-registered prediction on it.

Additional, and this one is mine rather than entry 6's:

| quantity | point | band |
|---|---|---|
| pre-screened arms beat their unscreened twin on median best-reward | **5 of 5** | ≥ 3 of 5 |
| PPO ranks last of the five on P1 unscreened | **yes** | — |
| P3: methods finding a feasible design in 150 sims | **0** of 30 runs | 0–2 |

### Prediction C: the interpolation costs nothing the sweep can see

| quantity | point | band |
|---|---|---|
| `n_interp_refused`, summed over all 170 runs | **≤ 30** of 25 500 | ≤ 130 (0.5 %) |
| runs where the interpolation refused more than 2 % of evaluations | **0** | 0 |
| `timing_void` (7g's warm-up-vs-control ratio outside [0.8, 1.25]) | **false** | — |

The refusal bound is the task-1 rate, 1 in 4543, scaled: 25 500 / 4543 ≈ **5.6
expected**. I am predicting ≤ 30 rather than ≤ 6 because task 1's rate was
measured at one load on P1-like draws and the sweep includes P3's corners.

### Prediction D: wall clock does not rank like simulations

Entry 6 predicted **GP-BO ≥ 1.15× its simulation-implied time, everything else
within 1.05×**. The calibration says GP-BO is 1.54× the `uniform` rate and PPO
is **2.33×**, so I predict entry 6's cross-cutting prediction is **HALF right**:
GP-BO exceeds 1.15× as stated, and **PPO also does**, which entry 6 did not
anticipate. Recorded as a miss against entry 6 in advance rather than discovered
afterwards.

### What would falsify the reasoning (as opposed to the numbers)

1. **Any P1 group's median lands exactly on 8.950669.** The ceiling would not
   have been removed for the population the sweep actually samples, and
   `PEAK_INTERP.md`'s headline would be over-stated.
2. **`timing_void` fires.** Then the wall-clock half of this entry is void and
   the sweep is repeated, not adjusted (7g). Simulation counts stand.
3. **The sweep does not finish, or the log is truncated.** The pilot already
   died before writing its summary and `analyse_log()` exists because of it;
   if recovery from a partial log fails, that is a harness failure and a
   result.
4. **`uniform` wins P1 outright.** Entry 6's ordering would be falsified, and
   the honest reading would be that a 7.10 %-base-rate problem at 150
   simulations does not reward search at all — which is an argument for task 3
   (corners) and against reporting P1 as a method comparison.
5. **Screened arms lose to unscreened ones.** The pre-screen's yield lift is
   measured; if it does not convert into better best-reward, the lift is buying
   proposals rather than designs and `GMID_MAP.md` §6's fairness point becomes
   the headline instead.

### Guard against over-claiming, in both directions

**A separable ordering on P1 is not evidence that RL works.** P1 is the sanity
rung; entry 6 says so and this entry does not upgrade it. If PPO loses here, it
is what entry 6 predicted and it is **not** evidence about the amortised,
spec-conditioned claim, which no run in this sweep tests.

**And separability is not significance.** `BASELINES.md` §8's CI-overlap rule
governs every ranking claim; "10 distinct medians" is a statement about the
metric's resolution, not about the methods. Prediction A deliberately separates
the two — the first row is about the ceiling, the "at least one separable pair"
row is about the methods.

**Nothing published moves either.** The lattice objective is still the default
everywhere; this sweep is the first run of a benchmark that had never been run,
on a flag that has to be asked for.

### Outcome — **the benchmark ranks. 20 of 45 P1 pairs separate, 0 groups tie at the ceiling, and the run took 42 minutes.** Run 2026-08-19 at `ad17cf4`, `nebula/BASELINES.md` §12.

`python -m nebula.experiments.baselines --sweep --interp`, 170 measured runs +
warm-up + control = **25 869 simulations, 42.1 min wall** at 8 workers. Timing
control **clean** (0.186 → 0.221 s/sim, ratio 0.844, inside [0.8, 1.25]), so the
wall-clock numbers are valid under 7g.

#### Prediction A — the metric discriminates. **Four for four.**

| quantity | point | band | measured | |
|---|---|---|---|---|
| P1 groups with median exactly 8.950669 | 0 of 10 | 0 | **0** | HIT |
| distinct median values, 10 P1 groups | 10 | ≥ 8 | **10** | HIT |
| at least one separable P1 pair | yes | — | **20 of 45 pairs** | HIT |
| P1 groups with median in the feasible band | 10 of 10 | 9–10 | **10** | HIT |

The pilot had **six of ten groups at exactly +8.950669**. The same benchmark on
the interpolated objective has **none**, and the top of the table
(`cmaes+screen` 8.99742) is separable from the bottom (`ppo` 8.91063) with room
to spare. **The third row is the one that mattered** — distinct medians are
nearly free with continuous values, whereas 20 disjoint confidence intervals out
of 45 pairs is a benchmark that can support a ranking.

#### Prediction B — entry 6's ordering, confirmed wherever the sample resolves it

Measured, unscreened only: **GP-BO 8.9955 > CMA-ES 8.9736 > uniform 8.9532 >
LHS 8.9419 > PPO 8.9106.**

Entry 6 said *"CMA-ES ≈ GP-BO > pre-screened uniform ≈ pre-screened LHS > LHS ≈
uniform > PPO, with CMA-ES and GP-BO not separable from each other"*. Every
clause it makes that this sample can test is right: CMA-ES and GP-BO are **not
separable** (CIs [8.9599, 8.9924] and [8.9886, 8.9988] overlap), LHS and uniform
are **not separable**, and **PPO is last and is separable from six of the other
nine groups**. The single deviation — pre-screened uniform (8.9860) landing
*above* unscreened CMA-ES (8.9736) rather than below it — is **not separable**
either, so it is not a falsification.

| my own additions | point | band | measured | |
|---|---|---|---|---|
| screened arms beat their unscreened twin | 5 of 5 | ≥ 3 | **4 of 5** | band hit, point MISS |
| PPO last of five, P1 unscreened | yes | — | **yes** | HIT |
| P3 runs finding a feasible design | 0 of 30 | 0–2 | **2 of 30** | band hit at its edge, point MISS |

**The screen helps four ways and hurts GP-BO** (+0.0328 uniform, +0.0242 LHS,
+0.0239 CMA-ES, +0.0182 PPO, **−0.0034 GP-BO**) — and the GP-BO figure is far
inside the CI overlap, so the honest statement is "no measurable effect on
GP-BO", which is entry 6's *"it helps uniform random most and CMA-ES least"*
reasoning extended to the other model-based method.

**Entry 6's "P3 is EMPTY" is FALSIFIED.** `P3/uniform` found a corner-and-load
robust design on **2 of 20 seeds** (median 77.5 simulations, conditional), one
of them scoring **8.034**. `P3/cmaes` found none in 10. Two designs is not a
yield estimate, but "no method finds one" is now known to be false, and that
matters for task 3: the robust problem is hard, not empty.

#### Prediction C — the interpolation costs nothing the sweep can see. **Three for three.**

| quantity | point | band | measured | |
|---|---|---|---|---|
| `n_interp_refused` over the whole sweep | ≤ 30 | ≤ 130 | **2** of 25 869 | HIT |
| runs refusing > 2 % of evaluations | 0 | 0 | **0** | HIT |
| `timing_void` | false | — | **false** | HIT |

0.0077 %, against the 5.6 expected from scaling task 1's rate — the refusal is
rarer on this population than on the funnel, not more common.

#### Prediction D — **my own revision was wrong and entry 6 was exactly right**

I predicted entry 6's cross-cutting wall-clock claim was "HALF right": GP-BO
above 1.15× as it said, **and PPO also above it**, which entry 6 did not
anticipate. Measured, against `P1/uniform` at 0.6131 s/sim:

    gp_bo 2.43x   gp_bo+screen 3.26x   ppo 1.01x   ppo+screen 1.03x
    cmaes 0.99x   lhs 1.00x            everything else within 1.03x

**Entry 6 was right on both halves and I was wrong on the half I added.**

**The mistake is reusable and is now G94.** My calibration measured PPO at
0.5603 s/sim — at a **40-simulation budget**, a quarter of the sweep's 150. PPO
carries a large *fixed* startup (torch import, network construction, the first
rollout) and dividing it by 40 attributes it to the marginal rate; dividing the
same constant by 150 makes it disappear. **A per-unit rate measured at a
fraction of the real budget over-attributes fixed startup to the margin, and the
error grows as the budget shrinks.** GP-BO went the other way for the mirror-image
reason — its cost is `O(n³)` in observations, so 40 observations badly
*under*-states what 150 cost, and the sweep measured 2.43× where the calibration
saw 1.54×. Neither method's rate is a constant; only the flat ones extrapolate.

`gp_bo+screen` at **3.26×** has a mechanism worth stating: a screened proposal
costs zero simulations but still costs a full acquisition optimisation, so
screening *raises* GP-BO's model time per simulation — **207.9 s of model time
against 127.1 s unscreened**. The pre-screen is not free for model-based
methods, and this is the first measurement of that.

#### What this does and does not license

**It licenses the ranking**, which the pilot could not: six of its ten groups
were pinned to the grid. It does **not** license any claim about RL. PPO losing
here is what entry 6 predicted and said in advance must be reported as such —
untuned PPO at 150 simulations on a fixed spec target loses to tuned classical
optimisers, and no run in this sweep tests the amortised, spec-conditioned claim
that would favour it. P1 remains the sanity rung.

*Nothing above the Outcome heading was edited.*

---

## 11. Session 22f — the LATTICE control. **What did removing the ceiling actually buy?**

**Written:** 2026-08-19, **before** the control run, and after entry 10's
outcome was written. The interpolated sweep is done; this is its A/B.

**Experiment:** `python -m nebula.experiments.baselines --sweep --tag lattice`
— the **identical** 170 runs at the **identical** seeds, with
`ac_peak_interp` OFF. 25 500 simulations, ~42 min. Every other input is
byte-identical, so the difference between the two logs is the objective and
nothing else.

**Why it is worth 42 minutes.** Everything claimed so far about the ceiling
rests on the *pilot* (60 simulations, 3 seeds, "not to rank methods") and on
task 1's re-scoring of the difficulty pools. Neither is the sweep. This run
makes "the ceiling stopped the benchmark from ranking" a **measured A/B on one
experiment** rather than an argument assembled from two others — which is the
single most persuasive table this project can put in front of a judge.

### Predictions

**The comb, computed exactly.** A feasible design's lattice reward is
`8 + (0.5 − |off + k·h|)/0.5` with `h` = 0.0664386 octaves and `off` = −0.0246654
(the nearest grid point sits *below* target), so the teeth are **not evenly
spaced in reward** — `|off + k·h|` alternates:

    k =  0   ->  8.950669      k = +1  ->  8.916454
    k = -1   ->  8.817792      k = +2  ->  8.783576

**Only two teeth lie inside the interpolated run's entire P1 range**
(8.910626 … 8.997423, a spread of **0.0868**): 8.950669 and 8.916454, which are
**0.0342 apart**. So the whole measured ordering — every method, screened and
unscreened — fits between two adjacent lattice values.

| quantity | point | band |
|---|---|---|
| P1 groups whose median is **exactly** 8.950669 | **7** of 10 | 4–10 |
| **distinct** median values, 10 P1 groups (interpolated: 10) | **2** | 2–4 |
| separable P1 pairs (interpolated: 20 of 45) | **8** of 45 | 0–24 |
| of those, pairs involving a **zero-width** CI | **≥ half** | — |
| median best-reward of `P1/cmaes+screen` | **8.950669** | — |
| groups unchanged to 3 decimals between the two runs | **0** | 0–2 |

**Why the separable-pair band is wide in BOTH directions, and why it is not the
headline.** If a group's seeds all land on the same tooth its bootstrap CI has
**zero width**, and a zero-width interval is trivially disjoint from any other —
so the lattice run can report *more* separable pairs than the interpolated one
while resolving *fewer* levels. The pilot already showed this ("one degenerate
zero-width interval"). **The comparison that means something is the number of
distinct resolvable levels: 2 on the lattice against 10 interpolated**, and the
separable-pair counts must be reported with the degenerate ones broken out or
they will say the opposite of the truth.

The "7 of 10" is read off the interpolated run's own ceiling-crossing table —
`cmaes`, `cmaes+screen`, `gp_bo`, `gp_bo+screen` reached 8.95067 on 10/10 seeds
and `uniform+screen` on 15/20, so those five have a majority of seeds at the top
tooth; `uniform` (10/20) and `lhs+screen` (12/20) are borderline; `lhs` (6/20),
`ppo` (1/10) and `ppo+screen` (3/10) are not.

### What would falsify the reasoning

1. **The lattice run separates as many pairs as the interpolated one.** Then the
   ceiling was never what limited the benchmark, `PEAK_INTERP.md`'s headline is
   over-stated, and the 42 minutes bought the most important correction of the
   week.
2. **A lattice median lands off the comb.** The comb is exact arithmetic; a
   median between teeth would mean either the seeds disagree enough that the
   median interpolates between two of them (legitimate for even seed counts —
   check before concluding) or G74's model is incomplete.
3. **The two runs give different `sims_to_first_feasible`.** Feasibility is
   `all margins ≥ 0` and the peak moves by up to a third of a grid step, so a
   few designs flip (task 1 measured 0.79 %) — but a *large* difference would
   mean the objective change is doing more than sharpening the top of the band.

### Guard against over-claiming

A larger separable-pair count on the interpolated objective is a statement about
**measurement resolution**, not about any method being better than it was. The
methods are identical; only the ruler changed. And if the lattice run happens to
separate a pair the interpolated one does not, that is noise at 10 seeds and
must not be reported as the lattice metric being better at anything.

### Outcome — **0 separable pairs on the lattice against 20 on the interpolated objective.** Run 2026-08-19, `nebula/BASELINES.md` §12.6.

`python -m nebula.experiments.baselines --sweep --tag lattice`, identical
allocation, identical seeds, flag off. **25 866 simulations, 47.8 min.** Timing
control clean (0.165 → 0.200 s/sim, ratio 0.822).

| quantity | point | band | measured | |
|---|---|---|---|---|
| P1 groups whose median is the ceiling | 7 of 10 | 4–10 | **8 of 10** | HIT |
| distinct median values (interpolated: 10) | 2 | 2–4 | **3** | HIT |
| separable P1 pairs (interpolated: 20 of 45) | 8 of 45 | 0–24 | **0 of 45** | band hit, **point wrong** |
| of those, pairs involving a zero-width CI | ≥ half | — | **vacuous — there are none** | — |
| median of `P1/cmaes+screen` | 8.950669 | — | **8.950670** | HIT |
| groups unchanged to 3 dp between runs | 0 | 0–2 | **0 of 10** | HIT |

**THE HEADLINE, AND IT IS THE CLEANEST NUMBER IN THIS PROJECT: the benchmark
resolved NOTHING on the lattice objective.** Zero of forty-five P1 pairs
separate. Eight of ten groups report a median of **8.950670** — the same six
digits — and **six of them have a bootstrap CI of literally zero width**,
because every one of their ten or twenty seeds returned the identical float.
The same 170 runs, at the same seeds, scored on the interpolated peak separate
**20 of 45**.

**I predicted the failure mode backwards, and the band caught it.** The entry
warned that zero-width CIs would *inflate* the separable count — "a zero-width
interval is trivially disjoint from any other" — and predicted 8 separable
pairs on that basis. It did not happen, for a reason that is obvious in
hindsight: the degenerate intervals did not land on *different* teeth, they all
collapsed onto **the same one**, so they are identical rather than disjoint.
The band (0–24) was wide because I knew the sign of the effect was uncertain,
and the honest reading is that the band did the work the point estimate could
not.

**Falsification condition 2 fired, and the pre-registered check disposes of
it.** `P1/ppo`'s median is **8.923336**, which is not a comb value. The entry
said in advance: *"legitimate for even seed counts — check before concluding"*.
It is: n = 10, so the median averages the 5th and 6th seeds, **8.950670 and
8.896002**. And 8.896002 is itself off-comb — because **the comb only exists
where `S3_f_peak` binds**, which the task-1 pools measured at **1075 of 1291
feasible designs (83 %)**; the other 17 % are set by a spec whose margin is
continuous. So the lattice reward is a comb over five sixths of the feasible
band, not all of it — **and it still resolved zero pairs**, which makes the
result stronger rather than weaker.

**Falsification condition 3 did not fire.** `sims_to_first_feasible` is
**identical in all ten P1 groups** — 9.5, 4.5, 4.5, 2.0, 12.5, 4.0, 5.0, 3.5,
6.0, 2.0, unchanged to the decimal — and both runs find a P3 design on the same
2 of 20 seeds. The objective change sharpens the **top** of the feasible band
and leaves the **boundary** where it was, which is exactly the separation of
concerns the change was supposed to have.

#### And the cost question is now settled the other way

**The lattice run — doing strictly less work — took 47.8 minutes against the
interpolated run's 42.1**, i.e. **1.135× longer** for 3 fewer simulations. The
interpolation is not merely cheap; on this machine the run-to-run noise is
larger than its cost **and has the opposite sign**. Every wall-clock claim about
the interpolation should now be quoted as "below the noise floor" and never as a
number. G71, demonstrated on a matched pair rather than argued.

#### What this licenses

**It converts "the ceiling stopped the benchmark ranking" from an argument
assembled out of the pilot and the difficulty pools into a measured A/B on one
experiment.** Same 170 runs, same seeds, same 25 500 simulations, one flag: 0
separable pairs against 20. That is the table to put in front of a judge.

It says nothing about any method being better than it was. The methods are
identical in the two runs; **only the ruler changed**.

*Nothing above the Outcome heading was edited.*


---

## 12. Session 22g — PPO gets ONE gradient update. Does giving it more help?

**Written:** 2026-08-19, **before** the run. Owner-authorised ("yes run it")
after the diagnostic below.

**Experiment:** `python -m nebula.experiments.exp_ppo_updates --run` —
`rollout_steps` ∈ {**64** (control), 32, 16, 8} × 10 replicates × 150
simulations = **6000 simulations**, ~15 min. One knob; `Objective`,
`_ObjectiveEnv`, `method_ppo`, the seed rule, the box, `V1_SPECS`, the
tolerances and `ac_peak_interp=True` are the sweep's.

### What is already known, and is NOT a prediction

**A retraction first.** This session twice told the owner PPO's stall was
**exploration collapse**. It was inferred from the flat anytime curve and it is
**measured false**:

    entropy per update   9.942 -> 9.952 -> 9.956    RISES
    final log_std        ~0.005 in all 7 dims       UNCHANGED from init (0.0)

Nothing collapses; `ent_coef` is 0.0 and there is nothing for it to fix. What
the same instrumented run measured instead, and these are inputs:

* **1.57 simulations per environment step** — `CtleSizingEnv.reset` simulates a
  fresh start point, and an invalid evaluation ends the episode at once: 38
  episodes in 150 steps, many of length 1. **~1/3 of the budget is resets.**
* so a 150-simulation budget buys **~96 environment steps**, and at
  `rollout_steps = 64` that is **ONE policy update**.

"PPO came last" means "PPO performed one gradient update".

### Prediction A: the control reproduces the sweep, or the run is void

| quantity | point |
|---|---|
| control (`rollout_steps=64`) median best-reward | **8.910626**, exactly the sweep's |
| control's 10 per-seed bests | identical to the sweep's PPO runs |

**This is the gate.** `run_one` uses `baselines.run_seed("P1","ppo",rep)`, the
sweep's own rule, so the control is the same run. If it does not reproduce,
nothing below transfers.

### Prediction B: more updates help, monotonically, and not by much

| arm | updates | point | band |
|---|---|---|---|
| 64 (control) | 1 | 8.9106 | — |
| 32 | 2 | **8.920** | 8.87–8.96 |
| 16 | 5 | **8.935** | 8.88–8.98 |
| 8 | 11 | **8.925** | 8.85–8.98 |

Monotone up to 16 and then **turning over at 8**, because 8-step rollouts give
gradients estimated from a single 8-step episode's worth of advantage — the
variance starts to cost more than the extra updates buy.

### Prediction C: it does not fix the ranking, and that is the point

| quantity | point | band |
|---|---|---|
| best arm separable from the control by 7h's CI rule | **no** | — |
| any arm beating unscreened uniform (8.95319) | **0 of 3** | 0–1 |
| any arm beating CMA-ES (8.97356) | **0 of 3** | 0 |

**At 10 seeds and a 0.05-level bootstrap CI, a ~0.02 shift is very unlikely to
separate.** I expect the *ordering* to move and the *statistics* not to, and I
am saying so in advance so that "PPO improved" is not reported off a point
estimate whose interval overlaps its own control.

The reason PPO is not expected to catch uniform random is structural: **150
simulations is a tiny sample budget for a policy-gradient method**, and no
value of `rollout_steps` changes that. It is also why the amortised,
spec-conditioned comparison — where the training cost is paid once and reused
across every new spec — is the one that could favour RL, and this run is not it.

### What would falsify the reasoning (as opposed to the numbers)

1. **The control does not reproduce.** The experiment is not the sweep's PPO.
   Stop; nothing transfers.
2. **No trend at all across the arms.** Then update COUNT is not the binding
   constraint, my diagnosis is wrong, and the two candidates I ranked below it
   — the ~1/3 of budget spent on resets, and the episode terminating at first
   feasibility — become the story instead. **That is the outcome I would learn
   most from.**
3. **An arm beats CMA-ES (8.97356).** Then "PPO is structurally sample-starved
   at 150 simulations" is wrong, PPO tuning is worth far more than I told the
   owner, and the recommendation to spend the next week on task 4 rather than
   on tuning should be revisited.
4. **`rollout_steps = 8` is the best arm by a clear margin.** My variance
   argument is wrong and the useful direction is *smaller still*, which is
   cheap to test and would be worth one more arm.

### Guard against over-claiming

**This tunes one hyperparameter, on one problem rung, at one budget, with one
seed protocol.** It is not "PPO tuning" in the sense `PLAN.md` §4 defers — it is
the single knob a measurement pointed at. A gain here does not license a claim
that PPO is competitive, and a null result does not license a claim that PPO
cannot be tuned.

**And the two bigger levers are deliberately NOT in this run**, because both
change the environment contract and are the owner's: (i) `reset` spending a
simulation per episode, (ii) `terminated = bool(rb.feasible)` ending the episode
at first feasibility, which trains the policy to *reach* the feasible band while
the benchmark scores how far *past* it the policy gets.

### Outcome — **the diagnosis was right, the fix works in the predicted direction, and it is far too small to matter.** Run 2026-08-19, 6000 simulations, 24.4 min.

#### Prediction A — the gate, passed at the strongest level available

The control does not merely reproduce the sweep's *median*: **all ten seeds are
bit-exact**, seed for seed (8.777005, 8.897793, 8.963242, 8.930217, 8.799842,
8.913282, 8.941015, 8.809983, 8.918471, 8.907969). The control arm **is** the
sweep's PPO block. Everything below transfers.

#### Prediction B — monotone, and I was wrong about where it turns over

| arm | updates | predicted | band | measured | |
|---|---|---|---|---|---|
| 64 (control) | 1 | 8.9106 | — | **8.91063** | gate |
| 32 | 2 | 8.920 | 8.87–8.96 | **8.91958** | **HIT** (point accurate to 4 dp) |
| 16 | 5 | 8.935 | 8.88–8.98 | **8.92048** | band hit, point high by 0.015 |
| 8 | 11 | 8.925 | 8.85–8.98 | **8.92120** | band hit, point high by 0.004 |

**"Monotone up to 16 and then turning over at 8" is MISS.** It is monotone all
the way: 8 is the *best* arm, not the turnover. My gradient-variance argument
did not bite at these rollout lengths.

**But the gains are saturating hard**, which is the more useful shape:

    updates   2 -> +0.0089    5 -> +0.0099    11 -> +0.0106

Five and a half times the updates buys 19 % more improvement. Falsification
condition 4 (*"`rollout_steps = 8` is the best arm by a clear margin"*) fired
only in its first half: 8 **is** the best arm, by **0.0007** over 16 — far
inside both intervals. So "smaller still" is suggested and **not established**,
and the extra arm that condition would have licensed is **not worth 1500
simulations** to chase a difference this size.

#### Prediction C — three for three, including the one that matters

| quantity | point | measured | |
|---|---|---|---|
| best arm separable from its control | **no** | **no** — all three overlap | HIT |
| arms beating unscreened uniform (8.95319) | 0 of 3 | **0** | HIT |
| arms beating CMA-ES (8.97356) | 0 of 3 | **0** | HIT |

**The whole effect is +0.0106 reward units and it does not separate.** In
context:

    gap PPO -> uniform random   0.0426     recovered  24.8 %
    gap PPO -> CMA-ES           0.0629     recovered  16.8 %

So fixing the update count recovers about a quarter of the gap to *random
search* — and the ranking is unchanged. **PPO is still last.**

This is exactly what the entry pre-registered, in the words it used: *"I expect
the ordering to move and the statistics not to, and I am saying so in advance so
that 'PPO improved' is not reported off a point estimate whose interval overlaps
its own control."* It did, they did not, and it is not.

#### What the null half of this tells us

Falsification condition 2 — *"no trend at all"* — **did not fire**: the trend is
real, monotone, and in the predicted direction. So the diagnosis (PPO gets one
gradient update) is confirmed as *a* cause. What the size of the effect
establishes is that it is **not the dominant one**.

**The two levers this run deliberately excluded are now the story**, and both
change the environment contract and are the owner's:

1. **~1/3 of the budget is episode resets** (1.57 simulations per environment
   step). Those resets are not wasted — they are logged as trials and count
   toward best-so-far — but they are *uniform random samples*, so a third of
   PPO's budget is spent being uniform random. Since uniform random scores
   **8.953** and PPO scores **8.911**, PPO is currently paying a third of its
   budget for the method it loses to.
2. **`terminated = bool(rb.feasible)`** ends the episode the moment a design is
   feasible. The policy is trained to *reach* the band; the benchmark scores how
   far *past* it the policy gets. That is a train/test mismatch, and unlike
   `rollout_steps` it is not a hyperparameter.

**Recommendation, unchanged by this run and now with a number behind it:** one
knob bought 25 % of the gap to random search. Two contract changes might buy
more. Neither is likely to make untuned PPO beat a tuned classical optimiser at
150 simulations from scratch, because that budget is structurally hostile to
policy-gradient methods — which is the argument for spending the remaining time
on the **amortised, spec-conditioned** comparison instead, where the training
cost is paid once and reused.

*Nothing above the Outcome heading was edited.*

---

## 13. Session 22g-b — did the PPO policy move at all?

**Written:** 2026-08-19, **before** the paired run. The owner asked whether the
learning stagnation was ever solved. It was not, and entry 12 says so — but
entry 12 logged only `best_reward`, so it cannot say whether the *policy*
changed. This closes that gap.

**Experiment:** `exp_ppo_updates --instrument` — `rollout_steps` ∈ {64, 8} × 10
seeds, `total_steps` capped at 90 (~135 simulations) so `train()` returns with
its stats instead of `BudgetExhausted` carrying them away. **Its `best_reward`
is therefore NOT comparable to entry 12's** and is labelled so in the log.

### Declared inputs — one seed already seen

`rollout_steps=8`, replicate 0: **12 updates**, entropy **9.9354 → 9.8996**
against an untrained 9.9326, final `log_std` ≈ ±0.03, and
**`mean_action_l2_move = 0.633`**. `init_reproduced` is True, so the
reconstruction of the initialisation is verified rather than assumed.

**That last number already complicates what I told the owner.** I said the
policy "never started". Its *spread* is unchanged, but its *mean* moved 0.633
in a tanh-bounded 7-dimensional action space whose maximum possible move is
2·√7 = 5.29. That is 12 % of the range, and it is not nothing.

### Predictions

| quantity | rollout=64 | rollout=8 | band |
|---|---|---|---|
| updates | 1–2 | 11–12 | — |
| entropy at last update − 9.9326 | **−0.01** | **−0.03** | ±0.15 both |
| `mean_action_l2_move` | **0.15** | **0.60** | 0.0–0.5 / 0.3–1.2 |
| curve gain over the last third | **+0.005** | **+0.010** | 0–0.05 both |

**The prediction that matters: the mean moves roughly in proportion to the
update count, while the spread stays at its initialisation.** If that holds,
"the policy never started" is the wrong description and must be withdrawn — the
right one is **the policy moves and does not improve**, i.e. the gradient signal
is uninformative rather than absent. Those are different diagnoses with
different fixes, and I would rather find out than keep the tidier sentence.

### What would falsify the reasoning

1. **`mean_action_l2_move` ≈ 0 at BOTH arms.** Then the smoke-test seed was
   anomalous, "never started" stands, and the fix is more updates or a larger
   learning rate.
2. **The two arms move the same amount.** Then the movement is not driven by
   the updates at all — it would be initialisation noise in my probe, and the
   measurement is worthless as written.
3. **Entropy falls below ~9.2 (σ < 0.9) at rollout=8.** Exploration *is*
   contracting after all, and the collapse story I retracted was early rather
   than wrong.

### Guard against over-claiming

A moving mean is **not** evidence that PPO is learning something useful — entry
12 measured the payoff at +0.0106, not separable. It would only establish
*where* the failure is: in the usefulness of the gradient, not in its absence.
Neither result changes the recommendation to spend the remaining time on the
amortised comparison.

### Outcome — **the spread never moves, the mean does, and the design stops improving either way.** Run 2026-08-19, 2670 simulations, 10.8 min.

| quantity | rollout=64 | rollout=8 | untrained |
|---|---|---|---|
| updates (median) | **2** | **12** | — |
| entropy at last update | 9.9129 | 9.9300 | **9.9326** |
| entropy − untrained | **−0.0197** | **−0.0026** | 0 |
| mean \|log_std\| | 0.0054 | 0.0080 | 0 |
| **mean action L2 move** | **0.167** | **0.389** | — |
| **curve gain over the last third (median)** | **0.0** | **0.0** | — |
| n | 10 | 9 (see below) | — |

#### Scoring

| prediction | point | band | measured | |
|---|---|---|---|---|
| updates, 64 / 8 | 1–2 / 11–12 | — | **2 / 12** | HIT |
| entropy − 9.9326, 64 | −0.01 | ±0.15 | **−0.0197** | HIT |
| entropy − 9.9326, 8 | −0.03 | ±0.15 | **−0.0026** | HIT |
| L2 move, 64 | 0.15 | 0.0–0.5 | **0.167** | HIT |
| L2 move, 8 | 0.60 | 0.3–1.2 | **0.389** | in band, **not cleanly scoreable** — see below |
| curve gain, 64 / 8 | +0.005 / +0.010 | 0–0.05 | **0.0 / 0.0** | in band at its floor, points too high |

**The L2 row is not a clean score and saying so matters more than claiming the
hit.** The prediction was anchored on the declared input 0.633, which came from
a **single** probe observation. The probe was then rebuilt — it had called
`env.reset()`, which *simulates*, and killed the first attempt at job 11 of 20 —
and the replacement averages over **32** fixed vectors, which reads 0.209 for
that same seed. **The number was predicted against one instrument and measured
with another.** The band survives; the point estimate was never comparable, and
it is recorded as not-scoreable rather than as a hit.

#### The prediction that mattered, and it held

> *"the mean moves roughly in proportion to the update count, while the spread
> stays at its initialisation"*

**Both halves hold.** Entropy sits within 0.02 of an untrained 7-dimensional
Gaussian in both arms and `log_std` within 0.008 of its initialisation — the
policy never narrows. And the mean moves **0.167 → 0.389**, i.e. **2.33× the
movement for 6× the updates**: monotone, clearly non-zero, sub-linear. None of
the three falsification conditions fired.

**So "the policy never started" is RETRACTED.** It moves. The accurate
statement, and the third diagnosis this project has given PPO's failure:

> **The policy moves and the design does not improve. The gradient is
> uninformative, not absent.**

This is the worse of the two readings. An absent gradient is fixed with more
updates or a larger step; an uninformative one means more updates move the
policy further along a direction that is not up — which is exactly entry 12's
measurement, where eleven updates instead of one bought **+0.0106, not
separable**.

#### The honest reading of the flat curve

**The median gain over the final third is 0.0 in both arms, and that is a median
rather than a universal.** Per seed:

    rollout=64   7 of 10 seeds gain exactly 0.0; the other three gain 0.196, 0.028, 0.736
    rollout=8    6 of 9  seeds gain exactly 0.0; the other three gain 0.167, 0.203, 0.370

So it is not "the curve is flat". It is **"most runs make no progress at all in
their final third, and a minority make a single late jump"** — the signature of
a search that is still finding things by luck rather than by policy. **Twelve
updates does not change that distribution.**

#### One run lost, and why

`rollout_steps=8`, replicate 8, spent its full 150-simulation budget before
`train()` returned, so `BudgetExhausted` carried its stats away and the arm has
**n = 9**. The `total_steps = 90` cap is calibrated on a *median* 1.49
simulations per step; a seed with many short episodes pays more resets and
overruns. Reported rather than back-filled.

*Nothing above the Outcome heading was edited.*

---

## 14. Session 22h — **grid search, the baseline G3 names and this project never had**

**Written:** 2026-08-19, **before** the run, and committed before it starts.

`CLAUDEwa.md` §7 states G3 as *"RL beats random search **and** grid search at
TT, with a plot"*. `METHODS` held `uniform, lhs, cmaes, gp_bo, ppo` and no
grid, so **G3 has not been failing its grid clause — it has been unscoreable on
it.** `optimize_ctle()` in `python_models/statistical_eye.py` grids CTLE
*settings* inside the link model; it does not size devices and never sees this
box, so it is not the missing arm. `method_grid` is, and it is now built.

This entry pre-registers what the re-run will say. The run is
`baselines --sweep --interp --tag interp_grid`: **31 500 simulations, 210 runs,
~51 minutes** at the sweep's own measured 0.09773 s/sim.

### Declared inputs — arithmetic, not predictions

These are computed and would be dishonest to score as forecasts.

| | |
|---|---|
| box dimension | `N_ACTIONS` = **7** |
| budget | 150 simulations, and P1 costs exactly **1.000 simulations per design** (measured over 3 000 `uniform` designs in the existing log) |
| levels the budget buys | `150 ** (1/7)` = **2.06** |
| the grid that fits | **L = 2**, 128 points; L = 3 is 2 187, i.e. **14.6× the budget** |
| so an unscreened P1 grid run is | the **same 128 points every seed**, then **22** points from a shuffled L = 3 |
| P3 | 6 sims/design → 25 designs → `grid_levels` = **1**, one point. Not a search; no P3 grid arm |

### The prediction that matters most, and it is about the STATISTICS

**Grid search is deterministic and this benchmark's machinery is not built for
that.** Every unscreened seed evaluates the identical 128-point factorial; the
only thing a seed changes is which 22 of L = 3's points the leftover budget
reaches. So:

> **`P1/grid`'s 20 replicates are not 20 independent runs. They are one lattice
> plus 20 short random tails.** Its bootstrap CI will be near zero width, and
> that zero means something completely different from `BASELINES.md` §12.6's:
> there, the OBJECTIVE could not resolve; here, the METHOD has no randomness.
> Any "separable at n = 20" verdict involving `P1/grid` is arithmetically true
> and inferentially weak, and the write-up must say so rather than bank it.

| # | quantity | point | acceptance band |
|---|---|---|---|
| 1 | unscreened grid seeds returning the **identical** `best_reward` | **18 of 20** | ≥ 14 of 20 |
| 2 | width of `P1/grid`'s 95 % bootstrap CI | **0.000** | ≤ 0.005 |
| 3 | `P1/grid` median final reward | **8.93** | 8.60 – 8.99 |
| 4 | `P1/grid` **vs `P1/uniform`** (8.9532) | grid **loses**, by 0.02 | −0.15 … +0.02 |
| 5 | `P1/grid+screen` − `P1/grid` | **+0.04** | 0.00 … +0.15 |
| 6 | is #5 the **largest** screen delta of the six methods? | **yes** | (current largest: `uniform` +0.0328) |
| 7 | `P1/grid` **vs `P1/ppo`** (8.9106) | grid **wins**, by 0.02 | −0.06 … +0.10 |
| 8 | simulated points on the L ≥ 3 lattice, screened vs unscreened | **~104 vs 22** | screened ≥ 3× unscreened |
| 9 | the 10 pre-existing group medians, re-run at the same seeds | **all 10 identical** | all within 1e-6 |
| 10 | wall clock | **51 min** | 40 – 90 min |

### The reasoning behind #3, #4 and #5, so a miss is informative

**#4, grid loses to uniform.** The binding reward row on P1 is `S3_f_peak`,
whose margin is `0.5 − |log2(f_peak/f_target)|`: it is a *distance to a target*,
so it pays for **resolution**. A 2-level lattice gives each axis exactly two
values and therefore gives `f_peak` at most 128 attainable values, all fixed in
advance; uniform's 150 draws take 150 distinct values from a continuum. Grid
should lose, and the mechanism is the same one Bergstra and Bengio's 2012
result names — a factorial spends its budget on coordinates that do not matter
as heavily as on the ones that do. **The margin should be small**, because
best-of-128 and best-of-150 from comparable populations are close; the loss is
resolution at the top, not coverage.

**#5 and #6, the screen buys the grid something it buys nothing else.** For
every other method the pre-screen buys *throughput*: a rejected proposal costs
no simulation, so more proposals fit. For the grid it buys **step size**. At
~36 % acceptance the screened arm clears the 128-point coarse factorial for
~46 simulations and spends the remaining ~104 inside **L = 3**, whose lattice
the unscreened arm barely enters. This is the only mechanism in the benchmark
that can change a grid's resolution, and it is why #5's band is one-sided at
the bottom rather than centred.

**The risk in #5, named before the fact:** the screen's measured
false-rejection rate at benchmark conditions is **3.88 %** (`BASELINES.md` §5,
ten times its 1 % design budget). On a random method a false rejection costs a
draw. On a *fixed* lattice it can delete the single best point the grid was
ever going to see, permanently, for every seed. So #5 has a real failure mode
that is invisible for every other arm, and if it comes back negative that is
the first place to look.

### What would falsify the reasoning

1. **`P1/grid`'s CI is NOT near zero and the seeds disagree widely.** Then
   something is re-randomising the lattice and `method_grid` is not doing what
   its docstring claims — check `_factorial`'s centring and the `seen` set.
2. **Grid beats `uniform` by more than 0.02.** Then the resolution argument in
   #4 is wrong, and the more likely explanation is that the box's *structure*
   (not its fineness) is what the reward rewards — which would be a real result
   about the problem and would make the P2/P3 grid arms worth building.
3. **Grid beats every classical optimiser.** Then the benchmark's 150-simulation
   budget is too small for any method to be doing better than dense sampling,
   and the ranking in `BASELINES.md` §12 is measuring luck. This is the outcome
   that would most damage the existing write-up, and it is why it is listed.
4. **Any of the 10 pre-existing medians moves.** Then the benchmark is not
   deterministic under its own seed protocol, and every A/B in this project
   that assumed it is — including §12.6's matched lattice control — needs a
   re-reading.
5. **`grid+screen` scores BELOW `grid`.** Then #5's mechanism is dominated by
   the 3.88 % false-rejection rate deleting lattice points, which would be the
   sharpest measurement of the screen's bias this project has.

### Guard against over-claiming, in both directions

**A grid arm does not rescue G3.** G3 requires RL to beat random search *and*
grid search. PPO already loses to `uniform` by 0.0426 (`BASELINES.md` §12), and
nothing in this entry changes that; the most a favourable grid result can do is
make G3 fail on one clause instead of two. **Building this arm makes G3
scoreable, not passable**, and the entry is written that way on purpose.

**And a grid loss is not evidence for RL.** If `ppo` beats `grid` (#7), the
correct sentence is "PPO beats the weakest baseline in the study", not "RL
beats grid search" as a headline — because the same table has PPO last of the
methods that search adaptively. `CLAUDEwa.md` §7's own instruction applies:
*"If BO matches RL, say so. That is a finding, not a loss."*

**What this row IS worth, and it is worth something.** The competition's
problem statement is a sentence about grid search — *"should take significantly
lower time than sweeping all MOS, R, C, L parameter space"* — so this is the
one baseline a panel is guaranteed to ask about, and after this run the answer
is a measured number with a matched budget and a stated point pattern rather
than an appeal to the curse of dimensionality.

### Outcome — **grid search is LAST, its confidence interval is exactly zero wide, and it is the FASTEST method in the study to a feasible design.** Run 2026-08-19, 31 879 simulations, 210 runs.

`baselines --sweep --interp --tag interp_grid`. Artifacts:
`baselines_run_interp_grid.jsonl.gz`, `baselines_results_interp_grid.json`.

#### The ranking, all twelve arms

| group | median final | 95 % CI | width |
|---|---|---|---|
| P1/cmaes+screen | 8.9974 | [8.9890, 8.9985] | 0.0095 |
| P1/gp_bo | 8.9955 | [8.9886, 8.9988] | 0.0103 |
| P1/gp_bo+screen | 8.9921 | [8.9846, 8.9978] | 0.0132 |
| P1/uniform+screen | 8.9860 | [8.9591, 8.9895] | 0.0305 |
| P1/cmaes | 8.9736 | [8.9599, 8.9924] | 0.0325 |
| P1/lhs+screen | 8.9661 | [8.9460, 8.9845] | 0.0386 |
| P1/uniform | 8.9532 | [8.8745, 8.9732] | 0.0986 |
| P1/lhs | 8.9419 | [8.8920, 8.9588] | 0.0669 |
| P1/ppo+screen | 8.9288 | [8.8998, 8.9627] | 0.0629 |
| P1/ppo | 8.9106 | [8.8100, 8.9302] | 0.1202 |
| **P1/grid+screen** | **8.8886** | **[8.8886, 8.9185]** | 0.0298 |
| **P1/grid** | **8.8886** | **[8.8886, 8.8886]** | **0.0000** |

**34 of 66 P1 pairs separate.** `grid` is separably below eight of the other
ten arms, and **not** separably below `uniform` or `ppo`.

#### Scoring

| # | prediction | point | band | measured | |
|---|---|---|---|---|---|
| 1 | identical unscreened seeds | 18/20 | ≥ 14/20 | **19 of 20** at 8.888648 | HIT |
| 2 | width of `P1/grid`'s CI | 0.000 | ≤ 0.005 | **0.0000**, exactly | HIT |
| 3 | `P1/grid` median | 8.93 | 8.60–8.99 | **8.8886** | HIT |
| 4 | grid − uniform | −0.02 | −0.15…+0.02 | **−0.0646** | HIT |
| 5 | grid+screen − grid | +0.04 | 0.00…+0.15 | **+0.0000** | in band **at its floor**, point too high |
| 6 | is #5 the largest screen delta? | yes | — | **no — it is the smallest** | **MISS** |
| 7 | grid − ppo | +0.02, grid **wins** | −0.06…+0.10 | **−0.0220**, grid **loses** | band held, **claim wrong** — see below |
| 8 | simulated L ≥ 3 points, screened vs unscreened | ~104 vs 22 | ≥ 3× | **114 vs 22 per seed, 5.19×** | HIT |
| 9 | the pre-existing group medians reproduce | all identical | ≤ 1e-6 | **0.00e+00 on all TWELVE** | HIT |
| 10 | wall clock | 51 min | 40–90 min | 53.8 min, but **`timing_void = True`** | **VOID, not scoreable** |

#### #7 is the one that matters, and the band was too wide to test it

I predicted grid would beat PPO and gave the prediction a band spanning zero.
**A band that spans zero cannot test a directional claim**, so recording this as
a hit on the band would be scoring the wrong thing. The claim was wrong: **grid
loses to PPO by 0.0220**, and PPO is the method this project has spent three
sessions establishing does not learn.

The mechanism is not adaptivity — `uniform` and `lhs` are not adaptive either
and both beat the grid. It is **resolution**. The binding reward row on P1 is
`S3_f_peak`, whose margin is a *distance to a target*; a continuous sampler's
effective resolution is its sample count, while a factorial's is
`budget ** (1/d)` = **2.06 levels per axis** at d = 7. Even a policy that never
learns proposes from a continuum and therefore has 150 distinct values per axis
where the grid has two. **That is Bergstra and Bengio's 2012 result, measured
on transistor sizing rather than on hyperparameters.**

#### #5 and #6 missed for one reason: the coarse lattice's best point is a WALL

The predicted mechanism **fired exactly as described** — the screen bought the
grid resolution, 2 280 simulated points on the 3-level lattice against 439
(5.19×), from 7 131 enumerated candidates against 439:

| | L = 2 simulated | L ≥ 3 simulated | L ≥ 3 *visited* |
|---|---|---|---|
| `P1/grid` | 2 560 (128/seed) | 439 (22/seed) | 439 |
| `P1/grid+screen` | 720 (36/seed) | **2 280 (114/seed)** | **7 131** |

— and it bought **nothing at the median**. Eleven of twenty screened seeds
still finished on the *same* 8.888648 design the unscreened arm found, because
114 extra points on a **three**-level lattice are still nowhere near fine
enough to improve on the best of the coarse 128. What the screen did buy is a
**tail**: the screened arm has 6 distinct outcomes against 2, and its best seed
reaches 8.9488 against 8.9185.

So the honest sentence is **"the screen bought the grid resolution and the
resolution was not the binding problem"**, which is a stronger result than the
prediction would have been: it says the grid's failure is not fixable by
spending its budget better.

#### Two findings nobody registered

**Grid search is the FASTEST method in the study to a feasible design, and the
only one that never improves it.**

| | sims to first feasible (median) | reached the ceiling |
|---|---|---|
| `P1/grid+screen` | **1.0** — the fastest of all twelve arms | **0 of 20** |
| `P1/grid` | 4.5 | **0 of 20** |
| `P1/uniform+screen` | 2.0 | 15 of 20 |
| `P1/uniform` | 6.0 | 10 of 20 |
| `P1/ppo` | 5.0 | 1 of 10 |

Every other P1 arm reaches the +8.950669 ceiling on at least one seed. **The
grid reaches it on none, in 40 runs and 6 000 simulations.** A coarse factorial
plus an analytic pre-screen lands on a working circuit with the **first**
simulation and then cannot move.

**And the benchmark is bit-for-bit deterministic.** All twelve pre-existing
group medians reproduced at **0.00e+00** across two independently ordered
sweeps — which is the strongest statement about this harness anyone has made,
and it was free.

#### One falsification condition fired, and it was G96 rather than physics

Falsifier 4 was *"any of the 10 pre-existing medians moves"*. **No median
moved.** But the count of separable P1 pairs among those same ten arms came
back **22 of 45** against the published **20 of 45**, on data that had not
changed by a bit — because `analyse` shared ONE bootstrap generator across
`groups.items()`, whose order is the order the process pool finished. Adding an
arm re-ordered the stream. Fixed with a per-group seed
(`baselines.group_seed`), after which the ten arms give **20 of 45** exactly,
and the lattice control still gives **0 of 45**. Recorded as **G96**. The
published contrast in `BASELINES.md` §12.6 is unaffected, and it is now
reproducible rather than accidentally correct.

#### The G3 verdict, stated plainly

G3 requires RL to beat random search **and** grid search at TT.

* **RL vs random search: LOSES.** `ppo` 8.9106 against `uniform` 8.9532.
* **RL vs grid search: does not separably win.** `ppo` 8.9106 sits above
  `grid` 8.8886 on the point estimate, but `ppo`'s interval [8.8100, 8.9302]
  contains the grid's entire (degenerate) interval, so by 7h's own rule this is
  **not separable at this sample size**.

**G3 fails on both clauses, and it can now be SCORED on both, which it could
not be before this run.** Building the arm made the gate answerable; it did not
make it passable, exactly as the pre-registration said.

*Nothing above the Outcome heading was edited.*

---

## 15. Session 22i — **is PPO starved, or is the gradient pointing the wrong way?**

**Written 2026-08-19, before the run, and committed before it starts.**

Entries 12 and 13 left two live explanations for PPO's failure and no way to
choose between them:

* **(a) starved.** 150 simulations buys ~96 environment steps and, at
  `rollout_steps = 64`, **one** policy update. A method given one gradient step
  has not been tested.
* **(b) misdirected.** Entry 13 measured that the policy *does* move — the mean
  action travels 0.167 → 0.389 as updates go 2 → 12 — while the design does not
  improve. An *uninformative* gradient, where more updates buy more travel in a
  direction that is not up.

**Only the budget separates them**, so the budget is what this varies:
`exp_budget_ladder --run`, three arms at **2400 simulations**, 40 runs,
**96 000 simulations, ~2.6–3.0 h**.

### Declared inputs — established before this entry, not predicted

| | |
|---|---|
| the ladder | 150 → 300 → 600 → 1200 → 2400, **doublings** |
| why not 200/250/300/350 | PPO's seed spread at 150 is ~0.12 wide and entry 12 measured an **11× increase in updates moving the score by 0.0106**, six times smaller. A ladder spanning 2.3× cannot resolve that |
| policy updates bought | **1 → 2 → 5 → 11 → 23** (`rollout_steps` = 64, 1.57 sims/step) |
| one run, not five | nothing in PPO's config depends on the budget: `steps = 100_000`, `lr` constant, no schedule. Same seed ⇒ identical trajectory, so a 2400 run *contains* the shorter ones |
| **that claim is verified, not assumed** | a 1200-simulation smoke run at budget 30 reproduced the published sweep's first 30 simulations on **40 of 40 curves at worst \|diff\| = 0.0**. The real run re-checks at n = 150 |
| the control | `uniform` (20 seeds) — PPO against itself trends upward whether or not it learns, because more simulations is more lottery tickets |
| the reference | `cmaes` (10 seeds) — is *anything* still improving at 2400? |

### The primary metric, and why it is not the raw gap

**The reward saturates near +9.0.** As the budget grows every method compresses
toward that asymptote and the difference between any two shrinks — which looks
exactly like "PPO is catching up" and would be an artifact of the ceiling. So
the headline is stated in the control's own units:

> **Random-equivalent budget** — how many *uniform random* simulations buy the
> score this arm reached in `n`. Below 1 means the method is worth less than
> guessing.

Computed on the already-published 150-simulation sweep:

| arm | score at 150 | uniform needs | ratio |
|---|---|---|---|
| cmaes | 8.9736 | more than 150 | **> 1.00×** |
| lhs | 8.9419 | 144 | 0.960× |
| **ppo** | **8.9106** | **108** | **0.720×** |
| grid | 8.8886 | 81 | 0.540× |

**150 simulations of our RL are worth 108 simulations of random guessing.**
That sentence is saturation-proof, and it is the sentence the report should
use.

### Predictions

| # | quantity | point | acceptance band |
|---|---|---|---|
| 1 | **`ppo` random-equivalent ratio at 2400** | **0.75×** | 0.40 – 1.10 |
| 2 | **does that ratio cross 1.0 at any rung?** | **no** | — |
| 3 | the ratio's trend across 150 → 2400 | **flat**, \|slope\| < 0.15 over the whole 16× | −0.4 … +0.4 |
| 4 | `ppo` median reward at 2400 | 8.985 | 8.94 – 8.999 |
| 5 | `uniform` median reward at 2400 | 8.996 | 8.985 – 8.9995 |
| 6 | `cmaes` median reward at 2400 | 8.999 | 8.990 – 9.000 |
| 7 | **raw gap `ppo − uniform` at 2400** | **−0.011** | −0.06 … +0.005 |
| 8 | **the raw gap shrinks while the ratio does not improve** | **yes** — the saturation artifact, registered so it cannot be reported as progress | — |
| 9 | `cmaes` ratio at 2400 | **censored** (uniform never catches it) | — |
| 10 | `ppo` gain over the final third at 2400 | +0.005 | 0.00 – 0.05 |
| 11 | prefix check against the published sweep | **0 of 40 mismatched**, worst \|diff\| **0.0** | exact |

**The prediction that matters is #1 and #2.** If PPO is merely starved, 23
policy updates instead of 1 has to show up as the ratio climbing through 1.0.
If entry 13's reading is right — the gradient is uninformative — it will sit
below 1 no matter how long the run is.

### What would falsify the reasoning

1. **The ratio exceeds 1.2 at 2400.** Then PPO *was* starved, entry 13's
   "misdirected" reading is wrong, and the right response is more training
   budget rather than a different algorithm. **This is the outcome that would
   most change the project's plan**, which is why it is listed first.
2. **Uniform saturates so hard that every arm's ratio is censored.** Then the
   problem is simply *solved* by random search at 2400 and the finding is not
   "RL lost" but **"there was nothing left to win at this budget"** — and the
   response is to make the problem harder (corners, tighter specs), not the
   policy better.
3. **The prefix check finds any mismatch.** Then a long run does not contain
   the short ones, the whole one-run ladder is invalid, and every rung has to
   be run separately.
4. **The ratio FALLS sharply with budget.** Then more updates actively hurt —
   the policy walks away from good regions — which is the strongest form of
   "misdirected" and would make the learning rate the first thing to look at.
5. **`cmaes` drops below 1.0.** Nothing about the harness should change at long
   budgets; if the strongest classical method stops beating random search, the
   run is measuring something other than search quality.

### Guard against over-claiming, in both directions

**A ratio below 1 at 2400 does not show that RL cannot size this circuit.** It
bounds *this* formulation: one fixed spec target, from scratch, this 7-D box,
this reward, this policy. `PREDICTIONS.md` entry 6 already says the amortised
spec-conditioned claim is untouched by any from-scratch comparison, and that
remains true here — **it is the one regime where the policy gets enough
experience to learn, and nothing in this entry tests it.**

**And a ratio above 1 would not rescue G3 by itself.** G3 is scored at 150
simulations, which is the budget every published arm ran at. A win at 2400
would be a finding about the budget, reported as such, and would argue for
re-running the whole benchmark at the larger budget rather than for quietly
re-scoring the gate.

### Outcome — **neither. PPO's deficit to random search closes with budget; PPO never gets past random search; and CMA-ES beats both at every rung by a margin that does not close.** Run 2026-08-19, 40 runs, 96 000 simulations, five resumed chunks.

`exp_budget_ladder --run`. Artifacts `budget_ladder_run.jsonl`,
`budget_ladder_results.json`, `budget_ladder_summary.json`.

#### The ladder — median best-so-far

| arm | 150 | 300 | 600 | 1200 | 2400 |
|---|---|---|---|---|---|
| **cmaes** | 8.9736 | 8.9965 | 8.9993 | **8.9999** | **8.9999** |
| uniform | 8.9532 | 8.9635 | 8.9860 | 8.9901 | 8.9939 |
| **ppo** | 8.9106 | 8.9521 | 8.9844 | 8.9903 | 8.9941 |

| separability | 150 | 300 | 600 | 1200 | 2400 |
|---|---|---|---|---|---|
| ppo vs uniform | not | not | not | not | **not, at any rung** |
| cmaes vs uniform | not | **SEP** | **SEP** | **SEP** | **SEP** |
| cmaes vs ppo | **SEP** | **SEP** | **SEP** | **SEP** | **SEP** |

#### The answer, in one paragraph

**PPO was partly starved and that is not the interesting half.** Its
150-simulation deficit to random search — `−0.0426`, and 0.750× of random's
budget after calibration — closes monotonically and is gone by 600–1200. So
one gradient update *was* costing it something.

**But it converges TO random search, not past it.** At 1200 and 2400 the gap
is `+0.0001` and `+0.0002`, and PPO is **not separable from uniform random at
any rung of the ladder**. Sixteen times the budget and twenty-three policy
updates instead of one buys PPO exactly parity with guessing.

**And the thing that is left to win, PPO does not win.** CMA-ES reaches
**8.9999** by 1200 against a ceiling of 9.0000, while uniform and PPO both
plateau at **~8.994**. That 0.006 does not close: CMA-ES is separable from
uniform from 300 up and from PPO at **every single rung**. Falsifier 2 —
"uniform saturates, so there was nothing left to win" — **did not fire**:
random search stops 0.006 short of what a classical optimiser takes.

> **This is the fourth diagnosis of PPO's failure and the first that is not
> about PPO being broken. PPO is not broken. It is a random search with extra
> steps.**

#### Scoring

| # | prediction | point | band | measured | |
|---|---|---|---|---|---|
| 1 | `ppo` random-equivalent ratio at 2400 | 0.75× | 0.40–1.10 | **censored, > 1.00×** | **MISS** |
| 2 | does the ratio cross 1.0 at any rung? | **no** | — | **yes** — 1.024× at 1200 | **MISS** |
| 3 | the ratio's trend is flat | flat | −0.4…+0.4 | 0.720 → 0.480 → 0.578 → 1.024 → >1.00; **rises** | **MISS** on the claim, inside the band |
| 4 | `ppo` median at 2400 | 8.985 | 8.94–8.999 | **8.9941** | HIT |
| 5 | `uniform` median at 2400 | 8.996 | 8.985–8.9995 | **8.9939** | HIT |
| 6 | `cmaes` median at 2400 | 8.999 | 8.990–9.000 | **8.9999** | HIT |
| 7 | raw gap at 2400 | −0.011 | −0.06…+0.005 | **+0.0002** | band held, **point had the wrong sign** |
| 8 | the raw gap shrinks while the ratio does not improve | yes | — | **no — the ratio improved too** | **MISS** |
| 9 | `cmaes` ratio at 2400 censored | censored | — | **censored** | HIT |
| 10 | `ppo` gain over the final third at 2400 | +0.005 | 0.00–0.05 | **+0.0000** | in band **at its floor** |
| 11 | prefix check | 0 of 40, exact | exact | **0 of 40, worst \|diff\| 0.000e+00** | HIT |

**6 hits, 4 misses, 1 at a band floor.** The four misses are all the same
miss: I predicted PPO would not close the gap, and it closed it. What I got
right is that closing it would not make PPO *good* — #7's band held and the
medians converge at a value 0.006 below CMA-ES.

#### **The control invalidated my own metric, and that is the most useful thing here**

`random_equivalent_budget` was defined as *"the first simulation at which
uniform's median curve reaches this score"*. Run against **uniform itself** it
must read 1.000× — and it does not:

| | 150 | 300 | 600 | 1200 | 2400 |
|---|---|---|---|---|---|
| **uniform vs uniform** | 0.960× | 0.893× | 0.632× | 0.988× | **0.623×** |

The cause is real, not a coding error. **A median over twenty monotone step
functions is itself a step function with long plateaus**, so "first reached" is
the *start* of the plateau the target sits on. `uniform 2400 → 1494` is a true
sentence — the median uniform run had already reached its 2400-simulation score
after 1494 — but it is **not an equivalent budget**, and **1.0 is the wrong
line to compare anything against.**

The pre-registered quantity is reported unchanged and scored as registered
(#1, #2, #3 above). Beside it now sits the same quantity divided by the
control's own value, where the control reads exactly 1.000× by construction:

| calibrated | 150 | 300 | 600 | 1200 | 2400 |
|---|---|---|---|---|---|
| cmaes | **2.167×** | > 8.96× | > 6.33× | > 2.02× | > 1.61× |
| uniform | 1.000× | 1.000× | 1.000× | 1.000× | 1.000× |
| **ppo** | **0.750×** | 0.537× | 0.916× | **1.036×** | > 1.61× |

**And this metric saturates too, which must be said rather than exploited.** At
2400 both PPO and CMA-ES read `> 1.61×` — the same censoring bound — because
uniform never reaches either. That is not evidence they are equal: their
medians are 8.9941 and 8.9999 and they are **separable**. Above ~1200
simulations the ratio stops discriminating and the medians are the honest
read-out.

Recorded as **G98**: *a ratio metric must be run against its own reference, and
if reference-against-reference is not 1.0 the threshold is wrong.* **The only
reason this was catchable is that the control was in the run** — the
originally-proposed design, PPO against itself, would have produced the same
numbers with nothing to check them against.

#### The design claim, verified

**40 of 40 curves matched the published 150-simulation sweep at worst
\|diff\| = 0.000e+00.** A 2400-simulation run does contain the 150-simulation
run, exactly, for all three methods — so the ladder was read off one run per
seed rather than five, and prediction 11 is a clean hit.

#### What this does and does not license

**It does not rescue G3.** G3 is scored at 150 simulations, the budget every
published arm ran at, and at 150 PPO is behind uniform by 0.0426. A budget at
which PPO reaches parity with random search is a finding about the budget, not
a re-score of the gate.

**It does not test the amortised claim.** Every run here optimises one fixed
spec target from scratch, which is the regime `PREDICTIONS.md` entry 6 already
ring-fences. The spec-conditioned policy remains the only place RL has an
argument, and nothing in this entry touches it.

**What it does license** is a sharper sentence than the project had before:
*at a matched budget, from 150 to 2400 simulations, our PPO agent is
statistically indistinguishable from uniform random search at every budget
tested, while CMA-ES is separably better at every budget tested.* That is worth
more to a panel than a hedge about sample sizes, and it is now measured rather
than argued.

*Nothing above the Outcome heading was edited.*

---

## 16. Session 22j — **how many random simulations buy a library that answers any S3 spec?**

**Written 2026-08-20, before the sub-sampling run.** The owner asked to build
the spec-conditioned policy (`CLAUDEwa.md` §7's second contribution). Two things
turned up while building its scaffolding, **both before any training**, and the
second one is why this entry exists.

### Declared inputs — already measured, NOT predictions

Stated here so nothing below is scored as a forecast of something already seen.

**(a) `target_peaking_db` IS INERT, deliberately and by documentation.**
`reward_v1.margins`'s docstring says it outright: *"`target_peaking_db` is
accepted for the spec-conditioned form but is NOT used: S3's peaking constraint
is a BAND (3-12 dB), and CLAUDEwa.md §3 reads the band as the requirement."*
Verified by measurement — one fixed design scores **8.999984 against targets of
3, 5, 7.5, 10 and 12 dB**, identically — while the same design's score moves
`8.000 → 8.996 → −0.000` across a sweep of `target_f_peak_hz`.

**The consequence has not been written down anywhere and it matters to the
claimed contribution: the spec-conditioned problem is ONE-DIMENSIONAL.** The
observation carries a two-channel target block and one channel can never change
any reward. A "type in a spec" demo can honour the *frequency* request; the
peaking request is a band membership, not a target. That is a faithful reading
of S3 rather than a defect — and it halves what "spec-conditioned" can mean
here.

**(b) A zero-simulation lookup over the designs already on disk serves every
held-out target.** `spec_pool.load_pool` rebuilds **74 526 distinct valid P1
designs** from 146 597 logged trials (the grid sweep and the budget ladder).
Because a measurement does not know what it was aiming at, each can be
re-scored against any target for free. Result: **32 of 32 held-out targets —
16 interpolation, 16 extrapolation — are served by a feasible design at a
median best reward of 9.0000**, against a practical ceiling of 9.0.

**So the amortised comparison's real opponent is not CMA-ES-from-scratch. It is
a table lookup that costs nothing per query and already wins.**

### What this entry actually predicts

The lookup's one-off cost is the pool. **How big does the pool have to be?**
The sub-pool proposed by `uniform` alone — **24 480 designs**, the only
unbiased sample, since CMA-ES and PPO rows were steered toward the legacy
target — is sub-sampled at 30 / 100 / 300 / 1 000 / 3 000 / 10 000 / 24 480 and
the 32 held-out targets are re-scored against each. Zero simulations, seconds
of compute. Ten seeds per size, because a small sub-pool is a lottery.

| # | quantity | point | acceptance band |
|---|---|---|---|
| 1 | pool size at which **all 16** interpolation targets are feasible | **300** | 100 – 3 000 |
| 2 | median best reward at 100 designs | **8.80** | 8.0 – 8.97 |
| 3 | median best reward at 1 000 designs | **8.96** | 8.90 – 8.995 |
| 4 | median best reward at 10 000 designs | **8.995** | 8.98 – 9.000 |
| 5 | designs needed to reach a median best reward of **8.99** | **3 000** | 1 000 – 20 000 |
| 6 | extrapolation set behaves the same as interpolation | **yes**, within 0.005 at every size | — |
| 7 | the curve is roughly **log-linear** in pool size | yes | — |

**The prediction that decides the project's next two weeks is #5.** If a few
thousand random simulations buy a library that answers any S3 spec at
essentially the ceiling, then the amortised claim `CLAUDEwa.md` §7 makes is
**already satisfied by a database**, and a policy has to beat *zero
simulations at 8.99*. If instead it takes tens of thousands, a policy trained
on less is still a contribution.

### What would falsify the reasoning

1. **Coverage does not saturate** — the curve is still climbing steeply at
   24 480. Then the library is not cheap after all and the amortised claim is
   live.
2. **The extrapolation set behaves differently.** It should not: the lookup has
   no notion of train and test, so a difference would mean the two target sets
   are not drawn from comparable regions and `spec_dist` needs re-reading.
3. **Feasibility saturates but reward does not.** Then "served" is the wrong
   headline and the honest metric is distance-to-ceiling, not a pass rate.
4. **Small sub-pools beat large ones on some seed.** Impossible if the metric
   is a max over a growing set — it would mean `score_pool` is not a pure
   function of (design, target) and the whole pool method is unsound.

### Guard against over-claiming

**A lookup that wins here has NOT solved the competition problem.** The pool is
**P1 only** — one corner, one load. `Trial.meas` on a P3 row is a corner
measurement, so corner rows are excluded by construction, and nothing in this
entry says anything about S9. **The place a library provably cannot answer is
exactly the place gate G4 lives**, and that asymmetry is the argument for
spending the remaining time on corners rather than on amortisation.

**And it is not an argument that RL is worthless** — it is an argument that
*this* target space is too small for amortisation to be interesting. Two
dimensions, one of them inert, densely covered by designs we already have.

### Outcome — **fifty random simulations answer every spec in S3; six hundred answer them at 8.99 of 9.0. The library is far cheaper than I predicted, and all three misses are in that direction.** Run 2026-08-20, zero simulations, seconds of compute.

Uniform sub-pool only (24 480 designs), 32 held-out targets, 10-30 seeds per
size. Write-up: `nebula/SPEC_CONDITIONED.md`.

| library size | targets served | median best reward |
|---|---|---|
| 1 | 10 % | -1.0000 |
| 5 | 47 % | 6.0466 |
| 10 | 77 % | 8.5193 |
| 20 | 96 % | 8.7385 |
| **50** | **100 %** | 8.8576 |
| 100 | 100 % | 8.9305 |
| 300 | 100 % | 8.9757 |
| **600** | 100 % | **8.9899** |
| 1 000 | 100 % | 8.9936 |
| 3 000 | 100 % | 8.9970 |
| 10 000 | 100 % | 8.9991 |
| 24 480 | 100 % | 8.9997 |

#### Scoring

| # | prediction | point | band | measured | |
|---|---|---|---|---|---|
| 1 | size at which all 16 interpolation targets are feasible | 300 | 100-3 000 | **50** | **MISS**, below the band |
| 2 | median best at 100 designs | 8.80 | 8.0-8.97 | **8.9305** | HIT |
| 3 | median best at 1 000 designs | 8.96 | 8.90-8.995 | **8.9936** | HIT |
| 4 | median best at 10 000 designs | 8.995 | 8.98-9.000 | **8.9991** | HIT |
| 5 | designs needed to reach a median of 8.99 | 3 000 | 1 000-20 000 | **~600** | **MISS**, below the band |
| 6 | extrapolation within 0.005 of interpolation at every size | yes | - | **0.034 at 30, 0.008 at 100**, then <= 0.002 | **MISS** at the two smallest sizes |
| 7 | the curve is roughly log-linear | yes | - | **an exact 1/N law** | HIT, and stronger than predicted |

**4 hits, 3 misses, and every miss is in the same direction: the library is
cheaper than I thought.** #1 was wrong by 6x and #5 by 5x, both toward "less
data needed", which strengthens the finding rather than weakening it. #6's
miss is a small-sample artifact -- a lookup has no notion of train and test, so
at 30 designs the two target sets differ by luck, and by 300 they agree to
0.002.

#### The scaling law, which was not predicted at all

| N | gap to 9.0 | N x gap |
|---|---|---|
| 30 | 0.24893 | 7.47 |
| 100 | 0.06332 | 6.33 |
| 300 | 0.02544 | 7.63 |
| 1 000 | 0.00641 | 6.41 |
| 3 000 | 0.00272 | 8.17 |
| 10 000 | 0.00092 | 9.24 |
| 24 480 | 0.00032 | 7.85 |

**gap ~= 7.6 / N**, constant to +/-20 % across three orders of magnitude. To
halve the distance from the optimum, double the library. Prediction 7 asked for
"roughly log-linear" and got something far tighter.

#### The crossover, derived from the law

`BASELINES.md` §14 measured CMA-ES at **8.9736 for 150 simulations** and
**8.9999 for 2400**, *per spec, every time*. Inverting `gap = 7.6/N`:

| to match | library needs | crossover |
|---|---|---|
| CMA-ES at 150 sims/spec | **~290 designs** | **~2 specs** |
| CMA-ES at 2400 sims/spec | ~76 000 designs | ~32 specs |

**After two different spec requests, 300 random simulations have already paid
for themselves and give better answers than CMA-ES does for 150 simulations
every single time.**

#### What it means for the claimed contribution

A spec-conditioned policy would have to beat **zero simulations at 8.99**, on a
target space that is 2-D with one dimension inert and that ~600 random
simulations already cover. Falsifier 1 did not fire -- coverage saturates hard
and early.

**The guard written before the run stands and is now the recommendation:** the
pool is P1 only, a lookup holds nominal measurements and nothing else, and the
place it provably cannot answer is exactly where **G4** lives. That asymmetry
is the argument for spending the remaining time on corners rather than on
amortisation -- **and it is the owner's call, not an agent's**, because
`CLAUDEwa.md` §7 claims the spec-conditioned policy as contribution #2.

*Nothing above the Outcome heading was edited.*

---

## 17. Session 22n — **PPO is trained on a different objective from the one it is scored on. Does removing the mismatch fix it?**

**Written 2026-08-20, before the run, and committed before it starts.**

### The defect, in two lines

`rl/env.py`:

    terminated = bool(rb.feasible)     # early success

`rl/reward_v1.py`, feasible branch:

    reward = B + min_i(margin_i / tol_i)      # how far PAST the band you get

**The episode ends the instant every spec is met, and the metric rewards
exactly what happens after that.** The policy is never once in a state from
which it could learn to improve a design that already works — that region is
terminal.

### Declared inputs — measured, not predicted

| | |
|---|---|
| PPO runs at 150 sims (published sweep) | 10, unscreened |
| **feasible designs found, median** | **11.5** |
| ⇒ episodes ending in success | **~12 in 150 simulations** |
| what follows each | a fresh **uniform-random** `reset()` |
| horizon | 8 steps |
| PPO at 150 / 600 (`BASELINES.md` §14) | **8.9106 / 8.9844** |
| uniform at 150 / 600 | 8.9532 / 8.9860 |
| cmaes at 150 / 600 | 8.9736 / 8.9993 |

So a run is *random start → short walk → hits feasibility → STOP → random
restart*, about twelve times. **Random restarts plus a short walk that stops at
"good enough" is structurally a random search** — which is exactly what §14
measured PPO to be at every budget from 150 to 2400.

`CONTINUE_HERE.md` §5 item 3 flagged this as an open decision months ago and
nobody tested it.

### The experiment

`exp_ppo_terminate --run`. Two arms × two budgets × 10 seeds = **40 runs,
15 000 simulations, ~25 min**. `terminate_on_feasible` defaults to True, so
nothing published moves. The treatment suppresses termination **only on a
valid, feasible** evaluation; an invalid one still ends the episode (§6d) and
the horizon still truncates. Same `PPOConfig`, same box, same evaluator, same
reward, and **the same seed protocol** — `run_seed("P1", "ppo", rep)` — so the
control at 150 is a bit-for-bit re-run of the sweep's PPO arm.

### The mechanism check, which is reported before the outcome

`steps_from_feasible` counts environment steps taken **from** a state that
already met every spec. It is **near zero in the control, not exactly zero** —
a `reset()` can land on a feasible design and the first step out of it precedes
any termination. A 60-simulation smoke run measured **one** such step in the
control against **three** in the treatment.

**If the treatment does not raise it well above the control, the flag did not
do what it claims and the outcome is void.** That number is read first.

### Predictions

| # | quantity | point | acceptance band |
|---|---|---|---|
| 1 | control median at 150 **reproduces the published 8.9106** | exact | \|Δ\| ≤ 1e-9 |
| 2 | `steps_from_feasible`, treatment ÷ control, at 150 | **≥ 8×** | ≥ 3× |
| 3 | **Δ median best at 150** (treatment − control) | **+0.015** | −0.020 … +0.060 |
| 4 | **Δ median best at 600** | **+0.010** | −0.015 … +0.050 |
| 5 | does the treatment beat **uniform random** at 150 (8.9532)? | **no** | — |
| 6 | treatment's gain over the final third, at 600 | **+0.004** | 0.000 … 0.040 |
| 7 | median episodes per run at 150, treatment vs control | **fewer, but < 2× fewer** | — |
| 8 | is Δ separable at either budget? | **no** at 10 seeds | — |

**The prediction that matters is #3 and #5 together: I expect a real,
directionally positive effect that is still not enough to beat random search.**
If that holds, the mismatch was a genuine defect *and* not the binding one, and
the negative result about RL gets stronger rather than weaker — because it will
have survived the removal of its most obvious excuse.

### What would falsify the reasoning

1. **The mechanism counter barely moves.** Then the flag is not doing what the
   code says and nothing else in this entry can be read.
2. **Δ ≥ +0.05 at both budgets, and the treatment beats uniform.** Then the
   mismatch *was* the binding defect, `BASELINES.md` §14's ranking was measuring
   an implementation bug rather than PPO, and **the G3 comparison must be
   re-run with the fix** before anything about RL is published.
3. **Δ is strongly negative.** Then episode restarts were doing the work — the
   run really was random search and removing the restarts removed the search.
   That is the cleanest possible confirmation of the diagnosis and the worst
   possible outcome for RL.
4. **The control does not reproduce 8.9106.** Then this harness is not running
   what the sweep ran and no comparison here is valid.

### Guard against over-claiming

**A positive Δ is not "RL works".** It would mean PPO trained on its own
objective does better than PPO trained on a different one — which is a
statement about the experimental setup, not about reinforcement learning. The
claim that matters is #5: whether it beats uniform random at the budget G3 is
scored at.

**And a null result is not a wasted run.** Today a reviewer can correctly say
*"you trained on a different objective from the one you reported."* After this
run they cannot, whichever way it lands — which is why it is worth doing
independently of the outcome.

### Outcome — **the mismatch was real and cost 0.0413. It closes 97 % of PPO's gap to random search, moves one of G3's two clauses, and is still not enough to win.** Run 2026-08-20, 40 runs, 15 000 simulations, 25 min.

#### The mechanism check, read first

| budget | arm | steps from feasible | fraction | episodes |
|---|---|---|---|---|
| 150 | control | 4 | 0.043 | 24 |
| 150 | **fixed** | **18** | **0.166** | 20 |
| 600 | control | 15 | 0.036 | 98 |
| 600 | **fixed** | **74** | **0.164** | 78 |

**4.5× and 4.9×.** The flag does what it claims: the policy now spends a sixth
of its steps inside the region the metric rewards, against a twenty-fifth
before. Falsifier 1 did not fire, so the outcome can be read.

#### The outcome

| budget | control | fixed | Δ | separable? |
|---|---|---|---|---|
| 150 | 8.910626 | **8.951936** | **+0.0413** | not separable |
| 600 | 8.984407 | 8.987479 | +0.0031 | not separable |

**The control reproduces the published sweep to 4.67e-07** — same seeds, same
objective, same harness. So the comparison is against the real published PPO
and not against a re-implementation.

#### The headline

> **Gap to uniform random at 150 simulations: −0.0426 before, −0.0013 after.
> 97.0 % of it closed by removing a two-line objective mismatch.**

That is **~4× larger than any other PPO intervention this project has tried** —
session 22g's `rollout_steps` change bought +0.0106.

**And it is still not a win.** At 150 the fixed policy sits 0.0013 *below*
uniform random. At 600 it edges 0.0015 *above*. Neither is separable; both are
rounding-level.

#### What it does to G3, and this is the part that matters

At 150 simulations, the budget G3 is scored at, against the published arms:

| comparison | control | **fixed** |
|---|---|---|
| RL vs **grid search** | not separable | **SEPARABLE WIN** |
| RL vs **random search** | not separable (−0.0426 on the point) | not separable (−0.0013) |
| RL vs LHS | not separable | not separable |
| RL vs CMA-ES | **separably BELOW** | not separable |

**Three of those four moved, all in RL's favour:**

* **G3's grid clause is now MET.** `ppo` [8.9175, 8.9787] against `grid`
  [8.8886, 8.8886] — the intervals do not overlap.
* **RL is no longer separably below CMA-ES.**
* The sentence *"RL loses to random search"* becomes **"RL is statistically
  indistinguishable from random search"**, which is both more accurate and
  more favourable, and is honestly earned.

**G3 still fails**, on one clause instead of two — and the failing clause is
now *"cannot demonstrate superiority"* rather than *"loses"*.

#### Scoring

| # | prediction | point | band | measured | |
|---|---|---|---|---|---|
| 1 | control reproduces 8.9106 | exact | ≤ 1e-9 | **4.67e-07** | reproduces; **my band was mis-specified** — see below |
| 2 | steps ratio, treatment ÷ control | ≥ 8× | ≥ 3× | **4.5× / 4.9×** | in band, point too high |
| 3 | Δ at 150 | +0.015 | −0.020…+0.060 | **+0.0413** | HIT |
| 4 | Δ at 600 | +0.010 | −0.015…+0.050 | **+0.0031** | HIT |
| 5 | does the fix beat uniform at 150? | **no** | — | **no**, −0.0013 | HIT |
| 6 | gain over the final third at 600 | +0.004 | 0.000–0.040 | **+0.0000** | in band at its floor |
| 7 | episodes fewer, but < 2× fewer | yes | — | 24→20, 98→78 | HIT |
| 8 | separable at either budget? | **no** | — | **no** | HIT |

**Five clean hits, two in-band with the point off, one band I wrote wrong.**

**#1 is scored as "reproduces, band mis-specified" rather than as a miss**, and
the distinction is mine to own: I set a 1e-9 band against a reference value I
only had to six decimal places, so the band was never checkable as written. The
substance — that this harness runs what the sweep ran — holds at 4.67e-07,
which is display precision.

**No falsifier fired.** In particular #2 did not: Δ at 600 is +0.0031, far
below the +0.05 that would have meant the published ranking was measuring an
implementation bug and forced a full G3 re-run.

#### The prediction that mattered, and it held

> *"a real, directionally positive effect that is still not enough to beat
> uniform random"*

Both halves. The effect is real and the largest yet; it is still not a win.
**So the negative result about RL is now stronger, not weaker — it has survived
the removal of its most obvious excuse.** Before today a reviewer could
correctly say *"you trained on a different objective from the one you
reported."* They no longer can.

#### What this does NOT license

**It is not a re-run of the benchmark.** `BASELINES.md` §14's PPO rows were
measured with the mismatch and stay as they are; this entry is the matched
control for them, at the same seeds and the same objective, and the fixed
numbers must be quoted **beside** them rather than substituted for them.
Whether the published sweep is re-run with `terminate_on_feasible=False` is a
§7f event and an owner's decision.

**And +0.0413 is not "RL works".** It is the cost of one implementation defect,
measured. The claim that matters is #5, and it is unchanged: at the budget G3
is scored at, reinforcement learning does not beat random search.

*Nothing above the Outcome heading was edited.*


---

## 18. Session 22q — **an EXTERNAL prediction about the reward, falsified by data that was already on disk**

**Written:** 2026-08-20, session 22q. **This entry is retrospective and says so
in its first line**, which the rest of this file's entries are not allowed to
be. The reason it is admissible: the prediction came from OUTSIDE this project
(a task brief), the data that falsifies it was **already committed** before the
prediction was made, and no simulation was run to produce the falsification.
There was nothing to pre-register — the measurement predated the claim. It is
recorded because a hypothesis that shaped a work plan and turned out to be
wrong is exactly what this file is for.

### The prediction, verbatim from the brief

> *"The reward treats power and noise as **scored** (more margin = better), so
> the optimiser spent its degrees of freedom buying margin on constraints that
> were already satisfied, and starved the one spec that binds."*

with the supporting observation that the delivered design has **6.9x power
margin, 7.1x noise margin and 23x area margin** while S8 is blocked, and the
proposed remedy that *"power, noise and area become hard constraints (pass/fail,
no credit for exceeding), not scored terms."*

### Outcome — **FALSIFIED on the mechanism, and the proposed remedy measures as a NO-OP. The conclusion it was reaching for is right; the reason is the opposite one.**

`reward_v1.reward`'s feasible branch is `B + min_i(margin_i / tol_i)` — a
**maximin**, not a sum. Exceeding a spec is worth exactly nothing unless that
spec is the binding minimum. That is `CLAUDEwa.md` section 9's own rule (*"do
not add bonus terms for exceeding a spec"*) already correctly implemented, and
it means the stated mechanism cannot occur in this objective.

Re-scoring the **74 526 distinct valid designs already on disk** against
9 dB / 1.9 GHz (`spec_pool`; **zero simulations** — a measurement does not know
what it was aiming at):

| binding row among the 33 214 FEASIBLE designs | share |
|---|---|
| `S3_f_peak` | **94.5 %** |
| `S3_peaking` | 3.5 % |
| `tail_saturation` | 1.2 % |
| **`S6_power`** | **0.6 %** |
| `saturation` | 0.2 % |
| **`S5_noise`** | **0.0 % — never** |

`corr(reward, power) = -0.17`, `corr(reward, noise) = -0.12`.

**The remedy, applied and measured.** Moving power and noise from scored to
hard-constraint:

* feasible set **identical** — 33 214 designs either way;
* reward changes on **210 of 33 214** designs (**0.63 %**);
* the best design is **unchanged**.

Area needed no change at all: `S7_area` was never in `V1_SPECS`.

**WHAT IS ACTUALLY WRONG IS THE OPPOSITE PROPERTY — the reward is not greedy,
it is INDIFFERENT.** A maximin goes flat once every non-binding row clears the
minimum. Within **0.001** of the best attainable reward the pool holds **38
designs spanning 0.500-4.217 mA of tail current (8.4x)** and 0.92-7.56 mW;
within 0.01, **355 designs spanning 11.3x**. **The delivered 1.1376 mA was
never bought. It was drawn from a plateau that is flat in current across an
order of magnitude.**

So the lever is an **added** term, not a removed one — and two further premises
of the brief are also false: `VDD_NOMINAL_V` is **1.8 V**, not 3.3 V, and the
`i_bias` box already spans **0.5-8 mA** with its ceiling set by S6 itself
(8 mA x 1.8 V = 14.4 mW against a 15 mW limit), so the tail-current bound
cannot be raised without admitting S6 violations.

**Owner's decision, 2026-08-20:** do not build the hard-constraint flag (it
measures as a no-op); ship the measurement; hold the linear-range scored term
until item 3 lands.

**The general lesson, now `HANDOFF.md` G102:** *before removing a term from an
objective, measure how often it BINDS.* A term that binds 0 % of the time is
already inert, and deleting it changes nothing while looking like a fix.

---

## 19. Session 22q — **what does S3 charge for linearity? The attainable linear-input-range front, and where it crosses PCIe Gen2 drive**

**Written:** 2026-08-20, session 22q, **before `exp_linear_pareto.py --run` was
executed at full size.**
**Experiment:** `python -m nebula.experiments.exp_linear_pareto --run` — two
arms, ~1 600 simulations, ~10 min. `pool`: 28 peaking bins x 30 designs
replayed from `spec_pool` with `swing=True`. `targeted`: CMA-ES at 5 peaking
bands x 150 simulations with **linear input range at Nyquist as the
objective**, which is what makes a negative result mean something.

### Declared inputs — measured before this entry, NOT predicted

1. `linear range at f = linear range at DC / |H(f)/H(0)|`, because `Cs` shorts
   out the same `Rs` the linear range is made of. Session 22q, `HANDOFF.md`
   G103.
2. The delivered design: **520 mVpp at DC, 172 mVpp at Nyquist**, drive
   **534.7 mVpp**, overdrive **3.11x**, at 135 of 135 points.
3. The drive is **post-channel**: 800 mVpp raw TX, -3.5 dB mandated
   de-emphasis, 0 dB channel loss at DC by construction.
4. The `gm/I_D` table says the box reaches **gm/I_D from 21.35 down to ~5**
   inside the current window, i.e. `V_ov` from ~94 mV up to ~400 mV. The
   delivered design sits near the **top** of that range (gm/I_D ~ 20).

### DISCLOSURE: a 28-simulation debug run was executed before this entry, and I have seen it

One design per bin, `--pool-only --per-bin 1`. It is stated here in full
because pre-registering against something already seen and not saying so is
the failure this file exists to prevent. It showed: the **DC** front rising
with peaking (~600 mVpp at 0 dB to ~1400 mVpp at 13 dB); the **Nyquist** front
roughly **flat** at 150-450 mVpp across 3-14 dB; and single samples at 8-11 dB
already reaching **0.65-0.82x** the drive. **It does not determine the front** —
n = 1 per bin, no targeted arm — and everything predicted below concerns what
30x the sample plus a search that optimises the quantity directly will find.

### Predictions

1. **The DC front RISES with peaking and the Nyquist front does NOT.** Formally:
   regress the DC front on `k = 10^(peaking/20)` in log-log; the slope lands in
   **[0.7, 1.3]**. The Nyquist front's spread across the 3-12 dB bins is
   **under 6 dB peak-to-peak** — i.e. flat to within a factor of 2.
   *Reasoning:* degeneration multiplies the DC linear range by `k` and the
   peaking divides it by the same `k`, so at the signal band the pair is
   un-degenerated and its range is set by `V_ov` alone. If this holds, **S3
   does not charge for linearity at all** — the price is paid in `gm/I_D`, and
   the framing of "maximum peaking at which the topology accepts PCIe Gen2
   drive" has no crossing point in peaking to find.
2. **The best linear range at Nyquist found anywhere lands in
   [450, 900] mVpp.** Point estimate **650 mVpp**. *Reasoning:* `V_ov` up to
   ~400 mV is reachable per input 4, and the delivered 172 mVpp sits at
   ~0.85 `V_ov`; the ceiling is supply headroom on 1.8 V, not the box.
3. **The drive IS reached at 3 dB.** Confidence high (85 %).
4. **The drive IS ALSO reached at 9.78 dB** — i.e. the owner's suggested
   prediction that 9.78 dB is unreachable at any sizing is one I expect to
   MISS. Confidence **65 %**. *Reasoning:* prediction 1. If the Nyquist front
   is flat in peaking then whatever is reachable at 3 dB is reachable at
   9.78 dB, and the debug run's 0.65-0.82x at 8-11 dB is already most of the
   way there on one sample per bin. **Band: the 9.5-10.0 dB bin's front lands
   in [400, 800] mVpp.**
5. **The targeted arm beats the pool arm at every band**, by at least **1.3x**
   in the 9-10 dB bins. *Reasoning:* the pool was produced by searches scoring
   `reward_v1`, which is blind to linear range, so its coverage of the
   high-`V_ov` corner is incidental.
6. **A design that clears the drive at Nyquist will NOT meet S3+S5+S6+saturation
   at the same time.** Confidence moderate (60 %). *Reasoning:* `V_ov` ~ 400 mV
   costs `vds > vdsat = V_ov` of output headroom on a 1.8 V rail with `vcm_in`
   at 1.1-1.6 V, and it costs current. **This is the prediction that decides
   whether S8 can actually be unblocked**, and arms 1-5 do not test it — the
   objective here scores linear range and peaking only. If 6 holds, the finding
   is a genuine three-way conflict; if it fails, the delivered design is simply
   in the wrong part of the box and should be re-searched.

### What would falsify the reasoning

* If the **Nyquist** front rises or falls monotonically with peaking by more
  than 6 dB, the `k`-cancellation is wrong and the DC/Nyquist relation needs
  re-deriving before any of this is quotable.
* If the targeted arm does **not** beat the pool arm, either CMA-ES is failing
  on this objective or the pool already covers the corner — and prediction 2's
  ceiling would then be a property of the box rather than of the sample.
* If many bins come back `n_with_a_hard_limit = 0` (the `.dc` sweep never
  compressing inside +/-0.8 V), the front is measuring the sweep range and not
  the circuit, and the sweep must be widened before anything is read off it.

### Guard against over-claiming, in both directions

**This is an ATTAINED front from ~1 600 simulations, not a proven envelope.**
No result here can show that no sizing anywhere does better. A "not reached"
verdict is evidence in proportion to the targeted arm's effort and nothing
more, and it must be written that way. Equally, a front that DOES cross the
drive says only that peaking and linear range can coexist — prediction 6 is
where the rest of the spec table gets its say, and it is not tested by this
run.

### Outcome — *not yet run.*
