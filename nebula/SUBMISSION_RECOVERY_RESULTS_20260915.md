# Automatic recovery and matched runtime results - 15 September 2026

The registered campaign completed **37 workflows: 13 coverage checks and 24
matched benchmark runs**. All worker processes finished without parent timeout;
completion includes correctly refused and failed designs. The driver/deep check
and [independent final review](product_audits/submission_recovery_20260915/final_review.json)
passed. The frozen [summary](product_audits/submission_recovery_20260915/summary.json)
and [workflow ledger](product_audits/submission_recovery_20260915/workflows.jsonl)
remain authoritative. Summary SHA-256:
`be0c1d9b3e38f5a903b3bb740f8e3d96c3481b686d06dec679153bec9c845893`.

## Coverage and automatic recovery

Delivered coverage was **4/13** including the previously exposed 6 dB / 2.1 GHz
diagnostic request, or **3/12** on the registered rectangular grid: peaking
3/6/9/12 dB crossed with peak frequency 1.25/1.9/2.5 GHz. The three grid
successes were 3/6/9 dB at 1.9 GHz. Eight grid requests had no single eligible
fixed setting in the frozen legacy bank; this is not proof of physical
impossibility. The remaining grid request, 6 dB / 2.5 GHz, exhausted its sole
eligible setting 480 with 308/315 checks: peak frequency failed the S3 band at
FF / 1.05 VDD / 0 C for all seven losses. See its
[physical result](product_audits/submission_recovery_20260915/coverage_005_6db_2p5ghz_rl_r0/output/physical_recovery/candidate_01_setting_480/result.json).

For **6 dB / 2.1 GHz**, recovery automatically tried **288 then 352**, preserving
one unchanged circuit across all 45 corners and seven losses per candidate.
[Setting 288](product_audits/submission_recovery_20260915/coverage_012_6db_2p1ghz_rl_r0/output/physical_recovery/candidate_01_setting_288/result.json)
returned 314/315: at SF / 0.95 VDD / 0 C and 3 dB channel loss, modeled output
swing 909.8 mVpp exceeded the 869.6 mVpp linear limit, so eye results were
unmeasured. [Setting 352](product_audits/submission_recovery_20260915/coverage_012_6db_2p1ghz_rl_r0/output/physical_recovery/candidate_02_setting_352/result.json)
passed 315/315 without changing thresholds. Both attempts remain billed:
274 charged invocations and 166.085 s complete workflow time in this coverage
run. No manual candidate choice or simulator retry repaired the first result.

The independently read [delivered standalone design](product_audits/submission_recovery_20260915/coverage_012_6db_2p1ghz_rl_r0/output/design.json)
reports these nominal measurements for setting 352:

| Quantity | Nominal value |
|---|---:|
| Peak boost / peak frequency | 6.614732 dB / 2.159514 GHz |
| Input-referred noise | 0.524866 mVrms |
| CTLE plus physical reference power | 6.965787 mW |
| Behavioral eye at representative 7.5 dB channel | 337.519 mV / 0.859375 UI |
| Counted geometry subtotal, not layout area | 0.00734015 mm2 |

The target match uses the unchanged tolerances of 1.5 dB and 0.3 octave.
The captured physical deck SHA-256 is
`e8f8b0c82e6d797ce6baff14b2df551812915ad575a5b4a6871757b0cce4eaed`.

## Matched runtime and infrastructure caveat

Both arms used the same bank, eligibility rule, exact-target registry access,
acceptance thresholds, eight-candidate ceiling and output work. RL supplies its
eligible nominal proposal before deterministic recovery; classical uses ascending
eligible settings. An exact registry candidate has equal priority in both arms,
but never substitutes for fresh physical verification. Every accepted candidate
passed all 315 conditions and required artifact checks.

The parent timer covers fresh interpreter startup, parsing/imports, selection,
all failed and accepted physical attempts, exact deck export, drawing,
explanation, persisted design, accounting receipts and process exit. OS/file
caches were not cleared. Recovery-only `design.wall_s` has a narrower labeled
scope; the workflow ledger's `parent_wall_s` is the comparison measure.

| Request | RL median (s) | Classical median (s) |
|---|---:|---:|
| 3 dB / 1.9 GHz | 76.477 | 70.737 |
| 6 dB / 2.1 GHz | 137.226 | 134.204 |
| 9 dB / 1.9 GHz | 72.812 | 67.943 |
| 12 dB / 2.5 GHz | 3.351 | 3.003 |

Each median uses all three registered repetitions, including refusals/failures;
12 dB / 2.5 GHz was refused by both arms. Across all 12 benchmark workflows per
arm, medians were 75.336 s RL and 70.362 s classical. Of 12 matched pairs, eight
had successful delivery on both sides. Their median classical/RL time ratio was
**0.939415**. This campaign does **not demonstrate an RL runtime advantage**;
three repetitions are descriptive, not evidence of a universal speed ratio.

Delivered successes were **RL 9/12 and classical 8/12**. The additional classical
failure was an infrastructure failure, not a measured electrical limit violation.
For 9 dB / 1.9 GHz, repeat 0, setting 490 was the only eligible candidate. At
FS / 1.05 VDD / 27 C, atomic replacement of `call_progress.json` raised
**WinError 5: Access is denied**, before AC/noise invocation. That measurement
directory is absent; the seven loss conditions were unmeasured, giving 308/315.
The exact reason is retained in the
[corner journal](product_audits/submission_recovery_20260915/benchmark_005_9db_1p9ghz_classical_r0/output/physical_recovery/candidate_01_setting_490/fixed_pvt.jsonl)
and [candidate result](product_audits/submission_recovery_20260915/benchmark_005_9db_1p9ghz_classical_r0/output/physical_recovery/candidate_01_setting_490/result.json).
The underlying Windows file-access cause is unestablished. Later planned
classical repetitions passed 315/315 with the same setting and identical
nominal deck hash. The failed repetition and its 67.193 s remain included;
the success-count difference is not evidence of superior RL candidate quality.

The campaign ledger records **4,110 charged invocations**, including 1,644 per
benchmark arm. These are not all confirmed simulator launches: the affected
run charged 137 but retained 136 simulator logs, because the failed bookkeeping
update preceded one invocation. Keep that distinction when quoting equal costs.
Total parent time across all 37 workflows was 2,360.062 s; it includes failed
and refused work, but excludes campaign gaps and preflight.

## Limits

This evidence concerns fixed physical CTLE/reference circuits with an ideal
behavioral DFE. It does not establish a transistor receiver, continuous full-range
target coverage, S7 layout-area compliance, or analog PVT signoff of the separate
integrated transistor DFE checkpoint. The exposed diagnostic request is not an
unseen-target generalization test. Historical failures, frozen registry entries,
source snapshots and earlier analog-PVT limitations remain unchanged.
