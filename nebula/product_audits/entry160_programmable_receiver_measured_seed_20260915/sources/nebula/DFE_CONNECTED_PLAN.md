# Entry 124: transistor CTLE plus causal 1-tap feedback prototype

Registered 2026-09-09, under the owner's bounded hardware-development
authorization. Entry 123 has closed successfully: one 8 um CML latch pair
passes 45/45 PVT points, all 32 scored bits and exact signed terminal checks.
That result is standalone; it does not already prove the connected circuit.

## Fixed hardware

Use the hash-verified Entry 105 physical CTLE export (setting 490), including
its PMOS attenuator, physical bias, drawn fixed Rs/Cs and 32.628 fF testbench
loads. Do not change any of those dimensions or claim the old 315/315 count
for the new circuit. CML device/load/bias geometry is exactly Entry 123's
8 um design; its internal nodes get a unique prefix to avoid sharing the
CTLE's different bias voltage accidentally.

A new current-mode summing amplifier connects directly to the CTLE output:
two W=8/L=.15/nf=4 NMOS input devices, W=20/L=.5/nf=10 physical mirror tail,
and two W=1/L=1.33/m=1 poly loads (800.1471 ohm nominal). Its output drives
the first CML latch, so real input and feedback-device capacitances load
both the CTLE and the latch outputs. The summing stage preserves the
positive-symbol convention CTLE outn-outp -> sum_p-sum_n -> q-qb.

The feedback DAC is a real differential NMOS pair W=2/L=.15/nf=1 driven
ONLY by stored q/qb. Four parallel mirror-tail branches have total widths
1, 2, 4, 8 um, L=.5, nf=max(1,W/2). Each branch has a W=8/L=.15/nf=4 NMOS
enable switch to ground. Four external static digital control pins enable
these branches. Code changes switch actual currents; they do not resize or
remove transistors. The tested codes are 0, 1, 2, 4 and 8 (not all 16).
Two fixed wiring polarities are screened; programmable polarity circuitry
is not claimed. No ideal current source, decision, reference-bit injection,
or behavioral feedback term is inside the DUT.

Clock sources remain external: complementary VDD/3..2*VDD/3, 5 GHz,
10 ps rise/fall, 80 ps plateau. Physical clock/control drivers are not built.
The original external common-mode source remains a declared assumption.

## Stimulus, membership and selection (maximum 58 calls)

Use LinkConfig seed 1 and its unchanged 0.8 V differential peak-to-peak TX,
-3.5 dB de-emphasis and balanced minimum-phase constructed channel. The
amplitude/de-emphasis anchors retain their existing assumption boundary.
80 bits: four repeats of 00110101 followed by 48 seeded bits; first 16
warm up, 64 score. Two unscored copies of the last bit pad the waveform.
The TX and channel operate on a 128-sample/UI, 32768-point grid with existing
causality/passivity checks. Linear convolution, not circular bit-sequence
wraparound, generates the external PWL stimulus. It starts after 2 UI;
the transient lasts 84 UI = 16.8 ns, maximum step 1 ps.

1. Three TT/7.5 dB baseline calls, DAC code 0, at clock phases .5, .75,
   1.0 UI after each symbol boundary. Among instrument/voltage-valid calls,
   choose highest sampled analog eye, tie resolved by earlier phase. If no
   valid baseline, stop this experiment. Clock phase is then fixed.
2. Eight TT/7.5 dB calls: codes 1,2,4,8 x fixed polarities +1,-1. Require
   64/64 master/held/previous decisions, sampled eye >100 mV, correct input
   sign, VDD power <15 mW and the voltage gates below. A winner must improve
   sampled eye over both the code-0 baseline and the SAME code's opposite
   polarity by >1 uV. Choose highest qualifying eye; ties use smaller code,
   then positive polarity. Otherwise stop this experiment and retain failures.
3. For that ONE code/polarity/phase, two TT diagnostic channel calls at 3 and
   12 dB, and 45 fixed-geometry PVT calls at the primary 7.5 dB channel.
   Diagnostic channel failures remain explicit; no per-corner or per-channel
   tap tuning, extra phases, retries or hidden candidate expansion.

## Gates and precise scope

Verify the external PWL input, complementary clocks and four control levels
against the intended values. Reject missing/nonfinite/undersampled/truncated
traces, wrong vector axes and all unexpected simulator warnings.
Require correct master sign at +88..98 ps, held output at +110..190 ps,
and previous decision at -10..-1 ps. Compute the finite-pattern sampled
eye from minimum positive and maximum negative analog values in the last
9 ps before the edge. This is NOT a horizontal eye, BER contour, noise,
metastability, offset/mismatch or all-history guarantee.

Retain exact signed D/G/S/B audits for EVERY transistor. The new DFE devices
must all satisfy the existing signed model-domain gate, without clipping or
terminal swapping. Additionally require |Vds|,|Vgs| <=1.95 V and documented
body-source bounds throughout the entire connected circuit. The legacy CTLE
contains bidirectional PMOS attenuator switches; a signed reverse-Vds finding
must remain visible in the whole-circuit audit and is NOT reclassified as a
documented signed-domain pass. A signal-function pass with such a finding is
not complete model-domain or receiver signoff. No old CML failure is waived.

Measure combined CTLE/summer/latch/DAC VDD power. Separately report net and
positive supplied clock power, control-source positive supplied power, signal
source power and common-mode source power. Include all new drawn device and
resistor geometry in a subtotal; no routed layout claim. A DC operating-point
initialized transient is not a supply-ramp startup or lifetime test.

Full S3/S4/S5/S7/S8-horizontal and full-channel PVT must be remeasured after
final integration, including configurable Rs/Cs. Typical passives, noiseless
constructed channel, external clock/control/common-mode and generic-poly
nonlinearity limitations remain. `full_receiver_verified` stays false.

Freeze tested source and this plan before SPICE. Save every deck, raw trace,
log, source snapshot, selection decision and original SHA-256 manifest.
Archive exact gzip siblings without deleting local raw traces. No report,
production registry, reward, training or frozen RL result changes in this stage.
