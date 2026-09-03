# Entry 89 exposed-DEVELOPMENT shield controls

Date: 2026-09-03

## Bottom line

The structural shield passes its DEVELOPMENT go/no-go test. On all 5,040
already-exposed identities, it makes every frozen Entry 88 policy safer than
the fixed comparator while retaining a large quality improvement.

This is **not** the Entry 89 final result. DEVELOPMENT includes all identities
exposed by Entries 87 and 88. The fresh midpoint journal has not been generated
and FINAL remains `NOT_GENERATED_NOT_SCORED`.

## Results

| arm | compliance | mean q | q delta | trials | false locks | shield interventions |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 0.9925 | 0.6703 | - | 1.000 | 38 | 0 |
| seed 2026090400 + shield | 0.9980 | 0.8213 | +0.1510 | 3.789 | 10 | 651 |
| seed 2026090401 + shield | 0.9980 | 0.8148 | +0.1445 | 3.625 | 10 | 660 |
| seed 2026090402 + shield | 0.9946 | 0.8075 | +0.1372 | 3.612 | 27 | 518 |
| seed 2026090403 + shield | 0.9982 | 0.8050 | +0.1347 | 3.725 | 9 | 742 |
| seed 2026090404 + shield | 0.9970 | 0.8238 | +0.1535 | 3.895 | 15 | 707 |

Without the shield, those same policy traces have compliance from 0.8677 to
0.9421 and q deltas from +0.0215 to +0.0973. The shield does not create or
measure any new code: it chooses the largest visible eye among settings the
policy actually visited and the simulator verifier marked compliant, including
the fixed start. Every verifier call equals a billed policy measurement.

The seven-move DEVELOPMENT teacher reaches mean q 0.9835 at mean Manhattan
distance 4.677; 98.06% of identities have a teacher target different from the
fixed start. This supports the registered oracle warm start but does not score
its prediction before the new models exist.

## Interpretation

The result isolates Entry 88's failure. Its actor was finding valuable settings;
the unsafe final LOCK discarded earlier compliant candidates. Separating
proposal from verified acceptance repairs that mechanism on exposed data.

Attribution must remain explicit: this is an **RL proposer + simulator shield**,
not a receiver-only RL controller. The policy supplies the candidate path; the
verifier supplies hidden compliance; the shield performs final selection.

## Evidence

- Source decoded SHA-256:
  `1B5F941DF4B34F3C90F6DD050F264D8A77C7BB2E5CE4D9EED8CC29EBD9F9843F`
- `experiments/shielded_controls_results.json`, SHA-256:
  `82F868B94A6D80C790C104ABF7383DC2257E919DC8E2441D9509D44AC066FF45`
- New SPICE simulations: zero
- Development checks D1 safety and D2 quality: PASS
- Complete non-slow regression: 2,675 passed, 13 deselected, 2 known warnings
  in 540.51 s
