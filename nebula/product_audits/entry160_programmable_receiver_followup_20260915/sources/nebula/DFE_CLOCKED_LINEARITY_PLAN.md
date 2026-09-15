# Entry 139: independent required clocked linearity measurement

Registered 2026-09-10 after Entry 138. Its held state-1 negative calibration
passes; held state-0 negative and positive branches are also valid. Only the
additional state-1 positive static diagnostic retains gmin warnings.
Entry 138's four-state gate remains FAILED and no full static/noise coverage
is inferred. That optional DC diagnostic is not an organiser requirement
and is not a prerequisite for a separate clocked transient from an accepted
starting state. No previous verdict, warning rule or threshold is changed.

Exactly two calls maximum, 180 s each, no retries or new device sizing:
use the BYTE-IDENTICAL Entry 138 negative-initialized tone decks, including
the original physical DFE clock, 100 MHz / 100 mV differential PEAK sine,
150 ns duration and 5 ps / 2.5 ps maximum time steps. Both registered calls
run once even if one fails. Reuse the exact frozen Entry 138 extractor,
Entry 137 harmonic/power/voltage/stimulus checks and resolution agreement.
No new measurement formula, source, clock, control value or solver option.

Require valid actual negative t=0 stored state, strict simulator warnings,
complete finite main/terminal waveforms, original source primitives, all
voltage/power gates, HD3 below -30 dBc in all three capture windows, half-window
agreement <=.5 dB, two-step HD3 agreement <=.5 dB and fundamental agreement
<=1%. The analysis is at the physical CTLE output with the transistor DFE
actively clocking, not at a hard-decision output.

The held-state-1 positive warning stays unverified. Periodic receiver noise,
generic-poly voltage-dependent nonlinearity, tuning-map accuracy, analog PVT,
BER, layout and full receiver signoff remain outside this result. In
particular the measured 1.75 GHz loaded peak is not promoted to 1.9 GHz.

Verify the complete Entry 138 raw manifest and all frozen circuit/analyzer
source hashes and the same external PDK closure before SPICE. Use its exact
reference_result.json and reference_ac.txt. The accepted state-0 negative
record and state-1 negative calibration are mandatory prerequisites.

Verification/provenance sequence for this orchestration-only change:
- Before-change full baseline: 3305 passed, 13 deselected, two known warnings,
  1019.90 s. Every reused circuit/analyzer was tested and committed at ca8cfb9.
- Failure-first tests for the new two-call schedule and complete prerequisites,
  plus focused old/new evidence and waveform checks, precede the run.
- Before either call, freeze all scientific sources into a content-addressed
  snapshot and record every SHA-256. No source edits during either call.
  Record the Git parent AND dirty-worktree flag honestly: the source
  snapshot, not a claim of a clean parent checkout, identifies the new wrapper.
- After the raw results exist, run the full mandatory regression and audit
  before committing the completed code/evidence/HANDOFF change. Never commit
  with test failures. This keeps the required before/after tests while
  avoiding a separate intermediate commit for an unchanged measurement method.

Run once into product_audits/entry139_dfe_clocked_linearity_20260910/.
Preserve failures; archive large traces losslessly without deleting originals.
No production/report/RL edits or public upload in this experiment.
