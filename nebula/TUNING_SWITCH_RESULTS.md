# Entry 95 -- Physical Rs/Cs Selector Result

**Date:** 2026-09-04

**Verdict:** **FAIL -- neither registered selector architecture may enter the CTLE**

**Scope:** isolated real-SKY130 NMOS, 45 PVT corners, three source biases,
five measured widths and two band-edge frequencies. This is not a production
bank or an RL result.

## Plain-language result

The present 512-setting product does not yet have a physically verified Rs/Cs
switch matrix. Entry 95 tested whether ordinary NMOS selectors can fill that
gap. They cannot under either registered arrangement.

Making the transistor wider improves its ON resistance, but simultaneously
adds more capacitance while it is OFF. The measured trade-off has no passing
width:

| Total W (um) | Fingers | Worst Ron (ohm) | Worst ON |Z| (ohm) | Worst OFF C (fF) |
|---:|---:|---:|---:|---:|
| 40  | 1  | 69.679 | 62.738 | 18.640 |
| 80  | 2  | 34.840 | 31.368 | 37.279 |
| 160 | 4  | 17.420 | 15.683 | 74.556 |
| 320 | 8  | 8.710  | 7.841  | 149.093 |
| 640 | 16 | 4.355  | 3.920  | 298.031 |

The 40 um device previously quoted as 16.50 ohm at a grounded source measures
18.10--69.68 ohm over the real 0.44--0.55 V source-bias/PVT grid. The worst
case is `fs/0.95/125C` at 0.55 V. This confirms that a switch number cannot be
moved from one bias point to another.

## Registered gates

| Gate | Requirement | Outcome |
|---|---|---|
| P1 | Exactly 675 valid unique rows | **PASS** |
| P2 | Ron falls and OFF C rises monotonically with W | **PASS** |
| P3 exact one-hot | Ron <= 2.02 ohm and OFF C <= 36.22 fF | **FAIL** |
| P4 six-switch binary | Ron <= 5.06 ohm and OFF C <= 198.0 fF | **FAIL** |
| P5 | Select smallest measured passing width | **NO SELECTION** |
| P6 | Compare 64 switched CTLE codes at TT | **NOT RUN by stopping rule** |

For the binary candidate, 320 um meets the capacitance limit but its worst Ron
is 8.71 ohm. At 640 um, Ron finally passes at 4.35 ohm, but OFF capacitance is
298.03 fF -- 51% above the limit. The exact one-hot bank is farther away: even
640 um misses its resistance limit, while 80 um already exceeds its OFF-load
limit.

## Prediction score

1. Real-bias 40 um Ron would exceed the old ground-biased 16.50 ohm: **HIT**.
2. No exact one-hot width would pass both limits: **HIT**.
3. At least one uniform-width binary choice would pass: **MISS**.
4. Full-bank interaction would exceed the isolated estimate: **NOT SCORED**,
   because P4 failed and the stopping rule forbade inserting it into the CTLE.

## What this means for the project

This is a useful negative result. The existing RL/controller work still proves
selection among 512 separately characterised circuit settings, but it must not
be presented as a tapeout-ready Rs/Cs switch matrix. Ordinary same-width NMOS
series selectors cannot be added without materially changing the bank.

A technically credible next experiment is a **split-capacitor differential
bank**: represent the capacitor between `s1` and `s2` with symmetric capacitors
to AC ground, placing the capacitor switches near ground where an NMOS has much
more gate overdrive. The resistor path needs a different arrangement because a
resistor to ground would alter DC bias. This is a new topology and therefore
requires a new preregistration and owner decision; it is not a reinterpretation
of this failed result.

## Evidence

- Result: `experiments/tuning_switch_results.json`
- Rows: 675; canonical-row SHA-256
  `753B55A40A2E2D9752590F01AA308444D67C002606511EB3FC6D0A4092F4CB41`
- Result-file SHA-256
  `E99F7CD8BAD788DF2F36CD4E3585E66110D30108D7AEBCB520498E7B6F339883`
- Frozen runner commit: `41552b7593257c47ccb43c4fe4526ea27ae321a7`
- Registration commit: `2a5e1ea`

The JSON field named `preregistration_commit` contains the frozen runner HEAD
(`41552b7`), not the earlier registration-only commit (`2a5e1ea`). The value is
accurate but the field name is imprecise; the evidence file is preserved rather
than rewritten after exposure.
