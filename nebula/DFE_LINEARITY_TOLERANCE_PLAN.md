# Entry 141: four-way numerical tolerance recovery

Registered 2026-09-10 after both Gear-2 Entry 140 traces also abort inside
xrc_var_s1.p2. Entry 139 and 140 remain failed instruments, not HD3 results.
Hypothesis: the very tight numerical tolerances of this new analog test
interact poorly with the official varactor subcircuit. No device is changed.

Exactly four calls, maximum 180 s each, no retries. Keep Gear order 2,
150 ns duration, input sine 100 MHz / 100 mV differential peak, real DFE
clock, code 2, external R/C controls, released initial guess and all devices.
Replace ONLY the Entry 137 tolerance line. Relative tolerances 2e-5 and 1e-5,
each at maximum timesteps 5 and 2.5 ps; voltage tolerance 1e-7 V and current
tolerance 1e-12 A. Both relative tolerances remain 50-100 times stricter than
the documented default .001; voltage tolerance is ten times stricter than
the documented default 1 microvolt. These facts alone do not prove accuracy.
Reference: https://ngspice.sourceforge.io/docs/ngspice-43-manual.pdf, section 11.1.

Run every registered case once. Require ALL FOUR valid, complete 150 ns
waveforms, unchanged input/clock primitives, starting polarity, warnings,
voltage/power gates and HD3 below -30 dBc in all old windows. Require pairwise
agreement for all six pairs: HD3 within .5 dB and fundamental within 1%.
No best-case selection or threshold relaxation. Explicit abort rejection.
No extrapolating a partial waveform. Keep generic-poly nonlinearity,
periodic receiver noise, all static states, target map and analog PVT unverified.

Verify full Entry 140 archive and frozen source/PDK hashes. Copy and SHA-256
freeze all sources before calls; record dirty Git-parent provenance.
Same before-change full baseline 3305 passed / 1019.90 s; failure-first and
focused checks before run, full mandatory post-result regression before local
commit. No source changes during run and no public upload. Retain old failures.

Run once in product_audits/entry141_dfe_linearity_tolerance_20260910/.
