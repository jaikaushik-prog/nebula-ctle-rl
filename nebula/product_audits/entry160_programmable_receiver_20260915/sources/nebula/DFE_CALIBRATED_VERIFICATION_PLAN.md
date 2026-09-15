# Entry 143: independently verify the calibrated primary controls

Registered 2026-09-10 after Entry 142 measures all 65 loaded OP/AC pairs in
one 33.4446967 s call (2.619166 s preflight). It selects R=.70 VDD, C=.185 VDD:
8.74388276 dB boost, 1.903117755 GHz peak. Keep the unchanged .5 dB/100 MHz
internal target tolerances. Only external C control differs from old .165 VDD.

Exactly seven calls maximum, 180 s each, no retries or retuning:
1-2: full OP/AC/10 MHz-5 GHz noise, held states 0 and 1, negative initial guess.
3-6: unchanged clocked 100 MHz/100 mV differential peak, 150 ns, Gear-2,
      relative tolerances 2e-5/1e-5 crossed with 5/2.5 ps steps.
7: connected physical 5 Gbps decoding of the old 7.5 dB constructed channel,
   same 80-bit pattern/64 scored bits, phase 1 UI, DAC code 2, normal feedback.
Run all seven once and retain every failure.

Same measured transistor geometry, models, clocks, source and outputs.
Static analysis retains old strict settings. The released initial guess uses
the original accepted reference. The link deck retains its old physical
initialization and solver. Only the two R/C source values are parameterized.

Reuse the EXACT frozen voltage/static/tone formulas with explicit target
argument instead of index, and EXACT frozen RC-control audit with explicit
control arguments. Source-comparison tests enforce this mechanical boundary.
No invented values are passed to an old hardcoded control check.

Require both static states valid, negative branches, noise/power/voltage and
target match. State 0 must also match the selected raw DC/complex AC/power
calibration. Require all four tone gates and all six pairwise .5 dB/1% checks.
Require fresh link acceptance: every scored bit correct, eye above 100 mV/
.4 UI and existing voltage/power conditions. Full nominal pass requires all.

The result does not transfer the earlier 45-case PVT to these new controls.
Analog PVT, periodic receiver noise, positive held branches, nine-target map,
runtime-with-DFE, generic-poly nonlinearity, layout and full receiver signoff
remain unverified. No product/report promotion at this stage.

Verify complete Entry 142 raw manifest and Entry 141 archive and all source/
PDK hashes before SPICE. Freeze copied sources, SHA-256 and honest dirty Git
parent. Same full before-change baseline 3305/1019.90 s; failure-first and
focused pre-run checks, full post-result regression and audit before commit.
Entry 142 focused pre-run: 42 passed in 34.16 s. Prior calls separately billed.

Run once in product_audits/entry143_dfe_calibrated_verification_20260910/.
Retain raw failures and lossless waveform archives without deleting originals.
No public upload until the contradictory privacy instructions are resolved.
