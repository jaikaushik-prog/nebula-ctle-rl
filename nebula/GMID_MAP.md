# GMID_MAP.md — a gm/I_D table and a design-space map, measured

**Session 20, 2026-08-17.** Infrastructure for a possible reparameterization of
the RL search, and the experiment that says how much of it works.

**Status.** Built and measured. **Not wired into the RL loop, and wiring it is a
human decision** (CLAUDEwa.md §8 rules 5 and 6): `common/params.py`,
`rl/contract.py` and `rl/env.py` are untouched, and adopting this would
invalidate every existing baseline comparison. This file is a measurement
brought back for that decision.

| | |
|---|---|
| The table | `nebula/device/gmid_lut.py` -> `nebula/device/data/gmid_lut_sky130_nfet01v8.npz` (tracked, G49) |
| The map | `nebula/common/design_space.py` (pure; no simulator, no I/O) |
| The experiment | `nebula/experiments/exp_gmid_validation.py` |
| Logged data | `gmid_validation_run.jsonl`, `gmid_validation_kalpha090.jsonl` (tracked) |
| Tests | `test_gmid_lut.py` (24), `test_design_space.py` (32), `test_exp_gmid_validation.py` (19) |
| One command | `python -m nebula.device.gmid_lut --build --workers 6` then `python -m nebula.experiments.exp_gmid_validation --run --n 1500` |

---

## 0. What a reader in a hurry needs

1. **The idea's stated mechanism does not work, and the measurement is
   unambiguous.** The hypothesis was that making `f_z` a coordinate would put
   the G44 sweep-edge region out of reach by construction. Measured: **G44 as a
   share of designs that actually reached the simulator is 38.07 % in device
   coordinates and 37.74 % in design coordinates.** Unchanged. The
   reparameterization does not make the bad region unreachable.

2. **The idea's stated BENEFIT is real but small, and it arrives by a different
   route than predicted.** The map rejects **89.40 %** of design-space
   proposals before spending a simulation — not because it can see the peak,
   but because those requests are not representable in the device box at all
   (**878 of 1341** are "no width in 20-100 um carries this current at this
   inversion level"). Net effect on what a search pays: **1.90 -> 1.64
   simulations per valid design, a 1.16x improvement.**

3. **The analytic peak predictor cannot be used as a pre-simulation filter as
   written.** Against SPICE on 159 simulated designs it scored **TN = 0** — it
   never once correctly excluded a design — with precision 61.78 %. Adding the
   guard's own 20 GHz search ceiling (a genuine defect in the first version,
   §5) takes it to **TN = 8, precision 65.10 %**. Still not a filter.

4. **Two things the map DOES get right, and they are worth keeping regardless
   of the decision.** `f_z` and `k` round-trip exactly through the geometry
   (algebraic, rel < 1e-9), and the DC gain lands at a median **-0.20 dB**
   against SPICE. The bias solve is a measured table, not a fit.

5. **A PDK finding that outlives this experiment: the gm/I_D method's central
   premise fails on SKY130 at fixed `nf`.** `I_D/W` varies **1.56x** across the
   `w_in` box because `W/nf` sweeps the model bins (G53's axis). Scaling
   current linearly in `W`, which is what the textbook method does, is a **56 %
   width error** on a device that simulates perfectly happily.

**The honest one-line verdict:** the infrastructure is sound and reusable, the
motivating argument is measured false, and the residual benefit (1.16x) is real
but is not on its own worth invalidating the baselines. See §8.

---

## 1. Why this was proposed

Two measured problems with searching in device coordinates, both from
`RL_SMOKE.md`:

* **G44 dominates the failure modes.** §5: **159 of 203 invalid evaluations —
  78.3 % of a 26.54 % invalid rate — were `peak_is_sweep_edge`**, a response
  still rising at 20 GHz that `meas ac MAX` reports as a large fictitious peak.
  Under a reward reading S3 peaking, every one would have scored high for a
  circuit with no peak.
* **The axes are badly conditioned.** §4: the seven device dimensions differ in
  strength by **21x** under one `MAX_STEP` (`vcm_in` 0.605 of a channel scale
  against `w_in`'s 0.0282), and `w_in`/`l_in` are the two weakest survivors —
  both acting on peaking through `gm`, where `rs` acts on the same channel
  **4-10x harder**.

The proposal: search `(gm/I_D, L, I, f_z, k, R_L, VCM)` instead. The claim was
that because

    f_z   is a coordinate
    f_p1  = k * f_z                    (CLAUDEwa.md §6: w_p1 = k/(Rs*Cs))
    f_p2  = 1 / (2*pi*R_L*C_L)         R_L a coordinate, C_L a context

the whole pole-zero triple is known before simulating, so the sweep-edge region
is identifiable — and the axes align with the specs.

**It fits the brief.** The problem statement asks for a framework that "sizes
devices using fewer search spaces (lowest design time)". A design-space
reparameterization is literally that, and gm/I_D is the methodology a
practising analog designer uses, which is an asset in front of this panel.

---

## 2. What was built

### 2.1 The table (`device/gmid_lut.py`)

Direct ngspice `.dc` sweep of one `nfet_01v8`, terminal voltages forced, bulk at
0 so `V_sb` **is** the source node. Stores nine `.op` **primitives** —
`gm, id, gmbs, gds, vth, vdsat, cgg, cgs, cgd` — and computes every derived
quantity in Python (rule 10). Built on the nfet-only trim (G36).

| axis | values | why |
|---|---|---|
| corner | `tt@27`, `ss@125`, `ff@0`, `ss@0` | TT plus `s9_yield.SCREEN_CORNERS` verbatim; G47 measured 3 corners worth 98.7 % of 45 |
| W (um) | 20, 35, 55, 75, 100 | `ACTION_SPACE`'s `w_in` box. **An axis, not a scaling reference — see §3** |
| L (um) | 0.15, 0.21, 0.30, 0.42, 0.60, 1.00 | `ACTION_SPACE`'s `l_in` box, log-spaced |
| V_ds (V) | 0.15, 0.35, 0.60, 0.95, 1.50 | floor below every measured `vdsat`, so the triode side is IN the table and can be rejected rather than extrapolated |
| V_sb (V) | 0.0, 0.20, 0.40, 0.60, 0.85 | **the body-effect axis.** 0.0 included so `gmbs = 0` is a lookup, not a guess |
| V_gs (V) | 0.30 .. 1.80 step 0.01 | free — one `.dc` carries the whole axis |

**Measured:** 3000 invocations, **510 s at 6 workers**. `gm/I_D` spans
**0.56 .. 35.87 1/V**; **100.00 %** of curves are strictly decreasing in `V_gs`
over the usable band, which is the gate the inversion depends on; `gmbs/gm`
spans **0.112 .. 0.259** (5th-95th percentile, `I_D` > 1 nA).

**The VDD axis of S9 costs nothing here**, and that is a property of the
indexing rather than a saving that was negotiated: the table is indexed on
terminal voltages, so a 5 % supply move changes where a design lands in the
table, not the table.

### 2.2 The map (`common/design_space.py`)

Seven in, seven out. Three coordinates swapped, four passed through:

    w_in  <- gm_over_id        rs <- k        cs <- f_z
    l_in, i_bias, rl, vcm_in   unchanged

The dimensionality is deliberately identical to `ACTION_SPACE`'s: a
reparameterization that also changed the dimension would confound two effects.

**The bias solve is a fixed point and the module says so.** `gm` is immediate
(`gm = gm_over_id * I_D`, both coordinates), so `Rs = 2(k-1)/(gm+gmbs)` is one
division — but `gmbs` needs `V_sb`, `V_sb` is `vcm_in - V_gs`, `W` is set by
requiring the device to carry `I_D`, and `V_ds` is `(VDD - I_D*R_L) - V_sb`.
Three mutually dependent unknowns, no closed form, explicit iteration cap,
`bias_no_convergence` returned rather than the last iterate. **`Rs` does not
enter the loop**, and that is exact rather than an approximation: it sits
between the two sources and carries no DC current at balance.

Every failure is **named** and nothing is **clamped**. Clamping an infeasible
request onto a box edge turns "you cannot have this" into a plausible-looking
sizing that simulates — G44's class of bug.

---

## 3. The premise that failed, and it is a PDK finding

The classical method's economy is that `gm/I_D` depends on inversion level and
not on `W`, so one sweep scales to any width through the current density
`I_D/W`. **Measured at TT/27, L = 0.30 um, V_ds = 0.75 V, V_sb = 0.40 V,
V_gs = 0.90 V:**

| W (um) | 10 | 15 | 20 | 30 | 40 | 60 | 80 | 100 |
|---|---|---|---|---|---|---|---|---|
| W/nf | 2.50 | 3.75 | 5.00 | 7.50 | 10.00 | 15.00 | 20.00 | 25.00 |
| I_D/W | 1.25e-5 | 1.35e-5 | 1.43e-5 | 1.56e-5 | 1.72e-5 | 1.87e-5 | 1.92e-5 | 1.95e-5 |
| gm/I_D | 10.74 | 10.47 | 10.23 | 10.00 | 9.63 | 9.31 | 9.19 | 9.14 |

`I_D/W` moves **1.56x across the `w_in` box** and `gm/I_D` moves 15 %. Over the
whole sweep at matched `V_gs`, the median relative spread across
W = {20, 40, 100} um is **2.33 % for gm/I_D and 33.13 % for I_D/W**.

**The mechanism is G53's.** SKY130's model bins are cut on **W per FINGER**, and
`rl/contract.py` fixes `nf` at 4 (G38), so sweeping `W` from 20 to 100 um sweeps
W/nf from 5 to 25 um straight across the bin set. The variation is **smooth and
monotone**, so it interpolates cleanly — which is exactly what makes it
dangerous: linear-in-`W` scaling is a **56 % width error** and the resulting
device simulates perfectly happily.

**Consequence, and it generalises past this file:** any gm/I_D work on SKY130
at fixed `nf` needs `W` as a real axis. That costs ~5x the build time and
nothing at lookup.

---

## 4. The experiment

**Two arms, same sampler, same evaluator, same corner and load.** 1500 Latin
hypercube samples each, seed 20260817, TT/27 C, `cl_mid` = 32.63 fF, drawn
passives and a real current-mirror tail throughout, scored by
`rl/evaluator.py` — the same validator the RL loop uses, so the verdicts are
comparable by construction.

* **Arm A (control), device coordinates:** LHS over `ACTION_SPACE`.
* **Arm B, design coordinates:** LHS over the design box, then `to_device`,
  then the same evaluator. A request the map rejects costs **no** simulation.

**The design box is DERIVED, not chosen** (rule 6): it is the **measured image
of the approved device box**, computed by forward-mapping the 1890 already-paid-
for TT operating points in `robust_geometry_data.csv` through
`design_space.to_design` —

| coordinate | range | source |
|---|---|---|
| `gm_over_id` | 1.332 .. 19.96 1/V | measured image |
| `k` | 1.069 .. 13.95 | measured image |
| `f_z` | 16.81 MHz .. 28.53 GHz | measured image |
| `l_in`, `i_bias`, `rl`, `vcm_in` | — | `ACTION_SPACE` verbatim |

**The control is NOT the RL smoke run.** That 26.54 % / 78.33 % came from a
*policy's* proposals; comparing a uniform sample against it would compare two
samplers as well as two parameterizations — G71's error one layer up. The smoke
numbers are quoted as context and labelled as context, in the code and in the
printout.

---

## 5. Results

### 5.1 Validity — **the main hypothesis misses**

1659 SPICE invocations, **359.8 s of simulator** — device arm 320.9 s for 1500
evaluations (**0.214 s each**), design arm 41.3 s for 159. Worth noting against
`RL_SMOKE.md`'s **2.07 s/evaluation** for the same extended-library netlist:
this ran on session 19a's uncommitted per-section library split, which is where
the ~10x came from. It is why an experiment of this size was affordable at all.

| | device (control) | design |
|---|---|---|
| proposed | 1500 | 1500 |
| **rejected by the map** (free) | 0 | **1341 (89.40 %)** |
| simulated | 1500 | 159 |
| valid | 788 | 97 |
| headroom-only | 138 | 2 |
| invalid | 574 | 60 |
| invalid rate (of simulated) | 38.27 % | 37.74 % |
| **G44 count** | 571 | 60 |
| **G44 % of SIMULATED** | **38.07 %** | **37.74 %** |
| G44 % of PROPOSED | 38.07 % | 4.00 % |
| VALID % of simulated | 52.53 % | 61.01 % |
| **simulations per VALID design** | **1.90** | **1.64** |

**Read the two G44 rows together, because either alone misleads.**

*"G44 % of PROPOSED falls 38.07 -> 4.00 %, a 9.5x reduction"* is true and is
almost entirely an artifact of 89.40 % of proposals never being simulated.

*"G44 % of SIMULATED is 38.07 vs 37.74 %"* is the number that tests the
hypothesis, and it says **the reparameterization does not make the sweep-edge
region less reachable.** Conditional on getting to the simulator, design
coordinates land in G44 at the same rate device coordinates do.

The metric that prices both kinds of waste is **simulations per valid design**,
and it is **1.90 -> 1.64, a 1.16x improvement.** That is the honest size of the
benefit.

### 5.2 What the map rejected, and why it is not a physics screen

| reason | count |
|---|---|
| `current_unreachable` | 878 |
| `rs_outside_box` | 208 |
| `outside_table` | 142 |
| `cs_outside_box` | 97 |
| `source_node_outside_table` | 16 |

**878 of 1341 — 65 % of all rejections — are "no width in 20-100 um carries
this current at this inversion level".** That is the design box's corners not
being representable in the device box, not the map detecting a bad circuit. The
free rejection is real and it is cheap, but calling it a screen would be
overclaiming: compare `BASELINES.md` §5's analytic pre-screen, which rejects
61.7 % of the box *on a prediction about S3* and lifts the S3 rate 2.60x.

### 5.3 Accuracy — requested against measured

Design arm, VALID rows only (a HEADROOM_ONLY row has no trustworthy AC spec set
by construction, so scoring against it would be scoring a number the evaluator
has said not to believe). Reported as **measured minus requested**.

| quantity | all valid (n = 95-97) | measured f_peak inside S3's window (n = 32) |
|---|---|---|
| `f_peak` error | median **-0.355 oct** (p10 -0.686, p90 -0.024) | median **-0.353 oct** (p10 -0.545, p90 -0.032) |
| `peaking` error | median **-0.933 dB** (p10 -2.917, p90 -0.305) | median **-0.816 dB** |
| `g_dc` error | median **-0.197 dB** (p10 -0.503, p90 +0.508) | median **-0.181 dB** |

**The DC gain is good** — a median 0.2 dB, which is inside CLAUDEwa.md §6's own
1 dB gate and says the bias solve and the body-effect term are both working.

**`f_peak` is systematically over-predicted by 0.35 octaves (28 %)**, and that
is worse than the analytic pre-screen manages at benchmark conditions
(`BASELINES.md` §11: 15.85 % MdAPE). The direction is consistent with G60 —
§6's equations neglect `r_o`, over-predict `k`, and therefore push both the
peak and the peaking up.

**The G60 calibration confirms the mechanism, and exposes a trade.** Re-running
the design arm at `k_alpha = 0.90` (`--design-only`, the control is unaffected
because it never calls the map), S3-window rows:

| | `k_alpha` = 1.0 (§6 verbatim) | `k_alpha` = 0.90 (G60-calibrated) |
|---|---|---|
| *S3-window rows* | *n = 32* | *n = 31* |
| peaking error | **-0.816 dB** | **-0.157 dB** |
| `f_peak` error | -0.353 oct | -0.288 oct |
| `g_dc` error | **-0.181 dB** | **-0.663 dB** |
| *whole design arm* | | |
| G44 % of simulated | 37.74 % | 36.42 % |
| sims per VALID | 1.64 | 1.62 |
| free rejection | 89.40 % | 89.93 % |

**The calibration fixes the peaking bias 5x and makes the DC gain 3.7x worse**,
because `A_dc = gm*R_L/k` and both read the same `k`. G60 says to fit `k` from
the measured peaking alone and treat `f_peak` as an independent check; this is
that trade made visible. Neither setting is recommended here — that is a human
decision, and the numbers for both are above.

### 5.4 Can G44 be seen before simulating? **No, not as written**

Confusion matrix against SPICE, design arm, 159 simulated rows. Positive =
"has an interior peak".

| predictor | TP | FP | TN | FN | accuracy | precision | recall |
|---|---|---|---|---|---|---|---|
| bare condition (peak anywhere) | 97 | 60 | **0** | 2 | 61.01 % | 61.78 % | 97.98 % |
| + the guard's 20 GHz search ceiling | 97 | 52 | **8** | 2 | 66.04 % | 65.10 % | 97.98 % |

**TN is the only number that matters here**: it counts designs the predictor
correctly kept out of the simulator. A predictor with TN = 0 has not saved a
single simulation, whatever its accuracy.

**The first version scored TN = 0 because of a real defect, and finding it is
part of the result.** The two questions are different:

    the closed form      does |H| have an interior maximum ANYWHERE?
    peak_is_sweep_edge   is the maximum WITHIN the 20 GHz search range
                         sitting at the range edge?

The G44 rows had predicted `f_peak` at a **median 9.94 GHz**, several above
20 GHz (one at 37.3 GHz). Those are *genuine* interior peaks — the closed form
is right — and the guard fires anyway, correctly, because inside the search
window the response is monotonically rising. `predicted_peak` now takes
`search_top_hz` and a test pins the case.

**That fix accounts for 8 of the 60 misses. The other 52 are model error**, and
they are the same three effects the map's own docstring names: `to_geometry`
quantisation (G67), the `res_po` bottom plate moving `f_p2` by up to +75 % of
`cl` (G66), and the one-zero/two-pole model itself (session 18c: 4.25 % of the
`f_peak` spread).

---

## 6. What this does NOT license

* **It does not license changing the action space.** Rules 5 and 6, and
  `BASELINES.md`'s own constraint that touching the box means re-running every
  baseline.
* **It does not license quoting any requested value.** Every number in §5 is
  `measured - requested`, and the measured side always comes from
  `rl/evaluator.py`. The map produces a REQUEST.
* **It is TT-only, one seed, one load, nominal VDD.** The table carries three
  more corners; the experiment does not use them.
* **The two arms do not sample the same set.** The design box is the image of
  the device box under *independent-coordinate* sampling, so it contains corner
  combinations that never co-occur — which is exactly why 65 % of rejections
  are `current_unreachable`. The cost metrics (§5.1's last two rows) price this
  correctly because they charge only for simulations actually spent, but the
  *distributions* over the feasible region are not identical between arms, and
  no claim here depends on them being so.
* **The device arm gets no free filter.** A fair "free rejection" comparison
  would run `experiments/prescreen.py` in front of the device arm. That is the
  obvious next experiment and it is not done.

---

## 7. What was earned along the way

Three PDK/tooling findings, each measured, each with a test:

1. **`I_D/W` is not width-independent on SKY130 at fixed `nf`** — 1.56x across
   the box, via the W-per-finger bins (§3).
2. **You write microns and you read back metres.** `W=40` in the netlist is
   40 um (`.option scale=1e-6`, G31); `print @m.xm1.m<dev>[w]` returns
   `4.000000e-05`. A read-back check written the obvious way fails by 1e6 on a
   correct circuit — G31's failure mode with the sign reversed.
3. **SKY130 refuses an out-of-bin WIDTH and silently extrapolates an out-of-bin
   LENGTH.** `W = 0.1 um` gives "could not find a valid modelname"; `L = 99 um`
   simulates happily and the current scales as a clean 1/L
   (I_D at V_gs = 1.2 V: 5.92e-3 at L = 0.15, 1.37e-3 at 1.0, 1.56e-4 at 10,
   1.59e-5 at 99). **On the L axis, the map's refusal to extrapolate is the
   only guard there is.**

And one BSIM4 convention worth knowing: **`cgs` is negative** as reported
(measured `cgg` +2.455e-14, `cgs` -1.663e-14, `cgd` +1.199e-16). These are
charge-derivative matrix entries, not terminal capacitances. Stored raw;
`f_t_hz()` takes `abs()` with the note attached.

---

## 8. The recommendation, and it is a human's call

**Do not adopt this before G2.** Three reasons, in order:

1. **The measured benefit does not justify the cost.** 1.16x on simulations per
   valid design, against invalidating the 8.73 % random-search baseline, the
   +8.950669 reward ceiling, and every arm of a benchmark that has not yet been
   run. `NEXT_STEPS.md` §0's judgement — *"do not add scope before G2"* — points
   the same way.
2. **The motivating mechanism is measured false.** G44 conditional on
   simulating is unchanged. The argument for adopting would have to be made on
   axis conditioning instead, and **this experiment does not test conditioning
   at all** — it samples, it does not search. A policy-gradient comparison is a
   different experiment.
3. **The timing is the one thing in its favour, and it is real.** The baselines
   sweep has NOT run. If this is ever going to be adopted, doing it before the
   sweep is the only moment it is free; afterwards it costs a 12-hour re-run.
   So the decision has a deadline even though the change does not.

**What to keep regardless:** the table itself is reusable and cheap, and it is
the natural input to `BASELINES.md` §12 item 1 — re-fitting the pre-screen at
benchmark conditions. That item's stated first mechanism is that the gm/I_D
model assumes `I_D = i_bias/2` where the real mirror delivers **4-8 % less**;
`solve_bias` takes `mirror_efficiency` as an explicit argument for exactly that,
defaulting to the ideal so the deficit is measured rather than assumed.

**The cheapest next experiment, if anyone wants to push this further:** put
`experiments/prescreen.py` in front of the device arm and re-run §5.1. That
makes the free-rejection comparison fair, costs one afternoon, and would settle
whether the map's 89.40 % is worth anything the pre-screen does not already
deliver at 61.7 %.
