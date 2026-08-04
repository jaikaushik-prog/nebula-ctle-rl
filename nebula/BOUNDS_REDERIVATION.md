# Bounds re-derivation on the corrected 1.8 V SKY130 bias

**Date:** 2026-08-04 (session 9d) · **Simulator:** ngspice 41, trimmed SKY130
library (G36) · **All numbers TT / 27 °C unless stated.**

This closes the `>>> START HERE <<<` item in HANDOFF §8. Session 9c found the
G1 operating point mis-biased at gm/I_D = 1.7 with its sources 0.44 V below
ground, which invalidated (a) the parameter bounds in
`common/params.py::BOUNDS` and (b) the 5.3 % S3 random-search yield measured
inside them. Both are re-derived here on the corrected point, together with
three prior conclusions that the re-derivation overturns.

**Read the headline first: [§4](#4-the-coupling-claim-does-not-survive-measurement)
falsifies the sentence this project has been building its argument around.**
It is a real result, it is cheap to state honestly, and it needs a decision
before the abstract (due 6 Aug).

Everything below is reproducible:

```
python -m nebula.experiments.s3_yield --n 2000 --box-scan
python -m pytest nebula/tests/test_sky130_runner.py -q
```

---

## 0. Summary of what changed

| # | Prior belief | Measured | Status |
|---|---|---|---|
| 1 | Available swing = `2·I_tail·RL` = 1.2 Vpp | 1.43 Vpp linear, 2.28 Vpp ceiling | **understated ~2×** |
| 2 | Compression is headroom-limited | Pair still saturated far past the 1 dB point | **wrong mechanism** |
| 3 | All twelve S3 designs compress at 3 dB loss | True at fixed boost; 1.22× at matched boost | **partly an artifact** |
| 4 | S3 is a coupled constraint → 5.3 % yield | Coupling factor **1.04×** — independent | **falsified** |
| 5 | `nf` multiplies effective width | `nf` splits W into fingers; ±10 % on gm | **wrong** |
| 6 | A higher-voltage device would buy swing | +12 % swing, loses S3 entirely | **rejected** |

Tests: **407 → 430** (`nebula/tests/test_sky130_runner.py`, 23 tests, of which
3 need the simulator and skip cleanly without it).

---

## 1. The measured output swing (`2·I·RL` was wrong twice)

Session 9c's compression verdict rested on *"available differential swing =
2·IT·RL = 1.2 Vpp"*. That number is wrong in two independent ways, and the
second is why it had to be measured rather than corrected.

**(a) It is a peak, not a peak-to-peak.** Full steering drives one branch to
`2·I` and the other to zero, so the differential output reaches `±2·I·RL` and
the peak-to-peak span is `4·I·RL` = **2.4 Vpp**, not 1.2. A factor of two, in
exactly the place `HANDOFF` G18 warns about.

**(b) It is a steering limit, and steering may not be what binds.** The
output can only fall until the pair leaves saturation, which is a
supply-headroom property that the formula knows nothing about. Which limit
binds first is a question about the operating point.

So `device/sky130_runner.py::swing_limits` measures all three off a DC
transfer curve (`.dc` sweep of the differential input, 401 points, +0.05 s per
evaluation). At the corrected point — W=40 L=0.15 nf=4, 1.5 mA/side, VCM 1.25,
VDD 1.8, Rs=200 Cs=1.6 p RL=400 CL=100 f:

| Limit | `|vid|` | `|vod|` | Differential Vpp |
|---|---|---|---|
| **1 dB gain compression** (the honest linear swing) | 412 mV | 713 mV | **1427** |
| Input pair leaves saturation | 704 mV | 1080 mV | 2161 |
| Current steering (5 % of I left) | 800 mV | 1141 mV | 2281 |
| `4·I·RL` textbook ceiling | — | — | 2400 |
| *what session 9c used* | — | — | *1200* |

DC differential gain 1.789 V/V (5.05 dB), matching 9c's +5.1 dB.

**The mechanism is current steering, not headroom.** At the 1 dB point both
devices are still comfortably saturated — `vds` 1.29 V against `vdsat`
0.079 V. The output node has ~0.74 V of downward headroom and uses ~0.36 V of
it. Raising VDD therefore buys almost nothing here (confirmed independently in
§3), and the lever is the degenerated pair's steering range, i.e. `I_tail`
and `Rs`.

`vout_swing_v` in `DeviceResult` should carry the **1 dB number**, and
`measured_swing_pp_v()` returns `None` rather than falling back to `4·I·RL`
when the sweep did not reach compression — substituting a computed ceiling for
an unmeasured linear limit is the substitution this whole exercise is about.

## 2. Fixed-boost vs matched-boost pairing

S3 says the peaking is **tunable** 3–12 dB and S2 says the knobs are Rs and
Cs. Session 9c evaluated twelve *fixed* designs against all five channel-loss
points, which is not how a tunable equaliser is operated: at 3 dB of loss you
select the 3 dB setting, not the 10 dB one.

Holding the corrected device fixed and sweeping only (Rs, Cs) over an 11×6
grid gives 11 settings that meet S3, spanning 3.30–11.99 dB at 1.26–2.40 GHz —
i.e. the tuning range S3 asks for is genuinely reachable on one device.

**Fixed boost** — every S3-meeting setting against every loss point:

| Channel loss | settings compressing |
|---|---|
| 3 dB | **11 / 11** |
| 5 dB | 6 / 11 |
| 7 / 9 / 12 dB | 1 / 11 |

**Matched boost** — each loss point uses the setting sized for its tilt
(tilt = loss − 1 dB DC loss, floored at S3's 3 dB minimum):

| Loss | target | chosen | peaking | need | have | ratio | |
|---|---|---|---|---|---|---|---|
| 3 dB | 3.0 dB | Rs 150, Cs 1.6 p | 3.30 dB | 1689 mVpp | 1389 | **1.22** | compresses |
| 5 dB | 4.0 dB | Rs 150, Cs 3.2 p | 4.23 dB | 1442 | 1389 | **1.04** | marginal |
| 7 dB | 6.0 dB | Rs 200, Cs 3.2 p | 5.53 dB | 1150 | 1427 | 0.81 | ok |
| 9 dB | 8.0 dB | Rs 300, Cs 3.2 p | 7.65 dB | 916 | 1459 | 0.63 | ok |
| 12 dB | 11.0 dB | Rs 600, Cs 1.6 p | 11.21 dB | 619 | 1347 | 0.46 | ok |

So the pairing **was** an artifact, but only partly: matched boost shrinks the
problem from "every design compresses at low loss, by up to 1.9×" to "the two
lowest-loss points compress, by 1.22× and 1.04×". Compression is real and it
is localised at the low-loss end. It is not the project-defining constraint
9c made it.

> **The larger caveat, and it dominates both tables.** The verdict depends
> entirely on which convention supplies the input amplitude. The table above
> uses 9c's — Nyquist content in, Nyquist gain out. Under the more
> conservative reading in `link/calibration.py` C3 — a long run of identical
> bits arrives at the **DC-loss-attenuated** amplitude and the CTLE's step
> response overshoots to roughly the **peak** gain — **11 / 11 settings
> compress at every loss point**, because `CHANNEL_DC_LOSS_DB` is a fixed
> 1.0 dB placeholder that does not move with the sweep. That placeholder has
> no measured provenance (`link/config.py` says so). **Right now a
> made-up constant, not the circuit, decides the compression verdict.** This
> is the strongest argument yet for HANDOFF §8 item 1, a real `.s4p` channel.

## 3. A higher-voltage device does not help

Tested: `sky130_fd_pr__nfet_g5v0d10v5` (thick oxide, 5 V gate) at VDD = 3.3 V,
against the full SKY130 library. Six sizings, VCM 1.4–2.0, I 0.5–1.5 mA/side.

**Rejected, and not for the expected reason.** The model bins give this family
a **minimum channel length of 1.0 µm** against 0.15 µm for `nfet_01v8`, and
f_T falls roughly as 1/L². At 2.5 GHz Nyquist that is decisive:

- best peaking achieved **2.66 dB** — below S3's 3 dB floor — at 1.32–1.38 GHz;
- pushing RL to 1200 Ω for gain moves the peak to **0.398 GHz** and drives the
  Nyquist boost to **−5.14 dB**: worse than a wire where the data lives. This
  is CLAUDEwa §3's reading-(a)-vs-(b) counterexample reproduced on a second
  device family, which is worth a sentence in the report;
- gm/I_D sticks at 3.5 because W is bin-capped at 100 µm and `nf` does not
  multiply width (§5);
- swing improves only **+12 %** (1599 vs 1427 mVpp) — consistent with §1: the
  limit is steering, not headroom, so more supply buys almost nothing;
- power rises 5.4 → 9.9 mW at the same current.

Thirty minutes well spent: it removes a plausible-sounding option permanently,
with a measured reason.

## 4. The coupling claim does not survive measurement

This is the important one.

The project's central argument, quoted from HANDOFF §6, is:

> *S3 requires hitting a peaking value AND a peak-frequency window
> simultaneously, and that target couples gm, Rs, Cs, RL and CL. No
> axis-aligned box … can exploit a coupled constraint — which is why random
> search inside well-chosen bounds lands only 5.3 % of the time. That is the
> argument for a learned policy, and it is the strongest single sentence
> available for the abstract.*

A bare percentage cannot support that claim, because it depends entirely on
how wide the box was drawn. The box-independent form is to decompose S3 into
its two conditions and compare the joint against the product of the marginals:

```
A: peaking in 3-12 dB          B: f_peak in 1.25-2.5 GHz
coupling factor = P(A)·P(B) / P(A and B)
```

If the conditions fight each other, the joint falls below the product and the
factor exceeds 1. 2000 Latin-hypercube samples per box, three box widths:

| box width | P(A) | P(B) | P(A)·P(B) | P(A and B) | **coupling** |
|---|---|---|---|---|---|
| ×0.6 | 69.40 % | 24.95 % | 17.32 % | 17.25 % | **1.00×** |
| ×1.0 (proposed) | 48.47 % | 16.03 % | 7.77 % | 8.73 % | **0.89×** |
| ×1.5 | 35.04 % | 8.01 % | 2.81 % | 3.13 % | **0.90×** |

Designs with **no peak at all** fail A and B together, which associates the
two conditions for a reason unrelated to the claim. Re-measured on the subset
that produces a genuine interior maximum:

| box width | P(A\|peak) | P(B\|peak) | product | joint | **coupling** |
|---|---|---|---|---|---|
| ×0.6 | — | — | — | — | 1.00× |
| ×1.0 | 58.05 % | 18.69 % | 10.85 % | 10.46 % | **1.04×** |
| ×1.5 | 44.73 % | 9.45 % | 4.23 % | 4.00 % | **1.06×** |

**The two S3 conditions are independent to measurement precision.** There is
no coupling penalty. The joint yield is low simply because one of the
marginals is low — `f_peak` lands inside the S3 window only 16 % of the time —
and multiplying two unremarkable probabilities gives an unremarkable product.
The raw yield moves 17 % → 8.7 % → 3.1 % across box widths (a 5.5× swing)
while the coupling factor stays inside 1.00–1.06, which is exactly the
box-independence the statistic was built to provide. It is stable, and what it
stably reports is *no effect*.

### What this does and does not mean

- It does **not** mean RL is the wrong approach.
- It **does** mean the sentence above must not appear in the abstract, the
  report or the slides. It is not supported by our own measurement, and a
  judge who asks "how do you know the constraint is coupled?" would get a
  number that refutes it.
- The honest replacement is 8.73 % as a **random-search baseline** — a fact,
  not a mechanism. Random search needs ~8 samples per hit at TT.

### Candidate arguments that are still standing (none yet measured)

1. **Tunability.** S3 wants *any* point in 3–12 dB on demand. Random search
   finds *a* design; it does not give a map from requested spec to sizing.
   That is precisely the spec-conditioned policy in CLAUDEwa §7, and it is a
   task random search cannot perform at all — a much stronger framing than a
   hit rate. **Untested.**
2. **S9, the 45 corners.** Everything above is TT/27 °C. The corner-robust
   yield is the number that matters and is unmeasured. If it collapses, the
   argument is there.
3. **The full conjunction.** S3 ∧ S8 ∧ compression ∧ corners, not S3 alone.
4. **Cost per hit**, honestly compared against Bayesian optimisation — which
   CLAUDEwa §12 already warns will be the first thing a judge asks about.

**This needs a human decision before the abstract.** Recommendation: lead with
(1), quote 8.73 % as a baseline rather than as evidence of coupling, and
measure (2) next — it is the cheapest of the four and the most likely to
produce a real constraint.

## 5. `nf` is not a width multiplier on SKY130

`BOUNDS["nf_in"]`'s provenance says *"1-32 multiplies effective W"*. That is
true of the generic-BSIM4 netlist, which writes `m={NF}`, and false of the
PDK subckt, where **W is the total device width and `nf` only splits it into
fingers**. Measured at W=40, 1.5 mA/side:

| nf | 1 | 2 | 4 | 8 | 16 | 32 |
|---|---|---|---|---|---|---|
| gm (mS) | 14.22 | 13.68 | 12.62 | 13.12 | 12.29 | 11.79 |

±10 %, non-monotonic — a parasitic effect. Two of the twelve action-space
dimensions are therefore near-dead **and non-monotonic**, which is worse than
dead for a policy gradient. Extra width has to come from W (bin-capped at
100 µm) or from a device multiplier, not from `nf`.

## 6. The proposed box

**Not written into `common/params.py`.** CLAUDEwa §8 rule 6 and G17 reserve
parameter ranges for a human. This is the proposal; every edge is traceable to
a measurement in `nebula/experiments/s3_yield.py::PROPOSED_BOX`, which carries
the full provenance strings. Lengths are SI metres (as everywhere else in the
repo); `SizingPoint.from_params` performs the single conversion to the microns
the netlist needs, and halves `i_bias` across the two sinks.

| param | lo | hi | log | why this edge |
|---|---|---|---|---|
| `w_in` | 20 µm | 100 µm | no | gm/I_D 5.62 → 14.36 across it; ceiling is the SKY130 W bin limit (no model above); floor is where v(s1) still clears +0.25 V |
| `l_in` | 0.15 µm | 1.0 µm | yes | 0.15 µm is the minimum L bin; at 1.0 µm peaking is 2.37 dB, already below S3 |
| `nf_in` | 1 | 8 | no | near-dead (§5); narrowed from 1–32 |
| `i_bias` (total) | 0.5 mA | 8.0 mA | yes | ceiling = S6 at 1.8 V (8 mA × 1.8 V = 14.4 mW) |
| `rs` | 50 Ω | 1000 Ω | yes | Rs 50 → 0.08 dB, 400 → 8.54 dB, 800 → 13.25 dB (through S3's ceiling) |
| `cs` | 100 fF | 10 pF | yes | ≤200 fF gives no peak at all; 6.4 pF puts f_peak at 1.05 GHz |
| `rl` | 50 Ω | 800 Ω | yes | RL 50 → f_peak 5.75 GHz; RL 1000 takes the pair out of saturation |
| `cl` | 10 fF | 500 fF | yes | **6× tighter than the 1.2 V box**: 400 fF already drives the Nyquist boost negative |
| `vcm_in` | 1.1 V | 1.6 V | no | v(s1) tracks VCM ~1:1 at ~12 mS gm cost over the whole range |

**Three parameters are deliberately absent.** `w_tail`, `l_tail`, `nf_tail`
cannot be derived from anything, because **the tail is still two ideal current
sinks** — no simulation in this project has ever contained a tail transistor.
Inventing ranges for a device that does not exist is what rule 6 forbids.
`param_space()` will keep raising until the G1 tail item lands, which is the
designed behaviour (G17: there is no half-populated state).

### Yield inside it

2000 samples: 110 rejected free by the 1.8 V headroom pre-check, 1890
simulated, 0 non-convergences.

| | count | rate |
|---|---|---|
| S3 (peaking **and** f_peak) | 165 | **8.73 %** |
| S3 also with positive Nyquist boost | 165 | 8.73 % |
| S5 noise < 1.5 mV<sub>rms</sub> | 1890 | **100 %** |
| S6 power < 15 mW | 1890 | **100 %** |
| input pair saturated | 1872 | 99.05 % |

S5 and S6 are free in this box, as they were at 1.2 V. Every S3-meeting sample
also has positive Nyquist boost, so at 1.8 V the §3 reading-(a)/(b) ambiguity
happens not to bite inside this box — worth stating, since it did bite on the
smoke test and on the 3.3 V device.

The S3-meeting points span essentially the full width of every bound, so
nothing is obviously trimmable on this evidence — unlike the 1.2 V box, where
`cl` was cut 5 p → 3 p on exactly this test.

---

## 7. What to do next

1. **Decide the argument** (§4). Blocks the abstract, due 6 Aug.
2. **Approve or amend the box** (§6), then it goes into `params.py`.
3. **Measure the corner-robust yield** — the same 2000 samples over the S9
   grid. Cheapest path to a real constraint, and it is the claimed
   contribution #1 in CLAUDEwa §7.
4. **Add the tail transistor**, which unblocks the three missing bounds.
5. **Replace `CHANNEL_DC_LOSS_DB`** with a measured channel (§2's caveat).
