# Nebula Next-Agent Start Prompt

You are continuing the Nebula competition project in the repository below. Treat this file as operational context, then follow the user's next instruction. Take action and finish the requested work; do not stop after proposing a plan. Do not redo completed work unless the user asks.

Repository:

    C:\Users\DELL\Desktop\serdes-dsp-framework-main

Remote:

    https://github.com/jaikaushik-prog/nebula-ctle-rl.git

## Mandatory first steps

1. Open AGENTS.md and obey its instruction to read HANDOFF.md in full before doing any work.
2. For Nebula work, read these in order:
   - HANDOFF.md
   - CLAUDEwa.md
   - nebula/G0_RESULTS.md
   - nebula/NRZ_RETARGET_AUDIT.md
3. Pay particular attention to HANDOFF section 9, Gotchas G1-G175. Several simulator failures return exit code zero and several unit errors produce plausible results.
4. Check the live repository state:

       git status --short
       git branch --show-current
       git rev-parse HEAD
       git remote -v

5. Do not reset, delete, or overwrite work to make the tree look clean. Inspect unexpected changes and preserve user work.
6. There is no active simulation, training job, or unfinished experiment at this handoff. The next user message defines the active task.

## Current Git state

At this handoff:

- Branch: nebula/winning-sprint-20260908
- Verified parent before this handoff file: 26e93ece8753b562f39904d61568c931d8b138d1
- Use git rev-parse HEAD as the authoritative current commit.
- At the start of this handoff, both GitHub branches pointed to the verified parent. After this file is committed, use the live refs as authoritative.
- The working tree was clean.
- Commit identity must remain Jai Kaushik <jaikaushik-prog@users.noreply.github.com>.
- Never use a BITS email for Git commits.

The user explicitly requested that project progress be backed up to the existing public repository and said it does not need to be made private. After a completed, verified change, update HANDOFF.md, commit it with the change, and push both the working branch and main. Use normal fast-forwards and never force-push.

The repository still contains ignore rules for copyrighted reference material. Do not add reference PDFs, organiser handouts, the AAPMS internship DOCX, PDK model files, release ZIPs, tmp, or gmcmp.pkl. The separate structural reference nebula/AAPMS-REPORT-v2 (3).docx must remain ignored.

## Owner and communication

The owner is Jai Kaushik, a BITS Pilani undergraduate and a beginner in analog/RL engineering. Explain changes in plain language: what changed, why it matters, how it was verified, and what it means for the competition presentation.

Project team:

- Jai Kaushik: f20240419@pilani.bits-pilani.ac.in
- Rishabh Agarwal: f20240387@pilani.bits-pilani.ac.in
- Avi Mehta: f20240607@pilani.bits-pilani.ac.in
- Institution: Birla Institute of Technology and Science, Pilani (BITS Pilani)

The user wants a strong, polished competition submission. Present implemented strengths clearly. Do not invent results or hide evidence boundaries. Avoid adding a large closing table that advertises every weakness; the owner explicitly removed that layout. State necessary qualifications beside the relevant result and keep the conclusion constructive.

Do not claim employment at Astera Labs or knowledge of an internal judging rubric.

## Two projects in this repository

The active competition project is Nebula under nebula/. The original SerDes
framework under python_models/ is a separate 112G PAM-4, 28 nm methodology
project. Do not mix its assumptions, units, models or results into Nebula. If
the user explicitly asks for SerDes work, follow the separate SerDes sections
of AGENTS.md and HANDOFF.md.

## Competition objective

Build a fully automated RL-assisted Python framework for analog circuit sizing. Given target specifications, it should select a reduced set of circuit candidates, integrate with SPICE, and output a final schematic and measured specifications with little per-request human intervention.

Target use case and requirements:

- PCIe Gen2, 5 Gbps NRZ, 2.5 GHz Nyquist
- CTLE peaking boost: 3-12 dB
- Tunable peak frequency: 1.25-2.5 GHz
- One-stage source-degenerated CTLE with variable Rs and Cs plus a 1-tap DFE
- HD3 below -30 dB at 100 MHz for 100 mV differential input
- Input-referred noise below 1.5 mVrms from 10 MHz to 5 GHz
- Power below 15 mW
- Area below 0.05 mm2 in a 130 nm PDK
- Eye opening above 0.4 UI and 100 mV
- TT, SS, FF, SF and FS; VDD +/-5 percent; temperatures 0, 27 and 125 C
- Bonus: LLM-based interaction wrapper

## Current product state

The current delivered path is an RL-assisted hybrid rather than unconstrained transistor synthesis.

- Main orchestration: nebula/physical_design.py
- CLI mode: rl-physical
- Web product: nebula/web/
- Verified registry: nebula/physical_verified_registry.json
- Primary physical demo:
  nebula/product_demo/physical_bias_9db_1p9ghz_20260906/

The physical design contains a SKY130 transistor CTLE, a real PMOS input attenuator, physical bias reference, poly resistor and MIM bypass capacitor. The exported circuit includes fixed drawn Rs and Cs values. A fabricated programmable Rs/Cs switch network is not demonstrated.

The main 9 dB / 1.9 GHz physical circuit is setting 490, code A7, Rs index 5, Cs index 2. It passes 45/45 sampled PVT points and 315/315 declared electrical-model cases. The grid is 5 process corners x 3 supplies x 3 temperatures, and each PVT point has 7 constructed channel-loss conditions. The same circuit is used at every point.

The recovery registry also contains fixed physical demonstrations at:

- 3 dB / 1.9 GHz: setting 401, 315/315
- 6 dB / 1.9 GHz: setting 474, 315/315
- 9 dB / 1.9 GHz: setting 490, 315/315

This demonstrates three target points along the 1.9 GHz line. It does not establish physical coverage of the entire 3-12 dB by 1.25-2.5 GHz rectangle.

The saved 5 dB / 1.9 GHz user run has 312/315 overall. Its three failures are all in the 3.0 dB channel slice: SS/0.95/0 C, SF/0.95/0 C and SF/0.95/27 C. The web PVT view was corrected so it opens the first failing slice, displays 42/45 for that slice and 312/315 overall, labels every cell PASS/FAIL/MISSING, and shows per-loss counts.

## RL contribution and correct attribution

Relevant files:

- nebula/rl/margin_improve_env.py
- nebula/rl/safety_shield.py
- nebula/experiments/shielded_policy_final_results.json
- nebula/product_audits/entry115_exhaustive_benchmark_20260908/
- nebula/product_audits/entry113_attribution_20260907/
- nebula/WINNING_SPRINT_RESULTS.md

The frozen policy operates in an 8 x 8 x 8 library of attenuation, Rs and Cs codes. It observes the target, current setting and a bounded measurement history. It can move one index up/down or LOCK. A deterministic best-compliant-visited shield selects the safe output.

Defensible headline results:

- Five frozen seeds were evaluated on 2,430 held-out midpoint identities.
- Shielded PPO improves mean normalized eye quality by 0.1550 over the fixed start, with a paired 95 percent interval of about 0.1508 to 0.1593.
- PPO averages 5.579 candidate visits.
- Compared with enumerating all 512 cached settings, that is a 91.7657x candidate-visit reduction.
- The exhaustive near-optimality gate failed: mean oracle-solvable regret is 0.28310 and 20.905 percent are within 0.05 of the oracle.
- Random local exploration has higher compliance in the controlled comparison, while PPO has higher mean quality and fewer visits than that local random control at the reported budget.
- The 91.8x number is candidate-visit reduction inside a cached library. It is not a measured end-to-end SPICE or wall-clock speedup.
- Offline characterisation and five-seed training must remain billed.
- The final physical-bias circuit was produced after the frozen RL experiment. Do not claim that the final physical circuit itself proves the frozen RL result.
- The deployed workflow can fall back to measured-bank selection and deterministic verification. Describe RL as a useful contributor within a hybrid workflow.

Do not rerun, tune, or reinterpret frozen held-out experiments merely to improve a headline.

## Analog and verification boundaries

Credit the implemented circuit while retaining these precise boundaries:

- The CTLE core, input attenuator and bias reference are transistor/device-level SKY130 simulations.
- Rs and Cs are physically valued fixed elements in the export. A working physical switch matrix is not present. Three attempted switch architectures failed their registered loss/capacitance gates.
- The delivered 1-tap DFE is behavioural cursor cancellation. The latest transistor decision/hold prototype passes 14/32 held bits; all 18 transitions miss the timing window. It is not an integrated hardware DFE.
- Noise and HD3 are simulated-model results. The generic poly model ignores voltage-coefficient parameters in this ngspice flow, so passive nonlinearity remains unverified.
- Power covers the CTLE and physical reference. It excludes the transistor DFE, clock, feedback DAC, tuning controls and common-mode generator.
- The reported area is a netlist-derived geometry subtotal, about 0.007854511 mm2. It is not a routed layout area and excludes several receiver blocks.
- The 32.628 fF output load is an assumed testbench load.
- PVT uses transistor corners with typical passives. It does not include passive tolerance, local mismatch, Monte Carlo or extracted layout parasitics.
- Eye results use a constructed channel family and a cursor-based, noiseless link model. They are not BER contours and arbitrary uploaded Touchstone channels are not covered by the frozen bank.
- Do not confuse peaking, absolute gain and channel insertion loss.
- Input noise returned by ngspice is already RMS voltage; never square-root it again.
- A simulator exit code is never sufficient. Parse output, assert expected vectors and reject warnings/failures explicitly.

## Current report variants

Preferred formal report:

    output/pdf/Nebula_Competition_Report_Academic.pdf

- Current SHA-256:
  a573db02335879e0a6a0b3feb2c9eeea2172c2f3f4b4e4699dfc8123c8f90670
- 22 pages
- Builder: nebula/report/competition_academic.py
- Checker: nebula/report/check_academic_pdf.py
- Tests: nebula/tests/test_academic_report.py
- QA record: output/pdf/Nebula_Competition_Report_Academic_review.json
- Source manifest: output/pdf/Nebula_Competition_Report_Academic_sources.json
- Pages 1-3 contain the team cover and CTLE visual, abstract plus automated-run summary, and contents plus evidence hierarchy.
- Pages 4-22 were raster-identical before and after the Entry 120 front-matter revision.
- Page 22 is the future-work section.

Preserved fallback report:

    output/pdf/Nebula_Competition_Report.pdf

- SHA-256:
  3cd67ffc933b8f369d601a72f16e39295542780777ca5bccc797135278faf43b
- 20 pages
- Do not overwrite it while experimenting with the academic version.

Byte-preserved archive:

    output/pdf/archive_before_academic_restructure_20260909/

The archive contains the fallback PDF, review, source manifest, builder snapshot and archive checksums. Git attributes preserve its exact bytes.

For academic report edits:

1. Modify only nebula/report/competition_academic.py unless the user explicitly requests the fallback report.
2. Rebuild using saved evidence:

       py -3.13 -m nebula.report.competition_academic

3. Run automated PDF QA:

       py -3.13 -m nebula.report.check_academic_pdf

4. Render and visually inspect every changed page at readable resolution.
5. Leave visual_review as PENDING until inspection is complete, then update the review JSON with the exact PDF hash and reviewed page numbers.
6. Compare untouched page raster hashes when the edit is local.
7. Keep figure numbering, outline entries, page references, source hashes and the final future-work page consistent.
8. Do not launch SPICE or training for a report-only edit.

## Important evidence locations

- Primary physical export and raw measurements:
  nebula/product_demo/physical_bias_9db_1p9ghz_20260906/
- Physical implementation summary:
  nebula/PHYSICAL_PRODUCT_RESULTS.md
- Product scope inventory:
  nebula/report/product_scope.py
- Exact schematic renderer:
  nebula/report/physical_schematic.py
- Fixed physical registry:
  nebula/physical_verified_registry.json
- RL final result:
  nebula/experiments/shielded_policy_final_results.json
- Exhaustive benchmark:
  nebula/product_audits/entry115_exhaustive_benchmark_20260908/
- Physical recovery evidence:
  nebula/product_audits/entry115_physical_recovery_20260908/
- Post-review evidence:
  nebula/POST_REVIEW_RESULTS.md
- Link and DFE model:
  nebula/link/
- Local product:
  nebula/web/
- Current progress and future work:
  HANDOFF.md and nebula/WINNING_SPRINT_RESULTS.md

Treat report, HANDOFF and result summaries as claims to verify against raw artifacts when the user's task depends on them.

## Testing and environment

Mandatory test command from the repository root:

    py -3.13 -m pytest tests nebula/tests -q -m "not slow"

Current clean baseline:

- 3001 passed
- 13 deselected
- 2 known warnings
- Most recent duration: 433.91 seconds

Run this full suite before and after repository changes, as AGENTS.md requires. Add meaningful focused tests for new behaviour. The two known warnings are the missing optional scikit-rf package and a PyTorch tensor conversion warning.

For simulator work only when the user asks or approves a registered experiment:

- Conda environment: nebula
- Simulator: ngspice 41
- Use ngspice_con.exe, never ngspice.exe
- PDK: C:\Users\DELL\sky130A
- Trimmed library: nebula/device/spice/sky130_nfet_only.lib.spice
- Run decks from nebula/device/spice so .spiceinit is read
- Instance W/L numbers are in microns
- Mocks produce fake values and may not enter deliverables
- Preserve the one-definition model-card rule
- Use bounded, preregistered experiments and retain raw failures

## Working rules for the next request

- Treat the user's next message as the active objective and continue until it is complete.
- Inspect existing work before changing it.
- Keep the original report and archive safe.
- For presentation edits, improve clarity and confidence without falsifying scope.
- For technical claims, verify source evidence and distinguish measured failure from missing verification.
- Do not ask the user to repeat context already present here.
- Do not ask for permission for ordinary reversible edits, tests, inspections, commits or the already-authorized backup push.
- Do not send messages, publish elsewhere or run destructive commands unless explicitly authorized.
- Update HANDOFF.md in the same commit as every repository change.
- Run focused checks and the full mandatory suite.
- Audit staged files for credentials, copyrighted references and oversized artifacts before committing.
- Push the verified commit to nebula/winning-sprint-20260908 and main.
- Report the outcome in plain language with clickable local file paths, test counts, commit hash and any material remaining limitation.

## Definition of done

A task is complete only when:

- The requested result exists and is inspectable.
- Relevant focused checks pass.
- The mandatory full suite passes.
- PDF or UI changes have visual QA.
- HANDOFF.md records the change.
- The staged diff contains only intended project-owned files.
- The commit uses the correct Git identity.
- GitHub main and the working branch point to the verified commit.
- The final response tells the user what changed, why it helps, where to find it and how it was verified.