# Entry 136: runtime tuning settles on unchanged physical hardware

The same powered N500/no-fixed-MIM physical CTLE changes its external R/C
controls through the measured near-9 -> 3 -> 6 -> 9 dB settings on the
1.9 GHz target line. With longer observation, all three transitions reach
the registered complex-response, control-voltage, residual and power
conditions and remain inside them for every subsequent observed window.

Measured windowed settling bounds after each 10 ns control ramp:

- 9 -> 3 dB controls: **850 ns**; 13 final passing windows.
- 3 -> 6 dB controls: **690 ns**; 29 final passing windows.
- 6 -> 9 dB controls: **650 ns**; 33 final passing windows.

There are 98 overlapping 20 ns windows per transition, spaced 10 ns apart.
Each passing window requires both measured complex gains within 2% of the
accepted static AC references, internal-control means within 1 mV of static
OP, output residual RMS <=5% and average circuit VDD power below 15 mW.
These are windowed small-signal measurements, not instantaneous or BER timing.

**The original 500 ns criterion remains FAILED for all three transitions.**
It is an internal demonstration target, not an organiser-specified latency.
Eventual settling is a separate measured conclusion; neither Entry 135 nor
its original acceptance gate is reclassified or relaxed.

The final observed control errors are .579136/.254836/.190706 mV. Whole-MOS
magnitude/body and varactor envelopes pass throughout the actual trace;
bilateral signed-domain qualifications remain in the saved audits. Maximum
20 ns-window VDD power is 6.969545 mW for this standalone CTLE/reference,
NOT the CTLE + DFE power. External-source generation remains excluded.
Positive supplied R/C-control energy is .254034/.152766/.162612 pJ over
the three complete transition/hold intervals; this is source-delivered
energy, not a fabricated driver-power estimate.

No device value changes: both 10 kohm control feeds, physical bypasses,
poly/NMOS resistance network, official varactor arrays, CTLE, physical bias
reference and original output load are unchanged. Only control timing and
the observation stop extend relative to Entry 135. Three accepted static
references are reused without SPICE reruns. No reset occurs between settings.

## What this adds to the submission

Rs/Cs configurability is demonstrated as actual electrical control of ONE
physical circuit during a continuous simulation, not merely fixed-passive
netlist substitution. This complements Entry 131's nine standalone target
identities and Entry 133's separate 45/45 connected CTLE + transistor DFE
electrical PVT checks at the primary fixed control setting.

This runtime measurement is TT/1.8 V/27 C with two 1 mV test tones. The DFE
is absent here: uninterrupted DFE decoding during a change, runtime PVT,
other loaded tuning targets, full tuning-rectangle coverage, loaded noise/
HD3, BER, physical control/clock generation and layout are not established.
Existing production exports, registry, PDFs and frozen RL claims remain
unchanged; they must not silently inherit these new hardware results.

Run from `d6a1590a2aa7e3611a828ea35f15fc4422616fb7`: one call, no retry,
111.350256 s including 1.744722 s prerequisite verification. The actual
trace has 639,451 rows over 3100 ns. Scientific sources and the external PDK
closure are unchanged; raw originals are preserved with lossless archives.
Two archives preserve 576,145,351 raw bytes in 146,769,203 bytes. The largest
is 93,265,618 bytes; both are explicitly audited project-owned waveform evidence.
Original manifest: 85 entries.
Validation: 178 focused tests passed; full suite 3285 passed, 13 deselected,
two known warnings in 563.57 s. Immediate before-change baseline: 3283 passed.
Summary SHA-256: `a816bab17c13a7700a83ef0dcd62c571a701df8be8b1f3265de026f95022d4e3`.
Manifest SHA-256: `d4177c1ce2b9458743f80466160558be5dbf5a4d931920f36e59f9eb45a70324`.
Evidence: `product_audits/entry136_configurable_rc_settling_20260910/`.
