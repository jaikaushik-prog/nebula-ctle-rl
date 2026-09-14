# Separately registered second analog attempt (14 September 2026)

Registered before a new simulator call, with explicit lead authorization after
review of the interrupted first attempt. This is a fresh execution of the exact
12-call protocol in DFE_ANALOG_PVT_SUBMISSION_PLAN.md: TT/1/27 followed by
FS/.95/125, six calls each, unchanged decks, geometry, solver settings, gates,
initialization, source controls, and stopping rules. No retry within either run.

## Original interruption and separate cost

The first pilot launched five calls and completed four. Its fifth nominal tone
log ends around 86.29 ns; no completed trace/result exists for that call. No
Python or ngspice process remained when the lead resumed supervision. The
termination cause is unknown. No FS call ran, no four-setting nominal HD3 gate
completed, and no completed pilot or analog PVT coverage is claimed. Original
source snapshots, config, results, logs, and partial fifth call remain untouched.
The additive interruption closeout preserves exact raw replay of all four
completed measurements and the original source/PDK identities.

The completed simulator durations were 28.110, 29.806, 50.784 and 57.975 s;
completed measurement durations total 172.439 s. With similar stress cost,
twelve new calls are estimated at 10-12 minutes including extraction. This is
an estimate, not a guarantee. The incomplete fifth call cost is unknown and
is separately billed as one launched call, never silently omitted.

## New bounds and provenance

Fresh output: `nebula/product_audits/submission_analog_pvt_20260914/second_attempt/`.
Maximum 12 new calls, 17 launched calls total across both attempts, 180 s per
call, 1200 s measured wall budget including preflight/extraction. Reserve the
full 180 s timeout before each launch. No expansion or third attempt is
authorized. Lossless trace archival/verification follows simulator completion.
The measured wall ceiling constrains launch decisions; final extraction and
metadata closeout may add a small overhead after the last simulator timeout.

The only runner change is an explicit validated wall-budget argument: default
2700 s retained, finite allowed range 180-2700 s, this invocation 1200 s. Both
registration plans and the revised scheduler/tests enter the new source snapshot.
The old snapshot remains authoritative for the interrupted attempt; it is not
rewritten to match current scheduling source. Frozen scientific prerequisite
source/PDK checks and all nominal exact-byte deck checks remain in force.

Command: `py -3.13 -u -m nebula.experiments.exp_dfe_analog_pvt_submission --out nebula/product_audits/submission_analog_pvt_20260914/second_attempt --wall-budget-seconds 1200`.

All original limitations remain: two sampled analog corners cannot establish
45-corner analog coverage; held-branch noise is not periodic receiver noise;
passive nonlinearity and full receiver/S9 signoff remain unverified.
