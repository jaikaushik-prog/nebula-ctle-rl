# Entry 100 - frozen product-readiness audit (2026-09-06)

Approved by the owner: fix area accounting/claims; verify one exported circuit;
repeat DFE sensitivity; clarify organiser scope; check request accuracy.

No topology, parameter bounds, reward, selector heuristic, training, or FINAL
test changes. This is a product diagnostic, not a fresh RL generalisation claim.
Frozen input: current committed `product_demo/rl_hybrid_9db_1p9ghz/design.json`
and `design.cir` (Entry 99, setting 425). The runner records their hashes and
checks every fresh deck has identical circuit geometry, values and switch
states, allowing only process, temperature, supply and measurement stimulus.

## Measurements and stop rules

- Inventory every exported top-level component. Count OFF attenuator branches
  and parallel multiplicities. Do not multiply total MOS width by finger count.
  Separate gate/body/plate proxies from cell area. Cbyp, bias generation, DFE,
  selectors and layout overhead remain unknown where unimplemented. No guessed
  overhead multiplier and no full-area pass.
- Fixed code at all 45 mandated PVT corners and the existing one design load.
  Run one full AC/noise/swing/operating-point HD3 measurement per corner, plus
  the existing checklist's 100 MHz HD3 test: **90 SPICE calls maximum**. Reuse
  each AC-derived link response for seven constructed channels. Record failures;
  do not switch codes to rescue them. S7 remains partial even if model rows pass.
- From the same pulse response, use the existing ideal/no-tap/20%-misadapted/
  nominal 4-bit-quantised policies. The ideal control must reproduce bridge
  height and width to 1e-9; otherwise that condition is uninterpretable. Missing
  conditions cannot become a full pass. This does not model DFE error propagation,
  jitter, timing closure, analog feedback parasitics or receiver area/power.
- Replay the actual frozen actor and current selector at 12 requests:
  {3, 6, 9, 12} dB x {1.25, 1.9, 2.5} GHz, all 315 channel/PVT conditions.
  Zero new SPICE for this part. Record refusals and actual errors, not only
  accepted requests. Do not tune against these results or change the ±1.5 dB /
  ±0.3 octave pass tolerances.
- Exclusively created output directory and flushed per-corner/request journals.
  Integrity failure stops attribution. Completed circuit failures remain failures.

## Predictions recorded before fresh simulation

1. The counted geometry subtotal will exceed the old 0.001677 mm2 passive proxy,
   but cannot establish S7 without missing implementations and layout.
2. The fixed setting will pass fewer than the adaptive map's 315 conditions;
   peaking/frequency drift is the likely cause. Report the actual failing rows.
3. Removing the ideal DFE will shrink some eyes. Whether every fixed-circuit
   condition still passes is unknown; do not borrow Entry 39's older answer.
4. 9 dB / 1.9 GHz will reproduce the shipped selector result; the high-peaking
   rectangle boundaries will retain coverage gaps.

The organiser question is prepared separately and is not sent without an official
contact. Freeze a transparently scoped demo after the audit, not a claim that all
competition requirements are complete. Any hardware redesign needs a new decision.
