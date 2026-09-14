# Entry 125: inactive DAC tail-node discharge recovery

Registered 2026-09-09 under the owner's bounded hardware-development authority.
Entry 124 is complete: 58 calls, 1328.832334 s, 44/45 electrical-function PVT
passes and 64/64 correct decisions at all 45 points. FS/0.95/125 fails the
UNCHANGED strict signed voltage gate: inactive Xdfe_tail3 reaches Vds=-2.45106
mV. Its source floats near 0.705 V while fd_common falls to 0.702914 V.
Excursions occur from about 744 to 15605 ps, not only during initialization.
Its eye is 109.683 mV and power 8.60877 mW; those passing metrics do not waive
the voltage failure. The original raw failure and all 58 cases stay immutable.

## Exactly two hardware candidates

Keep the entire Entry 124 physical CTLE, CML summer/latches and switched DAC.
Add four standard SKY130 NMOS, one from each fd_tail{k} to ground, with gate
connected to the EXISTING physical df_nbias and grounded body. W=0.42 um,
nf=1; candidate L=4 um or L=2 um, the SAME length for all four devices.
No ideal resistor/current source, new ideal bias, model redefinition or
source/drain swapping. The weak always-on devices provide a discharge path
when a current branch's enable switch is off. Real capacitance/loading and
extra current are included. Existing transistor sizes and loads do not change.

IMPORTANT: code 0 is now the minimum-current code, NOT feedback disabled.
The bleeders permit residual feedback current even with all enables low.
Matched comparisons must be called minimum-code and reversed-polarity
controls. Never relabel this new baseline as a zero-DFE/no-feedback result.
The original Entry 124 disabled-code comparison remains separate evidence.

## Membership (maximum 57 calls)

1. Eight code-2/sign+1/phase-1.0/7.5-dB screens: L=4,2 um, each at
   TT/1.00/27, FS/0.95/125, SS/0.95/125, FF/1.05/0.
2. For EACH length passing every screen, two TT/7.5 controls at phase 1.0:
   code 0/sign+1 and code 2/sign-1. Require both instrument/voltage-valid.
   Candidate code-2 sampled eye must exceed BOTH controls by >1 uV.
   Choose the longest qualifying length (weakest discharge device). If
   neither qualifies, stop: no hidden candidate, code, phase or retry.
3. One fixed selected length, code 2/sign+1/phase 1.0, all 45 PVT at 7.5 dB.
   Keep every failed case. Maximum=8+4+45=57 calls; actual calls are billed.

All Entry 124 logic, input, power, exact signed NEW-device voltage checks
and whole-circuit magnitude/body gates remain mandatory. New bleeders are
included in both transistor audits. Old reverse-Vds findings in the legacy
PMOS attenuator remain explicitly visible, not signed-domain passes.

Use the aperture measurement specified in DFE_TIMING_PLAN.md: positive-eye
width >0.4 UI in addition to sampled height >100 mV. This is a 64-history,
noiseless waveform aperture, NOT BER or phase-sweep robustness. Preserve
the original 80-bit pattern, seed, PWL, 1 ps maximum step, 16.8 ns duration,
clock levels and power accounting. `set wr_singlescale` removes repeated
time columns ONLY; no solver sample or terminal is discarded. Strict parser
requires expected column counts and matching monotonic finite time axes.

Freeze plans, source and tests before SPICE. Verify Entry 124 original and
gzip hashes before reuse. Store new exclusive artifacts, complete source
snapshots, raw failures and manifest; gzip siblings preserve exact bytes.
No second experiment or pytest/SPICE overlap. Original reports, fixed-passive
product/registry and frozen RL are untouched. A pass permits Entry 126's
separate channel retiming test; it does not finish receiver signoff or Rs/Cs.
