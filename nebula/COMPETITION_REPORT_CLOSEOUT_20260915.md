# Competition report editorial closeout - 15 September 2026

The owner requested a stronger competition-facing report emphasizing deliverable coverage, innovation and thought process. A separate final Word edition leads with demonstrated contributions, explains engineering decisions constructively and consolidates repeated qualifications without changing results.

## Current report

- File: `output/docx/Nebula_Competition_Report_20260915_Final.docx`
- 12 pages; 4,099 whitespace-delimited words including table cells.
- SHA-256: `0c10e6dcadcc31b19d2f6aa86debc14485f7fa50ac51cfc788ec631dbd832349`
- Source: `output/docx/Nebula_Academic_Final_Report_20260915_v4.docx`, now containing the owner's completed identity/contact fields. Its current SHA-256 is `f0b59435bb6b25ab36fb41069d09109f910f7971ce476d53871ae653b35872fc`.
- The source and all identity/contact fields are preserved. The earlier Entry163 frozen source hash predates the owner's edits and must not be silently updated in the old manifest.
- Builder: `nebula/report/competition_reframe.py`; before/after source manifest: `output/docx/Nebula_Competition_Report_20260915_Final_sources.json`.

## Editorial changes

The abstract, opening contribution summary and conclusion now lead with the working target-to-circuit flow, automatic rejection/recovery, physical exports and programmable receiver extension. Page 2 explicitly connects the work to all three judging criteria. Engineering sections foreground measured design choices, coverage progress and next qualification milestones.

S3 is labeled Partial coverage rather than Failed, with the same 4/12 demonstrated targets and an explicit statement that the full on-demand range is not met. This is a presentation label, not a specification pass or new result. The only changed table cells are this label and its adjacent evidence wording. All numerical results, 12 figure assets and three native equations are preserved.

Material scope remains explicit: ideal behavioral DFE for the 315-condition gate, separate nominal transistor receivers, independent reference ownership, signed model-domain findings, rejected noise instrument, outstanding receiver HD3/PVT, no demonstrated RL speed advantage or near-optimality, and no routed-area or BER claim. The report does not claim that the companion video has already been recorded.

## Verification and scope

Five focused document checks pass in 0.396 s using `python -m nebula.report.check_competition_reframe` in the managed document runtime. They cover source/output hashes, identity preservation, allowed table edits, identical figure/equation assets, required scope statements, page count and figure order. The older presentation check's source-hash failure reflects the owner's subsequent identity edits, not damage to the source.

Documents skill workflow used: isolated canonical render, individual full-size inspection of all 12 pages, then final page-2 revision and reinspection. Final PNGs for pages 1 and 3-12 are byte-identical to the individually reviewed first render. Final render is `tmp/academic-closeout/competition-report-final/`. Layout is clean and remains within the 10-12-page requirement.

No app, circuit, scientific evidence, existing report or existing demo was edited. No simulation, training, full regression, packaging, commit, push, email or submission occurred. Recording and submission remain owner actions. Use the new Final DOCX, not the preserved intermediate competition edition.
