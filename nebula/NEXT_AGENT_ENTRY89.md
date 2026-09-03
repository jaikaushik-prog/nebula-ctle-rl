# Next-session prompt: Nebula Entry 89 shielded oracle-warm-start RL

Continue in `C:\Users\DELL\Desktop\serdes-dsp-framework-main`. Read
`HANDOFF.md`, `CLAUDEwa.md`, `AGENTS.md`, `PREDICTIONS.md` Entry 89,
`MARGIN_IMPROVE_RL_RESULTS.md` and this file before acting.

Decision D19 is the owner's approval of one final safety-focused rescue:
oracle imitation/action ranking plus a hard best-compliant-visited shield and
fresh held-out data. Entry 87 and Entry 88 are immutable negative results. Do
not rewrite their policies, rewards, splits, artifacts or reports.

## Question and claim boundary

Can oracle-warm-started masked PPO retain Entry 88's useful eye-quality moves
while a structural verifier shield prevents any compliance loss relative to
the fixed start?

The shield is simulator-backed. Compliance remains hidden from the policy but
is available to the existing device/link verifier after a setting is measured.
This can support the zero-human simulator sizing flow; it is **not** evidence
for a receiver-only on-silicon calibration loop unless equivalent monitors are
built and validated later.

## Immutable development source

- Use `experiments/joint_bank_73_run.jsonl.gz`, decoded SHA-256
  `1B5F941DF4B34F3C90F6DD050F264D8A77C7BB2E5CE4D9EED8CC29EBD9F9843F`.
- DEVELOPMENT contains all 5,040 now-exposed Entry 88 identities: 45 corners,
  seven losses `3/4.5/6/7.5/9/10.5/12` dB and the 16 registered requests.
- Development use is unrestricted but every diagnostic is labelled exposed;
  it cannot be used as final evidence again.
- The request-conditioned fixed starts are selected from DEVELOPMENT only by
  Entry 88's existing deterministic rule.

## Oracle imitation, then unchanged PPO

- Same 62-value policy observation and seven masked actions as Entry 88. PVT,
  channel loss, compliance, non-eye rows, q and oracle remain hidden from the
  actor.
- For each DEVELOPMENT identity, the teacher target is the compliant setting
  with maximum eye area among settings within seven Manhattan moves of the
  fixed start. Ties use lower setting ID.
- Teacher trajectories use shortest paths. At each state the supervised target
  is uniform over every currently valid action that reduces Manhattan distance
  to the teacher target; the lowest-index reducing action advances the recorded
  trajectory, while the loss retains the uniform soft target. At the target it
  is LOCK. If the target is the initial start, that identity contributes no BC
  transition rather than an action that Entry 88's initial mask forbids. No
  arbitrary axis receives extra loss weight.
- Pretrain the actor for exactly 50 epochs, Adam `lr=3e-4`, batch 256, shuffled
  by the registered seed. Cross-entropy is the only imitation loss.
- Fine-tune with Entry 88's unchanged environment, telescoping reward and PPO
  defaults for exactly 200,000 DEVELOPMENT steps. There is no new reward
  weight, range or spec tolerance.
- Five seeds: `2026090500..2026090504`; deployment seed is preselected as
  `2026090500`. Each invocation writes distinct BC, final policy and summary
  artifacts and refuses overwrite.

## Structural safety shield

- The policy chooses which settings to measure and sees only its registered
  observation.
- After every measurement the existing simulator verifier supplies a Boolean
  compliance verdict to the shield, never to the policy.
- The shield retains all verifier-compliant visited settings, including the
  fixed start, and returns the one with maximum **visible eye area**. Ties use
  earliest measurement and then lower setting ID.
- If no visited setting is compliant, it returns the fixed start and records a
  shield failure. Therefore, identity by identity, any compliant fixed start
  must remain compliant after shielding.
- Policy termination and the eight-measurement budget remain unchanged. The
  shield does not create free measurements.

## Fresh FINAL TEST generated only after policy freeze

Implement but do not run a midpoint-bank generator before training. Only after
all five policies are committed may it run the same 512 settings x 45 corners
= 23,040 real-PMOS ngspice evaluations, with link views at the exact midpoints
between prior channel losses:

`3.75, 5.25, 6.75, 8.25, 9.75, 11.25` dB.

FINAL TEST requests are also exact midpoints of the old grid:

- peaking: `5, 7, 9` dB;
- frequency: `1.25e9 * 2**k` for `k = 0.265, 0.500, 0.735`.

This gives `45 x 6 x 9 = 2,430` identities with zero request/loss overlap with
DEVELOPMENT. They are fresh link/request views of the same circuit/PVT lattice,
not new silicon or new transistor geometries. New-request starts are selected
without FINAL data: nearest registered DEVELOPMENT request in the same
normalized `(peaking, log2-frequency)` coordinates already used by the
observation, with tuple order breaking exact ties.

The raw journal must be crash-resumable and membership-gated. Compress it,
record raw and decoded SHA-256, and commit it without scoring any FINAL request.
The single final evaluator may run only after the five policies and complete
journal validate.

## Controls and reporting

On DEVELOPMENT before policy freeze, report fixed, the five frozen Entry 88
PPO policies with and without the new shield, oracle-teacher trajectories and
the five Entry 89 policies with and without shielding. These are diagnostics,
not fresh evidence.

On FINAL TEST exactly once, report:

1. fixed nearest-request start;
2. frozen Entry 88 deployment PPO with the shield;
3. each Entry 89 unshielded policy;
4. each Entry 89 shielded policy (primary arm);
5. global and seven-move reachable hidden oracles.

Use the unchanged 10,000-resample paired percentile bootstrap, analysis seed
`2026090589`, aligned by exact identity. Report compliance, q, q delta, trials,
false locks, shield fallbacks, code-change rate and verifier calls.

## Registered gates

| gate | PASS condition |
|---|---|
| R1 provenance | Exact DEVELOPMENT hash/membership; five policies frozen before the midpoint journal; FINAL=2,430 exact identities and scored once |
| R2 observation | Tests prove no PVT/loss/compliance/q/oracle reaches the actor |
| R3 imitation | Teacher is DEVELOPMENT-only, seven-move reachable, shortest-path soft labels exact; BC artifacts finite and changed |
| R4 training | All five seeds complete 50 BC epochs plus exactly 200,000 finite PPO steps; distinct non-overwriting artifacts |
| R5 structural safety | Every compliant fixed start remains compliant after shielding in tests, DEVELOPMENT and FINAL; mean and deployment FINAL compliance are not below fixed |
| R6 quality | Primary five-seed mean FINAL q is at least fixed +0.0200 and paired 95% CI lower bound is >0 |
| R7 reproducibility | At least 4/5 primary seeds have positive paired q delta and deployment seed is positive |
| R8 cost | Mean primary trials <=8 and below 512; verifier calls equal billed measurements |
| R9 attribution/reporting | All registered controls, per-seed values, shield interventions/failures and unshielded-vs-shielded deltas are present |
| R10 scope | Report calls the shield simulator-backed and makes no receiver-only or silicon claim |

All R1-R10 must pass to claim a useful **simulator-backed, safety-shielded RL
contribution**. Any miss is preserved. No post-FINAL tuning, seed replacement,
gate change or second midpoint evaluation is permitted.

The preregistration-only complete non-slow baseline passes 2,662/2,662, with
13 deselected and 2 known warnings in 583.34 s.

## Stage 1 core boundary -- before BC/PPO runner

`rl/safety_shield.py` implements the simulator-backed selection exactly as
registered. `rl/oracle_imitation.py` builds DEVELOPMENT-only reachable-oracle
targets and shortest-path soft action labels; the actor-facing sample contains
only observation, action mask and target probabilities. Eight fail-capable
tests failed first on absent modules and now pass 8/8. No BC epoch, Entry 89 PPO
step, midpoint SPICE row or FINAL score exists. Commit this boundary before
implementing the training runner or generalizing the bank sweep.

The complete non-slow suite passes 2,670/2,670, with 13 deselected and 2 known
warnings in 537.99 s.

## Stage 2 exposed-DEVELOPMENT shield control -- before Entry 89 policy code

The control runner replays all five immutable Entry 88 policies over the full
5,040 exposed identities and applies the registered shield to the same measured
traces. Fixed compliance/q is 0.9925/0.6703. Shielded policy compliance is
0.9946-0.9982 and every seed retains q delta +0.1347 to +0.1535 at 3.612-3.895
measurements. D1 safety and D2 quality pass. The teacher ceiling is q=0.9835 at
mean distance 4.677. Artifact SHA-256:
`82F868B94A6D80C790C104ABF7383DC2257E919DC8E2441D9509D44AC066FF45`.

This is exposed diagnostic evidence only. FINAL remains
`NOT_GENERATED_NOT_SCORED`; zero new SPICE ran. Commit the runner, artifact,
tests and report before implementing the BC/PPO trainer. The complete non-slow
suite passes 2,675/2,675, with 13 deselected and 2 known warnings in 540.51 s.

## Stage 3 five-policy freeze -- before fresh midpoint generation

All seeds `2026090500..04` completed exactly 50 actor-only imitation epochs and
200,000 unchanged-default PPO steps. All fifteen BC, final-policy and summary
artifacts are finite, distinct and hash-frozen. The complete suite passes
2,690/2,690 after the DEVELOPMENT evaluator and manifest gates were added.

On all 5,040 exposed DEVELOPMENT identities, fixed compliance/q is
0.9925/0.6703. Entry 89 unshielded compliance is 0.7657-0.9631. Applying the
registered shield to the identical traces produces compliance 0.9980-0.9986
and q delta +0.1507 to +0.2214 at 4.669-7.465 measurements. Every compliant
fixed start is retained; D3-D5 pass. This is exposed mechanism evidence only.

The DEVELOPMENT result SHA-256 is
`9D462EE4F3FE97AFEF1FD372817A0672487A33AD3C46A794DCE3AB390C9EFFBF`.
The exact five-policy freeze manifest SHA-256 is
`3E910DECEFD7CAAA5D401655E77C310F8BE4A645DD48538EEE4E1531199734DB`.
FINAL remains `NOT_GENERATED_NOT_SCORED`; no midpoint row exists. Commit this
entire stage before running the midpoint generator. Then generate, validate,
compress, hash and commit all 23,040 rows without scoring any FINAL request.

## Stage 4 fresh midpoint evidence -- before FINAL evaluator

The five-policy freeze commit is `a84082e`. Only after that commit, the exact
midpoint generator completed all 23,040 real-PMOS ngspice setting/corner rows
in 7,859.41 s (130.99 min). Structural validation finds all 512 settings, all
45 corners and 23,040 unique pairs. The raw SHA-256 and the decoded-gzip
SHA-256 are both
`99B6BF526EE610CF39EBC921A2B8BEA2EA482A610354056569B2A176AA1169E2`;
the gzip SHA-256 is
`AE57F93E9636DC135C9E3B86DD37B9B59BE14C3A5DA511EAC4202101E529E9C4`.
Metadata SHA-256 is
`1C5C9527A1A982BD8C82373F98CE3AFDFD021C1AC542D04CF4FAB9D0C2612D65`.

The metadata status is exactly `GENERATED_NOT_SCORED`. None of the nine FINAL
requests or 2,430 FINAL identities has been evaluated. Commit the gzip,
metadata and this evidence boundary before implementing the fail-first FINAL
evaluator. After that commit, implement the evaluator exactly as registered in
the FINAL TEST section above, run the complete suite, and execute FINAL once.
The post-generation non-slow suite passes 2,690/2,690, with 13 deselected and
the two known warnings in 374.79 s.

## Stage 5 FINAL evaluator implementation -- before its one allowed run

Fresh evidence is frozen separately in commit `51a1146`. The one-time evaluator
is implemented in `experiments/exp_shielded_final.py`, with exact provenance,
identity, nearest-DEVELOPMENT-start, reporting, R1-R10 and no-overwrite gates.
Its six tests first failed because the module was absent and now pass 6/6. The
tests caught a binary-floating-point perturbation of the exact 0.500-octave tie;
the comparison now quantizes the distance before the required tuple-order tie
break.

No FINAL result exists and the evaluator has not run. Run the complete non-slow
suite and commit code, tests and handoff together. Only after that commit invoke
`python -m nebula.experiments.exp_shielded_final --evaluate` once. Preserve any
PASS or FAIL without rerunning or changing a gate.

The evaluator-boundary non-slow suite passes 2,696/2,696, with 13 deselected
and the two known warnings in 294.19 s.
