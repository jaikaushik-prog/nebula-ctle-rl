# Entry 129: bounded serial-bias instrument recovery

Registered 2026-09-10 while the frozen Entry 128 screen completes. Do not
alter that running source, retry its calls, or rewrite its failed evidence.
Entry 128's fixed-CTLE calibration matches all 251 original AC samples to
5.4362e-11 dB maximum error. Its large simultaneous-copy candidate decks
have hit their 60 s limit before producing OP/AC data. The old timeout
handler then raises a str/bytes concatenation TypeError instead of writing
the captured log. These are instrument failures, not measured CTLE failures;
missing captured output cannot be reconstructed and must stay disclosed.

## Recovery scope

Keep all nine physical geometries, all 81 R/C voltage pairs, the full PDK,
the existing AC/DC parsers and every electrical/shape threshold unchanged.
Instantiate only ONE tunable circuit plus ONE unchanged fixed control.
Change only the external Vr0/Vc0 voltage sources with ngspice `alter`, then
run/save OP and AC separately for every bias pair. No `alterparam`, model,
drawn geometry, device size or passive substitution is allowed.
The official control-language syntax is documented at:
https://ngspice.sourceforge.io/ngspice-control-language-tutorial.html

This demonstrates a single netlisted circuit under distinct DC control
settings, not transient runtime settling. DFE loading, noise/HD3 and later
PVT/receiver integration remain separate stages. All Entry 128 model-domain,
external-source, area and typical-passive qualifications remain unchanged.

Maximum NINE fresh ngspice_con processes, sequential, 180 s each, no retry.
First run the first registered geometry, N100/fixed0pF. Require all 81 pairs,
both-circuit primitive vectors and baseline comparisons before promoting
the instrument to the remaining eight geometries. Shape-spec success is
not required for this instrument gate. If the first instrument call fails,
stop after one. Otherwise retain all eight later calls including failures.
Bill both processes and analysis work: each completed call has 81 OP and
81 AC analyses (maximum 729 each), not one candidate evaluation.

Stream stdout/stderr directly into the retained log file before starting
the process. On timeout, retain that file and any partial tables and raise
an explicit timeout result; never concatenate TimeoutExpired text/bytes.
Test timeout retention and silent-error rejection before SPICE. Existing
frozen invoke helpers remain unchanged for reproducibility.

For each voltage setting save its own op_NNN.txt and ac_NNN.txt, exact
layout, input AC=1 and external DC controls. The fixed control's AC must
match the original saved baseline within 1e-6 dB at EVERY step. Its DC
vectors must stay unchanged within 1e-9 absolute units across steps.
Assemble the 81 ACTUALLY MEASURED candidate OP/AC records, plus the checked
fixed control, into the existing Entry 128 parser layout. No synthesized,
copied substitute or imputed candidate measurements are permitted.
Tests must reject missing steps, shifted controls, drifting baselines,
malformed columns, missing vectors and timeout/silent failures.

Verify Entry 127's complete raw manifest and Entry 128's finished manifest
and successful fixed calibration first. Pin all source, prior and external
PDK hashes; keep the original CTLE export and both prior runs unchanged.
Freeze after focused/full regression, then run once into
product_audits/entry129_configurable_rc_serial_20260910/.
