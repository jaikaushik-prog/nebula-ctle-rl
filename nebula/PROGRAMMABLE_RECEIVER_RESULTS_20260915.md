# Programmable receiver integration results

The selected-derived programmable receiver is implemented and exposed in Nebula as an experimental option. It is included as a separate saved option in matching future 6 dB / 2.1 GHz exports. The accepted fixed-Rs/Cs setting-352 CTLE remains the primary submission. No old circuit, result, receipt or acceptance threshold was replaced.

## What was added

`nebula/programmable_receiver.py` retains the selected amplifier, input attenuation, bias and established transistor DFE. It replaces the fixed source-degeneration Rs/Cs with the existing physical poly-resistor/NMOS branch and two SKY130 native varactor devices with multiplicity 500, including their physical feed and bypass network. The measured circuit has 73 SKY130 device instances, not 73 MOSFETs. External sources still supply clock, tap and R/C controls.

`nebula/programmable_option.py` binds the option to the exact accepted CTLE hash and the measured review. The application shows it under **Design explorer > Programmable receiver option — experimental**. Its exact measured deck, named-net device drawing, response/eye plot, control selection record, waveform and terminal voltages are directly accessible. The panel remains separate from the fixed selected receiver and independent 9 dB reference.

Matching new workflow exports add `receiver_programmable/receiver.cir`, `receiver_programmable/device_sheet.svg` and `receiver_programmable/metadata.json`, with hashes in the workflow receipt. These are copies of the saved measured option, not new transistor verification of each export. Other parents/requests do not inherit this calibration. The main `design.cir` remains the fixed accepted CTLE. The export tests use temporary output directories and do not run a new design.

## Nominal measurements

At TT / 1.8 V / 27 C, R control is 1.314 V (0.73 VDD) and C control is 0.378 V (0.21 VDD).

| Measurement | Result | Scope |
|---|---|---|
| Loaded peaking | 5.614715 / 5.618116 dB | Held-clock states 0 / 1 |
| Loaded peak | 2.068083 / 2.070592 GHz | Both states match 6 dB / 2.1 GHz within the pre-existing +/-0.5 dB and +/-100 MHz tolerances |
| Clocked decisions | 64 / 64 | Finite scored pattern, constructed 7.5 dB channel, external phase 1 UI and tap code 2 |
| Sampled eye | 325.629067 mV | Transistor summer waveform |
| Positive aperture | 0.720 UI | Limited by the registered scan extent |
| Aperture above 100 mV | 0.680 UI | Separate height-qualified width definition |
| VDD draw | 9.264265 mW | Clocked receiver; external generators excluded |

Three measured C controls at fixed R control give approximately 1.955, 2.069 and 2.169 GHz loaded peaks. This is a set of fixed-control snapshots, not a runtime retuning test or full tuning-range demonstration. Selection among the three controls is deterministic measured calibration, not RL. End-to-end grid coverage remains 4/12.

## Retained evidence and failures

Eight charged ngspice calls were used in this task. No additional science was run during app/report closeout. All outputs remain in six distinct Entry160 directories under `nebula/product_audits/`:

| Run suffix | Calls | Outcome |
|---|---:|---|
| `entry160_programmable_receiver_20260915` | 0 | Preflight rejected an unregistered control pair before simulation |
| `entry160_programmable_receiver_20260915_r2` | 1 | Held-state initialization unresolved; instrument invalid |
| `entry160_programmable_receiver_20260915_r3` | 1 | Revised held-state initialization still unresolved; instrument invalid |
| `entry160_programmable_receiver_followup_20260915` | 2 | Clocked signal result obtained; separate analog call rejected for convergence warnings |
| `entry160_programmable_receiver_measured_seed_20260915` | 3 | Clocked-waveform-derived initial guesses; both held-state batches and chosen-control clocked link produce valid measurements |
| `entry160_programmable_receiver_analog_20260915` | 1 | Noise instrument rejected for convergence warnings; remaining analog calls stopped |

The early generic `NO_MATCH` statuses must not be read as valid electrical rejections: initialization was invalid. The successful held-state analysis used internal voltages from the actual clocked receiver as released `.nodeset` guesses, not forced ideal decision sources. Repeat-control DC/AC/power checks remained unchanged.

The independent read-only review recomputes the two held-state datasets, exact control choice and clocked link metrics, checks 775 archived files, and verifies that the original accepted parent files are unchanged. The generated LF deck matches the Windows-newline measured deck after newline normalization; downloads serve the exact measured bytes.

- Review: `nebula/product_audits/entry160_programmable_receiver_review_20260915/review.json`
- Review SHA-256: `f41a0255f6167ceb291aaf6ed359f53b1a800468123deb2591c949e98773e147`
- Exact measured receiver SHA-256: `e7323661f9e47b7bb941c3b996bfc7ed7bf2369495abcf526bb693ee5deabbda`
- Unchanged accepted CTLE SHA-256: `e8f8b0c82e6d797ce6baff14b2df551812915ad575a5b4a6871757b0cce4eaed`

## Verification still required

Nominal AC and signal gates pass, but full receiver verification remains future work. Seven instances violate documented signed model-domain limits: six attenuator PMOS devices and the bilateral Rs NMOS switch. No passing noise value is credited; HD3 and PVT for this derived circuit were not completed. There is no periodic-noise, BER, runtime tuning, routed-area, integrated clock/control-power, reliability or complete target-range claim. Nothing in the independent 9 dB reference transfers its PVT result to this receiver.

## Closeout checks

Focused tests passed: baseline 16 in 5.96 seconds; final 26 in 3.12 seconds, including exact optional export and receipt assertions. The broader suite was deliberately not rerun under the owner's deadline direction. Browser checks at 1440x1000 and 1280x900 show the panel and all eight direct artifact links, hide it for an unrelated failed parent and show it for the second matching accepted parent. Unknown and malformed artifact paths return 404. There were no page errors, horizontal overflow or non-GET application requests in this saved-evidence check. The final panel width and typography were visually inspected. An actual browser download click produced the exact measured deck hash. A user-reported generic unavailable state was not reproduced on the current server (HTTP200) or a fresh browser; the panel now uses no-cache fetch, displays HTTP error details and offers Reload saved evidence. An injected404 followed by a retry successfully reloads the evidence without simulation.

Read-only submission preflight remains PASS: 1,240 accepted-run attempt artifacts and 11 prior evidence rows checked, zero simulator launches and zero files modified. This existing preflight is distinct from the new 775-file programmable review.

The academic report update is `output/docx/Nebula_Academic_Final_Report_20260915_v2.docx`:12 visually reviewed pages,3905 words and12 figures, SHA-256 `d40cc1cf297fe317b1ac7e9c414a54c7ec777d0d555d62965ba94a9e7b4ed17f`. The original Word report, entered member names, older PDFs, old demo narration and all earlier scientific records remain preserved. Recording and submission are owner actions. No training, full campaign, archive packaging, commit, push, email or publication was performed.
