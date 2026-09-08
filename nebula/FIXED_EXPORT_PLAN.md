# Entry 102 - fixed-robust product export

PAUSED 2026-09-06: owner prioritised physical Iref and bypass-capacitor area.
No fixed-export implementation or new verification run was completed. The
fail-first test specification is preserved in `plans/test_fixed_export.py.pending`
outside collection until this feature resumes; it imports an unimplemented module.

Owner approval: 6 September 2026, "lets do these" after the ordered closure plan.
This entry implements the first gate, not new RL training or new circuit topology.

- Keep adaptive mode and all immutable historical demos/results unchanged.
- New explicit `fixed-robust` mode takes the intersection of feasible codes over
  all 45 PVT points and seven existing channel views. No intersection means refusal.
- Keep the existing nominal selection if it belongs to the intersection;
  otherwise use the lowest code in the intersection. This deterministic fallback
  is classical, not credited to RL and not claimed optimal. No reward, bounds,
  target tolerances or bank rows change. The 9 dB/1.9 GHz intersection is [490].
- After one captured nominal export, reuse Entry 100's unchanged identity,
  two-HD3-tone and DFE instrument at all 45 corners: maximum 91 SPICE calls for
  the one integration demonstration. No bypass-changing retries, retuning,
  failed-row replacement or expansion to extra simulations after a failure.
- Pending bank eligibility is not a fresh verification pass. Store the exact
  deck and incremental raw audit journal, verify invariant circuit signatures,
  and show both model failures and incomplete receiver scope honestly.
- The web UI offers adaptive/fixed modes; its fixed choice includes the fresh
  audit in the background worker. Old cached Judge evidence stays labelled cached.
- Acceptance: new fail-first tests; full before/after suite; one new exclusive
  9 dB/1.9 GHz end-to-end output; inspect JSON/deck/schematic/API/evidence ZIP.

Remaining closure gates (not silently authorised design assumptions): organiser
clarification for DFE, electrical programmability and full area/power; coverage
expansion requires a separately frozen experiment. Slides/video/final release
should describe the final accepted scope, not claim these gaps are resolved.
