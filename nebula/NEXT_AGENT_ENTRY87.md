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

Implement in two commits:

1. fail-first tests, the new 512-code environment, and all non-RL controls;
   run and commit `margin_adapt_controls_results.json` before policy code;
2. fail-first categorical-PPO tests, train exactly five registered 200,000-
   step seeds, evaluate the held-out set once, and preserve every result and
   checkpoint.

Do not mutate `rl/adapt_env.py`, `exp_adapt_controls.py` or their artifacts;
they are the historical 64-code compliance experiment. Do not tune on `sf/fs`
or 4.5/7.5/10.5 dB. Do not change the registered reward, horizon, split,
hyperparameters, seeds or Q1-Q8 gates after seeing any result. No SPICE call is
needed: every transition is a frozen-table lookup.

Deployment seed is preselected as `2026090300`; do not choose the best seed
after evaluation. If any gate misses, report the honest negative result and
retain the strongest non-RL fallback.
