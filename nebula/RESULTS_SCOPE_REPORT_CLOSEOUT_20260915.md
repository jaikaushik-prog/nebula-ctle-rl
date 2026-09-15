# Results first report revision

The owner approved replacing repetitive self-assigned S1-S9 status labels with demonstrated results and verification scope. The current report is `output/docx/Nebula_Competition_Report_20260915_Final_v2.docx`.

- 12 pages; 4,134 whitespace-delimited words including tables.
- SHA-256: `55d8d8dd4c684d2ddc7187cb955e4573a7c389996cd4f423ed77bc1febedbdda`.
- Source Final DOCX preserved at SHA-256 `0c10e6dcadcc31b19d2f6aa86debc14485f7fa50ac51cfc788ec631dbd832349`.
- Source manifest: `output/docx/Nebula_Competition_Report_20260915_Final_v2.sources.json`.
- Reproduction and focused checks: `nebula/report/results_scope_revision.py`; use `--check` for read-only integrity checking.

Page 1 now has a results-first introduction and S1-S9 table without repeated Partial evidence or Verified pass verdict labels. It preserves precise measured values and circuit ownership. S3 retains 3/12 to 4/12 progress and incomplete full-range coverage. S4-S9 distinguish CTLE, ideal DFE, nominal transistor receiver and independent reference evidence. The unnecessary full PCIe protocol disclaimer is removed. Page 2 adds one concise qualification roadmap. No RL speedup or new specification pass was claimed.

The Documents skill render/inspect workflow was completed. The first render exposed one split Architecture label and a qualification paragraph using the wrong font size; both were corrected before delivery. All 12 final pages were individually inspected at full size. The final table stays on page 1, typography is consistent, and no clipping or overflow was found. Final PNGs/PDF for internal QA are under `tmp/academic-closeout/results-scope-final/`.

Focused structural checks passed before and after the layout correction: source and identities unchanged; every unrelated table and paragraph unchanged; exact requested revised table present; all 12 figure assets and three native equations unchanged; material model-domain and RL benchmark qualifications retained. Page count and all page images checked separately. The initial marker invocation used a missing remembered path; the actual installed marker was located and ran successfully once before authoring.

No app, circuit, simulation evidence, existing report or existing demo was edited. No simulation, training, full regression, packaging, commit, push or submission occurred. The new document is a presentation revision, not additional scientific verification. Owner recording and submission remain outstanding.
