# Submission analog PVT extension (14 September 2026)

Registered before any new simulator call. Owner authorization: final-submission
packet Task A; lead controls the exclusive simulator slot. This extends the
fixed Entry 143/144 integrated checkpoint, never the selected 3 dB product.

## Coverage audit and purpose

Entry 143 has two negative-branch held-clock OP/AC/noise checks and four
clocked HD3 numerical checks, all TT / 1.8 V / 27 C. Entry 144 has 45 finite,
noiseless link checks, not analog AC/noise/HD3 PVT. Both use the same calibrated
R=.70 VDD / C=.185 VDD controls. Existing analog functions hardcode nominal
supply in stimulus checks, control checks and power; reusing them directly
at other supplies would be invalid. A separate adapter parameterizes only
corner/supply and references the original physical generator and formulas.
No original runner, model, source, threshold or evidence is modified.

## Frozen definitions and gates

- Same 73-device topology, device/passive dimensions, source initialization,
  physical reference, attenuation, load, tuning network, DAC code 2, sign +1,
  1 UI external clock phase, and R=.70/C=.185 control fractions at every corner.
  Supply-derived testbench voltages follow the existing corner generator.
  NODESET remains the same released nominal initial guess, not a forced state.
- OP/AC/noise: both held clock states, negative resolved branch; static solver
  reltol=1e-7/vntol=1e-10/abstol=1e-13, AC dec 50 from 1 MHz to 100 GHz;
  input noise 500 linear samples, 10 MHz to 5 GHz, RMS total independently
  checked against spectral integration. No square root of RMS total.
- Report both broad S3 (interior peak, 3-12 dB, 1.25-2.5 GHz, positive Nyquist
  boost) and unchanged internal 9 dB/1.9 GHz match (.5 dB/100 MHz). They are
  separate gates. Nyquist boost uses log-frequency interpolation of the saved
  AC magnitude in dB at 2.5 GHz relative to the 1 MHz reference, without
  changing the original AC sweep. No corner retuning or threshold changes.
- HD3: clocked CTLE differential output, 100 MHz, 100 mV differential peak
  (200 mV differential peak-to-peak), 150 ns; 50-150, 50-100, 100-150 ns
  integer-cycle windows. Four settings: reltol 2e-5/1e-5 x maxstep 5/2.5 ps,
  vntol=1e-7/abstol=1e-12, Gear order 2. All HD3 windows below -30 dBc,
  window stability <=.5 dB, all six numerical pairs <=.5 dB and 1% H1.
- Noise <1.5 mVrms; measured VDD draw <15 mW. Existing strict new-DFE signed
  voltages, whole magnitude/body and varactor envelopes remain unchanged.
  Bilateral Rs-switch signed Vds findings remain separate and explicitly shown.
- Reject incomplete/nonfinite primitives, wrong actual stimuli or controls,
  failed branch, aborts, unexpected model warnings and changed source/PDK hashes.
  Record instrument failures distinctly from valid electrical/spec failures.

## Pilot membership, budget and stop conditions

Run nominal TT/1.00/27 first, then FS/.95/125 (the exact weakest sampled link
corner and prior inactive-tail failure). Six calls per corner: states 0/1,
then the four HD3 settings in the frozen order. Maximum 12 calls, 180 seconds
per call, no retry; maximum pilot wall budget 45 minutes including extraction.
Do not launch a call unless its full timeout fits the remaining wall budget.
Stop further corners after an invalid instrument/initialization or failed
nominal reproduction. Complete a valid corner's four numerical settings;
retain all failures. Valid target/spec misses are findings, not tuning prompts.

Before SPICE: exact-byte nominal decks must match all six frozen Entry 143
analog decks; raw nominal static replay must match; source comparison tests
must prove only supply/corner parameterization; failure tests must reject
malformed data and wrong supply. Verify Entry 143 archive and source/PDK
prerequisites, record actual parent Git/dirty state, exact source snapshots,
prior manifest identities and ngspice binary hash. Costs from earlier entries
are context only: Entry 143 seven calls 331.018 s, Entry 144 link 45 calls
1921.963 s. Pilot runtime is measured afresh, not inferred from those values.

Expansion is NOT automatically authorized by the pilot. Send the lead actual
costs/results and a maximum call/time budget before expansion. A justified next
stress set would include SS/.95/125, FF/1.05/0, SF/.95/0 and FF/1.05/125,
covering both edges of S3 and the prior maximum-power point. A stress subset
never proves 45-corner analog coverage. Full grid is at most 270 calls including
pilot, and must fit the separate lead-approved remaining budget before midnight
IST at the start of 15 September; mandatory report/recording work wins.

## Provenance and limitations

Fresh immutable output only:
`nebula/product_audits/submission_analog_pvt_20260914/pilot/`.
Any separately approved expansion uses a fresh sibling directory. Fail if the
output exists. One `dfe_slicer` run lock, one simulator process, durable per-call
results and raw failure logs, source snapshots, manifest and timing ledger.
Archive only after simulator work stops, retaining originals and raw hashes.

Held negative-state noise is not periodic receiver noise or all held branches.
Generic poly voltage coefficients are still ignored; passive process remains
typical, no mismatch or layout, no additional channel/target map, no DFE-active
runtime tuning or BER. Clock/control/common-mode sources remain external.
Drawn geometry is not routed area. Full receiver/S9 signoff remains false even
if the bounded analog measurements pass. Failed earlier experiments stay failed.
