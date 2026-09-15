# Entry 158: bounded nominal loaded-tuning diagnostic

Owner approval: 15 September 2026, at most two ngspice invocations, each at most
180 seconds; no retry, training, full PVT, topology change or replacement of
setting352. Implementation and focused verification deadline:11:17:31 UTC
(16:47:31 IST), one hour after starting the approved task.

Purpose: determine which existing programmable Rs/Cs control settings retain
their target response after loading by the existing transistor DFE. This is
the independent N500/no-fixed-MIM programmable reference, not selected352.
The original four-of-twelve end-to-end physical target result is unchanged.

Use the exact Entry143 static deck bodies, with the two measured held-clock
states and released negative-latch nodesets. Preserve device sizes, netlist
body, model library, supply1.8V, temperature27C, solver options and source
definitions. Only alter existing VrcR/VrcC external DC controls during OP/AC.
No transient, noise or distortion analysis is added.

Targets:3/6/9/12dB x1.25/1.9/2.5GHz, evaluated as an exposed diagnostic using
the existing internal tolerances0.5dB and100MHz. Entry131's saved N500 table
has nominal standalone AC matches for10/12;3 and6dB at1.25GHz have no match.
For each matched target, start with its deterministic saved minimum-error
control. Include the next two already measured Cs controls at the same Rs,
where available, to test the known DFE-loading frequency shift. All such
controls are existing Entry131 rows; no new parameter range is introduced.
Deduplicate controls. The calibrated0.7/0.185VDD point brackets each batch,
first and last, as a drift/instrument check against Entry143 raw OP/AC.

Run held state0, then state1 only if the first instrument and baseline checks
pass. Each invocation must produce exactly its scheduled OP/AC files. Parse
finite primitives, unit AC stimulus, exact supply/control/held-clock values,
negative stored branch, positive power and the original physical voltage,
varactor and AC-shape checks. Compare both baseline snapshots with saved raw
values:all nodes within1uV, complex AC relative difference<=1e-4, power within
100nW. Stop on invalid instrument, warning/abort, incomplete files or timeout.
Retain every completed/failed row and all charged calls. No retry or extra
candidate batch. Emit a source/PDK/runtime fingerprint and raw-file manifest.

Select only among measured scheduled controls that pass the original model
gates in BOTH held states and meet BOTH target errors. Minimize worst-state
normalized squared error, then lower R and C for ties. A nominal AC match
does not verify eye, HD3, noise, runtime tuning, PVT or full receiver compliance.
Keep all signed terminal-model findings; envelope acceptance is NOT signed-
domain or reliability signoff. Report missing targets and failed instruments.

Use focused failure-first parser/schedule tests, not a full regression. No
historical report/evidence edits, export adoption or default-circuit change.
