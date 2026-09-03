# Next-session prompt: Nebula Entry 87 margin-adaptation RL

Continue in `C:\Users\DELL\Desktop\serdes-dsp-framework-main`. Read
`HANDOFF.md`, `CLAUDEwa.md`, `AGENTS.md` and `PREDICTIONS.md` Entry 87 first.

D16 adopted Entry 86's verified 7.3 dB attenuator. D17 authorises Entry 87's
exact margin-adaptation contract. Preregistration must be committed before any
environment/control/policy implementation or training.

The immutable source is `experiments/joint_bank_73_run.jsonl.gz`, decoded
SHA-256
`1B5F941DF4B34F3C90F6DD050F264D8A77C7BB2E5CE4D9EED8CC29EBD9F9843F`.
Never rerun or edit its 23,040 real-PMOS rows.

The experiment was implemented in two ordered stages:

1. fail-first tests, the new 512-code environment, and all non-RL controls;
   `margin_adapt_controls_results.json` was committed before policy code;
2. fail-first categorical-PPO tests, exactly five registered 200,000-step
   seeds, and one held-out evaluation. Every result and checkpoint is now
   preserved.

Do not mutate `rl/adapt_env.py`, `exp_adapt_controls.py` or their artifacts;
they are the historical 64-code compliance experiment. Do not tune on `sf/fs`
or 4.5/7.5/10.5 dB. Do not change the registered reward, horizon, split,
hyperparameters, seeds or Q1-Q8 gates after seeing any result. No SPICE call is
needed: every transition is a frozen-table lookup.

Deployment seed is preselected as `2026090300`; do not choose the best seed
after evaluation. If any gate misses, report the honest negative result and
retain the strongest non-RL fallback.

## Current state

Stage 1 is committed as `52dabac`. Fourteen focused tests pass. The zero-SPICE
control artifact SHA-256 is
`4E7930C6EF353B81949F7D8C6562D6E4027F7B164F3B0099AD79FE652E09501D`.
The primary comparator is the request-conditioned fixed lookup: compliance
0.9931, mean q 0.6796, one trial. Therefore RL needs compliance >=0.9831 and
mean q >=0.6996 plus the registered CI/reproducibility gates.

Categorical PPO and the five-seed runner were frozen in implementation commit
`c1e0791`; the exact-key plumbing repair is `15c531d`. Before training, the
Entry 87 focused group passed 23/23 and the complete suite passed 2,630/2,630.

The exact-key repair is commit `15c531d`. All five registered seeds then
completed 200,000 steps with changed weights, finite telemetry and zero SPICE
calls. The held-out set was evaluated once. Q1-Q5 and Q7-Q8 pass; **Q6 fails**:
mean quality improved only 0.00287 against the required 0.0200, and the paired
95% CI lower bound is effectively zero. Overall Entry 87 is an honest negative
result. See `MARGIN_ADAPT_RL_RESULTS.md` and preserve all artifacts.

Do not rerun, retune, replace a seed, change the reward/gates, or evaluate a
new policy on this exposed TEST set. The current deployable controller is the
request-conditioned fixed lookup. A future RL attempt requires an
owner-approved new preregistration and an untouched validation set.
