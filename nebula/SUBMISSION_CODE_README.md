# Nebula source code and saved evidence

This package contains the current Nebula Python framework, web interface, frozen RL policies, characterized circuit banks, circuit generators and selected saved results. The final report and recorded video are submitted separately.

## Start with the saved application

Extract the ZIP completely into a short writable folder, for example `C:\Nebula`. Run commands from the extracted folder containing `nebula/`, not from inside the ZIP.

The recorded application environment is Windows with Python 3.13. Saved-result viewing does not launch NGSpice or train a policy. A clean environment installation has not been certified; the included archive validation records the exact checks performed.

If creating an environment with Anaconda or Miniforge:

```powershell
conda create -n nebula-review python=3.13 pip
conda activate nebula-review
python -m pip install -r nebula/requirements-submission.txt
python -m nebula.web.recovery_server --port 8766 --no-browser
```

Open http://127.0.0.1:8766/#results in a browser. Keep the terminal open. Do not use the older port 8765 launcher. If 8766 is occupied, close your own earlier Nebula server or explicitly choose another available port.

The recorded selected design has run ID `4608cf1c525f4e59b2d5226059b0ce5d`: requested 6 dB at 2.1 GHz, setting 288 rejected followed by accepted setting 352. A separate failed workflow is `daf7cf8a8bb5425b9be750f6cd804a87`; its 308/315 result is not the 314/315 rejection within the successful workflow. A historical adaptive-bank example is also included.

Use Design explorer, Design PVT, Compare circuits and Run files to inspect the saved outputs. The programmable receiver prototype is under Run files when the matching setting-352 design is selected. Its exact files are separate from the older selected-run archive.

Reading a natural-language request only parses specifications. `Generate and verify` starts new engineering work; `Profile channel` starts channel analysis. Neither is required to review this submission. The optional LLM provider requires a separately installed SDK and user-provided credentials; the deterministic parser and explanation fallback work without it. No credentials are included.

## Source map

- `nebula/web/`: application server, frontend and evidence adapters.
- `nebula/rl/` and `nebula/experiments/`: policy, training/evaluation implementation, frozen policy weights and characterized banks.
- `nebula/common/`, `nebula/device/`, `nebula/link/`: specifications, circuit/device generators, NGSpice integration and NRZ link model.
- `nebula/physical_recovery.py`, `nebula/recovery_workflow.py`: fixed-circuit rejection/recovery and recorded execution flow.
- `nebula/generated_receiver.py`, `nebula/programmable_option.py`: separate connected-receiver export and measured programmable option.
- `nebula/product_demo/submission_runs_20260915_v2/`: the selected successful and separate failed saved workflows, including their candidate evidence.
- `nebula/product_audits/`: selected raw receiver/tuning evidence and compact historical records. See the manifest for exact membership and omissions.
- `nebula/tests/`, `tests/`: test source. Some historical/scientific tests need external PDK files or large raw datasets not shipped here; do not treat this as a full clean-machine regression certificate.
- `python_models/`: the team's pre-existing link-model code used by the framework; the separate original PAM-4 project is not the competition target.
- `HANDOFF.md`, `CLAUDEwa.md`: technical definitions and development history. Older entries describe earlier states; current package guidance is this file.

## Evidence ownership

The primary output is one fixed-Rs/Cs physical CTLE, setting 352. Its 315-condition eye acceptance gate uses an ideal behavioral DFE. The selected CTLE plus transistor DFE and the programmable derivative have separate nominal measurements. The calibrated 9 dB / 1.9 GHz transistor receiver owns its own reference evidence, including 45-point link PVT. These are distinct evidence sets, not interchangeable verification of one circuit.

The measured target grid covers 4/12 requests. Full receiver qualification, signed model-domain closure, routed layout and measured-channel BER remain outside the demonstrated scope. The matched workflow benchmark does not establish an RL runtime advantage. Saved result bytes and their original evidence hashes have not been altered for this package.

## Running fresh SPICE work

Install NGSpice and SKY130 separately. The recorded simulator is NGSpice 41, Windows console binary `ngspice_con.exe`; the recorded SKY130A installation uses volare revision `c6d73a35f524070e85faff4a6a9eef49553ebc2b`. PySpice is not the working simulator integration.

Installed PDK model libraries are not distributed. The small project-owned `.lib.spice` wrappers contain include pointers rather than redistributed SKY130 model cards. Archived decks retain their original absolute model paths for provenance. A new machine must configure its simulator and PDK paths for new runs; do not edit archived evidence or re-hash it to make a modified deck look original.

Recorded external paths include `C:\Users\DELL\sky130A` and the simulator under `C:\Users\DELL\miniforge3\envs\nebula\Library\bin`. Consult `nebula/device/ngspice_runner.py`, `nebula/device/sky130_runner.py`, project-owned wrappers under `nebula/device/spice/`, and `nebula/G0_RESULTS.md` before configuring fresh runs. SKY130 instance dimensions and ngspice output parsing have important unit/model-domain checks; keep those checks intact.

This package supports source inspection and saved replay without representing every historical experiment as portable to a new machine. Offline scientific reproduction may require path configuration and separately installed tools/data.

## Package integrity and exclusions

Run the standard-library-only check after extraction:

```powershell
python verify_package.py
```

`CODE_MANIFEST.json` records SHA-256 hashes of packaged files, original working-tree provenance and omitted raw-evidence paths. `PACKAGE_VALIDATION.json` records focused checks against the extracted package; it is not a new circuit verification result.

The archive deliberately excludes reports, videos, narration/checklists, independent judge notes, local credentials, Git history, environments, temporary scratch files, organiser/reference documents and installed PDK libraries. Large historical raw waveform/terminal dumps are omitted where they are not required for the demonstrated saved UI. The selected accepted/failed workflows, generated receiver and programmable receiver evidence used by the UI are retained. Compact historical summaries, decks and manifests remain inspectable; an omitted historical raw trace is not claimed to have been reverified from this ZIP.
