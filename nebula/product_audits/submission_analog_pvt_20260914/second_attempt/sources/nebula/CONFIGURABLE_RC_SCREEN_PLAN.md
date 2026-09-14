# Entry 128: physical voltage-configurable Rs/Cs CTLE screen

Registered 2026-09-10 under the owner's authorization for bounded hardware
implementation experiments. Entry 127 is running while this instrument is
prepared. Its completed TT result motivates carrying capacitor loss into an
actual CTLE; its full results must be preserved before this screen starts.
Freeze this plan, source and tests after regression, before any new SPICE.

## Circuit and boundaries

Keep the verified physical CTLE core, attenuator, reference and output load.
Replace only the drawn source-to-source Rs/Cs section in a NEW circuit:

- Rs: one real poly Rmax in parallel with a real poly plus one standard
  SKY130 NMOS W=80/L=.15/nf=2. Its gate is voltage-controlled, not an ideal
  switch. Rmax and desired low endpoint come from hash-gated Entry 81/96;
  subtract the measured Entry 95 TT/.5 V W80 Ron when drawing the branch.
  This subtraction is a nominal sizing estimate, not measured variable Rs.
- Cs: two official cap_var_lvt arrays to a shared control node, plus an
  optional fixed source-to-source MIM capacitor. Each unit is W5/L.5/vm1;
  use native m only after Entry 127 complete-cell calibration passes.
- Each external control feeds a physical 10 kohm poly resistor. Add a
  physical 1 pF gate bypass and 10 pF capacitor-control bypass. External
  control generators themselves are not implemented. Fixed geometry is
  unchanged across every voltage setting for a given candidate.

Nine candidate geometries: 100/250/500 varactor cells per side crossed with
0/1.5/2.5 pF fixed MIM. They are architecture screening alternatives, NOT nine
runtime-selectable geometries. One candidate contains only its own devices.
No resistor/switch/varactor model is redeclared or copied; use the complete
unmodified external SKY130 library and hash all 319 include dependencies.
No frozen RL, production registry, old fixed export or PDF changes.

This first screen is standalone CTLE AC/DC at TT/1.00/27. It retains the
original assumed 32.628 fF output load; it does NOT include the DFE input
loading or establish connected DFE performance. Those require a later
registered transient/linearity/PVT integration stage.

## Fixed membership, budget and gates

Maximum TEN ngspice_con calls, one at a time, 60 s each, no retries:

1. One calibration: wrap the unchanged fixed CTLE in the same subcircuit
   interface used for the new candidates, using the full official library.
   Reproduce all 251 saved TT AC magnitude samples from 1 MHz to 100 GHz
   (50/decade), absolute error <=1e-6 dB; frequency rtol1e-12. Fail/timeout
   stops here. Original baseline file and manifest hashes are checked.
2. Conditional on calibration, one call for each of the nine geometries.
   Each call has 81 independent copies at the Cartesian product of external
   R fractions (0,.4,.45,.5,.55,.6,.7,.85,1) and C fractions
   (0,.05,.1,.15,.2,.3,.4,.6,1), times 1.8 V. One extra unchanged fixed CTLE
   is a same-deck calibration control. All nine calls are retained even if
   some fail; no replacement calls or geometry changes within this run.

The isolated copies share model definitions, not electrical nodes or supply
currents. Save both complex output voltages and differential input primitive
for every copy, all drawn MOS terminal DC voltages, and each copy's supply
current. Require exact finite vector counts/frequency axes, input AC=1, valid
external biases, positive measured VDD power <15 mW, and magnitude/body
voltage envelope checks. Parse and reject silent simulator errors.

Compute response in Python, outn-outp divided by measured input. Reuse the
checked log-frequency peak interpolator; retain edge/no-peak outcomes as
failed response rows, not guessed peaks. An AC-spec row requires an interior
peak, boost 3..12 dB and peak frequency 1.25..2.5 GHz as well as the above
electrical checks. There is NO fitted-target tolerance or optimization claim.
Report every valid/failed row, response range and finite differences when
one control is changed while the other stays fixed. Do not automatically
claim full rectangular coverage or promote a geometry to production.

Save the exact signed D/G/S/B audit for every MOS with the existing unchanged
audit code. In particular, the bilateral resistor NMOS can have negative
drawn Vds and its off gate can have negative Vgs. These are REPORTED model-
domain qualifications, NOT silently swapped/clipped voltages or a claim of
documented-range signoff. Ngspice's BSIM4 evaluator explicitly implements a
reverse mode, but that is not foundry validation outside documented ranges:
https://raw.githubusercontent.com/ngspice/ngspice/master/src/spicelib/devices/bsim4/b4ld.c
https://skywater-pdk.readthedocs.io/en/main/rules/device-details.html
The frozen new-DFE strict signed gates remain unchanged. Existing Entries
95--97 remain failed under their own gates; this is a different topology
and an amplifier screen, not a retrospective relaxation of those gates.

Geometry is a netlist-derived subtotal including new control feed/bypass,
not layout area. Varactor substrate leakage/breakdown, generic-poly voltage
nonlinearity, mismatch, passive corners, noise/HD3, runtime settling, full
receiver power and clock/control generation are not verified by this screen.
All source snapshots, raw files, failures, wall time and hashes are retained.
