# `cl`: what the CTLE output actually has to drive

**Date:** 2026-08-06 (session 12) · **Simulator:** ngspice 41, trimmed SKY130
library (G36) · **180 SPICE runs, 16 s** · All numbers VDD = 1.8 V.

Closes `CL_SENSITIVITY.md` §6's open item — *"`cl` is the one parameter here
that is not really free… pinning it at whatever value maximises S3 yield, if
that value is not physically justifiable, is choosing the answer. The honest
version fixes it from an estimate of the following stage's input capacitance"*
— and replaces `S9_YIELD.md`'s assumption #1.

**The answer:**

| | value | what sets it |
|---|---|---|
| **`cl_lo`** | **13.64 fF** | smallest defensible summer + slicer, at the lightest-loading corner, abutted routing |
| `cl_mid` | 32.63 fF | geometric mean — a screen point, not a claim |
| **`cl_hi`** | **78.04 fF** | largest defensible summer + slicer, at the heaviest-loading corner, lane-pitch routing |
| ratio | **5.72×** (2.52 octaves) | |

Three things fall out of it, in order of how much they matter:

1. **Every corner number this project has published was measured at a load
   1.92× above the top of the physically derived range.** The 150 fF pin sits
   outside [13.6, 78.0] fF entirely. It was never presented as physical — it
   was the best of five values tested for S3 yield — but it has been the
   operating assumption behind 13.49 % / 8.20 % / 8.10 %.
2. **The load spread is 2.52 octaves and S3's f_peak window is 1.00 octave.**
   **Measured consequence (session 12b, `S9_YIELD.md` §8): the corner-robust
   yield falls from 8.20 % to 0.05 % — one design in 1890.** The load range
   costs 99.4 % of the nominal winners where the whole 45-corner PVT set costs
   39 %, so **the load, not the corner set, is now the binding constraint**.
   Prediction and outcome are in `PREDICTIONS.md` entry 1: the number held, the
   reasoning behind it did not.
3. **`@m[cgg]` — the obvious way to measure a gate load — understates it by
   1.9–2.7×** on these devices, silently, because it excludes the overlap
   capacitance and the Miller multiplication of C_gd. New gotcha **G50**.

Reproduce:

```
python -m nebula.experiments.cl_range                # 180 runs, ~16 s
python -m nebula.experiments.cl_range --from-csv     # no simulator
python -m pytest nebula/tests/test_cap_probe.py nebula/tests/test_cl_range.py -q
```

`common/params.py` is untouched. **This is a proposal** — CLAUDEwa §8 rule 6
reserves bound changes for a human, and §8 below is what is being proposed.

---

## 0. Why `cl` is neither a knob nor a constant

The action space in CLAUDEwa §5.2 lists `CL` alongside `RL` as a "Load"
parameter. It does not belong there. `RL` is a resistor the designer draws;
`cl` is the input capacitance of whatever the CTLE is wired to, plus the wire.
Nobody *chooses* it, so it is not a design variable — `CL_SENSITIVITY.md` (G42)
measured that searching over it actively **lowers** the yield, which is what a
non-informative dimension does.

But it is not a constant either. It is not known to one value: it depends on
how the following stages are sized, and that decision has not been made. It is
**a context variable with a range** — the same epistemic status as
temperature, and handled the same way: derive the range, then screen across it.

That is a human decision, taken for this session. Its main weakness is stated
in §9 and a reader should read that before quoting the yield that follows.

---

## 1. What hangs on the node

S2 fixes the topology: *1-stage CTLE with source degeneration + 1-tap DFE*. So
the CTLE's differential output drives, per side:

* the **1-tap DFE summer** input pair — the stage at whose output the tap
  current is subtracted;
* the **slicer** input pair — the decision element.

Two gates per output node, plus the wire that reaches them. Both are sized at
**L = 0.15 µm**, the minimum SKY130 `nfet_01v8` bin: both are speed-critical,
neither needs output resistance, and f_T falls as 1/L² (G39).

### The sizes, and why each one is where it is

| stage | W | nf | I/side | R_L | measured \|A\| (TT) | 3σ input offset | why this size |
|---|---|---|---|---|---|---|---|
| `summer_min` | 4 µm | 2 | 0.5 mA | 800 Ω | 1.34 | 18.4 mV | smallest that still **amplifies** |
| `summer_max` | 12 µm | 6 | 1.0 mA | 800 Ω | 3.00 | 10.6 mV | built for gain ≈ 3 |
| `slicer_min` | 4 µm | 2 | 0.5 mA | 800 Ω | 1.34 | 18.4 mV | offset-**trimmed** receiver |
| `slicer_max` | 16 µm | 8 | 1.0 mA | 800 Ω | 3.52 | 9.2 mV | **untrimmed**, matching-limited |

**The lower edge is set by a gate, not by taste.** `MIN_STAGE_GAIN = 1.0`: a
summer or slicer front end that attenuates is worse than the wire it replaced,
because it hands the next element a smaller eye plus its own noise and offset.
This is not decoration — the first sizing tried here was 4 µm at 0.4 mA into
500 Ω and measured **|A| = 0.85 at TT**; the second was 0.5 mA into 700 Ω and
measured **0.95 at ss/125 °C**. 0.5 mA into 800 Ω is the smallest of the three
that clears unity at *every* corner (1.07 at ss/125 °C). The gate runs on every
sweep and the run prints PASS or FAIL.

**The upper edge is set by the offset budget.** Pelgrom on SKY130's own
mismatch card gives σ(V_th) = A_VT/√(W·L) with **A_VT = 3.356 mV·µm**, so a
pair's input-referred offset is √2·A_VT/√(W·L):

* at W = 4 µm the 3σ offset is **18.4 mV** — 18 % of S8's 100 mV eye. Usable
  only behind an offset-trim DAC, which is standard in a SerDes slicer and is
  therefore a real design option, not a cheat;
* at W = 16 µm it is **9.2 mV**, under a tenth of the eye, i.e. usable
  untrimmed. Past this, matching improves only as √W: another 2× of width buys
  30 % of offset for 100 % of load. So 16 µm is the largest the pair has any
  reason to be.

`summer_min` and `slicer_min` come out **identical**, and are deliberately not
perturbed to look different: two stages whose minimum size is set by the same
gm floor land on the same device.

> **A_VT's units are an inference, not a measurement.** The card reads
> `vth0 = 0.519 + AGAUSS(0,1,1)*(3.356e-3/sqrt(l*w*mult))`. Reading `l`,`w` as
> the instance values in **microns** (the netlist's units under
> `.option scale=1.0u`) gives 3.356 mV·µm. Reading them as metres gives
> σ(V_th) = 3 kV for an 8 × 0.15 µm device, which is not a number about a
> transistor. Only the *sizing sketch* depends on this; **no measured
> capacitance does.**

---

## 2. The measurement: not `@m[cgg]` — G50

BSIM4 exposes `@m[cgg]`, and it is the obvious probe. It is the wrong one, by
about 2×, and it is wrong in the way this project keeps getting hurt by: a
plausible number of roughly the right size. It reports the **intrinsic**
gate charge derivative and leaves out two real terms:

1. **Gate overlap.** SKY130's card carries `cgso = cgdo = 2.449e-10 F/m` at TT
   — 3.9 fF per side on a 16 µm device, which the CTLE output charges just the
   same.
2. **Miller multiplication of C_gd** by the loading stage's own gain. The
   *intrinsic* C_gd of a saturated device really is ~0 (1.8e-17 F measured),
   which is exactly what makes the trap work — but the *overlap* C_gd is not,
   and it gets multiplied by (1 + |A|).

So the load is measured the way the CTLE sees it. The loading pair is driven
**differentially** through zero-volt ammeters and the AC current the driver has
to supply into one gate is read at 1.25 GHz and 2.5 GHz:

```
C_in(per side) = Im{ i(Vgp) } / ( 2·π·f · |v_gate| )
```

| stage (TT/27 °C/V_out 1.2 V) | `@m[cgg]` | **measured C_in** | ratio |
|---|---|---|---|
| `summer_min` | 3.27 fF | **6.56 fF** | 2.00× |
| `summer_max` | 9.68 fF | **24.43 fF** | 2.52× |
| `slicer_min` | 3.27 fF | **6.56 fF** | 2.00× |
| `slicer_max` | 12.71 fF | **34.34 fF** | 2.70× |

The ratio grows with the stage's gain, which is the signature of the Miller
term rather than of a constant offset. At `slicer_max`, **52 % of the load is
gate-drain overlap × (1 + |A|)**.

### The measurement is cross-checked against the primitives, and the check can fail

An AC current is not self-evidently a capacitance, so it is reconstructed from
parsed `.op` primitives and the model card's own overlap constants:

```
C_in = (|cgs| + Cgso·W) + |cgb| + (|cgd| + Cgdo·W)·(1 + |A|)
```

At `slicer_max`/TT: (9.569 + 3.919) + 3.158 + (0.018 + 3.919)·4.516 =
**34.42 fF** against **34.34 fF** measured — 0.23 %. Across all 180 runs the
median disagreement is **1.02 %** and the worst is **2.20 %**.

`sanity_check_load()` **rejects** any point where the device is out of
saturation, the load is not capacitive (G/B > 0.10), or the reconstruction
disagrees by more than 5 %. **0 of 180 rejected.** A test corrupts the AC
number by 1.5× and requires the check to go red, so it is a gate and not a
comment (§8 rule 10).

Two smaller results from the same runs:

* **Capacitance dispersion across S3's window is 0.17 %.** Modelling the load
  as a single lumped `cl` in the CTLE netlist is therefore honest over
  1.25–2.5 GHz, which had been assumed and is now measured.
* The overlap constants are **read out of the PDK model file**, never
  re-declared in Python (rule 9), and the reader asserts all 180 model bins
  agree on the parameter before using it — `cgso` does, `u0` does not, and
  asking for `u0` raises.

---

## 3. What moves the load, and what does not

Measured over 5 process corners × 3 temperatures × 3 CTLE output common modes,
per stage:

| axis | how much it moves the load |
|---|---|
| **which stages, and how big** | **5.9×** (5.84 → 37.29 fF) |
| process corner | 1.16× |
| temperature (0 → 125 °C) | 1.08× |
| CTLE output common mode (1.2 → 1.6 V) | 1.04× |

**The sizing sketch dominates by a factor of five.** That is the honest
headline of this document: the range is wide because the following stage has
not been designed, not because silicon varies. It also says where effort would
buy accuracy — designing the slicer would narrow `cl` far more than any amount
of corner analysis.

### The corner that loads the node most is the one with the *least* gm

| corner | mean C_in (`slicer_max`) | `@m[cgg]` | mean gm |
|---|---|---|---|
| `fs` | **35.49 fF** | 14.82 fF | 5.35 mS |
| `ss` | 34.90 fF | 14.01 fF | 5.32 mS |
| `tt` | 33.26 fF | 12.70 fF | 5.62 mS |
| `ff` | 31.12 fF | 11.56 fF | 5.85 mS |
| `sf` | **30.60 fF** | 10.92 fF | 5.84 mS |

The C_in ordering matches the `cgg` ordering exactly and is the **inverse** of
the gm ordering. So the corner that is worst for the *load* is not the corner
that is worst for the *device* — the same shape of mistake G46 had to correct
once already for S3, and worth stating before somebody screens `cl` and gm at
"the" worst corner.

(Note also that for the nfet, `sf` behaves like the fast corner and `fs` like
the slow one — the label ordering is not (nfet, pfet). Measured, not assumed.)

One more, and it is a small piece of good news: the **C_in spread across
corners (1.16×) is smaller than the intrinsic `cgg` spread (1.36×)**, because
roughly half the load is overlap capacitance and `cgso` varies only ±1.7 %
across corners. The load is more corner-stable than the transistor is.

---

## 4. The routing allowance

Two factors, and they are not equally solid.

**Capacitance per unit length — derived from PDK data.** SKY130 ships
`sky130_fd_pr__cap_vpp_01p8x01p8_m1m2_noshield`, an interdigitated m1/m2 finger
capacitor whose subckt states everything needed:

```
ctot_a = 7.833e-16 F      rat_m1 = 0.387   rm11 ... r = {22*rm1}   (22 squares)
                          rat_m2 = 0.596   rm21 ... r = {28*rm2}   (28 squares)
```

so capacitance per micron of finger = rat · ctot / (n_squares · width):

* **m1: 0.0984 fF/µm**  ·  **m2: 0.1191 fF/µm**

Every number is parsed out of the PDK file at run time; the function raises if
the file's structure changes rather than falling back on a remembered value.

> **The one declared input.** Converting squares to microns needs the metal
> width. This install carries `libs.tech/ngspice` and
> `libs.ref/sky130_fd_pr/spice` only — no tech LEF, no magic techfile — so
> **0.14 µm is taken from the SKY130 design rules and is declared, not
> measured.** It is a divisor: if the fingers are drawn wider than minimum, the
> real fF/µm is *lower* and both edges move down.
>
> Two further reasons this is an **upper bound** on a routing wire, which is
> why it is honest to use it for the upper edge: a finger capacitor has a
> neighbour at minimum spacing on *both* sides, which routing normally does
> not; and `ctot_a` includes the m1-to-m2 coupling that makes it a capacitor at
> all.

**Wire length — stated, not measured.** There is no layout.

| edge | length | why | fF/µm | total |
|---|---|---|---|---|
| lo | 20 µm | summer and slicer abutted to the CTLE, which is how a bandwidth-critical node is laid out when nothing forces otherwise. The CTLE's own passives set the floor: C_s is 0.1–10 pF and R_L is 50–800 Ω, so the output node cannot be shorter than the height of that array. | 0.0984 | **1.97 fF** |
| hi | 120 µm | the following stages displaced by roughly a lane pitch — a clock distribution or an offset-trim DAC between them. Past this a designer buffers the node rather than driving it, so it is a ceiling on the plausible rather than on the possible. | 0.1191 | **14.29 fF** |

Routing is **14 %** of `cl_lo` and **18 %** of `cl_hi`. Even doubling the whole
allowance moves `cl_hi` by 18 % — a fifth of one octave — against a range that
is 2.52 octaves wide. **The routing assumption is not what makes the range
wide.**

---

## 5. The range, with per-edge provenance

```
cl_lo  =  11.67 fF device  +  1.97 fF routing  =  13.64 fF
cl_mid =  geometric mean                       =  32.63 fF
cl_hi  =  63.74 fF device  + 14.29 fF routing  =  78.04 fF
                                        ratio  =   5.72x  (2.52 octaves)
```

| edge | term | value | witness |
|---|---|---|---|
| **lo** | `summer_min` | 5.84 fF | `sf` / 125 °C / V_out 1.6 V |
| | `slicer_min` | 5.84 fF | `sf` / 125 °C / V_out 1.6 V |
| | routing | 1.97 fF | 20 µm × 0.0984 fF/µm |
| **hi** | `summer_max` | 26.46 fF | `fs` / 0 °C / V_out 1.2 V |
| | `slicer_max` | 37.29 fF | `fs` / 0 °C / V_out 1.2 V |
| | routing | 14.29 fF | 120 µm × 0.1191 fF/µm |

Each stage's extreme is taken **independently**: they are different devices and
nothing requires their extremes to fall at the same corner, so pairing them
corner-by-corner would produce a narrower range than the measurements support.
(In this sweep they happen to coincide, which is a fact about the data and not
a property of the method.)

`cl_mid` is the **geometric** mean because f_p2 = 1/(2π·R_L·C_L) is log-linear
in `cl` and `PROPOSED_BOX` scales `cl` logarithmically. The arithmetic mean
would be 45.8 fF — a third of an octave off centre.

### What this range does to the CTLE

f_p2 = 1/(2π·R_L·C_L), over `PROPOSED_BOX`'s R_L bound:

| | R_L = 50 Ω | R_L = 400 Ω | R_L = 800 Ω |
|---|---|---|---|
| at `cl_lo` | 233 GHz | 29.2 GHz | 14.6 GHz |
| at `cl_hi` | 40.8 GHz | 5.10 GHz | **2.55 GHz** |

At the high-R_L end the load pole crosses the top edge of S3's window as `cl`
moves from one end of its range to the other. **That is the mechanism behind
the next experiment.**

---

## 6. How this compares with what has been assumed

| | value | status |
|---|---|---|
| `S9_YIELD.md` assumption 1 | 150 fF | **1.92× above `cl_hi`** |
| `CL_SENSITIVITY.md` proposal | 150–250 fF | 1.9–3.2× above `cl_hi` |
| `PROPOSED_BOX["cl"]` search bound | 10–500 fF | contains the derived range; its top 6.4× is unreachable |
| **derived here** | **13.6–78.0 fF** | |

The 150 fF pin is not a small error. It is roughly a **2.4-octave** move of
f_p2 relative to `cl_lo`, and `CL_SENSITIVITY.md` already measured that the S3
yield swings from 8.78 % to 13.54 % over just 50 → 150 fF. Every corner number
this project has published sits at a load the following stage cannot plausibly
present.

**A coincidence worth naming rather than leaving to be discovered.** A
half-rate front end — two data slicers and two edge slicers on the node instead
of one slicer, which is what a real 5 Gbps receiver with a CDR looks like —
gives `cl_hi` = **141.8 fF**, essentially the 150 fF that was pinned. So the
pinned value was not absurd; it was the right number **for a topology S2 does
not describe.** It is reported here and deliberately **not** folded into the
bound, because changing the topology is a human decision (§8 rule 5).

For scale: +6 gates (quarter-rate) gives `cl_hi` = 269 fF.

---

## 7. Two findings that are not about `cl`

**(a) The loading stage needs a CTLE output common mode above ~1.15 V.** The
probe sweeps V_out ∈ {1.2, 1.4, 1.6} V and the loading pair's source node sits
at +0.16 V at the bottom of that. Below ~1.15 V the source goes negative — the
exact failure session 9c found for the CTLE itself, which no real tail can
provide. But `headroom_ok_1v8()` only requires the CTLE's own output to clear
**0.5 V**, so a large part of `PROPOSED_BOX` produces a CTLE whose output DC
cannot bias the stage it drives. Either the box needs a tighter floor on v_out,
or the receiver needs AC coupling or a level shift between the two. **Not
solved here; recorded because nothing in the project currently notices it.**

**(b) `cl` is partly designable after all, in one direction only.** What loads
the node is `C_load(context) + C_added(design)`: a designer who needs f_p2
lower can always *add* capacitance, but cannot remove what the next stage
presents. So the derived range is a **floor** that the design can move up from,
which — if the next experiment finds the spread unmanageable — is the obvious
place to look for a fix. Stated as an observation for a human; nothing in this
session acts on it.

---

## 8. Proposal (NOT written into `params.py`)

CLAUDEwa §8 rule 6 and G17 reserve parameter ranges for a human. Proposed:

> 1. **Remove `cl` from the action space** (already proposed by
>    `CL_SENSITIVITY.md` §6 and G42, on the independent ground that searching
>    it lowers the yield).
> 2. **Replace the 150 fF pin with the context range `cl ∈ [13.6, 78.0] fF`**,
>    screened at both edges like a PVT corner, with `cl_mid = 32.6 fF` in the
>    verification tier.
> 3. **Re-state every published corner number as conditional on the load**, and
>    re-run `s9_yield.py` inside this range — which is what session 12's second
>    half does.

If the half-rate reading of the topology is preferred instead, the range is
[13.6, 141.8] fF and the ratio is 10.4× rather than 5.7×. That is a **topology
decision** (§8 rule 5), not a bounds decision, and it belongs to a human.

---

## 9. What this does NOT say — read before quoting any yield

* **The range's width is dominated by a sketch, not by measurement.** The
  devices are measured; *which* devices, at *what* sizes, is engineering
  judgement written down in §1. A reader who sizes the slicer differently gets
  a different range. That is why every size carries its reasoning and why the
  answer is a range.
* **"Screen `cl` like a PVT corner" is a conservative reading, and arguably
  too conservative.** Temperature varies during operation; `cl` does not. It is
  fixed the moment the following stage is laid out, and *known* to the designer
  at that point. A design could legitimately be tuned for its actual load —
  and S3 says the peaking is **tunable** via R_s/C_s, so a real part has a knob
  that the fixed sizing points in `s9_yield.py` do not exercise. Requiring one
  fixed sizing to work at both edges of a 5.7× load range is therefore a
  **harder** question than the one silicon has to answer. It is the question
  that was asked for this session; the yield it produces should be read as a
  lower bound on what a tunable part could achieve.
* **The tail is still two ideal current sinks** — in the CTLE and in the
  probe's loading stage. This is a load measurement, so the tail matters much
  less here than in `S9_YIELD.md`, but the loading pair's bias is still
  idealised.
* **No layout exists.** The routing lengths are stated, not extracted.
* **The slicer is modelled as a resistively-loaded differential pair.** A real
  StrongARM latch is clocked, has no static current, and its Miller term
  changes through the evaluation phase. The static preamp model is a sketch
  chosen because it is the one whose capacitance is well-defined; a latch's
  input capacitance is time-varying and would need a different measurement
  entirely.
