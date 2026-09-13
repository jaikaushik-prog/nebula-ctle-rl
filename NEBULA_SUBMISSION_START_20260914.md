# Nebula submission-night restart - 14 September 2026

## Read this first: active instruction

You are continuing Jai Kaushik's Nebula competition project. The laptop was
unavailable for 2-3 days. Final submission is **15 September 2026**; the user
wants to finish the **frontend, formal report and demo tonight**.

The user explicitly requested this file so a NEW SESSION can start immediately.
Do the work, verify it and deliver it; do not stop at a plan. Start by reviewing
the existing unfinished frontend changes, then update the academic report, then
prepare and rehearse a reliable desktop demo. Keep the user updated simply.

This file supersedes the OLD root `NEXT_AGENT_PROMPT.md` for current status and
priorities. That old prompt describes Entry 120/121 and incorrectly implies
there is no working transistor DFE/configurable Rs/Cs. Historical failures in
HANDOFF are real, but later successful experiments must not be ignored.

This packet is a continuation guide, not a certificate that the pending frontend
or submission is complete. The final frontend regression result was not captured
before interruption. Do not turn historical test counts into current passes.

## 1. Repository and mandatory orientation

Repository:

    C:\Users\DELL\Desktop\serdes-dsp-framework-main

Remote:

    https://github.com/jaikaushik-prog/nebula-ctle-rl.git

Read `AGENTS.md`, then its required documents in this order:

1. `HANDOFF.md` in full, using bounded chunks to avoid truncated reads.
2. `CLAUDEwa.md` in full.
3. `nebula/G0_RESULTS.md`.
4. `nebula/NRZ_RETARGET_AUDIT.md`.

HANDOFF is nearly 20,000 lines. Its older paragraphs describe historical states;
the recent Entry 122-147 sequence and Gotchas through G195 matter now. Do not
claim you read a file fully if tool output truncated. This packet does not
replace the repository's instruction to read HANDOFF.

Read current evidence before changing a claim. Nebula is under `nebula/`:
5 Gbps NRZ, PCIe Gen2, SKY130. The original `python_models/` project is a
separate 112G PAM-4/28 nm methodology project; do not mix its assumptions or
results into Nebula.

Use available frontend-design and PDF skills when doing those respective tasks,
including their actual instructions and visual QA. Do not spend time on mobile.

## 2. LIVE state checked on 2026-09-14

- Branch: `nebula/winning-sprint-20260908`.
- Local HEAD: `c8cdff4216b39fc8bbab2acbdbb802cdd9d23439`.
- Read-only `git ls-remote` verified BOTH remote main and working branch at
  that same commit on 2026-09-14.
- Git identity: Jai Kaushik
  `jaikaushik-prog@users.noreply.github.com`.
- NEVER use a BITS email for commits.
- Worktree is NOT clean. Pending frontend work is intentional; preserve it.

At restart-packet creation these SIX files already had uncommitted changes:

    HANDOFF.md
    nebula/tests/test_web_hardware_checkpoint.py
    nebula/web/static/app.js
    nebula/web/static/circuit_views.js
    nebula/web/static/index.html
    nebula/web/static/styles.css

Their pre-packet diff was 356 insertions / 269 deletions. The packet creation
also adds this file and a dated resumption note in HANDOFF. No frontend code
was changed during packet creation.

No Python or ngspice processes were returned by the 2026-09-14 process check.
Do not assume the old server or old pytest session survived. Recheck live
processes before launching anything; old tool session IDs are not completion
evidence.

Run at the start:

    git status --short
    git branch --show-current
    git rev-parse HEAD
    git remote -v
    git diff --stat
    git diff -- HANDOFF.md nebula/web/static nebula/tests/test_web_hardware_checkpoint.py

The user repeatedly authorized public GitHub backup, most recently explicitly
on 2026-09-10. After verification, commit intended work WITH HANDOFF and push
both working branch and main via normal fast-forwards. Never force-push or
change visibility. Recheck refs before pushing, and verify them afterwards.
Do not upload unverified frontend changes simply to make a backup look finished.

Keep ignored copyrighted reference PDFs, organiser handouts, reference DOCX,
PDK model files, release ZIPs, `tmp`, and `gmcmp.pkl` out of Git.
`nebula/AAPMS-REPORT-v2 (3).docx` must remain ignored.

## 3. Owner, tone and deadline priorities

Owner: Jai Kaushik, BITS Pilani undergraduate; beginner in analog/RL engineering.
Explain what changed, why it helps, how it was verified, and how to present it.
Use simple, short progress updates, particularly during long tests.

Team for report/demo:

- Jai Kaushik: f20240419@pilani.bits-pilani.ac.in
- Rishabh Agarwal: f20240387@pilani.bits-pilani.ac.in
- Avi Mehta: f20240607@pilani.bits-pilani.ac.in
- Birla Institute of Technology and Science, Pilani (BITS Pilani)

User's explicit design preference: **PC/desktop only; clean, informative,
professional engineering-tool aesthetic.** Avoid crowded cards, repetition,
decorative dashboards, redundant scope/evidence sections, and mobile work.
Retain essential qualifications beside the result, not a large closing table
advertising weaknesses. Be confident about implemented work, never invent
results or imply knowledge of an internal judging rubric.

Tonight is submission preparation, not an invitation to restart research.
Use saved verified evidence for UI/report/demo. Do not launch training, alter
frozen held-out experiments, or start a new SPICE campaign just to improve
presentation. If a functional expansion needs new experiments, explain the
time/risk and distinguish it from presentation work.

## 4. What the organisers clarified

The user asked whether a behavioural DFE attached to transistor CTLE was enough.
Organisers said to start with a suitably loaded DFE model, but the final
implementation should demonstrate complete CTLE + DFE at transistor level
(their response typed "DFT" in the second sentence).

They also explicitly want **configurable Rs/Cs**, not merely different fixed
passive netlists. The user authorized implementing both, DFE first and backing
it up before Rs/Cs work. Those hardware experiments have now progressed far
beyond the original failed 14/32-bit prototype. Do not redo those failures.

## 5. Latest actual hardware result - essential distinction

There is now a **connected transistor CTLE + transistor DFE + electrically
configurable Rs/Cs checkpoint**, independently verified at selected controls.

Read:

    nebula/DFE_CALIBRATED_RESULTS.md
    nebula/product_audits/entry142_dfe_loaded_calibration_20260910/
    nebula/product_audits/entry143_dfe_calibrated_verification_20260910/
    nebula/product_audits/entry144_dfe_calibrated_pvt_20260910/

Exact nominal connected netlist:

    nebula/product_audits/entry143_dfe_calibrated_verification_20260910/link_state0_tol1e-05_step5ps/design.cir

Circuit includes SKY130 CTLE, PMOS input attenuator, physical bias/reference and
MIM bypass, an NMOS-controlled Rs network, two N500 varactors, CML summer,
master/slave decision memory, and real current-feedback DAC. The device sheet
parses 73 SKY130 instances from the pinned deck.

Selected target: **9 dB / 1.9 GHz**.
Controls: R=.70 VDD, C=.185 VDD, nominally **1.260 V / .333 V**.
Fixed code 2 and phase 1 for the calibrated link grid.

Verified nominal Entry 143 results:

- Actual loaded boost **8.743882760-8.746919126 dB**.
- Actual peak **1.903117755-1.906285212 GHz**.
- These satisfy unchanged internal target tolerances .5 dB / 100 MHz.
- Input noise **.654039305-.654050922 mVrms**, 10 MHz-5 GHz,
  two negative-branch held-clock small-signal measurements.
- Clocked CTLE-output HD3 **-54.9137 to -54.9201 dBc**,
  100 MHz / 100 mV differential peak input; four numerical settings pass.
- **64/64 scored bits** on the constructed **7.5 dB** channel.
- Sampled summer eye **210.340342 mV**.
- Positive opening **.705 UI**; width above 100 mV **.655 UI**.
- Nominal decoding-run VDD power **9.263481 mW**.
- Current geometry subtotal **.014715766 mm2**, NOT routed area.

Entry 144 independently passes **45/45 sampled LINK PVT points**, with the
same geometry, controls, code and phase, same 7.5 dB channel, 64/64 bits each:

- Five transistor corners x three supplies x three temperatures.
- Minimum sampled eye **113.243715 mV** at FS / .95 VDD / 125 C.
- Minimum positive opening **.635 UI**.
- Minimum opening above 100 mV **.560 UI**.
- Maximum CTLE + DFE VDD power **12.524081 mW**.
- Maximum external positive clock power **.128145920 mW**, reported separately.

Key boundaries to keep adjacent to these results:

- Link PVT is NOT all-spec analog PVT. Noise/HD3 are nominal checks.
- Eyes are finite-pattern, noiseless waveforms, NOT BER contours or signoff.
- Clock/control/common-mode generators remain external.
- Typical passives; no local mismatch, passive tolerance or extracted layout.
- Generic-poly voltage-dependent nonlinearity is outside model verification.
- Strict new-DFE signed-voltage and whole-circuit magnitude/body/varactor checks
  pass, but separately recorded bilateral Rs-switch signed Vds model-domain
  findings remain present at all 45 points. Do not claim reliability signoff.
- No complete loaded target rectangle, DFE-active runtime tuning or full
  receiver signoff has been established.
- Entry 143 common call labels are not solver settings for static/link cases.
  Read exact frozen decks; static retains reltol=1e-7, link uses 1 ps.
- Frozen raw data and failed experiments must never be rewritten.

Additional configurable-Rs/Cs evidence:

- Entry 131: one N500/no-fixed-MIM standalone circuit reaches nine nominal
  target identities, 3/6/9 dB x 1.5/1.9/2.25 GHz, within .5 dB/.1 GHz.
- Entry 135: all three standalone runtime transitions FAIL the original
  500 ns internal-control settling gate.
- Entry 136: SAME circuit eventually settles at 850/690/650 ns after ramps.
  Eventual tuning is demonstrated; original 500 ns failure remains failed.
- These standalone results are not a loaded CTLE+DFE target map.
- Earlier fixed-passive transistor DFE Entries 125/126 passed 135 declared
  channel/PVT cases; do not merge those into Entry 144's 45-case new-control grid.

Use raw summaries/manifest hashes and adapter tests to substantiate report
values, not this packet alone.

## 6. Product implementation vs saved hardware

Current web product:

    nebula/web/
    nebula/web/hardware_checkpoint.py
    nebula/web/hardware_visuals.py
    nebula/web/static/index.html
    nebula/web/static/app.js
    nebula/web/static/circuit_views.js
    nebula/web/static/styles.css

Run locally:

    py -3.13 -m nebula.web --no-browser

Default URL: http://127.0.0.1:8765/
Useful routes: /#hardware and /#results.

`hardware_checkpoint.py` pins Entry 143/144 summary hashes and nominal deck,
checks required real instances, serves `/api/hardware` and eight allow-listed
artifacts. Missing/changed evidence must fail closed.
`hardware_visuals.py` builds the device sheet and folds saved summer traces
into the nominal eye; no new measurement is invented.

IMPORTANT: the live Design Explorer generators `rl-hybrid` and `rl-physical`
still use earlier fixed-passive / cursor-DFE paths. The transistor checkpoint
is exposed in Receiver, NOT yet automatically re-generated for arbitrary input
specs. Frontend diagrams do not change backend measurement provenance.

Earlier physical workflow:

    nebula/physical_design.py
    nebula/physical_verified_registry.json
    nebula/product_demo/physical_bias_9db_1p9ghz_20260906/

Its fixed setting 490 (A7/R5/C2) passes 315/315 old electrical-model cases:
45 PVT x seven constructed channel losses, with behavioural cursor DFE.
Recovery registry has fixed 3/6/9 dB at 1.9 GHz, not full target coverage.
Old .007854511 mm2 subtotal belongs to the older CTLE/reference, not the
new complete transistor checkpoint's .014715766 mm2 subtotal.

Saved 5 dB/1.9 GHz user run is 312/315. Its three failures are the 3 dB loss
slice: SS/.95/0 C, SF/.95/0 C, SF/.95/27 C. Preserve failure-aware PVT rendering,
including first failing slice, 42/45 slice count, PASS/FAIL/MISSING labels and
per-loss totals. A 45-cell chart can refer to different underlying evidence;
never silently swap the new transistor Link PVT and old generator PVT.

## 7. Unfinished frontend work - resume here

User's latest detailed requests:

1. Receiver eye and values must not remain apparently valid when specifications
   change in Design Explorer.
2. Remove duplicate Receiver 45-corner PVT and bulky "Inspect exact evidence" /
   "Measurement scope" panels; actual generated-run PVT has its dedicated tab.
3. Old generated PNGs still say behavioural DFE, and old "scope and evidence"
   prose is out of date/confusing.
4. Show four clear block circuit diagrams: **CTLE, transistor DFE, attenuator,
   physical supply-dependent reference + bypass**.
5. Keep configurable Rs/Cs easy to find.
6. Keep the desktop product clean, informative, readable and professional.

Already implemented IN THE DIRTY TREE, not finally signed off:

- Receiver matches current numeric request against saved 9 dB / 1.9 GHz target.
  `hardwareTargetMatches` and `renderHardwareTargetState` in app.js hide saved
  eye/metrics on mismatch, retain topology and show an explicit missing-match
  message. Called on input edits, parsing and hardware load.
- Duplicate Receiver PVT/evidence/scope panels removed.
- Four-panel Design Explorer implementation map added via
  `NebulaCircuitViews.renderDesign` and `designBlockGrid`.
- Selected A/R/C codes and fixed Rs/Cs values appear beside the blocks.
- Fifth Receiver connectivity view added: physical reference + MIM bypass.
- DFE captions distinguish transistor reference from selected cursor score.
- Exact original generated CTLE image remains inside a collapsed disclosure.
- Obsolete signal cartoon/metric rail/hardware-boundary panel removed.
- Mode picker synced to displayed result; shorter mode labels to prevent clipping.
- Tests added for matching/mismatching targets, four cards, missing values.
- HANDOFF sections updated provisionally for Entry 147, BUT some wording says
  "completes" prematurely; correct pending/completed state after actual QA.
  The prior session did not append Entry 147's final verification log.

Review/fix candidates, NOT all independently confirmed bugs:

- 1040x340 SVGs scaled into two columns may have unreadably small device text.
  Inspect at normal desktop widths. Consider an expand control/clear inspector
  rather than more permanently expanded panels.
- New reference SVG wires may not land on MOS terminals correctly. Check
  actual helper coordinates and deck connectivity; capacitor helper may show
  a variable-cap arrow even for fixed Xcbyp. The exact source is authoritative:
  Xbpref p_bias/p_bias/vdd/vdd; Xbpfeed nbias/p_bias/vdd/vdd;
  Xrbias p_bias/0/0; XMR nbias/nbias/0/0; Xcbyp nbias/0.
- Attenuator guide gate labels appear hardcoded for A7 while selected card can
  show A6. Either make labels reflect selected configuration or explicitly
  show a checkpoint-only connectivity guide, not an exact generated circuit.
- CTLE configurable diagram is not the exact fixed-passive export. Keep this
  distinction understandable without reviving a wall of scope prose.
- Original generated PNG may STILL contain behavioural DFE because its backend
  truly is behavioural. Do not cosmetically relabel raw scientific evidence as
  transistor-simulated. Provide a truthful current product diagram; preserve
  exact raw artifacts and label provenance concisely.
- Removing scope panels must not remove essential "saved finite noiseless
  waveform" / "nominal analog, sampled link PVT" qualifications near results.
- Check target sync through manual inputs, natural-language parsing, Judge mode,
  generated results, reload and switching tabs/modes, including back to 9/1.9.
- Check missing/malformed targets and missing evidence do not show fake passes.
- Clarify read-only Rs/Cs controls; do not fake slider-driven measured values.
- Determine whether the generated-design UI and top-level navigation are now
  coherent; avoid redundant panels and ensure downloads/figures still work.

Prior visual QA assets (ignored):

    tmp/frontend_qa/hardware.png
    tmp/frontend_qa/hardware2.png
    tmp/frontend_qa/hardware3.png
    tmp/frontend_qa/hardware4.png
    tmp/frontend_qa/results.png
    tmp/frontend_qa/results2.png

Earlier screenshot inspections included 1200x1500 and 1440-wide desktop.
Some tall/large PNGs could not be opened via tool output limits. Do not claim
all final states were visually reviewed. DOM tests are not visual inspection.

## 8. Testing status - do not infer completion

Mandatory full suite from root:

    py -3.13 -m pytest tests nebula/tests -q -m "not slow"

Historical completed runs:

- Entry 146 final: **3407 passed**, 13 deselected, 2 warnings, 1438.15 s.
- Pre-Entry-147 baseline, recorded in prior session:
  **3407 passed**, 13 deselected, 2 warnings, 1191.12 s.
- Latest Entry 147 focused:
  **23 passed in 2.99 s** using:

      py -3.13 -m pytest nebula/tests/test_web_hardware_checkpoint.py nebula/tests/test_web_app.py -q

- Both JavaScript syntax checks had passed:

      node --check nebula/web/static/app.js
      node --check nebula/web/static/circuit_views.js

The interrupted final full run was last observed at 86% with no failures shown;
its completion is UNCONFIRMED. Old session ID 34081 is historical only.
No matching test process was running at packet creation. Rerun required final
validation; do not write a final 34xx count from expectation.

The two known warnings concern optional scikit-rf and PyTorch tensor conversion.
Suite duration is now around 20-30 minutes on this laptop, NOT the obsolete
1.5-minute/407-test count in AGENTS. Budget time accordingly. Reuse a verified
baseline only when appropriate, and record exact before/after results.

This packet-only turn did not rerun code tests, complete the frontend, commit
it, or push the dirty tree. The new session owns final implementation validation.

## 9. Formal report - update academic edition only

Preferred:

    output/pdf/Nebula_Competition_Report_Academic.pdf

Builder / checker / tests:

    nebula/report/competition_academic.py
    nebula/report/check_academic_pdf.py
    nebula/tests/test_academic_report.py

QA and provenance:

    output/pdf/Nebula_Competition_Report_Academic_review.json
    output/pdf/Nebula_Competition_Report_Academic_sources.json

Live SHA-256 checked 2026-09-14:

    a573db02335879e0a6a0b3feb2c9eeea2172c2f3f4b4e4699dfc8123c8f90670

Still the old 22-page academic edition; new transistor/configurable achievements
have NOT yet been incorporated. Inspect content before revising. Preserve the
academic structure, team cover, abstract, contents, evidence hierarchy, figure
sequence, outline, references and a constructive final future-work section.
Use raw new evidence, not broad search-and-replace of "behavioural".

Main report work:

- Integrate the latest connected transistor DFE and voltage-configurable Rs/Cs.
- Present calibrated nominal and link-PVT results with correct measurement scope.
- Update old statements saying transistor DFE/configuration is simply absent,
  while retaining old experiments as history only when useful.
- Distinguish frozen RL bank results, old delivered generator and new hardware.
- Update block/circuit and eye figures as needed from source-derived assets.
- Do not transfer old area/power or 315-case counts to the new receiver.
- Keep necessary limitations beside their claims; no sprawling weakness table.

Rebuild/check:

    py -3.13 -m nebula.report.competition_academic
    py -3.13 -m nebula.report.check_academic_pdf

Modify academic builder, not fallback builder, unless the user asks otherwise.
Add focused tests/source-manifest support when required. Render and visually
inspect every changed page at readable resolution. Keep visual_review PENDING
until actual inspection; then record exact PDF hash and reviewed pages.
If the edit is local, compare untouched-page raster hashes. Do not run SPICE
or training for report changes.

DO NOT OVERWRITE fallback:

    output/pdf/Nebula_Competition_Report.pdf

Live SHA-256 checked 2026-09-14:

    3cd67ffc933b8f369d601a72f16e39295542780777ca5bccc797135278faf43b

20 pages. Byte-preserved archive:

    output/pdf/archive_before_academic_restructure_20260909/

Preserve archive PDF/review/source manifest/builder snapshot/checksums bytewise.

## 10. RL evidence and safe attribution

Relevant:

    nebula/rl/margin_improve_env.py
    nebula/rl/safety_shield.py
    nebula/experiments/shielded_policy_final_results.json
    nebula/product_audits/entry115_exhaustive_benchmark_20260908/
    nebula/product_audits/entry113_attribution_20260907/
    nebula/WINNING_SPRINT_RESULTS.md

Frozen PPO operates in an 8x8x8 cached attenuation/Rs/Cs library, with target,
current setting and bounded measurement history; moves +/- one index or LOCK.
Deterministic best-compliant-visited safety shield chooses safe output.

Defensible figures, verify against raw sources:

- Five frozen seeds, 2,430 held-out midpoint identities.
- Mean normalized eye quality improvement over fixed start **.1550**,
  paired 95% interval about **.1508-.1593**.
- **5.579 candidate visits** on average.
- **91.7657x candidate-visit reduction** versus all 512 cached settings.
- NOT measured end-to-end SPICE or wall-clock acceleration.
- Exhaustive near-optimality gate FAILED: mean oracle-solvable regret **.28310**;
  **20.905%** within .05 of oracle.
- Local random control has higher compliance; PPO higher mean quality and fewer
  visits at the reported budget.
- Offline characterization and five-seed training remain billed.
- New calibrated physical receiver postdates frozen RL. It does not prove PPO
  discovered that circuit.
- Deployed selection is an RL-assisted hybrid with measured-bank fallback and
  deterministic verification, not unconstrained transistor synthesis.

Do not rerun/tune frozen held-out experiments to obtain a nicer headline.

## 11. Demo to finish after frontend/report

No new final demo package was created in the interrupted frontend work.
Inspect existing demo assets first; do not assume every older README is current:

    nebula/product_demo/rl_hybrid_9db_1p9ghz/
    nebula/product_demo/plain_english_9db_1p9ghz/
    nebula/product_demo/physical_bias_9db_1p9ghz_20260906/
    nebula/product_demo/touchstone_synthetic_demo/

Prepare a short desktop demo runbook and tested launch instructions, with saved
fallbacks so judging does not depend on a long new simulation. A sensible
sequence (proposal, not a claimed finished recording):

1. Show Receiver's actual calibrated transistor implementation, configurable
   Rs/Cs network, DFE feedback path and physical reference.
2. Show saved nominal eye and measured values with concise provenance.
3. Show generation/spec entry in Design Explorer and explain which path runs.
4. Inspect four circuit blocks, correct PVT result and generated files.
5. Explain RL's measured candidate-visit contribution and hardware verification
   without attributing one experiment's results to another.
6. Open final academic PDF and exact evidence/export as fallback.

Test launch, routes, selections, diagrams, downloads and failure-aware states.
Clearly label cached Judge mode as cached; never stage it as a fresh SPICE run.
Do not promise arbitrary controls/channel uploads are transistor-verified.
Uploaded Touchstone profiles remain PROFILED_NOT_RL_VERIFIED.

If the demo needs a recording or deck and format/duration is not specified,
ask one concise non-blocking question while preparing the runbook and local
desktop flow. Do not send/upload an actual competition submission without
the user's direction. GitHub backup authorization is not portal-submission
authorization.

## 12. Windows/tool issues carried forward

PowerShell, Python launcher `py -3.13`. Default shell-tool filesystem access
currently fails with:

    helper_unknown_error: apply deny-read ACLs

The same read-only commands with the tool's approved
`sandbox_permissions: require_escalated` work. Use the proper approval
mechanism; do not disable ACLs or alter system security. Packet creation
reconfirmed this issue. If the environment is fixed in the new session,
use ordinary tools normally.

Use apply_patch for edits. In the prior session the tool wrapper also hit the
ACL failure. The installed official Codex apply_patch backend was used through
an approved escalated exec; do not replace this with shell file-write tricks:

    C:\Users\DELL\AppData\Roaming\npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe

Its `--codex-run-as-apply-patch` entry point takes the complete patch as one
argument. In Windows PowerShell, a single-quoted here-string preserves literal
content; use correct Windows native-argument escaping for the complete patch.
Prefer the normal apply_patch tool whenever it works.

CUA/browser and view_image also failed in the prior session. Local headless
Edge screenshots and browser DOM interaction probes were used as fallback.
Do not spend hours repairing computer-control tools on submission night.

Edge:

    C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe

Useful headless flags: --headless=new --disable-gpu --hide-scrollbars,
--virtual-time-budget=6000, --window-size=1440,1800, a task-specific temporary
profile and screenshot path under ignored tmp. Wait for actual file creation.
Use hidden windows for background helper/server processes.

When view_image was unavailable, approved read-only base64 image loading into
the tool's image output worked for roughly <=165 KB screenshots; larger output
was truncated. Use readable viewport captures/crops, not unreadable thumbnails.
Never claim a visual review from DOM tests alone.

Simulator safeguards IF explicitly needed later:

- ngspice 41, conda environment nebula, ngspice_con.exe (never GUI ngspice.exe).
- PDK C:\Users\DELL\sky130A.
- Run decks from nebula/device/spice so .spiceinit is read.
- Instance W/L are plain micron numbers; avoid double scaling.
- Parse complete expected vectors and reject simulator warning/failure output;
  exit code zero alone proves nothing.
- Input noise is already RMS voltage; never take its square root again.
- One-definition model-card rule; no divergent hand-copied models.
- Mock results are fake and cannot enter deliverables.
- Bounded preregistered experiments only; preserve raw failures.

## 13. Practical start and definition of done

Start in this order:

1. Read required instructions, inspect live dirty diff, confirm no stale jobs.
2. Briefly tell Jai what is already implemented and what remains.
3. Finish the desktop frontend and check its provenance/diagram correctness.
4. Update academic report from calibrated evidence and perform PDF visual QA.
5. Prepare/rehearse demo, with clearly cached fallback and concise talk track.
6. Run focused tests and mandatory full suite; budget for its actual duration.
7. Finalize HANDOFF Entry 147 and subsequent dated report/demo records.
8. Audit intended staged files for secrets, prohibited references and size;
   preserve user work and archived PDFs.
9. Commit with correct identity, push both branches fast-forward, verify refs.
10. Return concise delivery links, exact test counts, PDF QA status and commit.

The requested submission-night result is complete only when frontend is
inspectable and visually checked, current report exists with verified evidence
and PDF QA, demo has been rehearsed, relevant tests pass, HANDOFF is accurate,
and verified project-owned changes are backed up to both GitHub branches.
Report any material remaining limitation honestly. Do not claim full hardware
generation/BER/analog-PVT signoff merely because the presentation is polished.
