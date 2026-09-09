# Connected transistor CTLE plus 1-tap DFE: Entry 124

Measured 2026-09-09 after registration commit `bbf0281`.
Evidence: `product_audits/entry124_dfe_connected_20260909/`.
58 real SPICE calls, 1328.832334 s, no retries. The runner correctly exits
nonzero because one selected-circuit PVT point fails its electrical gate.

## What now works

The physical CTLE drives a real transistor current-mode summer, W=8 CML
decision/hold pair, and a four-branch switched-current feedback DAC. Stored
q/qb alone drive feedback; there is no behavioural decision or cancellation
inside the circuit. Original CTLE devices/passives and loads remain present.

At TT, 7.5 dB constructed channel loss, the registered selection chooses
phase 1.0 UI, DAC code 2, positive fixed wiring polarity. All 64 scored bits
pass master, held-output and previous-bit checks. Sampled summer eye:

- Feedback code 0: 195.188973 mV.
- Selected code 2: 237.761878 mV (42.572905 mV improvement).
- Same code with reversed feedback wiring: 128.803924 mV.

Combined CTLE/summer/latch/DAC VDD power is 9.255979 mW at this point.
One fixed circuit/code/phase is then used at all 45 primary-channel PVT
points: **45/45 decode all 64 bits, but only 44/45 pass all electrical gates**.
Minimum sampled eye is 109.682577 mV, maximum VDD power 12.514816 mW.
Worst held and previous-decision margins are 38.405872 and 53.731345 mV.
External clocks' maximum positive supplied power is separately 0.128116 mW;
this does not include a fabricated clock generator. Drawn-geometry subtotal
is 0.007954521107 mm2, not routed receiver area.

## Measured failures and next physical correction

FS/0.95/125 is the one electrical failure. In inactive branch Xdfe_tail3,
drawn Vds reaches -2.451058 mV over 3,620 saved samples. Its source floats
near 0.705 V as the common DAC drain falls to 0.702914 V. This occurs during
operation, not only startup. Bits, eye and power pass there; they do not
override the exact signed voltage gate. Entry 125 preregisters two weak
physical discharge-device sizes to fix this floating node. Adding those
devices leaves residual feedback at code 0, which must be labelled minimum
current rather than disabled in the new experiment.

The 3 dB TT diagnostic passes 64/64 with 248.135050 mV sampled eye. The
12 dB diagnostic at the same clock phase fails: 15/64 and -318.102827 mV.
Saved CTLE outn-outp waveforms show later arrival at 12 dB; a later sampling
time is a hypothesis until a new transistor transient verifies it. Entry
126 is conditional on Entry 125 recovery and tests three later phases with
matched minimum-current/reversed controls and fixed per-channel PVT.

The early baseline phases (0.5 and 0.75 UI) and overstrong/reversed code-8
failure also remain in the evidence. No selection result is rewritten.

## Exact evidence boundary

This is connected transistor-level feedback evidence, not full receiver
signoff. All-new DFE MOS must meet strict signed terminal limits; whole-
circuit magnitude/body limits also apply. Legacy bidirectional PMOS input
attenuator switches show reverse-Vds samples in the whole-circuit signed
audit. Those findings remain visible and are not called signed-domain
passes. The 44/45 count is the registered signal/electrical gate, not a
claim of whole-circuit model-domain or reliability qualification.

The 64 scored histories are finite and noiseless. Entry 124 did not gate
horizontal eye width, BER, jitter, mismatch, passive tolerances or extracted
layout. Clocks, digital control levels and common-mode are external sources.
Rs/Cs are still fixed. Loaded noise/HD3 and final configurable-passive
integration require subsequent checks; old 315/315 model counts and frozen
RL results do not transfer to this circuit. Reports and product registry
are unchanged.

All 372 original file hashes are preserved. The 116 exact gzip siblings
contain 1,887,188,425 bytes, preserving 9,608,421,600 raw trace bytes; local
originals are retained. Largest gzip is 20,346,341 bytes. Original manifest
SHA-256: `3f4ddd3ca15f43f7010dfbbed23462f02608346fe03ed12bd67ab42e748fb845`.
Summary SHA-256: `1a10b873c394cc2ec06fc26b0d9b8cdc6f2fdc1868bf7b13fd0a2a750fb2edc1`.
