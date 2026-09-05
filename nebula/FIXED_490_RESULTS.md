# Setting 490: fresh fixed-circuit validation

**Result: PASS for the current circuit/link model. Not yet adopted in production.**

At the 9 dB / 1.9 GHz request, one unchanged circuit (A7/B42) passes all
**45 PVT corners** and **315 channel/PVT conditions**. Unlike the old adaptive
map, these results do not change Rs, Cs or attenuator code between corners.

The registered runner was frozen in commit `843ca0c`, then completed **91
SPICE calls in 88.37 seconds**: one captured nominal export and 90 corner/tone
measurements. No new RL training or additional request sweep was run.

## What changed relative to the failed fixed export

| Result | Old fixed setting 425 | Candidate fixed setting 490 |
|---|---:|---:|
| PVT corners passing the current model request checks | 43/45 | **45/45** |
| Channel/PVT conditions passing | 301/315 | **315/315** |
| Nominal peaking | 8.632696 dB | **8.852970 dB** |
| Nominal peak frequency | 1.896053 GHz | **1.771915 GHz** |
| SS / 95% VDD / 125 C peaking | 7.445335 dB | **7.647806 dB** |
| FS / 95% VDD / 125 C peaking | 7.446011 dB | **7.638321 dB** |

The two old failures are now above the unchanged 7.5 dB acceptance floor.
This is a circuit comparison, not an algorithm benchmark: setting 490 was
identified by a classical intersection of the frozen measured bank, **not a
new RL proposal**. The old demo and its evidence remain unchanged.

There is a trade-off: peaking accuracy improves, but nominal frequency is
farther from 1.9 GHz. All checks retain the existing +/-1.5 dB and +/-0.3 octave
request tolerances. The smallest peaking-match margin is **0.138321 dB**;
the smallest frequency-match margin is only **0.011880 octave**. Passing this
finite PVT grid is not proof of large manufacturing/layout margin.

## Distortion, power, eye and area

- 100 MHz HD3 passes at all 45 corners; worst **-82.700764 dBc**, using the
  existing checklist's 0.1 V differential peak drive.
- The operating-point 2.5 GHz HD3 check also passes everywhere.
- Worst simulated CTLE supply power is **7.117249 mW**, not total receiver power.
- All 315 ideal DFE controls reproduce the link bridge to 1e-9. Every policy
  passes both model eye requirements in all 315 conditions:

| DFE policy | Worst eye height | Worst eye width |
|---|---:|---:|
| Ideal | 132.442 mV | 0.765625 UI |
| Removed | **131.283 mV** | **0.656250 UI** |
| 20% residual tap error | 132.210 mV | 0.750000 UI |
| Existing nominal 4-bit grid | 131.283 mV | 0.765625 UI |

Height/width minima need not occur at the same condition. As in Entry 100,
the quantisation grid has 1/16 steps and inclusive endpoints; it is a sensitivity
model, not a transistor-level 16-code DAC. No clock jitter, DFE decision-error
propagation, feedback timing or physical DFE implementation is verified here.

Expanded geometry subtotal is **0.002847367 mm2**, of which the historical
Rs/Cs/two-RL proxy is 0.002005164 mm2. **Full S7 area remains NOT VERIFIED.**
The missing bias-capacitor implementation, complete bias circuitry, DFE/slicer,
clocking, Rs/Cs selectors, control logic and layout still cannot be counted as
zero. The seven channels are constructed loss models at one design load, not
measured board channels or a load/mismatch/layout sweep.

## Evidence and next step

Raw data, the exact netlist, candidate definition and hashes are in
[`product_audits/entry101_fixed490_20260906/`](product_audits/entry101_fixed490_20260906/).
`summary.json` is recomputable from the 45-row journal. Circuit signatures match
the same exported topology/geometry/switch state at every corner; only PVT and
measurement stimulus vary.

**Next: integrate a fixed-robust export-selection mode.** Keep RL as a proposer,
require one exported setting to pass all characterised conditions, and disclose
when the measured-bank fallback supplies that setting. Do not hard-code 490 as
an answer to unrelated requests. Keep the adaptive mode and fixed-circuit claims
distinct, and refuse requests with no fixed passing candidate. The organiser's
DFE/physical-tuning/area scope reply is still needed before hardware completion
can be claimed. No selector or demo change was made during this validation.

## Verification

Full suite before changes: **2,791 passed**. After changes and results:
**2,794 passed**, 13 deselected and two existing warnings. Focused candidate
and shared-readiness gates: 17 passed. The result recomputes from the raw
journal, input hashes match, every circuit signature agrees, and 91 calls are
accounted for. The original demo and production selector are unchanged.
