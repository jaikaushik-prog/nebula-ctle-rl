# Clean-input buffers plus memory pass; comparator interface remains open

2026-09-06, Entry 110. **32/32 bits pass** the unchanged +110..190 ps held
window using the existing sixteen width-4 buffer/memory MOS driven by clean
external signals. One TT / 1.8 V / 27 C call took **0.763771 s**. No other
trial, sizing change, PVT sweep or product integration followed.

## What we learned

| Actual test | Correct stored bits | Meaning |
|---|---:|---|
| Entry 107: comparator + buffers + memory | 15/32 | Connected prototype still fails |
| Entry 109: memory alone, clean inputs | 32/32 | Memory can store under clean drive |
| Entry 110: buffers + memory, clean inputs | 32/32 | Existing buffer/storage path can work under clean drive |

The new result narrows the demonstrated failure to the interaction with the
real comparator output: its level, transition speed, available pulse duration
and loading. It does not identify a unique capacitance or prove a particular
replacement circuit. It does not mean the comparator is adequate merely
because its raw outputs cross a VDD/2 decoding threshold.

Prior saved-waveform analysis found that all three equal-width Entry 107
circuits miss active-low memory pulses on all 18 data transitions. Their 14
repeated bits reach low only around +119..124 ps; the width-4 low spans last
about 18..26 ps. None arrives before +100 ps. All 101 Entry 107/108/109
evidence hashes and saved gate values were checked during that diagnosis.

## Measured timing and electrical scope

The new ideal x/y inputs arrive at the evaluation edge with full 1.8 V swing
and 2 ps edges. These are deliberately stronger and earlier than real
comparator outputs; there is no simulated comparator or physical clock source
in this isolated bench. The bx/by memory inputs are produced by the actual
two-inverter buffers, not forced by ideal sources.

- Buffer active-low threshold arrival: **37.5..39.5 ps** after stimulus edge.
- Last low sample: **129.5 ps**. Buffer delay extends active driving into
  the first part of the +110..190 ps held window. Both inputs are inactive
  for at least 60 subsequent saved hold-window samples, with q/qb still correct.
  Do not call the entire window unforced retention.
- Latest final complementary memory threshold settling: **92.5 ps**.
- Worst held margin relative to VDD/2: **0.806478 V**.
- DUT VDD supply average power: **0.657757 mW**.
- Ideal input-source net / positive supplied average power:
  **0.042304 / 0.119316 mW**, separate from DUT supply power.
- Sixteen-MOS gate W*L subtotal: **0.0000096 mm2**, not layout area.

These are sampled nominal diagnostics, not noise, mismatch, reliability or
receiver qualification. In particular, the active buffer waveforms undershoot
to approximately **-0.214 V**; the raw trace is retained without clipping.
Device terminal-stress/reliability has not been assessed. Supply/source power
does not include a real comparator, clock generator or feedback summer.

The clean case leaves only about 17.5 ps from latest memory settling to the
start of the required hold window. The real comparator introduces delay and
different waveforms; simply adding isolated delays is not a valid connected
simulation. We must remeasure the full path before any integration claim.

## Next decision

Stop these isolation calls. Propose a shorter/lower-load comparator-to-storage
interface with an explicit circuit, dimensions and bounded test budget for
owner approval. Do not repeat the failed global or stronger-drive width grids,
or shift the gate window. A nominal connected decision/hold pass must precede
PVT and causal previous-bit feedback/summing, loaded CTLE verification,
clock/noise/mismatch checks and full receiver power/area closure.

Rs/Cs, production CTLE/RL, behavioral DFE, dashboard, cached demo and old PDF
are unchanged. Full hardware DFE and full receiver verification remain false.

## Evidence and checks

[Frozen plan](DFE_BUFFER_MEMORY_PLAN.md) and
[raw result](product_audits/entry110_dfe_buffer_memory_20260906/summary.json).
All **25 evidence hashes** verified, including exact deck, both 8,040-point
waveform files, log, config and source/plan snapshots. Reanalysis reproduces
all saved measurement fields. Legacy Entry 109 deck remains unchanged.

Full software suite: **2914 passed before / 2922 after**, 13 deselected,
two unchanged warnings, 305.53 / 291.04 s. Seven new boundary tests failed
before implementation; focused group passed 84 before measurement and 85
after the measured-evidence regression was added. All eight new tests pass.
No experiment or test job remains running.

Professor-ready takeaway: "The unchanged buffers and memory work with clean
inputs. The remaining failure is in delivering a usable comparator decision
to that path on time. This is diagnostic progress, not a completed DFE."
