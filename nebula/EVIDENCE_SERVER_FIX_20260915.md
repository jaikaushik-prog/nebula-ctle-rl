# Saved-evidence loading correction — 15 September 2026

The owner confirmed the failing browser URL was http://127.0.0.1:8765/#results.
Process inspection found the original `py -3.13 -m nebula.web` server on8765
and the recovery server on8766. Both serve the same static UI, but the original
handler has no `/api/submission/*` routes. Its static-file fallback returns
`File not found.` The current recovery server returns the evidence correctly.
This was not missing programmable experiment data or a failed integrity review.

Open http://127.0.0.1:8766/#results. The original server remains available;
no process was terminated or scientific job started. Its UI now explains the
missing capability and links to the current server when a submission request
returns404 on localhost8765. No automatic navigation or cross-origin data
substitution occurs. Other loading failures display HTTP details and offer a
same-origin, read-only retry. No backend or acceptance logic was changed.

The Entry161 programmable explorer panel removal remains in effect. Its source,
API, optional exports and saved results are preserved. Run files' loaded-tuning
diagnostics describe the independent reference, not the Entry160 selected-derived
prototype. The latter's nominal measurements are in academic report v2 page8.
Implementation exists; complete receiver verification remains future work.

Baseline26 focused tests passed. After implementation29 passed in3.21s.
An intermediate test failed solely because its expected stylesheet version was
v2 rather than the deliberately updated v3; its assertion was updated.
Browser checks exercised both actual ports at1440x1000 and1280x900, all11
evidence-table artifact links on8766 (HTTP200), a simulated503 diagnostic error
and successful retry, no page errors, no non-GET requests and no horizontal
overflow. Screenshots of both servers were inspected; guidance is legible,
and the correct app has no added banner. Results:
`tmp/academic-closeout/evidence-loading-check.json`.

Recommended remaining priorities, not executed by this repair: concise prototype
discovery under Run files (not promotion to primary), align final report/demo
presentation with the current UI, verify the short saved-evidence demonstration,
complete identity fields and record the required video. Do not pursue unbounded
PMOS/PVT, BER, layout or RL retraining before the deadline.
