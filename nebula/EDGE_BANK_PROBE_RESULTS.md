# Entry 90 -- focused 12 dB physical-edge probe

**Date:** 2026-09-04

**Verdict:** **FAIL overall: Q1-Q2 and Q4-Q7 pass; Q3 fails at 314/315.**

**Scope:** diagnostic only. The production 7.3 dB bank, frozen RL policies,
reward, tolerances and Entry 89 FINAL are unchanged.

## Plain-language result

The proposed capacitor and resistor settings completely solve the high-frequency
12 dB request. The proposed 8.3 dB attenuator almost solves the low-frequency
12 dB request, but one short-channel/hot mixed-process condition remains.

| User request | Old 512-code bank | Old + 30 probe settings | Result |
|---|---:|---:|---|
| 3 dB @ 1.25 GHz control | 315/315 | 315/315 | retained |
| 3 dB @ 2.5 GHz control | 315/315 | 315/315 | retained |
| 7.5 dB @ 1.768 GHz control | 315/315 | 315/315 | retained |
| **12 dB @ 1.25 GHz** | 308/315 | **314/315** | improved, not closed |
| **12 dB @ 2.5 GHz** | 112/315 | **315/315** | fully closed |

The physical-bank idea is therefore substantially correct, but the exact
preregistered probe does not justify a full 3-12 dB x 1.25-2.5 GHz coverage
claim. One legal request/condition is still unsupported.

## What supplied the new coverage

The low edge gained six conditions: five from `low-r6-c4-a7` and one from
`low-r7-c3-a7`. The high edge gained all 203 missing conditions using four
settings:

| High-edge setting | Newly covered conditions |
|---|---:|
| `high-rmid-cx-a3` | 76 |
| `high-rmid-cx-a4` | 22 |
| `high-r7-cx-a5` | 63 |
| `high-r7-cx-a6` | 42 |

This is direct attribution to measured circuit settings, not an extrapolation.
It confirms both parts of the high-edge diagnosis: one lower Cs setting moves
the peak upward, and the intermediate Rs setting fills a real peaking-code gap.

## The one remaining failure

The remaining point is:

- request: **12 dB @ 1.25 GHz**
- channel loss: **3.0 dB**
- PVT: **SF / 0.95 VDD / 125 C**

Two adjacent measured choices expose the boundary:

- `low-r7-c2-a7` is scorable, but its peak is 1.5544 GHz and misses the
  request tolerance by 0.01442 octaves.
- `low-r7-c3-a7` has the right shape but compresses: 704.2 mVpp is demanded
  against a 698.4 mVpp measured limit.

The compression ratio corresponds to **0.07184 dB** additional attenuation.
That is a lower-bound diagnosis only, not permission to change the range. Entry
90's stop rule applies: do not test 8.4 dB or any other exposed-result response
without a new owner decision and preregistration.

## Frozen gates

| Gate | Criterion | Outcome |
|---|---|---|
| Q1 | exactly 30 settings x 45 corners, all seven link keys | **PASS** |
| Q2 | zero hard device failures | **PASS** |
| Q3 | 12 dB @ 1.25 GHz reaches 315/315 | **FAIL: 314/315** |
| Q4 | 12 dB @ 2.5 GHz reaches 315/315 | **PASS** |
| Q5 | three controls remain 315/315 | **PASS** |
| Q6 | new-row attribution is present | **PASS: 209 new conditions** |
| Q7 | old source hash and Entry 89 isolation hold | **PASS** |

The overall result is a fail because every gate was required.

## Predictions scored

1. Low edge closes at 315/315: **MISS** (314/315).
2. High edge closes at 315/315: **HIT**.
3. Three controls stay 315/315: **HIT**.
4. At least one new setting is used: **HIT** (209 conditions).

## Evidence and cost boundary

- Real-PMOS rows: **1,350/1,350**, 30 settings x 45 PVT corners.
- Existing rows reused: **23,040**; none was re-simulated.
- Raw/decoded journal SHA-256:
  `E46CE25CA4DF67DACEE8944852573162EAF3B3410757AF4E9E9ADD229B905D02`.
- Compressed journal SHA-256:
  `4EC5F77ED184AC2263FB4F5E49D6CD8D676E7B7A9F88974355FEAB0C869F5F53`.
- Result JSON SHA-256:
  `684D80727B3B44952B274AF10DBB30F31793C50FEC57E137A429636F5FFBC48E`.
- The recorded 400.65 s timer covers only the resumed 1,271-row segment. The
  first 79 rows were produced by a one-worker diagnostic segment whose elapsed
  time was not journalled, so no complete wall-clock claim is made.

The first launch used the conda Python and crashed inside SciPy's Windows LAPACK
DLL before producing a row. The system Python then drove the same absolute
`ngspice_con.exe` successfully. This was a host numerical-library failure, not
a circuit failure; the empty journal and subsequent exact membership make the
boundary auditable.

## Decision now required

The measured next candidate would be an **8.4 dB maximum attenuation** focused
only on the single remaining physical row/corner, because 8.3 dB is short by a
measured 0.07184 dB. That is not adopted or authorised here. Separately, the
successful 1.295 pF / 581.2 ohm high-edge settings still require a production
logical-code map and an RL integration plan before they can enter the product.
