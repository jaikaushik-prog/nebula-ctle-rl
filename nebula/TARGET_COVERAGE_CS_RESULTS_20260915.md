# Continuous-Cs target coverage results - 15 September 2026

The preregistered 6 dB / 2.5 GHz pilot found two new fixed physical CTLE candidates
that pass the unchanged 315-condition gate. All three registered candidates were
measured; none was skipped after the first success. The frozen 512-setting bank,
reward, parameter ranges, tolerances, topology and scientific definitions were
not changed. These are explicitly identified continuous-Cs refinements of base
480, with `bank_setting=null`, not new bank settings or an RL performance result.

| Candidate | Cs (pF) | Passes | Peak-frequency range across 45 corners (GHz) |
|---|---:|---:|---:|
| base480_cs1p01 | 1.701495152915326 | 308/315 | 2.057622-2.507925 |
| base480_cs1p02 | 1.718341639577854 | 315/315 | 2.048263-2.496324 |
| base480_cs1p03 | 1.735188126240382 | 315/315 | 2.039292-2.485231 |

Factor 1.01 still fails S3 peak-frequency band at FF / 1.05 supply scale / 0 C
for all seven channel losses; all its measurements are valid. Factors 1.02 and
1.03 have no failed or unmeasured conditions, and their nominal requested-target
checks also pass. Each retains one fixed geometry and circuit signature across
all 45 corners and seven losses. Original base 480 passed only 308/315, with
its fastest peak at 2.519638 GHz. A small Cs increase reduced that peak enough
to fit the existing upper frequency limit while preserving the slow-corner
requested-target tolerance. This is a measured improvement for one request;
frequency margins remain small and mismatch/passive/layout variation is untested.

For the first passing registered candidate, factor 1.02, nominal peaking is
6.746979 dB at 2.335455 GHz, noise 0.609854 mVrms and CTLE plus physical-reference
power 6.965787 mW. Nominal 100 MHz/Nyquist HD3 are -87.7811/-54.4794 dBc. The
representative 7.5 dB channel with ideal behavioral DFE has eye height 0.284962 V
and width 0.84375 UI. Geometry subtotal 0.00735697 mm2 is not full S7 layout area.

The campaign charged 411 invocations, exactly 137 per candidate, retaining 411
ngspice logs. Charged counts remain labeled as charges rather than independent
OS launch telemetry. All three runs completed without candidate/simulator retries.
Candidate wall times including their evidence closeout were 68.3715, 92.1462 and
104.5874 seconds. Aggregate recorded wall time was 281.4683 seconds from runner
start through candidate processing, before its final fingerprint/manifest closeout;
it is not the complete user-workflow benchmark timing. The registered budget was
900 seconds and 411 charges. Source, asset, simulator and PDK fingerprints matched
at closeout. An independent readback verified all 2,105 aggregate manifest files,
exact captured-deck hashes, 315 unique conditions, fixed candidate identities,
counts and the canonical acceptance function. Ten focused tests passed after a
recorded failure-first import test; no full regression was run for this experiment.

This adds physical evidence for a previously failing grid request. The historical
37-workflow coverage result remains 4/13 (3/12 rectangular grid). Combining this
new evidence with those distinct successes gives five tested target requests
(four on the rectangular grid), but this pilot did not rerun that workflow grid
or integrate the continuous candidates into automatic user-request dispatch.
No claim is made for full target-range coverage, analog DFE PVT closure, full
receiver power/area or S7 compliance. The gate remains physical CTLE plus ideal
behavioral DFE and constructed channels.

Evidence:

- [Preregistered plan](TARGET_COVERAGE_CS_PLAN_20260915.md)
- [Frozen campaign summary](product_audits/continuous_cs_coverage_20260915/summary.json)
- [Independent manifest and gate review](CONTINUOUS_CS_COVERAGE_REVIEW_20260915.json)
- [Factor 1.01 result](product_audits/continuous_cs_coverage_20260915/base480_cs1p01/result.json)
- [Factor 1.02 result](product_audits/continuous_cs_coverage_20260915/base480_cs1p02/result.json)
- [Factor 1.03 result](product_audits/continuous_cs_coverage_20260915/base480_cs1p03/result.json)

Frozen summary SHA-256: `cd08f782254bd7dc883156b671663f3531992ed2527d702e897ba79031a8291b`.
Aggregate manifest SHA-256: `e34bdb81db5be8e8f0009ad89b1f7e1196b1384fc4fa5096d889d3454b11bbfe`.
