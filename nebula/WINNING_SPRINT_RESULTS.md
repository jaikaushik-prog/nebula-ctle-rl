# Winning-sprint results - Entry 115

## A. Exhaustive-oracle benchmark (complete)

The frozen five-seed PPO evaluation was rescored against every one of the 512
cached midpoint settings for all 2,430 identities. No training and no SPICE
simulation occurred in this diagnostic.

| Metric | Result | Frozen gate |
|---|---:|---:|
| PPO compliance | 83.8848% | descriptive |
| Exhaustive-oracle compliance | 100.0000% | descriptive |
| PPO mean quality | 0.716902 | descriptive |
| Oracle mean quality | 1.000000 | descriptive |
| Mean regret on oracle-solvable identities | 0.283098 | <= 0.05: **FAIL** |
| Identities within 0.05 of oracle | 20.9053% | >= 90%: **FAIL** |
| Mean PPO candidate visits | 5.5794 | descriptive |
| Exhaustive candidate visits | 512 | fixed comparison |
| Candidate-visit reduction | 91.7657x | >= 20x: **PASS** |

The 95% request/loss-block interval is 0.236852-0.329850 for mean regret and
15.0947%-27.1272% for the within-0.05 fraction. Therefore Entry 115 does not
support a near-optimality claim. It does support a 91.8x reduction in cached
candidate visits relative to enumerating all 512 settings, with 83.9% policy
compliance on this exposed midpoint library-policy evaluation. Cached Python
timing is not SPICE speedup, and offline characterisation and training remain
costs.

Evidence:
`product_audits/entry115_exhaustive_benchmark_20260908/summary.json`,
`per_identity.jsonl.gz` and `sha256.json`.

## B. Fixed physical-candidate recovery (pending)

The runner and tests are frozen before measurement. It will attempt all ten
remaining candidates in the order recorded by `WINNING_SPRINT_PLAN.md`; it
will retain both passing and failing raw evidence. This is a classical recovery
experiment, not RL ranking.
