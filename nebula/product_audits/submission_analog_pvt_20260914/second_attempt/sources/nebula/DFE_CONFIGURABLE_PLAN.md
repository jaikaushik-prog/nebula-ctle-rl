# Entry 132: first connected configurable-Rs/Cs transistor CTLE + DFE gate

Registered 2026-09-10 after Entry 131 completes both fine-control maps.
Use its selected N500/no-fixed-MIM physical circuit and the measured primary
identity: R control .7 VDD, C control .165 VDD, measured standalone boost
8.909067327 dB and peak 1.857653018 GHz for the requested 9 dB/1.9 GHz point.
No interpolation, device resizing, ideal R/C replacement or geometry retuning.

Start from the exact Entry 125 B.deck(length=4) transistor CTLE+CML summer,
master/slave decision memory, real current DAC and four discharge transistors.
For the new circuit replace only Xrs/Xcs with the measured physical network,
remove their obsolete fixed-value metadata and add external R/C voltage
sources. Keep every old MOS/resistor, input attenuator, bias reference,
common-mode source, 32.628 fF assumed output load and clock waveform unchanged.
Use the unmodified full PDK needed for official varactors; pin its closure.
Default transient solver settings remain those of the verified DFE, not the
tighter serial-DC options: this experiment has no inter-step DC drift gate.
This must first pass an unchanged-fixed-DFE full-library calibration.

Maximum SEVEN sequential ngspice_con processes, 180 s each, no retries:

1. Fixed-Rs/Cs DFE calibration, TT/1.8 V/27 C, constructed 7.5 dB channel,
   phase 1 UI, DAC code 2, normal sign. Require the old complete signal gate
   and agreement with Entry 125 nominal result: eye within 1e-6 V, VDD power
   within 1e-9 W, positive-eye width within 0.005 UI, identical 64/64 bit count.
   Stop after one call if calibration fails.
2. New configurable circuit, same TT/channel/control settings and code 2,
   normal sign, at phases 1, 1.25, 1.5 and 1.75 UI. Retain all four calls.
   Choose the passing phase with largest sampled eye; earlier phase on ties.
   Stop after five total calls if no phase passes.
3. At that phase run minimum-current code 0/normal sign and code 2/reversed
   sign. Both must be valid measurements and the normal code-2 sampled eye
   must exceed each by more than 1e-6 V. Code 0 is NOT feedback-disabled:
   the retained real tail bleeders cause residual feedback.

Use the same finite noiseless 80-bit pattern (16 warmup, 64 scored), causal
constructed channel and existing stimulus/clock/bit/eye/power analyzers.
Required gate: correct master/held/previous decision for all 64 bits,
positive sample margins, sampled eye >100 mV, positive-eye width >0.4 UI,
0<VDD CTLE+DFE power<15 mW, strict signed new-DFE transistor audit, and the
unchanged whole-circuit magnitude/body envelope. No signed voltage clipping,
terminal swapping or relaxation of the established DFE gate is permitted.

Extend raw trace with R/C source voltage/current and actual gate/varactor
control nodes; regenerate full MOS-terminal list to include the new switch.
Require external control errors <=1e-8 V. Check all time samples of varactor
source/control voltages in [0,1.95] V and absolute difference <=2 V; retain
the exact signed new-switch audit separately. Report control ripple and
external R/C source net and positive power separately, alongside existing
clock/tap/common-mode/source accounting. Model-envelope passes are not
foundry reliability signoff, passive distortion or leakage verification.

Pin and verify complete Entry 131 raw evidence and Entry 125 gzip evidence;
pin every old/new scientific source and external PDK dependency. Tests first,
focused/full regression and local freeze before one run into
`product_audits/entry132_dfe_configurable_20260910/`. Retain every failure,
raw trace and terminal file; lossless gzip siblings may be added afterward
with the existing verified archive tool, without deleting raw originals.

This is one operating point/channel at TT. It does not transfer the old
fixed-passive 135/135 PVT result to this new circuit, demonstrate switching
settling, validate the other eight tuning identities under DFE loading,
establish noise/HD3/BER or constitute routed/full-receiver signoff. Later
target/PVT/dynamic tests require separate bounded registration based on this
result. No SPICE or training is launched for report-only work, no frozen RL
source or held-out experiment is changed, and the old PDFs stay untouched.
