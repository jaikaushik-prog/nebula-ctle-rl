# Entry 108: approved targeted buffer-drive experiment

Frozen 2026-09-06 before implementation and measurement. Owner approved four
combinations: first-stage buffer PMOS total W=8/16 um and second-stage buffer
NMOS total W=8/16 um, keeping the decision core and memory at 4 um. Maximum
49 calls. This is a standalone DFE building-block experiment, not integration.

## Exact circuit delta from Entry 107 width 4

For BOTH x and y paths, independently choose the same registered pair (P1,N2):
(8,8), (8,16), (16,8), (16,16), all in microns. Only these four instances change:
`Xbuf_x1_p`, `Xbuf_y1_p` use P1; `Xbuf_x2_n`, `Xbuf_y2_n` use N2.
All first-stage buffer NMOS and second-stage PMOS stay W=4 um. Core and memory
remain exactly Entry 107 width 4, including tail W=8 um. Every MOS L=.15 um,
nf=W/2; W remains total width, not per-finger width. Connectivity is unchanged.

The saved Entry 107 waveforms motivate stronger first-stage pull-up and
second-stage pull-down, but these are proposed starting choices, not guaranteed
fixes. Added input capacitance can slow the raw decision, so its original check
must also pass. No new ideal elements, PDK model cards, clock or current source.

## Frozen measurement and selection

Reuse DFE_HARDWARE_PLAN / DFE_BUFFER_PLAN stimuli and gate without alteration:
5 GHz external clock, 2 ps edges, 96 ps high plateau, 1 ps maximum step,
36 bits / 4 warmup / 32 scored, LinkConfig.seed=1, +/-50 mV differential input,
Entry 105 measured/hash-verified output common mode at the matching PVT point.
Raw polarity checked throughout 88-98 ps, held complementary output throughout
110-190 ps after each evaluation edge, same VDD/2 decoding. No relaxed threshold.

1. Evaluate all four pairs at TT / 1.00 supply / 27 C, in the order above.
2. If none passes the COMPLETE raw-plus-held gate, STOP at four calls.
3. If multiple pass, select smallest P1+N2 (smallest gate W*L subtotal); tie
   break lexicographically by (P1,N2). Do not use eye/power bonuses or change RL.
4. Run that ONE unchanged circuit at all 45 specified PVT points, including
   nominal. Keep every failure. No per-corner adjustment or later reselection.
5. At most 49 fresh calls total. No retry, fifth pair, phase adjustment,
   input-amplitude change or further hardware variant after seeing outcomes.

The nominal gate is a feasibility screen; it is not a PVT/receiver pass.
Exact MOS-instance signature must stay fixed throughout the selected sweep.
Capture main and buffer-node traces; malformed/missing data is a failed run.
Keep DUT VDD, external clock net/positive supplied, and input-source power
separate. Count every MOS W*L once, with full layout area explicitly unknown.

## Evidence and unchanged scope

Tests first, including exact four-device delta, rejected unapproved pairs,
legacy-render preservation, complete-gate selection and failed-run retention.
Full software suite before/after. New exclusive output folder, source/plan
snapshots, raw decks/logs/waveforms, per-bit records, source provenance and hashes.
Reuse the existing renderer, stimulus, gate, PDK and invocation helpers; no
duplicate model or redefined measurement. Old experiment defaults remain intact.

Rs/Cs, CTLE, bias, RL, product/UI, cached demo and report are untouched. A pass
would establish decision/hold under these tests, NOT a complete transistor DFE.
Causal previous-bit feedback, summing/tap control, connected CTLE loading,
clock generation, mismatch/dynamic noise, full receiver eyes/power/area remain
separate work requiring appropriate fixed plans. Preserve all prior failures.
