# Entry 144: calibrated fixed-control transistor link PVT

Registered 2026-09-10 after Entry 143 independently passes nominal tuning,
two held-state noise checks, four-way clocked distortion and fresh 64/64-bit
physical decoding at R=.70 VDD / C=.185 VDD. Nominal peak 1.903-1.906 GHz,
boost 8.744-8.747 dB; noise .65404-.65405 mVrms. HD3 -54.9137 to -54.9201 dBc.
Fresh nominal eye 210.340342 mV, positive opening .705 UI, width above
100 mV .655 UI, VDD power 9.263481 mW. These are finite-pattern model results.

Maximum 45 calls, 180 s each, no retries. Exactly reuse Entry 133's corner
order and stopping rules: nominal first must replay the fresh Entry 143
nominal raw reference; stop after one if it fails. Then SS/.95/125,
FF/1.05/0, SF/.95/0, FS/.95/125 screens; retain all four, stop after five if
any fails. Otherwise finish all remaining points in the original 5 process
x 3 VDD x 3 temperature grid. Never retune at a corner.

Same physical CTLE, Rs/Cs devices and DFE, ideal external clock/control/VCM
drivers, 7.5 dB constructed channel, 80-bit pattern/64 scored bits,
phase 1 UI, code 2 and normal feedback. External R/C voltages track VDD
at the two FIXED fractions. The nominal deck is byte-identical to Entry 143.

Use the frozen physical bit/eye/power/voltage/aperture formulas and the
argument-parameterized RC audit. Strict simulator/abort checks. Require
64 correct scored bits, eye >100 mV and >.4 UI, existing new-DFE signed
voltage/whole magnitude-body/varactor and power gates at every tested point.
Retain the separately reported signed bilateral Rs-switch findings.
Do not turn the numerical .005 UI eye scan into BER or jitter certification.

This remeasures link PVT at calibrated controls; no transfer of old controls.
Nominal analog evidence remains separate: analog PVT/noise/HD3, all held
branches, arbitrary channels, nine-target map/full rectangle, DFE-active
runtime tuning, mismatch/passive tolerances, layout and full receiver remain
unverified. Typical passives and transistor corners only.

Verify complete Entry 143 archive/source hashes and PDK closure; copy and
SHA-256 freeze all scientific sources before calls with honest dirty-parent
provenance. Same 3305/1019.90 s before-change full baseline; failure-first
and focused tests before run, mandatory full post-result regression/audit
before local commit. No full test suite or archive job concurrent with SPICE.

Run once in product_audits/entry144_dfe_calibrated_pvt_20260910/.
Retain failures, raw originals and lossless archives. No public upload or
visibility change while privacy instructions remain contradictory.
