# Submission analog PVT evidence (14 September 2026)

The separate second attempt executed all twelve registered calls. Nominal TT /
1.8 V / 27 C reproduced the frozen six-measurement result and passed the
combined analog model gate. FS / 1.71 V / 125 C failed the required resolved
negative-branch initialization in all six measurements. Its finite electrical
outputs are diagnostics, not validated held-branch analog evidence. No analog
PVT extension or full receiver pass is claimed. The first interrupted attempt
remains preserved and billed separately.

## Preserved interrupted attempt

[Interruption closeout](product_audits/submission_analog_pvt_20260914/pilot/interruption_closeout.json)
records four exact raw replays, five observed launches, one incomplete tone,
and seven never-launched calls. The fifth call log ends around 86.29 ns of
150 ns with no completed trace/result. No Python/ngspice process remained at
closeout; the precise process termination cause is unestablished. This is an
incomplete execution, not a measured stress-corner electrical failure.

| Completed nominal measurement | Result | Scope |
|---|---|---|
| Held clock 0 / 1 peak boost | 8.7439 / 8.7469 dB | CTLE output, negative resolved branch |
| Held clock 0 / 1 peak frequency | 1.9031 / 1.9063 GHz | Original AC sweep and peak interpolation |
| Held clock 0 / 1 Nyquist boost | 8.6414 / 8.6458 dB | 2.5 GHz relative to 1 MHz |
| Held clock 0 / 1 input noise | 0.654051 / 0.654039 mVrms | 10 MHz-5 GHz held-state small signal |
| Held clock 0 / 1 VDD draw | 9.2763 / 9.2807 mW | External clock/control sources excluded |
| HD3 reltol 2e-5, maxstep 5 / 2.5 ps | -54.9143 / -54.9201 dBc | 100 MHz, 100 mV differential peak, 50-150 ns |

All four completed measurements passed their instrument/initialization checks
and matched the frozen nominal replay. Both static measurements passed their
broad analog/positive Nyquist and internal target checks; the two completed
tones passed their individual HD3/window checks. The other two numerical tone
settings did not complete, so no new four-setting HD3 agreement or corner-level
combined analog pass is claimed from this interrupted attempt.

Completed simulator time was 166.675 s; the last durable progress elapsed time
was 181.684 s. Neither includes the incomplete fifth call or interruption. Full
campaign and incomplete-call wall times are unknown. All five launched calls
are billed separately from the second attempt.

[Archive review](product_audits/submission_analog_pvt_20260914/interruption_archive_review.json)
verified 125 manifest files and four lossless gzip trace siblings. Original raw
bytes remain on disk: 274,359,540 bytes; gzip siblings total 81,423,406 bytes.
Manifest SHA-256: `8e6c7e4002fce98c023b916646bd7b2a2261aaf17843abf9d183d2d05e95d156`.
Source snapshot/config identities (90 files) and external PDK closure matched
at closeout. The later scheduling-only second-attempt source change does not
rewrite the first attempt's authoritative snapshot.

## Completed second execution: initialization failure at FS

[Immutable summary](product_audits/submission_analog_pvt_20260914/second_attempt/summary.json)
and [independent archive/aggregate review](product_audits/submission_analog_pvt_20260914/second_attempt_review.json)
retain every row, validity flag and source path. Twelve calls finished; the
pilot validation flag is false because FS initialization failed. Only one
registered corner is instrument-complete; 44 of the 45 analog corners remain
unverified, including FS. The original finite/noiseless 45-corner link result
remains a separate measurement with different scope.

| Corner / held clock | Peak boost (dB) | Peak (GHz) | Nyquist boost (dB) | Input noise (mVrms) | VDD draw (mW) | Initialization |
|---|---:|---:|---:|---:|---:|---|
| [tt_vdd1.00_t27 / 0](product_audits/submission_analog_pvt_20260914/second_attempt/pvt_tt_vdd1.00_t27/static_state0_tol1e-05_step5ps/result.json) | 8.7439 | 1.9031 | 8.6414 | 0.654051 | 9.2763 | valid |
| [tt_vdd1.00_t27 / 1](product_audits/submission_analog_pvt_20260914/second_attempt/pvt_tt_vdd1.00_t27/static_state1_tol1e-05_step5ps/result.json) | 8.7469 | 1.9063 | 8.6458 | 0.654039 | 9.2807 | valid |
| [fs_vdd0.95_t125 / 0](product_audits/submission_analog_pvt_20260914/second_attempt/pvt_fs_vdd0.95_t125/static_state0_tol1e-05_step5ps/result.json) | 5.4777 | 1.4608 | 5.2068 | 0.778989 | 8.6248 | INVALID: unresolved |
| [fs_vdd0.95_t125 / 1](product_audits/submission_analog_pvt_20260914/second_attempt/pvt_fs_vdd0.95_t125/static_state1_tol1e-05_step5ps/result.json) | 5.4792 | 1.4629 | 5.2098 | 0.778989 | 8.6270 | INVALID: unresolved |

Static FS values above are diagnostic only. Both FS stored differentials were
approximately +0.22 microvolts, versus the registered q-qb < -0.1 V. The
released nominal NODESET is an initial guess; it did not establish the required
resolved state at this stress corner. Broad shape/noise/power checks alone
cannot override that failure. Both FS static internal 9 dB/1.9 GHz target
checks also missed. No branch forcing, corner tuning, solver change or retry
was used to hide the finding.

| Corner | Four HD3 values (dBc), frozen order | Numerical agreement | Combined analog model gate |
|---|---|---|---|
| tt_vdd1.00_t27 | -54.9143, -54.9201, -54.9137, -54.9197 | pass | pass |
| fs_vdd0.95_t125 | -62.2346, -62.2345, -62.2346, -62.2345 | pass | FAIL: initialization invalid |

HD3 order is reltol 2e-5 / 5 ps, 2e-5 / 2.5 ps, 1e-5 / 5 ps,
1e-5 / 2.5 ps. Stimulus and windows are unchanged. All FS tone runs also
started unresolved; their low HD3 and numerical agreement are diagnostics only.
The per-row source links are in the independent review.

Second execution: 12 simulator calls, 781.889 s summed simulator time, 835.492 s measured wall time, below the registered 1200 s launch budget. Across both attempts, 17 calls were launched; the incomplete first-attempt call still has unknown wall cost.

Archive verification passed for 175 manifest files and 16 lossless trace siblings: 1,135,238,316 raw bytes retained, 336,371,097 gzip bytes. All 91 source snapshots match config; the runner confirmed active sources and PDK unchanged through execution.

Second manifest SHA-256: `709e65586b10aa46ff29961dad454047f8a4e72c3dbaadfb07334e2e32f68f86`. Summary SHA-256: `da6095639be9f93349f00206aa2ec4b0ad06ac38a8b61d3154dfe6b71f8fe47b`. Archival followed simulator completion; no original captured file was overwritten.

## Separate second attempt and validation

[Second registration](DFE_ANALOG_PVT_SECOND_ATTEMPT_PLAN.md): same two corners
and twelve-call scientific protocol, fresh directory, maximum 1200 s wall and
180 s per call, full-timeout reservation, no in-run retries. Combined maximum
is seventeen launched calls across both attempts. Sources include both plans
and the explicit wall-budget option; original scientific sources remain frozen.

No-SPICE focused validation: **33 passed in 45.74 s**, including all six exact
nominal emitted-deck byte comparisons, mechanical supply-only parameterization,
raw static replay, failure/coverage gates, positive Nyquist rejection, and wall
budget bounds/full-timeout reservation. The original pre-pilot set had 27
passes; six tests cover the second attempt's scheduling-only budget option.
The lead owns the complete post-change suite and final release record.

## Limits on interpretation

Both attempts use the fixed 73-device integrated 9 dB checkpoint, R=.70 VDD,
C=.185 VDD, code 2, sign +1 and 1 UI external clock phase. They do not alter
the selected 3 dB product or tune corners. Held negative-branch noise is not
periodic receiver noise or all held branches. Typical passive process, ignored
generic-poly nonlinear coefficients, and signed bilateral Rs-switch model-domain
findings remain visible; passive nonlinearity/reliability are not verified.
External clocks/control/common-mode sources, no layout/mismatch, no runtime
DFE-active tuning and no statistical BER remain limitations. Even a successful
two-corner analog pilot would not establish 45-corner analog PVT or full
receiver/S9 signoff.
