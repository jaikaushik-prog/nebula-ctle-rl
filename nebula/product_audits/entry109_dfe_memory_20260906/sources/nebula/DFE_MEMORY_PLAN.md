# Entry 109: isolated existing-memory diagnostic

Frozen 2026-09-06 before measurement. Owner requested continuation after the
proposal to test the existing memory alone with clean inputs. This is an
isolation diagnostic, not a new sizing or topology search.

## Fixed scope and budget

- Exactly one fresh TT / 1.8 V / 27 C transient call. No retry, tuning, PVT
  sweep, buffer replay, feedback integration or product change in this entry.
- Extract the eight existing cross-coupled NAND memory instances directly
  from `dfe_hardware.dut_lines(4, buffered=True)`. Preserve every connection,
  canonical SKY130 model, W=4 um, L=.15 um and nf=2. No device redeclaration.
- Remove the comparator and buffers from this isolated testbench only.
  Ideal external voltage sources drive bx/by; they are NOT hardware inside
  a delivered DFE. No output state is imposed, no initial condition is set.
- Use the existing LinkConfig seed=1, 36-bit pattern (4 warmup + 32 scored),
  200 ps UI and evaluation edges from Entry 106. Both inputs idle high.
  For each bit, assert only bx low for one or by low for zero. Falling edge
  starts at the evaluation edge; return begins at edge+98 ps, reaches high
  at edge+100 ps. Both transitions take the existing 2 ps. Never assert both.
- Clean inputs become valid earlier than real comparator/buffer outputs.
  This gives the memory an intentionally easier test. A pass does not prove
  that it accepts the real path's delayed or incomplete pulses.

## Unchanged held-bit check, diagnostic meaning

Keep the earlier held window edge+110 through +190 ps, with at least 70
samples, and strict VDD/2 complementary decoding of q/qb. This tests retention
after release of the input. No raw-comparator result is fabricated. Exactly
32 bits must pass and both measured input sources must match their equations
to the existing 1e-5 V numerical tolerance. Finite, increasing, complete traces
and maximum 2 ps sample gaps are mandatory. Preserve failed traces and logs.

Report final settling delay through the end of each held window as a
diagnostic, not a new gate; repeated bits need not involve a transition.
Report supply and ideal input-source power separately. MOS W*L subtotal
is not layout area; full DFE and full receiver verification remain false.

If it passes: the existing memory works under this clean nominal stimulus;
investigate the real interface next under a separately frozen proposal.
If it fails: inspect its actual connectivity and waveform before proposing
another circuit change. In either case, stop after this single call.

Save exact deck, raw trace, ngspice log, config, results, source snapshots and
SHA256 manifest. Use the shared `dfe_slicer` lock and the existing strict
simulator launcher. Unit-test the probe before running, and run the complete
software regression before and after changes.
