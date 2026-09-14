# Submission physical recovery coverage and matched timing protocol

Status: PREPARATION ONLY until committed unchanged and a preflight manifest exists. The lead alone schedules simulations. This plan is fixed before any new measurements; all targets are exposed engineering diagnostics, never a held-out test.

## Purpose and scope

Measure whether automatic recovery can replace a failed fixed physical CTLE candidate, how much the complete delivered workflow costs, and which declared targets it can answer. The circuit is the existing physical-reference CTLE with ideal behavioral one-tap DFE scoring. This is not the separate 73-device transistor receiver, analog-PVT closure for that receiver, full S7 area compliance, or complete continuous target-range coverage.

No topology, geometry range, reward, tolerance, solver setting or physical acceptance gate changes. Each attempted candidate receives the existing fresh verifier: 45 PVT corners times seven constructed losses, 315 model conditions, with 137 maximum fresh ngspice invocations per candidate. Accepted cached rows never substitute for fresh physical evidence.

## Matched arms and recovery

Both arms use the same cached 512-setting bank, all-condition fixed-eligibility intersection, hash-checked verified registry, unchanged physical measurements, exact circuit export and drawing work. Exact registry selections are available to both arms and still remeasured.

RL uses the actual existing frozen policy proposer and retains its recorded selection role. Classical bypasses the policy proposer entirely. Both then traverse the identical eligible settings in the existing ascending fallback order, skip already-tried settings, stop at the first fresh accepted candidate, and allow at most eight distinct candidates. No candidate is retried with altered numerics. Every rejected attempt, simulator failure and export failure remains recorded and billed. An empty bank intersection means no eligible cached setting, not physical impossibility.

A workflow succeeds only if the recovered design passes the unchanged complete physical gate and request check and the exact netlist, schematic, design JSON and explanation are all written successfully. The last failed design remains inspectable when available. Missing/unknown simulator accounting stays unknown; it is never replaced with zero. A numerical instrument/provenance failure is separate from a measured physical rejection.

## Frozen target coverage

One RL workflow at each Cartesian point, ordered by boost then frequency:

- Boosts: 3, 6, 9, 12 dB.
- Frequencies: 1.25, 1.9, 2.5 GHz.

The thirteenth workflow is 6 dB at 2.1 GHz, an explicitly exposed diagnostic whose earlier fixed candidate passed 314/315 conditions. Its recovery is not a held-out success. Every target uses all seven characterized losses and all 45 PVT corners; there is no channel-loss override.

Coverage outcomes report delivered success, request errors, all attempted settings, failed specifications, total billed calls and complete workflow time. Empty eligibility, exhausted physical candidates, instrument errors and unfinished jobs remain separate statuses. Unrun targets remain unrun.

## Frozen matched timing subset

Four predeclared targets: 3 dB/1.9 GHz, 6 dB/2.1 GHz, 9 dB/1.9 GHz and 12 dB/2.5 GHz. Run three repetitions of both arms at every target: 24 fresh workflows total.

Repetition is the outer loop and the target order above is the inner loop. Arm order is RL then classical when repetition plus target index is even; classical then RL otherwise. This counterbalances order across the complete set. Do not choose order, repetitions or target inclusion after seeing favorable timings. Coverage jobs never replace benchmark jobs: their purpose and process-order protocol differ.

Every workflow starts in a fresh Python interpreter. The parent timer starts immediately before process creation and ends after process exit; it includes process startup, parsing, imports, policy/classical selection, all recovery attempts, fresh verification, exact netlist export, schematic drawing, design JSON/explanation writes and workflow receipt serialization. Parent journal/summary bookkeeping after process exit is outside that workflow timer. The common helper also records parsing, selection, physical and export phases with an explicitly narrower entry-to-output timer.

The controller refuses an occupied ngspice slot before each job, and a shared atomic recovery lock prevents overlapping recovery jobs across the web and benchmark. These guards do not prove absence of unrelated system load; record operator isolation and any observed interference. No OS/file cache flush is performed. Preflight hashes assets/models and therefore touches filesystem pages. Fresh-process does not mean cold filesystem or cold simulator libraries. Environment metadata records Python, ngspice executable identity, source and compressed asset hashes, and the actual five-corner PFET-capable PDK include closure without copying PDK model content.

## Budget and stopping rules

A single batch contains 13 coverage plus 24 benchmark workflows, each capped at eight candidates. The mathematical ceiling is 40,552 calls (37 x 8 x 137), not a promised work schedule.

The hard batch wall budget is 10,800 seconds from the first measurement launch, shared across coverage and benchmark commands. Gaps between commands consume that budget. If all 37 workflows reach exactly one candidate, 137 calls per workflow would total 5,069 calls. Empty eligible sets consume zero SPICE calls and reduce that subtotal; recovery adds calls. Actual per-call cost and rejection rate determine whether it fits; there is no assumed speed claim. The lead checks remaining submission time before starting.

Stop at the registered wall deadline, an incomplete/unknown call ledger, lost provenance, an occupied simulator slot, or a worker/instrumentation error. A scientific rejection or empty eligible set alone does not truncate the remaining predeclared schedule. Preserve partial results and explicitly show every unrun row. Do not replace failed or slow runs. Timeout termination stops only the owned child process tree, preserves its directory, and marks incomplete call counts unknown.

## Analysis and reproducibility

Report separate coverage and benchmark tables. Do not pool the extra RL-only coverage runs into an RL-versus-classical success comparison.

Within benchmark results, report each arm's delivered success fraction, all-workflow elapsed cost, all fresh calls, recovery depth, final request error and selected circuit identity. Compute paired classical/RL elapsed ratios only for the same target/repetition where both delivered successfully. Show failures and their costs alongside those conditional ratios. Ratios above one favor RL; below one favor classical. Three repeats are descriptive; no universal speedup or significance claim follows. Do not substitute bank-normalized quality q for physical request/error outcomes.

Commands from the repository root, with a fresh output directory:

    py -3.13 -m nebula.experiments.exp_submission_recovery_benchmark preflight --out <batch>
    py -3.13 -m nebula.experiments.exp_submission_recovery_benchmark coverage --out <batch>
    py -3.13 -m nebula.experiments.exp_submission_recovery_benchmark benchmark --out <batch>
    py -3.13 -m nebula.experiments.exp_submission_recovery_benchmark check --out <batch>

Preflight and check run no SPICE. Preflight pins this committed plan and environment. Measurement refuses changed pins. Each job preserves input, stdout/stderr, its complete raw physical directories, final artifacts and receipt. The parent retains workflows.jsonl and summary.json even for failure. No existing report, registry entry, accepted artifact or historical evidence is rewritten.

