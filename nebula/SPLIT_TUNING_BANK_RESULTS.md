# Entry 96 -- Split Tuning Bank Result

**Date:** 2026-09-04

**Verdict:** **FAIL -- capacitance accuracy passes, but switch loss is 19.8x over the conductance-error limit**

## Plain-language result

Moving the capacitor switches close to ground solved the problem it targeted:
the network reaches the intended capacitance values closely enough. However,
the enabled NMOS devices make those capacitors strongly lossy at GHz
frequencies. In other words, the circuit behaves like the requested capacitor
plus an unwanted resistor. That extra loss would damp the CTLE peaking, so the
bank is not allowed into the amplifier.

All 64 `Rcode x Ccode` settings simulated successfully with real SKY130
resistors, MIM capacitors and nine selector NMOS devices per setting. Each deck
also contained a separately drawn physical `R || C` control.

## Registered gates

| Gate | Requirement | Result |
|---|---|---|
| S1 | Exactly 64 valid unique codes | **PASS** |
| S2 | Conductance decreases monotonically with Rs code | **PASS** |
| S3 | Effective capacitance increases monotonically with Cs code | **PASS** |
| S4 | Conductance error <= 0.913434 mS | **FAIL: 18.117350 mS** |
| S5 | Effective-C error <= 0.593954 pF | **PASS: 0.517849 pF** |
| S6 | No CTLE/link/RL/FINAL access | **PASS** |
| Overall | S1--S6 all pass | **FAIL** |

The S4 miss is **19.83x** the limit. Per the registered stopping rule, no CTLE
simulation, code remap, all-corner run or RL retraining was performed.

## Why it failed

The error tracks capacitor code and frequency, not resistor code:

| Cs code | Max G error at 1.25 GHz (mS) | Max G error at 2.5 GHz (mS) |
|---:|---:|---:|
| 0 | 0.114 | 0.430 |
| 1 | 0.770 | 3.005 |
| 2 | 1.430 | 5.596 |
| 3 | 2.069 | 8.102 |
| 4 | 2.769 | 10.841 |
| 5 | 3.392 | 13.282 |
| 6 | 4.019 | 15.741 |
| 7 | 4.625 | 18.117 |

At Cs code 0 all three capacitor selectors are OFF; the residual error is
small. Enabling larger capacitor branches increases the real part of their
admittance almost linearly. The worst row is `R7/C7` at 2.5 GHz: switched
conductance is 20.744 mS versus 2.627 mS for the physical control. This is the
series resistance of the ON switches appearing as dielectric-path loss, not a
failure to obtain capacitance: the same row measures 9.939 pF versus 10.000 pF.

## Prediction score

1. Split capacitor would pass S5: **HIT**.
2. Floating resistor branches would make S4 pass: **MISS under the registered
   total-admittance gate**; the resistor-only/low-C rows are good, but capacitor
   switch loss dominates S4 at high Cs.
3. Both axes remain ordered: **HIT**.
4. S1--S6 all pass: **MISS**.

## Implication and next option

Entry 96 proves that checking only effective capacitance would be misleading:
the value is accurate while its loss is unacceptable. Simply inserting this
bank into the CTLE would produce a believable but degraded response.

A further attempt needs a fundamentally lower-resistance capacitor selector,
not another reinterpretation of these results. Possible candidates are a
qualified low-threshold SKY130 switch device, a safely boosted gate, or a
different tunable-capacitor architecture. Each changes device/reliability or
topology assumptions and requires separate approval and preregistration. Just
widening the existing NMOS also increases disabled capacitance and area, so it
is not an automatic fix.

## Evidence

- Result: `experiments/split_tuning_bank_results.json`
- 64-row SHA-256:
  `050315CC0F81869FAEEA1746F3627F68B0B5F20FC84BD0E85483CC64E5B4CCDE`
- Result-file SHA-256:
  `70E73F1A8798AF957BDF36D5275D64218F76A78CF75D451A3354928F327D5582`
- Registration commit: `944cb84`
- Frozen runner commit: `f6f4c01a04fb7eeb4c35c03380a8da8b8c4b1db9`
- Measured wall clock: 3.785 s with eight workers
- Final non-slow regression: 2,759 passed, 13 deselected, 2 known warnings
