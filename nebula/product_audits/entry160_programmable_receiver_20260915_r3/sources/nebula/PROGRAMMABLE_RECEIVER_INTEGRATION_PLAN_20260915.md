# Selected receiver programmable Rs Cs integration

Owner authorization: 15 September 2026, separate prototype with possible evidence-based incorporation, total time limit 2.5 hours. Start 12:04:35 UTC; hard stop 14:34:35 UTC (20:04:35 IST). Reserve the final 30 minutes for focused checks, presentation and handoff. No scientific launch after 14:04:35 UTC. The earlier Entry158 two-call limit is exhausted and is not reused: this is a new authorization and experiment.

## Circuit and scope

Start with accepted run 4608cf1c525f4e59b2d5226059b0ce5d, fixed physical CTLE setting352, and its existing generated transistor DFE. Preserve that run and every historical artifact byte-for-byte. Create a derived receiver with a new identity. Replace only Xrs/Xcs with the existing configurable_rc.added_lines((500,0.)) network: physical poly resistance, NMOS controlled branch, control feed/bypass and two native-multiplier SKY130 varactor arrays. Use the existing full official library because the trimmed CTLE library does not contain the varactor. Keep amplifier, attenuator, bias, DFE devices, clock phase1UI, tap2/sign1, external 7.5dB constructed channel and 5Gbps pattern unchanged. No PMOS correction, model-bound change, new RL training or topology beyond this approved tuning integration.

Expose rctrl/cctrl in the export, not ideal parameter substitutions. All controls come from existing registered and measured fine-grid settings. Reuse Entry158's 29 distinct proposals and baseline brackets for initial screening; include the existing .73/.195 pair if not already present. The target is the selected request 6dB/2.1GHz. Selection is deterministic measured calibration, not an RL action or an increase in existing 4/12 target-grid coverage.

## Instruments and acceptance

Tests precede implementation. Preserve exact selected-deck hash, unchanged retained element lines, one model-library definition, external control identity and no inherited verification badge. Fresh calls use direct-to-disk logs, exact decks and .spiceinit, timeout <=180 seconds, serialized simulator lock and charged-call ledger. The hard wall-clock limit overrides remaining planned work. Never overwrite/retry an existing measurement directory or conceal a failed call. Independent cases after a retained failure require an explicit case identity and stated purpose.

First measure nominal held clock0 and1 OP/AC with released negative-latch NODESET guesses from the existing measured reference. Verify the actual solved branch, stimulus, all terminal primitives, positive power, finite response, known-warning/abort rules and complete frequency axis. The first/last identical control repeats must agree to existing 1uV node, 1e-4 complex-response and 100nW power tolerances; these are new-DUT repeatability checks, not old-DUT equivalence. Every physical failure remains a failure even if instrumentation is valid.

Choose only a measured control that matches both held states within existing internal 0.5dB/100MHz tolerances and passes existing AC shape, magnitude/body envelope, new-DFE signed bounds and varactor envelope. Minimize worst-state normalized squared target error; ties use smaller R-control then C-control. Report whole-circuit signed limits separately and do not waive known bilateral-switch or attenuator violations.

If a matching control exists, perform a fresh complete nominal 64-scored-bit transistor transient at that control, using the existing waveform/timing/DFE analyzers plus exact control and all-device terminal checks. No fixed-circuit 315/315 or independent-reference45/45 result transfers. Add held-state noise at the chosen control only if time permits. Clocked HD3 or additional PVT is conditional on valid instruments and a meaningful scientific purpose; no broad PVT on an already model-domain-invalid circuit merely to accumulate green cells.

## Product decision

Structural integration alone is EXPERIMENTAL_UNVERIFIED. A passing response and signal check can be reported as nominal measured behavior, but any signed model-domain failure prevents nominal receiver signoff. Full receiver verification is false unless every required same-circuit gate is actually established. Setting352 remains the default and fallback. A read-only, hash-bound experimental variant panel may expose the new circuit, control values, measurements and failures. It must not relabel the accepted setting352 or offer unsupported live tuning. Report additions, if warranted, must preserve earlier report versions and undergo document rendering/visual review.

No email, commit, push or submission; no full regression or archive build. Record the exact completed evidence, elapsed time and remaining limitations in HANDOFF.md.
