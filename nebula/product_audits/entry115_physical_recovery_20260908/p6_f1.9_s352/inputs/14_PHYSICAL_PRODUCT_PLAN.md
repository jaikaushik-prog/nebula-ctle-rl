# Entry 105: opt-in physical-bias product integration

Frozen before measurements, 2026-09-06. User: continue integration after
Entry 104b. Legacy product, bank, weights, reward, bounds and demo stay unchanged.

## Contract

`rl-physical` is a separate, opt-in product mode. The old RL-hybrid proposer
and classical fixed-setting intersection supply ONE candidate, not evidence
that the new bias circuit passes. Keep the nominal proposal if it belongs to
the intersection across all requested channel/PVT conditions; otherwise choose
the lowest eligible code deterministically. An empty intersection is a refusal
within this characterised bank, not proof that no physical solution exists.

Replace Iref and Cbyp through the existing Entry 103 renderer. Calibrate once
at TT; freeze geometry, common mode, load and setting across all 45 corners.
Use the existing Entry 104 measurement/bridge/DFE checks with the corrected
G140 attenuation-adjusted swing range. No retries or per-corner recalibration.
The new gate excludes unknown S7 area explicitly and does not redefine reward.

## Bounded acceptance run

One new 9 dB / 1.9 GHz run, all seven constructed channels, into a new directory.
Maximum 137 SPICE calls: one captured legacy candidate, one TT PMOS calibration,
45 AC/noise, 45 100-MHz HD3, and 45 Nyquist-HD3/DC-swing calls. Separate analyses
reuse existing tested measurement blocks; no new combined SPICE instrument.
No startup, independent passive corners, mismatch, new training or load sweep.
All failures retained. Stop with failure/unknown, never substitute cached passes.

## Product acceptance

- CLI and background web worker expose the opt-in mode; legacy stays default.
- Returned nominal numbers and fixed PVT matrix come only from fresh hardware
  measurements and their explicitly behavioural device-to-link calculation.
- Export the exact measured physical TT deck, not a regenerated ideal-Iref deck.
- Draw physical bias/MIM components from that deck; refuse wrong connectivity.
- Bundle raw logs, waveforms, snapshots and hashes. No external paths in ZIPs.
- Model pass requires complete fixed membership and DFE control agreement;
  incomplete/failed physical verification cannot inherit an old bank pass.
- S7 full area remains unknown. Counted geometry includes the bypass MIM and
  bias devices. Power includes the CTLE/reference VDD branch, not full receiver.
- Preserve original audits, report, cached demo and paused Entry 102 test spec.
- Run full tests before/after. Baseline: 2823 passed, 13 deselected, 2 warnings.
