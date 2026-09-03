# Entry 89 frozen-policy DEVELOPMENT results

Date: 2026-09-03

## Bottom line

All five oracle-warm-started PPO policies completed their registered training,
and the simulator-backed shield passes the exposed-DEVELOPMENT diagnostics for
all five.

The fixed start has compliance 0.9925 and mean quality `q=0.6703`. Across the
five new policies, the shield raises mean compliance to 0.9983 and mean quality
to `q=0.8557`, an average quality improvement of +0.1854. Every seed improves
quality by much more than the +0.0200 final gate, and every seed retains every
identity on which the fixed start was compliant.

This is encouraging but **not final evidence**. These 5,040 identities were
already exposed during Entries 87 and 88 and were used to build the imitation
teacher. The fresh midpoint journal does not exist, and FINAL remains
`NOT_GENERATED_NOT_SCORED`.

## Training integrity

- Five predeclared seeds: `2026090500..2026090504`.
- Deployment seed was fixed in advance as `2026090500`.
- Each seed completed exactly 50 imitation epochs.
- Each seed completed exactly 200,000 PPO steps.
- Total PPO steps: 1,000,000.
- Mean imitation support accuracy: 0.9212.
- Every actor changed during imitation.
- Every value trunk remained unchanged during imitation.
- Every PPO run started from its own imitation checkpoint.
- Every final policy changed from its imitation checkpoint.
- All recorded losses and telemetry are finite.
- Training used the frozen DEVELOPMENT table and ran zero SPICE simulations.
- All fifteen BC, policy and training-summary files have distinct SHA-256
  hashes.

## Exposed-DEVELOPMENT results

| seed | unshielded compliance | unshielded q | shielded compliance | shielded q | q delta vs fixed | identities improved | trials / verifier calls | interventions | shield failures |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026090500 | 0.9004 | 0.7365 | 0.9980 | 0.8645 | +0.1942 | 95.65% | 7.465 | 2,337 | 10 |
| 2026090501 | 0.9230 | 0.7799 | 0.9986 | 0.8512 | +0.1810 | 95.71% | 4.715 | 764 | 7 |
| 2026090502 | 0.7657 | 0.6811 | 0.9980 | 0.8916 | +0.2214 | 95.73% | 5.261 | 1,333 | 10 |
| 2026090503 | 0.9631 | 0.7700 | 0.9980 | 0.8209 | +0.1507 | 78.17% | 5.050 | 2,015 | 10 |
| 2026090504 | 0.9137 | 0.7635 | 0.9986 | 0.8501 | +0.1798 | 96.03% | 4.669 | 1,208 | 7 |
| five-seed mean | 0.8932 | 0.7462 | **0.9983** | **0.8557** | **+0.1854** | - | **5.432** | - | - |

The shield uses exactly the settings measured by the policy and includes the
fixed start. It makes no free proposals. Mean verifier calls therefore equal
mean measured trials. A shield failure means that none of the visited settings,
including the fixed start, was compliant; these are identities on which the
fixed comparator was already noncompliant. Every compliant fixed start was
retained for every seed.

## What the unshielded comparison means

The new policies are not safe by themselves. Their unshielded compliance spans
0.7657 to 0.9631, below the fixed comparator's 0.9925. The policies are useful
candidate proposers, but their final LOCK action cannot be trusted as the
output selector.

The shield is therefore not a cosmetic addition. It is the part that enforces
the structural guarantee: among all measured candidates, return only the best
one that the full simulator verifier marks compliant.

The combined claim must remain:

> Oracle-imitation plus PPO proposes candidates; the simulator-backed shield
> selects the final verified setting.

It would be incorrect to call the shielded result "the policy alone," and it
would also be incorrect to describe it as receiver-only hardware adaptation.

## Development diagnostics

| diagnostic | result | meaning |
|---|---|---|
| D3 training | PASS | all five registered BC and PPO runs are complete, finite and distinct |
| D4 safety | PASS | all five shielded compliance rates are at least fixed, identity-level retention holds |
| D5 quality | PASS | all five shielded policies exceed fixed quality by at least +0.0200 |

These diagnostics do not select a seed and do not permit policy changes. All
five policies, including the preselected deployment seed, are frozen exactly as
trained.

## Frozen provenance

- DEVELOPMENT source decoded SHA-256:
  `1B5F941DF4B34F3C90F6DD050F264D8A77C7BB2E5CE4D9EED8CC29EBD9F9843F`
- Prior shield-controls SHA-256:
  `82F868B94A6D80C790C104ABF7383DC2257E919DC8E2441D9509D44AC066FF45`
- New DEVELOPMENT result SHA-256:
  `9D462EE4F3FE97AFEF1FD372817A0672487A33AD3C46A794DCE3AB390C9EFFBF`
- Five-policy manifest SHA-256:
  `3E910DECEFD7CAAA5D401655E77C310F8BE4A645DD48538EEE4E1531199734DB`
- New SPICE simulations: zero.
- FINAL status: `NOT_GENERATED_NOT_SCORED`.

The manifest contains the exact SHA-256 of every BC checkpoint, final policy,
training summary and the DEVELOPMENT result. The midpoint generator refuses to
run if any one of them changes.

## Next step

Commit the evaluator, all fifteen training artifacts, the DEVELOPMENT result,
the freeze manifest, tests and this report together. Only after that commit may
the fresh 23,040-row midpoint ngspice journal be generated. The nine midpoint
requests will then be evaluated exactly once across 2,430 fresh identities.

Professor-ready takeaway:

> On exposed development data, PPO provides valuable candidate paths but is
> unsafe alone; a simulator-backed best-compliant-visited shield converts those
> paths into a 99.83%-compliant result with a +0.185 mean eye-quality gain. The
> fresh test is still untouched, so this is a mechanism check, not the final
> claim.
