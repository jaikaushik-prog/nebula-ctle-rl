# Entry 138: initialize the loaded analog operating point

Registered 2026-09-10 after Entry 137 stops after two calls. State 0 emits
gmin convergence warnings, including "Last gmin step failed"; those data
remain rejected. State 1 is valid and meets broad S3/noise/power model limits,
but its 1.750132 GHz peak misses the requested 1.9 GHz identity tolerance.
Do not whitelist the warnings or relabel the old experiment as passing.

This is a six-call maximum initialization investigation, not a new circuit.
Same Entry 137 primary .7/.165 controls, devices, output load, physical
reference, code 2, clock phase, precision, source amplitudes, analysis bands,
strict warnings and all measurement thresholds. Do not repeat the other
eight old control settings yet; initialize the instrument first, then
register any loaded tuning-map correction based on accepted measurements.

Add ONLY one .nodeset line with df_q, df_qb, df_mp and df_mn initial guesses.
Negative-polarity values come exactly from the accepted Entry 137 state-1
DC primitives. Positive-polarity guesses swap the two members of each
differential pair. This swaps guesses only, never transistor terminals.
ngspice releases these preliminary constraints before its final solution.
No .ic, UIC, ideal decision source, forced bit, changed device, changed
feedback sign, or behavioral replacement is allowed. Record actual solved
stored differential voltage; require the requested sign times this value
to exceed 100 mV to confirm a resolved branch. This is an internal
operating-point check, not an NRZ eye or hardware reset requirement.

Maximum six sequential ngspice_con calls, 180 s each, no retries:
1. Held state 1, negative stored branch, with the new initial guesses.
   Require the unchanged instrument and resolved branch. Also require
   calibration against the accepted prior state-1 snapshot: every saved
   DC node within 1 uV, complex AC ratio error <=1e-4 over all 251 points,
   input noise within 0.1%, and VDD power within 100 nW.
   Stop after one if invalid or calibration fails.
2. Held state 1 positive branch, state 0 negative branch, state 0 positive
   branch. Run all three, retain failures. Stop after four total if any
   instrument or resolved-branch check fails.
3. Two clocked 150 ns, 100 MHz / 100 mV differential-peak distortion runs,
   5 ps and 2.5 ps maximum steps, negative initial guess. Confirm actual
   t=0 stored polarity, then reuse the unchanged Entry 137 full-waveform,
   harmonic-window, power, voltage and time-step agreement checks.

Keep the 1.9 GHz target-match flag separate from broad S3/noise/power/HD3
model acceptance. Do not silently revise controls to improve that flag.
Model HD3 does not close generic-poly voltage-coefficient limitations,
and held-clock noise is not periodic receiver noise or a switching bound.
This does not prove hardware power-up/reset, all tuning points, analog PVT,
full target rectangle, BER, layout or full receiver signoff. The old
45/45 NRZ PVT result is separate and must not be promoted to these new metrics.

Method reference: ngspice 41 manual, section 15.2.1, NODESET:
https://ngspice.sourceforge.io/docs/ngspice-41-manual.pdf
The preliminary node restrictions are released before the final solution.
Actual installed binary, model hashes and raw results remain authoritative.

Verify the entire 84-entry Entry 137 raw manifest, its complete source
closure, accepted calibration result and AC primitive file, and the same
external PDK closure. Snapshot every new/old scientific dependency and the
exact calibration primitives. Failure-first tests, focused/full regressions
and local source freeze precede one run into:
product_audits/entry138_dfe_loaded_initialization_20260910/
Retain every raw failure and archive any large traces losslessly without
deleting originals. No new report/product/RL edit and no public upload.
