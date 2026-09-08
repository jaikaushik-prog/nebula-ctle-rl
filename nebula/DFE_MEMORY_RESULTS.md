# Isolated memory passes; complete hardware DFE still unfinished

2026-09-06, Entry 109. The existing eight-transistor memory stores **32/32
tested bits correctly** when driven by clean, ideal external inputs. This
includes 15 zeros, 17 ones and 18 transitions in the scored sequence.
One TT / 1.8 V / 27 C SPICE call completed in **0.489541 seconds**. Stopped
at the frozen one-call budget; no resizing, PVT or integration followed.

## What this tells us

The existing W=4 um memory can set, reset and retain a bit at the test's
200 ps repetition interval under clean drive. It does not inherently remain
stuck at zero. The prior connected circuit still fails: Entry 107 gives
32/32 raw decisions but only 15/32 held bits, and Entry 108's four targeted
buffer sizes did not fix storage.

This localizes a demonstrated problem to the real decision/buffer/storage
interface, rather than justifying more blind memory-width scaling. It does
not prove a unique capacitive or timing cause, or guarantee that no other
problem will emerge once that interface is repaired.

The diagnostic deliberately supplies stronger and earlier signals than the
actual comparator/buffers. Full-swing active-low pulses start at the evaluation
edge, with 2 ps edges, and return high by +100 ps. Both inputs then remain
inactive through the unchanged **+110 to +190 ps held window**. No output
voltage or initial memory state is imposed. These ideal stimulus sources are
test equipment, not a replacement for hardware decision making.

## Measured quantities and scope

| Quantity | Isolated memory result |
|---|---:|
| Correct complementary held decisions | 32/32 |
| Worst held margin relative to VDD/2 | 0.893147 V |
| Latest final threshold settling in scored bits | 50.5 ps after stimulus edge |
| Memory VDD supply average power | 0.167895 mW |
| Ideal input sources, net average supplied power | 0.031393 mW |
| Ideal input sources, sum of positive supplied power | 0.110301 mW |
| Eight-MOS gate W*L subtotal | 0.0000048 mm2 |

The margin is a deterministic voltage-to-threshold distance, not a noise or
mismatch qualification. Delay is sampled at the simulator's time resolution,
not an exact analog propagation constant; repeated bits can already be stable.
The power numbers cover this isolated test only, not a complete DFE or receiver.
The gate-area subtotal is **not layout area**. Full S6/S7 closure remains open.

## Next step

Prepare a bounded interface diagnostic before choosing a new topology or
dimensions: inspect which real buffer pulses are too short or too shallow,
and separate delay from loading. A saved-waveform replay into this same memory
could help, but has **not** been run in Entry 109. Obtain approval for any
new circuit architecture, sizing ranges or timing changes. Do not extend the
failed width grid or relax the existing complete decision/hold gate.

After the connected decision/hold block passes, it still needs a correctly
phased previous-bit register, physical feedback summing/tap control, actual
CTLE loading/kickback verification and PVT/noise/mismatch checks. Clock
generation and complete receiver area/power also remain unfinished.

## Evidence and software checks

- [Frozen one-call plan](DFE_MEMORY_PLAN.md).
- [Raw measured result](product_audits/entry109_dfe_memory_20260906/summary.json).
  All **22 hashes** verified; exact deck, 8,040-point trace, log, config and
  source/plan snapshots retained. Reanalysis reproduces every saved field.
- The memory devices are extracted from the existing canonical renderer;
  no copied device definition or production-path replacement was introduced.
- Full software suite: **2896 passed before / 2914 after**, 13 deselected,
  two unchanged warnings, 330.24 / 383.05 s. All 18 new tests pass; focused
  DFE group 77 passed. No experiment or test job remains running.

Rs/Cs switching remains deferred. Working CTLE/RL product, behavioural DFE,
dashboard, cached demo and old PDF are unchanged.

Professor-ready takeaway: "The transistor memory works with clean inputs,
but our connected decision circuit does not yet drive it correctly. We have
isolated the next engineering problem; we have not claimed a complete DFE."
