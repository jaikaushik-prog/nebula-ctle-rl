# Product readiness - honest result (6 September 2026)

The automated product works as a **scoped circuit/link design tool**, but we
should not present it as a fully implemented, fully compliant receiver yet.
This audit changed reporting, not the circuit, policy, reward or target tolerances.

## What the new measurements say

| Check | Result | Meaning |
|---|---|---|
| One exported circuit, fixed setting 425 | **43/45 PVT corners**, 301/315 channel/PVT conditions pass the model checks | Two corners miss the requested peaking tolerance; the adaptive map's 315/315 cannot be claimed for this fixed circuit. |
| DFE removed entirely | **315/315 model eyes pass** | Ideal DFE cancellation is not what makes this circuit's eyes cross the S8 thresholds on these constructed channels. It does not implement or waive the required DFE. |
| 100 MHz HD3 | All 45 pass; worst **-82.850 dBc** at the existing checklist's 0.1 V differential peak drive | This is now measured separately from the bank's 2.5 GHz operating-point HD3. |
| Request accuracy | **8/12 requests** have a compliant setting at every condition | The full requested tuning rectangle is not covered. This is a product diagnostic, not a new held-out RL result. |
| Full area | **NOT VERIFIED** | Expanded geometry inventory exists; missing implementations and layout cannot be priced as zero. |

The frozen runner commit is `da86ac6`. It completed all **90 SPICE calls** and
the 12-request bank replay in **153.54 seconds**. No circuit was retuned to rescue
a failing corner; the command correctly exited 1 for the fixed-circuit failure.
Raw evidence and hashed input snapshots are included beside this file as
`audit_fixed_pvt.jsonl`, `audit_request_accuracy.jsonl`, `audit_summary.json`,
`audit_provenance.json`, `audit_area_inventory.json` and `audit_source_design.*`.

## The fixed-circuit miss, precisely

For a 9 dB request, the existing acceptance tolerance is ±1.5 dB: minimum 7.5 dB.
At SS / 95% VDD / 125 C, measured peaking is **7.445335 dB**; at FS / 95% VDD /
125 C it is **7.446011 dB**. They miss by approximately **0.055 dB** and
**0.054 dB**. Each repeats across seven channels, giving 14 failed conditions.
The failing row is only `S3_peaking_match`; these responses still sit inside
the problem statement's broad 3-12 dB band. We have not widened the tolerance.

The single circuit is therefore close, but it does **not** pass its current
all-corner request contract. This is a response-accuracy issue, not an eye failure.

## Area: what changed and what remains unknown

| Inventory | mm2 | What it includes |
|---|---:|---|
| Historical proxy | 0.001676824 | Rs, Cs and two RL bodies/plates only |
| All netlisted passive bodies/plates | 0.002175412 | Includes both attenuator legs, all OFF branches and parallel multiplicities |
| MOS gate geometry | 0.000343615 | Pair, mirror/tails and six PMOS switches; total width is not multiplied by nf again |
| Expanded geometry subtotal | **0.002519027** | A sum of geometry proxies, **not** a placed core footprint |

Cbyp is a 10 pF ideal capacitor with no physical geometry; Iref is an ideal
reference source, not an implemented bias generator. Their implementation
costs are unknown, not zero. CLp/CLn are treated as external load assumptions;
an integrated receiver must account for their realization. Missing DFE/slicer,
clocking, bias/common-mode generation, Rs/Cs selectors, digital control, contacts,
diffusion, wells, guard structures, routing, spacing and floorplan also prevent
full-area certification. There is no arbitrary overhead multiplier.

The raw historical `area_mm2` and reward remain unchanged so earlier experiments
stay reproducible. New JSON includes a separate inventory and the UI says
**Partial passive area / Full receiver area: not verified**. Power is labelled
CTLE-only, not complete receiver power.

## Current-circuit DFE sensitivity

All 315 ideal controls reproduce the current bridge's eye height and width to
1e-9. All four policies pass both eye thresholds in all 315 conditions:

| Policy | Worst height | Worst width |
|---|---:|---:|
| Ideal 1-tap cancellation | 147.416 mV | 0.781250 UI |
| No DFE | **139.531 mV** | **0.687500 UI** |
| 20% residual tap error | 145.839 mV | 0.765625 UI |
| Existing nominal 4-bit quantisation model | 141.204 mV | 0.781250 UI |

These are separate worst-case minima, not necessarily the same condition. The
quantisation diagnostic reuses the existing tap grid (1/16 step, clipped to
±0.5); inclusive endpoints give 17 grid values, so this is not a designed 16-code
hardware DAC. No DFE timing closure, decision-error propagation, clock jitter,
feedback parasitics or transistor-level power/area is established here. These
constructed loss channels also omit measured board reflections and crosstalk.

## Where requests work and where the product must refuse

Each cell is the number of channel/PVT conditions with a compliant adaptive
setting, out of 315. A request is deliverable under the current model only when
**all 315** pass. This table is request coverage, not a benchmark comparison.

| Peaking request | 1.25 GHz | 1.90 GHz | 2.50 GHz |
|---|---:|---:|---:|
| 3 dB | 315 | 315 | 315 |
| 6 dB | 315 | 315 | 315 |
| 9 dB | 315 | 315 | **273 - refuse** |
| 12 dB | **308 - refuse** | **312 - refuse** | **112 - refuse** |

The 9 dB / 1.9 GHz representative reproduces setting 425, **8.632696 dB** at
**1.896053 GHz**. Across its adaptive conditions the largest absolute peaking
error is **0.646687 dB**. Good nominal accuracy and fixed-code corner robustness
are separate questions; the current selector prioritises the former per condition.

## What to do next

1. **Validate a fixed robust candidate before changing the demo circuit.** A
   post-audit read-only intersection of the same bank's passing settings found
   exactly one fixed setting, **490**, satisfying the 9 dB / 1.9 GHz V6 checks at
   all 315 stored conditions. That is a candidate, not an adopted replacement:
   it has not received this fresh 100 MHz / DFE / exact-export audit. Do not
   silently swap it into setting 425's evidence or claim it is RL's selection.
2. **Send the organiser questions.** The draft is
   [`ORGANISER_SCOPE_QUESTIONS.md`](ORGANISER_SCOPE_QUESTIONS.md), currently unsent.
   Confirm physical Rs/Cs tuning, transistor-level DFE and full area/power scope
   before committing the remaining time to hardware work.
3. Keep the UI and evidence honest: MODEL PASS is not full receiver compliance;
   failed requests remain refusals. Keep the current demo reproducible while a
   replacement and any fixed-robust selection mode await a separate decision.

The software work and diagnostic measurements are complete. Full layout area,
DFE/selector hardware and organiser acceptance are **not** completed by this audit.

Verification: baseline 2,777 tests passed; post-change full run 2,790 passed;
final affected groups 81 passed including one additional schematic-label test.
These overlapping counts are not additive. Source hashes, recomputed summary,
preserved design data, live API and 15-file evidence ZIP are checked. The
schematic was visually inspected; interactive browser automation was unavailable.
