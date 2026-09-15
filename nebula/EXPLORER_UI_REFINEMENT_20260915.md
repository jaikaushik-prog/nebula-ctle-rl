# Design explorer refinement

The Design explorer now presents one selected circuit followed by an ordered set of full-width evidence panels. This is a presentation-only change requested after the programmable panel repeatedly appeared unavailable in the owner's browser.

## Changes

- The selected circuit heading, setting identity and Compare eyes / Circuit files actions share one aligned header. A short visible sentence states fixed Rs/Cs and behavioral DFE scope.
- The 512-setting catalogue explanation and exact netlist/evidence ownership are grouped under Selection and verification scope. The facts remain available without a long introductory text block.
- Inspect the exact generated CTLE drawing spans the full workspace width whether collapsed or expanded.
- Selected CTLE + transistor DFE is now its own full-width disclosure. Four measurements use an aligned definition list; conditions, verification scope and measured circuit files have separate, clearly labeled sections. The 0.720 UI positive aperture and 0.675 UI above 100 mV remain distinct.
- Independent transistor receiver evidence uses the same white surface, border, spacing, title/subtitle treatment and cyan expand control. Its independent 9 dB / 1.9 GHz scope remains explicit; the nested heading is Calibrated receiver checkpoint.
- The new programmable prototype panel and its automatic fetch are removed from the explorer. Its source, raw results, device drawing, read-only API and optional export implementation remain preserved. No failed scientific result was erased, and no accepted circuit was changed.
- Existing Aptos/Segoe typography, navy text, blue borders and cyan actions are retained. Mobile headers wrap text alongside the expand control; measurements reflow to two columns. Keyboard focus remains visible.

## Checks

Baseline focused tests: 16 passed in 2.67 seconds. Final focused union: 35 passed in 3.84 seconds. No full regression or scientific campaign was run.

Browser checks passed at 1440x1000, 1280x900 and 390x844. All three evidence panels have identical full widths and white summary backgrounds. All five selected receiver artifact links return 200. Expanding/collapsing the drawing, receiver, reference and scope sections works. Switching to the unrelated failed saved run hides the selected nominal receiver. No JavaScript errors, page-level horizontal overflow, non-GET requests or programmable-evidence requests occurred. Screenshots were inspected for the desktop header, collapsed list, expanded receiver, generated drawing, independent reference and mobile receiver.

Implementation: `nebula/web/static/explorer_refinement.css`, `index.html`, `judge_evidence.js` and `app.js`. Tests: `nebula/tests/test_explorer_refinement.py` and updated scope-label assertions in `test_web_recovery_clarity.py`. Browser result: `tmp/academic-closeout/explorer-refinement.json`.

The frontend-design skill informed the common palette and typography, left-aligned circuit hierarchy, full-width disclosures and final screenshot critique. No new font, image generation, animation or external dependency was added.

## Current presentation note

Open http://127.0.0.1:8766 and use Ctrl+F5 once to load the new versioned assets. The programmable panel is intentionally absent. The earlier optional programmable presentation note should use the report/evidence fallback, not refer to a visible explorer panel. The academic v2 report was not edited during this UI-only change; its scientific results remain unchanged, but its earlier UI description and screenshot predate this cleanup. The original report and all prior source manifests remain preserved.
