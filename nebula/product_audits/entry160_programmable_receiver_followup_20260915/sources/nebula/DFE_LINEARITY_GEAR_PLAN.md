# Entry 140: bounded Gear-2 clocked distortion recovery

Registered 2026-09-10 after both Entry 139 runs abort at 2.6 and 3.89 ns
with "Timestep too small" in xrc_var_s1.p2. Neither reaches the required
150 ns endpoint; both remain rejected. Their two calls cost 60.9518274 s
including .0569598 s preflight. Four lossless gzip siblings retain partial
traces; originals are not deleted.

Hypothesis: the default integration method cannot complete this coupled
varactor/clocked-latch transient. Test ONLY adding
`.options method=gear maxord=2` to the unchanged Entry 139 decks.
This is a numerical-method hypothesis, not proof of circuit performance.
Gear and maximum order are documented in the official ngspice manual:
https://ngspice.sourceforge.io/docs/ngspice-manual.pdf

Exactly two calls, maximum 180 s each, no retries: 5 and 2.5 ps maximum
steps, same 150 ns duration, clock, source amplitude/frequency, four-node
released initial guess, physical devices and controls. Run both once.
Retain the exact old harmonic windows, strict warnings, actual time-zero
branch, primitive, voltage, power and resolution-agreement gates.
Explicitly reject timestep-too-small/aborted diagnostics before extraction;
do not modify the frozen common scanner or any prior evidence/source.

The required result is CTLE-output HD3 with transistor DFE actively clocking.
Gear numerical damping is addressed only by the existing two-step agreement
test, not independent hardware validation. No full receiver, periodic noise,
all-static-state, loaded tuning-map, passive nonlinearity or analog PVT claim.

Verify complete Entry 139 archive and all source/PDK hashes. Snapshot every
new and inherited scientific source before calls, recording dirty worktree
and actual Git parent honestly. No source edits during simulation.
Same before-change full baseline 3305 passed / 1019.90 s; failure-first and
focused tests precede run, mandatory full post-result regression precedes
local commit. Do not insert an unrelated intermediate simulation or retry.

Run once in product_audits/entry140_dfe_linearity_gear_20260910/.
Keep all failures and lossless raw evidence. No product/report/RL edits and
no public upload while the privacy instruction conflict is unanswered.
