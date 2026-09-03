# Next-session prompt: Nebula Entry 88 improvement-reward RL

Continue in `C:\Users\DELL\Desktop\serdes-dsp-framework-main`. Read
`HANDOFF.md`, `CLAUDEwa.md`, `AGENTS.md`, `PREDICTIONS.md` Entry 88 and
`MARGIN_ADAPT_RL_RESULTS.md` before acting.

Decision D18 is the owner's exact approval of this contract. Entry 87 is an
immutable negative result and its exposed TEST identities, checkpoints,
summaries, reward, code and result must not be rewritten.

## Immutable source and split

Use `experiments/joint_bank_73_run.jsonl.gz`, decoded SHA-256
`1B5F941DF4B34F3C90F6DD050F264D8A77C7BB2E5CE4D9EED8CC29EBD9F9843F`.
No SPICE run is needed.

All 16 requests are present in both splits.

- TRAIN, 2,592 identities: Entry 87's complete exposed union:
  - processes `tt/ss/ff` at 3/6/9/12 dB; and
  - processes `sf/fs` at 4.5/7.5/10.5 dB.
- FINAL TEST, 2,448 policy-untouched identities: the exact complement:
  - processes `tt/ss/ff` at 4.5/7.5/10.5 dB (1,296); and
  - processes `sf/fs` at 3/6/9/12 dB (1,152).
- Overlap must be zero and union must be all 5,040 identities.

The transistor rows have been used in earlier hardware coverage summaries, so
call FINAL TEST **policy-untouched**, not wholly unseen silicon data. No Entry
87 policy or controller was evaluated on these exact identity combinations.

## Episode and human-approved reward

Create new Entry 88 modules/artifacts; do not mutate Entry 87 behavior.

- Same receiver-visible 62-value observation: request, current code and ordered
  valid/eye-height/eye-width measurement history. PVT, channel, compliance,
  non-eye rows, quality and oracle remain hidden.
- Same request-conditioned fixed start, selected from Entry 88 TRAIN only.
- Initial measurement counts toward the eight-setting budget.
- Same six one-axis moves plus `LOCK`.
- Mask moves that cannot change the code at a boundary.
- Mask `LOCK` until at least one real move has been measured (`n_trials >= 2`).
- Define hidden `q(setting)` exactly as Entry 87: compliant eye area divided by
  the best compliant eye area for the exact hidden identity, clipped to [0,1];
  noncompliant settings have q=0.
- On a move: `reward = q_new - q_previous`.
- On compliant `LOCK`: reward 0.
- On false `LOCK`: `reward = -1 - q_current`.
- The eighth measurement auto-locks with the same terminal rule.

Thus the undiscounted raw episode return is exactly `q_final - q_start` for a
compliant finish and `-1 - q_start` for a false finish. There is no separately
tuned reward scale or trial-cost weight. Trial count remains an explicit gate.

## Controls-first sequence

Stage 1 must be fail-first tested, run only on TRAIN, and committed before any
Entry 88 policy implementation:

1. request-conditioned fixed start;
2. masked random local policy, 20 fixed seeds `20260904100..20260904119`;
3. visible-eye coordinate hill-climb;
4. exhaustive maximum-visible-eye control;
5. hidden global oracle;
6. hidden oracle restricted to codes reachable within seven Manhattan moves
   of the TRAIN-selected start.

Record the reachable quality headroom and movement-distance distribution. The
FINAL TEST comparator and oracles are not scored until final evaluation.

## PPO and evaluation

- New masked categorical PPO; separate `(64,64)` tanh actor/value trunks.
- Retain Entry 87 optimizer defaults unchanged: rollout 64, epochs 10, four
  minibatches, lr 3e-4, gamma 0.99, GAE 0.95, clip 0.2, value coefficient 0.5,
  entropy coefficient 0, gradient norm 0.5.
- Exactly 200,000 TRAIN steps for each seed `2026090400..2026090404`.
- Preselected deployment seed: `2026090400`.
- One durable invocation/checkpoint/summary per seed; refuse overwrite.
- Evaluate deterministic masked-argmax policies on all 2,448 FINAL TEST
  identities exactly once, only after all five healthy artifacts exist.
- Paired bootstrap: 10,000 resamples, analysis seed `2026090488`, percentile
  95% interval aligned by exact identity.

## Registered gates

| gate | PASS condition |
|---|---|
| Q1 source/split | Source hash matches; TRAIN=2,592, TEST=2,448, overlap=0, union=5,040 |
| Q2 environment | Fail-first tests prove observation non-leakage, exact masks, reward telescoping, horizon and auto-lock |
| Q3 controls first | TRAIN-only controls and reachable oracle are committed before policy code/training; TEST has not been scored |
| Q4 training integrity | All five seeds complete exactly 200,000 finite steps, weights change, artifacts are distinct/non-overwriting |
| Q5 safety | Mean and deployment TEST compliance are no more than 1 percentage point below the paired fixed comparator |
| Q6 quality | Mean TEST q is at least comparator +0.0200 and paired 95% CI lower bound is >0 |
| Q7 reproducibility | At least 4/5 seeds have positive paired q delta and deployment seed is positive |
| Q8 cost/reporting | Mean trials <=8 and <512-setting exhaustive; per-seed returns, compliance, q, trials, false locks, code-change rate and controls are reported |

All eight must pass to claim a useful RL contribution. Any miss is preserved
as an honest result. Never tune or replace a seed after FINAL TEST exposure.

