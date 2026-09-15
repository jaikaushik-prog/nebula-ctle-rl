# Bounded continuous-Cs coverage pilot - 15 September 2026

Registered before implementation and measurement. The owner explicitly authorized
target-coverage improvement; the lead approved exactly the three candidates below
and a simulator slot after focused tests pass and no simulator/recovery job is
active. This is a new experiment, not a rewrite of the completed 37-workflow
campaign or the frozen 512-setting bank.

## Evidence and hypothesis

For 6 dB / 2.5 GHz, base setting 480 passed 308/315 fresh conditions. Its only
failed specification was S3 frequency band at FF / 1.05 VDD / 0 C: peak frequency
2.519638491 GHz, 0.786% above the unchanged 2.5 GHz ceiling. Slowest corner was
SS / .95 VDD / 125 C at 2.067071938 GHz, above the unchanged target-match lower
bound 2.5 GHz * 2**(-.3) = 2.030630991 GHz. A small downward shift may fit both.
This is a hypothesis, not a predicted pass. Increased Cs can also change boost.

Source: `product_audits/submission_recovery_20260915/coverage_005_6db_2p5ghz_rl_r0/output/physical_recovery/candidate_01_setting_480/result.json`.
A read-only scan of the hash-checked legacy bank found only 480 fully eligible.
Next candidates 408, 344 and 416 missed 56, 63 and 70 legacy conditions; 481
missed 126. Existing physical setting 352 has a 1.882 GHz slowest peak and cannot
simply be relabeled as meeting the 2.5 GHz request.

## Fixed candidate set and unchanged science

Use the exact base-480 normalized coordinates and attenuator code 7. Change only
Cs through the existing `contract.ACTION_SPACE` coordinate conversion and the
canonical drawn-passive generator. Existing Cs target is 1.6846486662527978 pF.

| Candidate identity | Cs factor | Target Cs (pF) |
|---|---:|---:|
| base480_cs1p01 | 1.01 | 1.701495152915326 |
| base480_cs1p02 | 1.02 | 1.718341639577854 |
| base480_cs1p03 | 1.03 | 1.735188126240382 |

These values stay inside the approved current 0.1-10 pF contract domain; no
range, reward, tolerance, topology, load, voltage, initialization or solver change.
They are new continuous refinements, not previously measured 512-bank settings.
Record `bank_setting=null`, `bank_code=null`, `base_setting=480` and the explicit
candidate identity. Internal reused fixed-circuit records may carry that text
identity in their `setting` field solely to verify one unchanged candidate;
never assign a new integer bank code or invent legacy-bank eligibility.

Use a separate adapter/runner. Reuse the canonical capture, reference calibration,
OP/AC/noise, S4 and Nyquist distortion/swing, device-to-link conversion, seven
channel losses and strict fixed 45-corner acceptance functions. The full gate
is the unchanged physical electrical/model gate plus requested target match;
S7/full receiver remain excluded. No synthetic physical pass or cached result.
Each candidate retains one geometry across all 45 corners and seven losses.

## Calls, stopping and evidence

Run all three candidates in listed order even if an earlier candidate passes or
fails. Each gets the complete existing 137-charge procedure (one legacy export,
one physical-reference calibration, three measurements per corner), maximum
411 charged invocations. No simulator or candidate retry; transient progress-file
replacement handling stays at the already hardened product implementation.

Budget: 900 s total wall time; historical comparable candidates took about
67-100 s, so three are estimated at 4-6 minutes including setup. Reserve the
full existing simulator timeout before each launch: 120 s for canonical export,
60 s for every other invocation. If the remaining wall budget cannot fit it,
stop for budget and preserve incomplete evidence; this is not favorable stopping.
An infrastructure exception remains a failure; continue the other registered
candidates if budget permits. A budget exception stops the campaign.

Fresh output only: `product_audits/continuous_cs_coverage_20260915/`. Refuse an
existing output. Hold the shared recovery exclusion lock. Snapshot source, this
plan, base-result/deck identities, exact simulator and PDK include closure hashes;
verify sources/PDK unchanged at closeout. Keep all logs, failures, call-charge
ledgers, candidate and aggregate results, and raw-file manifest. Distinguish
charged invocations from confirmed simulator starts. Report all three outcomes,
not just a winning design. No later expansion is automatically authorized.

Before measurement: failure-first tests for exact factors, only-Cs changes,
unchanged measurement/gate source, identity and membership failures, all-three
scheduling after success, partial failure billing and budget refusal. No SPICE
until these pass and lead-controlled simulator-slot conditions are satisfied.

This may improve one exposed target in the measured grid. It is not an RL
speedup/generalization experiment, a full-range coverage proof, a layout-area
signoff or analog PVT closure of the separate transistor DFE checkpoint.
