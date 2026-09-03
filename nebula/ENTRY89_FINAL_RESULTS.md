# Entry 89 one-time FINAL result

Date: 2026-09-04

## Outcome in simple language

The registered experiment passed. Five frozen RL policies were tested once on
2,430 fresh cases created only after training was complete. The combined RL
proposer and simulator safety shield improved eye quality, did not reduce
compliance relative to the fixed start, and used an average of 5.579 measured
settings instead of an exhaustive 512-setting sweep.

This does **not** prove that pure RL is safe. The unshielded policies performed
poorly. The useful contribution is the hybrid system: RL proposes a short path,
while the simulator checks every visited setting and returns the best compliant
one.

## Primary result

| Method | Compliance | Mean q | Delta vs fixed | Mean measurements |
|---|---:|---:|---:|---:|
| Fixed nearest-DEVELOPMENT start | 0.8226 | 0.5619 | 0.0000 | 1.000 |
| Entry 88 deployment policy + shield | 0.8272 | 0.6986 | +0.1367 | 4.123 |
| Entry 89 raw policy, five-seed mean | 0.6444 | 0.5481 | -0.0138 | 5.579 |
| **Entry 89 policy + shield, five-seed mean** | **0.8388** | **0.7169** | **+0.1550** | **5.579** |
| Seven-move reachable hidden oracle | 1.0000 | 0.9664 | +0.4045 | 5.942 |
| Global hidden oracle | 1.0000 | 1.0000 | +0.4381 | 1.000 |

The paired 10,000-resample 95% confidence interval for the primary quality
gain is **[+0.1508, +0.1593]**. Its lower bound is well above zero and the
registered +0.0200 threshold.

## Per-seed primary results

| Seed | Compliance | Mean q | Delta vs fixed | Measurements | Shield fallbacks |
|---:|---:|---:|---:|---:|---:|
| 2026090500 (deployment) | 0.8272 | 0.7011 | +0.1392 | 7.651 | 420 |
| 2026090501 | 0.8272 | 0.7048 | +0.1429 | 4.909 | 420 |
| 2026090502 | 0.8272 | 0.7386 | +0.1767 | 5.816 | 420 |
| 2026090503 | 0.8597 | 0.7162 | +0.1543 | 5.136 | 341 |
| 2026090504 | 0.8531 | 0.7237 | +0.1618 | 4.385 | 357 |

All five seeds improved q, including the preselected deployment seed. Every
compliant fixed start remained compliant after shielding. Verifier calls equal
billed measurements exactly; no check was treated as free.

## Registered gates

| Gate | Result |
|---|---|
| R1 provenance | PASS |
| R2 actor observation excludes hidden truth | PASS |
| R3 DEVELOPMENT-only oracle imitation | PASS |
| R4 five complete and distinct training runs | PASS |
| R5 structural safety | PASS |
| R6 quality gain and confidence interval | PASS |
| R7 seed reproducibility | PASS |
| R8 measurement cost | PASS |
| R9 attribution and reporting | PASS |
| R10 simulator-backed scope | PASS |

Overall registered result: **PASS**.

## Honest attribution

The safety shield is doing essential work. Raw Entry 89 mean compliance is
0.6444, below the fixed method's 0.8226, and raw mean q is also slightly lower.
The shield raises the same trajectories to 0.8388 compliance and 0.7169 q.

Oracle imitation plus the new policy training provides a smaller additional
improvement over the older policy using the same shield: +0.0117 absolute
compliance and +0.0183 q. Therefore, the defensible claim is not that the new
neural network alone solved circuit design. It is that a trained RL proposer,
combined with a strict simulator verifier, finds substantially better safe
settings with few measurements and generalizes to unseen midpoint requests.

## Remaining product gap and next action

Primary compliance is 0.8388, not 1.0000. A shield fallback means that none of
the settings visited in that episode was compliant, so the shield returned the
fixed start and honestly recorded failure. Across five seeds there were 1,958
such outcomes. Meanwhile, the global oracle achieved 1.0000 compliance, proving
that the 512-setting bank contains an answer for every fresh identity.

The product should therefore use this flow:

1. Use the frozen RL policy to propose up to eight settings.
2. Let ngspice verify every visited candidate and return the best compliant one.
3. If no compliant candidate was visited, invoke the existing
   analytic/library/CMA-ES search as a fallback.
4. Pass the verified result to the existing netlist, schematic and measured-spec
   output path.

That is a credible hybrid solution to the competition problem. The result is
simulator-backed on fresh link/request views of the same transistor/PVT
lattice. It is not receiver-only calibration, independent silicon validation,
or proof that RL synthesizes a new topology from scratch.

## Immutable artifact

- Result file: `experiments/shielded_policy_final_results.json`
- SHA-256:
  `942CDDD8B62FC862D81602AF87182D0841533505FB045CE04EB0DCADA8919FEA`
- Status: `EVALUATED_ONCE_AFTER_FROZEN_POLICIES_AND_DATA`
- FINAL simulations run: 0; all measurements came from the separately frozen
  real-ngspice midpoint bank
- Post-FINAL regression: 2,696 passed, 13 deselected and 2 known warnings in
  298.87 seconds

This FINAL evaluation must not be rerun, tuned or replaced.
