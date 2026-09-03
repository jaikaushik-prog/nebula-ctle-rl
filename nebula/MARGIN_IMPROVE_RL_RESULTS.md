# Entry 88 improvement-reward masked-PPO result

Date: 2026-09-03

## Bottom line

Entry 88 fixed Entry 87's immediate-LOCK collapse and learned a large,
reproducible quality improvement. It did **not** learn a safe controller.
Across the 2,448 policy-untouched FINAL TEST identities, mean normalized eye
quality rose from 0.6824 to 0.7690 (`+0.0866`), with paired-bootstrap 95%
confidence interval `[+0.0772, +0.0956]`. All five seeds were positive and the
policies used only 3.797 measured settings on average.

Compliance simultaneously fell from 0.9865 to 0.9274. The registered safety
floor was 0.9765, and the preselected deployment seed reached only 0.9461.
Q5 therefore fails; Q1-Q4 and Q6-Q8 pass; the overall experiment fails. No
policy is promoted. The request-conditioned fixed lookup remains the safe
deployable controller.

This is a more informative failure than Entry 87. The agent can learn useful
movement from the receiver-visible history, but maximizing expected scalar
return did not enforce the required compliance probability. A false-lock
penalty is not a hard safety constraint.

## Frozen experiment

- Real-device source: `experiments/joint_bank_73_run.jsonl.gz`
- Decoded source SHA-256:
  `1B5F941DF4B34F3C90F6DD050F264D8A77C7BB2E5CE4D9EED8CC29EBD9F9843F`
- Controls SHA-256:
  `7EE4650145E1603E1A90282A0F9B69C33E8070C8A4E52AF73156F3B8AC1497B6`
- TRAIN: 2,592 identities; Entry 87's complete exposed union
- FINAL TEST: the exact 2,448-identity policy-untouched complement
- Split: zero overlap; 5,040-identity union
- Policy: masked categorical PPO, separate `(64,64)` tanh actor/value trunks
- Training: five predeclared seeds, 200,000 steps each, 1,000,000 total
- Evaluation: deterministic masked argmax on all 2,448 FINAL TEST identities,
  exactly once after all five artifacts validated
- New SPICE simulations: zero; transitions use the frozen measured table
- Bootstrap: 10,000 paired resamples, seed `2026090488`
- Final non-slow regression: 2,662 passed, 13 deselected, 2 known warnings in
  466.52 s

## FINAL TEST results

| arm | compliant | compliance | mean q | q delta | trials | false locks | code changed |
|---|---:|---:|---:|---:|---:|---:|---:|
| fixed comparator | 2415/2448 | **0.9865** | 0.6824 | - | 1.000 | 33 | 0.0000 |
| PPO seed 2026090400 (deployment) | 2316/2448 | 0.9461 | **0.7894** | +0.1070 | 3.896 | 132 | 0.9457 |
| PPO seed 2026090401 | 2276/2448 | 0.9297 | 0.7707 | +0.0884 | 3.668 | 172 | 0.9980 |
| PPO seed 2026090402 | 2295/2448 | 0.9375 | 0.7792 | +0.0968 | 3.741 | 153 | 0.9902 |
| PPO seed 2026090403 | 2211/2448 | 0.9032 | 0.7335 | +0.0512 | 3.734 | 237 | 0.9154 |
| PPO seed 2026090404 | 2253/2448 | 0.9203 | 0.7720 | +0.0897 | 3.945 | 195 | 1.0000 |
| five-seed mean | - | **0.9274** | **0.7690** | **+0.0866** | **3.797** | **177.8** | **0.9699** |

The quality effect is not marginal: it is 4.33 times the registered +0.0200
minimum, and the confidence interval excludes zero comfortably. The safety
miss is also not marginal: aggregate compliance is 4.91 percentage points
below the registered floor and 5.91 points below the comparator. Deployment
seed 00 is 3.04 points below the safety floor.

Relative to the fixed comparator, seeds 00..04 respectively lost
`118, 166, 140, 232, 188` previously compliant identities and recovered
`19, 27, 20, 28, 26` of the comparator's failures. Every seed therefore has a
negative net compliance change even though every seed has a positive q change.

## FINAL TEST controls and ceilings

| arm | compliance | mean q | q improvement | trials |
|---|---:|---:|---:|---:|
| fixed comparator | 0.9865 | 0.6824 | 0.0000 | 1.000 |
| visible-eye hill-climb | 0.4289 | 0.3433 | -0.3391 | 8.000 |
| masked random, 20-seed mean | 0.4051 | 0.2804 | -0.4020 | 5.414 |
| exhaustive maximum visible eye | 0.0102 | 0.0102 | -0.6721 | 512.000 |
| global hidden oracle | 1.0000 | 1.0000 | +0.3176 | 1.000 |
| seven-move reachable hidden oracle | **1.0000** | **0.9886** | **+0.3062** | **5.356** |

The reachable oracle confirms that the action budget is not the cause of the
safety failure: safe, high-quality endpoints exist within seven moves. The
observable-eye controls confirm that visible eye alone cannot identify them.

## Registered gates

| gate | result | evidence |
|---|---|---|
| Q1 source/split | PASS | pinned source; 2,592/2,448; overlap 0; union 5,040 |
| Q2 environment | PASS | exact observation, masks, reward, horizon and auto-lock tests |
| Q3 controls first | PASS | TRAIN controls frozen in commit `6e3231e` before policy code |
| Q4 training integrity | PASS | 5/5 x 200,000 finite steps; changed, distinct artifacts |
| Q5 safety | **FAIL** | mean 0.9274 and deployment 0.9461 are below 0.9765 floor |
| Q6 quality | PASS | +0.0866 >= +0.0200; CI lower bound +0.0772 > 0 |
| Q7 reproducibility | PASS | 5/5 positive deltas; deployment seed positive |
| Q8 cost/reporting | PASS | 3.797 <= 8 and far below 512-setting exhaustive |

## Interpretation and next decision

Measured fact: masking and the improvement reward caused broad action. The
mean code-change rate is 96.99%, compared with Entry 87's almost-always LOCK.
Measured fact: this produced a large eye-quality gain and a large compliance
loss. Inference: the scalar expected-return objective permits a risk/quality
trade that conflicts with Q5; its false-lock penalty discourages failure but
cannot guarantee a compliance-rate constraint.

Do not tune Entry 88 on its now-exposed FINAL TEST identities. The current
deliverable must keep the fixed lookup. If the owner authorizes one rescue,
the evidence points toward a safety-constrained architecture, such as learning
oracle-ranked moves on TRAIN while a separate compliant-best-so-far shield
controls deployment. That must be preregistered and evaluated on genuinely new
held-out data. The reward, safety threshold, or seed set must not be changed
retroactively.

The first post-result full-suite run exposed a path-isolation defect in two
tests: redirecting the experiment directory did not redirect the module-level
result `Path`, so the newly existing real artifact triggered the overwrite
guard inside temporary-directory tests. No score or artifact was recomputed.
`results_path()` now resolves against the active experiment directory at call
time; the focused group passes 10/10 and the complete suite passes 2,662/2,662.

## Evidence files

- `experiments/margin_improve_rl_results.json`, SHA-256
  `1A274CAABC768610979F4DBC5DAEBC43E13C8AF10CB99D5FAD513ECC4E69C13C`
- Checkpoints, seeds 00..04:
  `18BC302DF496AE46DAAA1E20BA5775A052CB3245F2635E5BCDA56DE721BA12AA`,
  `98CB8202F59F9F9DC5B25DEAFE743006978EB51BD7076B99309B0D98216B5329`,
  `30CA2FF354928479B293741CA01469715689C44F912295A7D0E02AD3A8AFDC82`,
  `D76673BF8FBB8401C7ECBDFEE4937D256C4DFFA183807498E7CE446534B4B691`,
  `B4CA295A8AB11C3AF520E34CA3FF7362B3370085C76B6C900A380774332FECD4`
- Training summaries, seeds 00..04:
  `EE14AF125F034AA73419A5101161B23F5614E6FE8F129A8D3BCDC4356B85FEB8`,
  `ADE190721F18D3CA9AAA86F522214FEAD28C252B39D63F78844BC4E397A1D515`,
  `301C7613B34743B269A139FCA3D375386D8398E9868091AF9982EFAFD8B890D9`,
  `DFED7D030889A9DC82532C6FA26DE0E26F3ECFBE337EBADCD24537C605E57CE9`,
  `1BAD8D162E017D9511F4BC73E52E8C27314DD4FDAAB6EB786379A0B669A39893`
