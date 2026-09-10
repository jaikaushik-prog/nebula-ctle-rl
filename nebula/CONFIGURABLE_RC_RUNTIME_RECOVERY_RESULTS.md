# Entry 135: AC instrument fixed; physical control settling misses the registered gate

All three static references pass. The G164 three-point AC correction works;
DC/full-AC calibration and small-signal transient response match the measured
Entry 131 circuit. The fourth, continuous powered transient completes without
an instrument error. Sources/PDK remain unchanged. No retry ran.

The combined runtime gate FAILS for all three control transitions. At the
last 20 ns window in each 600 ns hold, internal-control mean errors are:

- 9 -> 3 dB controls: 3.495560 mV.
- 3 -> 6 dB controls: 1.530439 mV.
- 6 -> 9 dB controls: 1.533016 mV.

All exceed the registered 1 mV settling criterion. No transition has a
contiguous passing tail, so no combined settling bound is available within
this observation. The original 500 ns demonstration criterion remains failed;
it is not an organiser-specified tuning-latency limit.

The independently measured two-tone response does follow the settings:
complex-gain/residual/power-only passing tails begin 70/40/160 ns after the
ramps. Those omit the failed control-voltage condition and are diagnostic
results, NOT replacements for the failed combined gate. Whole-device
magnitude/body and varactor envelopes pass throughout. Bilateral signed
device qualifications remain visible in the raw audits.

Static low-frequency gains are approximately .388168/.677468/.501661 V/V
for the near-9/3/6 dB controls. The three states are distinct; these numbers
are absolute gains at 100 MHz, NOT peaking boost. Two small tones are not
NRZ/DFE decoding or HD3/BER verification. The DFE is absent in this instrument.

Entry 136 separately extends the observation window on the SAME circuit to
measure the actual combined settling time. It preserves the original 500 ns
criterion and must report that criterion separately from eventual settling.
It does not reduce a physical feed resistor or silently transfer PVT evidence
to a different circuit.

Run from `bf03238944dc15bfc0e9c14e1e924b86817c88ce`: four calls,
139.824614 s including 2.111230 s prerequisite verification. Original
manifest: 108 entries. Eight lossless gzip siblings preserve 408,926,058 raw
bytes in 104,741,405 bytes; largest 57,334,419 bytes. Originals retained.
This large archive is project-owned waveform evidence, not reference material.
Summary SHA-256: `7c5b725eba0a7e6420eb7d0e2f743d14c6a4f866cab4f537199b2e39bf7b3624`.
Manifest SHA-256: `77d99d8d188c0026e697cee01c83a6353c59cb57d63c7f131b4e030239d375ed`.
Evidence: `product_audits/entry135_configurable_rc_runtime_recovery_20260910/`.
