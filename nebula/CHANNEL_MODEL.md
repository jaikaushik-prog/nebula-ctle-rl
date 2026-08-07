# CHANNEL_MODEL.md — the channel, derived instead of invented

**Session 16, 2026-08-07.** Code: `nebula/link/channel.py`, `nebula/link/tx.py`,
`nebula/link/cursors.py`. Experiment: `nebula/experiments/channel_family.py`.
Pre-registration and outcome: `nebula/PREDICTIONS.md` entry 4.

**Read §0 first.** Two of this document's numbers move a published verdict, and
one of my own pre-registered predictions is a clean miss.

---

## 0. The four sentences

1. **The invented constant is gone.** `link/config.py` carried a hard-coded
   1.0 dB "channel loss at DC" with no provenance, and
   `BOUNDS_REDERIVATION.md` §2 says in a blockquote that *that constant, not
   the circuit, decided the compression verdict*. It is **deleted, not
   re-valued**; a test greps every executable file in the tree for the symbol.
2. **A 1-tap DFE is sufficient across the whole 3–12 dB family.** The eye is
   open at all 21 members, in all three de-emphasis settings, with and without
   a CTLE. S3's top of range and S8 *can* both be met with S2's topology. But
   **only 15% of what the DFE cannot reach is in `h2`**, and **31% of it sits
   beyond 20 UI** — so "one more DFE tap" would buy very little.
3. **The mandated TX de-emphasis is worth exactly 3.5 dB of the CTLE's job**,
   so the burden across the family is **−0.5 … +8.5 dB**. The **top 3.5 dB of
   S3's tunable range is never called for**, and at 3, 4.5 and 6 dB of channel
   loss the burden is *below* S3's 3 dB floor — the minimum setting
   over-equalises.
4. **The 1.22× compression reading at 3 dB survives verbatim**, and that is not
   good news. It survives because it was computed in a convention that the
   deleted constant never touched. Measured honestly — peak distortion through
   the real pulse response — **3 dB is 1.51×, and 5 of 7 loss points
   compress**, against the old "two lowest points, by 1.22× and 1.04×".

---

## 1. Why, and where the number comes from (5a)

### The constant's own name encoded the mistake

For a lossy transmission line the insertion loss **at DC is essentially zero**:
the DC resistance of a few inches of copper is milliohms against a 50 Ω line.
What is non-zero, and what an equaliser exists to undo, is the loss at
**Nyquist**. A "channel loss at DC" of 1.0 dB was a number attached to a
quantity that is physically ~0.

So the fix is not a better value. The fix is that the low-frequency correction
the constant was standing in for is **not a channel property at all** — it is
the transmitter's specified de-emphasis (§4).

### The derivation, stated

**There is no PCIe Gen2 reference receiver to copy.** Gen1 and Gen2 specify
**transmitter de-emphasis only**, at a fixed −3.5 dB with a −6 dB option;
receiver CTLE and DFE entered the specification at **Gen3**. So the channel is
ours to define, and the question is how to define it defensibly.

Industry practice sets CTLE boost at Nyquist ≈ channel insertion loss at
Nyquist. **S3's own 3–12 dB tunable boost requirement therefore implies a
channel family spanning roughly 3–12 dB of insertion loss at 2.5 GHz.** The
specification we were given defines the channel we have to equalise. That is a
construction we can defend in September; an invented scalar is not.

This is the same reasoning `DEFAULT_LOSS_SWEEP_DB` already used for the loss
*axis*. What is new is that each point is now a **response**, not a number.

---

## 2. The model, and the half people get wrong (5b)

```
IL_dB(f) = A*sqrt(f) + B*f          A, B >= 0
|H(f)|   = 10 ** (-IL_dB(f) / 20)
```

`A·√f` is skin effect; `B·f` is dielectric loss.

### The magnitude is the easy half

The phase is where this goes wrong. **A magnitude-only response with zero phase
is non-causal**: its impulse response is symmetric about `t = 0`, so half its
energy arrives before the pulse was launched, and every ISI cursor and eye
number computed from it is finite, plausible and wrong. This is the project's
failure mode #1, and nothing raises.

Phase is built as **minimum phase**, reconstructed from `ln|H|` by the standard
real-cepstrum fold (the Hilbert transform, done by FFT):

```
c      = IFFT( ln|H| )
c_min  = c * [1, 2, 2, ..., 2, 1, 0, ..., 0]
H_min  = exp( FFT(c_min) )
```

`|H_min|` reproduces the target magnitude to 1e-10 and the phase is the unique
minimum-phase one consistent with it. No bulk propagation delay is included —
minimum phase means zero excess delay, and a pure delay is not ISI.

### The causality gate, and the number it reports

`CAUSALITY_ENERGY_THRESHOLD = 1e-6` of the impulse-response energy at `t < 0`.
**Stated before the run, and then met by lengthening the FFT buffer rather than
by moving the threshold.**

The measurement that justifies the buffer is worth more than the buffer:

| n_fft | 4096 | 8192 | 16384 | **32768** | 65536 |
|---|---|---|---|---|---|
| pre-`t<0` energy, worst member | 8.7e-05 | 1.3e-05 | 1.8e-06 | **2.5e-07** | 3.5e-08 |

A clean power law. **That is how you tell time-domain aliasing of the tail from
a broken phase reconstruction** — a broken reconstruction would sit at a floor
instead of scaling down. `DEFAULT_N_FFT = 32768` (512 UI at 64 samples/UI) is
the first power of two clearing the threshold at every member.

**Per-member causality, as measured** (5f requires this reported, not merely
asserted):

| split | 3 dB | 6 dB | 9 dB | 12 dB |
|---|---|---|---|---|
| skin-dominated | 2.1e-10 | 7.0e-09 | 5.6e-08 | **2.5e-07** |
| balanced | 1.3e-10 | 3.3e-09 | 2.3e-08 | 8.8e-08 |
| dielectric-dominated | 3.6e-11 | 7.4e-10 | 4.4e-09 | 1.6e-08 |

21/21 pass. **The control:** the same 12 dB skin-dominated magnitude with zero
phase puts **48.0% of its energy at t < 0** (−3.2 dB) and raises nothing on its
own. That is what the gate exists to catch, and it is a test
(`test_the_gate_fails_on_the_thing_it_exists_to_catch`).

### Passivity and monotonicity

`max|H| = 1.0000` and `max(ΔH) ≤ -3.5e-11` at every member — `|H(f)| ≤ 1`
everywhere and non-increasing in `f`. Both hold by construction for `A, B ≥ 0`,
which is why the old `LinkConfig` "is this a high-pass channel?" guard could be
deleted rather than ported: the question can no longer be asked.

---

## 3. Parameterisation (5c)

`ChannelModel(il_db_at_nyquist=..., skin_fraction=...)`.

**Insertion loss at Nyquist is the primary constructor argument** and a
first-class attribute. `skin_fraction` is
`r = A·√f_N / (A·√f_N + B·f_N)` at Nyquist, so `(IL, r)` gives `(A, B)` in
closed form:

```
A = r * IL / sqrt(f_N)          B = (1 - r) * IL / f_N
```

The constructed loss at 2.5 GHz reproduces the target to **≤ 1.8e-15 dB**
across all 21 members (5f's closed-form check).

### Why a scalar cannot represent a channel — measured

The family is 7 losses × 3 splits. At a **fixed** headline number the split
changes the DFE's job materially:

| IL at 2.5 GHz | residual, skin (r=0.8) | residual, dielectric (r=0.2) | ratio |
|---|---|---|---|
| 3.0 | 0.0799 | 0.0402 | **1.99×** |
| 4.5 | 0.1319 | 0.0687 | 1.92× |
| 6.0 | 0.1954 | 0.1084 | 1.80× |
| 7.5 | 0.2739 | 0.1553 | 1.76× |
| 9.0 | 0.3675 | 0.2214 | 1.66× |
| 10.5 | 0.4783 | 0.2976 | 1.61× |
| 12.0 | 0.6133 | 0.3837 | **1.60×** |

(channel only, PCIe Gen2 mandated de-emphasis; residual = ISI a 1-tap DFE
cannot reach, as a fraction of the cursor.)

**Two channels with identical loss at Nyquist differ by up to 2× in the ISI a
1-tap DFE has to survive.** `√f` spends its loss early and rolls off slowly,
leaving a long algebraic tail; `B·f` rolls off faster in-band and leaves a
shorter one. Same headline number, different problem. This is the one genuinely
reusable idea in the APCCAS paper the mentor supplied, and it is now measured
rather than asserted.

**Note the direction, which was not predicted:** the ratio is *largest at low
loss* (1.99× at 3 dB) and falls as loss rises. The pre-registered claim was
that it would be roughly constant. It is not.

### Equivalent length — reported, never used to derive (5c)

The family targets a **loss** and reports the length. Going the other way would
hide a trace geometry inside every result.

Stated stackup: **FR-4 microstrip, 10 mil trace, 50 Ω single-ended**, Dk 4.3,
tan δ 0.02, 1 oz copper, ground-return allowance ×2 on the skin term. Both
formulas are in `Stackup`'s docstring and both are hand-checked by tests:

```
alpha_d = 3.775 dB/m/GHz        alpha_c = 11.285 dB/m/sqrt(GHz)
total at 2.5 GHz = 27.28 dB/m = 0.693 dB/inch
```

| IL at 2.5 GHz | 3.0 | 4.5 | 6.0 | 7.5 | 9.0 | 10.5 | 12.0 |
|---|---|---|---|---|---|---|---|
| equivalent length, inch | 4.33 | 6.49 | 8.66 | 10.82 | 12.99 | 15.15 | **17.32** |

**Four inches to a foot and a half of FR-4.** That is a recognisable PCIe Gen2
board, which is the whole point of quoting it.

**And a result that falls out of doing it honestly:** this stackup's own
natural split at 2.5 GHz is **r = 0.654**, so the *skin-dominated* member
(r = 0.8) is closer to a homogeneous trace than the balanced one, and **no
member of the family is self-consistent** — the length implied by `A` and the
length implied by `B` differ. `EquivalentLength.self_consistent` reports that
per member rather than smoothing it over. The family is a span of *shapes*, and
only one point on the `r` axis is a single length of any one trace.

---

## 4. The transmitter is part of the link, and it is specified (5d)

PCIe Gen1/Gen2 mandate **transmitter de-emphasis** and specify no receiver
equaliser. So the CTLE is not equalising a raw channel — it is equalising a
channel plus a partially pre-equalised transmitter.

`link/tx.py` models it as the 2-tap FIR it is, `y[n] = c0·x[n] + c1·x[n−1]`,
normalised so the **transition** bit reaches full swing (which is what
`V_TX-DIFF-PP` is measured on):

```
c0 =  (1 + d)/2      c1 = -(1 - d)/2       d = 10**(de_emphasis_dB/20)

-3.5 dB:  d = 0.66834   c0 = 0.83417   c1 = -0.16583
-6.0 dB:  d = 0.50119   c0 = 0.75059   c1 = -0.24941
```

`PCIE_GEN2_TX_DIFF_PP_MIN_V` (0.8 Vpp) is **imported** from `link/config.py`,
not redeclared (rule 9). The de-emphasis anchors now live beside it, in the
same file, for the same reason.

### How much it reduces the CTLE's boost — exactly

`|H_tx|` is `d` at DC and `1` at Nyquist by construction, so the transmitter
supplies **exactly `−de_emphasis_dB` of tilt**. Not approximately:

| setting | TX tilt | CTLE burden over the 3–12 dB family |
|---|---|---|
| none (control) | 0.000 dB | **+3.0 … +12.0 dB** |
| **−3.5 dB (Gen2 mandate)** | **3.500 dB** | **−0.5 … +8.5 dB** |
| −6.0 dB (Gen2 option) | 6.000 dB | −3.0 … +6.0 dB |

**Two consequences for S3, and they point in opposite directions:**

* **The top 3.5 dB of S3's range is never called for on this family.** The
  burden never exceeds 8.5 dB; S3 asks for 12.
* **At 3, 4.5 and 6 dB of channel loss the burden is below S3's 3 dB floor** —
  −0.5, +1.0 and +2.5 dB. A CTLE pinned at its minimum setting is adding boost
  the link does not need, which is exactly the over-equalised regime that
  spills energy into the *pre*-cursor, where no DFE can reach it.

So **the useful part of S3's tunable range, for this channel family and this
mandated transmitter, is roughly 3–8.5 dB, not 3–12 dB.** That is worth knowing
before any conclusion about achievable boost, and it is a statement about the
problem, not about our sizing.

---

## 5. The decisive measurement: is a 1-tap DFE enough? (5e)

### Method

TX pulse (with de-emphasis) ⊛ channel minimum-phase impulse response, optional
CTLE, sampled at UI intervals at the phase maximising `h0`. **64 samples per
UI** internally (5e asks for ≥ 32; 64 resolves the cursor phase to 3.1 ps), 512
UI of buffer. Residual after an **ideal** 1-tap DFE:

```
residual = ( sum |h_k| over k < 0  +  sum |h_k| over k >= 2 ) / h0
```

summed over the **whole** buffer, not a truncated window. `residual ≥ 1` means
the eye is closed and **no amount of gain reopens it**, because gain scales
signal and ISI identically. That is why this is the metric: it answers the
topology question without assuming any device.

### The headline table — channel only, PCIe Gen2 mandated −3.5 dB

Cursors normalised to `h0`; eye is the worst-case vertical opening at the CTLE
input, in differential mV.

| IL | split | burden | h₋₂ | h₋₁ | h₁ | h₂ | h₃ | h₄ | residual | eye mV |
|---|---|---|---|---|---|---|---|---|---|---|
| 3.0 | skin | −0.5 | 0.0000 | 0.0000 | −0.1443 | 0.0118 | 0.0086 | 0.0062 | 0.0799 | 525.8 |
| 4.5 | skin | +1.0 | 0.0000 | 0.0000 | −0.1075 | 0.0196 | 0.0142 | 0.0102 | 0.1319 | 453.0 |
| 6.0 | skin | +2.5 | 0.0000 | 0.0009 | −0.0656 | 0.0290 | 0.0210 | 0.0150 | 0.1954 | 380.7 |
| 7.5 | skin | +4.0 | 0.0000 | 0.0042 | −0.0205 | 0.0404 | 0.0290 | 0.0208 | 0.2739 | 309.7 |
| 9.0 | skin | +5.5 | 0.0000 | 0.0072 | +0.0299 | 0.0542 | 0.0385 | 0.0277 | 0.3675 | 242.0 |
| 10.5 | skin | +7.0 | 0.0000 | 0.0090 | +0.0855 | 0.0708 | 0.0499 | 0.0359 | 0.4783 | 178.3 |
| **12.0** | **skin** | **+8.5** | 0.0000 | 0.0154 | +0.1405 | 0.0901 | 0.0629 | 0.0453 | **0.6133** | **117.9** |
| 3.0 | balanced | −0.5 | 0.0000 | 0.0000 | −0.1406 | 0.0095 | 0.0072 | 0.0051 | 0.0598 | 546.8 |
| 6.0 | balanced | +2.5 | 0.0000 | 0.0051 | −0.0525 | 0.0242 | 0.0180 | 0.0126 | 0.1523 | 412.1 |
| 9.0 | balanced | +5.5 | 0.0000 | 0.0191 | +0.0555 | 0.0477 | 0.0338 | 0.0235 | 0.2961 | 278.4 |
| 12.0 | balanced | +8.5 | 0.0000 | 0.0408 | +0.1718 | 0.0826 | 0.0559 | 0.0390 | 0.5040 | 158.3 |
| 3.0 | dielectric | −0.5 | 0.0000 | 0.0009 | −0.1382 | 0.0070 | 0.0057 | 0.0039 | 0.0402 | 568.9 |
| 6.0 | dielectric | +2.5 | 0.0000 | 0.0095 | −0.0384 | 0.0185 | 0.0147 | 0.0099 | 0.1084 | 445.6 |
| 9.0 | dielectric | +5.5 | 0.0000 | 0.0300 | +0.0808 | 0.0398 | 0.0282 | 0.0189 | 0.2214 | 319.7 |
| 12.0 | dielectric | +8.5 | 0.0000 | 0.0578 | +0.2049 | 0.0737 | 0.0476 | 0.0316 | 0.3837 | 207.4 |

The complete 114-row table — all 21 members × 3 de-emphasis settings, with and
without a CTLE — is `experiments/channel_family_data.csv`, tracked on purpose
(G49).

**Note `h₁` changes sign.** Below ~8 dB of loss the mandated de-emphasis
**over**-cancels the first post-cursor, so the DFE has to add energy back
rather than remove it. That is a real consequence of a fixed pre-emphasis
meeting a variable channel, and it is invisible if the transmitter is left out
of the model.

### With a matched CTLE in front

CTLE = the existing 1-zero/2-pole behavioural model
(`common/design_equations.py`), placed so that **the peak sits at Nyquist and
the peak-to-DC ratio equals the burden** — which makes CLAUDEwa §3's readings
(a) and (b) the same number, removing the ambiguity from everything downstream.
Second pole at **8.633 GHz**, derived from `rl = 565 Ω` (design 432, the S9
survivor) × `cl_mid = 32.63 fF` (`CL_RANGE.md`). Normalised to **unity DC
gain**: shape only, no raw gain.

| IL | split | burden | residual, channel only | residual, +CTLE |
|---|---|---|---|---|
| 4.5 | skin | +1.0 | 0.1319 | 0.1233 |
| 6.0 | skin | +2.5 | 0.1954 | 0.1317 |
| 7.5 | skin | +4.0 | 0.2739 | 0.1522 |
| 9.0 | skin | +5.5 | 0.3675 | 0.1837 |
| 10.5 | skin | +7.0 | 0.4783 | 0.2259 |
| **12.0** | **skin** | **+8.5** | **0.6133** | **0.2764** |
| 12.0 | balanced | +8.5 | 0.5040 | 0.2839 |
| 12.0 | dielectric | +8.5 | 0.3837 | 0.3007 |

**Channel-only bounds what the DFE must remove; channel-plus-CTLE is the real
number.** The CTLE roughly halves the worst case (0.613 → 0.276).

### THE ANSWER

> **A 1-tap DFE is sufficient everywhere in 3–12 dB.** The eye is open at all
> 21 members, in all three de-emphasis settings, with and without a CTLE. Worst
> case anywhere: **0.847** at 12 dB skin-dominated with de-emphasis switched
> off; worst case in the actual PCIe Gen2 configuration: **0.613** channel-only
> and **0.276** with the CTLE.

**S3's top of range and S8 can both be met with S2's mandated topology.** That
is a clean answer, and it is the opposite of a failure.

### But the mechanism is the part to carry, and it is not reassuring

At 12 dB skin-dominated, mandated de-emphasis, where the residual is 0.6133:

| what | fraction of the cursor | share of the residual |
|---|---|---|
| pre-cursors (unreachable by any DFE) | 0.0154 | 2.5% |
| `h₂` alone — what a *second* DFE tap would buy | 0.0901 | **14.7%** |
| `h₂ … h₅` | 0.2327 | 37.9% |
| `h₂ … h₂₀` | 0.4066 | 66.3% |
| **beyond 20 UI** | **0.1913** | **31.2%** |

**A second DFE tap removes 15% of the problem; a twenty-tap DFE still leaves
31%.** That long algebraic tail is the `√f` signature — and it is exactly the
part a decision-feedback architecture is worst at, because a DFE's cost is
linear in taps while this tail decays as a power law. The dielectric-dominated
member is much better behaved (19.2% in `h₂`, only 15.9% beyond 20 UI), which
is the split axis earning its place again.

**So the useful statement is not "one tap is enough" but "one tap is enough,
and more taps would not help much — the CTLE is the block that has to do this
work."**

### S8's 100 mV vertical floor

The eye at the CTLE output, per unit of CTLE DC gain, and the DC gain S8 then
demands (mandated de-emphasis, matched CTLE):

| IL | split | eye @ unity DC gain | A_dc needed for 100 mV |
|---|---|---|---|
| 4.5 | skin | 480.2 mV | 0.208 (−13.6 dB) |
| 9.0 | skin | 482.6 mV | 0.207 (−13.7 dB) |
| 12.0 | skin | 460.4 mV | 0.217 (−13.3 dB) |
| 12.0 | balanced | 480.8 mV | 0.208 (−13.6 dB) |
| 12.0 | dielectric | 495.5 mV | 0.202 (−13.9 dB) |

**S8's vertical floor is met with the CTLE *attenuating* by 13.3–14.9 dB.** The
reference device measures A_dc = 1.79 V/V (+5.05 dB), which is **8.6× more gain
than S8 needs**. S8 vertical is nowhere near binding, and this is the first
time this project has been able to say so with a real pulse response behind it.

Note also that the eye at the CTLE output is **almost flat in channel loss**
(460–553 mV across the whole family). The matched CTLE gives back very nearly
what the channel took — which is the sanity check that the matching is doing
what it claims.

---

## 6. Compression, re-run (5g)

### What is being replaced

`BOUNDS_REDERIVATION.md` §2 reported, under matched boost:

> 3 dB → 1.22× (compresses), 5 dB → 1.04× (marginal), 7/9/12 dB clean

with a blockquote saying the verdict flips to "11/11 compressing at every loss
point" under `calibration.py` C3's convention, **because the DC-loss constant
was a fixed placeholder**. That is the sentence this section answers.

### The reproduction gate fired first, and passed

Before analysing anything, the run re-simulates the published reference device
(`w=40 nf=4 l=0.15 I=1.5 mA/side VCM=1.25 RL=400`):

| | published | measured |
|---|---|---|
| gm | 12.62 mS | **12.623** |
| gm/I_D | 8.42 | **8.415** |
| v(source) | +0.343 V | **0.343** |
| A_dc | 5.05 dB | **5.053** |
| 1 dB compression swing | 1427 mVpp | **1426.9** |

Five for five. The run aborts on a mismatch rather than replacing a verdict
with a comparison against a different device (same shape as G52).

### A correction that had to be made first: §6 is 0.8–1.5 dB optimistic

Convention C integrates the whole pulse response through the CTLE, so the CTLE
model has to be right. **Measured on this sweep, `design_equations.predict()`
over-predicts the boost at Nyquist by +0.77 … +1.47 dB**, growing with `R_s` —
it neglects `r_o`, so the degeneration factor comes out too large. Using it
would have inflated every convention-C number by up to 1.5 dB.

So the model is **calibrated to the measurement**: `f_z = 1/(2π R_s C_s)` and
`f_p2 = 1/(2π R_L C_L)` are exact (they are set by passives), `g_dc` is taken
from the measurement, and **only `k = f_p1/f_z` is fitted, from one measured
number** (the boost at Nyquist). The peaking and the peak frequency are then
independent checks:

* peaking residual **+0.094 … +0.232 dB** against §5.3b's 0.5 dB reject limit;
* peak frequency **−8.6% … −4.8%**, against `meas ac MAX`'s own 4.7%
  quantisation on an `ac dec 50` grid (session 11).

The uncalibrated model would have put 3 dB at **1.93×** instead of 1.51× — a
28% error in the headline, from a 1.5 dB error in a gain.

### The result

Sweep: 66 `(R_s, C_s)` settings on the reference device, 64.6 s; **14 meet S3**.
Each loss point uses the S3-meeting setting whose Nyquist boost is closest to
the **burden** (= channel IL − 3.5 dB of mandated de-emphasis).

| IL | burden | chosen | boost | have | need A | need B | need C | **A** | **B** | **C** |
|---|---|---|---|---|---|---|---|---|---|---|
| 3.0 | −0.5 | Rs150 Cs1.6p | 3.20 | 1389 | 1689 | 1612 | 2096 | **1.22** | 1.16 | **1.51** |
| 4.5 | +1.0 | Rs150 Cs1.6p | 3.20 | 1389 | 1421 | 1612 | 1897 | 1.02 | 1.16 | 1.37 |
| 6.0 | +2.5 | Rs150 Cs1.6p | 3.20 | 1389 | 1196 | 1612 | 1711 | 0.86 | 1.16 | 1.23 |
| 7.5 | +4.0 | Rs150 Cs3.2p | 3.83 | 1389 | 1082 | 1794 | 1798 | 0.78 | 1.29 | 1.30 |
| 9.0 | +5.5 | Rs250 Cs1.6p | 5.66 | 1445 | 860 | 1645 | 1439 | 0.60 | 1.14 | 1.00 |
| 10.5 | +7.0 | Rs300 Cs3.2p | 7.17 | 1459 | 771 | 1825 | 1642 | 0.53 | 1.25 | 1.13 |
| 12.0 | +8.5 | Rs400 Cs1.6p | 8.36 | 1444 | 615 | 1671 | 1246 | 0.43 | 1.16 | 0.86 |

(mVpp; ratio > 1 = compressing)

* **A** — session 9c/9d's convention: Nyquist content in, Nyquist gain out.
  **2/7 compress.**
* **B** — `calibration.py` C3: long-run level in, peak gain out.
  **7/7 compress.**
* **C** — peak distortion through the **actual** pulse response: the worst data
  pattern puts every UI-spaced sample on the same side, so the excursion is
  `Σ_k |pr(t + kT)|`, maximised over `t`. **5/7 compress. Use C.**

### Does the 1.22×-at-3 dB reading survive contact with a real channel?

**Under its own convention (A) it survives EXACTLY: 1689 mVpp against 1389, ratio
1.22.** Digit for digit the same as §2's table.

That is worth being precise about, because it is not a vindication. It survives
because convention A reads *Nyquist content through Nyquist gain*, and **neither
the deleted constant nor the de-emphasis touches either of those**: the channel's
DC loss never entered A, and the TX FIR has unity gain at Nyquist by
construction. So §2's blockquote was right that a made-up constant decided the
*C3* table — and the headline 1.22× was simply never sensitive to it.

**Measured honestly, the answer is worse.** Convention C at 3 dB is **1.51×**,
and compression binds at **5 of 7 loss points** rather than two.

### Does the matched-boost conclusion change? Yes.

The old conclusion was *"compression is real but localised at the low-loss end
— 1.22× and 1.04× at the two lowest points, clean above."* The new one is:

> **Compression binds across most of the family (5 of 7 points), it is still
> worst at LOW loss, and the mechanism is the long-run content plus the
> transition overshoot — not the Nyquist content.**

The "worst at low loss" half survives and is now better explained: at low loss
the CTLE is pinned at S3's 3 dB floor (§4 — the burden is *below* it), so it
delivers boost the link does not need on top of an input the channel has barely
attenuated.

**Direction of the change, stated plainly:** two of the three inputs moved in
opposite directions and the honest measurement moved further than either. The
channel's DC attenuation went from an invented 1.0 dB to a derived **0 dB**
(raising the demand); the transmitter's specified de-emphasis entered and cut
the long-run level from 0.713 V to **0.535 V** (lowering it by more); and then
computing the real worst-case pattern instead of a proxy raised it again, past
both.

---

## 7. Validation and tests (5f)

| requirement | how it is met | result |
|---|---|---|
| constructed IL at 2.5 GHz = target | closed form, all 21 members | ≤ **1.8e-15 dB** |
| causality gate, **reported** per member | §2's table | 21/21, worst 2.5e-07 vs 1e-06 |
| gate can fail | zero-phase control | **48.0%** at `t < 0` |
| passivity, monotonicity | 20 001-point grid per member | max\|H\| = 1.0000, max ΔH ≤ −3.5e-11 |
| **hand-computed reference** | a **lossless** channel must reproduce the TX pulse exactly | `h0 = c0·A`, `h1 = c1·A`, all else 0, residual 3.9e-15 — agreement to **1e-12** |
| **second hand-computed reference** | the UI-spaced cursors must sum to the transmitter's **long-run level**, because the channel is transparent at DC | holds to **7 figures** at every member |
| determinism | identical parameters → bit-identical arrays; perturbing numpy's global RNG changes nothing | exact |
| CTLE peak location | closed form vs a 400 000-point numeric search | agrees to 2e-4 |
| CTLE peak existence | `1/f_z² > 1/f_p1² + 1/f_p2²`, checked on both sides of the boundary | exact — this is session 9c's "f_z must sit below f_p2 or there is no peak at all" |
| §5.3b fit rejection | calibrated CTLE model, independent residuals | +0.094 … +0.232 dB vs a 0.5 dB limit |
| reference device reproduction | 5 published numbers | 5/5 |

**On determinism and `LinkConfig.seed`:** the channel has **no stochastic step
at all**. It is a pure function of two floats, so the seed never enters it. That
is the strongest available form of the repo's rule, and a test asserts it by
scrambling numpy's global RNG between two evaluations.

Tests: `nebula/tests/test_channel_model.py` (133) and
`nebula/tests/test_cursors.py` (157). Suite **725 → 1007**.

---

## 8. What is NOT modelled — declared here, not left for a reviewer (5h)

A smooth `A·√f + B·f` form has **no impedance discontinuities**. Real channels
have connectors, vias, package balls and stubs, all of which produce
**reflections** — and reflections are precisely the ISI a DFE handles worst:
they arrive many UI after the cursor, outside a 1-tap DFE's reach, and they do
not decay monotonically the way a smooth-loss tail does. Nothing in this
module's magnitude form can represent one.

It was cheap to measure, so it was measured. **Stated probe, not a measurement
of any board:** a connector-like echo `ρ = 0.05` at 2 UI and a via-like
`ρ = 0.02` at 5 UI, applied in the time domain at strictly positive delays
(causal by construction). Mandated de-emphasis, channel only:

| IL | split | residual, smooth | + reflections | Δ | eye mV | → |
|---|---|---|---|---|---|---|
| 3.0 | skin | 0.0799 | 0.1454 | +0.0655 | 525.8 | 488.4 |
| 6.0 | skin | 0.1954 | 0.2745 | +0.0790 | 380.7 | 343.3 |
| 9.0 | skin | 0.3675 | 0.4650 | +0.0975 | 242.0 | 204.7 |
| **12.0** | **skin** | **0.6133** | **0.7353** | **+0.1220** | **117.9** | **80.7** |
| 3.0 | dielectric | 0.0402 | 0.1068 | +0.0665 | 568.9 | 529.4 |
| 12.0 | dielectric | 0.3837 | 0.4920 | +0.1083 | 207.4 | 171.0 |

Range **+0.064 … +0.122**, median +0.085.

**Two things to carry, and the second is the uncomfortable one.**

1. To first order the effect is just `ρ₁ + ρ₂ = 0.07`, because both echoes land
   where the DFE cannot reach. That is the reassuring part.
2. **It grows with loss** — +0.065 at 3 dB, +0.122 at 12 dB — because an echo
   is a copy of the *whole* response, and at high loss that response is itself
   spread over many UI, so the echo brings its own tail. At the top of the
   family two modest echoes are **worth more than the entire difference between
   10.5 dB and 12 dB of channel loss**, and they push the channel-only eye from
   118 mV to **81 mV, below S8's floor**.

**So every number in this document is a lower bound on the DFE's difficulty**,
and the size of the gap is set by a reflection amplitude nobody has measured.
Also absent: crosstalk, mode conversion, fibre-weave skew, the connectors' own
insertion loss, and any frequency-dependent impedance.

---

## 9. The door left open for real data (5i)

`fit_from_touchstone(path, ports)` → `insertion_loss_from_touchstone` →
`fit_insertion_loss`. It extracts `IL(f)` from a supplied `.s4p`, least-squares
fits `A` and `B` with non-negativity, and **reports the residual**. Everything
downstream consumes a `ChannelModel`, so a measured channel replaces the
analytic family without touching the link layer.

Verified two ways:

* **a synthetic channel is recovered from its own insertion loss**: 8.00 dB,
  r = 0.65 → fitted 8.000000 dB, r = 0.650000, RMS residual **5.9e-15 dB**;
* **a shape the two-term form cannot follow is reported, not hidden**: the same
  channel plus a 3 dB resonant dip at 8 GHz fits to IL 8.18 dB, r = 0.671, with
  RMS residual **0.455 dB** and max **2.83 dB**. A large residual is
  *informative* — it is the signature of exactly the reflective structure §8
  says this form cannot represent.

`scikit-rf` is not installed (G15). The Touchstone reader **raises with the pip
hint** rather than falling back to the analytic family, because a run that
believes it is using measured data must never silently use invented data.

**Before trusting a supplied file, check its port map.** The default `(1, 3)`
pairing is a common `.s4p` convention, and a wrong pair reads a *return* loss as
an *insertion* loss — which produces a plausible number and a nonsense channel.

---

## 10. Note for later — do not build it yet (5j)

**Insertion loss at Nyquist is the conditioning variable for the policy.** It is
what the APCCAS paper's LUT is indexed on, it is what differs between protocol
generations, and it is what a spec-conditioned agent should be conditioned on.
`ChannelModel.il_db_at_nyquist` is a first-class attribute for that reason, and
`LinkConfig.channel_loss_db_at_nyquist` carries it.

**No RL plumbing was built in this task**, deliberately. One observation for
whoever does: §3 shows the split ratio `r` moves the DFE's job by up to 2× at a
fixed IL, so conditioning on IL **alone** would leave the policy blind to a
factor-of-two variation in the thing it is optimising. Whether `r` belongs in
the observation is a human's decision, and it is not obvious — a real receiver
cannot measure `r` either.

---

## 11. Everything whose conclusion rested on the deleted constant

| where | claim | status |
|---|---|---|
| `BOUNDS_REDERIVATION.md` §2 blockquote | "11/11 settings compress at every loss point under C3, because the DC-loss constant is a fixed placeholder" | **RETIRED.** Re-measured: 7/7 under C3 (B), 5/7 under the honest peak-distortion measurement (C) |
| `BOUNDS_REDERIVATION.md` §2 table | "matched boost: 1.22× at 3 dB, 1.04× at 5 dB, clean at 7/9/12" | **RE-DERIVED.** 1.22× survives *verbatim* under its own convention; the honest number is **1.51×**, and 5 of 7 points compress |
| `BOUNDS_REDERIVATION.md` §5 item 5 | "Replace the DC-loss constant with a measured channel" | **DONE**, via a derived family rather than a measurement; §9 is the seam for real data |
| `S9_YIELD.md` §7 item 3 | "Replace the 1.0 dB placeholder before any link-level number is quoted" | **DONE.** No link-level number in `S9_YIELD.md` depended on it — S9 is a device-layer sweep |
| `link/config.py::channel_loss_db_at_dc` | a configurable field defaulting to the constant | **RETIRED** → a derived property, exactly 0.0 |
| `link/config.py::v_in_diff_pp_v` | TX swing attenuated by the invented DC loss (0.713 V) | **RE-DERIVED**: TX **de-emphasised** long-run level, 0.535 V |
| `link/mock.py` | equalised `channel_tilt_db` | **CORRECTED** to `equalisation_burden_db` (tilt − TX tilt) |
| `nebula/tests/conftest.py::link_cfg` | 8 dB reference channel | **MOVED to 12 dB** — with 3.5 dB done by the TX, 8 dB left the fixture badly over-equalised |
| HANDOFF §8, "Compression: real, but much smaller than 9c reported" | | **AMENDED** — see §6 |

Nothing else in the tree read the constant; the grep test enforces that it
stays that way.

---

## 12. Caveats a human must weigh before quoting any of this

1. **The channel family is a construction, not a measurement.** It is derived
   from S3, defensibly, and §9 is how a real `.s4p` replaces it. Say
   "constructed from the specification" in any deliverable, never "the channel".
2. **Reflections are excluded and they matter** (§8). Every residual here is a
   lower bound; the stated probe adds +0.06 … +0.12 and pushes the 12 dB
   channel-only eye below S8's floor.
3. **The peak-distortion swing (convention C) is a worst-case pattern.** Real
   PCIe traffic is 8b/10b-scrambled and run-length-limited, so the true peak is
   smaller. C is the right *bound*; the gap to typical traffic is unmeasured.
4. **The compression re-run is at TT/27 °C only**, on the 9c/9d reference
   device with an **ideal tail**. It inherits G47's caveat.
5. **The CTLE second pole is one number** (8.633 GHz, from design 432 at
   `cl_mid`). `CL_RANGE.md` says `cl` spans 5.72×, so `f_p2` spans the same,
   and §5's residuals were not swept over it.
6. **`PCIE_GEN2_TX_DIFF_PP_MIN_V` and the −3.5/−6 dB de-emphasis figures are
   secondary-source**, not checked against the paywalled Base Specification. A
   human must confirm them before they reach the abstract, report or slides.
