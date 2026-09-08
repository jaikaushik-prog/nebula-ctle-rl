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

## B. Fixed physical-candidate recovery (complete)

All ten frozen candidates were measured in the preregistered order with 1,370
fresh SPICE calls. Both near-pass targets were recovered without changing the
circuit topology, PVT grid, channel grid, tolerances or acceptance predicate.

| Target | Preserved first miss | First passing setting | Result |
|---|---:|---:|---:|
| 3 dB / 1.9 GHz | 273 | 401 | 315/315 PASS |
| 6 dB / 1.9 GHz | 288 | 474 | 315/315 PASS |

Settings 410 and 352 also pass 315/315 for 6 dB / 1.9 GHz. Every candidate,
including failures, remains in the append-only journal and hash manifest. The
accepted 3 dB setting has worst-case eye height 170.1 mV, eye width 0.7969 UI,
100 MHz HD3 -73.50 dBc, noise 0.689 mVrms and power 9.802 mW. The accepted
6 dB setting has worst-case eye height 165.3 mV, eye width 0.7812 UI, 100 MHz
HD3 -76.997 dBc, noise 0.736 mVrms and power 9.802 mW.

The exact accepted settings are registered with result, deck, circuit-signature
and raw-evidence hashes. An exact 3 dB or 6 dB request now selects this verified
candidate automatically and re-runs the unchanged fresh physical gate. The
registry is a classical safety and product component; it is not RL ranking.

Evidence: `product_audits/entry115_physical_recovery_20260908/summary.json`,
`recovery.jsonl`, `sha256.json` and the ten nested candidate directories.
