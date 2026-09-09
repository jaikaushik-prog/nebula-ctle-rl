# Entry 126: channel timing and finite-pattern eye aperture

Registered 2026-09-09 under the owner's bounded hardware-development authority.
Entry 124 remains immutable. Its nominal 7.5 dB connected circuit passes
64/64 bits and improves sampled eye from 195.189 to 237.762 mV with DAC code 2.
Its 12 dB diagnostic fails at the SAME external clock phase (15/64 bits).
Read-only raw-waveform diagnosis shows that the 12 dB CTLE output arrives
later: outn-outp at offsets 1.25 and 1.5 UI has 64/64 correct signs, whereas
offset 1.0 has 32/64. This is a timing hypothesis, not a corrected SPICE pass.
Entry 124 finished at 44/45: an inactive DAC branch fails its strict signed
voltage gate at FS/0.95/125, despite 64/64 bits there. Entry 125 must first
pass all 45 PVT with its physical discharge-path recovery. This stage must
not run unless that prerequisite and its exact raw/source hashes verify.

## Unchanged hardware and assumptions

Keep the exact Entry 125 verified geometry: Entry 124 CTLE, CML summer,
W=8 latch pair, all four DAC branches/loads PLUS the four physical bleeders
at the ONE length selected by Entry 125's frozen rule. Fixed positive
feedback wiring polarity, code 2, is the candidate. Code 0 and reversed
code 2 are matched controls, not new transistor sizes. Code 0 has residual
feedback through the bleeders: call it minimum-current, NOT disabled.
No Rs/Cs change, ideal feedback or reference-bit injection.
External clocks may have a different phase for different known constructed
channels; they stay at 5 GHz with the same voltage levels and edge times.
This is NOT a fabricated CDR or automatic clock-recovery demonstration.
No per-PVT adjustment of clock phase, code or hardware is permitted.

Keep the Entry 124 80-bit pattern (64 scored, LinkConfig seed 1), original
TX swing/de-emphasis, 128 samples/UI channel input, 16.8 ns stop, maximum
transient step 1 ps, and all its logic/power/instrument/voltage gates.
Entry 125's only output-format change is ngspice `set wr_singlescale`: write the
shared time axis once instead of repeating it beside each vector. Retain
every adaptive solver sample, the same 15-digit values and every terminal.
No `linearize`, decimation, precision reduction or transient retuning.
The documented command is in the official ngspice control-language tutorial:
https://ngspice.sourceforge.io/ngspice-control-language-tutorial.html
Both output files must have the exact expected column count, finite data,
strictly increasing time, and identical time axes.

## Finite-pattern eye aperture

For each scored bit, interpolate the measured sum_p-sum_n waveform onto
offsets -0.5..+0.5 UI around that bit's clock edge, spaced by 0.005 UI.
Reject incomplete/nonfinite traces and gaps >2 ps. Use the minimum positive
symbol level and maximum negative symbol level over ALL 64 scored histories.
The aperture is the contiguous interval containing -0.025 UI (the middle
of the original pre-edge sampling window) where both absolute signs are
correct and the eye height is positive. Report its grid-conservative width;
also report the narrower aperture where height exceeds 100 mV. Report if
either interval reaches a scan boundary, in which case it is a lower bound.
New gate: positive-eye aperture >0.4 UI, in addition to Entry 124's sampled
height >100 mV, correct master/held/previous decisions and <15 mW VDD power.
This is a finite, noiseless waveform aperture at one operating clock phase,
NOT a BER contour, clock-phase sweep guarantee, jitter/offset tolerance,
metastability test or all-history proof.

## Membership and stopping (maximum 95 new calls)

1. Three TT/12 dB calls at phases 1.25, 1.5, 1.75 UI, code 2, sign +1.
   Among calls passing ALL old and new gates, choose highest sampled eye;
   tie goes to earlier phase. If none pass, stop at three calls.
2. Two matched TT/12 dB controls at that phase: code 0/sign +1 and
   code 2/sign -1. Require both instrument/voltage-valid; candidate eye
   must exceed BOTH controls by >1 uV. Otherwise stop at five calls.
3. Ninety fixed-hardware calls: 45 PVT at 3 dB/phase 1.0, then 45 PVT at
   12 dB/the selected phase. Code 2/sign +1 for every point. Keep all
   failures; no hidden retry or per-corner selection. Max calls = 3+2+90.

The aperture definition is shared with Entry 125, which measures it during
its new fixed-geometry 7.5 dB sweep. Reuse that verified 45-PVT prerequisite
with its original simulator count and source/raw hashes; it is not 45 new
Entry 126 simulations. Count old and new simulations separately.
Even if all pass, coverage is three declared channel losses, NOT 315 cases
or arbitrary channels. Full noise/HD3 and configurable-passive integration
remain separate verification work. Existing reports/registry/RL stay intact.

## Preservation and voltage boundary

Freeze plan, source and tests in a local commit before simulations. Use an
exclusive output folder, run lock, source snapshots and SHA-256 manifest.
Retain exact gzip siblings and local raw originals. Simulator errors are
failures regardless of exit status. No mocks enter measurements.

All new DFE MOS must pass the exact signed model-domain checks. Keep the
whole-circuit signed audit, including bidirectional legacy PMOS attenuator
reverse-Vds findings; the whole-circuit magnitude/body envelope is an
additional gate, not a waiver or full model-domain signoff. External clock,
controls/common-mode, typical passives, unverified poly voltage coefficient
and geometry-only area boundaries remain. `full_receiver_verified` is false.
