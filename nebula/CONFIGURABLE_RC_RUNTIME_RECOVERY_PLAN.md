# Entry 135: G164-compliant AC endpoint recovery for runtime control

Registered 2026-09-10 after Entry 134 stops on its first static call because
`ac lin 2` emits only one row. Preserve the failed source, result and all
raw data; do not infer the absent 1.9 GHz point or rerun inside Entry 134.

Use the exact Entry 134 experiment and all of its gates, geometry, controls,
stimulus, times, solver tolerances, source checks and four-call maximum.
The only deck change is `ac lin 3 100meg 1.9g` in static references. Require
exactly three finite rows at 100 MHz, 1 GHz and 1.9 GHz with valid measured
input in every row. Retain all three; pass the actual first/last rows into
the unchanged two-frequency parser and runtime analyzer. The continuous
runtime deck must remain byte-identical to Entry 134's registered deck.

This is the existing HANDOFF G164 workaround, not an electrical gate change.
First-reference failure stops after one call, other reference failures stop
after three, and the continuous test is the fourth and final call only after
all references and distinct-setting gates pass. 180 s per call, no retries.
The earlier Entry 134 call remains separately billed.

Verify the full Entry 134 raw/gzip archive and unchanged source hashes plus
the original Entry 131 prerequisite. Freeze failure-first tests and passing
focused/full regression before running once into
`product_audits/entry135_configurable_rc_runtime_recovery_20260910/`.
Retain all raw failures and use the existing lossless archive helper.

This still covers standalone small-signal runtime tuning only. It does not
verify uninterrupted DFE decoding, runtime PVT, noise/HD3, BER or full
receiver signoff. All Entry 134 scope limits and external-source exclusions
remain. Do not change frozen RL, PDFs or old production exports.
