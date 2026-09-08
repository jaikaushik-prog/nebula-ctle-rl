# Winning-sprint protocol - Entry 115 (2026-09-08)

This protocol is frozen before any Entry-115 outcome is computed or any new
SPICE candidate is measured. It strengthens two claims that the competition
brief asks directly: reduction against exhaustive search and automatic recovery
when the first physical candidate fails. It does not alter the frozen Entry-89
policies, reward, tolerances, existing measurements, PDK models or final demo.

## A. Exhaustive-oracle regret and visit reduction

Use the already exposed Entry-113 eight-visit PPO trajectories and the same
fresh-midpoint 512-setting table. For every one of the 2,430 identities and
each of the five frozen PPO seeds, exhaustively score all 512 settings through
the same compliance predicate and quality function used by the shield.

Report PPO and oracle compliance/quality, quality regret, fractions within
0.01 and 0.05, actual and unique visits versus 512, cached scoring wall time,
and 95% request/loss-block intervals. Near-optimality is supported only if mean
regret is at most 0.05 and at least 90% of oracle-solvable identities are within
0.05. Candidate-visit reduction is supported if the mean ratio is at least 20x.
Cached wall time is not SPICE speedup. Offline characterisation and training
costs remain costs. This exposed-data diagnostic is not a new held-out result
and does not establish performance for the later physical-bias circuit.

## B. Fixed physical-candidate recovery

Measure every remaining eligible candidate for the two multi-candidate targets
whose first physical candidate missed only the swing guard, in this fixed order:

- 3 dB / 1.9 GHz: 401, 337 (273 is the preserved first failure).
- 6 dB / 1.9 GHz: 481, 474, 473, 417, 410, 353, 352, 346
  (288 is the preserved first failure).

The order is decreasing input-attenuation code, then decreasing setting within
the code. More attenuation lowers demanded output swing. All candidates run,
even after a pass. Each uses one fixed circuit across 45 PVT corners and seven
channels, the unchanged 137-call ceiling, and a new anti-overwrite directory.
Any automatic product retry must export the actual passing circuit and bill all
calls. This remains classical recovery unless a separately frozen learner ranks
it; it is not relabelled RL selection.

## Gates and stopping rules

1. Verify existing hashes and identities before use.
2. Refuse uncommitted protocol text and existing outputs.
3. Change no target, tolerance, reward, model, load or PVT point after results.
4. Retain failures and stop after the ten listed candidates.
5. Endpoint expansion, transistor DFE and layout need separate protocols.
6. Run the required full tests before and after changes.
