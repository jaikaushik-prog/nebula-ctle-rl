# Nebula submission review guide

The repository is the code submission. The final report and recorded video are supplied separately by the team. For current installation/startup commands, use the [main README](../README.md#quick-start).

## Five-minute review

1. Start the app on port8766 after restoring compressed evidence. Open the saved accepted 6dB / 2.1GHz design.
2. In Design explorer, follow the recorded rejection of288 and recovery to352. Inspect the exact generated CTLE drawing and the specifications/sizing tables.
3. In Design PVT, change the channel loss and inspect the45 cells. The selected physical CTLE is fixed; the eye calculation uses an ideal behavioral DFE.
4. Compare the accepted result with the separate failed saved workflow. No fresh design run is required.
5. In Run files, download the circuit and evidence. Expand the programmable receiver prototype. Its circuit, controls and nominal check are distinct from the main exported CTLE.

## Evidence index

| Item | Repository location |
|---|---|
| Accepted selected352 workflow (includes rejected288) | [`4608cf1c525f4e59b2d5226059b0ce5d/`](../nebula/product_demo/submission_runs_20260915_v2/4608cf1c525f4e59b2d5226059b0ce5d/) |
| Separate failed308/315 workflow | [`daf7cf8a8bb5425b9be750f6cd804a87/`](../nebula/product_demo/submission_runs_20260915_v2/daf7cf8a8bb5425b9be750f6cd804a87/) |
| Selected CTLE + transistor DFE nominal | [`generated_receiver_6db_2p1ghz_20260915/`](../nebula/product_audits/generated_receiver_6db_2p1ghz_20260915/) |
| Programmable derivative review and diagrams | [`entry160_programmable_receiver_review_20260915/`](../nebula/product_audits/entry160_programmable_receiver_review_20260915/) |
| Programmable derivative measured control | [`entry160_programmable_receiver_measured_seed_20260915/`](../nebula/product_audits/entry160_programmable_receiver_measured_seed_20260915/) |
| Independent9dB receiver nominal | [`entry143_dfe_calibrated_verification_20260910/`](../nebula/product_audits/entry143_dfe_calibrated_verification_20260910/) |
| Independent9dB receiver link PVT | [`entry144_dfe_calibrated_pvt_20260910/`](../nebula/product_audits/entry144_dfe_calibrated_pvt_20260910/) |
| Matched RL/classical benchmark | [`submission_recovery_20260915/`](../nebula/product_audits/submission_recovery_20260915/) |

## Evidence restoration

Some waveform and device-terminal files are stored as lossless gzip siblings to keep Git objects smaller. Their original hashes remain unchanged in the experiment records.

```bash
python -m nebula.restore_submission_evidence
python -m nebula.restore_submission_evidence --check
```

The restore tool is standard-library-only, performs no download or simulation, verifies compressed and expanded hashes, and refuses to overwrite a different local file. The manifest records exactly which new submission traces it restores. Historical compressed datasets retain their existing reproduction procedures; the command is not a claim to restore every historical raw experiment.

If a receiver download is unavailable on a new clone, run restoration before restarting the app. If you are on8765, switch to8766. A missing hash-bound artifact is reported as unavailable rather than replaced by another circuit's result.

## Focused software checks

```bash
python -m pytest nebula/tests/test_restore_submission_evidence.py nebula/tests/test_run_files_prototype.py nebula/tests/test_evidence_loading.py nebula/tests/test_explorer_refinement.py nebula/tests/test_web_recovery_clarity.py nebula/tests/test_submission_evidence.py nebula/tests/test_programmable_option.py -q
```

These check software behavior and evidence access. They do not run a new SPICE campaign or certify a receiver. Historical tests may need external PDK files, datasets or machine-specific tools.

## Fresh design runs

The recorded physical flow uses NGSpice41 (`ngspice_con.exe` on Windows) and SkyWater SKY130A. Install the simulator and PDK separately; they are not pip dependencies. The recorded PDK revision is `c6d73a35f524070e85faff4a6a9eef49553ebc2b`.

Project-owned include wrappers and runner configuration refer to the original Windows installation. For a new machine, inspect `nebula/device/ngspice_runner.py`, `nebula/device/sky130_runner.py` and wrappers under `nebula/device/spice/` before configuring new runs. The saved decks deliberately retain their original paths and source hashes. Do not edit or re-hash a recorded deck to represent a new run as the original measurement.

Generate and verify launches new work. Select a separate `--run-root` for new results if desired. Keep signed model-domain, convergence, output-swing and evidence-integrity gates intact. A simulator exit code of zero alone is not an electrical pass.

## How to read the RL contribution

The learned policy proposes candidates within a characterized512-setting bank. Bank safety checks and deterministic recovery have separate roles; continuous-Cs refinement and programmable-control calibration are not additional RL achievements. The saved run demonstrates automatic rejection/recovery and a concrete physical export. The matched workflow timing experiment did not establish a speed advantage over its classical comparator; global near-optimality and complete on-demand target coverage are not claimed.

## Submission scope

The main output is setting352, fixed Rs/Cs. Its315-condition eye gate combines CTLE electrical evidence with an ideal behavioral DFE. The selected transistor receiver and programmable derivative have separate nominal checks. The9dB reference is independent. Full selected-receiver PVT/analog qualification, signed-domain closure, measured-channel BER and routed area remain future engineering work.
