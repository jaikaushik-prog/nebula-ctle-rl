# Entry 87 margin-adaptation RL result

Date: 2026-09-03

## Bottom line

The categorical-PPO implementation and evaluation pipeline worked, but the
registered research claim did **not** pass. All five policies completed their
exact 200,000-step TRAIN runs with changed weights and finite telemetry. On the
864 held-out TEST identities, RL improved the fixed comparator slightly:

- compliance: 0.9931 -> 0.9963;
- mean normalized eye quality `q`: 0.6796 -> 0.6825;
- mean measured settings: 1.000 -> 1.003.

That is a real positive movement, but it is too small to claim that RL
contributes. Gate Q6 required a mean quality gain of at least 0.0200 and a
strictly positive paired-bootstrap lower bound. The observed gain was only
0.00287, with 95% CI `[-1.93e-19, 0.00659]`. Q1-Q5 and Q7-Q8 pass; Q6 and the
overall experiment fail.

The correct deployable controller remains the request-conditioned fixed
TRAIN-only lookup. The preselected deployment policy (seed `2026090300`) is
preserved as experimental evidence, not promoted.

## Frozen experiment

- Real-device source: `experiments/joint_bank_73_run.jsonl.gz`
- Decoded source SHA-256:
  `1B5F941DF4B34F3C90F6DD050F264D8A77C7BB2E5CE4D9EED8CC29EBD9F9843F`
- Control artifact SHA-256:
  `4E7930C6EF353B81949F7D8C6562D6E4027F7B164F3B0099AD79FE652E09501D`
- TRAIN: 1,728 identities, processes `tt/ss/ff`, losses 3/6/9/12 dB
- TEST: 864 identities, processes `sf/fs`, losses 4.5/7.5/10.5 dB
- Overlap: zero
- Policy: categorical PPO, separate `(64,64)` tanh actor/value trunks
- Training: five predeclared seeds, 200,000 steps each, 1,000,000 total
- Evaluation: deterministic argmax, all 864 TEST identities exactly once per
  policy
- New SPICE simulations: zero; transitions use the frozen measured table
- Final non-slow regression: 2,631 passed, 13 deselected, 2 known warnings in
  297.13 s

## Held-out results

| arm | compliant | compliance | mean q | q delta | trials | false locks |
|---|---:|---:|---:|---:|---:|---:|
| fixed comparator | 858/864 | 0.9931 | 0.6796 | - | 1.000 | 6 |
| PPO seed 2026090300 | 860/864 | 0.9954 | 0.6819 | +0.00231 | 1.003 | 4 |
| PPO seed 2026090301 | 861/864 | 0.9965 | 0.6826 | +0.00301 | 1.003 | 3 |
| PPO seed 2026090302 | 861/864 | 0.9965 | 0.6826 | +0.00301 | 1.003 | 3 |
| PPO seed 2026090303 | 861/864 | 0.9965 | 0.6826 | +0.00301 | 1.003 | 3 |
| PPO seed 2026090304 | 861/864 | 0.9965 | 0.6826 | +0.00301 | 1.003 | 3 |
| five-seed mean | - | **0.9963** | **0.6825** | **+0.00287** | **1.003** | - |

The four later seeds produce the same deterministic TEST behavior despite
distinct learned weights. The deployment seed differs slightly but is also
positive, so the reproducibility gate passes.

## Registered gates

| gate | result | evidence |
|---|---|---|
| Q1 source/split | PASS | pinned source; 1,728/864 identities; zero overlap |
| Q2 environment | PASS | hidden state, seven actions, exact horizon/reward gates |
| Q3 controls first | PASS | control artifact committed before policy code/training |
| Q4 training integrity | PASS | 5/5 x 200,000 finite steps; distinct changed weights |
| Q5 safety | PASS | mean 0.9963 and deployment 0.9954 exceed 0.9831 floor |
| Q6 quality | **FAIL** | +0.00287 < +0.0200; CI lower bound is not >0 |
| Q7 reproducibility | PASS | 5/5 positive deltas; deployment delta positive |
| Q8 cost/reporting | PASS | 1.003 <= 8 and far below 512-setting exhaustive |

## What the policy actually learned

All five policies locked immediately on 861 of 864 TEST identities. They moved
only for the same request/corner family: `sf/0.95`, 4.5 dB channel loss,
8 dB requested peaking, and 1.386961840 GHz requested peak frequency, across
three temperatures. Seeds 01-04 made those three cases compliant; seed 00 made
two compliant and left the 125 C case false-locked.

This behavior explains both the small benefit and the narrow confidence
interval. It also rules out the claim that the policy learned broad
margin-seeking adaptation.

## Interpretation and next decision

Measured fact: the policies converged to almost-always LOCK. Inference: the
registered combination of a 99.31%-compliant start, an immediate positive lock
reward, move costs, and false-lock risk made exploration unattractive. This is
not proof that PPO cannot solve margin adaptation; the hidden oracle's `q=1.0`
shows that better measured settings exist. It is proof that this exact frozen
formulation did not obtain a useful margin policy.

Do not tune this experiment on its exposed TEST set. A second RL attempt needs
a new owner-approved preregistration and a fresh untouched validation set. The
scientifically safe fallback for the current deliverable is the fixed lookup,
with Entry 87 reported as a measured negative result.

## Evidence files

- `experiments/margin_adapt_rl_results.json`, SHA-256
  `18CC3C7E87251EBF4075992BCC4A7D621A2920F0323849886120C8B36B3B5696`
- Checkpoints, seeds 00..04:
  `10B17631497832BB4705A47E0ABCEF57C78B7FDCAF6195B1E013387E082E7F3F`,
  `EFC0A97BF00387A301FE44FF43F39E3CD502D170F3FE43E6391542C15813DC92`,
  `1AD3D0A74E58920A06C85AE30A4A14D713213503BE69C0BAECB73360B0FAA4E8`,
  `8949045A1897AB9845BF5F802D6D2AB462A59D1018C17CE0C56E66C83EECC6E4`,
  `E4CF2E65D2E9C334C2791FB9135544F2F2F9269F33556C0EA005E1109B57FE34`
- Training summaries, seeds 00..04:
  `E5981DB7DF25EDDE06F2B499FD8E00BD6CDC58DFC6313DC6262B1EB09DF8770B`,
  `FFF3F50B7965D7655BDE0B1821E9DE1FE81745A1E7CF097049289BF96D0FE149`,
  `3F81ACE96103DB590D569F085986082C4C5BCB08A6C0E137F5395371778BAB75`,
  `AFD3D4F1B33E9799C541F9E602303FDA5ED438B323300A2F38AB3B2D2636722E`,
  `32D08C1AA5AB9E6BDF699A166944AB729B0FDA15D2C55F8448E9FA871A5989A2`
