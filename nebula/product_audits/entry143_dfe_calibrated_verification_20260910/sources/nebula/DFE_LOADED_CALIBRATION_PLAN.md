# Entry 142: primary loaded target calibration

Registered 2026-09-10 after Entry 141's four-way HD3 pass. The old control
point is physically valid but peaks near 1.75 GHz when loaded by the DFE.
Calibrate only the external R/C controls of that unchanged transistor DUT.

One call maximum, 180 seconds, no retry. Measure 65 OP/AC pairs:
R fractions (.70,.68,.69,.71,.72) crossed with C .165 through .225 in .005
steps, R-major order. The first pair is the exact accepted loaded baseline.
Use the frozen Entry 138 state-0 negative static deck body and strict static
solver settings; no physical geometry, source, clock, model or bias change.
Only alter the existing R/C voltage sources inside the analysis sequence.

Validate all exact OP/AC files and strict warnings. The first row must match
all prior DC nodes within 1 uV, complex AC within 1e-4 relative and VDD
power within 100 nW. Validate every actual control/input/clock primitive,
negative stored branch, broad AC limits, power, strict new DFE voltage,
whole magnitude/body and varactor envelopes. Keep signed Rs-switch findings.

Select the smallest squared normalized target error among physically valid
rows within .5 dB of 9 dB and 100 MHz of 1.9 GHz; deterministic R/C tie break.
These are unchanged internal target tolerances, not relaxed limits.
No candidate outside the registered set. No frozen RL or held-out changes.

This only finds a loaded AC candidate. Do NOT transfer earlier noise, HD3,
eye/PVT or runtime claims to the newly selected controls. Independently
verify a selected candidate before promoting it. No nine-target map/full
rectangle, periodic noise, layout, passive nonlinearity or receiver signoff.

Full prior Entry 141 archive plus Entry 138 static manifest and all source/
PDK hashes precede SPICE. Snapshot exact sources and honest dirty Git parent.
Same 3305/1019.90 s before-change full baseline, failure-first and focused
pre-run tests, full post-result suite before local commit. Entry 141 raw replay
and related checks pass 49 tests in 27.89 s. No simultaneous full suite/SPICE.

Run once in product_audits/entry142_dfe_loaded_calibration_20260910/.
Preserve all results/failures. No product/report edit or public upload.
