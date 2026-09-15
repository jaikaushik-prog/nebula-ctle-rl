# Nebula presentation closeout

## Completed scope

The three owner-selected presentation tasks are complete. Use
http://127.0.0.1:8766/#results and refresh once to load the current scripts.

1. Run files now starts with **Programmable receiver prototype**, a separate
   expandable panel for the selected-derived experimental receiver. It contains
   four nominal metrics, physical control voltages, conditions, retained limits,
   eight named artifact links and expandable exact drawing/response views.
   Data loads only when opened. Selection changes discard the previous panel;
   a missing matching parent cannot inherit its results. Loading failures use
   the shared read-only retry and wrong-server guidance. Setting352 remains the
   accepted fixed CTLE. No live tuning slider or new verification is implied.
2. The final academic report is
   `output/docx/Nebula_Academic_Final_Report_20260915_v4.docx`.
   Four paragraphs and the interface screenshot were aligned with current
   navigation. Scientific tables, other narrative, 12 figures, three native
   equations and existing identity fields are preserved. The source v2 is
   byte-identical. Intermediate v3 was locked by another process when a layout
   correction was attempted; it was preserved, not force-closed or replaced.
3. A fresh demo script was written from current app/report/evidence, without
   reading prior scripts. Text: `nebula/CURRENT_APP_DEMO_20260915.md`.
   Word: `output/docx/Nebula_Current_App_Demo_20260915_v2.docx`.
   It includes exact actions, a 5:55 core, optional separate failed-run and
   explanation scenes, and a saved-report/file fallback. The failed saved run
   is 6 dB / 2.1 GHz, FAILED daf7cf8a; it is not setting288's recovery attempt.

## Verification

Focused final suite: **34 passed in3.01s**. The preceding Entry162 closeout had
29 passing tests; an initial expanded implementation check had31, then34 with
the new panel tests. The initial pre-edit check was launched but its console
summary was not retained, so it is not represented as a new baseline result.
No broad regression was run.

Browser rehearsal passed at1440x1000,1280x900 and390x844. It exercised lazy
loading, eight artifact responses and SHA-256 equality, an actual deck download,
all seven selected-CTLE PVT slices with45 passing cells each, a separate saved
failed run, valid/invalid query parsing, response/spec/sizing/run-record tabs,
comparison modes, the channel intake view, and simulated503/retry. Additional
checks exercised deterministic explanation, three evidence disclosures,
comparison swapping, diagnostic expansion and a null-parent response.
No page errors or horizontal overflow. Only parsing and deterministic explanation
used POST; design, channel-job and archive-generation routes were blocked and
never requested. No simulator/training/design job was launched by this task.

Intermediate rehearsal issues were test-only: a relative URL without a base,
selection while the explorer-only picker was hidden, a Windows text-decoding
assumption, and one transient page-load timeout. They were corrected or rerun;
passing browser records are `tmp/academic-closeout/entry163-rehearsal.json` and
`entry163-supplemental.json`. No scientific acceptance criterion was relaxed.

Both final DOCX files were rendered using the isolated portable LibreOffice
runtime. Every page was visually reviewed at full image size. Report pages1-9
and12 have identical pixels to the fully inspected first render; corrected
pages10-11 were reinspected. All four final demo pages were inspected. No clipping,
broken tables, lost equations or orphaned action headings remain. The final
read-only structural check also confirms unchanged scientific table cells and
source hash. The PDF text assertion was normalized for line wrapping.

| Artifact | Pages | Words | SHA-256 |
|---|---:|---:|---|
| Academic report v4 | 12 | 3911 | 586be1c4733643ead1225170c10be0c1347e94c0156d73fd89918cc371fae46a |
| Current app demo v2 | 4 | 1529 total;675 core spoken | 8a0f875de840f4ac6fe8b54459a0964a39871763a6c6bb6cfe7aaa6db97c7456 |

The approximately5:55 schedule allows on-screen actions; it is not a measured
human recording time. Optional scenes extend it. Source metadata is
`output/docx/Nebula_Current_Presentation_20260915_v2_sources.json`.

## Remaining owner actions

Fill team/institution and the six contact/email cells, read the current narration,
record and review the video, and submit the chosen report/video. Earlier versions
are preserved; use the exact final filenames above. Full programmable-receiver
verification, signed model-domain closure, expanded target coverage, BER, layout
and a demonstrated RL time advantage remain open engineering work. No report
wording or UI success was used to claim those tasks complete. No commit, push,
publication, email or submission was performed.
