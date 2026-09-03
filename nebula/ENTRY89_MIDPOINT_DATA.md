# Entry 89 fresh midpoint data boundary

## Plain-language result

The fresh circuit-measurement bank is complete. After all five RL policies were
frozen and committed, ngspice measured every one of the 512 tuning settings at
all 45 PVT corners. This produced 23,040 rows in 130.99 minutes.

This is the unopened examination paper for the RL models. It is not an RL
score. The nine final requests are defined, but none has been evaluated.

## Provenance and validation

- Five-policy freeze commit: `a84082e`
- Rows: 23,040 expected, 23,040 present
- Settings: 512 expected, 512 present
- PVT corners: 45 expected, 45 present
- Unique setting/corner pairs: 23,040
- Wall clock: 7,859.41 seconds (130.99 minutes)
- Metadata status: `GENERATED_NOT_SCORED`
- FINAL identities defined but not scored: 2,430
- Raw and decoded-gzip SHA-256:
  `99B6BF526EE610CF39EBC921A2B8BEA2EA482A610354056569B2A176AA1169E2`
- Gzip SHA-256:
  `AE57F93E9636DC135C9E3B86DD37B9B59BE14C3A5DA511EAC4202101E529E9C4`
- Metadata SHA-256:
  `1C5C9527A1A982BD8C82373F98CE3AFDFD021C1AC542D04CF4FAB9D0C2612D65`
- Post-generation test suite: 2,690 passed, 13 deselected, 2 known warnings in
  374.79 seconds

The equal raw and decoded hashes prove that compression preserved the journal
byte for byte. The raw JSONL remains only as a local crash-recovery file; Git
stores the much smaller verified gzip and its metadata.

## What happens next

1. Commit this dataset and provenance before any FINAL scoring code runs.
2. Implement the registered evaluator with tests that fail first.
3. Run the complete non-slow test suite.
4. Evaluate the frozen policies once on the 2,430 FINAL identities.
5. Apply the pre-registered R1-R10 gates and report pass or fail without tuning.

The final result will tell whether the simulator-shielded RL controller keeps
the fixed design's safety, improves compliant eye quality by at least 0.020,
generalizes to the fresh midpoint conditions and uses no more than eight billed
measurements on average.
