# Deadline engineering results - 15 September 2026

## What changed, and what did not

The approved programmable-reference check used exactly two NGSpice invocations,
each capped at180 seconds, and finished in78.514194 seconds driver wall.
No further simulation, training, layout or design campaign was launched.
Final physical CTLE setting352 and its saved acceptance evidence are unchanged.
Combined end-to-end target-grid coverage remains4/12.

## 1. Programmable Rs/Cs under transistor-DFE loading

The existing N500/no-fixed-MIM programmable reference was measured at29 distinct
previously measured control pairs plus the calibrated baseline at each batch end.
Each held-clock state therefore has31 OP/AC snapshots;62 total. Devices, bias,
supply1.8V, temperature27C, models and exact netlist bodies were unchanged.
Both starting/ending baselines reproduce their saved raw OP/AC. The319-file PDK
closure,91 source bindings and simulator binary stayed unchanged.

Saved standalone AC matches10/12 targets. This new bounded LOADED sample matches
5/12 in both held states, at the original internal0.5dB/100MHz tolerances:

| Target | Measured peaking, both states | Peak frequency, both states | R-control/VDD | C-control/VDD |
|---|---|---|---|---|
| 6dB /1.9GHz | 5.926-5.929dB | 1.852-1.855GHz | .730 | .165 |
| 6dB /2.5GHz | 5.584-5.589dB | 2.426-2.429GHz | .730 | .240 |
| 9dB /1.25GHz | 9.240-9.242dB | 1.250-1.253GHz | .700 | .030 |
| 9dB /1.9GHz | 8.744-8.747dB | 1.903-1.906GHz | .700 | .185 |
| 12dB /1.9GHz | 11.663-11.666dB | 1.901-1.904GHz | .650 | .195 |

No match in this bounded sample:3dB at all three frequencies,6dB/1.25GHz,
9dB/2.5GHz,12dB/1.25GHz and12dB/2.5GHz. This is not an exhaustive loaded map;
failure to match here does not prove no possible control can match.

All signed model-domain findings are retained. The AC gate is an existing model
envelope/shape gate, not full signed-domain acceptance. No new noise, HD3, eye,
runtime retuning, analog PVT or link-PVT result is inferred. Static control setting
is not dynamic retuning. These are reference controls, not replacements for352.

Reproduce the read-only check:
`py -3.13 -m nebula.experiments.review_loaded_tuning_bound`

It checks226 archived files and recomputes62 rows. Evidence:
`nebula/product_audits/entry158_loaded_tuning_20260915/`.
Summary SHA-256:`aedb02fbc6c30b92e4ff3c7c2679088fba1e958cf3dbc59c5d66feafeee30583`.
The approved simulator budget is exhausted. Do not rerun the experiment.

Professor-ready takeaway: the physical tuning network is real, but connecting
the DFE changes the frequency response. Nominal standalone target coverage does
not automatically become loaded-receiver coverage.

## 2. RL speed and near-optimality

`nebula/deadline_evidence.py` now recomputes the comparison from pinned saved
per-identity rows and workflow receipts. This is an evidence implementation,
not new learning, a faster policy or a newly held-out benchmark.

| Quantity | Recomputed result | Claim boundary |
|---|---|---|
| Exposed cached evaluation | 12,150 rows =2,430 identities x5seeds | Same512-setting bank; not continuous global optimum |
| Mean bank-oracle regret | .2830982744 | Near-optimality not established |
| Within .05 of bank oracle | 20.90535% | No new threshold or acceptance rule |
| Mean cached visits | 5.57942 | 91.7657x fewer than512 table visits; not SPICE speedup |
| RL complete workflow arm | 9/12 delivered;1,644 charged calls;949.913972s | All attempted work retained |
| Classical complete workflow arm | 8/12 delivered;1,644 charged calls;929.424036s | One non-delivery is a Windows ledger failure |
| Eight both-success pairs | Median classical/RL time=.939415 | Conditional, descriptive; no RL speed advantage |

The learned proposer is real; deterministic shielding and ascending eligible
candidate recovery contribute substantially. No code change today fixes the
unproven speed or optimality claims. Establishing either requires a separately
registered, fairly costed experiment; training and broad benchmarks are not
authorized by the two-call nominal approval.

Professor-ready takeaway: fewer cached candidate visits are demonstrated;
faster complete physical design is not. Keeping these denominators separate
makes the RL contribution defensible.

## 3. Selected-receiver PMOS/PVT gap

The selected352 CTLE plus transistor DFE nominal record remains64/64 bits,
296.981mV sampled eye and9.263600mW VDD draw. Its exact selected-CTLE hash binds
the evidence; the independent programmable reference cannot supply its PVT.

Six attenuator PMOS devices (`Xatt_swp0/1/2`, `Xatt_swn0/1/2`) have signed Vds
violations. All six Vds intervals straddle zero; the largest positive excursion
is about63.212mV. The two off devices in branch1 also have+298.977mV Vgs.
These are drawn-terminal model-domain findings, not a claim of measured damage.
They cannot be closed by swapping source/drain labels: the opposite portion of
each bipolar waveform would then have the wrong sign, and off-state Vgs remains.

The nominal link corner is one of45 required selected-receiver corners;44 are
unverified. Complete receiver analog-PVT is also missing. Do not transfer the
independent reference's45-point link result or selected-CTLE ideal-DFE315-point
result to this transistor receiver.

A credible next step requires a human-approved switch/topology or model-domain
decision, a nominal instrument check and signal recheck, followed by a separately
budgeted PVT plan. No PMOS dimensions, topology, model ranges, signed checks or
historical results were changed. Full receiver verification remains false.

## Read-only access and remaining work

`py -3.13 -m nebula.deadline_evidence` returns the recomputed evidence. The web
application exposes it under Run files > Additional engineering diagnostics.
The JSON download triggers no simulator, training or design job.

Focused tests:14 baseline;21 after tuning implementation; three additional
deadline-evidence tests pass. Broad regression is deliberately deferred by the
owner. Recording remains the owner's task. Measured-channel/BER validation is
not performed by this change; no measured channel has been substituted and a
64-bit noiseless waveform is not BER evidence.
