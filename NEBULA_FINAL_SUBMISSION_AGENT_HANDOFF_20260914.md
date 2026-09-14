# Nebula final submission: new-agent execution packet

Prepared 14 September 2026. Read this before older restart prompts.

## 1. Copy-paste startup prompt

> Read NEBULA_FINAL_SUBMISSION_AGENT_HANDOFF_20260914.md and the required repository documents using the owner-approved focused reading set below. Continue the Nebula submission work. First inspect the current files, Git state, remaining time and scientific evidence. Preserve the verified frontend and existing reports. Produce a separate 10-12-page final report, a matching 5-6-minute narration script in Word, and a concrete recording/submission package. Improve the supporting technical evidence using the bounded priorities below only while preserving time for those mandatory deliverables. Distinguish proven results, partial coverage and proposed experiments. Do the authorized work and verification, keep HANDOFF.md current, and back up verified project-owned changes using normal fast-forwards. Draft the submission email but do not send it. Explain progress simply; do not stop at a plan or repeatedly ask for permission for ordinary reversible work.

This packet describes work for the NEXT agent. Its proposed experiments have NOT been executed by creating this file.

## 2. Confirmed submission requirements and remaining time

The owner supplied the organiser email directly:

- Deadline: **15 September 2026, 11:00 PM**.
- Submit a **10-12-page report covering all deliverables**, plus a **project demo video**.
- Recipient: **nebula@asteralabs.com**.
- Email subject: **Nebula – Final Submission**.
- Include team name, college name, all team members' names, contact numbers and email IDs.
- Judging: **coverage of all deliverables, innovation, and thought process**.
- The top five teams will be shortlisted to present on the final day. Qualification is not guaranteed.
- No maximum video duration, video encoding, attachment-size limit, deadline timezone, or mandatory report file type was stated in the supplied email. Do not invent one. The owner chose a **5-6-minute video in their own voice**. A PDF report is a practical submission artifact, not a quoted organiser format requirement.

At the owner's stated **12:33 PM on 14 September**, there were **34 hours 27 minutes** until the deadline, assuming both times are in IST. Recompute on restart; that is not a live countdown. The workspace timezone is Asia/Kolkata. Aim to have a sendable package by **8:00 PM on 15 September**, preserving a three-hour buffer. Protect sleep, recording, review, export and upload time. Do not allocate every remaining hour to coding.

Collect missing team/contact information early, while continuing independent work. Never infer member contact details from Git identity. Email sending or mentor contact needs an explicit send instruction from the owner; preparing drafts and files is authorized.

## 3. Repository and mandatory orientation

Repository: `C:/Users/DELL/Desktop/serdes-dsp-framework-main`

Remote: `https://github.com/jaikaushik-prog/nebula-ctle-rl.git`

Working branch: `nebula/winning-sprint-20260908`.

Last verified implementation checkpoint before this documentation packet: `8d8e25a754b0a6a584871decba2d9da68de39a06`. Both remote main and working branch had reached it. Inspect Git again; do not assume that no newer changes exist.

There are two independent projects: `python_models/` is the original 112G PAM-4 framework; **Nebula is `nebula/`, a 5 Gbps NRZ PCIe Gen2 CTLE project using SKY130**. Do not import the other project's performance claims.

Read in this order:

1. `AGENTS.md` and the focused `HANDOFF.md` set below.
2. `CLAUDEwa.md` **in full**, including scientific change controls and experiment gates.
3. `nebula/G0_RESULTS.md` and `nebula/NRZ_RETARGET_AUDIT.md`.
4. Current evidence documents and source files for the task you undertake.

**Focused reading exception:** the owner explicitly answered "Use the focused reading set" after being told HANDOFF.md was about 1.26 MB / nearly 20,000 lines. This overrides the blanket historical full-read requirement for HANDOFF; it does not waive the Nebula contract or relevant gotchas. Read the opening restart/current-state notices, sections 4 and 6-9, **all gotchas through G198 and any later additions**, and recent Entries 147-150 plus this packet's entry. Read older entries only where referenced by your active task. Useful scientific history includes Entries 113/115 for attribution/benchmarking and 142-144 for the integrated receiver. Use bounded output; do not claim truncated text was read.

`NEBULA_SUBMISSION_START_20260914.md` remains useful background, but its old Receiver workflow, full historical reading instruction, and assumptions about the submission report are superseded here and by Entry 150. The existing 25-page report is now known to exceed the organiser's limit.

## 4. Product state and owner preferences: preserve these

The owner wanted a premium analog-design instrument with readable typography, little repeated prose, visible results and clear provenance. They explicitly rejected the Receiver tab and a monotonous vertical stack of features. The final verified workbench has **five tabs**:

- Design Explorer (default).
- Design PVT.
- Compare circuits.
- Channel.
- Run files.

Design Explorer owns the selected-design/status/measurement bar and a shared circuit canvas with four block selections. The complete CTLE including tail current sources is the default main diagram. Other blocks are accessible without four repeated large drawings. The adjacent inspector has Response, Specs, Sizing and Run record views. Expand circuit gives the drawing more space; New target opens a dialog. Two expandable panels expose the exact generated CTLE and the **separate 9 dB / 1.9 GHz transistor CTLE + DFE checkpoint**.

Compare circuits owns the eye plots: CTLE + ideal DFE, CTLE-only, and margin-envelope modes. The original screenshot's two-boundary shape was a margin envelope, not a dense waveform eye. The revised UI includes saved-response waveform overlays and honest model labels. Preserve stale-result guards, common plot axes and unavailable-data handling. Do not fabricate eye crossings, BER measurements, or transistor transient evidence to make a plot prettier.

The final browser rehearsal passed at 1440x1000 and 1280x900, including all circuit/inspector views, expansion, checkpoint panels, PVT, comparison modes and replay of a completed saved run. Do not restart an aesthetic overhaul in this submission window. Fix a demonstrated bug if necessary, with regression checks.

Relevant files:

- `nebula/web/static/app.js`, `index.html`, `styles.css`, `circuit_views.js`, `design_plots.js`.
- `nebula/web/design_visuals.py`, `server.py`, `hardware_checkpoint.py`, `hardware_visuals.py`.
- `nebula/web/rehearse_desktop.py` for the existing rehearsal route.

Saved demo run:

- Run root: `C:/Users/DELL/AppData/Local/Temp/nebula-web-85d05pa4`.
- Run ID: `ab981d69dac840e9820155d7e46e14dc`.
- Requested 3 dB / 1.9 GHz; measured about **3.910115 dB / 2.131144 GHz**.
- Modeled eye: **341.791199 mV / 0.859375 UI**.
- **315/315 conditions = 45 PVT corners x 7 channel losses**, using one fixed exported CTLE, saved transistor AC response and an ideal one-tap DFE model.
- This design's production acceptance tolerances are 1.5 dB and 0.3 octave. Do not apply a different checkpoint's tighter tolerance retrospectively or imply exact target matching.

Check an existing server before starting another. If necessary, resume with:

```powershell
py -3.13 -m nebula.web --port 8765 --run-root "C:\Users\DELL\AppData\Local\Temp\nebula-web-85d05pa4" --no-browser
```

Use `http://127.0.0.1:8765`. `python -m nebula.web.server` is not the launch entry point. Temp paths and process IDs are not permanent evidence; verify availability. Existing browser automation used CDP 9223. Multiple Windows listeners can exist on one port; inspect `netstat -ano` and process command lines rather than trusting a single Get-NetTCPConnection result or killing an unknown process.

## 5. Problem statement and claim boundaries

The supplied statement asks for an RL-based Python framework that accepts specifications, sizes devices with a reduced search burden, integrates a SPICE simulator, and outputs the final schematic and resulting specifications with minimal to zero human intervention. LLM interaction is a bonus.

Requested specification coverage:

| Requirement | Target from supplied problem statement |
|---|---|
| Signaling | PCIe Gen2, 5 Gbps NRZ, 2.5 GHz Nyquist |
| Equalization | One-stage source-degenerated CTLE with variable Rs/Cs, plus one-tap DFE |
| Peaking | 3-12 dB; tunable peak frequency 1.25-2.5 GHz |
| HD3 | Below -30 dBc at 100 MHz differential input |
| Input-referred noise | Below 1.5 mVrms over 10 MHz-5 GHz |
| Power | Below 15 mW |
| Area | Below 0.05 mm2 using a 130 nm PDK |
| Eye | Greater than 100 mV height and 0.4 UI width |
| PVT | TT, SS, FF, SF, FS; VDD +/-5%; 0-125 C |

Check the contract and actual input-amplitude convention when reporting HD3. Do not silently change peak, peak-to-peak or differential conventions.

Present this honestly as an **RL-assisted design framework**:

- A trained policy proposes settings, followed by deterministic verification, recovery/fallback and physical design/export stages where applicable.
- The frozen RL bank has 512 settings; actions involve attenuation/Rs/Cs codes. It is not demonstrated unrestricted sizing of every MOS device.
- Five-seed, 2,430 final request/loss/PVT evaluation identities are not 2,430 independently generated transistor geometries.
- The historical **91.8x** figure concerns candidate visits, not measured end-to-end SPICE/wall-clock acceleration. Do not market it as runtime speedup.
- Near-optimality is not established; earlier attribution/benchmark evidence includes stronger compliance from local random search. PPO's improvements over fixed settings or behavior cloning do not prove superiority to every search baseline.
- An offline subtotal of 6.711 hours has exclusions; retrieve its accounting before using it.
- The full 3-12 dB by 1.25-2.5 GHz rectangle and complete zero-human receiver design are not proven by a few successful targets.
- A UI parser is not automatically an LLM deliverable. Existing web parsing uses `use_llm=False`; claim the optional LLM bonus only if an actual provider-backed path is available and demonstrated.

Read `nebula/rl/hybrid_designer.py`, `nebula/POST_REVIEW_RESULTS.md`, `nebula/POST_REVIEW_PLAN.md`, `nebula/experiments/shielded_policy_final_results.json`, `exp_post_review_attribution.py`, and `exp_winning_benchmark.py` (the latter two under `nebula/experiments/`).

The separate integrated receiver checkpoint is meaningful hardware evidence, but not the same circuit as the selected 3 dB CTLE:

- Fixed 73-device integrated design, nominal Rs/Cs control fractions 0.70/0.185 VDD (1.26/0.333 V at nominal supply).
- Nominal peaking about **8.744-8.747 dB at 1.903-1.906 GHz**, using its declared 0.5 dB / 100 MHz tolerance.
- Nominal input noise about **0.65404-0.65405 mVrms**; held-state noise, not periodic clocked noise analysis.
- Nominal clocked HD3 about **-54.92 dBc** at the recorded 100 MHz / 100 mV peak test conditions; verify the differential convention from its netlist.
- Fixed-parameter **45-corner link PVT** run with a 64-bit test pattern and constructed 7.5 dB channel.
- Minimum eye height **113.244 mV**; minimum positive-opening width **0.635 UI**; width above 100 mV **0.560 UI**. These are different width definitions.
- Maximum recorded VDD draw **12.5241 mW**, excluding external clock/control/common-mode sources.
- Drawn-geometry subtotal **0.014715766 mm2**, not routed layout area.
- Signed Rs-switch Vds model-domain findings persist across the 45 corners; voltage-dependent poly-resistor behavior is omitted. More simulations alone do not remove these limitations.
- Existing 45-corner evidence is **link PVT**, not proof that AC peaking, noise and HD3 all pass at every corner.

Read `nebula/DFE_CALIBRATED_RESULTS.md`, `nebula/DFE_LOADED_CALIBRATION_PLAN.md`, `nebula/DFE_CALIBRATED_VERIFICATION_PLAN.md`; runners `nebula/device/dfe_calibrated_verification.py`, `dfe_configurable_pvt.py`; and `nebula/experiments/exp_dfe_loaded_calibration.py`, `exp_dfe_calibrated_verification.py`, `exp_dfe_calibrated_pvt.py`. Follow their recorded audit-folder pointers. Do not rerun frozen experiments into their original output folders.

## 6. Execution priorities and ready-to-use task prompts

Start the submission outline and gather member details immediately. Mandatory packaging must finish even if a technical experiment fails. The time boxes below are ceilings, not promises of simulator runtime. Rebudget against the real clock. Keep expensive SPICE work sequential; report drafting can proceed while a campaign runs if it does not disturb the measured machine workload.

### A. Highest-value technical extension: bounded analog PVT evidence

Suggested ceiling: **4-6 hours including debugging**, only if sufficient submission time remains.

> Audit what the fixed integrated 9 dB checkpoint has already verified. Write a new experiment plan for the missing analog PVT measurements, preserving its exact topology, fixed parameters, test definitions and model disclosures. Determine whether the existing runner supports corner-specific AC, input-noise and HD3 tests; the existing 45-corner link runner does not establish these. Add a separate versioned adapter or experiment if needed, without modifying frozen evidence. Start with a nominal point and a small justified stress subset, including FS / 0.95 VDD / 125 C where applicable. Verify operating points, units, parsing, model warnings and source hashes. Measure pilot runtime, then state a maximum call/time budget before expanding toward the full declared 45 corners. Stop if the runner is invalid, results require an unauthorized scientific change, or the time box threatens the submission. Record every pass, failure, untested condition, test definition and model limitation. Produce a concise coverage table linked to machine-readable evidence. Do not tune controls independently per corner and call it one fixed design.

Preflight: read CLAUDEwa scientific-change rules; check source/hash prerequisites; write to a fresh audit folder. Do not reinterpret frozen verification scripts as general-purpose new campaign tools. Existing experiment timing gives context only: Entry 142 recorded 65 OP/AC pairs in 33.445 s, Entry 143 seven checks in 331.018 s, and Entry 144 45 link calls in 1921.963 s. Analog/HD3 campaigns can cost substantially more.

Success means valid additional coverage or a bounded, intelligible failure finding. It does not require manufacturing an all-pass verdict. A smaller explicitly labeled stress subset is better than an unfinished or misleading full-PVT claim.

### B. Make the automation contribution inspectable

Suggested ceiling: **2-3 hours**.

> Produce one traceable design-run receipt using the supported production path and a supported target. Show the input request, actual policy proposals, verifier decisions, any fallback or centering steps, final selection reason, exported netlist/drawing, measured results, and measured stage/total elapsed time and SPICE-call accounting where instrumented. Reuse existing run records first. Add only the minimum instrumentation needed, preserving behavior. If a policy proposal was rejected or deterministic recovery supplied the final result, show that honestly. Distinguish cached, replayed and newly simulated work. Link the receipt to exact source and artifact identities, and make it usable in the report and demo without adding a new crowded frontend panel.

Do not write an imagined RL decision story around an existing output. This task directly supports the automated-framework deliverable and explains how the system recovers from imperfect proposals.

### C. Small fair runtime comparison, if budget remains

Suggested ceiling: **2-3 hours** after the receipt and runner are reliable.

> First identify an existing supported classical/bypass path that can be compared fairly with the RL-assisted production path. Use a small declared target set, identical circuit/search domain, acceptance criteria, verification and export work, cache policy and machine conditions. Include fallback, rejected candidates and retries in totals. Separate offline library/training costs from online request costs. Record per-target wall time, simulator calls, success/failure and achieved quality; include repeated measurements or clearly state a single-run limitation. Do not run concurrent heavy workloads during timing. Publish a small reproducible comparison and the limits of the comparison, even if RL is not faster. If no fair comparison is possible within the time box, retain the established attribution evidence and explicitly leave end-to-end acceleration unproven.

Do not reuse 91.8x candidate visits as seconds saved. Do not spend the remaining window building a new optimizer or rerunning full training to rescue a speed claim.

### D. Mandatory: 10-12-page report, matching script, recording package

Reserve **6-8 hours plus owner recording time and submission buffer**. This priority must survive reductions to A-C.

> Create a separate polished 10-12-page final report, preserving existing reports. Use the existing academic report as a source of verified evidence, not as a layout constraint. Build a clear engineering story: what was asked, why the problem is difficult, architecture, the RL-assisted design flow, what is physical versus modeled, what failed and changed, how each deliverable is addressed, results, competitive contribution and remaining limitations. Map claims to source artifacts and the organisers' three judging criteria. Preserve the useful circuit explanations and readable diagrams. Include any newly verified results only after reviewing their evidence. Count cover, references and appendices inside the 12-page ceiling unless the organiser explicitly permits otherwise. Render and visually inspect every page; avoid conspicuous accidental blank regions without shrinking text or padding with filler. Then update the 5-6-minute own-voice narration script, with exact screen actions and matching report references, deliver it as a visually verified Word document, and prepare a recording checklist and submission email draft. Do not claim the video exists until its actual file has been reviewed.

Suggested **12-page total** story (adapt intelligently; do not force awkward page breaks):

1. Title/team details, concise abstract, problem and contribution.
2. Requirements and deliverable/verification coverage matrix.
3. Product architecture and specification-to-netlist workflow.
4. RL formulation, action space, reward/proposal role and verification/fallback.
5. Source-degenerated CTLE and physical reference-current implementation.
6. Physical attenuation and peaking, variable Rs/Cs and design tradeoffs.
7. From transistor response to eye; what the one-tap DFE contributes.
8. Integrated receiver checkpoint and the difficult engineering iterations.
9. Nominal/PVT results, new valid evidence and precise measurement definitions.
10. Automation receipt, fair search/runtime evidence and competitive distinction.
11. Designer workflow, demonstration route, limitations and deliverable closure.
12. Conclusions, reproducibility/artifact guide and references.

The owner specifically liked these five circuit narratives and wants them retained, merging pages if needed:

- The source-degenerated CTLE.
- Reference current made physical.
- Physical attenuation and peaking.
- From transistor response to eye.
- What the 1-tap DFE contributes.

Use the local AAPMS-REPORT-V2 reference as a structural/style guide only if available and useful; do not copy unrelated content or upload the reference. The requested tone is structured and academic enough to be credible, but readable and competitive, with clear reasoning rather than dense textbook prose. The report should supplement the video with architecture and evidence depth.

Suggested video route (total about 5:40; rehearse to the owner's actual speaking pace):

- 0:00-0:35: problem and honest RL-assisted contribution.
- 0:35-1:20: architecture and policy/verifier/recovery flow.
- 1:20-2:35: selected 3 dB result, CTLE drawing, response and run receipt.
- 2:35-3:30: 45-corner/7-loss modeled coverage and Compare circuits eyes.
- 3:30-4:40: separate integrated 9 dB transistor checkpoint and verified measurements.
- 4:40-5:40: deliverable coverage, measured advantages, limits and closing value.

The owner will narrate and record. Give natural spoken paragraphs plus separate on-screen cues; do not make them read implementation filenames aloud. Saved completed runs are suitable for a reliable walkthrough when labeled accurately. Do not portray replay as a newly completed live optimization. Rehearse input/completion behavior separately and record one clean take; verify audio, visible text, playback, actual duration and final file location.

### Defer unless essential to a demonstrated submission blocker

No new frontend redesign, full policy retraining, unbounded target sweep, major topology change, PDK migration, layout campaign, or decorative dashboard expansion. The LLM wrapper is optional bonus work only if the real integration already exists and can be demonstrated cheaply; it must not displace required evidence or the report/video.

## 7. Existing artifacts and unfinished Word task

Current detailed report:

- `output/pdf/Nebula_Submission_Report_20260914.pdf`: **25 pages**, not compliant with the newly supplied 10-12-page requirement.
- SHA-256: `169845fac6690d16630a18d70d7118b0936b66ce9bca277aed7380ae2025c15f`.
- Builder: `nebula/report/submission_story.py`.
- Checker: `nebula/report/check_submission_story.py`.
- Source/review metadata are alongside the PDF. Entry 150 records all 25 pages checked; pages 6 and 21 were updated and inspected, other pages matched their previous reviewed version.
- Preserve the older academic and competition editions as well. Do not assume the user wants the current report deleted because they authorized a new one.

Choose a clearly separate final basename, for example `Nebula_Final_Submission_12p_20260915.pdf`, and keep its source plus source-to-claim/visual review record. That example file is a proposed output, not an existing artifact. Update all script page references; the detailed report's current RL and matrix pages are 8 and 23 and will change in the condensed edition.

Existing tracked walkthrough: `nebula/SUBMISSION_DEMO_SCRIPT_20260914.md`.

Word-script recovery status, verified while preparing this packet:

- `tmp/demo-word/build_script.py` exists locally and contains a newer six-scene, approximately 616-spoken-word script presenting RL-assisted design.
- The earlier intended output was `output/docx/Nebula_RL_Assisted_Demo_Script.docx`.
- **That DOCX is currently absent** despite having been created in an earlier attempt; cause is unknown. Do not give the owner a nonexistent link or claim it is finished. Inspect/rebuild from the surviving source, reconcile with final report/demo content and deliver a real file.
- Word rendering stalled; there is no completed page-render/visual-QA evidence for that Word document. Existing temp files/logs are not a passed layout review.
- No final demo recording has been verified. Earlier recording/control attempts did not establish a usable video.

Use the documents skill for DOCX and the PDF skill for report rendering if available. The local bundled Python runtime is at `C:/Users/DELL/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`. The bundled runtime had no LibreOffice installation; Word COM export attempts stalled. Inspect current capabilities and time-box renderer troubleshooting; do not claim visual verification from successful DOCX creation alone. Temporary files are not portable dependencies: preserve the final script source in a suitable project-owned path.

## 8. Validation, scientific controls and backup

Read the actual current repository rules; these reminders do not replace them.

- Update `HANDOFF.md` in the same commit as every change, including a dated Session Log entry and affected map/current-state/limitations/next-step sections.
- Required full command from repository root:

```powershell
py -3.13 -m pytest tests nebula/tests -q -m "not slow"
```

- Entry 150 final frontend baseline: **3427 passed, 13 deselected, two known warnings in 1127.20 s**; the preceding baseline was 3421 passed. Focused frontend checks: 36 passed. Do not add overlapping suite totals together.
- A later completed full run during Word preparation logged **3427 passed, 13 deselected, two warnings in 1517.67 s** in `tmp/demo-word/full-tests.log` (PowerShell UTF-16 log). This is existing evidence, not a new run performed by writing this packet.
- Budget about 20-30 minutes for the current full suite, not AGENTS.md's historical 407-test / 1.5-minute estimate. Run required before/after checks for implementation changes, add meaningful tests for fixes/features, and never commit with failures. Reuse a recorded baseline only after verifying the implementation has not changed. Documentation-only packet edits do not establish new scientific or test results.
- Run only one expensive SPICE campaign at a time. Do not overlap campaigns, timing experiments, heavy tests or policy jobs. Respect existing run locks and simulator-call budgets.
- `CLAUDEwa.md` section 8 governs parameter ranges, reward and specification tightness changes; do not silently alter them to produce success. Read its exact conditions before changing scientific settings. Topology decisions may require human approval under the contract; do independent preparation before requesting a concrete decision.
- Use the correct `ngspice_con.exe` and environment. PySpice is broken here. Read `.spiceinit` from the required working directory; use the verified trimmed SKY130 library and correct micron units. Check simulator output and operating points because exit code zero can conceal failures. Input-noise RMS volts must not be square-rooted again.
- Mocks produce fake numbers and may never substantiate a deliverable. Preserve source hashes, exact deck provenance, seeds, test definitions and frozen results. Do not weaken hash checks or rewrite prior result manifests to accommodate new source files.
- G197 documents nine legacy JSON working-tree CRLF versus Git LF hash differences. Do not normalize those files or rewrite expected hashes casually. G198 and later frontend/eye gotchas also remain mandatory reading.

Before report publication, check every prominent number against its result source and give the scope next to the claim: selected physical CTLE, ideal-DFE link model, or separate integrated transistor checkpoint. Label partial coverage and model limitations, especially power-source exclusions, geometric rather than layout area, finite test patterns, and held-state versus clocked analyses.

Git backup is already authorized for project-owned verified material in this **public** repository. Use the global identity `Jai Kaushik <jaikaushik-prog@users.noreply.github.com>`. Back up the working branch and main with normal fast-forwards only; inspect divergence and do not force-push. Stage explicit paths. Do not upload reference PDFs/DOCXs, organiser handouts/images, PDK models, secrets or ignored reference materials. The owner's `eye_Diag.jpeg` is currently untracked; leave it out. Do not change repository visibility. Keep final deliverables accessible locally even if an artifact is intentionally ignored by Git.

## 9. Environment and collaboration notes

- PowerShell is the default shell. Use UTF-8 explicitly for Markdown. Console print output should stay ASCII; Python code passed through shell pipes can corrupt literal non-ASCII text. Use Unicode escapes where needed.
- In this session the default exec/apply-patch sandbox encountered an ACL setup error. Read/write commands succeeded using reviewed `require_escalated` exec calls. That is an environment issue, not permission to bypass a rejection. If it recurs, use the approved mechanism and clearly report any actual block.
- Do not kill unknown Word, browser or Python processes. Verify the process command line and ownership first. The previous renderer did not complete; reopening the owner document is not evidence of export success.
- The owner paused the other frontend agent and assigned frontend ownership here. Check actual current work before overwriting files; do not assume an old agent is still active or resume redundant parallel editing.
- Keep user updates brief, plain and frequent. Explain what a finding means for their presentation. Ask only genuinely missing questions, early, while continuing independent work. Never promise qualification or claim full compliance from partial evidence.

## 10. Completion checklist for the next agent

- [ ] Current branch/source state and remaining time verified; required reading completed.
- [ ] Mandatory report/script/recording time protected; technical experiment plan and stop limits recorded.
- [ ] Any new scientific evidence is traceable, validated and honestly scoped; failed/untested conditions retained.
- [ ] Automation role and any measured speed claim match the actual production path and comparison accounting.
- [ ] Separate final report is 10-12 total pages, readable, rendered and visually checked, with a requirements matrix and preserved circuit story.
- [ ] Final Word narration script exists at a verified path, matches the five-tab product and report, and has completed visual QA.
- [ ] Owner has screen cues and a recording checklist; actual video is reviewed before calling it complete.
- [ ] Team/contact details are confirmed; email draft has correct subject, recipient and filenames. No email sent without explicit authorization.
- [ ] Required tests/checks passed for implementation changes; HANDOFF updated; verified project-owned files backed up normally.
- [ ] Final response gives clickable artifact paths, measured verification status and any remaining owner action, without burying the submission deadline.
