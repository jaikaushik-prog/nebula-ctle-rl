# Entry 131: finer control map on measured N250/N500 physical geometries

Registered 2026-09-10 after Entry 130 completes all nine instrument checks.
The coarse R grid skips directly from 0.7 to 0.85 VDD; observed N100/1.5pF
peaking at C=0.1 VDD drops from 8.984827 to 2.176083 dB. Measure intermediate
control voltages rather than assuming the missing 3/6 dB settings work.
N250/no-fixed-MIM demonstrates both controls within shape limits; N500/no-
fixed-MIM reaches lower frequencies. Carry ONLY those two already measured
geometries forward, in N250 then N500 order. No topology or sizing changes.

R control fractions: 0.65..0.85 inclusive, step 0.01 (21 values).
C control fractions: 0..0.30 inclusive, step 0.015 (21 values).
441 Cartesian pairs per geometry, changed as external DC sources on one
candidate plus the unchanged fixed reference. All original model/source
definitions, output load, TT conditions and precision settings are retained.
Maximum TWO sequential ngspice_con processes, 180 s each, no retries. Each
completed call has 441 OP and 441 AC analyses (maximum 882 each). Stop after
the first call if its instrument/reference checks fail; otherwise run N500.

Require exact per-step files, finite 251-point complex AC, unit differential
input, exact DC controls, positive supplied power, the unchanged 1e-9 DC and
1e-6 dB AC fixed-reference gates, and the same physical envelope/shape gates.
The new per-step DC parser reads actual primitive columns, never substitutes
old-grid control values or invents measurements. Test malformed columns,
nonfinite values, wrong controls and reference drift before SPICE.

Probe nine target identities: peaking 3/6/9 dB x peak 1.5/1.9/2.25 GHz.
A target exists only if a measured setting passes ALL electrical/AC gates
and lies within 0.5 dB AND 0.1 GHz of that target. Choose its setting by
minimum squared normalized error, then lower R and C control on exact ties.
Rank geometry by most found targets, then smallest mean normalized error
over found targets, then smaller geometry subtotal. A geometry must include
the 9 dB/1.9 GHz identity to be selected. Select none if either instrument
fails. Report every missing identity explicitly in the source result; do not
claim full 3-12 dB x 1.25-2.5 GHz coverage from this nine-identity screen.

Pin Entry 130 complete manifest, its unchanged sources and external PDK
closure; retain every failure and prior cost. Full regression and local
freeze before one run into `product_audits/entry131_configurable_rc_fine_20260910/`.
This is deterministic characterization, not RL training or held-out tuning.
Selection does NOT automatically verify DFE loading: register the connected
transistor experiment separately after these actual measurements exist.
No runtime settling, PVT, noise/HD3, layout or reliability claim is made.
