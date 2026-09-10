# Entry 133: fixed-control configurable CTLE + transistor DFE electrical PVT

Registered 2026-09-10 after Entry 132's seven-call connected gate passes.
Keep the exact selected physical circuit: N500/no-fixed-MIM, R=.7 VDD,
C=.165 VDD, CML width 8, four W=.42/L=4 bleeders, DAC code 2/normal sign,
external clock phase 1 UI, the same 80-bit pattern and 7.5 dB constructed
channel. No per-corner geometry, control-fraction, DAC or phase retuning.

Maximum 45 sequential ngspice_con processes, 180 s each, no retries. Every
registered corner is unique; earlier screen measurements are reused, not
rerun. First repeat nominal TT/1/27 and require the complete existing gate
plus Entry 132 nominal agreement (eye <=1e-6 V, VDD power <=1e-9 W, aperture
width <=.005 UI, identical 64/64 count). Stop after one if this fails.

Then run SS/.95/125, FF/1.05/0, SF/.95/0 and FS/.95/125, retaining all four
regardless of any failure. Stop after five total if any screen fails the
existing signal/control/voltage gate. Only if all five pass run the remaining
40 members of 5 processes x .95/1/1.05 VDD x 0/27/125 C. Once promoted, run
all remaining cases once and retain every failure. Declare primary-channel
PVT pass only for 45/45 accepted unique points, with unchanged source/PDK hashes.

Reuse the exact Entry 132 deck builder; only PVT values change. Parse actual
corner-scaled stimulus/clock/control voltages and currents. Keep all bit,
eye, power, varactor-control and signed-new-DFE gates unchanged; report the
new bilateral Rs switch's exact signed audit separately. Extend no measured
voltage into invented safe values. Whole-circuit magnitude/body checks remain
an envelope, not signed-domain/lifetime or passive-nonlinearity signoff.

Verify the complete Entry 132 raw/gzip manifest and all source hashes first.
Snapshot all dependencies and pin the same full external PDK closure. Test
one/five/45-call stopping, late failures, and exact nominal raw replay before
SPICE. Focused/full regression and local freeze precede one run into
`product_audits/entry133_dfe_configurable_pvt_20260910/`. Keep raw failures and
use the existing lossless archive helper without deleting original traces.

This gate covers finite-pattern transistor bit/eye/power/voltage behavior on
ONE declared channel and control setting. It does not validate peaking/frequency
at all corners, other tuning identities with DFE loading, other channels,
runtime reconfiguration, noise/HD3, BER, local mismatch, passive tolerance,
extracted parasitics, routed area or full receiver signoff. Do not inherit
older fixed-passive metrics or change frozen RL evaluation. Register those
additional checks separately based on the retained result of this bounded run.
