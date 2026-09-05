# Entry 101: fixed setting 490 validation (6 September 2026)

Owner approved the proposed next step. Scope: validate, before product adoption.
Request is 9 dB / 1.9 GHz. Fixed candidate is 490 (A7/B42); it was the only
all-condition passing intersection in the existing development bank. This is
classical bank selection, not a new RL proposal or a held-out performance claim.

Reuse Entry 100's unchanged `measure_fixed` and `summarise_fixed`: 45 PVT
corners, one committed load, seven constructed channel losses, two HD3 tones
(existing 100 MHz/0.1 V peak checklist and operating-point 2.5 GHz drive),
four existing DFE policies and 1e-9 ideal-control agreement. One captured
nominal export plus 90 corner calls: **91 SPICE calls maximum**. Disable
bypass-changing retries. No extra request sweep, training, topology change,
range change, threshold relaxation or FINAL exposure. Stop attribution if
circuit signatures differ. Preserve all failures and refuse overwrite.

Prediction: all 315 current model conditions will pass, including the two
peaking corners missed by 425. Whether the no-DFE eyes still all pass is an
open measurement, not an assumed conclusion. Full area and receiver hardware
remain unverified regardless of outcome. Do not replace the existing demo's
425 evidence with 490 numbers. A fixed-robust export-selection integration is
the next step after this validation, not part of the validation itself.
