# Post-review results - Entry 113 (2026-09-07)

The supplemental comparison establishes an incremental benefit from the PPO-trained policies over their imitation checkpoints at the same maximum budget, with more actual visits. It does not establish universal superiority: random local exploration achieves higher compliance. Physical coverage remains limited.

Protocol: POST_REVIEW_PLAN.md, committed at 030b8f2 before these runs. Frozen policies, rewards, ranges, historical FINAL and original physical demo were not changed. This is exposed-data analysis, not a newly held-out evaluation.

## Attribution

All arms retain the best compliant visited candidate, including the fixed start. Five matching imitation/PPO checkpoints; twenty persistent random streams. Every frozen PPO result reproduced. All visits, including repeats, are billed. Global sampling has a different move space; hill and local random use the existing one-index moves.

| Cap | Method | Compliance | Mean q | Actual visits | Unique visits |
|---:|---|---:|---:|---:|---:|
| 2 | fixed | 82.26% | 0.5619 | 1.000 | 1.000 |
| 2 | hill | 82.26% | 0.6153 | 2.000 | 2.000 |
| 2 | random_local | 85.76% | 0.5977 | 2.000 | 2.000 |
| 2 | random_global | 83.23% | 0.5722 | 2.000 | 2.000 |
| 2 | bc | 82.26% | 0.6078 | 2.000 | 2.000 |
| 2 | ppo | 82.36% | 0.6130 | 2.000 | 2.000 |
| 4 | fixed | 82.26% | 0.5619 | 1.000 | 1.000 |
| 4 | hill | 82.59% | 0.6182 | 4.000 | 2.018 |
| 4 | random_local | 88.58% | 0.6257 | 4.000 | 3.649 |
| 4 | random_global | 85.20% | 0.5931 | 4.000 | 4.000 |
| 4 | bc | 82.26% | 0.6667 | 3.810 | 3.810 |
| 4 | ppo | 82.79% | 0.6764 | 3.770 | 3.581 |
| 8 | fixed | 82.26% | 0.5619 | 1.000 | 1.000 |
| 8 | hill | 84.07% | 0.6339 | 8.000 | 4.023 |
| 8 | random_local | 90.79% | 0.6508 | 8.000 | 6.687 |
| 8 | random_global | 88.08% | 0.6273 | 8.000 | 8.000 |
| 8 | bc | 82.35% | 0.6769 | 4.474 | 4.474 |
| 8 | ppo | 83.88% | 0.7169 | 5.579 | 4.552 |

At cap 8, PPO minus imitation quality is +0.039957 (95% request/loss-block interval +0.016756 to +0.064411); compliance is +1.531 percentage points. PPO uses 5.579 visits versus imitation 4.474. Against local random, PPO quality is +0.066086 but compliance is -6.909 percentage points. The preregistered no-compliance-loss condition against all classical controls is NOT MET.

The preselected deployment seed remains 2026090500: 7.651 actual visits, 4.047 unique visits. Five-seed means are not its operational cost. No seed was selected from this analysis.

Intervals average seeds, group the 45 PVT rows within each of 54 request/loss blocks, and bootstrap 10,000 times. This conditions on the shared library; it is not uncertainty across independent hardware. Caps interrupt original eight-visit traces without changing observation normalisation; early LOCK is retained.

Cached diagnostic runtime: 88.733 s, zero SPICE and zero training. CPU proposal timings include legacy environment/oracle-scoring overhead and are not simulator or hardware latency.

## Physical request coverage

| Target dB / GHz | Setting | Eligible bank settings | Model cases | Status |
|---|---:|---:|---:|---|
| 3 / 1.25 | -- | 0 | -- | BANK_NO_FIXED |
| 3 / 1.9 | 273 | 3 | 312/315 | MODEL_FAIL |
| 3 / 2.5 | -- | 0 | -- | BANK_NO_FIXED |
| 6 / 1.25 | -- | 0 | -- | BANK_NO_FIXED |
| 6 / 1.9 | 288 | 9 | 314/315 | MODEL_FAIL |
| 6 / 2.5 | 480 | 1 | 308/315 | MODEL_FAIL |
| 9 / 1.25 | -- | 0 | -- | BANK_NO_FIXED |
| 9 / 1.9 | 490 | 1 | 315/315 | MODEL_PASS |
| 9 / 2.5 | -- | 0 | -- | BANK_NO_FIXED |
| 12 / 1.25 | -- | 0 | -- | BANK_NO_FIXED |
| 12 / 1.9 | -- | 0 | -- | BANK_NO_FIXED |
| 12 / 2.5 | -- | 0 | -- | BANK_NO_FIXED |

Four physical requests, 548 fresh calls, 380.446 s recorded coverage-run runtime. One of twelve requests passes all model conditions, three selected physical candidates fail, and eight have no fixed candidate in the bank. The bank refusals do not establish physical impossibility.

Every measured candidate is fixed across 45 PVT points and seven channel models. All four selected settings equal the RL-bypassed lowest fixed-eligible setting; two intersections are singletons. The record contains classical selection time and physical-run time, but not a timed complete RL-disabled physical pipeline. This establishes selected-setting agreement, not a general speedup.

Failures are preserved:
- p3_f1.9, ss/0.95/0C: 1 channel conditions; output-swing guard rejects linear-eye calculation.
- p3_f1.9, sf/0.95/0C: 1 channel conditions; output-swing guard rejects linear-eye calculation.
- p3_f1.9, sf/0.95/27C: 1 channel conditions; output-swing guard rejects linear-eye calculation.
- p6_f1.9, sf/0.95/0C: 1 channel conditions; output-swing guard rejects linear-eye calculation.
- p6_f2.5, ff/1.05/0C: 7 channel conditions; S3_f_peak_band.

A swing-guard rejection means the linear eye is not verified at that excursion; it is not a measured eye-height failure. The 6 dB / 2.5 GHz failure is the absolute upper frequency bound, independently of the project request tolerance.

## Model audit

All 616 original evidence hashes checked; 137 saved logs inspected. Generic res_high_po p2/q2/p3/q3 are ignored by ngspice 41. Saved HD3 extraction remains a valid result for that simulator model; omitted passive voltage-dependent distortion is NOT_VERIFIED.

Fixed-width PDK families contain supported voltage expressions but change resistance, temperature behaviour and parasitics. No coefficient translation, resistor substitution, circuit redesign or corrected-hardware claim was made.

## Cost ledger

| Recorded stage | Seconds |
|---|---:|
| joint_bank_73_results.json | 7875.991 |
| joint_bank_midpoint_metadata.json | 7859.409 |
| PPO seed 2026090500 | 1939.485 |
| PPO seed 2026090501 | 1249.153 |
| PPO seed 2026090502 | 2505.052 |
| PPO seed 2026090503 | 1344.834 |
| PPO seed 2026090504 | 1385.057 |

Subtotal: 24158.982 s = 6.711 hours of recorded stage runtimes. This excludes imitation, teacher construction, earlier sizing/search/training and other audits. Do not equate summed stage times with an independently measured sequential project duration. The original bank records unbilled retry decks.

No matched end-to-end MOS/R/C/L sweep or final-physical near-optimality claim has been established.

## Professor-ready takeaways

- PPO improves the learned quality-search behaviour over imitation, but random search remains better at rescuing infeasible starts under this budget.
- Robust generation is limited by the characterised candidate bank and physical swing/frequency constraints. Automatic refusal is useful product behaviour, not proof that the full requested domain is covered.
- Raw measurement reproducibility and simulator-model completeness are separate: the HD3 numbers reproduce while omitted resistor nonlinearity remains unknown.

## Artifacts and reproduction

- entry113_attribution_20260907: full per-identity trajectories, all budgets/seeds, paired intervals and hashes.
- entry113_coverage_20260907: every request, fresh decks, raw measurements, immutable signatures and hashes.
- entry113_models_20260907: warning fingerprints and PDK source hashes.
- Updated competition PDF: 19 pages; original report preserved under output/pdf/archive_20260906/.
- See REPRODUCE_POST_REVIEW.md for environment and release boundaries. LLM client availability was false; live bonus use remains NOT_VERIFIED.
